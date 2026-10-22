import { test, expect } from '@playwright/test';

test.describe('BRICK-003: OpenRouter LLM Integration & Live Streaming Chat', () => {
  test('01. Chat View renders model selector with curated frontier models and allows selection', async ({ page }) => {
    await page.goto('/');

    // Wait for model selector trigger
    const modelTrigger = page.locator('#model-selector-trigger');
    await expect(modelTrigger).toBeVisible({ timeout: 10000 });
    await expect(modelTrigger).toContainText('Auto Router');

    // Click trigger to open dropdown
    await modelTrigger.click();

    const dropdown = page.locator('#model-selector-dropdown');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    // Verify models in dropdown
    await expect(dropdown).toContainText('Claude Sonnet 4.5');
    await expect(dropdown).toContainText('Gemini 2.5 Flash');
    await expect(dropdown).toContainText('DeepSeek Chat V3');

    // Select Gemini 2.5 Flash
    const geminiOption = dropdown.locator('button:has-text("Gemini 2.5 Flash")');
    await geminiOption.click();

    // Verify trigger updated
    await expect(modelTrigger).toContainText('Gemini 2.5 Flash');
    await expect(dropdown).not.toBeVisible();
  });

  test('02. Live Chat Streaming generates real tokens and displays usage cost', async ({ page }) => {
    await page.goto('/');

    const textarea = page.locator('#chat-input-textarea');
    await expect(textarea).toBeVisible({ timeout: 10000 });

    // Type a concise prompt
    await textarea.fill('Reply with exactly two words: "Javed Verified"');

    const sendButton = page.locator('#send-message-button');
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    // User message should appear
    await expect(page.locator('text=Reply with exactly two words:')).toBeVisible();

    // Assistant response should start and finish streaming
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble).toContainText(/Javed|Verified/i, { timeout: 25000 });

    // Verify token and cost telemetry pill rendered in assistant bubble
    const telemetryPill = page.locator('text=/tokens/i');
    await expect(telemetryPill.first()).toBeVisible({ timeout: 10000 });
  });

  test('03. Stream Cancellation stops generation immediately', async ({ page }) => {
    await page.goto('/');

    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Write an extremely detailed, 1000-word essay about the cosmos, stars, and galaxies.');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Stop button should appear during streaming
    const stopButton = page.locator('#stop-generation-button');
    await expect(stopButton).toBeVisible({ timeout: 10000 });

    // Click stop button
    await stopButton.click();

    // Stop button should disappear and input re-enabled
    await expect(stopButton).not.toBeVisible({ timeout: 5000 });
    await expect(textarea).toBeEnabled({ timeout: 5000 });
  });

  test('04. Clear conversation resets chat history and returns to starter state', async ({ page }) => {
    await page.goto('/');

    const clearButton = page.locator('#clear-chat-button');
    await expect(clearButton).toBeVisible();

    await clearButton.click();

    // Empty state should be visible
    await expect(page.locator('text=Conversational AI Gateway')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=BRICK-003: OpenRouter Integration & Streaming Chat (ACTIVE)')).toBeVisible();
  });

  test('05. Developer Telemetry and Diagnostics views show live OpenRouter status', async ({ page }) => {
    // Check Telemetry View
    await page.goto('/dev/telemetry');
    await expect(page.locator('text=OpenRouter Billing & Rate Telemetry (BRICK-003 Live)')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('ACTIVE', { exact: true })).toBeVisible();
    await expect(page.locator('text=Application Daily Budget')).toBeVisible();
    await expect(page.locator('text=Frontier Model Rate Cards')).toBeVisible();

    // Check Diagnostics View
    await page.goto('/dev/diagnostics');
    const queryCatalogBtn = page.locator('button:has-text("Query Model Catalog")');
    await expect(queryCatalogBtn).toBeVisible({ timeout: 10000 });

    await queryCatalogBtn.click();

    const terminalBox = page.locator('pre');
    await expect(terminalBox).toContainText('"_test": "GET /api/v1/models"', { timeout: 10000 });
    await expect(terminalBox).toContainText('"_status": 200');
    await expect(terminalBox).toContainText('"default_model":');
  });

  test('06. Model selector dynamic search filters models in dropdown', async ({ page }) => {
    await page.goto('/');

    const modelTrigger = page.locator('#model-selector-trigger');
    await modelTrigger.click();

    const dropdown = page.locator('#model-selector-dropdown');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    // Type "DeepSeek" in the search input
    const searchInput = dropdown.locator('input[placeholder*="Search model"]');
    await searchInput.fill('DeepSeek');

    // DeepSeek should be visible, others filtered out
    await expect(dropdown.locator('text=DeepSeek Chat V3')).toBeVisible();
    await expect(dropdown.locator('text=Claude Sonnet 4.5')).not.toBeVisible();
  });

  test('07. Auto Router selection, cost tier switching, and dynamic model routing display', async ({ page }) => {
    await page.goto('/');

    const modelTrigger = page.locator('#model-selector-trigger');
    await expect(modelTrigger).toBeVisible({ timeout: 10000 });

    // Open dropdown and select Auto Router
    await modelTrigger.click();
    const dropdown = page.locator('#model-selector-dropdown');
    await expect(dropdown).toBeVisible({ timeout: 5000 });

    const autoRouterOption = dropdown.locator('button:has-text("Auto Router")');
    await expect(autoRouterOption).toBeVisible();
    await autoRouterOption.click();

    // Verify trigger shows Auto Router and default 'low' tier
    await expect(modelTrigger).toContainText('Auto Router');
    const tierBadge = page.locator('#model-selector-tier-badge');
    await expect(tierBadge).toContainText('low');

    // Cost tier selector should be visible
    const tierSelector = page.locator('#cost-tier-selector');
    await expect(tierSelector).toBeVisible();

    // Switch to medium tier
    const medButton = page.locator('#cost-tier-button-medium');
    await medButton.click();
    await expect(tierBadge).toContainText('medium');

    // Switch back to economical default 'low' tier
    const lowButton = page.locator('#cost-tier-button-low');
    await lowButton.click();
    await expect(tierBadge).toContainText('low');

    // Submit a query via Auto Router
    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Reply with exactly "AutoRouter Success"');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Assistant response should start streaming
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble).toBeVisible({ timeout: 20000 });
    await expect(assistantBubble).toContainText(/AutoRouter|Success/i, { timeout: 20000 });

    // Verify routed model badge is displayed with concrete resolved model
    const routedBadge = page.locator('#message-routed-model-badge');
    await expect(routedBadge).toBeVisible({ timeout: 15000 });
    await expect(routedBadge).toContainText('Routed:');
    await expect(routedBadge).toContainText(/low/i);
  });
});
