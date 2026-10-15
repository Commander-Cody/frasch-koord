/**
 * Whether the search index and the tiles a build ships were built from the
 * same files (#24). Both record the hashes of the files they were built from
 * as `built_from` (frasch/provenance.py): names.json at its top level, the
 * PMTiles archive in its metadata's `description` (tiles/build.sh). Built
 * from different states of those files, a place can sit in one dialect on
 * the map and in another on its card. The build warns then
 * (vite-plugins/build/assets.ts) rather than fails: the archive is
 * published separately and catches up with names.json later.
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import { archiveMetadata } from './archive.ts';

/** `{"places.csv": "<git blob hash>", …, "extracts": [...]}` */
export type BuiltFrom = Record<string, unknown>;

/** The search index, under the web/ root. */
const NAMES = 'public/data/names.json';

/**
 * Which inputs the index and the tiles were built from differently, as a
 * warning, or undefined when they agree. The extracts are left out: the
 * index takes its positions from names/osm_objects.json, whose hash is
 * compared, and each side's extract only says how current it is.
 */
export function provenanceWarning(
  index: BuiltFrom,
  tiles: BuiltFrom | undefined,
): string | undefined {
  if (!tiles) {
    return `the pinned tile archive carries no built_from stamp: rebuild it (\`just tiles\`) to be sure it matches ${NAMES}`;
  }
  const inputs = new Set([...Object.keys(index), ...Object.keys(tiles)]);
  const differing = [...inputs].filter((k) => k !== 'extracts' && index[k] !== tiles[k]).sort();
  if (differing.length === 0) return undefined;
  return (
    `the pinned tile archive and ${NAMES} were built from different ${differing.join(', ')}: ` +
    'map labels and place cards may disagree. Rebuild the index (`just rebuild index`) or ' +
    'rebuild and publish the tiles (`just tiles`, `just publish-tiles`)'
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

/** The warning about names.json and the fetched `archive` the build ships, if they differ. */
export async function builtFromWarning(root: string, archive: string): Promise<string | undefined> {
  const names = JSON.parse(await readFile(join(root, NAMES), 'utf8')) as { built_from?: BuiltFrom };
  const tiles = parseBuiltFrom((await archiveMetadata(archive)).description);
  return provenanceWarning(names.built_from ?? {}, tiles);
}
