// @vitest-environment node
/**
 * vite-plugins/glyphs.ts: which glyph ranges the labels need, read off the
 * style and the tile archive, and what a build refuses.
 */
import { mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import type { StyleSpecification } from 'maplibre-gl';
import { build, createLogger } from 'vite';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import glyphs, { archiveLabels, glyphProblems, renderedFields } from './glyphs.ts';
import { type TestTile, writeTestArchive } from './testArchive.ts';

const LATIN = ['0-255', '256-511'];

describe('glyphProblems', () => {
  it('passes labels whose characters all lie in the shipped ranges', () => {
    const labels = [
      { text: 'Hoorne: äöüå', uppercase: false },
      { text: 'Lunham, Kairem đā', uppercase: false },
    ];

    expect(glyphProblems(labels, LATIN)).toEqual([]);
  });

  it('names the range a stray character needs, once, with a label it is in', () => {
    const labels = [
      { text: 'Stråt – Bütjebel', uppercase: false },
      { text: 'Wai ‑ Hiir', uppercase: false },
      { text: 'B 5 Ⅱ', uppercase: false },
    ];

    expect(glyphProblems(labels, LATIN)).toEqual([
      '"–" (U+2013) in "Stråt – Bütjebel" needs the glyph range 8192-8447, which fonts.lock does not list',
      '"Ⅱ" (U+2161) in "B 5 Ⅱ" needs the glyph range 8448-8703, which fonts.lock does not list',
    ]);
  });

  it('checks the upper-case form of a label a layer shows in capitals', () => {
    // ÿ is Latin-1, its capital Ÿ (U+0178) is Latin Extended-A
    expect(glyphProblems([{ text: 'Hÿl', uppercase: false }], ['0-255'])).toEqual([]);
    expect(glyphProblems([{ text: 'Hÿl', uppercase: true }], ['0-255'])).toEqual([
      '"Ÿ" (U+0178) in "HŸL" needs the glyph range 256-511, which fonts.lock does not list',
    ]);
  });
});

describe('renderedFields', () => {
  /** A style of these layers. */
  function style(...layers: Record<string, unknown>[]): StyleSpecification {
    return { version: 8, sources: {}, layers } as unknown as StyleSpecification;
  }

  it("reads the properties a layer's text-field takes, expression or template", () => {
    const fields = renderedFields(
      style(
        {
          id: 'village',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'place',
          layout: { 'text-field': ['coalesce', ['get', 'name:frr'], ['get', 'name']] },
        },
        {
          id: 'shield',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'transportation_name',
          layout: { 'text-field': '{ref}', 'icon-image': 'road_{ref_length}' },
        },
      ),
    );

    expect(fields).toEqual([
      { sourceLayer: 'place', key: 'name:frr', uppercase: false },
      { sourceLayer: 'place', key: 'name', uppercase: false },
      { sourceLayer: 'transportation_name', key: 'ref', uppercase: false },
    ]);
  });

  it('marks the fields a layer shows in capitals, and leaves out layers without text', () => {
    const fields = renderedFields(
      style(
        { id: 'water', type: 'fill', source: 'openmaptiles', 'source-layer': 'water' },
        {
          id: 'oneway',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'transportation',
          layout: { 'icon-image': 'oneway' },
        },
        {
          id: 'island',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'place',
          layout: { 'text-field': ['get', 'name'], 'text-transform': 'uppercase' },
        },
        {
          id: 'village',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'place',
          layout: { 'text-field': ['get', 'name'] },
        },
        {
          id: 'town',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'place',
          layout: { 'text-field': ['get', 'name'] },
        },
      ),
    );

    expect(fields).toEqual([
      { sourceLayer: 'place', key: 'name', uppercase: true },
      { sourceLayer: 'place', key: 'name', uppercase: false },
    ]);
  });
});

describe('archiveLabels', () => {
  let dir: string;

  beforeEach(() => {
    dir = mkdtempSync(join(tmpdir(), 'glyphs-archive-'));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  const TILES: TestTile[] = [
    {
      z: 0,
      x: 0,
      y: 0,
      layers: {
        place: [{ name: 'Naibel', 'name:de': 'Niebüll', class: 'town' }],
        water_name: [{ name: 'Nordsee' }],
      },
    },
    { z: 1, x: 1, y: 0, layers: { place: [{ name: 'Naibel' }, { name: 'Hoorne' }] } },
  ];

  const FIELDS = [
    { sourceLayer: 'place', key: 'name', uppercase: false },
    { sourceLayer: 'place', key: 'name:de', uppercase: true },
  ];

  it('collects the values of the shown fields, each once', async () => {
    const archive = join(dir, 'test.pmtiles');
    writeTestArchive(archive, TILES);

    expect(await archiveLabels(archive, FIELDS)).toEqual([
      { text: 'Naibel', uppercase: false },
      { text: 'Niebüll', uppercase: true },
      { text: 'Hoorne', uppercase: false },
    ]);
  });

  it('reads gzip-compressed tiles, as Planetiler writes them', async () => {
    const archive = join(dir, 'test.pmtiles');
    writeTestArchive(archive, TILES, { gzip: true });

    expect(await archiveLabels(archive, FIELDS)).toHaveLength(3);
  });

  it('reads the tiles behind a leaf directory', async () => {
    const archive = join(dir, 'test.pmtiles');
    writeTestArchive(archive, TILES, { leaf: true });

    expect(await archiveLabels(archive, FIELDS)).toHaveLength(3);
  });
});

describe('a vite build with the plugin', () => {
  const STACKS = ['Noto Sans Regular', 'Noto Sans Italic', 'Noto Sans Bold'];
  const SHA256 = 'a'.repeat(64);
  const ARCHIVE = `.cache/tiles/${SHA256}.pmtiles`;

  /** A web/ checkout: both locks, the fetched glyphs, the pinned archive. */
  let root: string;

  function put(path: string, text: string): void {
    const file = join(root, path);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, text);
  }

  /** The pinned archive, with one place feature of these properties. */
  function pinArchive(place: Record<string, string>): void {
    mkdirSync(join(root, '.cache/tiles'), { recursive: true });
    writeTestArchive(join(root, ARCHIVE), [{ z: 0, x: 0, y: 0, layers: { place: [place] } }]);
  }

  function viteBuild(logger = createLogger('silent')) {
    return build({
      root,
      configFile: false,
      customLogger: logger,
      logLevel: 'silent',
      plugins: [glyphs()],
    });
  }

  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'glyphs-plugin-'));
    put('index.html', '<!doctype html><title>Frasch Maps</title>');
    put('fonts.lock', `STACKS=${STACKS.join(',')}\nRANGES=0-255 256-511\n`);
    put('tiles.lock', `ARCHIVE_SHA256=${SHA256}\n`);
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

  it('ships the listed ranges when every label fits them', async () => {
    await viteBuild();

    for (const stack of STACKS) {
      expect(readdirSync(join(root, 'dist/fonts', stack)).sort()).toEqual([
        '0-255.pbf',
        '256-511.pbf',
      ]);
    }
  });

  it('refuses a label the shipped ranges cannot show', async () => {
    pinArchive({ 'frasch:local': 'Stråt – Bütjebel' });

    await expect(viteBuild()).rejects.toThrow(
      '"–" (U+2013) in "Stråt – Bütjebel" needs the glyph range 8192-8447',
    );
  });

  it("ignores what the site's style does not show", async () => {
    pinArchive({ 'name:nonlatin': '北京', class: 'town' });

    await viteBuild();
  });

  it('refuses glyphs that are not the listed ranges', async () => {
    put('public/fonts/Noto Sans Bold/20224-20479.pbf', '');
    rmSync(join(root, 'public/fonts/Noto Sans Italic'), { recursive: true });

    await expect(viteBuild()).rejects.toThrow(
      'public/fonts/ does not hold the glyphs fonts.lock lists (missing: Noto Sans Italic/0-255.pbf, Noto Sans Italic/256-511.pbf; not listed: Noto Sans Bold/20224-20479.pbf): run `npm run fetch-assets`',
    );
  });

  it('checks the pinned archive with VITE_TILES_URL too, when it is fetched', async () => {
    vi.stubEnv('VITE_TILES_URL', 'pmtiles://https://example.org/schleswig-holstein.pmtiles');
    pinArchive({ 'frasch:local': 'B 5 Ⅱ' });

    await expect(viteBuild()).rejects.toThrow('needs the glyph range 8448-8703');
  });

  it('warns that it checked no labels with VITE_TILES_URL and no fetched archive', async () => {
    vi.stubEnv('VITE_TILES_URL', 'pmtiles://https://example.org/schleswig-holstein.pmtiles');
    rmSync(join(root, '.cache'), { recursive: true });
    const logger = createLogger('silent');
    const warn = vi.spyOn(logger, 'warn');

    await viteBuild(logger);

    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('the labels were not checked against the glyph ranges'),
      expect.anything(),
    );
  });
});
