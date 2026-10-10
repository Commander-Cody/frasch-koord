import { describe, expect, it } from 'vitest';

import worklistSchema from '../../../names/curate-worklist.schema.json';
import { pinnedFields, schemaFields, type Pin } from '../testing/schemaPin';
import type { CurateCandidate, CurateRow, CurateWorklist } from './curateWorklist';

// The worklist's types are written by hand; these pin them to its contract,
// names/curate-worklist.schema.json (see testing/schemaPin.ts).
describe('the worklist types', () => {
  it('CurateWorklist has the fields of the schema', () => {
    const pin: Pin<CurateWorklist> = {
      bbox: { array: true },
      kind_order: { array: true },
      polygon_kinds: { array: true },
      class_keys: { array: true },
      settlement_places: { array: true },
      results: { array: true },
      rows: { array: true },
    };
    expect(pinnedFields(pin)).toEqual(schemaFields(worklistSchema));
  });

  it('CurateRow has the fields of a row of the schema', () => {
    const pin: Pin<CurateRow> = {
      id: { string: true },
      line: { number: true },
      kind: { string: true },
      result: { string: true },
      name: { string: true },
      names: { object: true },
      name_de: { string: true },
      name_da: { string: true },
      de: { string: true },
      da: { string: true },
      hint: { string: true },
      note: { string: true },
      why: { string: true },
      hint_point: { array: true, null: true },
      candidates: { array: true },
    };
    expect(pinnedFields(pin)).toEqual(schemaFields(worklistSchema.$defs.row, worklistSchema));
  });

  it('CurateCandidate has the fields of a candidate of the schema', () => {
    const pin: Pin<CurateCandidate> = {
      ref: { string: true },
      name: { string: true },
      class: { string: true },
      km: { number: true, null: true },
      lon: { number: true, null: true },
      lat: { number: true, null: true },
      tags: { string: true },
      in_sh: { boolean: true },
      wikidata: { string: true, optional: true },
    };
    expect(pinnedFields(pin)).toEqual(schemaFields(worklistSchema.$defs.candidate, worklistSchema));
  });

  it('a row has exactly the results of the schema', () => {
    const results: Record<CurateRow['result'], true> = { ambiguous: true, not_found: true };
    expect(Object.keys(results).sort()).toEqual([...worklistSchema.$defs.result.enum].sort());
  });
});
