import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import i18n from '../i18n';
import type { NameEntry } from '../names/entry';
import type { NamesData } from '../names/load';
import { createSearch } from '../names/search';
import SearchBox from './SearchBox';

afterEach(cleanup);

const naibel: NameEntry = {
  id: 'naibel',
  osm: 'node/240042766',
  names: { 'frr-x-mooring': 'Naibel' },
  name_de: 'Niebüll',
  name_da: 'Nibøl',
  wikidata: 'Q21019',
  lon: 8.83,
  lat: 54.79,
  kind: 'settlement',
};

interface Rendered {
  entries?: NameEntry[];
  status?: NamesData['status'];
  onSelect?: (entry: NameEntry) => void;
}

function renderBox({ entries = [naibel], status = 'ready', onSelect = () => {} }: Rendered = {}) {
  const search = createSearch(entries);
  render(<SearchBox search={search} status={status} view="frr-x-mooring" onSelect={onSelect} />);
}

function type(query: string) {
  fireEvent.change(screen.getByRole('combobox'), { target: { value: query } });
}

it('names the search field for screen readers, not only by its placeholder', () => {
  renderBox();

  // Without its label, the field would be named by the placeholder.
  expect(screen.getByRole('combobox', { name: i18n.t('search.label') })).toBeDefined();
});

it('lists a found place by its name in the view', () => {
  renderBox();

  type('Niebüll');

  expect(screen.getByRole('option').querySelector('.search-result-name')?.textContent).toBe(
    'Naibel',
  );
});

it('adds the German name of a found place where it is another', () => {
  renderBox();

  type('Naibel');

  expect(within(screen.getByRole('option')).getByText('Niebüll')).toBeDefined();
});

it('hands a picked result on as the whole name-list entry', () => {
  const onSelect = vi.fn();
  renderBox({ onSelect });

  type('Naibel');
  fireEvent.click(within(screen.getByRole('listbox')).getByText('Naibel'));

  expect(onSelect).toHaveBeenCalledWith(naibel);
});

it('says so when it finds nothing', () => {
  renderBox();

  type('Xyz');

  expect(within(screen.getByRole('listbox')).getByText(i18n.t('search.noResults'))).toBeDefined();
});

it('says that the name list is still loading rather than that it found nothing', () => {
  renderBox({ entries: [], status: 'loading' });

  type('Naibel');

  expect(within(screen.getByRole('listbox')).getByText(i18n.t('search.loading'))).toBeDefined();
});

it('says once that the name list could not be loaded', () => {
  renderBox({ entries: [], status: 'error' });

  expect(screen.getByRole('alert').textContent).toBe(i18n.t('search.error'));
});
