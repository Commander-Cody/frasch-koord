/**
 * Fake request/response objects for the tests that drive a dev-server
 * middleware directly (devEndpoints.test.ts, curate.test.ts), with no real
 * HTTP server or Vite instance.
 */
import { PassThrough } from 'node:stream';
import type { IncomingMessage, ServerResponse } from 'node:http';

/** A response, as seen by whoever called `.end()` on it. */
export interface CapturedResponse {
  status: number;
  headers: Record<string, string>;
  body: string;
}

/**
 * Minimal fake IncomingMessage: a duplex stream (so a handler reading the
 * body sees `data`/`end`) plus the handful of fields the middlewares read.
 * Loopback by default, without any header.
 */
// Intersected with PassThrough (rather than cast to IncomingMessage alone) so
// tests can still call the stream's own `.end()`/`.destroy()` on the value a
// middleware accepts as a request.
export function fakeReq(opts: {
  method: string;
  url: string;
  headers?: Record<string, string>;
  remoteAddress?: string;
}): IncomingMessage & PassThrough {
  const req = new PassThrough();
  return Object.assign(req, {
    method: opts.method,
    url: opts.url,
    headers: opts.headers ?? {},
    socket: { remoteAddress: opts.remoteAddress ?? '127.0.0.1' },
  }) as unknown as IncomingMessage & PassThrough;
}

/**
 * Fake ServerResponse capturing status/headers/body. `done` resolves once
 * the handler calls `.end()`, the same point at which a real client would
 * see the response — tests await it instead of the middleware call itself,
 * since a middleware returns before its async work is done.
 */
export function fakeRes(): { res: ServerResponse; done: Promise<CapturedResponse> } {
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
