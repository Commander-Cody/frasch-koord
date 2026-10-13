import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import type { NameEntry } from './entry';
import { entryLookup, namesUrl, parseNames, useNames } from './load';

/** A minimal, otherwise-empty entry, for tests that only care about a few fields. */
function entry(fields: Partial<NameEntry> = {}): NameEntry {
  return { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '', ...fields };
}

function stubFetch(body: string, init: ResponseInit) {
  const fetch = vi.fn(async () => new Response(body, init));
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('parseNames', () => {
  const NAIBEL = {
    id: 'naibel',
    names: {},
    name_de: 'Niebüll',
    lon: 8,
    lat: 54,
    kind: 'settlement',
  };
  const quiet = () => vi.spyOn(console, 'warn').mockImplementation(() => {});

  it('is the places of the file and what it was built from', () => {
    const builtFrom = { 'places.csv': 'aaa', extracts: [] };

    expect(parseNames({ built_from: builtFrom, places: [NAIBEL] })).toEqual({
      entries: [NAIBEL],
      builtFrom,
    });
  });

  it('drops a place without an id', () => {
    quiet();

    const { entries } = parseNames({ places: [{ ...NAIBEL, id: undefined }, NAIBEL] });

    expect(entries).toEqual([NAIBEL]);
  });

  it('drops a second place with an id already taken', () => {
    quiet();
    const twin = { ...NAIBEL, name_de: 'Naibel' };

    const { entries } = parseNames({ places: [NAIBEL, twin] });

    expect(entries).toEqual([NAIBEL]);
  });

  it('says how many places it dropped', () => {
    const warn = quiet();

    parseNames({ places: [NAIBEL, NAIBEL, { ...NAIBEL, id: '' }] });

    expect(warn).toHaveBeenCalledExactlyOnceWith(
      'names.json: skipped 2 places without an id or with a repeated one',
    );
  });

  it('refuses a file without a list of places', () => {
    expect(() => parseNames({ entries: [] })).toThrow('no list of places');
  });
});

describe('useNames', () => {
  // The failure is logged; keep the test output clean.
  const quiet = () => vi.spyOn(console, 'error').mockImplementation(() => {});

  it('loads the list', async () => {
    stubFetch(
      JSON.stringify({
        built_from: { 'places.csv': 'aaa' },
        places: [
          { id: 'naibel', names: {}, name_de: 'Niebüll', lon: 8, lat: 54, kind: 'settlement' },
        ],
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
    const { result } = renderHook(() => useNames());
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.entries).toHaveLength(1);
    expect(result.current.find('naibel')?.name_de).toBe('Niebüll');
    expect(result.current.builtFrom).toEqual({ 'places.csv': 'aaa' });
  });

  it('ends in error on a 404', async () => {
    quiet();
    stubFetch('Not Found', { status: 404 });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.entries).toEqual([]);
  });

  it('ends in error on an SPA fallback (200 text/html)', async () => {
    quiet();
    stubFetch('<!doctype html><html><body><div id="root"></div></body></html>', {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('error'));
  });

  it('ends in error on JSON without a list of places', async () => {
    quiet();
    stubFetch('{"entries": []}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('error'));
  });
});

describe('namesUrl', () => {
  it('is under the root by default', () => {
    expect(namesUrl()).toBe(`${window.location.origin}/data/names.json`);
  });

  it('respects a non-root base', async () => {
    vi.stubEnv('BASE_URL', '/frasch-koord/');
    expect(namesUrl()).toBe(`${window.location.origin}/frasch-koord/data/names.json`);
    const fetch = stubFetch('{"built_from": {}, "places": []}', { status: 200 });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/frasch-koord/data/names.json`);
  });
});

describe('entryLookup', () => {
  // Two rows on one dyke (two spellings), a row claiming two objects, a country.
  const lungedik = entry({ id: 'lungedik', osm: 'way/28330569', name_de: 'Langerdeich' });
  const lungdiik = entry({ id: 'lungdiik', osm: 'way/28330569', name_de: 'Langerdeich' });
  const nordwarw = entry({ id: 'nordwarw', osm: 'way/1347936331; node/1332249790' });
  const danemark = entry({ id: 'danemark', wikidata: 'Q35' });
  const find = entryLookup([lungedik, lungdiik, nordwarw, danemark]);

  it('finds an entry by its row id', () => {
    expect(find('lungdiik')).toBe(lungdiik);
  });

  it('still opens an old ?place=node/… link: the first row on that object', () => {
    expect(find('way/28330569')).toBe(lungedik);
    expect(find('node/1332249790')).toBe(nordwarw);
  });

  it('still opens an old ?place=<ref>#<line> link, at the first row on that object', () => {
    expect(find('way/28330569#679')).toBe(lungedik);
  });

  it('still opens an old ?place=<QID> link of a country', () => {
    expect(find('Q35')).toBe(danemark);
  });

  it('finds nothing for an unknown reference', () => {
    expect(find('node/1')).toBeUndefined();
    expect(find('nobody')).toBeUndefined();
  });
});
