import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  ChevronLeft,
  ChevronRight,
  Download,
  Expand,
  File,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileUp,
  Folder,
  Grid2X2,
  Info,
  LayoutList,
  Loader2,
  MessageSquare,
  RefreshCw,
  Search,
  UploadCloud,
  X,
} from "lucide-react";
import { Button, JsonBlock } from "../components/ui";
import { categoryText, fileDirectory, fileExtension, formatBytes, formatDate, shortId } from "../lib/format";
import type { PageId } from "../types";
import type { FilePreview, FilePreviewSheet, UploadedFile } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

function fileIcon(filename?: string) {
  const ext = fileExtension(filename || "").toLowerCase();
  if ([".xlsx", ".xls", ".csv"].includes(ext)) return FileSpreadsheet;
  if ([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"].includes(ext)) return FileImage;
  return FileText;
}

function PreviewTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  if (!rows.length) return <div className="file-preview-empty">暂无表格数据</div>;
  const header = columns.length ? columns : rows[0].map((_, index) => String(index + 1));
  return (
    <div className="file-preview-table-wrap">
      <table className="file-preview-table">
        <thead>
          <tr>
            {header.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {row.map((cell, cellIndex) => (
                <td key={`cell-${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SheetPreview({ sheets }: { sheets: FilePreviewSheet[] }) {
  const [activeSheet, setActiveSheet] = useState(sheets[0]?.name || "");
  const current = sheets.find((sheet) => sheet.name === activeSheet) || sheets[0];
  if (!current) return <div className="file-preview-empty">暂无工作表</div>;
  return (
    <div className="file-preview-sheet">
      {sheets.length > 1 ? (
        <div className="file-preview-tabs">
          {sheets.map((sheet) => (
            <button key={sheet.name} className={sheet.name === current.name ? "active" : ""} onClick={() => setActiveSheet(sheet.name)} type="button">
              {sheet.name}
            </button>
          ))}
        </div>
      ) : null}
      <PreviewTable columns={current.columns} rows={current.rows} />
      {current.truncated ? <p className="file-preview-note">仅展示前 200 行 / 50 列</p> : null}
    </div>
  );
}

function FilePreviewBody({ preview, resolveUrl }: { preview: FilePreview; resolveUrl: (url: string) => string }) {
  if (preview.kind === "text") {
    return (
      <>
        <pre className="file-preview-text">{preview.text}</pre>
        {preview.truncated ? <p className="file-preview-note">内容已截断，完整内容请下载查看</p> : null}
      </>
    );
  }
  if (preview.kind === "json") {
    return (
      <>
        <JsonBlock value={preview.data} empty="-" />
        {preview.truncated ? <p className="file-preview-note">内容已截断，完整内容请下载查看</p> : null}
      </>
    );
  }
  if (preview.kind === "csv") {
    return (
      <>
        <PreviewTable columns={preview.columns || []} rows={preview.rows || []} />
        {preview.truncated ? <p className="file-preview-note">仅展示部分内容</p> : null}
      </>
    );
  }
  if (preview.kind === "sheet") {
    return (
      <>
        <SheetPreview sheets={preview.sheets || []} />
        {preview.truncated ? <p className="file-preview-note">文件较大，预览可能不完整</p> : null}
      </>
    );
  }
  if (preview.kind === "image") {
    return <img className="file-preview-image" src={resolveUrl(preview.url)} alt={preview.filename || "preview"} />;
  }
  if (preview.kind === "pdf") {
    return <iframe className="file-preview-pdf" src={resolveUrl(preview.url)} title={preview.filename || "pdf preview"} />;
  }
  if (preview.kind === "binary") {
    return <div className="file-preview-empty">{preview.message || "此文件类型不支持在线预览，请下载后查看"}</div>;
  }
  return <div className="file-preview-empty">此文件类型不支持在线预览，请下载后查看</div>;
}

function FilePreviewPanel({
  preview,
  loading,
  error,
  resolveUrl,
  onExpand,
}: {
  preview: FilePreview | null;
  loading: boolean;
  error: string;
  resolveUrl: (url: string) => string;
  onExpand?: () => void;
}) {
  if (loading) {
    return (
      <div className="file-preview-panel loading">
        <Loader2 size={18} className="spin" />
        <span>加载预览…</span>
      </div>
    );
  }
  if (error) {
    return <div className="file-preview-panel error">{error}</div>;
  }
  if (!preview) {
    return <div className="file-preview-panel empty">选择文件后可在此预览</div>;
  }
  return (
    <div className="file-preview-panel">
      <div className="file-preview-head">
        <strong>预览</strong>
        {onExpand ? (
          <Button variant="ghost" size="icon" onClick={onExpand} title="放大预览">
            <Expand size={15} />
          </Button>
        ) : null}
      </div>
      <div className="file-preview-body">
        <FilePreviewBody preview={preview} resolveUrl={resolveUrl} />
      </div>
    </div>
  );
}

export function FilesPage({ wb, switchPage }: { wb: WorkbenchState; switchPage: (page: PageId) => void }) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [activeFolder, setActiveFolder] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedFileId, setSelectedFileId] = useState("");
  const [previewExpanded, setPreviewExpanded] = useState(false);

  const folders = useMemo(() => {
    const base = [
      { id: "all", label: "全部文件", path: "", level: 0 },
      { id: "账单结果", label: "账单结果", path: "账单结果", level: 0 },
      { id: "供应商账单", label: "供应商账单", path: "供应商账单", level: 0 },
      { id: "对账凭证", label: "对账凭证", path: "对账凭证", level: 0 },
      { id: "对话资料", label: "对话资料", path: "对话资料", level: 0 },
      { id: "通用文件", label: "通用文件", path: "通用文件", level: 0 },
    ];
    const directoryPaths = new Set<string>();
    wb.uploadedFiles.forEach((file) => {
      const parts = fileDirectory(file).split("/").filter(Boolean);
      parts.forEach((_, index) => directoryPaths.add(parts.slice(0, index + 1).join("/")));
    });
    const dynamic = [...directoryPaths]
      .filter((path) => !base.some((folder) => folder.path === path))
      .sort((a, b) => a.localeCompare(b, "zh-CN"))
      .map((path) => {
        const parts = path.split("/");
        return { id: path, label: parts[parts.length - 1], path, level: Math.min(parts.length - 1, 3) };
      });
    return [...base, ...dynamic];
  }, [wb.uploadedFiles]);

  const filesInFolder = wb.uploadedFiles.filter((file) => activeFolder === "all" || fileDirectory(file).startsWith(activeFolder));
  const normalizedQuery = query.trim().toLowerCase();
  const visibleFiles = filesInFolder.filter((file) => {
    if (!normalizedQuery) return true;
    return [file.filename, file.category, file.s3_uri, file.job_id, file.session_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedQuery));
  });
  const selectedFile = visibleFiles.find((file) => file.id === selectedFileId) || visibleFiles[0];
  const currentFolder = folders.find((folder) => folder.id === activeFolder) || folders[0];
  const stagedSize = wb.selectedFiles.reduce((total, file) => total + file.size, 0);
  const previewReady = wb.filePreviewFileId === selectedFile?.id;

  useEffect(() => {
    if (wb.selectedFiles.length || !selectedFile?.id) {
      if (!selectedFile?.id) wb.clearFilePreview();
      return;
    }
    void wb.previewFile(selectedFile.id);
  }, [selectedFile?.id, wb.selectedFiles.length, wb.previewFile, wb.clearFilePreview]);

  const renderFileRow = (file: UploadedFile) => {
    const Icon = fileIcon(file.filename);
    return (
      <button className={`file-row ${selectedFile?.id === file.id ? "active" : ""}`} key={file.id} onClick={() => setSelectedFileId(file.id)} type="button">
        <span className="file-name-cell">
          <Icon size={17} />
          <strong>{file.filename}</strong>
        </span>
        <span>{formatDate(file.created_at)}</span>
        <span>
          {fileDirectory(file)} · {fileExtension(file.filename)}
        </span>
        <span>{formatBytes(file.byte_size)}</span>
      </button>
    );
  };

  return (
    <div className="file-explorer">
      <input ref={fileInputRef} className="file-input-hidden" type="file" multiple onChange={(event) => wb.setSelectedFiles(Array.from(event.target.files || []))} />
      <div className="explorer-toolbar">
        <div className="explorer-nav">
          <Button variant="ghost" size="icon" disabled title="后退">
            <ChevronLeft size={16} />
          </Button>
          <Button variant="ghost" size="icon" disabled title="前进">
            <ChevronRight size={16} />
          </Button>
          <Button variant="outline" size="icon" onClick={wb.refreshFiles} title="刷新">
            <RefreshCw size={16} />
          </Button>
        </div>
        <div className="breadcrumb-bar">
          <span>资料库</span>
          <ChevronRight size={14} />
          <strong>{currentFolder.label}</strong>
        </div>
        <label className="explorer-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索" />
        </label>
        <div className="explorer-actions">
          <Button variant="outline" size="icon" title="列表">
            <LayoutList size={16} />
          </Button>
          <Button variant="ghost" size="icon" title="网格">
            <Grid2X2 size={16} />
          </Button>
          <Button onClick={() => fileInputRef.current?.click()}>
            <UploadCloud size={15} />
            上传
          </Button>
        </div>
      </div>

      <aside className="explorer-sidebar">
        <div className="explorer-tree">
          {folders.map((folder) => {
            const count = folder.id === "all" ? wb.uploadedFiles.length : wb.uploadedFiles.filter((file) => fileDirectory(file).startsWith(folder.path)).length;
            return (
              <button
                key={folder.id}
                className={`tree-item level-${folder.level} ${activeFolder === folder.id ? "active" : ""}`}
                onClick={() => {
                  setActiveFolder(folder.id);
                  setSelectedFileId("");
                }}
                type="button"
              >
                <Folder size={16} />
                <span>{folder.label}</span>
                <small>{count}</small>
              </button>
            );
          })}
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
          {visibleFiles.map(renderFileRow)}
          {!visibleFiles.length ? (
            <div className="explorer-empty">
              <Folder size={28} />
              <span>空文件夹</span>
            </div>
          ) : null}
        </div>
      </main>

      <aside className="explorer-detail">
        {wb.selectedFiles.length ? (
          <>
            <div className="detail-icon">
              <FileUp size={30} />
            </div>
            <h3>待上传</h3>
            <div className="detail-kv">
              <span>数量</span>
              <strong>{wb.selectedFiles.length}</strong>
              <span>大小</span>
              <strong>{formatBytes(stagedSize)}</strong>
            </div>
            <div className="staged-file-list">
              {wb.selectedFiles.slice(0, 6).map((file) => (
                <div key={`${file.name}-${file.size}`}>
                  <File size={15} />
                  <span>{file.name}</span>
                </div>
              ))}
            </div>
            <div className="detail-form">
              <label className="field">
                <span>分类</span>
                <select value={wb.fileForm.category} onChange={(event) => wb.setFileForm((prev) => ({ ...prev, category: event.target.value }))}>
                  <option value="supplier-bill">供应商账单</option>
                  <option value="reconcile-evidence">对账凭证</option>
                  <option value="agent-context">对话资料</option>
                  <option value="general">通用文件</option>
                </select>
              </label>
              <label className="field">
                <span>上传人</span>
                <input value={wb.fileForm.uploaded_by} onChange={(event) => wb.setFileForm((prev) => ({ ...prev, uploaded_by: event.target.value }))} />
              </label>
              <label className="field">
                <span>账单任务</span>
                <input value={wb.fileForm.job_id} onChange={(event) => wb.setFileForm((prev) => ({ ...prev, job_id: event.target.value }))} />
              </label>
              <label className="field">
                <span>Agent 对话</span>
                <input value={wb.fileForm.session_id} onChange={(event) => wb.setFileForm((prev) => ({ ...prev, session_id: event.target.value }))} />
              </label>
            </div>
            <Button onClick={wb.uploadSelectedFiles} disabled={wb.pending === "upload"}>
              {wb.pending === "upload" ? <Loader2 size={15} className="spin" /> : <UploadCloud size={15} />}
              保存
            </Button>
          </>
        ) : selectedFile ? (
          <>
            <div className="detail-icon">
              {(() => {
                const Icon = fileIcon(selectedFile.filename);
                return <Icon size={30} />;
              })()}
            </div>
            <h3>{selectedFile.filename}</h3>
            <div className="detail-kv">
              <span>类型</span>
              <strong>{categoryText(selectedFile.category)}</strong>
              <span>目录</span>
              <strong>{fileDirectory(selectedFile)}</strong>
              <span>大小</span>
              <strong>{formatBytes(selectedFile.byte_size)}</strong>
              <span>创建时间</span>
              <strong>{formatDate(selectedFile.created_at)}</strong>
              <span>账单任务</span>
              <strong>{shortId(selectedFile.job_id)}</strong>
              <span>Agent 对话</span>
              <strong>{shortId(selectedFile.session_id)}</strong>
            </div>
            <div className="button-row section-block">
              <Button onClick={() => wb.downloadFile(selectedFile.id, selectedFile.filename)}>
                <Download size={15} />
                下载
              </Button>
              <Button onClick={() => wb.referenceFilesToAgent([selectedFile.id])} disabled={wb.pending === "agent"}>
                {wb.pending === "agent" ? <Loader2 size={15} className="spin" /> : <Bot size={15} />}
                引用到 Agent
              </Button>
              <Button variant="outline" onClick={() => switchPage("agent")}>
                <MessageSquare size={15} />
                打开 Agent
              </Button>
            </div>
            <FilePreviewPanel
              preview={previewReady ? wb.filePreview : null}
              loading={wb.filePreviewLoading && wb.filePreviewFileId === selectedFile.id}
              error={wb.filePreviewFileId === selectedFile.id ? wb.filePreviewError : ""}
              resolveUrl={wb.resolveFileUrl}
              onExpand={() => setPreviewExpanded(true)}
            />
            <details className="advanced-panel">
              <summary>文件地址</summary>
              <JsonBlock value={selectedFile.s3_uri} empty="-" />
            </details>
          </>
        ) : (
          <>
            <div className="detail-icon">
              <Info size={30} />
            </div>
            <h3>{currentFolder.label}</h3>
            <div className="detail-kv">
              <span>文件数</span>
              <strong>{visibleFiles.length}</strong>
              <span>总大小</span>
              <strong>{formatBytes(visibleFiles.reduce((total, file) => total + (file.byte_size || 0), 0))}</strong>
            </div>
          </>
        )}
      </aside>

      {previewExpanded && selectedFile && previewReady && wb.filePreview ? (
        <div className="file-preview-modal-backdrop" onClick={() => setPreviewExpanded(false)}>
          <div className="file-preview-modal" onClick={(event) => event.stopPropagation()}>
            <div className="file-preview-modal-head">
              <div>
                <strong>{selectedFile.filename}</strong>
                <span>{categoryText(selectedFile.category)}</span>
              </div>
              <div className="file-preview-modal-actions">
                <Button variant="outline" onClick={() => wb.downloadFile(selectedFile.id, selectedFile.filename)}>
                  <Download size={15} />
                  下载
                </Button>
                <Button variant="ghost" size="icon" onClick={() => setPreviewExpanded(false)} title="关闭">
                  <X size={16} />
                </Button>
              </div>
            </div>
            <div className="file-preview-modal-body">
              <FilePreviewBody preview={wb.filePreview} resolveUrl={wb.resolveFileUrl} />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
