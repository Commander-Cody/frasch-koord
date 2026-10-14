import { useCallback, useEffect, useState } from 'react';
import type { RefCallback } from 'react';

import { replaceQueryParams } from '../../url/queryParams';
import { useListNavigation } from './useListNavigation';
import { useOpenLinked } from './useOpenLinked';

export interface SelectionOptions {
  /** The query parameter that keeps the selection: `?row=`. */
  param: string;
  /** The keys in the order the list shows them, for ↓/↑. */
  keys: readonly string[];
  /** Whether the data a link is looked up in is there. */
  ready: boolean;
  /** The key a linked value names, if any; a key names itself as long as its item is there. */
  resolve: (value: string) => string | undefined;
  /** Brings the selected item into view on the map. */
  show?: (key: string) => void;
}

export interface Selection {
  selected: string | null;
  /** Selects `key` and shows it: from the list, the keys or a link. */
  select: (key: string) => void;
  /** Selects `key` without moving the map: it was clicked there. */
  selectInPlace: (key: string) => void;
  /** The ref for the list item of `key`: the selected one is kept in view. */
  itemRef: (key: string) => RefCallback<HTMLElement> | undefined;
}

/** Scrolls the selected item into view as it gets the ref, i.e. once per selection. */
function keepInView(node: HTMLElement | null): void {
  node?.scrollIntoView({ block: 'nearest' });
}

/**
 * Which item of a dev panel's list is selected, by a key that stays put when
 * the data is reloaded, and none once a reload took its item away. Kept in
 * `?<param>=`, opened from there once `ready`, and walked with the keys of
 * useListNavigation.
 */
export function useSelection({ param, keys, ready, resolve, show }: SelectionOptions): Selection {
  const [selected, setSelected] = useState<string | null>(null);
  const selectInPlace = useCallback(
    (key: string) => {
      setSelected(key);
      replaceQueryParams({ [param]: key });
    },
    [param],
  );
  const select = useCallback(
    (key: string) => {
      selectInPlace(key);
      show?.(key);
    },
    [selectInPlace, show],
  );

  const openLinked = useCallback(
    (value: string) => {
      const key = resolve(value);
      if (key !== undefined) select(key);
    },
    [resolve, select],
  );
  useOpenLinked(param, ready, openLinked);
  useForgetGone({ param, selected, ready, resolve, setSelected });
  useListNavigation(keys, selected, select);
  const itemRef = useCallback(
    (key: string) => (key === selected ? keepInView : undefined),
    [selected],
  );
  return { selected, select, selectInPlace, itemRef };
}

/** Selects nothing once the data no longer has the selected item, in the URL too. */
function useForgetGone({
  param,
  selected,
  ready,
  resolve,
  setSelected,
}: Pick<SelectionOptions, 'param' | 'ready' | 'resolve'> & {
  selected: string | null;
  setSelected: (key: null) => void;
}): void {
  useEffect(() => {
    if (!ready || selected === null || resolve(selected) !== undefined) return;
    setSelected(null);
    replaceQueryParams({ [param]: undefined });
  }, [param, selected, ready, resolve, setSelected]);
}
