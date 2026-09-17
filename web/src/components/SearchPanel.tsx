import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import MiniSearch from 'minisearch';

import { LABEL_OPTIONS, LOCAL_TAG } from '../config';

/**
 * One entry of public/data/names.json, written by names/export_search_index.py.
 * Only non-empty values are exported, so every optional field is genuinely
 * absent rather than an empty string.
 */
export interface NameEntry {
  /** Stable identifier, e.g. "node/240044177" (or "<osm id>#<csv line>" for a second row on the same object), or "local/<slug>" for a place OSM does not have. */
  id: string;
  /** Dialect names by registry tag, e.g. { "frr-x-mooring": "Naibel" }. */
  names: Record<string, string>;
  /** Name used by the people of the place itself (tile attribute `frasch:local`). */
  local?: string;
  /** Dialect area the place lies in, e.g. "frr-x-fering". */
  dialect?: string;
  /** Sub-dialect remark of the local name, e.g. "Foortuftinge". */
  variety?: string;
  /** German name, shown as a hint next to a Frisian one. */
  name_de: string;
  lon: number;
  lat: number;
  kind: string;
}

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
  /** Selected label option tag (a dialect, or LOCAL_TAG). */
  labels: string;
  onLabelsChange: (labels: string) => void;
  /** `name` is the entry's display name in the current view (for the map marker). */
  onSelect: (entry: NameEntry, name: string) => void;
}

const MAX_RESULTS = 8;

/**
 * The name to show for an entry in the selected view: the selected dialect's
 * own name, else the local Frisian one, else German — the search-result
 * counterpart of the label chain in style/localize.ts. The local view shows
 * only the local name (plus German as a last resort), never another dialect's.
 */
function displayName(entry: NameEntry, labels: string): string {
  if (labels === LOCAL_TAG) return entry.local ?? entry.name_de;
  // `?.` because names.json is fetched, not type-checked: an archive built
  // before the multi-dialect schema has no `names` object at all.
  return entry.names?.[labels] ?? entry.local ?? entry.name_de;
}

function createIndex() {
  return new MiniSearch<IndexedEntry>({
    fields: ['text'],
    storeFields: ['id', 'names', 'local', 'dialect', 'variety', 'name_de', 'lon', 'lat', 'kind'],
    searchOptions: { prefix: true, fuzzy: 0.2 },
  });
}

/** Flattens all of an entry's names into the indexed `text` field, deduplicated. */
function toIndexed(entry: NameEntry): IndexedEntry {
  const all = [...Object.values(entry.names ?? {}), entry.local, entry.name_de];
  return { ...entry, text: [...new Set(all.filter(Boolean))].join(' ') };
}

export default function SearchPanel({ labels, onLabelsChange, onSelect }: SearchPanelProps) {
  const { t } = useTranslation();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [index, setIndex] = useState<MiniSearch<IndexedEntry> | null>(null);
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
        idx.addAll(entries.map(toIndexed));
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
            {option.label ?? (option.labelKey ? t(option.labelKey) : option.tag)}
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
