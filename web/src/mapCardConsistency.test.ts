import { describe, expect, it } from 'vitest';
import { createPropertyExpression, latest } from '@maplibre/maplibre-gl-style-spec';

import { DIALECTS, LOCAL_TAG } from './config';
import { cardEntry, resolveName, type TileProps } from './names';
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

/** What the card would show, using the real card-building path. */
function cardLabel(tag: string, props: TileProps): string {
  return resolveName(cardEntry({ props }), tag).name;
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
};

describe('map label vs. place card (issue #16 regression)', () => {
  for (const [scenario, props] of Object.entries(SCENARIOS)) {
    for (const tag of VIEWS) {
      it(`${scenario} — ${tag} view`, () => {
        expect(cardLabel(tag, props)).toBe(mapLabel(tag, props));
      });
    }
  }
});
