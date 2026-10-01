import { useEffect, useRef, useState } from 'react';

/**
 * Opens what the page's `?<name>=` parameter names, once: `open` gets the
 * value as soon as `ready` says the data to look it up in is there. The
 * parameter is read at mount, before the panel writes its own selection back.
 */
export function useDeepLinkParam(
  name: string,
  ready: boolean,
  open: (value: string) => void,
): void {
  const [linked] = useState(() => new URLSearchParams(window.location.search).get(name));
  const opened = useRef(false);

  useEffect(() => {
    if (opened.current || linked === null || !ready) return;
    opened.current = true;
    open(linked);
  }, [linked, ready, open]);
}
