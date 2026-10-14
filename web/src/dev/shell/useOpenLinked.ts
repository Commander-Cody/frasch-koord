import { useEffect, useRef, useState } from 'react';

import { readQueryParam } from '../../url/queryParams';

/**
 * Opens what the page's `?<name>=` parameter names, once: `open` gets the
 * value as soon as `ready` says the data to look it up in is there. The
 * parameter is read at mount, before the panel writes its own selection back.
 * Nothing a panel offers to select is there before `ready`, so no choice of
 * the user's can come before the link's.
 */
export function useOpenLinked(name: string, ready: boolean, open: (value: string) => void): void {
  const [linked] = useState(() => readQueryParam(name));
  const settled = useRef(false);

  useEffect(() => {
    if (settled.current || linked === undefined || !ready) return;
    settled.current = true;
    open(linked);
  }, [linked, ready, open]);
}
