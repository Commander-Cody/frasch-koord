import { useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import MiniSearch from 'minisearch';

import { LABEL_OPTIONS } from '../config';
import type { NameEntry } from '../names';
import { displayName } from '../names';
import ShareButton from './ShareButton';

/**
 * Index document: every name of an entry flattened into one searchable
 * string. A place must be findable under any of its dialect names no matter
 * which view is selected — somebody typing "Naibel" while the map is in
 * Fering still means Niebüll.
 */
interface IndexedEntry extends NameEntry {
  text: string;
}

export interface SearchPanelProps {
  /** The name list, loaded once by App (see names.ts). */
  entries: NameEntry[];
  /** Selected label option tag (a dialect, or LOCAL_TAG). */
  labels: string;
  onLabelsChange: (labels: string) => void;
  /** `name` is the entry's display name in the current view (for the map marker). */
  onSelect: (entry: NameEntry, name: string) => void;
}

const MAX_RESULTS = 8;

function createIndex() {
  return new MiniSearch<IndexedEntry>({
    fields: ['text'],
    // Everything `displayName` reads, so a result is named as its map label is.
    storeFields: ['id', 'names', 'local', 'dialect', 'variety', 'name_nds', 'name_de', 'name_da', 'lon', 'lat', 'kind'],
    searchOptions: { prefix: true, fuzzy: 0.2 },
  });
}

/** Flattens all of an entry's names into the indexed `text` field, deduplicated. */
function toIndexed(entry: NameEntry): IndexedEntry {
  const all = [...Object.values(entry.names ?? {}), entry.local, entry.name_nds, entry.name_de];
  return { ...entry, text: [...new Set(all.filter(Boolean))].join(' ') };
}

export default function SearchPanel({
  entries,
  labels,
  onLabelsChange,
  onSelect,
}: SearchPanelProps) {
  const { t } = useTranslation();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState('');
  // Results are hidden after a selection until the user types again.
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  const index = useMemo(() => {
    if (entries.length === 0) return null;
    const idx = createIndex();
    idx.addAll(entries.map(toIndexed));
    return idx;
  }, [entries]);

  const results = useMemo<NameEntry[]>(() => {
    if (!index || query.trim().length === 0) return [];
    // MiniSearch spreads the stored fields onto each result object.
    return index.search(query).slice(0, MAX_RESULTS) as unknown as NameEntry[];
  }, [index, query]);

  const showList = open && query.trim().length > 0;

  const select = (entry: NameEntry) => {
    const name = displayName(entry, labels);
    setQuery(name);
    setOpen(false);
    onSelect(entry, name);
    inputRef.current?.blur();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
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
    <div className="search-panel">
      <div className="search-panel-row">
        <select
          className="dialect-select"
          aria-label={t('dialect.label')}
          value={labels}
          onChange={(e) => onLabelsChange(e.target.value)}
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
      </div>
      <input
        ref={inputRef}
        type="search"
        className="search-input"
        placeholder={t('search.placeholder')}
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
        onKeyDown={handleKeyDown}
      />
      {showList && (
        <ul id={listId} className="search-results" role="listbox">
          {results.length === 0 && <li className="search-empty">{t('search.noResults')}</li>}
          {results.map((entry, i) => {
            const name = displayName(entry, labels);
            return (
              <li
                key={entry.id}
                id={`${listId}-${i}`}
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
