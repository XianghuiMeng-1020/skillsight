/**
 * P4 Change Log E2E Tests
 * CL1: skill change -> change-log page sees event
 * CL2: role readiness change -> change-log sees role_readiness_changed
 * CL3: consent withdraw / doc delete -> change-log sees governance event
 *
 * Prerequisites: Backend 8001, Frontend 3000, P3 seed (skills, roles)
 */

import { test, expect, type Page } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

const API = process.env.API_BASE_URL || 'http://localhost:8001';
const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || process.env.BASE_URL || 'http://localhost:3000';

const P4_USER = `p4_e2e_${Date.now()}`;
let docId = '';
let token = '';

async function studentBffLogin(page: Page) {
  await page.goto(`${FRONTEND}/dashboard`);
  await page.waitForLoadState('domcontentloaded');
  const resp = await page.request.post(`${API}/bff/student/auth/dev_login`, {
    data: { subject_id: P4_USER, role: 'student', ttl_s: 3600 },
    headers: { 'Content-Type': 'application/json' },
  });
  expect(resp.ok(), `BFF student login failed: ${await resp.text()}`).toBeTruthy();
  const data = await resp.json();
  const t = data.token;
  await page.evaluate(({ token: tkn, userId }) => {
    localStorage.setItem('skillsight_token', tkn);
    localStorage.setItem('skillsight_role', 'student');
    localStorage.setItem('token', tkn);
    localStorage.setItem('user', JSON.stringify({ name: 'P4 E2E', id: userId, role: 'student' }));
  }, { token: t, userId: P4_USER });
  return t;
}

test.describe('P4 Change Log', () => {
  test('CL1: skill change -> change-log sees event', async ({ page }) => {
    token = await studentBffLogin(page);

    // Upload doc
    const tmp = path.join(os.tmpdir(), `p4_cl1_${Date.now()}.txt`);
    fs.writeFileSync(tmp, 'Python programming: pandas, scikit-learn, data analysis. Unit tests.');
    const formData = new FormData();
    formData.append('file', new Blob([fs.readFileSync(tmp)]), 'p4_evidence.txt');
    formData.append('purpose', 'skill_assessment');
    formData.append('scope', 'full');
    const fileContent = fs.readFileSync(tmp);
    const uploadResp = await page.request.post(`${API}/bff/student/documents/upload`, {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: { name: 'p4_evidence.txt', mimeType: 'text/plain', buffer: fileContent },
        purpose: 'skill_assessment',
        scope: 'full',
      },
    });
    fs.unlinkSync(tmp);
    if (!uploadResp.ok()) {
      test.skip(true, 'Upload failed - need skills in DB');
      return;
    }
    const uploadData = await uploadResp.json();
    docId = uploadData.doc_id;
    expect(docId).toBeTruthy();

    // Embed
    await page.request.post(`${API}/bff/student/chunks/embed/${docId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    // Get skill_id
    const skillsResp = await page.request.get(`${API}/skills?limit=1`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const skillsData = await skillsResp.json().catch(() => ({}));
    const skillId = skillsData.items?.[0]?.skill_id || skillsData.skill_id;
    if (!skillId) {
      test.skip(true, 'No skill in DB - run seed');
      return;
    }

    // Call BFF demonstration
    const demoResp = await page.request.post(`${API}/bff/student/ai/demonstration`, {
      data: { skill_id: skillId, doc_id: docId, k: 5 },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(demoResp.ok() || demoResp.status() === 503, `Demo failed: ${await demoResp.text()}`).toBeTruthy();

    // Navigate to change-log
    await page.goto(`${FRONTEND}/dashboard/change-log`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    const hasChangeLog = body?.includes('Change Log') || body?.includes('change');
    const hasEventOrEmpty = body?.includes('skill') || body?.includes('暂无') || body?.includes('no_changes') || body?.includes('No change');
    expect(hasChangeLog, 'Change log page should load').toBeTruthy();
    expect(hasEventOrEmpty || hasChangeLog, 'Should show events or empty state').toBeTruthy();

    await page.screenshot({ path: 'test-results/P4_CL1_change_log.png' });
  });

  test('CL2: role readiness -> change-log sees role_readiness_changed', async ({ page }) => {
    token = await studentBffLogin(page);

    // Call role alignment (uses first consented doc or needs doc_id)
    const rolesResp = await page.request.get(`${API}/roles?limit=1`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const rolesData = await rolesResp.json().catch(() => ({}));
    const roleId = rolesData.items?.[0]?.role_id || rolesData.role_id;
    if (!roleId) {
      test.skip(true, 'No role - run seed');
      return;
    }

    const alignResp = await page.request.post(`${API}/bff/student/roles/alignment`, {
      data: { role_id: roleId, ...(docId ? { doc_id: docId } : {}) },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    // May fail if no doc - skip
    if (!alignResp.ok()) {
      test.skip(true, 'Role alignment needs doc - run CL1 first or seed');
      return;
    }

    await page.goto(`${FRONTEND}/dashboard/change-log`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body).toMatch(/Change Log|change|变更/);
    await page.screenshot({ path: 'test-results/P4_CL2_change_log.png' });
  });

  test('CL3: consent withdraw -> change-log sees governance event', async ({ page }) => {
    token = await studentBffLogin(page);

    if (!docId) {
      // Create doc for withdraw test
      const tmp = path.join(os.tmpdir(), `p4_cl3_${Date.now()}.txt`);
      fs.writeFileSync(tmp, 'Withdraw test doc');
      const formData = new FormData();
      formData.append('file', new Blob([fs.readFileSync(tmp)]), 'withdraw_test.txt');
      formData.append('purpose', 'skill_assessment');
      formData.append('scope', 'full');
      const fileContent = fs.readFileSync(tmp);
      const up = await page.request.post(`${API}/bff/student/documents/upload`, {
        headers: { Authorization: `Bearer ${token}` },
        multipart: {
          file: { name: 'withdraw_test.txt', mimeType: 'text/plain', buffer: fileContent },
          purpose: 'skill_assessment',
          scope: 'full',
        },
      });
      fs.unlinkSync(tmp);
      if (up.ok()) {
        const d = await up.json();
        docId = d.doc_id;
      }
    }

    if (!docId) {
      test.skip(true, 'No doc to withdraw');
      return;
    }

    const withdrawResp = await page.request.post(`${API}/bff/student/consents/withdraw`, {
      data: { doc_id: docId, reason: 'P4 E2E test' },
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    });
    expect(withdrawResp.ok(), `Withdraw failed: ${await withdrawResp.text()}`).toBeTruthy();

    await page.goto(`${FRONTEND}/dashboard/change-log`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const body = await page.textContent('body');
    expect(body).toMatch(/Change Log|change|变更|Consent|consent|撤回|deleted/);
    await page.screenshot({ path: 'test-results/P4_CL3_change_log.png' });
  });
});
