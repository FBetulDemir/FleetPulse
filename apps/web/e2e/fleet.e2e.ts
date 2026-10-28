import { expect, test } from '@playwright/test';

import { signInAs, waitForLiveFleet } from './helpers';

test('the overview shows the live fleet', async ({ page }) => {
  await signInAs(page, 'Viewer');
  await waitForLiveFleet(page);

  await expect(page.locator('tbody tr')).toHaveCount(5);
  await expect(page.locator('.kpi', { hasText: 'Vessels' }).locator('dd')).toHaveText('5');
  await expect(page.getByText('Connected')).toBeVisible();
});

test('a vessel page shows live readings, live charts and history', async ({ page }) => {
  await signInAs(page, 'Viewer');
  await page.getByRole('link', { name: 'Vinga Pilot' }).click();

  await expect(page.getByRole('heading', { name: 'Vinga Pilot' })).toBeVisible();
  await expect(page.locator('.tile', { hasText: 'Speed' }).locator('dd')).toHaveText(/kn$/);
  // Charts appear once a few live readings have arrived.
  await expect(page.locator('figure canvas')).toHaveCount(2, { timeout: 20_000 });

  await page.getByRole('tab', { name: 'History' }).click();
  await expect(page.locator('.tile', { hasText: 'Readings' }).locator('dd')).toHaveText(/\d/);
  await expect(page.locator('figure canvas')).toHaveCount(1);
});
