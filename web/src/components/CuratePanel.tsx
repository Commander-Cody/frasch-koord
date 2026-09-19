/**
 * Curation review view (`?curate`, dev only, English-only on purpose — this is
 * a tool for the name-list owner, not part of the public map).
 *
 * It shows the rows `names/curate.py export` could not decide (`ambiguous`) or
 * could not find at all (`not_found`), drops the candidates on the map as
 * numbered pins, and writes every pick to `names/work/curate-patch.jsonl`
 * through the dev-server endpoints in `web/vite-plugins/curate.ts`.
 * `names/curate.py apply` later folds that patch into places.csv/curation.csv.
 *
 * One place can be several OSM objects (a node and its area, a landscape made
 * of relations): tick candidates or lookup results — or shift-click their pins
 * — and "Pick selected" saves them as one `osm` cell, `a; b; c`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { LngLatBounds, Marker } from 'maplibre-gl';
import type { MapMouseEvent, Map as MapLibreMap } from 'maplibre-gl';

import type { MapViewHandle } from './Map';
import './CuratePanel.css';

/* ------------------------------------------------------------------ types */

/** One candidate of a worklist row (see the shared contract, `candidates[]`). */
export interface CurateCandidate {
  /** "node/123" | "way/123" | "relation/123". */
  ref: string;
  name: string;
  class: string;
  /** Distance to the hint point in km, as computed by match.py. */
  km: number;
  /** Absent/null when candidates.jsonl had no position for the object. */
  lon?: number | null;
  lat?: number | null;
  /** Decisive tags as one string, e.g. "place=hamlet". */
  tags?: string;
  wikidata?: string;
}

/** One row of `names/work/curate.json`. */
export interface CurateRow {
  /** Physical line in places.csv (header = 1); the row's identity together with kind/name/de. */
  line: number;
  kind: string;
  result: 'ambiguous' | 'not_found';
  /** The Frisian name match.py worked with. */
  name: string;
  /** Every non-empty name column, raw cell text, keyed by column name. */
  names: Record<string, string>;
  de: string;
  da: string;
  hint: string;
  note: string;
  /** Why the matcher gave up (matches.csv `note`). */
  why: string;
  /** [lon, lat, radius_km] of the location hint, or null. */
  hint_point: [number, number, number] | null;
  candidates: CurateCandidate[];
}

/** `names/work/curate.json` as a whole. */
export interface CurateWorklist {
  generated: string;
  /** lon_min, lat_min, lon_max, lat_max. */
  bbox: [number, number, number, number];
  kind_order: string[];
  rows: CurateRow[];
}

/** One line of `names/work/curate-patch.jsonl`. */
export interface PatchEntry {
  line: number;
  kind: string;
  name: string;
  de: string;
  action: 'osm' | 'local' | 'skip' | 'clear';
  osm?: string;
  wikidata?: string;
  slug?: string;
  lat?: number;
  lon?: number;
  polygon_km2?: number;
  note?: string;
  at?: string;
}

/** A Nominatim or Overpass hit, normalised to what the pin/pick code needs. */
interface LookupResult {
  ref: string;
  name: string;
  /** Short type description, e.g. "place=hamlet" or "hamlet". */
  what: string;
  lon: number;
  lat: number;
  tags: string;
  wikidata?: string;
}

export interface CuratePanelProps {
  /** The live map, for pins and the "set position on map" click. */
  mapRef: RefObject<MapViewHandle | null>;
}

/* -------------------------------------------------------------- constants */

/** Pin colours. Kept to three groups on purpose — this is a working tool. */
const COLOR_SETTLEMENT = '#d81b60';
const COLOR_AREA = '#1e88e5';
const COLOR_OTHER = '#6d4c41';
const COLOR_HINT = '#00897b';
const COLOR_LOOKUP = '#f9a825';

/** OSM/OpenMapTiles classes that mean "a place where people live". */
const SETTLEMENT_CLASSES = new Set([
  'city',
  'town',
  'village',
  'hamlet',
  'suburb',
  'neighbourhood',
  'isolated_dwelling',
  'farm',
  'locality',
  'allotments',
]);

/** Kinds whose curation row can carry an area instead of a bare point. */
const POLYGON_KINDS = new Set(['koog', 'harde', 'landscape', 'island', 'hallig', 'sand']);

/** The panel covers the left edge, so pins must be fitted to the right of it. */
const FIT_PADDING = { left: 460, top: 60, right: 60, bottom: 60 };
const FIT_MAX_ZOOM = 14;

/** Source/layer ids of the hint-radius circle; removed again on every change. */
const HINT_SOURCE = 'curate-hint-circle';
const HINT_FILL = 'curate-hint-circle-fill';
const HINT_LINE = 'curate-hint-circle-line';

/* ---------------------------------------------------------------- helpers */

/** The `de`/`da` cells may hold several variants separated by ';'. */
function primary(cell: string): string {
  return (cell || '').split(';')[0].trim();
}

/** Non-ASCII letters this project actually meets, spelled out as the slug wants them. */
const SLUG_CHARS: Record<string, string> = {
  ä: 'ae',
  ö: 'oe',
  ü: 'ue',
  ß: 'ss',
  å: 'aa',
  ø: 'oe',
  æ: 'ae',
};

/** places.csv/curation.csv slug shape: `[a-z0-9]+(-[a-z0-9]+)*`. */
function slugify(text: string): string {
  let out = '';
  for (const ch of (text || '').toLowerCase()) out += SLUG_CHARS[ch] ?? ch;
  // Anything else accented (é, ô, …) loses its mark rather than a whole letter.
  out = out.normalize('NFD').replace(/[̀-ͯ]/g, '');
  return out.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function isValidSlug(slug: string): boolean {
  return /^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug);
}

/** Escapes a user's query for the Overpass `~"…"` regex. */
function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Accepts `way/123`, several joined by ';', and pasted openstreetmap.org URLs
 * (`https://www.openstreetmap.org/way/177387348`) — the two things one ends up
 * with after looking something up in a browser tab.
 */
function parseRefs(text: string): string[] | null {
  const parts = (text || '')
    .split(/[;\n,]+/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) return null;
  const refs: string[] = [];
  for (const part of parts) {
    const url = part.match(/openstreetmap\.org\/(node|way|relation)\/(\d+)/i);
    const plain = part.match(/^(node|way|relation)\/(\d+)$/i);
    const hit = url ?? plain;
    if (!hit) return null;
    refs.push(`${hit[1].toLowerCase()}/${hit[2]}`);
  }
  return refs;
}

function candidateColor(candidate: CurateCandidate): string {
  if (SETTLEMENT_CLASSES.has(candidate.class)) return COLOR_SETTLEMENT;
  if (candidate.ref.startsWith('way/') || candidate.ref.startsWith('relation/')) return COLOR_AREA;
  return COLOR_OTHER;
}

/** True when the candidate carries a usable position. */
function hasPoint(candidate: CurateCandidate): candidate is CurateCandidate & { lon: number; lat: number } {
  return typeof candidate.lon === 'number' && typeof candidate.lat === 'number';
}

/** A numbered dot as a marker element; MapLibre positions it, we only style it. */
function pinElement(label: string, color: string, title: string): HTMLElement {
  const el = document.createElement('div');
  el.className = 'curate-pin';
  el.style.background = color;
  el.textContent = label;
  el.title = title;
  return el;
}

/** Drops `el` from the ref -> pin map, leaving another pin under the same ref alone. */
function unregisterPin(pins: Map<string, HTMLElement>, el: HTMLElement): void {
  for (const [ref, pin] of pins) if (pin === el) pins.delete(ref);
}

/** Rough circle in degrees; good enough to show "the hint said within N km". */
function circleRing(lon: number, lat: number, radiusKm: number): [number, number][] {
  const ring: [number, number][] = [];
  const dLat = radiusKm / 111.32;
  const dLon = dLat / Math.max(0.1, Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= 48; i += 1) {
    const a = (i / 48) * 2 * Math.PI;
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return ring;
}

function removeHintCircle(map: MapLibreMap): void {
  for (const id of [HINT_FILL, HINT_LINE]) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  if (map.getSource(HINT_SOURCE)) map.removeSource(HINT_SOURCE);
}

function addHintCircle(map: MapLibreMap, lon: number, lat: number, radiusKm: number): void {
  removeHintCircle(map);
  map.addSource(HINT_SOURCE, {
    type: 'geojson',
    data: {
      type: 'Feature',
      properties: {},
      geometry: { type: 'Polygon', coordinates: [circleRing(lon, lat, radiusKm)] },
    },
  });
  map.addLayer({
    id: HINT_FILL,
    type: 'fill',
    source: HINT_SOURCE,
    paint: { 'fill-color': COLOR_HINT, 'fill-opacity': 0.1 },
  });
  map.addLayer({
    id: HINT_LINE,
    type: 'line',
    source: HINT_SOURCE,
    paint: { 'line-color': COLOR_HINT, 'line-opacity': 0.5, 'line-width': 1 },
  });
}

/** Tags worth seeing at a glance in a lookup result. */
const INTERESTING_TAGS = [
  'place',
  'highway',
  'natural',
  'landuse',
  'waterway',
  'boundary',
  'water',
  'man_made',
];

function tagSummary(tags: Record<string, string> | undefined): string {
  if (!tags) return '';
  return INTERESTING_TAGS.filter((k) => tags[k]).map((k) => `${k}=${tags[k]}`).join(' ');
}

/* -------------------------------------------------------------- component */

export default function CuratePanel({ mapRef }: CuratePanelProps) {
  const [worklist, setWorklist] = useState<CurateWorklist | null>(null);
  const [entries, setEntries] = useState<PatchEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);

  // Filters
  const [filterText, setFilterText] = useState('');
  const [filterKind, setFilterKind] = useState('');
  const [filterResult, setFilterResult] = useState<'all' | 'ambiguous' | 'not_found'>('all');
  const [hideDone, setHideDone] = useState(true);

  // Per-row form state, reset whenever the selection moves.
  const [activeRef, setActiveRef] = useState<string | null>(null);
  const [lookupQuery, setLookupQuery] = useState('');
  const [lookupResults, setLookupResults] = useState<LookupResult[]>([]);
  const [lookupSource, setLookupSource] = useState('');
  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [manualRef, setManualRef] = useState('');
  const [note, setNote] = useState('');
  const [slug, setSlug] = useState('');
  const [position, setPosition] = useState<{ lon: number; lat: number } | null>(null);
  const [pickingPosition, setPickingPosition] = useState(false);
  const [polygonKm2, setPolygonKm2] = useState('');
  const [postError, setPostError] = useState<string | null>(null);
  /** Refs ticked for a multi-object pick, in tick order (= order in the cell). */
  const [checkedRefs, setCheckedRefs] = useState<{ ref: string; wikidata?: string }[]>([]);

  const listRef = useRef<HTMLUListElement | null>(null);

  /* ---------------------------------------------------------- data load */

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [wlRes, patchRes] = await Promise.all([
          fetch('/__curate/worklist'),
          fetch('/__curate/patch'),
        ]);
        if (!wlRes.ok) {
          const body = (await wlRes.json().catch(() => null)) as { error?: string } | null;
          throw new Error(body?.error ?? `worklist: HTTP ${wlRes.status}`);
        }
        if (!patchRes.ok) throw new Error(`patch: HTTP ${patchRes.status}`);
        const wl = (await wlRes.json()) as CurateWorklist;
        const patch = (await patchRes.json()) as { entries: PatchEntry[] };
        if (cancelled) return;
        setWorklist(wl);
        setEntries(patch.entries ?? []);
        setLoadError(null);
      } catch (err: unknown) {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  /* ---------------------------------------------------- deep link (?line=) */

  // `?curate&line=40` opens that row: a session note ("I stopped at 40"),
  // a link from a report, or a scripted screenshot. The current row is
  // written back so reloading keeps the place.
  const initialLine = useRef<number | null>(
    (() => {
      const raw = new URLSearchParams(window.location.search).get('line');
      return raw && /^\d+$/.test(raw) ? Number(raw) : null;
    })(),
  );

  /* ------------------------------------------------------------ derived */

  /** Last entry per row; an `clear` entry withdraws the row's decision. */
  const doneByLine = useMemo(() => {
    const last = new Map<number, PatchEntry>();
    for (const entry of entries) last.set(entry.line, entry);
    const done = new Map<number, PatchEntry>();
    for (const [line, entry] of last) {
      if (entry.action !== 'clear') done.set(line, entry);
    }
    return done;
  }, [entries]);

  // Memoised so every derivation below (and the lint's dependency analysis)
  // sees one stable array rather than a fresh `[]` on each render.
  const rows = useMemo(() => worklist?.rows ?? [], [worklist]);

  const kinds = useMemo(() => {
    const order = worklist?.kind_order ?? [];
    const present = new Set(rows.map((r) => r.kind));
    const known = order.filter((k) => present.has(k));
    // Anything the exporter emitted but kind_order does not know about still
    // has to be reachable, so append the leftovers.
    const rest = [...present].filter((k) => !order.includes(k)).sort();
    return [...known, ...rest];
  }, [worklist, rows]);

  const visible = useMemo(() => {
    const needle = filterText.trim().toLowerCase();
    return rows.filter((row) => {
      if (filterKind && row.kind !== filterKind) return false;
      if (filterResult !== 'all' && row.result !== filterResult) return false;
      if (hideDone && doneByLine.has(row.line)) return false;
      if (!needle) return true;
      const haystack = [row.name, ...Object.values(row.names ?? {}), row.de, row.da, row.hint]
        .join(' ')
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [rows, filterKind, filterResult, hideDone, filterText, doneByLine]);

  const selected = useMemo(
    () => rows.find((row) => row.line === selectedLine) ?? null,
    [rows, selectedLine],
  );
  const selectedDone = selected ? (doneByLine.get(selected.line) ?? null) : null;

  const doneCount = useMemo(
    () => rows.filter((row) => doneByLine.has(row.line)).length,
    [rows, doneByLine],
  );

  /* ----------------------------------------------------------- map pins */

  /**
   * Stable (functional update) so the pin effects below can call it without
   * depending on the selection — re-running them would re-fit the map.
   */
  const toggleChecked = useCallback((ref: string, wikidata?: string) => {
    setCheckedRefs((prev) =>
      prev.some((item) => item.ref === ref)
        ? prev.filter((item) => item.ref !== ref)
        : [...prev, { ref, ...(wikidata ? { wikidata } : {}) }],
    );
  }, []);

  /** Pin element per ref, so ticking only toggles a class instead of re-adding markers. */
  const pinEls = useRef(new Map<string, HTMLElement>());

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !selected) return;

    const markers: Marker[] = [];
    const pins = pinEls.current;
    const bounds = new LngLatBounds();
    let any = false;

    selected.candidates.forEach((candidate, i) => {
      if (!hasPoint(candidate)) return;
      const el = pinElement(
        String(i + 1),
        candidateColor(candidate),
        `${candidate.ref} ${candidate.name} (${candidate.class})`,
      );
      el.addEventListener('click', (event) => {
        // Otherwise the click would also reach the map (position picking).
        event.stopPropagation();
        if (event.shiftKey) toggleChecked(candidate.ref, candidate.wikidata);
        else setActiveRef(candidate.ref);
      });
      pins.set(candidate.ref, el);
      markers.push(new Marker({ element: el }).setLngLat([candidate.lon, candidate.lat]).addTo(map));
      bounds.extend([candidate.lon, candidate.lat]);
      any = true;
    });

    const hint = selected.hint_point;
    if (hint) {
      const el = pinElement('H', COLOR_HINT, `location hint: ${selected.hint} (${hint[2]} km)`);
      el.classList.add('curate-pin-hint');
      markers.push(new Marker({ element: el }).setLngLat([hint[0], hint[1]]).addTo(map));
      bounds.extend([hint[0], hint[1]]);
      any = true;
    }

    let cancelled = false;
    const drawCircle = () => {
      if (cancelled || !hint) return;
      try {
        addHintCircle(map, hint[0], hint[1], hint[2]);
      } catch {
        // The circle is decoration; a style still in flux must not break pins.
      }
    };
    if (hint) {
      if (map.isStyleLoaded()) drawCircle();
      else map.once('load', drawCircle);
    }

    if (any) {
      map.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: FIT_MAX_ZOOM, duration: 600 });
    } else if (worklist) {
      // Nothing to look at: at least put the region on screen.
      const [w, s, e, n] = worklist.bbox;
      map.flyTo({ center: [(w + e) / 2, (s + n) / 2], zoom: 9, essential: true });
    }

    return () => {
      cancelled = true;
      map.off('load', drawCircle);
      for (const marker of markers) {
        unregisterPin(pins, marker.getElement());
        marker.remove();
      }
      try {
        removeHintCircle(map);
      } catch {
        // Style already torn down — nothing left to clean.
      }
    };
  }, [selected, worklist, mapRef, toggleChecked]);

  /* ------------------------------------------------------- lookup pins */

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || lookupResults.length === 0) return;
    const pins = pinEls.current;
    const markers = lookupResults.map((result, i) => {
      const el = pinElement(String(i + 1), COLOR_LOOKUP, `${result.ref} ${result.name}`);
      el.classList.add('curate-pin-lookup');
      el.addEventListener('click', (event) => {
        event.stopPropagation();
        if (event.shiftKey) toggleChecked(result.ref, result.wikidata);
        else map.flyTo({ center: [result.lon, result.lat], zoom: 14, essential: true });
      });
      // A ref that is also a candidate keeps its candidate pin in the map.
      if (!pins.has(result.ref)) pins.set(result.ref, el);
      return new Marker({ element: el }).setLngLat([result.lon, result.lat]).addTo(map);
    });
    return () => {
      for (const marker of markers) {
        unregisterPin(pins, marker.getElement());
        marker.remove();
      }
    };
  }, [lookupResults, mapRef, toggleChecked]);

  // Declared after the pin effects so their elements are registered first.
  useEffect(() => {
    const checked = new Set(checkedRefs.map((item) => item.ref));
    for (const [ref, el] of pinEls.current) {
      el.classList.toggle('curate-pin-checked', checked.has(ref));
    }
  }, [checkedRefs, selected, lookupResults]);

  /* ------------------------------------------------ position picking */

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !pickingPosition) return;
    const onClick = (event: MapMouseEvent) => {
      setPosition({ lon: event.lngLat.lng, lat: event.lngLat.lat });
      setPickingPosition(false);
    };
    map.on('click', onClick);
    map.getCanvas().style.cursor = 'crosshair';
    return () => {
      map.off('click', onClick);
      map.getCanvas().style.cursor = '';
    };
  }, [pickingPosition, mapRef]);

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !position) return;
    const marker = new Marker({ color: '#2e7d32', draggable: true })
      .setLngLat([position.lon, position.lat])
      .addTo(map);
    marker.on('dragend', () => {
      const at = marker.getLngLat();
      setPosition({ lon: at.lng, lat: at.lat });
    });
    return () => {
      marker.remove();
    };
  }, [position, mapRef]);

  /* -------------------------------------------------------- navigation */

  /**
   * Moving to another row is the one event that clears the per-row inputs
   * (lookup query, slug, position, note...). Doing it here rather than in an
   * effect on `selected` keeps it a single render and one obvious place.
   */
  const goTo = useCallback(
    (line: number) => {
      setSelectedLine(line);
      const params = new URLSearchParams(window.location.search);
      params.set('line', String(line));
      // Keep MapLibre's `#zoom/lat/lon` hash: it is part of the resume state.
      window.history.replaceState(
        window.history.state,
        '',
        `${window.location.pathname}?${params}${window.location.hash}`,
      );
      const row = rows.find((candidate) => candidate.line === line) ?? null;
      const de = row ? primary(row.de) : '';
      setLookupQuery(row ? de || primary(row.da) || row.name : '');
      setSlug(row ? slugify(de || row.name) : '');
      setActiveRef(null);
      setCheckedRefs([]);
      setLookupResults([]);
      setLookupSource('');
      setLookupError(null);
      setManualRef('');
      setNote('');
      setPosition(null);
      setPickingPosition(false);
      setPolygonKm2('');
      setPostError(null);
    },
    [rows],
  );

  // Once the worklist is there, honour the deep link (only once).
  useEffect(() => {
    const line = initialLine.current;
    if (line === null || rows.length === 0) return;
    initialLine.current = null;
    if (rows.some((row) => row.line === line)) goTo(line);
  }, [rows, goTo]);

  const move = useCallback(
    (delta: number) => {
      if (visible.length === 0) return;
      const at = visible.findIndex((row) => row.line === selectedLine);
      const next = at < 0 ? 0 : Math.min(visible.length - 1, Math.max(0, at + delta));
      goTo(visible[next].line);
    },
    [visible, selectedLine, goTo],
  );

  // Global so the keys work wherever the eye is, but never while typing.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) {
        return;
      }
      if (event.key === 'ArrowDown' || event.key === 'j') {
        event.preventDefault();
        move(1);
      } else if (event.key === 'ArrowUp' || event.key === 'k') {
        event.preventDefault();
        move(-1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [move]);

  // Keep the selected row in view when it moved by keyboard.
  useEffect(() => {
    listRef.current?.querySelector('.is-selected')?.scrollIntoView({ block: 'nearest' });
  }, [selectedLine]);

  /* ------------------------------------------------------------- saving */

  const advance = useCallback(
    (fromLine: number) => {
      const at = visible.findIndex((row) => row.line === fromLine);
      const next = visible.slice(at + 1).find((row) => !doneByLine.has(row.line));
      if (next) goTo(next.line);
    },
    [visible, doneByLine, goTo],
  );

  const send = useCallback(
    async (row: CurateRow, patch: Omit<PatchEntry, 'line' | 'kind' | 'name' | 'de'>) => {
      const entry: PatchEntry = {
        line: row.line,
        kind: row.kind,
        name: row.name,
        de: primary(row.de),
        ...patch,
      };
      setPostError(null);
      try {
        const res = await fetch('/__curate/patch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(entry),
        });
        const body = (await res.json().catch(() => null)) as
          | { ok?: boolean; entry?: PatchEntry; error?: string }
          | null;
        if (!res.ok || !body?.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
        // Mirror the appended line locally so the list turns "done" at once.
        setEntries((prev) => [...prev, body.entry ?? entry]);
        if (entry.action !== 'clear') advance(row.line);
      } catch (err: unknown) {
        setPostError(err instanceof Error ? err.message : String(err));
      }
    },
    [advance],
  );

  /* ------------------------------------------------------------ lookups */

  const runNominatim = useCallback(async () => {
    if (!worklist) return;
    const [w, s, e, n] = worklist.bbox;
    setLookupBusy(true);
    setLookupError(null);
    try {
      const url =
        'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=25&bounded=1' +
        `&viewbox=${w},${n},${e},${s}&q=${encodeURIComponent(lookupQuery)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Nominatim HTTP ${res.status} (rate limited?)`);
      const hits = (await res.json()) as {
        osm_type?: string;
        osm_id?: number;
        name?: string;
        display_name?: string;
        category?: string;
        type?: string;
        lat: string;
        lon: string;
      }[];
      const results: LookupResult[] = hits
        .filter((h) => h.osm_type && h.osm_id)
        .map((h) => ({
          ref: `${h.osm_type}/${h.osm_id}`,
          name: h.name || h.display_name || '',
          what: [h.category, h.type].filter(Boolean).join('='),
          lon: Number(h.lon),
          lat: Number(h.lat),
          tags: h.display_name ?? '',
        }));
      setLookupResults(results);
      setLookupSource(`Nominatim: ${results.length} result(s)`);
    } catch (err: unknown) {
      setLookupError(err instanceof Error ? err.message : String(err));
    } finally {
      setLookupBusy(false);
    }
  }, [worklist, lookupQuery]);

  const runOverpass = useCallback(async () => {
    if (!worklist) return;
    const [w, s, e, n] = worklist.bbox;
    setLookupBusy(true);
    setLookupError(null);
    try {
      const query =
        '[out:json][timeout:25];' +
        `nwr["name"~"${escapeRegex(lookupQuery)}",i](${s},${w},${n},${e});` +
        'out center tags 60;';
      const res = await fetch('https://overpass-api.de/api/interpreter', {
        method: 'POST',
        body: query,
      });
      if (!res.ok) throw new Error(`Overpass HTTP ${res.status} (busy/rate limited?)`);
      const body = (await res.json()) as {
        elements?: {
          type: string;
          id: number;
          lat?: number;
          lon?: number;
          center?: { lat: number; lon: number };
          tags?: Record<string, string>;
        }[];
      };
      const results: LookupResult[] = [];
      for (const element of body.elements ?? []) {
        // Ways/relations carry their position in `center` (`out center`).
        const lon = element.lon ?? element.center?.lon;
        const lat = element.lat ?? element.center?.lat;
        if (typeof lon !== 'number' || typeof lat !== 'number') continue;
        results.push({
          ref: `${element.type}/${element.id}`,
          name: element.tags?.name ?? '',
          what: tagSummary(element.tags) || element.type,
          lon,
          lat,
          tags: tagSummary(element.tags),
          wikidata: element.tags?.wikidata,
        });
      }
      setLookupResults(results);
      setLookupSource(`Overpass: ${results.length} result(s)`);
    } catch (err: unknown) {
      setLookupError(err instanceof Error ? err.message : String(err));
    } finally {
      setLookupBusy(false);
    }
  }, [worklist, lookupQuery]);

  /* -------------------------------------------------------------- render */

  if (loadError) {
    return (
      <div className="curate-panel">
        <h1 className="curate-title">Curation review</h1>
        <p className="curate-error">
          Could not load the worklist: {loadError}
        </p>
        <p className="curate-hint-text">
          The curation view needs the Vite dev server (<code>npm run dev</code>) and a worklist
          exported with <code>names/curate.py export</code>.
        </p>
      </div>
    );
  }

  if (!worklist) {
    return (
      <div className="curate-panel">
        <h1 className="curate-title">Curation review</h1>
        <p className="curate-hint-text">Loading…</p>
      </div>
    );
  }

  const refsValid = parseRefs(manualRef) !== null;
  const polygonRelevant = selected ? POLYGON_KINDS.has(selected.kind) : false;
  const canSaveLocal = Boolean(selected) && isValidSlug(slug) && position !== null;
  const checkedSet = new Set(checkedRefs.map((item) => item.ref));
  // Only an unambiguous wikidata id goes along; `apply` cannot choose between two.
  const checkedQids = [...new Set(checkedRefs.flatMap((item) => (item.wikidata ? [item.wikidata] : [])))];

  return (
    <div className="curate-panel">
      <header className="curate-header">
        <h1 className="curate-title">Curation review</h1>
        <p className="curate-counts">
          {rows.length - doneCount} open · {doneCount} done · {visible.length} shown
        </p>
        <input
          type="search"
          className="curate-input"
          placeholder="filter: Frisian, German, hint"
          value={filterText}
          onChange={(event) => setFilterText(event.target.value)}
        />
        <div className="curate-row">
          <select
            className="curate-input"
            aria-label="kind"
            value={filterKind}
            onChange={(event) => setFilterKind(event.target.value)}
          >
            <option value="">all kinds</option>
            {kinds.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
          <select
            className="curate-input"
            aria-label="result"
            value={filterResult}
            onChange={(event) =>
              setFilterResult(event.target.value as 'all' | 'ambiguous' | 'not_found')
            }
          >
            <option value="all">all results</option>
            <option value="ambiguous">ambiguous</option>
            <option value="not_found">not found</option>
          </select>
        </div>
        <label className="curate-check">
          <input
            type="checkbox"
            checked={hideDone}
            onChange={(event) => setHideDone(event.target.checked)}
          />
          hide done
        </label>
      </header>

      <ul className="curate-list" ref={listRef}>
        {visible.length === 0 && <li className="curate-empty">nothing matches the filter</li>}
        {visible.map((row) => {
          const done = doneByLine.get(row.line);
          return (
            <li
              key={row.line}
              className={[
                'curate-item',
                row.line === selectedLine ? 'is-selected' : '',
                done ? 'is-done' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <button type="button" onClick={() => goTo(row.line)}>
                <span className="curate-item-head">
                  <span className="curate-item-name">{row.name}</span>
                  <span className="curate-item-de">{primary(row.de) || primary(row.da)}</span>
                  <span className={`curate-badge curate-badge-${row.result}`}>{row.kind}</span>
                </span>
                {row.hint && <span className="curate-item-hint">{row.hint}</span>}
                {done && (
                  <span className="curate-item-done">
                    {done.action === 'osm' && `✓ ${done.osm ?? ''}`}
                    {done.action === 'local' && `✓ local/${done.slug ?? ''}`}
                    {done.action === 'skip' && '✓ skipped'}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {selected && (
        <section className="curate-detail">
          <h2 className="curate-detail-title">
            {selected.name}
            <span className="curate-detail-line">places.csv line {selected.line}</span>
          </h2>
          <dl className="curate-facts">
            {Object.entries(selected.names ?? {}).map(([column, value]) => (
              <div key={column}>
                <dt>{column}</dt>
                <dd>{value}</dd>
              </div>
            ))}
            {selected.de && (
              <div>
                <dt>de</dt>
                <dd>{selected.de}</dd>
              </div>
            )}
            {selected.da && (
              <div>
                <dt>da</dt>
                <dd>{selected.da}</dd>
              </div>
            )}
            {selected.hint && (
              <div>
                <dt>hint</dt>
                <dd>{selected.hint}</dd>
              </div>
            )}
            {selected.note && (
              <div>
                <dt>note</dt>
                <dd>{selected.note}</dd>
              </div>
            )}
            <div>
              <dt>kind</dt>
              <dd>
                {selected.kind} · {selected.result}
              </dd>
            </div>
            {selected.why && (
              <div>
                <dt>why</dt>
                <dd>{selected.why}</dd>
              </div>
            )}
          </dl>

          {selectedDone && (
            <p className="curate-done-note">
              already decided: {selectedDone.action}
              {selectedDone.osm ? ` ${selectedDone.osm}` : ''}
              {selectedDone.slug ? ` local/${selectedDone.slug}` : ''}
            </p>
          )}

          <h3 className="curate-section">Candidates ({selected.candidates.length})</h3>
          {selected.candidates.length === 0 && (
            <p className="curate-hint-text">no candidates — use the lookups below</p>
          )}
          <ul className="curate-candidates">
            {selected.candidates.map((candidate, i) => (
              <li
                key={candidate.ref}
                className={
                  [
                    candidate.ref === activeRef ? 'is-active' : '',
                    checkedSet.has(candidate.ref) ? 'is-checked' : '',
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
              >
                <input
                  type="checkbox"
                  className="curate-check-ref"
                  aria-label={`select ${candidate.ref}`}
                  checked={checkedSet.has(candidate.ref)}
                  onChange={() => toggleChecked(candidate.ref, candidate.wikidata)}
                />
                <button
                  type="button"
                  className="curate-candidate"
                  onClick={() => {
                    setActiveRef(candidate.ref);
                    const map = mapRef.current?.getMap();
                    if (map && hasPoint(candidate)) {
                      map.flyTo({ center: [candidate.lon, candidate.lat], zoom: 14, essential: true });
                    }
                  }}
                >
                  <span className="curate-num" style={{ background: candidateColor(candidate) }}>
                    {i + 1}
                  </span>
                  <span className="curate-candidate-body">
                    <span className="curate-candidate-name">{candidate.name}</span>
                    <span className="curate-mono">{candidate.ref}</span>
                    <span className="curate-candidate-meta">
                      {candidate.class}
                      {typeof candidate.km === 'number' ? ` · ${candidate.km} km` : ''}
                      {candidate.tags ? ` · ${candidate.tags}` : ''}
                      {candidate.wikidata ? ` · ${candidate.wikidata}` : ''}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  className="curate-pick"
                  onClick={() =>
                    void send(selected, {
                      action: 'osm',
                      osm: candidate.ref,
                      ...(candidate.wikidata ? { wikidata: candidate.wikidata } : {}),
                      ...(note.trim() ? { note: note.trim() } : {}),
                    })
                  }
                >
                  Pick
                </button>
              </li>
            ))}
          </ul>

          <h3 className="curate-section">Look up in OSM</h3>
          <input
            className="curate-input"
            value={lookupQuery}
            aria-label="lookup query"
            onChange={(event) => setLookupQuery(event.target.value)}
          />
          <div className="curate-row">
            <button type="button" disabled={lookupBusy} onClick={() => void runNominatim()}>
              Nominatim
            </button>
            <button type="button" disabled={lookupBusy} onClick={() => void runOverpass()}>
              Overpass
            </button>
            <a
              href={`https://www.openstreetmap.org/search?query=${encodeURIComponent(
                lookupQuery,
              )}#map=10/54.7/8.9`}
              target="_blank"
              rel="noreferrer"
            >
              openstreetmap.org
            </a>
          </div>
          {lookupBusy && <p className="curate-hint-text">searching…</p>}
          {lookupError && <p className="curate-error">{lookupError}</p>}
          {lookupSource && !lookupError && <p className="curate-hint-text">{lookupSource}</p>}
          <ul className="curate-candidates">
            {lookupResults.map((result, i) => (
              <li
                key={`${result.ref}-${i}`}
                className={checkedSet.has(result.ref) ? 'is-checked' : undefined}
              >
                <input
                  type="checkbox"
                  className="curate-check-ref"
                  aria-label={`select ${result.ref}`}
                  checked={checkedSet.has(result.ref)}
                  onChange={() => toggleChecked(result.ref, result.wikidata)}
                />
                <button
                  type="button"
                  className="curate-candidate"
                  onClick={() => {
                    const map = mapRef.current?.getMap();
                    map?.flyTo({ center: [result.lon, result.lat], zoom: 14, essential: true });
                  }}
                >
                  <span className="curate-num" style={{ background: COLOR_LOOKUP }}>
                    {i + 1}
                  </span>
                  <span className="curate-candidate-body">
                    <span className="curate-candidate-name">{result.name || '(unnamed)'}</span>
                    <span className="curate-mono">{result.ref}</span>
                    <span className="curate-candidate-meta">{result.what || result.tags}</span>
                  </span>
                </button>
                <button
                  type="button"
                  className="curate-pick"
                  onClick={() =>
                    void send(selected, {
                      action: 'osm',
                      osm: result.ref,
                      ...(result.wikidata ? { wikidata: result.wikidata } : {}),
                      ...(note.trim() ? { note: note.trim() } : {}),
                    })
                  }
                >
                  Pick
                </button>
              </li>
            ))}
          </ul>

          {checkedRefs.length > 0 && (
            <div className="curate-multi">
              <span className="curate-mono">
                {checkedRefs.length} selected: {checkedRefs.map((item) => item.ref).join('; ')}
              </span>
              {checkedQids.length > 1 && (
                <p className="curate-hint-text">
                  different wikidata ids ({checkedQids.join(', ')}) — none saved
                </p>
              )}
              <div className="curate-row">
                <button
                  type="button"
                  onClick={() =>
                    void send(selected, {
                      action: 'osm',
                      osm: checkedRefs.map((item) => item.ref).join('; '),
                      ...(checkedQids.length === 1 ? { wikidata: checkedQids[0] } : {}),
                      ...(note.trim() ? { note: note.trim() } : {}),
                    })
                  }
                >
                  Pick {checkedRefs.length} selected
                </button>
                <button type="button" onClick={() => setCheckedRefs([])}>
                  clear selection
                </button>
              </div>
            </div>
          )}

          <h3 className="curate-section">OSM reference by hand</h3>
          <input
            className="curate-input"
            placeholder="way/177387348; node/123 or an openstreetmap.org URL"
            value={manualRef}
            aria-label="osm reference"
            onChange={(event) => setManualRef(event.target.value)}
          />
          <div className="curate-row">
            <button
              type="button"
              disabled={!refsValid}
              onClick={() => {
                const refs = parseRefs(manualRef);
                if (!refs) return;
                void send(selected, {
                  action: 'osm',
                  osm: refs.join('; '),
                  ...(note.trim() ? { note: note.trim() } : {}),
                });
              }}
            >
              Pick reference
            </button>
            {manualRef.trim() && !refsValid && (
              <span className="curate-error">node/way/relation id or OSM URL expected</span>
            )}
          </div>

          <h3 className="curate-section">Local reference (place OSM does not have)</h3>
          <input
            className="curate-input"
            value={slug}
            aria-label="slug"
            onChange={(event) => setSlug(event.target.value)}
          />
          {!isValidSlug(slug) && (
            <p className="curate-error">slug must look like `toftem-emmelsbuell`</p>
          )}
          <div className="curate-row">
            <button
              type="button"
              className={pickingPosition ? 'is-armed' : undefined}
              onClick={() => setPickingPosition((on) => !on)}
            >
              {pickingPosition ? 'click the map…' : 'set position on map'}
            </button>
            <span className="curate-mono">
              {position ? `${position.lat.toFixed(6)}, ${position.lon.toFixed(6)}` : 'no position'}
            </span>
          </div>
          {polygonRelevant && (
            <input
              className="curate-input"
              type="number"
              min="0"
              step="0.1"
              placeholder="polygon_km2 (optional area label)"
              aria-label="polygon_km2"
              value={polygonKm2}
              onChange={(event) => setPolygonKm2(event.target.value)}
            />
          )}
          <button
            type="button"
            disabled={!canSaveLocal}
            onClick={() =>
              void send(selected, {
                action: 'local',
                slug,
                lat: Number(position?.lat.toFixed(6)),
                lon: Number(position?.lon.toFixed(6)),
                ...(polygonRelevant && polygonKm2.trim()
                  ? { polygon_km2: Number(polygonKm2) }
                  : {}),
                ...(note.trim() ? { note: note.trim() } : {}),
              })
            }
          >
            Save local
          </button>

          <h3 className="curate-section">Note / skip</h3>
          <input
            className="curate-input"
            placeholder="note (optional, any action)"
            value={note}
            aria-label="note"
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="curate-row">
            <button
              type="button"
              onClick={() =>
                void send(selected, {
                  action: 'skip',
                  ...(note.trim() ? { note: note.trim() } : {}),
                })
              }
            >
              Skip
            </button>
            {selectedDone && (
              <button type="button" onClick={() => void send(selected, { action: 'clear' })}>
                Clear
              </button>
            )}
          </div>
          {postError && <p className="curate-error">could not save: {postError}</p>}
        </section>
      )}
    </div>
  );
}
