import { Brain } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

export const MemoryView = () => {
  return (
    <EmptyState
      icon={Brain}
      title="Long-Term User Memory & Semantic Knowledge Store"
      description="Persistent storage of user preferences, verified facts, and conversation summaries with transparent inspection, inline editing, and deletion."
      scheduledBrick="BRICK-009: Persistent Memory & Knowledge Retrieval (RAG)"
      stage="Stage 5: Memory, Tools & Execution"
      prerequisites={[
        'BRICK-009: SQLite Persistent Fact Store with Provenance Metadata',
        'BRICK-009: sqlite-vec Semantic Vector Indexing for Long-Term RAG',
      ]}
      architectureNote="Architecture Reference: ADR-004 & Section 3.8 of docs/ARCHITECTURE.md. Zero third-party cloud vector DB lock-in."
    />
  )
}
