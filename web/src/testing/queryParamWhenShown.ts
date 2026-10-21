// What the address bar says at the moment a change first reaches the page:
// for a test that the URL is kept in the same commit as what is shown, which
// a read after `findByText` cannot tell (the page has gone on by then).

import { readQueryParam } from '../url/queryParams';

/**
 * The query parameter `name` as it is when `text` first shows in the page.
 * Call it before the action that brings `text` up; it waits for as long as
 * the test runs if `text` never shows.
 */
export function queryParamWhenShown(name: string, text: string): Promise<string | undefined> {
  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      if (!document.body.textContent?.includes(text)) return;
      observer.disconnect();
      resolve(readQueryParam(name));
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  });
}
