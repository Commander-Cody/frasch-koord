import { expect, it } from 'vitest';

import de from './locales/de.json';
import i18n from './i18n';

// Languages made up here, so no test depends on which locale files exist.
const WITH_STRINGS = 'frr-x-with';
const WITHOUT_STRINGS = 'frr-x-none';

it('names the page in the UI language', async () => {
  await i18n.changeLanguage('de');
  expect(document.title).toBe(de.app.title);
});

it('gives the page the language its UI is in', async () => {
  i18n.addResourceBundle(WITH_STRINGS, 'translation', { app: { title: 'With' } });
  await i18n.changeLanguage(WITH_STRINGS);
  expect(document.documentElement.lang).toBe(WITH_STRINGS);
});

it('gives the page German when its UI language has no strings: the UI falls back to German', async () => {
  await i18n.changeLanguage(WITHOUT_STRINGS);
  expect(document.documentElement.lang).toBe('de');
});
