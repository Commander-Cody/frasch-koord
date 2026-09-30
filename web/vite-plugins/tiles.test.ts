// @vitest-environment node
/**
 * The build step of vite-plugins/tiles.ts on a temp web/ root: what it lets
 * into dist/tiles/, and what makes it refuse to build.
 */
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { assetProblems, shipTiles } from './tiles.ts';

const PINNED = 'the published archive';
const PINNED_SHA256 = createHash('sha256').update(PINNED).digest('hex');

/** A web/ checkout: the lock, the fetched archive in the cache. */
let root: string;
let outDir: string;

function put(path: string, text: string): void {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'tiles-plugin-'));
  outDir = join(root, 'dist');
  put('tiles.lock', `ARCHIVE_URL=https://example.org/schleswig-holstein.pmtiles\nARCHIVE_SHA256=${PINNED_SHA256}\n`);
  put(`.cache/tiles/${PINNED_SHA256}.pmtiles`, PINNED);
  for (const font of ['Noto Sans Regular', 'Noto Sans Italic', 'Noto Sans Bold']) put(`public/fonts/${font}/0-255.pbf`, '');
  // What Vite copied from public/tiles/: a local build behind the dev symlink.
  put('dist/tiles/schleswig-holstein.pmtiles', 'a local build');
  put('dist/tiles/.gitkeep', '');
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('shipTiles', () => {
  it('ships the pinned archive, not what public/tiles held', async () => {
    await shipTiles({ root, outDir, external: false });

    expect(readFileSync(join(outDir, 'tiles/schleswig-holstein.pmtiles'), 'utf8')).toBe(PINNED);
  });

  it('ships no archive when the tiles are hosted elsewhere', async () => {
    await shipTiles({ root, outDir, external: true });

    expect(readdirSync(join(outDir, 'tiles'))).toEqual(['.gitkeep']);
  });
});

describe('assetProblems', () => {
  it('passes a checkout with the glyphs and the pinned archive', async () => {
    expect(await assetProblems({ root, external: false })).toEqual([]);
  });

  it('refuses a build without the fetched archive', async () => {
    rmSync(join(root, '.cache'), { recursive: true });

    expect(await assetProblems({ root, external: false })).toEqual([
      'the pinned tile archive is not fetched: run `npm run fetch-assets` (or set VITE_TILES_URL)',
    ]);
  });

  it('refuses a fetched archive that is not the pinned one', async () => {
    put(`.cache/tiles/${PINNED_SHA256}.pmtiles`, 'a truncated download');

    expect(await assetProblems({ root, external: false })).toEqual([
      `.cache/tiles/${PINNED_SHA256}.pmtiles does not match tiles.lock: run \`npm run fetch-assets\` again`,
    ]);
  });

  it('refuses a build without the glyphs, wherever the tiles come from', async () => {
    rmSync(join(root, 'public/fonts/Noto Sans Italic'), { recursive: true });

    expect(await assetProblems({ root, external: true })).toEqual([
      'the glyphs are not fetched (public/fonts/Noto Sans Italic): run `npm run fetch-assets`',
    ]);
  });

  it('refuses a lock that pins no archive', async () => {
    put('tiles.lock', 'ARCHIVE_URL=https://example.org/schleswig-holstein.pmtiles\n');

    expect(await assetProblems({ root, external: false })).toEqual(['tiles.lock pins no sha256 (ARCHIVE_SHA256=)']);
  });
});
