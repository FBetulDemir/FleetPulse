import { Page, expect } from '@playwright/test';

export type DemoRole = 'Admin' | 'Operator' | 'Viewer';

export async function signInAs(page: Page, role: DemoRole): Promise<void> {
  await page.goto('/login');
  // The demo buttons are named like "Viewer , Read-only access".
  await page.getByRole('button', { name: new RegExp(`^${role}\\b`) }).click();
  await expect(page.getByRole('heading', { name: 'Fleet overview' })).toBeVisible();
}

/** Waits until the map shows live markers, i.e. the WebSocket delivers data. */
export async function waitForLiveFleet(page: Page): Promise<void> {
  await expect(page.locator('.fp-marker')).toHaveCount(5, { timeout: 30_000 });
}
