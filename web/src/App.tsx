import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import AreaPanel from './components/AreaPanel';
import CuratePanel from './components/CuratePanel';
import MapView from './components/Map';
import type { MapViewHandle } from './components/Map';
import SearchPanel from './components/SearchPanel';
import type { NameEntry } from './components/SearchPanel';
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
  const mapRef = useRef<MapViewHandle | null>(null);

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
  };

  // Both dev views keep the default labels/UI language: they are about which
  // OSM object a row means, and which dialect an area is, not about how the
  // map reads. `?curate` wins if both are set.
  const panel = CURATE_MODE ? (
    <CuratePanel mapRef={mapRef} />
  ) : AREAS_MODE ? (
    <AreaPanel mapRef={mapRef} />
  ) : (
    <SearchPanel labels={labels} onLabelsChange={handleLabelsChange} onSelect={handleSelect} />
  );

  return (
    <div className="app">
      <MapView ref={mapRef} labels={labels} />
      {panel}
    </div>
  );
}

export default App;
