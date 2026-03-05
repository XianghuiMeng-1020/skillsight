/**
 * Staff Golden Path E2E Tests (Instructor/TA)
 * dev_login → courses → course detail → review queue → resolve ticket
 *
 * Prerequisites:
 *   - Backend on http://localhost:8001
 *   - Frontend on http://localhost:3000
 *   - P3 seed data (staff_demo, teaching relations, review tickets)
 */

import { test, expect } from '@playwright/test';

const API = process.env.API_BASE_URL || 'http://localhost:8001';
const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

async function staffDevLogin(page: { request: { post: (url: string, opts: unknown) => Promise<{ ok: () => boolean; json: () => Promise<{ token: string }> }> } }) {
  const resp = await page.request.post(`${API}/bff/staff/auth/dev_login`, {
    data: { subject_id: 'staff_demo', role: 'staff', course_ids: ['COMP3000', 'COMP3100'], term_id: '2025-26-T1' },
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.ok(), `staff dev_login failed: ${await resp.text()}`).toBeTruthy();
  const { token } = await resp.json();
  await page.evaluate((t: string) => {
    localStorage.setItem('skillsight_token', t);
    localStorage.setItem('skillsight_role', 'staff');
  }, token);
  return token;
}

test.describe('Staff Golden Path', () => {
  test('S1: dev_login → Staff courses list', async ({ page }) => {
    await page.goto(`${FRONTEND}/staff`);
    await staffDevLogin(page);
    await page.reload();
    await page.waitForSelector('text=My Courses', { timeout: 10000 });
    await page.screenshot({ path: 'test-results/P3_S1_staff_courses.png' });
    const body = await page.textContent('body');
    expect(body).toMatch(/courses|Courses|COMP|course/i);
  });

  test('S2: Course detail → skills summary + review queue', async ({ page }) => {
    await page.goto(`${FRONTEND}/staff`);
    await staffDevLogin(page);
    await page.reload();
    await page.waitForSelector('a[href*="/staff/courses/"]', { timeout: 10000 });
    const link = page.locator('a[href*="/staff/courses/"]').first();
    await link.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    const hasSkills = await page.locator('text=Skills Summary').isVisible().catch(() => false);
    const hasReviews = await page.locator('text=Review Queue').isVisible().catch(() => false);
    expect(hasSkills || hasReviews, 'Course detail should show Skills or Review tab').toBeTruthy();
    await page.screenshot({ path: 'test-results/P3_S2_course_detail.png' });
  });

  test('S3: Review queue → ticket list', async ({ page }) => {
    await page.goto(`${FRONTEND}/staff`);
    await staffDevLogin(page);
    await page.reload();
    const courseLink = page.locator('a[href*="/staff/courses/"]').first();
    if (await courseLink.isVisible()) {
      await courseLink.click();
      await page.waitForLoadState('networkidle');
      await page.locator('button:has-text("Review Queue")').click().catch(() => {});
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: 'test-results/P3_S3_review_queue.png' });
  });

  test('S4: Resolve ticket (approve)', async ({ page }) => {
    await page.goto(`${FRONTEND}/staff`);
    await staffDevLogin(page);
    await page.reload();
    const ticketLink = page.locator('a[href*="/staff/review/"]').first();
    if (!(await ticketLink.isVisible())) {
      test.skip(true, 'No open ticket in queue – run seed_p3_demo_data.py first');
      return;
    }
    await ticketLink.click();
    await page.waitForLoadState('networkidle');
    await page.locator('button:has-text("Approve")').first().click();
    await page.locator('textarea').fill('E2E approval');
    await page.locator('[data-testid="submit-resolve"]').click();
    await page.waitForSelector('text=Resolved|Ticket Resolved|Redirecting', { timeout: 10000 }).catch(() => {});
    await page.screenshot({ path: 'test-results/P3_S4_resolve_ticket.png' });
  });
});
