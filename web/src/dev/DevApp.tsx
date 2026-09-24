/**
 * Root of the dev views, `?curate` (CuratePanel.tsx) and `?areas`
 * (AreaPanel.tsx): the map with one of the review panels instead of the
 * search panel and place card of the public App.
 *
 * Only ever loaded under `vite dev`: main.tsx imports this module behind
 * `import.meta.env.DEV`, so a production build leaves it (and both panels)
 * out entirely.
 */
import { useRef } from 'react';

import MapView from '../components/Map';
import type { MapViewHandle } from '../components/Map';
import { INITIAL_LABELS } from '../urlState';
import AreaPanel from './AreaPanel';
import CuratePanel from './CuratePanel';
import '../App.css';

export type DevTool = 'curate' | 'areas';

export default function DevApp({ tool }: { tool: DevTool }) {
  const mapRef = useRef<MapViewHandle | null>(null);
  // Neither view offers the label selector: they are about which OSM object a
  // row means, and which dialect an area is, not about how the map reads, so
  // they stay in the view the page opened in. Both bring their own click
  // handling, so the map gets no place-card click handler, and neither writes
  // the public view's `?view=`/`?place=` into the URL.
  return (
    <div className="app">
      <MapView ref={mapRef} labels={INITIAL_LABELS} />
      {tool === 'curate' ? <CuratePanel mapRef={mapRef} /> : <AreaPanel mapRef={mapRef} />}
    </div>
  );
}
