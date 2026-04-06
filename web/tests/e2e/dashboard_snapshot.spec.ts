import { test, expect } from '@playwright/test';
import * as fs from 'fs';

test('获取仪表板页面完整快照', async ({ page }) => {
  const PROD_URL = 'https://skillsight-230.pages.dev';

  console.log('导航到网站...');
  await page.goto(PROD_URL);
  await page.waitForLoadState('networkidle');

  console.log('输入邮箱并登录...');
  const emailInput = page.locator('input[type="email"], input[placeholder*="邮箱"], input[placeholder*="Email"]').first();
  await emailInput.fill('demo@connect.hku.hk');
  await page.waitForTimeout(500);
  
  const loginButton = page.locator('button:has-text("Sign in"), button:has-text("登录"), button:has-text("继续"), button:has-text("Continue")').first();
  await loginButton.click();
  
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  console.log('获取页面快照...');

  const html = await page.content();
  fs.writeFileSync('test-results/dashboard-html.html', html);
  console.log('✓ HTML已保存');

  console.log('\n查找统计卡片...');
  const statCards = await page.locator('[class*="stat"], [class*="card"], [data-testid*="stat"]').all();
  console.log(`找到 ${statCards.length} 个可能的统计卡片`);
  
  for (let i = 0; i < Math.min(statCards.length, 10); i++) {
    const text = await statCards[i].textContent();
    const classes = await statCards[i].getAttribute('class');
    console.log(`卡片 ${i + 1}: ${text?.substring(0, 50)} | 类: ${classes}`);
  }

  console.log('\n查找侧边栏按钮...');
  const sidebarButtons = await page.locator('nav button, aside button, [role="navigation"] button').all();
  console.log(`找到 ${sidebarButtons.length} 个侧边栏按钮`);
  
  for (let i = 0; i < sidebarButtons.length; i++) {
    const text = await sidebarButtons[i].textContent();
    const ariaLabel = await sidebarButtons[i].getAttribute('aria-label');
    console.log(`按钮 ${i + 1}: "${text}" | aria-label: "${ariaLabel}"`);
  }

  console.log('\n查找所有包含"退出"或"logout"的元素...');
  const logoutElements = await page.locator('text=/退出|登出|Sign out|Logout/i').all();
  console.log(`找到 ${logoutElements.length} 个相关元素`);
  
  for (let i = 0; i < logoutElements.length; i++) {
    const text = await logoutElements[i].textContent();
    const tagName = await logoutElements[i].evaluate(el => el.tagName);
    console.log(`元素 ${i + 1}: <${tagName}> "${text}"`);
  }

  await page.screenshot({ path: 'test-results/dashboard-full.png', fullPage: true });
  console.log('\n✓ 完整截图已保存');
});
