import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider, useTheme } from '@/context'
import { ThemeToggle } from '@/components/layout/ThemeToggle'

function ThemeConsumer() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="current-theme">{theme}</span>
      <span data-testid="resolved-theme">{resolvedTheme}</span>
      <button onClick={() => setTheme('light')}>Set Light</button>
      <button onClick={() => setTheme('dark')}>Set Dark</button>
      <button onClick={() => setTheme('system')}>Set System</button>
    </div>
  )
}

describe('Theme Management', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('defaults to system theme when no localStorage value exists', () => {
    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    expect(screen.getByTestId('current-theme')).toHaveTextContent('system')
  })

  it('persists selected theme to localStorage and updates DOM class', async () => {
    const user = userEvent.setup()

    render(
      <ThemeProvider>
        <ThemeConsumer />
      </ThemeProvider>
    )

    await user.click(screen.getByText('Set Dark'))

    expect(localStorage.getItem('javed-theme')).toBe('dark')
    expect(screen.getByTestId('current-theme')).toHaveTextContent('dark')
    expect(screen.getByTestId('resolved-theme')).toHaveTextContent('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    await user.click(screen.getByText('Set Light'))

    expect(localStorage.getItem('javed-theme')).toBe('light')
    expect(screen.getByTestId('current-theme')).toHaveTextContent('light')
    expect(screen.getByTestId('resolved-theme')).toHaveTextContent('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('ThemeToggle component renders radio options and allows switching', async () => {
    const user = userEvent.setup()

    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    )

    const lightRadio = screen.getByRole('radio', { name: /light theme/i })
    const darkRadio = screen.getByRole('radio', { name: /dark theme/i })
    const systemRadio = screen.getByRole('radio', { name: /system theme/i })

    expect(lightRadio).toBeInTheDocument()
    expect(darkRadio).toBeInTheDocument()
    expect(systemRadio).toBeInTheDocument()

    await user.click(darkRadio)
    expect(darkRadio).toHaveAttribute('aria-checked', 'true')
    expect(lightRadio).toHaveAttribute('aria-checked', 'false')
    expect(localStorage.getItem('javed-theme')).toBe('dark')
  })
})
