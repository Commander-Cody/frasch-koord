/**
 * The selected row of the curation view and every way to decide it: pick a
 * candidate or a lookup result (or several, ticked), an OSM reference by
 * hand, a local reference at a position set on the map, or skip it.
 *
 * Everything typed or ticked here belongs to this one row: CuratePanel keys
 * the component by the row id, so moving to another row starts afresh.
 */
import { useCallback, useState } from 'react';
import type { RefObject } from 'react';

import type { MapViewHandle } from '../components/Map';
import { primary } from '../names';
import { candidateColor, hasPoint, type Position, usePositionPin, useRowPins } from './curateMapLayers';
import { isValidSlug, type Decision, type PatchEntry } from './curatePatch';
import { parseRefs, slugify, type Bbox, type CurateCandidate, type CurateRow } from './curateWorklist';
import CurateLookup from './CurateLookup';
import { useOsmLookup } from './osmLookup';
import RefItem from './RefItem';

/** How many ticked refs the selection summary spells out ("select all" can tick hundreds). */
const MAX_LISTED_REFS = 12;

/** Kinds whose curation row can carry an area instead of a bare point. */
const POLYGON_KINDS = new Set(['koog', 'harde', 'landscape', 'island', 'hallig', 'sand']);

export interface CurateDetailProps {
  row: CurateRow;
  /** The row's current decision, if it has one. */
  done: PatchEntry | null;
  /** The worklist's bbox, which the lookups search in. */
  bbox: Bbox;
  mapRef: RefObject<MapViewHandle | null>;
  /** Stores a decision; rejects with a message fit for the panel. */
  onSave: (row: CurateRow, decision: Decision) => Promise<void>;
}

/** An OSM object ticked for a multi-object pick. */
interface CheckedRef {
  ref: string;
  wikidata?: string;
}

function checkedRef(ref: string, wikidata?: string): CheckedRef {
  return { ref, ...(wikidata ? { wikidata } : {}) };
}

function osmDecision(ref: string, wikidata?: string): Decision {
  return { action: 'osm', osm: ref, ...(wikidata ? { wikidata } : {}) };
}

/** Every decision but `clear` takes the note along. */
function withNote(decision: Decision, note: string): Decision {
  const trimmed = note.trim();
  return decision.action !== 'clear' && trimmed ? { ...decision, note: trimmed } : decision;
}

/**
 * The refs ticked for a multi-object pick, in tick order (= order in the
 * cell). The functions are stable, so the map's pin effects can take them
 * without re-running — which would re-fit the map.
 */
function useCheckedRefs() {
  const [checked, setChecked] = useState<CheckedRef[]>([]);
  const toggle = useCallback((ref: string, wikidata?: string) => {
    setChecked((prev) =>
      prev.some((item) => item.ref === ref)
        ? prev.filter((item) => item.ref !== ref)
        : [...prev, checkedRef(ref, wikidata)],
    );
  }, []);
  /** Ticks every given candidate, keeping what is already ticked (and its order). */
  const checkAll = useCallback((candidates: CurateCandidate[]) => {
    setChecked((prev) => {
      const have = new Set(prev.map((item) => item.ref));
      const added = candidates
        .filter((candidate) => !have.has(candidate.ref))
        .map(({ ref, wikidata }) => checkedRef(ref, wikidata));
      return added.length > 0 ? [...prev, ...added] : prev;
    });
  }, []);
  const clear = useCallback(() => setChecked([]), []);
  return { checked, toggle, checkAll, clear };
}

export default function CurateDetail({ row, done, bbox, mapRef, onSave }: CurateDetailProps) {
  const de = primary(row.de);
  const lookup = useOsmLookup(bbox, de || primary(row.da) || row.name);
  const { checked, toggle, checkAll, clear } = useCheckedRefs();
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [postError, setPostError] = useState<string | null>(null);

  useRowPins({ mapRef, row, bbox, lookupResults: lookup.results, checked, onActivate: setActiveRef, onToggle: toggle });

  const decide = (decision: Decision) => {
    setPostError(null);
    onSave(row, withNote(decision, note)).catch((err: unknown) =>
      setPostError(err instanceof Error ? err.message : String(err)),
    );
  };
  const pick = (ref: string, wikidata?: string) => decide(osmDecision(ref, wikidata));
  const flyTo = (lon: number, lat: number) =>
    mapRef.current?.getMap()?.flyTo({ center: [lon, lat], zoom: 14, essential: true });
  const isChecked = (ref: string) => checked.some((item) => item.ref === ref);

  return (
    <section className="curate-detail">
      <h2 className="curate-detail-title">
        {row.name}
        <span className="curate-detail-line">
          {row.id} · places.csv line {row.line}
        </span>
      </h2>
      <RowFacts row={row} />
      {done && (
        <p className="curate-done-note">
          already decided: {done.action}
          {done.osm ? ` ${done.osm}` : ''}
          {done.slug ? ` local/${done.slug}` : ''}
        </p>
      )}

      <Candidates
        candidates={row.candidates}
        activeRef={activeRef}
        isChecked={isChecked}
        onToggle={toggle}
        onCheckAll={checkAll}
        onShow={(candidate) => {
          setActiveRef(candidate.ref);
          if (hasPoint(candidate)) flyTo(candidate.lon, candidate.lat);
        }}
        onPick={pick}
      />
      <CurateLookup
        lookup={lookup}
        isChecked={isChecked}
        onToggle={toggle}
        onShow={(result) => flyTo(result.lon, result.lat)}
        onPick={pick}
      />
      {checked.length > 0 && <CheckedPick checked={checked} onClear={clear} decide={decide} />}
      <ManualRef decide={decide} />
      <LocalRef row={row} initialSlug={slugify(de || row.name)} mapRef={mapRef} decide={decide} />

      <h3 className="dev-panel-section">Note / skip</h3>
      <input
        className="dev-panel-input"
        placeholder="note (optional, any action)"
        value={note}
        aria-label="note"
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="curate-row">
        <button type="button" onClick={() => decide({ action: 'skip' })}>
          Skip
        </button>
        {done && (
          <button type="button" onClick={() => decide({ action: 'clear' })}>
            Clear
          </button>
        )}
      </div>
      {postError && <p className="dev-panel-error">could not save: {postError}</p>}
    </section>
  );
}

/** What the worklist knows about the row. */
function RowFacts({ row }: { row: CurateRow }) {
  const facts: [string, string][] = [
    ...Object.entries(row.names ?? {}),
    ['de', row.de],
    ['da', row.da],
    ['hint', row.hint],
    ['note', row.note],
    ['kind', `${row.kind} · ${row.result}`],
    ['why', row.why],
  ];
  return (
    <dl className="dev-panel-facts">
      {facts
        .filter(([, value]) => value)
        .map(([term, value]) => (
          <div key={term}>
            <dt>{term}</dt>
            <dd>{value}</dd>
          </div>
        ))}
    </dl>
  );
}

interface CandidatesProps {
  candidates: CurateCandidate[];
  activeRef: string | null;
  isChecked: (ref: string) => boolean;
  onToggle: (ref: string, wikidata?: string) => void;
  onCheckAll: (candidates: CurateCandidate[]) => void;
  onShow: (candidate: CurateCandidate) => void;
  onPick: (ref: string, wikidata?: string) => void;
}

/** The matcher's candidates, numbered and coloured like their pins. */
function Candidates({ candidates, activeRef, isChecked, onToggle, onCheckAll, onShow, onPick }: CandidatesProps) {
  const inSh = candidates.filter((candidate) => candidate.in_sh);
  const hasInShFlag = candidates.some((candidate) => candidate.in_sh !== undefined);
  return (
    <>
      <h3 className="dev-panel-section">Candidates ({candidates.length})</h3>
      {candidates.length === 0 && <p className="dev-panel-hint">no candidates — use the lookups below</p>}
      {candidates.length > 1 && (
        <div className="curate-row">
          <button type="button" onClick={() => onCheckAll(candidates)}>
            select all
          </button>
          <button
            type="button"
            disabled={inSh.length === 0}
            title={hasInShFlag ? undefined : 'curate.json predates the in_sh flag — re-run names/curate.py export'}
            onClick={() => onCheckAll(inSh)}
          >
            select all in Schleswig-Holstein ({inSh.length})
          </button>
        </div>
      )}
      <ul className="curate-candidates">
        {candidates.map((candidate, i) => (
          <RefItem
            key={candidate.ref}
            osmRef={candidate.ref}
            number={i + 1}
            color={candidateColor(candidate)}
            name={candidate.name}
            meta={candidateMeta(candidate)}
            active={candidate.ref === activeRef}
            checked={isChecked(candidate.ref)}
            onToggle={() => onToggle(candidate.ref, candidate.wikidata)}
            onShow={() => onShow(candidate)}
            onPick={() => onPick(candidate.ref, candidate.wikidata)}
          />
        ))}
      </ul>
    </>
  );
}

function candidateMeta(candidate: CurateCandidate): string {
  return [
    candidate.class,
    typeof candidate.km === 'number' ? ` · ${candidate.km} km` : '',
    candidate.tags ? ` · ${candidate.tags}` : '',
    candidate.wikidata ? ` · ${candidate.wikidata}` : '',
  ].join('');
}

interface CheckedPickProps {
  checked: CheckedRef[];
  onClear: () => void;
  decide: (decision: Decision) => void;
}

/** The ticked objects, picked together as one `osm` cell. */
function CheckedPick({ checked, onClear, decide }: CheckedPickProps) {
  // Only an unambiguous wikidata id goes along; `apply` cannot choose between two.
  const qids = [...new Set(checked.flatMap((item) => (item.wikidata ? [item.wikidata] : [])))];
  const refs = checked.map((item) => item.ref);
  const pick = () => decide(osmDecision(refs.join('; '), qids.length === 1 ? qids[0] : undefined));
  return (
    <div className="curate-multi">
      <span className="dev-panel-mono curate-mono">
        {checked.length} selected: {refs.slice(0, MAX_LISTED_REFS).join('; ')}
        {checked.length > MAX_LISTED_REFS ? '; …' : ''}
      </span>
      {qids.length > 1 && <p className="dev-panel-hint">different wikidata ids ({qids.join(', ')}) — none saved</p>}
      <div className="curate-row">
        <button type="button" onClick={pick}>
          Pick {checked.length} selected
        </button>
        <button type="button" onClick={onClear}>
          clear selection
        </button>
      </div>
    </div>
  );
}

/** An OSM reference typed or pasted in. */
function ManualRef({ decide }: { decide: (decision: Decision) => void }) {
  const [text, setText] = useState('');
  const refs = parseRefs(text);
  return (
    <>
      <h3 className="dev-panel-section">OSM reference by hand</h3>
      <input
        className="dev-panel-input"
        placeholder="way/177387348; node/123 or an openstreetmap.org URL"
        value={text}
        aria-label="osm reference"
        onChange={(event) => setText(event.target.value)}
      />
      <div className="curate-row">
        <button type="button" disabled={!refs} onClick={() => refs && decide(osmDecision(refs.join('; ')))}>
          Pick reference
        </button>
        {text.trim() && !refs && <span className="dev-panel-error">node/way/relation id or OSM URL expected</span>}
      </div>
    </>
  );
}

interface LocalRefProps {
  row: CurateRow;
  initialSlug: string;
  mapRef: RefObject<MapViewHandle | null>;
  decide: (decision: Decision) => void;
}

/** A place OSM does not have: a slug and a position set on the map. */
function LocalRef({ row, initialSlug, mapRef, decide }: LocalRefProps) {
  const [slug, setSlug] = useState(initialSlug);
  const [position, setPosition] = useState<Position | null>(null);
  const [picking, setPicking] = useState(false);
  const [polygonKm2, setPolygonKm2] = useState('');
  usePositionPin({ mapRef, position, setPosition, picking, setPicking });

  const polygonRelevant = POLYGON_KINDS.has(row.kind);
  const save = (at: Position) =>
    decide({
      action: 'local',
      slug,
      lat: Number(at.lat.toFixed(6)),
      lon: Number(at.lon.toFixed(6)),
      ...(polygonRelevant && polygonKm2.trim() ? { polygon_km2: Number(polygonKm2) } : {}),
    });

  return (
    <>
      <h3 className="dev-panel-section">Local reference (place OSM does not have)</h3>
      <input
        className="dev-panel-input"
        value={slug}
        aria-label="slug"
        onChange={(event) => setSlug(event.target.value)}
      />
      {!isValidSlug(slug) && <p className="dev-panel-error">slug must look like `toftem-emmelsbuell`</p>}
      <div className="curate-row">
        <button type="button" className={picking ? 'is-armed' : undefined} onClick={() => setPicking(!picking)}>
          {picking ? 'click the map…' : 'set position on map'}
        </button>
        <span className="dev-panel-mono curate-mono">
          {position ? `${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}` : 'no position'}
        </span>
      </div>
      {polygonRelevant && (
        <input
          className="dev-panel-input"
          type="number"
          min="0"
          step="0.1"
          placeholder="polygon_km2 (optional area label)"
          aria-label="polygon_km2"
          value={polygonKm2}
          onChange={(event) => setPolygonKm2(event.target.value)}
        />
      )}
      <button type="button" disabled={!isValidSlug(slug) || !position} onClick={() => position && save(position)}>
        Save local
      </button>
    </>
  );
}
