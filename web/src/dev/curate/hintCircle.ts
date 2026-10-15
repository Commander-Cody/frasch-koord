// The radius of a row's location hint on the map: "the hint said within N km".

import { useMemo } from 'react';
import type { LayerSpecification, Map as MapLibreMap } from 'maplibre-gl';

import { useGeoJsonOverlay, type OverlayData } from '../shell/useGeoJsonOverlay';
import type { CurateRow } from './worklist';

export type HintPoint = NonNullable<CurateRow['hint_point']>;

export const COLOR_HINT = '#00897b';

const SOURCE = 'curate-hint-circle';

const LAYERS: LayerSpecification[] = [
  {
    id: 'curate-hint-circle-fill',
    type: 'fill',
    source: SOURCE,
    paint: { 'fill-color': COLOR_HINT, 'fill-opacity': 0.1 },
  },
  {
    id: 'curate-hint-circle-line',
    type: 'line',
    source: SOURCE,
    paint: { 'line-color': COLOR_HINT, 'line-opacity': 0.5, 'line-width': 1 },
  },
];

const NO_CIRCLE: OverlayData = { type: 'FeatureCollection', features: [] };

/** Draws the radius of `hint`, or nothing for a row without one. */
export function useHintCircle(map: MapLibreMap, hint: HintPoint | null): void {
  const data = useMemo(() => (hint ? circle(hint) : NO_CIRCLE), [hint]);
  useGeoJsonOverlay(map, { source: SOURCE, data, layers: LAYERS });
}

function circle([lon, lat, radiusKm]: HintPoint): OverlayData {
  return {
    type: 'Feature',
    properties: {},
    geometry: { type: 'Polygon', coordinates: [circleRing(lon, lat, radiusKm)] },
  };
}

/** Rough circle in degrees; good enough to show "the hint said within N km". */
function circleRing(lon: number, lat: number, radiusKm: number): [number, number][] {
  const ring: [number, number][] = [];
  const dLat = radiusKm / 111.32;
  const dLon = dLat / Math.max(0.1, Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= 48; i += 1) {
    const a = (i / 48) * 2 * Math.PI;
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return ring;
}
