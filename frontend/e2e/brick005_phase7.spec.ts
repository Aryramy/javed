import { test, expect } from '@playwright/test';

test.describe('BRICK-005 Phase 7: Real Chrome User Mode MCP Tool Interaction & Agent Runtime', () => {
  const e2eToken = process.env.JAVED_OWNER_TOKEN || 'test-e2e-owner-token-987654321';

  // Helper to mutate tool policy via owner session
  async function setToolPolicy(request: any, toolId: string, permission: 'allowed_read_only' | 'approval_required' | 'denied') {
    const sessRes = await request.post('http://127.0.0.1:8000/api/v1/mcp/auth/session', {
      headers: {
        'Origin': 'http://127.0.0.1:5173',
        'Host': '127.0.0.1:8000',
      },
      data: { owner_token: e2eToken },
    });
    if (!sessRes.ok()) {
      throw new Error(`Failed to create owner session: ${await sessRes.text()}`);
    }
    const { session_token } = await sessRes.json();
    const toolRes = await request.get(`http://127.0.0.1:8000/api/v1/mcp/tools/${encodeURIComponent(toolId)}`);
    if (!toolRes.ok()) {
      throw new Error(`Failed to inspect tool ${toolId}: ${await toolRes.text()}`);
    }
    const toolData = await toolRes.json();

    const permRes = await request.post(`http://127.0.0.1:8000/api/v1/mcp/tools/${encodeURIComponent(toolId)}/permission`, {
      headers: {
        'X-Javed-Owner-Token': session_token,
        'Origin': 'http://127.0.0.1:5173',
        'Host': '127.0.0.1:8000',
      },
      data: {
        permission,
        enabled: permission !== 'denied',
        expected_policy_version: toolData.policy_version,
        expected_fingerprint: toolData.tool.fingerprint,
      },
    });
    if (!permRes.ok()) {
      throw new Error(`Failed to update tool policy: ${await permRes.text()}`);
    }
  }

  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
  });

  test('Scenario A — Read-only Time tool executes directly and displays real activity without approval modal', async ({ page, request }) => {
    // 1. Authorize tool as ALLOWED_READ_ONLY
    await setToolPolicy(request, 'time__get_current_time', 'allowed_read_only');

    // 2. Open User Mode and select Agent Mode
    await page.goto('/');
    const agentToggle = page.locator('#mode-toggle-agent');
    await expect(agentToggle).toBeVisible({ timeout: 15000 });
    await agentToggle.click();
    await expect(page.locator('#agent-status-badge')).toBeVisible();

    // 3. Trigger a Time tool request
    const textarea = page.locator('#chat-input-textarea');
    await textarea.fill('Please tell me the current time in UTC.');
    await page.locator('#send-message-button').click();

    // 4. Verify tool activity card appears in #tool-activity-section
    const activitySection = page.locator('#tool-activity-section');
    await expect(activitySection).toBeVisible({ timeout: 25000 });

    const toolCard = page.locator('[data-testid="tool-activity-card"]');
    await expect(toolCard).toBeVisible();
    await expect(page.locator('[data-testid="tool-activity-name"]')).toHaveText('time__get_current_time');
    await expect(page.locator('[data-testid="tool-activity-server"]')).toHaveText('time');

    // 5. Verify NO approval card appears
    await expect(page.locator('[data-testid="approval-card"]')).toHaveCount(0);

    // 6. Verify completion status and duration display
    const statusBadge = page.locator('[data-testid="tool-activity-status"]');
    await expect(statusBadge).toHaveText(/COMPLETED/i, { timeout: 30000 });
    await expect(page.locator('[data-testid="tool-activity-result"]')).toBeVisible();

    // 7. Verify agent response contains real time info
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble.last()).toContainText(/authorized and executed/i, { timeout: 20000 });
  });

  test('Scenario B — Human approval displays approval card, approves, resumes LangGraph, and completes tool activity', async ({ page, request }) => {
    // 1. Configure APPROVAL_REQUIRED policy
    await setToolPolicy(request, 'time__get_current_time', 'approval_required');

    // 2. Open User Mode and select Agent Mode
    await page.goto('/');
    await page.locator('#mode-toggle-agent').click();
    await expect(page.locator('#agent-status-badge')).toBeVisible();

    // 3. Request time
    await page.locator('#chat-input-textarea').fill('Request current time in UTC under approval policy.');
    await page.locator('#send-message-button').click();

    // 4. Verify real approval card appears in approvals section
    const approvalCard = page.locator('[data-testid="approval-card"]');
    await expect(approvalCard).toBeVisible({ timeout: 30000 });
    await expect(page.locator('#approval-status-badge')).toHaveText(/pending/i);

    // 5. Verify tool activity card also shows AWAITING APPROVAL state
    const activityCard = page.locator('[data-testid="tool-activity-card"]');
    await expect(activityCard).toBeVisible();
    await expect(page.locator('[data-testid="tool-activity-status"]')).toHaveText(/AWAITING APPROVAL/i);

    // 6. Click Approve button
    const approveBtn = page.locator('#approve-tool-button');
    await expect(approveBtn).toBeEnabled();
    await approveBtn.click();

    // 7. Verify approval card transitions to approved
    await expect(page.locator('#approval-status-badge')).toHaveText(/approved/i, { timeout: 20000 });

    // 8. Verify tool activity transitions to COMPLETED
    const activityStatus = page.locator('[data-testid="tool-activity-status"]');
    await expect(activityStatus).toHaveText(/COMPLETED/i, { timeout: 30000 });
    await expect(page.locator('[data-testid="tool-activity-result"]')).toBeVisible();

    // 9. Verify assistant response completes
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble.last()).toContainText(/authorized and executed/i, { timeout: 20000 });
  });

  test('Scenario C — Denial rejects tool call, prevents MCP dispatch, and displays REJECTED state truthfully', async ({ page, request }) => {
    // 1. Ensure APPROVAL_REQUIRED policy
    await setToolPolicy(request, 'time__get_current_time', 'approval_required');

    // 2. Open User Mode in Agent Mode
    await page.goto('/');
    await page.locator('#mode-toggle-agent').click();

    // 3. Request time
    await page.locator('#chat-input-textarea').fill('Check time to test rejection flow.');
    await page.locator('#send-message-button').click();

    // 4. Verify approval card appears
    const approvalCard = page.locator('[data-testid="approval-card"]');
    await expect(approvalCard).toBeVisible({ timeout: 30000 });

    // 5. Click Reject and confirm rejection
    await page.locator('#reject-tool-button').click();
    const rejectReasonInput = page.locator('#reject-reason-input');
    await expect(rejectReasonInput).toBeVisible();
    await rejectReasonInput.fill('Operation not authorized by security administrator.');
    await page.locator('#confirm-reject-button').click();

    // 6. Verify approval status updates to rejected
    await expect(page.locator('#approval-status-badge')).toHaveText(/rejected/i, { timeout: 15000 });

    // 7. Verify tool activity card reflects REJECTED lifecycle
    const activityCard = page.locator('[data-testid="tool-activity-card"]');
    await expect(activityCard).toBeVisible();
    await expect(page.locator('[data-testid="tool-activity-status"]')).toHaveText(/REJECTED/i);

    // 8. Verify agent response acknowledges rejection without generic success
    const assistantBubble = page.locator('.prose');
    await expect(assistantBubble.last()).toContainText(/rejected by human operator/i, { timeout: 20000 });
    await expect(page.locator('[data-testid="tool-activity-card"]')).not.toHaveText(/COMPLETED/i);
  });

  test('Scenario D — Reload recovery restores pending approvals and tool activity without duplication', async ({ page, request }) => {
    // 1. Ensure APPROVAL_REQUIRED policy
    await setToolPolicy(request, 'time__get_current_time', 'approval_required');

    // 2. Open User Mode in Agent Mode
    await page.goto('/');
    await page.locator('#mode-toggle-agent').click();

    // 3. Trigger approval
    await page.locator('#chat-input-textarea').fill('Create pending approval to test page reload recovery.');
    await page.locator('#send-message-button').click();

    const approvalCard = page.locator('[data-testid="approval-card"]');
    await expect(approvalCard).toBeVisible({ timeout: 30000 });

    // 4. Reload the page while approval is pending
    await page.reload();

    // 5. Verify restored state
    await page.locator('#mode-toggle-agent').click();
    await expect(approvalCard).toBeVisible({ timeout: 20000 });
    await expect(page.locator('#approval-status-badge')).toHaveText(/pending/i);

    // Verify tool activity card was restored
    const toolCard = page.locator('[data-testid="tool-activity-card"]');
    await expect(toolCard).toBeVisible({ timeout: 20000 });
    // Single card, no duplication
    await expect(toolCard).toHaveCount(1);

    // 6. Resume successfully after reload
    await page.locator('#approve-tool-button').click();
    await expect(page.locator('#approval-status-badge')).toHaveText(/approved/i, { timeout: 20000 });
    await expect(page.locator('[data-testid="tool-activity-status"]')).toHaveText(/COMPLETED/i, { timeout: 30000 });
  });

  test('Scenario E — Controlled tool failure displays FAILED lifecycle state and error message truthfully', async ({ page, request }) => {
    // 1. Authorize tool as ALLOWED_READ_ONLY so it dispatches directly to MCP server
    await setToolPolicy(request, 'time__get_current_time', 'allowed_read_only');

    // 2. Open User Mode in Agent Mode
    await page.goto('/');
    await page.locator('#mode-toggle-agent').click();

    // 3. Request time with invalid timezone prompt to trigger controlled server failure
    await page.locator('#chat-input-textarea').fill('Get time in fail invalid timezone test.');
    await page.locator('#send-message-button').click();

    // 4. Verify tool activity card appears
    const activityCard = page.locator('[data-testid="tool-activity-card"]');
    await expect(activityCard).toBeVisible({ timeout: 30000 });

    // 5. Verify tool status transitions to FAILED
    const statusBadge = page.locator('[data-testid="tool-activity-status"]');
    await expect(statusBadge).toHaveText(/FAILED/i, { timeout: 30000 });

    // 6. Verify sanitized error is displayed and NO success badge appears
    await expect(page.locator('[data-testid="tool-activity-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="tool-activity-card"]')).not.toHaveText(/COMPLETED/i);

    // 7. Verify agent response acknowledges failure truthfully
    const errorBubble = page.locator('.text-rose-400, .prose').last();
    await expect(errorBubble).toContainText(/Invalid timezone|execution error|failed/i, { timeout: 20000 });
  });
});
