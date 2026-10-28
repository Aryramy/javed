import React from 'react'
import { BrowserPreviewPanel } from '@/components/browser/BrowserPreviewPanel'

export const BrowserView: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col p-4 md:p-6 max-w-7xl mx-auto w-full space-y-4">
      <div>
        <h1 className="text-xl font-bold text-zinc-100">
          Browser Automation Console
        </h1>
        <p className="text-xs text-zinc-400 mt-1">
          Deterministic Playwright execution with real-time viewport streaming,
          ephemeral context isolation, and security guardrails.
        </p>
      </div>

      <div className="flex-1">
        <BrowserPreviewPanel />
      </div>
    </div>
  )
}
