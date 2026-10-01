/**
 * One OSM object the curation view offers for a row — a candidate of the
 * worklist or a lookup result: its number and colour (as on its map pin), a
 * checkbox for a multi-object pick, and "Pick" for this object alone.
 */
import { singleWikidataId } from './curatePatch';

export interface RefItemProps {
  osmRef: string;
  /** The number on its pin. */
  number: number;
  color: string;
  name: string;
  meta: string;
  /** The object's `wikidata` tag, as OSM has it. */
  wikidataTag?: string;
  /** The candidate last clicked, here or on the map. */
  active?: boolean;
  checked: boolean;
  onToggle: () => void;
  /** Shows the object: a click on the item. */
  onShow: () => void;
  onPick: () => void;
}

export default function RefItem(props: RefItemProps) {
  const {
    osmRef,
    number,
    color,
    name,
    meta,
    wikidataTag,
    active = false,
    checked,
    onToggle,
    onShow,
    onPick,
  } = props;
  const className = [active ? 'is-active' : '', checked ? 'is-checked' : '']
    .filter(Boolean)
    .join(' ');
  return (
    <li className={className || undefined}>
      <input
        type="checkbox"
        className="curate-check-ref"
        aria-label={`select ${osmRef}`}
        checked={checked}
        onChange={onToggle}
      />
      <button type="button" className="curate-candidate" onClick={onShow}>
        <span className="curate-num" style={{ background: color }}>
          {number}
        </span>
        <span className="curate-candidate-body">
          <span className="curate-candidate-name">{name}</span>
          <span className="dev-panel-mono curate-mono">{osmRef}</span>
          <span className="curate-candidate-meta">{meta}</span>
          {wikidataTag && !singleWikidataId(wikidataTag) && (
            <span className="curate-candidate-warning">
              wikidata {wikidataTag}: not one id, not saved
            </span>
          )}
        </span>
      </button>
      <button type="button" className="curate-pick" onClick={onPick}>
        Pick
      </button>
    </li>
  );
}
