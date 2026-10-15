/**
 * What web/tiles.lock and web/fonts.lock pin: the tile archive and the
 * glyphs the site ships. `npm run fetch-assets` (scripts/fetch-assets.ts)
 * fetches them, the build (vite-plugins/build/) checks and ships them; both
 * read the locks here.
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

/** The archive's name, under public/tiles/ for the dev server and dist/tiles/ for a build. */
export const ARCHIVE_NAME = 'schleswig-holstein.pmtiles';

/** Where the fetched archives are kept, under the web/ root, one file per sha256. */
export const TILE_CACHE_DIR = '.cache/tiles';

/** The tile archive tiles.lock pins. */
export interface TilesPin {
  url: string;
  sha256: string;
  /** Where `npm run fetch-assets` keeps it, relative to the web/ root. */
  cachePath: string;
}

/** The glyphs fonts.lock pins: these ranges of these stacks, out of the zip at `url`. */
export interface FontsPin {
  url: string;
  sha256: string;
  stacks: string[];
  ranges: string[];
  /** Every file public/fonts/ is to hold, as `<stack>/<range>.pbf`. */
  listedFiles: string[];
}

/** The `KEY=value`s of a lock file; `#` starts a comment line. */
async function readLock(root: string, name: string): Promise<Map<string, string>> {
  const text = await readFile(join(root, name), 'utf8');
  return new Map(
    [...text.matchAll(/^([A-Z0-9_]+)=(.*)$/gm)].map(([, key, value]) => [key, value.trim()]),
  );
}

export async function readTilesPin(root: string): Promise<TilesPin> {
  const lock = await readLock(root, 'tiles.lock');
  const sha256 = lock.get('ARCHIVE_SHA256') ?? '';
  // It names a file in the cache, so it has to be a hash and nothing else.
  if (!/^[0-9a-f]{64}$/.test(sha256)) {
    throw new Error(`tiles.lock pins no sha256 (ARCHIVE_SHA256=${sha256})`);
  }
  return {
    url: lock.get('ARCHIVE_URL') ?? '',
    sha256,
    cachePath: `${TILE_CACHE_DIR}/${sha256}.pmtiles`,
  };
}

export async function readFontsPin(root: string): Promise<FontsPin> {
  const lock = await readLock(root, 'fonts.lock');
  const stacks = (lock.get('STACKS') ?? '').split(',').filter(Boolean);
  const ranges = (lock.get('RANGES') ?? '').split(/\s+/).filter(Boolean);
  return {
    url: lock.get('FONTS_URL') ?? '',
    sha256: lock.get('FONTS_SHA256') ?? '',
    stacks,
    ranges,
    listedFiles: stacks.flatMap((stack) => ranges.map((range) => `${stack}/${range}.pbf`)),
  };
}
