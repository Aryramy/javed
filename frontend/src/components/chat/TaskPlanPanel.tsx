import React, { useState } from 'react';
import {
  CheckCircle2,
  Circle,
  ListTodo,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';
import type { AgentTodoItem } from '../../types/agent';
import { cn } from '../../lib/utils';

interface TaskPlanPanelProps {
  todos: AgentTodoItem[];
  activeRunId?: string;
  isStreaming?: boolean;
}

export const TaskPlanPanel: React.FC<TaskPlanPanelProps> = ({
  todos,
  activeRunId,
  isStreaming = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (!todos || todos.length === 0) {
    return null;
  }

  const completedCount = todos.filter((t) => t.status === 'completed').length;
  const inProgressCount = todos.filter((t) => t.status === 'in_progress').length;
  const totalCount = todos.length;

  return (
    <div
      data-testid="task-plan-panel"
      className="mb-4 rounded-xl border border-blue-500/30 bg-blue-950/20 shadow-lg backdrop-blur-sm transition-all duration-200 overflow-hidden"
    >
      {/* Header bar */}
      <div
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="flex items-center justify-between px-4 py-2.5 bg-blue-950/40 border-b border-blue-500/20 cursor-pointer select-none hover:bg-blue-900/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <ListTodo className="w-4 h-4 text-blue-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-blue-300">
            Structured Agent Plan
          </span>
          {activeRunId && (
            <span className="text-[10px] font-mono text-zinc-500 px-1.5 py-0.5 rounded bg-zinc-900/60">
              {activeRunId}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          {isStreaming && inProgressCount > 0 && (
            <span className="flex items-center gap-1 text-[11px] text-blue-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span>Executing</span>
            </span>
          )}
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30">
            {completedCount}/{totalCount} Completed
          </span>
          <button
            type="button"
            className="text-zinc-400 hover:text-zinc-200 transition-colors"
            aria-label={isCollapsed ? 'Expand plan' : 'Collapse plan'}
          >
            {isCollapsed ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronUp className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>

      {/* Todo items list */}
      {!isCollapsed && (
        <div className="p-3 space-y-2">
          {todos.map((todo, idx) => {
            const isCompleted = todo.status === 'completed';
            const isInProgress = todo.status === 'in_progress';

            return (
              <div
                key={todo.id || `todo-${idx}`}
                data-testid={`todo-item-${todo.status}`}
                className={cn(
                  'flex items-start gap-3 p-2.5 rounded-lg border text-xs transition-colors',
                  isCompleted &&
                    'bg-emerald-950/20 border-emerald-500/30 text-emerald-200/90',
                  isInProgress &&
                    'bg-blue-950/30 border-blue-500/40 text-blue-200 shadow-sm',
                  !isCompleted &&
                    !isInProgress &&
                    'bg-zinc-900/40 border-zinc-800 text-zinc-400'
                )}
              >
                <div className="mt-0.5 shrink-0">
                  {isCompleted ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : isInProgress ? (
                    <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
                  ) : (
                    <Circle className="w-4 h-4 text-zinc-500" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <span
                    className={cn(
                      'leading-relaxed break-words font-medium',
                      isCompleted && 'line-through text-emerald-300/70',
                      isInProgress && 'text-zinc-100 font-semibold'
                    )}
                  >
                    {todo.content}
                  </span>
                </div>

                <span
                  className={cn(
                    'shrink-0 text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border',
                    isCompleted &&
                      'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
                    isInProgress &&
                      'bg-blue-500/20 text-blue-300 border-blue-500/30 animate-pulse',
                    !isCompleted &&
                      !isInProgress &&
                      'bg-zinc-800 text-zinc-400 border-zinc-700'
                  )}
                >
                  {isCompleted
                    ? 'Completed'
                    : isInProgress
                    ? 'In Progress'
                    : 'Pending'}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
