import { useRef } from 'react';
import { useTranslation } from 'react-i18next';

import CloseButton from './components/CloseButton';
import ErrorBoundary from './components/ErrorBoundary';
import MapView from './components/Map';
import type { MapViewHandle } from './components/Map';
import PlaceCard from './components/PlaceCard';
import SearchPanel from './components/SearchPanel';
import { useCardFocus } from './hooks/useCardFocus';
import { useCloseOnEscape } from './hooks/useCloseOnEscape';
import { useLinkedPlace } from './hooks/useLinkedPlace';
import { usePlaceSelection } from './hooks/usePlaceSelection';
import { useSheetHeight } from './hooks/useSheetHeight';
import { useUrlSync } from './hooks/useUrlSync';
import { useView } from './hooks/useView';
import { useNames } from './names';
import { useProvenanceCheck } from './provenance';
import './App.css';

function App() {
  const mapRef = useRef<MapViewHandle | null>(null);
  const appRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLElement | null>(null);
  const cardHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const searchFieldRef = useRef<HTMLInputElement | null>(null);
  // One fetch of the name list for both the search index and the card.
  const { status: namesStatus, entries, find, builtFrom } = useNames();
  useProvenanceCheck(builtFrom);
  const [view, changeView] = useView();
  const { selection, selectEntry, selectFeature, openLinked, close } = usePlaceSelection(
    mapRef,
    cardRef,
    find,
    view,
  );
  const { focusNextCard, closeByKeyboard } = useCardFocus(
    { card: cardRef, heading: cardHeadingRef, searchField: searchFieldRef },
    selection,
    close,
  );
  const linkedPlace = useLinkedPlace(namesStatus, find, openLinked);
  const cardOpen = selection !== null;
  useSheetHeight(appRef, cardRef, cardOpen);
  useUrlSync({ view, place: selection?.entry?.id ?? linkedPlace });
  useCloseOnEscape(cardOpen, closeByKeyboard);

  return (
    <div ref={appRef} className="app">
      <MapView ref={mapRef} view={view} onSelectFeature={selectFeature} />
      {/* The side panel only: a card that trips over a malformed entry must
          not unmount the map with it. */}
      <ErrorBoundary
        resetKey={selection}
        fallback={(reset) => (
          <div className="side-panel">
            <PanelError
              onClose={() => {
                close();
                reset();
              }}
            />
          </div>
        )}
      >
        <div className="side-panel">
          <SearchPanel
            ref={searchFieldRef}
            entries={entries}
            status={namesStatus}
            view={view}
            onViewChange={changeView}
            onSelect={(entry, name) => {
              focusNextCard();
              selectEntry(entry, name);
            }}
          />
          {selection && (
            <PlaceCard
              ref={cardRef}
              headingRef={cardHeadingRef}
              selection={selection}
              view={view}
              onClose={(byKeyboard) => (byKeyboard ? closeByKeyboard() : close())}
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
