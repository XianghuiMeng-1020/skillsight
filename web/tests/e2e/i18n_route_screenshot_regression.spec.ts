import { test, expect } from '@playwright/test';

const BASE = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';
const ROUTES = ['/dashboard', '/dashboard/skills', '/dashboard/assessments', '/upload', '/assess', '/settings'];
const LANGS = [
  { code: 'en', label: 'en' },
  { code: 'zh', label: 'zh' },
  { code: 'zh-TW', label: 'zh-TW' },
];

test.describe('i18n route screenshot regression', () => {
  test('capture all student routes in three languages', async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await page.evaluate(() => {
      localStorage.setItem(
        'user',
        JSON.stringify({
          id: 'demo_i18n_regression',
          name: 'Demo Student',
          email: 'demo@test.hku.hk',
          role: 'student',
          avatar: 'DS',
        })
      );
    });

    for (const lang of LANGS) {
      await page.evaluate((languageCode) => {
        localStorage.setItem('language', languageCode);
      }, lang.code);

      for (const route of ROUTES) {
        await page.goto(`${BASE}${route}`);
        await expect(page).toHaveURL(new RegExp(route.replace('/', '\\/')));
        await page.waitForTimeout(200);
        await page.screenshot({
          path: `test-results/i18n-route-snapshots/${lang.label}-${route.replace(/\//g, '_') || 'home'}.png`,
          fullPage: true,
        });
      }
    }
  });
});
