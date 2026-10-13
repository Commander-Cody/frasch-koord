import { describe, expect, it } from 'vitest';

import { cardEntry } from './card';
import type { CardEntry } from './entry';

/** A minimal, otherwise-empty entry, for tests that only care about a few fields. */
function entry(fields: Partial<CardEntry> = {}): CardEntry {
  return { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '', ...fields };
}

describe('cardEntry', () => {
  it('is exactly the name-list entry when there is no clicked tile', () => {
    const e = entry({ name_de: 'Niebüll' });
    expect(cardEntry(e)).toBe(e);
  });

  it('is built from the tile alone when the place has no name-list entry', () => {
    const props = { 'name:de': 'Niebüll', 'frasch:ref': 'node/1' };
    const result = cardEntry(undefined, props);
    expect(result.id).toBe('node/1');
    expect(result.name_de).toBe('Niebüll');
  });

  it("does not take a tile's generic name for its German one", () => {
    // North of the border OSM's `name` is Danish; the card must not list it as German.
    const result = cardEntry(undefined, { name: 'Ribe' });
    expect(result.name_osm).toBe('Ribe');
    expect(result.name_de).toBe('');
  });

  it('lets the entry win field by field over the tile', () => {
    const e = entry({
      names: { 'frr-x-mooring': 'EntryMooring' },
      variety: 'EntryVariety',
      name_de: 'EntryDE',
      name_da: 'EntryDA',
      kind: 'entry-kind',
    });
    const props = {
      'name:frr-x-mooring': 'TileMooring',
      'frasch:variety': 'TileVariety',
      'name:de': 'TileDE',
      'name:da': 'TileDA',
      'frasch:kind': 'tile-kind',
    };
    const result = cardEntry(e, props);
    expect(result.names['frr-x-mooring']).toBe('EntryMooring');
    expect(result.variety).toBe('EntryVariety');
    expect(result.name_de).toBe('EntryDE');
    expect(result.name_da).toBe('EntryDA');
    expect(result.kind).toBe('entry-kind');
  });

  it('fills gaps the entry leaves empty from the tile', () => {
    const e = entry(); // every optional field absent, name_de/kind empty strings
    const props = {
      'frasch:local': 'TileLocal',
      'frasch:dialect': 'tile-dialect',
      'frasch:variety': 'TileVariety',
      'name:de': 'TileDE',
      'name:da': 'TileDA',
      'frasch:kind': 'tile-kind',
    };
    const result = cardEntry(e, props);
    expect(result.local).toBe('TileLocal');
    expect(result.dialect).toBe('tile-dialect');
    expect(result.variety).toBe('TileVariety');
    expect(result.name_de).toBe('TileDE');
    expect(result.name_da).toBe('TileDA');
    expect(result.kind).toBe('tile-kind');
  });

  it('takes the local name from the tile even when the entry has one, since the tile is what the clicked label showed', () => {
    const e = entry({ local: 'EntryLocal' });
    const props = { 'frasch:local': 'TileLocal' };
    expect(cardEntry(e, props).local).toBe('TileLocal');
  });

  it('takes the dialect area from the tile together with its local name', () => {
    const e = entry({ local: 'EntryLocal', dialect: 'entry-dialect' });
    const props = { 'frasch:local': 'TileLocal', 'frasch:dialect': 'tile-dialect' };
    expect(cardEntry(e, props).dialect).toBe('tile-dialect');
  });

  it("keeps the entry's dialect area when the tile has no local name", () => {
    const e = entry({ local: 'EntryLocal', dialect: 'entry-dialect' });
    const props = { 'frasch:dialect': 'tile-dialect' };
    expect(cardEntry(e, props).dialect).toBe('entry-dialect');
  });

  it("falls back to the entry's local name when the tile has none", () => {
    const e = entry({ local: 'EntryLocal' });
    expect(cardEntry(e, { name: 'TileOSM' }).local).toBe('EntryLocal');
  });

  it('takes name_nds from the tile even when the entry has one, since the tile is what the clicked label showed', () => {
    const e = entry({ name_nds: 'EntryNDS' });
    const props = { 'name:nds': 'TileNDS' };
    expect(cardEntry(e, props).name_nds).toBe('TileNDS');
  });

  it('takes name_osm from the tile even when the entry has one, since the tile is what the clicked label showed', () => {
    const e = entry({ name_osm: 'EntryOSM' });
    expect(cardEntry(e, { name: 'TileOSM' }).name_osm).toBe('TileOSM');
  });

  it("falls back to the entry's name_osm when the tile has none", () => {
    const e = entry({ name_osm: 'EntryOSM' });
    expect(cardEntry(e, { 'name:de': 'TileDE' }).name_osm).toBe('EntryOSM');
  });

  it('fills name_osm from the tile when the entry has none', () => {
    expect(cardEntry(entry(), { name: 'TileOSM' }).name_osm).toBe('TileOSM');
  });

  it("falls back to the entry's name_nds when the tile has none", () => {
    const e = entry({ name_nds: 'EntryNDS' });
    const props = { 'name:de': 'TileDE' }; // no name:nds on this tile
    expect(cardEntry(e, props).name_nds).toBe('EntryNDS');
  });
});
