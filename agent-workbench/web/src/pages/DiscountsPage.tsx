import { DownloadCloud, Loader2, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Field } from "../components/ui";
import type { CostDiscountRow, RevenueDiscountRow } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

export function DiscountsPage({ wb }: { wb: WorkbenchState }) {
  const [batchCost, setBatchCost] = useState("");
  const [batchRevenue, setBatchRevenue] = useState("");

  useEffect(() => {
    void wb.loadDiscounts();
  }, [wb.loadDiscounts]);

  function updateCostRow(index: number, patch: Partial<CostDiscountRow>) {
    wb.setCostDiscountRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function updateRevenueRow(index: number, patch: Partial<RevenueDiscountRow>) {
    wb.setRevenueDiscountRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addCostRow() {
    wb.setCostDiscountRows((rows) => [...rows, { channel_id: "", channel_name: "", model: "*", discount: 1 }]);
  }

  function addRevenueRow() {
    wb.setRevenueDiscountRows((rows) => [...rows, { user_id: "", user_name: "", model: "*", discount: 1 }]);
  }

  function applyBatchCost() {
    const value = Number(batchCost);
    if (!Number.isFinite(value)) return;
    wb.setCostDiscountRows((rows) => rows.map((row) => ({ ...row, discount: value })));
  }

  function applyBatchRevenue() {
    const value = Number(batchRevenue);
    if (!Number.isFinite(value)) return;
    wb.setRevenueDiscountRows((rows) => rows.map((row) => ({ ...row, discount: value })));
  }

  async function save() {
    await wb.saveDiscounts({ cost_rows: wb.costDiscountRows, revenue_rows: wb.revenueDiscountRows });
  }

  async function reseed() {
    await wb.reseedDiscounts();
  }

  const saving = wb.pending === "discounts";
  const isEmpty = !wb.costDiscountRows.length && !wb.revenueDiscountRows.length;

  return (
    <div className="discounts-page">
      <Card>
        <CardHeader>
          <CardTitle>折扣管理</CardTitle>
          <div className="inline-form">
            <Badge tone="green">全局生效</Badge>
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
            {wb.costDiscountRows.length ? (
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
                    {wb.costDiscountRows.map((row, index) => (
                      <tr key={`cost-${index}`}>
                        <td><input value={row.channel_id} onChange={(e) => updateCostRow(index, { channel_id: e.target.value })} placeholder="65" /></td>
                        <td><span className="discount-name">{row.channel_name || "-"}</span></td>
                        <td><input value={row.model} onChange={(e) => updateCostRow(index, { model: e.target.value })} placeholder="*" /></td>
                        <td><input type="number" step="0.01" value={row.discount} onChange={(e) => updateCostRow(index, { discount: Number(e.target.value) })} /></td>
                        <td>
                          <button type="button" className="icon-btn" onClick={() => wb.setCostDiscountRows((rows) => rows.filter((_, i) => i !== index))}>
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
            {wb.revenueDiscountRows.length ? (
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
                    {wb.revenueDiscountRows.map((row, index) => (
                      <tr key={`rev-${index}`}>
                        <td><input value={row.user_id} onChange={(e) => updateRevenueRow(index, { user_id: e.target.value })} placeholder="89" /></td>
                        <td><span className="discount-name">{row.user_name || "-"}</span></td>
                        <td><input value={row.model} onChange={(e) => updateRevenueRow(index, { model: e.target.value })} placeholder="*" /></td>
                        <td><input type="number" step="0.01" value={row.discount} onChange={(e) => updateRevenueRow(index, { discount: Number(e.target.value) })} /></td>
                        <td>
                          <button type="button" className="icon-btn" onClick={() => wb.setRevenueDiscountRows((rows) => rows.filter((_, i) => i !== index))}>
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
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
          保存折扣（立即生效）
        </Button>
      </div>
    </div>
  );
}
