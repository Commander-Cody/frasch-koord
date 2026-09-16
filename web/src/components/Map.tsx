import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  AttributionControl,
  addProtocol,
} from 'maplibre-gl';
import type { LngLatLike, StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';

import fraschBright from '../style/frasch-bright.json';
import { buildStyle } from '../style/localize';
import { TILES_URL } from '../config';

// Register the pmtiles:// protocol with MapLibre exactly once, no matter
// how many times this component mounts.
let pmtilesProtocolRegistered = false;
function ensurePmtilesProtocol(): void {
  if (pmtilesProtocolRegistered) return;
  const protocol = new Protocol();
  addProtocol('pmtiles', protocol.tile);
  pmtilesProtocolRegistered = true;
}

const NORTH_FRISIA_CENTER: [number, number] = [8.85, 54.6];
const INITIAL_ZOOM = 9;

export interface MapViewProps {
  /** BCP 47 dialect tag, e.g. "frr-x-mooring". Rebuilds the style on change. */
  dialect: string;
}

/**
 * Imperative API exposed to parents via ref. Methods read the live map
 * instance lazily, so they work regardless of when the map finished
 * initialising relative to the parent's render.
 */
export interface MapViewHandle {
  /** The underlying maplibre-gl Map, or null before mount / after unmount. */
  getMap(): MapLibreMap | null;
  /** Animate to `center` at `zoom` and drop a single marker there. */
  flyTo(center: LngLatLike, zoom: number, marker?: { title?: string }): void;
  /** Remove the marker placed by flyTo, if any. */
  clearMarker(): void;
}

/**
 * Full-viewport MapLibre map. Exposes a small imperative handle via ref so
 * parents (e.g. search) can fly to a location and drop a marker.
 */
const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView({ dialect }, ref) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const appliedDialect = useRef(dialect);

  // NOTE: the handle must not capture mapRef.current directly. This hook runs
  // in the layout phase, before the effect below has created the map, so a
  // captured value would be null forever. Reading the ref inside each method
  // sidesteps that.
  useImperativeHandle(
    ref,
    () => ({
      getMap: () => mapRef.current,
      flyTo: (center, zoom, marker) => {
        const map = mapRef.current;
        if (!map) return;
        if (!markerRef.current) {
          markerRef.current = new Marker({ color: '#d33' });
        }
        const m = markerRef.current;
        m.setLngLat(center);
        const el = m.getElement();
        if (marker?.title) el.title = marker.title;
        else el.removeAttribute('title');
        m.addTo(map);
        map.flyTo({ center, zoom, essential: true });
      },
      clearMarker: () => {
        markerRef.current?.remove();
      },
    }),
    [],
  );

  // Create the map once on mount.
  useEffect(() => {
    ensurePmtilesProtocol();
    if (!containerRef.current) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      style: buildStyle(fraschBright as unknown as StyleSpecification, TILES_URL, dialect),
      center: NORTH_FRISIA_CENTER,
      zoom: INITIAL_ZOOM,
      // Reflects viewport (zoom/lat/lon[/bearing/pitch]) in the URL hash and
      // reads an initial view from it if present, e.g. `#12/54.64/8.77`.
      // Handy for linking to / screenshotting a specific view.
      hash: true,
      attributionControl: false,
    });
    map.addControl(new NavigationControl(), 'top-right');
    map.addControl(new AttributionControl({ compact: false }), 'bottom-right');

    mapRef.current = map;

    return () => {
      // MapLibre's `hash: true` clears the URL hash inside map.remove().
      // In dev, React StrictMode mounts this effect, cleans it up, then
      // mounts it again, all before paint; without this, that throwaway
      // first mount's cleanup would wipe an initial `#zoom/lat/lon` hash
      // before the second (real) mount ever gets to read it. Preserve and
      // restore it so both mounts see the same starting view.
      const hash = window.location.hash;
      markerRef.current?.remove();
      markerRef.current = null;
      map.remove();
      if (hash) {
        window.history.replaceState(window.history.state, '', hash);
      }
      mapRef.current = null;
    };
    // Only the initial dialect matters here; changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Rebuild the style whenever the dialect actually changes. Tracking the
  // applied dialect (rather than a first-run flag) also survives React
  // StrictMode's double effect invocation in development.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || appliedDialect.current === dialect) return;
    appliedDialect.current = dialect;
    map.setStyle(buildStyle(fraschBright as unknown as StyleSpecification, TILES_URL, dialect));
  }, [dialect]);

  return <div ref={containerRef} className="map-container" />;
});

export default MapView;
