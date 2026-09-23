import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import de from './locales/de.json';
import frrMooring from './locales/frr-x-mooring.json';
import { labelOption } from './config';
import { INITIAL_LABELS } from './urlState';

// Mooring UI strings that nobody has written yet (see
// src/locales/frr-x-mooring.json) are left as empty strings - never invented -
// so that i18next falls back to German
// (fallbackLng) instead of rendering blank UI text; returnEmptyString:false
// is what makes an empty string count as "missing" for fallback purposes.
void i18n.use(initReactI18next).init({
  resources: {
    de: { translation: de },
    'frr-x-mooring': { translation: frrMooring },
  },
  // The initial UI language is the one of the label option the page opens
  // in, the link's `?view=` or the default (App switches it on every
  // selector change).
  lng: labelOption(INITIAL_LABELS).uiLanguage,
  fallbackLng: 'de',
  returnEmptyString: false,
  interpolation: { escapeValue: false },
});

export default i18n;
