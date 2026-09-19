import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import curate from './vite-plugins/curate.ts'

// https://vite.dev/config/
export default defineConfig({
  // `curate` only registers itself for `vite dev` (apply: 'serve'): the
  // curation review view is a local tool that writes into names/work/.
  plugins: [react(), curate()],
  // maplibre-gl loads its web worker as a separate module; Vite's dep
  // pre-bundling would leave that file out (404 on maplibre-gl-worker.mjs).
  optimizeDeps: { exclude: ['maplibre-gl'] },
})
