import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { LngLat, MapGeoJSONFeature } from 'maplibre-gl';
import { useTranslation } from 'react-i18next';

import AreaPanel from './components/AreaPanel';
import CuratePanel from './components/CuratePanel';
import MapView from './components/Map';
import type { MapViewHandle } from './components/Map';
import PlaceCard from './components/PlaceCard';
import SearchPanel from './components/SearchPanel';
import type { NameEntry, PlaceSelection, TileProps } from './names';
import { displayName, useNames } from './names';
import { labelOption } from './config';
import { INITIAL_LABELS, readUrlState, writeUrlState } from './urlState';
import './App.css';

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

/**
 * `?curate` opens the name-list curation review instead of the search panel
 * (dev only, see components/CuratePanel.tsx). Read once at module load: the
 * two modes are different tools, not a state the user toggles.
 */
const CURATE_MODE = new URLSearchParams(window.location.search).has('curate');

/**
 * `?areas` opens the dialect-area review instead of the search panel (dev
 * only, see components/AreaPanel.tsx). Read once at module load, like
 * CURATE_MODE: the modes are separate tools, not a state the user toggles.
 */
const AREAS_MODE = new URLSearchParams(window.location.search).has('areas');

/**
 * The place a shared link opens the card of (`?place=`, see urlState.ts), and
 * whether the link also says where to look (`#zoom/lat/lon`). Read at module
 * load, before the map mounts and starts writing a hash of its own.
 */
const LINKED_PLACE = readUrlState().place;
const LINKED_VIEWPORT = window.location.hash.length > 1;

function App() {
  const { i18n } = useTranslation();
  // The selected label option: a dialect tag, or LOCAL_TAG for the local view.
  const [labels, setLabels] = useState(INITIAL_LABELS);
  // The place whose card is open, from a map click or a search result.
  const [selection, setSelection] = useState<PlaceSelection | null>(null);
  // The linked place until the name list has loaded and it can be looked up.
  const [linkedPlace, setLinkedPlace] = useState(LINKED_PLACE);
  const mapRef = useRef<MapViewHandle | null>(null);
  const appRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLElement | null>(null);
  // A map move that has to wait for the card: on a phone the card is a
  // bottom sheet, and where the place should land depends on its height.
  // Run (and cleared) as soon as the card for the new selection is laid out.
  const pendingMove = useRef<((inset: number) => void) | null>(null);
  // One fetch of the name list for both the search index and the card.
  const { entries, byRef } = useNames();

  // Map labels and UI chrome move together: each option names the UI language
  // it comes with (the local view has no dialect of its own and borrows one,
  // see config.LOCAL_VIEW_UI_LANGUAGE). i18next falls back to German for any
  // language without resources, so unwritten dialect UIs are harmless.
  const handleLabelsChange = (tag: string) => {
    setLabels(tag);
    void i18n.changeLanguage(labelOption(tag).uiLanguage);
  };

  const handleSelect = (entry: NameEntry, name: string) => {
    const zoom = ZOOM_BY_KIND[entry.kind] ?? DEFAULT_TARGET_ZOOM;
    pendingMove.current = (inset) =>
      mapRef.current?.flyTo([entry.lon, entry.lat], zoom, { title: name }, inset);
    // A search result carries only the index's stored fields — no Danish
    // name, no Wikidata id — so the card gets the full name-list entry.
    setSelection({ entry: byRef.get(entry.id) ?? entry });
  };

  const closeCard = useCallback(() => {
    setSelection(null);
    mapRef.current?.clearMarker();
  }, []);

  /**
   * A click on a place label. `frasch:ref` is the id of the feature's row in
   * the name list (tiles/inject_names.py writes it, names/export_search_index.py
   * uses it as the entry id); a feature without one, or one the list does not
   * have, still gets a card — from the tile's own attributes.
   */
  const handleFeature = useCallback(
    (feature: MapGeoJSONFeature | null, at: LngLat) => {
      if (!feature) {
        closeCard();
        return;
      }
      // A label tapped in the lower half of a phone would end up under the
      // sheet that is about to open.
      pendingMove.current = (inset) => mapRef.current?.reveal(at, inset);
      const props = feature.properties as TileProps;
      const ref = props['frasch:ref'];
      setSelection({
        entry: typeof ref === 'string' ? byRef.get(ref) : undefined,
        props,
        featureId: feature.id,
      });
      // The label the user just clicked says where the place is; a search
      // marker from before would only sit somewhere else.
      mapRef.current?.clearMarker();
    },
    [byRef, closeCard],
  );

  // Open the card of a linked place once the name list is there. Only
  // name-list places can be linked: a tile feature the list does not have
  // (a plain German village) has nothing to look it up by before its tile is
  // on screen. Without a viewport in the link, fly there as a search would.
  useEffect(() => {
    if (!linkedPlace || byRef.size === 0) return;
    setLinkedPlace(undefined);
    const entry = byRef.get(linkedPlace);
    if (!entry) return;
    const name = displayName(entry, labels);
    if (LINKED_VIEWPORT) {
      setSelection({ entry });
      mapRef.current?.showMarker([entry.lon, entry.lat], { title: name });
      // The link keeps its viewport, but a desktop sharer never had the
      // phone's sheet in the way.
      pendingMove.current = (inset) => mapRef.current?.reveal([entry.lon, entry.lat], inset);
    } else {
      handleSelect(entry, name);
    }
    // Runs once per link; `labels` only names the marker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [byRef, linkedPlace]);

  // The card of a new selection is in the DOM now, so its height is known.
  // Before paint, so the map starts moving in the same frame the sheet shows.
  useLayoutEffect(() => {
    const move = pendingMove.current;
    pendingMove.current = null;
    if (!move) return;
    const card = cardRef.current;
    move(card && window.matchMedia(PHONE_MEDIA).matches ? card.offsetHeight : 0);
  }, [selection]);

  // The sheet's height, for App.css to lift the attribution above it on a
  // phone. Tracked while the card is open: its content changes with the
  // place and the view.
  const cardOpen = selection !== null;
  useEffect(() => {
    const app = appRef.current;
    const card = cardRef.current;
    if (!app || !card) return;
    const observer = new ResizeObserver(() => {
      app.style.setProperty('--sheet-height', `${card.offsetHeight}px`);
    });
    observer.observe(card);
    return () => {
      observer.disconnect();
      app.style.removeProperty('--sheet-height');
    };
  }, [cardOpen]);

  // Keep the address bar a shareable link to what is on screen (MapLibre adds
  // the viewport). The dev views have no selector and no card to link to.
  useEffect(() => {
    if (CURATE_MODE || AREAS_MODE) return;
    writeUrlState({ view: labels, place: selection?.entry?.id ?? linkedPlace });
  }, [labels, selection, linkedPlace]);

  // Escape closes the card, like any transient panel.
  useEffect(() => {
    if (!selection) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeCard();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selection, closeCard]);

  // Neither dev view offers the selector: they are about which OSM object a
  // row means, and which dialect an area is, not about how the map reads, so
  // they stay in the view the page opened in. `?curate` wins if both are set.
  const devMode = CURATE_MODE || AREAS_MODE;
  const panel = CURATE_MODE ? (
    <CuratePanel mapRef={mapRef} />
  ) : AREAS_MODE ? (
    <AreaPanel mapRef={mapRef} />
  ) : (
    <div className="side-panel">
      <SearchPanel
        entries={entries}
        labels={labels}
        onLabelsChange={handleLabelsChange}
        onSelect={handleSelect}
      />
      {selection && (
        <PlaceCard ref={cardRef} selection={selection} labels={labels} onClose={closeCard} />
      )}
    </div>
  );

  return (
    <div ref={appRef} className="app">
      {/* The dev views bring their own click handling, so they get no
          place card and no click handler of ours. */}
      <MapView ref={mapRef} labels={labels} onSelectFeature={devMode ? undefined : handleFeature} />
      {panel}
    </div>
  );
}

export default App;
