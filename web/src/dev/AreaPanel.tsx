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
 * `names/build_dialect_areas.py`, press Reload.
 *
 * English-only on purpose, like the curation view: this is a tool, not the map.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RefObject } from 'react';
import type { GeoJSONSource, Map as MapLibreMap, MapLayerMouseEvent } from 'maplibre-gl';
import type { ExpressionSpecification } from '@maplibre/maplibre-gl-style-spec';

import type { MapViewHandle } from '../components/Map';
import {
  BEFORE_ID,
  COLOR_UNASSIGNED,
  COLOR_UNKNOWN,
  DIALECT_COLORS,
  FILL,
  FIT_PADDING,
  LAYERS,
  LINE,
  SELECTED,
  SELECTED_CASING,
  SOURCE,
  fidFilter,
  layerSpecs,
} from './areaLayers';
import { DIALECTS } from '../config';
import './AreaPanel.css';

/* ------------------------------------------------------------------ data */

/** One municipality, as names/build_dialect_areas.py writes it. */
export interface AreaProps {
  /** Stable within one build; the selection key. */
  fid: number;
  /** false = a Kreis Nordfriesland municipality no CSV row claims. */
  assigned: boolean;
  /** Dialect tag; absent on unassigned features (see the build script). */
  dialect?: string;
  label?: string;
  name: string;
  /** The research note of the CSV row, verbatim. */
  note?: string;
  osm: string;
  /** Line in names/dialect_areas.csv; absent on unassigned features. */
  line?: number;
  km2: number;
}

interface AreaFeature {
  type: 'Feature';
  properties: AreaProps;
  geometry: { type: string; coordinates: unknown };
}

interface AreaCollection {
  type: 'FeatureCollection';
  features: AreaFeature[];
}

/** What this MapLibre build's GeoJSON source accepts, without depending on a
 *  global `GeoJSON` namespace that tsconfig.app.json does not pull in. */
type SourceData = Parameters<GeoJSONSource['setData']>[0];

/* ------------------------------------------------------------- geometry */

type Bounds = [[number, number], [number, number]];

/** Bounding box of a Polygon/MultiPolygon, without pulling in a geo library. */
function bboxOf(geometry: { coordinates: unknown }): Bounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const walk = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === 'number' && typeof node[1] === 'number') {
      const [x, y] = node as [number, number];
      if (x < minX) minX = x;
      if (y < minY) minY = y;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
      return;
    }
    for (const child of node) walk(child);
  };
  walk(geometry.coordinates);
  return minX === Infinity ? null : [
    [minX, minY],
    [maxX, maxY],
  ];
}

/* ------------------------------------------------------------------ misc */

/** "relation/1420394; way/123" -> one openstreetmap.org link each. */
function osmRefs(osm: string): string[] {
  return osm
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean);
}

export interface AreaPanelProps {
  mapRef: RefObject<MapViewHandle | null>;
}

export default function AreaPanel({ mapRef }: AreaPanelProps) {
  const [collection, setCollection] = useState<AreaCollection | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedFid, setSelectedFid] = useState<number | null>(null);
  const [filterText, setFilterText] = useState('');
  /** A dialect tag, '' for everything, or 'unassigned'. */
  const [filterDialect, setFilterDialect] = useState('');

  // The click handler and the style-rebuild guard both need the current
  // selection without being rebuilt every time it changes.
  const selectedRef = useRef<number | null>(null);
  const itemRefs = useRef(new Map<number, HTMLLIElement>());

  /* ------------------------------------------------------------- loading */

  // Bumped by the Reload button. The geometry is a build artefact, so
  // re-reading it is the whole of "refresh": edit the CSV, re-run the build,
  // press Reload.
  const [reloadNonce, setReloadNonce] = useState(0);
  const reload = useCallback(() => setReloadNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch('/__areas/parts');
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { error?: string } | null;
          throw new Error(body?.error ?? `HTTP ${res.status}`);
        }
        const data = (await res.json()) as AreaCollection;
        if (cancelled) return;
        setCollection(data);
        setLoadError(null);
      } catch (err) {
        if (cancelled) return;
        setCollection(null);
        setLoadError(err instanceof Error ? err.message : String(err));
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadNonce]);

  /* ------------------------------------------------------------- derived */

  const features = useMemo(() => collection?.features ?? [], [collection]);

  const byFid = useMemo(() => {
    const map = new Map<number, AreaFeature>();
    for (const feature of features) map.set(feature.properties.fid, feature);
    return map;
  }, [features]);

  /** Registry order, so the legend reads like names/dialects.csv. */
  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const feature of features) {
      const key = feature.properties.assigned
        ? (feature.properties.dialect ?? '?')
        : 'unassigned';
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const rows = DIALECTS.map((dialect) => ({
      key: dialect.tag,
      label: dialect.label,
      color: DIALECT_COLORS[dialect.tag] ?? COLOR_UNKNOWN,
      count: counts.get(dialect.tag) ?? 0,
    })).filter((row) => row.count > 0);
    const loose = counts.get('unassigned') ?? 0;
    if (loose > 0) {
      rows.push({
        key: 'unassigned',
        label: 'not assigned',
        color: COLOR_UNASSIGNED,
        count: loose,
      });
    }
    return rows;
  }, [features]);

  const visible = useMemo(() => {
    const needle = filterText.trim().toLowerCase();
    return features.filter((feature) => {
      const p = feature.properties;
      if (filterDialect === 'unassigned' && p.assigned) return false;
      if (filterDialect && filterDialect !== 'unassigned' && p.dialect !== filterDialect) {
        return false;
      }
      if (!needle) return true;
      return `${p.name} ${p.osm} ${p.note ?? ''}`.toLowerCase().includes(needle);
    });
  }, [features, filterText, filterDialect]);

  /** The list, grouped by dialect in registry order, unassigned last. */
  const sections = useMemo(() => {
    const order = new Map<string, number>(DIALECTS.map((d, i) => [d.tag, i]));
    const bucket = new Map<string, AreaFeature[]>();
    for (const feature of visible) {
      const key = feature.properties.assigned
        ? (feature.properties.dialect ?? '?')
        : 'unassigned';
      const list = bucket.get(key);
      if (list) list.push(feature);
      else bucket.set(key, [feature]);
    }
    return [...bucket.entries()]
      .sort((a, b) => (order.get(a[0]) ?? 99) - (order.get(b[0]) ?? 99))
      .map(([key, items]) => ({
        key,
        label:
          key === 'unassigned'
            ? 'not assigned'
            : (items[0].properties.label ?? key),
        color: key === 'unassigned' ? COLOR_UNASSIGNED : (DIALECT_COLORS[key] ?? COLOR_UNKNOWN),
        items: [...items].sort((a, b) => a.properties.name.localeCompare(b.properties.name, 'de')),
      }));
  }, [visible]);

  const selected = selectedFid === null ? null : (byFid.get(selectedFid) ?? null);

  /* --------------------------------------------------- deep link (?area=) */

  // `?areas&area=35` opens the row on line 35 of dialect_areas.csv — a link
  // from the checklist, or just resuming where the last session stopped.
  // Unknown lines are ignored: line numbers shift when a row is added, the
  // same caveat names/curate.py documents for `?curate&line=`.
  const initialLine = useRef<number | null>(
    (() => {
      const raw = new URLSearchParams(window.location.search).get('area');
      return raw && /^\d+$/.test(raw) ? Number(raw) : null;
    })(),
  );

  /* ----------------------------------------------------------- selection */

  const applySelection = useCallback((map: MapLibreMap, fid: number | null) => {
    for (const id of [SELECTED_CASING, SELECTED]) {
      if (map.getLayer(id)) map.setFilter(id, fidFilter(fid));
    }
  }, []);

  const select = useCallback(
    (fid: number | null, opts?: { fly?: boolean }) => {
      setSelectedFid(fid);
      selectedRef.current = fid;

      const feature = fid === null ? null : (byFid.get(fid) ?? null);

      // Only assigned rows get a shareable key; an unassigned municipality has
      // no line in the CSV to point at.
      const params = new URLSearchParams(window.location.search);
      const line = feature?.properties.line;
      if (line === undefined) params.delete('area');
      else params.set('area', String(line));
      // Keep MapLibre's `#zoom/lat/lon` hash: it is part of the resume state.
      window.history.replaceState(
        window.history.state,
        '',
        `${window.location.pathname}?${params}${window.location.hash}`,
      );

      const map = mapRef.current?.getMap();
      if (map) {
        applySelection(map, fid);
        if (opts?.fly && feature) {
          const bounds = bboxOf(feature.geometry);
          if (bounds) map.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: 13, duration: 600 });
        }
      }
      if (fid !== null) {
        itemRefs.current.get(fid)?.scrollIntoView({ block: 'nearest' });
      }
    },
    [applySelection, byFid, mapRef],
  );

  // Honour the deep link once the geometry is there (only once).
  useEffect(() => {
    const line = initialLine.current;
    if (line === null || features.length === 0) return;
    initialLine.current = null;
    const hit = features.find((feature) => feature.properties.line === line);
    if (hit) select(hit.properties.fid, { fly: true });
  }, [features, select]);

  /* ------------------------------------------------------------- overlay */

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !collection) return;
    let cancelled = false;

    // Idempotent on purpose: `addSource` itself fires `styledata`, React
    // StrictMode mounts every effect twice in development, and a style rebuild
    // calls this again to put the layers back.
    const ensure = () => {
      if (cancelled) return;
      try {
        const existing = map.getSource(SOURCE) as GeoJSONSource | undefined;
        if (existing) {
          existing.setData(collection as unknown as SourceData);
          return;
        }
        map.addSource(SOURCE, { type: 'geojson', data: collection as unknown as SourceData });
        const before = map.getLayer(BEFORE_ID) ? BEFORE_ID : undefined;
        for (const spec of layerSpecs()) map.addLayer(spec, before);
        applySelection(map, selectedRef.current);
      } catch {
        // A style still in flux must not break the panel; `styledata` retries.
      }
    };

    if (map.isStyleLoaded()) ensure();
    else map.once('load', ensure);
    // MapView rebuilds the whole style when the label option changes, which
    // drops every imperatively added layer. `?areas` shows no label selector
    // today, so this is insurance — but it is the difference between "works"
    // and "silently empty" the day one is added.
    map.on('styledata', ensure);

    return () => {
      cancelled = true;
      map.off('load', ensure);
      map.off('styledata', ensure);
      try {
        for (const id of LAYERS) if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(SOURCE)) map.removeSource(SOURCE);
      } catch {
        // Style already torn down.
      }
    };
  }, [collection, applySelection, mapRef]);

  // The legend doubles as the map filter: drawing one dialect alone is the
  // reliable way to tell two look-alike colours apart (see DIALECT_COLORS).
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !collection) return;
    const filter: ExpressionSpecification | null = !filterDialect
      ? null
      : filterDialect === 'unassigned'
        ? (['!', ['get', 'assigned']] as unknown as ExpressionSpecification)
        : (['==', ['get', 'dialect'], filterDialect] as unknown as ExpressionSpecification);
    try {
      for (const id of [FILL, LINE]) {
        if (map.getLayer(id)) map.setFilter(id, filter);
      }
    } catch {
      // Layers not added yet; `ensure` will run with the filter reapplied
      // by this effect on the next render.
    }
  }, [filterDialect, collection, mapRef]);

  /* --------------------------------------------------------------- click */

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !collection) return;

    const onClick = (event: MapLayerMouseEvent) => {
      const hits = event.features ?? [];
      if (hits.length === 0) return;
      // Smallest wins, like dialects.AreaIndex: nothing nests today, but a
      // Hallig inside a municipality is the obvious next row.
      const best = hits.reduce((winner, candidate) =>
        Number(candidate.properties?.km2) < Number(winner.properties?.km2) ? candidate : winner,
      );
      const fid = Number(best.properties?.fid);
      // Deliberately no fly: the map must not jump out from under the cursor
      // that just clicked it.
      if (Number.isFinite(fid)) select(fid, { fly: false });
    };
    const enter = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const leave = () => {
      map.getCanvas().style.cursor = '';
    };

    map.on('click', FILL, onClick);
    map.on('mouseenter', FILL, enter);
    map.on('mouseleave', FILL, leave);
    return () => {
      map.off('click', FILL, onClick);
      map.off('mouseenter', FILL, enter);
      map.off('mouseleave', FILL, leave);
      map.getCanvas().style.cursor = '';
    };
  }, [collection, mapRef, select]);

  /* ---------------------------------------------------------- navigation */

  const move = useCallback(
    (delta: number) => {
      if (visible.length === 0) return;
      const flat = sections.flatMap((section) => section.items);
      const at = flat.findIndex((feature) => feature.properties.fid === selectedFid);
      const next = at < 0 ? 0 : Math.min(flat.length - 1, Math.max(0, at + delta));
      select(flat[next].properties.fid, { fly: true });
    },
    [sections, visible.length, select, selectedFid],
  );

  /* -------------------------------------------------------------- render */

  if (loadError) {
    return (
      <div className="area-panel">
        <h1 className="area-title">Dialect areas</h1>
        <p className="area-error">Could not load the areas: {loadError}</p>
        <p className="area-hint">
          This view needs the Vite dev server (<code>npm run dev</code>) and the geometry built
          by <code>names/build_dialect_areas.py</code>.
        </p>
        <button type="button" onClick={reload}>
          Reload
        </button>
      </div>
    );
  }

  if (!collection) {
    return (
      <div className="area-panel">
        <h1 className="area-title">Dialect areas</h1>
        <p className="area-hint">loading…</p>
      </div>
    );
  }

  const assignedCount = features.filter((feature) => feature.properties.assigned).length;

  return (
    <div
      className="area-panel"
      onKeyDown={(event) => {
        if (event.target instanceof HTMLInputElement) return;
        if (event.key === 'ArrowDown' || event.key === 'j') {
          event.preventDefault();
          move(1);
        } else if (event.key === 'ArrowUp' || event.key === 'k') {
          event.preventDefault();
          move(-1);
        }
      }}
    >
      <div className="area-header">
        <h1 className="area-title">Dialect areas</h1>
        <p className="area-counts">
          {assignedCount} assigned · {features.length - assignedCount} not assigned ·{' '}
          {visible.length} shown
          <button className="area-reload" type="button" onClick={reload}>
            Reload
          </button>
        </p>
        <input
          className="area-input"
          value={filterText}
          aria-label="filter by name, OSM reference or note"
          placeholder="filter by name, osm ref or note…"
          onChange={(event) => setFilterText(event.target.value)}
        />
      </div>

      <ul className="area-legend">
        {groups.map((group) => (
          <li key={group.key}>
            <button
              type="button"
              className={`area-legend-item${filterDialect === group.key ? ' is-active' : ''}`}
              title="show only this one on the map"
              onClick={() => setFilterDialect(filterDialect === group.key ? '' : group.key)}
            >
              <span className="area-swatch" style={{ background: group.color }} />
              <span className="area-legend-label">{group.label}</span>
              <span className="area-legend-count">{group.count}</span>
            </button>
          </li>
        ))}
      </ul>

      {selected && (
        <div className="area-detail">
          <h2 className="area-detail-name">{selected.properties.name || '(unnamed)'}</h2>
          <dl className="area-facts">
            <div>
              <dt>dialect</dt>
              <dd>
                {selected.properties.assigned ? (
                  <>
                    <span
                      className="area-swatch"
                      style={{
                        background:
                          DIALECT_COLORS[selected.properties.dialect ?? ''] ?? COLOR_UNKNOWN,
                      }}
                    />{' '}
                    {selected.properties.label}{' '}
                    <span className="area-mono">{selected.properties.dialect}</span>
                  </>
                ) : (
                  <em>not in dialect_areas.csv</em>
                )}
              </dd>
            </div>
            {selected.properties.line !== undefined && (
              <div>
                <dt>row</dt>
                <dd>
                  <span className="area-mono">dialect_areas.csv:{selected.properties.line}</span>
                </dd>
              </div>
            )}
            <div>
              <dt>area</dt>
              <dd>{selected.properties.km2} km²</dd>
            </div>
            <div>
              <dt>osm</dt>
              <dd>
                {osmRefs(selected.properties.osm).map((ref) => (
                  <a
                    key={ref}
                    className="area-mono"
                    href={`https://www.openstreetmap.org/${ref}`}
                    target="_blank"
                    rel="noopener"
                  >
                    {ref}
                  </a>
                ))}
              </dd>
            </div>
          </dl>
          {selected.properties.assigned ? (
            selected.properties.note ? (
              <p className="area-note">{selected.properties.note}</p>
            ) : (
              <p className="area-hint">no note on this row</p>
            )
          ) : (
            <div className="area-add">
              <p className="area-hint">
                No row claims this municipality, so nothing inside it gets a dialect. To add
                it, paste this into <code>names/dialect_areas.csv</code>, re-run
                <code> names/build_dialect_areas.py</code>, then press Reload.
              </p>
              <button
                type="button"
                onClick={() => void navigator.clipboard?.writeText(selected.properties.osm)}
              >
                copy {selected.properties.osm}
              </button>
            </div>
          )}
        </div>
      )}

      {sections.length === 0 && <p className="area-hint">nothing matches that filter</p>}

      {sections.map((section) => (
        <div key={section.key}>
          <p className="area-section">
            <span className="area-swatch" style={{ background: section.color }} />{' '}
            {section.label} ({section.items.length})
          </p>
          <ul className="area-list">
            {section.items.map((feature) => {
              const { fid, name, line } = feature.properties;
              return (
                <li
                  key={fid}
                  ref={(node) => {
                    if (node) itemRefs.current.set(fid, node);
                    else itemRefs.current.delete(fid);
                  }}
                >
                  <button
                    type="button"
                    className={`area-item${fid === selectedFid ? ' is-selected' : ''}`}
                    onClick={() => select(fid, { fly: true })}
                  >
                    <span>{name || '(unnamed)'}</span>
                    {line !== undefined && <span className="area-line">{line}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
