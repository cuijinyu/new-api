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
  return value
    .replace(/\r\n/g, "\n")
    .replace(/\|\|/g, "|\n|")
    .replace(/([^\n])(\s*)(#{1,6})(?=\S)/g, "$1\n\n$3")
    .replace(/(^|\n)(#{1,6})(?=\S)/g, "$1$2 ")
    .replace(/(^|\n)(#{1,6} [^\n|]+)(\|)/g, "$1$2\n\n$3")
    .replace(/([^\n])(\s*)(\d+\.\s+\*\*)/g, "$1\n$3");
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
