import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

import { namesUrl, useNames } from './names';

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

describe('useNames', () => {
  // The failure is logged; keep the test output clean.
  const quiet = () => vi.spyOn(console, 'error').mockImplementation(() => {});

  it('loads the list', async () => {
    stubFetch(JSON.stringify([{ id: 'node/1', names: {}, name_de: 'Niebüll', lon: 8, lat: 54, kind: 'settlement' }]), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
    const { result } = renderHook(() => useNames());
    expect(result.current.status).toBe('loading');
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.entries).toHaveLength(1);
    expect(result.current.byRef.get('node/1')?.name_de).toBe('Niebüll');
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

  it('ends in error on JSON that is not a list', async () => {
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
    const fetch = stubFetch('[]', { status: 200 });
    const { result } = renderHook(() => useNames());
    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(fetch).toHaveBeenCalledWith(`${window.location.origin}/frasch-koord/data/names.json`);
  });
});
