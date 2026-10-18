// @vitest-environment node
/**
 * vite-plugins/build/glyphs.ts: which glyph ranges the labels need, read off the
 * style and the tile archive, and what a build refuses.
 */
import { join } from 'node:path';
import type { StyleSpecification } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import { archiveLabels, glyphProblems, renderedFields, siteFields } from './glyphs.ts';
import { DIALECTS } from '../../src/dialects/registry.ts';
import { type TestTile, writeTestArchive } from './testArchive.ts';
import { tempDirPerTest } from '../testDir.ts';

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

describe('siteFields', () => {
  it("reads a name layer's properties in every view, offered by the selector or not", () => {
    const base = {
      version: 8,
      sources: {},
      layers: [
        {
          id: 'place',
          type: 'symbol',
          source: 'openmaptiles',
          'source-layer': 'place',
          layout: { 'text-field': '{name}' },
        },
      ],
    } as StyleSpecification;

    const keys = siteFields(base).map((field) => field.key);
    expect(keys).toEqual(expect.arrayContaining(['frasch:local', 'name:frr', 'name:nds', 'name']));
    // Every dialect's name, whether the selector offers its view or not.
    expect(keys).toEqual(expect.arrayContaining(DIALECTS.map((d) => `name:${d.tag}`)));
  });
});

describe('archiveLabels', () => {
  const dir = tempDirPerTest('glyphs-archive-');

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
    const archive = join(dir.path, 'test.pmtiles');
    writeTestArchive(archive, TILES);

    expect(await archiveLabels(archive, FIELDS)).toEqual([
      { text: 'Naibel', uppercase: false },
      { text: 'Niebüll', uppercase: true },
      { text: 'Hoorne', uppercase: false },
    ]);
  });

  it('reads gzip-compressed tiles, as Planetiler writes them', async () => {
    const archive = join(dir.path, 'test.pmtiles');
    writeTestArchive(archive, TILES, { gzip: true });

    expect(await archiveLabels(archive, FIELDS)).toHaveLength(3);
  });

  it('reads the tiles behind a leaf directory', async () => {
    const archive = join(dir.path, 'test.pmtiles');
    writeTestArchive(archive, TILES, { leaf: true });

    expect(await archiveLabels(archive, FIELDS)).toHaveLength(3);
  });
});
