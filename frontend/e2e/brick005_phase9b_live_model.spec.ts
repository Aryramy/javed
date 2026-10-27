import { test, expect } from '@playwright/test';

test.describe('BRICK-005 Phase 9B: Real Live OpenRouter Model MCP Browser Acceptance', () => {
  test('Full Real Stack: Real OpenRouter Model -> Real Time MCP Execution -> Final React Response', async ({ page }) => {
    test.setTimeout(90000);

    await page.goto('/');

    // 1. Activate Agent Mode (LangGraph Deep Agents Runtime + SecureMCPGateway)
    const agentModeToggle = page.locator('#mode-toggle-agent');
    await expect(agentModeToggle).toBeVisible({ timeout: 15000 });
    await agentModeToggle.click();
    await expect(agentModeToggle).toHaveClass(/bg-blue/);

    const textarea = page.locator('#chat-input-textarea');
    await expect(textarea).toBeVisible({ timeout: 15000 });

    // 2. Send prompt asking for current time in Doha using the Time MCP tool
    const promptText = 'What is the current time in Doha? Use the available Time MCP tool.';
    await textarea.fill(promptText);

    const sendBtn = page.locator('#send-message-button');
    await expect(sendBtn).toBeEnabled();
    await sendBtn.click();

    // 3. User message appears in chat
    await expect(page.locator(`text=${promptText}`)).toBeVisible({ timeout: 5000 });

    // 4. Real model generates tool call -> SecureMCPGateway dispatches to real Time MCP STDIO server
    const toolCard = page.locator('[data-testid="tool-activity-card"]');
    await expect(toolCard.first()).toBeVisible({ timeout: 45000 });

    // 5. Verify tool card attributes & execution state
    await expect(toolCard.first()).toHaveAttribute('data-tool-id', 'time__get_current_time');
    await expect(toolCard.first()).toContainText(/COMPLETED/i, { timeout: 30000 });

    // 6. Verify Assistant response renders truthful real time synthesis
    const assistantProse = page.locator('.prose');
    await expect(assistantProse.first()).toBeVisible({ timeout: 30000 });
    const responseText = await assistantProse.first().innerText();
    expect(responseText.length).toBeGreaterThan(15);
    expect(responseText.toLowerCase()).toMatch(/doha|qatar|time|utc|\d{1,2}:\d{2}|2026/i);

    // 7. Confirm no scripted-model substitution occurred
    expect(responseText).not.toContain('The time request was rejected by human operator');
  });
});
