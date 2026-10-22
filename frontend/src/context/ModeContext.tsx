import React, { useState } from 'react'
import { ModeContext, type AppMode } from './mode-context'

const MODE_STORAGE_KEY = 'javed-mode'

export function ModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<AppMode>(() => {
    try {
      const saved = localStorage.getItem(MODE_STORAGE_KEY)
      if (saved === 'user' || saved === 'dev') {
        return saved
      }
    } catch {
      // ignore storage access errors
    }
    return 'user'
  })

  const setMode = (newMode: AppMode) => {
    setModeState(newMode)
    try {
      localStorage.setItem(MODE_STORAGE_KEY, newMode)
    } catch {
      // ignore storage errors
    }
  }

  const toggleMode = () => {
    setMode(mode === 'user' ? 'dev' : 'user')
  }

  return (
    <ModeContext.Provider value={{ mode, setMode, toggleMode }}>
      {children}
    </ModeContext.Provider>
  )
}
