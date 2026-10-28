import AxeBuilder from '@axe-core/playwright';
import { Page, expect, test } from '@playwright/test';

import { signInAs, waitForLiveFleet } from './helpers';

/** Runs axe against WCAG 2.2 A/AA rules and fails on serious or critical issues. */
async function expectNoSeriousViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    // Leaflet's map tiles are decorative images drawn by the library.
    .exclude('.leaflet-tile-pane')
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(', ')})`);
  expect(serious).toEqual([]);
}

test('login page', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();

  await expectNoSeriousViolations(page);
});

test('fleet overview', async ({ page }) => {
  await signInAs(page, 'Operator');
  await waitForLiveFleet(page);

  await expectNoSeriousViolations(page);
});

test('vessel page', async ({ page }) => {
  await signInAs(page, 'Viewer');
  await page.getByRole('link', { name: 'Vinga Pilot' }).click();
  await expect(page.locator('figure canvas')).toHaveCount(2, { timeout: 20_000 });

  await expectNoSeriousViolations(page);
});

test('alerts page', async ({ page }) => {
  await signInAs(page, 'Operator');
  await page.getByRole('link', { name: /Alerts/ }).click();
  await page.getByRole('radio', { name: 'All' }).click();

  await expectNoSeriousViolations(page);
});
