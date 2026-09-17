import type { StyleSpecification, LayerSpecification } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

import { LOCAL_TAG } from '../config';

// `../style/frasch-bright.json` started as a fork of upstream OSM Bright
// (openmaptiles/osm-bright-gl-style, openmaptiles:version "3.x", fetched
// 2026-09-15 - see web/README.md for details) and is now edited directly as
// our own style (place-label layers restructured for Frisian place kinds,
// see the "Label classes" section of the README). This module keeps doing
// only what must stay dynamic at runtime: pointing the vector source at the
// configured tiles URL, building the label expression for the selected
// dialect (or the local-dialect view), and resolving glyph/sprite URLs
// against the page origin.

/**
 * Builds the `text-field` expression for a label option.
 *
 * `tag` is either a dialect tag such as "frr-x-mooring" (the corresponding
 * tile property is literally "name:frr-x-mooring") or LOCAL_TAG, the "local
 * dialect" view.
 *
 *  - dialect view: the dialect's own name first, then the local Frisian name
 *    of the place (`frasch:local`, e.g. a Fering name on Föhr while the map
 *    is in Mooring) so a Frisian name is preferred over a German one even
 *    where this dialect has none, then generic Frisian, Low Saxon, German,
 *    a transliterated Latin name, and finally the generic OSM `name`.
 *  - local view: ONLY the name the people of the place use themselves, then
 *    the local majority language. Deliberately no `name:frr` (that is some
 *    other dialect's name, which is exactly what this view avoids) and no
 *    `name:de` — German comes in via `name:latin`/`name` anyway, but only
 *    after Low Saxon has had its turn.
 *
 * Phase 1 covers Schleswig-Holstein only, so `name:nds` (Low Saxon) is always
 * the local majority language outside the Frisian areas. That assumption
 * breaks as soon as the tiles leave northern Germany. Planned for the planet
 * build, not yet implemented: two symbol layers per label layer sharing the
 * same base filter, one filtered `within` a northern-Germany polygon using
 * this chain, the other filtered to its complement using a chain without
 * `name:nds` (and, outside Germany, preferring `name:en` over `name:de`).
 * Not implemented today because there is no such polygon in the style yet.
 */
export function nameExpression(tag: string): ExpressionSpecification {
  if (tag === LOCAL_TAG) {
    return [
      'coalesce',
      ['get', 'frasch:local'],
      ['get', 'name:nds'],
      ['get', 'name:latin'],
      ['get', 'name'],
    ] as unknown as ExpressionSpecification;
  }
  return [
    'coalesce',
    ['get', `name:${tag}`],
    ['get', 'frasch:local'],
    ['get', 'name:frr'],
    ['get', 'name:nds'],
    ['get', 'name:de'],
    ['get', 'name:latin'],
    ['get', 'name'],
  ] as unknown as ExpressionSpecification;
}

/**
 * Does this symbol layer's text-field render the feature's `name`
 * (possibly combined with `name:latin`/`name:nonlatin` in various
 * OpenMapTiles/OSM Bright templating styles)? Layers that label something
 * else entirely (e.g. `{ref}` road shields) are left untouched.
 */
function referencesName(textField: unknown): boolean {
  if (typeof textField === 'string') {
    return textField.includes('name');
  }
  if (Array.isArray(textField)) {
    // Recurse into expressions such as ["concat", ["get", "name:latin"], ...]
    return textField.some((part) => referencesName(part));
  }
  return false;
}

/**
 * Rewrites `baseStyle` into a label-aware, self-hosted style:
 *  - points the `openmaptiles` source at `tilesUrl`
 *  - rewrites every symbol layer's name-based `text-field` to the chain of
 *    `nameExpression(labels)` above
 *  - points `glyphs`/`sprite` at locally hosted, absolute-path URLs
 *
 * `labels` is a dialect tag or LOCAL_TAG (see `nameExpression`).
 */
export function buildStyle(
  baseStyle: StyleSpecification,
  tilesUrl: string,
  labels: string,
): StyleSpecification {
  const style: StyleSpecification = structuredClone(baseStyle);

  // (a) Vector tile source: MapLibre reads TileJSON out of the PMTiles
  // archive itself via the registered `pmtiles://` protocol, so a plain
  // `{ type: 'vector', url: tilesUrl }` source is all that's needed here.
  style.sources = {
    ...style.sources,
    openmaptiles: {
      type: 'vector',
      url: tilesUrl,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> · © <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a>',
    },
  };

  // (b) Rewrite name-based text-fields to follow the selected label chain.
  const textFieldExpression = nameExpression(labels);
  style.layers = style.layers.map((layer: LayerSpecification): LayerSpecification => {
    if (layer.type !== 'symbol' || !layer.layout) return layer;
    const textField = (layer.layout as Record<string, unknown>)['text-field'];
    if (textField === undefined || !referencesName(textField)) return layer;
    return {
      ...layer,
      layout: {
        ...layer.layout,
        'text-field': textFieldExpression,
      },
    };
  });

  // (c) Serve glyphs and sprites locally rather than from a third party.
  // MapLibre requires absolute sprite URLs; resolve against the page origin
  // (falls back to the bare path when run outside a browser, e.g. in tests).
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  style.glyphs = `${origin}/fonts/{fontstack}/{range}.pbf`;
  style.sprite = `${origin}/sprites/sprite`;

  return style;
}
