// @vitest-environment node
/**
 * vite-plugins/areas.ts as Vite loads it: where the dev server finds the
 * parts of the dialect areas, and that a build leaves the plugin out. What
 * the endpoint answers is devEndpoints.test.ts's.
 */
import { createServer as createHttpServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { join } from 'node:path';
import { createServer, resolveConfig } from 'vite';
import { describe, expect, it } from 'vitest';

import areas from './areas.ts';
import { tempDirPerTest } from './testDir.ts';

/** A checkout: web/, the Vite root, next to names/. */
const checkout = tempDirPerTest('areas-plugin-');

/** The body of `GET /__areas/parts` from a dev server on web/ with the plugin. */
async function getParts(): Promise<string> {
  const vite = await createServer({
    root: join(checkout.path, 'web'),
    configFile: false,
    logLevel: 'silent',
    appType: 'custom',
    plugins: [areas()],
    server: { middlewareMode: true, ws: false },
  });
  const http = createHttpServer(vite.middlewares);
  try {
    await new Promise<void>((resolve) => http.listen(0, '127.0.0.1', resolve));
    const { port } = http.address() as AddressInfo;
    return await (await fetch(`http://127.0.0.1:${port}/__areas/parts`)).text();
  } finally {
    http.close();
    await vite.close();
  }
}

describe('areas', () => {
  it('serves the parts file in names/, next to the Vite root', async () => {
    const parts = '{ "type": "FeatureCollection", "features": [] }';
    checkout.put('names/dialect_areas_parts.geojson', parts);

    expect(await getParts()).toBe(parts);
  });

  it('is left out of a build', async () => {
    const config = await resolveConfig({ configFile: false, plugins: [areas()] }, 'build');

    expect(config.plugins.map((plugin) => plugin.name)).not.toContain('frasch-areas');
  });
});
