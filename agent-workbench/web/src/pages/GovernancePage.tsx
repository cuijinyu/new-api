import { useEffect, useMemo, useState } from "react";
import {
  BookMarked,
  CheckCircle2,
  FileText,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, DiffView, EmptyState, Field } from "../components/ui";
import { displayText, formatDate, formatImpact, shortId, statusText, statusTone, textOf } from "../lib/format";
import type { ChangeRequest, Skill, SkillContent } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

type GovTab = "requests" | "library";

export function GovernancePage({ wb }: { wb: WorkbenchState }) {
  const [tab, setTab] = useState<GovTab>("requests");

  return (
    <div className="governance-page">
      <div className="gov-tabs">
        <button className={`gov-tab ${tab === "requests" ? "active" : ""}`} onClick={() => setTab("requests")}>
          <CheckCircle2 size={15} />
          处理建议
          <span className="gov-tab-count">{wb.changeRequests.length}</span>
        </button>
        <button className={`gov-tab ${tab === "library" ? "active" : ""}`} onClick={() => setTab("library")}>
          <BookMarked size={15} />
          经验库
          <span className="gov-tab-count">{wb.skills.length}</span>
        </button>
      </div>
      {tab === "requests" ? <ChangeRequestPanel wb={wb} /> : <ExperienceLibraryPanel wb={wb} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 处理建议（原有能力，仅迁移到标签页内）
// ---------------------------------------------------------------------------
function ChangeRequestPanel({ wb }: { wb: WorkbenchState }) {
  const [selectedId, setSelectedId] = useState("");
  const { changeRequests, pending } = wb;
  const openCount = changeRequests.filter((item) => String(item.status).toLowerCase() === "open").length;
  const appliedCount = changeRequests.filter((item) => String(item.status).toLowerCase() === "applied").length;
  const ignoredCount = changeRequests.filter((item) => String(item.status).toLowerCase() === "ignored").length;
  const selected = changeRequests.find((item) => item.id === selectedId) || changeRequests[0];
  const isBusy = pending === "change" || pending === "changeRerun";

  return (
    <div className="governance-layout">
      <Card className="governance-list-card">
        <CardHeader>
          <CardTitle>建议列表</CardTitle>
          <Button variant="outline" size="sm" onClick={wb.refreshChangeRequests}>
            <RefreshCw size={14} />
            刷新
          </Button>
        </CardHeader>
        <CardContent>
          <div className="summary-card governance-stats">
            <div>
              <span>待处理</span>
              <strong>{openCount}</strong>
            </div>
            <div>
              <span>已应用</span>
              <strong>{appliedCount}</strong>
            </div>
            <div>
              <span>已忽略</span>
              <strong>{ignoredCount}</strong>
            </div>
            <div>
              <span>全部</span>
              <strong>{changeRequests.length}</strong>
            </div>
          </div>
          <div className="session-list governance-request-list">
            {changeRequests.map((item) => (
              <button key={item.id} className={`session-item ${selected?.id === item.id ? "active" : ""}`} onClick={() => setSelectedId(item.id)}>
                <div className="experience-item-head">
                  <strong>{item.reason || item.type || "价格方案建议"}</strong>
                  <Badge tone={statusTone(item.status)}>{statusText(item.status)}</Badge>
                </div>
                <span>{[item.vendor, item.month].filter(Boolean).join(" · ") || shortId(item.id)}</span>
                <div className="session-meta">
                  <small>影响 {formatImpact(item.impact || (item.impact_summary_json as ChangeRequest["impact"]))}</small>
                  <small>{formatDate(item.created_at)}</small>
                </div>
              </button>
            ))}
            {!changeRequests.length ? <EmptyState title="暂无建议" hint="Agent 完成对账后会在这里生成可处理的价格方案建议。" /> : null}
          </div>
        </CardContent>
      </Card>

      <Card className="governance-detail-card">
        <CardHeader>
          <CardTitle>建议详情</CardTitle>
          {selected ? <Badge tone={statusTone(selected.status)}>{statusText(selected.status)}</Badge> : null}
        </CardHeader>
        <CardContent>
          {selected ? (
            <GovernanceDetail wb={wb} request={selected} isBusy={isBusy} />
          ) : (
            <EmptyState icon={<CheckCircle2 size={26} />} title="选择一条建议查看详情" hint="左侧选择后可查看前后配置 diff、影响金额与证据文件。" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function GovernanceDetail({ wb, request, isBusy }: { wb: WorkbenchState; request: ChangeRequest; isBusy: boolean }) {
  const status = String(request.status).toLowerCase();
  const isOpen = status === "open";
  const before = request.before_config || (request.change_payload?.before as ChangeRequest["before_config"]);
  const after = request.after_config || (request.change_payload?.after as ChangeRequest["after_config"]);
  const impact = request.impact || (request.impact_summary_json as ChangeRequest["impact"]);
  const evidence = request.evidence_files || [];

  return (
    <div className="governance-detail">
      <div className="summary-card">
        <div>
          <span>建议编号</span>
          <strong>{shortId(request.id)}</strong>
        </div>
        <div>
          <span>来源任务</span>
          <strong>{shortId(request.job_id)}</strong>
        </div>
        <div>
          <span>影响金额</span>
          <strong className={impact?.amount_usd_delta ? "impact-value" : ""}>{formatImpact(impact)}</strong>
        </div>
        <div>
          <span>提出方</span>
          <strong>{textOf(request.proposed_by)}</strong>
        </div>
      </div>

      <div className="governance-reason">
        <span>建议说明</span>
        <p>{displayText(request.reason, "Agent 未提供文字说明，可查看下方配置 diff。")}</p>
      </div>

      <section className="governance-section">
        <h3>配置前后对比</h3>
        <DiffView before={before} after={after} />
      </section>

      <section className="governance-section">
        <h3>证据文件</h3>
        {evidence.length ? (
          <div className="artifact-list">
            {evidence.map((file) => (
              <div className="artifact-row" key={file.id}>
                <FileText size={16} />
                <span>
                  <strong>{file.filename}</strong>
                  <code>{file.s3_uri || "-"}</code>
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-cell">该建议未附带证据文件</div>
        )}
      </section>

      <div className="governance-actions">
        <Button onClick={() => wb.applyChangeRequest(request.id)} disabled={!isOpen || isBusy}>
          {wb.pending === "change" ? <Loader2 size={15} className="spin" /> : <CheckCircle2 size={15} />}
          应用
        </Button>
        <Button variant="outline" onClick={() => wb.ignoreChangeRequest(request.id)} disabled={!isOpen || isBusy}>
          <XCircle size={15} />
          忽略
        </Button>
        <Button variant="secondary" onClick={() => wb.saveChangeRequestExperience(request.id)} disabled={isBusy}>
          <Save size={15} />
          沉淀为经验
        </Button>
        <Button variant="ghost" onClick={() => wb.rerunBillForChangeRequest(request.id)} disabled={isBusy}>
          {wb.pending === "changeRerun" ? <Loader2 size={15} className="spin" /> : <RotateCcw size={15} />}
          重新生成账单
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 经验库（经验 = Skills，启用即自动注入对账 Agent）
// ---------------------------------------------------------------------------
type SkillDraft = {
  name: string;
  category: string;
  vendor: string;
  tags: string;
  bill_type: string;
  keywords: string;
  content: string;
};

const EMPTY_DRAFT: SkillDraft = {
  name: "",
  category: "billing-experience",
  vendor: "*",
  tags: "",
  bill_type: "",
  keywords: "",
  content: "# 经验标题\n\n## 适用场景\n\n## 排查/处理步骤\n\n## 注意事项\n",
};

function appliesOf(skill: Skill): { bill_type?: string[]; keywords?: string[]; source?: string } {
  const manifest = (skill.manifest || {}) as Record<string, unknown>;
  const applies = (manifest.applies_to || {}) as { bill_type?: string[]; keywords?: string[] };
  return { bill_type: applies.bill_type, keywords: applies.keywords, source: manifest.source as string | undefined };
}

function ExperienceLibraryPanel({ wb }: { wb: WorkbenchState }) {
  const { skills, pending } = wb;
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "disabled">("all");
  const [selectedId, setSelectedId] = useState("");
  const [mode, setMode] = useState<"view" | "edit" | "create">("view");
  const [draft, setDraft] = useState<SkillDraft>(EMPTY_DRAFT);
  const [content, setContent] = useState("");
  const isBusy = pending === "skills";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return skills.filter((skill) => {
      if (statusFilter !== "all" && String(skill.status || "active") !== statusFilter) return false;
      if (!q) return true;
      const hay = [skill.name, skill.vendor, skill.category, ...(skill.tags || [])].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [skills, query, statusFilter]);

  const selected = skills.find((item) => item.id === selectedId) || (mode === "create" ? undefined : filtered[0]);

  // 选中技能时加载其正文。
  useEffect(() => {
    if (mode === "create") return;
    const id = selected?.id;
    if (!id) {
      setContent("");
      return;
    }
    let alive = true;
    void wb.loadSkillContent(id).then((data: SkillContent | null) => {
      if (alive) setContent(data?.content || "");
    });
    return () => {
      alive = false;
    };
  }, [selected?.id, mode, wb]);

  const startCreate = () => {
    setMode("create");
    setSelectedId("");
    setDraft(EMPTY_DRAFT);
  };

  const startEdit = () => {
    if (!selected) return;
    const applies = appliesOf(selected);
    setDraft({
      name: selected.name,
      category: selected.category || "billing-experience",
      vendor: selected.vendor || "*",
      tags: (selected.tags || []).join(", "),
      bill_type: (applies.bill_type || []).join(", "),
      keywords: (applies.keywords || []).join(", "),
      content,
    });
    setMode("edit");
  };

  const submitCreate = async () => {
    if (!draft.name.trim()) return;
    const result = await wb.createSkill(draft);
    if (result?.ok) {
      setMode("view");
      const created = (result.data as { id?: string }).id;
      if (created) setSelectedId(created);
    }
  };

  const submitEdit = async () => {
    if (!selected) return;
    const applies_to: Record<string, unknown> = {};
    const billTypes = splitInput(draft.bill_type);
    const keywords = splitInput(draft.keywords);
    if (billTypes.length) applies_to.bill_type = billTypes;
    if (keywords.length) applies_to.keywords = keywords;
    const result = await wb.updateSkill(selected.id, {
      name: draft.name.trim(),
      vendor: draft.vendor.trim() || "*",
      tags: splitInput(draft.tags),
      content: draft.content,
      applies_to,
    });
    if (result?.ok) {
      setContent(draft.content);
      setMode("view");
    }
  };

  const removeSkill = async () => {
    if (!selected) return;
    if (!window.confirm(`确认删除经验「${selected.name}」？该操作不可恢复。`)) return;
    const result = await wb.deleteSkill(selected.id);
    if (result?.ok) {
      setSelectedId("");
      setMode("view");
    }
  };

  return (
    <div className="governance-layout">
      <Card className="governance-list-card">
        <CardHeader>
          <CardTitle>经验 / 技能</CardTitle>
          <div className="gov-head-actions">
            <Button variant="outline" size="sm" onClick={wb.refreshSkills}>
              <RefreshCw size={14} />
              刷新
            </Button>
            <Button size="sm" onClick={startCreate}>
              <Plus size={14} />
              新建经验
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="gov-hint">启用状态的经验会按供应商 / 账单类型相关性自动注入到对账 Agent。</p>
          <div className="skill-filter-row">
            <input className="input" placeholder="搜索名称 / 供应商 / 标签" value={query} onChange={(e) => setQuery(e.target.value)} />
            <select className="input" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}>
              <option value="all">全部</option>
              <option value="active">已启用</option>
              <option value="disabled">已停用</option>
            </select>
          </div>
          <div className="session-list">
            {filtered.map((skill) => {
              const applies = appliesOf(skill);
              const active = String(skill.status || "active") === "active";
              return (
                <button
                  key={skill.id}
                  className={`session-item ${selected?.id === skill.id && mode !== "create" ? "active" : ""}`}
                  onClick={() => {
                    setSelectedId(skill.id);
                    setMode("view");
                  }}
                >
                  <div className="experience-item-head">
                    <strong>{skill.name}</strong>
                    <Badge tone={active ? "green" : "default"}>{active ? "启用" : "停用"}</Badge>
                  </div>
                  <span>{[skill.vendor && skill.vendor !== "*" ? skill.vendor : "全部供应商", (applies.bill_type || []).join("/") || "全部账单"].join(" · ")}</span>
                  <div className="session-meta">
                    <small>{skill.version || "v1"} · {applies.source || "manual"}</small>
                    <small>{formatDate(skill.created_at)}</small>
                  </div>
                </button>
              );
            })}
            {!filtered.length ? <EmptyState title="暂无经验" hint="点击「新建经验」手动沉淀，或在建议详情里点「沉淀为经验」。" /> : null}
          </div>
        </CardContent>
      </Card>

      <Card className="governance-detail-card">
        <CardHeader>
          <CardTitle>{mode === "create" ? "新建经验" : "经验详情"}</CardTitle>
          {selected && mode === "view" ? <Badge tone={String(selected.status || "active") === "active" ? "green" : "default"}>{String(selected.status || "active") === "active" ? "启用中（自动注入）" : "已停用"}</Badge> : null}
        </CardHeader>
        <CardContent>
          {mode === "create" ? (
            <SkillForm draft={draft} setDraft={setDraft} onSubmit={submitCreate} onCancel={() => setMode("view")} isBusy={isBusy} submitLabel="创建经验" />
          ) : mode === "edit" && selected ? (
            <SkillForm draft={draft} setDraft={setDraft} onSubmit={submitEdit} onCancel={() => setMode("view")} isBusy={isBusy} submitLabel="保存修改" lockName />
          ) : selected ? (
            <SkillDetail wb={wb} skill={selected} content={content} onEdit={startEdit} onDelete={removeSkill} isBusy={isBusy} />
          ) : (
            <EmptyState icon={<Sparkles size={26} />} title="选择或新建一条经验" hint="经验以 Markdown 形式保存为真实 SKILL.md 文件，启用后自动注入对账 Agent。" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SkillDetail({
  wb,
  skill,
  content,
  onEdit,
  onDelete,
  isBusy,
}: {
  wb: WorkbenchState;
  skill: Skill;
  content: string;
  onEdit: () => void;
  onDelete: () => void;
  isBusy: boolean;
}) {
  const applies = appliesOf(skill);
  const active = String(skill.status || "active") === "active";
  return (
    <div className="governance-detail">
      <div className="summary-card">
        <div>
          <span>分类</span>
          <strong>{skill.category || "billing-experience"}</strong>
        </div>
        <div>
          <span>适用供应商</span>
          <strong>{skill.vendor && skill.vendor !== "*" ? skill.vendor : "全部"}</strong>
        </div>
        <div>
          <span>适用账单类型</span>
          <strong>{(applies.bill_type || []).join(" / ") || "全部"}</strong>
        </div>
        <div>
          <span>版本 / 来源</span>
          <strong>{skill.version || "v1"} · {applies.source || "manual"}</strong>
        </div>
      </div>

      {(skill.tags || []).length ? (
        <div className="skill-tags">
          {(skill.tags || []).map((tag) => (
            <span className="skill-tag" key={tag}>
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      <section className="governance-section">
        <h3>经验正文（SKILL.md）</h3>
        <pre className="skill-content">{content || "（内容为空）"}</pre>
        <small className="gov-hint">S3：{textOf(skill.s3_prefix)}</small>
      </section>

      <div className="governance-actions">
        <Button onClick={onEdit} disabled={isBusy}>
          <Pencil size={15} />
          编辑
        </Button>
        <Button
          variant={active ? "outline" : "default"}
          onClick={() => wb.setSkillStatus(skill.id, active ? "disabled" : "active")}
          disabled={isBusy}
        >
          {isBusy ? <Loader2 size={15} className="spin" /> : active ? <XCircle size={15} /> : <CheckCircle2 size={15} />}
          {active ? "停用（不再注入）" : "启用（自动注入）"}
        </Button>
        <Button variant="destructive" onClick={onDelete} disabled={isBusy}>
          <Trash2 size={15} />
          删除
        </Button>
      </div>
    </div>
  );
}

function SkillForm({
  draft,
  setDraft,
  onSubmit,
  onCancel,
  isBusy,
  submitLabel,
  lockName = false,
}: {
  draft: SkillDraft;
  setDraft: (next: SkillDraft) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isBusy: boolean;
  submitLabel: string;
  lockName?: boolean;
}) {
  const patch = (key: keyof SkillDraft, value: string) => setDraft({ ...draft, [key]: value });
  return (
    <div className="skill-form">
      <div className="skill-form-grid">
        <Field label="名称">
          <input className="input" value={draft.name} disabled={lockName} onChange={(e) => patch("name", e.target.value)} placeholder="如：1001AI Claude 缓存计费差异处理" />
        </Field>
        <Field label="分类">
          <input className="input" value={draft.category} onChange={(e) => patch("category", e.target.value)} placeholder="billing-experience" />
        </Field>
        <Field label="适用供应商" hint="* 表示对所有供应商生效">
          <input className="input" value={draft.vendor} onChange={(e) => patch("vendor", e.target.value)} placeholder="* 或 1001AI-Claude" />
        </Field>
        <Field label="适用账单类型" hint="逗号分隔，留空=全部">
          <input className="input" value={draft.bill_type} onChange={(e) => patch("bill_type", e.target.value)} placeholder="channel_cost_bill, customer_invoice" />
        </Field>
        <Field label="标签" hint="逗号分隔">
          <input className="input" value={draft.tags} onChange={(e) => patch("tags", e.target.value)} placeholder="reconcile, cache, claude" />
        </Field>
        <Field label="相关关键词" hint="逗号分隔，命中会提升注入优先级">
          <input className="input" value={draft.keywords} onChange={(e) => patch("keywords", e.target.value)} placeholder="缓存, 降档, 分段计费" />
        </Field>
      </div>
      <Field label="经验正文（Markdown，将保存为 SKILL.md）">
        <textarea className="input skill-textarea" rows={16} value={draft.content} onChange={(e) => patch("content", e.target.value)} />
      </Field>
      <div className="governance-actions">
        <Button onClick={onSubmit} disabled={isBusy || !draft.name.trim()}>
          {isBusy ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
          {submitLabel}
        </Button>
        <Button variant="ghost" onClick={onCancel} disabled={isBusy}>
          取消
        </Button>
      </div>
    </div>
  );
}

function splitInput(value: string): string[] {
  return Array.from(
    new Set(
      (value || "")
        .split(/[,，\n]/)
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}
