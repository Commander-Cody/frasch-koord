import { useTranslation } from 'react-i18next';

import { LABEL_OPTIONS } from '../config';

export interface ViewSelectProps {
  /** Selected label option tag (a dialect, or LOCAL_TAG). */
  view: string;
  onViewChange: (view: string) => void;
}

/** The selector of what the map is labelled in: a dialect, or the local view. */
export default function ViewSelect({ view, onViewChange }: ViewSelectProps) {
  const { t } = useTranslation();
  return (
    <select
      className="dialect-select"
      aria-label={t('dialect.label')}
      value={view}
      onChange={(e) => onViewChange(e.target.value)}
    >
      {LABEL_OPTIONS.map((option) => (
        <option key={option.tag} value={option.tag}>
          {/* Dialect names come from the registry as-is; only the local
              view's name is translated. */}
          {t(option.labelKey, { defaultValue: option.label ?? option.tag })}
        </option>
      ))}
    </select>
  );
}
