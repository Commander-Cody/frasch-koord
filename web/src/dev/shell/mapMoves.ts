// The map moves of the dev panels: to a point, or to fit a stretch of map,
// in both cases clear of the panel over the map's left edge.

import type { LngLatBoundsLike, LngLatLike, Map as MapLibreMap } from 'maplibre-gl';

import { FIT_PADDING } from './panelLayout';

/** How close the panels go: one object fills the view. */
export const CLOSE_ZOOM = 14;

/** Flies to `center`. Every move answers the user's own action, so `essential`: reduced motion does not skip it. */
export function flyTo(map: MapLibreMap, center: LngLatLike, zoom = CLOSE_ZOOM): void {
  map.flyTo({ center, zoom, essential: true });
}

/** Fits `bounds` into the part of the map the panel leaves free. */
export function fitTo(map: MapLibreMap, bounds: LngLatBoundsLike): void {
  map.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: CLOSE_ZOOM, duration: 600 });
}
