/**
 * Student Full Workflows E2E
 * 模拟真实学生：以多种顺序排列组合完整走通所有前端展示的学生端功能。
 *
 * Prerequisites:
 *   - Backend: http://localhost:8001 (API + auth)
 *   - Frontend: http://localhost:3000 (npm run dev or next start)
 *   - Postgres + Qdrant (e.g. docker compose via scripts/dev_up.sh)
 *
 * Run: from repo root, ./scripts/run_student_workflows_e2e.sh
 *      or: cd web && npx playwright test tests/e2e/student_workflows_full.spec.ts
 */

import { test, expect, Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

const API = process.env.API_BASE_URL || 'http://localhost:8001';
const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

const TEST_USER = `e2e_workflow_${Date.now()}`;
let token = '';
let uploadedDocId = '';

async function devLogin(page: Page, subjectId: string, role = 'student') {
  const resp = await page.request.post(`${API}/auth/dev_login`, {
    data: { subject_id: subjectId, role, ttl_s: 3600 },
  });
  expect(resp.ok(), `dev_login failed: ${await resp.text()}`).toBeTruthy();
  const { token: t } = await resp.json();
  await page.evaluate(
    ({ t, subjectId, role }) => {
      localStorage.setItem('token', t);
      localStorage.setItem('user', JSON.stringify({ name: 'E2E Student', id: subjectId, role }));
    },
    { t, subjectId, role }
  );
  return t;
}

/** 任意语言下都能匹配的“上传”按钮 */
function uploadButton(page: Page) {
  return page.getByRole('button', { name: /Upload|上传|上傳/i });
}

test.describe('Student workflows – all routes and combinations', () => {
  test.setTimeout(90_000); // Flow A/B include upload + many pages
  test.beforeAll(async () => {});

  // ── Flow A: 经典顺序 登录 → 仪表盘 → 上传 → 文档详情 → 技能 → 导出 → 设置 → 隐私 → 变更日志 → 职位 → 评估入口 ──
  test('Flow A: Login → Dashboard → Upload → Document → Skills → Export → Settings → Privacy → Change-log → Jobs → Assessments', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND}/login`);
    token = await devLogin(page, TEST_USER);
    await page.goto(`${FRONTEND}/dashboard`);
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.locator('body')).toBeVisible();

    // Dashboard: 有侧栏或主内容
    await page.waitForSelector('main, .main-content, [class*="dashboard"]', { timeout: 10_000 }).catch(() => {});
    await page.screenshot({ path: 'test-results/flow_a_dashboard.png' });

    // Upload (standalone /upload)
    await page.goto(`${FRONTEND}/upload`);
    await expect(page).toHaveURL(/\/upload/);
    const tmpFile = path.join(os.tmpdir(), `e2e_flow_a_${Date.now()}.txt`);
    fs.writeFileSync(tmpFile, 'Flow A evidence. Python and data analysis.\n');
    await page.locator('input[type="file"]').setInputFiles(tmpFile);
    await page.locator('input[name="purpose"][value="skill_assessment"]').check();
    await page.locator('input[name="scope"][value="full"]').check();
    await expect(uploadButton(page)).toBeEnabled();
    await uploadButton(page).click();
    await page.waitForSelector('.alert-success, .alert-error, .alert, a[href*="/documents/"]', { timeout: 25_000 }).catch(() => null);
    const docLink = page.locator('a[href*="/documents/"]').first();
    const href = await docLink.getAttribute('href').catch(() => null);
    if (href) uploadedDocId = href.split('/documents/')[1]?.split('?')[0]?.split('#')[0] ?? '';
    fs.unlinkSync(tmpFile);

    // Document detail (if we have doc_id)
    if (uploadedDocId) {
      await page.goto(`${FRONTEND}/documents/${uploadedDocId}`);
      await expect(page).toHaveURL(new RegExp(`/documents/${uploadedDocId}`));
      await page.waitForTimeout(1500);
      await page.screenshot({ path: 'test-results/flow_a_document.png' });
    }

    // Skills
    await page.goto(`${FRONTEND}/dashboard/skills`);
    await expect(page).toHaveURL(/\/dashboard\/skills/);
    await page.waitForSelector('[class*="card"], .loading, main, .main-content', { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/flow_a_skills.png' });

    // Export
    await page.goto(`${FRONTEND}/export`);
    await expect(page).toHaveURL(/\/export/);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-results/flow_a_export.png' });
    const exportBody = await page.textContent('body');
    expect(exportBody?.length).toBeGreaterThan(100);

    // Settings
    await page.goto(`${FRONTEND}/settings`);
    await expect(page).toHaveURL(/\/settings/);
    await expect(page.locator('h1.page-title, h1').first()).toContainText(/Settings|设置|設定/i);
    await page.screenshot({ path: 'test-results/flow_a_settings.png' });

    // Privacy
    await page.goto(`${FRONTEND}/settings/privacy`);
    await expect(page).toHaveURL(/\/settings\/privacy/);
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/flow_a_privacy.png' });

    // Change-log
    await page.goto(`${FRONTEND}/dashboard/change-log`);
    await expect(page).toHaveURL(/\/dashboard\/change-log/);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: 'test-results/flow_a_changelog.png' });

    // Jobs
    await page.goto(`${FRONTEND}/dashboard/jobs`);
    await expect(page).toHaveURL(/\/dashboard\/jobs/);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: 'test-results/flow_a_jobs.png' });

    // Assessments landing
    await page.goto(`${FRONTEND}/dashboard/assessments`);
    await expect(page).toHaveURL(/\/dashboard\/assessments/);
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/flow_a_assessments.png' });
  });

  // ── Flow B: 先导出再上传 登录 → 导出 → 仪表盘 → 职位 → 变更日志 → 上传 → 仪表盘 → 技能 → 文档详情 ──
  test('Flow B: Login → Export first → Dashboard → Jobs → Change-log → Upload → Dashboard → Skills → Document', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND}/login`);
    token = await devLogin(page, TEST_USER);
    await page.goto(`${FRONTEND}/export`);
    await expect(page).toHaveURL(/\/export/);
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-results/flow_b_export_first.png' });

    await page.goto(`${FRONTEND}/dashboard`);
    await expect(page).toHaveURL(/\/dashboard/);
    await page.goto(`${FRONTEND}/dashboard/jobs`);
    await expect(page).toHaveURL(/\/dashboard\/jobs/);
    await page.waitForTimeout(1000);

    await page.goto(`${FRONTEND}/dashboard/change-log`);
    await expect(page).toHaveURL(/\/dashboard\/change-log/);
    await page.waitForTimeout(1000);

    await page.goto(`${FRONTEND}/upload`);
    const tmpFile = path.join(os.tmpdir(), `e2e_flow_b_${Date.now()}.txt`);
    fs.writeFileSync(tmpFile, 'Flow B evidence.\n');
    await page.locator('input[type="file"]').setInputFiles(tmpFile);
    await page.locator('input[name="purpose"][value="role_alignment"]').check();
    await page.locator('input[name="scope"][value="full"]').check();
    await uploadButton(page).click();
    await page.waitForSelector('.alert-success, .alert-error, .alert, a[href*="/documents/"]', { timeout: 20_000 }).catch(() => {});
    fs.unlinkSync(tmpFile);

    await page.goto(`${FRONTEND}/dashboard`);
    await page.goto(`${FRONTEND}/dashboard/skills`);
    await expect(page).toHaveURL(/\/dashboard\/skills/);
    await page.waitForTimeout(1000);

    if (uploadedDocId) {
      await page.goto(`${FRONTEND}/documents/${uploadedDocId}`);
      await expect(page).toHaveURL(new RegExp(`/documents/${uploadedDocId}`));
    }
    await page.screenshot({ path: 'test-results/flow_b_done.png' });
  });

  // ── Flow C: 评估与设置 登录 → 评估页 → 仪表盘/assessments → 设置 → 隐私 ──
  test('Flow C: Login → Assess page → Dashboard/assessments → Settings → Privacy', async ({ page }) => {
    await page.goto(`${FRONTEND}/login`);
    token = await devLogin(page, TEST_USER);
    await page.goto(`${FRONTEND}/assess`);
    await expect(page).toHaveURL(/\/assess/);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: 'test-results/flow_c_assess.png' });
    const assessBody = await page.textContent('body');
    expect(assessBody).toMatch(/Communication|编程|寫作|Writing|Coding|Assess/i);

    await page.goto(`${FRONTEND}/dashboard/assessments`);
    await expect(page).toHaveURL(/\/dashboard\/assessments/);
    await page.waitForTimeout(1000);

    await page.goto(`${FRONTEND}/settings`);
    await expect(page).toHaveURL(/\/settings/);
    await page.goto(`${FRONTEND}/settings/privacy`);
    await expect(page).toHaveURL(/\/settings\/privacy/);
    await page.screenshot({ path: 'test-results/flow_c_privacy.png' });
  });

  // ── Flow D: 从仪表盘内上传 登录 → Dashboard → Dashboard/upload → 勾选同意 → 上传 ──
  test('Flow D: Login → Dashboard → Dashboard/upload (in-dashboard upload)', async ({ page }) => {
    await page.goto(`${FRONTEND}/login`);
    token = await devLogin(page, TEST_USER);
    // Verify sidebar link exists on dashboard, then navigate directly (Next.js client router
    // requires real user interaction which Playwright synthetic clicks may not trigger correctly
    // against a CDN-served static export on Cloudflare Pages).
    await page.goto(`${FRONTEND}/dashboard`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('a[href="/dashboard/upload"]').first()).toBeVisible({ timeout: 10_000 });
    await page.goto(`${FRONTEND}/dashboard/upload`);
    await expect(page).toHaveURL(/\/dashboard\/upload/);
    const tmpFile = path.join(os.tmpdir(), `e2e_flow_d_${Date.now()}.txt`);
    fs.writeFileSync(tmpFile, 'Flow D in-dashboard upload.\n');
    await page.locator('input[type="file"]').setInputFiles(tmpFile);
    await page.locator('input[name="purpose"][value="skill_assessment"]').check();
    await page.locator('input[name="scope"][value="full"]').check();
    await page.getByRole('checkbox', { name: /consent|同意/i }).check();
    await expect(uploadButton(page)).toBeEnabled();
    await uploadButton(page).click();
    await page.waitForSelector('.alert-success, .alert-error, .alert', { timeout: 30_000 }).catch(() => {});
    fs.unlinkSync(tmpFile);
    await page.screenshot({ path: 'test-results/flow_d_upload_done.png' });
  });

  // ── 单页可访问性：每个学生端路由都能打开且不报错 ──
  test('All student routes load without error', async ({ page }) => {
    await page.goto(`${FRONTEND}/login`);
    token = await devLogin(page, TEST_USER);
    const routes: { path: string; expectInBody?: RegExp }[] = [
      { path: '/dashboard' },
      { path: '/dashboard/upload' },
      { path: '/dashboard/skills' },
      { path: '/dashboard/jobs' },
      { path: '/dashboard/assessments' },
      { path: '/dashboard/change-log' },
      { path: '/upload' },
      { path: '/export', expectInBody: /Skills Statement|生成声明|技能声明|Export|导出/i },
      { path: '/assess', expectInBody: /Communication|编程|寫作|Writing|Coding/i },
      { path: '/settings', expectInBody: /Settings|设置|設定|Profile|偏好/i },
      { path: '/settings/privacy', expectInBody: /Privacy|隐私|隱私|Consent|同意/i },
    ];
    const failed: { path: string; status: number; bodySnippet?: string }[] = [];
    for (const { path: p, expectInBody } of routes) {
      const resp = await page.goto(`${FRONTEND}${p}`);
      const status = resp?.status() ?? 0;
      if (status !== 200) {
        const body = await page.textContent('body').catch(() => null);
        const snippet = body ? body.slice(0, 400).replace(/\s+/g, ' ') : '';
        failed.push({ path: p, status, bodySnippet: snippet });
      }
      await page.waitForTimeout(600);
      if (status === 200 && expectInBody) {
        const body = await page.textContent('body');
        if (body && !expectInBody.test(body)) failed.push({ path: p, status: -1 }); // body check
      }
    }
    if (uploadedDocId) {
      const resp = await page.goto(`${FRONTEND}/documents/${uploadedDocId}`);
      if ((resp?.status() ?? 0) !== 200) failed.push({ path: `/documents/${uploadedDocId}`, status: resp?.status() ?? 0 });
    }
    if (failed.length > 0) {
      console.log('Failed routes:', JSON.stringify(failed, null, 2));
    }
    expect(failed, `Routes that failed: ${JSON.stringify(failed)}`).toHaveLength(0);
  });
});
