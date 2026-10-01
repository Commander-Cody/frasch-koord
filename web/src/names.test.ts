import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import patchSchema from '../../names/curate-patch.schema.json';
import {
  cardEntry,
  entryLookup,
  namesUrl,
  osmRefFromFeatureId,
  osmUrl,
  placeOsmRef,
  primary,
  resolveName,
  useNames,
  WIKIDATA_ID,
  type NameEntry,
} from './names';

/** A minimal, otherwise-empty entry, for tests that only care about a few fields. */
function entry(fields: Partial<NameEntry> = {}): NameEntry {
  return { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '', ...fields };
}

function stubFetch(body: string, init: ResponseInit) {
  const fetch = vi.fn(async () => new Response(body, init));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('useNames', () => {
  // The failure is logged; keep the test output clean.
  const quiet = () => vi.spyOn(console, 'error').mockImplementation(() => {});

  it('loads the list', async () => {
    stubFetch(
      JSON.stringify({
        built_from: { 'places.csv': 'aaa' },
        places: [
          { id: 'naibel', names: {}, name_de: 'Niebüll', lon: 8, lat: 54, kind: 'settlement' },
        ],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
    const { result } = renderHook(() => useNames());
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.entries).toHaveLength(1);
    expect(result.current.find('naibel')?.name_de).toBe('Niebüll');
    expect(result.current.builtFrom).toEqual({ 'places.csv': 'aaa' });
  });

  it('ends in error on a 404', async () => {
    quiet();
    stubFetch('Not Found', { status: 404 });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.entries).toEqual([]);
  });

  it('ends in error on an SPA fallback (200 text/html)', async () => {
    quiet();
    stubFetch('<!doctype html><html><body><div id="root"></div></body></html>', {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('ends in error on JSON without a list of places', async () => {
    quiet();
    stubFetch('{"entries": []}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('error'));
  });
});

describe('namesUrl', () => {
  it('is under the root by default', () => {
    expect(namesUrl()).toBe(`${window.location.origin}/data/names.json`);
  });

  it('respects a non-root base', async () => {
    vi.stubEnv('BASE_URL', '/frasch-koord/');
    expect(namesUrl()).toBe(`${window.location.origin}/frasch-koord/data/names.json`);
    const fetch = stubFetch('{"built_from": {}, "places": []}', { status: 200 });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/frasch-koord/data/names.json`);
  });
});

describe('resolveName', () => {
  it("prefers the dialect's own name over frasch:local", () => {
    const e = entry({ names: { 'frr-x-mooring': 'Naibel' }, local: 'Naibel Local' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Naibel', source: 'frr-x-mooring' });
  });

  it('falls back to frasch:local when the dialect has no name of its own', () => {
    const e = entry({ local: 'Wik' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Wik', source: 'local' });
  });

  it("falls back to another dialect's name, reporting that dialect as the source", () => {
    const e = entry({ names: { 'frr-x-fering': 'Feering Name' } });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({
      name: 'Feering Name',
      source: 'frr-x-fering',
    });
  });

  it('reports name:frr as source "frr"', () => {
    const e = entry({ name_frr: 'Rüms' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Rüms', source: 'frr' });
  });

  it('reports name:nds as source "nds"', () => {
    const e = entry({ name_nds: 'Niböl' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Niböl', source: 'nds' });
  });

  it('reports the German name as source "de"', () => {
    const e = entry({ name_de: 'Niebüll' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Niebüll', source: 'de' });
  });

  it("reports OSM's generic name as Danish where it is the Danish name", () => {
    const e = entry({ name_osm: 'Ribe', name_da: 'Ribe', name_de: 'Ripen' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Ribe', source: 'da' });
  });

  it("reports OSM's generic name as German where it is the German name", () => {
    const e = entry({ name_osm: 'Niebüll', name_de: 'Niebüll' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Niebüll', source: 'de' });
  });

  it('reports OSM\'s generic name as source "osm" where it is no name the entry knows a language of', () => {
    const e = entry({ name_osm: 'Tønder', name_de: 'Tondern' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Tønder', source: 'osm' });
  });

  it('falls back to Danish only as a last resort, after German has had its turn', () => {
    const e = entry({ name_da: 'Ålborg' });
    expect(resolveName(e, 'frr-x-mooring')).toEqual({ name: 'Ålborg', source: 'da' });
  });

  it('resolves to an empty name when the entry has nothing at all', () => {
    expect(resolveName(entry(), 'frr-x-mooring')).toEqual({ name: '', source: 'de' });
  });

  it('the local view never shows name:frr, only frasch:local then Low Saxon then German', () => {
    // name_frr is deliberately ignored by the local view (see labelChain.ts);
    // Low Saxon still wins over OSM's generic name and the German one.
    const e = entry({ name_frr: 'Rüms', name_nds: 'Sölerloch', name_osm: 'Sylt', name_de: 'Sylt' });
    expect(resolveName(e, 'frr-x-local')).toEqual({ name: 'Sölerloch', source: 'nds' });
  });

  it("the local view prefers OSM's generic name over the German one", () => {
    const e = entry({ name_osm: 'Tønder', name_de: 'Tondern' });
    expect(resolveName(e, 'frr-x-local').name).toBe('Tønder');
  });

  it('the local view falls back to German where there is no generic name', () => {
    expect(resolveName(entry({ name_de: 'Tondern' }), 'frr-x-local')).toEqual({
      name: 'Tondern',
      source: 'de',
    });
  });
});

describe('cardEntry', () => {
  it('is exactly the name-list entry when there is no clicked tile', () => {
    const e = entry({ name_de: 'Niebüll' });
    expect(cardEntry({ entry: e })).toBe(e);
  });

  it('is built from the tile alone when the place has no name-list entry', () => {
    const props = { 'name:de': 'Niebüll', 'frasch:ref': 'node/1' };
    const result = cardEntry({ props });
    expect(result.id).toBe('node/1');
    expect(result.name_de).toBe('Niebüll');
  });

  it("does not take a tile's generic name for its German one", () => {
    // North of the border OSM's `name` is Danish; the card must not list it as German.
    const result = cardEntry({ props: { name: 'Ribe' } });
    expect(result.name_osm).toBe('Ribe');
    expect(result.name_de).toBe('');
  });

  it('lets the entry win field by field over the tile', () => {
    const e = entry({
      names: { 'frr-x-mooring': 'EntryMooring' },
      local: 'EntryLocal',
      dialect: 'entry-dialect',
      variety: 'EntryVariety',
      name_de: 'EntryDE',
      name_da: 'EntryDA',
      kind: 'entry-kind',
    });
    const props = {
      'name:frr-x-mooring': 'TileMooring',
      'frasch:local': 'TileLocal',
      'frasch:dialect': 'tile-dialect',
      'frasch:variety': 'TileVariety',
      'name:de': 'TileDE',
      'name:da': 'TileDA',
      'frasch:kind': 'tile-kind',
    };
    const result = cardEntry({ entry: e, props });
    expect(result.names['frr-x-mooring']).toBe('EntryMooring');
    expect(result.local).toBe('EntryLocal');
    expect(result.dialect).toBe('entry-dialect');
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
    const result = cardEntry({ entry: e, props });
    expect(result.local).toBe('TileLocal');
    expect(result.dialect).toBe('tile-dialect');
    expect(result.variety).toBe('TileVariety');
    expect(result.name_de).toBe('TileDE');
    expect(result.name_da).toBe('TileDA');
    expect(result.kind).toBe('tile-kind');
  });

  it('takes name_nds from the tile even when the entry has one, since the tile is what the clicked label showed', () => {
    const e = entry({ name_nds: 'EntryNDS' });
    const props = { 'name:nds': 'TileNDS' };
    expect(cardEntry({ entry: e, props }).name_nds).toBe('TileNDS');
  });

  it('takes name_osm from the tile even when the entry has one, since the tile is what the clicked label showed', () => {
    const e = entry({ name_osm: 'EntryOSM' });
    expect(cardEntry({ entry: e, props: { name: 'TileOSM' } }).name_osm).toBe('TileOSM');
  });

  it("falls back to the entry's name_osm when the tile has none", () => {
    const e = entry({ name_osm: 'EntryOSM' });
    expect(cardEntry({ entry: e, props: { 'name:de': 'TileDE' } }).name_osm).toBe('EntryOSM');
  });

  it('fills name_osm from the tile when the entry has none', () => {
    expect(cardEntry({ entry: entry(), props: { name: 'TileOSM' } }).name_osm).toBe('TileOSM');
  });

  it("falls back to the entry's name_nds when the tile has none", () => {
    const e = entry({ name_nds: 'EntryNDS' });
    const props = { 'name:de': 'TileDE' }; // no name:nds on this tile
    expect(cardEntry({ entry: e, props }).name_nds).toBe('EntryNDS');
  });
});

describe('osmRefFromFeatureId', () => {
  // The three examples verified against the archive in the doc comment.
  it('decodes a node id (Niebüll)', () => {
    expect(osmRefFromFeatureId(2400427661)).toBe('node/240042766');
  });

  it('decodes a relation id (Föhr)', () => {
    expect(osmRefFromFeatureId(33525413)).toBe('relation/3352541');
  });

  it('decodes a way id (Gröde)', () => {
    expect(osmRefFromFeatureId(10871603522)).toBe('way/1087160352');
  });

  it('accepts the id as a numeric string too', () => {
    expect(osmRefFromFeatureId('2400427661')).toBe('node/240042766');
  });

  it('returns null for a type digit outside 1-3', () => {
    expect(osmRefFromFeatureId(100)).toBeNull(); // n % 10 === 0
  });

  it('returns null for zero, negative, non-integer, or missing ids', () => {
    expect(osmRefFromFeatureId(0)).toBeNull();
    expect(osmRefFromFeatureId(-21)).toBeNull();
    expect(osmRefFromFeatureId(1.5)).toBeNull();
    expect(osmRefFromFeatureId(undefined)).toBeNull();
    expect(osmRefFromFeatureId('not-a-number')).toBeNull();
  });
});

describe('osmUrl', () => {
  it('links a node', () => {
    expect(osmUrl('node/240042766')).toBe('https://www.openstreetmap.org/node/240042766');
  });

  it('links a way', () => {
    expect(osmUrl('way/1087160352')).toBe('https://www.openstreetmap.org/way/1087160352');
  });

  it('links a relation', () => {
    expect(osmUrl('relation/3352541')).toBe('https://www.openstreetmap.org/relation/3352541');
  });

  it('links the first of several references', () => {
    expect(osmUrl('way/1347936331; node/1332249790')).toBe(
      'https://www.openstreetmap.org/way/1347936331',
    );
  });

  it('returns null for a synthetic local/ place', () => {
    expect(osmUrl('local/some-slug')).toBeNull();
  });

  it('returns null for a bare Wikidata QID', () => {
    expect(osmUrl('Q123')).toBeNull();
  });

  it('returns null when there is no reference at all', () => {
    expect(osmUrl(undefined)).toBeNull();
  });
});

// The card links a row's QID only if WIKIDATA_ID takes it, and the curation
// panel saves one only if the patch schema does: the two must never disagree.
// The schema also takes the empty string (an empty cell), which wikidataUrl
// turns away before it tests, so the samples are all non-empty.
describe('WIKIDATA_ID', () => {
  const schema = new RegExp(patchSchema.properties.wikidata.pattern);

  it.each(['Q1', 'Q42', 'Q559369', 'q42', 'Q', 'Q4a', ' Q42', 'P31', 'Q-1'])(
    'takes %j exactly when the patch schema does',
    (qid) => {
      expect(WIKIDATA_ID.test(qid)).toBe(schema.test(qid));
    },
  );
});

describe('entryLookup', () => {
  // Two rows on one dyke (two spellings), a row claiming two objects, a country.
  const lungedik = entry({ id: 'lungedik', osm: 'way/28330569', name_de: 'Langerdeich' });
  const lungdiik = entry({ id: 'lungdiik', osm: 'way/28330569', name_de: 'Langerdeich' });
  const nordwarw = entry({ id: 'nordwarw', osm: 'way/1347936331; node/1332249790' });
  const danemark = entry({ id: 'danemark', wikidata: 'Q35' });
  const find = entryLookup([lungedik, lungdiik, nordwarw, danemark]);

  it('finds an entry by its row id', () => {
    expect(find('lungdiik')).toBe(lungdiik);
  });

  it('still opens an old ?place=node/… link: the first row on that object', () => {
    expect(find('way/28330569')).toBe(lungedik);
    expect(find('node/1332249790')).toBe(nordwarw);
  });

  it('still opens an old ?place=<ref>#<line> link, at the first row on that object', () => {
    expect(find('way/28330569#679')).toBe(lungedik);
  });

  it('still opens an old ?place=<QID> link of a country', () => {
    expect(find('Q35')).toBe(danemark);
  });

  it('finds nothing for an unknown reference', () => {
    expect(find('node/1')).toBeUndefined();
    expect(find('nobody')).toBeUndefined();
  });
});

describe('placeOsmRef', () => {
  it("is the name-list entry's OSM reference", () => {
    expect(
      placeOsmRef({ entry: entry({ id: 'naibel', osm: 'node/240042766' }), featureId: 33525413 }),
    ).toBe('node/240042766');
  });

  it("is the clicked feature's object when the name list does not have the place", () => {
    expect(placeOsmRef({ props: { name: 'Bredstedt' }, featureId: 2400427661 })).toBe(
      'node/240042766',
    );
  });
});

// frasch/placelist.py reads a cell the same way (most examples are its
// docstrings'): the two must agree on which variant of a cell is its name.
describe('primary', () => {
  it('is the first variant of a cell', () => {
    expect(primary('Rübel; Rübbel (wisinge)')).toBe('Rübel');
  });

  it('splits only outside brackets, and strips the remark', () => {
    expect(primary('Huađer; Huuger (Sölring; Wisinge)')).toBe('Huađer');
  });

  it('strips every remark of the variant', () => {
    expect(primary('Brouersweerw (Foortuftinge) (Nickelsen 1982)')).toBe('Brouersweerw');
  });

  it('skips a variant that is only a remark', () => {
    expect(primary('(remark only); Name')).toBe('Name');
  });

  it("drops a doubtful name's trailing question mark", () => {
    expect(primary('Hoorst? (Moor)')).toBe('Hoorst');
  });

  it('is empty for an empty cell', () => {
    expect(primary('')).toBe('');
  });
});
