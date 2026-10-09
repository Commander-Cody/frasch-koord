import { expect, it } from 'vitest';

import { DIALECTS } from '../config';
import { DIALECT_COLORS } from './areaLayers';

it('has a colour for exactly the dialects of the registry', () => {
  expect(Object.keys(DIALECT_COLORS).sort()).toEqual(DIALECTS.map((dialect) => dialect.tag).sort());
});
