import { describe, expect, it } from 'vitest';

import indexSchema from '../../names/search-index.schema.json';
import { provenanceWarning, parseBuiltFrom, type BuiltFrom, type ExtractStamp } from './provenance';
import { pinnedFields, schemaFields, type Pin } from './testing/schemaPin';

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
    expect(provenanceWarning(INDEX, { ...INDEX })).toBeNull();
  });

  it('names every input the two were built from differently', () => {
    const tiles = { ...INDEX, 'places.csv': 'old', 'dialect_areas.geojson': 'older' };
    const warning = provenanceWarning(INDEX, tiles);
    expect(warning).toContain('places.csv');
    expect(warning).toContain('dialect_areas.geojson');
    expect(warning).not.toContain('dialects.csv');
  });

  it('ignores the extracts, which only say how current each side is', () => {
    const tiles = { ...INDEX, extracts: [{ file: 'x.osm.pbf', replication_timestamp: '' }] };
    expect(provenanceWarning(INDEX, tiles)).toBeNull();
  });

  it('warns about tiles that carry no stamp at all', () => {
    expect(provenanceWarning(INDEX, undefined)).toMatch(/no built_from/);
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

// ExtractStamp is written by hand; this pins it to the stamp of names.json,
// names/search-index.schema.json (see testing/schemaPin.ts).
describe('ExtractStamp', () => {
  it('has the fields of an extract of the search index schema', () => {
    const pin: Pin<ExtractStamp> = {
      file: { string: true },
      replication_timestamp: { string: true },
    };
    expect(pinnedFields(pin)).toEqual(schemaFields(indexSchema.$defs.extract, indexSchema));
  });
});
