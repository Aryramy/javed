import { test, expect } from '@playwright/test';

test.describe('BRICK-005 Phase 6: Minimal React Live Acceptance in Developer Mode', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dev/connectivity');
  });

  test('01. View Time MCP connection status, discovered tools, and mutate permissions live', async ({ page }) => {
    // 1. Verify Developer Mode Connectivity View renders MCP Administration Panel
    const adminPanel = page.locator('[data-testid="mcp-admin-panel"]');
    await expect(adminPanel).toBeVisible({ timeout: 15000 });

    // 2. View approved Time MCP Server connection status
    const serverCard = page.locator('[data-testid="mcp-server-time"]');
    await expect(serverCard).toBeVisible({ timeout: 15000 });
    await expect(serverCard).toContainText(/Time Reference Server/i);
    await expect(serverCard).toContainText(/transport: stdio/i);

    // 3. View the two discovered Time tools
    const toolTime = page.locator('[data-testid="mcp-tool-time__get_current_time"]');
    const toolConvert = page.locator('[data-testid="mcp-tool-time__convert_time"]');
    await expect(toolTime).toBeVisible();
    await expect(toolConvert).toBeVisible();

    // 4. Verify Owner Authentication Required card is visible and controls are initially disabled
    const authCard = page.locator('[data-testid="mcp-owner-auth-card"]');
    await expect(authCard).toBeVisible();
    await expect(authCard).toContainText(/Owner Authentication Required/i);

    const permSelect = page.locator('[data-testid="mcp-perm-select-time__get_current_time"]');
    await expect(permSelect).toBeDisabled();

    // 5. Authenticate with owner token (configured via JAVED_OWNER_TOKEN)
    const e2eToken = process.env.JAVED_OWNER_TOKEN || 'test-e2e-owner-token-987654321';
    const tokenInput = page.locator('[data-testid="mcp-owner-token-input"]');
    await tokenInput.fill(e2eToken);
    const unlockBtn = page.locator('[data-testid="mcp-owner-token-submit-btn"]');
    await unlockBtn.click();

    // Verify session is active and controls are unlocked
    await expect(authCard).toContainText(/Owner Session Active/i);
    await expect(permSelect).toBeEnabled();

    // 6. Apply one owner-authorized permission change: mutate time__get_current_time to ALLOWED_READ_ONLY
    await permSelect.selectOption('allowed_read_only');

    const updateBtn = page.locator('[data-testid="mcp-perm-update-btn-time__get_current_time"]');
    await expect(updateBtn).toBeEnabled();

    const [mutationResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes('/api/v1/mcp/tools/time__get_current_time/permission') &&
          res.status() === 200,
        { timeout: 15000 }
      ),
      updateBtn.click(),
    ]);

    expect(mutationResponse.status()).toBe(200);
    const mutationData = await mutationResponse.json();
    expect(mutationData.tool.permission).toBe('allowed_read_only');

    // 7. Verify the updated permission state is rendered in the UI
    const feedback = page.locator('[data-testid="mcp-admin-feedback"]');
    await expect(feedback).toBeVisible();
    await expect(feedback).toContainText(/Updated 'time__get_current_time' to ALLOWED_READ_ONLY/i);
    await expect(toolTime).toContainText(/ALLOWED_READ_ONLY/);

    // 8. Restore DENIED and verify immediate revocation
    await permSelect.selectOption('denied');
    const [revokeResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes('/api/v1/mcp/tools/time__get_current_time/permission') &&
          res.status() === 200,
        { timeout: 15000 }
      ),
      updateBtn.click(),
    ]);

    expect(revokeResponse.status()).toBe(200);
    const revokeData = await revokeResponse.json();
    expect(revokeData.tool.permission).toBe('denied');
    expect(revokeData.tool.enabled).toBe(false);

    await expect(feedback).toContainText(/Updated 'time__get_current_time' to DENIED/i);
    await expect(toolTime).toContainText(/DENIED/);

    // 9. Lock console (logout) and verify controls lock again
    const logoutBtn = page.locator('[data-testid="mcp-owner-logout-btn"]');
    await logoutBtn.click();
    await expect(authCard).toContainText(/Owner Authentication Required/i);
    await expect(permSelect).toBeDisabled();
  });
});
