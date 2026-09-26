import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { readUrlState, writeUrlState } from './urlState';

function setLocation(url: string) {
  window.history.replaceState(null, '', url);
}

beforeEach(() => {
  setLocation('/');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('readUrlState', () => {
  it('is empty when the URL has neither param', () => {
    setLocation('/');
    expect(readUrlState()).toEqual({ view: undefined, place: undefined });
  });

  it('parses both params', () => {
    setLocation('/?view=frr-x-fering&place=node%2F123');
    expect(readUrlState()).toEqual({ view: 'frr-x-fering', place: 'node/123' });
  });

  it('treats an empty value the same as a missing one', () => {
    setLocation('/?view=&place=');
    expect(readUrlState()).toEqual({ view: undefined, place: undefined });
  });

  it('ignores unrelated query parameters', () => {
    setLocation('/?foo=bar&view=frr-x-mooring');
    expect(readUrlState()).toEqual({ view: 'frr-x-mooring', place: undefined });
  });

  it('ignores the MapLibre viewport hash, which lives in a different part of the URL', () => {
    setLocation('/?place=node/123#12/54.79/8.83');
    expect(readUrlState()).toEqual({ view: undefined, place: 'node/123' });
  });

  it('takes the first value of a repeated param (URLSearchParams.get semantics)', () => {
    setLocation('/?view=frr-x-mooring&view=frr-x-fering');
    expect(readUrlState().view).toBe('frr-x-mooring');
  });
});

describe('writeUrlState', () => {
  it('round-trips what it writes', () => {
    writeUrlState({ view: 'frr-x-fering', place: 'node/123' });
    expect(readUrlState()).toEqual({ view: 'frr-x-fering', place: 'node/123' });
  });

  it('writes place ids with a literal slash rather than %2F', () => {
    writeUrlState({ place: 'node/123' });
    expect(window.location.search).toBe('?place=node/123');
  });

  it('removes a param that is now undefined', () => {
    setLocation('/?view=frr-x-fering&place=node/123');
    writeUrlState({ view: 'frr-x-fering', place: undefined });
    expect(readUrlState()).toEqual({ view: 'frr-x-fering', place: undefined });
  });

  it('leaves other, unrelated query parameters alone', () => {
    setLocation('/?other=1');
    writeUrlState({ view: 'frr-x-mooring' });
    expect(new URLSearchParams(window.location.search).get('other')).toBe('1');
  });

  it('keeps the viewport hash untouched', () => {
    setLocation('/#12/54.79/8.83');
    writeUrlState({ place: 'node/123' });
    expect(window.location.hash).toBe('#12/54.79/8.83');
  });

  it('does not touch history when nothing actually changes', () => {
    setLocation('/?view=frr-x-fering');
    const replaceState = vi.spyOn(window.history, 'replaceState');
    writeUrlState({ view: 'frr-x-fering' });
    expect(replaceState).not.toHaveBeenCalled();
  });

  it('uses replaceState, not pushState, so picking a view/place is not a back-button step', () => {
    const pushState = vi.spyOn(window.history, 'pushState');
    writeUrlState({ view: 'frr-x-fering' });
    expect(pushState).not.toHaveBeenCalled();
  });
});
