// e2e/fixtures.ts
import { test as base, Page } from '@playwright/test';

export interface MockUser {
  name: string;
  given_name: string;
  family_name: string;
  preferred_username: string;
  email: string;
  email_verified: boolean;
}

export interface MockProject {
  id: string;
  name: string;
}

export const testUser: MockUser = {
  name: 'Jane Doe',
  given_name: 'Jane',
  family_name: 'Doe',
  preferred_username: 'jdoe',
  email: 'jane.doe@image-platform.local',
  email_verified: true,
};

/**
 * In-memory stand-in for the BFF, so e2e tests run against `ng serve`
 * without Keycloak, the BFF, or the AssetService.
 */
export class MockBff {
  user: MockUser | null = testUser;
  projects: MockProject[] = [];

  constructor(private page: Page) {}

  async install() {
    await this.page.route('**/api/me', (route) =>
      this.user
        ? route.fulfill({ json: { id_token: this.user } })
        : route.fulfill({ status: 401, json: { detail: 'Not authenticated' } }),
    );

    await this.page.route('**/api/proxy/projects/', async (route) => {
      const request = route.request();
      if (request.method() === 'POST') {
        const { name } = request.postDataJSON() as { name: string };
        const project = { id: crypto.randomUUID(), name };
        this.projects.push(project);
        return route.fulfill({ status: 201, json: project });
      }
      return route.fulfill({ json: this.projects });
    });

    await this.page.route('**/api/logout', (route) => route.fulfill({ json: { logoutUrl: '' } }));
  }
}

export const test = base.extend<{ bff: MockBff }>({
  // auto: every test gets the mocked BFF, even if it never touches `bff`.
  bff: [
    async ({ page }, use) => {
      const bff = new MockBff(page);
      await bff.install();
      await use(bff);
    },
    { auto: true },
  ],
});

export { expect } from '@playwright/test';
