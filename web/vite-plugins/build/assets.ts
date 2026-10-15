/**
 * Every check of a build, inside the Vite build itself, so a plain
 * `vite build` (e.g. `--base /frasch-koord/` for GitHub Pages) is checked
 * like `npm run build`:
 *
 *  - when it starts, what it needs: the pinned tile archive
 *    (vite-plugins/build/tiles.ts) and the listed glyphs, covering every
 *    label of that archive (glyphs.ts). Every problem is reported at once.
 *    It warns when that archive and names.json were built from different
 *    name files (provenance.ts).
 *  - once it is written: the pinned archive in place of whatever
 *    public/tiles/ held, then the output itself (checkBuild.ts).
 *
 * Build only (`apply: 'build'`); the dev server reads public/ in place.
 */
import { resolve } from 'node:path';
import type { Plugin } from 'vite';

import { checkBuild } from './checkBuild.ts';
import { fontProblems } from './glyphs.ts';
import { builtFromWarning } from './provenance.ts';
import { checkTiles, shipTiles, type TilesBuild } from './tiles.ts';

/** What stops a build, and what it should know but builds anyway. */
export interface BuildProblems {
  problems: string[];
  warnings: string[];
}

/** Everything that stands in a build's way when it starts, and what it should warn about. */
export async function buildProblems({
  root,
  external,
}: Omit<TilesBuild, 'outDir'>): Promise<BuildProblems> {
  const tiles = await checkTiles({ root, external });
  const problems = [...tiles.problems, ...(await fontProblems(root, tiles.archive))];
  return { problems, warnings: await archiveWarnings(root, tiles.archive, external) };
}

/**
 * What the build should know about the archive: that names.json was built
 * from other files, or with VITE_TILES_URL that there was none to check.
 * Without VITE_TILES_URL, checkTiles already stops a build that has none.
 */
async function archiveWarnings(
  root: string,
  archive: string | undefined,
  external: boolean,
): Promise<string[]> {
  if (archive !== undefined) {
    const warning = await builtFromWarning(root, archive);
    return warning === undefined ? [] : [warning];
  }
  return external
    ? [
        "no fetched tile archive matches tiles.lock, so the labels were not checked against the glyph ranges fonts.lock lists, nor its built_from against names.json's (`npm run fetch-assets` fetches it)",
      ]
    : [];
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
      const problems = checkBuild(build.outDir);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
  };
}
