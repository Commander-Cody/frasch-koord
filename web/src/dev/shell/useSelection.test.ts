import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, renderHook } from '@testing-library/react';

import { useSelection, type SelectionOptions } from './useSelection';

const KEYS = ['naibel', 'rischsbel', 'deesbel'];

function options(own: Partial<SelectionOptions> = {}): SelectionOptions {
  return { param: 'row', keys: KEYS, ready: true, resolve: (value) => value, ...own };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/?curate');
});

describe('useSelection', () => {
  it('keeps the selection in the URL', () => {
    const { result } = renderHook(() => useSelection(options()));
    act(() => result.current.select('rischsbel'));
    expect(new URLSearchParams(window.location.search).get('row')).toBe('rischsbel');
  });

  it('opens what the link names once the data is there', () => {
    window.history.replaceState(null, '', '/?areas&area=relation/2');
    const resolve = (value: string) => (value === 'relation/2' ? 'relation/1' : undefined);
    const { result, rerender } = renderHook((props: SelectionOptions) => useSelection(props), {
      initialProps: options({ param: 'area', ready: false, resolve }),
    });
    rerender(options({ param: 'area', ready: true, resolve }));
    expect(result.current.selected).toBe('relation/1');
  });

  it('walks the list with the arrow keys', () => {
    const { result } = renderHook(() => useSelection(options()));
    act(() => result.current.select('naibel'));
    fireEvent.keyDown(window, { key: 'ArrowDown' });
    expect(result.current.selected).toBe('rischsbel');
  });

  it('shows what it selects', () => {
    const show = vi.fn();
    const { result } = renderHook(() => useSelection(options({ show })));
    act(() => result.current.select('deesbel'));
    expect(show).toHaveBeenCalledWith('deesbel');
  });

  it('leaves the map where it is for what was picked on it', () => {
    const show = vi.fn();
    const { result } = renderHook(() => useSelection(options({ show })));
    act(() => result.current.selectInPlace('deesbel'));
    expect(show).not.toHaveBeenCalled();
  });
});
