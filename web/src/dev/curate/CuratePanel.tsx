/**
 * Curation review view (`?curate`, dev only, English-only on purpose — this is
 * a tool for the name-list owner, not part of the public map).
 *
 * It shows the rows `frasch curate export` could not decide (`ambiguous`) or
 * could not find at all (`not_found`), drops the candidates on the map as
 * numbered pins, and writes every pick to `names/work/curate-patch.jsonl`
 * through the dev-server endpoints in `web/vite-plugins/curate.ts`.
 * `frasch curate apply` later folds that patch into places.csv/curation.csv;
 * after that, or after another export, Reload reads the worklist again.
 *
 * One place can be several OSM objects (a node and its area, a landscape made
 * of relations): tick candidates or lookup results — or shift-click their pins
 * — and "Pick selected" saves them as one `osm` cell, `a; b; c`.
 *
 * This component holds the worklist, the filter and the selection; the list,
 * the selected row's detail with its lookups, and the map's pins are their
 * own modules (CurateList, CurateDetail, CurateLookup, pins, hintCircle).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import DevPanel from '../shell/DevPanel';
import { useDevResource } from '../shell/useDevResource';
import { useSelection, type Selection } from '../shell/useSelection';
import CurateDetail from './CurateDetail';
import CurateFilters from './CurateFilters';
import CurateList from './CurateList';
import { decidedRows, postPatchEntry, type Decision, type PatchEntry } from './patch';
import {
  filterRows,
  loadWorklist,
  NO_FILTER,
  rowKinds,
  type CurateRow,
  type LoadedWorklist,
} from './worklist';
import './CuratePanel.css';

export default function CuratePanel({ map }: { map: MapLibreMap }) {
  const resource = useDevResource(loadWorklist);
  const worklist = resource.data?.worklist;
  const [filter, setFilter] = useState(NO_FILTER);

  const doneById = useMemo(() => decidedRows(resource.data?.entries ?? []), [resource.data]);
  // Memoised so every derivation below (and the lint's dependency analysis)
  // sees one stable array rather than a fresh `[]` on each render.
  const rows = useMemo(() => worklist?.rows ?? [], [worklist]);
  const visible = useMemo(
    () => filterRows(rows, filter, (id) => doneById.has(id)),
    [rows, filter, doneById],
  );

  // `?curate&row=schorkewarw-2` opens that row: a session note ("I stopped
  // there"), a link from a report, or a scripted screenshot.
  const selection = useSelection({
    param: 'row',
    keys: useMemo(() => visible.map((row) => row.id), [visible]),
    ready: worklist !== undefined,
    resolve: useCallback((id: string) => rows.find((row) => row.id === id)?.id, [rows]),
  });
  const selected = rows.find((row) => row.id === selection.selected) ?? null;
  const save = useSave(resource.update, visible, doneById, selection);
  const doneCount = rows.filter((row) => doneById.has(row.id)).length;

  return (
    <DevPanel
      className="curate-panel"
      title="Curation review"
      what="the worklist"
      needs={
        <>
          The curation view needs a worklist exported with <code>frasch curate export</code>.
        </>
      }
      resource={resource}
      header={
        <CurateFilters
          filter={filter}
          onChange={setFilter}
          kinds={worklist ? rowKinds(worklist) : []}
          results={worklist?.results ?? []}
          counts={{ open: rows.length - doneCount, done: doneCount, shown: visible.length }}
        />
      }
    >
      <CurateList
        rows={visible}
        doneById={doneById}
        selectedId={selection.selected}
        onSelect={selection.select}
        itemRef={selection.itemRef}
      />
      {selected && worklist && (
        // Keyed by row: everything typed or ticked for one row starts afresh on the next.
        <CurateDetail
          key={selected.id}
          row={selected}
          done={doneById.get(selected.id) ?? null}
          bbox={worklist.bbox}
          classKeys={worklist.class_keys}
          settlementPlaces={worklist.settlement_places}
          canBePolygon={worklist.polygon_kinds.includes(selected.kind)}
          map={map}
          onSave={save}
        />
      )}
    </DevPanel>
  );
}

/**
 * Stores a decision, shows the row as decided at once, and moves on to the
 * next open row of the list as shown — but only from where the user still
 * is: they may have gone to another row while the save was on its way.
 */
function useSave(
  update: (change: (data: LoadedWorklist) => LoadedWorklist) => void,
  visible: CurateRow[],
  doneById: Map<string, PatchEntry>,
  { selected, select }: Pick<Selection, 'selected' | 'select'>,
) {
  // For a save that resolves later: has the user moved on meanwhile?
  const selectedNow = useRef(selected);
  useEffect(() => {
    selectedNow.current = selected;
  }, [selected]);

  return useCallback(
    async (row: CurateRow, decision: Decision) => {
      const { id, line, kind, name } = row;
      const stored = await postPatchEntry({ id, line, kind, name, de: row.name_de, ...decision });
      // Mirror the appended line locally so the list turns "done" at once.
      update((loaded) => ({ ...loaded, entries: [...loaded.entries, stored] }));
      if (decision.action === 'clear' || selectedNow.current !== id) return;
      const at = visible.findIndex((other) => other.id === id);
      const next = visible.slice(at + 1).find((other) => !doneById.has(other.id));
      if (next) select(next.id);
    },
    [update, visible, doneById, select],
  );
}
