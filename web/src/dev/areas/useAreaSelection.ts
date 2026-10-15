// Which municipality the review view has selected: by its key (areas.ts
// `areaKey`), so that it stays selected across a rebuild; a list row, the
// keys or a link fit the map to it.

import { useCallback, useMemo } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { fitTo } from '../shell/mapMoves';
import { useSelection, type Selection } from '../shell/useSelection';
import {
  areaKey,
  bboxOf,
  findByRef,
  type AreaCollection,
  type AreaFeature,
  type DialectGroup,
} from './areas';

export interface AreaSelection extends Selection {
  /** The selected municipality; undefined when none is, or a reload took it away. */
  area: AreaFeature | undefined;
}

/** `collection`: every municipality, null until loaded; `sections`: the list as shown. */
export function useAreaSelection(
  map: MapLibreMap,
  collection: AreaCollection | null,
  sections: readonly DialectGroup[],
): AreaSelection {
  const features = useMemo(() => collection?.features ?? [], [collection]);
  const byKey = useMemo(
    () => new Map(features.map((feature) => [areaKey(feature.properties), feature])),
    [features],
  );
  const selection = useSelection({
    param: 'area',
    keys: useMemo(() => listedKeys(sections), [sections]),
    ready: collection !== null,
    resolve: useCallback(
      (ref: string) => {
        const hit = findByRef(features, ref);
        return hit && areaKey(hit.properties);
      },
      [features],
    ),
    show: useCallback((key: string) => showArea(map, byKey.get(key)), [map, byKey]),
  });
  const area = selection.selected === null ? undefined : byKey.get(selection.selected);
  return { ...selection, area };
}

function listedKeys(sections: readonly DialectGroup[]): string[] {
  return sections.flatMap((section) => section.features.map((f) => areaKey(f.properties)));
}

function showArea(map: MapLibreMap, feature: AreaFeature | undefined): void {
  const bounds = feature && bboxOf(feature.geometry);
  if (bounds) fitTo(map, bounds);
}
