import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { LngLat, MapGeoJSONFeature } from 'maplibre-gl';

import type { MapViewHandle } from '../components/Map';
import type { EntryLookup, NameEntry, PlaceSelection, TileProps } from '../names';
import { displayName } from '../names';

/** Target zoom per feature kind: large areas get a wider view than villages. */
const ZOOM_BY_KIND: Record<string, number> = {
  landscape: 10,
  island: 11,
  koog: 12,
  water: 12,
  sand: 12,
  hallig: 13,
  helgoland: 13,
  settlement: 14,
  warft: 15,
};
const DEFAULT_TARGET_ZOOM = 14;

/**
 * Phone width, where the search panel is a top bar and the place card a
 * bottom sheet over the map. Must match the media query in App.css.
 */
const PHONE_MEDIA = '(max-width: 600px)';

/** A map move given how many pixels at the bottom of the map the card covers. */
type Move = (inset: number) => void;

/**
 * Schedules a map move that has to wait for the card: on a phone the card is
 * a bottom sheet, and where the place should land depends on its height. A
 * scheduled move runs (once) as soon as the card of the next selection is
 * laid out — before paint, so the map starts moving in the same frame the
 * sheet shows.
 */
function useMoveAfterCard(cardRef: RefObject<HTMLElement | null>, selection: PlaceSelection | null) {
  const pendingMove = useRef<Move | null>(null);
  useLayoutEffect(() => {
    const move = pendingMove.current;
    pendingMove.current = null;
    if (!move) return;
    const card = cardRef.current;
    move(card && window.matchMedia(PHONE_MEDIA).matches ? card.offsetHeight : 0);
  }, [cardRef, selection]);
  return useCallback((move: Move) => {
    pendingMove.current = move;
  }, []);
}

export interface PlaceSelectionState {
  /** The place whose card is open, from a map click, a search result or a link. */
  selection: PlaceSelection | null;
  /** A search result: fly there. `name` is its display name, for the marker. */
  selectEntry: (entry: NameEntry, name: string) => void;
  /** A map click on a place label, or on none (`null`), which closes the card. */
  selectFeature: (feature: MapGeoJSONFeature | null, at: LngLat) => void;
  /** A linked place (see useLinkedPlace): fly there, unless the link says where to look. */
  openLinked: (entry: NameEntry, hasViewport: boolean) => void;
  close: () => void;
}

/**
 * Which place's card is open, and moving the map to it. `find` is the name
 * list's lookup; `view` only names the marker of a linked place.
 */
export function usePlaceSelection(
  mapRef: RefObject<MapViewHandle | null>,
  cardRef: RefObject<HTMLElement | null>,
  find: EntryLookup,
  view: string,
): PlaceSelectionState {
  const [selection, setSelection] = useState<PlaceSelection | null>(null);
  const moveAfterCard = useMoveAfterCard(cardRef, selection);

  const selectEntry = (entry: NameEntry, name: string) => {
    const zoom = ZOOM_BY_KIND[entry.kind] ?? DEFAULT_TARGET_ZOOM;
    moveAfterCard((inset) => mapRef.current?.flyTo([entry.lon, entry.lat], zoom, { title: name }, inset));
    setSelection({ entry });
  };

  const close = useCallback(() => {
    setSelection(null);
    mapRef.current?.clearMarker();
  }, [mapRef]);

  /**
   * `frasch:ref` is the id of the feature's row in the name list
   * (tiles/inject_names.py writes it, names/export_search_index.py uses it as
   * the entry id; tiles built before the row ids carry the row's OSM
   * reference, which `find` knows too); a feature without one, or one the
   * list does not have, still gets a card — from the tile's own attributes.
   */
  const selectFeature = useCallback(
    (feature: MapGeoJSONFeature | null, at: LngLat) => {
      if (!feature) {
        close();
        return;
      }
      // A label tapped in the lower half of a phone would end up under the
      // sheet that is about to open.
      moveAfterCard((inset) => mapRef.current?.reveal(at, inset));
      const props = feature.properties as TileProps;
      const ref = props['frasch:ref'];
      setSelection({
        entry: typeof ref === 'string' ? find(ref) : undefined,
        props,
        featureId: feature.id,
      });
      // The label the user just clicked says where the place is; a search
      // marker from before would only sit somewhere else.
      mapRef.current?.clearMarker();
    },
    [find, close, mapRef, moveAfterCard],
  );

  const openLinked = (entry: NameEntry, hasViewport: boolean) => {
    const name = displayName(entry, view);
    if (!hasViewport) {
      selectEntry(entry, name);
      return;
    }
    setSelection({ entry });
    mapRef.current?.showMarker([entry.lon, entry.lat], { title: name });
    // The link keeps its viewport, but a desktop sharer never had the
    // phone's sheet in the way.
    moveAfterCard((inset) => mapRef.current?.reveal([entry.lon, entry.lat], inset));
  };

  return { selection, selectEntry, selectFeature, openLinked, close };
}
