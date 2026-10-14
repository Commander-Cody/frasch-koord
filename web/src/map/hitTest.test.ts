import { afterEach, expect, it, vi } from 'vitest';
import type { MapGeoJSONFeature, Point, PointLike } from 'maplibre-gl';

import { placeHitTest } from './hitTest';
import type { HitTestMap } from './hitTest';

afterEach(() => {
  vi.unstubAllGlobals();
});

interface Label {
  layer: string;
  x: number;
  y: number;
  feature: MapGeoJSONFeature;
}

function label(layer: string, x: number, y: number): Label {
  return { layer, x, y, feature: { id: `${layer}@${x},${y}` } as unknown as MapGeoJSONFeature };
}

/**
 * A map with labels painted at points, topmost first. Like MapLibre, it
 * refuses to query a layer its style does not have.
 */
function fakeMap(labels: Label[], styleLayers: string[]): HitTestMap {
  return {
    getLayer: ((id: string) =>
      styleLayers.includes(id) ? {} : undefined) as HitTestMap['getLayer'],
    queryRenderedFeatures: ((box: [PointLike, PointLike], { layers }: { layers: string[] }) => {
      for (const id of layers) if (!styleLayers.includes(id)) throw new Error(`no layer ${id}`);
      const [[x0, y0], [x1, y1]] = box as [[number, number], [number, number]];
      return labels
        .filter((l) => layers.includes(l.layer) && l.x >= x0 && l.x <= x1 && l.y >= y0 && l.y <= y1)
        .map((l) => l.feature);
    }) as HitTestMap['queryRenderedFeatures'],
  };
}

/** A point on the map's canvas. */
function at(x: number, y: number): Point {
  return { x, y } as Point;
}

function pointer(touch: boolean): void {
  vi.stubGlobal('matchMedia', () => ({ matches: touch }));
}

it('hits the topmost label a few pixels off the mouse pointer', () => {
  pointer(false);
  const [top, below] = [label('place-town', 105, 100), label('place-village', 100, 104)];
  const hit = placeHitTest(fakeMap([top, below], ['place-town', 'place-village']), [
    'place-town',
    'place-village',
  ]);

  expect(hit(at(100, 100))).toBe(top.feature);
});

it('misses a label further off the mouse pointer', () => {
  pointer(false);
  const hit = placeHitTest(fakeMap([label('place-town', 110, 100)], ['place-town']), [
    'place-town',
  ]);

  expect(hit(at(100, 100))).toBeUndefined();
});

it('hits that label with a finger', () => {
  pointer(true);
  const town = label('place-town', 110, 100);
  const hit = placeHitTest(fakeMap([town], ['place-town']), ['place-town']);

  expect(hit(at(100, 100))).toBe(town.feature);
});

it('leaves out a label layer the style in flight has not added yet', () => {
  pointer(false);
  const town = label('place-town', 100, 100);
  const hit = placeHitTest(fakeMap([town], ['place-town']), ['place-town', 'place-village']);

  expect(hit(at(100, 100))).toBe(town.feature);
});
