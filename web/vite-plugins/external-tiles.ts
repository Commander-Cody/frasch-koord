/**
 * Keeps the PMTiles archive out of `dist/` when the build is pointed at tiles
 * hosted elsewhere (`VITE_TILES_URL`, see src/config.ts).
 *
 * Vite copies web/public/ into the build as it is, and public/tiles/ holds the
 * ~125 MB archive (a symlink in a dev checkout, which the copy follows). A
 * build without VITE_TILES_URL serves the tiles itself and needs it; one with
 * it would only upload an archive nobody requests. The glyphs in public/fonts/
 * stay either way: the style always loads them from the site (see
 * src/style/localize.ts).
 *
 * Build only (`apply: 'build'`); the dev server reads public/ in place.
 */
import { readdir, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Plugin } from 'vite';

export default function externalTiles(): Plugin {
  let tilesDir = '';
  let external = false;
  return {
    name: 'frasch-external-tiles',
    apply: 'build',
    configResolved(config) {
      external = Boolean(config.env.VITE_TILES_URL);
      tilesDir = resolve(config.root, config.build.outDir, 'tiles');
    },
    // After Vite has copied public/ into the output.
    async closeBundle() {
      if (!external) return;
      const files = await readdir(tilesDir).catch(() => [] as string[]);
      const archives = files.filter((f) => f.endsWith('.pmtiles'));
      await Promise.all(archives.map((f) => rm(resolve(tilesDir, f))));
      if (archives.length > 0) {
        this.info(`VITE_TILES_URL is set: left ${archives.join(', ')} out of the build`);
      }
    },
  };
}
