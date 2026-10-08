import { expect, it } from 'vitest';

import { pinnedFields, schemaFields, type Pin } from './schemaPin';

interface Place {
  id: string;
  km: number | null;
  wikidata?: string;
}

it('reads what a pin says of each field', () => {
  const pin: Pin<Place> = {
    id: { string: true },
    km: { number: true, null: true },
    wikidata: { string: true, optional: true },
  };

  expect(pinnedFields(pin)).toEqual({
    id: ['string'],
    km: ['null', 'number'],
    wikidata: ['optional', 'string'],
  });
});

it('reads a property the schema does not require as optional', () => {
  const schema = {
    required: ['id'],
    properties: { id: { type: 'string' }, at: { type: 'string' } },
  };

  expect(schemaFields(schema)).toEqual({ id: ['string'], at: ['optional', 'string'] });
});

it('reads every type of a property that has several', () => {
  const schema = { required: ['km'], properties: { km: { type: ['number', 'null'] } } };

  expect(schemaFields(schema)).toEqual({ km: ['null', 'number'] });
});

it('reads an integer as a number', () => {
  const schema = { required: ['line'], properties: { line: { type: 'integer' } } };

  expect(schemaFields(schema)).toEqual({ line: ['number'] });
});

it('reads an enum as the type of its values', () => {
  const schema = { required: ['action'], properties: { action: { enum: ['osm', 'skip'] } } };

  expect(schemaFields(schema)).toEqual({ action: ['string'] });
});

it('reads a constant as the type of its value', () => {
  const schema = { required: ['type'], properties: { type: { const: 'Feature' } } };

  expect(schemaFields(schema)).toEqual({ type: ['string'] });
});

it("follows a reference into the schema's definitions", () => {
  const schema = {
    required: ['slug'],
    properties: { slug: { $ref: '#/$defs/slug' } },
    $defs: { slug: { type: 'string' } },
  };

  expect(schemaFields(schema)).toEqual({ slug: ['string'] });
});
