"""Pricing snapshot flatten/write-back helpers for the workbench UI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


PRICING_TYPES = {"flat", "tiered", "multimodal"}
KNOWN_MODEL_KEYS = {
    "name",
    "type",
    "flat_tier",
    "tiers",
    "ip",
    "op",
    "chp",
    "cwp",
    "cwp_1h",
    "op_text",
    "op_image",
    "note",
}


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _float_or_default(value: Any, default: float = 0.0) -> float:
    parsed = _float_or_none(value)
    return default if parsed is None else parsed


def _int_or_default(value: Any, default: int = 0) -> int:
    parsed = _float_or_none(value)
    return default if parsed is None else int(parsed)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _pricing_type(value: Any) -> str:
    text = str(value or "flat").strip().lower()
    return text if text in PRICING_TYPES else "flat"


def _empty_row(model: dict[str, Any], model_type: str, tier_index: int | None = None) -> dict[str, Any]:
    return {
        "model": str(model.get("name") or ""),
        "type": model_type,
        "flat_tier": bool(model.get("flat_tier", False)),
        "tier_index": tier_index,
        "min_k": None,
        "max_k": None,
        "ip": None,
        "op": None,
        "chp": None,
        "cwp": None,
        "cwp_1h": None,
        "op_text": None,
        "op_image": None,
        "note": model.get("note"),
    }


def flatten_pricing(pricing: dict[str, Any] | None) -> dict[str, Any]:
    """Flatten pricing.json models into editable table rows."""
    if not isinstance(pricing, dict):
        pricing = {}
    rows: list[dict[str, Any]] = []
    for model in pricing.get("models", []):
        if not isinstance(model, dict) or not model.get("name"):
            continue
        model_type = _pricing_type(model.get("type"))
        if model_type == "tiered":
            tiers = model.get("tiers") if isinstance(model.get("tiers"), list) else []
            for index, tier in enumerate(tiers):
                if not isinstance(tier, dict):
                    continue
                row = _empty_row(model, model_type, index)
                row.update(
                    {
                        "min_k": tier.get("min_k"),
                        "max_k": tier.get("max_k"),
                        "ip": tier.get("ip"),
                        "op": tier.get("op"),
                        "chp": tier.get("chp"),
                        "cwp": tier.get("cwp"),
                        "cwp_1h": tier.get("cwp_1h"),
                    }
                )
                rows.append(row)
            if not tiers:
                rows.append(_empty_row(model, model_type, 0))
            continue
        row = _empty_row(model, model_type, None)
        row.update(
            {
                "ip": model.get("ip"),
                "op": model.get("op"),
                "chp": model.get("chp"),
                "cwp": model.get("cwp"),
                "cwp_1h": model.get("cwp_1h"),
                "op_text": model.get("op_text"),
                "op_image": model.get("op_image"),
            }
        )
        rows.append(row)
    return {
        "metadata": {
            "version": pricing.get("version"),
            "updated_at": pricing.get("updated_at"),
            "models": len(pricing.get("models", [])) if isinstance(pricing.get("models"), list) else 0,
        },
        "rows": rows,
    }


def _model_extras(model: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(model, dict):
        return {}
    return {key: deepcopy(value) for key, value in model.items() if key not in KNOWN_MODEL_KEYS}


def _flat_model(name: str, model_type: str, row: dict[str, Any], base_model: dict[str, Any] | None) -> dict[str, Any]:
    model = {**_model_extras(base_model), "name": name, "type": model_type, "flat_tier": _bool_value(row.get("flat_tier"))}
    model.update(
        {
            "ip": _float_or_default(row.get("ip")),
            "op": _float_or_default(row.get("op")),
            "chp": _float_or_default(row.get("chp")),
            "cwp": _float_or_default(row.get("cwp")),
            "cwp_1h": _float_or_default(row.get("cwp_1h")),
        }
    )
    note = str(row.get("note") or "").strip()
    if note:
        model["note"] = note
    return model


def _multimodal_model(name: str, row: dict[str, Any], base_model: dict[str, Any] | None) -> dict[str, Any]:
    model = {**_model_extras(base_model), "name": name, "type": "multimodal"}
    model.update(
        {
            "ip": _float_or_default(row.get("ip")),
            "op_text": _float_or_default(row.get("op_text")),
            "op_image": _float_or_default(row.get("op_image")),
        }
    )
    note = str(row.get("note") or "").strip()
    if note:
        model["note"] = note
    return model


def _tier_model(name: str, rows: list[dict[str, Any]], base_model: dict[str, Any] | None) -> dict[str, Any]:
    first = rows[0]
    model = {**_model_extras(base_model), "name": name, "type": "tiered", "flat_tier": _bool_value(first.get("flat_tier"))}
    ordered = sorted(enumerate(rows), key=lambda item: (_int_or_default(item[1].get("tier_index"), item[0]), _float_or_default(item[1].get("min_k"))))
    tiers: list[dict[str, Any]] = []
    for index, row in ordered:
        tiers.append(
            {
                "min_k": _float_or_default(row.get("min_k"), 0.0),
                "max_k": _float_or_default(row.get("max_k"), -1.0),
                "ip": _float_or_default(row.get("ip")),
                "op": _float_or_default(row.get("op")),
                "chp": _float_or_default(row.get("chp")),
                "cwp": _float_or_default(row.get("cwp")),
                "cwp_1h": _float_or_default(row.get("cwp_1h")),
            }
        )
    model["tiers"] = tiers
    note = str(first.get("note") or "").strip()
    if note:
        model["note"] = note
    return model


def apply_pricing_rows(pricing: dict[str, Any] | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace pricing.models with submitted editable rows, preserving metadata."""
    base = deepcopy(pricing) if isinstance(pricing, dict) else {}
    existing_models = {
        str(model.get("name")): model
        for model in base.get("models", [])
        if isinstance(model, dict) and model.get("name")
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        name = str(row.get("model") or row.get("name") or "").strip()
        if not name:
            continue
        if name not in grouped:
            grouped[name] = []
            order.append(name)
        grouped[name].append(row)

    models: list[dict[str, Any]] = []
    for name in order:
        model_rows = grouped[name]
        model_type = _pricing_type(model_rows[0].get("type"))
        base_model = existing_models.get(name)
        if model_type == "tiered":
            models.append(_tier_model(name, model_rows, base_model))
        elif model_type == "multimodal":
            models.append(_multimodal_model(name, model_rows[0], base_model))
        else:
            models.append(_flat_model(name, "flat", model_rows[0], base_model))

    base["models"] = models
    return base
