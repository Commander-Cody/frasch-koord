/**
 * The × that closes or dismisses something. The glyph is not a word, so it
 * is the same in every UI language; `label` says what it does.
 */
export interface CloseButtonProps {
  label: string;
  onClick: () => void;
  className?: string;
}

export default function CloseButton({ label, onClick, className }: CloseButtonProps) {
  return (
    <button type="button" className={className} aria-label={label} onClick={onClick}>
      ×
    </button>
  );
}
