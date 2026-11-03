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

function boundaryLayer(id: string): LineLayerSpecification {
  return BOUNDARY_LAYERS.find((candidate) => candidate.id === id) as LineLayerSpecification;
}

/** The width in pixels layer `id` draws its lines in at `zoom`. */
function lineWidthAt(id: string, zoom: number): number {
  const width = normalizePropertyExpression(
    boundaryLayer(id).paint?.['line-width'],
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

it('draws a Kreis boundary by its own layer', () => {
  expect(layersDrawingLandBoundary(6)).toEqual(['boundary-land-district']);
});

it('leaves a Land boundary to the regional layer', () => {
  expect(layersDrawingLandBoundary(4)).toEqual(['boundary-land-level-4']);
});

const ZOOMS = [8, 10, 12, 14, 16];

it.each(ZOOMS)('draws a municipal boundary thinner than a Kreis boundary at z%i', (zoom) => {
  expect(lineWidthAt('boundary-land-municipal', zoom)).toBeLessThan(
    lineWidthAt('boundary-land-district', zoom),
  );
});

it.each(ZOOMS)('draws a Kreis boundary thinner than a Land boundary at z%i', (zoom) => {
  expect(lineWidthAt('boundary-land-district', zoom)).toBeLessThan(
    lineWidthAt('boundary-land-level-4', zoom),
  );
});

it('draws Kreis and municipal boundaries in the same colour', () => {
  expect(boundaryLayer('boundary-land-district').paint?.['line-color']).toBe(
    boundaryLayer('boundary-land-municipal').paint?.['line-color'],
  );
});
