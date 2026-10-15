/**
 * The tile archive a build ships: the one `web/tiles.lock` pins, and
 * nothing else from public/tiles/.
 *
 * Vite copies web/public/ into the build as it is. public/tiles/ holds
 * whatever archive is linked there -- the one `npm run fetch-assets` fetched,
 * or a tile builder's own from tiles/data/ -- and a build must not ship an
 * archive nobody can name. So the copied archives are dropped, and the
 * pinned one is taken from the fetch cache (.cache/tiles/<sha256>.pmtiles)
 * instead. With VITE_TILES_URL set the tiles live elsewhere (see
 * src/site.ts) and no archive is shipped at all. A link there that leads
 * nowhere (to tiles not built yet) stops the build as well: Vite cannot copy
 * it. vite-plugins/build/assets.ts runs the check and ships the archive.
 */
import type { Dirent } from 'node:fs';
import { copyFile, mkdir, readdir, readlink, rm } from 'node:fs/promises';
import { join } from 'node:path';

import { readTilesPin } from './pins.ts';
import { exists, sha256Of } from './files.ts';

/** Where the dev server's archive is linked, under the web/ root. */
const PUBLIC_TILES = 'public/tiles';

/** The web/ root a build runs in, the dist/ it writes, and whether VITE_TILES_URL is set. */
export interface TilesBuild {
  root: string;
  outDir: string;
  external: boolean;
}

/** What a build finds of the tiles when it starts. */
export interface TilesCheck {
  /** What stands in its way, one line each; empty when it has all it needs. */
  problems: string[];
  /** The fetched archive, when it is the one tiles.lock pins; nothing else may be read as it. */
  archive: string | undefined;
}

/** The fetched archive when it is the pinned one, or what is wrong with it. */
async function verifiedArchive(root: string): Promise<{ archive: string } | { problem: string }> {
  let pin;
  try {
    pin = await readTilesPin(root);
  } catch (err) {
    return { problem: (err as Error).message };
  }
  const archive = join(root, pin.cachePath);
  const actual = await sha256Of(archive);
  if (actual === undefined) {
    return {
      problem:
        'the pinned tile archive is not fetched: run `npm run fetch-assets` (or set VITE_TILES_URL)',
    };
  }
  if (actual !== pin.sha256) {
    return {
      problem: `${pin.cachePath} does not match tiles.lock: run \`npm run fetch-assets\` again`,
    };
  }
  return { archive };
}

/** The links directly in `dir` whose target is not there. */
async function danglingLinks(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true }).catch(() => [] as Dirent[]);
  const links = entries.filter((entry) => entry.isSymbolicLink()).map((entry) => entry.name);
  const targetExists = await Promise.all(links.map((name) => exists(join(dir, name))));
  return links.filter((_, i) => !targetExists[i]);
}

/**
 * One line per dangling link in public/tiles/, such as a tile builder's to
 * an archive that is not built yet: Vite's copy of public/ into the build
 * fails on it with a bare ENOENT.
 */
export async function danglingLinkProblems(root: string): Promise<string[]> {
  const dir = join(root, PUBLIC_TILES);
  return Promise.all(
    (await danglingLinks(dir)).map(async (name) => {
      const target = await readlink(join(dir, name));
      return `${PUBLIC_TILES}/${name} links to ${target}, which does not exist: the dev server shows no map and \`npm run build\` stops. Build the tiles, or remove the link and run \`npm run fetch-assets\``;
    }),
  );
}

/**
 * The pinned archive and public/tiles/ when a build starts. With
 * VITE_TILES_URL the build ships no archive, so a missing or wrong one is
 * no problem; it is only not handed on.
 */
export async function checkTiles({
  root,
  external,
}: Omit<TilesBuild, 'outDir'>): Promise<TilesCheck> {
  const verified = await verifiedArchive(root);
  const archiveProblems = 'problem' in verified && !external ? [verified.problem] : [];
  return {
    problems: [...archiveProblems, ...(await danglingLinkProblems(root))],
    archive: 'archive' in verified ? verified.archive : undefined,
  };
}

/** Drops the archives Vite copied from public/tiles/: a dev symlink's target, or a stale fetch. */
async function dropCopiedArchives(tilesDir: string): Promise<void> {
  const files = await readdir(tilesDir).catch(() => [] as string[]);
  await Promise.all(files.filter((f) => f.endsWith('.pmtiles')).map((f) => rm(join(tilesDir, f))));
}

/** Replaces the archives Vite copied into `outDir` with the pinned one, or none. */
export async function shipTiles({ root, outDir, external }: TilesBuild): Promise<void> {
  await dropCopiedArchives(join(outDir, 'tiles'));
  if (external) return;
  const pin = await readTilesPin(root);
  await mkdir(join(outDir, 'tiles'), { recursive: true });
  await copyFile(join(root, pin.cachePath), join(outDir, 'tiles', pin.name));
}
