/**
 * "Look up in OSM" of the curation view: the query, the Nominatim and
 * Overpass buttons (osmLookup.ts), a link to search openstreetmap.org
 * itself, and the results, numbered like their pins on the map.
 */
import { COLOR_LOOKUP } from './curateMapLayers';
import { LOOKUP_SERVICES, type LookupResult, type OsmLookup } from './osmLookup';
import RefItem from './RefItem';

export interface CurateLookupProps {
  lookup: OsmLookup;
  isChecked: (ref: string) => boolean;
  onToggle: (ref: string, wikidata?: string) => void;
  onShow: (result: LookupResult) => void;
  onPick: (ref: string, wikidata?: string) => void;
}

export default function CurateLookup({
  lookup,
  isChecked,
  onToggle,
  onShow,
  onPick,
}: CurateLookupProps) {
  const { query, setQuery, results, source, busy, error, run } = lookup;
  return (
    <>
      <h3 className="dev-panel-section">Look up in OSM</h3>
      <input
        className="dev-panel-input"
        value={query}
        aria-label="lookup query"
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="curate-row">
        {LOOKUP_SERVICES.map((service) => (
          <button key={service} type="button" disabled={busy} onClick={() => void run(service)}>
            {service}
          </button>
        ))}
        <a
          href={`https://www.openstreetmap.org/search?query=${encodeURIComponent(query)}#map=10/54.7/8.9`}
          target="_blank"
          rel="noreferrer"
        >
          openstreetmap.org
        </a>
      </div>
      {busy && <p className="dev-panel-hint">searching…</p>}
      {error && <p className="dev-panel-error">{error}</p>}
      {source && !error && <p className="dev-panel-hint">{source}</p>}
      <ul className="curate-candidates">
        {results.map((result, i) => (
          <RefItem
            key={`${result.ref}-${i}`}
            osmRef={result.ref}
            number={i + 1}
            color={COLOR_LOOKUP}
            name={result.name || '(unnamed)'}
            meta={result.what || result.tags}
            wikidataTag={result.wikidata}
            checked={isChecked(result.ref)}
            onToggle={() => onToggle(result.ref, result.wikidata)}
            onShow={() => onShow(result)}
            onPick={() => onPick(result.ref, result.wikidata)}
          />
        ))}
      </ul>
    </>
  );
}
