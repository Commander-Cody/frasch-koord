import type { StyleSpecification } from 'maplibre-gl';

import { siteUrl } from '../../site';
import { labelLayers } from './labels';

// `frasch-bright.json` started as a fork of upstream OSM Bright
// (openmaptiles/osm-bright-gl-style, openmaptiles:version "3.x", fetched
// 2026-09-15 - see web/README.md for details) and is now edited directly as
// our own style (place-label layers restructured for Frisian place kinds,
// see the "Label classes" section of the README). This module keeps doing
// only what must stay dynamic at runtime: pointing the vector source at the
// configured tiles URL, applying the label expression (labels.ts) of the
// selected view, and resolving glyph/sprite URLs
// against the page and the site's base path.

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
 * Rewrites `baseStyle` into a label-aware, self-hosted style:
 *  - points the `openmaptiles` source at `tilesUrl`
 *  - rewrites every symbol layer's name-based `text-field` to the chain of
 *    `nameExpression(view)` (labels.ts)
 *  - points `glyphs`/`sprite` at the copies this site hosts itself
 *
 * `view` is a dialect tag or LOCAL_TAG.
 */
export function buildStyle(
  baseStyle: StyleSpecification,
  tilesUrl: string,
  view: string,
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

  // (b) Rewrite name-based text-fields to follow the view's label chain.
  style.layers = labelLayers(style.layers, view);

  // (c) Serve glyphs and sprites locally rather than from a third party.
  // MapLibre requires absolute sprite URLs; siteUrl resolves them against
  // the page and the site's base path.
  style.glyphs = siteUrl('fonts/{fontstack}/{range}.pbf');
  style.sprite = siteUrl('sprites/sprite');

  return style;
}
