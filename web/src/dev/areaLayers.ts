/**
 * Map layers and the dialect colour table for the review view (`?areas`).
 *
 * Kept out of AreaPanel.tsx because it is pure data with no React in it: the
 * palette is a reviewable artefact in its own right, and the layer specs can
 * be checked against the MapLibre style spec without a browser.
 */
import type { LayerSpecification } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

/* ---------------------------------------------------------------- colour */

/**
 * One colour per dialect, for this review view only — nothing public reads it.
 *
 * Not picked by eye. The eleven hues come from the data-viz reference palette,
 * and the *assignment* was solved against the dialect adjacency computed from
 * the geometry itself (which areas actually share a boundary — including
 * Sölring/Wiedingharder, which meet out in the Wattenmeer). Every touching
 * pair, and every pair within ~6 km, clears the colour-vision gates with ~1.5x
 * margin: worst CVD dE 12.5, worst normal-vision dE 23.5 (targets 8 / 15).
 *
 * Eleven categories cannot ALL be pairwise colourblind-safe — no assignment of
 * any eleven hues can — so pairs that never touch may look alike under protan
 * (Karrharder/Südergoesharder is the closest). That is why colour is never the
 * only channel here: the legend pairs every swatch with its name, the list is
 * grouped by dialect, the detail block always spells the dialect out, and
 * clicking a legend row draws that dialect alone.
 */
export const DIALECT_COLORS: Record<string, string> = {
  'frr-x-mooring': '#1baf7a',
  'frr-x-wieding': '#4a3aa7',
  'frr-x-karrhard': '#96591b',
  'frr-x-nordgoes': '#2a78d6',
  'frr-x-midgoes': '#e87ba4',
  'frr-x-suedgoes': '#008300',
  'frr-x-fering': '#eda100',
  'frr-x-oomrang': '#0091a7',
  'frr-x-solring': '#eb6834',
  'frr-x-hallig': '#c2185b',
  'frr-x-halunder': '#e34948',
};

/** A municipality no row claims. Deliberately outside the palette: this is a
 *  missing-data state, not a twelfth dialect. */
export const COLOR_UNASSIGNED = '#9aa0a6';
/** A dialect tag the table does not know — never silently invisible. */
export const COLOR_UNKNOWN = '#111111';

/* ---------------------------------------------------------------- layers */

export const SOURCE = 'areas-parts';
export const FILL = 'areas-fill';
export const LINE = 'areas-line';
export const SELECTED_CASING = 'areas-selected-casing';
export const SELECTED = 'areas-selected';
export const LAYERS = [SELECTED, SELECTED_CASING, LINE, FILL];

/** First symbol layer of frasch-bright.json: everything we add goes below it,
 *  so no place label is ever covered by the overlay. */
export const BEFORE_ID = 'waterway-name';

/** Padding that keeps a fitted area clear of the panel. */
export const FIT_PADDING = { left: 460, top: 60, right: 60, bottom: 60 };

export const colorExpr: ExpressionSpecification = [
  'case',
  ['!', ['get', 'assigned']],
  COLOR_UNASSIGNED,
  [
    'match',
    ['get', 'dialect'],
    ...Object.entries(DIALECT_COLORS).flatMap(([tag, color]) => [tag, color]),
    COLOR_UNKNOWN,
  ],
] as unknown as ExpressionSpecification;

/** `['==', ['get','fid'], fid]`, or a filter that matches nothing. */
export function fidFilter(fid: number | null): ExpressionSpecification {
  return ['==', ['get', 'fid'], fid ?? -1] as unknown as ExpressionSpecification;
}

export function layerSpecs(): LayerSpecification[] {
  return [
    {
      id: FILL,
      type: 'fill',
      source: SOURCE,
      paint: {
        'fill-color': colorExpr,
        // Lighter as you zoom in: up close the boundary is the subject, not
        // the block, and the place labels have to stay readable through it.
        'fill-opacity': [
          'interpolate',
          ['linear'],
          ['zoom'],
          8,
          0.38,
          12,
          0.3,
          15,
          0.2,
        ] as unknown as ExpressionSpecification,
      },
    },
    {
      id: LINE,
      type: 'line',
      source: SOURCE,
      paint: {
        // Same hue as the fill at ~3x the alpha. This is what keeps two
        // adjacent municipalities OF THE SAME DIALECT apart -- which is the
        // whole job, since what is being reviewed is a per-municipality
        // assignment. `fill-antialias` cannot do it: it draws the fill's own
        // edge in the fill colour.
        'line-color': colorExpr,
        'line-opacity': 0.95,
        'line-width': [
          'interpolate',
          ['linear'],
          ['zoom'],
          8,
          0.6,
          11,
          1.2,
          14,
          2,
        ] as unknown as ExpressionSpecification,
      },
    },
    {
      id: SELECTED_CASING,
      type: 'line',
      source: SOURCE,
      filter: fidFilter(null),
      paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.9 },
    },
    {
      id: SELECTED,
      type: 'line',
      source: SOURCE,
      filter: fidFilter(null),
      paint: { 'line-color': '#111111', 'line-width': 2.5 },
    },
  ] as LayerSpecification[];
}
