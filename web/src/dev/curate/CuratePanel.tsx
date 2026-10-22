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
 * It also creates places the list does not have yet (#113): "New place", or
 * a click on the label of an OSM object no row names, opens a form whose
 * `create` goes into the patch under a provisional key. Until apply such a
 * place is listed apart, marked new, and is decided like a row — or edited,
 * or discarded.
 *
 * This component holds the worklist, the filter and the selection; the list,
 * the selected row's detail with its lookups, the form of a new place and
 * the map's pins are their own modules (CurateList, CurateDetail,
 * CurateLookup, NewPlaceForm with usePlaceForm, LabelOffer with labelClicks,
 * pins, hintCircle).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Map as MapLibreMap, MapGeoJSONFeature } from 'maplibre-gl';

import DevPanel from '../shell/DevPanel';
import { useDevResource } from '../shell/useDevResource';
import { useSelection, type Selection } from '../shell/useSelection';
import CurateDetail from './CurateDetail';
import CurateFilters from './CurateFilters';
import CurateList from './CurateList';
import { clickedLabel, useLabelClicks, type ClickedLabel } from './labelClicks';
import LabelOffer from './LabelOffer';
import NewPlaceForm from './NewPlaceForm';
import { placeRow } from './newPlaces';
import {
  createdPlaces,
  decidedRows,
  storeEntry,
  type Decision,
  type PatchEntry,
  type UpdateLoaded,
} from './patch';
import { comparedPlaces, editForm, labelForm, newPlaceForm, usePlaceForm } from './usePlaceForm';
import {
  filterRows,
  loadWorklist,
  NO_FILTER,
  rowKinds,
  type ListRow,
  type LoadedWorklist,
  type RowFilter,
} from './worklist';
import './CuratePanel.css';

export default function CuratePanel({ map }: { map: MapLibreMap }) {
  const resource = useDevResource(loadWorklist);
  const worklist = resource.data?.worklist;
  const [filter, setFilter] = useState(NO_FILTER);
  const { doneById, created, rows, visible, visibleNew, allRows } = useListRows(
    resource.data,
    filter,
  );

  // `?curate&row=schorkewarw-2` opens that row: a session note ("I stopped
  // there"), a link from a report, or a scripted screenshot. A created
  // place opens by its key until apply.
  const selection = useSelection({
    param: 'row',
    keys: useMemo(() => [...visibleNew, ...visible].map((row) => row.id), [visibleNew, visible]),
    ready: worklist !== undefined,
    resolve: useCallback((id: string) => allRows.find((row) => row.id === id)?.id, [allRows]),
  });
  const selected = allRows.find((row) => row.id === selection.selected) ?? null;
  const save = useSave(resource.update, visible, doneById, selection);
  const doneCount = rows.filter((row) => doneById.has(row.id)).length;

  // Whether the next map click sets the selected row's position: then it is
  // no label click. The detail disarms it when it goes (CurateDetail).
  const [picking, setPicking] = useState(false);
  const [label, setLabel] = useLabelOffer(map, picking);
  const places = usePlaceForm(resource.update, selection);
  // A row opened from a list is what the user turns to: the form gives way.
  const openRow = (id: string) => {
    places.close();
    selection.select(id);
  };
  const selectedPlace = created.find((place) => place.key === selected?.id);
  const listProps = {
    doneById,
    selectedId: selection.selected,
    onSelect: openRow,
    itemRef: selection.itemRef,
  };

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
          kinds={worklist ? rowKinds(worklist.kind_order, allRows) : []}
          results={worklist?.results ?? []}
          counts={{ open: rows.length - doneCount, done: doneCount, shown: visible.length }}
        />
      }
    >
      <div className="curate-row">
        <button type="button" onClick={() => places.open(newPlaceForm())}>
          New place
        </button>
      </div>
      {label && (
        <LabelOffer
          label={label}
          onCreate={() => {
            places.open(labelForm(label, worklist?.settlement_places ?? []));
            setLabel(null);
          }}
          onDismiss={() => setLabel(null)}
        />
      )}
      {visibleNew.length > 0 && (
        <>
          <h3 className="dev-panel-section">New places ({visibleNew.length})</h3>
          <CurateList
            rows={visibleNew}
            label={`New places (${visibleNew.length})`}
            {...listProps}
          />
        </>
      )}
      <CurateList rows={visible} label="worklist" {...listProps} />
      {places.form && worklist ? (
        <>
          <NewPlaceForm
            key={places.form.key}
            title={places.form.title}
            kinds={worklist.kind_order}
            columns={worklist.all_name_columns}
            places={comparedPlaces(worklist.places, created, places.form.key)}
            initial={places.form.initial}
            saving={places.saving}
            onSave={(draft) => places.save(draft, worklist.naming_columns)}
            onCancel={places.close}
          />
        </>
      ) : (
        selected &&
        worklist && (
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
            picking={picking}
            setPicking={setPicking}
            onSave={save}
            {...(selectedPlace && {
              onEdit: () => places.open(editForm(selectedPlace)),
              onDiscard: () => places.discard(selectedPlace.key),
            })}
          />
        )
      )}
      {places.error && <p className="dev-panel-error">could not save: {places.error}</p>}
    </DevPanel>
  );
}

const NONE_DONE = () => false;

/**
 * The rows of the panel: the worklist's and the created places', each with
 * those the filter lets through, and which are decided. Memoised so every
 * derivation (and the lint's dependency analysis) sees stable arrays rather
 * than a fresh `[]` on each render.
 */
function useListRows(data: LoadedWorklist | null, filter: RowFilter) {
  const worklist = data?.worklist;
  const entries = data?.entries;
  const doneById = useMemo(() => decidedRows(entries ?? []), [entries]);
  const created = useMemo(() => createdPlaces(entries ?? []), [entries]);
  const rows = useMemo(() => worklist?.rows ?? [], [worklist]);
  const newRows = useMemo(
    () =>
      created.map((place) =>
        placeRow(place, worklist?.frisian_columns ?? [], worklist?.naming_columns ?? []),
      ),
    [created, worklist],
  );
  const visible = useMemo(
    () => filterRows(rows, filter, (id) => doneById.has(id)),
    [rows, filter, doneById],
  );
  // A created place stays listed, decided or not: it is not in places.csv yet.
  const visibleNew = useMemo(
    () => filterRows(newRows, { ...filter, result: 'all', hideDone: false }, NONE_DONE),
    [newRows, filter],
  );
  const allRows = useMemo<ListRow[]>(() => [...newRows, ...rows], [newRows, rows]);
  return { doneById, created, rows, visible, visibleNew, allRows };
}

/**
 * The label of an object the name list does not have that was clicked last,
 * while no click sets a position (`picking`); and a way to take it back.
 */
function useLabelOffer(map: MapLibreMap, picking: boolean) {
  const [label, setLabel] = useState<ClickedLabel | null>(null);
  useLabelClicks(map, (feature: MapGeoJSONFeature) => {
    if (picking) return;
    const offer = clickedLabel(feature);
    if (offer) setLabel(offer);
  });
  return [label, setLabel] as const;
}

/**
 * Stores a decision, shows the row as decided at once, and moves on to the
 * next open row of the worklist as shown — but only from where the user still
 * is: they may have gone to another row while the save was on its way. A
 * created place is not in the worklist: there it stays.
 */
function useSave(
  update: UpdateLoaded,
  visible: ListRow[],
  doneById: Map<string, PatchEntry>,
  { selected, select }: Pick<Selection, 'selected' | 'select'>,
) {
  // For a save that resolves later: has the user moved on meanwhile?
  const selectedNow = useRef(selected);
  useEffect(() => {
    selectedNow.current = selected;
  }, [selected]);

  return useCallback(
    async (row: ListRow, decision: Decision) => {
      const { id, line, kind, name } = row;
      // a created place has no line yet
      const where = row.result === 'new' ? {} : { line };
      await storeEntry(update, { id, ...where, kind, name, de: row.name_de, ...decision });
      if (decision.action === 'clear' || selectedNow.current !== id) return;
      const at = visible.findIndex((other) => other.id === id);
      if (at < 0) return;
      const next = visible.slice(at + 1).find((other) => !doneById.has(other.id));
      if (next) select(next.id);
    },
    [update, visible, doneById, select],
  );
}
