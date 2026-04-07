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

  it('keeps critical dashboard i18n labels stable', () => {
    const criticalKeys = [
      'dashboard.uploadEvidence',
      'dashboard.goToAssessments',
      'dashboard.goToJobs',
      'nav.sampleCases',
      'sampleCases.quickTourTitle',
    ] as const;
    const snapshot = criticalKeys.map((key) => ({ key, ...translations[key] }));
    expect(snapshot).toMatchInlineSnapshot(`
      [
        {
          "en": "Upload Evidence",
          "key": "dashboard.uploadEvidence",
          "zh": "上传证据",
          "zh-TW": "上傳證據",
        },
        {
          "en": "Go to Assessments",
          "key": "dashboard.goToAssessments",
          "zh": "前往评估",
          "zh-TW": "前往評估",
        },
        {
          "en": "Go to Job Matching",
          "key": "dashboard.goToJobs",
          "zh": "前往职位匹配",
          "zh-TW": "前往職位匹配",
        },
        {
          "en": "Sample Cases",
          "key": "nav.sampleCases",
          "zh": "示例案例",
          "zh-TW": "示例案例",
        },
        {
          "en": "One-Click Tour",
          "key": "sampleCases.quickTourTitle",
          "zh": "一键导览",
          "zh-TW": "一鍵導覽",
        },
      ]
    `);
  });
});
