import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

/** How long the "link copied" confirmation stays up. */
const CONFIRM_MS = 2000;

/**
 * Phones and tablets get the system share sheet — that is where "send this to
 * my aunt" happens there. Desktop browsers may have `navigator.share` too
 * (Safari, Chrome on Windows), but their sheet is clumsier than a copied link.
 */
function hasShareSheet(): boolean {
  return typeof navigator.share === 'function' && window.matchMedia('(pointer: coarse)').matches;
}

/**
 * Shares the page as it is: App keeps the address bar in sync with the
 * selected view and open place (see urlState.ts), and MapLibre keeps the
 * viewport in its hash, so the current URL already is the link.
 */
export default function ShareButton() {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), CONFIRM_MS);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const share = async () => {
    const url = window.location.href;
    if (hasShareSheet()) {
      try {
        await navigator.share({ title: document.title, url });
        return;
      } catch (err) {
        // The user closed the sheet: nothing to do. Anything else (no
        // permission, a sheet already open) falls through to copying.
        if (err instanceof DOMException && err.name === 'AbortError') return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // No clipboard outside a secure context (the dev server opened by LAN
      // IP) or when the browser refuses: hand the link over to copy by hand.
      window.prompt(t('share.copyManually'), url);
    }
  };

  return (
    <div className="share">
      <button
        type="button"
        className="share-button"
        aria-label={t('share.label')}
        title={t('share.label')}
        onClick={() => void share()}
      >
        {copied ? (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 12.5l4.5 4.5L19 7.5" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="18" cy="5.5" r="2.5" />
            <circle cx="6" cy="12" r="2.5" />
            <circle cx="18" cy="18.5" r="2.5" />
            <path d="M8.2 10.8l7.6-4.1M8.2 13.2l7.6 4.1" />
          </svg>
        )}
      </button>
      <span className="share-status" role="status">
        {copied ? t('share.copied') : ''}
      </span>
    </div>
  );
}
