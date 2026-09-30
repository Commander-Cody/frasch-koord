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
 * live elsewhere (see src/config.ts) and no archive is shipped at all. The
 * glyphs in public/fonts/ are needed either way: the style always loads them
 * from the site (see src/style/localize.ts).
 *
 * Build only (`apply: 'build'`); the dev server reads public/ in place.
 */
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { copyFile, mkdir, readdir, readFile, rm, stat } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pipeline } from 'node:stream/promises';
import type { Plugin } from 'vite';

/** Where the site serves its own archive from, under dist/ (see src/config.ts). */
const ARCHIVE = 'tiles/schleswig-holstein.pmtiles';

/** The font stacks src/style/frasch-bright.json names, which scripts/fetch-fonts.sh fetches. */
const FONTS = ['Noto Sans Regular', 'Noto Sans Italic', 'Noto Sans Bold'];

/** The web/ root a build runs in, the dist/ it writes, and whether VITE_TILES_URL is set. */
export interface TilesBuild {
  root: string;
  outDir: string;
  external: boolean;
}

async function lockValue(root: string, key: string): Promise<string> {
  const lock = await readFile(join(root, 'tiles.lock'), 'utf8');
  return lock.match(new RegExp(`^${key}=(.*)$`, 'm'))?.[1] ?? '';
}

function cachedArchive(root: string, sha256: string): string {
  return join(root, '.cache/tiles', `${sha256}.pmtiles`);
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
  const pinned = await lockValue(root, 'ARCHIVE_SHA256');
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

async function fontProblem(root: string): Promise<string | undefined> {
  const missing = [];
  for (const font of FONTS) {
    const dir = `public/fonts/${font}`;
    if (!(await stat(join(root, dir)).catch(() => undefined))?.isDirectory()) missing.push(dir);
  }
  if (missing.length > 0) return `the glyphs are not fetched (${missing.join(', ')}): run \`npm run fetch-assets\``;
}

/** What the build lacks, one line each, when it starts; empty when it has all it needs. */
export async function assetProblems({ root, external }: Omit<TilesBuild, 'outDir'>): Promise<string[]> {
  const problems = [await fontProblem(root), external ? undefined : await archiveProblem(root)];
  return problems.filter((p) => p !== undefined);
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
  const sha256 = await lockValue(root, 'ARCHIVE_SHA256');
  await mkdir(join(outDir, 'tiles'), { recursive: true });
  await copyFile(cachedArchive(root, sha256), join(outDir, ARCHIVE));
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
