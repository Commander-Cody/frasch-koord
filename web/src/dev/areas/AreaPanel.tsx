/**
 * Dialect-area review view (`?areas`). Dev only, read-only.
 *
 * `names/dialect_areas.csv` assigns every municipality of Kreis Nordfriesland
 * to a dialect, and the mainland rows are a researched draft nobody has
 * checked. A wrong row is invisible in the data — places are joined to an area
 * by point-in-polygon at build time, never by name — so it only ever shows up
 * as a wrong label on the map. This view puts the rows *on* the map: every
 * municipality coloured by its dialect, with the row's research `note` a click
 * away, and the municipalities no row claims drawn in grey so a hole in the
 * coverage cannot be missed.
 *
 * Nothing writes back. Edit `names/dialect_areas.csv`, re-run
 * `just rebuild areas`, press Reload.
 *
 * English-only on purpose, like the curation view: this is a tool, not the map.
 */
import { useMemo, useState } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { DIALECTS } from '../../dialects/registry';
import DevPanel from '../shell/DevPanel';
import { fetchJson } from '../shell/fetchJson';
import { useDevResource } from '../shell/useDevResource';
import AreaDetail from './AreaDetail';
import AreaFilters from './AreaFilters';
import AreaLegend from './AreaLegend';
import AreaList from './AreaList';
import { filterAreas, groupByDialect, type AreaCollection } from './areas';
import { useAreaMap } from './useAreaMap';
import { useAreaSelection } from './useAreaSelection';
import './AreaPanel.css';

/** The geometry is a build artefact, served by web/vite-plugins. */
const loadAreas = () => fetchJson<AreaCollection>('/__areas/parts');

/** Registry order, so the legend and the list read like names/dialects.csv. */
const DIALECT_ORDER = DIALECTS.map((d) => d.tag);

export default function AreaPanel({ map }: { map: MapLibreMap }) {
  const resource = useDevResource(loadAreas);
  const features = useMemo(() => resource.data?.features ?? [], [resource.data]);
  const groups = useMemo(() => groupByDialect(features, DIALECT_ORDER), [features]);
  const [text, setText] = useState('');
  const [shown, setShown] = useState<string | null>(null);
  const visible = useMemo(() => filterAreas(features, { text, shown }), [features, text, shown]);
  const sections = useMemo(() => groupByDialect(visible, DIALECT_ORDER), [visible]);
  const selection = useAreaSelection(map, features, sections);
  useAreaMap(map, {
    collection: resource.data,
    selectedOsm: selection.area?.properties.osm ?? null,
    shown,
    // Deliberately no move: the map must not jump out from under the cursor.
    onPick: selection.selectInPlace,
  });

  return (
    <DevPanel
      className="area-panel"
      title="Dialect areas"
      what="the areas"
      needs={
        <>
          This view needs the Vite dev server (<code>npm run dev</code>) and the geometry built by{' '}
          <code>just rebuild areas</code>.
        </>
      }
      resource={resource}
      header={
        <AreaFilters text={text} onText={setText} features={features} shown={visible.length} />
      }
    >
      <AreaLegend groups={groups} shown={shown} onShow={setShown} />
      {selection.area && <AreaDetail area={selection.area.properties} />}
      <AreaList
        sections={sections}
        selected={selection.selected}
        onSelect={selection.select}
        itemRef={selection.itemRef}
      />
    </DevPanel>
  );
}
