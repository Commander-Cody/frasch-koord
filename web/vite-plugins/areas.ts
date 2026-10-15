/**
 * Dev-only HTTP endpoint behind `/__areas/` for the dialect-area review view
 * (`?areas`, see src/dev/areas/AreaPanel.tsx).
 *
 * `names/dialect_areas_parts.geojson` lives next to the CSV it is generated
 * from, outside the Vite root, so the browser cannot reach it; the dev server
 * hands it over. Dev only (`apply: 'serve'`), so that none of it is in the
 * release build: the build has no business carrying a review tool, and the
 * file quotes the research notes (`low: … best-guess Bökingharde`) about
 * assignments the owner has not confirmed yet. The file and the notes are no
 * secret — they are in the repository — but the map should not present them
 * as fact, so only the local machine's own pages get them (devEndpoints).
 * `npm run build` fails when either reaches dist/ (check-build.mjs).
 *
 * Read-only, unlike vite-plugins/curate.ts: the review writes nothing back,
 * `names/dialect_areas.csv` is edited by hand.
 */
import { resolve } from 'node:path';
import type { Connect, Plugin } from 'vite';

import { devEndpoints, serveFile, type DevEndpointOptions } from './devEndpoints.ts';
import { AREAS_BASE, AREA_PARTS_FILE } from './devToolNames.ts';

/** Where the plugin instance reads; see `areas()`'s `configResolved`. */
export interface AreasPaths extends DevEndpointOptions {
  partsPath: string;
}

/** `GET /__areas/parts`: the file `frasch build areas` wrote. */
export function createAreasMiddleware({
  partsPath,
  https,
}: AreasPaths): Connect.NextHandleFunction {
  return devEndpoints(
    AREAS_BASE,
    { 'GET parts': serveFile(partsPath, 'application/geo+json', 'run `just rebuild areas`') },
    { https },
  );
}

export default function areas(): Plugin {
  // Resolved from the Vite root (web/) so the plugin does not care about the
  // process' working directory.
  let partsPath = '';

  return {
    name: 'frasch-areas',
    apply: 'serve',
    configResolved(config) {
      partsPath = resolve(config.root, '../names', AREA_PARTS_FILE);
    },
    configureServer(server) {
      const https = Boolean(server.config.server.https);
      server.middlewares.use(createAreasMiddleware({ partsPath, https }));
    },
  };
}
