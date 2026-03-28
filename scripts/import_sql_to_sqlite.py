"""
从 MySQL SQL 备份（.sql.gz）中解析 logs 表数据并导入 SQLite。
一次性读入内存 + 正则定位 INSERT 块 + Python 状态机拆分行（与第一轮相同逻辑）。
"""
import gzip
import re
import sqlite3
import time
from datetime import datetime

SQL_GZ_PATH = "e:/new-api/data/new-api_2026032513132199gwf.sql.gz"
SQLITE_PATH = "e:/new-api/scripts/logs_analysis.db"


def unescape_mysql_string(s):
    return (s
            .replace("\\'", "'")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
            .replace("\\n", "\n")
            .replace("\\r", "\r")
            .replace("\\t", "\t")
            .replace("\\0", "\0"))


def parse_value(token):
    token = token.strip()
    if token == 'NULL':
        return None
    if token.startswith("'") and token.endswith("'"):
        return unescape_mysql_string(token[1:-1])
    try:
        if '.' in token:
            return float(token)
        return int(token)
    except ValueError:
        return token


def split_values_row(row_str):
    fields = []
    current = []
    in_string = False
    escape = False
    for c in row_str:
        if escape:
            current.append(c)
            escape = False
        elif c == '\\' and in_string:
            current.append(c)
            escape = True
        elif c == "'" and not in_string:
            in_string = True
            current.append(c)
        elif c == "'" and in_string:
            in_string = False
            current.append(c)
        elif c == ',' and not in_string:
            fields.append(''.join(current).strip())
            current = []
        else:
            current.append(c)
    if current:
        fields.append(''.join(current).strip())
    return fields


def parse_rows_from_values(values_str):
    rows = []
    depth = 0
    in_string = False
    escape = False
    start = -1
    i = 0
    while i < len(values_str):
        c = values_str[i]
        if escape:
            escape = False
        elif c == '\\' and in_string:
            escape = True
        elif c == "'" and not in_string:
            in_string = True
        elif c == "'" and in_string:
            in_string = False
        elif c == '(' and not in_string:
            if depth == 0:
                start = i + 1
            depth += 1
        elif c == ')' and not in_string:
            depth -= 1
            if depth == 0 and start >= 0:
                rows.append(values_str[start:i])
                start = -1
        i += 1
    return rows


def find_logs_insert_block(gz_path):
    print(f"[*] 读取 {gz_path} ...")
    with gzip.open(gz_path, 'rt', encoding='utf-8', errors='replace') as f:
        content = f.read()

    print("[*] 定位 logs INSERT 块 ...")
    lock_idx = content.find("LOCK TABLES `logs` WRITE")
    if lock_idx < 0:
        print("[!] 未找到 logs 表数据块")
        return []

    unlock_idx = content.find("UNLOCK TABLES", lock_idx)
    logs_block = content[lock_idx:unlock_idx]
    print(f"[*] logs 数据块大小: {len(logs_block)/1024/1024:.1f} MB")

    insert_pattern = re.compile(r"INSERT INTO `logs` VALUES\s*(.+?);", re.DOTALL)
    matches = insert_pattern.findall(logs_block)
    print(f"[*] 找到 {len(matches)} 个 INSERT 语句")
    return matches


def import_to_sqlite(gz_path, sqlite_path):
    conn = sqlite3.connect(sqlite_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    cur = conn.cursor()

    cur.execute("SELECT MAX(id) FROM logs")
    max_existing_id = cur.fetchone()[0] or 0
    print(f"[*] SQLite 中现有最大 id: {max_existing_id:,}")

    insert_blocks = find_logs_insert_block(gz_path)
    if not insert_blocks:
        print("[!] 没有找到数据，退出")
        conn.close()
        return

    total_inserted = 0
    total_skipped = 0
    total_rows = 0

    print("[*] 开始解析并导入 ...")
    t0 = time.time()

    for block_idx, values_str in enumerate(insert_blocks):
        rows = parse_rows_from_values(values_str)

        batch = []
        for row_str in rows:
            fields = split_values_row(row_str)
            if len(fields) != 19:
                continue

            total_rows += 1

            try:
                row_id = int(fields[0].strip())
            except ValueError:
                row_id = 0

            if row_id <= max_existing_id:
                total_skipped += 1
                continue

            batch.append([parse_value(f) for f in fields])

        if batch:
            cur.executemany(
                "INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                batch
            )
            total_inserted += len(batch)

        if (block_idx + 1) % 10 == 0 or block_idx == len(insert_blocks) - 1:
            conn.commit()
            elapsed = time.time() - t0
            print(f"  块 {block_idx+1}/{len(insert_blocks)}: "
                  f"已解析 {total_rows:,} 行, 导入 {total_inserted:,}, 跳过 {total_skipped:,} "
                  f"({elapsed:.1f}s)")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\n[完成] 总计解析 {total_rows:,} 行, 导入 {total_inserted:,} 条新记录, "
          f"跳过 {total_skipped:,} 条已存在记录, 耗时 {elapsed:.1f}s")


if __name__ == "__main__":
    import_to_sqlite(SQL_GZ_PATH, SQLITE_PATH)
