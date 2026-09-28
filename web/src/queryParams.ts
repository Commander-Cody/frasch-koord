// The one place the page writes its own URL: the public map's link state
// (urlState.ts) and the dev panels' deep links (`?curate&row=`, `?areas&area=`).
// The viewport is MapLibre's own `#zoom/lat/lon` hash, which this leaves alone.

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
