import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import MiniSearch from 'minisearch';

import { DIALECTS } from '../config';

export interface NameEntry {
  id: string;
  name: string;
  name_de: string;
  lon: number;
  lat: number;
  kind: string;
}

export interface SearchPanelProps {
  dialect: string;
  onDialectChange: (dialect: string) => void;
  onSelect: (entry: NameEntry) => void;
}

const MAX_RESULTS = 8;

function createIndex() {
  return new MiniSearch<NameEntry>({
    fields: ['name', 'name_de'],
    storeFields: ['id', 'name', 'name_de', 'lon', 'lat', 'kind'],
    searchOptions: { prefix: true, fuzzy: 0.2 },
  });
}

export default function SearchPanel({ dialect, onDialectChange, onSelect }: SearchPanelProps) {
  const { t } = useTranslation();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [index, setIndex] = useState<MiniSearch<NameEntry> | null>(null);
  const [query, setQuery] = useState('');
  // Results are hidden after a selection until the user types again.
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch('/data/names.json')
      .then((res) => res.json())
      .then((entries: NameEntry[]) => {
        if (cancelled) return;
        const idx = createIndex();
        idx.addAll(entries);
        setIndex(idx);
      })
      .catch((err: unknown) => {
        console.error('Failed to load names.json', err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const results = useMemo<NameEntry[]>(() => {
    if (!index || query.trim().length === 0) return [];
    // MiniSearch spreads the stored fields onto each result object.
    return index.search(query).slice(0, MAX_RESULTS) as unknown as NameEntry[];
  }, [index, query]);

  const showList = open && query.trim().length > 0;

  const select = (entry: NameEntry) => {
    setQuery(entry.name);
    setOpen(false);
    onSelect(entry);
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
      <select
        className="dialect-select"
        aria-label={t('dialect.label')}
        value={dialect}
        onChange={(e) => onDialectChange(e.target.value)}
      >
        {DIALECTS.map((d) => (
          <option key={d.tag} value={d.tag}>
            {d.label}
          </option>
        ))}
      </select>
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
          {results.map((entry, i) => (
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
                <span className="search-result-name">{entry.name}</span>
                {entry.name_de && entry.name_de !== entry.name && (
                  <span className="search-result-de">{entry.name_de}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
