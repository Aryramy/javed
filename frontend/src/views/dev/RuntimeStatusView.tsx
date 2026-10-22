import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Activity, Database, Laptop, Wifi } from 'lucide-react'
import { useTheme, useMode, useBackend } from '@/context'

export const RuntimeStatusView: React.FC = () => {
  const location = useLocation()
  const { theme, resolvedTheme } = useTheme()
  const { mode } = useMode()
  const { status, latencyMs, systemStatus } = useBackend()

  const [windowSize, setWindowSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  })

  const [isOnline, setIsOnline] = useState(navigator.onLine)
  const [storageCount] = useState(() => {
    try {
      return localStorage.length
    } catch {
      return 0
    }
  })

  useEffect(() => {
    const handleResize = () => {
      setWindowSize({
        width: window.innerWidth,
        height: window.innerHeight,
      })
    }

    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)

    window.addEventListener('resize', handleResize)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
          <Activity className="w-4 h-4" />
          <span>Live Runtime Telemetry</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Frontend Runtime & Environment Status
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Real-time metrics gathered directly from the client execution context.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Network Status */}
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>Browser Network</span>
            <Wifi className="w-4 h-4 text-primary" />
          </div>
          <div className="text-lg font-bold text-foreground flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-destructive'}`} />
            <span>{isOnline ? 'ONLINE' : 'OFFLINE'}</span>
          </div>
          <span className="text-[10px] text-muted-foreground mt-1 block">navigator.onLine</span>
        </div>

        {/* Viewport Dimensions */}
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>Viewport Resolution</span>
            <Laptop className="w-4 h-4 text-primary" />
          </div>
          <div className="text-lg font-bold font-mono text-foreground">
            {windowSize.width} × {windowSize.height}
          </div>
          <span className="text-[10px] text-muted-foreground mt-1 block">DPR: {window.devicePixelRatio}x</span>
        </div>

        {/* Active Route */}
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>Active Pathname</span>
            <Activity className="w-4 h-4 text-primary" />
          </div>
          <div className="text-sm font-bold font-mono text-primary truncate">
            {location.pathname}
          </div>
          <span className="text-[10px] text-muted-foreground mt-1 block">Router Location</span>
        </div>

        {/* Local Storage Items */}
        <div className="p-4 rounded-xl border border-border bg-card shadow-sm">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>Local Preferences</span>
            <Database className="w-4 h-4 text-primary" />
          </div>
          <div className="text-lg font-bold text-foreground">
            {storageCount} Key{storageCount === 1 ? '' : 's'}
          </div>
          <span className="text-[10px] text-muted-foreground mt-1 block">localStorage footprint</span>
        </div>
      </div>

      {/* Detailed Client Environment Table */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
        <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">
          Client Environment Telemetry
        </h3>
        <div className="divide-y divide-border/60 text-xs">
          <div className="py-2.5 flex justify-between">
            <span className="text-muted-foreground">Operating Mode</span>
            <span className="font-mono font-semibold uppercase text-primary">{mode}</span>
          </div>
          <div className="py-2.5 flex justify-between">
            <span className="text-muted-foreground">Configured Theme Preference</span>
            <span className="font-mono font-semibold capitalize text-foreground">{theme}</span>
          </div>
          <div className="py-2.5 flex justify-between">
            <span className="text-muted-foreground">Resolved DOM Theme</span>
            <span className="font-mono font-semibold capitalize text-foreground">{resolvedTheme}</span>
          </div>
          <div className="py-2.5 flex justify-between">
            <span className="text-muted-foreground">Backend Service Link</span>
            <span className="font-mono font-semibold uppercase text-foreground">
              {status === 'connected' ? (
                <span className="text-emerald-500">Connected ({latencyMs ?? 0}ms)</span>
              ) : (
                <span className="text-rose-500">{status}</span>
              )}
            </span>
          </div>
          {systemStatus && (
            <div className="py-2.5 flex justify-between">
              <span className="text-muted-foreground">Backend Process Uptime</span>
              <span className="font-mono text-foreground">{systemStatus.uptime_seconds}s</span>
            </div>
          )}
          <div className="py-2.5 flex justify-between">
            <span className="text-muted-foreground">Browser User Agent</span>
            <span className="font-mono text-foreground text-[11px] truncate max-w-md">{navigator.userAgent}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
