/**
 * Dev-only HTTP endpoints behind `/__curate/` for the curation review view
 * (`?curate`, see src/dev/CuratePanel.tsx).
 *
 * The browser cannot read or append to files in `names/work/`, so the Vite dev
 * server does it: it hands out the worklist `names/curate.py export` wrote and
 * appends every pick to an append-only JSONL patch that `names/curate.py apply`
 * consumes. Dev only (`apply: 'serve'`) — a production build has no such thing,
 * which is why the panel tells the user to start the dev server when the fetch
 * fails.
 */
import { appendFile, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Connect, Plugin } from 'vite';

/** Everything this plugin answers lives under here; anything else falls through. */
const BASE = '/__curate/';

/** Mirrors the patch contract: any other action would only confuse `apply`. */
const ACTIONS = new Set(['osm', 'local', 'skip', 'clear']);

/** A patch entry is a handful of short strings; anything bigger is a mistake. */
const MAX_BODY = 64 * 1024;

/**
 * Fields `names/curate.py apply` actually reads (plus the server-set `at`
 * added below). A POST body is attacker-controlled input parsed as JSON and
 * spread into an append-only file that `apply` later trusts as human-checked,
 * so anything not on this list — a stray `__proto__`, a key from some other
 * tool poking the endpoint — is dropped rather than carried through.
 */
const PATCH_ENTRY_KEYS = [
  'line',
  'kind',
  'name',
  'de',
  'action',
  'osm',
  'wikidata',
  'slug',
  'lat',
  'lon',
  'polygon_km2',
  'note',
] as const;

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  // A stale worklist would silently hide rows the exporter just added.
  res.setHeader('Cache-Control', 'no-store');
  res.end(text);
}

function isMissing(err: unknown): boolean {
  return (err as NodeJS.ErrnoException | null)?.code === 'ENOENT';
}

/**
 * True for loopback addresses only: 127.0.0.0/8, ::1, and the IPv4-mapped
 * ::ffff:127.x.x.x that Node reports for a dual-stack socket. `vite --host`
 * can bind this server to the LAN, and nothing under BASE — including the
 * read-only GETs — is meant to be reachable from another machine on it.
 */
function isLoopbackAddress(address: string | undefined): boolean {
  if (!address) return false;
  const stripped = address.replace(/^::ffff:/i, '');
  if (stripped === '::1') return true;
  const match = /^(\d{1,3})\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.exec(stripped);
  return match !== null && Number(match[1]) === 127;
}

/**
 * True unless the request's `Content-Type` is `application/json` (parameters
 * like `; charset=utf-8` are fine; the check is case-insensitive). This is
 * the load-bearing check against M11: a cross-site `fetch` with `mode:
 * 'no-cors'` can only send a "simple request" — no custom headers, and a
 * `Content-Type` limited to `text/plain`, form-encoded or multipart — which
 * skips CORS preflight entirely. Requiring the one media type simple
 * requests cannot set forces a real cross-origin POST through a preflight,
 * which Vite's dev server (no `Access-Control-Allow-Origin` configured here)
 * then refuses before this handler ever sees it.
 */
function hasJsonContentType(req: IncomingMessage): boolean {
  const header = req.headers['content-type'];
  if (typeof header !== 'string') return false;
  const mediaType = header.split(';', 1)[0]?.trim().toLowerCase();
  return mediaType === 'application/json';
}

/**
 * True if the request does not look same-origin. Browsers send
 * `Sec-Fetch-Site` on every fetch, so `same-origin` is the only value the
 * panel's own calls carry; `Origin`, where present, must be this server's own
 * (scheme from its config, host from the `Host` header, so `vite --host`
 * still works). A request with neither header (curl, a local script) is let
 * through: no page on another site can steer those.
 */
function isCrossOrigin(req: IncomingMessage, https: boolean): boolean {
  const secFetchSite = req.headers['sec-fetch-site'];
  if (typeof secFetchSite === 'string' && secFetchSite !== 'same-origin') return true;

  const origin = req.headers.origin;
  if (typeof origin !== 'string') return false;
  const expected = `${https ? 'https' : 'http'}://${req.headers.host ?? ''}`;
  return origin !== expected;
}

/** Drops every field `apply` does not read; see PATCH_ENTRY_KEYS. */
function pickKnownFields(entry: Record<string, unknown>): Record<string, unknown> {
  const picked: Record<string, unknown> = {};
  for (const key of PATCH_ENTRY_KEYS) {
    if (Object.hasOwn(entry, key)) picked[key] = entry[key];
  }
  return picked;
}

/**
 * Buffers the request body, capped at MAX_BODY. Past the cap it answers 413
 * itself and destroys the request (otherwise the client keeps streaming into
 * our buffer), and resolves `undefined`: the response is already sent.
 */
function readBody(req: IncomingMessage, res: ServerResponse): Promise<string | undefined> {
  return new Promise((resolve, reject) => {
    let data = '';
    let settled = false;
    req.setEncoding('utf8');
    req.on('data', (chunk: string) => {
      if (settled) return;
      data += chunk;
      if (data.length > MAX_BODY) {
        settled = true;
        sendJson(res, 413, { error: 'request body too large' });
        req.destroy();
        resolve(undefined);
      }
    });
    req.on('end', () => {
      if (!settled) {
        settled = true;
        resolve(data);
      }
    });
    req.on('error', (err) => {
      if (!settled) {
        settled = true;
        reject(err);
      }
    });
  });
}

/** Parses the JSONL patch, tolerating a half-written last line. */
function parsePatch(text: string): unknown[] {
  const entries: unknown[] = [];
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      entries.push(JSON.parse(trimmed));
    } catch {
      // Append-only file: a broken line is scratch, not a reason to 500.
      console.warn(`[curate] skipping unparseable patch line: ${trimmed.slice(0, 120)}`);
    }
  }
  return entries;
}

/** Where the plugin instance reads and writes; see `curate()`'s `configResolved`. */
export interface CuratePaths {
  worklistPath: string;
  patchPath: string;
  /**
   * Whether the dev server itself runs https, i.e. `server.config.server.https`.
   * Defaults to false (Vite's own default) — see `isCrossOrigin` for why the
   * expected Origin's scheme is pinned to this rather than accepted as-is.
   */
  https?: boolean;
}

/**
 * Builds the request handler, kept separate from `curate()` so tests can
 * drive it directly with fake req/res objects instead of a real Vite dev
 * server. `curate()`'s `configureServer` is the only real caller.
 */
export function createCurateMiddleware(paths: CuratePaths): Connect.NextHandleFunction {
  const { worklistPath, patchPath, https = false } = paths;

  return (req, res, next) => {
    const url = req.url ?? '';
    if (!url.startsWith(BASE)) {
      next();
      return;
    }
    // Strip a query string / hash; these endpoints take none.
    const route = url.slice(BASE.length).split(/[?#]/)[0];

    // LAN safety net, checked before anything else and for every route
    // (including the read-only GETs): `vite --host` can expose this server
    // beyond localhost, and none of it is meant for another machine.
    if (!isLoopbackAddress(req.socket.remoteAddress)) {
      sendJson(res, 403, { error: 'forbidden' });
      return;
    }

    // Browser same-origin check. Applied to every route, not just the POST
    // that writes: the panel's own GETs are same-origin too, so this costs
    // it nothing, and a page on another site has no business reading the
    // worklist or the patch log either.
    if (isCrossOrigin(req, https)) {
      sendJson(res, 403, { error: 'forbidden' });
      return;
    }

    void (async () => {
      try {
        if (route === 'worklist' && req.method === 'GET') {
          let text: string;
          try {
            text = await readFile(worklistPath, 'utf8');
          } catch (err) {
            if (!isMissing(err)) throw err;
            sendJson(res, 404, { error: 'run names/curate.py export' });
            return;
          }
          // Passed through verbatim: the exporter owns the schema.
          res.statusCode = 200;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.setHeader('Cache-Control', 'no-store');
          res.end(text);
          return;
        }

        if (route === 'patch' && req.method === 'GET') {
          let text = '';
          try {
            text = await readFile(patchPath, 'utf8');
          } catch (err) {
            // No picks yet is the normal first-run state, not an error.
            if (!isMissing(err)) throw err;
          }
          sendJson(res, 200, { entries: parsePatch(text) });
          return;
        }

        if (route === 'patch' && req.method === 'POST') {
          // Rejecting anything but the one media type a CORS "simple
          // request" cannot set is what forces a cross-origin POST through
          // a preflight; see hasJsonContentType.
          if (!hasJsonContentType(req)) {
            sendJson(res, 415, { error: 'Content-Type must be application/json' });
            return;
          }
          const body = await readBody(req, res);
          // undefined means readBody already answered (413) and closed the
          // connection; nothing left to do.
          if (body === undefined) return;
          let entry: Record<string, unknown>;
          try {
            entry = JSON.parse(body) as Record<string, unknown>;
          } catch {
            sendJson(res, 400, { error: 'body is not JSON' });
            return;
          }
          if (!entry || typeof entry !== 'object' || Array.isArray(entry)) {
            sendJson(res, 400, { error: 'body must be a JSON object' });
            return;
          }
          if (!Number.isInteger(entry.line)) {
            sendJson(res, 400, { error: 'line must be an integer' });
            return;
          }
          if (typeof entry.action !== 'string' || !ACTIONS.has(entry.action)) {
            sendJson(res, 400, { error: `action must be one of ${[...ACTIONS].join(', ')}` });
            return;
          }
          // Only known fields survive, and the server's clock — not
          // whatever `at` a caller may have sent — is the one `apply` can
          // trust; see PATCH_ENTRY_KEYS and pickKnownFields.
          const stored = { ...pickKnownFields(entry), at: new Date().toISOString() };
          // `appendFile` creates the file on first pick, and O_APPEND keeps
          // concurrent tabs from interleaving half lines.
          await appendFile(patchPath, `${JSON.stringify(stored)}\n`, 'utf8');
          sendJson(res, 200, { ok: true, entry: stored });
          return;
        }

        sendJson(res, 404, { error: `unknown endpoint ${BASE}${route}` });
      } catch (err) {
        // The message can hold an absolute filesystem path; that goes to
        // the server log only, never into the response.
        console.error('[curate] request failed', err);
        sendJson(res, 500, { error: 'internal error' });
      }
    })();
  };
}

export default function curate(): Plugin {
  // Resolved from the Vite root (web/) so the plugin does not care about the
  // process' working directory.
  let worklistPath = '';
  let patchPath = '';

  return {
    name: 'frasch-curate',
    apply: 'serve',
    configResolved(config) {
      const workDir = resolve(config.root, '../names/work');
      worklistPath = resolve(workDir, 'curate.json');
      patchPath = resolve(workDir, 'curate-patch.jsonl');
    },
    configureServer(server) {
      const https = Boolean(server.config.server.https);
      server.middlewares.use(createCurateMiddleware({ worklistPath, patchPath, https }));
    },
  };
}
