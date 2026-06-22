/**
 * Billing UX E2E verification (Playwright).
 *
 * Usage:
 *   WORKBENCH_API_URL=http://127.0.0.1:18093 \
 *   WORKBENCH_WEB_URL=http://127.0.0.1:5175 \
 *   node e2e/billing_ux_verify.mjs
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARTIFACTS = path.join(__dirname, "browser-artifacts");
const API = process.env.WORKBENCH_API_URL || "http://localhost:18092";
const WEB = process.env.WORKBENCH_WEB_URL || "http://127.0.0.1:5174";
const BILLING_POLL_MS = Number(process.env.BILLING_POLL_MS || 600_000);

fs.mkdirSync(ARTIFACTS, { recursive: true });

async function apiJson(pathname, init = {}) {
  const res = await fetch(`${API}${pathname}`, {
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    ...init,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${init.method || "GET"} ${pathname} ${res.status}: ${text}`);
  return text ? JSON.parse(text) : {};
}

async function assertKpiApi() {
  const versions = await apiJson("/api/config/versions");
  const active =
    versions.items?.find((v) => v.status === "active")?.version ||
    versions.items?.[0]?.version ||
    "local-v0";
  const res = await fetch(`${API}/api/billing/kpi-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ month: "2026-06", config_version: active, channel_id: 65 }),
  });
  if (!res.ok) throw new Error(`KPI API ${res.status}: ${await res.text()}`);
  const data = await res.json();
  if (!(Number(data.total_usd) > 0)) throw new Error(`KPI total_usd not > 0: ${JSON.stringify(data)}`);
  return { data, activeVersion: active };
}

async function waitForBillingJob(page, snap) {
  const progress = page.locator(".billing-run-progress");
  const completedBadge = page.getByText("已完成", { exact: true });
  const failed = page.locator(".billing-alert-error");

  await progress.waitFor({ state: "visible", timeout: 120_000 }).catch(() => {});
  await snap("billing-ux-e2e-04-generate-running.png");

  const deadline = Date.now() + BILLING_POLL_MS;
  while (Date.now() < deadline) {
    if (await failed.count()) {
      const msg = await failed.innerText();
      throw new Error(`Billing run failed in UI: ${msg}`);
    }
    if (await completedBadge.count()) break;
    const body = await page.locator("body").innerText();
    if (body.includes("账单结果") && body.includes("总费用")) break;
    await page.waitForTimeout(3000);
  }

  if (!(await completedBadge.count())) {
    const body = await page.locator("body").innerText();
    if (!body.includes("账单结果")) {
      throw new Error("Billing did not complete within timeout");
    }
  }
  await snap("billing-ux-e2e-05-billing-completed.png");
}

async function verifyDownloadFromJob(jobId) {
  const detail = await apiJson(`/api/jobs/${jobId}`);
  const artifacts = await apiJson(`/api/jobs/${jobId}/artifacts`);
  const uris = [];
  const raw = artifacts.artifacts;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    uris.push(...Object.values(raw).filter(Boolean));
  } else if (Array.isArray(artifacts.items)) {
    for (const item of artifacts.items) {
      if (item.uri) uris.push(item.uri);
    }
  }
  if (Array.isArray(artifacts.listed)) {
    uris.push(...artifacts.listed.filter(Boolean));
  }
  if (!uris.length && detail.job?.result_uri) uris.push(detail.job.result_uri);

  const targetUri = uris.find((u) => u.endsWith(".xlsx") || u.endsWith(".json") || u.includes("summary")) || uris[0];
  if (!targetUri) throw new Error(`No artifact URI for job ${jobId}`);

  const url = `${API}/api/billing/download?uri=${encodeURIComponent(targetUri)}`;
  const res = await fetch(url, { redirect: "manual" });
  if (res.status !== 200 && res.status !== 302) {
    throw new Error(`Download ${res.status} for ${targetUri}`);
  }
  if (res.status === 302) {
    const loc = res.headers.get("location");
    if (!loc) throw new Error("Download redirect missing location");
    const follow = await fetch(loc);
    if (!follow.ok) throw new Error(`Download follow ${follow.status}`);
    const buf = Buffer.from(await follow.arrayBuffer());
    if (buf.length < 10) throw new Error("Download body too small");
    return { targetUri, bytes: buf.length };
  }
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.length < 10) throw new Error("Download body too small");
  return { targetUri, bytes: buf.length };
}

async function testDiscountsSave(page, snap) {
  const before = await apiJson("/api/config/versions");
  const beforeCount = before.items?.length || 0;
  const activeBefore = before.items?.find((v) => v.status === "active")?.version;

  await page.getByRole("navigation").getByRole("button", { name: "价格方案", exact: true }).click();
  await page.waitForTimeout(1500);
  await snap("billing-ux-e2e-06-discounts-before-save.png");

  let discountInput = page.locator(".discount-table tbody tr").first().locator('input[type="number"]');
  if (!(await discountInput.count())) {
    const addRow = page.getByRole("button", { name: "增行" }).first();
    await addRow.click();
    await page.waitForTimeout(500);
    const firstRow = page.locator(".discount-table tbody tr").first();
    await firstRow.locator("td").nth(0).locator("input").fill("65");
    await firstRow.locator("td").nth(1).locator("input").fill("e2e-channel");
    await firstRow.locator("td").nth(2).locator("input").fill("*");
    discountInput = firstRow.locator('input[type="number"]');
    await discountInput.fill("0.35");
  } else {
    const current = Number(await discountInput.inputValue());
    await discountInput.fill(String(current === 0.99 ? 0.98 : 0.99));
  }

  await page.getByRole("button", { name: "保存并生成新价格方案" }).click();
  await page.waitForTimeout(5000);
  await snap("billing-ux-e2e-07-discounts-after-save.png");

  const after = await apiJson("/api/config/versions");
  const afterCount = after.items?.length || 0;
  const activeAfter = after.items?.find((v) => v.status === "active")?.version;
  if (afterCount <= beforeCount) {
    throw new Error(`Expected new config version; before=${beforeCount} after=${afterCount}`);
  }
  if (activeAfter === activeBefore) {
    throw new Error(`Active version unchanged: ${activeBefore}`);
  }
  return { beforeCount, afterCount, activeBefore, activeAfter };
}

async function main() {
  const results = { passed: [], failed: [] };
  const pass = (name, detail) => {
    results.passed.push({ name, detail });
    console.log(`PASS ${name}`, detail || "");
  };
  const fail = (name, err) => {
    results.failed.push({ name, error: String(err) });
    console.error(`FAIL ${name}`, err);
  };

  console.log("API KPI check…");
  let kpi;
  try {
    kpi = await assertKpiApi();
    pass("kpi-preview-api", kpi.data);
  } catch (err) {
    fail("kpi-preview-api", err);
    throw err;
  }

  const browser = await chromium.launch({
    headless: true,
    channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
  });
  const page = await browser.newPage();
  const snap = async (name) => {
    const p = path.join(ARTIFACTS, name);
    await page.screenshot({ path: p, fullPage: true });
    console.log("screenshot:", p);
    return p;
  };

  try {
    await page.goto(`${WEB}/#billing`, { waitUntil: "networkidle" });
    await snap("billing-ux-e2e-01-billing-page.png");

    const bodyText = await page.locator("body").innerText();
    if (bodyText.includes("计费口径")) throw new Error('Found deprecated term "计费口径"');
    if (!bodyText.includes("价格方案")) throw new Error('Missing "价格方案" label');
    pass("billing-page-copy");

    await page.waitForTimeout(3000);
    await snap("billing-ux-e2e-02-kpi-after-wait.png");
    pass("kpi-cards-render");

    await page.getByRole("navigation").getByRole("button", { name: "价格方案", exact: true }).click();
    await page.waitForTimeout(1000);
    await snap("billing-ux-e2e-03-discounts-page.png");
    pass("discounts-nav");

    await page.getByRole("navigation").getByRole("button", { name: "生成账单", exact: true }).click();
    await page.waitForTimeout(1500);
    await page.locator(".billing-primary-actions .btn-default").click();

    try {
      await waitForBillingJob(page, snap);
      pass("billing-run-complete");
    } catch (err) {
      fail("billing-run-complete", err);
      await snap("billing-ux-e2e-04-generate-error.png");
      throw err;
    }

    const jobs = await apiJson("/api/jobs");
    const jobId =
      jobs.items?.find((j) => String(j.status).toUpperCase() === "COMPLETED")?.id ||
      jobs.items?.[0]?.id;
    if (!jobId) throw new Error("Could not determine job id");

    try {
      const dl = await verifyDownloadFromJob(jobId);
      pass("download-endpoint", dl);
    } catch (err) {
      fail("download-endpoint", err);
      const dlBtn = page.getByRole("button", { name: /下载|\.xlsx|\.json/i }).first();
      if (await dlBtn.count()) {
        const [download] = await Promise.all([page.waitForEvent("download", { timeout: 30_000 }), dlBtn.click()]);
        const fn = path.join(ARTIFACTS, `billing-ux-e2e-download-${download.suggestedFilename()}`);
        await download.saveAs(fn);
        pass("download-ui-fallback", { fn });
      } else {
        throw err;
      }
    }
    await snap("billing-ux-e2e-08-after-download.png");

    try {
      const disc = await testDiscountsSave(page, snap);
      pass("discounts-save-new-version", disc);
    } catch (err) {
      fail("discounts-save-new-version", err);
      await snap("billing-ux-e2e-07-discounts-error.png");
      throw err;
    }

    console.log("\n=== E2E summary ===");
    console.log(JSON.stringify(results, null, 2));
    console.log("Screenshots in", ARTIFACTS);
  } finally {
    await browser.close();
  }

  if (results.failed.length) process.exit(1);
}

main().catch((err) => {
  console.error("E2E failed:", err);
  process.exit(1);
});
