import { useEffect, useImperativeHandle, useRef, useState } from 'react';
import type { Ref, RefObject } from 'react';
import { Marker } from 'maplibre-gl';
import type { LngLat, LngLatLike, Map as MapLibreMap, MapGeoJSONFeature, Point } from 'maplibre-gl';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import CloseButton from '../ui/CloseButton';
import { createMap, removeMap } from './createMap';
import { placeHitTest } from './hitTest';
import { oncePerFrame } from './oncePerFrame';
import { PLACE_LAYERS, styleFor } from './style';
import { useMapFailure } from './useMapFailure';
import './MapView.css';

/** How close (px) to the edge of a bottom inset a place may sit before `reveal` pans. */
const REVEAL_MARGIN = 24;

/** The single marker of the map: where it stands, and what its tooltip names. */
export interface MapMarker {
  at: [lon: number, lat: number];
  title: string;
}

/** Called with the place label a click hit, or `null` when it hit none, and where the click was. */
export type SelectFeature = (feature: MapGeoJSONFeature | null, at: LngLat) => void;

export interface MapViewProps {
  /**
   * The view: a dialect ("frr-x-mooring") or the local view (LOCAL_TAG).
   * The style is rebuilt on every change.
   */
  view: string;
  /** Left out by the dev views, which bring their own click handling. */
  onSelectFeature?: SelectFeature;
  /** Called with the map once its first style has loaded: the dev views draw on it. */
  onReady?: (map: MapLibreMap) => void;
  /** The marker to show, if any (see selection/placeSelection.ts `markerOf`). */
  marker?: MapMarker | null;
  /** The imperative handle below, for App's map moves. */
  ref?: Ref<MapViewHandle>;
}

/** The map moves a selection makes: all the public app asks of the map. */
export interface MapMoves {
  /**
   * Animate to `center` at `zoom`. `inset` is how many pixels at the bottom
   * of the map something covers (the phone bottom sheet): the place lands in
   * the middle of what stays visible.
   */
  flyTo(center: LngLatLike, zoom: number, inset: number): void;
  /**
   * Pan up just enough to bring `center` into the middle of the part of the
   * map above a bottom `inset`, if that inset covers it. No-op otherwise.
   */
  reveal(center: LngLatLike, inset: number): void;
}

/**
 * Imperative API exposed to parents via ref. Methods read the live map
 * instance lazily, so they work regardless of when the map finished
 * initialising relative to the parent's render.
 */
export type MapViewHandle = MapMoves;

/** Full-viewport MapLibre map, labelled in `view`. */
export default function MapView({
  view,
  onSelectFeature,
  onReady,
  marker = null,
  ref,
}: MapViewProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { mapRef, map } = useMapInstance(containerRef, view, t);
  useMapHandle(ref, mapRef);
  useReady(map, onReady);
  useViewStyle(map, view);
  usePlaceClicks(map, onSelectFeature);
  useMarker(map, marker);
  const { failure, dismiss } = useMapFailure(map);

  return (
    <>
      <div ref={containerRef} className="map-container" />
      {failure && (
        <div className="map-error panel" role="alert">
          <span>{t('errors.map')}</span>
          <CloseButton label={t('errors.dismiss')} onClick={dismiss} />
        </div>
      )}
    </>
  );
}

/**
 * The map in `containerRef`, created once on mount in `initialView`, its
 * controls labelled by `t`. As a ref for the handle, whose methods have to
 * reach it in the effects of the parent's first render, and as state for the
 * hooks that set it up.
 */
function useMapInstance(
  containerRef: RefObject<HTMLDivElement | null>,
  initialView: string,
  t: TFunction,
): { mapRef: RefObject<MapLibreMap | null>; map: MapLibreMap | null } {
  const mapRef = useRef<MapLibreMap | null>(null);
  const [map, setMap] = useState<MapLibreMap | null>(null);
  useEffect(() => {
    if (!containerRef.current) return;
    const created = createMap(containerRef.current, styleFor(initialView), t);
    mapRef.current = created;
    setMap(created);
    return () => {
      removeMap(created);
      mapRef.current = null;
      setMap(null);
    };
    // Only the initial view matters here; changes are handled by useViewStyle.
    // The controls keep the strings of the first `t` (see createMap).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { mapRef, map };
}

/**
 * The handle must not capture mapRef.current: this hook runs in the layout
 * phase, before the effect that creates the map, so a captured value would be
 * null forever. Reading the ref inside each method sidesteps that.
 */
function useMapHandle(ref: Ref<MapViewHandle> | undefined, mapRef: RefObject<MapLibreMap | null>) {
  useImperativeHandle(
    ref,
    () => ({
      flyTo: (center, zoom, inset) => {
        // A one-off offset rather than map padding: padding would stay on
        // the map after the sheet closes, and shift every later view.
        mapRef.current?.flyTo({ center, zoom, offset: [0, -inset / 2], essential: true });
      },
      reveal: (center, inset) => {
        if (mapRef.current) revealAbove(mapRef.current, center, inset);
      },
    }),
    [mapRef],
  );
}

/** Pans `map` so `center` sits in the middle of what a bottom `inset` leaves visible, if it covers it. */
function revealAbove(map: MapLibreMap, center: LngLatLike, inset: number): void {
  if (inset <= 0) return;
  const height = map.getContainer().clientHeight;
  const { y } = map.project(center);
  if (y < height - inset - REVEAL_MARGIN) return;
  map.panBy([0, y - (height - inset) / 2]);
}

/** Hands `map` to `onReady` once its first style has loaded. */
function useReady(map: MapLibreMap | null, onReady?: (map: MapLibreMap) => void): void {
  useEffect(() => {
    if (!map || !onReady) return;
    const ready = () => onReady(map);
    map.once('load', ready);
    return () => {
      map.off('load', ready);
    };
  }, [map, onReady]);
}

/**
 * Rebuilds the style whenever the view actually changes. Tracking the applied
 * view (rather than a first-run flag) also survives React StrictMode's double
 * effect invocation in development.
 */
function useViewStyle(map: MapLibreMap | null, view: string): void {
  const appliedView = useRef(view);
  useEffect(() => {
    if (!map || appliedView.current === view) return;
    appliedView.current = view;
    map.setStyle(styleFor(view));
  }, [map, view]);
}

/**
 * Place labels are clickable: a click hands the label it hit to
 * `onSelectFeature`, and the pointer turns into a hand over one. Registered
 * once, on the map rather than on layer ids (those would have to be
 * re-registered after every setStyle), so they read the current callback
 * through a ref instead of capturing it.
 */
function usePlaceClicks(map: MapLibreMap | null, onSelectFeature?: SelectFeature): void {
  const selectRef = useRef(onSelectFeature);
  useEffect(() => {
    selectRef.current = onSelectFeature;
  }, [onSelectFeature]);
  useEffect(() => {
    if (!map) return;
    const hit = placeHitTest(map, PLACE_LAYERS);
    const clicks = map.on('click', (e) => selectRef.current?.(hit(e.point) ?? null, e.lngLat));
    // A hit test over every label layer is too much for every mouse move;
    // the cursor only has to keep up with what is painted.
    const hover = oncePerFrame((point: Point) => {
      map.getCanvas().style.cursor = hit(point) ? 'pointer' : '';
    });
    const moves = map.on('mousemove', (e) => {
      if (selectRef.current) hover.call(e.point);
    });
    return () => {
      hover.cancel();
      clicks.unsubscribe();
      moves.unsubscribe();
    };
  }, [map]);
}

/** Shows `marker` on `map`, recreated whenever it changes. */
function useMarker(map: MapLibreMap | null, marker: MapMarker | null): void {
  useEffect(() => {
    if (!map || !marker) return;
    const pin = new Marker({ color: '#d33' }).setLngLat(marker.at).addTo(map);
    if (marker.title) pin.getElement().title = marker.title;
    return () => {
      pin.remove();
    };
  }, [map, marker]);
}
