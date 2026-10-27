import { test, expect } from './fixtures';

test.describe('App shell', () => {
  test('shows the signed-in user in the toolbar and profile card', async ({ page, bff }) => {
    await page.goto('/');

    await expect(page.locator('mat-toolbar')).toContainText('Secure File Gateway');
    await expect(page.locator('.user-chip')).toContainText(bff.user!.preferred_username);

    const profile = page.locator('.profile-card');
    await expect(profile.getByRole('heading', { name: 'Jane Doe' })).toBeVisible();
    await expect(profile).toContainText('jane.doe@image-platform.local');
    await expect(profile.locator('.verified')).toBeVisible();
  });

  test('offers Sign In when the user is not authenticated', async ({ page, bff }) => {
    bff.user = null;
    await page.goto('/');

    await expect(page.getByRole('link', { name: /Sign In/ })).toBeVisible();
    await expect(page.getByText('Loading profile...')).toBeVisible();
  });

  test('redirects the root path to /projects', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/projects$/);
  });
});
