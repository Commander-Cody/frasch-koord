// The curation view's "Look up in OSM": Nominatim and Overpass, called from
// the browser against the public instances and bounded to the worklist's
// bbox. Light, hand-driven use only — that is what their usage policies allow.

import { useEffect, useRef, useState } from 'react';

import type { Bbox } from './curateWorklist';

/** A Nominatim or Overpass hit, normalised to what the pin/pick code needs. */
export interface LookupResult {
  ref: string;
  name: string;
  /** Short type description, e.g. "place=hamlet" or "hamlet". */
  what: string;
  lon: number;
  lat: number;
  tags: string;
  wikidata?: string;
}

/** Tags worth seeing at a glance in a lookup result. */
const INTERESTING_TAGS = [
  'place',
  'highway',
  'natural',
  'landuse',
  'waterway',
  'boundary',
  'water',
  'man_made',
];

function tagSummary(tags: Record<string, string> | undefined): string {
  if (!tags) return '';
  return INTERESTING_TAGS.filter((k) => tags[k])
    .map((k) => `${k}=${tags[k]}`)
    .join(' ');
}

/**
 * Escapes a user's query for the Overpass `~"…"` regex: its special
 * characters, and the `"` that would end the QL string around it.
 */
function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\"]/g, '\\$&');
}

interface NominatimHit {
  osm_type?: string;
  osm_id?: number;
  name?: string;
  display_name?: string;
  category?: string;
  type?: string;
  lat: string;
  lon: string;
}

async function searchNominatim(
  query: string,
  [w, s, e, n]: Bbox,
  signal: AbortSignal,
): Promise<LookupResult[]> {
  const url =
    'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=25&bounded=1' +
    `&viewbox=${w},${n},${e},${s}&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Nominatim HTTP ${res.status} (rate limited?)`);
  const hits = (await res.json()) as NominatimHit[];
  return hits
    .filter((h) => h.osm_type && h.osm_id)
    .map((h) => ({
      ref: `${h.osm_type}/${h.osm_id}`,
      name: h.name || h.display_name || '',
      what: [h.category, h.type].filter(Boolean).join('='),
      lon: Number(h.lon),
      lat: Number(h.lat),
      tags: h.display_name ?? '',
    }));
}

interface OverpassElement {
  type: string;
  id: number;
  lat?: number;
  lon?: number;
  center?: { lat: number; lon: number };
  tags?: Record<string, string>;
}

async function searchOverpass(
  query: string,
  [w, s, e, n]: Bbox,
  signal: AbortSignal,
): Promise<LookupResult[]> {
  const overpassQuery =
    '[out:json][timeout:25];' +
    `nwr["name"~"${escapeRegex(query)}",i](${s},${w},${n},${e});` +
    'out center tags 60;';
  const res = await fetch('https://overpass-api.de/api/interpreter', {
    method: 'POST',
    body: overpassQuery,
    signal,
  });
  if (!res.ok) throw new Error(`Overpass HTTP ${res.status} (busy/rate limited?)`);
  const body = (await res.json()) as { elements?: OverpassElement[] };
  const results: LookupResult[] = [];
  for (const element of body.elements ?? []) {
    // Ways/relations carry their position in `center` (`out center`).
    const lon = element.lon ?? element.center?.lon;
    const lat = element.lat ?? element.center?.lat;
    if (typeof lon !== 'number' || typeof lat !== 'number') continue;
    results.push({
      ref: `${element.type}/${element.id}`,
      name: element.tags?.name ?? '',
      what: tagSummary(element.tags) || element.type,
      lon,
      lat,
      tags: tagSummary(element.tags),
      wikidata: element.tags?.wikidata,
    });
  }
  return results;
}

const SERVICES = { Nominatim: searchNominatim, Overpass: searchOverpass };
export type LookupService = keyof typeof SERVICES;
export const LOOKUP_SERVICES = Object.keys(SERVICES) as LookupService[];

export interface OsmLookup {
  query: string;
  setQuery: (query: string) => void;
  results: LookupResult[];
  /** Which service answered, and with how many results. */
  source: string;
  busy: boolean;
  error: string | null;
  run: (service: LookupService) => Promise<void>;
}

/**
 * The lookup's query, starting at `initialQuery`, and what the last search
 * found. A search still on its way when the component unmounts is aborted.
 */
export function useOsmLookup(bbox: Bbox, initialQuery: string): OsmLookup {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<LookupResult[]>([]);
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);

  useEffect(() => () => pending.current?.abort(), []);

  const run = async (service: LookupService) => {
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError(null);
    try {
      const found = await SERVICES[service](query, bbox, controller.signal);
      setResults(found);
      setSource(`${service}: ${found.length} result(s)`);
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return { query, setQuery, results, source, busy, error, run };
}
