import { describe, it, expect } from 'vitest';
import { withDemoQuery } from '@/lib/demoMode';

describe('demoMode utils', () => {
  it('keeps raw path when demo is disabled', () => {
    expect(withDemoQuery('/dashboard/upload', false)).toBe('/dashboard/upload');
  });

  it('appends demo query for plain paths', () => {
    expect(withDemoQuery('/dashboard/upload', true)).toBe('/dashboard/upload?demo=1');
  });

  it('appends demo query with ampersand when path already has query', () => {
    expect(withDemoQuery('/dashboard/upload?tab=recent', true)).toBe('/dashboard/upload?tab=recent&demo=1');
  });

  it('does not duplicate demo query when already present', () => {
    expect(withDemoQuery('/dashboard/upload?tab=recent&demo=1', true)).toBe('/dashboard/upload?tab=recent&demo=1');
  });

  it('normalizes non-1 demo values to demo=1', () => {
    expect(withDemoQuery('/dashboard/upload?demo=0&tab=recent', true)).toBe('/dashboard/upload?tab=recent&demo=1');
  });

  it('preserves hash fragments while appending demo query', () => {
    expect(withDemoQuery('/dashboard/upload?tab=recent#next', true)).toBe('/dashboard/upload?tab=recent&demo=1#next');
  });
});
