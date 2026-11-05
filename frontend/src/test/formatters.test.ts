import { describe, it, expect } from 'vitest';
import {
  formatDocumentDate,
  formatExtractionTimestamp,
  formatDuration,
  getStatusBadgeClasses,
  normalizePageMarkers,
  normalizeMarkdownTables,
} from '../utils/formatters';

describe('Authoritative Formatters & Presentation Utilities', () => {
  describe('formatDocumentDate', () => {
    it('formats ISO dates into unambiguous day-month-year format', () => {
      expect(formatDocumentDate('2026-11-03T10:00:00Z')).toBe('3 Nov 2026');
      expect(formatDocumentDate('2026-01-15T12:00:00Z')).toBe('15 Jan 2026');
    });

    it('returns "Date unavailable" for invalid or null date strings without throwing', () => {
      expect(formatDocumentDate(null)).toBe('Date unavailable');
      expect(formatDocumentDate(undefined)).toBe('Date unavailable');
      expect(formatDocumentDate('')).toBe('Date unavailable');
      expect(formatDocumentDate('invalid-date-string')).toBe('Date unavailable');
    });
  });

  describe('formatExtractionTimestamp', () => {
    it('formats ISO timestamp with date, time, and timezone', () => {
      const formatted = formatExtractionTimestamp('2026-11-03T13:43:05Z');
      expect(formatted).not.toContain('Invalid Date');
      expect(formatted).toMatch(/3 Nov 2026/);
    });

    it('returns "Timestamp unavailable" for null, undefined, or malformed strings and never renders Invalid Date', () => {
      expect(formatExtractionTimestamp(null)).toBe('Timestamp unavailable');
      expect(formatExtractionTimestamp(undefined)).toBe('Timestamp unavailable');
      expect(formatExtractionTimestamp('not-a-timestamp')).toBe('Timestamp unavailable');
      expect(formatExtractionTimestamp('Invalid Date')).toBe('Timestamp unavailable');
    });
  });

  describe('formatDuration', () => {
    it('formats durations < 1000ms in ms', () => {
      expect(formatDuration(842)).toBe('842 ms');
      expect(formatDuration(50)).toBe('50 ms');
      expect(formatDuration(0)).toBe('0 ms');
    });

    it('formats durations >= 1000ms in seconds with 2 decimal places', () => {
      expect(formatDuration(12480)).toBe('12.48 s');
      expect(formatDuration(1000)).toBe('1.00 s');
      expect(formatDuration(2500)).toBe('2.50 s');
    });

    it('returns "Duration unavailable" for null, undefined, or negative values and never renders bare "ms"', () => {
      expect(formatDuration(null)).toBe('Duration unavailable');
      expect(formatDuration(undefined)).toBe('Duration unavailable');
      expect(formatDuration(-10)).toBe('Duration unavailable');
      expect(formatDuration(NaN)).toBe('Duration unavailable');
    });
  });

  describe('getStatusBadgeClasses', () => {
    it('maps SUCCESS to emerald green', () => {
      const cls = getStatusBadgeClasses('SUCCESS');
      expect(cls).toContain('text-emerald-400');
      expect(cls).toContain('bg-emerald-500/10');
    });

    it('maps lowercase success to emerald green', () => {
      const cls = getStatusBadgeClasses('success');
      expect(cls).toContain('text-emerald-400');
    });

    it('maps PARTIAL_SUCCESS to amber', () => {
      const cls = getStatusBadgeClasses('PARTIAL_SUCCESS');
      expect(cls).toContain('text-amber-400');
    });

    it('maps FAILED and REJECTED to rose/red', () => {
      expect(getStatusBadgeClasses('FAILED')).toContain('text-rose-400');
      expect(getStatusBadgeClasses('REJECTED')).toContain('text-rose-400');
      expect(getStatusBadgeClasses('failed')).toContain('text-rose-400');
    });

    it('maps IN_PROGRESS to blue', () => {
      expect(getStatusBadgeClasses('IN_PROGRESS')).toContain('text-blue-400');
      expect(getStatusBadgeClasses('in_progress')).toContain('text-blue-400');
    });

    it('maps PENDING and CANCELLED to neutral zinc', () => {
      expect(getStatusBadgeClasses('PENDING')).toContain('text-zinc-400');
      expect(getStatusBadgeClasses('cancelled')).toContain('text-zinc-400');
    });
  });

  describe('normalizePageMarkers', () => {
    it('normalizes various page marker formats to [Page X of Y]', () => {
      const input = 'Header text\nPage 1 | 40\nBody paragraph\nPage 2 of 40\nMore text';
      const normalized = normalizePageMarkers(input);
      expect(normalized).toContain('[Page 1 of 40]');
      expect(normalized).toContain('[Page 2 of 40]');
    });

    it('normalizes standalone Page X to [Page X]', () => {
      const input = 'Section\n--- Page 5 ---\nContent';
      const normalized = normalizePageMarkers(input);
      expect(normalized).toContain('[Page 5]');
    });
  });

  describe('normalizeMarkdownTables', () => {
    it('ensures blank lines around table blocks so GFM parses them properly', () => {
      const input = 'Paragraph before\n| Col1 | Col2 |\n| --- | --- |\n| Val1 | Val2 |\nParagraph after';
      const output = normalizeMarkdownTables(input);
      expect(output).toContain('\n\n| Col1 | Col2 |');
      expect(output).toContain('| Val1 | Val2 |\n\nParagraph after');
    });
  });
});

