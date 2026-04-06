/**
 * Programme Leader Golden Path E2E Tests
 * dev_login → programme overview → coverage matrix → trend
 *
 * Prerequisites:
 *   - Backend on http://localhost:8001
 *   - Frontend on http://localhost:3000
 *   - P3 seed (prog_leader_demo, programme CSCI_MSC)
 */

import { test, expect, type Page } from '@playwright/test';

const API = process.env.API_BASE_URL || 'http://localhost:8001';
const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

async function programmeDevLogin(page: Page) {
  const resp = await page.request.post(`${API}/bff/programme/auth/dev_login`, {
    data: { subject_id: 'prog_leader_demo', role: 'programme_leader', programme_id: 'CSCI_MSC' },
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.ok(), `programme dev_login failed: ${await resp.text()}`).toBeTruthy();
  const { token } = await resp.json();
  await page.evaluate((t: string) => {
    localStorage.setItem('skillsight_token', t);
    localStorage.setItem('skillsight_role', 'programme_leader');
  }, token);
  return token;
}

test.describe('Programme Golden Path', () => {
  test('P1: dev_login → Programme overview', async ({ page }) => {
    await page.goto(`${FRONTEND}/programme`);
    await programmeDevLogin(page);
    await page.reload();
    await page.waitForSelector('text=Programme Overview|Programmes|programme', { timeout: 10000 });
    await page.screenshot({ path: 'test-results/P3_P1_programme_overview.png' });
    const body = await page.textContent('body');
    expect(body).toMatch(/programme|Programme|overview/i);
  });

  test('P2: Programme detail → coverage matrix', async ({ page }) => {
    await page.goto(`${FRONTEND}/programme`);
    await programmeDevLogin(page);
    await page.reload();
    const progLink = page.locator('a[href*="/programme/programmes/"]').first();
    if (await progLink.isVisible()) {
      await progLink.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1500);
      const hasMatrix = await page.locator('text=Coverage Matrix').isVisible().catch(() => false);
      const hasGaps = await page.locator('text=Gap Analysis').isVisible().catch(() => false);
      expect(hasMatrix || hasGaps, 'Should show coverage or gaps').toBeTruthy();
    }
    await page.screenshot({ path: 'test-results/P3_P2_coverage_matrix.png' });
  });

  test('P3: Trend tab', async ({ page }) => {
    await page.goto(`${FRONTEND}/programme`);
    await programmeDevLogin(page);
    await page.reload();
    const progLink = page.locator('a[href*="/programme/programmes/"]').first();
    if (await progLink.isVisible()) {
      await progLink.click();
      await page.waitForLoadState('networkidle');
      await page.locator('button:has-text("Skill Trend")').click().catch(() => {});
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: 'test-results/P3_P3_trend.png' });
  });
});
