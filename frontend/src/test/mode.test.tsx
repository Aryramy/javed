import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModeProvider, useMode } from '@/context'

function ModeConsumer() {
  const { mode, setMode, toggleMode } = useMode()
  return (
    <div>
      <span data-testid="current-mode">{mode}</span>
      <button onClick={() => setMode('dev')}>Set Dev</button>
      <button onClick={() => setMode('user')}>Set User</button>
      <button onClick={toggleMode}>Toggle Mode</button>
    </div>
  )
}

describe('Mode Management (User vs Developer Mode)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaults to user mode', () => {
    render(
      <ModeProvider>
        <ModeConsumer />
      </ModeProvider>
    )

    expect(screen.getByTestId('current-mode')).toHaveTextContent('user')
  })

  it('switches to dev mode and saves to localStorage', async () => {
    const user = userEvent.setup()

    render(
      <ModeProvider>
        <ModeConsumer />
      </ModeProvider>
    )

    await user.click(screen.getByText('Set Dev'))
    expect(screen.getByTestId('current-mode')).toHaveTextContent('dev')
    expect(localStorage.getItem('javed-mode')).toBe('dev')

    await user.click(screen.getByText('Toggle Mode'))
    expect(screen.getByTestId('current-mode')).toHaveTextContent('user')
    expect(localStorage.getItem('javed-mode')).toBe('user')
  })
})
