import { expect, it } from 'vitest';

import { PHONE_MEDIA, TOUCH_MEDIA } from './layout';
import { STYLESHEETS, declarations } from './testing/stylesheets';

/** Every `@media` query about `feature` in those stylesheets, with its file. */
function mediaQueries(feature: string): { file: string; query: string }[] {
  return Object.entries(STYLESHEETS).flatMap(([file, css]) =>
    [...css.matchAll(/@media\s*([^{]*?)\s*\{/g)]
      .filter(([, query]) => query.includes(feature))
      .map(([, query]) => ({ file, query })),
  );
}

it('lays out for a phone at the width the code moves the map for', () => {
  const queries = mediaQueries('max-width');
  expect(queries.length).toBeGreaterThan(0);
  for (const { file, query } of queries)
    expect({ file, query }).toEqual({ file, query: PHONE_MEDIA });
});

it('sizes for a finger where the code does', () => {
  const queries = mediaQueries('pointer');
  expect(queries.length).toBeGreaterThan(0);
  for (const { file, query } of queries)
    expect({ file, query }).toEqual({ file, query: TOUCH_MEDIA });
});

it('keeps what sits below the phone bar clear of the notch, as the bar is', () => {
  const belowBar = declarations().filter(
    ({ property, value }) => property === 'top' && value.includes('--bar-height'),
  );
  expect(belowBar.length).toBeGreaterThan(0);
  for (const { file, value } of belowBar)
    expect({ file, value }).toEqual({ file, value: expect.stringContaining('var(--safe-top)') });
});
