import { useNavigate } from 'react-router-dom'
import { Bot, Code2, Menu, User, X } from 'lucide-react'
import { useMode } from '@/context'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { cn } from '@/lib/utils'

interface HeaderProps {
  mobileMenuOpen: boolean
  setMobileMenuOpen: (open: boolean) => void
}

export const Header: React.FC<HeaderProps> = ({ mobileMenuOpen, setMobileMenuOpen }) => {
  const { mode, setMode } = useMode()
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

      {/* Right Tools (Theme + Status Indicator) */}
      <div className="flex items-center gap-3">
        <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span>Shell Ready</span>
        </div>

        <ThemeToggle />
      </div>
    </header>
  )
}
