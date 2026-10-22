import { afterEach, expect, it, vi } from 'vitest';
import { getConfig } from '@testing-library/react';

import { queryParamWhenShown } from './queryParamWhenShown';

afterEach(() => {
  vi.useRealTimers();
});

it('names the text it waited for in vain', async () => {
  vi.useFakeTimers();
  const area = queryParamWhenShown('area', 'nothing matches that filter');
  vi.advanceTimersByTime(getConfig().asyncUtilTimeout);
  await expect(area).rejects.toThrow(/"nothing matches that filter"/);
});
