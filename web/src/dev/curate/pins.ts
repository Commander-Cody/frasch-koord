// The pins the curation view puts on the map for the selected row: its
// candidates and lookup results, numbered, the location hint, and the
// position pin of a local reference. MapLibre positions the markers; the
// hooks below only add and remove them. The hint's radius is hintCircle.ts.

import { useEffect, useRef } from 'react';
import { LngLatBounds, Marker } from 'maplibre-gl';
import type { MapMouseEvent, Map as MapLibreMap } from 'maplibre-gl';

import { fitTo, flyTo } from '../shell/mapMoves';
import { COLOR_HINT, type HintPoint } from './hintCircle';
import type { LookupResult } from './osmLookup';
import type { Bbox, CurateCandidate, ListRow } from './worklist';

/* ----------------------------------------------------------------- colour */

/** Pin colours. Kept to three groups on purpose — this is a working tool. */
const COLOR_SETTLEMENT = '#d81b60';
const COLOR_AREA = '#1e88e5';
const COLOR_OTHER = '#6d4c41';
export const COLOR_LOOKUP = '#f9a825';
/** A position set by hand: the colour DevPanel.css has for what is decided (`--dev-panel-ok`). */
const COLOR_POSITION = '#2e7d32';

/**
 * A candidate's pin colour. `settlementPlaces`: the classes that mean "a
 * place where people live" (the worklist's `settlement_places`).
 */
export function candidateColor(
  candidate: CurateCandidate,
  settlementPlaces: readonly string[],
): string {
  if (settlementPlaces.includes(candidate.class)) return COLOR_SETTLEMENT;
  if (candidate.ref.startsWith('way/') || candidate.ref.startsWith('relation/')) return COLOR_AREA;
  return COLOR_OTHER;
}

/** True when the candidate carries a usable position. */
export function hasPoint(
  candidate: CurateCandidate,
): candidate is CurateCandidate & { lon: number; lat: number } {
  return candidate.lon !== null && candidate.lat !== null;
}

/* ------------------------------------------------------------------- pins */

/** What the map flies to when the row has nothing to pin: the region. */
const REGION_ZOOM = 9;

/** Where the pins register by ref, and what clicking them does. */
interface PinWiring {
  /** Pin element per ref (`useRowPins`'s `pinEls`). */
  pins: Map<string, HTMLElement>;
  onActivate: (ref: string) => void;
  onToggle: (ref: string, wikidata?: string) => void;
}

/** The wiring of the candidates' pins, which also have a colour each. */
interface CandidatePinWiring extends PinWiring {
  colorOf: (candidate: CurateCandidate) => string;
}

/** A numbered dot as a marker element; MapLibre positions it, we only style it. */
function pinElement(label: string, color: string, title: string): HTMLElement {
  const el = document.createElement('div');
  el.className = 'curate-pin';
  el.style.background = color;
  el.textContent = label;
  el.title = title;
  return el;
}

/** A pin's click and shift-click; neither reaches the map (position picking). */
function onPinClick(el: HTMLElement, click: () => void, shiftClick: () => void): void {
  el.addEventListener('click', (event) => {
    event.stopPropagation();
    if (event.shiftKey) shiftClick();
    else click();
  });
}

/** Drops `el` from the ref -> pin map, leaving another pin under the same ref alone. */
function unregisterPin(pins: Map<string, HTMLElement>, el: HTMLElement): void {
  for (const [ref, pin] of pins) if (pin === el) pins.delete(ref);
}

function removeMarkers(markers: Marker[], pins: Map<string, HTMLElement>): void {
  for (const marker of markers) {
    unregisterPin(pins, marker.getElement());
    marker.remove();
  }
}

/* ------------------------------------------------------------------ hooks */

export interface RowPinsOptions {
  row: ListRow;
  /** The worklist's bbox: what the map shows when the row has nothing to pin. */
  bbox: Bbox;
  /** The worklist's `settlement_places`: what colours a candidate's pin as a settlement. */
  settlementPlaces: readonly string[];
  lookupResults: LookupResult[];
  /** What is ticked for a multi-object pick; those pins are marked. */
  checked: readonly { ref: string }[];
  /** A click on a candidate pin. Must be stable: a new one would re-fit the map. */
  onActivate: (ref: string) => void;
  /** A shift-click on a pin. Must be stable, like `onActivate`. */
  onToggle: (ref: string, wikidata?: string) => void;
}

/**
 * The row's candidate pins, its location hint and the lookup results' pins,
 * with the map fitted to the row. Ticked refs get their pins marked.
 */
export function useRowPins(map: MapLibreMap, options: RowPinsOptions): void {
  const { row, bbox, settlementPlaces, lookupResults, checked, onActivate, onToggle } = options;
  /** Pin element per ref, so ticking only toggles a class instead of re-adding markers. */
  const pinEls = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    const pins = pinEls.current;
    const bounds = new LngLatBounds();
    const colorOf = (candidate: CurateCandidate) => candidateColor(candidate, settlementPlaces);
    const markers = [
      ...candidateMarkers(map, row, { pins, colorOf, onActivate, onToggle }, bounds),
    ];
    const hint = row.hint_point;
    if (hint) markers.push(hintMarker(map, hint, row.hint, bounds));

    if (markers.length > 0) {
      fitTo(map, bounds);
    } else {
      // Nothing to look at: at least put the region on screen.
      const [w, s, e, n] = bbox;
      flyTo(map, [(w + e) / 2, (s + n) / 2], REGION_ZOOM);
    }

    return () => removeMarkers(markers, pins);
  }, [map, row, bbox, settlementPlaces, onActivate, onToggle]);

  useEffect(() => {
    if (lookupResults.length === 0) return;
    const pins = pinEls.current;
    const markers = lookupResults.map((result, i) =>
      lookupMarker(map, result, i, { pins, onToggle }),
    );
    return () => removeMarkers(markers, pins);
  }, [map, lookupResults, onToggle]);

  // Declared after the pin effects so their elements are registered first.
  useEffect(() => {
    const checkedRefs = new Set(checked.map((item) => item.ref));
    for (const [ref, el] of pinEls.current) {
      el.classList.toggle('curate-pin-checked', checkedRefs.has(ref));
    }
  }, [checked, row, lookupResults]);
}

function candidateMarkers(
  map: MapLibreMap,
  row: ListRow,
  { pins, colorOf, onActivate, onToggle }: CandidatePinWiring,
  bounds: LngLatBounds,
): Marker[] {
  const markers: Marker[] = [];
  row.candidates.forEach((candidate, i) => {
    if (!hasPoint(candidate)) return;
    const title = `${candidate.ref} ${candidate.name} (${candidate.class})`;
    const el = pinElement(String(i + 1), colorOf(candidate), title);
    onPinClick(
      el,
      () => onActivate(candidate.ref),
      () => onToggle(candidate.ref, candidate.wikidata),
    );
    pins.set(candidate.ref, el);
    markers.push(new Marker({ element: el }).setLngLat([candidate.lon, candidate.lat]).addTo(map));
    bounds.extend([candidate.lon, candidate.lat]);
  });
  return markers;
}

function hintMarker(
  map: MapLibreMap,
  [lon, lat, radiusKm]: HintPoint,
  text: string,
  bounds: LngLatBounds,
): Marker {
  const el = pinElement('H', COLOR_HINT, `location hint: ${text} (${radiusKm} km)`);
  el.classList.add('curate-pin-hint');
  bounds.extend([lon, lat]);
  return new Marker({ element: el }).setLngLat([lon, lat]).addTo(map);
}

function lookupMarker(
  map: MapLibreMap,
  result: LookupResult,
  i: number,
  { pins, onToggle }: Pick<PinWiring, 'pins' | 'onToggle'>,
): Marker {
  const el = pinElement(String(i + 1), COLOR_LOOKUP, `${result.ref} ${result.name}`);
  el.classList.add('curate-pin-lookup');
  onPinClick(
    el,
    () => flyTo(map, [result.lon, result.lat]),
    () => onToggle(result.ref, result.wikidata),
  );
  // A ref that is also a candidate keeps its candidate pin in the map.
  if (!pins.has(result.ref)) pins.set(result.ref, el);
  return new Marker({ element: el }).setLngLat([result.lon, result.lat]).addTo(map);
}

export interface Position {
  lon: number;
  lat: number;
}

export interface PositionPinOptions {
  position: Position | null;
  setPosition: (position: Position) => void;
  /** Whether the next map click sets the position. */
  picking: boolean;
  setPicking: (picking: boolean) => void;
}

/** The draggable pin of a local reference's position, and setting it by a map click. */
export function usePositionPin(
  map: MapLibreMap,
  { position, setPosition, picking, setPicking }: PositionPinOptions,
): void {
  useEffect(() => {
    if (!picking) return;
    const onClick = (event: MapMouseEvent) => {
      setPosition({ lon: event.lngLat.lng, lat: event.lngLat.lat });
      setPicking(false);
    };
    map.on('click', onClick);
    map.getCanvas().style.cursor = 'crosshair';
    return () => {
      map.off('click', onClick);
      map.getCanvas().style.cursor = '';
    };
  }, [map, picking, setPosition, setPicking]);

  // One marker for the component's lifetime, moved rather than recreated: a
  // drag sets the position it already shows.
  const marker = useRef<Marker | null>(null);
  useEffect(() => {
    if (!position) return;
    if (marker.current) {
      marker.current.setLngLat([position.lon, position.lat]);
      return;
    }
    const pin = new Marker({ color: COLOR_POSITION, draggable: true })
      .setLngLat([position.lon, position.lat])
      .addTo(map);
    pin.on('dragend', () => {
      const at = pin.getLngLat();
      setPosition({ lon: at.lng, lat: at.lat });
    });
    marker.current = pin;
  }, [map, position, setPosition]);
  useEffect(
    () => () => {
      marker.current?.remove();
      marker.current = null;
    },
    [],
  );
}
