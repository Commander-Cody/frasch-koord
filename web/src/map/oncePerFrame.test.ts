import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { oncePerFrame } from './oncePerFrame';

/** Frames requested so far and not yet run or cancelled, run by `nextFrame`. */
let frames: Map<number, FrameRequestCallback>;

function nextFrame() {
  const due = [...frames.values()];
  frames.clear();
  for (const callback of due) callback(0);
}

beforeEach(() => {
  frames = new Map();
  let id = 0;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    frames.set(++id, callback);
    return id;
  });
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => frames.delete(handle));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

it('runs once per frame, with the arguments of the last call in it', () => {
  const run = vi.fn();
  const throttled = oncePerFrame(run);

  throttled.call(1);
  throttled.call(2);
  throttled.call(3);
  expect(run).not.toHaveBeenCalled();
  nextFrame();
  expect(run.mock.calls).toEqual([[3]]);

  throttled.call(4);
  nextFrame();
  expect(run.mock.calls).toEqual([[3], [4]]);
});

it('drops a call still waiting for its frame when cancelled', () => {
  const run = vi.fn();
  const throttled = oncePerFrame(run);

  throttled.call(1);
  throttled.cancel();
  nextFrame();

  expect(run).not.toHaveBeenCalled();
});
