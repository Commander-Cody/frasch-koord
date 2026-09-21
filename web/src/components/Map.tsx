import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  AttributionControl,
  addProtocol,
} from 'maplibre-gl';
import type { LngLatLike, MapGeoJSONFeature, StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Protocol } from 'pmtiles';

import fraschBright from '../style/frasch-bright.json';
import { buildStyle, placeLayerIds } from '../style/localize';
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

/** Half-width in pixels of the box a click queries: a finger is not a pixel. */
const CLICK_SLOP = 6;

export interface MapViewProps {
  /**
   * Label option tag: a dialect ("frr-x-mooring") or the local-dialect view
   * (LOCAL_TAG). Passed straight to `buildStyle`; the style is rebuilt on
   * every change.
   */
  labels: string;
  /**
   * Called with the place label a click hit, or `null` when it hit none.
   * Left out by the dev views, which bring their own click handling.
   */
  onSelectFeature?: (feature: MapGeoJSONFeature | null) => void;
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
const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView(
  { labels, onSelectFeature },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const appliedLabels = useRef(labels);
  // The click handler is registered once, on the map rather than on layer
  // ids (those would have to be re-registered after every setStyle), so it
  // reads the current callback through a ref instead of capturing it.
  const selectRef = useRef(onSelectFeature);
  useEffect(() => {
    selectRef.current = onSelectFeature;
  }, [onSelectFeature]);

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

    const style = buildStyle(fraschBright as unknown as StyleSpecification, TILES_URL, labels);
    const map = new MapLibreMap({
      container: containerRef.current,
      style,
      center: NORTH_FRISIA_CENTER,
      zoom: INITIAL_ZOOM,
      // Reflects viewport (zoom/lat/lon[/bearing/pitch]) in the URL hash and
      // reads an initial view from it if present, e.g. `#12/54.64/8.77`.
      // Handy for linking to / screenshotting a specific view.
      hash: true,
      attributionControl: false,
    });
    // Place labels are clickable: hit-test a small box around the pointer
    // against the label layers of the current style and hand the topmost
    // feature to the parent. A click that hits none clears the selection.
    // Read off the style once — every label option rebuilds the same layers,
    // only their text-field changes — and skip the ones a style in flight has
    // not added yet.
    const placeLayers = placeLayerIds(style);
    const labelLayers = () => placeLayers.filter((id) => map.getLayer(id));
    const hit = (point: { x: number; y: number }) =>
      map.queryRenderedFeatures(
        [
          [point.x - CLICK_SLOP, point.y - CLICK_SLOP],
          [point.x + CLICK_SLOP, point.y + CLICK_SLOP],
        ],
        { layers: labelLayers() },
      )[0];
    map.on('click', (e) => {
      if (!selectRef.current) return;
      selectRef.current(hit(e.point) ?? null);
    });
    map.on('mousemove', (e) => {
      if (!selectRef.current) return;
      map.getCanvas().style.cursor = hit(e.point) ? 'pointer' : '';
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
    // Only the initial label option matters here; changes are handled below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Rebuild the style whenever the label option actually changes. Tracking
  // the applied option (rather than a first-run flag) also survives React
  // StrictMode's double effect invocation in development.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || appliedLabels.current === labels) return;
    appliedLabels.current = labels;
    map.setStyle(buildStyle(fraschBright as unknown as StyleSpecification, TILES_URL, labels));
  }, [labels]);

  return <div ref={containerRef} className="map-container" />;
});

export default MapView;
