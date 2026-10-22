import { Compass } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

export const BrowserView = () => {
  return (
    <EmptyState
      icon={Compass}
      title="Dual-Engine Browser Control Center"
      description="Live browser automation combining deterministic Playwright automation for known pages and vision-guided Browser Use for exploratory web navigation."
      scheduledBrick="BRICK-006: Deterministic Playwright Execution"
      stage="Stage 4: Browser Automation & Web Intelligence"
      prerequisites={[
        'BRICK-006: Playwright Python Chromium Runner & Live Viewport Streaming',
        'BRICK-008: Intelligent Dynamic Exploration with Browser Use',
      ]}
      architectureNote="Architecture Reference: Section 3.6 of docs/ARCHITECTURE.md. Ephemeral context isolation and download quarantine."
    />
  )
}
