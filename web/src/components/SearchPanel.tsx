import { useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import MiniSearch from 'minisearch';

import { LABEL_OPTIONS } from '../config';
import type { NameEntry, NamesData } from '../names';
import { displayName } from '../names';
import ShareButton from './ShareButton';

/**
 * Index document: every name of an entry flattened into one searchable
 * string. A place must be findable under any of its dialect names no matter
 * which view is selected — somebody typing "Naibel" while the map is in
 * Fering still means Niebüll. The index keeps only the id; a hit is looked
 * up in the name list again, so the index never has to know its schema.
 */
interface IndexedEntry {
  id: string;
  text: string;
}

/** The index over the name list, and the entries its hits name. */
interface SearchIndex {
  index: MiniSearch<IndexedEntry>;
  byId: Map<string, NameEntry>;
}

export interface SearchPanelProps {
  /** The name list, loaded once by App (see names.ts). */
  entries: NameEntry[];
  /** Whether that list is there yet, or failed to load. */
  status: NamesData['status'];
  /** Selected label option tag (a dialect, or LOCAL_TAG). */
  view: string;
  onViewChange: (view: string) => void;
  /** `name` is the entry's display name in the current view (for the map marker). */
  onSelect: (entry: NameEntry, name: string) => void;
}

const MAX_RESULTS = 8;

/** Flattens all of an entry's names into the indexed `text` field, deduplicated. */
function toIndexed(entry: NameEntry): IndexedEntry {
  const all = [...Object.values(entry.names ?? {}), entry.local, entry.name_nds, entry.name_osm, entry.name_de];
  return { id: entry.id, text: [...new Set(all.filter(Boolean))].join(' ') };
}

/**
 * The entries MiniSearch can take: it throws on one without an `id` and on a
 * second one with the same `id`, which would take search down for the whole
 * list. names.json is fetched, not type-checked, so skip (and log) those.
 */
function indexable(entries: NameEntry[]): NameEntry[] {
  const seen = new Set<string>();
  const kept = entries.filter((e) => {
    if (typeof e?.id !== 'string' || seen.has(e.id)) return false;
    seen.add(e.id);
    return true;
  });
  if (kept.length < entries.length) {
    console.warn(`names.json: skipped ${entries.length - kept.length} entries without an id or with a repeated one`);
  }
  return kept;
}

function createSearchIndex(entries: NameEntry[]): SearchIndex | null {
  if (entries.length === 0) return null;
  const kept = indexable(entries);
  const index = new MiniSearch<IndexedEntry>({
    fields: ['text'],
    searchOptions: { prefix: true, fuzzy: 0.2 },
  });
  index.addAll(kept.map(toIndexed));
  return { index, byId: new Map(kept.map((entry) => [entry.id, entry])) };
}

function search({ index, byId }: SearchIndex, query: string): NameEntry[] {
  return index
    .search(query)
    .slice(0, MAX_RESULTS)
    .flatMap((hit) => byId.get(hit.id) ?? []);
}

export default function SearchPanel({
  entries,
  status,
  view,
  onViewChange,
  onSelect,
}: SearchPanelProps) {
  const { t } = useTranslation();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState('');
  // Results are hidden after a selection until the user types again.
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  const searchIndex = useMemo(() => createSearchIndex(entries), [entries]);

  const results = useMemo<NameEntry[]>(() => {
    if (!searchIndex || query.trim().length === 0) return [];
    return search(searchIndex, query);
  }, [searchIndex, query]);

  // Without the name list there is nothing to search: say so once, under
  // the field, instead of "no results" to every query.
  const failed = status === 'error';
  const showList = open && !failed && query.trim().length > 0;

  const select = (entry: NameEntry) => {
    const name = displayName(entry, view);
    setQuery(name);
    setOpen(false);
    onSelect(entry, name);
    inputRef.current?.blur();
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
    // One flat grid, arranged by App.css: on desktop the selector and the
    // share button above the search field, on a phone all three in one bar.
    // The field comes first, the thing a phone visitor is there for.
    <div className="search-panel">
      <input
        ref={inputRef}
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
        aria-activedescendant={showList && results[activeIdx] ? `${listId}-${activeIdx}` : undefined}
        autoComplete="off"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActiveIdx(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={handleKeyDown}
      />
      <select
        className="dialect-select"
        aria-label={t('dialect.label')}
        value={view}
        onChange={(e) => onViewChange(e.target.value)}
      >
        {LABEL_OPTIONS.map((option) => (
          <option key={option.tag} value={option.tag}>
            {/* Dialect names come from the registry as-is; only the local
                view's name is translated. */}
            {t(option.labelKey, { defaultValue: option.label ?? option.tag })}
          </option>
        ))}
      </select>
      <ShareButton />
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
    </div>
  );
}
