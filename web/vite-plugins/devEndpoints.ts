/**
 * The HTTP endpoints of the dev tools (vite-plugins/curate.ts,
 * vite-plugins/areas.ts), built one way: everything under a tool's base
 * passes the same gates — this machine's own same-origin pages only — before
 * a route sees it, and no answer carries a filesystem path. A tool brings
 * its routes; `serveFile` is the one that hands out a file another command
 * wrote.
 */
import { readFile } from 'node:fs/promises';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Connect } from 'vite';

/** Answers one endpoint; what it throws is answered with a bare 500. */
export type RouteHandler = (req: IncomingMessage, res: ServerResponse) => Promise<void>;

/** A dev tool's endpoints, keyed `"<METHOD> <route>"` (`'GET parts'`). */
export type Routes = Record<string, RouteHandler>;

/** Answers `status` with `body` as JSON. */
export function sendJson(res: ServerResponse, status: number, body: unknown): void {
  send(res, status, 'application/json', JSON.stringify(body));
}

function send(res: ServerResponse, status: number, mediaType: string, text: string): void {
  res.statusCode = status;
  res.setHeader('Content-Type', `${mediaType}; charset=utf-8`);
  // The tools read files a command has just rewritten (an export, a build):
  // a cached copy would hide what it changed.
  res.setHeader('Cache-Control', 'no-store');
  res.end(text);
}

/** Whether `err` says the file is not there. */
export function isMissing(err: unknown): boolean {
  return (err as NodeJS.ErrnoException | null)?.code === 'ENOENT';
}

/**
 * The route handing out the text file at `path` verbatim, as `mediaType`
 * (whatever wrote it owns its schema), or a 404 with `missingHint` — how to
 * make it — while there is none.
 */
export function serveFile(path: string, mediaType: string, missingHint: string): RouteHandler {
  return async (_req, res) => {
    let text: string;
    try {
      text = await readFile(path, 'utf8');
    } catch (err) {
      if (!isMissing(err)) throw err;
      sendJson(res, 404, { error: missingHint });
      return;
    }
    send(res, 200, mediaType, text);
  };
}

/**
 * True for loopback addresses only: 127.0.0.0/8, ::1, and the IPv4-mapped
 * ::ffff:127.x.x.x that Node reports for a dual-stack socket. `vite --host`
 * can bind the dev server to the LAN, and no dev tool — not even a read-only
 * GET — is meant to be reachable from another machine on it.
 */
function isLoopbackAddress(address: string | undefined): boolean {
  if (!address) return false;
  const stripped = address.replace(/^::ffff:/i, '');
  if (stripped === '::1') return true;
  const match = /^(\d{1,3})\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.exec(stripped);
  return match !== null && Number(match[1]) === 127;
}

/**
 * What gives the request away as not same-origin, or undefined. Browsers
 * send `Sec-Fetch-Site` on every fetch, so `same-origin` is the only value
 * the tools' own calls carry (`none` is a URL typed into the address bar);
 * `Origin`, where present, must be this server's own (scheme from its config,
 * host from the `Host` header, so `vite --host` still works). A request with
 * neither header (curl, a local script) is let through: no page on another
 * site can steer those.
 */
function crossOriginSign(req: IncomingMessage, https: boolean): string | undefined {
  const secFetchSite = req.headers['sec-fetch-site'];
  if (typeof secFetchSite === 'string' && secFetchSite !== 'same-origin') {
    return `Sec-Fetch-Site is ${secFetchSite}`;
  }
  const origin = req.headers.origin;
  if (typeof origin !== 'string') return undefined;
  const expected = `${https ? 'https' : 'http'}://${req.headers.host ?? ''}`;
  return origin === expected ? undefined : `a page of ${origin}`;
}

/**
 * Why the request is turned away (403) before any endpoint sees it, or
 * undefined. Both gates hold for every route, the read-only GETs included:
 * the tools' own pages are local and same-origin, so they cost them nothing.
 */
function refusalOf(req: IncomingMessage, https: boolean): string | undefined {
  const address = req.socket.remoteAddress;
  if (!isLoopbackAddress(address)) {
    return `${address ?? 'an unknown address'} is another machine; the dev tools answer this one only`;
  }
  const sign = crossOriginSign(req, https);
  return sign && `${sign}; the dev tools answer their own pages only`;
}

function failRequest(req: IncomingMessage, res: ServerResponse, err: unknown): void {
  // The message can hold an absolute filesystem path; that goes to the
  // server log only, never into the response, which points there instead.
  console.error(`[dev endpoints] ${req.method} ${req.url} failed:`, err);
  sendJson(res, 500, { error: 'internal error, see the dev server log' });
}

/** How the dev server is set up, as far as the gates need to know. */
export interface DevEndpointOptions {
  /**
   * Whether the dev server itself runs https, i.e. `server.config.server.https`.
   * Defaults to false (Vite's own default) — see `crossOriginSign` for why the
   * expected Origin's scheme is pinned to this rather than accepted as-is.
   */
  https?: boolean;
}

/** The middleware answering `routes` under `base`. */
export function devEndpoints(
  base: string,
  routes: Routes,
  { https = false }: DevEndpointOptions = {},
): Connect.NextHandleFunction {
  return (req, res, next) => {
    const url = req.url ?? '';
    if (!url.startsWith(base)) {
      next();
      return;
    }
    const refusal = refusalOf(req, https);
    if (refusal) {
      sendJson(res, 403, { error: `forbidden: ${refusal}` });
      return;
    }
    // Strip a query string / hash; no endpoint takes one.
    const route = url.slice(base.length).split(/[?#]/)[0];
    const key = `${req.method} ${route}`;
    if (!Object.hasOwn(routes, key)) {
      sendJson(res, 404, { error: `unknown endpoint ${req.method} ${base}${route}` });
      return;
    }
    routes[key](req, res).catch((err: unknown) => failRequest(req, res, err));
  };
}
