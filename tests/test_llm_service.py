"""Tests for src/llm_service.py and /api/llm/* routes (OpenAI, custom Local, Anthropic, env defaults, errors)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import llm_service  # noqa: E402
import server  # noqa: E402


@pytest.fixture()
def isolated_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(llm_service, "CONFIG_PATH", tmp_path / "llm_config.json")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    return TestClient(server.app), tmp_path


def _install_mock_transport(monkeypatch, handler):
    real_async_client = httpx.AsyncClient
    captured: list[dict] = []

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(llm_service.httpx, "AsyncClient", factory)
    return captured


def test_env_defaults_not_persisted_and_key_masked(isolated_llm, monkeypatch):
    client, tmp_path = isolated_llm
    monkeypatch.setenv("OPENAI_BASE_URL", "http://192.0.2.10:3425/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-9876")

    resp = client.get("/api/llm/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["local_url"] == "http://192.0.2.10:3425/v1"
    assert cfg["env_base_url"] == "http://192.0.2.10:3425/v1"
    assert cfg["api_key"] == ""
    assert cfg["api_key_set"] is True
    assert cfg["api_key_source"] == "env"

    on_disk = json.loads((tmp_path / "llm_config.json").read_text(encoding="utf-8"))
    assert on_disk["api_key"] == ""
    assert "9876" not in json.dumps(on_disk)


def test_update_config_preserves_saved_key_when_blank_or_masked(isolated_llm):
    client, tmp_path = isolated_llm
    r1 = client.post("/api/llm/config", json={
        "provider": "openai",
        "api_key": "sk-saved-1234",
        "model": "gpt-4o",
        "local_url": "http://localhost:11434/v1",
        "system_prompt": "Custom prompt",
    })
    assert r1.status_code == 200
    assert r1.json()["api_key"] == "*********1234"
    assert r1.json()["api_key_source"] == "config"

    r2 = client.post("/api/llm/config", json={
        "provider": "openai",
        "api_key": "",
        "model": "Flash41",
        "base_url": "http://192.0.2.20:3425/v1",
    })
    assert r2.status_code == 200
    assert r2.json()["api_key"] == "*********1234"
    assert r2.json()["model"] == "Flash41"
    assert r2.json()["base_url"] == "http://192.0.2.20:3425/v1"

    on_disk = json.loads((tmp_path / "llm_config.json").read_text(encoding="utf-8"))
    assert on_disk["api_key"] == "sk-saved-1234"


def test_chat_openai_local_streaming_and_user_input_preserved(isolated_llm, monkeypatch):
    client, _ = isolated_llm
    seen_requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen_requests.append({
            "url": str(request.url),
            "auth": request.headers.get("authorization", ""),
            "body": body,
        })
        sse = (
            'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":" from Flash41"}}]}\n\n'
            'data: [DONE]\n\n'
        )
        return httpx.Response(200, content=sse.encode("utf-8"), headers={"content-type": "text/event-stream"})

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key-4321")

    client.post("/api/llm/config", json={
        "provider": "local",
        "model": "Flash41",
        "local_url": "http://192.0.2.50:3425/v1/",
    })

    user_text = "  Keep   exact spacing & symbols: IL=21?  "
    resp = client.post("/api/llm/chat", json={"messages": [{"role": "user", "content": user_text}]})
    assert resp.status_code == 200
    assert 'data: {"token": "OK"}' in resp.text
    assert 'data: {"token": " from Flash41"}' in resp.text
    assert "data: [DONE]" in resp.text

    assert len(seen_requests) == 1
    assert seen_requests[0]["url"] == "http://192.0.2.50:3425/v1/chat/completions"
    assert seen_requests[0]["auth"] == "Bearer sk-env-key-4321"
    sent_msgs = seen_requests[0]["body"]["messages"]
    assert sent_msgs[0]["role"] == "system"
    assert sent_msgs[1] == {"role": "user", "content": user_text}


def test_chat_openai_provider_uses_env_base_url_and_api_key(isolated_llm, monkeypatch):
    client, _ = isolated_llm
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"connected"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )

    _install_mock_transport(monkeypatch, handler)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://192.0.2.99:3425/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-env-9999")

    client.post("/api/llm/config", json={"provider": "openai", "model": "Flash41"})
    resp = client.post("/api/llm/test", json={})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "reply": "connected"}
    assert seen_urls == ["http://192.0.2.99:3425/v1/chat/completions"]


def test_test_connection_uses_draft_without_saving(isolated_llm, monkeypatch):
    client, _ = isolated_llm
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen.append((str(request.url), body["model"]))
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"connected"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        )

    _install_mock_transport(monkeypatch, handler)

    resp = client.post("/api/llm/test", json={
        "provider": "local",
        "model": "Flash41",
        "local_url": "http://192.0.2.1:3425/v1",
        "api_key": "sk-draft-secret",
    })
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "reply": "connected"}
    assert seen == [("http://192.0.2.1:3425/v1/chat/completions", "Flash41")]

    # Draft override must not overwrite saved config
    saved = client.get("/api/llm/config").json()
    assert saved["model"] == "qwen2.5:7b"
    assert saved["api_key"] == ""


def test_anthropic_chat_and_analyze_paths(isolated_llm, monkeypatch):
    client, _ = isolated_llm
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen.append({"url": str(request.url), "x_api_key": request.headers.get("x-api-key"), "body": body})
        sse = (
            'event: content_block_delta\n'
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Claude OK"}}\n\n'
            'event: message_stop\n'
            'data: {"type":"message_stop"}\n\n'
        )
        return httpx.Response(200, content=sse.encode("utf-8"), headers={"content-type": "text/event-stream"})

    _install_mock_transport(monkeypatch, handler)
    client.post("/api/llm/config", json={
        "provider": "anthropic",
        "api_key": "sk-ant-secret-5555",
        "model": "claude-sonnet-4-20250514",
    })

    r_chat = client.post("/api/llm/chat", json={"messages": [{"role": "user", "content": "Hi"}]})
    assert r_chat.status_code == 200
    assert 'data: {"token": "Claude OK"}' in r_chat.text
    assert seen[0]["x_api_key"] == "sk-ant-secret-5555"
    assert "system" in seen[0]["body"]

    r_an = client.post("/api/llm/analyze", json={"image_base64": "AAAA", "context": {"direction": "inline"}})
    assert r_an.status_code == 200
    assert 'data: {"token": "Claude OK"}' in r_an.text
    assert seen[1]["body"]["messages"][0]["content"][0]["type"] == "image"


@pytest.mark.parametrize(
    "status,body,expected_substr",
    [
        (401, '{"error":{"message":"invalid key sk-should-not-echo"}}', "Authentication failed (HTTP 401)"),
        (404, '{"error":{"message":"model not found"}}', "not found (HTTP 404)"),
        (429, '{"error":{"message":"too many requests"}}', "Rate limit or quota exceeded (HTTP 429)"),
        (502, "Bad Gateway", "Upstream LLM server error (HTTP 502)"),
    ],
)
def test_upstream_http_errors_surface_in_english(isolated_llm, monkeypatch, status, body, expected_substr):
    client, _ = isolated_llm

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode("utf-8"))

    _install_mock_transport(monkeypatch, handler)
    r_test = client.post("/api/llm/test", json={
        "provider": "local",
        "model": "Flash41",
        "local_url": "http://192.0.2.1:3425/v1",
        "api_key": "sk-top-secret-key",
    })
    assert r_test.status_code == 502
    detail = r_test.json()["detail"]
    assert expected_substr in detail
    assert "sk-top-secret-key" not in detail

    client.post("/api/llm/config", json={
        "provider": "local",
        "model": "Flash41",
        "local_url": "http://192.0.2.1:3425/v1",
        "api_key": "sk-top-secret-key",
    })
    r_chat = client.post("/api/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r_chat.status_code == 200
    assert expected_substr in r_chat.text
    assert "sk-top-secret-key" not in r_chat.text


def test_timeout_error_surfaces_in_english(isolated_llm, monkeypatch):
    client, _ = isolated_llm

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    _install_mock_transport(monkeypatch, handler)
    r_test = client.post("/api/llm/test", json={
        "provider": "local",
        "model": "Flash41",
        "local_url": "http://192.0.2.1:3425/v1",
    })
    assert r_test.status_code == 502
    assert "timed out" in r_test.json()["detail"].lower()


def test_missing_openai_key_returns_400_in_english(isolated_llm):
    client, _ = isolated_llm
    r = client.post("/api/llm/test", json={"provider": "openai", "model": "gpt-4o", "base_url": ""})
    assert r.status_code == 400
    assert "API key is not set" in r.json()["detail"]
