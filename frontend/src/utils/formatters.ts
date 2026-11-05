/**
 * Authoritative formatting and presentation utilities for Javed UI.
 * Enforces unambiguous dates, safe timestamps, bounded durations,
 * WCAG-compliant status badges, and page-marker normalization.
 */

const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/**
 * Format an ISO date string into an unambiguous document date: e.g. "3 Nov 2026".
 * If invalid or missing, returns "Date unavailable". Never returns "Invalid Date".
 */
export function formatDocumentDate(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Date unavailable';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return 'Date unavailable';

  const day = d.getDate();
  const month = MONTH_NAMES[d.getMonth()];
  const year = d.getFullYear();
  return `${day} ${month} ${year}`;
}

/**
 * Format an ISO timestamp string into an unambiguous, localized date & time with timezone.
 * e.g. "3 Nov 2026, 1:43:05 PM GMT+3" or "3 Nov 2026, 13:43:05 UTC".
 * If invalid or missing, returns "Timestamp unavailable". Never returns "Invalid Date".
 */
export function formatExtractionTimestamp(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Timestamp unavailable';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return 'Timestamp unavailable';

  const day = d.getDate();
  const month = MONTH_NAMES[d.getMonth()];
  const year = d.getFullYear();

  try {
    const timeWithTz = d.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
      timeZoneName: 'short',
    });
    return `${day} ${month} ${year}, ${timeWithTz}`;
  } catch {
    const time = d.toTimeString().split(' ')[0];
    return `${day} ${month} ${year}, ${time}`;
  }
}

/**
 * Format duration in milliseconds to a human-readable string.
 * Formats >= 1000ms as seconds (e.g. "12.48 s") and < 1000ms as ms (e.g. "842 ms").
 * If null/undefined/invalid, returns "Duration unavailable". Never returns a bare "ms".
 */
export function formatDuration(durationMs: number | null | undefined): string {
  if (durationMs === null || durationMs === undefined || isNaN(durationMs) || durationMs < 0) {
    return 'Duration unavailable';
  }
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2)} s`;
  }
  return `${Math.round(durationMs)} ms`;
}

/**
 * Return WCAG-compliant Tailwind badge classes for extraction and execution status.
 */
export function getStatusBadgeClasses(status: string | null | undefined): string {
  const s = status?.toLowerCase().trim() || '';
  switch (s) {
    case 'success':
      return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30';
    case 'partial_success':
      return 'bg-amber-500/10 text-amber-400 border border-amber-500/30';
    case 'failed':
    case 'rejected':
      return 'bg-rose-500/10 text-rose-400 border border-rose-500/30';
    case 'in_progress':
      return 'bg-blue-500/10 text-blue-400 border border-blue-500/30';
    case 'pending':
    case 'cancelled':
    default:
      return 'bg-zinc-500/10 text-zinc-400 border border-zinc-500/30';
  }
}

/**
 * Normalize page boundaries in extracted text/markdown for consistent presentation preview.
 * Converts formats such as "Page 1 | 40" or "--- Page 1 ---" into standard "[Page 1 of 40]".
 * Purely for preview display; does not alter raw source or cryptographic hashes.
 */
export function normalizePageMarkers(content: string): string {
  if (!content) return '';
  return content
    // Convert "Page X | Y" or "Page X/Y" or "Page X of Y" into "[Page X of Y]"
    .replace(/(?:^|\n)(?:[-=~*#\s]*)(?:Page\s+(\d+)\s*(?:\||\/|of)\s*(\d+))(?:[-=~*#\s]*)(?=\n|$)/gi, '\n[Page $1 of $2]\n')
    // Convert standalone "--- Page X ---" into "[Page X]"
    .replace(/(?:^|\n)(?:[-=~*#\s]*)(?:Page\s+(\d+))(?:[-=~*#\s]*)(?=\n|$)/gi, '\n[Page $1]\n')
    // Clean up excessive newlines around page markers
    .replace(/\n{3,}\[Page/g, '\n\n[Page');
}

/**
 * Ensure markdown tables have leading and trailing blank lines so GFM parser triggers reliably.
 * Never inserts blank lines between rows within a table block.
 */
export function normalizeMarkdownTables(markdown: string): string {
  if (!markdown) return '';
  const lines = markdown.split('\n');
  const result: string[] = [];
  let inTable = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const isTableLine = line.trim().startsWith('|') && line.trim().endsWith('|');

    if (isTableLine && !inTable) {
      // Table starts: ensure blank line before it if previous line wasn't blank
      if (result.length > 0 && result[result.length - 1].trim() !== '') {
        result.push('');
      }
      inTable = true;
    } else if (!isTableLine && inTable) {
      // Table ended: ensure blank line after it if current line isn't blank
      if (line.trim() !== '') {
        result.push('');
      }
      inTable = false;
    }

    result.push(line);
  }

  return result.join('\n');
}
