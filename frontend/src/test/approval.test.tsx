import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApprovalCard } from '../components/chat/ApprovalCard';
import type { ApprovalRecord } from '../types/agent';

describe('ApprovalCard Component', () => {
  const sampleApproval: ApprovalRecord = {
    approval_id: 'appr-test-12345678',
    interrupt_id: 'inter-test-001',
    run_id: 'run-test-001',
    thread_id: 'thread-test-001',
    server_id: 'time',
    tool_id: 'time__get_current_time',
    tool_call_id: 'call_abc123',
    arguments: { timezone: 'UTC' },
    argument_digest: 'd41d8cd98f00b204e9800998ecf8427e',
    tool_fingerprint: 'fp_time_get_current_time_v1',
    policy_version: 1,
    created_at: new Date().toISOString(),
    status: 'pending',
    dispatch_status: 'not_dispatched',
  };

  it('renders pending approval card with tool name, server, and action buttons', () => {
    render(
      <ApprovalCard
        approval={sampleApproval}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByTestId('approval-card')).toBeInTheDocument();
    expect(screen.getByTestId('approval-status-badge')).toHaveTextContent(/pending/i);
    expect(screen.getByTestId('approval-tool-name')).toHaveTextContent('time__get_current_time');
    expect(screen.getByTestId('approval-server-id')).toHaveTextContent('time');
    expect(screen.getByTestId('approve-tool-button')).toBeInTheDocument();
    expect(screen.getByTestId('reject-tool-button')).toBeInTheDocument();
  });

  it('invokes onApprove when approve button is clicked', async () => {
    const user = userEvent.setup();
    const handleApprove = vi.fn().mockResolvedValue(undefined);

    render(
      <ApprovalCard
        approval={sampleApproval}
        onApprove={handleApprove}
        onReject={vi.fn()}
      />
    );

    const approveBtn = screen.getByTestId('approve-tool-button');
    await user.click(approveBtn);

    expect(handleApprove).toHaveBeenCalledTimes(1);
    expect(handleApprove).toHaveBeenCalledWith('appr-test-12345678');
  });

  it('reveals rejection input and invokes onReject with reason', async () => {
    const user = userEvent.setup();
    const handleReject = vi.fn().mockResolvedValue(undefined);

    render(
      <ApprovalCard
        approval={sampleApproval}
        onApprove={vi.fn()}
        onReject={handleReject}
      />
    );

    const rejectBtn = screen.getByTestId('reject-tool-button');
    await user.click(rejectBtn);

    const input = screen.getByTestId('reject-reason-input');
    expect(input).toBeInTheDocument();
    await user.type(input, 'Security policy violation');

    const confirmBtn = screen.getByTestId('confirm-reject-button');
    await user.click(confirmBtn);

    expect(handleReject).toHaveBeenCalledTimes(1);
    expect(handleReject).toHaveBeenCalledWith('appr-test-12345678', 'Security policy violation');
  });

  it('displays approved state and dispatch outcome when completed', () => {
    const completedApproval: ApprovalRecord = {
      ...sampleApproval,
      status: 'approved',
      dispatch_status: 'completed',
      result_summary: 'Current time is 11:30:00 UTC',
    };

    render(
      <ApprovalCard
        approval={completedApproval}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByTestId('approval-status-badge')).toHaveTextContent(/approved/i);
    expect(screen.queryByTestId('approve-tool-button')).not.toBeInTheDocument();
    expect(screen.getByText(/Current time is 11:30:00 UTC/i)).toBeInTheDocument();
  });

  it('displays error message if onApprove throws', async () => {
    const user = userEvent.setup();
    const handleApprove = vi.fn().mockRejectedValue(new Error('Permission revoked before dispatch'));

    render(
      <ApprovalCard
        approval={sampleApproval}
        onApprove={handleApprove}
        onReject={vi.fn()}
      />
    );

    const approveBtn = screen.getByTestId('approve-tool-button');
    await user.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByTestId('approval-action-error')).toHaveTextContent(
        'Permission revoked before dispatch'
      );
    });
  });
});
