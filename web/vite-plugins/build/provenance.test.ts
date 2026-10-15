// @vitest-environment node
/** vite-plugins/build/provenance.ts: whether names.json and the tiles were built from the same files. */
import { describe, expect, it } from 'vitest';

import { type BuiltFrom, parseBuiltFrom, provenanceWarning } from './provenance.ts';

const INDEX: BuiltFrom = {
  'places.csv': 'aaa',
  'dialects.csv': 'bbb',
  'dialect_areas.geojson': 'ccc',
  extracts: [
    { file: 'schleswig-holstein-latest.osm.pbf', replication_timestamp: '2026-09-22T20:22:59Z' },
  ],
};

describe('provenanceWarning', () => {
  it('is silent when tiles and index were built from the same files', () => {
    expect(provenanceWarning(INDEX, { ...INDEX })).toBeUndefined();
  });

  it('names every input the two were built from differently, and only those', () => {
    const tiles = { ...INDEX, 'places.csv': 'old', 'dialect_areas.geojson': 'older' };

    expect(provenanceWarning(INDEX, tiles)).toBe(
      'the pinned tile archive and public/data/names.json were built from different dialect_areas.geojson, places.csv: map labels and place cards may disagree. Rebuild the index (`just rebuild index`) or rebuild and publish the tiles (`just tiles`, `just publish-tiles`)',
    );
  });

  it('ignores the extracts, which only say how current each side is', () => {
    const tiles = { ...INDEX, extracts: [{ file: 'x.osm.pbf', replication_timestamp: '' }] };

    expect(provenanceWarning(INDEX, tiles)).toBeUndefined();
  });

  it('warns about tiles that carry no stamp at all', () => {
    expect(provenanceWarning(INDEX, undefined)).toBe(
      'the pinned tile archive carries no built_from stamp: rebuild it (`just tiles`) to be sure it matches public/data/names.json',
    );
  });
});

describe('parseBuiltFrom', () => {
  it('reads the stamp the tile build writes into the archive description', () => {
    expect(parseBuiltFrom(JSON.stringify({ built_from: INDEX }))).toEqual(INDEX);
  });

  it('has nothing to say about the stock OpenMapTiles description', () => {
    expect(parseBuiltFrom('A tileset showcasing all layers in OpenMapTiles.')).toBeUndefined();
  });
});
