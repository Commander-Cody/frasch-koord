import { useEffect, useRef } from 'react';
import type {
  FilterSpecification,
  GeoJSONSource,
  LayerSpecification,
  Map as MapLibreMap,
} from 'maplibre-gl';

/** What this MapLibre build's GeoJSON source accepts, without depending on a
 *  global `GeoJSON` namespace that tsconfig.app.json does not pull in. */
export type OverlayData = Parameters<GeoJSONSource['setData']>[0];

export interface GeoJsonOverlay {
  /** The id of the GeoJSON source; every layer draws from it. */
  source: string;
  data: OverlayData;
  /** Added once, in this order; afterwards only their filters follow a change. */
  layers: LayerSpecification[];
  /** The layer of the base style to draw beneath, so no label is covered. */
  beforeId?: string;
}

/**
 * Draws `data` on `map` in `layers` while the component is mounted. The
 * source and its layers are added once (the map has loaded before a panel
 * mounts); new data is handed to the source, a new filter to its layer.
 */
export function useGeoJsonOverlay(map: MapLibreMap, overlay: GeoJsonOverlay): void {
  const { source, data, layers, beforeId } = overlay;
  // What the mount adds, without the mount re-running for every new value.
  const latest = useRef(overlay);
  useEffect(() => {
    latest.current = overlay;
  });

  useEffect(() => {
    const added = latest.current.layers.map((layer) => layer.id);
    map.addSource(source, { type: 'geojson', data: latest.current.data });
    for (const layer of latest.current.layers) map.addLayer(layer, beforeId);
    return () => {
      // Asked first, since the map may be gone already when the panel goes
      // with it: a removed map has no layers left to remove.
      for (const id of added) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(source)) map.removeSource(source);
    };
  }, [map, source, beforeId]);

  useEffect(() => {
    map.getSource<GeoJSONSource>(source)?.setData(data);
  }, [map, source, data]);

  useEffect(() => {
    for (const layer of layers) map.setFilter(layer.id, filterOf(layer));
  }, [map, layers]);
}

function filterOf(layer: LayerSpecification): FilterSpecification | null {
  return 'filter' in layer ? (layer.filter ?? null) : null;
}
