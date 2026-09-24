import { useCallback, useMemo } from 'react';
import type { Ref } from 'react';
import { useTranslation } from 'react-i18next';

import { DIALECTS, dialect, dialectLabelKey } from '../config';
import type { DialectEntry } from '../config';
import type { PlaceSelection } from '../names';
import { cardEntry, osmUrl, placeRef, resolveName, wikidataUrl } from '../names';
import './PlaceCard.css';

export interface PlaceCardProps {
  selection: PlaceSelection;
  /** Selected label option tag (a dialect, or LOCAL_TAG) — the view the headline is in. */
  labels: string;
  onClose: () => void;
  /** The card element: App measures it, where it is the phone bottom sheet. */
  ref?: Ref<HTMLElement>;
}

/** One line of the name list below the headline. */
interface Line {
  key: string;
  label: string;
  /** Registry label of an extinct dialect gets a marker; nothing else does. */
  extinct?: boolean;
  name: string;
  /** The sub-dialect the local form belongs to (`frasch:variety`). */
  note?: string;
}

/**
 * The card for one place: its name in the selected view, every other dialect
 * the name list has a name in, the local form, Low Saxon, German and Danish,
 * and links to the objects behind it.
 *
 * Its data is `cardEntry(selection)` — the name-list entry where the place has
 * one, filled up from the clicked tile feature (see names.ts).
 */
export default function PlaceCard({ selection, labels, onClose, ref: cardRef }: PlaceCardProps) {
  const { t } = useTranslation();
  const entry = useMemo(() => cardEntry(selection), [selection]);
  // Dialect names are translated like any other UI string; the registry
  // label covers a dialect the locale files do not know yet.
  const dialectLabel = useCallback(
    (d: DialectEntry) => t(dialectLabelKey(d.tag), { defaultValue: d.label }),
    [t],
  );

  // What the headline actually is — the selected dialect only when that
  // dialect has a name for the place. The card must not label a fallback
  // with the dialect the map claims to be in.
  const { name: headline, source: shownAs } = resolveName(entry, labels);
  const area = entry.dialect ? dialect(entry.dialect) : undefined;
  const shownDialect = dialect(shownAs);
  const kind = entry.kind ? t(`kind.${entry.kind}`, { defaultValue: '' }) : '';
  // The local form is named after the area's dialect only when it IS that
  // dialect's name. Where the place has a form of its own (Woiguurd, while
  // Mooring says Waiguurd), calling both "Mooring" would contradict itself.
  const localIsAreaName = area !== undefined && entry.names?.[area.tag] === entry.local;
  const localLabel = localIsAreaName ? `${t('card.local')} · ${dialectLabel(area)}` : t('card.local');
  const headlineLabel =
    shownAs === 'local'
      ? localLabel
      : shownAs === 'frr'
        ? t('card.frisian')
        : shownAs === 'nds'
          ? t('card.lowSaxon')
          : shownAs === 'de'
            ? t('card.german')
            : shownAs === 'da'
              ? t('card.danish')
              : shownDialect && dialectLabel(shownDialect);

  const lines = useMemo<Line[]>(() => {
    const out: Line[] = [];
    for (const d of DIALECTS) {
      const name = entry.names?.[d.tag];
      if (!name) continue;
      // The headline already shows this one.
      if (d.tag === shownAs) continue;
      // The area's own dialect falls back to the `local` column in
      // names/dialects.py, so its name can be the very same string as the
      // local form. Show it once, on the local line, which names the dialect.
      if (d.tag === entry.dialect && name === entry.local) continue;
      out.push({ key: d.tag, label: dialectLabel(d), extinct: d.status === 'extinct', name });
    }
    // Not when the headline is already that form: the selected dialect's
    // name and the local one are the same string wherever the place lies in
    // that dialect's own area (Niebüll in Mooring).
    if (entry.local && shownAs !== 'local' && entry.local !== headline) {
      out.push({ key: 'local', label: localLabel, name: entry.local, note: entry.variety });
    }
    // OSM's dialect-less Frisian name, for places our list does not have.
    // Where it only repeats a name already on the card (it usually is the
    // same word as the dialect's), it says nothing worth a line.
    if (entry.name_frr && ![headline, ...out.map((l) => l.name)].includes(entry.name_frr)) {
      out.push({ key: 'frr', label: t('card.frisian'), name: entry.name_frr });
    }
    // Low Saxon only where it says something German does not: most places
    // are the same word in both (Husum).
    if (entry.name_nds && entry.name_nds !== headline && entry.name_nds !== entry.name_de) {
      out.push({ key: 'nds', label: t('card.lowSaxon'), name: entry.name_nds });
    }
    if (entry.name_de && entry.name_de !== headline) {
      out.push({ key: 'de', label: t('card.german'), name: entry.name_de });
    }
    if (entry.name_da && entry.name_da !== headline) {
      out.push({ key: 'da', label: t('card.danish'), name: entry.name_da });
    }
    return out;
  }, [entry, shownAs, headline, localLabel, dialectLabel, t]);

  const ref = placeRef(selection);
  const osm = osmUrl(ref ?? undefined);
  const wikidata = wikidataUrl(entry.wikidata);
  // The "report a wrong or missing name" link belongs here; it is issue #8.

  return (
    <aside ref={cardRef} className="place-card" aria-label={t('card.title')}>
      <button type="button" className="place-card-close" aria-label={t('card.close')} onClick={onClose}>
        ×
      </button>
      <h2 className="place-card-name">{headline}</h2>
      <p className="place-card-meta">
        {headlineLabel}
        {/* Where the headline IS the local form, its variety remark belongs
            here — there is no local line below to carry it. */}
        {entry.variety && entry.local === headline && (
          <span className="place-card-note">{entry.variety}</span>
        )}
        {kind && <span className="place-card-kind">{kind}</span>}
      </p>
      {lines.length > 0 && (
        <dl className="place-card-names">
          {lines.map((line) => (
            <div key={line.key}>
              <dt>
                {line.label}
                {line.extinct && <abbr title={t('card.extinct')}>&nbsp;†</abbr>}
              </dt>
              <dd>
                {line.name}
                {line.note && <span className="place-card-note">{line.note}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {(osm || wikidata) && (
        <p className="place-card-links">
          {osm && (
            <a href={osm} target="_blank" rel="noopener noreferrer">
              {t('card.osm')}
            </a>
          )}
          {wikidata && (
            <a href={wikidata} target="_blank" rel="noopener noreferrer">
              {t('card.wikidata')}
            </a>
          )}
        </p>
      )}
    </aside>
  );
}
