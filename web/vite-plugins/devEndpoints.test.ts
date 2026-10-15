// @vitest-environment node
/**
 * Exercises devEndpoints and serveFile with fake req/res objects: the
 * routing under a base, the answers that are not a route's own, and the
 * gates every dev tool's endpoints sit behind — through each tool's own
 * middleware, so a tool that skips them fails here.
 */
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createAreasMiddleware } from './areas.ts';
import { createCurateMiddleware } from './curate.ts';
import { devEndpoints, sendJson, serveFile } from './devEndpoints.ts';
import { fakeReq, fakeRes } from './testHttp.ts';

const noopNext = () => {
  throw new Error('next() should not be called for a URL under the base');
};

/** A dev tool with one GET route that answers `{ pong: true }`. */
const pingTool = devEndpoints('/__test/', {
  'GET ping': async (_req, res) => sendJson(res, 200, { pong: true }),
});

/** Sends a body-less request through `middleware`, as a loopback caller. */
async function request(
  middleware: ReturnType<typeof devEndpoints>,
  opts: Parameters<typeof fakeReq>[0],
) {
  const req = fakeReq(opts);
  const { res, done } = fakeRes();
  middleware(req, res, noopNext);
  req.end();
  return done;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('devEndpoints', () => {
  it('answers a route under its base by method and name', async () => {
    const res = await request(pingTool, { method: 'GET', url: '/__test/ping' });
    expect(JSON.parse(res.body)).toEqual({ pong: true });
  });

  it('tells the browser not to keep a JSON answer', async () => {
    const res = await request(pingTool, { method: 'GET', url: '/__test/ping' });
    expect(res.headers['cache-control']).toBe('no-store');
  });

  it('hands a URL outside its base on to the next middleware', () => {
    const next = vi.fn();
    pingTool(fakeReq({ method: 'GET', url: '/ping' }), fakeRes().res, next);
    expect(next).toHaveBeenCalled();
  });

  it('answers a route it does not have with a 404 naming it', async () => {
    const res = await request(pingTool, { method: 'POST', url: '/__test/ping' });
    expect([res.status, JSON.parse(res.body)]).toEqual([
      404,
      { error: 'unknown endpoint POST /__test/ping' },
    ]);
  });

  it('routes by the path alone, whatever the query string', async () => {
    const res = await request(pingTool, { method: 'GET', url: '/__test/ping?t=1' });
    expect(JSON.parse(res.body)).toEqual({ pong: true });
  });

  it('answers a failing route with a 500 that keeps its error to the server log', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const failing = devEndpoints('/__test/', {
      'GET fail': () => Promise.reject(new Error('EACCES: /home/someone/names/secret')),
    });
    const res = await request(failing, { method: 'GET', url: '/__test/fail' });
    expect([res.status, JSON.parse(res.body)]).toEqual([500, { error: 'internal error' }]);
  });
});

describe('serveFile', () => {
  let dir: string;
  let path: string;

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'dev-endpoints-test-'));
    path = join(dir, 'parts.geojson');
  });

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  /** A tool serving `file` as GeoJSON at `GET parts`, with `missingHint`. */
  function fileTool(file: string) {
    return devEndpoints('/__test/', {
      'GET parts': serveFile(file, 'application/geo+json', 'run the build'),
    });
  }

  it('passes the file through as it is, under its content type', async () => {
    await writeFile(path, '{ "type": "FeatureCollection" }');
    const res = await request(fileTool(path), { method: 'GET', url: '/__test/parts' });
    expect([res.status, res.headers['content-type'], res.body]).toEqual([
      200,
      'application/geo+json; charset=utf-8',
      '{ "type": "FeatureCollection" }',
    ]);
  });

  it('tells the browser not to keep the file', async () => {
    await writeFile(path, '{}');
    const res = await request(fileTool(path), { method: 'GET', url: '/__test/parts' });
    expect(res.headers['cache-control']).toBe('no-store');
  });

  it('answers a missing file with a 404 telling how to make it', async () => {
    const res = await request(fileTool(path), { method: 'GET', url: '/__test/parts' });
    expect([res.status, JSON.parse(res.body)]).toEqual([404, { error: 'run the build' }]);
  });

  it('answers a file it cannot read with a 500 that does not name its path', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    // a directory: readFile fails, and not because nothing is there
    const res = await request(fileTool(dir), { method: 'GET', url: '/__test/parts' });
    expect([res.status, res.body.includes(dir)]).toEqual([500, false]);
  });
});

/** A dev tool's middleware reading its file from `dir`, and the GET that reads it. */
interface DevTool {
  url: string;
  file: string;
  middleware: (dir: string) => ReturnType<typeof devEndpoints>;
}

const TOOLS: Record<string, DevTool> = {
  curate: {
    url: '/__curate/worklist',
    file: 'curate.json',
    middleware: (dir) =>
      createCurateMiddleware({
        worklistPath: join(dir, 'curate.json'),
        patchPath: join(dir, 'curate-patch.jsonl'),
      }),
  },
  areas: {
    url: '/__areas/parts',
    file: 'parts.geojson',
    middleware: (dir) => createAreasMiddleware({ partsPath: join(dir, 'parts.geojson') }),
  },
};

describe.each(Object.entries(TOOLS))('the gates of %s', (_, tool) => {
  let dir: string;
  let middleware: ReturnType<typeof devEndpoints>;

  beforeEach(async () => {
    dir = await mkdtemp(join(tmpdir(), 'dev-gates-test-'));
    await writeFile(join(dir, tool.file), '{}');
    middleware = tool.middleware(dir);
  });

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  /** The status of a GET of the tool's file, from `remoteAddress` with `headers`. */
  async function statusOf(headers: Record<string, string>, remoteAddress = '127.0.0.1') {
    const res = await request(middleware, { method: 'GET', url: tool.url, headers, remoteAddress });
    return res.status;
  }

  it('refuses a caller from another machine', async () => {
    expect(await statusOf({}, '10.0.0.5')).toBe(403);
  });

  it('refuses a page of another origin', async () => {
    const headers = { host: 'localhost:5173', origin: 'http://evil.example' };
    expect(await statusOf(headers)).toBe(403);
  });

  it('refuses a fetch the browser marks as not same-origin', async () => {
    expect(await statusOf({ 'sec-fetch-site': 'cross-site' })).toBe(403);
  });

  it.each(['127.0.0.1', '::1', '::ffff:127.0.0.1'])(
    'lets the same-origin page of this machine (%s) through',
    async (address) => {
      const headers = {
        host: 'localhost:5173',
        origin: 'http://localhost:5173',
        'sec-fetch-site': 'same-origin',
      };
      expect(await statusOf(headers, address)).toBe(200);
    },
  );
});
