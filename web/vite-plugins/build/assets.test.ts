// @vitest-environment node
/**
 * vite-plugins/build/assets.ts: a vite build of a tiny site on a temp web/
 * root -- both locks, the fetched glyphs and tile archive, and a script that
 * starts a stand-in MapLibre worker -- and what makes it refuse.
 */
import { createHash } from 'node:crypto';
import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { build, createLogger } from 'vite';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import assets, { buildProblems } from './assets.ts';
import { writeTestArchive } from './testArchive.ts';

const STACKS = ['Noto Sans Regular', 'Noto Sans Italic', 'Noto Sans Bold'];
/** What names.json and, unless a test says otherwise, the tiles were built from. */
const BUILT_FROM = { 'places.csv': 'aaa', 'osm_objects.json': 'bbb', extracts: [] };

/** The web/ root of the site, and the dist/ a build writes. */
let root: string;
let outDir: string;

function put(path: string, content: string): void {
  const file = join(root, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, content);
}

/**
 * Pins and fetches an archive with one place feature of these properties,
 * built from `builtFrom`: writes it to the cache under its sha256, and
 * tiles.lock pinning it.
 */
function pinArchive(place: Record<string, string>, builtFrom = BUILT_FROM): string {
  const file = join(root, '.cache/tiles/new.pmtiles');
  mkdirSync(dirname(file), { recursive: true });
  const description = JSON.stringify({ built_from: builtFrom });
  writeTestArchive(file, [{ z: 0, x: 0, y: 0, layers: { place: [place] } }], {
    metadata: { description },
  });
  const sha256 = createHash('sha256').update(readFileSync(file)).digest('hex');
  renameSync(file, join(root, `.cache/tiles/${sha256}.pmtiles`));
  put('tiles.lock', `ARCHIVE_URL=https://example.org/sh.pmtiles\nARCHIVE_SHA256=${sha256}\n`);
  return sha256;
}

function viteBuild(logger = createLogger('silent')) {
  return build({
    root,
    configFile: false,
    customLogger: logger,
    logLevel: 'silent',
    plugins: [assets()],
  });
}

beforeEach(() => {
  root = mkdtempSync(join(tmpdir(), 'assets-plugin-'));
  outDir = join(root, 'dist');
  put(
    'index.html',
    '<!doctype html><title>Frasch Maps</title><script type="module" src="/main.js"></script>',
  );
  put(
    'main.js',
    "import workerUrl from './maplibre-gl-worker.js?worker&url';\nconsole.log(workerUrl);\n",
  );
  put('maplibre-gl-worker.js', 'self.onmessage = () => {};\n');
  put('public/data/names.json', JSON.stringify({ built_from: BUILT_FROM, places: [] }));
  put('fonts.lock', `STACKS=${STACKS.join(',')}\nRANGES=0-255 256-511\n`);
  for (const stack of STACKS) {
    put(`public/fonts/${stack}/0-255.pbf`, '');
    put(`public/fonts/${stack}/256-511.pbf`, '');
  }
  pinArchive({ 'frasch:local': 'Hoorne äöüå', 'name:frr-x-solring': 'Kairem đā' });
});

afterEach(() => {
  vi.unstubAllEnvs();
  rmSync(root, { recursive: true, force: true });
});

describe('buildProblems', () => {
  it('passes a site with the pinned archive and the listed glyphs', async () => {
    expect(await buildProblems({ root, external: false })).toEqual({ problems: [], warnings: [] });
  });

  it('refuses a label the shipped ranges cannot show', async () => {
    pinArchive({ 'frasch:local': 'Stråt – Bütjebel' });

    const { problems } = await buildProblems({ root, external: false });

    expect(problems).toEqual([
      '"–" (U+2013) in "Stråt – Bütjebel" needs the glyph range 8192-8447, which fonts.lock does not list',
    ]);
  });

  it("ignores what the site's style does not show", async () => {
    pinArchive({ 'name:nonlatin': '北京', class: 'town' });

    const { problems } = await buildProblems({ root, external: false });

    expect(problems).toEqual([]);
  });

  it('refuses glyphs that are not the listed ranges', async () => {
    put('public/fonts/Noto Sans Bold/20224-20479.pbf', '');
    rmSync(join(root, 'public/fonts/Noto Sans Italic'), { recursive: true });

    const { problems } = await buildProblems({ root, external: false });

    expect(problems).toEqual([
      'public/fonts/ does not hold the glyphs fonts.lock lists (missing: Noto Sans Italic/0-255.pbf, Noto Sans Italic/256-511.pbf; not listed: Noto Sans Bold/20224-20479.pbf): run `npm run fetch-assets`',
    ]);
  });

  it('reports the tiles and the glyphs that are wrong together', async () => {
    rmSync(join(root, '.cache'), { recursive: true });
    put('public/fonts/Noto Sans Bold/20224-20479.pbf', '');

    const { problems } = await buildProblems({ root, external: false });

    expect(problems).toEqual([
      'the pinned tile archive is not fetched: run `npm run fetch-assets` (or set VITE_TILES_URL)',
      'public/fonts/ does not hold the glyphs fonts.lock lists (not listed: Noto Sans Bold/20224-20479.pbf): run `npm run fetch-assets`',
    ]);
  });

  it('names a fetched archive that is not the pinned one, without reading it', async () => {
    const sha256 = pinArchive({ 'frasch:local': 'Hoorne' });
    put(`.cache/tiles/${sha256}.pmtiles`, 'a truncated download');

    expect(await buildProblems({ root, external: false })).toEqual({
      problems: [
        `.cache/tiles/${sha256}.pmtiles does not match tiles.lock: run \`npm run fetch-assets\` again`,
      ],
      warnings: [],
    });
  });

  it('checks the pinned archive with VITE_TILES_URL too, when it is fetched', async () => {
    pinArchive({ 'frasch:local': 'B 5 Ⅱ' });

    const { problems } = await buildProblems({ root, external: true });

    expect(problems).toEqual([
      '"Ⅱ" (U+2161) in "B 5 Ⅱ" needs the glyph range 8448-8703, which fonts.lock does not list',
    ]);
  });

  it('warns that it checked nothing with VITE_TILES_URL and no fetched archive', async () => {
    rmSync(join(root, '.cache'), { recursive: true });

    expect(await buildProblems({ root, external: true })).toEqual({
      problems: [],
      warnings: [
        "no fetched tile archive matches tiles.lock, so the labels were not checked against the glyph ranges fonts.lock lists, nor its built_from against names.json's (`npm run fetch-assets` fetches it)",
      ],
    });
  });

  it('reads no archive that is not the pinned one with VITE_TILES_URL, and says so', async () => {
    const sha256 = pinArchive({ 'frasch:local': 'Hoorne' });
    put(`.cache/tiles/${sha256}.pmtiles`, 'a truncated download');

    expect(await buildProblems({ root, external: true })).toEqual({
      problems: [],
      warnings: [
        "no fetched tile archive matches tiles.lock, so the labels were not checked against the glyph ranges fonts.lock lists, nor its built_from against names.json's (`npm run fetch-assets` fetches it)",
      ],
    });
  });

  it('only refuses, without a warning, a build that has no archive and no VITE_TILES_URL', async () => {
    rmSync(join(root, '.cache'), { recursive: true });

    const { warnings } = await buildProblems({ root, external: false });

    expect(warnings).toEqual([]);
  });

  it('warns when the archive was built from other name files than names.json', async () => {
    pinArchive({ 'frasch:local': 'Hoorne' }, { ...BUILT_FROM, 'places.csv': 'older' });

    expect(await buildProblems({ root, external: false })).toEqual({
      problems: [],
      warnings: [
        'the pinned tile archive and public/data/names.json were built from different places.csv: map labels and place cards may disagree. Rebuild the index (`just rebuild index`) or rebuild and publish the tiles (`just tiles`, `just publish-tiles`)',
      ],
    });
  });
});

describe('a vite build with the plugin', () => {
  it('ships the pinned archive and the listed glyphs', async () => {
    const sha256 = pinArchive({ 'frasch:local': 'Hoorne' });

    await viteBuild();

    expect(readFileSync(join(outDir, 'tiles/schleswig-holstein.pmtiles'))).toEqual(
      readFileSync(join(root, `.cache/tiles/${sha256}.pmtiles`)),
    );
    expect(readdirSync(join(outDir, 'fonts/Noto Sans Bold')).sort()).toEqual([
      '0-255.pbf',
      '256-511.pbf',
    ]);
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
  });

  it('ships no archive with VITE_TILES_URL', async () => {
    put('public/tiles/schleswig-holstein.pmtiles', 'a local build');
    vi.stubEnv('VITE_TILES_URL', 'pmtiles://https://example.org/schleswig-holstein.pmtiles');

    await viteBuild();

    expect(readdirSync(join(outDir, 'tiles'))).toEqual([]);
  });

  it('stops at its start with what is missing, not with what it could not copy', async () => {
    rmSync(join(root, '.cache'), { recursive: true });
    mkdirSync(join(root, 'public/tiles'));
    symlinkSync('../../own-tiles/sh.pmtiles', join(root, 'public/tiles/sh.pmtiles'));

    await expect(viteBuild()).rejects.toThrow(
      /the pinned tile archive is not fetched.*\n.*public\/tiles\/sh\.pmtiles links to/,
    );
  });

  it('hands its warnings to Vite', async () => {
    pinArchive({ 'frasch:local': 'Hoorne' }, { ...BUILT_FROM, 'places.csv': 'older' });
    const logger = createLogger('silent');
    const warn = vi.spyOn(logger, 'warn');

    await viteBuild(logger);

    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('were built from different places.csv'),
      expect.anything(),
    );
  });

  it('refuses an output the build check finds a dev tool in', async () => {
    put(
      'main.js',
      "import workerUrl from './maplibre-gl-worker.js?worker&url';\nfetch('/__curate/rows', { body: workerUrl });\n",
    );

    await expect(viteBuild()).rejects.toThrow('a dev tool is in the build');
  });
});
