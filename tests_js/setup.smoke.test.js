import { describe, expect, it } from 'vitest';

// Confirms the Vitest + jsdom toolchain itself is wired up correctly,
// independent of any real form-builder.js behavior.
describe('vitest setup', () => {
  it('runs a test and has access to a DOM (jsdom) global', () => {
    expect(1 + 1).toBe(2);
    expect(typeof document).toBe('object');
  });
});
