import { ChevronLeft, ChevronRight, FileText, Folder, Grid2X2, Info, LayoutList, Loader2, RefreshCw, Search } from "lucide-react";
import { Badge, Button, DataTable } from "../components/ui";
import { formatBytes, formatDate, previewCell } from "../lib/format";
import type { RawLogsForm } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

export function RawLogsPage({ wb }: { wb: WorkbenchState }) {
  const form = wb.rawLogsForm;

  function updateField(key: keyof RawLogsForm, value: string | boolean) {
    wb.setRawLogsForm((prev) => ({ ...prev, [key]: value }));
  }

  function updateDate(value: string) {
    if (!value) {
      wb.setRawLogsForm((prev) => ({ ...prev, year: "", month: "", day: "" }));
      return;
    }
    const [year, month, day] = value.split("-");
    wb.setRawLogsForm((prev) => ({ ...prev, year, month, day }));
  }

  const selectedObject = wb.rawLogObjects.find((item) => item.key === wb.selectedRawLogKey);
  const preview = wb.rawLogPreview;
  const previewRows = preview?.rows || [];
  const previewColumns = (preview?.columns || []).slice(0, 10);
  const matches = wb.rawLogSearchResult?.matches || [];
  const selectedDate = form.year && form.month && form.day ? `${form.year}-${form.month.padStart(2, "0")}-${form.day.padStart(2, "0")}` : "";
  const currentPrefix = selectedObject?.key ? selectedObject.key.split("/").slice(0, -1).join("/") : form.prefix;
  const hourOptions = ["", ...Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, "0"))];

  return (
    <div className="file-explorer rawlogs-explorer">
      <div className="explorer-toolbar">
        <div className="explorer-nav">
          <Button variant="ghost" size="icon" disabled title="后退">
            <ChevronLeft size={16} />
          </Button>
          <Button variant="ghost" size="icon" disabled title="前进">
            <ChevronRight size={16} />
          </Button>
          <Button variant="outline" size="icon" onClick={() => wb.loadRawLogsObjects()} disabled={wb.pending === "rawlogs"} title="刷新">
            {wb.pending === "rawlogs" ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
          </Button>
        </div>
        <div className="breadcrumb-bar">
          <span>日志检索</span>
          <ChevronRight size={14} />
          <strong>{selectedDate || currentPrefix || form.prefix}</strong>
        </div>
        <div className="rawlogs-date-controls">
          <input type="date" value={selectedDate} onChange={(event) => updateDate(event.target.value)} />
          <select value={form.hour} onChange={(event) => updateField("hour", event.target.value)}>
            {hourOptions.map((hour) => (
              <option key={hour || "all"} value={hour}>
                {hour ? `${hour}:00` : "全天"}
              </option>
            ))}
          </select>
        </div>
        <label className="explorer-search">
          <Search size={15} />
          <input value={form.query} onChange={(event) => updateField("query", event.target.value)} placeholder="request_id / model / error" />
        </label>
        <div className="explorer-actions">
          <Button variant="outline" size="icon" title="列表">
            <LayoutList size={16} />
          </Button>
          <Button variant="ghost" size="icon" title="网格">
            <Grid2X2 size={16} />
          </Button>
          <Button onClick={() => wb.loadRawLogsObjects()} disabled={wb.pending === "rawlogs"}>
            {wb.pending === "rawlogs" ? <Loader2 size={15} className="spin" /> : <RefreshCw size={15} />}
            查询
          </Button>
        </div>
      </div>

      <aside className="explorer-sidebar">
        <div className="explorer-tree">
          <button className="tree-item active">
            <Folder size={16} />
            <span>当前分区</span>
            <small>{wb.rawLogObjects.length}</small>
          </button>
          {wb.rawLogPrefixes.map((prefix) => (
            <button className="tree-item" key={prefix} onClick={() => wb.openRawLogPrefix(prefix)}>
              <Folder size={16} />
              <span>{prefix.split("/").filter(Boolean).slice(-1)[0] || prefix}</span>
              <small>目录</small>
            </button>
          ))}
        </div>
      </aside>

      <main className="explorer-main">
        <div className="file-list-head">
          <span>名称</span>
          <span>修改日期</span>
          <span>类型</span>
          <span>大小</span>
        </div>
        <div className="file-list-body">
          {wb.rawLogObjects.map((object) => (
            <button className={`file-row ${wb.selectedRawLogKey === object.key ? "active" : ""}`} key={object.key} onClick={() => wb.previewRawLog(object.key)}>
              <span className="file-name-cell">
                <FileText size={17} />
                <strong>{object.filename || object.key}</strong>
              </span>
              <span>{formatDate(object.last_modified)}</span>
              <span>{object.key.endsWith(".gz") ? "GZIP" : "NDJSON"} · 日志</span>
              <span>{formatBytes(object.size)}</span>
            </button>
          ))}
          {wb.rawLogsNextToken ? (
            <button className="file-row rawlogs-more-row" onClick={() => wb.loadRawLogsObjects(wb.rawLogsNextToken)}>
              <span className="file-name-cell">
                <RefreshCw size={17} />
                <strong>加载更多对象</strong>
              </span>
              <span>-</span>
              <span>分页</span>
              <span>-</span>
            </button>
          ) : null}
          {!wb.rawLogObjects.length ? (
            <div className="explorer-empty">
              <Folder size={28} />
              <span>当前日期下暂无对象</span>
            </div>
          ) : null}
        </div>
      </main>

      <aside className="explorer-detail rawlogs-detail">
        {preview ? (
          <>
            <div className="detail-icon">
              <FileText size={30} />
            </div>
            <h3>{selectedObject?.filename || preview.key}</h3>
            <div className="detail-kv">
              <span>大小</span>
              <strong>{formatBytes(preview.object_size || selectedObject?.size)}</strong>
              <span>读取</span>
              <strong>{formatBytes(preview.decoded_bytes)}</strong>
              <span>压缩</span>
              <strong>{preview.compression || "-"}</strong>
              <span>状态</span>
              <strong>{preview.truncated ? "预览已截断" : "完整预览"}</strong>
            </div>
            {previewRows.length && previewColumns.length ? (
              <DataTable
                columns={["#", ...previewColumns]}
                rows={previewRows.map((row, index) => [
                  index + 1,
                  ...previewColumns.map((column) => (
                    <span className="rawlog-table-cell" title={previewCell(row[column])} key={`${index}-${column}`}>
                      {previewCell(row[column])}
                    </span>
                  )),
                ])}
                empty="暂无结构化行"
              />
            ) : (
              <pre className="rawlog-preview-text">{preview.text || "暂无预览"}</pre>
            )}
            {previewRows.length && previewColumns.length ? (
              <details className="advanced-panel section-block">
                <summary>查看原文</summary>
                <pre className="rawlog-preview-text">{preview.text || "暂无预览"}</pre>
              </details>
            ) : null}
          </>
        ) : (
          <>
            <div className="detail-icon">
              <Info size={30} />
            </div>
            <h3>日志检索</h3>
            <div className="detail-kv">
              <span>Bucket</span>
              <strong>{form.bucket || wb.rawLogsConfig?.bucket || "-"}</strong>
              <span>Prefix</span>
              <strong>{form.prefix || wb.rawLogsConfig?.prefix || "-"}</strong>
              <span>对象数</span>
              <strong>{wb.rawLogObjects.length}</strong>
              <span>日期</span>
              <strong>{selectedDate || "-"}</strong>
            </div>
          </>
        )}

        <div className="detail-form section-block">
          <label className="field">
            <span>来源 Bucket</span>
            <input value={form.bucket} placeholder={wb.rawLogsConfig?.bucket || "ezmodel-log"} onChange={(event) => updateField("bucket", event.target.value)} />
          </label>
          <label className="field">
            <span>来源 Prefix</span>
            <input value={form.prefix} placeholder={wb.rawLogsConfig?.prefix || "llm-raw-logs"} onChange={(event) => updateField("prefix", event.target.value)} />
          </label>
          <label className="toggle-row">
            <input type="checkbox" checked={form.recursive} onChange={(event) => updateField("recursive", event.target.checked)} />
            递归列出对象
          </label>
        </div>

        <div className="rawlogs-search-block section-block">
          <div className="button-row">
            <Button onClick={wb.searchRawLogs} disabled={!form.query.trim() || wb.pending === "rawlogSearch"}>
              {wb.pending === "rawlogSearch" ? <Loader2 size={15} className="spin" /> : <Search size={15} />}
              搜索当前分区
            </Button>
            <Badge tone={matches.length ? "green" : "default"}>{matches.length} 条</Badge>
          </div>
          {wb.rawLogSearchResult ? (
            <div className="rawlogs-search-summary">
              <span>{wb.rawLogSearchResult.prefix}</span>
              <strong>扫描 {wb.rawLogSearchResult.scanned_objects || 0} 个对象</strong>
            </div>
          ) : null}
          <div className="rawlogs-matches">
            {matches.map((match, index) => (
              <button className="rawlog-match" key={`${match.key}-${match.line}-${index}`} onClick={() => wb.previewRawLog(match.key)}>
                <strong>{match.key}</strong>
                <span>
                  第 {match.line || "-"} 行 · {formatDate(match.last_modified)}
                </span>
                <code>{match.snippet || ""}</code>
              </button>
            ))}
            {!matches.length ? <div className="empty-cell">暂无命中</div> : null}
          </div>
        </div>
      </aside>
    </div>
  );
}
