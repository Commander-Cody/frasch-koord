import { expect, it } from 'vitest';

import partsSchema from '../../../names/dialect-area-parts.schema.json';
import { pinnedFields, schemaFields, type Pin } from '../testing/schemaPin';
import type { AreaProps } from './AreaPanel';

// AreaProps is written by hand; this pins it to the contract of the parts
// file, names/dialect-area-parts.schema.json (see testing/schemaPin.ts).
it('AreaProps has the fields of a part of the schema', () => {
  const pin: Pin<AreaProps> = {
    fid: { number: true },
    assigned: { boolean: true },
    dialect: { string: true, optional: true },
    name: { string: true },
    note: { string: true, optional: true },
    osm: { string: true },
    line: { number: true, optional: true },
    km2: { number: true },
  };
  expect(pinnedFields(pin)).toEqual(schemaFields(partsSchema.$defs.part, partsSchema));
});
