/**
 * Admin Golden Path E2E Tests
 * dev_login → onboarding → skills import → roles import → audit search → metrics
 *
 * Prerequisites:
 *   - Backend on http://localhost:8001
 *   - Frontend on http://localhost:3000
 */

import { test, expect, type Page } from '@playwright/test';

const API = process.env.API_BASE_URL || 'http://localhost:8001';
const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

async function adminDevLogin(page: Page) {
  const resp = await page.request.post(`${API}/bff/admin/auth/dev_login`, {
    data: { subject_id: 'admin_demo', role: 'admin' },
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.ok(), `admin dev_login failed: ${await resp.text()}`).toBeTruthy();
  const { token } = await resp.json();
  await page.evaluate((t: string) => {
    localStorage.setItem('skillsight_token', t);
    localStorage.setItem('skillsight_role', 'admin');
  }, token);
  return token;
}

test.describe('Admin Golden Path', () => {
  test('A1: dev_login → Admin dashboard', async ({ page }) => {
    await page.goto(`${FRONTEND}/admin`);
    await adminDevLogin(page);
    await page.reload();
    await page.waitForSelector('text=System Dashboard|Admin Portal|admin', { timeout: 10000 });
    await page.screenshot({ path: 'test-results/P3_A1_admin_dashboard.png' });
  });

  test('A2: Onboarding page', async ({ page }) => {
    await page.goto(`${FRONTEND}/admin`);
    await adminDevLogin(page);
    await page.reload();
    await page.locator('a[href="/admin/onboarding"]').click();
    await page.waitForLoadState('networkidle');
    const hasEntity = await page.locator('text=Faculty|Programme|Course|Term').first().isVisible();
    expect(hasEntity, 'Onboarding page should show entity selector').toBeTruthy();
    await page.screenshot({ path: 'test-results/P3_A2_onboarding.png' });
  });

  test('A3: Skills page', async ({ page }) => {
    await page.goto(`${FRONTEND}/admin/skills`);
    await adminDevLogin(page);
    await page.reload();
    await page.waitForLoadState('networkidle');
    const body = await page.textContent('body');
    expect(body).toMatch(/Skill|skill|registry/i);
    await page.screenshot({ path: 'test-results/P3_A3_skills.png' });
  });

  test('A4: Roles page', async ({ page }) => {
    await page.goto(`${FRONTEND}/admin/roles`);
    await adminDevLogin(page);
    await page.reload();
    await page.waitForLoadState('networkidle');
    const body = await page.textContent('body');
    expect(body).toMatch(/Role|role|library/i);
    await page.screenshot({ path: 'test-results/P3_A4_roles.png' });
  });

  test('A5: Audit search', async ({ page }) => {
    await page.goto(`${FRONTEND}/admin/audit`);
    await adminDevLogin(page);
    await page.reload();
    await page.waitForLoadState('networkidle');
    const hasSearch = await page.locator('button:has-text("Search")').isVisible().catch(() => false);
    const hasAudit = await page.locator('text=Audit|audit').first().isVisible();
    expect(hasSearch || hasAudit, 'Audit page should load').toBeTruthy();
    await page.screenshot({ path: 'test-results/P3_A5_audit.png' });
  });

  test('A6: Metrics page', async ({ page }) => {
    await page.goto(`${FRONTEND}/admin/metrics`);
    await adminDevLogin(page);
    await page.reload();
    await page.waitForLoadState('networkidle');
    const body = await page.textContent('body');
    expect(body).toMatch(/Usage|Reliability|Metric|metric/i);
    await page.screenshot({ path: 'test-results/P3_A6_metrics.png' });
  });
});
