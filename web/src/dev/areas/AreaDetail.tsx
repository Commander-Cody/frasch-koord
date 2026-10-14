/**
 * The selected municipality of the review view: its dialect, its row in
 * names/dialect_areas.csv and the row's research note — or, for one no row
 * claims, how to add it.
 */
import { osmRefs, osmUrl } from '../../names/osmRef';
import { groupKey, groupLabel, type AreaProps } from './areas';
import { groupColor } from './areaLayers';
import Swatch from './Swatch';

export default function AreaDetail({ area }: { area: AreaProps }) {
  return (
    <section className="dev-panel-detail">
      <h2 className="dev-panel-detail-title">{area.name || '(unnamed)'}</h2>
      <dl className="dev-panel-facts">
        <div>
          <dt>dialect</dt>
          <dd>
            {area.dialect ? (
              <>
                <Swatch color={groupColor(groupKey(area))} /> {groupLabel(area.dialect)}{' '}
                <span className="dev-panel-mono">{area.dialect}</span>
              </>
            ) : (
              <em>not in dialect_areas.csv</em>
            )}
          </dd>
        </div>
        {area.line !== undefined && (
          <div>
            <dt>row</dt>
            <dd className="dev-panel-mono">dialect_areas.csv:{area.line}</dd>
          </div>
        )}
        <div>
          <dt>area</dt>
          <dd>{area.km2} km²</dd>
        </div>
        <div>
          <dt>osm</dt>
          <dd className="area-refs">
            {osmRefs(area.osm).map((ref) => (
              <a
                key={ref}
                className="dev-panel-mono"
                href={osmUrl(ref) ?? undefined}
                target="_blank"
                rel="noopener"
              >
                {ref}
              </a>
            ))}
          </dd>
        </div>
      </dl>
      {area.assigned ? <Note note={area.note} /> : <AddRow osm={area.osm} />}
    </section>
  );
}

/** The research note, verbatim: it is the reason the row says what it says. */
function Note({ note }: { note?: string }) {
  if (!note) return <p className="dev-panel-hint">no note on this row</p>;
  return <p className="area-note">{note}</p>;
}

/** How to give a municipality no row claims a dialect. */
function AddRow({ osm }: { osm: string }) {
  return (
    <div className="area-add">
      <p className="dev-panel-hint">
        No row claims this municipality, so nothing inside it gets a dialect. To add it, paste this
        into <code>names/dialect_areas.csv</code>, re-run <code>just rebuild areas</code>, then
        press Reload.
      </p>
      <button type="button" onClick={() => void navigator.clipboard?.writeText(osm)}>
        copy {osm}
      </button>
    </div>
  );
}
