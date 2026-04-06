import { test, expect } from '@playwright/test';
import { setupResumeExplainabilityMocks } from './helpers/resumeExplainabilityMock';

const FRONTEND = process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000';

test.describe('Resume Explainability Export', () => {
  test('工作台可触发可解释报告 DOCX/PDF 导出', async ({ page }) => {
    const { exportCalls } = await setupResumeExplainabilityMocks(page);

    await page.goto(`${FRONTEND}/dashboard/resume?review_id=rid-current&step=5`);
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
  });
});

