/**
 * Curation review view (`?curate`, dev only, English-only on purpose — this is
 * a tool for the name-list owner, not part of the public map).
 *
 * It shows the rows `frasch curate export` could not decide (`ambiguous`) or
 * could not find at all (`not_found`), drops the candidates on the map as
 * numbered pins, and writes every pick to `names/work/curate-patch.jsonl`
 * through the dev-server endpoints in `web/vite-plugins/curate.ts`.
 * `frasch curate apply` later folds that patch into places.csv/curation.csv.
 *
 * One place can be several OSM objects (a node and its area, a landscape made
 * of relations): tick candidates or lookup results — or shift-click their pins
 * — and "Pick selected" saves them as one `osm` cell, `a; b; c`.
 *
 * This component holds the worklist, the filter and the selection; the list,
 * the selected row's detail with its lookups, and the map pins are their own
 * modules (CurateList, CurateDetail, CurateLookup, curateMapLayers).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';

import type { MapViewHandle } from '../components/Map';
import { replaceQueryParams } from '../queryParams';
import CurateDetail from './CurateDetail';
import CurateFilters from './CurateFilters';
import CurateList from './CurateList';
import { decidedRows, postPatchEntry, type Decision, type PatchEntry } from './curatePatch';
import {
  fetchWorklist,
  filterRows,
  NO_FILTER,
  rowKinds,
  type CurateRow,
  type CurateWorklist,
} from './curateWorklist';
import DevPanel from './DevPanel';
import { useDeepLinkParam } from './useDeepLinkParam';
import { useListNavigation } from './useListNavigation';
import './CuratePanel.css';

export interface CuratePanelProps {
  /** The live map, for pins and the "set position on map" click. */
  mapRef: RefObject<MapViewHandle | null>;
}

export default function CuratePanel({ mapRef }: CuratePanelProps) {
  const [worklist, setWorklist] = useState<CurateWorklist | null>(null);
  const [entries, setEntries] = useState<PatchEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // For a save that resolves later (has the user moved on meanwhile?) and for
  // the deep link (has the user chosen a row before it could open?).
  const selectedIdNow = useRef<string | null>(null);
  const [filter, setFilter] = useState(NO_FILTER);

  useEffect(() => {
    let cancelled = false;
    fetchWorklist()
      .then((loaded) => {
        if (cancelled) return;
        setWorklist(loaded.worklist);
        setEntries(loaded.entries);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* ------------------------------------------------------------ derived */

  const doneById = useMemo(() => decidedRows(entries), [entries]);
  // Memoised so every derivation below (and the lint's dependency analysis)
  // sees one stable array rather than a fresh `[]` on each render.
  const rows = useMemo(() => worklist?.rows ?? [], [worklist]);
  const kinds = useMemo(() => (worklist ? rowKinds(worklist) : []), [worklist]);
  const visible = useMemo(
    () => filterRows(rows, filter, (id) => doneById.has(id)),
    [rows, filter, doneById],
  );
  const visibleIds = useMemo(() => visible.map((row) => row.id), [visible]);
  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );
  const doneCount = useMemo(
    () => rows.filter((row) => doneById.has(row.id)).length,
    [rows, doneById],
  );

  /* --------------------------------------------------------- navigation */

  const goTo = useCallback((id: string) => {
    selectedIdNow.current = id;
    setSelectedId(id);
    replaceQueryParams({ row: id });
  }, []);

  // `?curate&row=schorkewarw-2` opens that row: a session note ("I stopped
  // there"), a link from a report, or a scripted screenshot. `goTo` writes the
  // current row back so reloading keeps the place.
  const openLinkedRow = useCallback(
    (id: string) => {
      if (rows.some((row) => row.id === id)) goTo(id);
    },
    [rows, goTo],
  );
  const hasSelection = useCallback(() => selectedIdNow.current !== null, []);
  useDeepLinkParam('row', rows.length > 0, openLinkedRow, hasSelection);
  useListNavigation(visibleIds, selectedId, goTo);

  /* ------------------------------------------------------------- saving */

  /** On to the next open row after `fromId`, in the list as shown. */
  const advance = useCallback(
    (fromId: string) => {
      const at = visible.findIndex((row) => row.id === fromId);
      const next = visible.slice(at + 1).find((row) => !doneById.has(row.id));
      if (next) goTo(next.id);
    },
    [visible, doneById, goTo],
  );

  const save = useCallback(
    async (row: CurateRow, decision: Decision) => {
      const { id, line, kind, name } = row;
      const entry: PatchEntry = { id, line, kind, name, de: row.name_de, ...decision };
      const stored = await postPatchEntry(entry);
      // Mirror the appended line locally so the list turns "done" at once.
      setEntries((prev) => [...prev, stored]);
      // Only from where the user still is: they may have gone to another row
      // while the save was on its way.
      if (entry.action !== 'clear' && selectedIdNow.current === row.id) advance(row.id);
    },
    [advance],
  );

  /* ------------------------------------------------------------- render */

  return (
    <DevPanel
      className="curate-panel"
      title="Curation review"
      what="the worklist"
      needs={
        <>
          The curation view needs the Vite dev server (<code>npm run dev</code>) and a worklist
          exported with <code>frasch curate export</code>.
        </>
      }
      loaded={worklist !== null}
      error={loadError}
      header={
        <CurateFilters
          filter={filter}
          onChange={setFilter}
          kinds={kinds}
          results={worklist?.results ?? []}
          counts={{ open: rows.length - doneCount, done: doneCount, shown: visible.length }}
        />
      }
    >
      <CurateList rows={visible} doneById={doneById} selectedId={selectedId} onSelect={goTo} />
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
          mapRef={mapRef}
          onSave={save}
        />
      )}
    </DevPanel>
  );
}
