"""Unit tests for app.runner.sandbox_client — HTTP calls are mocked."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from app.runner.sandbox_client import SandboxClient, SandboxError


def make_response(payload=None, *, status_code=200, content: bytes | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.headers = {"content-type": "application/json"}
    if content is not None:
        response.content = content
        response.text = content.decode("utf-8", errors="replace")
    else:
        body = b"" if payload is None else json.dumps(payload).encode()
        response.content = body
        response.text = body.decode("utf-8", errors="replace")
        response.json.return_value = payload or {}
    return response


def endpoint_response():
    return make_response({"endpoint": "execd.local:44772", "headers": {"x-sandbox": "test"}})


@pytest.fixture
def mock_requests():
    with patch("app.runner.sandbox_client._requests") as m:
        mock_mod = MagicMock()
        m.return_value = mock_mod
        mock_mod.RequestException = Exception
        yield mock_mod


@pytest.fixture
def client(mock_requests):
    with patch("app.runner.config.sandbox_url", return_value="http://sandbox:8080"):
        with patch("app.runner.config.sandbox_api_key", return_value="test-key"):
            return SandboxClient()


class TestSandboxClientInit:
    def test_raises_without_url(self):
        with patch("app.runner.config.sandbox_url", return_value=""):
            with patch("app.runner.config.sandbox_api_key", return_value=""):
                with pytest.raises(SandboxError, match="not configured"):
                    SandboxClient()

    def test_sets_base_url(self, client):
        assert client.base_url == "http://sandbox:8080"
        assert client.api_key == "test-key"


class TestCreateSandbox:
    def test_calls_post(self, client, mock_requests):
        mock_requests.request.side_effect = [
            make_response({"id": "sb-123"}),
            make_response({"id": "sb-123", "status": {"state": "running"}}),
        ]

        result = client.create_sandbox(image="python:3.12")
        call_args = mock_requests.request.call_args_list[0]
        assert call_args[0][0] == "POST"
        assert call_args[0][1].endswith("/sandboxes")
        body = json.loads(call_args[1]["data"])
        assert body["image"]["uri"] == "python:3.12"
        assert result == {"id": "sb-123"}


class TestGetSandbox:
    def test_calls_get(self, client, mock_requests):
        mock_requests.request.return_value = make_response({"id": "sb-123", "status": "running"})

        result = client.get_sandbox("sb-123")
        call_args = mock_requests.request.call_args
        assert call_args[0][0] == "GET"
        assert "sb-123" in call_args[0][1]
        assert result["status"] == "running"


class TestDeleteSandbox:
    def test_calls_delete(self, client, mock_requests):
        mock_requests.request.return_value = make_response(None, status_code=204)

        result = client.delete_sandbox("sb-456")
        call_args = mock_requests.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "sb-456" in call_args[0][1]
        assert result == {}


class TestExecCommand:
    def test_calls_exec(self, client, mock_requests):
        mock_requests.request.return_value = endpoint_response()
        stream_response = MagicMock()
        stream_response.status_code = 200
        stream_response.iter_lines.return_value = [
            'event: stdout',
            'data: {"text":"ok"}',
            '',
            'event: execution_complete',
            'data: {"exit_code":0}',
            '',
        ]
        stream_response.__enter__.return_value = stream_response
        stream_response.__exit__.return_value = None
        mock_requests.post.return_value = stream_response

        result = client.exec_command("sb-1", ["python", "-c", "print('hi')"], cwd="/workspace")
        call_args = mock_requests.post.call_args
        body = json.loads(call_args[1]["data"])
        assert body["command"] == "python -c 'print('\"'\"'hi'\"'\"')'"
        assert body["cwd"] == "/workspace"
        assert result["returncode"] == 0
        assert result["stdout"] == "ok"


class TestWriteFile:
    def test_encodes_base64(self, client, mock_requests):
        mock_requests.request.return_value = endpoint_response()
        mock_requests.post.return_value = make_response({"ok": True})

        client.write_file("sb-1", "/workspace/input/file.txt", b"hello world")
        call_args = mock_requests.post.call_args
        files = call_args[1]["files"]
        metadata = json.loads(files[0][1][1])
        assert metadata["path"] == "/workspace/input/file.txt"
        assert files[1][1][1] == b"hello world"


class TestReadFile:
    def test_decodes_response(self, client, mock_requests):
        mock_requests.request.return_value = endpoint_response()
        mock_requests.get.return_value = make_response(content=b"file content")

        result = client.read_file("sb-1", "/workspace/output/result.json")
        assert result == b"file content"

    def test_returns_empty_content(self, client, mock_requests):
        mock_requests.request.return_value = endpoint_response()
        mock_requests.get.return_value = make_response(content=b"")

        assert client.read_file("sb-1", "/bad/path") == b""


class TestListFiles:
    def test_parses_entries(self, client, mock_requests):
        mock_requests.request.side_effect = [
            endpoint_response(),
            make_response({"files": [{"path": "/a"}, {"path": "/b"}]}),
        ]

        result = client.list_files("sb-1", "/workspace/output")
        assert result == ["/a", "/b"]


class TestHttpErrors:
    def test_4xx_raises(self, client, mock_requests):
        response = MagicMock()
        response.status_code = 404
        response.text = "Not Found"
        mock_requests.request.return_value = response

        with pytest.raises(SandboxError, match="HTTP 404"):
            client.get_sandbox("no-such")

    def test_network_error(self, client, mock_requests):
        mock_requests.request.side_effect = Exception("connection refused")

        with pytest.raises(SandboxError, match="failed"):
            client.get_sandbox("sb-1")
