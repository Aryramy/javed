import { test, expect } from '@playwright/test'

test.describe('BRICK-002: Real FastAPI Backend & Frontend Integration', () => {
  test('01. Global Header and Chat View display live backend connectivity', async ({ page }) => {
    await page.goto('/')

    // Wait for connection indicator in the header
    const statusBadge = page.locator('[data-testid="backend-status-badge"]')
    await expect(statusBadge).toBeVisible({ timeout: 10000 })
    await expect(statusBadge).toContainText('Connected', { timeout: 10000 })

    // Check ChatView banner shows backend live connection info
    const chatBanner = page.locator('text=BACKEND CONNECTED:')
    await expect(chatBanner).toBeVisible({ timeout: 5000 })
  })

  test('02. Developer Connectivity View shows real REST, WebSocket, and subsystem states', async ({ page }) => {
    await page.goto('/dev/connectivity')

    // Verify Title & Primary Metric Cards
    await expect(page.locator('text=Subsystem Connectivity Monitor')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('REST Gateway', { exact: true })).toBeVisible()
    await expect(page.locator('text=WebSocket Status')).toBeVisible()

    // Verify Real Channels
    await expect(page.locator('text=FastAPI REST Gateway')).toBeVisible()
    await expect(page.locator('text=WebSocket Transport Channel')).toBeVisible()
    await expect(page.locator('text=Server-Sent Events (SSE) Stream')).toBeVisible()

    // Verify honest future stage marking
    await expect(page.locator('text=OpenRouter Model Gateway')).toBeVisible()
    await expect(page.locator('text=Scheduled: BRICK-003')).toBeVisible()
  })

  test('03. Developer Diagnostics View executes live REST and WebSocket probes', async ({ page }) => {
    await page.goto('/dev/diagnostics')

    const terminalBox = page.locator('pre')
    await expect(terminalBox).toBeVisible({ timeout: 10000 })

    // Click "Measure Ping" button
    const pingButton = page.locator('button:has-text("Measure Ping")')
    await pingButton.click()
    await expect(terminalBox).toContainText('"_status": "ACKNOWLEDGED"', { timeout: 5000 })
    await expect(terminalBox).toContainText('measured_rtt_ms')

    // Click "Check System Status" button
    const statusButton = page.locator('button:has-text("Check System Status")')
    await statusButton.click()
    await expect(terminalBox).toContainText('"app_name": "Javed — New JARVIS"', { timeout: 5000 })
    await expect(terminalBox).toContainText('"backend_version": "0.1.0"')

    // Click "Readiness Probe" button
    const readyButton = page.locator('button:has-text("Readiness Probe")')
    await readyButton.click()
    await expect(terminalBox).toContainText('"status": "ready"', { timeout: 5000 })
  })

  test('04. Developer Logs View displays bounded live transport event stream', async ({ page }) => {
    await page.goto('/dev/logs')

    // Verify event stream header
    await expect(page.locator('text=Transport Event Stream & Audit Log')).toBeVisible({ timeout: 10000 })

    // Verify retention counter and transport descriptor
    await expect(page.locator('text=ACTIVE TRANSPORT:')).toBeVisible()
    await expect(page.locator('text=RETENTION:')).toBeVisible()

    // Verify presence of real transport events
    await expect(page.locator('span:has-text("WS_CONNECTED"), span:has-text("HEARTBEAT_ACK"), span:has-text("PING_ACK")').first()).toBeVisible({ timeout: 5000 })
  })

  test('05. WebSocket manual disconnect and reconnect controls update UI state', async ({ page }) => {
    await page.goto('/dev/diagnostics')

    const statusBadge = page.locator('[data-testid="backend-status-badge"]')
    await expect(statusBadge).toContainText('Connected', { timeout: 10000 })

    // Disconnect socket
    const disconnectBtn = page.locator('button:has-text("Disconnect Socket")')
    await disconnectBtn.click()

    await expect(statusBadge).toContainText('Disconnected', { timeout: 5000 })

    // Reconnect socket
    const reconnectBtn = page.locator('button:has-text("Reconnect Socket")')
    await reconnectBtn.click()

    await expect(statusBadge).toContainText('Connected', { timeout: 5000 })
  })
})
