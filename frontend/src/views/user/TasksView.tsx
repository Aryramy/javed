import { CheckSquare } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

export const TasksView = () => {
  return (
    <EmptyState
      icon={CheckSquare}
      title="Autonomous Task Execution & HITL Approval"
      description="Multi-step task decomposition and sandboxed tool execution with human-in-the-loop approval modals for consequential actions will be activated in Stage 3."
      scheduledBrick="BRICK-005: Tool Registry, Validation & Permissions"
      stage="Stage 3: Agent Orchestration & Tools"
      prerequisites={[
        'BRICK-004: Deep Agents & LangGraph Runtime with State Checkpointing',
        'BRICK-005: 4-Tier Security Matrix & Interactive HITL Confirmation Modal',
      ]}
      architectureNote="Architecture Reference: Pure Gating Node pattern invoking interrupt() and Command(resume=...) per ADR-003."
    />
  )
}
