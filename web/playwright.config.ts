import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/e2e-results.json' }],
  ],
  use: {
    baseURL: process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Start frontend automatically. Backend must be running at API_BASE_URL (default localhost:8001).
  // Use E2E_USE_PROD=1 for production build (run `npm run build` first, or use test:e2e:workflows:prod).
  webServer: {
    command: process.env.E2E_USE_PROD ? 'npm run start' : 'npm run dev',
    url: process.env.NEXT_PUBLIC_FRONTEND_URL || 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
