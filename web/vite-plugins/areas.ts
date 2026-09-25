/**
 * Dev-only HTTP endpoint behind `/__areas/` for the dialect-area review view
 * (`?areas`, see src/dev/AreaPanel.tsx).
 *
 * `names/dialect_areas_parts.geojson` lives next to the CSV it is generated
 * from, outside the Vite root, so the browser cannot reach it; the dev server
 * hands it over. Dev only (`apply: 'serve'`) for two reasons: a production
 * build has no business carrying a review tool, and the file quotes the
 * research notes verbatim ("best guess only", "no direct source found") about
 * assignments the owner has not confirmed yet. That prose should not ship to
 * the public site.
 *
 * Read-only, unlike vite-plugins/curate.ts: the review writes nothing back,
 * `names/dialect_areas.csv` is edited by hand.
 */
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

/** Everything this plugin answers lives under here; anything else falls through. */
const BASE = '/__areas/';

/** Told to the user when the file is not there yet; the only way to make one. */
const BUILD_HINT =
  'run names/build_dialect_areas.py tiles/data/schleswig-holstein-latest.osm.pbf';

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  // The reviewer re-runs the build and hits Reload; a cached copy would show
  // them the assignments they just changed.
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(body));
}

function isMissing(err: unknown): boolean {
  return (err as NodeJS.ErrnoException | null)?.code === 'ENOENT';
}

export default function areas(): Plugin {
  // Resolved from the Vite root (web/) so the plugin does not care about the
  // process' working directory.
  let partsPath = '';

  return {
    name: 'frasch-areas',
    apply: 'serve',
    configResolved(config) {
      partsPath = resolve(config.root, '../names/dialect_areas_parts.geojson');
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? '';
        if (!url.startsWith(BASE)) {
          next();
          return;
        }
        // Strip a query string / hash; this endpoint takes none.
        const route = url.slice(BASE.length).split(/[?#]/)[0];

        void (async () => {
          try {
            if (route === 'parts' && req.method === 'GET') {
              let text: string;
              try {
                text = await readFile(partsPath, 'utf8');
              } catch (err) {
                if (!isMissing(err)) throw err;
                sendJson(res, 404, { error: BUILD_HINT });
                return;
              }
              // Passed through verbatim: the build script owns the schema.
              res.statusCode = 200;
              res.setHeader('Content-Type', 'application/geo+json; charset=utf-8');
              res.setHeader('Cache-Control', 'no-store');
              res.end(text);
              return;
            }

            sendJson(res, 404, { error: `unknown endpoint ${BASE}${route}` });
          } catch (err) {
            console.error('[areas] request failed', err);
            sendJson(res, 500, { error: String(err) });
          }
        })();
      });
    },
  };
}
