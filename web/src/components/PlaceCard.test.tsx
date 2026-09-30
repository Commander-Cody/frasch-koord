import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

import i18n from '../i18n';
import { LOCAL_TAG } from '../config';
import type { NameEntry } from '../names';
import PlaceCard from './PlaceCard';

afterEach(cleanup);

function place(fields: Partial<NameEntry>): NameEntry {
  return { id: 'ribe', names: {}, name_de: '', lon: 8.76, lat: 55.33, kind: '', ...fields };
}

function renderCard(entry: NameEntry) {
  render(<PlaceCard selection={{ entry }} view={LOCAL_TAG} onClose={() => {}} />);
}

it("labels OSM's generic name in the local view with the language it is the name in", () => {
  renderCard(place({ name_osm: 'Ribe', name_da: 'Ribe', name_de: 'Ripen' }));

  expect(screen.getByRole('heading').textContent).toBe('Ribe');
  expect(screen.getByText(i18n.t('card.danish'), { selector: '.place-card-meta' })).toBeDefined();
  // The German exonym is still on the card, as a line of its own.
  expect(screen.getByText(i18n.t('card.german'), { selector: 'dt' }).nextSibling?.textContent).toBe('Ripen');
});

it("names no language for OSM's generic name where the entry knows none it is the name in", () => {
  renderCard(place({ name_osm: 'Tønder', name_de: 'Tondern' }));

  expect(screen.getByRole('heading').textContent).toBe('Tønder');
  expect(document.querySelector('.place-card-meta')?.textContent).toBe('');
});

it('names no kind for a place kind the UI has no word for', () => {
  renderCard(place({ name_de: 'Niebüll', kind: 'spaceport' }));

  expect(document.querySelector('.place-card-kind')).toBeNull();
  expect(document.querySelector('.place-card-meta')?.textContent).not.toContain('kind.');
});
