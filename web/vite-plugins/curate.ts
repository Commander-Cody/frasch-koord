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
import type { Plugin } from 'vite';

/** Everything this plugin answers lives under here; anything else falls through. */
const BASE = '/__curate/';

/** Mirrors the patch contract: any other action would only confuse `apply`. */
const ACTIONS = new Set(['osm', 'local', 'skip', 'clear']);

/** A patch entry is a handful of short strings; anything bigger is a mistake. */
const MAX_BODY = 64 * 1024;

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

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((done, fail) => {
    let data = '';
    req.setEncoding('utf8');
    req.on('data', (chunk: string) => {
      data += chunk;
      if (data.length > MAX_BODY) fail(new Error('request body too large'));
    });
    req.on('end', () => done(data));
    req.on('error', fail);
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
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';
        if (!url.startsWith(BASE)) {
          next();
          return;
        }
        // Strip a query string / hash; these endpoints take none.
        const route = url.slice(BASE.length).split(/[?#]/)[0];

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
              const body = await readBody(req);
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
              // The server's clock is the one `apply` can trust; a browser may
              // have sent an `at` of its own, and we overwrite it on purpose.
              const stored = { ...entry, at: new Date().toISOString() };
              // `appendFile` creates the file on first pick, and O_APPEND keeps
              // concurrent tabs from interleaving half lines.
              await appendFile(patchPath, `${JSON.stringify(stored)}\n`, 'utf8');
              sendJson(res, 200, { ok: true, entry: stored });
              return;
            }

            sendJson(res, 404, { error: `unknown endpoint ${BASE}${route}` });
          } catch (err) {
            console.error('[curate] request failed', err);
            sendJson(res, 500, { error: String(err) });
          }
        })();
      });
    },
  };
}
