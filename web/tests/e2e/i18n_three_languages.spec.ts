/**
 * i18n: 三种语言切换后，各页面文案与所选语言一致
 * 不依赖后端，使用 localStorage 模拟登录
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

async function setDemoUser(page: import('@playwright/test').Page) {
  await page.goto(BASE + '/login');
  await page.evaluate(() => {
    localStorage.setItem(
      'user',
      JSON.stringify({
        id: 'demo_i18n',
        name: 'Demo Student',
        email: 'demo@test.hku.hk',
        role: 'student',
        avatar: 'DS',
      })
    );
  });
}

test.describe('i18n: 三种语言', () => {

  test('English: 设置页与仪表盘显示英文', async ({ page }) => {
    await setDemoUser(page);
    await page.goto(BASE + '/settings');
    await expect(page).toHaveURL(/\/settings/);

    // 设置语言为 English（点击语言下拉，再点 English 选项）
    await page.getByRole('button', { name: /简体中文|繁體中文|English/ }).first().click();
    await page.locator('button:has-text("English")').last().click();

    await page.waitForTimeout(400);

    // 设置页应为英文
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await expect(page.getByText('Manage your account and preferences')).toBeVisible();
    await expect(page.getByRole('heading', { name: '👤 Profile' })).toBeVisible();

    // 仪表盘应为英文
    await page.goto(BASE + '/dashboard');
    await expect(page.getByRole('heading', { name: /Welcome back/ })).toBeVisible();
    await expect(page.getByText('Upload Evidence').first()).toBeVisible();
    await expect(page.getByText('Quick Actions')).toBeVisible();
    await expect(page.getByText('Documents Uploaded').first()).toBeVisible();
    // 技能档案页应为英文
    await page.goto(BASE + '/dashboard/skills');
    await expect(page.getByRole('heading', { name: 'Skills Profile' })).toBeVisible();
  });

  test('简体中文: 设置页与仪表盘显示简体中文', async ({ page }) => {
    await setDemoUser(page);
    await page.goto(BASE + '/settings');
    await expect(page).toHaveURL(/\/settings/);

    await page.getByRole('button', { name: /简体中文|繁體中文|English/ }).first().click();
    await page.locator('button:has-text("简体中文")').last().click();

    await page.waitForTimeout(400);

    await expect(page.getByRole('heading', { name: '设置' })).toBeVisible();
    await expect(page.getByText('管理你的账户与偏好')).toBeVisible();

    await page.goto(BASE + '/dashboard');
    await expect(page.getByRole('heading', { name: /欢迎回来/ })).toBeVisible();
    await expect(page.getByText('上传证据').first()).toBeVisible();
    await expect(page.getByText('快捷操作')).toBeVisible();
    await page.goto(BASE + '/dashboard/skills');
    await expect(page.getByRole('heading', { name: '技能档案' })).toBeVisible();
  });

  test('繁體中文: 设置页与仪表盘显示繁体中文', async ({ page }) => {
    await setDemoUser(page);
    await page.goto(BASE + '/settings');
    await expect(page).toHaveURL(/\/settings/);

    await page.getByRole('button', { name: /简体中文|繁體中文|English/ }).first().click();
    await page.locator('button:has-text("繁體中文")').last().click();

    await page.waitForTimeout(400);

    await expect(page.getByRole('heading', { name: '設定' })).toBeVisible();
    await expect(page.getByText('管理你的帳戶與偏好')).toBeVisible();

    await page.goto(BASE + '/dashboard');
    await expect(page.getByRole('heading', { name: /歡迎回來/ })).toBeVisible();
    await expect(page.getByText('上傳證據').first()).toBeVisible();
    await expect(page.getByText('快捷操作')).toBeVisible();
    await page.goto(BASE + '/dashboard/skills');
    await expect(page.getByRole('heading', { name: '技能檔案' })).toBeVisible();
  });
});
