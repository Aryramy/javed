import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme, type Theme } from '@/context'
import { cn } from '@/lib/utils'

export const ThemeToggle: React.FC = () => {
  const { theme, setTheme } = useTheme()

  const options: { value: Theme; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { value: 'light', label: 'Light Theme', icon: Sun },
    { value: 'dark', label: 'Dark Theme', icon: Moon },
    { value: 'system', label: 'System Theme', icon: Monitor },
  ]

  return (
    <div
      role="radiogroup"
      aria-label="Theme selection"
      className="inline-flex items-center p-1 rounded-lg bg-secondary/80 border border-border"
    >
      {options.map((option) => {
        const Icon = option.icon
        const isActive = theme === option.value
        return (
          <button
            key={option.value}
            role="radio"
            aria-checked={isActive}
            aria-label={option.label}
            title={option.label}
            onClick={() => setTheme(option.value)}
            className={cn(
              'p-1.5 rounded-md text-xs font-medium transition-all duration-150 flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary/40',
              isActive
                ? 'bg-background text-foreground shadow-sm shadow-black/10'
                : 'text-muted-foreground hover:text-foreground hover:bg-background/40'
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            <span className="sr-only sm:not-sr-only text-[11px] font-medium capitalize">
              {option.value}
            </span>
          </button>
        )
      })}
    </div>
  )
}
