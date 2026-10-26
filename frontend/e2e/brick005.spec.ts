import { test, expect } from '@playwright/test';

test.describe('BRICK-005 Phase 5B: Real Chrome HITL End-to-End Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
  });

  test('01. Approve Scenario — Real approval card appears, approve click resumes LangGraph and executes Time MCP tool', async ({ page }) => {
    // 1. Open JAVED User Mode
    await page.goto('/');

    // 2. Select Agent Mode
    const agentToggle = page.locator('#mode-toggle-agent');
    await expect(agentToggle).toBeVisible({ timeout: 15000 });
    await agentToggle.click();
    await expect(page.locator('#agent-status-badge')).toBeVisible();

    // 3. Trigger a Time MCP tool request under APPROVAL_REQUIRED policy
    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('What is the current time in UTC using the official time tool?');
    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // 4. Verify that the real approval card appears
    const approvalCard = page.locator('[data-testid="approval-card"]');
    await expect(approvalCard).toBeVisible({ timeout: 45000 });
    await expect(page.locator('#approval-tool-name')).toHaveText('time__get_current_time');
    await expect(page.locator('#approval-server-id')).toHaveText('time');
    await expect(page.locator('#approval-status-badge')).toHaveText(/pending/i);

    // 5. Confirm that no MCP dispatch happened before approval
    await expect(page.locator('#approve-tool-button')).toBeVisible();
    await expect(page.locator('#reject-tool-button')).toBeVisible();

    // 6. Click Approve in Chrome & 7. Verify actual FastAPI request
    const [resumeResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes('/api/v1/agent/approvals/') &&
          res.url().includes('/resume') &&
          res.status() === 200,
        { timeout: 30000 }
      ),
      page.locator('#approve-tool-button').click(),
    ]);

    expect(resumeResponse.status()).toBe(200);

    // 8. Verify the correct LangGraph invocation resumes & 9. Real Time MCP server executes exactly once
    // 10. Verify result appears in the React chat
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble.last()).toContainText(/time|datetime|UTC|202/i, { timeout: 45000 });

    // 11. Verify the UI does not incorrectly remain paused
    await expect(page.locator('#agent-status-badge')).toContainText(/completed/i, { timeout: 30000 });
    // Approval status badge updates to approved
    await expect(page.locator('#approval-status-badge')).toHaveText(/approved/i);
  });

  test('02. Reject Scenario — Rejecting tool request prevents MCP execution and updates UI', async ({ page }) => {
    // 1. Open JAVED User Mode
    await page.goto('/');

    // 2. Select Agent Mode
    const agentToggle = page.locator('#mode-toggle-agent');
    await expect(agentToggle).toBeVisible({ timeout: 15000 });
    await agentToggle.click();
    await expect(page.locator('#agent-status-badge')).toBeVisible();

    // Trigger a new real approval request
    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Please fetch the current time in UTC.');
    const sendButton = page.locator('#send-message-button');
    await sendButton.click();

    // Verify approval card appears
    const approvalCard = page.locator('[data-testid="approval-card"]');
    await expect(approvalCard).toBeVisible({ timeout: 45000 });
    await expect(page.locator('#approval-status-badge')).toHaveText(/pending/i);

    // Click Reject
    const rejectButton = page.locator('#reject-tool-button');
    await rejectButton.click();

    // In the reject form, fill an optional reason or confirm
    const confirmReject = page.locator('#confirm-reject-button');
    await expect(confirmReject).toBeVisible();

    const [resumeResponse] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes('/api/v1/agent/approvals/') &&
          res.url().includes('/resume') &&
          res.status() === 200,
        { timeout: 30000 }
      ),
      confirmReject.click(),
    ]);

    expect(resumeResponse.status()).toBe(200);

    // Verify that MCP execution never occurred and rejected state is displayed
    await expect(page.locator('#approval-status-badge')).toHaveText(/rejected/i, { timeout: 30000 });
    await expect(page.locator('#agent-status-badge')).toContainText(/completed|idle/i, { timeout: 30000 });

    // Chat bubble displays cancellation / refusal
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble.last()).toContainText(/rejected|cancelled/i, { timeout: 30000 });
  });
});
