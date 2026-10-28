import { expect, test } from '@playwright/test';

import { signInAs, waitForLiveFleet } from './helpers';

test('an operator triggers a failure, gets notified and acknowledges the alert', async ({
  page,
}) => {
  await signInAs(page, 'Operator');
  await waitForLiveFleet(page);

  // "Send bad data" raises its alert immediately, which keeps this test fast.
  await page.getByRole('combobox', { name: 'Vessel' }).click();
  await page.getByRole('option', { name: 'Donsö Surveyor' }).click();
  await page.getByRole('button', { name: 'Send bad data' }).click();

  const notification = page.locator('.mat-mdc-snack-bar-label', {
    hasText: 'Warning · Donsö Surveyor: Invalid telemetry',
  });
  await expect(notification.first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('link', { name: /Alerts/ })).toContainText(/\d+ open/);

  await page.getByRole('button', { name: 'View alerts' }).click();
  const alert = page.locator('.alert', { hasText: 'Donsö Surveyor' }).first();
  await expect(alert).toContainText('Invalid telemetry');

  await alert.getByRole('button', { name: /Acknowledge/ }).click();
  await expect(alert).toContainText('Acknowledged by Demo Operator');

  // Put the vessel back to normal for other tests.
  await page.getByRole('link', { name: 'Overview' }).click();
  await page.getByRole('combobox', { name: 'Vessel' }).click();
  await page.getByRole('option', { name: 'Donsö Surveyor' }).click();
  await page.getByRole('button', { name: 'Reset' }).click();
});

test('viewers can see alerts but not trigger failures or acknowledge', async ({ page }) => {
  await signInAs(page, 'Viewer');

  await expect(page.getByText('Sign in as Operator or Admin')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Overheat motor' })).toHaveCount(0);

  await page.getByRole('link', { name: /Alerts/ }).click();
  await page.getByRole('radio', { name: 'All' }).click();
  await expect(page.getByRole('button', { name: /Acknowledge/ })).toHaveCount(0);
});
