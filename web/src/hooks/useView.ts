import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { labelOption } from '../config';
import { initialView } from '../urlState';

/**
 * The selected label option — a dialect tag, or LOCAL_TAG for the local view —
 * and the function that switches it. Starts in the view the link names.
 *
 * Map labels and UI chrome move together: each option names the UI language
 * it comes with (the local view has no dialect of its own and borrows one,
 * see config.LOCAL_VIEW_UI_LANGUAGE). i18next falls back to German for any
 * language without resources, so unwritten dialect UIs are harmless.
 */
export function useView(): [string, (view: string) => void] {
  const { i18n } = useTranslation();
  const [view, setView] = useState(initialView);
  const changeView = (tag: string) => {
    setView(tag);
    void i18n.changeLanguage(labelOption(tag).uiLanguage);
  };
  return [view, changeView];
}
