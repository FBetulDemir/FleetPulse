import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests against the full running stack (`docker compose up`).
 * They use the real API, database, broker and simulator; nothing is mocked.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  // The tests share one live stack (and one fleet), so run them one at a time.
  workers: 1,
  timeout: 60_000,
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    // 127.0.0.1 rather than localhost: on Windows, localhost tries IPv6 first and the
    // stack only listens on IPv4.
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://127.0.0.1:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
