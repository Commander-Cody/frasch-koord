import { afterEach, expect, it, vi } from 'vitest';
import { forwardRef } from 'react';
import { render, screen } from '@testing-library/react';

import './i18n';

// MapLibre needs WebGL, which jsdom has not; a bare container stands in for
// it, which is all this test needs: whether it survives.
vi.mock('./components/Map', () => ({
  default: forwardRef(function MapStub() {
    return <div className="map-container" data-testid="map" />;
  }),
}));

// A card that trips over a malformed names.json entry.
vi.mock('./components/PlaceCard', () => ({
  default: function BrokenCard(): never {
    throw new Error('malformed entry');
  },
}));

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('keeps the map when the place card crashes', async () => {
  // React and ErrorBoundary both log the crash.
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const entry = { id: 'node/1', names: {}, name_de: 'Niebüll', lon: 8.83, lat: 54.79, kind: 'settlement' };
  vi.stubGlobal('fetch', async () => new Response(JSON.stringify([entry]), { status: 200 }));
  // A link to the place opens its card as soon as the name list is there.
  // App reads the link at module load, so set it before importing App.
  window.history.replaceState(null, '', '/?place=node/1');
  const { default: App } = await import('./App');

  render(<App />);

  expect(await screen.findByRole('alert')).toHaveProperty('className', 'panel-error');
  expect(screen.getByTestId('map')).toBeDefined();
});
