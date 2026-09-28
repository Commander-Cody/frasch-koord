import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import DevPanel from './DevPanel';

afterEach(cleanup);

/** What stays the same between the states. */
const curation = {
  className: 'curate-panel',
  title: 'Curation review',
  what: 'the worklist',
  needs: <>This view needs the Vite dev server.</>,
};

describe('DevPanel', () => {
  it('says it is loading, and shows nothing of the panel yet', () => {
    render(
      <DevPanel {...curation} loaded={false} error={null}>
        <p>rows</p>
      </DevPanel>,
    );
    expect(screen.getByRole('heading', { name: 'Curation review' })).toBeDefined();
    expect(screen.getByText('Loading…')).toBeDefined();
    expect(screen.queryByText('rows')).toBeNull();
  });

  it('says what failed to load, and what the view needs, instead of the panel', () => {
    render(
      <DevPanel {...curation} loaded={false} error="HTTP 404">
        <p>rows</p>
      </DevPanel>,
    );
    expect(screen.getByText('Could not load the worklist: HTTP 404')).toBeDefined();
    expect(screen.getByText('This view needs the Vite dev server.')).toBeDefined();
    expect(screen.queryByText('Loading…')).toBeNull();
    expect(screen.queryByText('rows')).toBeNull();
  });

  it('offers to load again after an error, where the panel can', () => {
    const reload = vi.fn();
    render(<DevPanel {...curation} loaded={false} error="HTTP 404" onReload={reload} />);
    fireEvent.click(screen.getByRole('button', { name: 'Reload' }));
    expect(reload).toHaveBeenCalled();
  });

  it('shows the panel once loaded', () => {
    render(
      <DevPanel {...curation} loaded error={null}>
        <p>rows</p>
      </DevPanel>,
    );
    expect(screen.getByText('rows')).toBeDefined();
    expect(screen.queryByText('Loading…')).toBeNull();
  });
});
