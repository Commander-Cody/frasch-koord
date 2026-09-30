import { expect, it } from 'vitest';

import i18n from './i18n';

it('names the page in the UI language', async () => {
  await i18n.changeLanguage('de');
  expect(document.title).toBe('Frasch Maps');
});

it('gives the page the language its UI is in', async () => {
  await i18n.changeLanguage('frr-x-mooring');
  expect(document.documentElement.lang).toBe('frr-x-mooring');
  // No Fering UI strings yet: its UI is German.
  await i18n.changeLanguage('frr-x-fering');
  expect(document.documentElement.lang).toBe('de');
});
