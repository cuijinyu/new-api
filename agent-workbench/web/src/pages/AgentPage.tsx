import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  BookMarked,
  Bot,
  Bug,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  Pause,
  Play,
  Receipt,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Star,
  TerminalSquare,
  UploadCloud,
  X,
} from "lucide-react";
import { MarkdownMessage } from "../components/MarkdownMessage";
import { Badge, Button, EmptyState, JsonBlock } from "../components/ui";
import { agentCommandSuggestions, groupAgentEvents, type AgentCommandSuggestion, type AgentTimelineItem } from "../lib/agentWindow";
import {
  billDocumentAmount,
  billDocumentListHint,
  billDocumentTitle,
  billTargetLabel,
  billTypeShort,
  resolveBillDate,
} from "../lib/billLibrary";
import {
  categoryText,
  displayText,
  formatBytes,
  formatDate,
  formatImpact,
  formatMoney,
  shortId,
  statusText,
  statusTone,
} from "../lib/format";
import type { AgentEvent, AgentSession, BillDocument, JsonObject, PageId, SkillPreviewItem, UploadedFile } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

type PanelTab = "resources" | "skills" | "suggestions";
type ResourceView = "attached" | "available" | "outputs";
type ResourceKindFilter = "all" | "billing" | "supplier" | "evidence";
type ResultFileRef = { label?: string; uri?: string; role?: string; path?: string; file_id?: string; filename?: string; byte_size?: number; content_type?: string };

const panelTabs: Array<{ id: PanelTab; label: string }> = [
  { id: "resources", label: "资料" },
  { id: "skills", label: "经验" },
  { id: "suggestions", label: "建议" },
];

const resourceViews: Array<{ id: ResourceView; label: string }> = [
  { id: "attached", label: "已引用" },
  { id: "available", label: "可引用" },
  { id: "outputs", label: "产物" },
];

const resourceKindFilters: Array<{ id: ResourceKindFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "billing", label: "账单" },
  { id: "supplier", label: "供应商" },
  { id: "evidence", label: "凭证" },
];

const sessionStatusFilters = [
  { id: "all", label: "全部" },
  { id: "active", label: "进行中" },
  { id: "paused", label: "暂停" },
  { id: "done", label: "完成" },
  { id: "failed", label: "失败" },
];

function uniqueFiles(files: UploadedFile[]) {
  const seen = new Set<string>();
  return files.filter((file) => {
    if (!file.id || seen.has(file.id)) return false;
    seen.add(file.id);
    return true;
  });
}

function sessionTitle(session: AgentSession) {
  return session.title || displayText(session.prompt || "", shortId(session.id)).slice(0, 64);
}

function eventPayload(event?: AgentEvent) {
  return event?.payload && Object.keys(event.payload).length ? event.payload : null;
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasDetailValue(value: unknown) {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as JsonObject).length > 0;
  return true;
}

function payloadValue(payload: JsonObject | null, keys: string[]) {
  if (!payload) return undefined;
  for (const key of keys) {
    if (hasDetailValue(payload[key])) return payload[key];
  }
  const result = payload.result;
  if (isJsonObject(result)) {
    for (const key of keys) {
      if (hasDetailValue(result[key])) return result[key];
    }
  }
  return undefined;
}

function omitToolLogFields(value: unknown) {
  if (!isJsonObject(value)) return value;
  const logKeys = new Set(["stdout", "stderr", "stdout_tail", "stderr_tail"]);
  const compact = Object.fromEntries(Object.entries(value).filter(([key, item]) => !logKeys.has(key) && hasDetailValue(item)));
  return Object.keys(compact).length ? compact : undefined;
}

function toolArguments(callPayload: JsonObject | null, resultPayload: JsonObject | null) {
  return payloadValue(callPayload, ["arguments", "args", "input", "rawInput", "raw_input", "command", "argv"]) || payloadValue(resultPayload, ["arguments", "args", "input"]);
}

function toolResult(resultPayload: JsonObject | null) {
  const value = payloadValue(resultPayload, ["result", "output", "outputs", "text", "message", "error"]);
  return omitToolLogFields(value);
}

function toolLogValue(payload: JsonObject | null, keys: string[]) {
  const value = payloadValue(payload, keys);
  if (Array.isArray(value)) return value.map((item) => String(item)).join("");
  return value;
}

function commandPreview(value: unknown) {
  if (typeof value === "string") return value;
  if (!isJsonObject(value)) return "";
  if (Array.isArray(value.argv)) return value.argv.map((item) => String(item)).join(" ");
  const direct = value.command || value.cmd || value.script;
  return typeof direct === "string" ? direct : "";
}

function toolMetaChips(item: Extract<AgentTimelineItem, { kind: "step" }>) {
  const callPayload = eventPayload(item.call);
  const resultPayload = eventPayload(item.result);
  const payload = resultPayload || callPayload || {};
  const result = isJsonObject(payload.result) ? payload.result : {};
  const toolName = payload.tool_name || payload.name || payload.title;
  const status = payload.status || item.status;
  const returncode = payload.returncode ?? result.returncode;
  const durationMs = payload.duration_ms;
  const runtime = payload.runtime || payload.agent;
  const attempt = payload.attempt && payload.max_attempts ? `${payload.attempt}/${payload.max_attempts}` : payload.attempt;
  return [
    toolName ? `工具 ${toolName}` : "",
    runtime ? `运行时 ${runtime}` : "",
    status ? `状态 ${status}` : "",
    returncode !== undefined && returncode !== null ? `退出码 ${returncode}` : "",
    durationMs ? `耗时 ${durationMs} ms` : "",
    attempt ? `重试 ${attempt}` : "",
    payload.tool_call_id ? `ID ${shortId(String(payload.tool_call_id))}` : "",
  ].filter(Boolean);
}

function suggestedActionsFromResult(result: WorkbenchState["agentResult"], waitingForInfo: boolean) {
  if (result?.recommended_actions?.length) return result.recommended_actions;
  if (waitingForInfo) return ["补充 Agent 请求的口径、凭证或异常行号，再继续分析。"];
  return ["继续追问差异原因、影响范围或需要补充的凭证。"];
}

function localFileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function mergeLocalFiles(current: File[], incoming: File[]) {
  const seen = new Set(current.map(localFileKey));
  const next = [...current];
  incoming.forEach((file) => {
    const key = localFileKey(file);
    if (seen.has(key)) return;
    seen.add(key);
    next.push(file);
  });
  return next;
}

function dragEventHasFiles(event: DragEvent<HTMLElement>) {
  return Array.from(event.dataTransfer.types || []).includes("Files");
}

function activeBillMentionQuery(message: string) {
  const match = message.match(/(?:^|[\s\n])@([^\s@]*)$/);
  return match ? match[1] : null;
}

function billMentionLabel(document: BillDocument) {
  const date = resolveBillDate(document);
  const period = date.raw || date.monthKey || "unknown";
  const type = billTypeShort(document.bill_type).replace(/\s+/g, "");
  const target = billTargetLabel(document).replace(/\s+/g, "");
  return `@账单:${period}:${type}:${target}`;
}

function replaceActiveBillMention(message: string, mention: string) {
  const match = message.match(/(^|[\s\n])@[^\s@]*$/);
  if (!match) return message.trim() ? `${message.trim()}\n${mention}` : mention;
  const start = match.index ?? 0;
  const prefix = message.slice(0, start);
  const leading = match[1] || "";
  return `${prefix}${leading}${mention} `;
}

function billSearchText(document: BillDocument) {
  const date = resolveBillDate(document);
  return [
    document.id,
    document.bill_type,
    document.status,
    date.raw,
    date.monthKey,
    date.label,
    date.dayLabel,
    billDocumentTitle(document),
    billDocumentListHint(document),
    billTargetLabel(document),
    billTypeShort(document.bill_type),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function resourceKind(file?: UploadedFile): ResourceKindFilter {
  if (!file) return "evidence";
  if (file.category === "billing-result") return "billing";
  if (file.category === "supplier-bill") return "supplier";
  return "evidence";
}

function resourceSearchText(file: UploadedFile) {
  return [file.filename, file.category, file.job_id, file.session_id, file.s3_uri, file.metadata ? JSON.stringify(file.metadata) : ""]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function resourceMeta(file: UploadedFile, attached: boolean) {
  return [categoryText(file.category), file.byte_size ? formatBytes(file.byte_size) : "", attached ? "已在当前任务" : "可加入当前任务"].filter(Boolean).join(" · ");
}

function resultFileName(file: ResultFileRef) {
  if (file.label) return file.label;
  if (file.filename) return file.filename;
  if (file.path) return file.path.split(/[\\/]/).filter(Boolean).pop() || file.path;
  if (file.role) return file.role;
  const name = (file.uri || "").split(/[\\/]/).filter(Boolean).pop();
  return name || "结果文件";
}

export function AgentPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const eventListRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const composerDragDepthRef = useRef(0);
  const [panelTab, setPanelTab] = useState<PanelTab>("resources");
  const [resourceView, setResourceView] = useState<ResourceView>("attached");
  const [resourceQuery, setResourceQuery] = useState("");
  const [resourceKindFilter, setResourceKindFilter] = useState<ResourceKindFilter>("all");
  const [isMobileSessionsOpen, setIsMobileSessionsOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [isMobilePanelOpen, setIsMobilePanelOpen] = useState(false);
  const [isComposerDragActive, setIsComposerDragActive] = useState(false);
  const [isBillPickerOpen, setIsBillPickerOpen] = useState(false);
  const [billPickerQuery, setBillPickerQuery] = useState("");

  const timeline = useMemo(() => groupAgentEvents(wb.agentEvents), [wb.agentEvents]);
  const latestWaitingSeq = Math.max(0, ...wb.agentEvents.filter((event) => event.event_type === "human.input.waiting").map((event) => Number(event.seq || 0)));
  const latestReplySeq = Math.max(
    0,
    ...wb.agentEvents
      .filter((event) => event.event_type === "operator.message.received" || (event.event_type === "message" && event.role === "user"))
      .map((event) => Number(event.seq || 0)),
  );
  const latestRunEndSeq = Math.max(0, ...wb.agentEvents.filter((event) => event.event_type === "run.completed" || event.event_type === "run.error").map((event) => Number(event.seq || 0)));
  const waitingForInfo = latestWaitingSeq > latestReplySeq && latestWaitingSeq > latestRunEndSeq;
  const sessionStatus = wb.currentSession?.status?.toUpperCase() || "";
  const isStreaming = wb.agentStreamActive || wb.pending === "agentStream";
  const currentStatus = isStreaming ? wb.streamStatus : wb.currentSession?.status ? statusText(wb.currentSession.status) : wb.streamStatus;
  const isSendingMessage = wb.pending === "agentMessage";
  const isUploadingContext = wb.pending === "upload";
  const isAgentContextBusy = wb.pending === "agent";
  const hasCompletedRun = latestRunEndSeq > 0 || sessionStatus === "COMPLETED" || sessionStatus === "FAILED";
  const acceptsLiveInput = isStreaming || ["RUNNING", "SANDBOX_READY", "HUMAN_REPLIED"].includes(sessionStatus);
  const canPauseSession = Boolean(wb.agentSessionId && !isAgentContextBusy && ["RUNNING", "SANDBOX_READY", "HUMAN_REPLIED"].includes(sessionStatus));
  const continuationMode = Boolean(wb.agentSessionId && !acceptsLiveInput && (waitingForInfo || hasCompletedRun || sessionStatus === "PAUSED"));
  const composerPlaceholder = acceptsLiveInput
    ? "Agent 正在执行。可以像 Codex 一样随时补充口径、凭证、行号或追问。"
    : waitingForInfo
      ? "补充 Agent 正在等待的口径、凭证或异常行号，发送后会接力继续执行。"
      : continuationMode
        ? "继续追问、补充新凭证或要求 Agent 复核上一轮结论。"
        : "描述你要 Agent 核对的差异、口径或凭证。可输入 @ 引用资料，或输入 / 选择操作。";
  const sendLabel = acceptsLiveInput ? "发送补充" : continuationMode ? "接力继续" : "发送";
  const result = wb.agentResult;
  const outputFiles = useMemo<ResultFileRef[]>(() => {
    const merged: ResultFileRef[] = [];
    const seen = new Set<string>();
    const add = (file: ResultFileRef) => {
      const key = file.file_id || file.uri || file.path || file.filename || file.label || "";
      if (!key || seen.has(key)) return;
      seen.add(key);
      merged.push(file);
    };
    (result?.result_files || []).forEach((file) => add(file));
    wb.agentFiles
      .filter((file) => file.category === "agent-output")
      .forEach((file) =>
        add({
          label: file.filename,
          filename: file.filename,
          file_id: file.id,
          uri: file.s3_uri,
          role: typeof file.metadata?.["role"] === "string" ? file.metadata["role"] : file.category,
          path: typeof file.metadata?.["path"] === "string" ? file.metadata["path"] : undefined,
          byte_size: file.byte_size,
        }),
      );
    return merged;
  }, [result?.result_files, wb.agentFiles]);

  const referenceFiles = useMemo(
    () =>
      wb.uploadedFiles
        .filter((file) => file.category === "billing-result" || file.category === "supplier-bill" || file.category === "reconcile-evidence")
        .slice(0, 80),
    [wb.uploadedFiles],
  );
  const commandSuggestions = useMemo(() => agentCommandSuggestions(wb.agentMessage, referenceFiles, wb.sessions), [wb.agentMessage, referenceFiles, wb.sessions]);
  const attachedContextFiles = useMemo(() => wb.agentFiles.filter((file) => file.category !== "agent-output"), [wb.agentFiles]);
  const attachedFileIds = useMemo(() => new Set(attachedContextFiles.map((file) => file.id)), [attachedContextFiles]);
  const availableFiles = useMemo(() => {
    const query = resourceQuery.trim().toLowerCase();
    return uniqueFiles(referenceFiles)
      .filter((file) => resourceKindFilter === "all" || resourceKind(file) === resourceKindFilter)
      .filter((file) => !query || resourceSearchText(file).includes(query));
  }, [referenceFiles, resourceKindFilter, resourceQuery]);
  // 命令快捷条默认隐藏，只有用户主动输入 @（引用资料）或 /（操作）时才浮现，保持输入区清爽。
  const showCommandStrip = wb.agentMessage.includes("@") || wb.agentMessage.includes("/");
  const recommendedActions = suggestedActionsFromResult(result, waitingForInfo);
  const billPickerDocuments = useMemo(() => {
    const query = billPickerQuery.trim().toLowerCase();
    return wb.billDocuments
      .filter((document) => !query || billSearchText(document).includes(query))
      .sort((a, b) => {
        const da = resolveBillDate(a);
        const db = resolveBillDate(b);
        const dateCompare = (db.raw || db.monthKey).localeCompare(da.raw || da.monthKey);
        if (dateCompare !== 0) return dateCompare;
        return String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""));
      })
      .slice(0, 24);
  }, [wb.billDocuments, billPickerQuery]);

  useEffect(() => {
    void wb.refreshSessions({ selectLatest: true });
    void wb.refreshFiles();
    void wb.refreshSkills();
    void wb.refreshAutomation();
    // Agent 页每次挂载时刷新工作窗口数据。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 根据当前会话（供应商/账期）与排除项，预览本次将注入的经验/技能。
  const sessionVendor = wb.currentSession?.vendor;
  const sessionMonth = wb.currentSession?.month;
  useEffect(() => {
    void wb.previewSkills({ vendor: sessionVendor, month: sessionMonth, excluded: wb.excludedSkillIds });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionVendor, sessionMonth, wb.excludedSkillIds, wb.skills.length]);

  useEffect(() => {
    if (eventListRef.current) {
      eventListRef.current.scrollTop = eventListRef.current.scrollHeight;
    }
  }, [timeline.length]);

  function appendPrompt(text: string) {
    wb.setAgentMessage((prev) => (prev.trim() ? `${prev.trim()}\n${text}` : text));
  }

  function applyFilter() {
    void wb.refreshSessions({ filter: wb.sessionFilter });
  }

  function startNewTask() {
    wb.startNewAgentTask();
    wb.setExcludedSkillIds([]);
    setIsMobileSessionsOpen(false);
  }

  // 勾除/恢复某条经验：更新排除集合，已有会话即时落库。
  async function toggleSkillExclusion(skillId: string) {
    const next = wb.excludedSkillIds.includes(skillId)
      ? wb.excludedSkillIds.filter((id) => id !== skillId)
      : [...wb.excludedSkillIds, skillId];
    wb.setExcludedSkillIds(next);
    if (wb.agentSessionId) await wb.saveAgentSkillExclusions(wb.agentSessionId, next);
  }

  function addSelectedFiles(files: File[]) {
    if (!files.length) return;
    wb.setAgentSelectedFiles((prev) => mergeLocalFiles(prev, files));
    composerTextareaRef.current?.focus();
  }

  function handleComposerDragEnter(event: DragEvent<HTMLElement>) {
    if (!dragEventHasFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    composerDragDepthRef.current += 1;
    setIsComposerDragActive(true);
  }

  function handleComposerDragOver(event: DragEvent<HTMLElement>) {
    if (!dragEventHasFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setIsComposerDragActive(true);
  }

  function handleComposerDragLeave(event: DragEvent<HTMLElement>) {
    if (!dragEventHasFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    composerDragDepthRef.current = Math.max(0, composerDragDepthRef.current - 1);
    if (composerDragDepthRef.current === 0) setIsComposerDragActive(false);
  }

  function handleComposerDrop(event: DragEvent<HTMLElement>) {
    if (!dragEventHasFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    composerDragDepthRef.current = 0;
    setIsComposerDragActive(false);
    addSelectedFiles(Array.from(event.dataTransfer.files || []));
  }

  function handleAgentMessageChange(value: string) {
    wb.setAgentMessage(value);
    const mentionQuery = activeBillMentionQuery(value);
    if (mentionQuery !== null) {
      setBillPickerQuery(mentionQuery);
      setIsBillPickerOpen(true);
    }
  }

  async function submitComposerMessage() {
    const text = (composerTextareaRef.current?.value ?? wb.agentMessage).trim();
    if (!text) return;
    let targetSessionId: string | null = null;
    if (wb.agentSelectedFiles.length) {
      targetSessionId = await wb.uploadAgentFiles();
      if (!targetSessionId) return;
    }
    void wb.sendAndStream(text, targetSessionId || undefined);
  }

  async function selectSession(id: string) {
    await wb.selectSession(id);
    setIsMobileSessionsOpen(false);
  }

  async function applyCommandSuggestion(suggestion: AgentCommandSuggestion) {
    if (suggestion.action === "governance") {
      switchPage("governance");
      return;
    }
    if (suggestion.fileIds?.length) {
      await wb.referenceFilesToAgent(suggestion.fileIds);
      setPanelTab("resources");
    }
    if (suggestion.insertText) appendPrompt(suggestion.insertText);
  }

  async function referenceFile(fileId: string) {
    await wb.referenceFilesToAgent([fileId]);
    setPanelTab("resources");
  }

  async function referenceBillDocument(document: BillDocument) {
    const sessionId = await wb.referenceBillDocumentToAgent(document.id);
    if (!sessionId) return;
    wb.setAgentMessage((prev) => replaceActiveBillMention(prev, billMentionLabel(document)));
    setPanelTab("resources");
    setIsBillPickerOpen(false);
    setBillPickerQuery("");
  }

  return (
    <div className="agent-window">
      <div className="agent-window-mobile-bar">
        <Button variant="outline" size="sm" onClick={() => setIsMobileSessionsOpen((value) => !value)}>
          任务列表
        </Button>
        <Button variant="outline" size="sm" onClick={() => setIsMobilePanelOpen((value) => !value)}>
          上下文面板
        </Button>
      </div>

      <aside className={`agent-task-sidebar ${isMobileSessionsOpen ? "open" : ""} ${sidebarCollapsed ? "collapsed" : ""}`}>
        {sidebarCollapsed ? (
          <div className="agent-sidebar-rail">
            <Button variant="ghost" size="icon" aria-label="展开任务列表" onClick={() => setSidebarCollapsed(false)}>
              <PanelLeftOpen size={16} />
            </Button>
            <Button variant="secondary" size="icon" aria-label="新建任务" onClick={startNewTask}>
              <MessageSquarePlus size={16} />
            </Button>
            <span className="agent-sidebar-rail-count" title={`${wb.sessions.length} 个会话`}>
              {wb.sessions.length}
            </span>
          </div>
        ) : (
          <>
        <div className="agent-pane-head">
          <div>
            <span>对账任务</span>
            <strong>{wb.sessions.length} 个会话</strong>
          </div>
          <div className="agent-pane-head-actions">
            <Button variant="secondary" size="sm" onClick={startNewTask}>
              <MessageSquarePlus size={14} />
              新建任务
            </Button>
            <Button variant="ghost" size="icon" aria-label="收起任务列表" onClick={() => setSidebarCollapsed(true)}>
              <PanelLeftClose size={16} />
            </Button>
          </div>
        </div>

        <div className="agent-search-box">
          <input
            value={wb.sessionFilter.q}
            onChange={(event) => wb.setSessionFilter((prev) => ({ ...prev, q: event.target.value }))}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyFilter();
            }}
            placeholder="搜索任务、供应商或经验"
          />
          <Button variant="ghost" size="icon" onClick={applyFilter} disabled={wb.pending === "agent"}>
            <RefreshCw size={15} />
          </Button>
        </div>

        <div className="agent-status-filter-row" role="group" aria-label="任务状态筛选">
          {sessionStatusFilters.map((filter) => (
            <button
              key={filter.id}
              type="button"
              className={wb.sessionFilter.status === filter.id ? "active" : ""}
              onClick={() => {
                const nextFilter = { ...wb.sessionFilter, status: filter.id };
                wb.setSessionFilter(nextFilter);
                void wb.refreshSessions({ filter: nextFilter });
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <label className="agent-favorite-filter">
          <input
            type="checkbox"
            checked={wb.sessionFilter.favorite}
            onChange={(event) => {
              const favorite = event.target.checked;
              const nextFilter = { ...wb.sessionFilter, favorite };
              wb.setSessionFilter(nextFilter);
              void wb.refreshSessions({ filter: nextFilter });
            }}
          />
          只看收藏任务
        </label>

        <div className="agent-task-list">
          {wb.sessions.map((session) => (
            <div
              role="button"
              tabIndex={0}
              className={`agent-task-item ${wb.agentSessionId === session.id ? "active" : ""}`}
              key={session.id}
              onClick={() => void selectSession(session.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  void selectSession(session.id);
                }
              }}
            >
              <span className="agent-task-title">{sessionTitle(session)}</span>
              <span className="agent-task-prompt">{displayText(session.prompt || "", "暂无任务描述").slice(0, 82)}</span>
              <span className="agent-task-meta">
                <Badge tone={statusTone(session.status)}>{statusText(session.status)}</Badge>
                <small>{formatDate(session.updated_at || session.created_at)}</small>
              </span>
              <span className="agent-task-actions">
                <button
                  type="button"
                  className={`agent-star-button ${session.favorite ? "active" : ""}`}
                  aria-label={session.favorite ? "取消收藏" : "收藏任务"}
                  onClick={(event) => {
                    event.stopPropagation();
                    void wb.favoriteSession(session.id, !session.favorite);
                  }}
                >
                  <Star size={14} fill={session.favorite ? "currentColor" : "none"} />
                </button>
                <small>{shortId(session.id)}</small>
              </span>
            </div>
          ))}
          {!wb.sessions.length ? <EmptyState title="暂无任务" hint="输入问题后会自动创建一个对账任务窗口。" /> : null}
        </div>
          </>
        )}
      </aside>

      <main className="agent-workspace">
        <header className="agent-run-header">
          <div className="agent-run-title">
            <div className="agent-run-icon">
              <Bot size={18} />
            </div>
            <div>
              <span>当前任务</span>
              <strong>{wb.currentSession ? sessionTitle(wb.currentSession) : "新的对账任务"}</strong>
            </div>
          </div>
          <div className="agent-run-actions">
            <Badge tone={statusTone(wb.currentSession?.status || wb.streamStatus)}>{currentStatus}</Badge>
            {canPauseSession ? (
              <Button variant="outline" size="sm" onClick={() => wb.pauseSession(wb.agentSessionId)} disabled={wb.pending === "agentPause"}>
                {wb.pending === "agentPause" ? <Loader2 size={14} className="spin" /> : <Pause size={14} />}
                暂停
              </Button>
            ) : null}
            {wb.agentSessionId && sessionStatus === "PAUSED" ? (
              <Button variant="outline" size="sm" onClick={() => wb.resumeSession(wb.agentSessionId)} disabled={wb.pending === "agentResume"}>
                {wb.pending === "agentResume" ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
                继续
              </Button>
            ) : null}
            <Button
              variant={showDebug ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setShowDebug((value) => !value)}
              title="显示/隐藏每条消息的事件与步骤详情"
            >
              <Bug size={14} />
              调试
            </Button>
          </div>
        </header>

        <section className="agent-timeline" ref={eventListRef}>
          {timeline.length ? timeline.map((item) => <TimelineItem key={item.id} item={item} showDebug={showDebug} />) : <AgentEmptyState onPrompt={appendPrompt} />}
          {result?.summary || result?.reason ? (
            <div className="agent-final-summary">
              <div className="agent-final-summary-head">
                <CheckCircle2 size={18} />
                <strong>本轮结论</strong>
              </div>
              <MarkdownMessage content={displayText(result.reason || result.summary)} />
            </div>
          ) : null}
        </section>

        <footer
          className={`agent-composer-shell ${isComposerDragActive ? "drag-active" : ""}`}
          onDragEnter={handleComposerDragEnter}
          onDragOver={handleComposerDragOver}
          onDragLeave={handleComposerDragLeave}
          onDrop={handleComposerDrop}
        >
          {acceptsLiveInput ? (
            <div className="agent-handoff-banner">
              <Sparkles size={15} />
              <span>Agent 正在执行，可以继续发送补充信息；新消息会进入当前任务上下文。</span>
            </div>
          ) : continuationMode ? (
            <div className="agent-handoff-banner">
              <Sparkles size={15} />
              <span>{waitingForInfo ? "Agent 正在等待人工补充，发送后会接力继续。" : "本轮沙箱执行已结束，可以带着历史上下文继续追问。"}</span>
            </div>
          ) : null}
          {showCommandStrip ? (
            <div className="agent-command-strip">
              {commandSuggestions.map((suggestion) => (
                <button key={suggestion.id} type="button" onClick={() => void applyCommandSuggestion(suggestion)} disabled={!suggestion.fileIds?.length && suggestion.id.includes("bill")}>
                  <strong>{suggestion.label}</strong>
                  <span>{suggestion.description}</span>
                </button>
              ))}
            </div>
          ) : null}
          {isBillPickerOpen ? (
            <BillPickerPopover
              documents={billPickerDocuments}
              query={billPickerQuery}
              busy={wb.pending === "agent"}
              onQueryChange={setBillPickerQuery}
              onClose={() => setIsBillPickerOpen(false)}
              onRefresh={() => void wb.refreshAutomation()}
              onSelect={(document) => void referenceBillDocument(document)}
            />
          ) : null}
          {isComposerDragActive ? (
            <div className="agent-composer-drop-hint">
              <UploadCloud size={18} />
              <span>松开后把文件加入这次 Agent 上下文</span>
            </div>
          ) : null}
          <div className="agent-composer">
            <button type="button" className="agent-icon-button" aria-label="选择附件" onClick={() => fileInputRef.current?.click()}>
              <Paperclip size={18} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="agent-hidden-file"
              onChange={(event) => {
                addSelectedFiles(Array.from(event.target.files || []));
                event.currentTarget.value = "";
              }}
            />
            <textarea
              ref={composerTextareaRef}
              value={wb.agentMessage}
              onChange={(event) => handleAgentMessageChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  submitComposerMessage();
                }
              }}
              placeholder={composerPlaceholder}
            />
            <div className="agent-composer-buttons">
              {wb.agentSelectedFiles.length ? (
                <Button variant="outline" onClick={wb.uploadAgentFiles} disabled={wb.pending === "upload" || wb.pending === "agent"}>
                  {wb.pending === "upload" || wb.pending === "agent" ? <Loader2 size={15} className="spin" /> : <UploadCloud size={15} />}
                  加入上下文
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => {
                    setBillPickerQuery("");
                    setIsBillPickerOpen(true);
                    if (!wb.billDocuments.length) void wb.refreshAutomation();
                  }}
                  disabled={isAgentContextBusy}
                >
                  <Receipt size={15} />
                  账单库
                </Button>
              )}
              <Button onClick={submitComposerMessage} disabled={!wb.agentMessage.trim() || isSendingMessage || isUploadingContext || isAgentContextBusy}>
                {isSendingMessage || isUploadingContext || isAgentContextBusy ? <Loader2 size={15} className="spin" /> : <Send size={15} />}
                {sendLabel}
              </Button>
            </div>
          </div>
          {wb.agentSelectedFiles.length ? (
            <div className="agent-selected-files">
              {wb.agentSelectedFiles.map((file) => (
                <span className="agent-selected-file-chip" key={localFileKey(file)}>
                  <span>
                    {file.name} · {formatBytes(file.size)}
                  </span>
                  <button
                    type="button"
                    aria-label={`移除 ${file.name}`}
                    onClick={() => wb.setAgentSelectedFiles((prev) => prev.filter((item) => localFileKey(item) !== localFileKey(file)))}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          ) : null}
        </footer>
      </main>

      <aside className={`agent-context-panel ${isMobilePanelOpen ? "open" : ""}`}>
        <div className="agent-panel-tabs">
          {panelTabs.map((tab) => (
            <button key={tab.id} type="button" className={panelTab === tab.id ? "active" : ""} onClick={() => setPanelTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>
        <div className="agent-panel-body">
          {panelTab === "resources" ? (
            <ResourceTray
              session={wb.currentSession}
              activeView={resourceView}
              onViewChange={setResourceView}
              attachedFiles={attachedContextFiles}
              attachedFileIds={attachedFileIds}
              availableFiles={availableFiles}
              availableTotal={referenceFiles.length}
              resultFiles={outputFiles}
              query={resourceQuery}
              onQueryChange={setResourceQuery}
              kindFilter={resourceKindFilter}
              onKindFilterChange={setResourceKindFilter}
              onReferenceFile={referenceFile}
              onDownloadFile={wb.downloadFile}
              onDownloadArtifact={wb.downloadArtifact}
            />
          ) : null}
          {panelTab === "skills" ? (
            <SkillsPanel
              preview={wb.skillPreview}
              excludedIds={wb.excludedSkillIds}
              onToggle={toggleSkillExclusion}
              onManage={() => switchPage("governance")}
            />
          ) : null}
          {panelTab === "suggestions" ? (
            <SuggestionsPanel
              result={result}
              recommendedActions={recommendedActions}
              waitingForInfo={waitingForInfo}
              onOpenGovernance={() => switchPage("governance")}
            />
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function BillPickerPopover({
  documents,
  query,
  busy,
  onQueryChange,
  onClose,
  onRefresh,
  onSelect,
}: {
  documents: BillDocument[];
  query: string;
  busy: boolean;
  onQueryChange: (value: string) => void;
  onClose: () => void;
  onRefresh: () => void;
  onSelect: (document: BillDocument) => void;
}) {
  return (
    <div className="agent-bill-picker" role="dialog" aria-label="引用账单库账单">
      <div className="agent-bill-picker-head">
        <div>
          <strong>引用账单库</strong>
          <span>选择账单后会把汇总、Excel 和可用日志挂到当前 Agent 会话</span>
        </div>
        <button type="button" aria-label="关闭账单选择" onClick={onClose}>
          <X size={16} />
        </button>
      </div>
      <label className="agent-bill-search">
        <Search size={15} />
        <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索账期、客户、渠道或账单类型" autoFocus />
      </label>
      <div className="agent-bill-list">
        {documents.map((document) => {
          const amount = billDocumentAmount(document);
          const date = resolveBillDate(document);
          return (
            <button type="button" className="agent-bill-row" key={document.id} onClick={() => onSelect(document)} disabled={busy}>
              <Receipt size={16} />
              <span>
                <strong>{billDocumentTitle(document)}</strong>
                <small>
                  {billDocumentListHint(document)} · {date.raw || date.monthKey || "未标账期"} · {shortId(document.id)}
                </small>
              </span>
              <span className="agent-bill-row-side">
                <Badge tone={statusTone(document.status)}>{statusText(document.status)}</Badge>
                <small title={amount.label}>{formatMoney(amount.amount)}</small>
              </span>
            </button>
          );
        })}
        {!documents.length ? (
          <EmptyState title={query ? "没有匹配账单" : "账单库暂无账单"} hint={query ? "换一个账期、客户号、渠道号或账单类型再试。" : "刷新账单库，或先在出账/自动化里生成账单。"} />
        ) : null}
      </div>
      <div className="agent-bill-picker-foot">
        <Button variant="ghost" size="sm" onClick={onRefresh}>
          <RefreshCw size={14} />
          刷新账单库
        </Button>
      </div>
    </div>
  );
}

function ToolValueBlock({ value, empty }: { value: unknown; empty: string }) {
  if (!hasDetailValue(value)) return <pre className="json-block agent-tool-text-block">{empty}</pre>;
  if (typeof value === "string") return <pre className="json-block agent-tool-text-block">{value}</pre>;
  return <JsonBlock value={value} empty={empty} />;
}

function ToolDetailSection({ label, value, empty }: { label: string; value: unknown; empty: string }) {
  if (!hasDetailValue(value)) return null;
  return (
    <section className="agent-tool-detail-section">
      <strong>{label}</strong>
      <ToolValueBlock value={value} empty={empty} />
    </section>
  );
}

function ToolCallDetails({ item, showRaw }: { item: Extract<AgentTimelineItem, { kind: "step" }>; showRaw: boolean }) {
  const callPayload = eventPayload(item.call);
  const resultPayload = eventPayload(item.result);
  const args = toolArguments(callPayload, resultPayload);
  const result = toolResult(resultPayload);
  const stdout = toolLogValue(resultPayload, ["stdout_tail", "stdout"]);
  const stderr = toolLogValue(resultPayload, ["stderr_tail", "stderr"]);
  const error = !hasDetailValue(stderr) ? toolLogValue(resultPayload, ["error", "error_message", "message"]) : undefined;
  const raw = { call: callPayload, result: resultPayload };
  const command = commandPreview(args);
  const chips = toolMetaChips(item);
  const hasVisibleDetail = chips.length || hasDetailValue(args) || hasDetailValue(result) || hasDetailValue(stdout) || hasDetailValue(stderr) || hasDetailValue(error) || showRaw;

  if (!hasVisibleDetail) return null;

  return (
    <details className="agent-tool-details">
      <summary>
        <span>查看 tool call 详情</span>
        <small>{item.result ? "参数、结果和日志" : "参数和运行状态"}</small>
      </summary>
      <div className="agent-tool-detail-body">
        {chips.length ? (
          <div className="agent-tool-detail-meta">
            {chips.map((chip) => (
              <span key={chip}>{chip}</span>
            ))}
          </div>
        ) : null}
        {command ? (
          <div className="agent-tool-command">
            <TerminalSquare size={14} />
            <code>{command}</code>
          </div>
        ) : null}
        <ToolDetailSection label="调用参数" value={args} empty="暂无调用参数" />
        <ToolDetailSection label="执行结果" value={result} empty="暂无执行结果" />
        <ToolDetailSection label="stdout" value={stdout} empty="暂无 stdout" />
        <ToolDetailSection label="stderr" value={stderr || error} empty="暂无 stderr" />
        {showRaw ? <ToolDetailSection label="原始事件" value={raw} empty="暂无原始事件" /> : null}
      </div>
    </details>
  );
}

function TimelineItem({ item, showDebug }: { item: AgentTimelineItem; showDebug: boolean }) {
  if (item.kind === "step") {
    const description = displayText(
      item.result?.content || item.call?.content,
      item.status === "completed" ? "Agent 已完成这一步检查。" : "Agent 正在核对相关资料。",
    );
    return (
      <article className={`agent-timeline-item agent-step ${item.status}`}>
        <div className="agent-timeline-marker">
          {item.status === "completed" ? <CheckCircle2 size={16} /> : <Loader2 size={16} className="spin" />}
        </div>
        <div className="agent-timeline-content">
          <div className="agent-timeline-head">
            <strong>{item.title}</strong>
            <span>{item.status === "completed" ? "已完成" : "运行中"} {item.time ? `· ${item.time}` : ""}</span>
          </div>
          <p>{description}</p>
          <ToolCallDetails item={item} showRaw={showDebug} />
        </div>
      </article>
    );
  }

  if (item.kind === "state") {
    return (
      <article className={`agent-timeline-item agent-state agent-state-${item.tone}`}>
        <div className="agent-timeline-marker">
          <Sparkles size={16} />
        </div>
        <div className="agent-timeline-content">
          <div className="agent-timeline-head">
            <strong>{item.title}</strong>
            <span>{item.time}</span>
          </div>
          <MarkdownMessage content={displayText(item.body)} />
          {showDebug && eventPayload(item.event) ? (
            <details>
              <summary>查看事件详情</summary>
              <JsonBlock value={item.event.payload} empty="暂无事件详情" />
            </details>
          ) : null}
        </div>
      </article>
    );
  }

  return (
    <article className={`agent-timeline-item agent-${item.kind}`}>
      <div className="agent-timeline-marker">
        {item.kind === "message" ? <TerminalSquare size={16} /> : <Bot size={16} />}
      </div>
      <div className="agent-timeline-content">
          <div className="agent-timeline-head">
            <strong>{item.title}</strong>
            <span>{item.time}</span>
          </div>
        {item.kind === "assistant" ? <MarkdownMessage content={displayText(item.body)} /> : <p>{item.body}</p>}
        {showDebug && eventPayload(item.event) ? (
          <details>
            <summary>查看事件详情</summary>
            <JsonBlock value={item.event.payload} empty="暂无事件详情" />
          </details>
        ) : null}
      </div>
    </article>
  );
}

function AgentEmptyState({ onPrompt }: { onPrompt: (text: string) => void }) {
  const examples = [
    "先判断供应商账单和内部账单的差异来自哪里。",
    "检查本月渠道折扣是否影响对账结论。",
    "列出还缺哪些凭证，再开始给结论。",
  ];
  return (
    <div className="agent-empty-run">
      <Bot size={30} />
      <strong>像启动一个 Codex 任务一样开始对账</strong>
      <span>输入目标，Agent 会自动建立会话、读取上下文、展示检查步骤和最终结论。</span>
      <div>
        {examples.map((example) => (
          <button key={example} type="button" onClick={() => onPrompt(example)}>
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}

function ResourceTray({
  session,
  activeView,
  onViewChange,
  attachedFiles,
  attachedFileIds,
  availableFiles,
  availableTotal,
  resultFiles,
  query,
  onQueryChange,
  kindFilter,
  onKindFilterChange,
  onReferenceFile,
  onDownloadFile,
  onDownloadArtifact,
}: {
  session?: AgentSession | null;
  activeView: ResourceView;
  onViewChange: (view: ResourceView) => void;
  attachedFiles: UploadedFile[];
  attachedFileIds: Set<string>;
  availableFiles: UploadedFile[];
  availableTotal: number;
  resultFiles: ResultFileRef[];
  query: string;
  onQueryChange: (value: string) => void;
  kindFilter: ResourceKindFilter;
  onKindFilterChange: (value: ResourceKindFilter) => void;
  onReferenceFile: (fileId: string) => void;
  onDownloadFile: (fileId: string, filename?: string) => void;
  onDownloadArtifact: (params: { fileId?: string; uri?: string; filename?: string }) => void;
}) {
  const billingCount = attachedFiles.filter((file) => resourceKind(file) === "billing").length;
  const supplierCount = attachedFiles.filter((file) => resourceKind(file) === "supplier").length;
  const evidenceCount = attachedFiles.filter((file) => resourceKind(file) === "evidence").length;

  return (
    <div className="agent-resource-tray">
      <div className="agent-context-summary">
        <span>当前任务资料</span>
        <strong>{attachedFiles.length ? `已引用 ${attachedFiles.length} 个资料` : "还没有引用资料"}</strong>
        <div>
          <Badge tone={billingCount ? "green" : "default"}>账单 {billingCount}</Badge>
          <Badge tone={supplierCount ? "blue" : "default"}>供应商 {supplierCount}</Badge>
          <Badge tone={evidenceCount ? "amber" : "default"}>凭证 {evidenceCount}</Badge>
        </div>
        {session ? <small>{session.vendor || "未指定供应商"} · {session.month || "未指定账期"} · {statusText(session.status)}</small> : null}
      </div>

      <div className="agent-resource-tabs">
        {resourceViews.map((view) => (
          <button key={view.id} type="button" className={activeView === view.id ? "active" : ""} onClick={() => onViewChange(view.id)}>
            {view.label}
          </button>
        ))}
      </div>

      {activeView === "available" ? (
        <div className="agent-resource-filter">
          <label>
            <Search size={14} />
            <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="搜索文件名、账期、供应商或渠道" />
          </label>
          <div>
            {resourceKindFilters.map((filter) => (
              <button key={filter.id} type="button" className={kindFilter === filter.id ? "active" : ""} onClick={() => onKindFilterChange(filter.id)}>
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="agent-resource-list">
        {activeView === "attached" ? (
          attachedFiles.length ? (
            attachedFiles.map((file) => <AttachedResourceRow key={file.id} file={file} />)
          ) : (
            <EmptyState title="暂无已引用资料" hint="从“可引用”或账单库选择资料后，会显示在这里。" />
          )
        ) : null}

        {activeView === "available" ? (
          availableFiles.length ? (
            availableFiles.map((file) => (
              <AvailableResourceRow key={file.id} file={file} attached={attachedFileIds.has(file.id)} onReferenceFile={onReferenceFile} />
            ))
          ) : (
            <EmptyState title={availableTotal ? "没有匹配资料" : "暂无可引用资料"} hint={availableTotal ? "换个关键词或类型再试。" : "先在账单库、生成账单或资料库上传文件。"} />
          )
        ) : null}

        {activeView === "outputs" ? (
          resultFiles.length ? (
            resultFiles.map((file, index) => (
              <ResultResourceRow
                file={file}
                key={`${file.file_id || file.uri || file.path || file.label || file.role}-${index}`}
                onDownloadFile={onDownloadFile}
                onDownloadArtifact={onDownloadArtifact}
              />
            ))
          ) : (
            <EmptyState title="暂无结果产物" hint="任务完成后会显示报告、结果 JSON 或建议文件。" />
          )
        ) : null}
      </div>
    </div>
  );
}

function AttachedResourceRow({ file }: { file: UploadedFile }) {
  return (
    <div className="agent-resource-row attached">
      <FileText size={16} />
      <span>
        <strong>{file.filename}</strong>
        <small>{resourceMeta(file, true)}</small>
      </span>
      <Badge tone={resourceKind(file) === "billing" ? "green" : "blue"}>{categoryText(file.category)}</Badge>
    </div>
  );
}

function AvailableResourceRow({ file, attached, onReferenceFile }: { file: UploadedFile; attached: boolean; onReferenceFile: (fileId: string) => void }) {
  return (
    <button className={`agent-resource-row available ${attached ? "attached" : ""}`} type="button" onClick={() => onReferenceFile(file.id)} disabled={attached}>
      <FileText size={16} />
      <span>
        <strong>{file.filename}</strong>
        <small>{resourceMeta(file, attached)}</small>
      </span>
      <Badge tone={attached ? "green" : resourceKind(file) === "billing" ? "green" : "blue"}>{attached ? "已引用" : "引用"}</Badge>
    </button>
  );
}

function ResultResourceRow({
  file,
  onDownloadFile,
  onDownloadArtifact,
}: {
  file: ResultFileRef;
  onDownloadFile: (fileId: string, filename?: string) => void;
  onDownloadArtifact: (params: { fileId?: string; uri?: string; filename?: string }) => void;
}) {
  const filename = file.filename || resultFileName(file);
  const canDownload = Boolean(file.file_id || file.uri);
  const download = () => {
    if (file.file_id) {
      onDownloadFile(file.file_id, filename);
      return;
    }
    if (file.uri) onDownloadArtifact({ uri: file.uri, filename });
  };
  return (
    <div className="agent-resource-row output">
      <FileText size={16} />
      <span>
        <strong>{resultFileName(file)}</strong>
        <small>{[file.role || "任务产物", file.path, file.byte_size ? formatBytes(file.byte_size) : ""].filter(Boolean).join(" · ")}</small>
      </span>
      <Badge tone="blue">产物</Badge>
      <button type="button" className="agent-output-download" onClick={download} disabled={!canDownload} aria-label={`下载 ${filename}`}>
        <Download size={14} />
      </button>
    </div>
  );
}

function SkillsPanel({
  preview,
  excludedIds,
  onToggle,
  onManage,
}: {
  preview: SkillPreviewItem[];
  excludedIds: string[];
  onToggle: (id: string) => void;
  onManage: () => void;
}) {
  return (
    <div className="agent-panel-stack">
      <div className="agent-panel-section">
        <div className="agent-skill-head">
          <h3>将注入的经验</h3>
          <Button variant="ghost" size="sm" onClick={onManage}>
            <BookMarked size={14} />
            管理经验库
          </Button>
        </div>
        <p className="agent-skill-hint">
          启用的经验按当前会话的供应商 / 账期相关性排序自动注入对账 Agent。取消勾选可在本次会话排除某条经验。
        </p>
        {preview.map((skill) => {
          const excluded = excludedIds.includes(skill.id);
          return (
            <label className={`agent-skill-row ${excluded ? "excluded" : ""}`} key={skill.id}>
              <input type="checkbox" checked={!excluded} onChange={() => onToggle(skill.id)} />
              <span className="agent-skill-main">
                <strong>{skill.name}</strong>
                <small>
                  {(skill.vendor && skill.vendor !== "*" ? skill.vendor : "全部供应商")} · {skill.version || "v1"} · 相关度 {skill.score ?? 0}
                </small>
              </span>
              {(skill.tags || []).slice(0, 2).map((tag) => (
                <Badge tone="blue" key={tag}>
                  {tag}
                </Badge>
              ))}
            </label>
          );
        })}
        {!preview.length ? <EmptyState icon={<BookMarked size={24} />} title="暂无可注入经验" hint="在经验库新建并启用经验后，会按相关性自动注入到这里。" /> : null}
      </div>
    </div>
  );
}

function SuggestionsPanel({
  result,
  recommendedActions,
  waitingForInfo,
  onOpenGovernance,
}: {
  result: WorkbenchState["agentResult"];
  recommendedActions: string[];
  waitingForInfo: boolean;
  onOpenGovernance: () => void;
}) {
  return (
    <div className="agent-panel-stack">
      <div className="agent-suggestion-card">
        <span>结论</span>
        <MarkdownMessage
          content={displayText(result?.reason || result?.summary, waitingForInfo ? "Agent 正在等待补充资料。" : "任务完成后会汇总差异原因和处理建议。")}
        />
      </div>
      <div className="agent-impact-grid">
        <div>
          <span>影响金额</span>
          <strong>{formatImpact(result?.impact)}</strong>
        </div>
        <div>
          <span>建议状态</span>
          <strong>{result?.suggestion_ready ? "可处理" : waitingForInfo ? "待补充" : "分析中"}</strong>
        </div>
      </div>
      <div className="agent-panel-section">
        <h3>建议动作</h3>
        <ul className="agent-action-list">
          {recommendedActions.map((action, index) => (
            <li key={index}>
              <MarkdownMessage className="agent-markdown-compact" content={displayText(action)} />
            </li>
          ))}
        </ul>
      </div>
      {result?.saveable_experience ? (
        <div className="agent-suggestion-card">
          <span>可沉淀经验</span>
          <MarkdownMessage content={displayText(result.saveable_experience)} />
        </div>
      ) : null}
      {(result?.change_request_id || result?.suggestion_ready || result?.config_change) ? (
        <Button onClick={onOpenGovernance}>
          <Sparkles size={15} />
          去处理建议
        </Button>
      ) : null}
    </div>
  );
}
