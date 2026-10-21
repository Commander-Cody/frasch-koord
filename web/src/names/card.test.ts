import { describe, expect, it } from 'vitest';
import type { LngLat } from 'maplibre-gl';

import { DIALECTS } from '../dialects/registry';
import { LOCAL_TAG } from '../dialects/views';
import type { PlaceSelection } from '../selection/placeSelection';
import { cardModel } from './card';
import type { NameEntry } from './entry';
import type { NameSource } from './resolveName';
import type { TileProps } from './tile';

const MOORING = 'frr-x-mooring';
const FERING = 'frr-x-fering';

const inDialect = (tag: string): NameSource => ({ kind: 'dialect', tag });
const FRISIAN: NameSource = { kind: 'language', language: 'frr' };
const LOW_SAXON: NameSource = { kind: 'dialect', tag: 'nds' };
const SYNNEJYSK = 'jut';
const GERMAN: NameSource = { kind: 'language', language: 'de' };
const DANISH: NameSource = { kind: 'language', language: 'da' };

/** An entry of the name list with only the names of `fields`. */
function listed(fields: Partial<NameEntry> = {}): NameEntry {
  return { id: 'place', names: {}, name_de: '', lon: 0, lat: 0, kind: '', ...fields };
}

/** A place opened from the search: its card is its entry. */
function found(fields: Partial<NameEntry>): PlaceSelection {
  const entry = listed(fields);
  return { pick: { via: 'search', ref: entry.id }, entry };
}

/** A clicked map label with the tile properties `props`, of `entry` where the list has the place. */
function clicked(props: TileProps, entry?: NameEntry): PlaceSelection {
  return { pick: { via: 'map', props, at: { lng: 0, lat: 0 } as LngLat }, entry };
}

describe('the headline', () => {
  it("is the place's name in the view, with the name it is", () => {
    const card = cardModel(found({ names: { [MOORING]: 'Naibel' }, name_de: 'Niebüll' }), MOORING);

    expect(card).toMatchObject({ headline: 'Naibel', source: inDialect(MOORING) });
  });

  it("names the area's dialect with a local form that is that dialect's name", () => {
    const wik = found({ names: { [FERING]: 'Wik' }, local: 'Wik', dialect: FERING });

    expect(cardModel(wik, LOCAL_TAG).source).toEqual({ kind: 'local', dialect: FERING });
  });

  it("names no dialect with a local form of the place's own", () => {
    // Mooring says Waiguurd: calling Woiguurd "Mooring" too would contradict the line below.
    const woiguurd = found({
      names: { [MOORING]: 'Waiguurd' },
      local: 'Woiguurd',
      dialect: MOORING,
    });

    expect(cardModel(woiguurd, LOCAL_TAG).source).toEqual({ kind: 'local' });
  });

  it('carries the variety remark of the local form where it is that form', () => {
    const place = found({ local: 'Brouersweerw', variety: 'Foortuftinge' });

    expect(cardModel(place, LOCAL_TAG).note).toBe('Foortuftinge');
  });

  it('carries no variety remark where it is another name than the local form', () => {
    const place = found({
      names: { [MOORING]: 'Naibel' },
      local: 'Brouersweerw',
      variety: 'Foortuftinge',
    });

    expect(cardModel(place, MOORING).note).toBeUndefined();
  });
});

describe('the kind', () => {
  it("is the entry's", () => {
    expect(cardModel(found({ name_de: 'Oland', kind: 'hallig' }), MOORING).kind).toBe('hallig');
  });
});

describe('the lines', () => {
  it("are the place's names in the other dialects, in the order of the registry", () => {
    const [first, second] = DIALECTS.map((d) => d.tag).filter((tag) => tag !== MOORING);
    const names = { [second]: 'Second', [MOORING]: 'Naibel', [first]: 'First' };

    expect(cardModel(found({ names }), MOORING).lines).toEqual([
      { source: inDialect(first), name: 'First' },
      { source: inDialect(second), name: 'Second' },
    ]);
  });

  it("show the name in the area's dialect once, as the local form, where the two are one", () => {
    const wik = found({
      names: { [MOORING]: 'Wiik', [FERING]: 'Wik' },
      local: 'Wik',
      dialect: FERING,
    });

    expect(cardModel(wik, MOORING).lines).toEqual([
      { source: { kind: 'local', dialect: FERING }, name: 'Wik' },
    ]);
  });

  it('give the local form its variety remark', () => {
    const place = found({
      names: { [MOORING]: 'Naibel' },
      local: 'Brouersweerw',
      variety: 'Foortuftinge',
    });

    expect(cardModel(place, MOORING).lines).toEqual([
      { source: { kind: 'local' }, name: 'Brouersweerw', note: 'Foortuftinge' },
    ]);
  });

  it('leave out a local form the headline already is, under another name', () => {
    // Niebüll lies in Mooring's own area: the dialect's name and the local form are one string.
    const naibel = found({ names: { [MOORING]: 'Naibel' }, local: 'Naibel', dialect: MOORING });

    expect(cardModel(naibel, MOORING).lines).toEqual([]);
  });

  it('end with the German and the Danish name', () => {
    const naibel = found({ names: { [MOORING]: 'Naibel' }, name_de: 'Niebüll', name_da: 'Nibøl' });

    expect(cardModel(naibel, MOORING).lines).toEqual([
      { source: GERMAN, name: 'Niebüll' },
      { source: DANISH, name: 'Nibøl' },
    ]);
  });

  it('leave out the name the headline is', () => {
    expect(cardModel(found({ name_de: 'Niebüll' }), MOORING).lines).toEqual([]);
  });

  // A known Low Saxon or Synnejysk name is shown even where it is the same
  // word as another: the reader learns that it is, not that it is unknown.
  it('show a Low Saxon name that is the same word as the German one', () => {
    const husum = found({ names: { [MOORING]: 'Hüsem', nds: 'Husum' }, name_de: 'Husum' });

    expect(cardModel(husum, MOORING).lines).toEqual([
      { source: LOW_SAXON, name: 'Husum' },
      { source: GERMAN, name: 'Husum' },
    ]);
  });

  it('show a Low Saxon name that is the same word as the headline', () => {
    const treen = found({ names: { [MOORING]: 'Treen', nds: 'Treen' }, name_de: 'Treene' });

    expect(cardModel(treen, MOORING).lines).toContainEqual({ source: LOW_SAXON, name: 'Treen' });
  });

  it('have the Low Saxon name before the German one', () => {
    const naibel = found({
      names: { [MOORING]: 'Naibel', nds: 'Niebüll op Platt' },
      name_de: 'Niebüll',
    });

    expect(cardModel(naibel, MOORING).lines.map((line) => line.source)).toEqual([
      LOW_SAXON,
      GERMAN,
    ]);
  });

  it('have the Frisian names before the Synnejysk one', () => {
    const tynne = found({ names: { [MOORING]: 'Tuner', [SYNNEJYSK]: 'Tynne', [FERING]: 'Töner' } });

    expect(cardModel(tynne, MOORING).lines.map((line) => line.source)).toEqual([
      inDialect(FERING),
      inDialect(SYNNEJYSK),
    ]);
  });

  it("call the Synnejysk name of a place in a Synnejysk area its local form, of the area's variety", () => {
    const laigem = found({
      names: { [MOORING]: 'Läigem', [SYNNEJYSK]: 'Lym' },
      local: 'Lym',
      dialect: SYNNEJYSK,
    });

    expect(cardModel(laigem, MOORING).lines).toEqual([
      { source: { kind: 'local', dialect: SYNNEJYSK }, name: 'Lym' },
    ]);
  });
});

describe('the card of a clicked label the name list does not have', () => {
  it('is that of the names its tile feature carries', () => {
    const card = cardModel(clicked({ 'name:de': 'Niebüll', name: 'Niebüll' }), MOORING);

    expect(card).toMatchObject({ headline: 'Niebüll', source: GERMAN });
  });

  // OpenMapTiles writes `name_de` on every feature: `name:de` where OSM has
  // one, the plain `name` everywhere else.
  it("does not take OpenMapTiles' name_de for a German name", () => {
    const card = cardModel(clicked({ name: 'Kalleshave', name_de: 'Kalleshave' }), MOORING);

    expect(card).toMatchObject({ headline: 'Kalleshave', source: { kind: 'unknown' }, lines: [] });
  });

  it('names the language of a generic name that is its name in that language', () => {
    const props = { name: 'Kalleshave', name_de: 'Kalleshave', 'name:da': 'Kalleshave' };

    expect(cardModel(clicked(props), MOORING).source).toEqual(DANISH);
  });

  it('does not show a generic name of unknown language below another headline', () => {
    const props = { 'name:nds': 'Niebüll op Platt', name: 'Niebüll', name_de: 'Niebüll' };

    expect(cardModel(clicked(props), LOCAL_TAG).lines).toEqual([]);
  });

  it("has the feature's kind, ours before OpenMapTiles'", () => {
    const props = { name: 'Oland', 'frasch:kind': 'hallig', class: 'island' };

    expect(cardModel(clicked(props), MOORING).kind).toBe('hallig');
  });

  it("has OpenMapTiles' class for a kind where the feature has none of ours", () => {
    expect(cardModel(clicked({ name: 'Achtrup', class: 'village' }), MOORING).kind).toBe('village');
  });

  it("lists OSM's Frisian name of no dialect", () => {
    const props = { 'name:frr': 'Söl', 'name:de': 'Sylt', name: 'Sylt' };

    expect(cardModel(clicked(props), LOCAL_TAG).lines).toEqual([{ source: FRISIAN, name: 'Söl' }]);
  });

  it("calls OSM's Frisian name of a place in a Frisian area its local form in a dialect view", () => {
    const props = {
      'frasch:local': 'Schörkeweerw',
      'frasch:dialect': 'frr-x-hallig',
      'name:frr': 'Schörkeweerw',
      name: 'Kirchwarft',
    };

    expect(cardModel(clicked(props), MOORING).source).toEqual({ kind: 'local' });
  });

  it("leaves out OSM's Frisian name where it only repeats a name on the card", () => {
    const props = { 'name:frr-x-solring': 'Söl', 'name:frr': 'Söl', name: 'Sylt' };

    expect(cardModel(clicked(props), LOCAL_TAG).lines).toEqual([
      { source: inDialect('frr-x-solring'), name: 'Söl' },
    ]);
  });
});

describe('the card of a clicked label of a listed place', () => {
  it("has the list's names rather than the tile feature's", () => {
    const entry = listed({
      names: { [MOORING]: 'Listed Mooring' },
      name_de: 'Listed German',
      name_da: 'Listed Danish',
      kind: 'hallig',
    });
    const props = {
      'name:frr-x-mooring': 'Tile Mooring',
      'name:de': 'Tile German',
      'name:da': 'Tile Danish',
      'frasch:kind': 'island',
    };

    expect(cardModel(clicked(props, entry), MOORING)).toMatchObject({
      headline: 'Listed Mooring',
      kind: 'hallig',
      lines: [
        { source: GERMAN, name: 'Listed German' },
        { source: DANISH, name: 'Listed Danish' },
      ],
    });
  });

  it('has from the tile feature what the list does not have', () => {
    // OSM's `name:da` on Föhr, where our own `da` column is empty.
    const entry = listed({ names: { [MOORING]: 'Feer' } });
    const props = { 'name:de': 'Föhr', 'name:da': 'Før', 'frasch:kind': 'island' };

    expect(cardModel(clicked(props, entry), MOORING)).toMatchObject({
      kind: 'island',
      lines: [
        { source: GERMAN, name: 'Föhr' },
        { source: DANISH, name: 'Før' },
      ],
    });
  });

  // A row may name several objects; its entry stands for the first of them.
  it("has the clicked object's own local name, with the dialect area that one lies in", () => {
    const entry = listed({ local: 'Nöördweerew', dialect: 'frr-x-hallig' });
    const props = {
      'frasch:local': 'Noordweerw',
      'frasch:dialect': 'frr-x-nordgoes',
      'name:frr-x-nordgoes': 'Noordweerw',
    };

    expect(cardModel(clicked(props, entry), LOCAL_TAG)).toMatchObject({
      headline: 'Noordweerw',
      source: { kind: 'local', dialect: 'frr-x-nordgoes' },
    });
  });

  it('has no local name where the clicked object has none, whatever its row has', () => {
    // Issue #89: the second object of the row lies outside every dialect area.
    const entry = listed({
      names: { 'frr-x-wieding': 'e Wäsk' },
      local: 'e Wäsk',
      dialect: 'frr-x-wieding',
      name_de: 'Wisch',
    });
    const props = { 'name:frr-x-wieding': 'e Wäsk', 'name:de': 'Wisch', name: 'Wisch' };

    expect(cardModel(clicked(props, entry), LOCAL_TAG)).toMatchObject({
      headline: 'Wisch',
      lines: [{ source: inDialect('frr-x-wieding'), name: 'e Wäsk' }],
    });
  });

  // The remark is the row's, on its `local` cell: the same on every object.
  it("has the entry's variety remark rather than the tile feature's", () => {
    const entry = listed({ variety: 'Listed' });
    const props = { 'frasch:local': 'Brouersweerw', 'frasch:variety': 'Tile' };

    expect(cardModel(clicked(props, entry), LOCAL_TAG).note).toBe('Listed');
  });

  it("has the tile feature's variety remark where the entry has none", () => {
    const props = { 'frasch:local': 'Brouersweerw', 'frasch:variety': 'Tile' };

    expect(cardModel(clicked(props, listed()), LOCAL_TAG).note).toBe('Tile');
  });

  // The tile's own value is what the clicked label shows; the entry's comes
  // from the OSM extract the list was matched against, which may be older.
  const TILE_FIRST_NAMES = [
    { name: 'Low Saxon', tileKey: 'name:nds', entryFields: { names: { nds: 'Listed' } } },
    { name: 'generic', tileKey: 'name', entryFields: { name_osm: 'Listed' } },
  ] as const;

  it.each(TILE_FIRST_NAMES)(
    "has the tile feature's $name name rather than the entry's",
    ({ tileKey, entryFields }) => {
      const entry = listed(entryFields);

      expect(cardModel(clicked({ [tileKey]: 'Tile' }, entry), LOCAL_TAG).headline).toBe('Tile');
    },
  );

  it.each(TILE_FIRST_NAMES)(
    "has the entry's $name name where the tile feature has none",
    ({ entryFields }) => {
      const entry = listed(entryFields);

      expect(cardModel(clicked({}, entry), LOCAL_TAG).headline).toBe('Listed');
    },
  );
});
