// @vitest-environment node
/**
 * scripts/fetch-assets.ts on a temp web/ root whose locks pin files a local
 * HTTP server hands out, as a release server would.
 */
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, readlinkSync, rmSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { join } from 'node:path';
import { zipSync } from 'fflate';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { fetchFonts, fetchTiles, type Report } from './fetch-assets.ts';
import { tempDirPerTest } from '../vite-plugins/testDir.ts';

const LINK = 'public/tiles/schleswig-holstein.pmtiles';
const PUBLISHED = 'the published archive';
const PUBLISHED_SHA256 = createHash('sha256').update(PUBLISHED).digest('hex');

/** A web/ checkout, and the files the release server hands out by name. */
const web = tempDirPerTest('fetch-assets-web-');
let published: Map<string, Buffer | string>;
let server: Server;
let serverUrl: string;
/** What the fetch reported, line by line. */
let info: string[];
let warnings: string[];
const report: Report = {
  info: (line) => info.push(line),
  warn: (line) => warnings.push(line),
};

function pinTiles(url: string, sha256: string): void {
  web.put('tiles.lock', `# pinned\nARCHIVE_URL=${url}\nARCHIVE_SHA256=${sha256}\n`);
}

beforeEach(async () => {
  info = [];
  warnings = [];
  published = new Map([['schleswig-holstein.pmtiles', PUBLISHED]]);
  server = createServer((req, res) => {
    const file = published.get(req.url!.slice(1));
    res.writeHead(file === undefined ? 404 : 200).end(file ?? 'Not Found');
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  serverUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  web.put('public/tiles/.gitkeep', '');
  pinTiles(`${serverUrl}/schleswig-holstein.pmtiles`, PUBLISHED_SHA256);
});

afterEach(async () => {
  await new Promise((resolve) => server.close(resolve));
});

describe('fetchTiles', () => {
  it('fetches the pinned archive and links the site to it', async () => {
    await fetchTiles(web.path, report);

    expect(readFileSync(join(web.path, `.cache/tiles/${PUBLISHED_SHA256}.pmtiles`), 'utf8')).toBe(
      PUBLISHED,
    );
    expect(readlinkSync(join(web.path, LINK))).toBe(
      `../../.cache/tiles/${PUBLISHED_SHA256}.pmtiles`,
    );
  });

  it('links the archive under the name it is published by', async () => {
    published.set('denmark.pmtiles', PUBLISHED);
    pinTiles(`${serverUrl}/denmark.pmtiles`, PUBLISHED_SHA256);

    await fetchTiles(web.path, report);

    expect(readlinkSync(join(web.path, 'public/tiles/denmark.pmtiles'))).toBe(
      `../../.cache/tiles/${PUBLISHED_SHA256}.pmtiles`,
    );
  });

  it('drops its own link of an archive published by another name', async () => {
    web.link(LINK, `../../.cache/tiles/${'0'.repeat(64)}.pmtiles`);
    published.set('denmark.pmtiles', PUBLISHED);
    pinTiles(`${serverUrl}/denmark.pmtiles`, PUBLISHED_SHA256);

    await fetchTiles(web.path, report);

    expect(readdirSync(join(web.path, 'public/tiles')).sort()).toEqual([
      '.gitkeep',
      'denmark.pmtiles',
    ]);
  });

  it("keeps a tile builder's own link of another name than the pinned archive's", async () => {
    web.put('own-tiles/schleswig-holstein.pmtiles', 'a local build');
    web.link(LINK, '../../own-tiles/schleswig-holstein.pmtiles');
    published.set('denmark.pmtiles', PUBLISHED);
    pinTiles(`${serverUrl}/denmark.pmtiles`, PUBLISHED_SHA256);

    await fetchTiles(web.path, report);

    expect(readlinkSync(join(web.path, LINK))).toBe('../../own-tiles/schleswig-holstein.pmtiles');
  });

  it('fetches nothing when the pinned archive is already there', async () => {
    await fetchTiles(web.path, report);
    published.clear();

    await fetchTiles(web.path, report);

    expect(readFileSync(join(web.path, LINK), 'utf8')).toBe(PUBLISHED);
  });

  it("keeps a tile builder's own archive linked, and says so", async () => {
    web.put('own-tiles/schleswig-holstein.pmtiles', 'a local build');
    web.link(LINK, '../../own-tiles/schleswig-holstein.pmtiles');

    await fetchTiles(web.path, report);

    expect(readlinkSync(join(web.path, LINK))).toBe('../../own-tiles/schleswig-holstein.pmtiles');
    expect(info).toContainEqual(expect.stringContaining(`kept ${LINK}`));
  });

  it("keeps a tile builder's link to an archive that is not built, and warns", async () => {
    web.link(LINK, '../../own-tiles/schleswig-holstein.pmtiles');

    await fetchTiles(web.path, report);

    expect(readlinkSync(join(web.path, LINK))).toBe('../../own-tiles/schleswig-holstein.pmtiles');
    expect(info).not.toContainEqual(expect.stringContaining('kept'));
    expect(warnings).toEqual([
      `${LINK} links to ../../own-tiles/schleswig-holstein.pmtiles, which does not exist: the dev server shows no map and \`npm run build\` stops. Build the tiles, or remove the link and run \`npm run fetch-assets\``,
    ]);
  });

  it('moves on from an earlier pinned archive, and drops it', async () => {
    const earlier = `.cache/tiles/${'0'.repeat(64)}.pmtiles`;
    web.put(earlier, "last month's archive");
    web.link(LINK, `../../${earlier}`);

    await fetchTiles(web.path, report);

    expect(readlinkSync(join(web.path, LINK))).toBe(
      `../../.cache/tiles/${PUBLISHED_SHA256}.pmtiles`,
    );
    expect(readdirSync(join(web.path, '.cache/tiles'))).toEqual([`${PUBLISHED_SHA256}.pmtiles`]);
  });

  it('repoints its own link to an earlier archive that is gone, without a warning', async () => {
    web.link(LINK, `../../.cache/tiles/${'0'.repeat(64)}.pmtiles`);

    await fetchTiles(web.path, report);

    expect(readlinkSync(join(web.path, LINK))).toBe(
      `../../.cache/tiles/${PUBLISHED_SHA256}.pmtiles`,
    );
    expect(warnings).toEqual([]);
  });

  it('refuses an archive that is not the pinned one, and leaves nothing of it', async () => {
    published.set('schleswig-holstein.pmtiles', 'a re-uploaded archive');

    await expect(fetchTiles(web.path, report)).rejects.toThrow('checksum mismatch');
    expect(readdirSync(join(web.path, 'public/tiles'))).toEqual(['.gitkeep']);
    expect(readdirSync(join(web.path, '.cache/tiles'))).toEqual([]);
  });

  it('refuses a download the server does not have, naming it', async () => {
    published.clear();

    await expect(fetchTiles(web.path, report)).rejects.toThrow(
      `download failed: ${serverUrl}/schleswig-holstein.pmtiles (HTTP 404)`,
    );
  });
});

describe('fetchFonts', () => {
  const STACKS = ['Noto Sans Regular', 'Noto Sans Italic', 'Noto Sans Bold'];
  /** What the zip has of each stack; fonts.lock lists the first two. */
  const ZIPPED = ['0-255', '256-511', '20224-20479'];
  const LISTED = ['0-255.pbf', '256-511.pbf'];

  let zipSha256: string;

  function pinFonts({ url = `${serverUrl}/noto-sans.zip`, ranges = '0-255 256-511' } = {}): void {
    web.put(
      'fonts.lock',
      `# pinned\nFONTS_URL=${url}\nFONTS_SHA256=${zipSha256}\nSTACKS=${STACKS.join(',')}\nRANGES=${ranges}\n`,
    );
  }

  /** Puts these ranges of every stack into public/fonts/, as an earlier fetch left them. */
  function install(ranges: string[]): void {
    for (const stack of STACKS) {
      for (const range of ranges) web.put(`public/fonts/${stack}/${range}.pbf`, `old ${range}`);
    }
  }

  function installed(stack: string): string[] {
    return readdirSync(join(web.path, 'public/fonts', stack)).sort();
  }

  function glyphs(path: string): string {
    return readFileSync(join(web.path, 'public/fonts', path), 'utf8');
  }

  beforeEach(() => {
    const files = Object.fromEntries(
      STACKS.flatMap((stack) =>
        ZIPPED.map((range) => [
          `noto-sans/${stack}/${range}.pbf`,
          new TextEncoder().encode(`${stack} ${range}`),
        ]),
      ),
    );
    const zip = Buffer.from(zipSync(files));
    published.set('noto-sans.zip', zip);
    zipSha256 = createHash('sha256').update(zip).digest('hex');
    pinFonts();
  });

  it('fetches the listed ranges of each stack, and no others', async () => {
    await fetchFonts(web.path, report);

    for (const stack of STACKS) expect(installed(stack)).toEqual(LISTED);
    expect(glyphs('Noto Sans Bold/256-511.pbf')).toBe('Noto Sans Bold 256-511');
  });

  it('leaves an install of exactly the listed ranges alone, fetching nothing', async () => {
    install(['0-255', '256-511']);
    published.clear();

    await fetchFonts(web.path, report);

    expect(glyphs('Noto Sans Bold/0-255.pbf')).toBe('old 0-255');
  });

  it('prunes an earlier, fuller install down to the listed ranges, fetching nothing', async () => {
    install(['0-255', '256-511', '20224-20479']);
    web.put('public/fonts/Noto Sans Medium/0-255.pbf', 'a stack nobody lists');
    published.clear();

    await fetchFonts(web.path, report);

    expect(readdirSync(join(web.path, 'public/fonts')).sort()).toEqual([...STACKS].sort());
    for (const stack of STACKS) expect(installed(stack)).toEqual(LISTED);
  });

  it('repairs a partial install from the download', async () => {
    install(['0-255', '256-511']);
    rmSync(join(web.path, 'public/fonts/Noto Sans Italic/256-511.pbf'));

    await fetchFonts(web.path, report);

    for (const stack of STACKS) expect(installed(stack)).toEqual(LISTED);
    expect(glyphs('Noto Sans Italic/256-511.pbf')).toBe('Noto Sans Italic 256-511');
  });

  it('refuses a listed range the download does not have, and leaves the fonts as they were', async () => {
    install(['0-255']);
    pinFonts({ ranges: '0-255 512-767' });

    await expect(fetchFonts(web.path, report)).rejects.toThrow(
      `${serverUrl}/noto-sans.zip has no range 512-767 of Noto Sans Regular`,
    );
    expect(installed('Noto Sans Bold')).toEqual(['0-255.pbf']);
  });
});
