import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import DevPanel from './DevPanel';
import type { DevResource } from './useDevResource';

afterEach(cleanup);

/** What stays the same between the states. */
const curation = {
  className: 'curate-panel',
  title: 'Curation review',
  what: 'the worklist',
  needs: <>This view needs the Vite dev server.</>,
};

function resource(state: Partial<DevResource<string>>): DevResource<string> {
  return { data: null, error: null, reload: () => {}, update: () => {}, ...state };
}

describe('DevPanel', () => {
  it('says it is loading, and shows nothing of the panel yet', () => {
    render(
      <DevPanel {...curation} resource={resource({})}>
        <p>rows</p>
      </DevPanel>,
    );
    expect(screen.getByRole('heading', { name: 'Curation review' })).toBeDefined();
    expect(screen.getByText('Loading…')).toBeDefined();
    expect(screen.queryByText('rows')).toBeNull();
  });

  it('says what failed to load, and what the view needs, instead of the panel', () => {
    render(
      <DevPanel {...curation} resource={resource({ data: 'worklist', error: 'HTTP 404' })}>
        <p>rows</p>
      </DevPanel>,
    );
    expect(screen.getByText('Could not load the worklist: HTTP 404')).toBeDefined();
    expect(screen.getByText('This view needs the Vite dev server.')).toBeDefined();
    expect(screen.queryByText('Loading…')).toBeNull();
    expect(screen.queryByText('rows')).toBeNull();
  });

  it('shows the panel once loaded', () => {
    render(
      <DevPanel {...curation} resource={resource({ data: 'worklist' })}>
        <p>rows</p>
      </DevPanel>,
    );
    expect(screen.getByText('rows')).toBeDefined();
    expect(screen.queryByText('Loading…')).toBeNull();
  });

  // The heading with its Reload button is in either frame: the one in place
  // of the panel and the panel's sticky header.
  it.each([
    ['after an error', { error: 'HTTP 404' }],
    ['once loaded', { data: 'worklist' }],
  ])('offers to load again %s', (_, state) => {
    const reload = vi.fn();
    render(<DevPanel {...curation} resource={resource({ ...state, reload })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(reload).toHaveBeenCalled();
  });
});
