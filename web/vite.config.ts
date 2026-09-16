import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // maplibre-gl loads its web worker as a separate module; Vite's dep
  // pre-bundling would leave that file out (404 on maplibre-gl-worker.mjs).
  optimizeDeps: { exclude: ['maplibre-gl'] },
})
