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
  LAYERS,
  LINE,
  SELECTED,
  SELECTED_CASING,
  SOURCE,
  fidFilter,
  layerSpecs,
} from './areaLayers';
import { DIALECTS } from '../config';
import { replaceQueryParams } from '../queryParams';
import DevPanel from './DevPanel';
import { FIT_PADDING } from './panelLayout';
import { useDeepLinkParam } from './useDeepLinkParam';
import { useListNavigation } from './useListNavigation';
import './AreaPanel.css';

/* ------------------------------------------------------------------ data */

/** One municipality, as frasch/build_dialect_areas.py writes it. */
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
  /** The CSV row's OSM references (`relation/1; relation/2`); one per row, so the first is the deep-link key. */
  osm: string;
  /** Line in names/dialect_areas.csv, for display; absent on unassigned features. */
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
  return minX === Infinity
    ? null
    : [
        [minX, minY],
        [maxX, maxY],
      ];
}

/* ------------------------------------------------------------------ misc */

/** "relation/1420394; way/123" -> ["relation/1420394", "way/123"]: one link each, and the deep-link keys. */
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

  // The click handler, the style-rebuild guard and the deep link all need the
  // current selection without being rebuilt every time it changes.
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
      const key = feature.properties.assigned ? (feature.properties.dialect ?? '?') : 'unassigned';
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
      const key = feature.properties.assigned ? (feature.properties.dialect ?? '?') : 'unassigned';
      const list = bucket.get(key);
      if (list) list.push(feature);
      else bucket.set(key, [feature]);
    }
    return [...bucket.entries()]
      .sort((a, b) => (order.get(a[0]) ?? 99) - (order.get(b[0]) ?? 99))
      .map(([key, items]) => ({
        key,
        label: key === 'unassigned' ? 'not assigned' : (items[0].properties.label ?? key),
        color: key === 'unassigned' ? COLOR_UNASSIGNED : (DIALECT_COLORS[key] ?? COLOR_UNKNOWN),
        items: [...items].sort((a, b) => a.properties.name.localeCompare(b.properties.name, 'de')),
      }));
  }, [visible]);

  const selected = selectedFid === null ? null : (byFid.get(selectedFid) ?? null);

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

      // The deep-link key: the first OSM reference of the feature's row.
      replaceQueryParams({ area: feature ? osmRefs(feature.properties.osm)[0] : undefined });

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

  const selectAndFly = useCallback((fid: number) => select(fid, { fly: true }), [select]);

  /* --------------------------------------------------- deep link (?area=) */

  // `?areas&area=relation/1147134` opens the municipality with that OSM
  // reference — a link from the checklist, or just resuming where the last
  // session stopped. A reference belongs to one dialect_areas.csv row only
  // (frasch/check.py enforces it), and unlike a line number it stays put when
  // rows are added. An unknown one is ignored.
  const openLinkedArea = useCallback(
    (ref: string) => {
      const hit = features.find((feature) => osmRefs(feature.properties.osm).includes(ref));
      if (hit) selectAndFly(hit.properties.fid);
    },
    [features, selectAndFly],
  );
  const hasSelection = useCallback(() => selectedRef.current !== null, []);
  useDeepLinkParam('area', features.length > 0, openLinkedArea, hasSelection);

  /* ------------------------------------------------------------- overlay */

  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map || !collection) return;
    let cancelled = false;

    // Idempotent on purpose: `addSource` itself fires `styledata`, React
    // StrictMode mounts every effect twice in development, and a style rebuild
    // calls this again to put the layers back. A source that is there already
    // holds this collection (a new one re-runs the effect, which removes the
    // old), so only a style that lost it needs the data again.
    const ensure = () => {
      if (cancelled) return;
      try {
        if (map.getSource(SOURCE)) return;
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

  // The list's order: by section, as shown.
  const listedFids = useMemo(
    () => sections.flatMap((section) => section.items.map((feature) => feature.properties.fid)),
    [sections],
  );
  useListNavigation(listedFids, selectedFid, selectAndFly);

  /* -------------------------------------------------------------- render */

  const assignedCount = features.filter((feature) => feature.properties.assigned).length;

  return (
    <DevPanel
      className="area-panel"
      title="Dialect areas"
      what="the areas"
      needs={
        <>
          This view needs the Vite dev server (<code>npm run dev</code>) and the geometry built by{' '}
          <code>names/build_dialect_areas.py</code>.
        </>
      }
      loaded={collection !== null}
      error={loadError}
      onReload={reload}
      header={
        <>
          <p className="dev-panel-counts area-counts">
            {assignedCount} assigned · {features.length - assignedCount} not assigned ·{' '}
            {visible.length} shown
            <button className="area-reload" type="button" onClick={reload}>
              Reload
            </button>
          </p>
          <input
            className="dev-panel-input"
            value={filterText}
            aria-label="filter by name, OSM reference or note"
            placeholder="filter by name, osm ref or note…"
            onChange={(event) => setFilterText(event.target.value)}
          />
        </>
      }
    >
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
          <dl className="dev-panel-facts area-facts">
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
                    <span className="dev-panel-mono">{selected.properties.dialect}</span>
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
                  <span className="dev-panel-mono">
                    dialect_areas.csv:{selected.properties.line}
                  </span>
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
                    className="dev-panel-mono"
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
              <p className="dev-panel-hint">no note on this row</p>
            )
          ) : (
            <div className="area-add">
              <p className="dev-panel-hint">
                No row claims this municipality, so nothing inside it gets a dialect. To add it,
                paste this into <code>names/dialect_areas.csv</code>, re-run
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

      {sections.length === 0 && <p className="dev-panel-hint">nothing matches that filter</p>}

      {sections.map((section) => (
        <div key={section.key}>
          <p className="dev-panel-section">
            <span className="area-swatch" style={{ background: section.color }} /> {section.label} (
            {section.items.length})
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
    </DevPanel>
  );
}
