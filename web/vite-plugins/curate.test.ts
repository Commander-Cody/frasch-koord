// @vitest-environment node
/**
 * Exercises createCurateMiddleware directly, with fake req/res objects and no
 * real HTTP server or Vite instance. Covers the M11 hardening of the POST:
 * the Content-Type gate, the known-field allowlist on a stored patch entry
 * and the oversized-body 413. And that an entry is stored only if it keeps the
 * patch contract (names/curate-patch.schema.json). The gates in front of every
 * route, and the 500 that never echoes the underlying error, are
 * devEndpoints.test.ts's.
 */
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createCurateMiddleware } from './curate.ts';
import { PATCH_FIELDS } from './patchFields.ts';
import { fakeReq, fakeRes } from './testHttp.ts';
import patchSchema from '../../names/curate-patch.schema.json' with { type: 'json' };

/** The endpoint the POST tests write to. */
const PATCH_URL = '/__curate/patch';

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
    const req = fakeReq({ method: 'POST', url: PATCH_URL, headers });
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

  const validEntry = {
    id: 'alkersem',
    line: 3,
    kind: 'settlement',
    name: 'Alkersem',
    de: 'Alkersum',
    action: 'skip',
  };
  const localEntry = { ...validEntry, action: 'local', slug: 'alkersem', lat: 54.7, lon: 8.5 };
  /** A valid entry per action of the schema, with every field the action may carry. */
  const fullEntries: Record<string, Record<string, unknown>> = {
    osm: { ...validEntry, action: 'osm', osm: 'way/1', wikidata: 'Q559369', note: 'the church' },
    local: { ...localEntry, polygon_km2: 2, note: 'gone since 1634' },
    skip: { ...validEntry, note: 'not a place' },
    clear: { ...validEntry, action: 'clear' },
  };
  const jsonHeaders = { 'content-type': 'application/json' };

  it('rejects a non-JSON Content-Type with 415, and appends nothing', async () => {
    const res = await post({ 'content-type': 'text/plain' }, JSON.stringify(validEntry));
    expect(res.status).toBe(415);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('accepts a same-origin JSON POST, storing only the known fields', async () => {
    const entry = { ...validEntry, action: 'osm', osm: 'node/1', evil: 'dropped' };
    const res = await post(
      { ...jsonHeaders, host: 'localhost:5173', origin: 'http://localhost:5173' },
      JSON.stringify(entry),
    );
    expect(res.status).toBe(200);
    const stored = JSON.parse(res.body) as { ok: boolean; entry: Record<string, unknown> };
    expect(stored.ok).toBe(true);
    expect(Object.keys(stored.entry).sort()).toEqual(
      ['action', 'at', 'de', 'id', 'kind', 'line', 'name', 'osm'].sort(),
    );
    expect(stored.entry.evil).toBeUndefined();
    expect(typeof stored.entry.at).toBe('string');

    const onDisk = await readPatchEntries();
    expect(onDisk).toHaveLength(1);
    expect(Object.keys(onDisk[0]).sort()).toEqual(
      ['action', 'at', 'de', 'id', 'kind', 'line', 'name', 'osm'].sort(),
    );
  });

  it('keeps every field the patch schema defines', async () => {
    // No entry has them all, each action having its own: the fields are
    // those of the entries together.
    for (const entry of Object.values(fullEntries)) {
      await post(jsonHeaders, JSON.stringify(entry));
    }
    const stored = (await readPatchEntries()).flatMap((entry) => Object.keys(entry));
    expect([...new Set(stored)].sort()).toEqual([...PATCH_FIELDS].sort());
  });

  it('sets `at` itself, whatever the caller sent', async () => {
    await post(jsonHeaders, JSON.stringify({ ...validEntry, at: 'forged' }));
    const [stored] = await readPatchEntries();
    expect(stored.at).not.toBe('forged');
  });

  it.each(patchSchema.properties.action.enum)('accepts the schema action %s', async (action) => {
    const res = await post(jsonHeaders, JSON.stringify(fullEntries[action]));
    expect(res.status).toBe(200);
  });

  it('rejects an action the schema does not list with 400', async () => {
    const res = await post(jsonHeaders, JSON.stringify({ ...validEntry, action: 'delete' }));
    expect(res.status).toBe(400);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('rejects a local entry of zero area with 400, and appends nothing', async () => {
    const res = await post(jsonHeaders, JSON.stringify({ ...localEntry, polygon_km2: 0 }));
    expect(res.status).toBe(400);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('names the field and the rule of the schema it breaks', async () => {
    const res = await post(jsonHeaders, JSON.stringify({ ...localEntry, polygon_km2: 0 }));
    expect(JSON.parse(res.body)).toEqual({
      error: 'polygon_km2: breaks exclusiveMinimum (curate-patch.schema.json)',
    });
  });

  it('rejects an entry without a field its action requires with 400', async () => {
    const res = await post(jsonHeaders, JSON.stringify({ ...localEntry, lon: undefined }));
    expect(res.status).toBe(400);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('names the field an entry lacks', async () => {
    // the schema finds a missing field at the entry, not at the field
    const res = await post(jsonHeaders, JSON.stringify({ ...localEntry, lon: undefined }));
    expect(JSON.parse(res.body)).toEqual({
      error: 'lon: breaks required (curate-patch.schema.json)',
    });
  });

  it('rejects an entry with a field of another action with 400', async () => {
    const res = await post(jsonHeaders, JSON.stringify({ ...fullEntries.osm, polygon_km2: 2 }));
    expect(res.status).toBe(400);
    expect(await readPatchEntries()).toEqual([]);
  });

  it.each([
    ['without an id', { ...validEntry, id: undefined }],
    ['with an empty id', { ...validEntry, id: '' }],
    ['with a line number for an id', { ...validEntry, id: 3 }],
  ])('rejects an entry %s with 400: frasch curate apply finds the row by it', async (_, entry) => {
    const res = await post(jsonHeaders, JSON.stringify(entry));
    expect(res.status).toBe(400);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('rejects an oversized body with 413 and destroys the connection', async () => {
    const req = fakeReq({ method: 'POST', url: PATCH_URL, headers: jsonHeaders });
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

  it('serves the entries stored so far', async () => {
    await post(jsonHeaders, JSON.stringify(validEntry));
    const req = fakeReq({ method: 'GET', url: PATCH_URL });
    const { res, done } = fakeRes();
    middleware(req, res, noopNext);
    req.end();
    const result = await done;
    expect(result.status).toBe(200);
    const body = JSON.parse(result.body) as { entries: unknown[] };
    expect(body.entries).toHaveLength(1);
  });
});
