import { chromium } from "../web/node_modules/playwright/index.mjs";
import path from "node:path";

const BASE = "https://skillsight-230.pages.dev";
const OUT = path.resolve(process.cwd(), "demo/screenshots");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  page.setDefaultTimeout(30000);

  // bootstrap demo session
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const tryDemo = page.locator('button:has-text("Try our demo")').first();
  if (await tryDemo.isVisible().catch(() => false)) {
    await tryDemo.click();
    await page.waitForURL(/dashboard/, { timeout: 25000 }).catch(() => {});
    await page.waitForTimeout(2500);
  }
  // ensure EN
  const en = page.locator('button', { hasText: /^EN$/ }).first();
  if (await en.isVisible().catch(() => false)) {
    await en.click().catch(() => {});
    await page.waitForTimeout(500);
  }

  // 1) Export page — wait for the actual statement to render
  await page.goto(`${BASE}/export?demo=1`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const en2 = page.locator('button', { hasText: /^EN$/ }).first();
  if (await en2.isVisible().catch(() => false)) await en2.click().catch(() => {});
  // Wait until "Generating statement..." is gone OR 12s
  for (let i = 0; i < 24; i++) {
    const generating = await page.locator('text=Generating statement').first().isVisible().catch(() => false);
    if (!generating) break;
    await page.waitForTimeout(500);
  }
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, "18_export.png"), fullPage: true });
  console.log("ok 18_export.png");

  // 2) My Skills page — expand first skill to reveal Why/Evidence
  await page.goto(`${BASE}/dashboard/skills?demo=1`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const en3 = page.locator('button', { hasText: /^EN$/ }).first();
  if (await en3.isVisible().catch(() => false)) await en3.click().catch(() => {});
  await page.waitForTimeout(2500);
  // try to find an expandable skill card and click it
  const expandTargets = ['button:has-text("▼")', 'button[aria-expanded="false"]', 'div[role="button"]:has-text("Data Analysis")', 'button:has-text("Data Analysis")', '[data-testid="skill-card"] button'];
  for (const sel of expandTargets) {
    try {
      const el = page.locator(sel).first();
      if (await el.isVisible({ timeout: 1000 }).catch(() => false)) {
        await el.click({ timeout: 2000 }).catch(() => {});
        await page.waitForTimeout(800);
      }
    } catch {}
  }
  // click the first skill row (Data Analysis) to ensure expansion
  const dataAnalysis = page.locator('text=Data Analysis').first();
  if (await dataAnalysis.isVisible().catch(() => false)) {
    await dataAnalysis.click().catch(() => {});
    await page.waitForTimeout(800);
  }
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(OUT, "09b_my_skills_expanded.png"), fullPage: true });
  console.log("ok 09b_my_skills_expanded.png");

  // 3) Live Jobs viewport (not fullPage) — clean header + first cards
  await page.goto(`${BASE}/dashboard/jobs-live?demo=1`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const en4 = page.locator('button', { hasText: /^EN$/ }).first();
  if (await en4.isVisible().catch(() => false)) await en4.click().catch(() => {});
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, "13b_jobs_live_top.png"), fullPage: false });
  console.log("ok 13b_jobs_live_top.png");

  // 4) Dashboard viewport (clean hero shot) — already have full version, also do viewport
  await page.goto(`${BASE}/dashboard?demo=1`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const en5 = page.locator('button', { hasText: /^EN$/ }).first();
  if (await en5.isVisible().catch(() => false)) await en5.click().catch(() => {});
  await page.waitForTimeout(2500);
  // dismiss possible popups
  const closers = ['button[aria-label="Close"]', 'button:has-text("Close")'];
  for (const sel of closers) {
    const els = await page.$$(sel);
    for (const e of els) {
      if (await e.isVisible().catch(() => false)) await e.click({ timeout: 500 }).catch(() => {});
    }
  }
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(OUT, "07b_dashboard_top.png"), fullPage: false });
  console.log("ok 07b_dashboard_top.png");

  // 5) Job Matching viewport
  await page.goto(`${BASE}/dashboard/jobs?demo=1`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const en6 = page.locator('button', { hasText: /^EN$/ }).first();
  if (await en6.isVisible().catch(() => false)) await en6.click().catch(() => {});
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, "12b_jobs_top.png"), fullPage: false });
  console.log("ok 12b_jobs_top.png");

  await browser.close();
})();
