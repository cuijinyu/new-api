"""
从 MySQL dump 中提取 logs 表数据，导入 SQLite，按模型汇总对账。
"""
import sqlite3
import re
import json
import os
import sys
import time
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SQL_FILE = os.path.join(os.path.dirname(__file__), "new-api_20260311155621w2vvh.sql")
DB_FILE = os.path.join(os.path.dirname(__file__), "logs_analysis.db")
QUOTA_PER_UNIT = 500_000.0  # $0.002 / 1K tokens => $1 = 500,000 quota

def create_db(conn):
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS logs")
    c.execute("""
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            created_at INTEGER,
            type INTEGER,
            content TEXT,
            username TEXT,
            token_name TEXT,
            model_name TEXT,
            quota INTEGER DEFAULT 0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            use_time INTEGER DEFAULT 0,
            is_stream INTEGER,
            channel_id INTEGER,
            channel_name TEXT,
            token_id INTEGER DEFAULT 0,
            "group" TEXT,
            ip TEXT,
            other TEXT
        )
    """)
    c.execute("CREATE INDEX idx_model ON logs(model_name)")
    c.execute("CREATE INDEX idx_type ON logs(type)")
    c.execute("CREATE INDEX idx_created_at ON logs(created_at)")
    conn.commit()


def parse_mysql_values(line):
    """Parse MySQL INSERT INTO ... VALUES (...),(...),... into list of tuples."""
    # Find the VALUES part
    m = re.match(r"INSERT INTO `\w+` VALUES\s*", line)
    if not m:
        return []
    
    values_str = line[m.end():]
    if values_str.endswith(";"):
        values_str = values_str[:-1]
    
    rows = []
    i = 0
    n = len(values_str)
    
    while i < n:
        # Skip whitespace and commas
        while i < n and values_str[i] in (' ', ',', '\n', '\r'):
            i += 1
        if i >= n:
            break
        if values_str[i] != '(':
            i += 1
            continue
        
        # Parse one tuple
        i += 1  # skip '('
        fields = []
        while i < n:
            # Skip whitespace
            while i < n and values_str[i] == ' ':
                i += 1
            if i >= n:
                break
            
            if values_str[i] == ')':
                i += 1
                break
            
            if values_str[i] == ',':
                i += 1
                continue
            
            if values_str[i] == "'":
                # Quoted string
                i += 1
                parts = []
                while i < n:
                    if values_str[i] == '\\':
                        if i + 1 < n:
                            next_ch = values_str[i+1]
                            if next_ch == "'":
                                parts.append("'")
                            elif next_ch == '"':
                                parts.append('"')
                            elif next_ch == '\\':
                                parts.append('\\')
                            elif next_ch == 'n':
                                parts.append('\n')
                            elif next_ch == 'r':
                                parts.append('\r')
                            elif next_ch == 't':
                                parts.append('\t')
                            elif next_ch == '0':
                                parts.append('\0')
                            else:
                                parts.append(next_ch)
                            i += 2
                        else:
                            parts.append('\\')
                            i += 1
                    elif values_str[i] == "'":
                        i += 1
                        break
                    else:
                        parts.append(values_str[i])
                        i += 1
                fields.append(''.join(parts))
            elif values_str[i:i+4] == 'NULL':
                fields.append(None)
                i += 4
            else:
                # Number or other literal
                j = i
                while i < n and values_str[i] not in (',', ')'):
                    i += 1
                fields.append(values_str[j:i].strip())
            
        rows.append(tuple(fields))
    
    return rows


def import_logs(conn):
    """Read SQL file and import logs table data."""
    c = conn.cursor()
    
    in_logs_section = False
    total_rows = 0
    batch = []
    
    print("Reading SQL file...")
    t0 = time.time()
    
    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.rstrip('\n')
            
            if "Dumping data for table `logs`" in line:
                in_logs_section = True
                continue
            
            if in_logs_section and line.startswith("UNLOCK TABLES"):
                in_logs_section = False
                break
            
            if in_logs_section and line.startswith("INSERT INTO `logs`"):
                rows = parse_mysql_values(line)
                for row in rows:
                    # Ensure we have exactly 19 fields
                    if len(row) < 19:
                        row = row + (None,) * (19 - len(row))
                    elif len(row) > 19:
                        row = row[:19]
                    
                    # Convert numeric fields
                    converted = []
                    for idx, val in enumerate(row):
                        if val is None:
                            converted.append(None)
                        elif idx in (0, 1, 2, 3, 8, 9, 10, 11, 12, 14, 16):
                            # Integer fields: id, user_id, created_at, type, quota, 
                            # prompt_tokens, completion_tokens, use_time, is_stream, channel_id, token_id
                            # Note: channel_name is idx=15 (text), group is idx=16 (text)
                            # Fix: channel_id=14 is not in this list correctly
                            try:
                                converted.append(int(val))
                            except (ValueError, TypeError):
                                converted.append(val)
                        else:
                            converted.append(val)
                    batch.append(tuple(converted))
                
                if len(batch) >= 10000:
                    c.executemany("INSERT OR IGNORE INTO logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                    total_rows += len(batch)
                    batch = []
                    print(f"  Imported {total_rows} rows... ({time.time()-t0:.1f}s)")
    
    if batch:
        c.executemany("INSERT OR IGNORE INTO logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
        total_rows += len(batch)
    
    conn.commit()
    elapsed = time.time() - t0
    print(f"Done. Imported {total_rows} rows in {elapsed:.1f}s")
    return total_rows


def analyze(conn):
    """Run analysis queries."""
    c = conn.cursor()
    
    # type=2 是消费日志 (LogTypeConsume)
    print("\n" + "="*100)
    print("1. 总览 (type=2 消费日志)")
    print("="*100)
    c.execute("""
        SELECT 
            COUNT(*) as total_requests,
            SUM(quota) as total_quota,
            SUM(prompt_tokens) as total_prompt,
            SUM(completion_tokens) as total_completion,
            ROUND(SUM(quota) / ?, 6) as total_cost_usd
        FROM logs WHERE type = 2
    """, (QUOTA_PER_UNIT,))
    row = c.fetchone()
    print(f"  总请求数: {row[0]:,}")
    print(f"  总 quota: {row[1]:,}")
    print(f"  总 prompt_tokens: {row[2]:,}")
    print(f"  总 completion_tokens: {row[3]:,}")
    print(f"  总费用 (USD): ${row[4]:,.6f}")
    print(f"  总费用 (RMB): ¥{row[4]*7.3:,.2f}")
    
    # 按模型汇总
    print("\n" + "="*100)
    print("2. 按模型汇总 (type=2)")
    print("="*100)
    c.execute("""
        SELECT 
            model_name,
            COUNT(*) as cnt,
            SUM(prompt_tokens) as sum_prompt,
            SUM(completion_tokens) as sum_completion,
            SUM(quota) as sum_quota,
            ROUND(SUM(quota) / ?, 6) as cost_usd
        FROM logs 
        WHERE type = 2
        GROUP BY model_name
        ORDER BY sum_quota DESC
    """, (QUOTA_PER_UNIT,))
    
    print(f"{'Model':<35} {'请求数':>8} {'Prompt Tokens':>15} {'Completion Tokens':>18} {'Quota':>15} {'费用(USD)':>15}")
    print("-" * 110)
    for row in c.fetchall():
        model, cnt, pt, ct, quota, cost = row
        print(f"{model:<35} {cnt:>8,} {pt:>15,} {ct:>18,} {quota:>15,} ${cost:>14,.6f}")
    
    # 按 group 汇总
    print("\n" + "="*100)
    print("3. 按 Group 汇总 (type=2)")
    print("="*100)
    c.execute("""
        SELECT 
            "group",
            COUNT(*) as cnt,
            SUM(quota) as sum_quota,
            ROUND(SUM(quota) / ?, 6) as cost_usd
        FROM logs 
        WHERE type = 2
        GROUP BY "group"
        ORDER BY sum_quota DESC
    """, (QUOTA_PER_UNIT,))
    
    print(f"{'Group':<30} {'请求数':>10} {'Quota':>18} {'费用(USD)':>15}")
    print("-" * 75)
    for row in c.fetchall():
        grp, cnt, quota, cost = row
        print(f"{grp or 'NULL':<30} {cnt:>10,} {quota:>18,} ${cost:>14,.6f}")
    
    # 按日期汇总
    print("\n" + "="*100)
    print("4. 按日期汇总 (type=2)")
    print("="*100)
    c.execute("""
        SELECT 
            DATE(created_at, 'unixepoch') as dt,
            COUNT(*) as cnt,
            SUM(quota) as sum_quota,
            ROUND(SUM(quota) / ?, 6) as cost_usd
        FROM logs 
        WHERE type = 2
        GROUP BY dt
        ORDER BY dt
    """, (QUOTA_PER_UNIT,))
    
    print(f"{'Date':<15} {'请求数':>10} {'Quota':>18} {'费用(USD)':>15}")
    print("-" * 60)
    for row in c.fetchall():
        dt, cnt, quota, cost = row
        print(f"{dt:<15} {cnt:>10,} {quota:>18,} ${cost:>14,.6f}")
    
    # 分析 other 字段中的 group_ratio
    print("\n" + "="*100)
    print("5. Group Ratio 分布 (从 other JSON 字段提取)")
    print("="*100)
    c.execute("""
        SELECT id, model_name, quota, other FROM logs WHERE type = 2 AND other IS NOT NULL LIMIT 500000
    """)
    
    ratio_dist = {}
    total_checked = 0
    for row_id, model, quota, other_json in c.fetchall():
        total_checked += 1
        try:
            other = json.loads(other_json)
            gr = other.get("group_ratio", 1.0)
            gr_key = f"{gr:.2f}"
            if gr_key not in ratio_dist:
                ratio_dist[gr_key] = {"count": 0, "quota": 0}
            ratio_dist[gr_key]["count"] += 1
            ratio_dist[gr_key]["quota"] += quota
        except:
            pass
    
    print(f"  检查了 {total_checked} 条记录")
    print(f"{'Group Ratio':<15} {'请求数':>10} {'Quota':>18} {'费用(USD)':>15}")
    print("-" * 60)
    for gr in sorted(ratio_dist.keys()):
        d = ratio_dist[gr]
        cost = d["quota"] / QUOTA_PER_UNIT
        print(f"{gr:<15} {d['count']:>10,} {d['quota']:>18,} ${cost:>14,.6f}")

    # 对比：去掉 group_ratio 后的「成本价」
    print("\n" + "="*100)
    print("6. 还原成本价（去除 group_ratio）")
    print("="*100)
    c.execute("""
        SELECT model_name, quota, other FROM logs WHERE type = 2
    """)
    
    model_cost = {}
    model_raw = {}
    for model, quota, other_json in c.fetchall():
        if model not in model_cost:
            model_cost[model] = 0
            model_raw[model] = 0
        model_raw[model] += quota
        
        gr = 1.0
        if other_json:
            try:
                other = json.loads(other_json)
                gr = other.get("group_ratio", 1.0)
                if gr <= 0:
                    gr = 1.0
            except:
                pass
        model_cost[model] += quota / gr
    
    total_raw = sum(model_raw.values())
    total_base = sum(model_cost.values())
    
    print(f"{'Model':<35} {'平台扣费(USD)':>15} {'成本价(USD)':>15} {'差额(USD)':>12} {'Group Ratio':>12}")
    print("-" * 95)
    for model in sorted(model_raw.keys(), key=lambda m: model_raw[m], reverse=True):
        raw_usd = model_raw[model] / QUOTA_PER_UNIT
        base_usd = model_cost[model] / QUOTA_PER_UNIT
        diff = raw_usd - base_usd
        avg_ratio = model_raw[model] / model_cost[model] if model_cost[model] > 0 else 1.0
        print(f"{model:<35} ${raw_usd:>14,.6f} ${base_usd:>14,.6f} ${diff:>11,.4f} {avg_ratio:>11.4f}")
    
    print("-" * 95)
    raw_total_usd = total_raw / QUOTA_PER_UNIT
    base_total_usd = total_base / QUOTA_PER_UNIT
    diff_total = raw_total_usd - base_total_usd
    avg_total_ratio = total_raw / total_base if total_base > 0 else 1.0
    print(f"{'TOTAL':<35} ${raw_total_usd:>14,.6f} ${base_total_usd:>14,.6f} ${diff_total:>11,.4f} {avg_total_ratio:>11.4f}")
    
    # 对比对账脚本结果
    print("\n" + "="*100)
    print("7. 与对账脚本结果对比")
    print("="*100)
    reconcile_results = {
        "claude-3-7-sonnet-20250219": {"count": 25, "cost": 0.005250},
        "claude-haiku-4-5-20251001": {"count": 8500, "cost": 230.665893},
        "claude-opus-4-1-20250805": {"count": 36, "cost": 0.608640},
        "claude-opus-4-20250514": {"count": 32, "cost": 21.745319},
        "claude-sonnet-4-6": {"count": 15726, "cost": 4369.368690},
        "deepseek-r1-0528": {"count": 44, "cost": 0.010159},
        "deepseek-v3.2": {"count": 1, "cost": 0.000002},
        "glm-5": {"count": 46, "cost": 0.001748},
        "gpt-5": {"count": 23, "cost": 0.002501},
        "kimi-k2.5": {"count": 23, "cost": 0.000800},
        "seed-1-6-250915": {"count": 23, "cost": 0.004986},
    }
    
    c.execute("""
        SELECT 
            model_name,
            COUNT(*) as cnt,
            SUM(quota) as sum_quota,
            SUM(prompt_tokens) as sum_prompt,
            SUM(completion_tokens) as sum_completion
        FROM logs 
        WHERE type = 2
        GROUP BY model_name
    """)
    
    db_models = {}
    for model, cnt, quota, pt, ct in c.fetchall():
        db_models[model] = {"count": cnt, "quota": quota, "prompt": pt, "completion": ct}
    
    print(f"{'Model':<35} {'DB请求数':>8} {'对账请求数':>10} {'DB费用(USD)':>15} {'对账费用(USD)':>15} {'差额':>12}")
    print("-" * 100)
    
    all_models = set(list(reconcile_results.keys()) + list(db_models.keys()))
    for model in sorted(all_models):
        db = db_models.get(model, {"count": 0, "quota": 0})
        rc = reconcile_results.get(model, {"count": 0, "cost": 0})
        db_cost = db["quota"] / QUOTA_PER_UNIT
        diff = db_cost - rc["cost"]
        print(f"{model:<35} {db['count']:>8,} {rc['count']:>10,} ${db_cost:>14,.6f} ${rc['cost']:>14,.6f} ${diff:>11,.4f}")


def main():
    need_import = not os.path.exists(DB_FILE)
    
    conn = sqlite3.connect(DB_FILE)
    
    if need_import:
        create_db(conn)
        total = import_logs(conn)
        if total == 0:
            print("No logs imported!")
            sys.exit(1)
    else:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM logs")
        total = c.fetchone()[0]
        print(f"DB already exists with {total:,} rows, skipping import.")
    
    analyze(conn)
    conn.close()


if __name__ == "__main__":
    main()
