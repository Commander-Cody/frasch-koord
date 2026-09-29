import { useEffect, useRef, useState } from 'react';

import type { EntryLookup, NameEntry, NamesData } from '../names';
import { readUrlState } from '../urlState';

/** What a shared link says: the place to open, and whether it also says where to look. */
interface Link {
  place?: string;
  hasViewport: boolean;
}

function readLink(): Link {
  return { place: readUrlState().place, hasViewport: window.location.hash.length > 1 };
}

/**
 * Opens the place a shared link names (`?place=`, see urlState.ts) once the
 * name list is there to look it up in: `open` gets its entry, and whether the
 * link carries a viewport (`#zoom/lat/lon`) of its own. Only name-list places
 * can be linked: a tile feature the list does not have (a plain German
 * village) has nothing to look it up by before its tile is on screen.
 *
 * The link is read at mount, before the map starts writing a hash of its own.
 * Returns the linked place until it is opened (or found missing), so the
 * address bar keeps it while the list loads.
 */
export function useLinkedPlace(
  status: NamesData['status'],
  find: EntryLookup,
  open: (entry: NameEntry, hasViewport: boolean) => void,
): string | undefined {
  const [link] = useState(readLink);
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current || !link.place || status !== 'ready') return;
    opened.current = true;
    const entry = find(link.place);
    if (entry) open(entry, link.hasViewport);
  }, [link, status, find, open]);

  return status === 'ready' ? undefined : link.place;
}
