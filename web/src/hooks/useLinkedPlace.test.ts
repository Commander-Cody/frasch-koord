import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

import { entryLookup, type NameEntry, type NamesData } from '../names';
import { useLinkedPlace } from './useLinkedPlace';

const naibel: NameEntry = {
  id: 'naibel',
  names: {},
  name_de: 'Niebüll',
  lon: 8.83,
  lat: 54.79,
  kind: 'settlement',
};
const find = entryLookup([naibel]);

type Status = NamesData['status'];

function renderLinkedPlace(status: Status = 'loading') {
  const open = vi.fn();
  const hook = renderHook((props: { status: Status }) => useLinkedPlace(props.status, find, open), {
    initialProps: { status },
  });
  return { ...hook, open };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/');
});

describe('useLinkedPlace', () => {
  it('keeps the linked place, and opens nothing, while the name list loads', () => {
    window.history.replaceState(null, '', '/?place=naibel');
    const { result, open } = renderLinkedPlace('loading');
    expect(result.current).toBe('naibel');
    expect(open).not.toHaveBeenCalled();
  });

  it("opens the linked place once the name list is there, keeping the link's viewport", () => {
    window.history.replaceState(null, '', '/?place=naibel#12/54.79/8.83');
    const { result, open, rerender } = renderLinkedPlace('loading');
    rerender({ status: 'ready' });
    expect(open).toHaveBeenCalledWith(naibel, true);
    expect(result.current).toBeUndefined();
  });

  it('reads the viewport at mount, before the map writes a hash of its own', () => {
    window.history.replaceState(null, '', '/?place=naibel');
    const { open, rerender } = renderLinkedPlace('loading');
    window.history.replaceState(null, '', '/?place=naibel#9/54.6/8.9');
    rerender({ status: 'ready' });
    expect(open).toHaveBeenCalledWith(naibel, false);
  });

  it('opens a place only once', () => {
    window.history.replaceState(null, '', '/?place=naibel');
    const { open, rerender } = renderLinkedPlace('ready');
    rerender({ status: 'ready' });
    expect(open).toHaveBeenCalledTimes(1);
  });

  it('drops a link to a place the name list does not have', () => {
    window.history.replaceState(null, '', '/?place=nowhere');
    const { result, open } = renderLinkedPlace('ready');
    expect(open).not.toHaveBeenCalled();
    expect(result.current).toBeUndefined();
  });

  it('has nothing to open without a link', () => {
    const { result, open } = renderLinkedPlace('ready');
    expect(open).not.toHaveBeenCalled();
    expect(result.current).toBeUndefined();
  });
});
