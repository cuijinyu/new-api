"""
Seed test log data into PostgreSQL for performance testing.

Generates ~100k log records to simulate a production-like workload
on a 1C1G database instance.

Usage:
    pip install "psycopg[binary]"
    python scripts/seed_test_logs.py [--dsn DSN] [--count COUNT]
"""

import argparse
import random
import time
import hashlib

import psycopg
from psycopg.rows import tuple_row

MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
    "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307",
    "deepseek-chat", "deepseek-coder", "gemini-1.5-pro", "gemini-1.5-flash",
]
GROUPS = ["default", "vip", "premium", "free"]
LOG_TYPES = [2, 2, 2, 2, 2, 5, 1, 6]  # weighted: mostly consume
TOKEN_NAMES = [f"token-{i}" for i in range(20)]
USERNAMES = [f"user{i}" for i in range(50)]


def gen_token_key(idx):
    return hashlib.md5(f"test-token-{idx}".encode()).hexdigest()[:32]


def seed_tokens(cur, count=20):
    """Insert fake tokens so GetLogByKey can resolve them."""
    now = int(time.time())
    cur.execute("DELETE FROM tokens WHERE id <= %s", (count,))
    for i in range(1, count + 1):
        cur.execute(
            """INSERT INTO tokens (id, user_id, key, status, name, created_time,
               accessed_time, expired_time, remain_quota, unlimited_quota, used_quota)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (i, 1, gen_token_key(i), 1, TOKEN_NAMES[i - 1], now, now, -1, 500000, False, 0),
        )
    print(f"Seeded {count} tokens")


def seed_logs(cur, count=100_000):
    """Insert fake log records in batches."""
    now = int(time.time())
    thirty_days_ago = now - 30 * 86400
    batch_size = 2000
    total = 0

    while total < count:
        batch = min(batch_size, count - total)
        rows = []
        for _ in range(batch):
            ts = random.randint(thirty_days_ago, now)
            log_type = random.choice(LOG_TYPES)
            token_idx = random.randint(1, 20)
            user_idx = random.randint(0, 49)
            model = random.choice(MODELS)
            prompt = random.randint(50, 8000)
            completion = random.randint(10, 4000)
            quota = random.randint(100, 50000)
            use_time = random.randint(1, 30)

            rows.append((
                USERNAMES[user_idx], ts, log_type, "",
                TOKEN_NAMES[token_idx - 1], model, quota, prompt, completion,
                use_time, random.choice([True, False]),
                random.randint(1, 5), token_idx, random.choice(GROUPS),
                f"10.0.0.{random.randint(1,254)}", "{}", user_idx + 1,
            ))

        cur.executemany(
            """INSERT INTO logs (username, created_at, type, content, token_name,
               model_name, quota, prompt_tokens, completion_tokens, use_time,
               is_stream, channel_id, token_id, "group", ip, other, user_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            rows,
        )
        total += batch
        print(f"  Inserted {total}/{count} logs...", end="\r")

    print(f"\nSeeded {total} log records")


def main():
    parser = argparse.ArgumentParser(description="Seed test log data")
    parser.add_argument("--dsn", default="postgresql://root:123456@localhost:5432/new-api")
    parser.add_argument("--count", type=int, default=100_000)
    args = parser.parse_args()

    with psycopg.connect(args.dsn, autocommit=False) as conn:
        with conn.cursor(row_factory=tuple_row) as cur:
            seed_tokens(cur, 20)
            conn.commit()
            seed_logs(cur, args.count)
            conn.commit()

    print("Done!")


if __name__ == "__main__":
    main()
