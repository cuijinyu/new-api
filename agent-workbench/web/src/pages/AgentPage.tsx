import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  BookMarked,
  Bot,
  Bug,
  CheckCircle2,
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
import { agentCommandSuggestions, buildContextItems, groupAgentEvents, type AgentCommandSuggestion, type AgentTimelineItem } from "../lib/agentWindow";
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
  fileDirectory,
  formatBytes,
  formatDate,
  formatImpact,
  formatMoney,
  shortId,
  statusText,
  statusTone,
} from "../lib/format";
import type { AgentEvent, AgentSession, BillDocument, PageId, SkillPreviewItem, UploadedFile } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

type PanelTab = "resources" | "skills" | "suggestions";

const panelTabs: Array<{ id: PanelTab; label: string }> = [
  { id: "resources", label: "资料" },
  { id: "skills", label: "经验注入" },
  { id: "suggestions", label: "建议" },
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

function stepPayload(item: Extract<AgentTimelineItem, { kind: "step" }>) {
  return item.result?.payload || item.call?.payload || null;
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

export function AgentPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const eventListRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const composerDragDepthRef = useRef(0);
  const [panelTab, setPanelTab] = useState<PanelTab>("resources");
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
  const currentStatus = wb.currentSession?.status ? statusText(wb.currentSession.status) : wb.streamStatus;
  const isStreaming = wb.pending === "agentStream" || wb.pending === "agentMessage" || wb.pending === "agent";
  const hasCompletedRun = latestRunEndSeq > 0 || sessionStatus === "COMPLETED" || sessionStatus === "FAILED";
  const canPauseSession = Boolean(wb.agentSessionId && !isStreaming && ["RUNNING", "SANDBOX_READY", "HUMAN_REPLIED"].includes(sessionStatus));
  const continuationMode = Boolean(wb.agentSessionId && !isStreaming && (waitingForInfo || hasCompletedRun || sessionStatus === "PAUSED"));
  const composerPlaceholder = waitingForInfo
    ? "补充 Agent 正在等待的口径、凭证或异常行号，发送后会接力继续执行。"
    : continuationMode
      ? "继续追问、补充新凭证或要求 Agent 复核上一轮结论。"
      : "描述你要 Agent 核对的差异、口径或凭证。可输入 @ 引用资料，或输入 / 选择操作。";
  const sendLabel = continuationMode ? "接力继续" : "发送";
  const result = wb.agentResult;

  const referenceFiles = useMemo(
    () =>
      wb.uploadedFiles
        .filter((file) => file.category === "billing-result" || file.category === "supplier-bill" || file.category === "reconcile-evidence")
        .slice(0, 18),
    [wb.uploadedFiles],
  );
  const contextFiles = useMemo(() => uniqueFiles([...wb.agentFiles, ...referenceFiles]), [wb.agentFiles, referenceFiles]);
  const contextItems = useMemo(() => buildContextItems(contextFiles, wb.sessions, wb.currentSession), [contextFiles, wb.sessions, wb.currentSession]);
  const commandSuggestions = useMemo(() => agentCommandSuggestions(wb.agentMessage, referenceFiles, wb.sessions), [wb.agentMessage, referenceFiles, wb.sessions]);
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

        <div className="agent-filter-row">
          <input
            value={wb.sessionFilter.vendor}
            onChange={(event) => wb.setSessionFilter((prev) => ({ ...prev, vendor: event.target.value }))}
            onKeyDown={(event) => event.key === "Enter" && applyFilter()}
            placeholder="供应商"
          />
          <input
            value={wb.sessionFilter.month}
            onChange={(event) => wb.setSessionFilter((prev) => ({ ...prev, month: event.target.value }))}
            onKeyDown={(event) => event.key === "Enter" && applyFilter()}
            placeholder="账期"
          />
        </div>

        <label className="agent-favorite-filter">
          <input
            type="checkbox"
            checked={wb.sessionFilter.favorite}
            onChange={(event) => {
              const favorite = event.target.checked;
              wb.setSessionFilter((prev) => ({ ...prev, favorite }));
              void wb.refreshSessions({ filter: { ...wb.sessionFilter, favorite } });
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
          {continuationMode ? (
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
                  disabled={isStreaming}
                >
                  <Receipt size={15} />
                  账单库
                </Button>
              )}
              <Button onClick={submitComposerMessage} disabled={!wb.agentMessage.trim() || isStreaming}>
                {isStreaming ? <Loader2 size={15} className="spin" /> : <Send size={15} />}
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
            <div className="agent-panel-stack">
              <ContextPanel items={contextItems} referenceFiles={referenceFiles} onReferenceFile={referenceFile} />
              <ArtifactsPanel files={wb.agentFiles} resultFiles={result?.result_files || []} />
            </div>
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

function TimelineItem({ item, showDebug }: { item: AgentTimelineItem; showDebug: boolean }) {
  if (item.kind === "step") {
    const payload = stepPayload(item);
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
          <p>{item.status === "completed" ? "Agent 已完成这一步检查。" : "Agent 正在核对相关资料。"}</p>
          {showDebug && payload ? (
            <details>
              <summary>查看步骤详情</summary>
              <JsonBlock value={payload} empty="暂无步骤详情" />
            </details>
          ) : null}
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

function ContextPanel({
  items,
  referenceFiles,
  onReferenceFile,
}: {
  items: ReturnType<typeof buildContextItems>;
  referenceFiles: UploadedFile[];
  onReferenceFile: (fileId: string) => void;
}) {
  return (
    <div className="agent-panel-stack">
      <div className="agent-panel-section">
        <h3>当前上下文</h3>
        {items.map((item) => (
          <div className="agent-context-row" key={`${item.kind}-${item.id}`}>
            <FileText size={15} />
            <span>
              <strong>{item.title}</strong>
              <small>{item.meta || shortId(item.id)}</small>
            </span>
            {item.category ? <Badge tone={item.category === "billing-result" ? "green" : "blue"}>{categoryText(item.category)}</Badge> : null}
          </div>
        ))}
        {!items.length ? <EmptyState title="暂无上下文" hint="引用账单结果或上传供应商资料后会出现在这里。" /> : null}
      </div>
      <div className="agent-panel-section">
        <h3>可引用资料</h3>
        {referenceFiles.slice(0, 10).map((file) => (
          <button className="agent-reference-row" type="button" key={file.id} onClick={() => onReferenceFile(file.id)}>
            <span>
              <strong>{file.filename}</strong>
              <small>{fileDirectory(file)}</small>
            </span>
            <Badge tone={file.category === "billing-result" ? "green" : "blue"}>{categoryText(file.category)}</Badge>
          </button>
        ))}
        {!referenceFiles.length ? <EmptyState title="暂无可引用资料" hint="可先在生成账单或资料库上传文件。" /> : null}
      </div>
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

function ArtifactsPanel({ files, resultFiles }: { files: UploadedFile[]; resultFiles: Array<{ label?: string; uri?: string; role?: string }> }) {
  return (
    <div className="agent-panel-stack">
      <div className="agent-panel-section">
        <h3>会话文件</h3>
        {files.map((file) => (
          <div className="agent-artifact-row" key={file.id}>
            <FileText size={16} />
            <span>
              <strong>{file.filename}</strong>
              <small>{categoryText(file.category)} · {formatBytes(file.byte_size)}</small>
              <code>{file.s3_uri || "-"}</code>
            </span>
          </div>
        ))}
        {!files.length ? <EmptyState title="暂无会话文件" hint="Agent 任务引用或上传资料后会展示在这里。" /> : null}
      </div>
      <div className="agent-panel-section">
        <h3>结果产物</h3>
        {resultFiles.map((file, index) => (
          <div className="agent-artifact-row" key={`${file.uri}-${index}`}>
            <FileText size={16} />
            <span>
              <strong>{file.label || file.role || "结果文件"}</strong>
              <code>{file.uri || "-"}</code>
            </span>
          </div>
        ))}
        {!resultFiles.length ? <EmptyState title="暂无结果产物" hint="任务完成后会展示报告、结果 JSON 或建议文件。" /> : null}
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
