// @vitest-environment node
/**
 * Exercises createCurateMiddleware directly, with fake req/res objects and no
 * real HTTP server or Vite instance. Covers the M11 hardening: the
 * Content-Type / Origin / Sec-Fetch-Site / loopback gates on `/__curate/`,
 * the known-field allowlist on a stored patch entry, the oversized-body 413,
 * and that a 500 never echoes the underlying error (which can hold an
 * absolute filesystem path).
 */
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import type { IncomingMessage, ServerResponse } from 'node:http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createCurateMiddleware } from './curate.ts';

/** A response, as seen by whoever called `.end()` on it. */
interface CapturedResponse {
  status: number;
  headers: Record<string, string>;
  body: string;
}

/**
 * Minimal fake IncomingMessage: a duplex stream (so `.on('data'/'end')` in
 * readBody works) plus the handful of fields the middleware actually reads.
 */
// Intersected with PassThrough (rather than cast to IncomingMessage alone) so
// tests can still call the stream's own `.end()`/`.destroy()` on the value
// createCurateMiddleware accepts as a request.
function fakeReq(opts: {
  method: string;
  url?: string;
  headers?: Record<string, string>;
  remoteAddress?: string;
}): IncomingMessage & PassThrough {
  const req = new PassThrough();
  return Object.assign(req, {
    method: opts.method,
    url: opts.url ?? '/__curate/patch',
    headers: opts.headers ?? {},
    socket: { remoteAddress: opts.remoteAddress ?? '127.0.0.1' },
  }) as unknown as IncomingMessage & PassThrough;
}

/**
 * Fake ServerResponse capturing status/headers/body. `done` resolves once
 * the handler calls `.end()`, the same point at which a real client would
 * see the response — every test awaits it instead of the middleware call
 * itself, since the middleware always returns before its async work is done.
 */
function fakeRes(): { res: ServerResponse; done: Promise<CapturedResponse> } {
  const headers: Record<string, string> = {};
  let resolveDone!: (v: CapturedResponse) => void;
  const done = new Promise<CapturedResponse>((resolve) => {
    resolveDone = resolve;
  });
  const res = {
    statusCode: 200,
    setHeader(name: string, value: string) {
      headers[name.toLowerCase()] = value;
    },
    end(body?: string) {
      resolveDone({ status: res.statusCode, headers, body: body ?? '' });
    },
  };
  return { res: res as unknown as ServerResponse, done };
}

const noopNext = () => {
  throw new Error('next() should not be called for a /__curate/ URL');
};

describe('createCurateMiddleware', () => {
  let dir: string;
  let worklistPath: string;
  let patchPath: string;
  let middleware: ReturnType<typeof createCurateMiddleware>;

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'curate-test-'));
    worklistPath = join(dir, 'curate.json');
    patchPath = join(dir, 'curate-patch.jsonl');
    middleware = createCurateMiddleware({ worklistPath, patchPath });
  });

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  /** POSTs a raw body with the given headers against a loopback caller. */
  function post(headers: Record<string, string>, body: string) {
    const req = fakeReq({ method: 'POST', headers });
    const { res, done } = fakeRes();
    middleware(req, res, noopNext);
    req.end(body);
    return done;
  }

  /** Reads back the appended patch lines, parsed. */
  async function readPatchEntries(): Promise<Record<string, unknown>[]> {
    const text = await readFile(patchPath, 'utf8').catch(() => '');
    return text
      .split('\n')
      .filter((line) => line.trim())
      .map((line) => JSON.parse(line) as Record<string, unknown>);
  }

  const validEntry = { line: 3, kind: 'settlement', name: 'Alkersum', de: 'Alkersum', action: 'skip' };
  const jsonHeaders = { 'content-type': 'application/json' };

  it('rejects a non-JSON Content-Type with 415, and appends nothing', async () => {
    const res = await post({ 'content-type': 'text/plain' }, JSON.stringify(validEntry));
    expect(res.status).toBe(415);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('rejects a cross-site Origin with 403, and appends nothing', async () => {
    const res = await post(
      { ...jsonHeaders, host: 'localhost:5173', origin: 'http://evil.example' },
      JSON.stringify(validEntry),
    );
    expect(res.status).toBe(403);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('rejects Sec-Fetch-Site: cross-site with 403, and appends nothing', async () => {
    const res = await post(
      { ...jsonHeaders, 'sec-fetch-site': 'cross-site' },
      JSON.stringify(validEntry),
    );
    expect(res.status).toBe(403);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('rejects a non-loopback caller with 403, even for a plain GET', async () => {
    const req = fakeReq({ method: 'GET', url: '/__curate/patch', remoteAddress: '10.0.0.5' });
    const { res, done } = fakeRes();
    middleware(req, res, noopNext);
    req.end();
    expect((await done).status).toBe(403);
  });

  it('accepts a same-origin JSON POST, storing only the known fields', async () => {
    const entry = { ...validEntry, osm: 'node/1', evil: 'dropped' };
    const res = await post(
      { ...jsonHeaders, host: 'localhost:5173', origin: 'http://localhost:5173' },
      JSON.stringify(entry),
    );
    expect(res.status).toBe(200);
    const stored = JSON.parse(res.body) as { ok: boolean; entry: Record<string, unknown> };
    expect(stored.ok).toBe(true);
    expect(Object.keys(stored.entry).sort()).toEqual(
      ['action', 'at', 'de', 'kind', 'line', 'name', 'osm'].sort(),
    );
    expect(stored.entry.evil).toBeUndefined();
    expect(typeof stored.entry.at).toBe('string');

    const onDisk = await readPatchEntries();
    expect(onDisk).toHaveLength(1);
    expect(Object.keys(onDisk[0]).sort()).toEqual(['action', 'at', 'de', 'kind', 'line', 'name', 'osm'].sort());
  });

  it('rejects an oversized body with 413 and destroys the connection', async () => {
    const req = fakeReq({ method: 'POST', headers: jsonHeaders });
    const { res, done } = fakeRes();
    const destroySpy = vi.spyOn(req, 'destroy');
    middleware(req, res, noopNext);
    // Comfortably over MAX_BODY (64 KiB); written as one chunk so the
    // 'data' handler sees the overflow on its very first call.
    req.end('a'.repeat(70 * 1024));
    const result = await done;
    expect(result.status).toBe(413);
    expect(destroySpy).toHaveBeenCalled();
    expect(await readPatchEntries()).toEqual([]);
  });

  it('answers a write failure with a generic 500 that does not leak the path', async () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {});
    // A patch path inside a directory that does not exist: appendFile
    // rejects with ENOENT, which is not the "missing file itself" case
    // readFile handles, so it falls through to the generic 500.
    const brokenPatchPath = join(dir, 'no-such-subdir', 'curate-patch.jsonl');
    const broken = createCurateMiddleware({ worklistPath, patchPath: brokenPatchPath });
    const req = fakeReq({ method: 'POST', headers: jsonHeaders });
    const { res, done } = fakeRes();
    broken(req, res, noopNext);
    req.end(JSON.stringify(validEntry));
    const result = await done;
    expect(result.status).toBe(500);
    expect(result.body).not.toContain(dir);
    expect(result.body).not.toContain('no-such-subdir');
    quiet.mockRestore();
  });

  it('still serves GET /__curate/patch for a loopback, same-origin caller', async () => {
    await post(
      { ...jsonHeaders, host: 'localhost:5173', origin: 'http://localhost:5173' },
      JSON.stringify(validEntry),
    );
    const req = fakeReq({
      method: 'GET',
      url: '/__curate/patch',
      headers: { host: 'localhost:5173', origin: 'http://localhost:5173' },
    });
    const { res, done } = fakeRes();
    middleware(req, res, noopNext);
    req.end();
    const result = await done;
    expect(result.status).toBe(200);
    const body = JSON.parse(result.body) as { entries: unknown[] };
    expect(body.entries).toHaveLength(1);
  });
});
