// What the search index and the tiles were built from (#24). Both record the
// hashes of the files they were built from as `built_from` (frasch/provenance.py):
// names.json at its top level, the PMTiles archive in its metadata's
// `description` (tiles/build.sh). Built from different states of those files,
// a place can sit in one dialect on the map and in another on its card, so
// the app says so in the console — it is a deployment mistake, not something
// a visitor can fix.

import { useEffect } from 'react';
import { PMTiles } from 'pmtiles';

import { TILES_URL } from './config';

export interface ExtractStamp {
  file: string;
  replication_timestamp: string;
}

/** `{"places.csv": "<git blob hash>", …, "extracts": [...]}` */
export type BuiltFrom = Record<string, string | ExtractStamp[]>;

/**
 * Which inputs the index and the tiles were built from differently, as a
 * console message, or null when they agree. The extracts are left out: the
 * index takes its positions from names/osm_objects.json, whose hash is
 * compared, and each side's extract only says how current it is.
 */
export function provenanceWarning(index: BuiltFrom, tiles: BuiltFrom | undefined): string | null {
  if (!tiles) {
    return 'The tiles carry no built_from stamp: rebuild them (tiles/build.sh) to be sure they match names.json.';
  }
  const inputs = new Set([...Object.keys(index), ...Object.keys(tiles)]);
  const differing = [...inputs].filter((k) => k !== 'extracts' && index[k] !== tiles[k]).sort();
  if (differing.length === 0) return null;
  return (
    `names.json and the tiles were built from different ${differing.join(', ')}: ` +
    'map labels and place cards may disagree. Rebuild both (`just rebuild index`, `just tiles`).'
  );
}

/** The stamp in an archive's description, if the description is one. */
export function parseBuiltFrom(description: unknown): BuiltFrom | undefined {
  if (typeof description !== 'string') return undefined;
  try {
    const parsed: unknown = JSON.parse(description);
    const stamp = (parsed as { built_from?: unknown } | null)?.built_from;
    return stamp && typeof stamp === 'object' ? (stamp as BuiltFrom) : undefined;
  } catch {
    return undefined;
  }
}

const PMTILES_PREFIX = 'pmtiles://';

/** The stamp in the metadata of a `pmtiles://` archive. */
async function tilesBuiltFrom(tilesUrl: string): Promise<BuiltFrom | undefined> {
  const archive = new PMTiles(tilesUrl.slice(PMTILES_PREFIX.length));
  const metadata = (await archive.getMetadata()) as { description?: unknown };
  return parseBuiltFrom(metadata.description);
}

/**
 * Once names.json has loaded, compares its stamp with the tiles' and warns in
 * the console when they differ. A tile source that is not a PMTiles archive
 * has no stamp to read and is not checked.
 */
export function useProvenanceCheck(indexBuiltFrom: BuiltFrom | undefined): void {
  useEffect(() => {
    if (!indexBuiltFrom || !TILES_URL.startsWith(PMTILES_PREFIX)) return;
    let cancelled = false;
    tilesBuiltFrom(TILES_URL)
      .then((tiles) => {
        const warning = provenanceWarning(indexBuiltFrom, tiles);
        if (warning && !cancelled) console.warn(warning);
      })
      // The map itself reports an archive it cannot read.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [indexBuiltFrom]);
}
