import { useState } from 'react'
import {
  CheckCircle,
  Database,
  Key,
  Monitor,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sun,
  User,
} from 'lucide-react'
import { useTheme, useMode, type Theme } from '@/context'
import { cn } from '@/lib/utils'

export const SettingsView: React.FC = () => {
  const { theme, setTheme } = useTheme()
  const { mode, setMode } = useMode()
  const [resetSuccess, setResetSuccess] = useState(false)

  const handleResetPreferences = () => {
    try {
      localStorage.removeItem('javed-theme')
      localStorage.removeItem('javed-mode')
      setTheme('dark')
      setMode('user')
      setResetSuccess(true)
      setTimeout(() => setResetSuccess(false), 3000)
    } catch {
      // ignore storage errors
    }
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Application Settings
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Manage local appearance, interface perspective, and review verified system security posture.
        </p>
      </div>

      {/* Theme Settings Card */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Sun className="w-4 h-4 text-primary" />
          <span>Appearance & Color Scheme</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Select your preferred visual style. Settings persist across browser refreshes via local storage.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { id: 'light' as Theme, label: 'Light Theme', desc: 'Clean, high-contrast daytime palette', icon: Sun },
            { id: 'dark' as Theme, label: 'Dark Theme', desc: 'Deep Charcoal / Slate default palette', icon: Moon },
            { id: 'system' as Theme, label: 'System Default', desc: 'Syncs with your operating system preference', icon: Monitor },
          ].map((item) => {
            const Icon = item.icon
            const isSelected = theme === item.id
            return (
              <button
                key={item.id}
                onClick={() => setTheme(item.id)}
                className={cn(
                  'flex flex-col items-start p-3.5 rounded-lg border text-left transition-all',
                  isSelected
                    ? 'border-primary bg-primary/5 text-foreground ring-1 ring-primary/40'
                    : 'border-border bg-secondary/30 text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
                )}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <Icon className={cn('w-4 h-4', isSelected ? 'text-primary' : 'text-muted-foreground')} />
                  <span className="text-xs font-semibold text-foreground">{item.label}</span>
                </div>
                <span className="text-[11px] text-muted-foreground leading-normal">{item.desc}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Perspective / Mode Settings Card */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <User className="w-4 h-4 text-primary" />
          <span>Interface Perspective</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Switch between personal assistant interaction and high-density diagnostic observability.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            onClick={() => setMode('user')}
            className={cn(
              'flex flex-col items-start p-3.5 rounded-lg border text-left transition-all',
              mode === 'user'
                ? 'border-primary bg-primary/5 text-foreground ring-1 ring-primary/40'
                : 'border-border bg-secondary/30 text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
            )}
          >
            <span className="text-xs font-semibold text-foreground mb-1">User Mode</span>
            <span className="text-[11px] text-muted-foreground">
              Conversational stream, interactive tool results, document viewers, and live browser previews.
            </span>
          </button>

          <button
            onClick={() => setMode('dev')}
            className={cn(
              'flex flex-col items-start p-3.5 rounded-lg border text-left transition-all',
              mode === 'dev'
                ? 'border-primary bg-primary/5 text-foreground ring-1 ring-primary/40'
                : 'border-border bg-secondary/30 text-muted-foreground hover:bg-secondary/60 hover:text-foreground'
            )}
          >
            <span className="text-xs font-semibold text-foreground mb-1">Developer Mode</span>
            <span className="text-[11px] text-muted-foreground">
              LangGraph state inspector, real-time token/cost meters, tool schemas, and raw event timelines.
            </span>
          </button>
        </div>
      </div>

      {/* Gateway & Secret Isolation Policy */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Key className="w-4 h-4 text-primary" />
          <span>API Gateway & Secret Security</span>
        </div>
        <div className="space-y-2 text-xs text-muted-foreground">
          <div className="flex items-center justify-between p-2.5 rounded-lg bg-secondary/50 border border-border font-mono text-[11px]">
            <span className="text-muted-foreground">Documented Gateway URL:</span>
            <span className="text-primary font-semibold">https://openrouter.ai/api/v1</span>
          </div>
          <div className="flex items-center gap-2 p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="w-4 h-4 shrink-0" />
            <span>
              <strong>Zero Secret Leakage Guarantee:</strong> API keys reside exclusively in the server-side host environment (<code>.env</code>). They are never transmitted to or cached within client-side code or browser storage.
            </span>
          </div>
        </div>
      </div>

      {/* Local Storage & Cache Controls */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground mb-1">
            <Database className="w-4 h-4 text-primary" />
            <span>Local UI Preferences Storage</span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Clear locally stored theme and mode preferences back to system defaults.
          </p>
        </div>
        <button
          onClick={handleResetPreferences}
          className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary flex items-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-primary/40 transition-colors"
        >
          {resetSuccess ? (
            <>
              <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
              <span className="text-emerald-500 font-semibold">Reset Done</span>
            </>
          ) : (
            <>
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Reset Defaults</span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
