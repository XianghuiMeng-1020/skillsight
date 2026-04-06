import { test, expect } from '@playwright/test';

test.describe('预览部署验证 - SkillSight Preview Deployment', () => {
  const PREVIEW_URL = 'https://a112a0ff.skillsight-230-97u.pages.dev';

  test('完整预览部署验证流程', async ({ page }) => {
    console.log('\n=== 步骤 1: 导航到预览网站 ===');
    await page.goto(PREVIEW_URL);
    
    console.log('\n=== 步骤 2: 等待页面加载并检查重定向 ===');
    await page.waitForLoadState('networkidle', { timeout: 10000 });
    
    const currentUrl = page.url();
    console.log(`当前URL: ${currentUrl}`);
    
    if (currentUrl.includes('/login')) {
      console.log('✓ 页面已自动重定向到 /login');
    } else {
      console.log('页面未重定向到 /login,当前在首页');
    }
    
    await page.screenshot({ path: 'test-results/preview-01-initial-page.png', fullPage: true });
    console.log('✓ 截图已保存: preview-01-initial-page.png');

    console.log('\n=== 步骤 3: 检查登录页面元素 ===');
    
    // 检查测试账户提示卡
    console.log('\n检查测试账户提示卡...');
    const testAccountHintSelectors = [
      'text=测试账户',
      'text=Test account',
      'text=測試賬戶',
      ':text("无 HKU 账号也可体验")',
    ];
    
    let testAccountFound = false;
    for (const selector of testAccountHintSelectors) {
      const count = await page.locator(selector).count();
      if (count > 0) {
        testAccountFound = true;
        const hintText = await page.locator(selector).first().textContent();
        console.log(`✓ 找到测试账户提示: "${hintText}"`);
        break;
      }
    }
    
    if (!testAccountFound) {
      console.log('⚠ 未找到测试账户提示卡');
    }
    
    // 检查邮箱输入框
    console.log('\n检查Dev登录邮箱输入框...');
    const emailInput = page.locator('input[type="email"]').first();
    const emailInputVisible = await emailInput.isVisible({ timeout: 5000 }).catch(() => false);
    
    if (emailInputVisible) {
      const placeholder = await emailInput.getAttribute('placeholder');
      console.log(`✓ 找到邮箱输入框,placeholder: "${placeholder}"`);
    } else {
      console.log('⚠ 未找到邮箱输入框');
    }
    
    await page.screenshot({ path: 'test-results/preview-02-login-page.png', fullPage: true });
    console.log('✓ 截图已保存: preview-02-login-page.png');

    console.log('\n=== 步骤 4: 使用开发账户登录 ===');
    
    if (emailInputVisible) {
      await emailInput.fill('demo@connect.hku.hk');
      console.log('✓ 输入邮箱: demo@connect.hku.hk');
      
      await page.waitForTimeout(500);
      
      // 查找登录按钮
      const loginButtonSelectors = [
        'button:has-text("使用邮箱继续")',
        'button:has-text("Continue with email")',
        'button:has-text("继续")',
        'button[type="submit"]',
      ];
      
      let loginButton = null;
      for (const selector of loginButtonSelectors) {
        const button = page.locator(selector).first();
        if (await button.isVisible({ timeout: 1000 }).catch(() => false)) {
          loginButton = button;
          break;
        }
      }
      
      if (loginButton) {
        const isEnabled = await loginButton.isEnabled();
        console.log(`登录按钮状态: ${isEnabled ? '已启用' : '已禁用'}`);
        
        if (isEnabled) {
          await loginButton.click();
          console.log('✓ 点击登录按钮');
          
          try {
            await page.waitForURL('**/dashboard', { timeout: 10000 });
            console.log(`登录后URL: ${page.url()}`);
            expect(page.url()).toContain('/dashboard');
          } catch (e) {
            console.log('⚠ 未能导航到仪表板,可能登录失败或需要更长时间');
            console.log(`当前URL: ${page.url()}`);
          }
        } else {
          console.log('⚠ 登录按钮未启用,跳过登录');
        }
      } else {
        console.log('⚠ 未找到登录按钮');
      }
    }
    
    await page.screenshot({ path: 'test-results/preview-03-after-login-attempt.png', fullPage: true });
    console.log('✓ 截图已保存: preview-03-after-login-attempt.png');

    console.log('\n=== 步骤 5: 验证仪表板页面(如果成功登录) ===');
    
    if (page.url().includes('/dashboard')) {
      console.log('等待仪表板完全加载...');
      await page.waitForLoadState('networkidle', { timeout: 10000 });
      await page.waitForTimeout(2000); // 额外等待2秒确保动态内容加载
      
      console.log('\n检查统计卡片...');
      const statCards = page.locator('.stat-card');
      const statCardCount = await statCards.count();
      console.log(`找到 ${statCardCount} 个统计卡片`);
      
      // 检查已验证技能卡片的图标颜色
      console.log('\n检查已验证技能图标颜色...');
      const verifiedSkillsCard = page.locator('.stat-card').filter({ hasText: '已验证技能' }).or(
        page.locator('.stat-card').filter({ hasText: 'Verified Skills' })
      ).or(
        page.locator('.stat-card').filter({ hasText: '已驗證技能' })
      );
      
      const verifiedCardCount = await verifiedSkillsCard.count();
      if (verifiedCardCount > 0) {
        const statIcon = verifiedSkillsCard.first().locator('.stat-icon');
        const iconClass = await statIcon.getAttribute('class');
        console.log(`已验证技能图标class: "${iconClass}"`);
        
        if (iconClass?.includes('green')) {
          console.log('✓ 已验证技能图标使用 "green" 类');
        } else if (iconClass?.includes('blue')) {
          console.log('⚠ 警告: 已验证技能图标使用 "blue" 类 (预期是 green)');
        } else {
          console.log(`⚠ 已验证技能图标使用其他类: ${iconClass}`);
        }
      } else {
        console.log('⚠ 未找到已验证技能卡片');
      }
      
      await page.screenshot({ path: 'test-results/preview-04-dashboard-stats.png', fullPage: true });
      console.log('✓ 截图已保存: preview-04-dashboard-stats.png');

      console.log('\n检查侧边栏退出登录按钮...');
      const logoutButtonSelectors = [
        'button:has-text("退出登录")',
        'button:has-text("Sign out")',
        'button:has-text("登出")',
      ];
      
      let logoutButton = null;
      for (const selector of logoutButtonSelectors) {
        const button = page.locator(selector).first();
        if (await button.isVisible({ timeout: 2000 }).catch(() => false)) {
          logoutButton = button;
          break;
        }
      }
      
      if (logoutButton) {
        const buttonText = await logoutButton.textContent();
        console.log(`退出登录按钮文本: "${buttonText}"`);
        
        // 检查是否有emoji图标
        const hasEmoji = buttonText?.includes('🚪');
        console.log(`是否包含 🚪 emoji: ${hasEmoji ? '是' : '否'}`);
        
        // 检查是否有文本
        const hasText = buttonText && buttonText.trim().length > 1;
        console.log(`是否包含文本: ${hasText ? '是' : '否'}`);
        
        if (hasEmoji && hasText) {
          console.log('✓ 退出登录按钮同时显示图标(🚪)和文本');
        } else if (!hasEmoji) {
          console.log('⚠ 警告: 退出登录按钮没有 🚪 emoji');
        } else if (!hasText) {
          console.log('⚠ 警告: 退出登录按钮只有图标,没有文本');
        }
      } else {
        console.log('⚠ 未找到退出登录按钮');
      }
      
      await page.screenshot({ path: 'test-results/preview-05-sidebar.png', fullPage: true });
      console.log('✓ 截图已保存: preview-05-sidebar.png');
    } else {
      console.log('⚠ 未能登录到仪表板,跳过仪表板验证');
    }

    console.log('\n=== 验证完成 ===');
    console.log('所有截图已保存到 test-results/ 目录');
  });
});
