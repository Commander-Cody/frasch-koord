import { featureFilter } from '@maplibre/maplibre-gl-style-spec';
import type { LayerSpecification } from 'maplibre-gl';

import type { TileProps } from '../names/tile';

/** A feature as a style filter sees it: its properties and geometry type. */
export interface StyledFeature {
  properties: TileProps;
  /** 1 point, 2 line, 3 polygon, as in the vector tile spec. */
  type: 1 | 2 | 3;
}

function isShownAt(layer: LayerSpecification, zoom: number): boolean {
  return zoom >= (layer.minzoom ?? 0) && zoom < (layer.maxzoom ?? 24);
}

/**
 * The ids of those of `layers` that draw `feature` at `zoom`: the layer's
 * zoom range and its filter, by MapLibre's own evaluation.
 */
export function layersDrawing(
  layers: LayerSpecification[],
  feature: StyledFeature,
  zoom: number,
): string[] {
  return layers
    .filter((layer) => {
      if (!isShownAt(layer, zoom)) return false;
      const filter = 'filter' in layer ? layer.filter : undefined;
      return featureFilter(filter, 'filter').filter({ zoom }, feature);
    })
    .map((layer) => layer.id);
}
