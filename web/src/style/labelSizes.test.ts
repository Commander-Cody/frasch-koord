import { describe, expect, it } from 'vitest';
import { latest, normalizePropertyExpression } from '@maplibre/maplibre-gl-style-spec';
import type { StyleSpecification, SymbolLayerSpecification } from 'maplibre-gl';

import fraschBright from './frasch-bright.json';

const style = fraschBright as unknown as StyleSpecification;
const MAX_ZOOM = 20;

function symbolLayer(id: string): SymbolLayerSpecification {
  const layer = style.layers.find((candidate) => candidate.id === id);
  if (layer?.type !== 'symbol') throw new Error(`no symbol layer ${id}`);
  return layer;
}

/** The layer's `text-size` in px at a zoom, by MapLibre's own evaluation. */
function textSize(layer: SymbolLayerSpecification, zoom: number): number {
  const spec = latest.layout_symbol['text-size'] as unknown as Parameters<
    typeof normalizePropertyExpression
  >[2];
  const size = layer.layout?.['text-size'] ?? spec.default;
  return normalizePropertyExpression(size, 'text-size', spec).evaluate({ zoom }) as number;
}

function zoomsFrom(minZoom: number): number[] {
  return Array.from({ length: MAX_ZOOM - minZoom + 1 }, (_, index) => minZoom + index);
}

describe('label sizes', () => {
  // A Warft is a place name; a bus stop (poi-level-*) is map furniture next
  // to it and must not out-shout it.
  const warft = symbolLayer('place-warft');
  const poi = symbolLayer('poi-level-1');

  it.each(zoomsFrom(warft.minzoom ?? 0))(
    'a Warft is labelled no smaller than a POI at z%i',
    (zoom) => {
      expect(textSize(warft, zoom)).toBeGreaterThanOrEqual(textSize(poi, zoom));
    },
  );
});
