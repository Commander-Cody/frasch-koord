import { describe, expect, it } from 'vitest';

import indexSchema from '../../../names/search-index.schema.json';
import { pinnedFields, schemaFields, type Pin } from '../testing/schemaPin';
import type { NameEntry } from './entry';

// NameEntry is written by hand; this pins it to the contract of names.json,
// names/search-index.schema.json (see testing/schemaPin.ts).
describe('NameEntry', () => {
  it('has the fields of a place of the search index schema', () => {
    const pin: Pin<NameEntry> = {
      id: { string: true },
      osm: { string: true, optional: true },
      names: { object: true },
      local: { string: true, optional: true },
      dialect: { string: true, optional: true },
      variety: { string: true, optional: true },
      name_de: { string: true },
      name_osm: { string: true, optional: true },
      name_da: { string: true, optional: true },
      wikidata: { string: true, optional: true },
      lon: { number: true },
      lat: { number: true },
      kind: { string: true },
    };
    expect(pinnedFields(pin)).toEqual(schemaFields(indexSchema.$defs.place, indexSchema));
  });
});
