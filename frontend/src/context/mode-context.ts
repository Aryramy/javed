import { createContext } from 'react'

export type AppMode = 'user' | 'dev'

export interface ModeContextType {
  mode: AppMode
  setMode: (mode: AppMode) => void
  toggleMode: () => void
}

export const ModeContext = createContext<ModeContextType | undefined>(undefined)
