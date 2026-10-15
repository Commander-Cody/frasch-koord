import { describe, expect, it } from 'vitest';

import patchSchema from '../../../../names/curate-patch.schema.json';
import { PATCH_FIELDS } from '../../../vite-plugins/patchFields.ts';
import { decidedRows, decisionLabel, singleWikidataId, type PatchEntry } from './patch';

function decision(
  id: string,
  line: number,
  action: PatchEntry['action'],
  osm?: string,
): PatchEntry {
  return { id, line, kind: 'warft', name: 'Schörkewärw', de: 'Kirchwarft', action, osm };
}

describe('decidedRows', () => {
  it("is each row's last decision", () => {
    const done = decidedRows([
      decision('schorkewarw', 5, 'skip'),
      decision('schorkewarw', 5, 'osm', 'node/1'),
    ]);
    expect(done.get('schorkewarw')?.osm).toBe('node/1');
  });

  it('keeps rows that share name and German name apart by id', () => {
    const done = decidedRows([
      decision('schorkewarw', 5, 'osm', 'node/1'),
      decision('schorkewarw-2', 6, 'osm', 'node/2'),
    ]);
    expect([...done.keys()]).toEqual(['schorkewarw', 'schorkewarw-2']);
  });

  it('forgets a withdrawn decision, whatever line either was sent with', () => {
    // a row was added above between the two: the same row, another line
    const done = decidedRows([
      decision('schorkewarw', 11, 'osm', 'node/1'),
      decision('schorkewarw', 12, 'clear'),
    ]);
    expect(done.has('schorkewarw')).toBe(false);
  });
});

describe('decisionLabel', () => {
  it('names a local decision by its reference', () => {
    const local: PatchEntry = { ...decision('toftem', 2, 'local'), slug: 'toftem-emmelsbull' };
    expect(decisionLabel(local)).toBe('local/toftem-emmelsbull');
  });

  it('says a skip is one', () => {
    expect(decisionLabel(decision('toftem', 2, 'skip'))).toBe('skipped');
  });
});

describe('singleWikidataId', () => {
  it('is the id of a tag with a single one', () => {
    expect(singleWikidataId('Q1717813')).toBe('Q1717813');
  });

  it('ignores whitespace around the id', () => {
    expect(singleWikidataId(' Q1717813 ')).toBe('Q1717813');
  });

  it('is nothing for a tag with several ids', () => {
    expect(singleWikidataId('Q1717813;Q20729612')).toBeUndefined();
  });

  it('is nothing for a tag that is no id', () => {
    expect(singleWikidataId('q1717813')).toBeUndefined();
  });

  it('is nothing for an empty or missing tag', () => {
    expect(singleWikidataId('')).toBeUndefined();
    expect(singleWikidataId(undefined)).toBeUndefined();
  });
});

// PatchEntry is written by hand; these pin it to the patch contract. The
// records fail to compile when the type gains or loses a field or an action,
// the comparisons fail when the schema does.
describe('PatchEntry', () => {
  it('has exactly the fields of the patch schema', () => {
    const fields: Record<keyof PatchEntry, true> = {
      id: true,
      line: true,
      kind: true,
      name: true,
      de: true,
      action: true,
      osm: true,
      wikidata: true,
      slug: true,
      lat: true,
      lon: true,
      polygon_km2: true,
      note: true,
      at: true,
    };
    expect(Object.keys(fields).sort()).toEqual([...PATCH_FIELDS].sort());
  });

  it('has exactly the actions of the patch schema', () => {
    const actions: Record<PatchEntry['action'], true> = {
      osm: true,
      local: true,
      skip: true,
      clear: true,
    };
    expect(Object.keys(actions).sort()).toEqual([...patchSchema.properties.action.enum].sort());
  });
});
