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
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createCurateMiddleware } from './curate.ts';
import { PATCH_FIELDS } from './patchFields.ts';
import { tempDirPerTest } from './testDir.ts';
import { fakeReq, fakeRes } from './testHttp.ts';
import patchSchema from '../../names/curate-patch.schema.json' with { type: 'json' };

/** The endpoint the POST tests write to. */
const PATCH_URL = '/__curate/patch';

const noopNext = () => {
  throw new Error('next() should not be called for a /__curate/ URL');
};

describe('createCurateMiddleware', () => {
  const dir = tempDirPerTest('curate-test-');
  let worklistPath: string;
  let patchPath: string;
  let middleware: ReturnType<typeof createCurateMiddleware>;

  beforeEach(() => {
    worklistPath = join(dir.path, 'curate.json');
    patchPath = join(dir.path, 'curate-patch.jsonl');
    middleware = createCurateMiddleware({ worklistPath, patchPath });
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
    create: {
      id: 'new:3f9c0a',
      action: 'create',
      kind: 'warft',
      names: { mooring: 'Hoorne', de: 'Horne' },
      note: 'from the 1920 map',
    },
    discard: { id: 'new:3f9c0a', action: 'discard' },
  };
  const jsonHeaders = { 'content-type': 'application/json' };

  it('rejects a non-JSON Content-Type with 415, and appends nothing', async () => {
    const res = await post({ 'content-type': 'text/plain' }, JSON.stringify(validEntry));
    expect(res.status).toBe(415);
    expect(await readPatchEntries()).toEqual([]);
  });

  it('answers a same-origin JSON POST with the entry it stored', async () => {
    const res = await post(
      { ...jsonHeaders, host: 'localhost:5173', origin: 'http://localhost:5173' },
      JSON.stringify({ ...validEntry, action: 'osm', osm: 'node/1' }),
    );
    expect(res.status).toBe(200);
    const [onDisk] = await readPatchEntries();
    expect(JSON.parse(res.body)).toEqual({ ok: true, entry: onDisk });
  });

  it('stores only the known fields', async () => {
    const entry = { ...validEntry, action: 'osm', osm: 'node/1', evil: 'dropped' };
    await post(jsonHeaders, JSON.stringify(entry));
    const onDisk = await readPatchEntries();
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

  it.each([
    [
      'of zero area',
      { ...localEntry, polygon_km2: 0 },
      'polygon_km2: breaks exclusiveMinimum (curate-patch.schema.json)',
    ],
    // the schema finds a missing field at the entry, not at the field
    [
      'without a field its action requires',
      { ...localEntry, lon: undefined },
      'lon: breaks required (curate-patch.schema.json)',
    ],
  ])(
    'rejects a local entry %s with 400, naming the field and the rule it breaks',
    async (_, entry, error) => {
      const res = await post(jsonHeaders, JSON.stringify(entry));
      expect({ status: res.status, body: JSON.parse(res.body) }).toEqual({
        status: 400,
        body: { error },
      });
    },
  );

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

  it('rejects a created place under a row id with 400: it would look like the row', async () => {
    const res = await post(jsonHeaders, JSON.stringify({ ...fullEntries.create, id: 'hoorne' }));
    expect(res.status).toBe(400);
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
