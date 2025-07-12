import { test, expect } from '@playwright/test';

test.describe('Inspector UI', () => {
  test('should load and display Inspector Online', async ({ page }) => {
    // Navigate to the Inspector UI
    await page.goto('/_inspector/ui/');

    // Check that the page loads
    await expect(page).toHaveTitle(/Inspector UI/);

    // Check for the main heading
    await expect(page.locator('h1')).toContainText('🔍 Inspector Online');

    // Check that it fetches and displays the backend version
    await expect(page.locator('.success')).toContainText('Backend version:');
    await expect(page.locator('.success strong')).toContainText('0.0.1');
  });

  test('health endpoint should return valid JSON', async ({ request }) => {
    const response = await request.get('/_inspector/health');
    
    expect(response.ok()).toBeTruthy();
    expect(response.status()).toBe(200);
    
    const json = await response.json();
    expect(json).toHaveProperty('name', 'mcp-agent-inspector');
    expect(json).toHaveProperty('version', '0.0.1');
  });
});