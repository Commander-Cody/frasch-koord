import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { LayerSpecification } from 'maplibre-gl';

import { FakeMap } from '../../testing/fakeMap';
import { useGeoJsonOverlay, type GeoJsonOverlay, type OverlayData } from './useGeoJsonOverlay';

const FILL: LayerSpecification = { id: 'test-fill', type: 'fill', source: 'test' };
const LINE: LayerSpecification = { id: 'test-line', type: 'line', source: 'test' };

const EMPTY: OverlayData = { type: 'FeatureCollection', features: [] };

/** The map with one label layer of its own, which the overlay has to stay under. */
function mapWithLabels(): FakeMap {
  const fake = new FakeMap();
  fake.addLayer({ id: 'place-label' });
  return fake;
}

const POINT: OverlayData = {
  type: 'Feature',
  properties: {},
  geometry: { type: 'Point', coordinates: [8.9, 54.6] },
};

/** The overlay's props, a test's own over the defaults. */
function overlay(own: Partial<GeoJsonOverlay> = {}): GeoJsonOverlay {
  return { source: 'test', data: EMPTY, layers: [FILL, LINE], ...own };
}

describe('useGeoJsonOverlay', () => {
  it('draws its layers under the one it is told to stay below', () => {
    const fake = mapWithLabels();
    renderHook(() =>
      useGeoJsonOverlay(fake.map, {
        source: 'test',
        data: EMPTY,
        layers: [FILL, LINE],
        beforeId: 'place-label',
      }),
    );
    expect(fake.layerIds()).toEqual(['test-fill', 'test-line', 'place-label']);
  });

  it('shows new data', () => {
    const fake = new FakeMap();
    const { rerender } = renderHook((props: GeoJsonOverlay) => useGeoJsonOverlay(fake.map, props), {
      initialProps: overlay(),
    });
    rerender(overlay({ data: POINT }));
    expect(fake.sourceData('test')).toBe(POINT);
  });

  it("applies a layer's new filter", () => {
    const fake = new FakeMap();
    const { rerender } = renderHook((props: GeoJsonOverlay) => useGeoJsonOverlay(fake.map, props), {
      initialProps: overlay(),
    });
    rerender(
      overlay({ layers: [{ ...FILL, filter: ['==', ['get', 'osm'], 'relation/1'] }, LINE] }),
    );
    expect(fake.filterOf('test-fill')).toEqual(['==', ['get', 'osm'], 'relation/1']);
  });

  it('leaves the map as it was once unmounted', () => {
    const fake = mapWithLabels();
    const { unmount } = renderHook(() =>
      useGeoJsonOverlay(fake.map, overlay({ beforeId: 'place-label' })),
    );
    unmount();
    expect(fake.layerIds()).toEqual(['place-label']);
    expect(fake.getSource('test')).toBeUndefined();
  });
});
