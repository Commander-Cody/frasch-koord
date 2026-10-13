import { useCallback, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { LngLat, MapGeoJSONFeature } from 'maplibre-gl';

import CloseButton from './components/CloseButton';
import ErrorBoundary from './components/ErrorBoundary';
import MapView from './components/Map';
import type { MapViewHandle } from './components/Map';
import PlaceCard from './components/PlaceCard';
import SearchPanel from './components/SearchPanel';
import { useCloseOnEscape } from './hooks/useCloseOnEscape';
import { usePlaceSelection } from './hooks/usePlaceSelection';
import { useSheetHeight } from './hooks/useSheetHeight';
import { useView } from './hooks/useView';
import { useNames } from './names/load';
import { mapPick, markerOf } from './placeSelection';
import { useProvenanceCheck } from './provenance';
import './App.css';

function App() {
  const mapRef = useRef<MapViewHandle | null>(null);
  const appRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLElement | null>(null);
  const cardHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const searchFieldRef = useRef<HTMLInputElement | null>(null);
  // One fetch of the name list for both the search index and the card.
  const names = useNames();
  useProvenanceCheck(names.builtFrom);
  const [view, changeView] = useView();
  const { selection, select, close } = usePlaceSelection(names, {
    map: mapRef,
    card: cardRef,
    heading: cardHeadingRef,
    searchField: searchFieldRef,
  });
  const marker = useMemo(() => markerOf(selection, view), [selection, view]);
  const cardOpen = selection !== null;
  useSheetHeight(appRef, cardRef, cardOpen);
  useCloseOnEscape(cardOpen, close);
  // A click on a place label opens its card; one that hits none closes it.
  const clickMap = useCallback(
    (feature: MapGeoJSONFeature | null, at: LngLat) =>
      feature ? select(mapPick(feature, at)) : close('pointer'),
    [select, close],
  );

  return (
    <div ref={appRef} className="app">
      <MapView ref={mapRef} view={view} marker={marker} onSelectFeature={clickMap} />
      {/* The side panel only: a card that trips over a malformed entry must
          not unmount the map with it. */}
      <ErrorBoundary
        resetKey={selection}
        fallback={(reset) => (
          <div className="side-panel">
            <PanelError
              onClose={() => {
                close('pointer');
                reset();
              }}
            />
          </div>
        )}
      >
        <div className="side-panel">
          <SearchPanel
            ref={searchFieldRef}
            entries={names.entries}
            status={names.status}
            view={view}
            onViewChange={changeView}
            onSelect={(entry) => select({ via: 'search', ref: entry.id })}
          />
          {selection && (
            <PlaceCard
              ref={cardRef}
              headingRef={cardHeadingRef}
              selection={selection}
              view={view}
              onClose={close}
            />
          )}
        </div>
      </ErrorBoundary>
    </div>
  );
}

/**
 * What the side panel shows after it crashed. Closing it clears the
 * selection, which is what most likely broke it, and brings the panel back,
 * also when the crash came without one (the search panel's own).
 */
function PanelError({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="panel-error" role="alert">
      <span>{t('errors.panel')}</span>
      <CloseButton className="place-card-close" label={t('card.close')} onClick={onClose} />
    </div>
  );
}

export default App;
