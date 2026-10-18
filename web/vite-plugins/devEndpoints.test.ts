// @vitest-environment node
/**
 * Exercises devEndpoints and serveFile with fake req/res objects: the
 * routing under a base, the answers that are not a route's own, and the
 * gates every dev tool's endpoints sit behind — through each tool's own
 * middleware, so a tool that skips them fails here.
 */
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createAreasMiddleware } from './areas.ts';
import { createCurateMiddleware } from './curate.ts';
import { devEndpoints, sendJson, serveFile } from './devEndpoints.ts';
import { tempDirPerTest } from './testDir.ts';
import { fakeReq, fakeRes, type CapturedResponse } from './testHttp.ts';

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

  describe('a failing route', () => {
    const error = new Error('EACCES: /home/someone/names/secret');
    const failing = devEndpoints('/__test/', { 'GET fail': () => Promise.reject(error) });

    it('is answered with a 500 that points to the server log, not with its error', async () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const res = await request(failing, { method: 'GET', url: '/__test/fail' });
      expect([res.status, JSON.parse(res.body)]).toEqual([
        500,
        { error: 'internal error, see the dev server log' },
      ]);
    });

    it('is logged with the request that failed', async () => {
      const log = vi.spyOn(console, 'error').mockImplementation(() => {});
      await request(failing, { method: 'GET', url: '/__test/fail' });
      expect(log).toHaveBeenCalledWith('[dev endpoints] GET /__test/fail failed:', error);
    });
  });
});

describe('serveFile', () => {
  const dir = tempDirPerTest('dev-endpoints-test-');
  const FILE = 'parts.geojson';

  /** A tool serving `file` as GeoJSON at `GET parts`, with `missingHint`. */
  function fileTool(file: string) {
    return devEndpoints('/__test/', {
      'GET parts': serveFile(file, 'application/geo+json', 'run the build'),
    });
  }

  /** `GET parts` of a tool serving `file`, by default the test's FILE. */
  function getParts(file = join(dir.path, FILE)) {
    return request(fileTool(file), { method: 'GET', url: '/__test/parts' });
  }

  it('passes the file through as it is, under its content type', async () => {
    dir.put(FILE, '{ "type": "FeatureCollection" }');
    const res = await getParts();
    expect([res.status, res.headers['content-type'], res.body]).toEqual([
      200,
      'application/geo+json; charset=utf-8',
      '{ "type": "FeatureCollection" }',
    ]);
  });

  it('tells the browser not to keep the file', async () => {
    dir.put(FILE, '{}');
    const res = await getParts();
    expect(res.headers['cache-control']).toBe('no-store');
  });

  it('answers a missing file with a 404 telling how to make it', async () => {
    const res = await getParts();
    expect([res.status, JSON.parse(res.body)]).toEqual([404, { error: 'run the build' }]);
  });

  it('answers a file it cannot read with a 500 that does not name its path', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    // a directory: readFile fails, and not because nothing is there
    const res = await getParts(dir.path);
    expect([res.status, res.body.includes(dir.path)]).toEqual([500, false]);
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
  const dir = tempDirPerTest('dev-gates-test-');
  let middleware: ReturnType<typeof devEndpoints>;

  beforeEach(() => {
    dir.put(tool.file, '{}');
    middleware = tool.middleware(dir.path);
  });

  /** A GET of the tool's file from `remoteAddress` with `headers`, answered. */
  function get(headers: Record<string, string>, remoteAddress = '127.0.0.1') {
    return request(middleware, { method: 'GET', url: tool.url, headers, remoteAddress });
  }

  /** The status of an answer, and the error it gives. */
  function refusal(res: CapturedResponse) {
    return [res.status, (JSON.parse(res.body) as { error?: string }).error];
  }

  it('refuses a caller from another machine, naming it', async () => {
    expect(refusal(await get({}, '10.0.0.5'))).toEqual([
      403,
      'forbidden: 10.0.0.5 is another machine; the dev tools answer this one only',
    ]);
  });

  it('refuses a page of another origin, naming it', async () => {
    const headers = { host: 'localhost:5173', origin: 'http://evil.example' };
    expect(refusal(await get(headers))).toEqual([
      403,
      'forbidden: a page of http://evil.example; the dev tools answer their own pages only',
    ]);
  });

  it('refuses a fetch the browser marks as not same-origin, saying how it was marked', async () => {
    expect(refusal(await get({ 'sec-fetch-site': 'cross-site' }))).toEqual([
      403,
      'forbidden: Sec-Fetch-Site is cross-site; the dev tools answer their own pages only',
    ]);
  });

  it.each(['127.0.0.1', '::1', '::ffff:127.0.0.1'])(
    'lets the same-origin page of this machine (%s) through',
    async (address) => {
      const headers = {
        host: 'localhost:5173',
        origin: 'http://localhost:5173',
        'sec-fetch-site': 'same-origin',
      };
      expect((await get(headers, address)).status).toBe(200);
    },
  );
});
