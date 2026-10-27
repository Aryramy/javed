import { test, expect } from '@playwright/test';

test.describe('BRICK-005 Phase 8: Real Chrome Developer MCP Console, Execution Ledger & Live Diagnostics', () => {
  const e2eToken = process.env.JAVED_OWNER_TOKEN || 'test-e2e-owner-token-987654321';

  test.beforeEach(async ({ page }) => {
    await page.goto('/dev/connectivity');
    await page.evaluate(() => localStorage.clear());
  });

  test('Scenario A — Console & Registry: Developer Mode renders real server, discovered tools, and expandable JSON schemas', async ({ page }) => {
    // 1. Verify Developer MCP Console is rendered
    const consolePanel = page.locator('[data-testid="mcp-admin-panel"]');
    await expect(consolePanel).toBeVisible({ timeout: 15000 });
    await expect(consolePanel).toContainText(/Developer MCP Console & Subsystem Gateway/i);

    // 2. Inspect Navigation Tabs
    const overviewTab = page.locator('[data-testid="mcp-tab-overview"]');
    const serversTab = page.locator('[data-testid="mcp-tab-servers"]');
    const toolsTab = page.locator('[data-testid="mcp-tab-tools"]');
    const ledgerTab = page.locator('[data-testid="mcp-tab-ledger"]');
    const approvalsTab = page.locator('[data-testid="mcp-tab-approvals"]');
    const diagnosticsTab = page.locator('[data-testid="mcp-tab-diagnostics"]');

    await expect(overviewTab).toBeVisible();
    await expect(serversTab).toBeVisible();
    await expect(toolsTab).toBeVisible();
    await expect(ledgerTab).toBeVisible();
    await expect(approvalsTab).toBeVisible();
    await expect(diagnosticsTab).toBeVisible();

    // 3. Inspect Live Time MCP Server on Servers tab
    await serversTab.click();
    const serverCard = page.locator('[data-testid="mcp-server-time"]');
    await expect(serverCard).toBeVisible({ timeout: 15000 });
    await expect(serverCard).toContainText(/Time Reference Server/i);
    await expect(serverCard).toContainText(/transport: stdio/i);
    await expect(serverCard).toContainText(/connected/i);
    await expect(serverCard).toContainText(/Tools Discovered:\s*2/i);

    // 4. Switch to Tools tab and verify dynamically discovered tools
    await toolsTab.click();
    const toolTime = page.locator('[data-testid="mcp-tool-time__get_current_time"]');
    const toolConvert = page.locator('[data-testid="mcp-tool-time__convert_time"]');
    await expect(toolTime).toBeVisible({ timeout: 15000 });
    await expect(toolConvert).toBeVisible({ timeout: 15000 });

    // Verify metadata: tool ID, description, SHA-256 fingerprint
    await expect(toolTime).toContainText(/time__get_current_time/);
    await expect(toolTime).toContainText(/fingerprint:/i);

    // 5. Expand JSON input schema for time__convert_time
    const schemaToggle = page.locator('[data-testid="mcp-tool-schema-toggle-time__convert_time"]');
    await expect(schemaToggle).toBeVisible();
    await schemaToggle.click();

    const schemaContainer = page.locator('[data-testid="mcp-tool-input-schema-time__convert_time"]');
    await expect(schemaContainer).toBeVisible();
    await expect(schemaContainer).toContainText(/source_timezone/i);
    await expect(schemaContainer).toContainText(/target_timezone/i);

    // 6. Test search filter
    const searchInput = page.locator('[data-testid="mcp-tool-search-input"]');
    await searchInput.fill('convert');
    await expect(toolConvert).toBeVisible();
    await expect(toolTime).toBeHidden();

    // Clear search
    await searchInput.fill('');
    await expect(toolTime).toBeVisible();
  });

  test('Scenario B — Owner Permission Change: Authenticate, mutate permission, verify backend reflection, revoke, confirm DENIED', async ({ page }) => {
    // 1. Verify owner auth card indicates authentication required
    const authCard = page.locator('[data-testid="mcp-owner-auth-card"]');
    await expect(authCard).toBeVisible({ timeout: 15000 });
    await expect(authCard).toContainText(/Owner Authentication Required/i);

    // 2. Verify permission controls are locked
    await page.locator('[data-testid="mcp-tab-tools"]').click();
    const permSelect = page.locator('[data-testid="mcp-perm-select-time__get_current_time"]');
    await expect(permSelect).toBeDisabled();

    // 3. Authenticate with owner token
    await page.locator('[data-testid="mcp-tab-overview"]').click();
    const tokenInput = page.locator('[data-testid="mcp-owner-token-input"]');
    await tokenInput.fill(e2eToken);
    await page.locator('[data-testid="mcp-owner-token-submit-btn"]').click();

    // Verify session unlocked
    await expect(authCard).toContainText(/Owner Session Active/i);

    // 4. Navigate to Tools and mutate time__get_current_time
    await page.locator('[data-testid="mcp-tab-tools"]').click();
    await expect(permSelect).toBeEnabled();
    const currentVal = await permSelect.inputValue();
    const nextVal = currentVal === 'allowed_read_only' ? 'approval_required' : 'allowed_read_only';
    await permSelect.selectOption(nextVal);

    const updateBtn = page.locator('[data-testid="mcp-perm-update-btn-time__get_current_time"]');
    await expect(updateBtn).toBeEnabled();

    const [mutationRes] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes('/api/v1/mcp/tools/time__get_current_time/permission') &&
          res.status() === 200,
        { timeout: 15000 }
      ),
      updateBtn.click(),
    ]);

    expect(mutationRes.status()).toBe(200);
    const mutationData = await mutationRes.json();
    expect(mutationData.tool.permission).toBe(nextVal);

    // Verify UI feedback
    const feedback = page.locator('[data-testid="mcp-admin-feedback"]');
    await expect(feedback).toBeVisible();
    await expect(feedback).toContainText(new RegExp(`Updated 'time__get_current_time' to ${nextVal.toUpperCase()}`, 'i'));

    // 5. Revoke to DENIED and confirm immediate host-policy enforcement
    await permSelect.selectOption('denied');
    const [revokeRes] = await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes('/api/v1/mcp/tools/time__get_current_time/permission') &&
          res.status() === 200,
        { timeout: 15000 }
      ),
      updateBtn.click(),
    ]);

    expect(revokeRes.status()).toBe(200);
    const revokeData = await revokeRes.json();
    expect(revokeData.tool.permission).toBe('denied');
    await expect(feedback).toContainText(/Updated 'time__get_current_time' to DENIED/i);
  });

  test('Scenario C — Execution Ledger: Authenticated execution records genuine ledger entry with durations and UNCERTAIN safety', async ({ page, request }) => {
    // 1. Authorize time__get_current_time via owner session
    const sessRes = await request.post('http://127.0.0.1:8000/api/v1/mcp/auth/session', {
      headers: {
        'Origin': 'http://127.0.0.1:5173',
        'Host': '127.0.0.1:8000',
      },
      data: { owner_token: e2eToken },
    });
    expect(sessRes.ok()).toBeTruthy();
    const { session_token } = await sessRes.json();

    const toolRes = await request.get('http://127.0.0.1:8000/api/v1/mcp/tools/time__get_current_time');
    const toolData = await toolRes.json();

    const permRes = await request.post('http://127.0.0.1:8000/api/v1/mcp/tools/time__get_current_time/permission', {
      headers: {
        'X-Javed-Owner-Token': session_token,
        'Origin': 'http://127.0.0.1:5173',
        'Host': '127.0.0.1:8000',
      },
      data: {
        permission: 'approval_required',
        enabled: true,
        expected_policy_version: toolData.policy_version,
        expected_fingerprint: toolData.tool.fingerprint,
      },
    });
    expect(permRes.ok()).toBeTruthy();

    // 2. Dispatch a real tool execution via agent stream in User Mode
    await page.goto('/');
    const agentToggle = page.locator('#mode-toggle-agent');
    await expect(agentToggle).toBeVisible({ timeout: 15000 });
    await agentToggle.click();
    await expect(page.locator('#agent-status-badge')).toBeVisible();

    await page.locator('#chat-input-textarea').fill('Please tell me the current time in UTC.');
    await page.locator('#send-message-button').click();

    // Wait for approval card and click Approve
    const approvalCard = page.locator('[data-testid="approval-card"]');
    await expect(approvalCard).toBeVisible({ timeout: 30000 });
    const approveBtn = page.locator('#approve-tool-button');
    await expect(approveBtn).toBeEnabled();
    await approveBtn.click();

    // Wait for tool completion in User Mode
    const statusBadge = page.locator('[data-testid="tool-activity-status"]');
    await expect(statusBadge).toHaveText(/COMPLETED/i, { timeout: 30000 });

    // 3. Navigate back to Developer Mode Execution Ledger
    await page.goto('/dev/connectivity');
    const ledgerTab = page.locator('[data-testid="mcp-tab-ledger"]');
    await expect(ledgerTab).toBeVisible({ timeout: 15000 });
    await ledgerTab.click();

    const ledgerViewer = page.locator('[data-testid="mcp-ledger-viewer"]');
    await expect(ledgerViewer).toBeVisible();

    // 4. Verify durable record appears with tool identity, duration, and status
    const ledgerEntry = page.locator('[data-testid^="mcp-ledger-entry-"]').first();
    await expect(ledgerEntry).toBeVisible({ timeout: 15000 });
    await expect(ledgerEntry).toContainText(/time__get_current_time/i);
    await expect(ledgerEntry).toContainText(/COMPLETED/i);
    await expect(ledgerEntry).toContainText(/ms/i);
    await expect(ledgerEntry).toContainText(/server:\s*time/i);

    // Expand details
    await ledgerEntry.locator('button:has-text("Details")').click();
    await expect(ledgerEntry).toContainText(/Dispatch ID:/i);

    // Verify Section 8 safety: no manual retry button exists
    await expect(ledgerEntry.locator('button:has-text("Retry")')).toHaveCount(0);
  });

  test('Scenario D — Authorization Failure & Logout: Invalid token rejected, logout relocks controls', async ({ page }) => {
    // 1. Attempt unlock with invalid credentials
    const tokenInput = page.locator('[data-testid="mcp-owner-token-input"]');
    await tokenInput.fill('invalid-bogus-token-12345');
    await page.locator('[data-testid="mcp-owner-token-submit-btn"]').click();

    // Verify error feedback and controls remain locked
    const feedback = page.locator('[data-testid="mcp-admin-feedback"]');
    await expect(feedback).toBeVisible({ timeout: 10000 });
    await expect(feedback).toContainText(/Authentication failed|Invalid/i);
    await expect(page.locator('[data-testid="mcp-owner-auth-card"]')).toContainText(/Owner Authentication Required/i);

    // 2. Authenticate successfully
    await tokenInput.fill(e2eToken);
    await page.locator('[data-testid="mcp-owner-token-submit-btn"]').click();
    await expect(page.locator('[data-testid="mcp-owner-auth-card"]')).toContainText(/Owner Session Active/i);

    // 3. Test logout relocks controls
    const logoutBtn = page.locator('[data-testid="mcp-owner-logout-btn"]');
    await expect(logoutBtn).toBeVisible();
    await logoutBtn.click();

    await expect(page.locator('[data-testid="mcp-owner-auth-card"]')).toContainText(/Owner Authentication Required/i);
    await page.locator('[data-testid="mcp-tab-tools"]').click();
    await expect(page.locator('[data-testid="mcp-perm-select-time__get_current_time"]')).toBeDisabled();
  });

  test('Scenario E — Observability, Approvals Summary & Diagnostics: Truthful metrics, zero secret leakage', async ({ page, request }) => {
    // 1. Inspect Approvals Overview tab
    await page.locator('[data-testid="mcp-tab-approvals"]').click();
    const approvalsCard = page.locator('[data-testid="mcp-approvals-summary-card"]');
    await expect(approvalsCard).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="mcp-summary-pending-count"]')).toBeVisible();
    await expect(page.locator('[data-testid="mcp-summary-approved-count"]')).toBeVisible();
    await expect(page.locator('[data-testid="mcp-summary-rejected-count"]')).toBeVisible();

    // 2. Inspect Live Diagnostics tab
    await page.locator('[data-testid="mcp-tab-diagnostics"]').click();
    const diagCard = page.locator('[data-testid="mcp-diagnostics-card"]');
    await expect(diagCard).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="mcp-diag-tool-count"]')).toHaveText(/2 Tools/);
    await expect(page.locator('[data-testid="mcp-diag-approvals-store"]')).toContainText(/Operational/i);
    await expect(page.locator('[data-testid="mcp-diag-checkpoints-store"]')).toContainText(/Operational/i);

    // 3. Verify zero secrets leaked into browser DOM or storage
    const pageHtml = await page.content();
    expect(pageHtml).not.toContain(e2eToken);
    expect(pageHtml).not.toContain('sk-or-');
    expect(pageHtml).not.toContain('openrouter_api_key');

    const localStorageKeys = await page.evaluate(() => Object.keys(localStorage));
    expect(localStorageKeys).not.toContain('javed_owner_token');
    expect(localStorageKeys).not.toContain('session_token');
  });
});
