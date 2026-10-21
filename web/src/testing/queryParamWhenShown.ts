// What the address bar says at the moment a change first reaches the page:
// for a test that the URL is kept in the same commit as what is shown, which
// a read after `findByText` cannot tell (the page has gone on by then).

import { getConfig } from '@testing-library/react';

import { readQueryParam } from '../url/queryParams';

/**
 * The query parameter `name` as it is when `text` first shows in the page.
 * Call it before the action that brings `text` up; it gives up after as long
 * as a `findBy…` query waits.
 */
export function queryParamWhenShown(name: string, text: string): Promise<string | undefined> {
  return new Promise((resolve, reject) => {
    const observer = new MutationObserver(() => {
      if (!document.body.textContent?.includes(text)) return;
      settle();
      resolve(readQueryParam(name));
    });
    const timeout = setTimeout(() => {
      settle();
      reject(new Error(`?${name}= was to be read once "${text}" showed, but it never did`));
    }, getConfig().asyncUtilTimeout);
    function settle() {
      observer.disconnect();
      clearTimeout(timeout);
    }
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  });
}
