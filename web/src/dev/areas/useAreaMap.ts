// What the dialect-area view does on the map: the municipalities as an
// overlay, the selected one outlined, and a click on one selecting it.

import { useEffect, useMemo } from 'react';
import type { Map as MapLibreMap, MapLayerMouseEvent } from 'maplibre-gl';

import { useGeoJsonOverlay, type OverlayData } from '../shell/useGeoJsonOverlay';
import { areaKey, type AreaCollection, type AreaProps } from './areas';
import { areaLayers, BEFORE_ID, FILL, SOURCE, type AreaLayerState } from './areaLayers';

const NO_AREAS: AreaCollection = { type: 'FeatureCollection', features: [] };

export interface AreaMapOptions extends AreaLayerState {
  /** null until loaded. */
  collection: AreaCollection | null;
  /** A click on a municipality, with its key. */
  onPick: (key: string) => void;
}

export function useAreaMap(map: MapLibreMap, options: AreaMapOptions): void {
  const { collection, selectedOsm, shown, onPick } = options;
  const layers = useMemo(() => areaLayers({ selectedOsm, shown }), [selectedOsm, shown]);
  useGeoJsonOverlay(map, {
    source: SOURCE,
    data: (collection ?? NO_AREAS) as unknown as OverlayData,
    layers,
    beforeId: BEFORE_ID,
  });
  useAreaClicks(map, onPick);
}

/** A click on a municipality picks it, and the pointer says it can be clicked. */
function useAreaClicks(map: MapLibreMap, onPick: (key: string) => void): void {
  useEffect(() => {
    const onClick = (event: MapLayerMouseEvent) => {
      const hits = event.features ?? [];
      if (hits.length === 0) return;
      // Smallest wins, like dialect_areas.AreaIndex: nothing nests today, but a
      // Hallig inside a municipality is the obvious next row.
      const best = hits.reduce((winner, candidate) =>
        Number(candidate.properties.km2) < Number(winner.properties.km2) ? candidate : winner,
      );
      onPick(areaKey(best.properties as AreaProps));
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
      leave();
    };
  }, [map, onPick]);
}
