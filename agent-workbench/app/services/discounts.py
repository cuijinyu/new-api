"""折扣快照展开与写回：对齐 pricing_engine 的 cost/revenue 折扣结构。"""

from __future__ import annotations

from typing import Any


def flatten_discounts(discounts: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    cost_rows: list[dict[str, Any]] = []
    revenue_rows: list[dict[str, Any]] = []
    if not isinstance(discounts, dict):
        discounts = {}
    cost_root = discounts.get("cost_discounts") if isinstance(discounts.get("cost_discounts"), dict) else {}
    for ch_id, entry in cost_root.get("by_channel", {}).items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("_name") or "")
        for model, rate in entry.items():
            if str(model).startswith("_"):
                continue
            cost_rows.append({
                "channel_id": str(ch_id),
                "channel_name": name,
                "model": str(model),
                "discount": float(rate),
            })
    rev_root = discounts.get("revenue_discounts") if isinstance(discounts.get("revenue_discounts"), dict) else {}
    for uid, entry in rev_root.get("by_user", {}).items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("_name") or "")
        for model, rate in entry.items():
            if str(model).startswith("_"):
                continue
            revenue_rows.append({
                "user_id": str(uid),
                "user_name": name,
                "model": str(model),
                "discount": float(rate),
            })
    return {"cost_rows": cost_rows, "revenue_rows": revenue_rows}


def _rows_to_cost_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_channel: dict[str, dict[str, Any]] = {}
    for row in rows:
        ch_id = str(row.get("channel_id") or "").strip()
        if not ch_id:
            continue
        model = str(row.get("model") or "*").strip() or "*"
        entry = by_channel.setdefault(ch_id, {})
        if row.get("channel_name"):
            entry["_name"] = str(row["channel_name"])
        entry[model] = float(row.get("discount") or 1.0)
    return by_channel


def _rows_to_revenue_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_user: dict[str, dict[str, Any]] = {}
    for row in rows:
        uid = str(row.get("user_id") or "").strip()
        if not uid:
            continue
        model = str(row.get("model") or "*").strip() or "*"
        entry = by_user.setdefault(uid, {})
        if row.get("user_name"):
            entry["_name"] = str(row["user_name"])
        entry[model] = float(row.get("discount") or 1.0)
    return by_user


def apply_discount_rows(
    discounts: dict[str, Any],
    cost_rows: list[dict[str, Any]],
    revenue_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    base = dict(discounts) if isinstance(discounts, dict) else {}
    cost_discounts = dict(base.get("cost_discounts") or {})
    revenue_discounts = dict(base.get("revenue_discounts") or {})
    defaults = cost_discounts.get("defaults") if isinstance(cost_discounts.get("defaults"), dict) else {"*": 1.0}
    cost_discounts["defaults"] = defaults
    cost_discounts["by_channel"] = _rows_to_cost_map(cost_rows)
    rev_defaults = revenue_discounts.get("defaults") if isinstance(revenue_discounts.get("defaults"), dict) else {"*": 1.0}
    revenue_discounts["defaults"] = rev_defaults
    revenue_discounts["by_user"] = _rows_to_revenue_map(revenue_rows)
    return {**base, "cost_discounts": cost_discounts, "revenue_discounts": revenue_discounts}
