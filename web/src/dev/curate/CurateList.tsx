/**
 * The curation view's worklist: one button per row the filter lets through,
 * marked when selected or decided, the selected one kept in view.
 */
import type { RefCallback } from 'react';

import { decisionLabel, type PatchEntry } from './patch';
import type { CurateRow } from './worklist';

export interface CurateListProps {
  rows: CurateRow[];
  /** The decision per row id (see patch.decidedRows). */
  doneById: Map<string, PatchEntry>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** useSelection's `itemRef`. */
  itemRef: (id: string) => RefCallback<HTMLElement> | undefined;
}

export default function CurateList({
  rows,
  doneById,
  selectedId,
  onSelect,
  itemRef,
}: CurateListProps) {
  if (rows.length === 0) return <p className="dev-panel-hint">nothing matches the filter</p>;
  return (
    <ul className="dev-panel-list curate-list">
      {rows.map((row) => {
        const done = doneById.get(row.id);
        const className = [
          'dev-panel-rowbutton',
          row.id === selectedId ? 'is-selected' : '',
          done ? 'is-done' : '',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <li key={row.id} ref={itemRef(row.id)}>
            <button type="button" className={className} onClick={() => onSelect(row.id)}>
              <span className="curate-item-head">
                <span className="curate-item-name">{row.name}</span>
                <span className="curate-item-de">{row.name_de || row.name_da}</span>
                <span className={`curate-badge curate-badge-${row.result}`}>{row.kind}</span>
              </span>
              {row.hint && <span className="curate-item-hint">{row.hint}</span>}
              {done && <span className="curate-done">✓ {decisionLabel(done)}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
