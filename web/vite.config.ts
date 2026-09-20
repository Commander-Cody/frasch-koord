import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import areas from './vite-plugins/areas.ts'
import curate from './vite-plugins/curate.ts'

// https://vite.dev/config/
export default defineConfig({
  // Both only register themselves for `vite dev` (apply: 'serve'): the
  // curation review view is a local tool that writes into names/work/, and
  // `areas` hands the dialect-area review its geometry from names/ (read-only).
  plugins: [react(), curate(), areas()],
  // maplibre-gl loads its web worker as a separate module; Vite's dep
  // pre-bundling would leave that file out (404 on maplibre-gl-worker.mjs).
  optimizeDeps: { exclude: ['maplibre-gl'] },
})
