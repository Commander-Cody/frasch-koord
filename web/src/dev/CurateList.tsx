/**
 * The curation view's worklist: one button per row the filter lets through,
 * marked when selected or decided. Keeps the selected row in view when it
 * moved by keyboard.
 */
import { useEffect, useRef } from 'react';

import type { PatchEntry } from './curatePatch';
import type { CurateRow } from './curateWorklist';

export interface CurateListProps {
  rows: CurateRow[];
  /** The decision per row id (see curatePatch.decidedRows). */
  doneById: Map<string, PatchEntry>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function CurateList({ rows, doneById, selectedId, onSelect }: CurateListProps) {
  const listRef = useRef<HTMLUListElement | null>(null);
  useEffect(() => {
    listRef.current?.querySelector('.is-selected')?.scrollIntoView({ block: 'nearest' });
  }, [selectedId]);

  return (
    <ul className="curate-list" ref={listRef}>
      {rows.length === 0 && <li className="curate-empty">nothing matches the filter</li>}
      {rows.map((row) => {
        const done = doneById.get(row.id);
        const className = [
          'curate-item',
          row.id === selectedId ? 'is-selected' : '',
          done ? 'is-done' : '',
        ]
          .filter(Boolean)
          .join(' ');
        return (
          <li key={row.id} className={className}>
            <button type="button" onClick={() => onSelect(row.id)}>
              <span className="curate-item-head">
                <span className="curate-item-name">{row.name}</span>
                <span className="curate-item-de">{row.name_de || row.name_da}</span>
                <span className={`curate-badge curate-badge-${row.result}`}>{row.kind}</span>
              </span>
              {row.hint && <span className="curate-item-hint">{row.hint}</span>}
              {done && <span className="curate-item-done">{doneLabel(done)}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function doneLabel(done: PatchEntry): string {
  if (done.action === 'osm') return `✓ ${done.osm ?? ''}`;
  if (done.action === 'local') return `✓ local/${done.slug ?? ''}`;
  if (done.action === 'skip') return '✓ skipped';
  return '';
}
