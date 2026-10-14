import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { LOCAL_TAG } from '../config';
import ViewSelect from './ViewSelect';

afterEach(cleanup);

it('has the current view selected', () => {
  render(<ViewSelect view={LOCAL_TAG} onViewChange={() => {}} />);

  expect(screen.getByRole<HTMLSelectElement>('combobox').value).toBe(LOCAL_TAG);
});

it('reports the option that was picked', () => {
  const onViewChange = vi.fn();
  render(<ViewSelect view="frr-x-mooring" onViewChange={onViewChange} />);

  fireEvent.change(screen.getByRole('combobox'), { target: { value: LOCAL_TAG } });

  expect(onViewChange).toHaveBeenCalledWith(LOCAL_TAG);
});
