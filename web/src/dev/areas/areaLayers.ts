/**
 * Map layers and the dialect colour table for the review view (`?areas`).
 *
 * Kept out of AreaPanel.tsx because it is pure data with no React in it: the
 * palette is a reviewable artefact in its own right, and the layer specs can
 * be checked against the MapLibre style spec without a browser.
 */
import type { FilterSpecification, LayerSpecification } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

import { UNASSIGNED } from './areas';

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
 *
 * A dialect added to the registry needs a colour here: areaLayers.test.ts
 * holds the table to the registry's tags.
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

/** The colour of a group of the list and the legend: a dialect tag, or UNASSIGNED. */
export function groupColor(key: string): string {
  return key === UNASSIGNED ? COLOR_UNASSIGNED : (DIALECT_COLORS[key] ?? COLOR_UNKNOWN);
}

/* ---------------------------------------------------------------- layers */

export const SOURCE = 'areas-parts';
/** The fill is what a click on a municipality hits. */
export const FILL = 'areas-fill';
const LINE = 'areas-line';
const SELECTED_CASING = 'areas-selected-casing';
const SELECTED = 'areas-selected';

/** First symbol layer of frasch-bright.json: everything we add goes below it,
 *  so no place label is ever covered by the overlay. */
export const BEFORE_ID = 'waterway-name';

/**
 * Each dialect tag's colour, COLOR_UNKNOWN for any other. The first pair is
 * taken apart because the type of a `match` asks for at least one.
 */
function dialectColor(): ExpressionSpecification {
  const [[firstTag, firstColor], ...others] = Object.entries(DIALECT_COLORS);
  return ['match', ['get', 'dialect'], firstTag, firstColor, ...others.flat(), COLOR_UNKNOWN];
}

const colorExpr: ExpressionSpecification = [
  'case',
  ['!', ['get', 'assigned']],
  COLOR_UNASSIGNED,
  dialectColor(),
];

export interface AreaLayerState {
  /** The `osm` cell of the selected municipality; null when none is. */
  selectedOsm: string | null;
  /** The group drawn alone: a dialect tag or UNASSIGNED; null draws them all. */
  shown: string | null;
}

/** The overlay's layers, bottom first, filtered to what `state` says. */
export function areaLayers({ selectedOsm, shown }: AreaLayerState): LayerSpecification[] {
  const shownFilter = groupFilter(shown);
  // The `osm` cell, not a single reference: a reference is on one row only,
  // so the whole cell names the municipality as well, and MapLibre can
  // compare it without splitting it.
  const selectedFilter = ['==', ['get', 'osm'], selectedOsm ?? ''] as FilterSpecification;
  return [
    {
      id: FILL,
      type: 'fill',
      source: SOURCE,
      ...shownFilter,
      paint: {
        'fill-color': colorExpr,
        // Lighter as you zoom in: up close the boundary is the subject, not
        // the block, and the place labels have to stay readable through it.
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.38, 12, 0.3, 15, 0.2],
      },
    },
    {
      id: LINE,
      type: 'line',
      source: SOURCE,
      ...shownFilter,
      paint: {
        // Same hue as the fill at ~3x the alpha. This is what keeps two
        // adjacent municipalities OF THE SAME DIALECT apart -- which is the
        // whole job, since what is being reviewed is a per-municipality
        // assignment. `fill-antialias` cannot do it: it draws the fill's own
        // edge in the fill colour.
        'line-color': colorExpr,
        'line-opacity': 0.95,
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.6, 11, 1.2, 14, 2],
      },
    },
    {
      id: SELECTED_CASING,
      type: 'line',
      source: SOURCE,
      filter: selectedFilter,
      paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.9 },
    },
    {
      id: SELECTED,
      type: 'line',
      source: SOURCE,
      filter: selectedFilter,
      paint: { 'line-color': '#111111', 'line-width': 2.5 },
    },
  ];
}

/** The legend doubles as the map filter: drawing one dialect alone is the
 *  reliable way to tell two look-alike colours apart (see DIALECT_COLORS). */
function groupFilter(shown: string | null): { filter?: FilterSpecification } {
  if (shown === null) return {};
  if (shown === UNASSIGNED) return { filter: ['!', ['get', 'assigned']] };
  return { filter: ['==', ['get', 'dialect'], shown] };
}
