/**
 * Puts the tile archive `web/tiles.lock` pins into the build, and nothing
 * else from public/tiles/, and stops a build that would show no map.
 *
 * Vite copies web/public/ into the build as it is. public/tiles/ holds
 * whatever archive is linked there -- the one `npm run fetch-assets` fetched
 * (scripts/fetch-tiles.sh), or a tile builder's own from tiles/data/ -- and
 * a build must not ship an archive nobody can name. So the copied archives
 * are dropped, and the pinned one is taken from the fetch cache
 * (.cache/tiles/<sha256>.pmtiles) instead. With VITE_TILES_URL set the tiles
 * live elsewhere (see src/config.ts) and no archive is shipped at all. A link
 * there that leads nowhere (to tiles not built yet) stops the build as well:
 * Vite cannot copy it. The glyphs are vite-plugins/glyphs.ts' business.
 *
 * Build only (`apply: 'build'`); the dev server reads public/ in place.
 */
import { createHash } from 'node:crypto';
import { createReadStream, type Dirent } from 'node:fs';
import { copyFile, mkdir, readdir, readlink, rm, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pipeline } from 'node:stream/promises';
import type { Plugin } from 'vite';

import { lockValue } from './lock.ts';

/** Where the site serves its own archive from, under dist/ (see src/config.ts). */
const ARCHIVE = 'tiles/schleswig-holstein.pmtiles';

/** Where the dev server's archive is linked, under the web/ root. */
const PUBLIC_TILES = 'public/tiles';

/** The web/ root a build runs in, the dist/ it writes, and whether VITE_TILES_URL is set. */
export interface TilesBuild {
  root: string;
  outDir: string;
  external: boolean;
}

function pinnedSha256(root: string): Promise<string> {
  return lockValue(join(root, 'tiles.lock'), 'ARCHIVE_SHA256');
}

function cachedArchive(root: string, sha256: string): string {
  return join(root, '.cache/tiles', `${sha256}.pmtiles`);
}

/** Where `npm run fetch-assets` puts the archive tiles.lock pins. */
export async function pinnedArchive(root: string): Promise<string> {
  return cachedArchive(root, await pinnedSha256(root));
}

/** The file's sha256, or undefined when there is no such file. */
async function sha256Of(file: string): Promise<string | undefined> {
  const hash = createHash('sha256');
  try {
    await pipeline(createReadStream(file), hash);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return undefined;
    throw err;
  }
  return hash.digest('hex');
}

async function archiveProblem(root: string): Promise<string | undefined> {
  const pinned = await pinnedSha256(root);
  // It names a file in .cache/tiles/, so it has to be a hash and nothing else.
  if (!/^[0-9a-f]{64}$/.test(pinned)) return `tiles.lock pins no sha256 (ARCHIVE_SHA256=${pinned})`;
  const actual = await sha256Of(cachedArchive(root, pinned));
  if (actual === undefined) {
    return 'the pinned tile archive is not fetched: run `npm run fetch-assets` (or set VITE_TILES_URL)';
  }
  if (actual !== pinned) {
    return `.cache/tiles/${pinned}.pmtiles does not match tiles.lock: run \`npm run fetch-assets\` again`;
  }
}

/** Whether the path leads to a file, its links followed. */
async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return false;
    throw err;
  }
  return true;
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
async function danglingLinkProblems(root: string): Promise<string[]> {
  const dir = join(root, PUBLIC_TILES);
  return Promise.all(
    (await danglingLinks(dir)).map(async (name) => {
      const target = await readlink(join(dir, name));
      return `${PUBLIC_TILES}/${name} links to ${target}, which does not exist: build the tiles, or remove the link and run \`npm run fetch-tiles\``;
    }),
  );
}

/** What stands in the build's way, one line each, when it starts; empty when it has all it needs. */
export async function assetProblems({
  root,
  external,
}: Omit<TilesBuild, 'outDir'>): Promise<string[]> {
  const problem = external ? undefined : await archiveProblem(root);
  return [...(problem === undefined ? [] : [problem]), ...(await danglingLinkProblems(root))];
}

/** Drops the archives Vite copied from public/tiles/: a dev symlink's target, or a stale fetch. */
async function dropCopiedArchives(tilesDir: string): Promise<void> {
  const files = await readdir(tilesDir).catch(() => [] as string[]);
  await Promise.all(files.filter((f) => f.endsWith('.pmtiles')).map((f) => rm(join(tilesDir, f))));
}

/** Replaces the archives Vite copied into `outDir` with the pinned one, or none. */
async function shipTiles({ root, outDir, external }: TilesBuild): Promise<void> {
  await dropCopiedArchives(join(outDir, 'tiles'));
  if (external) return;
  await mkdir(join(outDir, 'tiles'), { recursive: true });
  await copyFile(await pinnedArchive(root), join(outDir, ARCHIVE));
}

export default function tiles(): Plugin {
  let build: TilesBuild;
  return {
    name: 'frasch-tiles',
    apply: 'build',
    configResolved(config) {
      build = {
        root: config.root,
        outDir: resolve(config.root, config.build.outDir),
        external: Boolean(config.env.VITE_TILES_URL),
      };
    },
    async buildStart() {
      const problems = await assetProblems(build);
      if (problems.length > 0) this.error(problems.join('\n'));
    },
    // After Vite has copied public/ into the output. Not closeBundle, which
    // also runs after a failed build and would bury buildStart's message.
    async writeBundle() {
      await shipTiles(build);
    },
  };
}
