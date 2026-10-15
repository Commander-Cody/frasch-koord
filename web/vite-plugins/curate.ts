/**
 * Dev-only HTTP endpoints behind `/__curate/` for the curation review view
 * (`?curate`, see src/dev/curate/CuratePanel.tsx).
 *
 * The browser cannot read or append to files in `names/work/`, so the Vite dev
 * server does it: it hands out the worklist `frasch curate export` wrote and
 * appends every pick to an append-only JSONL patch that `frasch curate apply`
 * consumes — every pick that keeps the patch's contract, that is
 * (names/curate-patch.schema.json): `apply` would refuse any other. Dev only
 * (`apply: 'serve'`) — a production build has no such thing, which is why the
 * panel tells the user to start the dev server when the fetch fails.
 */
import { appendFile, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import {
  registerSchema,
  validate,
  type OutputUnit,
  type SchemaObject,
  type Validator,
} from '@hyperjump/json-schema/draft-2020-12';
import { BASIC } from '@hyperjump/json-schema/experimental';
import type { Connect, Plugin } from 'vite';

import patchSchema from '../../names/curate-patch.schema.json' with { type: 'json' };
import {
  devEndpoints,
  isMissing,
  sendJson,
  serveFile,
  type DevEndpointOptions,
  type RouteHandler,
} from './devEndpoints.ts';
import { CURATE_BASE } from './devToolNames.ts';
import { PATCH_FIELDS } from './patchFields.ts';

/** A patch entry is a handful of short strings; anything bigger is a mistake. */
const MAX_BODY = 64 * 1024;

/**
 * The fields of the patch contract (names/curate-patch.schema.json), minus the
 * `at` this server sets itself. A POST body is attacker-controlled input
 * parsed as JSON and spread into an append-only file that `apply` later
 * trusts as human-checked, so anything not on this list — a stray
 * `__proto__`, a key from some other tool poking the endpoint — is dropped
 * rather than carried through.
 */
const PATCH_ENTRY_KEYS = PATCH_FIELDS.filter((key) => key !== 'at');

/**
 * True unless the request's `Content-Type` is `application/json` (parameters
 * like `; charset=utf-8` are fine; the check is case-insensitive). This is
 * the load-bearing check against M11: a cross-site `fetch` with `mode:
 * 'no-cors'` can only send a "simple request" — no custom headers, and a
 * `Content-Type` limited to `text/plain`, form-encoded or multipart — which
 * skips CORS preflight entirely. Requiring the one media type simple
 * requests cannot set forces a real cross-origin POST through a preflight.
 * Vite's own CORS middleware runs before this plugin and answers that
 * preflight without `Access-Control-Allow-Origin` for any origin but
 * localhost, so the browser never sends the POST. A page on another localhost
 * port does pass the preflight (Vite's default allows every localhost
 * origin); the same-origin gate of `devEndpoints` turns that one away.
 */
function hasJsonContentType(req: IncomingMessage): boolean {
  const header = req.headers['content-type'];
  if (typeof header !== 'string') return false;
  const mediaType = header.split(';', 1)[0]?.trim().toLowerCase();
  return mediaType === 'application/json';
}

/** Drops every field `apply` does not read; see PATCH_ENTRY_KEYS. */
function pickKnownFields(entry: Record<string, unknown>): Record<string, unknown> {
  const picked: Record<string, unknown> = {};
  for (const key of PATCH_ENTRY_KEYS) {
    if (Object.hasOwn(entry, key)) picked[key] = entry[key];
  }
  return picked;
}

/** A JSON value, as the validator takes one. */
type Json = Parameters<Validator>[0];

/** The patch contract compiled, on the first entry posted. */
let patchValidator: Promise<Validator> | undefined;

function compilePatchValidator(): Promise<Validator> {
  // Cast through `unknown`: TypeScript gives each object of the imported JSON
  // the keys of its siblings as `undefined`, which no schema keyword is.
  registerSchema(patchSchema as unknown as SchemaObject);
  return validate(patchSchema.$id);
}

/** The keyword of the schema an error is about: the last step of its location. */
function ruleOf(error: OutputUnit): string {
  return error.absoluteKeywordLocation.split('/').at(-1) ?? '';
}

/**
 * The error to report. An action's branch that fails evaluates none of its
 * fields, and the schema then calls every one of them unevaluated too: that
 * is only the answer when nothing else failed, which is an entry with a field
 * of another action. (`apply` orders its errors the same way.)
 */
function tellingError(errors: OutputUnit[]): OutputUnit {
  return errors.find((error) => ruleOf(error) !== 'unevaluatedProperties') ?? errors[0];
}

/**
 * The value of the keyword an error is about, read off the schema by the
 * error's location. The steps are taken as they are: no key on the way to a
 * keyword of this schema needs a JSON pointer's unescaping.
 */
function keywordValue(error: OutputUnit): unknown {
  const steps = error.absoluteKeywordLocation.split('#/')[1].split('/');
  return steps.reduce<unknown>(
    (node, step) => (node as Record<string, unknown>)[step],
    patchSchema,
  );
}

/**
 * The field(s) of `entry` an error is about: the one it was found at, or — a
 * `required` is found at the entry itself — the ones that are missing.
 */
function fieldsOf(error: OutputUnit, entry: Record<string, unknown>): string {
  if (ruleOf(error) !== 'required') return error.instanceLocation.slice('#/'.length);
  const required = keywordValue(error) as string[];
  return required.filter((field) => !Object.hasOwn(entry, field)).join(', ');
}

/** What breaks names/curate-patch.schema.json in `entry`, or undefined. */
async function schemaProblem(entry: Record<string, unknown>): Promise<string | undefined> {
  patchValidator ??= compilePatchValidator();
  const output = (await patchValidator)(entry as Json, BASIC);
  if (output.valid) return undefined;
  const error = tellingError(output.errors ?? []);
  const fields = fieldsOf(error, entry);
  return `${fields && `${fields}: `}breaks ${ruleOf(error)} (curate-patch.schema.json)`;
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
export interface CuratePaths extends DevEndpointOptions {
  worklistPath: string;
  patchPath: string;
}

/** `GET /__curate/patch`: every entry stored in `patchPath` so far. */
function getPatch(patchPath: string): RouteHandler {
  return async (_req, res) => {
    let text = '';
    try {
      text = await readFile(patchPath, 'utf8');
    } catch (err) {
      // No picks yet is the normal first-run state, not an error.
      if (!isMissing(err)) throw err;
    }
    sendJson(res, 200, { entries: parsePatch(text) });
  };
}

/**
 * The JSON object a POST carries. A request without one it answers itself
 * (415, 413, 400) and resolves `undefined`: the response is already sent.
 */
async function readPostedObject(
  req: IncomingMessage,
  res: ServerResponse,
): Promise<Record<string, unknown> | undefined> {
  // Rejecting anything but the one media type a CORS "simple request" cannot
  // set is what forces a cross-origin POST through a preflight; see
  // hasJsonContentType.
  if (!hasJsonContentType(req)) {
    sendJson(res, 415, { error: 'Content-Type must be application/json' });
    return undefined;
  }
  const body = await readBody(req, res);
  // undefined means readBody already answered (413) and closed the
  // connection; nothing left to do.
  if (body === undefined) return undefined;
  let posted: unknown;
  try {
    posted = JSON.parse(body);
  } catch {
    sendJson(res, 400, { error: 'body is not JSON' });
    return undefined;
  }
  if (!posted || typeof posted !== 'object' || Array.isArray(posted)) {
    sendJson(res, 400, { error: 'body must be a JSON object' });
    return undefined;
  }
  return posted as Record<string, unknown>;
}

/** `POST /__curate/patch`: appends the posted entry to `patchPath`, if it keeps the contract. */
function appendPatch(patchPath: string): RouteHandler {
  return async (req, res) => {
    const entry = await readPostedObject(req, res);
    if (entry === undefined) return;
    // Only known fields survive, and the server's clock — not whatever `at` a
    // caller may have sent — is the one `apply` can trust; see PATCH_ENTRY_KEYS
    // and pickKnownFields.
    const stored = { ...pickKnownFields(entry), at: new Date().toISOString() };
    // What is stored is what `apply` reads, so that is what must keep the
    // contract: `apply` refuses a line that does not.
    const problem = await schemaProblem(stored);
    if (problem !== undefined) {
      sendJson(res, 400, { error: problem });
      return;
    }
    // `appendFile` creates the file on first pick, and O_APPEND keeps
    // concurrent tabs from interleaving half lines.
    await appendFile(patchPath, `${JSON.stringify(stored)}\n`, 'utf8');
    sendJson(res, 200, { ok: true, entry: stored });
  };
}

/**
 * Builds the request handler, kept separate from `curate()` so tests can
 * drive it directly with fake req/res objects instead of a real Vite dev
 * server. `curate()`'s `configureServer` is the only real caller.
 */
export function createCurateMiddleware({
  worklistPath,
  patchPath,
  https,
}: CuratePaths): Connect.NextHandleFunction {
  return devEndpoints(
    CURATE_BASE,
    {
      // Passed through verbatim: the exporter owns the schema.
      'GET worklist': serveFile(worklistPath, 'application/json', 'run frasch curate export'),
      'GET patch': getPatch(patchPath),
      'POST patch': appendPatch(patchPath),
    },
    { https },
  );
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
