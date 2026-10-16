import { expect, it } from 'vitest';

import { declarations } from './testing/stylesheets';

/**
 * Where a colour may be spelled out: index.css, which defines the public
 * site's tokens, and the dev tools, which keep a palette of their own.
 */
function mayDefineColours(file: string): boolean {
  return file === '../index.css' || file.startsWith('../dev/');
}

/** Keywords a colour property takes that name no colour of their own. */
const NOT_A_COLOUR = new Set([
  'currentcolor',
  'transparent',
  'inherit',
  'initial',
  'unset',
  'revert',
]);

/** Whether the browser (jsdom here) takes `word` for a colour name. */
function isColourName(word: string): boolean {
  const style = document.createElement('div').style;
  style.color = word;
  return style.color !== '' && !NOT_A_COLOUR.has(word.toLowerCase());
}

/** The colours `value` spells out: hex, colour functions and colour names. */
function colourLiterals(value: string): string[] {
  const words = value.replace(/--[\w-]+/g, '').match(/[a-z][\w-]*/gi) ?? [];
  return [
    ...(value.match(/#[\da-f]{3,8}\b/gi) ?? []),
    ...(value.match(/\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/gi) ?? []),
    ...words.filter(isColourName),
  ];
}

it('takes every colour of the public site from its tokens', () => {
  const spelled = declarations()
    .filter(({ file }) => !mayDefineColours(file))
    .filter(({ value }) => colourLiterals(value).length > 0);
  expect(spelled).toEqual([]);
});
