import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime

from costing import calc_cost, calc_web_search_cost
from data_loader import (
    download_and_parse,
    download_one,
    get_s3_client,
    list_s3_objects,
    prioritize_cached_keys,
)
from usage_parser import extract_usage


def get_group_key(record, usage, group_by):
    if group_by == "model":
        return record.get("model", "unknown")
    if group_by == "channel":
        return f"{record.get('channel_id', 0)}-{record.get('channel_name', 'unknown')}"
    if group_by == "user":
        return str(record.get("user_id", 0))
    if group_by == "hour":
        try:
            dt = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:00")
        except (ValueError, KeyError):
            return "unknown"
    return "unknown"


def new_stat_bucket():
    return {
        "count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "web_search_calls": 0,
        "cost": 0.0,
        "web_search_cost": 0.0,
        "errors": 0,
        "no_pricing": 0,
    }


def merge_stats(dst, src):
    for key, bucket in src.items():
        out = dst[key]
        for field, value in bucket.items():
            out[field] += value


class ProgressBar:
    def __init__(self, total, label, enabled=True, width=28):
        self.total = max(total, 0)
        self.label = label
        self.enabled = enabled and total > 1
        self.width = width
        self.completed = 0
        self.failures = 0
        self.start_time = time.time()
        self.last_draw = 0.0
        if self.enabled:
            self._draw(force=True)

    def update(self, completed=0, failures=0, force=False):
        self.completed += completed
        self.failures += failures
        if self.completed > self.total:
            self.completed = self.total
        self._draw(force=force)

    def close(self):
        if not self.enabled:
            return
        self._draw(force=True)
        if self.completed < self.total:
            print(file=sys.stderr, flush=True)

    def _draw(self, force=False):
        if not self.enabled:
            return
        now = time.time()
        if not force and self.completed < self.total and (now - self.last_draw) < 0.2:
            return
        self.last_draw = now
        elapsed = max(now - self.start_time, 0.001)
        pct = self.completed / max(self.total, 1)
        filled = min(self.width, int(self.width * pct))
        bar = "#" * filled + "-" * (self.width - filled)
        speed = self.completed / elapsed
        line = (
            f"\r  [{self.label}] [{bar}] "
            f"{self.completed}/{self.total} {pct * 100:5.1f}% "
            f"{speed:6.1f} 文件/s"
        )
        if self.failures:
            line += f"  失败:{self.failures}"
        end = "\n" if self.completed >= self.total else ""
        print(line, end=end, file=sys.stderr, flush=True)


def build_detail_row(date_str, record, model, usage, ws_count, cost, group_key):
    return {
        "date": date_str,
        "request_id": record.get("request_id", ""),
        "model": model,
        "channel_id": record.get("channel_id", 0),
        "channel_name": record.get("channel_name", ""),
        "user_id": record.get("user_id", 0),
        "status_code": record.get("status_code", 0),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cache_read_tokens": usage["cache_read_tokens"],
        "cache_creation_tokens": usage["cache_creation_tokens"],
        "cache_5m_tokens": usage["cache_creation_5m_tokens"],
        "cache_1h_tokens": usage["cache_creation_1h_tokens"],
        "web_search_calls": ws_count,
        "cost_usd": round(cost, 8),
        "group_key": group_key,
    }


def process_records(records, date_str, pricing_cfg, group_by,
                    filter_user_ids=None, filter_models=None, filter_channel_ids=None,
                    time_from=None, time_to=None, collect_details=True):
    models_pricing = pricing_cfg.get("models", {})
    web_search_cfg = pricing_cfg.get("web_search", {})
    user_id_set = set(filter_user_ids) if filter_user_ids else None
    model_set = set(filter_models) if filter_models else None
    channel_id_set = set(filter_channel_ids) if filter_channel_ids else None

    stats = defaultdict(new_stat_bucket)
    details = []
    total_records = len(records)
    filtered_out = 0
    parse_failures = 0
    error_categories = Counter()

    for rec in records:
        if time_from or time_to:
            ts = rec.get("created_at", "")
            if ts:
                if time_from and ts < time_from:
                    filtered_out += 1
                    continue
                if time_to and ts > time_to:
                    filtered_out += 1
                    continue

        if user_id_set and rec.get("user_id", 0) not in user_id_set:
            filtered_out += 1
            continue
        if channel_id_set and rec.get("channel_id", 0) not in channel_id_set:
            filtered_out += 1
            continue

        model = rec.get("model", "unknown")
        if model_set and model not in model_set:
            filtered_out += 1
            continue

        usage, fail_reason = extract_usage(rec)
        if usage is None:
            parse_failures += 1
            error_categories[fail_reason] += 1
            continue

        model_pricing = models_pricing.get(model)
        group_key = get_group_key(rec, usage, group_by)
        s = stats[group_key]
        s["count"] += 1
        s["input_tokens"] += usage["input_tokens"]
        s["output_tokens"] += usage["output_tokens"]
        s["cache_read_tokens"] += usage["cache_read_tokens"]
        s["cache_creation_tokens"] += usage["cache_creation_tokens"]
        s["web_search_calls"] += usage.get("web_search_requests", 0)

        if rec.get("status_code", 200) >= 400:
            s["errors"] += 1

        if model_pricing:
            cost = calc_cost(usage, model_pricing, model, web_search_cfg)
            s["cost"] += cost
            ws_count = usage.get("web_search_requests", 0)
            ws_cost = 0.0
            if ws_count > 0 and web_search_cfg:
                ws_cost = calc_web_search_cost(model, ws_count, web_search_cfg)
            s["web_search_cost"] += ws_cost

            if collect_details:
                details.append(build_detail_row(
                    date_str, rec, model, usage, ws_count, cost, group_key
                ))
        else:
            s["no_pricing"] += 1

    return stats, details, total_records, parse_failures, filtered_out, error_categories


def _chunk_keys(keys, chunk_size):
    for i in range(0, len(keys), chunk_size):
        yield keys[i:i + chunk_size]


def _process_key_batch(region, endpoint, bucket, keys, cache_dir, date_str, pricing_cfg, group_by,
                       filter_user_ids=None, filter_models=None, filter_channel_ids=None,
                       time_from=None, time_to=None, collect_details=True, download_workers=1):
    stats = defaultdict(new_stat_bucket)
    details = []
    total_records = 0
    filtered_out = 0
    parse_failures = 0
    error_categories = Counter()
    download_errors = 0

    def merge_batch(records):
        nonlocal total_records, filtered_out, parse_failures
        batch = process_records(
            records, date_str, pricing_cfg, group_by,
            filter_user_ids=filter_user_ids, filter_models=filter_models,
            filter_channel_ids=filter_channel_ids, time_from=time_from, time_to=time_to,
            collect_details=collect_details,
        )
        batch_stats, batch_details, batch_total, batch_parse_failures, batch_filtered_out, batch_errors = batch
        merge_stats(stats, batch_stats)
        if collect_details and batch_details:
            details.extend(batch_details)
        total_records += batch_total
        filtered_out += batch_filtered_out
        parse_failures += batch_parse_failures
        error_categories.update(batch_errors)

    if len(keys) <= 1 or download_workers <= 1:
        client = get_s3_client(region, endpoint)
        for key in keys:
            try:
                records = download_and_parse(client, bucket, key, cache_dir=cache_dir)
            except Exception:
                download_errors += 1
                continue
            merge_batch(records)
    else:
        actual_workers = min(download_workers, len(keys))
        with ThreadPoolExecutor(max_workers=actual_workers) as pool:
            future_to_key = {
                pool.submit(download_one, region, endpoint, bucket, key, cache_dir): key
                for key in keys
            }
            for future in as_completed(future_to_key):
                try:
                    records = future.result()
                except Exception:
                    download_errors += 1
                    continue
                merge_batch(records)

    return {
        "stats": {k: dict(v) for k, v in stats.items()},
        "details": details,
        "total_records": total_records,
        "filtered_out": filtered_out,
        "parse_failures": parse_failures,
        "error_categories": dict(error_categories),
        "download_errors": download_errors,
    }


def process_date(s3, bucket, prefix, date_str, pricing_cfg, group_by, verbose,
                 filter_user_ids=None, filter_models=None, filter_channel_ids=None,
                 workers=10, region="", endpoint="", cache_dir=None,
                 time_from=None, time_to=None, processes=0, collect_details=True,
                 process_threads=4):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    s3_prefix = f"{prefix}/{dt.strftime('%Y/%m/%d')}/"

    keys = list_s3_objects(s3, bucket, s3_prefix)
    if verbose:
        print(f"  [{date_str}] 找到 {len(keys)} 个文件")

    stats = defaultdict(new_stat_bucket)
    details = []
    total_records = 0
    filtered_out = 0
    parse_failures = 0
    error_categories = Counter()
    download_errors = 0

    t0 = time.time()
    keys, cache_hits = prioritize_cached_keys(keys, cache_dir=cache_dir)
    if verbose and cache_hits:
        print(f"  [{date_str}] 缓存命中: {cache_hits}/{len(keys)} 文件")
        print(f"  [{date_str}] 已按缓存优先排序")
    progress = ProgressBar(len(keys), date_str)

    def merge_result(result):
        nonlocal total_records, filtered_out, parse_failures, download_errors
        merge_stats(stats, result["stats"])
        if collect_details and result["details"]:
            details.extend(result["details"])
        total_records += result["total_records"]
        filtered_out += result["filtered_out"]
        parse_failures += result["parse_failures"]
        error_categories.update(result["error_categories"])
        download_errors += result.get("download_errors", 0)

    if len(keys) <= 1:
        for key in keys:
            try:
                records = download_and_parse(s3, bucket, key, cache_dir=cache_dir)
            except Exception as e:
                download_errors += 1
                if verbose:
                    print(f"    下载失败 {key}: {e}")
                progress.update(completed=1, failures=1)
                continue
            batch = process_records(
                records, date_str, pricing_cfg, group_by,
                filter_user_ids=filter_user_ids, filter_models=filter_models,
                filter_channel_ids=filter_channel_ids, time_from=time_from, time_to=time_to,
                collect_details=collect_details,
            )
            b_stats, b_details, b_total, b_parse, b_filtered, b_errors = batch
            merge_stats(stats, b_stats)
            if collect_details and b_details:
                details.extend(b_details)
            total_records += b_total
            filtered_out += b_filtered
            parse_failures += b_parse
            error_categories.update(b_errors)
            progress.update(completed=1)
    elif processes and processes > 1:
        actual_processes = min(processes, len(keys))
        chunk_size = max(200, min(1000, len(keys) // (actual_processes * 4) or 1))
        if verbose:
            print(f"  [{date_str}] 多进程处理: {actual_processes} 进程, 每进程 {process_threads} 下载线程, 分块 {chunk_size} 文件")
        with ProcessPoolExecutor(max_workers=actual_processes) as pool:
            future_to_count = {
                pool.submit(
                    _process_key_batch,
                    region, endpoint, bucket, key_batch, cache_dir, date_str, pricing_cfg, group_by,
                    filter_user_ids, filter_models, filter_channel_ids,
                    time_from, time_to, collect_details, process_threads,
                ): len(key_batch)
                for key_batch in _chunk_keys(keys, chunk_size)
            }
            for future in as_completed(future_to_count):
                batch_count = future_to_count[future]
                try:
                    result = future.result()
                    merge_result(result)
                    progress.update(completed=batch_count, failures=result.get("download_errors", 0))
                except Exception as e:
                    download_errors += batch_count
                    if verbose:
                        print(f"    分块处理失败: {e}")
                    progress.update(completed=batch_count, failures=batch_count)
    elif workers <= 1:
        for key in keys:
            try:
                records = download_and_parse(s3, bucket, key, cache_dir=cache_dir)
            except Exception as e:
                download_errors += 1
                if verbose:
                    print(f"    下载失败 {key}: {e}")
                progress.update(completed=1, failures=1)
                continue
            batch = process_records(
                records, date_str, pricing_cfg, group_by,
                filter_user_ids=filter_user_ids, filter_models=filter_models,
                filter_channel_ids=filter_channel_ids, time_from=time_from, time_to=time_to,
                collect_details=collect_details,
            )
            b_stats, b_details, b_total, b_parse, b_filtered, b_errors = batch
            merge_stats(stats, b_stats)
            if collect_details and b_details:
                details.extend(b_details)
            total_records += b_total
            filtered_out += b_filtered
            parse_failures += b_parse
            error_categories.update(b_errors)
            progress.update(completed=1)
    else:
        actual_workers = min(workers, len(keys))
        with ThreadPoolExecutor(max_workers=actual_workers) as pool:
            future_to_key = {
                pool.submit(download_one, region, endpoint, bucket, key, cache_dir): key
                for key in keys
            }
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    records = future.result()
                except Exception as e:
                    download_errors += 1
                    if verbose:
                        print(f"    下载失败 {key}: {e}")
                    progress.update(completed=1, failures=1)
                    continue
                batch = process_records(
                    records, date_str, pricing_cfg, group_by,
                    filter_user_ids=filter_user_ids, filter_models=filter_models,
                    filter_channel_ids=filter_channel_ids, time_from=time_from, time_to=time_to,
                    collect_details=collect_details,
                )
                b_stats, b_details, b_total, b_parse, b_filtered, b_errors = batch
                merge_stats(stats, b_stats)
                if collect_details and b_details:
                    details.extend(b_details)
                total_records += b_total
                filtered_out += b_filtered
                parse_failures += b_parse
                error_categories.update(b_errors)
                progress.update(completed=1)

    elapsed = time.time() - t0
    progress.close()
    if verbose and len(keys) > 1:
        print(f"  [{date_str}] 下载完成: {len(keys)} 文件, {elapsed:.1f}s, "
              f"{len(keys) / max(elapsed, 0.001):.0f} 文件/s"
              + (f", {download_errors} 失败" if download_errors else ""))

    return stats, details, total_records, parse_failures, filtered_out, error_categories
