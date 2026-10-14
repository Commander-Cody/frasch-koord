// The one module that reads and writes the page's URL: the public map's link
// state (linkState.ts), the dev panels' deep links (`?curate&row=`,
// `?areas&area=`), and what else needs the address. The viewport is MapLibre's
// own `#zoom/lat/lon` hash (see map/createMap.ts), which it reads and writes itself.

/** The value of `?<name>=`, the first of several; an empty one counts as none. */
export function readQueryParam(name: string): string | undefined {
  return new URLSearchParams(window.location.search).get(name) || undefined;
}

/** Whether the URL has `?<name>`, with a value or without one. */
export function hasQueryParam(name: string): boolean {
  return new URLSearchParams(window.location.search).has(name);
}

/**
 * Sets the given query parameters in the address bar — an undefined or empty
 * value removes one — and keeps every other parameter and the hash.
 * `replaceState`, not `pushState`: picking a dialect, a place or a row is not
 * a navigation the back button should step through; and not even that when
 * nothing changes.
 */
export function replaceQueryParams(values: Record<string, string | undefined>): void {
  const params = new URLSearchParams(window.location.search);
  for (const [key, value] of Object.entries(values)) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  // OSM references (`relation/1147134`, old `?place=node/123` ids) carry a
  // slash; it is fine in a query and reads much better than %2F in a link
  // people paste into chats.
  const query = params.toString().replace(/%2F/gi, '/');
  const { pathname, search, hash } = window.location;
  const url = `${pathname}${query ? `?${query}` : ''}${hash}`;
  if (url !== `${pathname}${search}${hash}`) {
    window.history.replaceState(window.history.state, '', url);
  }
}

/** Whether the URL says where to look: MapLibre's `#zoom/lat/lon`. */
export function hasViewport(): boolean {
  return window.location.hash.length > 1;
}

/** The address as it is: the link to what is on screen. */
export function pageUrl(): string {
  return window.location.href;
}

/**
 * `url` resolved against the page. Outside a browser there is no page to
 * resolve against, so it is returned as it is.
 */
export function resolvedOnPage(url: string): string {
  return typeof window === 'undefined' ? url : new URL(url, window.location.href).href;
}

/** Runs `action` and puts back the hash, should the action have removed it. */
export function keepingHash(action: () => void): void {
  const { hash } = window.location;
  action();
  if (hash) window.history.replaceState(window.history.state, '', hash);
}
