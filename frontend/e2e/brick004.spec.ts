import { test, expect } from '@playwright/test';

test.describe('BRICK-004: Deep Agents & LangGraph Runtime E2E Acceptance', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Clear storage before each test for clean isolation
    await page.evaluate(() => localStorage.clear());
  });

  test('01. Interaction Mode Switcher toggles between Chat Mode and Agent Mode', async ({ page }) => {
    await page.goto('/');

    const chatToggle = page.locator('#mode-toggle-chat');
    const agentToggle = page.locator('#mode-toggle-agent');

    await expect(chatToggle).toBeVisible({ timeout: 10000 });
    await expect(agentToggle).toBeVisible();

    // Initial state is Chat Mode
    await expect(page.locator('text=Conversational AI Gateway')).toBeVisible();

    // Click Agent Mode toggle
    await agentToggle.click();

    // Verify Agent Mode UI active
    await expect(page.locator('text=Stateful Agent Runtime')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('text=BRICK-004: Deep Agents + LangGraph Runtime (ACTIVE)')).toBeVisible();
    await expect(page.locator('#agent-status-badge')).toBeVisible();
    await expect(page.locator('#new-thread-button')).toBeVisible();
    await expect(page.getByText('Deep Agents + LangGraph', { exact: true })).toBeVisible();

    // Switch back to Chat Mode
    await chatToggle.click();
    await expect(page.locator('text=Conversational AI Gateway')).toBeVisible({ timeout: 5000 });
  });

  test('02. Scenario A — Simple request produces direct response without elaborate plan', async ({ page }) => {
    await page.goto('/');

    // Switch to Agent Mode
    await page.locator('#mode-toggle-agent').click();
    await expect(page.locator('#agent-status-badge')).toBeVisible();

    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Explain what a Power BI measure is in two sentences.');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Assistant response should appear and stream
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble).toContainText(/measure|calculation|formula|DAX/i, { timeout: 60000 });

    // Status badge should transition to COMPLETED
    await expect(page.locator('#agent-status-badge')).toContainText(/completed/i, { timeout: 30000 });

    // Telemetry pill should appear
    const telemetryPill = page.locator('text=/tokens/i');
    await expect(telemetryPill.first()).toBeVisible({ timeout: 15000 });
  });

  test('03. Scenario B — Complex planning generates structured task plan with real framework events', async ({ page }) => {
    test.setTimeout(120000);
    await page.goto('/');

    // Switch to Agent Mode
    await page.locator('#mode-toggle-agent').click();

    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Create a five-step implementation plan for a Power BI project using SharePoint data, including validation checkpoints.');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Real TaskPlanPanel should appear during or after planning
    const planPanel = page.locator('[data-testid="task-plan-panel"]');
    // Allow up to 60s for model reasoning and streaming
    await expect(planPanel).toBeVisible({ timeout: 60000 });
    await expect(planPanel).toContainText('Structured Agent Plan');

    // Verify structured plan steps rendered
    const todoItems = page.locator('[data-testid^="todo-item-"]');
    await expect(todoItems.first()).toBeVisible();

    // Assistant explanation content should also render
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble).toContainText(/SharePoint|Power BI|plan|step|validation/i, { timeout: 35000 });

    // Verify completed badge
    await expect(page.locator('#agent-status-badge')).toContainText(/completed/i, { timeout: 15000 });
  });

  test('04. Scenario C — Persistent thread context retains conversation memory', async ({ page }) => {
    await page.goto('/');

    // Switch to Agent Mode
    await page.locator('#mode-toggle-agent').click();

    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('For this conversation, remember that our sample project is called Project Orchid.');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Wait for acknowledgment
    const assistantBubble = page.locator('.prose').first();
    await expect(assistantBubble).toContainText(/Orchid|remember|project/i, { timeout: 60000 });
    await expect(page.locator('#agent-status-badge')).toContainText(/completed/i, { timeout: 30000 });

    // Follow-up question in the same thread
    await textarea.fill('What is the sample project called?');
    await sendButton.click();

    // Second assistant bubble should specifically recall "Project Orchid"
    const secondAssistantBubble = page.locator('.prose').nth(1);
    await expect(secondAssistantBubble).toContainText(/Project Orchid|Orchid/i, { timeout: 60000 });
  });

  test('05. Scenario D — Strict Zero-Trust boundary rejects unauthorized host operations', async ({ page }) => {
    await page.goto('/');

    // Switch to Agent Mode
    await page.locator('#mode-toggle-agent').click();

    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Delete a file from my Desktop.');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Assistant response must clearly indicate refusal or lack of filesystem capabilities
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble).toContainText(
      /cannot|unable|prohibited|not supported|not allowed|do not have access|don't have access|not able|security|boundary/i,
      {
        timeout: 60000,
      }
    );

    // Confirm agent status completed
    await expect(page.locator('#agent-status-badge')).toContainText(/completed/i, { timeout: 30000 });
  });

  test('06. Agent stream cancellation halts generation cleanly', async ({ page }) => {
    await page.goto('/');

    // Switch to Agent Mode
    await page.locator('#mode-toggle-agent').click();

    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Generate an extremely verbose 20-step analysis of architectural patterns for multi-agent systems.');

    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Stop button should become visible while streaming
    const stopButton = page.locator('#stop-generation-button');
    await expect(stopButton).toBeVisible({ timeout: 15000 });

    // Click stop button
    await stopButton.click();

    // Status badge should show cancelled
    await expect(page.locator('#agent-status-badge')).toContainText(/cancelled/i, { timeout: 5000 });
    await expect(textarea).toBeEnabled({ timeout: 5000 });
  });

  test('07. Developer Mode telemetry displays live agent runtime properties', async ({ page }) => {
    await page.goto('/dev/telemetry');

    // Verify Deep Agents card is visible in Telemetry view
    await expect(page.locator('text=Deep Agents & LangGraph Runtime (BRICK-004 Live)')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=ACTIVE (0.7.32 / LangGraph 1.2.17)')).toBeVisible();
    await expect(page.locator('text=Checkpointer Engine')).toBeVisible();
    await expect(page.locator('text=AsyncSqliteSaver')).toBeVisible();
    await expect(page.locator('text=Database Path')).toBeVisible();
    await expect(page.locator('text=Zero-Trust Tool Permissions')).toBeVisible();
    await expect(page.locator('text=TodoList Planning Only')).toBeVisible();
    await expect(page.locator('text=Restricted Tools')).toBeVisible();
  });
});
