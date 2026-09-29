import { expect, it } from 'vitest';

import i18n from './i18n';

it('names the page in the UI language', async () => {
  await i18n.changeLanguage('de');
  expect(document.title).toBe('Frasch Maps');
});
