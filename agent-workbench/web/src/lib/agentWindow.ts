import type { AgentEvent, AgentSession, UploadedFile } from "../types";
import { categoryText, displayText, fileDirectory, formatDate, shortId } from "./format";

export type AgentTimelineItem =
  | { id: string; kind: "message"; event: AgentEvent; title: string; body: string; time: string }
  | { id: string; kind: "assistant"; event: AgentEvent; title: string; body: string; time: string }
  | { id: string; kind: "step"; call?: AgentEvent; result?: AgentEvent; title: string; status: "running" | "completed"; time: string }
  | { id: string; kind: "state"; event: AgentEvent; title: string; body: string; tone: "default" | "green" | "amber" | "red" | "blue"; time: string };

export type AgentContextItem = {
  id: string;
  title: string;
  meta: string;
  kind: "file" | "session" | "current";
  category?: string;
};

export type AgentCommandSuggestion = {
  id: string;
  label: string;
  description: string;
  insertText?: string;
  fileIds?: string[];
  sessionIds?: string[];
  action?: "governance";
};

function eventKey(event: AgentEvent, index: number) {
  return event.id || `${event.event_type || "event"}-${event.seq || index}`;
}

function eventTime(event?: AgentEvent) {
  return event?.created_at ? formatDate(event.created_at) : "";
}

const assistantWordBoundaryHints = new Set([
  "a",
  "an",
  "and",
  "available",
  "by",
  "card",
  "check",
  "confirming",
  "delta",
  "directory",
  "excel",
  "exploring",
  "files",
  "for",
  "input",
  "inspect",
  "internal",
  "json",
  "key",
  "let",
  "markdown",
  "me",
  "now",
  "parsing",
  "python",
  "rate",
  "reading",
  "reference",
  "rendering",
  "script",
  "start",
  "supplier",
  "table",
  "the",
  "tools",
  "total",
  "value",
  "with",
]);

function shouldInsertAssistantSpace(left: string, right: string) {
  if (!left || !right) return false;
  const prev = left[left.length - 1];
  const next = right[0];
  if (!prev || !next || /\s/.test(prev) || /\s/.test(next)) return false;
  if ("([{/<".includes(prev) || ".,;:!?)]}/|".includes(next)) return false;
  if (!/^[A-Za-z']$/.test(prev) || !/^[A-Za-z]$/.test(next)) return false;
  const nextWord = right.match(/^[A-Za-z]+/)?.[0].toLowerCase() || "";
  return assistantWordBoundaryHints.has(nextWord);
}

function appendAssistantContent(left: string, right: string) {
  if (!right) return left;
  return `${left}${shouldInsertAssistantSpace(left, right) ? " " : ""}${right}`;
}

function toolTitle(event?: AgentEvent) {
  const payload = event?.payload || {};
  return displayText(payload.title || payload.tool_name, event?.event_type === "tool.result" ? "完成检查步骤" : "执行检查步骤");
}

export function groupAgentEvents(events: AgentEvent[]): AgentTimelineItem[] {
  const items: AgentTimelineItem[] = [];
  const openTools = new Map<string, { index: number; call: AgentEvent }>();

  events.forEach((event, index) => {
    const key = eventKey(event, index);
    const type = event.event_type || "";
    const payload = event.payload || {};
    const toolName = String(payload.tool_name || payload.name || payload.title || key);

    if (type === "tool.call") {
      const item: AgentTimelineItem = {
        id: key,
        kind: "step",
        call: event,
        title: toolTitle(event),
        status: "running",
        time: eventTime(event),
      };
      items.push(item);
      openTools.set(toolName, { index: items.length - 1, call: event });
      return;
    }

    if (type === "tool.result") {
      const open = openTools.get(toolName);
      if (open && items[open.index]?.kind === "step") {
        const current = items[open.index] as Extract<AgentTimelineItem, { kind: "step" }>;
        items[open.index] = {
          ...current,
          result: event,
          title: toolTitle(event) || current.title,
          status: "completed",
          time: eventTime(event) || current.time,
        };
        openTools.delete(toolName);
        return;
      }
      items.push({
        id: key,
        kind: "step",
        result: event,
        title: toolTitle(event),
        status: "completed",
        time: eventTime(event),
      });
      return;
    }

    if (type === "message" || event.role === "user" || event.role === "operator") {
      items.push({
        id: key,
        kind: "message",
        event,
        title: "你",
        body: displayText(event.content, "补充了一条信息。"),
        time: eventTime(event),
      });
      return;
    }

    if (type === "assistant.delta" || event.role === "assistant") {
      const last = items[items.length - 1];
      const content = String(event.content || "");
      if (last?.kind === "assistant") {
        items[items.length - 1] = {
          ...last,
          event,
          body: displayText(appendAssistantContent(last.body, content), "Agent 更新了一条进展。"),
          time: eventTime(event) || last.time,
        };
        return;
      }
      items.push({
        id: key,
        kind: "assistant",
        event,
        title: "对账 Agent",
        body: displayText(event.content, "Agent 更新了一条进展。"),
        time: eventTime(event),
      });
      return;
    }

    if (type === "human.input.waiting") {
      items.push({
        id: key,
        kind: "state",
        event,
        title: "等待补充信息",
        body: displayText(event.content, "Agent 需要你补充口径、凭证或异常行号。"),
        tone: "amber",
        time: eventTime(event),
      });
      return;
    }

    if (type === "run.error") {
      items.push({
        id: key,
        kind: "state",
        event,
        title: "运行失败",
        body: displayText(event.content, "本轮分析失败，请保留上下文后重试。"),
        tone: "red",
        time: eventTime(event),
      });
      return;
    }

    if (type === "run.completed") {
      items.push({
        id: key,
        kind: "state",
        event,
        title: "任务完成",
        body: displayText(event.content, "本轮分析已完成。"),
        tone: "green",
        time: eventTime(event),
      });
      return;
    }

    if (type === "run.started") {
      items.push({
        id: key,
        kind: "state",
        event,
        title: "开始分析",
        body: displayText(event.content, "Agent 已开始分析。"),
        tone: "blue",
        time: eventTime(event),
      });
      return;
    }

    if (type === "session.created") {
      items.push({
        id: key,
        kind: "state",
        event,
        title: "任务已创建",
        body: displayText(event.content, "对账任务窗口已准备好。"),
        tone: "default",
        time: eventTime(event),
      });
    }
  });

  return items;
}

export function buildContextItems(files: UploadedFile[], sessions: AgentSession[], currentSession?: AgentSession): AgentContextItem[] {
  const fileItems = files.slice(0, 12).map((file) => ({
    id: file.id,
    title: file.filename,
    meta: [categoryText(file.category), fileDirectory(file), file.created_at ? formatDate(file.created_at) : ""].filter(Boolean).join(" · "),
    kind: "file" as const,
    category: file.category,
  }));

  const current = currentSession
    ? [{
        id: currentSession.id,
        title: currentSession.title || shortId(currentSession.id),
        meta: [currentSession.vendor, currentSession.month, currentSession.status].filter(Boolean).join(" · "),
        kind: "current" as const,
      }]
    : [];

  const sessionItems = sessions
    .filter((session) => session.id !== currentSession?.id)
    .slice(0, 6)
    .map((session) => ({
      id: session.id,
      title: session.title || shortId(session.id),
      meta: [session.vendor, session.month, session.updated_at ? formatDate(session.updated_at) : ""].filter(Boolean).join(" · "),
      kind: "session" as const,
    }));

  return [...current, ...fileItems, ...sessionItems];
}

export function agentCommandSuggestions(input: string, files: UploadedFile[], sessions: AgentSession[]): AgentCommandSuggestion[] {
  const query = input.trim();
  const billingFiles = files.filter((file) => file.category === "billing-result").slice(0, 6).map((file) => file.id);
  const supplierFiles = files.filter((file) => file.category === "supplier-bill" || file.category === "reconcile-evidence").slice(0, 6).map((file) => file.id);

  const suggestions: AgentCommandSuggestion[] = [
    {
      id: "billing-result",
      label: "@账单结果",
      description: billingFiles.length ? `引用 ${billingFiles.length} 个账单结果文件` : "暂无可引用的账单结果",
      fileIds: billingFiles,
      insertText: "@账单结果 请基于这些账单结果核对差异。",
    },
    {
      id: "supplier-bill",
      label: "@供应商账单",
      description: supplierFiles.length ? `引用 ${supplierFiles.length} 个供应商资料` : "暂无供应商资料",
      fileIds: supplierFiles,
      insertText: "@供应商账单 请和内部账单做差异核对。",
    },
    {
      id: "experience",
      label: "@经验库",
      description: "已按相关性自动注入经验，可在「经验注入」面板增删",
      insertText: "@经验库 请参考已注入的对账经验再给结论。",
    },
    {
      id: "save-experience",
      label: "/沉淀经验",
      description: "把当前结论整理成可复用经验（保存到经验库）",
      insertText: "请把本次对账结论整理成可复用经验，包含场景、判断依据和处理建议。",
    },
    {
      id: "governance",
      label: "/处理建议",
      description: "切到建议与经验页处理 Agent 给出的建议",
      action: "governance",
    },
  ];

  if (!query || query.endsWith("@") || query.endsWith("/") || query.includes("@") || query.includes("/")) {
    return suggestions;
  }
  return suggestions.slice(0, 3);
}
