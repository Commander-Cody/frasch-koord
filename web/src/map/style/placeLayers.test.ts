import { expect, it } from 'vitest';
import { featureFilter } from '@maplibre/maplibre-gl-style-spec';
import type { LayerSpecification } from 'maplibre-gl';

import type { TileProps } from '../../names/tile';
import { BASE_STYLE, PLACE_LAYERS } from './index';

function placeLayer(id: string): LayerSpecification {
  const layer = BASE_STYLE.layers.find((candidate) => candidate.id === id);
  if (!layer) throw new Error(`no layer ${id}`);
  return layer;
}

function isShownAt(layer: LayerSpecification, zoom: number): boolean {
  return zoom >= (layer.minzoom ?? 0) && zoom < (layer.maxzoom ?? 24);
}

/**
 * The place layers that draw a point feature with the properties `props` at
 * `zoom`: the layer's zoom range and its filter, by MapLibre's own evaluation.
 */
function layersDrawing(props: TileProps, zoom: number): string[] {
  return PLACE_LAYERS.map(placeLayer)
    .filter((layer) => {
      if (!isShownAt(layer, zoom)) return false;
      const filter = 'filter' in layer ? layer.filter : undefined;
      return featureFilter(filter, 'filter').filter({ zoom }, { properties: props, type: 1 });
    })
    .map((layer) => layer.id);
}

// What the tiles carry for a landscape labelled by a synthetic island square
// (Ääderstää, see names/README.md#curationcsv--per-feature-map-tuning).
const landscape = { class: 'island', 'frasch:kind': 'landscape', 'frasch:maxzoom': '10' };

it('draws a landscape by place-landscape alone', () => {
  expect(layersDrawing(landscape, 9)).toEqual(['place-landscape']);
});

it('draws no landscape above its frasch:maxzoom', () => {
  expect(layersDrawing(landscape, 11)).toEqual([]);
});

it('draws a landscape that is a point by place-landscape alone', () => {
  const landscapePoint = { class: 'hamlet', 'frasch:kind': 'landscape' };

  expect(layersDrawing(landscapePoint, 12)).toEqual(['place-landscape']);
});

it('leaves a landscape of an admin class to its admin layer', () => {
  const schleswigHolstein = { class: 'state', 'frasch:kind': 'landscape' };

  expect(layersDrawing(schleswigHolstein, 6)).toEqual(['place-state']);
});
