import { expect, it } from 'vitest';

import { PHONE_MEDIA } from './layout';

/** Every stylesheet under src/, by path. */
const STYLESHEETS = import.meta.glob<string>('./**/*.css', { query: '?raw', import: 'default', eager: true });

/** Every `@media` query with a `max-width` in those stylesheets, with its file. */
function widthQueries(): { file: string; query: string }[] {
  return Object.entries(STYLESHEETS).flatMap(([file, css]) =>
    [...css.matchAll(/@media\s*([^{]*max-width[^{]*?)\s*\{/g)].map(([, query]) => ({ file, query })),
  );
}

it('lays out for a phone at the width the code moves the map for', () => {
  const queries = widthQueries();
  expect(queries.length).toBeGreaterThan(0);
  for (const { file, query } of queries) expect({ file, query }).toEqual({ file, query: PHONE_MEDIA });
});
