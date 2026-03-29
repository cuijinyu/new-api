"""
通用成本账单导入器

支持 CSV / Excel 格式，自动检测列名，按模型汇总。
导入记录保存到 imports/ 目录。
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

_IMPORTS_DIR = Path(__file__).resolve().parent / "imports"

# Common column name aliases
_MODEL_ALIASES = {"model", "模型", "model_name", "Model", "MODEL"}
_AMOUNT_ALIASES = {"amount", "额度", "total", "cost", "金额", "Amount", "Cost", "Total"}
_COUNT_ALIASES = {"count", "记录数", "calls", "Count", "Calls", "数量"}


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
