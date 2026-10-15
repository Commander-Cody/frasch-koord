/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

import areas from './vite-plugins/areas.ts';
import assets from './vite-plugins/build/assets.ts';
import curate from './vite-plugins/curate.ts';

// https://vite.dev/config/
export default defineConfig({
  // `curate` and `areas` are left out of a build (apply: 'serve'): the
  // curation review view is a local tool that writes into names/work/, and
  // `areas` hands the dialect-area review its geometry from names/
  // (read-only). `vite preview` loads them too, since Vite resolves it as
  // 'serve' as well, but they only add dev-server endpoints, so there they do
  // nothing. `assets` only runs on a build: it checks what the build ships.
  plugins: [react(), curate(), areas(), assets()],
  // MapLibre's worker is bundled on its own (see src/map/createMap.ts) and
  // started as a module worker, so it is built as an ES module too.
  worker: { format: 'es' },
  // The libraries change far less often than the app: in chunks of their own
  // a browser keeps them cached across deploys. MapLibre (with pmtiles) is
  // most of the bytes; the rest of node_modules is the second chunk.
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            {
              name: 'maplibre',
              test: /node_modules[\\/](maplibre-gl|@maplibre|pmtiles)[\\/]/,
              priority: 2,
            },
            { name: 'vendor', test: /node_modules[\\/]/, priority: 1 },
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    // Vitest hands every stylesheet over empty; a `?raw` import is read as
    // text (src/layout.test.ts checks the media queries in it).
    css: { include: [/\.css\?raw$/] },
    // The dev-endpoint tests (vite-plugins/devEndpoints.test.ts,
    // curate.test.ts) override this to 'node' themselves (a
    // `// @vitest-environment node` docblock): they drive a Vite dev-server
    // middleware directly and have no business needing a DOM.
    include: ['src/**/*.test.{ts,tsx}', 'vite-plugins/**/*.test.ts', 'scripts/**/*.test.ts'],
  },
});
