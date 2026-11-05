import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MarkdownContent } from '../components/chat/MarkdownContent';

describe('Chat Markdown Content & GFM Table Rendering', () => {
  it('renders Document Registry table fixture as real HTML table', () => {
    const documentRegistryMarkdown = `
Here is the current document registry:

| Document ID | Name | Source | Version | Status |
| --- | --- | --- | --- | --- |
| doc-001 | PRC SLA External.pdf | PDF | v1 | Ingested |
| doc-002 | Annual Financials.xlsx | Excel | v2 | Ingested |
| doc-003 | https://example.com | Web Page | v1 | Verified |
`;

    render(<MarkdownContent content={documentRegistryMarkdown} />);

    // Verify <table>, <thead>, and <tbody> elements rendered
    const table = screen.getByRole('table');
    expect(table).toBeInTheDocument();

    expect(screen.getByText('Document ID')).toBeInTheDocument();
    expect(screen.getByText('PRC SLA External.pdf')).toBeInTheDocument();
    expect(screen.getByText('Annual Financials.xlsx')).toBeInTheDocument();
    expect(screen.getByText('doc-003')).toBeInTheDocument();
  });

  it('renders SLA Priority Matrix table fixture as real HTML table', () => {
    const slaMatrixMarkdown = `
### Service Level Agreement Priority Matrix

| Priority | Severity | Response Target | Resolution Target | Escalation |
| :--- | :--- | :--- | :--- | :--- |
| P1 | Critical | 15 minutes | 4 hours | VP Engineering |
| P2 | Major | 1 hour | 8 hours | Director On-Call |
| P3 | Moderate | 4 hours | 24 hours | Team Lead |
| P4 | Minor | 1 business day | 5 business days | Standard Queue |
`;

    render(<MarkdownContent content={slaMatrixMarkdown} />);

    expect(screen.getByRole('heading', { level: 3, name: /Service Level Agreement Priority Matrix/i })).toBeInTheDocument();

    const table = screen.getByRole('table');
    expect(table).toBeInTheDocument();

    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('15 minutes')).toBeInTheDocument();
    expect(screen.getByText('VP Engineering')).toBeInTheDocument();
    expect(screen.getByText('5 business days')).toBeInTheDocument();
  });

  it('renders Business Hours table fixture as real HTML table', () => {
    const businessHoursMarkdown = `
| Day | Support Tier 1 | Support Tier 2 | Escalation Standby |
| --- | --- | --- | --- |
| Monday - Friday | 08:00 - 20:00 UTC | 09:00 - 18:00 UTC | 24/7 Coverage |
| Saturday | 10:00 - 16:00 UTC | On Call | 24/7 Coverage |
| Sunday | Emergency Only | On Call | 24/7 Coverage |
`;

    render(<MarkdownContent content={businessHoursMarkdown} />);

    const table = screen.getByRole('table');
    expect(table).toBeInTheDocument();

    expect(screen.getByText('Monday - Friday')).toBeInTheDocument();
    expect(screen.getByText('08:00 - 20:00 UTC')).toBeInTheDocument();
    expect(screen.getByText('Emergency Only')).toBeInTheDocument();
  });

  it('safely escapes raw HTML and preserves code blocks and links', () => {
    const mixedMarkdown = `
Check out [Documentation](https://javed.ai/docs) and safe code:

\`\`\`python
def secure_process():
    return "zero-leakage"
\`\`\`

<script>alert("unsafe-xss")</script>
`;

    const { container } = render(<MarkdownContent content={mixedMarkdown} />);

    expect(screen.getByRole('link', { name: 'Documentation' })).toHaveAttribute('href', 'https://javed.ai/docs');
    expect(screen.getByText(/zero-leakage/)).toBeInTheDocument();

    // Raw script tag must NOT be executed or rendered as an active script element
    expect(container.querySelector('script')).toBeNull();
  });
});

