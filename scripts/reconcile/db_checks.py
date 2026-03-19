import csv
import gzip
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import orjson


def _safe_json_loads(text):
    if not text:
        return {}
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_request_path(other_obj):
    v = other_obj.get("request_path")
    return v if isinstance(v, str) else ""


def _contains_failure_hint(content, other_raw):
    text = f"{content or ''}\n{other_raw or ''}".lower()
    keywords = (
        "error", "fail", "failed", "timeout", "overload", "rate limit",
        "insufficient", "invalid", "cancel", "aborted",
        "失败", "错误", "超时", "限流", "取消", "中止", "额度", "余额",
    )
    return any(k in text for k in keywords)


def _has_explicit_error_field(obj):
    """递归检查 other JSON 中是否存在明确错误字段。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = str(k).lower()
            if "error" in key_lower or key_lower in ("failed", "failure", "status_code", "upstream_status"):
                if isinstance(v, bool) and v:
                    return True
                if isinstance(v, (int, float)) and int(v) >= 400:
                    return True
                if isinstance(v, str) and v.strip() and v.strip().lower() not in ("0", "ok", "success", "none", "null"):
                    return True
            if _has_explicit_error_field(v):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_explicit_error_field(item):
                return True
    return False


def _collect_failure_reasons(row, other_obj, failure_mode):
    """
    strict:
      - 仅保留明确失败信号（error 字段 / 失败关键词）
    loose:
      - 兼容旧逻辑，包含 frt=-1000 / zero tokens 等弱信号
    """
    hard_reasons = []
    weak_reasons = []

    if _has_explicit_error_field(other_obj):
        hard_reasons.append("explicit_error_field")
    if _contains_failure_hint(row["content"], row["other"]):
        hard_reasons.append("failure_keyword_hint")

    if row["prompt_tokens"] == 0 and row["completion_tokens"] == 0:
        weak_reasons.append("zero_prompt_and_completion_tokens")
    if row["completion_tokens"] == 0:
        weak_reasons.append("zero_completion_tokens")
    if int(other_obj.get("frt", 0) or 0) == -1000:
        weak_reasons.append("frt_is_minus_1000")

    if failure_mode == "strict":
        return sorted(set(hard_reasons))
    return sorted(set(hard_reasons + weak_reasons))


def _group_retry_clusters(rows, retry_window_sec):
    clusters = []
    if not rows:
        return clusters

    current = [rows[0]]
    for row in rows[1:]:
        prev = current[-1]
        if row["created_at"] - prev["created_at"] <= retry_window_sec:
            current.append(row)
        else:
            if len(current) >= 2:
                clusters.append(current)
            current = [row]
    if len(current) >= 2:
        clusters.append(current)
    return clusters


def run_db_checks(db_path, date_str, retry_window_sec=120, check_output_prefix=None, failure_mode="strict"):
    if not os.path.exists(db_path):
        print(f"错误: DB 文件不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    day_start = int(date_obj.timestamp())
    day_end = int((date_obj + timedelta(days=1)).timestamp())

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT id, user_id, created_at, model_name, quota, prompt_tokens, completion_tokens,
               use_time, token_id, channel_id, channel_name, content, other
        FROM logs
        WHERE type = 2
          AND created_at >= ?
          AND created_at < ?
          AND quota > 0
        ORDER BY user_id, token_id, model_name, prompt_tokens, completion_tokens, quota, created_at, id
        """,
        (day_start, day_end),
    ).fetchall()

    total_billed = len(rows)
    print(f"\n{'='*80}")
    print(f"  DB 异常检查 - {date_str}")
    print(f"{'='*80}")
    print(f"  数据库: {db_path}")
    print(f"  当天计费记录(type=2, quota>0): {total_billed:,}")
    print(f"  重试窗口: {retry_window_sec}s")
    print(f"  失败判定口径: {failure_mode}")

    by_sig = defaultdict(list)
    failed_billed_rows = []
    failed_reason_counter = Counter()

    for row in rows:
        other_obj = _safe_json_loads(row["other"])
        request_path = _get_request_path(other_obj)

        sig = (
            row["user_id"],
            row["token_id"],
            row["model_name"],
            row["prompt_tokens"],
            row["completion_tokens"],
            row["quota"],
            request_path,
        )
        by_sig[sig].append(row)

        reasons = _collect_failure_reasons(row, other_obj, failure_mode)
        if reasons:
            failed_billed_rows.append({
                "id": row["id"],
                "created_at": datetime.fromtimestamp(row["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                "user_id": row["user_id"],
                "token_id": row["token_id"],
                "model_name": row["model_name"],
                "quota": row["quota"],
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "use_time": row["use_time"],
                "channel_id": row["channel_id"],
                "channel_name": row["channel_name"] or "",
                "request_path": request_path,
                "reasons": "|".join(reasons),
            })
            for reason in reasons:
                failed_reason_counter[reason] += 1

    retry_clusters = []
    duplicate_rows = []
    duplicate_quota = 0
    for sig_rows in by_sig.values():
        if len(sig_rows) < 2:
            continue
        clusters = _group_retry_clusters(sig_rows, retry_window_sec)
        for cluster in clusters:
            first = cluster[0]
            extras = cluster[1:]
            extra_quota = sum(r["quota"] for r in extras)
            duplicate_quota += extra_quota
            retry_clusters.append({
                "user_id": first["user_id"],
                "token_id": first["token_id"],
                "model_name": first["model_name"],
                "prompt_tokens": first["prompt_tokens"],
                "completion_tokens": first["completion_tokens"],
                "quota": first["quota"],
                "request_path": _get_request_path(_safe_json_loads(first["other"])),
                "cluster_count": len(cluster),
                "duplicate_count": len(extras),
                "cluster_start": datetime.fromtimestamp(first["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                "cluster_end": datetime.fromtimestamp(cluster[-1]["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                "duplicate_quota_sum": extra_quota,
                "id_chain": ",".join(str(r["id"]) for r in cluster),
            })
            for r in extras:
                duplicate_rows.append({
                    "id": r["id"],
                    "created_at": datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "user_id": r["user_id"],
                    "token_id": r["token_id"],
                    "model_name": r["model_name"],
                    "quota": r["quota"],
                    "prompt_tokens": r["prompt_tokens"],
                    "completion_tokens": r["completion_tokens"],
                    "channel_id": r["channel_id"],
                    "channel_name": r["channel_name"] or "",
                    "request_path": _get_request_path(_safe_json_loads(r["other"])),
                    "cluster_start_id": first["id"],
                })

    print("\n  [1] 疑似重试重复计费")
    print(f"      簇数量: {len(retry_clusters):,}")
    print(f"      重复计费条数(每簇去掉首条): {len(duplicate_rows):,}")
    print(f"      重复计费 quota 合计: {duplicate_quota:,}")
    if retry_clusters:
        by_model = Counter()
        for c in retry_clusters:
            by_model[c["model_name"]] += c["duplicate_quota_sum"]
        print("      Top 模型(按疑似重复 quota):")
        for model, quota in by_model.most_common(10):
            print(f"        {model:<35} {quota:>12,}")

    print("\n  [2] 疑似请求失败但计费")
    print(f"      记录数: {len(failed_billed_rows):,}")
    print("      原因分布:")
    for reason, cnt in failed_reason_counter.most_common():
        print(f"        {reason:<36} {cnt:>10,}")

    if check_output_prefix:
        dup_file = f"{check_output_prefix}_duplicates.csv"
        dup_cluster_file = f"{check_output_prefix}_duplicate_clusters.csv"
        fail_file = f"{check_output_prefix}_failed_billed.csv"

        with open(dup_file, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "id", "created_at", "user_id", "token_id", "model_name", "quota",
                "prompt_tokens", "completion_tokens", "channel_id", "channel_name",
                "request_path", "cluster_start_id",
            ])
            w.writeheader()
            w.writerows(duplicate_rows)

        with open(dup_cluster_file, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "user_id", "token_id", "model_name", "prompt_tokens", "completion_tokens",
                "quota", "request_path", "cluster_count", "duplicate_count",
                "cluster_start", "cluster_end", "duplicate_quota_sum", "id_chain",
            ])
            w.writeheader()
            w.writerows(retry_clusters)

        with open(fail_file, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "id", "created_at", "user_id", "token_id", "model_name", "quota",
                "prompt_tokens", "completion_tokens", "use_time", "channel_id",
                "channel_name", "request_path", "reasons",
            ])
            w.writeheader()
            w.writerows(failed_billed_rows)

        print("\n  CSV 导出:")
        print(f"    - {dup_file}")
        print(f"    - {dup_cluster_file}")
        print(f"    - {fail_file}")

    print(f"{'='*80}\n")
    conn.close()


def _parse_raw_created_at_to_epoch(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return int(dt.timestamp())
    except ValueError:
        return None


def run_raw_detail_cross_check(
    db_path,
    date_str,
    bucket,
    prefix,
    region,
    endpoint,
    cache_dir=None,
    bucket_sec=60,
    output_prefix=None,
):
    """
    用原始明细(S3)对照 logs 落账数据：
    - key: user/model/input/output + 时间分桶
    - 若 db_count > raw_count，计为疑似多入账
    """
    if bucket_sec <= 0:
        bucket_sec = 60

    if not os.path.exists(db_path):
        print(f"错误: DB 文件不存在: {db_path}", file=sys.stderr)
        sys.exit(1)

    from data_loader import download_and_parse, get_s3_client, list_s3_objects
    from usage_parser import extract_usage

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    day_start = int(date_obj.timestamp())
    day_end = int((date_obj + timedelta(days=1)).timestamp())
    s3_prefix = f"{prefix}/{date_obj.strftime('%Y/%m/%d')}/"

    def _parse_cached_gzip_file(path):
        try:
            with open(path, "rb") as f:
                raw = f.read()
            data = gzip.decompress(raw)
        except Exception:
            return []
        records = []
        for line in data.decode("utf-8", errors="replace").strip().split("\n"):
            if not line.strip():
                continue
            try:
                records.append(orjson.loads(line))
            except orjson.JSONDecodeError:
                continue
        return records

    def _list_cached_entries(cache_root, key_prefix):
        base = os.path.join(cache_root, key_prefix)
        entries = []
        if not os.path.isdir(base):
            return entries
        for root, _, files in os.walk(base):
            for name in files:
                p = os.path.join(root, name)
                rel = os.path.relpath(p, cache_root).replace("\\", "/")
                entries.append((rel, p))
        return entries

    cached_entries = _list_cached_entries(cache_dir, s3_prefix) if cache_dir else []
    use_cache_only = not bucket
    s3 = None
    keys = []
    if not use_cache_only:
        s3 = get_s3_client(region, endpoint)
        keys = list_s3_objects(s3, bucket, s3_prefix)
    else:
        keys = [k for k, _ in cached_entries]

    raw_counter = Counter()
    raw_req_samples = defaultdict(list)
    raw_total = 0
    raw_usage_ok = 0
    raw_parse_fail = 0
    raw_download_fail = 0

    total_keys = len(keys)
    t0 = datetime.now()
    if total_keys:
        print(f"      开始扫描原始明细文件: {total_keys:,} 个")
    for idx, key in enumerate(keys, 1):
        records = None
        if use_cache_only:
            cache_path = os.path.join(cache_dir, key) if cache_dir else None
            if not cache_path or not os.path.exists(cache_path):
                raw_download_fail += 1
                continue
            records = _parse_cached_gzip_file(cache_path)
        else:
            try:
                records = download_and_parse(s3, bucket, key, cache_dir=cache_dir)
            except Exception:
                raw_download_fail += 1
                continue
        for rec in records:
            raw_total += 1
            usage, _ = extract_usage(rec)
            if usage is None:
                raw_parse_fail += 1
                continue
            raw_usage_ok += 1

            ts = _parse_raw_created_at_to_epoch(rec.get("created_at"))
            if ts is None:
                continue
            key_tuple = (
                rec.get("user_id", 0),
                rec.get("model", "unknown"),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                ts // bucket_sec,
            )
            raw_counter[key_tuple] += 1
            rid = rec.get("request_id", "")
            if rid and len(raw_req_samples[key_tuple]) < 3:
                raw_req_samples[key_tuple].append(rid)
        if idx % 200 == 0 or idx == total_keys:
            elapsed = (datetime.now() - t0).total_seconds()
            speed = idx / elapsed if elapsed > 0 else 0.0
            print(
                f"      进度: {idx:,}/{total_keys:,} 文件 "
                f"({idx / max(total_keys, 1) * 100:.1f}%), "
                f"{speed:.1f} 文件/s",
                flush=True,
            )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    db_rows = cur.execute(
        """
        SELECT id, user_id, created_at, model_name, quota, prompt_tokens, completion_tokens
        FROM logs
        WHERE type = 2
          AND quota > 0
          AND created_at >= ?
          AND created_at < ?
        ORDER BY created_at, id
        """,
        (day_start, day_end),
    ).fetchall()

    db_counter = Counter()
    db_quota_map = defaultdict(list)
    db_id_map = defaultdict(list)
    for row in db_rows:
        key_tuple = (
            row["user_id"],
            row["model_name"],
            row["prompt_tokens"],
            row["completion_tokens"],
            int(row["created_at"]) // bucket_sec,
        )
        db_counter[key_tuple] += 1
        db_quota_map[key_tuple].append(int(row["quota"] or 0))
        if len(db_id_map[key_tuple]) < 5:
            db_id_map[key_tuple].append(row["id"])

    suspicious_groups = []
    excess_rows_total = 0
    excess_quota_min_total = 0
    excess_quota_max_total = 0

    for key_tuple, db_count in db_counter.items():
        raw_count = raw_counter.get(key_tuple, 0)
        if db_count <= raw_count:
            continue
        excess = db_count - raw_count
        quotas = db_quota_map.get(key_tuple, [])
        q_sorted_asc = sorted(quotas)
        q_sorted_desc = sorted(quotas, reverse=True)
        q_min = sum(q_sorted_asc[:excess]) if quotas else 0
        q_max = sum(q_sorted_desc[:excess]) if quotas else 0
        excess_rows_total += excess
        excess_quota_min_total += q_min
        excess_quota_max_total += q_max

        bucket_start_ts = key_tuple[4] * bucket_sec
        suspicious_groups.append({
            "bucket_start": datetime.fromtimestamp(bucket_start_ts).strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": key_tuple[0],
            "model_name": key_tuple[1],
            "input_tokens": key_tuple[2],
            "output_tokens": key_tuple[3],
            "raw_count": raw_count,
            "db_count": db_count,
            "excess_count": excess,
            "excess_quota_min": q_min,
            "excess_quota_max": q_max,
            "db_sample_ids": ",".join(str(x) for x in db_id_map.get(key_tuple, [])),
            "raw_sample_request_ids": ",".join(raw_req_samples.get(key_tuple, [])),
        })

    suspicious_groups.sort(
        key=lambda x: (x["excess_quota_max"], x["excess_count"]),
        reverse=True,
    )

    print("\n  [3] 原始明细 vs logs 对照")
    print(f"      日期: {date_str}")
    if use_cache_only:
        print(f"      数据来源: 本地缓存(.cache)")
        print(f"      缓存文件数: {len(keys):,} (读取失败 {raw_download_fail})")
    else:
        print(f"      数据来源: S3 + 本地缓存命中")
        print(f"      S3 文件数: {len(keys):,} (下载失败 {raw_download_fail})")
    print(f"      原始记录: {raw_total:,}  usage可解析: {raw_usage_ok:,}  解析失败: {raw_parse_fail:,}")
    print(f"      时间分桶: {bucket_sec}s")
    print(f"      疑似多入账分组: {len(suspicious_groups):,}")
    print(f"      疑似多入账条数: {excess_rows_total:,}")
    print(f"      疑似多入账 quota 区间估算: [{excess_quota_min_total:,}, {excess_quota_max_total:,}]")

    if suspicious_groups:
        print("      Top 分组(按excess_quota_max):")
        for row in suspicious_groups[:10]:
            print(
                f"        {row['bucket_start']}  u={row['user_id']}  {row['model_name']:<30} "
                f"db/raw={row['db_count']}/{row['raw_count']}  excess={row['excess_count']}  "
                f"quota_max={row['excess_quota_max']:,}"
            )

    if output_prefix:
        out_file = f"{output_prefix}_raw_vs_db_suspicious.csv"
        with open(out_file, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=[
                "bucket_start", "user_id", "model_name", "input_tokens", "output_tokens",
                "raw_count", "db_count", "excess_count",
                "excess_quota_min", "excess_quota_max",
                "db_sample_ids", "raw_sample_request_ids",
            ])
            w.writeheader()
            w.writerows(suspicious_groups)
        print(f"      CSV 导出: {out_file}")

    conn.close()
