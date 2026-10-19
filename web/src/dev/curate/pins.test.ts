import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, renderHook } from '@testing-library/react';

import { FakeMap, FakeMarker } from '../../testing/fakeMap';
import { candidateColor, useRowPins, type RowPinsOptions } from './pins';
import type { LookupResult } from './osmLookup';
import type { CurateCandidate, CurateRow } from './worklist';

vi.mock('maplibre-gl', async (actual) => ({
  ...(await actual<typeof import('maplibre-gl')>()),
  Marker: FakeMarker,
}));

afterEach(cleanup);

const SETTLEMENT_PLACES = ['village', 'town'];

/** A candidate of `placeClass` at `at`, or without a position. */
function candidate(
  ref: string,
  placeClass: string,
  at: [number, number] | null = [8.8, 54.8],
): CurateCandidate {
  const [lon, lat] = at ?? [null, null];
  return { ref, name: ref, class: placeClass, km: 1, lon, lat, tags: '', in_sh: true };
}

describe('candidateColor', () => {
  const colorOf = (ref: string, placeClass: string) =>
    candidateColor(candidate(ref, placeClass), SETTLEMENT_PLACES);

  it('colours a settlement by its class, whatever its OSM type', () => {
    expect(colorOf('way/1', 'village')).toBe(colorOf('node/1', 'village'));
  });

  it('colours a way and a relation alike, as areas', () => {
    expect(colorOf('way/1', 'farmland')).toBe(colorOf('relation/1', 'boundary'));
  });

  it('tells a settlement, an area and any other object apart', () => {
    const colors = [
      colorOf('node/1', 'town'),
      colorOf('way/1', 'farmland'),
      colorOf('node/2', 'church'),
    ];
    expect(new Set(colors).size).toBe(3);
  });
});

describe('useRowPins', () => {
  /** A worklist row with `candidates`, and a location hint where given: what the pins read of it. */
  function row(candidates: CurateCandidate[], hint_point: CurateRow['hint_point'] = null) {
    return { id: 'naibel', candidates, hint: 'near Niebüll', hint_point } as CurateRow;
  }

  /** Puts the pins of `options` on a fake map; -> the pin elements in the document. */
  function renderPins(options: Partial<RowPinsOptions>) {
    const all: RowPinsOptions = {
      row: row([]),
      bbox: [8, 54, 9, 55],
      settlementPlaces: SETTLEMENT_PLACES,
      lookupResults: [],
      checked: [],
      onActivate: () => {},
      onToggle: () => {},
      ...options,
    };
    return renderHook(() => useRowPins(new FakeMap().map, all));
  }

  /** The pin of `ref`, by the title it is given. */
  function pinOf(ref: string): HTMLElement {
    const pin = [...document.querySelectorAll<HTMLElement>('.curate-pin')].find((el) =>
      el.title.startsWith(`${ref} `),
    );
    if (!pin) throw new Error(`no pin of ${ref}`);
    return pin;
  }

  const pinLabels = () =>
    [...document.querySelectorAll('.curate-pin')].map((pin) => pin.textContent);

  it("numbers the pins by their candidate's place in the row, leaving out one without a position", () => {
    const candidates = [
      candidate('node/1', 'village'),
      candidate('node/2', 'village', null),
      candidate('node/3', 'village'),
    ];

    renderPins({ row: row(candidates) });

    expect(pinLabels()).toEqual(['1', '3']);
  });

  it("pins the row's location hint", () => {
    renderPins({ row: row([], [8.8, 54.8, 5]) });

    expect(document.querySelector('.curate-pin-hint')?.getAttribute('title')).toBe(
      'location hint: near Niebüll (5 km)',
    );
  });

  it('pins the lookup results', () => {
    const result: LookupResult = {
      ref: 'way/8',
      name: 'Niebüll',
      what: 'town',
      lon: 8.8,
      lat: 54.8,
    };

    renderPins({ lookupResults: [result] });

    expect(pinOf('way/8').classList.contains('curate-pin-lookup')).toBe(true);
  });

  it('marks the pins of what is ticked', () => {
    const candidates = [candidate('node/1', 'village'), candidate('node/2', 'village')];

    renderPins({ row: row(candidates), checked: [{ ref: 'node/2' }] });

    const marked = (ref: string) => pinOf(ref).classList.contains('curate-pin-checked');
    expect([marked('node/1'), marked('node/2')]).toEqual([false, true]);
  });

  it('activates a candidate on a click on its pin', () => {
    const onActivate = vi.fn();
    renderPins({ row: row([candidate('node/1', 'village')]), onActivate });

    fireEvent.click(pinOf('node/1'));

    expect(onActivate).toHaveBeenCalledWith('node/1');
  });

  it('ticks a candidate on a shift-click on its pin', () => {
    const onToggle = vi.fn();
    const tagged = { ...candidate('node/1', 'village'), wikidata: 'Q1' };
    renderPins({ row: row([tagged]), onToggle });

    fireEvent.click(pinOf('node/1'), { shiftKey: true });

    expect(onToggle).toHaveBeenCalledWith('node/1', 'Q1');
  });

  it('takes its pins off the map when it goes', () => {
    const { unmount } = renderPins({ row: row([candidate('node/1', 'village')], [8.8, 54.8, 5]) });

    unmount();

    expect(pinLabels()).toEqual([]);
  });
});
