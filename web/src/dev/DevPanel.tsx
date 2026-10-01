/**
 * The frame both dev panels (CuratePanel, AreaPanel) share: the box over the
 * left edge of the map (DevPanel.css), its heading, and what it says while its
 * data loads or after that failed. Once loaded, the heading sits in a sticky
 * header together with the panel's own `header`.
 */
import type { CSSProperties, ReactNode } from 'react';

import { PANEL_WIDTH } from './panelLayout';
import './DevPanel.css';

export interface DevPanelProps {
  title: string;
  /** The panel's own class, for its own rules (and scripts/smoke.mjs). */
  className: string;
  /** What the panel loads, for the error line: "the worklist". */
  what: string;
  /** What the view needs to load at all, shown under an error. */
  needs: ReactNode;
  loaded: boolean;
  /** Why loading failed; wins over `loaded`. */
  error: string | null;
  /** Offered as a Reload button after an error. */
  onReload?: () => void;
  /** The rest of the sticky header, under the title. */
  header?: ReactNode;
  children?: ReactNode;
}

const WIDTH_STYLE = { '--dev-panel-width': `${PANEL_WIDTH}px` } as CSSProperties;

export default function DevPanel({ title, className, header, children, ...load }: DevPanelProps) {
  const heading = <h1 className="dev-panel-title">{title}</h1>;
  return (
    <div className={`dev-panel ${className}`} style={WIDTH_STYLE}>
      {load.error || !load.loaded ? (
        <>
          {heading}
          <LoadStatus {...load} />
        </>
      ) : (
        <>
          <header className="dev-panel-header">
            {heading}
            {header}
          </header>
          {children}
        </>
      )}
    </div>
  );
}

function LoadStatus({
  what,
  needs,
  error,
  onReload,
}: Pick<DevPanelProps, 'what' | 'needs' | 'error' | 'onReload'>) {
  if (!error) return <p className="dev-panel-hint">Loading…</p>;
  return (
    <>
      <p className="dev-panel-error">{`Could not load ${what}: ${error}`}</p>
      <p className="dev-panel-hint">{needs}</p>
      {onReload && (
        <button type="button" onClick={onReload}>
          Reload
        </button>
      )}
    </>
  );
}
