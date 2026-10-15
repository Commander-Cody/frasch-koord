/**
 * Every check of a build, inside the Vite build itself, so a plain
 * `vite build` (e.g. `--base /frasch-koord/` for GitHub Pages) is checked
 * like `npm run build`:
 *
 *  - when it starts, what it needs: the pinned tile archive
 *    (vite-plugins/build/tiles.ts) and the listed glyphs, covering every
 *    label of that archive (glyphs.ts). Every problem is reported at once.
 *  - once it is written: the pinned archive in place of whatever
 *    public/tiles/ held, then the output itself (checkBuild.ts).
 *
 * Build only (`apply: 'build'`); the dev server reads public/ in place.
 */
import { access } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import type { Plugin } from 'vite';

import { checkBuild } from './checkBuild.ts';
import { fontProblems } from './glyphs.ts';
import { readTilesPin } from './pins.ts';
import { shipTiles, type TilesBuild, tilesProblems } from './tiles.ts';

/** What stops a build, and what it should know but builds anyway. */
export interface BuildProblems {
  problems: string[];
  warnings: string[];
}

/** The fetched archive tiles.lock pins, or undefined when it is not there (or the lock is broken). */
async function fetchedArchive(root: string): Promise<string | undefined> {
  try {
    const archive = join(root, (await readTilesPin(root)).cachePath);
    await access(archive);
    return archive;
  } catch {
    return undefined;
  }
}

/** Everything that stands in a build's way when it starts, and what it should warn about. */
export async function buildProblems({
  root,
  external,
}: Omit<TilesBuild, 'outDir'>): Promise<BuildProblems> {
  const archive = await fetchedArchive(root);
  const problems = [
    ...(await tilesProblems({ root, external })),
    ...(await fontProblems(root, archive)),
  ];
  // Without VITE_TILES_URL tilesProblems already stops a build that has no archive.
  const warnings =
    external && archive === undefined
      ? [
          'the pinned tile archive is not fetched, so the labels were not checked against the glyph ranges fonts.lock lists (`npm run fetch-assets` fetches it)',
        ]
      : [];
  return { problems, warnings };
}

export default function assets(): Plugin {
  let build: TilesBuild;
  return {
    name: 'frasch-assets',
    apply: 'build',
    configResolved(config) {
      build = {
        root: config.root,
        outDir: resolve(config.root, config.build.outDir),
        external: Boolean(config.env.VITE_TILES_URL),
      };
    },
    async buildStart() {
      const { problems, warnings } = await buildProblems(build);
      for (const warning of warnings) this.warn(warning);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
    // After Vite has copied public/ into the output. Not closeBundle, which
    // also runs after a failed build and would bury buildStart's message.
    async writeBundle() {
      await shipTiles(build);
      const { problems } = checkBuild(build.outDir);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
  };
}
