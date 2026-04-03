import { describe, it, expect } from 'vitest';
import { translations } from '@/lib/translations';

describe('translations', () => {
  const allKeys = Object.keys(translations);

  it('has translation entries', () => {
    expect(allKeys.length).toBeGreaterThan(100);
  });

  it('every key has zh, zh-TW, and en variants', () => {
    const missing: string[] = [];
    for (const key of allKeys) {
      const entry = translations[key];
      if (!entry.zh) missing.push(`${key}.zh`);
      if (!entry['zh-TW']) missing.push(`${key}.zh-TW`);
      if (!entry.en) missing.push(`${key}.en`);
    }
    expect(missing).toEqual([]);
  });

  it('no translation value is just the key itself', () => {
    const selfRef: string[] = [];
    for (const key of allKeys) {
      const entry = translations[key];
      if (entry.zh === key || entry.en === key) {
        selfRef.push(key);
      }
    }
    expect(selfRef).toEqual([]);
  });
});
