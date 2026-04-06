import { test, expect } from '@playwright/test';
import { setupResumeExplainabilityMocks } from './helpers/resumeExplainabilityMock';

test.describe('部署验证 - SkillSight Production Deployment', () => {
  const PROD_URL = 'https://skillsight-230.pages.dev';

  test('完整部署验证流程', async ({ page }) => {
    console.log('\n=== 步骤 1: 导航到生产网站 ===');
    await page.goto(PROD_URL);
    
    console.log('\n=== 步骤 2: 检查首页加载 ===');
    await page.waitForLoadState('networkidle');
    
    const title = await page.title();
    console.log(`页面标题: ${title}`);
    expect(title).toContain('SkillSight');
    
    const heading = await page.locator('h1').first().textContent();
    console.log(`主标题: ${heading}`);
    expect(heading).toContain('SkillSight');
    
    const subtitleLocators = [
      page.locator('text=HKU Skills-to-Jobs Transparency System'),
      page.locator('text=HKU 技能与职业透明系统'),
      page.locator('text=HKU 技能與職業透明系統'),
    ];
    
    let subtitle = null;
    for (const locator of subtitleLocators) {
      if (await locator.count() > 0) {
        subtitle = locator.first();
        break;
      }
    }
    
    if (subtitle) {
      await expect(subtitle).toBeVisible();
      const subtitleText = await subtitle.textContent();
      console.log(`✓ 确认显示副标题: "${subtitleText}"`);
    } else {
      console.log('⚠ 未找到副标题文本');
    }
    
    await page.screenshot({ path: 'test-results/01-homepage.png', fullPage: true });
    console.log('✓ 截图已保存: 01-homepage.png');

    console.log('\n=== 步骤 3: 检查是否在登录页或首页 ===');
    const currentUrl = page.url();
    console.log(`当前URL: ${currentUrl}`);
    
    if (!currentUrl.includes('/login')) {
      console.log('页面未重定向到 /login,可能首页就是登录页');
    }
    
    await page.screenshot({ path: 'test-results/02-login-page.png', fullPage: true });
    console.log('✓ 截图已保存: 02-login-page.png');

    console.log('\n=== 步骤 4: 检查登录页面元素 ===');
    
    const hkuPortalButton = page.locator('button:has-text("HKU Portal"), button:has-text("HKU 门户"), button:has-text("登入"), button:has-text("登录")').first();
    await expect(hkuPortalButton).toBeVisible();
    const hkuButtonText = await hkuPortalButton.textContent();
    console.log(`✓ 找到 HKU Portal 按钮: "${hkuButtonText}"`);
    
    const testAccountHint = page.locator('text=测试账户, text=Test account, text=測試賬戶');
    const testAccountVisible = await testAccountHint.count() > 0;
    if (testAccountVisible) {
      console.log('✓ 找到测试账户提示卡');
    } else {
      console.log('⚠ 未找到测试账户提示卡 (可能在中文界面中不显示)');
    }
    
    const emailInput = page.locator('input[type="email"], input[placeholder*="邮箱"], input[placeholder*="Email"]').first();
    await expect(emailInput).toBeVisible();
    console.log('✓ 找到邮箱输入框');

    console.log('\n=== 步骤 5: 使用开发账户登录 ===');
    await emailInput.fill('demo@connect.hku.hk');
    console.log('✓ 输入邮箱: demo@connect.hku.hk');
    
    await page.waitForTimeout(500);
    
    const loginButton = page.locator('button:has-text("Sign in"), button:has-text("登录"), button:has-text("继续"), button:has-text("Continue")').first();
    await expect(loginButton).toBeEnabled();
    await loginButton.click();
    console.log('✓ 点击登录按钮');
    
    await page.waitForURL('**/dashboard', { timeout: 15000 });
    console.log(`登录后URL: ${page.url()}`);
    expect(page.url()).toContain('/dashboard');
    
    await page.screenshot({ path: 'test-results/03-after-login.png', fullPage: true });
    console.log('✓ 截图已保存: 03-after-login.png');

    console.log('\n=== 步骤 6: 验证仪表板页面 ===');
    await page.waitForLoadState('networkidle');
    
    console.log('\n检查已验证技能统计图标颜色...');
    const verifiedSkillsStat = page.locator('[data-testid="verified-skills-stat"], .stat-card:has-text("Verified Skills"), .stat-card:has-text("已验证技能")').first();
    
    if (await verifiedSkillsStat.isVisible()) {
      const statIcon = verifiedSkillsStat.locator('svg, .icon').first();
      const iconColor = await statIcon.evaluate((el) => {
        const computed = window.getComputedStyle(el);
        return {
          color: computed.color,
          fill: computed.fill,
          stroke: computed.stroke,
        };
      });
      console.log(`图标颜色信息: ${JSON.stringify(iconColor)}`);
      
      const isGreen = 
        iconColor.color?.includes('34, 197, 94') || 
        iconColor.color?.includes('22, 163, 74') ||
        iconColor.color?.includes('rgb(34, 197, 94)') ||
        iconColor.color?.includes('rgb(22, 163, 74)') ||
        iconColor.fill?.includes('34, 197, 94') ||
        iconColor.fill?.includes('22, 163, 74') ||
        iconColor.fill?.includes('rgb(34, 197, 94)') ||
        iconColor.fill?.includes('rgb(22, 163, 74)');
      
      if (isGreen) {
        console.log('✓ 已验证技能图标是绿色的');
      } else {
        console.log('⚠ 警告: 已验证技能图标可能不是绿色');
        console.log('  实际颜色:', iconColor);
      }
    } else {
      console.log('⚠ 未找到已验证技能统计卡片');
    }
    
    await page.screenshot({ path: 'test-results/04-dashboard-stats.png', fullPage: true });
    console.log('✓ 截图已保存: 04-dashboard-stats.png');

    console.log('\n检查侧边栏退出登录按钮...');
    const sidebar = page.locator('nav, aside, [role="navigation"]').first();
    
    const logoutButton = page.locator('button:has-text("退出登录"), button:has-text("Sign out"), button:has-text("Logout")').first();
    
    if (await logoutButton.isVisible()) {
      const buttonText = await logoutButton.textContent();
      console.log(`退出登录按钮文本: "${buttonText}"`);
      
      const hasIcon = await logoutButton.locator('svg, .icon').count() > 0;
      console.log(`是否有图标: ${hasIcon ? '是' : '否'}`);
      
      if (hasIcon && buttonText && buttonText.trim().length > 0) {
        console.log('✓ 退出登录按钮同时显示图标和文本');
      } else if (!hasIcon) {
        console.log('⚠ 警告: 退出登录按钮没有图标');
      } else if (!buttonText || buttonText.trim().length === 0) {
        console.log('⚠ 警告: 退出登录按钮没有文本');
      }
    } else {
      console.log('⚠ 未找到退出登录按钮');
    }
    
    await page.screenshot({ path: 'test-results/05-sidebar.png', fullPage: true });
    console.log('✓ 截图已保存: 05-sidebar.png');

    console.log('\n=== 验证完成 ===');
    console.log('所有截图已保存到 test-results/ 目录');
  });

  test('可解释报告导出集成验证（DOCX/PDF）', async ({ page }) => {
    const APP_URL = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';
    const { exportCalls } = await setupResumeExplainabilityMocks(page, {
      token: 'deploy-e2e-token',
      userId: 'deploy-e2e',
      userName: 'Deploy E2E',
    });

    await page.goto(`${APP_URL}/dashboard/resume?review_id=rid-current&step=5`);
    await expect(page.locator('text=/导出工作台|Export Workbench/')).toBeVisible({ timeout: 15000 });

    const compareSelect = page.locator('select').filter({ has: page.locator('option[value="rid-compare"]') }).first();
    await compareSelect.selectOption('rid-compare');
    await page.locator('button:has-text("开始对比"), button:has-text("Compare")').first().click();
    await expect(page.locator('text=/语义改动洞察|Semantic Change Insights/')).toBeVisible({ timeout: 10000 });

    await page.locator('button:has-text("导出可解释报告 DOCX"), button:has-text("Export Explainability DOCX")').first().click();
    await page.locator('button:has-text("导出可解释报告 PDF"), button:has-text("Export Explainability PDF")').first().click();

    await expect.poll(() => exportCalls.length).toBe(2);
    expect(exportCalls[0]?.export_format).toBe('docx');
    expect(exportCalls[1]?.export_format).toBe('pdf');

    await page.screenshot({ path: 'test-results/06-explainability-export.png', fullPage: true });
    console.log('✓ 可解释报告导出集成验证通过');
  });
});
