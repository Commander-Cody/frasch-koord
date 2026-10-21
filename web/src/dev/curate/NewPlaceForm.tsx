/**
 * The form of a place the curation view creates (#113), or edits before
 * `frasch curate apply`: its kind, a cell per name column and a note. It
 * lists the rows that already have a name typed — names do repeat, so that
 * only warns.
 */
import { useState } from 'react';

import { duplicates, isComplete, type PlaceDraft } from './newPlaces';
import type { ListedPlace } from './worklist';

export interface NewPlaceFormProps {
  title: string;
  /** The kinds to offer: every kind, in the worklist's order. */
  kinds: readonly string[];
  /** The name columns to fill in: every one of the worklist, in list order. */
  columns: readonly string[];
  /** The places a name typed may repeat: the rows of the list and the other new places. */
  places: readonly ListedPlace[];
  initial: PlaceDraft;
  /** Inert while the place is on its way to the patch. */
  saving: boolean;
  onSave: (draft: PlaceDraft) => void;
  onCancel: () => void;
}

export default function NewPlaceForm({
  title,
  kinds,
  columns,
  places,
  initial,
  saving,
  onSave,
  onCancel,
}: NewPlaceFormProps) {
  const [draft, setDraft] = useState(initial);
  const setName = (column: string, cell: string) =>
    setDraft({ ...draft, names: { ...draft.names, [column]: cell } });
  const repeated = duplicates(draft.names, places);

  return (
    <section className="dev-panel-detail">
      <h2 className="dev-panel-detail-title">{title}</h2>
      <fieldset className="curate-decisions" disabled={saving} aria-busy={saving}>
        <select
          className="dev-panel-input"
          aria-label="new place kind"
          value={draft.kind}
          onChange={(event) => setDraft({ ...draft, kind: event.target.value })}
        >
          <option value="">kind…</option>
          {kinds.map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
        {columns.map((column) => (
          <input
            key={column}
            className="dev-panel-input"
            placeholder={column}
            aria-label={`new place ${column}`}
            value={draft.names[column] ?? ''}
            onChange={(event) => setName(column, event.target.value)}
          />
        ))}
        <input
          className="dev-panel-input"
          placeholder="note (optional)"
          aria-label="new place note"
          value={draft.note}
          onChange={(event) => setDraft({ ...draft, note: event.target.value })}
        />
        {repeated.length > 0 && <Duplicates places={repeated} />}
        <div className="curate-row">
          <button type="button" disabled={!isComplete(draft)} onClick={() => onSave(draft)}>
            Save place
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </fieldset>
    </section>
  );
}

/** The rows that already have a name typed. */
function Duplicates({ places }: { places: ListedPlace[] }) {
  return (
    <>
      <p className="dev-panel-hint">already in the list (saving is still allowed):</p>
      <ul className="dev-panel-list curate-duplicates" aria-label="already in the list">
        {places.map((place) => (
          <li key={place.id} className="dev-panel-mono curate-mono">
            {place.id} · {place.kind} · {Object.values(place.names).join(' / ')}
          </li>
        ))}
      </ul>
    </>
  );
}
