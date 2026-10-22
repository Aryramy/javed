import { useContext } from 'react'
import { BackendContext, type BackendContextValue } from './backend-context'

export const useBackend = (): BackendContextValue => {
  const context = useContext(BackendContext)
  if (!context) {
    throw new Error('useBackend must be used within a BackendProvider')
  }
  return context
}
