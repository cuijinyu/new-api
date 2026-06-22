import { DownloadCloud, Loader2, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Field } from "../components/ui";
import type { CostDiscountRow, RevenueDiscountRow } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

function cloneCostRows(rows: CostDiscountRow[]) {
  return rows.map((row) => ({ ...row }));
}

function cloneRevenueRows(rows: RevenueDiscountRow[]) {
  return rows.map((row) => ({ ...row }));
}

function discountRowsChanged(
  draftCostRows: CostDiscountRow[],
  savedCostRows: CostDiscountRow[],
  draftRevenueRows: RevenueDiscountRow[],
  savedRevenueRows: RevenueDiscountRow[],
) {
  return JSON.stringify(draftCostRows) !== JSON.stringify(savedCostRows) || JSON.stringify(draftRevenueRows) !== JSON.stringify(savedRevenueRows);
}

export function DiscountsPage({ wb }: { wb: WorkbenchState }) {
  const [batchCost, setBatchCost] = useState("");
  const [batchRevenue, setBatchRevenue] = useState("");
  const [draftCostRows, setDraftCostRows] = useState<CostDiscountRow[]>([]);
  const [draftRevenueRows, setDraftRevenueRows] = useState<RevenueDiscountRow[]>([]);

  useEffect(() => {
    void wb.loadDiscounts();
  }, [wb.loadDiscounts]);

  useEffect(() => {
    setDraftCostRows(cloneCostRows(wb.costDiscountRows));
  }, [wb.costDiscountRows]);

  useEffect(() => {
    setDraftRevenueRows(cloneRevenueRows(wb.revenueDiscountRows));
  }, [wb.revenueDiscountRows]);

  const hasUnsavedChanges = discountRowsChanged(draftCostRows, wb.costDiscountRows, draftRevenueRows, wb.revenueDiscountRows);

  function updateCostRow(index: number, patch: Partial<CostDiscountRow>) {
    setDraftCostRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function updateRevenueRow(index: number, patch: Partial<RevenueDiscountRow>) {
    setDraftRevenueRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addCostRow() {
    setDraftCostRows((rows) => [...rows, { channel_id: "", channel_name: "", model: "*", discount: 1 }]);
  }

  function addRevenueRow() {
    setDraftRevenueRows((rows) => [...rows, { user_id: "", user_name: "", model: "*", discount: 1 }]);
  }

  function applyBatchCost() {
    const value = Number(batchCost);
    if (!Number.isFinite(value)) return;
    setDraftCostRows((rows) => rows.map((row) => ({ ...row, discount: value })));
  }

  function applyBatchRevenue() {
    const value = Number(batchRevenue);
    if (!Number.isFinite(value)) return;
    setDraftRevenueRows((rows) => rows.map((row) => ({ ...row, discount: value })));
  }

  function resetDraft() {
    setDraftCostRows(cloneCostRows(wb.costDiscountRows));
    setDraftRevenueRows(cloneRevenueRows(wb.revenueDiscountRows));
  }

  async function save() {
    const confirmed = window.confirm("确认保存折扣并立即生效？这会影响后续出账、KPI 预览与 Agent 对账。");
    if (!confirmed) return;
    await wb.saveDiscounts({ cost_rows: draftCostRows, revenue_rows: draftRevenueRows });
  }

  async function reseed() {
    const confirmed = window.confirm(
      hasUnsavedChanges
        ? "从 scripts/athena 导入会覆盖当前生效折扣，并丢弃未保存改动。确定继续？"
        : "从 scripts/athena 导入会覆盖当前生效折扣。确定继续？",
    );
    if (!confirmed) return;
    await wb.reseedDiscounts();
  }

  const saving = wb.pending === "discounts";
  const isEmpty = !draftCostRows.length && !draftRevenueRows.length;

  return (
    <div className="discounts-page">
      <Card>
        <CardHeader>
          <CardTitle>折扣管理</CardTitle>
          <div className="inline-form">
            <Badge tone="green">全局生效</Badge>
            <Badge tone={hasUnsavedChanges ? "amber" : "green"}>{hasUnsavedChanges ? "未保存" : "已保存"}</Badge>
            <Button variant="outline" size="sm" onClick={() => void reseed()} disabled={saving}>
              {saving ? <Loader2 size={14} className="spin" /> : <DownloadCloud size={14} />}
              从 scripts/athena 导入
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="page-hint">折扣对所有出账全局生效，保存后立即应用到后续 KPI 预览与账单生成。无需选择版本。</p>
          {isEmpty ? (
            <p className="billing-banner billing-banner-warn">
              当前没有折扣数据。点击右上角「从 scripts/athena 导入」可载入仓库里的原始折扣口径（<code>scripts/athena/discounts.json</code>）。
            </p>
          ) : null}
        </CardContent>
      </Card>

      <div className={`explicit-save-bar ${hasUnsavedChanges ? "dirty" : "clean"}`}>
        <div>
          <strong>{hasUnsavedChanges ? "有未保存改动" : "当前折扣已保存"}</strong>
          <span>保存后才会影响后续出账、KPI 预览与 Agent 对账。</span>
        </div>
        <div className="explicit-save-actions">
          <Button variant="ghost" size="sm" onClick={resetDraft} disabled={!hasUnsavedChanges || saving}>
            <RotateCcw size={14} />
            放弃改动
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={!hasUnsavedChanges || saving}>
            {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
            保存并生效
          </Button>
        </div>
      </div>

      <div className="discounts-grid">
        <Card>
          <CardHeader>
            <CardTitle>渠道成本折扣</CardTitle>
            <div className="inline-form">
              <Field label="批量折扣率">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="2"
                  placeholder="0.35"
                  value={batchCost}
                  onChange={(e) => setBatchCost(e.target.value)}
                />
              </Field>
              <Button variant="outline" size="sm" onClick={applyBatchCost}>
                应用到全部
              </Button>
              <Button variant="ghost" size="sm" onClick={addCostRow}>
                <Plus size={14} /> 增行
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {draftCostRows.length ? (
              <div className="discount-table-wrap">
                <table className="discount-table">
                  <thead>
                    <tr>
                      <th>渠道 ID</th>
                      <th>名称</th>
                      <th>模型</th>
                      <th>折扣率</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {draftCostRows.map((row, index) => (
                      <tr key={`cost-${index}`}>
                        <td><input value={row.channel_id} onChange={(e) => updateCostRow(index, { channel_id: e.target.value })} placeholder="65" /></td>
                        <td><span className="discount-name">{row.channel_name || "-"}</span></td>
                        <td><input value={row.model} onChange={(e) => updateCostRow(index, { model: e.target.value })} placeholder="*" /></td>
                        <td><input type="number" step="0.01" value={row.discount} onChange={(e) => updateCostRow(index, { discount: Number(e.target.value) })} /></td>
                        <td>
                          <button type="button" className="icon-btn" onClick={() => setDraftCostRows((rows) => rows.filter((_, i) => i !== index))}>
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="暂无渠道折扣" hint="点击增行添加渠道 × 模型折扣，模型可用 * 通配。" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>客户收入折扣</CardTitle>
            <div className="inline-form">
              <Field label="批量折扣率">
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="2"
                  placeholder="0.8"
                  value={batchRevenue}
                  onChange={(e) => setBatchRevenue(e.target.value)}
                />
              </Field>
              <Button variant="outline" size="sm" onClick={applyBatchRevenue}>
                应用到全部
              </Button>
              <Button variant="ghost" size="sm" onClick={addRevenueRow}>
                <Plus size={14} /> 增行
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {draftRevenueRows.length ? (
              <div className="discount-table-wrap">
                <table className="discount-table">
                  <thead>
                    <tr>
                      <th>用户 ID</th>
                      <th>名称</th>
                      <th>模型</th>
                      <th>折扣率</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {draftRevenueRows.map((row, index) => (
                      <tr key={`rev-${index}`}>
                        <td><input value={row.user_id} onChange={(e) => updateRevenueRow(index, { user_id: e.target.value })} placeholder="89" /></td>
                        <td><span className="discount-name">{row.user_name || "-"}</span></td>
                        <td><input value={row.model} onChange={(e) => updateRevenueRow(index, { model: e.target.value })} placeholder="*" /></td>
                        <td><input type="number" step="0.01" value={row.discount} onChange={(e) => updateRevenueRow(index, { discount: Number(e.target.value) })} /></td>
                        <td>
                          <button type="button" className="icon-btn" onClick={() => setDraftRevenueRows((rows) => rows.filter((_, i) => i !== index))}>
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="暂无客户折扣" hint="为客户 ID × 模型配置应付折扣率。" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="discounts-actions">
        <Button variant="ghost" onClick={resetDraft} disabled={!hasUnsavedChanges || saving}>
          <RotateCcw size={15} />
          放弃改动
        </Button>
        <Button onClick={() => void save()} disabled={!hasUnsavedChanges || saving}>
          {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
          保存折扣并生效
        </Button>
      </div>
    </div>
  );
}
