import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { LngLat } from 'maplibre-gl';

import i18n from '../i18n';
import { DIALECTS } from '../dialects/registry';
import { LOCAL_TAG } from '../dialects/views';
import type { NameEntry } from '../names/entry';
import type { PlaceSelection } from '../selection/placeSelection';
import PlaceCard from './PlaceCard';

// Which names a card shows is names/card.test.ts's; this is what the card
// calls each of them.

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage('frr-x-mooring');
});

const MOORING = 'frr-x-mooring';
const FERING = 'frr-x-fering';

function place(fields: Partial<NameEntry>): NameEntry {
  return { id: 'ribe', names: {}, name_de: '', lon: 8.76, lat: 55.33, kind: '', ...fields };
}

function renderCard(entry: NameEntry, view = LOCAL_TAG) {
  const pick = { via: 'search', ref: entry.id } as const;
  render(<PlaceCard selection={{ pick, entry }} view={view} onClose={() => {}} />);
}

/** The card of a clicked label the name list does not have. */
function renderClicked(props: Record<string, string>) {
  const selection: PlaceSelection = {
    pick: { via: 'map', props, at: { lng: 0, lat: 0 } as LngLat },
  };
  render(<PlaceCard selection={selection} view={LOCAL_TAG} onClose={() => {}} />);
}

/** What the card calls the headline. */
function headlineLabel(): string | undefined {
  return document.querySelector('.place-card-meta')?.firstChild?.textContent ?? undefined;
}

/** What the card calls the name `name` of a line below the headline. */
function lineLabel(name: string): string | null | undefined {
  return screen.getByText(name, { selector: 'dd' }).previousElementSibling?.textContent;
}

it('calls a name in a dialect by the name of the dialect', () => {
  renderCard(place({ names: { [MOORING]: 'Naibel' } }), MOORING);

  expect(headlineLabel()).toBe(i18n.t(`dialects.${MOORING}`));
});

it('calls a dialect by its registry name in the German UI', async () => {
  await i18n.changeLanguage('de');
  const [{ tag, label }] = DIALECTS;
  renderCard(place({ names: { [tag]: 'Hoorbel' } }), tag);

  expect(headlineLabel()).toBe(label);
});

it("calls a local form that is the name in its area's dialect by both", () => {
  renderCard(place({ names: { [FERING]: 'Wik' }, local: 'Wik', dialect: FERING }));

  expect(headlineLabel()).toBe(`${i18n.t('card.local')} · ${i18n.t(`dialects.${FERING}`)}`);
});

it("calls a local form of the place's own the local form alone", () => {
  renderCard(place({ names: { [MOORING]: 'Waiguurd' }, local: 'Woiguurd', dialect: MOORING }));

  expect(headlineLabel()).toBe(i18n.t('card.local'));
});

it("labels OSM's generic name in the local view with the language it is the name in", () => {
  renderCard(place({ name_osm: 'Ribe', name_da: 'Ribe', name_de: 'Ripen' }));

  expect(headlineLabel()).toBe(i18n.t('card.danish'));
});

it.each([
  ['Low Saxon', 'card.lowSaxon', { name_nds: 'Other' }],
  ['German', 'card.german', { name_de: 'Other' }],
  ['Danish', 'card.danish', { name_da: 'Other' }],
])('calls the %s name by its language', (_language, key, names) => {
  renderCard(place({ names: { [MOORING]: 'Naibel' }, ...names }), MOORING);

  expect(lineLabel('Other')).toBe(i18n.t(key));
});

it("calls OSM's Frisian name of no dialect Frisian", () => {
  renderClicked({ 'name:frr': 'Söl', 'name:de': 'Sylt', name: 'Sylt' });

  expect(lineLabel('Söl')).toBe(i18n.t('card.frisian'));
});

it("names no language for OSM's generic name where the entry knows none it is the name in", () => {
  renderCard(place({ name_osm: 'Tønder', name_de: 'Tondern' }));

  expect(screen.getByRole('heading').textContent).toBe('Tønder');
  expect(document.querySelector('.place-card-meta')?.textContent).toBe('');
});

it('marks the name in an extinct dialect', () => {
  const extinct = DIALECTS.find((d) => d.status === 'extinct')!.tag;
  renderCard(place({ names: { [MOORING]: 'Naibel', [extinct]: 'Old name' } }), MOORING);

  expect(screen.getByTitle(i18n.t('card.extinct'))).toBeDefined();
});

it('shows the variety remark of a local form in the headline next to what it is called', () => {
  renderCard(place({ local: 'Brouersweerw', variety: 'Foortuftinge' }));

  expect(document.querySelector('.place-card-meta .place-card-note')?.textContent).toBe(
    'Foortuftinge',
  );
});

it('names no kind for a place kind the UI has no word for', () => {
  renderCard(place({ name_de: 'Niebüll', kind: 'spaceport' }));

  expect(document.querySelector('.place-card-kind')).toBeNull();
  expect(document.querySelector('.place-card-meta')?.textContent).not.toContain('kind.');
});
