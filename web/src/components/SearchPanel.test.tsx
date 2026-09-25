import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';

import '../i18n';
import type { NameEntry } from '../names';
import SearchPanel from './SearchPanel';

afterEach(() => {
  vi.restoreAllMocks();
});

it('searches past entries without an id or with a repeated one', () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  const entry = { id: 'node/1', names: {}, name_de: 'Niebüll', lon: 8.83, lat: 54.79, kind: 'settlement' };
  const entries = [entry, { ...entry }, { ...entry, id: undefined }] as unknown as NameEntry[];

  render(
    <SearchPanel entries={entries} status="ready" labels="frr-x-mooring" onLabelsChange={() => {}} onSelect={() => {}} />,
  );
  fireEvent.change(screen.getByPlaceholderText(/./), { target: { value: 'Niebüll' } });

  expect(within(screen.getByRole('listbox')).getAllByRole('option')).toHaveLength(1);
  expect(warn).toHaveBeenCalledOnce();
});
