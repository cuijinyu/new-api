#!/usr/bin/env node
/**
 * S3 高速并发下载器 —— 将指定日期的原始日志文件批量下载到本地缓存目录。
 * 缓存路径与 Python reconcile 的 data_loader.py 完全兼容。
 *
 * 用法:
 *   node s3_download.mjs --date 2026-03-19
 *   node s3_download.mjs --date-range 2026-03-01 2026-03-10
 *   node s3_download.mjs --date 2026-03-19 --concurrency 300
 */

import { S3Client, ListObjectsV2Command, GetObjectCommand } from "@aws-sdk/client-s3";
import { NodeHttpHandler } from "@smithy/node-http-handler";
import https from "node:https";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── CLI ──────────────────────────────────────────────────────────────────────

function parseCli() {
  const { values } = parseArgs({
    options: {
      date:        { type: "string" },
      "date-range":{ type: "string", multiple: true },
      bucket:      { type: "string", default: env("RAW_LOG_S3_BUCKET", env("S3_BUCKET", "")) },
      region:      { type: "string", default: env("RAW_LOG_S3_REGION", env("S3_REGION", "us-east-1")) },
      prefix:      { type: "string", default: env("RAW_LOG_S3_PREFIX", env("S3_PREFIX", "llm-raw-logs")) },
      endpoint:    { type: "string", default: env("RAW_LOG_S3_ENDPOINT", env("S3_ENDPOINT", "")) },
      "cache-dir": { type: "string", default: ".cache" },
      concurrency: { type: "string", default: "200" },
    },
    strict: false,
  });
  return values;
}

function env(key, fallback = "") {
  return process.env[key] || fallback;
}

// ── S3 client ────────────────────────────────────────────────────────────────

function makeClient(region, endpoint, maxSockets = 200) {
  const agent = new https.Agent({
    maxSockets,
    keepAlive: true,
    keepAliveMsecs: 5000,
  });
  const cfg = {
    region,
    credentials: {
      accessKeyId:     env("RAW_LOG_S3_ACCESS_KEY_ID", env("AWS_ACCESS_KEY_ID")),
      secretAccessKey: env("RAW_LOG_S3_SECRET_ACCESS_KEY", env("AWS_SECRET_ACCESS_KEY")),
    },
    maxAttempts: 4,
    requestHandler: new NodeHttpHandler({
      httpsAgent: agent,
      connectionTimeout: 5000,
      socketTimeout: 30000,
    }),
  };
  if (endpoint) cfg.endpoint = endpoint;
  return new S3Client(cfg);
}

// ── List objects ─────────────────────────────────────────────────────────────

async function listAllKeys(client, bucket, prefix) {
  const keys = [];
  let token;
  let page = 0;
  do {
    const cmd = new ListObjectsV2Command({
      Bucket: bucket, Prefix: prefix, MaxKeys: 1000,
      ...(token ? { ContinuationToken: token } : {}),
    });
    const resp = await client.send(cmd);
    for (const obj of resp.Contents ?? []) keys.push(obj.Key);
    token = resp.IsTruncated ? resp.NextContinuationToken : undefined;
    page++;
    process.stderr.write(`\r  列举中... ${keys.length} 个文件 (第 ${page} 页)`);
  } while (token);
  process.stderr.write(`\r  列举完成: ${keys.length} 个文件 (${page} 页)        \n`);
  return keys;
}

// ── Download one key (no cache check — caller already filtered) ──────────────

async function downloadKey(client, bucket, key, cacheDir) {
  const cmd = new GetObjectCommand({ Bucket: bucket, Key: key });
  const resp = await client.send(cmd);
  const chunks = [];
  for await (const chunk of resp.Body) chunks.push(chunk);
  const buf = Buffer.concat(chunks);

  const cachePath = join(cacheDir, key);
  mkdirSync(dirname(cachePath), { recursive: true });
  writeFileSync(cachePath, buf);
  return buf.length;
}

// ── Progress bar ─────────────────────────────────────────────────────────────

class Progress {
  constructor(total, label) {
    this.total = total;
    this.label = label;
    this.done = 0;
    this.failed = 0;
    this.bytes = 0;
    this.t0 = Date.now();
    this.lastDraw = 0;
  }

  tick(bytes) {
    this.done++;
    if (bytes < 0) this.failed++;
    else this.bytes += bytes;
    this.draw();
  }

  draw(force = false) {
    const now = Date.now();
    if (!force && now - this.lastDraw < 200 && this.done < this.total) return;
    this.lastDraw = now;
    const elapsed = Math.max((now - this.t0) / 1000, 0.001);
    const pct = this.done / Math.max(this.total, 1);
    const w = 30;
    const filled = Math.min(w, Math.round(w * pct));
    const bar = "#".repeat(filled) + "-".repeat(w - filled);
    const speed = (this.done / elapsed).toFixed(0);
    const mbps = ((this.bytes / 1024 / 1024) / elapsed).toFixed(1);
    let line = `\r  [${this.label}] [${bar}] ${this.done}/${this.total}  ${(pct * 100).toFixed(1)}%  ${speed} 文件/s  ${mbps} MB/s`;
    if (this.failed) line += `  失败:${this.failed}`;
    if (this.done >= this.total) line += "\n";
    process.stderr.write(line);
  }

  summary() {
    const elapsed = ((Date.now() - this.t0) / 1000).toFixed(1);
    const mb = (this.bytes / 1024 / 1024).toFixed(1);
    const speed = (this.done / Math.max((Date.now() - this.t0) / 1000, 0.001)).toFixed(0);
    console.log(`  下载完成: ${this.done} 文件, ${elapsed}s, ${mb} MB, ${speed} 文件/s, ${this.failed} 失败`);
  }
}

// ── Concurrency pool ─────────────────────────────────────────────────────────

async function downloadAll(client, bucket, keys, cacheDir, concurrency) {
  const progress = new Progress(keys.length, "download");
  let idx = 0;

  async function worker() {
    while (idx < keys.length) {
      const i = idx++;
      if (i >= keys.length) break;
      try {
        const bytes = await downloadKey(client, bucket, keys[i], cacheDir);
        progress.tick(bytes);
      } catch (e) {
        progress.tick(-1);
      }
    }
  }

  const actualConcurrency = Math.min(concurrency, keys.length);
  const workers = Array.from({ length: actualConcurrency }, () => worker());
  await Promise.all(workers);
  progress.summary();
}

// ── Date helpers ─────────────────────────────────────────────────────────────

function buildDates(args) {
  if (args["date-range"] && args["date-range"].length >= 2) {
    const [start, end] = args["date-range"];
    const dates = [];
    let cur = new Date(start + "T00:00:00Z");
    const last = new Date(end + "T00:00:00Z");
    while (cur <= last) {
      dates.push(cur.toISOString().slice(0, 10));
      cur.setUTCDate(cur.getUTCDate() + 1);
    }
    return dates;
  }
  if (args.date) return [args.date];
  const y = new Date(Date.now() - 86400000);
  return [y.toISOString().slice(0, 10)];
}

// ── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  const args = parseCli();
  const bucket = args.bucket;
  if (!bucket) { console.error("错误: 请设置 S3_BUCKET 或 --bucket"); process.exit(1); }

  const region = args.region;
  const endpoint = args.endpoint;
  const prefix = args.prefix;
  const concurrency = parseInt(args.concurrency, 10) || 200;
  const cacheDir = join(__dirname, args["cache-dir"]);

  mkdirSync(cacheDir, { recursive: true });

  const client = makeClient(region, endpoint, concurrency + 10);
  const dates = buildDates(args);

  console.log(`  S3 下载器 (Node.js)`);
  console.log(`  桶: ${bucket}, 区域: ${region}, 并发: ${concurrency}`);
  console.log(`  缓存目录: ${cacheDir}`);
  console.log(`  日期: ${dates.join(", ")}`);

  for (const dateStr of dates) {
    const dt = new Date(dateStr + "T00:00:00Z");
    const y = dt.getUTCFullYear();
    const m = String(dt.getUTCMonth() + 1).padStart(2, "0");
    const d = String(dt.getUTCDate()).padStart(2, "0");
    const s3Prefix = `${prefix}/${y}/${m}/${d}/`;

    console.log(`\n  [${dateStr}] 列举 ${s3Prefix} ...`);
    const keys = await listAllKeys(client, bucket, s3Prefix);
    console.log(`  [${dateStr}] 找到 ${keys.length} 个文件`);

    if (keys.length === 0) continue;

    const uncached = keys.filter(k => !existsSync(join(cacheDir, k)));
    const cachedCount = keys.length - uncached.length;
    console.log(`  [${dateStr}] 缓存已有: ${cachedCount}, 需下载: ${uncached.length}`);

    if (uncached.length === 0) {
      console.log(`  [${dateStr}] 全部已缓存，跳过`);
      continue;
    }

    await downloadAll(client, bucket, uncached, cacheDir, concurrency);
  }

  console.log("\n  全部完成 ✓");
}

main().catch(e => { console.error(e); process.exit(1); });
