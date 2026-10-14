import { useEffect, useLayoutEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { labelOption } from '../config';
import { initialView, writeView } from '../url/linkState';

/**
 * Keeps the UI in the language of the label option `view`: map labels and UI
 * chrome move together. Each option names the UI language it comes with (the
 * local view has no dialect of its own and borrows one, see
 * config.LOCAL_VIEW_UI_LANGUAGE). i18next falls back to German for any
 * language without resources, so unwritten dialect UIs are harmless.
 *
 * Before paint, so a page that opens in another view than the default never
 * shows the default's language first.
 */
export function useUiLanguage(view: string): void {
  const { i18n } = useTranslation();
  useLayoutEffect(() => {
    const language = labelOption(view).uiLanguage;
    if (i18n.language !== language) void i18n.changeLanguage(language);
  }, [i18n, view]);
}

/**
 * The selected label option — a dialect tag, or LOCAL_TAG for the local view —
 * and the function that switches it. Starts in the view the link names, and
 * keeps the UI language and the link's `?view=` with it.
 */
export function useView(): [string, (view: string) => void] {
  const [view, setView] = useState(initialView);
  useUiLanguage(view);
  useEffect(() => writeView(view), [view]);
  return [view, setView];
}
