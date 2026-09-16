import type { StyleSpecification, LayerSpecification } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

// `../style/frasch-bright.json` started as a fork of upstream OSM Bright
// (openmaptiles/osm-bright-gl-style, openmaptiles:version "3.x", fetched
// 2026-09-15 - see web/README.md for details) and is now edited directly as
// our own style (place-label layers restructured for Frisian place kinds,
// see the "Label classes" section of the README). This module keeps doing
// only what must stay dynamic at runtime: pointing the vector source at the
// configured tiles URL, building the dialect-aware name expression, and
// resolving glyph/sprite URLs against the page origin.

/**
 * Builds a name-based text-field expression that prefers the given dialect,
 * then falls back through other Frisian names, Low German, German, a
 * transliterated Latin name, then the generic OSM `name` field.
 *
 * `dialect` is a BCP 47 tag such as "frr-x-mooring"; the corresponding tile
 * property is literally "name:frr-x-mooring".
 *
 * This is Germany-only for now (which is all Phase 1 covers). Planned, not
 * yet implemented: outside Germany, drop `name:de` and prefer `name:en`
 * instead. The approach when that's built: two symbol layers per label
 * layer sharing the same base filter, one filtered with `within` a Germany
 * polygon using this chain, the other filtered to its complement using an
 * English-preferring chain (`coalesce(name:<dialect>, name:frr, name:en,
 * name:latin, name)`). Not implemented today because there's no Germany
 * polygon wired into the style yet.
 */
function dialectNameExpression(dialect: string): ExpressionSpecification {
  return [
    'coalesce',
    ['get', `name:${dialect}`],
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
 * Rewrites `baseStyle` into a dialect-aware, self-hosted style:
 *  - points the `openmaptiles` source at `tilesUrl`
 *  - rewrites every symbol layer's name-based `text-field` to prefer the
 *    given dialect, falling back to other Frisian, then German, then the
 *    plain `name` field
 *  - points `glyphs`/`sprite` at locally hosted, absolute-path URLs
 */
export function buildStyle(
  baseStyle: StyleSpecification,
  tilesUrl: string,
  dialect: string,
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

  // (b) Rewrite name-based text-fields to be dialect-aware.
  const nameExpression = dialectNameExpression(dialect);
  style.layers = style.layers.map((layer: LayerSpecification): LayerSpecification => {
    if (layer.type !== 'symbol' || !layer.layout) return layer;
    const textField = (layer.layout as Record<string, unknown>)['text-field'];
    if (textField === undefined || !referencesName(textField)) return layer;
    return {
      ...layer,
      layout: {
        ...layer.layout,
        'text-field': nameExpression,
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
