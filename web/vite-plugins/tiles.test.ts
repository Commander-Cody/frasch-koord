// @vitest-environment node
/**
 * vite-plugins/tiles.ts on a temp web/ root: what a build lets
 * into dist/tiles/, and what makes it refuse to build.
 */
import { createHash } from 'node:crypto';
import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { build } from 'vite';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import tiles, { assetProblems } from './tiles.ts';

const PINNED = 'the published archive';
const PINNED_SHA256 = createHash('sha256').update(PINNED).digest('hex');

/** A web/ checkout: the lock and the fetched archive in the cache. */
let root: string;
let outDir: string;

function put(path: string, text: string): void {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text);
}

/** A symlink at `path` to `target`, which need not exist. */
function link(path: string, target: string): void {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  symlinkSync(target, file);
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'tiles-plugin-'));
  outDir = join(root, 'dist');
  put(
    'tiles.lock',
    `ARCHIVE_URL=https://example.org/schleswig-holstein.pmtiles\nARCHIVE_SHA256=${PINNED_SHA256}\n`,
  );
  put(`.cache/tiles/${PINNED_SHA256}.pmtiles`, PINNED);
});

afterEach(() => {
  vi.unstubAllEnvs();
  rmSync(root, { recursive: true, force: true });
});

describe('assetProblems', () => {
  it('passes a checkout with the pinned archive', async () => {
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

  it('refuses a lock that pins no archive', async () => {
    put('tiles.lock', 'ARCHIVE_URL=https://example.org/schleswig-holstein.pmtiles\n');

    expect(await assetProblems({ root, external: false })).toEqual([
      'tiles.lock pins no sha256 (ARCHIVE_SHA256=)',
    ]);
  });

  it('passes a link in public/tiles/ to an archive that is there', async () => {
    link('public/tiles/schleswig-holstein.pmtiles', `../../.cache/tiles/${PINNED_SHA256}.pmtiles`);

    expect(await assetProblems({ root, external: false })).toEqual([]);
  });

  it('refuses a link in public/tiles/ to an archive that is not built', async () => {
    link('public/tiles/schleswig-holstein.pmtiles', '../../own-tiles/schleswig-holstein.pmtiles');

    expect(await assetProblems({ root, external: false })).toEqual([
      'public/tiles/schleswig-holstein.pmtiles links to ../../own-tiles/schleswig-holstein.pmtiles, which does not exist: build the tiles, or remove the link and run `npm run fetch-tiles`',
    ]);
  });

  it('names every dangling link in public/tiles/, and only those', async () => {
    link('public/tiles/denmark.pmtiles', '../../own-tiles/denmark.pmtiles');
    link('public/tiles/halligen.pmtiles', `../../.cache/tiles/${PINNED_SHA256}.pmtiles`);
    link('public/tiles/schleswig-holstein.pmtiles', '../../own-tiles/schleswig-holstein.pmtiles');

    const problems = await assetProblems({ root, external: false });

    expect(problems.map((problem) => problem.split(' links to ')[0]).sort()).toEqual([
      'public/tiles/denmark.pmtiles',
      'public/tiles/schleswig-holstein.pmtiles',
    ]);
  });

  it('refuses a dangling link with VITE_TILES_URL too', async () => {
    link('public/tiles/denmark.pmtiles', '../../own-tiles/denmark.pmtiles');

    expect(await assetProblems({ root, external: true })).toEqual([
      'public/tiles/denmark.pmtiles links to ../../own-tiles/denmark.pmtiles, which does not exist: build the tiles, or remove the link and run `npm run fetch-tiles`',
    ]);
  });
});

describe('a vite build with the plugin', () => {
  function viteBuild() {
    put('index.html', '<!doctype html><title>Frasch Maps</title>');
    return build({ root, logLevel: 'silent', configFile: false, plugins: [tiles()] });
  }

  it('stops with what is missing, not with what it could not copy', async () => {
    rmSync(join(root, '.cache'), { recursive: true });

    await expect(viteBuild()).rejects.toThrow('npm run fetch-assets');
  });

  it('stops at a dangling link in public/tiles/ with the ways out', async () => {
    link('public/tiles/schleswig-holstein.pmtiles', '../../own-tiles/schleswig-holstein.pmtiles');

    await expect(viteBuild()).rejects.toThrow('remove the link and run `npm run fetch-tiles`');
  });

  it("ships the pinned archive in place of public/tiles' own", async () => {
    put('public/tiles/.gitkeep', '');
    put('public/tiles/schleswig-holstein.pmtiles', 'a local build');
    put('public/tiles/denmark.pmtiles', 'another local build');

    await viteBuild();

    expect(readdirSync(join(outDir, 'tiles')).sort()).toEqual([
      '.gitkeep',
      'schleswig-holstein.pmtiles',
    ]);
    expect(readFileSync(join(outDir, 'tiles/schleswig-holstein.pmtiles'), 'utf8')).toBe(PINNED);
  });

  it('ships no archive with VITE_TILES_URL', async () => {
    put('public/tiles/schleswig-holstein.pmtiles', 'a local build');
    vi.stubEnv('VITE_TILES_URL', 'pmtiles://https://example.org/schleswig-holstein.pmtiles');

    await viteBuild();

    expect(readdirSync(join(outDir, 'tiles'))).toEqual([]);
  });
});
