import { useNavigate } from 'react-router-dom'
import { Bot, Code2, Menu, User, X } from 'lucide-react'
import { useBackend, useMode } from '@/context'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { cn } from '@/lib/utils'

interface HeaderProps {
  mobileMenuOpen: boolean
  setMobileMenuOpen: (open: boolean) => void
}

export const Header: React.FC<HeaderProps> = ({ mobileMenuOpen, setMobileMenuOpen }) => {
  const { mode, setMode } = useMode()
  const { status, latencyMs, reconnectAttempts } = useBackend()
  const navigate = useNavigate()

  const handleModeSwitch = (newMode: 'user' | 'dev') => {
    if (mode !== newMode) {
      setMode(newMode)
      if (newMode === 'dev') {
        navigate('/dev/info')
      } else {
        navigate('/chat')
      }
    }
  }

  return (
    <header className="sticky top-0 z-40 w-full h-16 border-b border-border bg-card/80 backdrop-blur-md px-4 sm:px-6 flex items-center justify-between">
      {/* Brand & Mobile Hamburger */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label={mobileMenuOpen ? 'Close navigation' : 'Open navigation'}
          className="lg:hidden p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-primary/40"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>

        <div className="flex items-center gap-2.5 cursor-pointer" onClick={() => navigate(mode === 'user' ? '/chat' : '/dev/info')}>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-blue-700 flex items-center justify-center text-white shadow-md shadow-primary/20">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold tracking-tight text-base text-foreground">
                JARVIS
              </span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold">
                Javed
              </span>
            </div>
            <p className="text-[10px] text-muted-foreground font-medium hidden sm:block">
              Stage 1 • Foundation & UI Shell
            </p>
          </div>
        </div>
      </div>

      {/* Mode Switcher Pill */}
      <div className="flex items-center bg-secondary/80 p-1 rounded-xl border border-border shadow-inner">
        <button
          onClick={() => handleModeSwitch('user')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150',
            mode === 'user'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          )}
          aria-pressed={mode === 'user'}
        >
          <User className="w-3.5 h-3.5" />
          <span>User Mode</span>
        </button>

        <button
          onClick={() => handleModeSwitch('dev')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150',
            mode === 'dev'
              ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20 font-semibold'
              : 'text-muted-foreground hover:text-foreground'
          )}
          aria-pressed={mode === 'dev'}
        >
          <Code2 className="w-3.5 h-3.5" />
          <span>Developer Mode</span>
        </button>
      </div>

      {/* Right Tools (Theme + Real Backend Connection Indicator) */}
      <div className="flex items-center gap-3">
        <button
          data-testid="backend-status-badge"
          onClick={() => navigate('/dev/connectivity')}
          title="Click to view connectivity diagnostics"
          aria-label={`Backend connection status: ${status}`}
          className={cn(
            'flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-all duration-150',
            status === 'connected' && (latencyMs !== null && latencyMs > 100)
              ? 'bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400'
              : status === 'connected'
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400'
              : status === 'connecting'
              ? 'bg-blue-500/10 border-blue-500/20 text-blue-600 dark:text-blue-400'
              : status === 'reconnecting'
              ? 'bg-amber-500/10 border-amber-500/20 text-amber-600 dark:text-amber-400'
              : 'bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400'
          )}
        >
          {status === 'connected' ? (
            <>
              <span
                className={cn(
                  'w-1.5 h-1.5 rounded-full',
                  latencyMs !== null && latencyMs > 100 ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500 animate-pulse'
                )}
              />
              <span className="font-mono">
                {latencyMs !== null && latencyMs > 100
                  ? `Degraded • ${latencyMs}ms`
                  : latencyMs !== null
                  ? `Connected • ${latencyMs}ms`
                  : 'Connected'}
              </span>
            </>
          ) : status === 'connecting' ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />
              <span>Connecting...</span>
            </>
          ) : status === 'reconnecting' ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-ping" />
              <span>Reconnecting ({reconnectAttempts})...</span>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
              <span>Disconnected</span>
            </>
          )}
        </button>

        <ThemeToggle />
      </div>
    </header>
  )
}
