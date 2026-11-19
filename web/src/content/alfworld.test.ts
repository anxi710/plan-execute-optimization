import { describe, expect, it } from 'vitest';
import { pairedOutcomes, type Trial } from './alfworld';

describe('ALFWorld dialogue and paired analysis', () => {
  it('pairs by both task and model rather than row position', () => {
    const t = (taskId: number, model: string, score: number) => ({ taskId: String(taskId), model, score }) as Trial;
    expect(pairedOutcomes([t(1, 'a', 1), t(2, 'a', 0), t(1, 'b', 0)], [t(1, 'b', 1), t(1, 'a', 0), t(2, 'a', 0)]))
      .toEqual([1, 1, 1]);
  });
});
