import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToolActivityCard } from '../components/chat/ToolActivityCard';
import type { ToolActivityRecord } from '../types/agent';

describe('ToolActivityCard Component', () => {
  const baseRecord: ToolActivityRecord = {
    tool_call_id: 'tc-test-001',
    tool_id: 'time__get_current_time',
    server_id: 'time',
    tool_name: 'time__get_current_time',
    description: 'Get current time in timezone',
    arguments: { timezone: 'UTC' },
    status: 'REQUESTED',
    started_at: '2026-10-27T10:00:00Z',
  };

  it('renders REQUESTED badge, tool name, server ID, and purpose', () => {
    render(<ToolActivityCard activity={baseRecord} />);

    expect(screen.getByTestId('tool-activity-card')).toBeInTheDocument();
    expect(screen.getByTestId('tool-activity-name')).toHaveTextContent('time__get_current_time');
    expect(screen.getByTestId('tool-activity-server')).toHaveTextContent('time');
    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/REQUESTED/i);
    expect(screen.getByTestId('tool-activity-purpose')).toHaveTextContent('Get current time in timezone');
  });

  it('renders AWAITING_APPROVAL badge', () => {
    const awaitingRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'AWAITING_APPROVAL',
      approval_id: 'appr-123',
    };
    render(<ToolActivityCard activity={awaitingRecord} />);

    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/AWAITING APPROVAL/i);
  });

  it('renders EXECUTING badge when tool is running', () => {
    const executingRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'EXECUTING',
    };
    render(<ToolActivityCard activity={executingRecord} />);

    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/EXECUTING/i);
  });

  it('renders COMPLETED badge, duration, and result summary', () => {
    const completedRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'COMPLETED',
      result_summary: '{"datetime": "2026-10-27T12:00:00Z"}',
      completed_at: '2026-10-27T10:00:01Z',
      elapsed_ms: 45,
    };
    render(<ToolActivityCard activity={completedRecord} />);

    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/COMPLETED/i);
    expect(screen.getByTestId('tool-activity-duration')).toHaveTextContent('45ms');
    expect(screen.getByTestId('tool-activity-result')).toHaveTextContent('2026-10-27T12:00:00Z');
  });

  it('renders FAILED badge and error message truthfully without success badge', () => {
    const failedRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'FAILED',
      error_message: 'MCP connection timed out',
      completed_at: '2026-10-27T10:00:05Z',
      elapsed_ms: 5000,
    };
    render(<ToolActivityCard activity={failedRecord} />);

    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/FAILED/i);
    expect(screen.getByTestId('tool-activity-error')).toHaveTextContent('MCP connection timed out');
    expect(screen.queryByText(/COMPLETED/i)).not.toBeInTheDocument();
  });

  it('renders REJECTED and UNCERTAIN lifecycles', () => {
    const rejectedRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'REJECTED',
      error_message: 'Rejected by operator',
    };
    const { rerender } = render(<ToolActivityCard activity={rejectedRecord} />);
    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/REJECTED/i);

    const uncertainRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'UNCERTAIN',
      error_message: 'Transport disconnected mid-call',
    };
    rerender(<ToolActivityCard activity={uncertainRecord} />);
    expect(screen.getByTestId('tool-activity-status')).toHaveTextContent(/UNCERTAIN/i);
  });

  it('expands arguments and timestamps on toggle', async () => {
    const user = userEvent.setup();
    const detailedRecord: ToolActivityRecord = {
      ...baseRecord,
      status: 'COMPLETED',
      result_summary: '{"datetime": "2026-10-27T12:00:00Z"}',
      completed_at: '2026-10-27T10:00:01Z',
      elapsed_ms: 120,
    };
    render(<ToolActivityCard activity={detailedRecord} />);

    expect(screen.queryByTestId('tool-activity-args')).not.toBeInTheDocument();

    const toggleBtn = screen.getByTestId('tool-activity-toggle');
    await user.click(toggleBtn);

    expect(screen.getByTestId('tool-activity-args')).toBeInTheDocument();
    expect(screen.getByTestId('tool-activity-args')).toHaveTextContent('"timezone": "UTC"');
    expect(screen.getByTestId('tool-activity-time')).toBeInTheDocument();
  });
});
