/**
 * A clicked map label of an object the name list does not have (see
 * labelClicks.ts), and the new place it offers to start from it.
 */
import type { ClickedLabel } from './labelClicks';

export interface LabelOfferProps {
  label: ClickedLabel;
  onCreate: () => void;
  onDismiss: () => void;
}

export default function LabelOffer({ label, onCreate, onDismiss }: LabelOfferProps) {
  return (
    <div className="curate-label">
      <span className="dev-panel-mono curate-mono">
        {label.name || 'a label without a name'}
        {label.ref && ` · ${label.ref}`}
      </span>
      <div className="curate-row">
        <button type="button" onClick={onCreate}>
          New place from this
        </button>
        <button type="button" onClick={onDismiss}>
          dismiss
        </button>
      </div>
    </div>
  );
}
