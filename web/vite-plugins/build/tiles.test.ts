// @vitest-environment node
/**
 * vite-plugins/build/tiles.ts on a temp web/ root: what about the pinned
 * archive and public/tiles/ makes a build refuse.
 */
import { createHash } from 'node:crypto';
import { rmSync } from 'node:fs';
import { join } from 'node:path';
import { beforeEach, describe, expect, it } from 'vitest';

import { checkTiles } from './tiles.ts';
import { tempDirPerTest } from '../testDir.ts';

const PINNED = 'the published archive';
const PINNED_SHA256 = createHash('sha256').update(PINNED).digest('hex');

/** A web/ checkout: the lock and the fetched archive in the cache. */
const web = tempDirPerTest('tiles-plugin-');

beforeEach(() => {
  web.put(
    'tiles.lock',
    `ARCHIVE_URL=https://example.org/schleswig-holstein.pmtiles\nARCHIVE_SHA256=${PINNED_SHA256}\n`,
  );
  web.put(`.cache/tiles/${PINNED_SHA256}.pmtiles`, PINNED);
});

/** What a build would refuse, with VITE_TILES_URL set or not. */
async function tilesProblems(external: boolean): Promise<string[]> {
  return (await checkTiles({ root: web.path, external })).problems;
}

describe('checkTiles', () => {
  it('passes a checkout with the pinned archive', async () => {
    expect(await tilesProblems(false)).toEqual([]);
  });

  it('refuses a build without the fetched archive', async () => {
    rmSync(join(web.path, '.cache'), { recursive: true });

    expect(await tilesProblems(false)).toEqual([
      'the pinned tile archive is not fetched: run `npm run fetch-assets` (or set VITE_TILES_URL)',
    ]);
  });

  it('refuses a fetched archive that is not the pinned one', async () => {
    web.put(`.cache/tiles/${PINNED_SHA256}.pmtiles`, 'a truncated download');

    expect(await tilesProblems(false)).toEqual([
      `.cache/tiles/${PINNED_SHA256}.pmtiles does not match tiles.lock: run \`npm run fetch-assets\` again`,
    ]);
  });

  it('refuses a lock that pins no archive', async () => {
    web.put('tiles.lock', 'ARCHIVE_URL=https://example.org/schleswig-holstein.pmtiles\n');

    expect(await tilesProblems(false)).toEqual(['tiles.lock pins no sha256 (ARCHIVE_SHA256=)']);
  });

  it('passes a link in public/tiles/ to an archive that is there', async () => {
    web.link(
      'public/tiles/schleswig-holstein.pmtiles',
      `../../.cache/tiles/${PINNED_SHA256}.pmtiles`,
    );

    expect(await tilesProblems(false)).toEqual([]);
  });

  it('refuses a link in public/tiles/ to an archive that is not built', async () => {
    web.link(
      'public/tiles/schleswig-holstein.pmtiles',
      '../../own-tiles/schleswig-holstein.pmtiles',
    );

    expect(await tilesProblems(false)).toEqual([
      'public/tiles/schleswig-holstein.pmtiles links to ../../own-tiles/schleswig-holstein.pmtiles, which does not exist: the dev server shows no map and `npm run build` stops. Build the tiles, or remove the link and run `npm run fetch-assets`',
    ]);
  });

  it('names every dangling link in public/tiles/, and only those', async () => {
    web.link('public/tiles/denmark.pmtiles', '../../own-tiles/denmark.pmtiles');
    web.link('public/tiles/halligen.pmtiles', `../../.cache/tiles/${PINNED_SHA256}.pmtiles`);
    web.link(
      'public/tiles/schleswig-holstein.pmtiles',
      '../../own-tiles/schleswig-holstein.pmtiles',
    );

    const problems = await tilesProblems(false);

    expect(problems.map((problem) => problem.split(' links to ')[0]).sort()).toEqual([
      'public/tiles/denmark.pmtiles',
      'public/tiles/schleswig-holstein.pmtiles',
    ]);
  });

  it('refuses a dangling link with VITE_TILES_URL too', async () => {
    web.link('public/tiles/denmark.pmtiles', '../../own-tiles/denmark.pmtiles');

    expect(await tilesProblems(true)).toEqual([
      'public/tiles/denmark.pmtiles links to ../../own-tiles/denmark.pmtiles, which does not exist: the dev server shows no map and `npm run build` stops. Build the tiles, or remove the link and run `npm run fetch-assets`',
    ]);
  });
});
