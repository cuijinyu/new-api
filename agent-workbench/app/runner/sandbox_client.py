"""OpenSandbox Lifecycle + Execd 客户端封装。

只在 RUNNER_MODE=sandbox 时使用。封装：
- Lifecycle：create / get / pause / resume / delete 沙箱
- Execd：在沙箱内执行命令、读写文件

凭证经环境变量在 exec 时注入，绝不写入持久层。
"""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

from . import config


class SandboxError(RuntimeError):
    pass


def _requests():
    # requests 仅在真正使用沙箱时才需要，做惰性导入避免无沙箱环境的导入开销/失败。
    try:
        import requests  # noqa: PLC0415

        return requests
    except ImportError as exc:  # pragma: no cover
        raise SandboxError("the 'requests' package is required for sandbox mode") from exc


class SandboxClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: int = 60) -> None:
        self.base_url = (base_url or config.sandbox_url()).rstrip("/")
        self.api_key = api_key or config.sandbox_api_key()
        self.timeout = timeout
        if not self.base_url:
            raise SandboxError("OPEN_SANDBOX_URL is not configured")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
            headers["OPEN-SANDBOX-API-KEY"] = self.api_key
        return headers

    def _request(self, method: str, path: str, payload: Any | None = None) -> Any:
        requests = _requests()
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                data=json.dumps(payload) if payload is not None else None,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SandboxError(f"{method} {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise SandboxError(f"{method} {url} -> HTTP {response.status_code}: {response.text[:500]}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _execd_endpoint(self, sandbox_id: str) -> tuple[str, dict[str, str]]:
        result = self._request("GET", f"/sandboxes/{sandbox_id}/endpoints/44772?use_server_proxy=false")
        endpoint = str((result or {}).get("endpoint") or "").strip()
        if not endpoint:
            raise SandboxError(f"execd endpoint is missing for sandbox {sandbox_id}: {result}")
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"
        endpoint = self._apply_execd_host_override(endpoint)
        headers = result.get("headers") if isinstance(result, dict) else None
        return endpoint.rstrip("/"), {str(k): str(v) for k, v in (headers or {}).items()}

    def _apply_execd_host_override(self, endpoint: str) -> str:
        override = (os.getenv("OPEN_SANDBOX_EXECD_HOST_OVERRIDE") or "").strip()
        if not override:
            return endpoint
        parts = urlsplit(endpoint)
        netloc = override
        if parts.port:
            netloc = f"{override}:{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def _execd_request(self, sandbox_id: str, method: str, path: str, *, payload: Any | None = None, **kwargs) -> Any:
        requests = _requests()
        base_url, endpoint_headers = self._execd_endpoint(sandbox_id)
        headers = {"Content-Type": "application/json", **endpoint_headers}
        url = f"{base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                data=json.dumps(payload) if payload is not None else None,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise SandboxError(f"{method} {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise SandboxError(f"{method} {url} -> HTTP {response.status_code}: {response.text[:500]}")
        if not response.content:
            return {}
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return {"raw": response.text}

    def _wait_until_running(self, sandbox_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + min(config.sandbox_timeout_seconds(), 120)
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            latest = self.get_sandbox(sandbox_id)
            status = latest.get("status") if isinstance(latest.get("status"), dict) else {}
            state = str(status.get("state") or "").lower()
            if state == "running":
                return latest
            if state in {"failed", "terminated", "stopped"}:
                raise SandboxError(f"sandbox {sandbox_id} entered {state}: {status}")
            time.sleep(0.5)
        raise SandboxError(f"sandbox {sandbox_id} did not become running: {latest}")

    # --- Lifecycle ---------------------------------------------------------
    def create_sandbox(self, *, image: str | None = None, env: dict[str, str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "image": {"uri": image or config.sandbox_image()},
            "env": env or {},
            "metadata": {str(k): str(v) for k, v in (metadata or {}).items()},
            "resourceLimits": {"cpu": "1", "memory": "2Gi"},
            "entrypoint": ["tail", "-f", "/dev/null"],
            "timeout": config.sandbox_timeout_seconds(),
        }
        created = None
        last_error: SandboxError | None = None
        for _ in range(5):
            try:
                created = self._request("POST", "/sandboxes", payload)
                break
            except SandboxError as exc:
                message = str(exc)
                if "Ports are not available" not in message and "SANDBOX_START_FAILED" not in message:
                    raise
                last_error = exc
                time.sleep(0.3)
        if created is None:
            raise last_error or SandboxError("create_sandbox failed")
        sandbox_id = str(created.get("id") or created.get("sandbox_id") or "")
        if sandbox_id:
            self._wait_until_running(sandbox_id)
        return created

    def get_sandbox(self, sandbox_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sandboxes/{sandbox_id}")

    def pause_sandbox(self, sandbox_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sandboxes/{sandbox_id}/pause")

    def resume_sandbox(self, sandbox_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sandboxes/{sandbox_id}/resume")

    def delete_sandbox(self, sandbox_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/sandboxes/{sandbox_id}")

    # --- Execd -------------------------------------------------------------
    def exec_command(
        self,
        sandbox_id: str,
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        stdout_callback: Callable[[str], None] | None = None,
        stderr_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        import shlex

        command = " ".join(shlex.quote(part) for part in argv)
        payload = {
            "command": command,
            "cwd": cwd,
            "envs": env or {},
            "background": False,
            "timeout": (timeout or config.agent_exec_timeout_seconds()) * 1000,
        }
        requests = _requests()
        base_url, endpoint_headers = self._execd_endpoint(sandbox_id)
        url = f"{base_url}/command"
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        returncode = 0
        try:
            with requests.post(
                url,
                headers={"Content-Type": "application/json", **endpoint_headers},
                data=json.dumps(payload),
                timeout=(timeout or config.agent_exec_timeout_seconds()) + 30,
                stream=True,
            ) as response:
                if response.status_code >= 400:
                    raise SandboxError(f"POST {url} -> HTTP {response.status_code}: {response.text[:500]}")
                event_name = ""
                data_lines: list[str] = []
                for raw in response.iter_lines(decode_unicode=True):
                    line = raw or ""
                    if not line:
                        if data_lines:
                            event = self._parse_sse_event(event_name, data_lines)
                            event_type = str(event.get("type") or event_name)
                            text = str(event.get("text") or "")
                            if event_type == "stdout":
                                stdout_chunks.append(text)
                                if stdout_callback:
                                    stdout_callback(text)
                            elif event_type == "stderr":
                                stderr_chunks.append(text)
                                if stderr_callback:
                                    stderr_callback(text)
                            elif event_type == "error":
                                stderr_chunks.append(text or json.dumps(event, ensure_ascii=False))
                                returncode = 1
                            elif event_type == "execution_complete":
                                code = event.get("exit_code") or (event.get("results") or {}).get("exit_code")
                                if code is not None:
                                    try:
                                        returncode = int(code)
                                    except (TypeError, ValueError):
                                        returncode = returncode or 0
                            event_name = ""
                            data_lines = []
                        continue
                    if line.startswith("event:"):
                        event_name = line.removeprefix("event:").strip()
                    elif line.startswith("data:"):
                        data_lines.append(line.removeprefix("data:").strip())
        except requests.RequestException as exc:
            raise SandboxError(f"POST {url} failed: {exc}") from exc
        return {"returncode": returncode, "stdout": "".join(stdout_chunks), "stderr": "".join(stderr_chunks)}

    def _parse_sse_event(self, event_name: str, data_lines: list[str]) -> dict[str, Any]:
        data = "\n".join(data_lines).strip()
        if not data:
            return {"type": event_name}
        try:
            parsed = json.loads(data)
        except ValueError:
            return {"type": event_name, "text": data}
        if isinstance(parsed, dict):
            parsed.setdefault("type", event_name)
            return parsed
        return {"type": event_name, "text": str(parsed)}

    def write_file(self, sandbox_id: str, path: str, data: bytes) -> dict[str, Any]:
        requests = _requests()
        base_url, endpoint_headers = self._execd_endpoint(sandbox_id)
        url = f"{base_url}/files/upload"
        files = [
            ("metadata", ("metadata", json.dumps({"path": path, "mode": 755}), "application/json")),
            ("file", (path.rsplit("/", 1)[-1] or "file", data, "application/octet-stream")),
        ]
        try:
            response = requests.post(url, headers=endpoint_headers, files=files, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SandboxError(f"POST {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise SandboxError(f"POST {url} -> HTTP {response.status_code}: {response.text[:500]}")
        return {"status": "uploaded", "path": path}

    def read_file(self, sandbox_id: str, path: str) -> bytes:
        requests = _requests()
        base_url, endpoint_headers = self._execd_endpoint(sandbox_id)
        url = f"{base_url}/files/download?{urlencode({'path': path})}"
        try:
            response = requests.get(url, headers=endpoint_headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SandboxError(f"GET {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise SandboxError(f"GET {url} -> HTTP {response.status_code}: {response.text[:500]}")
        return response.content

    def list_files(self, sandbox_id: str, path: str) -> list[str]:
        result = self._execd_request(sandbox_id, "GET", f"/directories/list?{urlencode({'path': path, 'depth': 8})}")
        if isinstance(result, dict):
            entries = result.get("files") or result.get("entries") or result.get("items") or []
        else:
            entries = result
        if isinstance(entries, list):
            return [str(item.get("path") if isinstance(item, dict) else item) for item in entries if str(item.get("type") if isinstance(item, dict) else "file") != "directory"]
        return []
