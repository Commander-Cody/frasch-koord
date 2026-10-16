/**
 * The frame both dev panels (CuratePanel, AreaPanel) share: the box over the
 * left edge of the map (DevPanel.css), its heading with a Reload button, and
 * what it says while its data loads or after that failed. Once loaded, the
 * heading sits in a sticky header together with the panel's own `header`.
 */
import type { CSSProperties, ReactNode } from 'react';

import { PANEL_WIDTH } from './panelLayout';
import type { DevResource } from './useDevResource';
import './DevPanel.css';

export interface DevPanelProps {
  title: string;
  /** The panel's own class, for its own rules (and scripts/smoke.ts). */
  className: string;
  /** What the panel loads, for the error line: "the worklist". */
  what: string;
  /** What the view needs to load at all, shown under an error. */
  needs: ReactNode;
  /** What the panel shows; an error wins over the data. */
  resource: Pick<DevResource<unknown>, 'data' | 'error' | 'reload'>;
  /** The rest of the sticky header, under the title. */
  header?: ReactNode;
  children?: ReactNode;
}

const WIDTH_STYLE = { '--dev-panel-width': `${PANEL_WIDTH}px` } as CSSProperties;

export default function DevPanel({
  title,
  className,
  what,
  needs,
  resource,
  header,
  children,
}: DevPanelProps) {
  const heading = (
    <div className="dev-panel-titlebar">
      <h1 className="dev-panel-title">{title}</h1>
      <button type="button" onClick={resource.reload}>
        Reload
      </button>
    </div>
  );
  const loaded = resource.error === null && resource.data !== null;
  return (
    <div className={`dev-panel panel ${className}`} style={WIDTH_STYLE}>
      {loaded ? (
        <>
          <header className="dev-panel-header">
            {heading}
            {header}
          </header>
          {children}
        </>
      ) : (
        <>
          {heading}
          <LoadStatus what={what} needs={needs} error={resource.error} />
        </>
      )}
    </div>
  );
}

function LoadStatus({
  what,
  needs,
  error,
}: Pick<DevPanelProps, 'what' | 'needs'> & { error: string | null }) {
  if (error === null) return <p className="dev-panel-hint">Loading…</p>;
  return (
    <>
      <p className="dev-panel-error">{`Could not load ${what}: ${error}`}</p>
      <p className="dev-panel-hint">{needs}</p>
    </>
  );
}
