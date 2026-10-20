// The municipalities of the dialect-area review (`?areas`), as
// frasch/build_dialect_areas.py writes them to names/dialect_areas_parts.geojson,
// and what the view works out from them. No React, no map.

import { dialect } from '../../dialects/registry';
import { osmRefs } from '../../names/osmRef';

/**
 * One municipality. The contract itself is
 * names/dialect-area-parts.schema.json; areas.test.ts pins AreaProps to it.
 */
export interface AreaProps {
  /** false = a Kreis Nordfriesland municipality no CSV row claims. */
  assigned: boolean;
  /** Dialect tag — the registry has its label; absent on unassigned features (see the build script). */
  dialect?: string;
  name: string;
  /** The research note of the CSV row, verbatim. */
  note?: string;
  /** The CSV row's OSM references (`relation/1; relation/2`); a reference is on one row only. */
  osm: string;
  /** Line in names/dialect_areas.csv, for display; absent on unassigned features. */
  line?: number;
  km2: number;
}

export interface AreaFeature {
  type: 'Feature';
  properties: AreaProps;
  geometry: { type: string; coordinates: unknown };
}

export interface AreaCollection {
  type: 'FeatureCollection';
  features: AreaFeature[];
}

/**
 * What selects a municipality, in the view and in `?area=`: the first OSM
 * reference of its row. Unlike the feature's place in the file or the row's
 * line, it stays put when a row is added and the areas are rebuilt.
 */
export function areaKey(props: AreaProps): string {
  return osmRefs(props.osm)[0];
}

/** The municipality of a row with `ref` among its OSM references, if any. */
export function findByRef(features: readonly AreaFeature[], ref: string): AreaFeature | undefined {
  return features.find((feature) => osmRefs(feature.properties.osm).includes(ref));
}

/** The group of the municipalities no row claims; never a dialect tag. */
export const UNASSIGNED = 'unassigned';

/** The municipalities of one dialect, or the unassigned ones. */
export interface DialectGroup {
  /** The dialect tag, or UNASSIGNED. */
  key: string;
  features: AreaFeature[];
}

/**
 * The name of a group: the variety's, as the registry has it. A
 * municipality no row claims is not a gap: south of the border it is Low
 * Saxon by default (frasch/build_dialect_areas.py).
 */
export function groupLabel(key: string): string {
  return key === UNASSIGNED ? 'no row – Low Saxon by default' : (dialect(key)?.label ?? key);
}

/** The group a municipality belongs in. */
export function groupKey(props: AreaProps): string {
  return props.dialect ?? UNASSIGNED;
}

/**
 * The municipalities by dialect: the dialects in `order`, then any tag it
 * does not know, the unassigned last. Each group by name.
 */
export function groupByDialect(
  features: readonly AreaFeature[],
  order: readonly string[],
): DialectGroup[] {
  const groups = new Map<string, AreaFeature[]>();
  for (const feature of features) {
    const key = groupKey(feature.properties);
    groups.set(key, [...(groups.get(key) ?? []), feature]);
  }
  const rank = (key: string) => {
    if (key === UNASSIGNED) return order.length + 1;
    const at = order.indexOf(key);
    return at < 0 ? order.length : at;
  };
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b))
    .map(([key, grouped]) => ({ key, features: grouped.sort(byName) }));
}

function byName(a: AreaFeature, b: AreaFeature): number {
  return a.properties.name.localeCompare(b.properties.name, 'de');
}

/** What the list shows. */
export interface AreaFilter {
  /** Matched against the name, the OSM references and the note. */
  text: string;
  /** A group drawn alone (see groupKey); null for all of them. */
  shown: string | null;
}

export function filterAreas(features: readonly AreaFeature[], filter: AreaFilter): AreaFeature[] {
  const needle = filter.text.trim().toLowerCase();
  return features.filter((feature) => {
    const props = feature.properties;
    if (filter.shown !== null && groupKey(props) !== filter.shown) return false;
    return `${props.name} ${props.osm} ${props.note ?? ''}`.toLowerCase().includes(needle);
  });
}

export type Bounds = [[number, number], [number, number]];

/** Bounding box of a Polygon/MultiPolygon, without pulling in a geo library. */
export function bboxOf(geometry: { coordinates: unknown }): Bounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const walk = (node: unknown): void => {
    if (!Array.isArray(node)) return;
    if (typeof node[0] === 'number' && typeof node[1] === 'number') {
      const [x, y] = node as [number, number];
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
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
