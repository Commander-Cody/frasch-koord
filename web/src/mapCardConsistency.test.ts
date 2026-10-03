import { describe, expect, it } from 'vitest';
import { createPropertyExpression, latest } from '@maplibre/maplibre-gl-style-spec';

import { DIALECTS, LOCAL_TAG } from './config';
import {
  cardEntry,
  resolveName,
  type NameEntry,
  type PlaceSelection,
  type TileProps,
} from './names';
import { nameExpression } from './style/localize';

// Issue #16: the place card once showed German while the map label showed
// Low Saxon for the same place, because the card's label chain and the map's
// text-field expression had drifted apart. Both are supposed to be built from
// the single chain in labelChain.ts (map: style/localize.ts's nameExpression,
// card: names.ts's resolveName/cardEntry), but nothing stops a future edit to
// one side from forgetting the other. This test evaluates the REAL map
// expression (nameExpression, the same export buildStyle puts into
// `text-field`) with MapLibre's own style-spec expression engine and checks
// it against the REAL card path, for the same tile properties and view, so a
// drift on either side fails here rather than shipping.

const VIEWS = [...DIALECTS.map((d) => d.tag), LOCAL_TAG];

/** What the map would render as the label, using the real style expression. */
function mapLabel(tag: string, props: TileProps): string {
  const result = createPropertyExpression(
    nameExpression(tag),
    'text-field',
    // The style-spec JSON's own type is looser than the (unexported)
    // StylePropertySpecification createPropertyExpression wants; go via its
    // own parameter type rather than reaching for `any`.
    latest.layout_symbol['text-field'] as unknown as Parameters<typeof createPropertyExpression>[2],
  );
  if (result.result === 'error') {
    throw new Error(`invalid text-field expression for ${tag}: ${JSON.stringify(result.value)}`);
  }
  const value = result.value.evaluate({ zoom: 10 }, { properties: props, type: 'Point' });
  return value.toString();
}

/** A click on a map label: the tile properties, and the entry when the place is listed. */
type ClickedLabel = PlaceSelection & { props: TileProps };

/** What the card would show, using the real card-building path. */
function cardLabel(tag: string, selection: PlaceSelection): string {
  return resolveName(cardEntry(selection), tag).name;
}

// Realistic tile-property sets a clicked feature could carry, named after
// what makes each interesting. OpenMapTiles always carries the plain `name`
// on a labelled point (it is the primary field; name:xx are translations
// added alongside it). South of the border it is normally the same string as
// name:de, north of it the Danish name.
const SCENARIOS: Record<string, TileProps> = {
  'only a German name': { 'name:de': 'Niebüll', name: 'Niebüll' },
  'Low Saxon and German': { 'name:nds': 'Niböl', 'name:de': 'Niebüll', name: 'Niebüll' },
  'a mooring name': { 'name:frr-x-mooring': 'Naibel', 'name:de': 'Niebüll', name: 'Niebüll' },
  'frasch:local on Föhr with a fering name': {
    'frasch:local': 'Wik',
    'frasch:dialect': 'frr-x-fering',
    'name:frr-x-fering': 'Wik',
    'name:de': 'Wyk auf Föhr',
    name: 'Wyk auf Föhr',
  },
  'name:frr only, no dialect-specific or German name': { 'name:frr': 'Rüms' },
  'only the generic OSM name': { name: 'Sylt' },
  // Issue #32: not what OpenMapTiles writes today, but a names.json entry
  // whose object has no `name` looks like this to the card.
  'a German name and no generic OSM name': { 'name:de': 'Niebüll' },
  // Issue #32: north of the border OSM's own name is the Danish one, and the
  // local view labels with it rather than with German.
  'a Danish place with a German exonym': { 'name:de': 'Ripen', 'name:da': 'Ribe', name: 'Ribe' },
  // Issue #81: a place the name list does not have, inside a dialect area.
  // The injector writes OSM's `name:frr` as its `frasch:local`.
  'OSM’s Frisian name as the local one, inside a dialect area': {
    'frasch:local': 'Schörkeweerw',
    'name:frr': 'Schörkeweerw',
    name: 'Kirchwarft',
  },
};

/** A names.json entry with the fields no scenario here is about filled in. */
function listed(
  entry: Pick<NameEntry, 'id' | 'names' | 'name_de'> & Partial<NameEntry>,
): NameEntry {
  return { lon: 0, lat: 0, kind: 'settlement', ...entry };
}

// A clicked label of a place in the name list: its names.json entry together
// with the tile properties of its object, as tiles/inject_names.py writes
// them. The card then reads the entry first, so these exercise cardEntry's
// merge as well. Since issue #61 the injector writes the list's `de` as
// `name:de`, the step where the card's German name comes from the list.
const LISTED_SCENARIOS: Record<string, ClickedLabel & { entry: NameEntry }> = {
  'a listed Danish place whose German name only the list has': {
    entry: listed({
      id: 'tingle',
      names: { 'frr-x-wieding': 'Tingle' },
      name_de: 'Tingleff',
      name_osm: 'Tinglev',
      name_da: 'Tinglev',
    }),
    props: {
      'frasch:ref': 'tingle',
      'name:frr-x-wieding': 'Tingle',
      'name:de': 'Tingleff',
      'name:da': 'Tinglev',
      name: 'Tinglev',
    },
  },
  // the local view falls through to `name:de`, its last step
  'a listed place whose object has no generic OSM name': {
    entry: listed({ id: 'listlai', names: { 'frr-x-solring': 'Listlai' }, name_de: 'Lister Ley' }),
    props: { 'frasch:ref': 'listlai', 'name:frr-x-solring': 'Listlai', 'name:de': 'Lister Ley' },
  },
  // the list has no German name, so the tile keeps OSM's
  'a listed place with only OSM’s German name and no generic OSM name': {
    entry: listed({
      id: 'satj',
      names: { 'frr-x-mooring': 'Sätj', 'frr-x-wieding': 'Säit' },
      name_de: '',
    }),
    props: {
      'frasch:ref': 'satj',
      'name:frr-x-mooring': 'Sätj',
      'name:frr-x-wieding': 'Säit',
      'name:de': 'Seth',
    },
  },
  // Issue #81: the row has no name in the dialect of its area, so both sides
  // take OSM's `name:frr` as the local name, ahead of another dialect's.
  'a listed place whose local name is OSM’s Frisian one': {
    entry: listed({
      id: 'hamborjer-hali',
      names: { 'frr-x-mooring': 'Hamborjer Håli' },
      name_de: 'Hamburger Hallig',
      name_osm: 'Hamburger Hallig',
      local: 'Hamborjer Hali',
      dialect: 'frr-x-nordgoes',
      kind: 'hallig',
    }),
    props: {
      'frasch:ref': 'hamborjer-hali',
      'frasch:local': 'Hamborjer Hali',
      'frasch:dialect': 'frr-x-nordgoes',
      'name:frr-x-mooring': 'Hamborjer Håli',
      'name:frr': 'Hamborjer Hali',
      'name:de': 'Hamburger Hallig',
      name: 'Hamburger Hallig',
    },
  },
  // A row with two objects: the entry stands for the first (the way on the
  // Hallig, whose local name is OSM's), the clicked one lies in another area.
  'the second object of a listed row, in another dialect area': {
    entry: listed({
      id: 'nordwarw',
      names: { 'frr-x-mooring': 'Nordwärw', 'frr-x-nordgoes': 'Noordweerw' },
      name_de: 'Nordwarft',
      name_osm: 'Nordwarft',
      local: 'Nöördweerew',
      dialect: 'frr-x-hallig',
      kind: 'warft',
    }),
    props: {
      'frasch:ref': 'nordwarw',
      'frasch:local': 'Noordweerw',
      'frasch:dialect': 'frr-x-nordgoes',
      'name:frr-x-mooring': 'Nordwärw',
      'name:frr-x-nordgoes': 'Noordweerw',
      'name:de': 'Nordwarft',
      name: 'Nordwarft',
    },
  },
};

const CASES: [string, ClickedLabel][] = [
  ...Object.entries(SCENARIOS).map(([scenario, props]): [string, ClickedLabel] => [
    scenario,
    { props },
  ]),
  ...Object.entries(LISTED_SCENARIOS),
];

describe('map label vs. place card (issue #16 regression)', () => {
  for (const [scenario, selection] of CASES) {
    for (const tag of VIEWS) {
      it(`${scenario} — ${tag} view`, () => {
        expect(cardLabel(tag, selection)).toBe(mapLabel(tag, selection.props));
      });
    }
  }
});
