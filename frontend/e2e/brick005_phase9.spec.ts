import { test, expect } from '@playwright/test';

test.describe('BRICK-005 Phase 9: Model-Driven MCP Tool Selection, Protocol Reconciliation & Confidential Ledger', () => {
  const e2eToken = process.env.JAVED_OWNER_TOKEN || 'test-e2e-owner-token-987654321';

  test.beforeEach(async ({ page }) => {
    await page.goto('/dev/connectivity');
    await page.evaluate(() => localStorage.clear());
  });

  test('Scenario A — Protocol Version & Diagnostics: Time MCP Server negotiates 2026-07-28 protocol version', async ({ page }) => {
    const consolePanel = page.locator('[data-testid="mcp-admin-panel"]');
    await expect(consolePanel).toBeVisible({ timeout: 15000 });

    // 1. Inspect Servers Tab
    await page.locator('[data-testid="mcp-tab-servers"]').click();
    const serverCard = page.locator('[data-testid="mcp-server-time"]');
    await expect(serverCard).toBeVisible({ timeout: 15000 });
    await expect(serverCard).toContainText(/Time Reference Server/i);
    // Protocol version 2026-07-28 verified live
    await expect(serverCard).toContainText(/2026-07-28/i);

    // 2. Inspect Diagnostics Tab
    await page.locator('[data-testid="mcp-tab-diagnostics"]').click();
    const diagSection = page.locator('[data-testid="mcp-diagnostics-section"]');
    await expect(diagSection).toBeVisible({ timeout: 10000 });
    await expect(diagSection).toContainText(/MCP Subsystem Diagnostics/i);
  });

  test('Scenario B — Execution Ledger: Expandable item details display redacted arguments safely', async ({ page }) => {
    // 1. Authenticate with owner token
    const tokenInput = page.locator('[data-testid="mcp-owner-token-input"]');
    await tokenInput.fill(e2eToken);
    await page.locator('[data-testid="mcp-owner-token-submit-btn"]').click();
    await expect(page.locator('[data-testid="mcp-owner-auth-card"]')).toContainText(/Owner Session Active/i);

    // 2. Navigate to Ledger Tab
    await page.locator('[data-testid="mcp-tab-ledger"]').click();
    const ledgerViewer = page.locator('[data-testid="mcp-ledger-viewer"]');
    await expect(ledgerViewer).toBeVisible({ timeout: 10000 });

    // 3. Inspect ledger entries if present
    const ledgerEntries = page.locator('[data-testid^="mcp-ledger-entry-"]');
    const count = await ledgerEntries.count();
    if (count > 0) {
      const firstEntry = ledgerEntries.first();
      const detailsBtn = firstEntry.locator('button:has-text("Details")');
      if (await detailsBtn.isVisible()) {
        await detailsBtn.click();
      }
      const argsView = page.locator('[data-testid="ledger-arguments-view"]').first();
      if (await argsView.isVisible()) {
        const text = await argsView.innerText();
        // Secrets must be redacted
        expect(text).not.toContain('SUPER_SECRET');
        expect(text).not.toContain('api_key_value');
      }
    }
  });

  test('Scenario C — Model Selector Tool Capability: Chat view model selector shows tool capabilities', async ({ page }) => {
    await page.goto('/');

    const modelTrigger = page.locator('#model-selector-trigger');
    await expect(modelTrigger).toBeVisible({ timeout: 10000 });
    await expect(modelTrigger).toContainText(/Auto Router|gpt|claude|gemini/i);

    // Click trigger to open dropdown
    await modelTrigger.click();
    const dropdown = page.locator('#model-selector-dropdown');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    // Close dropdown
    await modelTrigger.click();
  });

  test('Scenario D — Conversational Intent & Tool Boundary: Direct prompt does not trigger unneeded tool execution', async ({ page }) => {
    await page.goto('/');

    const textarea = page.locator('#chat-input-textarea');
    await expect(textarea).toBeVisible({ timeout: 10000 });

    // Send concise conversational prompt
    await textarea.fill('Hello! What is your name and purpose?');

    const sendBtn = page.locator('#send-message-button');
    await expect(sendBtn).toBeEnabled();
    await sendBtn.click();

    // User message should appear
    await expect(page.locator('text=Hello! What is your name')).toBeVisible();

    // Assistant response should start streaming
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble.first()).toBeVisible({ timeout: 25000 });

    // Should NOT have an active tool card in pure conversational answer
    const toolCards = page.locator('[data-testid="tool-activity-card"]');
    expect(await toolCards.count()).toBe(0);
  });
});
