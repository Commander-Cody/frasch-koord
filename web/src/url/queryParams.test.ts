import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  hasQueryParam,
  hasViewport,
  keepingHash,
  pageUrl,
  readQueryParam,
  replaceQueryParams,
  resolvedOnPage,
} from './queryParams';

function setLocation(url: string) {
  window.history.replaceState(null, '', url);
}

beforeEach(() => {
  setLocation('/');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('readQueryParam', () => {
  it('reads a value, slash and all', () => {
    setLocation('/?view=frr-x-fering&place=node%2F123');
    expect(readQueryParam('place')).toBe('node/123');
  });

  it('has nothing for a parameter the URL lacks', () => {
    setLocation('/?foo=bar');
    expect(readQueryParam('place')).toBeUndefined();
  });

  it('treats an empty value the same as a missing one', () => {
    setLocation('/?place=');
    expect(readQueryParam('place')).toBeUndefined();
  });

  it('takes the first value of a repeated parameter', () => {
    setLocation('/?view=frr-x-mooring&view=frr-x-fering');
    expect(readQueryParam('view')).toBe('frr-x-mooring');
  });

  it("does not look into MapLibre's viewport hash", () => {
    setLocation('/#12/54.79/8.83?place=naibel');
    expect(readQueryParam('place')).toBeUndefined();
  });
});

describe('hasQueryParam', () => {
  it('sees a parameter without a value', () => {
    setLocation('/?curate');
    expect(hasQueryParam('curate')).toBe(true);
  });

  it('does not see one the URL lacks', () => {
    setLocation('/?areas');
    expect(hasQueryParam('curate')).toBe(false);
  });
});

describe('replaceQueryParams', () => {
  it("sets a parameter, keeping the others and MapLibre's viewport hash", () => {
    setLocation('/?curate#12/54.79/8.83');
    replaceQueryParams({ row: 'schorkewarw-2' });
    expect(`${window.location.search}${window.location.hash}`).toBe(
      '?curate=&row=schorkewarw-2#12/54.79/8.83',
    );
  });

  it('removes a parameter without a value, and the ? with the last one', () => {
    setLocation('/?area=relation/1147134#12/54.79/8.83');
    replaceQueryParams({ area: undefined });
    expect(window.location.href).toBe(`${window.location.origin}/#12/54.79/8.83`);
  });

  it('writes a slash in a value as it is: `node/123` reads better than node%2F123 in a link', () => {
    replaceQueryParams({ area: 'relation/1147134' });
    expect(window.location.search).toBe('?area=relation/1147134');
  });

  it('leaves history alone when nothing changes', () => {
    setLocation('/?curate=&row=schorkewarw-2');
    const replaceState = vi.spyOn(window.history, 'replaceState');
    replaceQueryParams({ row: 'schorkewarw-2' });
    expect(replaceState).not.toHaveBeenCalled();
  });

  it('adds no step for the back button', () => {
    const pushState = vi.spyOn(window.history, 'pushState');
    replaceQueryParams({ view: 'frr-x-fering' });
    expect(pushState).not.toHaveBeenCalled();
  });
});

describe('hasViewport', () => {
  it('sees the viewport a link carries', () => {
    setLocation('/?place=naibel#12/54.79/8.83');
    expect(hasViewport()).toBe(true);
  });

  it('sees none in a link without a hash', () => {
    setLocation('/?place=naibel');
    expect(hasViewport()).toBe(false);
  });
});

describe('pageUrl', () => {
  it('is the whole address, query and viewport included', () => {
    setLocation('/?view=frr-x-local&place=naibel#12/54.79/8.83');
    expect(pageUrl()).toBe(
      `${window.location.origin}/?view=frr-x-local&place=naibel#12/54.79/8.83`,
    );
  });
});

describe('resolvedOnPage', () => {
  it('resolves a relative URL against the page', () => {
    setLocation('/frasch-koord/?place=naibel');
    expect(resolvedOnPage('./')).toBe(`${window.location.origin}/frasch-koord/`);
  });
});

describe('keepingHash', () => {
  it('puts back the hash the action removed, with the query as it was', () => {
    setLocation('/?place=naibel#12/54.79/8.83');
    keepingHash(() => setLocation('/?place=naibel'));
    expect(`${window.location.search}${window.location.hash}`).toBe('?place=naibel#12/54.79/8.83');
  });

  it('writes nothing where there was no hash', () => {
    const replaceState = vi.spyOn(window.history, 'replaceState');
    keepingHash(() => {});
    expect(replaceState).not.toHaveBeenCalled();
  });
});

/** Every module under src/ that is not a test, by path. */
const MODULES = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

it("is the only module that touches the page's URL", () => {
  const touching = Object.entries(MODULES)
    .filter(([, source]) => /\bwindow\.(location|history)\b/.test(source))
    .map(([file]) => file);
  expect(touching).toEqual(['./queryParams.ts']);
});
