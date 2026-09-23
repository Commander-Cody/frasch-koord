import type { StyleSpecification, LayerSpecification } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

import { labelChain } from '../labelChain';

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
 * Builds the `text-field` expression for a label option: a `coalesce` over
 * the tile properties of `labelChain(tag)`, the chain the place card and the
 * search results follow too (see labelChain.ts).
 */
export function nameExpression(tag: string): ExpressionSpecification {
  return [
    'coalesce',
    ...labelChain(tag).map((key) => ['get', key]),
  ] as unknown as ExpressionSpecification;
}

/**
 * The ids of the layers that label places — what a click on the map has to
 * hit to open a place card. Read off the style rather than hardcoded, so the
 * two cannot drift apart when a label class is added (see the "Label classes"
 * section of web/README.md).
 */
export function placeLayerIds(style: StyleSpecification): string[] {
  return style.layers
    .filter((l) => l.type === 'symbol' && 'source-layer' in l && l['source-layer'] === 'place')
    .map((l) => l.id);
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
