// Capture screenshots for the SkillSight HKU demo deck.
// Uses the deployed demo at https://skillsight-230.pages.dev/ (?demo=1).
// Run from repo root:  node scripts/capture_demo_screenshots.mjs
import { chromium } from "../web/node_modules/playwright/index.mjs";
import path from "node:path";
import fs from "node:fs";

const BASE = "https://skillsight-230.pages.dev";
const OUT = path.resolve(process.cwd(), "demo/screenshots");
fs.mkdirSync(OUT, { recursive: true });

const VIEWPORT = { width: 1440, height: 900 };

const SHOTS = [
  // [filename, url path, options]
  ["06_login.png", "/login", { fullPage: false, dismissModal: false, waitMs: 1500 }],
  ["07_dashboard.png", "/dashboard?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["08_upload.png", "/upload?demo=1", { fullPage: true, dismissModal: true, waitMs: 1500 }],
  ["09_my_skills.png", "/dashboard/skills?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["10_assessments.png", "/dashboard/assessments?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["11_resume.png", "/dashboard/resume?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["12_jobs.png", "/dashboard/jobs?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["13_jobs_live.png", "/dashboard/jobs-live?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["14_learning.png", "/dashboard/learning?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["15_timeline.png", "/dashboard/timeline?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["16_market.png", "/dashboard/market-insights?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["17_peer.png", "/dashboard/peer-benchmark?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["18_export.png", "/export?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["19_privacy.png", "/settings/privacy?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["20_settings.png", "/settings?demo=1", { fullPage: true, dismissModal: true, waitMs: 1500 }],
  ["21_change_log.png", "/dashboard/change-log?demo=1", { fullPage: true, dismissModal: true, waitMs: 1500 }],
  ["22_evidence.png", "/evidence?demo=1", { fullPage: true, dismissModal: true, waitMs: 1500 }],
  ["23_assess.png", "/assess?demo=1", { fullPage: true, dismissModal: true, waitMs: 1500 }],
  ["30_admin.png", "/admin?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["31_admin_audit.png", "/admin/audit?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["32_admin_skills.png", "/admin/skills?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["33_admin_roles.png", "/admin/roles?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["34_admin_jobs.png", "/admin/jobs?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["35_admin_metrics.png", "/admin/metrics?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["36_admin_onboarding.png", "/admin/onboarding?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["37_admin_courseskill.png", "/admin/course-skill-map?demo=1", { fullPage: true, dismissModal: true, waitMs: 2000 }],
  ["40_staff.png", "/staff?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
  ["41_programme.png", "/programme?demo=1", { fullPage: true, dismissModal: true, waitMs: 2500 }],
];

async function dismissPopups(page) {
  const closers = ['button:has-text("Close")', 'button[aria-label="Close"]', 'button:has-text("Got it")', 'button:has-text("Skip")', 'button:has-text("Dismiss")'];
  for (const sel of closers) {
    try {
      const els = await page.$$(sel);
      for (const el of els) {
        if (await el.isVisible().catch(() => false)) {
          await el.click({ timeout: 800 }).catch(() => {});
        }
      }
    } catch {}
  }
}

async function forceEnglish(page) {
  // Click any EN language toggle to enforce English
  try {
    const buttons = await page.$$('button');
    for (const b of buttons) {
      const txt = (await b.innerText().catch(() => "")).trim();
      if (txt === "EN") {
        const pressed = await b.getAttribute("aria-pressed").catch(() => null);
        if (pressed !== "true") {
          await b.click({ timeout: 800 }).catch(() => {});
          await page.waitForTimeout(400);
        }
        break;
      }
    }
  } catch {}
}

async function activateDemoMode(page) {
  // Visit /login first, click "Try our demo" so that demo session bootstraps.
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1500);
  // English language already default
  const tryDemo = page.locator('button:has-text("Try our demo")').first();
  if (await tryDemo.isVisible().catch(() => false)) {
    await tryDemo.click().catch(() => {});
    await page.waitForURL(/dashboard/, { timeout: 25000 }).catch(() => {});
    await page.waitForTimeout(2500);
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);

  // Capture login page first (fresh, no demo session yet).
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, "06_login.png"), fullPage: false });
  console.log("ok 06_login.png");

  await activateDemoMode(page);

  for (const [filename, urlPath, opts] of SHOTS) {
    if (filename === "06_login.png") continue;
    const url = `${BASE}${urlPath}`;
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForTimeout(800);
      await forceEnglish(page);
      await page.waitForTimeout(opts.waitMs ?? 2000);
      if (opts.dismissModal) await dismissPopups(page);
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(OUT, filename), fullPage: opts.fullPage });
      const stat = fs.statSync(path.join(OUT, filename));
      console.log(`ok ${filename}  (${stat.size} bytes)  url=${url}`);
    } catch (e) {
      console.log(`FAIL ${filename}  url=${url}  ${e.message?.slice(0, 100)}`);
    }
  }

  await browser.close();
  console.log("\nDone. Screenshots in", OUT);
})();
