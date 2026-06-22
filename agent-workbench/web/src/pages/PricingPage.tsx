import { DownloadCloud, Layers3, Loader2, Plus, Save, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState } from "../components/ui";
import type { PricingRow } from "../types";
import type { WorkbenchState } from "../hooks/useWorkbench";

const pricingTypes = [
  { value: "flat", label: "固定价" },
  { value: "tiered", label: "分层价" },
  { value: "multimodal", label: "多模态" },
];

function isTiered(row: PricingRow) {
  return row.type === "tiered";
}

function isMultimodal(row: PricingRow) {
  return row.type === "multimodal";
}

function nextModelName(rows: PricingRow[], prefix: string) {
  let index = rows.length + 1;
  let name = `${prefix}-${index}`;
  const names = new Set(rows.map((row) => row.model));
  while (names.has(name)) {
    index += 1;
    name = `${prefix}-${index}`;
  }
  return name;
}

function numericValue(value: unknown) {
  return value === undefined || value === null ? "" : String(value);
}

function checkedValue(value: unknown) {
  if (typeof value === "string") return value.toLowerCase() === "true";
  return Boolean(value);
}

export function PricingPage({ wb }: { wb: WorkbenchState }) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    void wb.loadPricing();
  }, [wb.loadPricing]);

  const saving = wb.pending === "pricing";
  const normalizedQuery = query.trim().toLowerCase();
  const visibleRows = useMemo(() => {
    return wb.pricingRows
      .map((row, index) => ({ row, index }))
      .filter(({ row }) => {
        if (typeFilter !== "all" && row.type !== typeFilter) return false;
        if (!normalizedQuery) return true;
        return [row.model, row.type, row.note].some((value) => String(value || "").toLowerCase().includes(normalizedQuery));
      });
  }, [wb.pricingRows, normalizedQuery, typeFilter]);

  const modelCount = useMemo(() => new Set(wb.pricingRows.map((row) => row.model).filter(Boolean)).size, [wb.pricingRows]);

  function updateRow(index: number, patch: Partial<PricingRow>) {
    wb.setPricingRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function addFlatModel() {
    wb.setPricingRows((rows) => [
      ...rows,
      { model: nextModelName(rows, "flat-model"), type: "flat", flat_tier: false, ip: 0, op: 0, chp: 0, cwp: 0, cwp_1h: 0 },
    ]);
  }

  function addTieredModel() {
    wb.setPricingRows((rows) => [
      ...rows,
      {
        model: nextModelName(rows, "tiered-model"),
        type: "tiered",
        flat_tier: false,
        tier_index: 0,
        min_k: 0,
        max_k: -1,
        ip: 0,
        op: 0,
        chp: 0,
        cwp: 0,
        cwp_1h: 0,
      },
    ]);
  }

  function addMultimodalModel() {
    wb.setPricingRows((rows) => [
      ...rows,
      { model: nextModelName(rows, "multimodal-model"), type: "multimodal", ip: 0, op_text: 0, op_image: 0, note: "" },
    ]);
  }

  function addTier(model: string) {
    wb.setPricingRows((rows) => {
      const tiers = rows.filter((row) => row.model === model && row.type === "tiered");
      const lastTier = tiers[tiers.length - 1];
      const lastMax = Number(lastTier?.max_k);
      const nextIndex = tiers.length;
      return [
        ...rows,
        {
          model,
          type: "tiered",
          flat_tier: lastTier?.flat_tier ?? false,
          tier_index: nextIndex,
          min_k: Number.isFinite(lastMax) && lastMax !== -1 ? lastMax : 0,
          max_k: -1,
          ip: lastTier?.ip ?? 0,
          op: lastTier?.op ?? 0,
          chp: lastTier?.chp ?? 0,
          cwp: lastTier?.cwp ?? 0,
          cwp_1h: lastTier?.cwp_1h ?? 0,
        },
      ];
    });
  }

  async function save() {
    await wb.savePricing({ rows: wb.pricingRows });
  }

  async function reseed() {
    await wb.reseedPricing();
  }

  return (
    <div className="pricing-page">
      <Card>
        <CardHeader>
          <CardTitle>刊例价管理</CardTitle>
          <div className="inline-form">
            <Badge tone="green">全局生效</Badge>
            <Badge tone="blue">{modelCount} 个模型</Badge>
            <Button variant="outline" size="sm" onClick={() => void reseed()} disabled={saving}>
              {saving ? <Loader2 size={14} className="spin" /> : <DownloadCloud size={14} />}
              从 scripts/athena 导入
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="pricing-summary">
            <div>
              <span>配置版本</span>
              <strong>{wb.pricingMetadata?.version || "-"}</strong>
            </div>
            <div>
              <span>更新日期</span>
              <strong>{wb.pricingMetadata?.updated_at || "-"}</strong>
            </div>
            <div>
              <span>行数</span>
              <strong>{wb.pricingRows.length}</strong>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>模型刊例价</CardTitle>
          <div className="pricing-toolbar">
            <label className="pricing-search">
              <Search size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索模型" />
            </label>
            <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
              <option value="all">全部类型</option>
              {pricingTypes.map((item) => (
                <option value={item.value} key={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
            <Button variant="outline" size="sm" onClick={addFlatModel}>
              <Plus size={14} /> 固定价
            </Button>
            <Button variant="outline" size="sm" onClick={addTieredModel}>
              <Layers3 size={14} /> 分层价
            </Button>
            <Button variant="outline" size="sm" onClick={addMultimodalModel}>
              <Plus size={14} /> 多模态
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {visibleRows.length ? (
            <div className="pricing-table-wrap">
              <table className="pricing-table">
                <thead>
                  <tr>
                    <th>模型</th>
                    <th>类型</th>
                    <th>阶梯</th>
                    <th>区间 K</th>
                    <th>固定阶梯</th>
                    <th>输入</th>
                    <th>输出/文本</th>
                    <th>图片输出</th>
                    <th>缓存命中</th>
                    <th>缓存写 5m</th>
                    <th>缓存写 1h</th>
                    <th>备注</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map(({ row, index }) => (
                    <tr key={`${row.model}-${row.type}-${index}`}>
                      <td>
                        <input value={row.model} onChange={(event) => updateRow(index, { model: event.target.value })} />
                      </td>
                      <td>
                        <select
                          value={row.type}
                          onChange={(event) => {
                            const nextType = event.target.value;
                            updateRow(index, {
                              type: nextType,
                              tier_index: nextType === "tiered" ? row.tier_index ?? 0 : null,
                              min_k: nextType === "tiered" ? row.min_k ?? 0 : null,
                              max_k: nextType === "tiered" ? row.max_k ?? -1 : null,
                            });
                          }}
                        >
                          {pricingTypes.map((item) => (
                            <option value={item.value} key={item.value}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {isTiered(row) ? (
                          <input
                            type="number"
                            value={numericValue(row.tier_index)}
                            onChange={(event) => updateRow(index, { tier_index: event.target.value })}
                          />
                        ) : (
                          <span className="pricing-dash">-</span>
                        )}
                      </td>
                      <td>
                        {isTiered(row) ? (
                          <div className="pricing-range">
                            <input type="number" value={numericValue(row.min_k)} onChange={(event) => updateRow(index, { min_k: event.target.value })} />
                            <input type="number" value={numericValue(row.max_k)} onChange={(event) => updateRow(index, { max_k: event.target.value })} />
                          </div>
                        ) : (
                          <span className="pricing-dash">-</span>
                        )}
                      </td>
                      <td>
                        {isMultimodal(row) ? (
                          <span className="pricing-dash">-</span>
                        ) : (
                          <input
                            type="checkbox"
                            checked={checkedValue(row.flat_tier)}
                            onChange={(event) => updateRow(index, { flat_tier: event.target.checked })}
                          />
                        )}
                      </td>
                      <td>
                        <input type="number" step="0.0001" value={numericValue(row.ip)} onChange={(event) => updateRow(index, { ip: event.target.value })} />
                      </td>
                      <td>
                        {isMultimodal(row) ? (
                          <input
                            type="number"
                            step="0.0001"
                            value={numericValue(row.op_text)}
                            onChange={(event) => updateRow(index, { op_text: event.target.value })}
                          />
                        ) : (
                          <input type="number" step="0.0001" value={numericValue(row.op)} onChange={(event) => updateRow(index, { op: event.target.value })} />
                        )}
                      </td>
                      <td>
                        {isMultimodal(row) ? (
                          <input
                            type="number"
                            step="0.0001"
                            value={numericValue(row.op_image)}
                            onChange={(event) => updateRow(index, { op_image: event.target.value })}
                          />
                        ) : (
                          <span className="pricing-dash">-</span>
                        )}
                      </td>
                      <td>
                        {isMultimodal(row) ? (
                          <span className="pricing-dash">-</span>
                        ) : (
                          <input type="number" step="0.0001" value={numericValue(row.chp)} onChange={(event) => updateRow(index, { chp: event.target.value })} />
                        )}
                      </td>
                      <td>
                        {isMultimodal(row) ? (
                          <span className="pricing-dash">-</span>
                        ) : (
                          <input type="number" step="0.0001" value={numericValue(row.cwp)} onChange={(event) => updateRow(index, { cwp: event.target.value })} />
                        )}
                      </td>
                      <td>
                        {isMultimodal(row) ? (
                          <span className="pricing-dash">-</span>
                        ) : (
                          <input
                            type="number"
                            step="0.0001"
                            value={numericValue(row.cwp_1h)}
                            onChange={(event) => updateRow(index, { cwp_1h: event.target.value })}
                          />
                        )}
                      </td>
                      <td>
                        <input value={row.note || ""} onChange={(event) => updateRow(index, { note: event.target.value })} />
                      </td>
                      <td>
                        <div className="pricing-row-actions">
                          {isTiered(row) ? (
                            <button type="button" className="icon-btn" onClick={() => addTier(row.model)} title="添加阶梯">
                              <Plus size={14} />
                            </button>
                          ) : null}
                          <button type="button" className="icon-btn" onClick={() => wb.setPricingRows((rows) => rows.filter((_, i) => i !== index))} title="删除">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="暂无刊例价" hint="从 scripts/athena 导入，或新增模型后保存。" />
          )}
        </CardContent>
      </Card>

      <div className="discounts-actions">
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
          保存刊例价（立即生效）
        </Button>
      </div>
    </div>
  );
}
