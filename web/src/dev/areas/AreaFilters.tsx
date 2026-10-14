/** The review view's counts and its text filter, in the sticky header. */
import type { AreaFeature } from './areas';

export interface AreaFiltersProps {
  text: string;
  onText: (text: string) => void;
  /** Every municipality, for the counts. */
  features: readonly AreaFeature[];
  /** How many the filter lets through. */
  shown: number;
}

export default function AreaFilters({ text, onText, features, shown }: AreaFiltersProps) {
  const assigned = features.filter((feature) => feature.properties.assigned).length;
  return (
    <>
      <p className="dev-panel-counts">
        {assigned} assigned · {features.length - assigned} not assigned · {shown} shown
      </p>
      <input
        className="dev-panel-input"
        value={text}
        aria-label="filter by name, OSM reference or note"
        placeholder="filter by name, osm ref or note…"
        onChange={(event) => onText(event.target.value)}
      />
    </>
  );
}
