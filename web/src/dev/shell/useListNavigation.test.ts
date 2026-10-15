import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useListNavigation } from './useListNavigation';

function press(key: string, target: EventTarget = window) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
}

function renderNavigation(items: string[], selected: string | null) {
  const select = vi.fn();
  renderHook(() => useListNavigation(items, selected, select));
  return select;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useListNavigation', () => {
  it('moves down the list with j', () => {
    const select = renderNavigation(['a', 'b', 'c'], 'a');
    press('j');
    expect(select).toHaveBeenCalledWith('b');
  });

  it('moves up the list with k', () => {
    const select = renderNavigation(['a', 'b', 'c'], 'b');
    press('k');
    expect(select).toHaveBeenCalledWith('a');
  });

  it('takes the arrow keys too', () => {
    const select = renderNavigation(['a', 'b', 'c'], 'b');
    press('ArrowDown');
    press('ArrowUp');
    expect(select.mock.calls).toEqual([['c'], ['a']]);
  });

  it('starts at the top when nothing is selected', () => {
    const select = renderNavigation(['a', 'b', 'c'], null);
    press('j');
    expect(select).toHaveBeenCalledWith('a');
  });

  it('never runs past the end of the list', () => {
    const select = renderNavigation(['a', 'b', 'c'], 'c');
    press('j');
    expect(select).toHaveBeenCalledWith('c');
  });

  it('leaves the keys alone while typing', () => {
    const select = renderNavigation(['a', 'b', 'c'], 'a');
    const input = document.body.appendChild(document.createElement('input'));
    press('j', input);
    expect(select).not.toHaveBeenCalled();
  });

  it('does nothing on an empty list', () => {
    const select = renderNavigation([], null);
    press('j');
    expect(select).not.toHaveBeenCalled();
  });
});
