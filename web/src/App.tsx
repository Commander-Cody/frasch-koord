import { useCallback, useEffect, useRef, useState } from 'react';
import type { MapGeoJSONFeature } from 'maplibre-gl';
import { useTranslation } from 'react-i18next';

import AreaPanel from './components/AreaPanel';
import CuratePanel from './components/CuratePanel';
import MapView from './components/Map';
import type { MapViewHandle } from './components/Map';
import PlaceCard from './components/PlaceCard';
import SearchPanel from './components/SearchPanel';
import type { NameEntry, PlaceSelection, TileProps } from './names';
import { useNames } from './names';
import { DEFAULT_LABELS, labelOption } from './config';
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

function App() {
  const { i18n } = useTranslation();
  // The selected label option: a dialect tag, or LOCAL_TAG for the local view.
  const [labels, setLabels] = useState(DEFAULT_LABELS);
  // The place whose card is open, from a map click or a search result.
  const [selection, setSelection] = useState<PlaceSelection | null>(null);
  const mapRef = useRef<MapViewHandle | null>(null);
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
    mapRef.current?.flyTo([entry.lon, entry.lat], zoom, { title: name });
    setSelection({ entry });
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
    (feature: MapGeoJSONFeature | null) => {
      if (!feature) {
        closeCard();
        return;
      }
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

  // Escape closes the card, like any transient panel.
  useEffect(() => {
    if (!selection) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeCard();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selection, closeCard]);

  // Both dev views keep the default labels/UI language: they are about which
  // OSM object a row means, and which dialect an area is, not about how the
  // map reads. `?curate` wins if both are set.
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
      {selection && <PlaceCard selection={selection} labels={labels} onClose={closeCard} />}
    </div>
  );

  return (
    <div className="app">
      {/* The dev views bring their own click handling, so they get no
          place card and no click handler of ours. */}
      <MapView ref={mapRef} labels={labels} onSelectFeature={devMode ? undefined : handleFeature} />
      {panel}
    </div>
  );
}

export default App;
