/**
 * Resume Enhancement Center — smoke (no full LLM/score/export pipeline).
 * Full upload→score→export requires backend LLM and is covered by manual QA + backend tests.
 */

import { test, expect, Page } from '@playwright/test';

const API = process.env.API_BASE_URL || 'http://localhost:8001';
const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

async function devLogin(page: Page, subjectId: string) {
  const resp = await page.request.post(`${API}/auth/dev_login`, {
    data: { subject_id: subjectId, role: 'student', ttl_s: 3600 },
  });
  expect(resp.ok(), `dev_login failed: ${await resp.text()}`).toBeTruthy();
  const { token } = await resp.json();
  await page.evaluate(({ token, subjectId }) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify({ name: 'E2E Resume', id: subjectId, role: 'student' }));
  }, { token, subjectId });
}

test.describe('Resume page smoke', () => {
  test('loads Resume Enhancement Center after dev login', async ({ page }) => {
    const user = `e2e_resume_${Date.now()}`;
    await page.goto(`${FRONTEND}/login`);
    await devLogin(page, user);
    await page.goto(`${FRONTEND}/dashboard/resume`);
    await expect(page).toHaveURL(/\/dashboard\/resume/);
    await expect(page.locator('body')).toContainText(/Resume|简历/);
  });
});
