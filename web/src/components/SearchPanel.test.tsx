import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';

import '../i18n';
import type { NameEntry } from '../names';
import SearchPanel from './SearchPanel';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('searches past entries without an id or with a repeated one', () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const entry = { id: 'node/1', names: {}, name_de: 'Niebüll', lon: 8.83, lat: 54.79, kind: 'settlement' };
  const entries = [entry, { ...entry }, { ...entry, id: undefined }] as unknown as NameEntry[];

  render(
    <SearchPanel entries={entries} status="ready" view="frr-x-mooring" onViewChange={() => {}} onSelect={() => {}} />,
  );
  fireEvent.change(screen.getByPlaceholderText(/./), { target: { value: 'Niebüll' } });

  expect(within(screen.getByRole('listbox')).getAllByRole('option')).toHaveLength(1);
  expect(warn).toHaveBeenCalledOnce();
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
    <SearchPanel entries={[entry]} status="ready" view="frr-x-mooring" onViewChange={() => {}} onSelect={onSelect} />,
  );

  fireEvent.change(screen.getByPlaceholderText(/./), { target: { value: 'Naibel' } });
  fireEvent.click(within(screen.getByRole('listbox')).getByText('Naibel'));

  expect(onSelect).toHaveBeenCalledWith(entry, 'Naibel');
});
