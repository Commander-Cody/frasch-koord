import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { replaceQueryParams } from './queryParams';

beforeEach(() => {
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('replaceQueryParams', () => {
  it("sets a parameter, keeping the others and MapLibre's viewport hash", () => {
    window.history.replaceState(null, '', '/?curate#12/54.79/8.83');
    replaceQueryParams({ row: 'schorkewarw-2' });
    expect(`${window.location.search}${window.location.hash}`).toBe(
      '?curate=&row=schorkewarw-2#12/54.79/8.83',
    );
  });

  it('removes a parameter without a value, and the ? with the last one', () => {
    window.history.replaceState(null, '', '/?area=relation/1147134#12/54.79/8.83');
    replaceQueryParams({ area: undefined });
    expect(window.location.href).toBe(`${window.location.origin}/#12/54.79/8.83`);
  });

  it('writes a slash in a value as it is: `node/123` reads better than node%2F123 in a link', () => {
    replaceQueryParams({ area: 'relation/1147134' });
    expect(window.location.search).toBe('?area=relation/1147134');
  });

  it('leaves history alone when nothing changes', () => {
    window.history.replaceState(null, '', '/?curate=&row=schorkewarw-2');
    const replaceState = vi.spyOn(window.history, 'replaceState');
    replaceQueryParams({ row: 'schorkewarw-2' });
    expect(replaceState).not.toHaveBeenCalled();
  });
});
