"""最小化安全防护：Bearer 鉴权、CORS 白名单、上传大小限制。

设计目标：
- 默认本地放行（不配置 token 即不鉴权），避免破坏本地 Docker E2E。
- 配置 WORKBENCH_API_TOKEN 后，除放行路径外都要求 Bearer token。
- CORS 白名单可通过 WORKBENCH_CORS_ORIGINS 收敛。

实现为纯 ASGI 中间件而非 BaseHTTPMiddleware，避免缓冲 SSE 流式响应。
"""

from __future__ import annotations

import json
import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send


# 永远放行：健康检查、文档、CORS 预检。
PUBLIC_PATHS = {"/health", "/api/status", "/docs", "/openapi.json", "/redoc"}


def cors_origins() -> list[str]:
    raw = os.getenv("WORKBENCH_CORS_ORIGINS", "*")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["*"]


def cors_allow_credentials() -> bool:
    # 通配 origin 时浏览器不允许携带凭证，自动关闭以符合规范。
    if "*" in cors_origins():
        return False
    return os.getenv("WORKBENCH_CORS_CREDENTIALS", "true").strip().lower() != "false"


def api_token() -> str:
    return (os.getenv("WORKBENCH_API_TOKEN", "") or "").strip()


def max_upload_bytes() -> int:
    raw = os.getenv("WORKBENCH_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024))
    try:
        value = int(raw)
    except ValueError:
        value = 50 * 1024 * 1024
    return max(1024, value)


def max_request_bytes() -> int:
    # 上传走 base64，约放大 4/3，再留冗余。
    return int(max_upload_bytes() * 1.5) + 1024 * 1024


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path.startswith("/docs") or path.startswith("/redoc")


async def _send_json_error(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AuthMiddleware:
    """配置 token 后校验 Bearer；未配置则放行（本地默认）。纯 ASGI，不缓冲流。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = api_token()
        method = scope.get("method", "GET")
        path = scope.get("path", "")
        if not token or method == "OPTIONS" or _is_public(path):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        header = headers.get("authorization", "")
        provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if provided != token:
            await _send_json_error(send, 401, "missing or invalid bearer token")
            return
        await self.app(scope, receive, send)


class RequestSizeLimitMiddleware:
    """基于 Content-Length 的粗粒度请求体大小限制。纯 ASGI。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_request_bytes():
                    await _send_json_error(send, 413, "request body too large")
                    return
            except ValueError:
                pass
        await self.app(scope, receive, send)
