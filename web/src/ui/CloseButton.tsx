import type { MouseEvent } from 'react';

import './CloseButton.css';

/**
 * The × that closes or dismisses something. The glyph is not a word, so it
 * is the same in every UI language; `label` says what it does. It looks the
 * same wherever it is; `inCorner` puts it in the top right corner of the
 * panel it is in (which has to be positioned), else it sits in the flow.
 */
export interface CloseButtonProps {
  label: string;
  onClick: (e: MouseEvent<HTMLButtonElement>) => void;
  inCorner?: boolean;
}

export default function CloseButton({ label, onClick, inCorner = false }: CloseButtonProps) {
  return (
    <button
      type="button"
      className={inCorner ? 'close-button is-in-corner' : 'close-button'}
      aria-label={label}
      onClick={onClick}
    >
      ×
    </button>
  );
}
