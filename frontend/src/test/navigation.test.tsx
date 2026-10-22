import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { App } from '@/App'

describe('App Navigation and Route Rendering', () => {
  beforeEach(() => {
    localStorage.clear()
    window.history.pushState({}, 'Test', '/')
  })

  it('renders the default chat view with honest empty state', () => {
    render(<App />)

    expect(screen.getByText('Conversational AI Gateway')).toBeInTheDocument()
    expect(
      screen.getByText(/Interactive streaming chat powered by Deep Agents/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/BRICK-003: OpenRouter Integration & Streaming Chat/i)).toBeInTheDocument()
  })

  it('navigates to tasks view when tasks nav link is clicked', async () => {
    const user = userEvent.setup()
    render(<App />)

    const tasksLink = screen.getByRole('link', { name: /tasks/i })
    await user.click(tasksLink)

    expect(
      screen.getByText('Autonomous Task Execution & HITL Approval')
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Multi-step task decomposition and sandboxed tool execution/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/BRICK-005: Tool Registry, Validation & Permissions/i)
    ).toBeInTheDocument()
  })

  it('switches to Developer Mode and renders developer views', async () => {
    const user = userEvent.setup()
    render(<App />)

    const devModeButton = screen.getByRole('button', { name: /developer mode/i })
    await user.click(devModeButton)

    // Should navigate to /dev/info and show Application Metadata
    expect(screen.getByText(/Application Architecture & System Information/i)).toBeInTheDocument()
    expect(screen.getByText('Verified System Properties & Runtime Baseline')).toBeInTheDocument()
    expect(screen.getByText(/BRICK-001: Reproducible Foundation & Real React UI Shell/i)).toBeInTheDocument()
  })

  it('displays accurate runtime status in Developer Mode', async () => {
    const user = userEvent.setup()
    render(<App />)

    // Switch to dev mode
    const devModeButton = screen.getByRole('button', { name: /developer mode/i })
    await user.click(devModeButton)

    // Click Runtime Status link
    const runtimeLink = screen.getByRole('link', { name: /runtime status/i })
    await user.click(runtimeLink)

    expect(screen.getByText(/Frontend Runtime & Environment Status/i)).toBeInTheDocument()
    expect(screen.getByText(/Viewport Resolution/i)).toBeInTheDocument()
    expect(screen.getByText(/Active Pathname/i)).toBeInTheDocument()
    expect(screen.getByText(/Local Preferences/i)).toBeInTheDocument()
  })
})
