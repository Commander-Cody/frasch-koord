/**
 * The dialects of the review view (`?areas`) with their colours and how many
 * municipalities each has. Doubles as the map filter: a click draws that
 * dialect alone, a second click all of them again.
 */
import type { DialectGroup } from './areas';
import { groupLabel } from './areas';
import { groupColor } from './areaLayers';
import Swatch from './Swatch';

export interface AreaLegendProps {
  groups: DialectGroup[];
  /** The group drawn alone, if any. */
  shown: string | null;
  onShow: (key: string | null) => void;
}

export default function AreaLegend({ groups, shown, onShow }: AreaLegendProps) {
  return (
    <ul className="dev-panel-list area-legend">
      {groups.map(({ key, features }) => (
        <li key={key}>
          <button
            type="button"
            className={`area-legend-item${shown === key ? ' is-active' : ''}`}
            title="show only this one on the map"
            onClick={() => onShow(shown === key ? null : key)}
          >
            <Swatch color={groupColor(key)} />
            <span>{groupLabel(key)}</span>
            <span className="area-legend-count">{features.length}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
