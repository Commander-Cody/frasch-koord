import { useRef, useState } from 'react';

import MapView from './components/Map';
import type { MapViewHandle } from './components/Map';
import SearchPanel from './components/SearchPanel';
import type { NameEntry } from './components/SearchPanel';
import { DEFAULT_DIALECT } from './config';
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

function App() {
  const [dialect, setDialect] = useState(DEFAULT_DIALECT);
  const mapRef = useRef<MapViewHandle | null>(null);

  const handleSelect = (entry: NameEntry) => {
    const zoom = ZOOM_BY_KIND[entry.kind] ?? DEFAULT_TARGET_ZOOM;
    mapRef.current?.flyTo([entry.lon, entry.lat], zoom, { title: entry.name });
  };

  return (
    <div className="app">
      <MapView ref={mapRef} dialect={dialect} />
      <SearchPanel dialect={dialect} onDialectChange={setDialect} onSelect={handleSelect} />
    </div>
  );
}

export default App;
