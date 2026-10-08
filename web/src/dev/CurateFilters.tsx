/**
 * The curation view's counts and list filter, in the panel's sticky header.
 */
import type { CurateRow, ResultFilter, RowFilter } from './curateWorklist';

export interface CurateFiltersProps {
  filter: RowFilter;
  onChange: (filter: RowFilter) => void;
  /** The kinds to offer, in the exporter's order. */
  kinds: string[];
  /** The results to offer, as the worklist names them. */
  results: CurateRow['result'][];
  counts: { open: number; done: number; shown: number };
}

export default function CurateFilters({
  filter,
  onChange,
  kinds,
  results,
  counts,
}: CurateFiltersProps) {
  const set = (change: Partial<RowFilter>) => onChange({ ...filter, ...change });
  return (
    <>
      <p className="dev-panel-counts">
        {counts.open} open · {counts.done} done · {counts.shown} shown
      </p>
      <input
        type="search"
        className="dev-panel-input"
        placeholder="filter: Frisian, German, hint"
        value={filter.text}
        onChange={(event) => set({ text: event.target.value })}
      />
      <div className="curate-row">
        <select
          className="dev-panel-input"
          aria-label="kind"
          value={filter.kind}
          onChange={(event) => set({ kind: event.target.value })}
        >
          <option value="">all kinds</option>
          {kinds.map((kind) => (
            <option key={kind} value={kind}>
              {kind}
            </option>
          ))}
        </select>
        <select
          className="dev-panel-input"
          aria-label="result"
          value={filter.result}
          onChange={(event) => set({ result: event.target.value as ResultFilter })}
        >
          <option value="all">all results</option>
          {results.map((result) => (
            <option key={result} value={result}>
              {result.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
      </div>
      <label className="curate-check">
        <input
          type="checkbox"
          checked={filter.hideDone}
          onChange={(event) => set({ hideDone: event.target.checked })}
        />
        hide done
      </label>
    </>
  );
}
