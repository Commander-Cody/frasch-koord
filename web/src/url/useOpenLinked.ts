import { useEffect, useRef, useState } from 'react';

import { readQueryParam } from './queryParams';

/**
 * Opens what the page's `?<name>=` parameter names, once: `open` gets the
 * value as soon as `ready` says the data to look it up in is there. The
 * parameter is read at mount, before the panel writes its own selection back.
 *
 * A selection the user made before that wins: `hasSelection` is asked when
 * the link would open (a getter, so it sees a click the last render has not),
 * and if it says yes, the link is dropped for good.
 */
export function useOpenLinked(
  name: string,
  ready: boolean,
  open: (value: string) => void,
  hasSelection: () => boolean,
): void {
  const [linked] = useState(() => readQueryParam(name));
  const settled = useRef(false);

  useEffect(() => {
    if (settled.current || linked === undefined || !ready) return;
    settled.current = true;
    if (!hasSelection()) open(linked);
  }, [linked, ready, open, hasSelection]);
}
