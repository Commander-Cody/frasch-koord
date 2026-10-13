import { useImperativeHandle } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { LngLat, MapGeoJSONFeature } from 'maplibre-gl';

import i18n from './i18n';
import { LOCAL_TAG } from './config';
import type { MapViewProps } from './components/Map';
import type { NameEntry } from './names';
import App from './App';

// How a place gets selected and what the map does about it: the real side
// panel, with the map stubbed (MapLibre needs WebGL, which jsdom has not).
// The stub keeps what App gives it and records what App asks of it.
const map = vi.hoisted(() => ({
  select: undefined as MapViewProps['onSelectFeature'],
  marker: undefined as MapViewProps['marker'],
  flyTo: vi.fn(),
  reveal: vi.fn(),
}));
vi.mock('./components/Map', () => ({
  default: function MapStub({ onSelectFeature, marker, ref }: MapViewProps) {
    map.select = onSelectFeature;
    map.marker = marker;
    useImperativeHandle(ref, () => ({ getMap: () => null, flyTo: map.flyTo, reveal: map.reveal }));
    return <div className="map-container" />;
  },
}));

const naibel: NameEntry = {
  id: 'naibel',
  names: { 'frr-x-mooring': 'Naibel' },
  name_nds: 'Neebüll',
  name_de: 'Niebüll',
  lon: 8.83,
  lat: 54.79,
  kind: 'settlement',
};
const feer: NameEntry = {
  id: 'feer',
  names: { 'frr-x-mooring': 'Feer' },
  name_de: 'Föhr',
  lon: 8.5,
  lat: 54.72,
  kind: 'island',
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

/** The app at `url`, with the name list loaded. */
async function openApp(url = '/') {
  window.history.replaceState(null, '', url);
  const serveNames = holdNames([naibel, feer]);
  render(<App />);
  await serveNames();
}

const NAIBEL_LABEL = { lng: 8.829, lat: 54.788 } as LngLat;

/** A click on Naibel's map label; `null` for a click that hits no label. */
function clickMap(ref: string | null) {
  const feature = { id: 2400427661, properties: { 'frasch:ref': ref, 'name:de': 'Niebüll' } };
  act(() => map.select?.(ref ? (feature as unknown as MapGeoJSONFeature) : null, NAIBEL_LABEL));
}

/** Picks the first search result for `query`. */
function pick(query: string) {
  const field = screen.getByRole('combobox', { name: i18n.t('search.label') });
  fireEvent.change(field, { target: { value: query } });
  fireEvent.keyDown(field, { key: 'Enter' });
}

function switchView(tag: string) {
  const selector = screen.getByRole('combobox', { name: i18n.t('dialect.label') });
  fireEvent.change(selector, { target: { value: tag } });
}

function placeInUrl(): string | null {
  return new URLSearchParams(window.location.search).get('place');
}

beforeEach(() => {
  map.flyTo.mockClear();
  map.reveal.mockClear();
  // Browser APIs jsdom has not; a desktop, where no sheet covers the map.
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
  vi.restoreAllMocks();
});

it('flies to a search pick, as close as its kind wants', async () => {
  await openApp();

  pick('Feer');

  expect(map.flyTo).toHaveBeenCalledWith([8.5, 54.72], 11, 0);
});

it('marks a search pick with its name', async () => {
  await openApp();

  pick('Naibel');

  expect(map.marker).toEqual({ at: [8.83, 54.79], title: 'Naibel' });
});

it("names the marker in the view switched to, like the place's label", async () => {
  await openApp();
  pick('Naibel');

  switchView(LOCAL_TAG);

  expect(map.marker?.title).toBe('Neebüll');
});

it('leaves the map where it is for a click on a label', async () => {
  await openApp();

  clickMap('naibel');

  expect(map.flyTo).not.toHaveBeenCalled();
});

it('reveals a clicked label the card would cover', async () => {
  await openApp();

  clickMap('naibel');

  expect(map.reveal).toHaveBeenCalledWith(NAIBEL_LABEL, 0);
});

it('takes the marker of a search pick away for a click on a label', async () => {
  await openApp();
  pick('Feer');

  clickMap('naibel');

  expect(map.marker).toBeNull();
});

it('does not move the map again when the name list arrives after the click', async () => {
  const serveNames = holdNames([naibel]);
  render(<App />);
  clickMap('naibel');

  await serveNames();

  expect(map.reveal).toHaveBeenCalledTimes(1);
});

it('lands a search pick in what the bottom sheet of a phone leaves of the map', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(240);
  await openApp();

  pick('Naibel');

  expect(map.flyTo).toHaveBeenCalledWith([8.83, 54.79], 14, 240);
});

it('flies to the place of a link that does not say where to look', async () => {
  await openApp('/?place=naibel');

  expect(map.flyTo).toHaveBeenCalledWith([8.83, 54.79], 14, 0);
});

it('marks the place of a link', async () => {
  await openApp('/?place=naibel');

  expect(map.marker).toEqual({ at: [8.83, 54.79], title: 'Naibel' });
});

it('keeps the viewport of a link that has one', async () => {
  await openApp('/?place=naibel#9/54.6/8.9');

  expect(map.flyTo).not.toHaveBeenCalled();
});

it('reveals the place of a link with a viewport, should the card cover it', async () => {
  await openApp('/?place=naibel#9/54.6/8.9');

  expect(map.reveal).toHaveBeenCalledWith([8.83, 54.79], 0);
});

it('takes a hash the map wrote after the page opened for no viewport of the link', async () => {
  window.history.replaceState(null, '', '/?place=naibel');
  const serveNames = holdNames([naibel]);
  render(<App />);
  window.history.replaceState(null, '', '/?place=naibel#9/54.6/8.9');

  await serveNames();

  expect(map.flyTo).toHaveBeenCalledTimes(1);
});

it('opens the card of a linked place', async () => {
  await openApp('/?place=naibel');

  expect(screen.getByRole('heading').textContent).toBe('Naibel');
});

it('keeps a card opened by hand while the list loads, whatever the link names', async () => {
  window.history.replaceState(null, '', '/?place=feer');
  const serveNames = holdNames([naibel, feer]);
  render(<App />);
  clickMap('naibel');

  await serveNames();

  expect(screen.getByRole('heading').textContent).toBe('Naibel');
});

it('does not fly to the linked place once a card was opened by hand', async () => {
  window.history.replaceState(null, '', '/?place=feer');
  const serveNames = holdNames([naibel, feer]);
  render(<App />);
  clickMap('naibel');

  await serveNames();

  expect(map.flyTo).not.toHaveBeenCalled();
});

it('never takes the linked place out of the address bar while its list loads', async () => {
  window.history.replaceState(null, '', '/?place=naibel');
  const written: string[] = [];
  const replaceState = window.history.replaceState.bind(window.history);
  vi.spyOn(window.history, 'replaceState').mockImplementation((...args) => {
    replaceState(...args);
    written.push(window.location.search);
  });
  const serveNames = holdNames([naibel]);
  render(<App />);

  await serveNames();

  expect(written.filter((search) => !search.includes('place=naibel'))).toEqual([]);
});

it('keeps the linked place in the address bar when its list fails to load: a reload may find it', async () => {
  window.history.replaceState(null, '', '/?place=naibel');
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.stubGlobal('fetch', async () => new Response('', { status: 500 }));
  render(<App />);

  await screen.findByRole('alert');

  expect(placeInUrl()).toBe('naibel');
});

it('drops a link to a place the name list does not have', async () => {
  await openApp('/?place=nowhere');

  expect(placeInUrl()).toBeNull();
});

it('puts the place of the open card into the address bar', async () => {
  await openApp();

  pick('Naibel');

  expect(placeInUrl()).toBe('naibel');
});

it('takes the place out of the address bar when the card closes', async () => {
  await openApp('/?place=naibel');

  clickMap(null);

  expect(placeInUrl()).toBeNull();
});

it('takes the marker away when the card closes', async () => {
  await openApp('/?place=naibel');

  clickMap(null);

  expect(map.marker).toBeNull();
});
