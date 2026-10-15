// Talking to the dev server's endpoints (web/vite-plugins): what they answer,
// or why not, as a message fit for a panel.

/**
 * The JSON body `url` answers with. Rejects when the answer is a failure,
 * with the `error` its body names, or else with its status — and, whatever
 * went wrong, with `url` in front: a panel that loads two files at once
 * has to say which of them failed.
 */
export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  try {
    return await bodyOf<T>(await fetch(url, init));
  } catch (err) {
    throw new Error(`${url}: ${errorMessage(err)}`);
  }
}

async function bodyOf<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: string } | null;
    throw new Error(body?.error ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

/** Why something failed, for the panel: the message of an Error, or whatever else was thrown. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
