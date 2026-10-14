import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import ErrorBoundary from './ErrorBoundary';

afterEach(() => {
  vi.restoreAllMocks();
});

it('tries again on reset, also when resetKey stays the same', () => {
  // React and ErrorBoundary both log the crash.
  vi.spyOn(console, 'error').mockImplementation(() => {});
  let broken = true;
  function Panel() {
    if (broken) throw new Error('malformed entry');
    return <p>panel</p>;
  }

  render(
    <ErrorBoundary resetKey={null} fallback={(reset) => <button onClick={reset}>close</button>}>
      <Panel />
    </ErrorBoundary>,
  );
  expect(screen.queryByText('panel')).toBeNull();

  broken = false;
  fireEvent.click(screen.getByText('close'));
  expect(screen.getByText('panel')).toBeDefined();
});
