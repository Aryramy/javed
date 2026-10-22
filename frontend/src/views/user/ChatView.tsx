import { MessageSquare } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

export const ChatView = () => {
  return (
    <EmptyState
      icon={MessageSquare}
      title="Conversational AI Gateway"
      description="Interactive streaming chat powered by Deep Agents and LangGraph will connect directly to OpenRouter once the backend transport layer is established."
      scheduledBrick="BRICK-003: OpenRouter Integration & Streaming Chat"
      stage="Stage 2: Intelligence & Models"
      prerequisites={[
        'BRICK-001: Reproducible Foundation & Real React UI Shell (ACTIVE)',
        'BRICK-002: FastAPI Integration, WebSockets & SSE Gateway (NEXT)',
        'BRICK-003: OpenRouter Adapter & assistant-ui Thread Integration',
      ]}
      architectureNote="Architecture Reference: Section 3.1 & 3.4 of docs/ARCHITECTURE.md. Chat UI will pair assistant-ui with FastAPI WebSockets."
    />
  )
}
