import { useMemo } from 'react';
import type { Ref } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';

import { dialect, dialectLabelKey } from '../config';
import { cardModel } from '../names/card';
import { placeOsmRef, wikidataUrl } from '../names/links';
import type { Language, NameSource } from '../names/resolveName';
import { osmUrl } from '../osmRef';
import type { CloseMeans, PlaceSelection } from '../placeSelection';
import CloseButton from './CloseButton';
import './PlaceCard.css';

export interface PlaceCardProps {
  selection: PlaceSelection;
  /** Selected label option tag (a dialect, or LOCAL_TAG) — the view the headline is in. */
  view: string;
  /** `keyboard`: closed with Enter or Space on ×, rather than by a click or tap. */
  onClose: (means: CloseMeans) => void;
  /** The card element: it is measured where it is the phone bottom sheet. */
  ref?: Ref<HTMLElement>;
  /** The headline: a search pick moves focus there (see usePlaceSelection). */
  headingRef?: Ref<HTMLHeadingElement>;
}

/** Locale keys of the labels of the names in no dialect of the registry. */
const LANGUAGE_LABEL_KEYS: Record<Language, string> = {
  frr: 'card.frisian',
  nds: 'card.lowSaxon',
  de: 'card.german',
  da: 'card.danish',
};

/**
 * The name of a dialect. Dialect names are translated like any other UI
 * string; the registry label covers a dialect the locale files do not know
 * yet. None for a tag the registry does not have.
 */
function dialectLabel(tag: string | undefined, t: TFunction): string {
  const entry = tag === undefined ? undefined : dialect(tag);
  return entry ? t(dialectLabelKey(entry.tag), { defaultValue: entry.label }) : '';
}

/** What a name is called on the card; nothing for one of unknown source. */
function sourceLabel(source: NameSource, t: TFunction): string {
  switch (source.kind) {
    case 'dialect':
      return dialectLabel(source.tag, t);
    case 'local': {
      const area = dialectLabel(source.dialect, t);
      return area ? `${t('card.local')} · ${area}` : t('card.local');
    }
    case 'language':
      return t(LANGUAGE_LABEL_KEYS[source.language]);
    case 'unknown':
      return '';
  }
}

/** Only the name in an extinct dialect of the registry gets a marker. */
function isExtinct(source: NameSource): boolean {
  return source.kind === 'dialect' && dialect(source.tag)?.status === 'extinct';
}

/** A line's React key: a card has one line per source. */
function sourceKey(source: NameSource): string {
  if (source.kind === 'dialect') return source.tag;
  return source.kind === 'language' ? source.language : source.kind;
}

/**
 * The card for one place: its name in the selected view, every other dialect
 * the name list has a name in, the local form, Low Saxon, German and Danish,
 * and links to the objects behind it.
 *
 * Which names it shows, and in which order, is `cardModel` of the selection
 * (names/card.ts); this gives each its label.
 */
export default function PlaceCard({
  selection,
  view,
  onClose,
  ref: cardRef,
  headingRef,
}: PlaceCardProps) {
  const { t, i18n } = useTranslation();
  const card = useMemo(() => cardModel(selection, view), [selection, view]);
  // A kind without a word in the locale files names no kind at all (an empty
  // `defaultValue` would not do: returnEmptyString is off, see i18n.ts).
  const kindKey = `kind.${card.kind}`;
  const kind = card.kind && i18n.exists(kindKey) ? t(kindKey) : '';

  // What only a click on the map brings along: the feature's tile.
  const featureId = selection.pick.via === 'map' ? selection.pick.featureId : undefined;
  const osm = osmUrl(placeOsmRef(selection.entry, featureId) ?? undefined);
  const wikidata = wikidataUrl(selection.entry?.wikidata);
  // The "report a wrong or missing name" link belongs here; it is issue #8.

  return (
    <aside ref={cardRef} className="place-card" aria-label={t('card.title')}>
      {/* A click from Enter or Space has no pointer clicks to count. */}
      <CloseButton
        className="place-card-close"
        label={t('card.close')}
        onClick={(e) => onClose(e.detail === 0 ? 'keyboard' : 'pointer')}
      />
      <h2 ref={headingRef} className="place-card-name" tabIndex={-1}>
        {card.headline}
      </h2>
      <p className="place-card-meta">
        {sourceLabel(card.source, t)}
        {card.note && <span className="place-card-note">{card.note}</span>}
        {kind && <span className="place-card-kind">{kind}</span>}
      </p>
      {card.lines.length > 0 && (
        <dl className="place-card-names">
          {card.lines.map((line) => (
            <div key={sourceKey(line.source)}>
              <dt>
                {sourceLabel(line.source, t)}
                {isExtinct(line.source) && <abbr title={t('card.extinct')}>&nbsp;†</abbr>}
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
