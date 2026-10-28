import { expect, test } from '@playwright/test';

import { signInAs } from './helpers';

test('protected pages send visitors to the login page and back', async ({ page }) => {
  await page.goto('/alerts');

  await expect(page).toHaveURL(/\/login\?returnUrl=%2Falerts/);

  await page.getByLabel('Email').fill('demo-viewer@example.com');
  await page.getByLabel('Password').fill('fleetpulse-demo');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();

  await expect(page).toHaveURL(/\/alerts$/);
  await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible();
});

test('a wrong password shows one generic message', async ({ page }) => {
  await page.goto('/login');

  await page.getByLabel('Email').fill('demo-admin@example.com');
  await page.getByLabel('Password').fill('not the password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();

  await expect(page.getByRole('alert')).toHaveText('Invalid email or password.');
});

test('the session survives a reload, and signing out ends it', async ({ page, context }) => {
  await signInAs(page, 'Viewer');

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Fleet overview' })).toBeVisible();

  // Tokens are in httpOnly cookies: page scripts cannot read them.
  expect(await page.evaluate(() => document.cookie)).toBe('');
  const names = (await context.cookies()).map((cookie) => cookie.name).sort();
  expect(names).toEqual(['fp_access', 'fp_refresh']);

  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/');
  await expect(page).toHaveURL(/\/login/);
});
