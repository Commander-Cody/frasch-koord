import { describe, expect, it } from 'vitest';
import { createPropertyExpression, latest } from '@maplibre/maplibre-gl-style-spec';
import type { LngLat } from 'maplibre-gl';

import { ALL_VIEW_TAGS } from './dialects/views';
import { cardModel } from './names/card';
import type { NameEntry } from './names/entry';
import type { TileProps } from './names/tile';
import { nameExpression } from './map/style/labels';
import listedScenarios from './testing/generated/listedScenarios.json';

// Issue #16: the place card once showed German while the map label showed
// Low Saxon for the same place, because the card's label chain and the map's
// text-field expression had drifted apart. Both are supposed to be built from
// the single chain in dialects/labelChain.ts (map: map/style/labels.ts's nameExpression,
// card: names/card.ts's cardModel), but nothing stops a future edit to
// one side from forgetting the other. This test evaluates the REAL map
// expression (nameExpression, the same export styleFor puts into
// `text-field`) with MapLibre's own style-spec expression engine and checks
// it against the REAL card path, for the same tile properties and view, so a
// drift on either side fails here rather than shipping.

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
interface ClickedLabel {
  props: TileProps;
  entry?: NameEntry;
}

/** What the card would show, using the real card-building path. */
function cardLabel(tag: string, { entry, props }: ClickedLabel): string {
  const pick = { via: 'map', props, at: { lng: 0, lat: 0 } as LngLat } as const;
  return cardModel({ pick, entry }, tag).headline;
}

/**
 * `props` with OpenMapTiles' own `name_de` on top, which every feature of
 * the tiles has: OSM's `name:de`, else the plain `name`. No German name, that
 * is, where the two differ (issue #104).
 */
function asInTheTiles(props: TileProps): TileProps {
  const name_de = props['name:de'] ?? props.name;
  return name_de === undefined ? props : { ...props, name_de };
}

// Realistic tile-property sets a clicked feature could carry, named after
// what makes each interesting. OpenMapTiles always carries the plain `name`
// on a labelled point (it is the primary field; name:xx are translations
// added alongside it). South of the border it is normally the same string as
// name:de, north of it the Danish name. `asInTheTiles` adds `name_de`.
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

// A clicked label of a place in the name list: its names.json entry together
// with the tile properties of its object, as the pipeline writes them --
// tiles/tests/test_consistency.py builds both from one small extract and
// commits them here, and fails when they are no longer what the pipeline
// gives (#109). The card reads the entry first, so these exercise the card's
// merge of the two as well.
const LISTED_SCENARIOS = listedScenarios as Record<string, ClickedLabel & { entry: NameEntry }>;

const CASES = [
  ...Object.entries(SCENARIOS).map(([scenario, props]): [string, ClickedLabel] => [
    scenario,
    { props },
  ]),
  ...Object.entries(LISTED_SCENARIOS),
].map(([scenario, { props, entry }]): [string, ClickedLabel] => [
  scenario,
  { props: asInTheTiles(props), entry },
]);

describe('map label vs. place card (issue #16 regression)', () => {
  for (const [scenario, selection] of CASES) {
    for (const tag of ALL_VIEW_TAGS) {
      it(`${scenario} — ${tag} view`, () => {
        expect(cardLabel(tag, selection)).toBe(mapLabel(tag, selection.props));
      });
    }
  }
});
