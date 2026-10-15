/**
 * The municipalities the filter lets through, under their dialect: one
 * button each, the selected one marked and kept in view.
 */
import type { RefCallback } from 'react';

import { areaKey, groupLabel, type DialectGroup } from './areas';
import { groupColor } from './areaLayers';
import Swatch from './Swatch';

export interface AreaListProps {
  sections: DialectGroup[];
  selected: string | null;
  onSelect: (key: string) => void;
  /** useSelection's `itemRef`. */
  itemRef: (key: string) => RefCallback<HTMLElement> | undefined;
}

export default function AreaList({ sections, selected, onSelect, itemRef }: AreaListProps) {
  if (sections.length === 0) return <p className="dev-panel-hint">nothing matches that filter</p>;
  return sections.map(({ key, features }) => (
    <section key={key}>
      <h3 className="dev-panel-section">
        <Swatch color={groupColor(key)} /> {groupLabel(key)} ({features.length})
      </h3>
      <ul className="dev-panel-list">
        {features.map(({ properties }) => {
          const area = areaKey(properties);
          return (
            <li key={area} ref={itemRef(area)}>
              <button
                type="button"
                className={`dev-panel-rowbutton${area === selected ? ' is-selected' : ''}`}
                onClick={() => onSelect(area)}
              >
                <span>{properties.name || '(unnamed)'}</span>
                {properties.line !== undefined && (
                  <span className="area-line">{properties.line}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  ));
}
