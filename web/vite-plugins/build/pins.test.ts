// @vitest-environment node
/** vite-plugins/build/pins.ts: what web/tiles.lock and web/fonts.lock pin. */
import { describe, expect, it } from 'vitest';

import { readFontsPin, readTilesPin } from './pins.ts';
import { tempDirPerTest } from '../testDir.ts';

const SHA256 = 'b45cefc4ab0d1367e09d046bdfcb0252a654c95ab1b9a8bb6dad6b9505691ea3';

/** A web/ checkout with nothing but its locks. */
const web = tempDirPerTest('pins-');

describe('readTilesPin', () => {
  it('reads the archive tiles.lock pins, and where the fetch keeps it', async () => {
    web.put(
      'tiles.lock',
      `# the archive\nARCHIVE_URL=https://example.org/sh.pmtiles\nARCHIVE_SHA256=${SHA256}\n`,
    );

    expect(await readTilesPin(web.path)).toEqual({
      url: 'https://example.org/sh.pmtiles',
      sha256: SHA256,
      name: 'sh.pmtiles',
      cachePath: `.cache/tiles/${SHA256}.pmtiles`,
    });
  });

  it('refuses a lock whose URL names no archive file', async () => {
    web.put('tiles.lock', `ARCHIVE_URL=https://example.org/tiles/\nARCHIVE_SHA256=${SHA256}\n`);

    await expect(readTilesPin(web.path)).rejects.toThrow(
      'tiles.lock pins no tile archive (ARCHIVE_URL=https://example.org/tiles/): it has to end in <name>.pmtiles',
    );
  });

  it('refuses a lock whose sha256 is not one', async () => {
    web.put('tiles.lock', 'ARCHIVE_SHA256=../../elsewhere\n');

    await expect(readTilesPin(web.path)).rejects.toThrow(
      'tiles.lock pins no sha256 (ARCHIVE_SHA256=../../elsewhere)',
    );
  });
});

describe('readFontsPin', () => {
  it('lists the listed ranges of every listed stack as the files to ship', async () => {
    web.put(
      'fonts.lock',
      `FONTS_URL=https://example.org/noto.zip\nFONTS_SHA256=${SHA256}\n` +
        'STACKS=Noto Sans Regular,Noto Sans Bold\nRANGES=0-255 256-511\n',
    );

    expect(await readFontsPin(web.path)).toEqual({
      url: 'https://example.org/noto.zip',
      sha256: SHA256,
      stacks: ['Noto Sans Regular', 'Noto Sans Bold'],
      ranges: ['0-255', '256-511'],
      listedFiles: [
        'Noto Sans Regular/0-255.pbf',
        'Noto Sans Regular/256-511.pbf',
        'Noto Sans Bold/0-255.pbf',
        'Noto Sans Bold/256-511.pbf',
      ],
    });
  });
});
