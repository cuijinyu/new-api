import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

type MarkdownMessageProps = {
  className?: string;
  content?: string | null;
  fallback?: string;
};

const components: Components = {
  a({ children, href, ...props }) {
    return (
      <a href={href} rel="noreferrer" target="_blank" {...props}>
        {children}
      </a>
    );
  },
  table({ children, ...props }) {
    return (
      <div className="agent-markdown-table">
        <table {...props}>{children}</table>
      </div>
    );
  },
};

function normalizeMarkdownSource(value: string) {
  const lines = value.replace(/\r\n/g, "\n").split("\n");
  const normalized: string[] = [];
  let inFence = false;

  for (const rawLine of lines) {
    let line = rawLine;
    if (/^\s*```/.test(line)) {
      inFence = !inFence;
      normalized.push(line);
      continue;
    }
    if (!inFence) {
      line = line.replace(/^(#{1,6})(?=\S)/, "$1 ");
      const headingMatch = line.match(/^(.+?)(\s+)(#{1,6}\s+\S.*)$/);
      if (headingMatch && !headingMatch[1].trim().startsWith("#")) {
        normalized.push(headingMatch[1].trimEnd(), "", headingMatch[3]);
        continue;
      }
      const listMatch = line.match(/^(.+?)(\s+)((?:[-*+]\s+|\d+\.\s+)\S.*)$/);
      if (listMatch && listMatch[1].trim().length > 2) {
        normalized.push(listMatch[1].trimEnd(), listMatch[3]);
        continue;
      }
    }
    normalized.push(line);
  }

  return normalized.join("\n").replace(/\n{3,}/g, "\n\n");
}

export function MarkdownMessage({ className = "", content, fallback = "-" }: MarkdownMessageProps) {
  const source = normalizeMarkdownSource(String(content || fallback).trim());
  if (!source) return null;

  return (
    <div className={`agent-markdown ${className}`.trim()} data-testid="agent-markdown">
      <ReactMarkdown components={components} remarkPlugins={[remarkGfm, remarkBreaks]}>
        {source}
      </ReactMarkdown>
    </div>
  );
}
