import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import type { AgentEvent, JsonObject } from "../types";
import { displayText, textOf } from "../lib/format";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary" | "outline" | "ghost" | "destructive";
  size?: "sm" | "md" | "icon";
};

export function Button({ className = "", variant = "default", size = "md", type = "button", ...props }: ButtonProps) {
  return <button type={type} className={`btn btn-${variant} btn-${size} ${className}`} {...props} />;
}

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <section className={`card ${className}`} {...props} />;
}

export function CardHeader({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card-header ${className}`} {...props} />;
}

export function CardTitle({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h2 className={`card-title ${className}`}>{children}</h2>;
}

export function CardDescription({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`card-description ${className}`}>{children}</p>;
}

export function CardContent({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card-content ${className}`} {...props} />;
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function Badge({ tone = "default", children }: { tone?: "default" | "green" | "amber" | "red" | "blue"; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function JsonBlock({ value, empty = "No data" }: { value: unknown; empty?: string }) {
  const hasValue = value !== undefined && value !== null && value !== "";
  return <pre className="json-block">{hasValue ? JSON.stringify(value, null, 2) : empty}</pre>;
}

export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: ReactNode }) {
  return (
    <div className="empty-state">
      {icon ? <div className="empty-state-icon">{icon}</div> : null}
      <strong>{title}</strong>
      {hint ? <span>{hint}</span> : null}
    </div>
  );
}

export function Skeleton({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`skeleton-block ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <span key={index} className="skeleton-line" />
      ))}
    </div>
  );
}

// 价格方案建议的前后对比视图（before/after）。
export function DiffView({ before, after, empty = "暂无配置差异" }: { before?: JsonObject; after?: JsonObject; empty?: string }) {
  const hasBefore = before && Object.keys(before).length > 0;
  const hasAfter = after && Object.keys(after).length > 0;
  if (!hasBefore && !hasAfter) {
    return <div className="empty-cell">{empty}</div>;
  }
  const keys = Array.from(new Set([...Object.keys(before || {}), ...Object.keys(after || {})])).sort();
  return (
    <div className="diff-view">
      {keys.map((key) => {
        const beforeValue = serializeDiffValue(before?.[key]);
        const afterValue = serializeDiffValue(after?.[key]);
        const changed = beforeValue !== afterValue;
        return (
          <div className={`diff-row ${changed ? "diff-changed" : ""}`} key={key}>
            <span className="diff-key">{key}</span>
            <span className="diff-before">{beforeValue || "—"}</span>
            <span className="diff-arrow">→</span>
            <span className="diff-after">{afterValue || "—"}</span>
          </div>
        );
      })}
    </div>
  );
}

function serializeDiffValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// 工具调用/结果卡片，技术细节收进折叠。
export function ToolEventCard({ event }: { event: AgentEvent }) {
  const payload = event.payload || {};
  const status = String(payload.status || (event.event_type === "tool.result" ? "completed" : "running"));
  const title = displayText(payload.title, event.event_type === "tool.result" ? "完成一个检查步骤" : "正在执行检查步骤");
  return (
    <div className="tool-card">
      <div className="tool-card-head">
        <strong>{title}</strong>
        <Badge tone={status === "completed" ? "green" : "amber"}>{status === "completed" ? "已完成" : "检查中"}</Badge>
      </div>
      <div className="tool-meta">
        <span>{status === "completed" ? "已完成一次自动检查" : "Agent 正在核对资料"}</span>
        {payload.duration_ms ? <span>耗时：{textOf(payload.duration_ms)} ms</span> : null}
      </div>
      <details>
        <summary>查看技术详情</summary>
        <JsonBlock value={payload} empty="暂无技术详情" />
      </details>
    </div>
  );
}

export function DataTable({
  columns,
  rows,
  empty = "No rows",
}: {
  columns: string[];
  rows: Array<Array<ReactNode>>;
  empty?: string;
}) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length} className="empty-cell">
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
