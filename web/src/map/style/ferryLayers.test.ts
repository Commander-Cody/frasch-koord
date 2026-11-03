import { expect, it } from 'vitest';
import type { LayerSpecification } from 'maplibre-gl';

import { layersDrawing } from '../../testing/layersDrawing';
import { BASE_STYLE } from './index';

const TRANSPORTATION_LAYERS: LayerSpecification[] = BASE_STYLE.layers.filter(
  (layer) => 'source-layer' in layer && layer['source-layer'] === 'transportation',
);

/** The transportation layers that draw a ferry route at `zoom`. */
function layersDrawingFerryLine(zoom: number): string[] {
  const feature = { properties: { class: 'ferry' }, type: 2 } as const;
  return layersDrawing(TRANSPORTATION_LAYERS, feature, zoom);
}

it('draws no ferry line at z9', () => {
  expect(layersDrawingFerryLine(9)).toEqual([]);
});

it('draws a ferry line by the ferry layer at z10', () => {
  expect(layersDrawingFerryLine(10)).toEqual(['ferry']);
});
