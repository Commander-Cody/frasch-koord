import type { StyleSpecification } from 'maplibre-gl';

import { siteUrl, TILES_URL } from '../../site';
import fraschBright from './frasch-bright.json';
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
 * frasch-bright.json, typed: a JSON import widens every literal to `string`,
 * so it is cast, once, here.
 */
export const BASE_STYLE = fraschBright as unknown as StyleSpecification;

/**
 * The layers a click on the map can hit a place label in: read off the base
 * style once, since every view has the same label layers and only their
 * text-field differs.
 */
export const PLACE_LAYERS = placeLayerIds(BASE_STYLE);

/**
 * The site's style in `view` (a dialect tag or LOCAL_TAG): BASE_STYLE with
 *  - its `openmaptiles` source pointed at TILES_URL
 *  - the `text-field` of every layer marked `frasch:label` rewritten to the
 *    view's label chain (labels.ts)
 *  - `glyphs`/`sprite` pointed at the copies this site hosts itself
 */
export function styleFor(view: string): StyleSpecification {
  const style: StyleSpecification = structuredClone(BASE_STYLE);

  // (a) Vector tile source: MapLibre reads TileJSON out of the PMTiles
  // archive itself via the registered `pmtiles://` protocol, so a plain
  // `{ type: 'vector', url }` source is all that's needed here.
  style.sources = {
    ...style.sources,
    openmaptiles: {
      type: 'vector',
      url: TILES_URL,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a> · © <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a>',
    },
  };

  // (b) Label the marked layers by the view's label chain.
  style.layers = labelLayers(style.layers, view);

  // (c) Serve glyphs and sprites locally rather than from a third party.
  // MapLibre requires absolute sprite URLs; siteUrl resolves them against
  // the page and the site's base path.
  style.glyphs = siteUrl('fonts/{fontstack}/{range}.pbf');
  style.sprite = siteUrl('sprites/sprite');

  return style;
}
