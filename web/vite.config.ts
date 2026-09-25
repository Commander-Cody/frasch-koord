/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import areas from './vite-plugins/areas.ts'
import curate from './vite-plugins/curate.ts'
import externalTiles from './vite-plugins/external-tiles.ts'

// https://vite.dev/config/
export default defineConfig({
  // `curate` and `areas` only register themselves for `vite dev` (apply:
  // 'serve'): the curation review view is a local tool that writes into
  // names/work/, and `areas` hands the dialect-area review its geometry from
  // names/ (read-only). `externalTiles` only runs on a build.
  plugins: [react(), curate(), areas(), externalTiles()],
  // MapLibre's worker is bundled on its own (see src/components/Map.tsx) and
  // started as a module worker, so it is built as an ES module too.
  worker: { format: 'es' },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
  },
})
