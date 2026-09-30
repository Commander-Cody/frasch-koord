import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { LngLat, MapGeoJSONFeature } from 'maplibre-gl';

import './i18n';
import type { MapViewProps } from './components/Map';
import type { NameEntry } from './names';
import App from './App';

// The side panel as a visitor uses it: the real search panel and place card,
// with the map stubbed (MapLibre needs WebGL, which jsdom has not). The stub
// keeps the click handler App gives it, so a test can click a map label.
const map = vi.hoisted(() => ({ select: undefined as MapViewProps['onSelectFeature'] }));
vi.mock('./components/Map', () => ({
  default: function MapStub({ onSelectFeature }: MapViewProps) {
    map.select = onSelectFeature;
    return <div className="map-container" />;
  },
}));

const naibel: NameEntry = {
  id: 'naibel',
  osm: 'node/240042766',
  names: { 'frr-x-mooring': 'Naibel' },
  name_de: 'Niebüll',
  name_da: 'Nibøl',
  wikidata: 'Q21019',
  lon: 8.83,
  lat: 54.79,
  kind: 'settlement',
};

/** Serves names.json once the test calls the returned function. */
function holdNames(entries: NameEntry[]): () => Promise<void> {
  let serve!: () => void;
  const served = new Promise<void>((resolve) => (serve = resolve));
  vi.stubGlobal('fetch', async () => {
    await served;
    return new Response(JSON.stringify({ built_from: {}, places: entries }), { status: 200 });
  });
  return async () => {
    await act(async () => serve());
  };
}

/** A click on the map label of the name-list row `ref`, as the tiles carry it. */
function clickLabel(ref: string, props: Record<string, string>) {
  const feature = { id: 2400427660, properties: { 'frasch:ref': ref, ...props } } as unknown as MapGeoJSONFeature;
  act(() => map.select?.(feature, { lng: 8.83, lat: 54.79 } as LngLat));
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
  // Browser APIs jsdom has not; the layout they measure is not under test.
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('gives a card opened before the name list loads its curated data once the list is there', async () => {
  const serveNames = holdNames([naibel]);
  render(<App />);

  clickLabel('naibel', { 'name:frr-x-mooring': 'Naibel', 'name:de': 'Niebüll' });
  await serveNames();

  expect(screen.getByText('Nibøl')).toBeDefined();
  expect(screen.getByRole('link', { name: 'Wikidata' })).toBeDefined();
  expect(new URLSearchParams(window.location.search).get('place')).toBe('naibel');
});

it('leaves the card open on Escape in the search field, and closes it on Escape elsewhere', async () => {
  const serveNames = holdNames([naibel]);
  render(<App />);
  await serveNames();
  clickLabel('naibel', { 'name:frr-x-mooring': 'Naibel' });
  const field = screen.getByRole('combobox', { name: 'Ort suchen' });
  fireEvent.change(field, { target: { value: 'Nai' } });

  // The first Escape closes the result list, a second one finds nothing
  // left to close in the field; neither is meant for the card.
  fireEvent.keyDown(field, { key: 'Escape' });
  expect(screen.queryByRole('listbox')).toBeNull();
  fireEvent.keyDown(field, { key: 'Escape' });
  expect(screen.getByRole('heading', { name: 'Naibel' })).toBeDefined();

  fireEvent.keyDown(document.body, { key: 'Escape' });
  expect(screen.queryByRole('heading', { name: 'Naibel' })).toBeNull();
});
