import { test, expect } from './fixtures';

test.describe('Projects', () => {
  test('shows an empty state when there are no projects', async ({ page }) => {
    await page.goto('/projects');

    await expect(page.getByRole('heading', { name: 'No Projects Found' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create First Project' })).toBeVisible();
  });

  test('lists existing projects', async ({ page, bff }) => {
    bff.projects = [
      { id: 'p-1', name: 'Holiday Photos' },
      { id: 'p-2', name: 'Product Shots' },
    ];
    await page.goto('/projects');

    await expect(page.getByRole('heading', { name: '2 Projects Found' })).toBeVisible();
    await expect(page.locator('.project-card')).toHaveCount(2);
    await expect(page.locator('.project-card').first()).toContainText('Holiday Photos');
  });

  test('creates a project from the empty state', async ({ page, bff }) => {
    await page.goto('/projects');

    page.once('dialog', (dialog) => dialog.accept('Wedding'));
    await page.getByRole('button', { name: 'Create First Project' }).click();

    await expect(page.locator('.project-card')).toContainText('Wedding');
    expect(bff.projects.map((p) => p.name)).toEqual(['Wedding']);
  });

  test('navigates to the upload page for a project', async ({ page, bff }) => {
    bff.projects = [{ id: 'p-1', name: 'Holiday Photos' }];
    await page.goto('/projects');

    await page.getByRole('button', { name: 'Upload Images' }).click();
    await expect(page).toHaveURL(/\/upload\/p-1$/);
  });
});
