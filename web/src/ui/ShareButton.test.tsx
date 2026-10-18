import { afterEach, beforeEach, expect, it, vi, type Mock } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

import i18n from '../i18n';
import ShareButton from './ShareButton';

const PAGE = '/?view=frr-x-local#13/54.52/8.65';

let writeText: Mock<(text: string) => Promise<void>>;
let prompt: Mock<(message?: string, value?: string) => string | null>;

/** A browser with a share sheet: `share` is what it does. */
function withShareSheet(share: (data: ShareData) => Promise<void>) {
  Object.defineProperty(navigator, 'share', { value: vi.fn(share), configurable: true });
}

/** The browser's share sheet, on a touch device: `share` is what it does. */
function onTouchDeviceWith(share: (data: ShareData) => Promise<void>) {
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  withShareSheet(share);
}

beforeEach(async () => {
  await i18n.changeLanguage('de');
  window.history.replaceState(null, '', PAGE);
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  writeText = vi.fn(() => Promise.resolve());
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  prompt = vi.fn(() => null);
  vi.stubGlobal('prompt', prompt);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, 'share');
  Reflect.deleteProperty(navigator, 'clipboard');
});

/** Renders the button and clicks it, waiting for what the click set off. */
async function share() {
  render(<ShareButton />);
  await act(async () => {
    fireEvent.click(screen.getByRole('button'));
  });
}

it('copies the link of the page', async () => {
  await share();

  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}${PAGE}`);
});

it('says the link is copied', async () => {
  await share();

  expect(screen.getByRole('status').textContent).toBe(i18n.t('share.copied'));
});

it('hands the link of the page to the share sheet on a touch device', async () => {
  onTouchDeviceWith(() => Promise.resolve());

  await share();

  expect(navigator.share).toHaveBeenCalledWith({
    title: document.title,
    url: `${window.location.origin}${PAGE}`,
  });
});

it('copies the link on a desktop, though its browser has a share sheet', async () => {
  withShareSheet(() => Promise.resolve());

  await share();

  expect(writeText).toHaveBeenCalled();
});

it('copies nothing once the share sheet has shared the link', async () => {
  onTouchDeviceWith(() => Promise.resolve());

  await share();

  expect(writeText).not.toHaveBeenCalled();
});

it('copies nothing when the user closes the share sheet', async () => {
  onTouchDeviceWith(() => Promise.reject(new DOMException('closed', 'AbortError')));

  await share();

  expect(writeText).not.toHaveBeenCalled();
});

it('copies the link when the share sheet fails otherwise', async () => {
  onTouchDeviceWith(() => Promise.reject(new DOMException('busy', 'InvalidStateError')));

  await share();

  expect(writeText).toHaveBeenCalled();
});

it('hands the link over to copy by hand where the clipboard refuses it', async () => {
  writeText.mockRejectedValue(new Error('not a secure context'));

  await share();

  expect(prompt).toHaveBeenCalledWith(i18n.t('share.copyManually'), window.location.href);
});
