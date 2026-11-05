import React, { useState } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Check, Copy } from 'lucide-react';
import { normalizeMarkdownTables } from '../../utils/formatters';

interface MarkdownContentProps {
  content: string;
}

export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content }) => {
  const normalizedContent = normalizeMarkdownTables(content);

  return (
    <div className="prose prose-invert max-w-none text-sm leading-relaxed space-y-2">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const isInline = !match && !className;
            const codeString = String(children).replace(/\n$/, '');

            if (isInline) {
              return (
                <code
                  className="px-1.5 py-0.5 rounded bg-zinc-800 text-cyan-300 font-mono text-xs border border-zinc-700/60"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <CodeBlock language={match ? match[1] : ''} code={codeString} />
            );
          },
          table({ children }) {
            return (
              <div className="my-3 overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950/70 shadow-sm">
                <table className="min-w-full divide-y divide-zinc-800 text-left text-xs font-mono">
                  {children}
                </table>
              </div>
            );
          },
          thead({ children }) {
            return (
              <thead className="bg-zinc-900/90 text-zinc-300 font-semibold uppercase tracking-wider text-[11px]">
                {children}
              </thead>
            );
          },
          tbody({ children }) {
            return <tbody className="divide-y divide-zinc-800/60 text-zinc-300">{children}</tbody>;
          },
          tr({ children }) {
            return <tr className="hover:bg-zinc-900/50 transition-colors">{children}</tr>;
          },
          th({ children }) {
            return (
              <th className="px-3.5 py-2.5 text-xs font-semibold text-zinc-200 border-b border-zinc-800">
                {children}
              </th>
            );
          },
          td({ children }) {
            return <td className="px-3.5 py-2 text-xs text-zinc-300 whitespace-nowrap">{children}</td>;
          },
          p({ children }) {
            return <p className="mb-2 last:mb-0 text-zinc-200">{children}</p>;
          },
          ul({ children }) {
            return <ul className="list-disc list-inside space-y-1 my-2 text-zinc-300">{children}</ul>;
          },
          ol({ children }) {
            return <ol className="list-decimal list-inside space-y-1 my-2 text-zinc-300">{children}</ol>;
          },
          li({ children }) {
            return <li className="text-zinc-300">{children}</li>;
          },
          a({ href, children }) {
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2 transition-colors"
              >
                {children}
              </a>
            );
          },
          blockquote({ children }) {
            return (
              <blockquote className="border-l-2 border-cyan-500/60 pl-3 italic text-zinc-400 my-2 bg-zinc-900/30 py-1 rounded-r">
                {children}
              </blockquote>
            );
          },
        }}
      >
        {normalizedContent}
      </Markdown>
    </div>
  );
};

interface CodeBlockProps {
  language: string;
  code: string;
}

const CodeBlock: React.FC<CodeBlockProps> = ({ language, code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard write failed
    }
  };

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-zinc-700/80 bg-zinc-950 shadow-md font-mono text-xs">
      <div className="flex items-center justify-between px-3 py-1.5 bg-zinc-900/90 border-b border-zinc-800 text-[11px] text-zinc-400">
        <span className="font-semibold text-zinc-300 uppercase tracking-wider">{language || 'code'}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-0.5 rounded hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-emerald-400" />
              <span className="text-emerald-400">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-zinc-200 leading-normal">
        <code>{code}</code>
      </pre>
    </div>
  );
};
