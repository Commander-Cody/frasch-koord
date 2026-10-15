import {
  AttributionControl,
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
} from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// MapLibre 6 looks for its worker next to its own module
// (`new URL('./maplibre-gl-worker.mjs', import.meta.url)`), a file Vite's
// production build never emits: the request would get index.html and no tile
// would ever be parsed. `?worker&url` makes Vite bundle the worker — with the
// maplibre-gl-shared.mjs chunk it imports — as an asset of its own, and
// setWorkerUrl points MapLibre at it, in dev and build alike.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

import { keepingHash } from '../url/queryParams';
import { registerPmtilesProtocol } from './pmtiles';

setWorkerUrl(maplibreWorkerUrl);

const NORTH_FRISIA_CENTER: [number, number] = [8.85, 54.6];
const INITIAL_ZOOM = 9;

/** A MapLibre map in `container`, styled with `style`, with the site's controls. */
export function createMap(container: HTMLElement, style: StyleSpecification): MapLibreMap {
  registerPmtilesProtocol();
  const map = new MapLibreMap({
    container,
    style,
    center: NORTH_FRISIA_CENTER,
    zoom: INITIAL_ZOOM,
    // Reflects the viewport (zoom/lat/lon[/bearing/pitch]) in the URL hash
    // and reads an initial one from it if present, e.g. `#12/54.64/8.77`.
    // Handy for linking to / screenshotting a specific place. The view and
    // the open place ride along in the query (url/linkState.ts).
    hash: true,
    attributionControl: false,
  });
  map.addControl(new NavigationControl(), 'top-right');
  map.addControl(new AttributionControl({ compact: false }), 'bottom-right');
  // For the production-build smoke check (scripts/smoke.ts), which has no
  // other way to see the map load.
  map.once('load', () => {
    map.getContainer().dataset.state = 'loaded';
  });
  return map;
}

/**
 * Removes `map`, leaving the URL's hash as it is. MapLibre's `hash: true`
 * clears the hash inside map.remove(). In dev, React StrictMode mounts a map,
 * removes it, then mounts it again, all before paint; without this, that
 * throwaway first map would wipe an initial `#zoom/lat/lon` hash before the
 * second (real) one ever gets to read it.
 */
export function removeMap(map: MapLibreMap): void {
  keepingHash(() => map.remove());
}
