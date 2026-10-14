import SearchBox from './SearchBox';
import type { SearchBoxProps } from './SearchBox';
import ShareButton from './ShareButton';
import ViewSelect from './ViewSelect';
import type { ViewSelectProps } from './ViewSelect';

export type ControlBarProps = SearchBoxProps & ViewSelectProps;

/**
 * The controls above the map: the search, the view selector and the share
 * button. One flat grid, arranged by App.css: on desktop the selector and
 * the share button above the search field, on a phone all three in one bar.
 * The field comes first, the thing a phone visitor is there for.
 */
export default function ControlBar({ view, onViewChange, ...searchBox }: ControlBarProps) {
  return (
    <div className="control-bar">
      <SearchBox view={view} {...searchBox} />
      <ViewSelect view={view} onViewChange={onViewChange} />
      <ShareButton />
    </div>
  );
}
