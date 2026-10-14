import { useId, useMemo, useState } from 'react';
import type { KeyboardEvent, Ref } from 'react';
import { useTranslation } from 'react-i18next';

import type { NameEntry } from '../names/entry';
import type { NamesData } from '../names/load';
import { displayName } from '../names/resolveName';
import type { Search } from '../names/search';

export interface SearchBoxProps {
  /** The search over the name list, loaded once by App (see names/load.ts). */
  search: Search;
  /** Whether that list is there yet, or failed to load. */
  status: NamesData['status'];
  /** Selected label option tag (a dialect, or LOCAL_TAG): results are named as the map labels them. */
  view: string;
  onSelect: (entry: NameEntry) => void;
  /** The search field: focus returns there when the card closes (see usePlaceSelection). */
  ref?: Ref<HTMLInputElement>;
}

/**
 * The search field with its list of results, a combobox. Renders no element
 * of its own around the two: they are placed by the grid of the bar they are
 * in (ControlBar, App.css).
 */
export default function SearchBox({ search, status, view, onSelect, ref }: SearchBoxProps) {
  const { t } = useTranslation();
  const listId = useId();
  const [query, setQuery] = useState('');
  // Results are hidden after a selection until the user types again (or
  // asks for them with Enter): focus coming back to the field, as it does
  // when the card closes from the keyboard, does not bring them back.
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  const results = useMemo(() => search(query), [search, query]);

  // Without the name list there is nothing to search: say so once, under
  // the field, instead of "no results" to every query.
  const failed = status === 'error';
  const showList = open && !failed && query.trim().length > 0;

  const select = (entry: NameEntry) => {
    setQuery(displayName(entry, view));
    setOpen(false);
    setPicked(true);
    // The card this opens takes focus (see usePlaceSelection).
    onSelect(entry);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    // Escape in the field is the field's: it closes the result list (and the
    // browser clears a search field on it), never the place card too, which
    // listens for Escape on the window (useCloseOnEscape).
    if (e.key === 'Escape') e.stopPropagation();
    if (!showList) {
      // Enter on a closed list re-runs the search for the current text.
      if (e.key === 'Enter' && query.trim().length > 0) {
        setOpen(true);
        setActiveIdx(0);
      }
      return;
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIdx((i) => (results.length ? (i + 1) % results.length : 0));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActiveIdx((i) => (results.length ? (i - 1 + results.length) % results.length : 0));
        break;
      case 'Enter': {
        e.preventDefault();
        const entry = results[activeIdx] ?? results[0];
        if (entry) select(entry);
        break;
      }
      case 'Escape':
        setOpen(false);
        break;
      default:
        break;
    }
  };

  return (
    <>
      <input
        ref={ref}
        type="search"
        className="search-input"
        aria-label={t('search.label')}
        placeholder={t('search.placeholder')}
        disabled={failed}
        value={query}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={
          showList && results[activeIdx] ? `${listId}-${activeIdx}` : undefined
        }
        autoComplete="off"
        onChange={(e) => {
          setQuery(e.target.value);
          setPicked(false);
          setOpen(true);
          setActiveIdx(0);
        }}
        onFocus={() => setOpen(!picked)}
        onBlur={() => setOpen(false)}
        onKeyDown={handleKeyDown}
      />
      {failed && (
        <p className="search-error" role="alert">
          {t('search.error')}
        </p>
      )}
      {showList && (
        <ul
          id={listId}
          className="search-results"
          // The WAI-ARIA combobox pattern: the input controls a list of
          // options, which no native element offers (<datalist> cannot be styled
          // or labelled per option, <select> is not a search field).
          // eslint-disable-next-line jsx-a11y/no-noninteractive-element-to-interactive-role
          role="listbox"
        >
          {results.length === 0 && (
            <li className="search-empty">
              {t(status === 'loading' ? 'search.loading' : 'search.noResults')}
            </li>
          )}
          {results.map((entry, i) => {
            const name = displayName(entry, view);
            return (
              <li
                key={entry.id}
                id={`${listId}-${i}`}
                // eslint-disable-next-line jsx-a11y/no-noninteractive-element-to-interactive-role -- see the listbox
                role="option"
                aria-selected={i === activeIdx}
                className={i === activeIdx ? 'is-active' : undefined}
              >
                <button
                  type="button"
                  tabIndex={-1}
                  // onMouseDown so the click wins over the input's blur.
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => select(entry)}
                  onMouseEnter={() => setActiveIdx(i)}
                >
                  <span className="search-result-name">{name}</span>
                  {entry.name_de && entry.name_de !== name && (
                    <span className="search-result-de">{entry.name_de}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
