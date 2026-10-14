/**
 * Root of the dev views, `?curate` (curate/CuratePanel.tsx) and `?areas`
 * (areas/AreaPanel.tsx): the map with one of the review panels instead of the
 * control bar and place card of the public App.
 *
 * Only ever loaded under `vite dev`: main.tsx imports this module behind
 * `import.meta.env.DEV`, so a production build leaves it (and both panels)
 * out entirely.
 */
import { useState } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import MapView from '../map/MapView';
import { useUiLanguage } from '../dialects/useView';
import { initialView } from '../url/linkState';
import AreaPanel from './areas/AreaPanel';
import CuratePanel from './curate/CuratePanel';
import '../App.css';

export type DevTool = 'curate' | 'areas';

export default function DevApp({ tool }: { tool: DevTool }) {
  const [view] = useState(initialView);
  // The panel comes once the map has loaded, so it can draw on it right away.
  const [map, setMap] = useState<MapLibreMap | null>(null);
  useUiLanguage(view);
  // Neither view offers the label selector: they are about which OSM object a
  // row means, and which dialect an area is, not about how the map reads, so
  // they stay in the view the page opened in. Both bring their own click
  // handling, so the map gets no place-card click handler, and neither writes
  // the public view's `?view=`/`?place=` into the URL.
  return (
    <div className="app">
      <MapView view={view} onReady={setMap} />
      {map && (tool === 'curate' ? <CuratePanel map={map} /> : <AreaPanel map={map} />)}
    </div>
  );
}
