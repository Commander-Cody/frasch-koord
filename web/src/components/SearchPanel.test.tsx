import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import i18n from '../i18n';
import type { NameEntry } from '../names';
import SearchPanel from './SearchPanel';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('hands a picked result on as the whole name-list entry', () => {
  const entry: NameEntry = {
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
  const onSelect = vi.fn();
  render(
    <SearchPanel
      entries={[entry]}
      status="ready"
      view="frr-x-mooring"
      onViewChange={() => {}}
      onSelect={onSelect}
    />,
  );

  fireEvent.change(screen.getByPlaceholderText(/./), { target: { value: 'Naibel' } });
  fireEvent.click(within(screen.getByRole('listbox')).getByText('Naibel'));

  expect(onSelect).toHaveBeenCalledWith(entry, 'Naibel');
});

it("finds a place by OSM's generic name, which the local view labels it with", () => {
  const entry: NameEntry = {
    id: 'ribe',
    names: {},
    name_de: 'Ripen',
    name_da: 'Ribe',
    name_osm: 'Ribe',
    lon: 8.76,
    lat: 55.33,
    kind: 'settlement',
  };
  render(
    <SearchPanel
      entries={[entry]}
      status="ready"
      view="frr-x-local"
      onViewChange={() => {}}
      onSelect={() => {}}
    />,
  );

  fireEvent.change(screen.getByPlaceholderText(/./), { target: { value: 'Ribe' } });

  expect(within(screen.getByRole('listbox')).getByText('Ribe')).toBeDefined();
});

it('names the search field for screen readers, not only by its placeholder', () => {
  render(
    <SearchPanel
      entries={[]}
      status="ready"
      view="frr-x-mooring"
      onViewChange={() => {}}
      onSelect={() => {}}
    />,
  );

  // Without its label, the field would be named by the placeholder.
  expect(screen.getByRole('combobox', { name: i18n.t('search.label') })).toBeDefined();
});
