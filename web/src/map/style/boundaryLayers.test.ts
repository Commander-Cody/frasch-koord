import { expect, it } from 'vitest';
import { latest, normalizePropertyExpression } from '@maplibre/maplibre-gl-style-spec';
import type { LayerSpecification, LineLayerSpecification } from 'maplibre-gl';

import { layersDrawing } from '../../testing/layersDrawing';
import { BASE_STYLE } from './index';

const BOUNDARY_LAYERS: LayerSpecification[] = BASE_STYLE.layers.filter(
  (layer) => 'source-layer' in layer && layer['source-layer'] === 'boundary',
);

/** The boundary layers that draw a land boundary of `adminLevel` at z12. */
function layersDrawingLandBoundary(adminLevel: number): string[] {
  const feature = { properties: { admin_level: adminLevel, maritime: 0 }, type: 2 } as const;
  return layersDrawing(BOUNDARY_LAYERS, feature, 12);
}

/** The width in pixels layer `id` draws its lines in at `zoom`. */
function lineWidthAt(id: string, zoom: number): number {
  const layer = BOUNDARY_LAYERS.find((candidate) => candidate.id === id) as LineLayerSpecification;
  const width = normalizePropertyExpression(
    layer.paint?.['line-width'],
    'line-width',
    // See testing/textField.ts: the style-spec JSON's type is looser than the parameter's.
    latest.paint_line['line-width'] as unknown as Parameters<typeof normalizePropertyExpression>[2],
  );
  return width.evaluate({ zoom });
}

// In Schleswig-Holstein: 7 an Amt, 8 a Gemeinde.
it.each([7, 8])('draws a municipal boundary of admin_level %i by its own layer', (adminLevel) => {
  expect(layersDrawingLandBoundary(adminLevel)).toEqual(['boundary-land-municipal']);
});

// 4 a Land, 6 a Kreis.
it.each([4, 6])('leaves a boundary of admin_level %i to the regional layer', (adminLevel) => {
  expect(layersDrawingLandBoundary(adminLevel)).toEqual(['boundary-land-level-4']);
});

it.each([8, 10, 12, 14, 16])(
  'draws a municipal boundary thinner than a regional one at z%i',
  (zoom) => {
    expect(lineWidthAt('boundary-land-municipal', zoom)).toBeLessThan(
      lineWidthAt('boundary-land-level-4', zoom),
    );
  },
);
