/** A function that runs at most once per animation frame, see `oncePerFrame`. */
export interface FrameThrottled<Args extends unknown[]> {
  call: (...args: Args) => void;
  /** Drops a call still waiting for its frame. */
  cancel: () => void;
}

/**
 * Runs `run` at most once per animation frame, with the arguments of the
 * last call before it: for work on every pointer move that only has to keep
 * up with what is painted.
 */
export function oncePerFrame<Args extends unknown[]>(
  run: (...args: Args) => void,
): FrameThrottled<Args> {
  let frame: number | null = null;
  let latest: Args;
  return {
    call: (...args) => {
      latest = args;
      frame ??= requestAnimationFrame(() => {
        frame = null;
        run(...latest);
      });
    },
    cancel: () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
    },
  };
}
