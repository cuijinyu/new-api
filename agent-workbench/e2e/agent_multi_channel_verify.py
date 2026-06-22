#!/usr/bin/env python3
"""Concurrent Agent Workbench bill-reference E2E verifier.

This script exercises the Agent page contract with real API calls:

* pick several channel bill documents from the bill library
* prepare each document as referenceable Agent files
* create one Agent session per channel and attach its bill files
* open all Agent SSE streams concurrently
* send a live follow-up message while streams are active
* verify streaming, concurrency, bill references, context injection, and profit analysis
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_CHANNELS = ("81", "82", "84")
PROFIT_TERMS = ("利润", "毛利", "profit", "margin")
COST_TERMS = ("成本", "cost")
REVENUE_TERMS = ("收入", "revenue")
AGENT_ERROR_STATUSES = {"error", "failed", "failure", "cancelled", "canceled"}


class E2EError(RuntimeError):
    pass


@dataclass
class Settings:
    api_url: str
    api_token: str | None
    channels: tuple[str, ...]
    agent_count: int
    month: str | None
    stream_timeout_seconds: int
    request_timeout_seconds: int
    followup_delay_seconds: float


@dataclass
class SelectedBill:
    document: dict[str, Any]
    expected_total_usd: float
    reference_files: list[dict[str, Any]] = field(default_factory=list)
    session: dict[str, Any] | None = None
    reference_event: dict[str, Any] | None = None
    message_ack: dict[str, Any] | None = None

    @property
    def document_id(self) -> str:
        return str(self.document["id"])

    @property
    def channel_id(self) -> str:
        return str(self.document.get("target_id") or self.document.get("channel_id") or "")

    @property
    def session_id(self) -> str:
        if not self.session:
            return ""
        return str(self.session.get("session_id") or self.session.get("id") or "")


@dataclass
class StreamRun:
    bill: SelectedBill
    request_start_at: float | None = None
    first_event_at: float | None = None
    end_at: float | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def event_types(self) -> list[str]:
        return [str(event.get("event_type") or "") for event in self.events]

    @property
    def terminal_type(self) -> str | None:
        for event in reversed(self.events):
            event_type = str(event.get("event_type") or "")
            if event_type in {"run.completed", "run.error"}:
                return event_type
        return None


def settings_from_args() -> Settings:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("WORKBENCH_API_URL", "http://127.0.0.1:18088"))
    parser.add_argument("--api-token", default=os.environ.get("WORKBENCH_API_TOKEN") or None)
    parser.add_argument("--channels", default=os.environ.get("WORKBENCH_E2E_CHANNELS", ",".join(DEFAULT_CHANNELS)))
    parser.add_argument("--agents", type=int, default=int(os.environ.get("WORKBENCH_E2E_AGENT_COUNT", "3")))
    parser.add_argument("--month", default=os.environ.get("WORKBENCH_E2E_MONTH") or None)
    parser.add_argument("--stream-timeout", type=int, default=int(os.environ.get("WORKBENCH_E2E_STREAM_TIMEOUT", "420")))
    parser.add_argument("--request-timeout", type=int, default=int(os.environ.get("WORKBENCH_E2E_REQUEST_TIMEOUT", "60")))
    parser.add_argument("--followup-delay", type=float, default=float(os.environ.get("WORKBENCH_E2E_FOLLOWUP_DELAY", "2.0")))
    args = parser.parse_args()
    channels = tuple(item.strip() for item in args.channels.split(",") if item.strip())
    return Settings(
        api_url=args.api_url.rstrip("/"),
        api_token=args.api_token,
        channels=channels or DEFAULT_CHANNELS,
        agent_count=max(1, args.agents),
        month=args.month,
        stream_timeout_seconds=args.stream_timeout,
        request_timeout_seconds=args.request_timeout,
        followup_delay_seconds=args.followup_delay,
    )


class WorkbenchClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def url(self, path: str) -> str:
        return f"{self.settings.api_url}/{path.lstrip('/')}"

    def request(self, method: str, path: str, payload: Any | None = None, *, accept: str = "application/json") -> Any:
        body = None
        headers = {"Accept": accept}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.settings.api_token:
            headers["Authorization"] = f"Bearer {self.settings.api_token}"
        req = Request(self.url(path), data=body, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.settings.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise E2EError(f"{method} {req.full_url} failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise E2EError(f"{method} {req.full_url} failed: {exc.reason}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise E2EError(f"{method} {req.full_url} returned non-JSON: {raw[:1000]}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: Any) -> Any:
        return self.request("POST", path, payload)

    def stream_events(self, path: str) -> list[dict[str, Any]]:
        headers = {"Accept": "text/event-stream"}
        if self.settings.api_token:
            headers["Authorization"] = f"Bearer {self.settings.api_token}"
        req = Request(self.url(path), headers=headers, method="GET")
        events: list[dict[str, Any]] = []
        current_event: str | None = None
        data_lines: list[str] = []

        def flush() -> None:
            nonlocal current_event, data_lines
            if not data_lines:
                current_event = None
                return
            raw_data = "\n".join(data_lines)
            try:
                event = json.loads(raw_data)
            except json.JSONDecodeError:
                event = {"event_type": current_event or "message", "content": raw_data, "payload": {}}
            if current_event and not event.get("event_type"):
                event["event_type"] = current_event
            events.append(event)
            current_event = None
            data_lines = []

        try:
            with urlopen(req, timeout=self.settings.stream_timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if line == "":
                        flush()
                    elif line.startswith("event:"):
                        current_event = line[len("event:") :].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[len("data:") :].strip())
                flush()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise E2EError(f"GET {req.full_url} stream failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise E2EError(f"GET {req.full_url} stream failed: {exc.reason}") from exc
        return events


def kpi_total_usd(document: dict[str, Any]) -> float:
    summary = document.get("summary") if isinstance(document.get("summary"), dict) else {}
    for key in ("total_usd", "cost_usd", "revenue_usd"):
        value = summary.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    kpis = document.get("kpis") if isinstance(document.get("kpis"), dict) else {}
    try:
        return float(kpis.get("total_usd") or 0)
    except (TypeError, ValueError):
        return 0.0


def select_bill_documents(client: WorkbenchClient, settings: Settings) -> list[SelectedBill]:
    query = {"bill_type": "channel_cost_bill"}
    if settings.month:
        query["month"] = settings.month
    payload = client.get(f"/api/bill-documents?{urlencode(query)}")
    documents = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(documents, list):
        raise E2EError("/api/bill-documents did not return an items list")

    candidates: list[dict[str, Any]] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        if str(document.get("bill_type") or "") != "channel_cost_bill":
            continue
        if str(document.get("target_type") or "") != "channel":
            continue
        if not str(document.get("target_id") or "").strip():
            continue
        if kpi_total_usd(document) <= 0:
            continue
        candidates.append(document)

    by_channel: dict[str, dict[str, Any]] = {}
    for document in candidates:
        channel_id = str(document.get("target_id") or "")
        current = by_channel.get(channel_id)
        if current is None or str(document.get("created_at") or "") > str(current.get("created_at") or ""):
            by_channel[channel_id] = document

    selected_docs: list[dict[str, Any]] = []
    for channel_id in settings.channels:
        document = by_channel.get(channel_id)
        if document:
            selected_docs.append(document)
        if len(selected_docs) >= settings.agent_count:
            break
    if len(selected_docs) < settings.agent_count:
        used = {str(document.get("target_id") or "") for document in selected_docs}
        for document in sorted(candidates, key=lambda item: str(item.get("created_at") or ""), reverse=True):
            channel_id = str(document.get("target_id") or "")
            if channel_id in used:
                continue
            used.add(channel_id)
            selected_docs.append(document)
            if len(selected_docs) >= settings.agent_count:
                break

    if len(selected_docs) < settings.agent_count:
        available = sorted({str(document.get("target_id") or "") for document in candidates})
        raise E2EError(f"need {settings.agent_count} channel bill documents, found {len(selected_docs)}; available channels={available}")

    return [SelectedBill(document=document, expected_total_usd=kpi_total_usd(document)) for document in selected_docs[: settings.agent_count]]


def prepare_references(client: WorkbenchClient, bill: SelectedBill) -> None:
    payload = client.post(
        f"/api/bill-documents/{bill.document_id}/reference-files",
        {
            "referenced_by": "e2e",
            "metadata": {
                "source": "agent_multi_channel_verify",
                "channel_id": bill.channel_id,
            },
        },
    )
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not files:
        raise E2EError(f"bill document {bill.document_id} returned no reference files")
    wrong_channel_files = []
    for file in files:
        filename = str(file.get("filename") or "")
        match = re.search(r"_ch(\d+)(?:_|\.|$)", filename)
        if match and match.group(1) != bill.channel_id:
            wrong_channel_files.append(filename)
    if wrong_channel_files:
        raise E2EError(
            f"bill document {bill.document_id} for channel {bill.channel_id} exposed other channel files: {wrong_channel_files}"
        )
    bill.reference_files = files


def create_session(client: WorkbenchClient, bill: SelectedBill) -> None:
    summary = bill.document.get("summary") if isinstance(bill.document.get("summary"), dict) else {}
    month = str(bill.document.get("month") or summary.get("month") or "")
    prompt = (
        f"请校验渠道 {bill.channel_id} 在 {month} 的渠道成本账单，并分析利润情况。"
        f"请明确列出内部成本金额 {bill.expected_total_usd:.4f} USD、收入侧资料是否充足、"
        "利润和毛利率能否计算；如果缺收入资料，请说明缺口和下一步需要引用哪类账单。"
        "输出要简短，包含：成本、收入、利润判断、下一步。"
    )
    payload = client.post(
        "/api/agent/sessions",
        {
            "provider": "claude_code",
            "runtime": "codingplan",
            "prompt": prompt,
            "live": False,
            "metadata": {
                "e2e": True,
                "e2e_case": "multi-channel-profit",
                "title": f"E2E 渠道 {bill.channel_id} 利润校验",
                "channel_id": bill.channel_id,
                "month": month,
                "bill_type": "channel_cost_bill",
                "target_type": "channel",
                "target_id": bill.channel_id,
                "bill_document_id": bill.document_id,
                "expected_cost_usd": bill.expected_total_usd,
            },
        },
    )
    session_id = str(payload.get("session_id") or payload.get("id") or "")
    if not session_id:
        raise E2EError(f"session create response for channel {bill.channel_id} did not include session id: {payload}")
    bill.session = payload


def attach_references(client: WorkbenchClient, bill: SelectedBill) -> None:
    file_ids = [str(file.get("id") or "") for file in bill.reference_files if file.get("id")]
    if not file_ids:
        raise E2EError(f"bill document {bill.document_id} has no reference file ids")
    payload = client.post(
        f"/api/agent/sessions/{bill.session_id}/files/reference",
        {
            "file_ids": file_ids,
            "referenced_by": "e2e",
            "metadata": {
                "source": "agent_multi_channel_verify",
                "bill_document_id": bill.document_id,
                "channel_id": bill.channel_id,
            },
        },
    )
    bill.reference_event = payload.get("event") if isinstance(payload, dict) else None
    if not isinstance(bill.reference_event, dict):
        raise E2EError(f"session {bill.session_id} did not return file.reference event")


def run_streams_concurrently(client: WorkbenchClient, bills: list[SelectedBill], settings: Settings) -> list[StreamRun]:
    runs = [StreamRun(bill=bill) for bill in bills]
    barrier = threading.Barrier(len(runs) + 1)

    def worker(run: StreamRun) -> None:
        try:
            barrier.wait(timeout=30)
            run.request_start_at = time.monotonic()
            events = client.stream_events(f"/api/agent/sessions/{run.bill.session_id}/stream?live=false")
            run.events = events
            if events:
                run.first_event_at = run.request_start_at
        except Exception as exc:  # noqa: BLE001 - captured for aggregate E2E diagnostics.
            run.error = str(exc)
        finally:
            run.end_at = time.monotonic()

    threads = [threading.Thread(target=worker, args=(run,), name=f"stream-{run.bill.channel_id}", daemon=True) for run in runs]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=30)
    time.sleep(settings.followup_delay_seconds)
    for bill in bills:
        try:
            bill.message_ack = client.post(
                f"/api/agent/sessions/{bill.session_id}/messages",
                {
                    "role": "user",
                    "content": f"运行中补充：请在利润分析里明确渠道 {bill.channel_id} 的成本、收入缺口和毛利率判断。",
                    "metadata": {"source": "agent_multi_channel_verify", "live_followup": True},
                },
            )
        except Exception as exc:  # noqa: BLE001
            bill.message_ack = {"error": str(exc)}
    for thread in threads:
        thread.join(timeout=settings.stream_timeout_seconds + 30)
    for run, thread in zip(runs, threads):
        if thread.is_alive():
            run.error = run.error or "stream thread did not finish before timeout"
            run.end_at = time.monotonic()
    return runs


def text_blob(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def result_payloads_from(*values: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            result = value.get("result")
            if isinstance(result, dict):
                payloads.append(result)
            metadata = value.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("result"), dict):
                payloads.append(metadata["result"])
            payload = value.get("payload")
            if isinstance(payload, dict):
                walk(payload)
            for key in ("session", "events"):
                if key in value:
                    walk(value[key])
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for value in values:
        walk(value)
    return payloads


def assistant_analysis_blob(history: dict[str, Any], session: dict[str, Any], run: StreamRun) -> str:
    parts: list[Any] = []
    for event in [*run.events, *(history.get("events") or [])]:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or "")
        role = str(event.get("role") or "")
        if role == "assistant" or event_type in {"assistant.delta", "run.completed"}:
            parts.append({"content": event.get("content"), "payload": event.get("payload")})
    parts.extend(result_payloads_from(history, session, run.events))
    return text_blob(parts)


def assert_history(client: WorkbenchClient, bill: SelectedBill, run: StreamRun) -> dict[str, Any]:
    history = client.get(f"/api/agent/sessions/{bill.session_id}/history")
    events = history.get("events") if isinstance(history, dict) else []
    files = history.get("files") if isinstance(history, dict) else []
    event_types = [str(event.get("event_type") or "") for event in events if isinstance(event, dict)]
    if "file.reference" not in event_types:
        raise E2EError(f"session {bill.session_id} has no file.reference event in history")
    expected_file_ids = {str(file.get("id") or "") for file in bill.reference_files}
    history_file_ids = {str(file.get("id") or "") for file in files if isinstance(file, dict)}
    missing_file_ids = sorted(expected_file_ids - history_file_ids)
    if missing_file_ids:
        raise E2EError(f"session {bill.session_id} history is missing referenced file ids: {missing_file_ids}")

    session_payload = client.get(f"/api/agent/sessions/{bill.session_id}")
    session = session_payload.get("session") if isinstance(session_payload, dict) else {}
    sandbox_id = session.get("sandbox_id") if isinstance(session, dict) else None
    if sandbox_id and "context.injected" not in event_types:
        raise E2EError(f"session {bill.session_id} has sandbox {sandbox_id} but no context.injected event")

    ack_event = (bill.message_ack or {}).get("ack_event") if isinstance(bill.message_ack, dict) else None
    if not isinstance(ack_event, dict):
        raise E2EError(f"session {bill.session_id} live follow-up did not return ack_event: {bill.message_ack}")
    ack_payload = ack_event.get("payload") if isinstance(ack_event.get("payload"), dict) else {}
    if not ack_payload.get("live_input"):
        raise E2EError(f"session {bill.session_id} ack_event did not mark live_input=true: {ack_event}")

    for result in result_payloads_from(history, session, run.events):
        status = str(result.get("status") or "").strip().lower()
        if status in AGENT_ERROR_STATUSES:
            summary = str(result.get("summary") or result.get("reason") or "")[:500]
            raise E2EError(f"session {bill.session_id} agent result status is {status}: {summary}")

    analysis_blob = assistant_analysis_blob(history, session if isinstance(session, dict) else {}, run)
    analysis_lower = analysis_blob.lower()
    if not any(term.lower() in analysis_lower for term in PROFIT_TERMS):
        raise E2EError(f"session {bill.session_id} output did not mention profit/margin")
    if not any(term.lower() in analysis_lower for term in COST_TERMS):
        raise E2EError(f"session {bill.session_id} output did not mention cost")
    if not any(term.lower() in analysis_lower for term in REVENUE_TERMS):
        raise E2EError(f"session {bill.session_id} output did not mention revenue")
    return {"history": history, "session": session}


def assert_streams(runs: list[StreamRun]) -> None:
    for run in runs:
        if run.error:
            raise E2EError(f"session {run.bill.session_id} stream failed: {run.error}")
        if not run.events:
            raise E2EError(f"session {run.bill.session_id} stream returned no events")
        if "run.started" not in run.event_types:
            raise E2EError(f"session {run.bill.session_id} stream did not include run.started; got {run.event_types}")
        if run.terminal_type != "run.completed":
            raise E2EError(f"session {run.bill.session_id} terminal event is {run.terminal_type}; got {run.event_types}")

    starts = [run.request_start_at for run in runs if run.request_start_at is not None]
    first_events = [run.first_event_at for run in runs if run.first_event_at is not None]
    ends = [run.end_at for run in runs if run.end_at is not None]
    if len(starts) != len(runs) or max(starts) - min(starts) > 3:
        raise E2EError("stream requests were not started concurrently enough")
    if len(first_events) != len(runs) or max(first_events) - min(first_events) > 10:
        raise E2EError("stream first events were not received concurrently enough")
    if len(ends) == len(runs) and not (max(first_events) < min(ends)):
        raise E2EError("streams did not overlap in time")


def print_summary(bills: list[SelectedBill], runs: list[StreamRun], checked: list[dict[str, Any]]) -> None:
    print("\n=== Agent Workbench multi-channel E2E summary ===")
    for bill, run, details in zip(bills, runs, checked):
        session = details["session"]
        event_counts: dict[str, int] = {}
        for event_type in run.event_types:
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        duration = (run.end_at or 0) - (run.request_start_at or run.end_at or 0)
        injected = [
            event
            for event in details["history"].get("events", [])
            if isinstance(event, dict) and event.get("event_type") == "context.injected"
        ]
        injected_files = []
        if injected:
            payload = injected[-1].get("payload") if isinstance(injected[-1].get("payload"), dict) else {}
            injected_files = [item.get("filename") for item in payload.get("files", []) if isinstance(item, dict)]
        print(
            json.dumps(
                {
                    "channel": bill.channel_id,
                    "document_id": bill.document_id,
                    "expected_total_usd": bill.expected_total_usd,
                    "session_id": bill.session_id,
                    "sandbox_id": session.get("sandbox_id") if isinstance(session, dict) else None,
                    "reference_files": [file.get("filename") for file in bill.reference_files],
                    "injected_files": injected_files,
                    "stream_terminal": run.terminal_type,
                    "stream_duration_seconds": round(duration, 2),
                    "event_counts": event_counts,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )


def main() -> int:
    settings = settings_from_args()
    client = WorkbenchClient(settings)
    try:
        health = client.get("/health")
        if not isinstance(health, dict) or not health.get("ok"):
            raise E2EError(f"API health check failed: {health}")
        bills = select_bill_documents(client, settings)
        for bill in bills:
            prepare_references(client, bill)
            create_session(client, bill)
            attach_references(client, bill)
        runs = run_streams_concurrently(client, bills, settings)
        assert_streams(runs)
        checked = [assert_history(client, bill, run) for bill, run in zip(bills, runs)]
        print_summary(bills, runs, checked)
    except E2EError as exc:
        print(f"E2E FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
