import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, renderHook } from '@testing-library/react';

import { FakeMap } from '../../testing/fakeMap';
import { useHintCircle, type HintPoint } from './hintCircle';

afterEach(cleanup);

/** What the circle of `hint` puts in its source on a fake map. */
function drawn(hint: HintPoint | null): unknown {
  const fake = new FakeMap();
  renderHook(() => useHintCircle(fake.map, hint));
  return fake.sourceData('curate-hint-circle');
}

describe('useHintCircle', () => {
  // 11.132 km is 0.1° of latitude, at the 111.32 km a degree the circle reckons with.
  it("reaches as far north and south of the hint's point as its radius says", () => {
    const circle = drawn([8.8, 54.5, 11.132]) as { geometry: { coordinates: number[][][] } };
    const lats = circle.geometry.coordinates[0].map(([, lat]) => lat);
    expect([Math.min(...lats), Math.max(...lats)].map((lat) => lat.toFixed(6))).toEqual([
      '54.400000',
      '54.600000',
    ]);
  });

  it('draws nothing for a row without a hint', () => {
    expect(drawn(null)).toEqual({ type: 'FeatureCollection', features: [] });
  });
});
