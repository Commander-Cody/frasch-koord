import { expect, it } from 'vitest';

import { pmtilesArchive } from './pmtiles';

const URL = 'pmtiles://https://tiles.example/schleswig-holstein.pmtiles';

it('hands everyone who reads an archive the same instance', () => {
  expect(pmtilesArchive(URL)).toBe(pmtilesArchive(URL));
});

it('has no archive for a tile source that is not a PMTiles archive', () => {
  expect(pmtilesArchive('https://tiles.example/tiles.json')).toBeUndefined();
});
