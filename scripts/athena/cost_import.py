"""
通用成本账单导入器

支持两种格式:
  1. 汇总格式 — 按模型聚合的金额 (model, amount)
  2. 逐条明细格式 — 每行一个请求 (request_id, model_name, quota, ...)
     自动检测: 存在 request_id + quota 列时识别为逐条明细

导入记录保存到 imports/ 目录。
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

_IMPORTS_DIR = Path(__file__).resolve().parent / "imports"

QUOTA_TO_USD = 500_000.0

# Common column name aliases
_MODEL_ALIASES = {"model", "模型", "model_name", "Model", "MODEL"}
_AMOUNT_ALIASES = {"amount", "额度", "total", "cost", "金额", "Amount", "Cost", "Total"}
_COUNT_ALIASES = {"count", "记录数", "calls", "Count", "Calls", "数量"}

# Row-level bill column aliases
_REQUEST_ID_ALIASES = {"request_id", "Request ID", "RequestID"}
_QUOTA_ALIASES = {"quota", "Quota"}
_CREATED_AT_ALIASES = {"created_at", "CreatedAt", "created_time"}


def _detect_column(df_columns, aliases: set) -> str | None:
    """Find the first column name that matches any alias."""
    for col in df_columns:
        if col in aliases or col.strip() in aliases:
            return col
    return None


def import_cost_bill(filepath: str,
                     column_mapping: dict = None,
                     channel_id: int = None,
                     vendor_name: str = None,
                     month: str = None) -> pd.DataFrame:
    """Import a vendor cost bill from CSV or Excel.

    Args:
        filepath: Path to CSV or Excel file
        column_mapping: Optional dict to override column detection,
                        e.g. {"model": "产品名称", "amount": "消费金额"}
        channel_id: Optional channel ID to tag the import
        vendor_name: Optional vendor name for metadata
        month: Optional billing month (YYYY-MM) for metadata

    Returns:
        DataFrame with normalized columns: model, amount, count (if available)
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, engine="openpyxl" if ext == ".xlsx" else None)
    elif ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
            try:
                df = pd.read_csv(filepath, encoding=enc)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        else:
            raise ValueError(f"Cannot decode CSV file: {filepath}")
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    if df.empty:
        raise ValueError("File is empty")

    # Apply column mapping
    mapping = column_mapping or {}
    model_col = mapping.get("model") or _detect_column(df.columns, _MODEL_ALIASES)
    amount_col = mapping.get("amount") or _detect_column(df.columns, _AMOUNT_ALIASES)
    count_col = mapping.get("count") or _detect_column(df.columns, _COUNT_ALIASES)

    if not model_col:
        raise ValueError(
            f"Cannot detect model column. Columns found: {list(df.columns)}. "
            f"Use column_mapping={{'model': 'your_column_name'}}")
    if not amount_col:
        raise ValueError(
            f"Cannot detect amount column. Columns found: {list(df.columns)}. "
            f"Use column_mapping={{'amount': 'your_column_name'}}")

    result = pd.DataFrame()
    result["model"] = df[model_col].astype(str).str.strip()
    result["amount"] = pd.to_numeric(df[amount_col], errors="coerce").fillna(0)
    if count_col:
        result["count"] = pd.to_numeric(df[count_col], errors="coerce").fillna(0).astype(int)

    # Save import record
    _save_import_record(filepath, channel_id, vendor_name, month,
                        len(result), float(result["amount"].sum()))

    return result


def import_and_summarize(filepath: str,
                         column_mapping: dict = None,
                         channel_id: int = None,
                         vendor_name: str = None,
                         month: str = None) -> pd.DataFrame:
    """Import and return model-level summary."""
    raw = import_cost_bill(filepath, column_mapping, channel_id, vendor_name, month)

    agg = {"amount": "sum"}
    if "count" in raw.columns:
        agg["count"] = "sum"

    summary = raw.groupby("model").agg(agg).reset_index()
    summary = summary.rename(columns={"amount": "vendor_amount"})
    if "count" in summary.columns:
        summary = summary.rename(columns={"count": "vendor_count"})

    return summary.sort_values("vendor_amount", ascending=False)


def _save_import_record(filepath: str, channel_id, vendor_name, month,
                        row_count: int, total_amount: float):
    """Save metadata about the import to imports/ directory."""
    _IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(filepath)
    record = {
        "timestamp": ts,
        "original_file": basename,
        "channel_id": channel_id,
        "vendor_name": vendor_name,
        "month": month,
        "row_count": row_count,
        "total_amount": round(total_amount, 4),
    }

    meta_path = _IMPORTS_DIR / f"{ts}_{basename}.meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    copy_path = _IMPORTS_DIR / f"{ts}_{basename}"
    shutil.copy2(filepath, copy_path)


def list_imports() -> list[dict]:
    """List all import records."""
    if not _IMPORTS_DIR.exists():
        return []
    records = []
    for f in sorted(_IMPORTS_DIR.glob("*.meta.json"), reverse=True):
        with open(f, "r", encoding="utf-8") as fh:
            records.append(json.load(fh))
    return records


# ---------------------------------------------------------------------------
# Row-level bill import (e.g. channel 25 format)
# ---------------------------------------------------------------------------

def _read_file(filepath: str) -> pd.DataFrame:
    """Read CSV or Excel file with encoding auto-detection."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(filepath, engine="openpyxl" if ext == ".xlsx" else None)
    elif ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
            try:
                return pd.read_csv(filepath, encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f"Cannot decode CSV file: {filepath}")
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def is_row_level_bill(filepath: str) -> bool:
    """Detect whether a file is a row-level bill (has request_id + quota columns)."""
    df = _read_file(filepath) if isinstance(filepath, str) else filepath
    cols = set(df.columns)
    has_request_id = bool(cols & _REQUEST_ID_ALIASES)
    has_quota = bool(cols & _QUOTA_ALIASES)
    has_model = bool(cols & _MODEL_ALIASES)
    return has_request_id and has_quota and has_model


def import_row_level_bill(filepaths: list[str] | str,
                          channel_id: int = None,
                          vendor_name: str = None,
                          month: str = None) -> pd.DataFrame:
    """Import one or more row-level vendor bills (逐条明细格式).

    Expects columns: request_id, model_name, quota, prompt_tokens,
    completion_tokens, created_at. Filters out rows with model_name=0
    or quota=0 (anomalous records).

    Returns a DataFrame with normalized columns ready for row-level crosscheck.
    """
    if isinstance(filepaths, str):
        filepaths = [filepaths]

    chunks = []
    for fp in filepaths:
        df = _read_file(fp)
        chunks.append(df)
        _save_import_record(fp, channel_id, vendor_name, month,
                            len(df), float(df.get("quota", pd.Series([0])).sum() / QUOTA_TO_USD))

    df = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]

    # Normalize column names
    col_map = {}
    for col in df.columns:
        if col in _REQUEST_ID_ALIASES:
            col_map[col] = "request_id"
        elif col in _MODEL_ALIASES:
            col_map[col] = "model_name"
        elif col in _QUOTA_ALIASES:
            col_map[col] = "quota"
        elif col in _CREATED_AT_ALIASES:
            col_map[col] = "created_at"
    df = df.rename(columns=col_map)

    # Filter anomalous rows
    if "model_name" in df.columns:
        df = df[df["model_name"].astype(str).str.strip() != "0"]
    if "quota" in df.columns:
        df["quota"] = pd.to_numeric(df["quota"], errors="coerce").fillna(0)

    # Compute USD
    df["vendor_usd"] = df["quota"] / QUOTA_TO_USD

    # Ensure numeric columns
    for col in ("prompt_tokens", "completion_tokens"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def summarize_row_level_bill(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize a row-level bill by model for model-level crosscheck."""
    agg = {
        "request_id": "count",
        "vendor_usd": "sum",
    }
    if "prompt_tokens" in df.columns:
        agg["prompt_tokens"] = "sum"
    if "completion_tokens" in df.columns:
        agg["completion_tokens"] = "sum"
    if "quota" in df.columns:
        agg["quota"] = "sum"

    summary = df.groupby("model_name").agg(agg).reset_index()
    summary = summary.rename(columns={
        "request_id": "vendor_count",
        "vendor_usd": "vendor_amount",
    })
    return summary.sort_values("vendor_amount", ascending=False)
