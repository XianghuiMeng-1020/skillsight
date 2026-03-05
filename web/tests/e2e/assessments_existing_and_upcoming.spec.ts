import { test, expect } from '@playwright/test';

const BASE = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

test.describe('Assessments: existing and upcoming', () => {
  test('existing three flows work and upcoming cards are visible', async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await page.evaluate(async (apiBase) => {
      const subjectId = 'demo_assessments';
      const resp = await fetch(`${apiBase}/auth/dev_login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject_id: subjectId, role: 'student', ttl_s: 3600 }),
      });
      const data = await resp.json();
      localStorage.setItem(
        'user',
        JSON.stringify({
          id: subjectId,
          name: 'Demo Student',
          email: 'demo@test.hku.hk',
          role: 'student',
          avatar: 'DS',
        })
      );
      if (data?.token) {
        localStorage.setItem('token', data.token);
        localStorage.setItem('skillsight_token', data.token);
        localStorage.setItem('skillsight_role', 'student');
      }
      localStorage.setItem('skillsight-language', 'zh');
    }, API);

    await page.route('**/interactive/communication/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'comm-session-1',
          topic: '介绍一次你解决冲突的经历',
          duration_seconds: 60,
        }),
      });
    });

    await page.route('**/interactive/communication/submit', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          evaluation: { overall_score: 86, level: 'advanced' },
        }),
      });
    });

    await page.route('**/interactive/programming/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'prog-session-1',
          problem: {
            title: 'Two Sum',
            description: '返回两个下标使其和等于 target',
            function_signature: 'def solution(nums, target):',
          },
        }),
      });
    });

    await page.route('**/interactive/programming/submit', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          evaluation: { overall_score: 90, level: 'expert' },
        }),
      });
    });

    await page.route('**/interactive/writing/start', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: 'writing-session-1',
          prompt: { title: '校园 AI 使用规范', prompt: '请讨论 AI 在学习中的利弊。' },
          time_limit_minutes: 30,
          anti_copy_token: 'token-1',
        }),
      });
    });

    await page.route('**/interactive/writing/submit', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          evaluation: { overall_score: 84, level: 'intermediate' },
        }),
      });
    });

    await page.goto(`${BASE}/dashboard/assessments`);
    await expect(page).toHaveURL(/\/dashboard\/assessments/);

    await expect(page.getByText('覆盖的技能领域')).toBeVisible();
    await expect(page.getByText('口头表达、即兴反应、逻辑组织')).toBeVisible();
    await expect(page.getByText('编程能力、算法思维、代码质量')).toBeVisible();
    await expect(page.getByText('书面表达、结构组织、语法')).toBeVisible();

    await expect(page.getByText('数据分析')).toBeVisible();
    await expect(page.getByText('问题解决 / 案例分析')).toBeVisible();
    await expect(page.getByText('演示 / 路演')).toBeVisible();
    await expect(page.getByText('即将上线').first()).toBeVisible();

    // Communication
    await page.getByRole('button', { name: '🚀 开始评估' }).click();
    await expect(page.getByText('你的话题')).toBeVisible();
    await page.getByRole('button', { name: '▶️ 开始录制' }).click();
    await page.getByRole('button', { name: '⏹️ 停止录制' }).click();
    await page.getByRole('button', { name: '📤 提交作答' }).click();
    await expect(page.getByText('评估完成！')).toBeVisible();
    await page.getByRole('button', { name: '再测一次' }).click();

    // Programming
    await page.locator('.assessment-card').filter({ hasText: '编程能力' }).first().click();
    await page.getByRole('button', { name: '🚀 开始评估' }).click();
    await expect(page.getByText('Two Sum')).toBeVisible();
    await page.locator('textarea').fill('def solution(nums, target):\n    return [0, 1]');
    await page.getByRole('button', { name: '📤 提交解答' }).click();
    await expect(page.getByText('评估完成！')).toBeVisible();
    await page.getByRole('button', { name: '再测一次' }).click();

    // Writing
    await page.locator('.assessment-card').filter({ hasText: '写作能力' }).first().click();
    await page.getByRole('button', { name: '🚀 开始评估' }).click();
    await expect(page.getByText('校园 AI 使用规范')).toBeVisible();
    await page
      .locator('textarea')
      .fill('this is a writing test content '.repeat(70));
    await page.getByRole('button', { name: '📤 提交文章' }).click();
    await expect(page.getByText('评估完成！')).toBeVisible();
  });
});
