import type { AgentEvent, AgentSession, UploadedFile } from "../types";
import { categoryText, displayText, fileDirectory, formatDate, shortId } from "./format";

export type AgentStepStatus = "running" | "retrying" | "completed" | "failed";

export type AgentTimelineItem =
  | { id: string; kind: "message"; event: AgentEvent; title: string; body: string; time: string }
  | { id: string; kind: "assistant"; event: AgentEvent; title: string; body: string; time: string }
  | { id: string; kind: "step"; call?: AgentEvent; result?: AgentEvent; title: string; status: AgentStepStatus; time: string }
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

function toolPairKey(event: AgentEvent, fallback: string) {
  const payload = event.payload || {};
  const stableId = payload.tool_call_id || payload.call_id || payload.id;
  return { key: String(stableId || fallback), stable: Boolean(stableId) };
}

function enqueueOpenTool(map: Map<string, Array<{ index: number; call: AgentEvent }>>, key: string, value: { index: number; call: AgentEvent }) {
  const current = map.get(key) || [];
  current.push(value);
  map.set(key, current);
}

function dequeueOpenTool(map: Map<string, Array<{ index: number; call: AgentEvent }>>, key: string) {
  const current = map.get(key);
  if (!current?.length) return null;
  const value = current.shift() || null;
  if (current.length) map.set(key, current);
  else map.delete(key);
  return value;
}

function latestOpenTool(map: Map<string, Array<{ index: number; call: AgentEvent }>>, key: string) {
  const current = map.get(key);
  return current?.length ? current[current.length - 1] : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasEventValue(value: unknown) {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function mergeRecordValue(previous: unknown, incoming: unknown) {
  if (isRecord(previous) && isRecord(incoming)) return { ...previous, ...incoming };
  return hasEventValue(incoming) ? incoming : previous;
}

function mergeToolCallEvent(previous: AgentEvent | undefined, incoming: AgentEvent) {
  if (!previous?.payload) return incoming;
  const previousPayload = previous.payload;
  const incomingPayload = incoming.payload || {};
  const payload: Record<string, unknown> = { ...previousPayload, ...incomingPayload };
  const preserveKeys = ["arguments", "args", "input", "rawInput", "raw_input", "command", "argv", "cwd", "kind", "tool_name", "name", "title"];

  for (const key of preserveKeys) {
    payload[key] = mergeRecordValue(previousPayload[key], incomingPayload[key]);
  }

  return {
    ...previous,
    ...incoming,
    content: hasEventValue(incoming.content) ? incoming.content : previous.content,
    payload,
  };
}

function mergeToolResultEvent(previous: AgentEvent | undefined, incoming: AgentEvent) {
  if (!previous?.payload) return incoming;
  const previousPayload = previous.payload;
  const incomingPayload = incoming.payload || {};
  const payload: Record<string, unknown> = { ...previousPayload, ...incomingPayload };
  const previousResult = previousPayload.result;
  const incomingResult = incomingPayload.result;

  if (isRecord(previousResult) && isRecord(incomingResult)) {
    payload.result = { ...previousResult, ...incomingResult };
  } else if (!hasEventValue(incomingResult) && hasEventValue(previousResult)) {
    payload.result = previousResult;
  }

  for (const key of ["stdout", "stderr", "stdout_tail", "stderr_tail"]) {
    if (!hasEventValue(payload[key]) && hasEventValue(previousPayload[key])) {
      payload[key] = previousPayload[key];
    }
    if (isRecord(payload.result) && isRecord(previousResult) && !hasEventValue(payload.result[key]) && hasEventValue(previousResult[key])) {
      payload.result[key] = previousResult[key];
    }
  }

  return { ...previous, ...incoming, payload };
}

function statusFromToolEvent(event: AgentEvent | undefined, fallback: AgentStepStatus): AgentStepStatus {
  const raw = String(event?.payload?.status || "").toLowerCase();
  if (["failed", "failure", "error", "errored", "cancelled", "canceled", "timeout", "timed_out"].includes(raw)) return "failed";
  if (["retrying", "retry", "backoff"].includes(raw)) return "retrying";
  if (["completed", "complete", "succeeded", "success", "done"].includes(raw)) return "completed";
  if (["running", "pending", "started", "in_progress", "working"].includes(raw)) return "running";
  if (event?.event_type === "tool.result") return "completed";
  return fallback;
}

function stepStatus(call: AgentEvent | undefined, result: AgentEvent | undefined, fallback: AgentStepStatus = "running") {
  if (result) return statusFromToolEvent(result, fallback);
  return statusFromToolEvent(call, fallback);
}

export function groupAgentEvents(events: AgentEvent[]): AgentTimelineItem[] {
  const items: AgentTimelineItem[] = [];
  const openTools = new Map<string, Array<{ index: number; call: AgentEvent }>>();
  const pairedTools = new Map<string, number>();

  events.forEach((event, index) => {
    const key = eventKey(event, index);
    const type = event.event_type || "";
    const payload = event.payload || {};
    const toolName = String(payload.tool_name || payload.name || payload.title || key);
    const pair = toolPairKey(event, toolName);

    if (type === "tool.call") {
      const pairedIndex = pair.stable ? pairedTools.get(pair.key) : undefined;
      if (pairedIndex !== undefined && items[pairedIndex]?.kind === "step") {
        const current = items[pairedIndex] as Extract<AgentTimelineItem, { kind: "step" }>;
        const call = mergeToolCallEvent(current.call, event);
        items[pairedIndex] = {
          ...current,
          call,
          title: toolTitle(call) || current.title,
          status: stepStatus(call, current.result, current.status),
          time: current.time || eventTime(call),
        };
        return;
      }

      const existingOpen = pair.stable ? latestOpenTool(openTools, pair.key) : null;
      if (existingOpen && items[existingOpen.index]?.kind === "step") {
        const current = items[existingOpen.index] as Extract<AgentTimelineItem, { kind: "step" }>;
        const call = mergeToolCallEvent(current.call, event);
        items[existingOpen.index] = {
          ...current,
          call,
          title: toolTitle(call) || current.title,
          status: stepStatus(call, current.result, current.status),
          time: eventTime(call) || current.time,
        };
        return;
      }

      const item: AgentTimelineItem = {
        id: key,
        kind: "step",
        call: event,
        title: toolTitle(event),
        status: stepStatus(event, undefined),
        time: eventTime(event),
      };
      items.push(item);
      enqueueOpenTool(openTools, pair.key, { index: items.length - 1, call: event });
      return;
    }

    if (type === "tool.result") {
      const pairedIndex = pair.stable ? pairedTools.get(pair.key) : undefined;
      if (pairedIndex !== undefined && items[pairedIndex]?.kind === "step") {
        const current = items[pairedIndex] as Extract<AgentTimelineItem, { kind: "step" }>;
        const result = mergeToolResultEvent(current.result, event);
        items[pairedIndex] = {
          ...current,
          result,
          title: toolTitle(result) || current.title,
          status: stepStatus(current.call, result, current.status),
          time: eventTime(result) || current.time,
        };
        return;
      }

      const open = dequeueOpenTool(openTools, pair.key);
      if (open && items[open.index]?.kind === "step") {
        const current = items[open.index] as Extract<AgentTimelineItem, { kind: "step" }>;
        const result = mergeToolResultEvent(current.result, event);
        items[open.index] = {
          ...current,
          result,
          title: toolTitle(result) || current.title,
          status: stepStatus(current.call, result, current.status),
          time: eventTime(result) || current.time,
        };
        if (pair.stable) pairedTools.set(pair.key, open.index);
        return;
      }
      const status = stepStatus(undefined, event);
      items.push({
        id: key,
        kind: "step",
        result: event,
        title: toolTitle(event),
        status,
        time: eventTime(event),
      });
      if (pair.stable) pairedTools.set(pair.key, items.length - 1);
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

    if (type === "operator.message.received") {
      items.push({
        id: key,
        kind: "state",
        event,
        title: "已收到补充",
        body: displayText(event.content, "补充消息已进入当前任务上下文。"),
        tone: "blue",
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
