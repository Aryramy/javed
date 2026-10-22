import { NavLink } from 'react-router-dom'
import {
  Activity,
  Brain,
  CheckCircle2,
  CheckSquare,
  Compass,
  FileText,
  Gauge,
  Info,
  MessageSquare,
  Radio,
  Settings,
  ShieldCheck,
  Terminal,
} from 'lucide-react'
import { useBackend, useMode } from '@/context'
import { cn } from '@/lib/utils'

interface SidebarProps {
  mobileOpen: boolean
  setMobileOpen: (open: boolean) => void
}

export const Sidebar = ({ mobileOpen, setMobileOpen }: SidebarProps) => {
  const { mode } = useMode()
  const { status, latencyMs } = useBackend()

  const userNavItems = [
    { name: 'Chat', path: '/chat', icon: MessageSquare, badge: 'BRICK-003' },
    { name: 'Tasks', path: '/tasks', icon: CheckSquare, badge: 'BRICK-005' },
    { name: 'Browser', path: '/browser', icon: Compass, badge: 'BRICK-006' },
    { name: 'Documents', path: '/documents', icon: FileText, badge: 'BRICK-007' },
    { name: 'Memory', path: '/memory', icon: Brain, badge: 'BRICK-009' },
    { name: 'Settings', path: '/settings', icon: Settings },
  ]

  const devNavItems = [
    { name: 'App Info', path: '/dev/info', icon: Info, active: true },
    { name: 'Runtime Status', path: '/dev/runtime', icon: Activity, active: true },
    {
      name: 'Connectivity',
      path: '/dev/connectivity',
      icon: Radio,
      badge: status === 'connected' ? 'Connected' : 'Disconnected',
    },
    { name: 'Diagnostics', path: '/dev/diagnostics', icon: ShieldCheck, active: true },
    { name: 'Logs & Events', path: '/dev/logs', icon: Terminal, active: true },
    { name: 'Telemetry', path: '/dev/telemetry', icon: Gauge, active: true },
    { name: 'Verification', path: '/dev/verification', icon: CheckCircle2, active: true },
  ]

  const navItems = mode === 'user' ? userNavItems : devNavItems

  const sidebarContent = (
    <div className="flex flex-col h-full bg-card border-r border-border w-64 select-none">
      {/* Mode Scope Header */}
      <div className="p-4 border-b border-border/70">
        <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          {mode === 'user' ? 'Personal Assistant Views' : 'Diagnostic Console Views'}
        </div>
        <div className="text-xs font-medium text-foreground flex items-center justify-between">
          <span>{mode === 'user' ? 'End-User Experience' : 'Internal Observability'}</span>
          <span className={cn(
            'px-1.5 py-0.5 rounded text-[10px] font-semibold font-mono',
            mode === 'user' ? 'bg-secondary text-muted-foreground' : 'bg-primary/20 text-primary'
          )}>
            {mode.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-colors group',
                  isActive
                    ? 'bg-primary text-primary-foreground font-semibold shadow-sm shadow-primary/20'
                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                )
              }
            >
              <div className="flex items-center gap-2.5">
                <Icon className="w-4 h-4 shrink-0 transition-transform group-hover:scale-105" />
                <span>{item.name}</span>
              </div>
              {item.badge && (
                <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-black/20 text-muted-foreground dark:text-muted-foreground border border-border/50">
                  {item.badge}
                </span>
              )}
            </NavLink>
          )
        })}
      </nav>

      {/* Foundation Integrity Footer */}
      <div className="p-4 border-t border-border/70 bg-secondary/30">
        <div className="flex items-center gap-2 mb-1.5">
          <span
            className={cn(
              'w-2 h-2 rounded-full',
              status === 'connected'
                ? 'bg-emerald-500 animate-pulse'
                : status === 'connecting'
                ? 'bg-blue-500 animate-ping'
                : status === 'reconnecting'
                ? 'bg-amber-500 animate-ping'
                : 'bg-rose-500'
            )}
          />
          <span className="text-[11px] font-semibold text-foreground">
            {status === 'connected'
              ? 'Backend Connected'
              : status === 'connecting'
              ? 'Backend Connecting...'
              : status === 'reconnecting'
              ? 'Backend Reconnecting...'
              : 'Backend Disconnected'}
          </span>
        </div>
        <p className="text-[10px] text-muted-foreground leading-tight" data-testid="sidebar-connection-status">
          {status === 'connected'
            ? `FastAPI gateway operational${latencyMs !== null ? ` (${latencyMs}ms)` : ''}. Mocked data strictly prohibited.`
            : 'Backend FastAPI gateway disconnected. Mocked data strictly prohibited.'}
        </p>
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:block shrink-0 h-[calc(100vh-4rem)] sticky top-16 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-50 lg:hidden bg-black/60 backdrop-blur-sm"
          onClick={() => setMobileOpen(false)}
        >
          <div
            className="fixed inset-y-0 left-0 w-64 bg-card shadow-2xl z-50 flex flex-col animate-slide-in-left"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  )
}
