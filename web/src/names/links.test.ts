import { describe, expect, it } from 'vitest';

import patchSchema from '../../../names/curate-patch.schema.json';
import type { NameEntry } from './entry';
import { osmRefFromFeatureId, placeOsmRef, WIKIDATA_ID } from './links';

/** A minimal, otherwise-empty entry, for tests that only care about a few fields. */
function entry(fields: Partial<NameEntry> = {}): NameEntry {
  return { id: '', names: {}, name_de: '', lon: 0, lat: 0, kind: '', ...fields };
}

describe('osmRefFromFeatureId', () => {
  // The three examples verified against the archive in the doc comment.
  it('decodes a node id (Niebüll)', () => {
    expect(osmRefFromFeatureId(2400427661)).toBe('node/240042766');
  });

  it('decodes a relation id (Föhr)', () => {
    expect(osmRefFromFeatureId(33525413)).toBe('relation/3352541');
  });

  it('decodes a way id (Gröde)', () => {
    expect(osmRefFromFeatureId(10871603522)).toBe('way/1087160352');
  });

  it('accepts the id as a numeric string too', () => {
    expect(osmRefFromFeatureId('2400427661')).toBe('node/240042766');
  });

  it('returns null for a type digit outside 1-3', () => {
    expect(osmRefFromFeatureId(100)).toBeNull(); // n % 10 === 0
  });

  it('returns null for zero, negative, non-integer, or missing ids', () => {
    expect(osmRefFromFeatureId(0)).toBeNull();
    expect(osmRefFromFeatureId(-21)).toBeNull();
    expect(osmRefFromFeatureId(1.5)).toBeNull();
    expect(osmRefFromFeatureId(undefined)).toBeNull();
    expect(osmRefFromFeatureId('not-a-number')).toBeNull();
  });
});

// The card links a row's QID only if WIKIDATA_ID takes it -- the pattern of
// the names.json contract --, and the curation panel saves one only if the
// patch schema does: the two contracts must never disagree.
describe('WIKIDATA_ID', () => {
  const schema = new RegExp(patchSchema.$defs.wikidata.pattern);

  it.each(['Q1', 'Q42', 'Q559369', 'q42', 'Q', 'Q4a', ' Q42', 'P31', 'Q-1', ''])(
    'takes %j exactly when the patch schema does',
    (qid) => {
      expect(WIKIDATA_ID.test(qid)).toBe(schema.test(qid));
    },
  );
});

describe('placeOsmRef', () => {
  it("is the name-list entry's OSM reference", () => {
    expect(placeOsmRef(entry({ id: 'naibel', osm: 'node/240042766' }), 33525413)).toBe(
      'node/240042766',
    );
  });

  it('is the first of the several references of a row', () => {
    expect(placeOsmRef(entry({ id: 'nordwarw', osm: 'way/1347936331; node/1332249790' }))).toBe(
      'way/1347936331',
    );
  });

  it("is the clicked feature's object when the name list does not have the place", () => {
    expect(placeOsmRef(undefined, 2400427661)).toBe('node/240042766');
  });
});
