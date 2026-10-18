import { describe, expect, it } from 'vitest';

import worklistSchema from '../../../../names/curate-worklist.schema.json';
import { pinnedFields, schemaFields, type Pin } from '../../testing/schemaPin';
import {
  filterRows,
  NO_FILTER,
  rowKinds,
  type CurateCandidate,
  type CurateRow,
  type CurateWorklist,
} from './worklist';

/** A worklist row with only `fields` set. */
function row(id: string, fields: Partial<CurateRow> = {}): CurateRow {
  return {
    id,
    line: 2,
    kind: 'settlement',
    result: 'ambiguous',
    name: '',
    names: {},
    name_de: '',
    name_da: '',
    slug_suggestion: '',
    de: '',
    da: '',
    hint: '',
    note: '',
    why: '',
    hint_point: null,
    candidates: [],
    ...fields,
  };
}

/** A worklist of `rows` that walks the kinds in `kind_order`. */
function worklist(kind_order: string[], rows: CurateRow[]): CurateWorklist {
  return {
    bbox: [8, 54, 9, 55],
    kind_order,
    polygon_kinds: [],
    class_keys: [],
    settlement_places: [],
    results: ['ambiguous', 'not_found'],
    rows,
  };
}

const ids = (rows: CurateRow[]) => rows.map((r) => r.id);
const NONE_DONE = () => false;
const ALL = { ...NO_FILTER, hideDone: false };

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
      slug_suggestion: { string: true },
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

describe('filterRows', () => {
  it('keeps the rows of the chosen kind', () => {
    const rows = [row('a', { kind: 'koog' }), row('b', { kind: 'settlement' })];
    expect(ids(filterRows(rows, { ...ALL, kind: 'koog' }, NONE_DONE))).toEqual(['a']);
  });

  it('keeps the rows of the chosen result', () => {
    const rows = [row('a', { result: 'ambiguous' }), row('b', { result: 'not_found' })];
    expect(ids(filterRows(rows, { ...ALL, result: 'not_found' }, NONE_DONE))).toEqual(['b']);
  });

  it.each([
    [true, ['open']],
    [false, ['decided', 'open']],
  ])('with hideDone %s, shows %j', (hideDone, expected) => {
    const rows = [row('decided'), row('open')];
    const isDone = (id: string) => id === 'decided';
    expect(ids(filterRows(rows, { ...ALL, hideDone }, isDone))).toEqual(expected);
  });

  it.each([
    ['the name', { name: 'Naibel' }],
    ['a name column', { names: { name_frr_x_mooring: 'Naibel' } }],
    ['the German names', { de: 'Naibel (alt)' }],
    ['the Danish names', { da: 'Naibel' }],
    ['the hint', { hint: 'near Naibel' }],
  ])('finds the text in %s', (_, fields) => {
    const rows = [row('found', fields), row('other', { name: 'Rischsbel' })];
    expect(ids(filterRows(rows, { ...ALL, text: 'naibel' }, NONE_DONE))).toEqual(['found']);
  });

  it('ignores the case of the text and the space around it', () => {
    const rows = [row('found', { name: 'naibel' })];
    expect(ids(filterRows(rows, { ...ALL, text: ' NAIBEL ' }, NONE_DONE))).toEqual(['found']);
  });
});

describe('rowKinds', () => {
  it("lists the rows' kinds in kind_order, the kinds it does not know after them, sorted", () => {
    const rows = ['mill', 'koog', 'church', 'settlement'].map((kind) => row(kind, { kind }));
    expect(rowKinds(worklist(['settlement', 'koog'], rows))).toEqual([
      'settlement',
      'koog',
      'church',
      'mill',
    ]);
  });

  it('leaves out a kind of kind_order no row has', () => {
    const rows = [row('a', { kind: 'koog' })];
    expect(rowKinds(worklist(['settlement', 'koog'], rows))).toEqual(['koog']);
  });
});
