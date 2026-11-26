"""
LLM service: provider abstraction layer (Anthropic / OpenAI / Local)
Config is persisted to data/llm_config.json and read/written through the API.
Uses httpx AsyncClient directly for SSE streaming so OpenAI, custom OpenAI-compatible
endpoints, and Anthropic work out of the box without requiring extra SDK packages.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator

import httpx

logger = logging.getLogger("sam3-server")

# ── Path constants ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "llm_config.json"

OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"

CHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
TEST_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)

# ── Default config ────────────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = (
    "You are SGSeg AI, an expert assistant for seismic interpretation and geological analysis. "
    "You are skilled at reading seismic sections, horizon tracking, fault identification, facies analysis, "
    "and suggesting interactive point prompts for the SAM3 segmentation model. "
    "Answer the user's technical questions in English, briefly and accurately."
)

DEFAULT_CONFIG = {
    "provider": "local",
    "api_key": "",
    "model": "qwen2.5:7b",
    "local_url": "http://localhost:11434/v1",
    "base_url": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
}

PROVIDER_DEFAULTS = {
    "anthropic": {"model": "claude-sonnet-4-20250514"},
    "openai": {"model": "gpt-4o", "base_url": OPENAI_DEFAULT_BASE_URL},
    "local": {"model": "qwen2.5:7b", "local_url": "http://localhost:11434/v1"},
}

VALID_PROVIDERS = ("anthropic", "openai", "local")


# ── Internal helpers ──────────────────────────────────────────

def _env_str(name: str) -> str:
    return os.environ.get(name, "").strip()


def _default_config() -> dict:
    env_url = _env_str("OPENAI_BASE_URL")
    cfg = dict(DEFAULT_CONFIG)
    if env_url:
        cfg["local_url"] = env_url
        cfg["base_url"] = env_url
    return cfg


def _load_config() -> dict:
    """Load the config; create the default config file on first run (never persists env secrets)."""
    defaults = _default_config()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            for key, val in defaults.items():
                if key not in config or (key in ("local_url", "system_prompt") and not config[key]):
                    config[key] = val
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to read LLM config: %s; using defaults", e)
    _save_config_raw(defaults)
    return defaults


def _save_config_raw(config: dict) -> None:
    """Write the raw config to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _mask_api_key(key: str) -> str:
    """Mask the API key for display: keep only the last 4 characters."""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


def _is_masked_key(val: str) -> bool:
    return bool(val) and (val.startswith("*") or set(val) == {"*"})


def _resolve_api_key(config: dict, provider: str) -> tuple[str, str]:
    """Return (api_key, source) where source is 'config', 'env', or ''."""
    saved = (config.get("api_key") or "").strip()
    if saved and not _is_masked_key(saved):
        return saved, "config"
    if provider in ("openai", "local"):
        env_key = _env_str("OPENAI_API_KEY")
        if env_key:
            return env_key, "env"
    elif provider == "anthropic":
        env_key = _env_str("ANTHROPIC_API_KEY")
        if env_key:
            return env_key, "env"
    return "", ""


def _resolve_openai_base_url(config: dict, provider: str) -> str:
    """Resolve and validate the base URL for openai or local providers."""
    if provider == "local":
        url = (config.get("local_url") or "").strip() or _env_str("OPENAI_BASE_URL") or PROVIDER_DEFAULTS["local"]["local_url"]
    else:
        url = (config.get("base_url") or "").strip() or _env_str("OPENAI_BASE_URL") or OPENAI_DEFAULT_BASE_URL

    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"Invalid API URL: {url!r} (must start with http:// or https://)")
    return url.rstrip("/")


def _merge_runtime_override(base: dict, override: dict | None) -> dict:
    """Merge a transient config override (e.g. from Test connection) without writing to disk."""
    if not override:
        return dict(base)
    merged = dict(base)
    prov = (override.get("provider") or "").strip()
    if prov:
        if prov not in VALID_PROVIDERS:
            raise ValueError(f"Unsupported provider: {prov}")
        merged["provider"] = prov
    for key in ("model", "local_url", "system_prompt"):
        val = override.get(key)
        if val is not None and str(val).strip():
            merged[key] = str(val).strip()
    if "base_url" in override and override["base_url"] is not None:
        merged["base_url"] = str(override["base_url"]).strip()
    new_key = (override.get("api_key") or "").strip()
    if new_key and not _is_masked_key(new_key):
        merged["api_key"] = new_key
    return merged


def _extract_error_detail(body_text: str) -> str:
    """Extract a concise, safe upstream error summary without exposing secrets."""
    raw = (body_text or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])[:200]
            if isinstance(err, str) and err:
                return err[:200]
            for k in ("detail", "message"):
                if parsed.get(k):
                    return str(parsed[k])[:200]
    except Exception:
        pass
    collapsed = " ".join(raw.split())
    return collapsed[:200]


def _format_http_error(status_code: int, body_text: str, base_url: str) -> str:
    detail = _extract_error_detail(body_text)
    suffix = f" ({detail})" if detail else ""
    if status_code in (401, 403):
        return f"Authentication failed (HTTP {status_code}): check your API key and permissions.{suffix}"
    if status_code == 404:
        return f"Upstream endpoint or model not found (HTTP 404) at {base_url}: check API URL and model name.{suffix}"
    if status_code == 429:
        return f"Rate limit or quota exceeded (HTTP 429): please retry shortly.{suffix}"
    if status_code >= 500:
        return f"Upstream LLM server error (HTTP {status_code}).{suffix}"
    return f"Upstream LLM request failed (HTTP {status_code}).{suffix}"


def _prepare_openai_messages(config: dict, messages: list[dict]) -> list[dict]:
    """Prepend configured system_prompt if the message list does not already include one."""
    if not messages:
        raise ValueError("messages must not be empty")
    system_prompt = (config.get("system_prompt") or "").strip()
    full_messages = [dict(m) for m in messages]
    if system_prompt and not any(m.get("role") == "system" for m in full_messages):
        full_messages.insert(0, {"role": "system", "content": system_prompt})
    return full_messages


# ── Public API ────────────────────────────────────────────────

def get_config() -> dict:
    """Return the current config with any saved API key masked and env defaults surfaced safely."""
    config = _load_config()
    provider = config.get("provider", "local")
    effective_key, key_source = _resolve_api_key(config, provider)

    result = dict(config)
    result["api_key"] = _mask_api_key(config.get("api_key", ""))
    result["api_key_set"] = bool(effective_key)
    result["api_key_source"] = key_source
    result["env_base_url"] = _env_str("OPENAI_BASE_URL")
    return result


def update_config(new_config: dict) -> dict:
    """Save a new config. Masked or blank api_key preserves the existing stored key."""
    old = _load_config()
    merged = dict(old)

    prov = (new_config.get("provider") or "").strip()
    if prov:
        if prov not in VALID_PROVIDERS:
            raise ValueError(f"Unsupported provider: {prov}")
        merged["provider"] = prov

    for key in ("model", "local_url", "system_prompt"):
        if key in new_config and new_config[key] is not None and str(new_config[key]).strip():
            merged[key] = str(new_config[key]).strip()

    if "base_url" in new_config and new_config["base_url"] is not None:
        merged["base_url"] = str(new_config["base_url"]).strip()

    new_key = (new_config.get("api_key") or "").strip()
    if new_key and not _is_masked_key(new_key):
        merged["api_key"] = new_key

    _save_config_raw(merged)
    logger.info("LLM config updated: provider=%s, model=%s", merged["provider"], merged["model"])
    return get_config()


def list_providers() -> list[dict]:
    """List the available providers and their default config."""
    env_url = _env_str("OPENAI_BASE_URL")
    return [
        {
            "id": "anthropic",
            "name": "Anthropic (Claude)",
            "default_model": PROVIDER_DEFAULTS["anthropic"]["model"],
            "needs_url": False,
        },
        {
            "id": "openai",
            "name": "OpenAI (GPT-4o)",
            "default_model": PROVIDER_DEFAULTS["openai"]["model"],
            "default_url": env_url or OPENAI_DEFAULT_BASE_URL,
            "needs_url": True,
        },
        {
            "id": "local",
            "name": "Local (Ollama/vLLM)",
            "default_model": PROVIDER_DEFAULTS["local"]["model"],
            "default_url": env_url or PROVIDER_DEFAULTS["local"]["local_url"],
            "needs_url": True,
        },
    ]


async def chat(
    messages: list[dict],
    stream: bool = True,
    config_override: dict | None = None,
    timeout: httpx.Timeout | None = None,
) -> AsyncGenerator[str, None]:
    """Run an LLM chat and yield text tokens."""
    config = _merge_runtime_override(_load_config(), config_override)
    provider = config.get("provider", "local")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")

    api_key, _ = _resolve_api_key(config, provider)
    if provider == "anthropic" and not api_key:
        raise ValueError("API key is not set; configure it in the AI assistant settings or set ANTHROPIC_API_KEY.")
    if provider == "openai" and not api_key:
        base_url = _resolve_openai_base_url(config, provider)
        if base_url == OPENAI_DEFAULT_BASE_URL:
            raise ValueError("API key is not set; configure it in the AI assistant settings or set OPENAI_API_KEY.")

    effective_timeout = timeout or CHAT_TIMEOUT
    if provider == "anthropic":
        async for token in _chat_anthropic(config, api_key, messages, effective_timeout):
            yield token
    else:
        async for token in _chat_openai(
            config, messages, is_local=(provider == "local"), api_key=api_key, timeout=effective_timeout
        ):
            yield token


async def test_connection(config_override: dict | None = None) -> str:
    """Verify the active or draft LLM configuration by running a short completion."""
    test_messages = [
        {"role": "user", "content": 'Reply with the single word "connected".'}
    ]
    chunks: list[str] = []
    async for token in chat(
        test_messages,
        stream=True,
        config_override=config_override,
        timeout=TEST_TIMEOUT,
    ):
        chunks.append(token)
    reply = "".join(chunks).strip()
    if not reply:
        raise RuntimeError("Upstream LLM returned an empty response.")
    return reply


# ── OpenAI-compatible streaming (OpenAI & Local) ──────────────

async def _stream_openai_compatible(
    base_url: str,
    api_key: str,
    payload: dict,
    timeout: httpx.Timeout,
) -> AsyncGenerator[str, None]:
    """POST {base_url}/chat/completions and stream SSE delta tokens."""
    url = f"{base_url}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    logger.info("OpenAI-compatible request: url=%s, model=%s", url, payload.get("model"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(_format_http_error(resp.status_code, body, base_url))

                content_type = (resp.headers.get("content-type") or "").lower()
                if "application/json" in content_type and "text/event-stream" not in content_type:
                    raw = (await resp.aread()).decode("utf-8", errors="replace")
                    data = json.loads(raw)
                    if isinstance(data, dict) and data.get("error"):
                        raise RuntimeError(_format_http_error(resp.status_code, raw, base_url))
                    choices = data.get("choices") or []
                    if choices:
                        msg = (choices[0].get("message") or {}).get("content")
                        if msg:
                            yield msg
                    return

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(chunk, dict) and chunk.get("error"):
                        raise RuntimeError(
                            f"Upstream LLM stream error: {_extract_error_detail(data_str) or 'unknown error'}"
                        )
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    token = delta.get("content")
                    if token is None:
                        token = (choices[0].get("message") or {}).get("content")
                    if token:
                        yield token
    except httpx.TimeoutException as e:
        raise RuntimeError("Request timed out while waiting for the LLM server.") from e
    except httpx.ConnectError as e:
        raise RuntimeError(f"Could not connect to the LLM server at {base_url}.") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"Network error contacting LLM server at {base_url}: {e}") from e


async def _chat_openai(
    config: dict,
    messages: list[dict],
    is_local: bool = False,
    api_key: str | None = None,
    timeout: httpx.Timeout = CHAT_TIMEOUT,
) -> AsyncGenerator[str, None]:
    """Streaming chat call for OpenAI or Local OpenAI-compatible servers."""
    provider = "local" if is_local else "openai"
    base_url = _resolve_openai_base_url(config, provider)
    resolved_key = api_key if api_key is not None else _resolve_api_key(config, provider)[0]
    if is_local and not resolved_key:
        resolved_key = "not-needed"

    model = (config.get("model") or "").strip() or PROVIDER_DEFAULTS[provider]["model"]
    full_messages = _prepare_openai_messages(config, messages)
    payload = {
        "model": model,
        "messages": full_messages,
        "stream": True,
    }
    async for token in _stream_openai_compatible(base_url, resolved_key, payload, timeout):
        yield token


# ── Anthropic streaming ───────────────────────────────────────

async def _stream_anthropic(
    api_key: str,
    payload: dict,
    timeout: httpx.Timeout,
) -> AsyncGenerator[str, None]:
    """POST Anthropic /v1/messages and stream SSE text_delta tokens."""
    base_url = (_env_str("ANTHROPIC_BASE_URL") or ANTHROPIC_DEFAULT_BASE_URL).rstrip("/")
    url = f"{base_url}/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }

    logger.info("Anthropic request: model=%s", payload.get("model"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code >= 400:
                    body = (await resp.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(_format_http_error(resp.status_code, body, base_url))

                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    ev_type = event.get("type")
                    if ev_type == "error":
                        raise RuntimeError(
                            f"Anthropic API error: {_extract_error_detail(data_str) or 'unknown error'}"
                        )
                    if ev_type == "content_block_delta":
                        delta = event.get("delta") or {}
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            yield delta["text"]
                    elif ev_type == "message_stop":
                        break
    except httpx.TimeoutException as e:
        raise RuntimeError("Request timed out while waiting for the Anthropic API.") from e
    except httpx.ConnectError as e:
        raise RuntimeError(f"Could not connect to the Anthropic API at {base_url}.") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"Network error contacting Anthropic API: {e}") from e


async def _chat_anthropic(
    config: dict,
    api_key: str,
    messages: list[dict],
    timeout: httpx.Timeout = CHAT_TIMEOUT,
) -> AsyncGenerator[str, None]:
    """Streaming chat call through the Anthropic Messages API."""
    if not messages:
        raise ValueError("messages must not be empty")
    system_prompt = (config.get("system_prompt") or "").strip()
    user_messages = [m for m in messages if m.get("role") != "system"]
    if not user_messages:
        raise ValueError("messages must contain at least one non-system message")
    system_msg = next((m for m in messages if m.get("role") == "system"), None)
    effective_system = (system_msg["content"] if system_msg else "") or system_prompt

    model = (config.get("model") or "").strip() or PROVIDER_DEFAULTS["anthropic"]["model"]
    payload: dict = {
        "model": model,
        "max_tokens": 4096,
        "messages": user_messages,
        "stream": True,
    }
    if effective_system:
        payload["system"] = effective_system

    async for token in _stream_anthropic(api_key, payload, timeout):
        yield token


# ── VLM slice interpretation ──────────────────────────────────

async def analyze_image(image_base64: str, context: dict) -> AsyncGenerator[str, None]:
    """
    VLM interpretation of a seismic slice. Sends a canvas screenshot plus structured context
    so a vision-language model can analyse the pick points, SAM3 segmented regions and geological features.
    """
    config = _load_config()
    provider = config.get("provider", "local")
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")

    api_key, _ = _resolve_api_key(config, provider)
    if provider == "anthropic" and not api_key:
        raise ValueError("API key is not set; configure it in the AI assistant settings or set ANTHROPIC_API_KEY.")
    if provider == "openai" and not api_key:
        base_url = _resolve_openai_base_url(config, provider)
        if base_url == OPENAI_DEFAULT_BASE_URL:
            raise ValueError("API key is not set; configure it in the AI assistant settings or set OPENAI_API_KEY.")

    prompt = _build_analysis_prompt(context)

    if provider == "anthropic":
        async for token in _analyze_anthropic(config, api_key, image_base64, prompt):
            yield token
    else:
        async for token in _analyze_openai(
            config, image_base64, prompt, is_local=(provider == "local"), api_key=api_key
        ):
            yield token


def _build_analysis_prompt(context: dict) -> str:
    """Build the geological interpretation prompt."""
    direction = context.get("direction", "inline")
    dir_cn = {"inline": "Inline", "crossline": "Crossline",
              "timeslice": "Time slice"}.get(direction, direction)
    line_label = context.get("line_label", "unknown")
    volume_name = context.get("volume_name", "unknown")
    coords = context.get("coords", {})
    x_label = coords.get("x_label", "X")
    y_label = coords.get("y_label", "Y")
    time_at_slice = context.get("time_at_slice")

    picks = context.get("picks", {})
    n_include = picks.get("include", 0)
    n_exclude = picks.get("exclude", 0)

    sam = context.get("sam_mask", {})
    has_sam = sam.get("score", 0) > 0

    parts = [
        "Give a professional geological interpretation of this seismic image.",
        "",
        "[Section info]",
        f"- Volume: {volume_name}",
        f"- Section type: {dir_cn}",
        f"- {line_label}",
        f"- X axis ({x_label}): {coords.get('x_min', '?')} ~ {coords.get('x_max', '?')}",
    ]

    if direction == "timeslice":
        parts.append(f"- Y axis ({y_label}): {coords.get('y_max', '?')} ~ {coords.get('y_min', '?')}")
        if time_at_slice is not None:
            parts.append(f"- Current time level: ~{time_at_slice} ms")
        parts.append("- Note: this is a horizontal slice (map view), not a vertical section.")
        parts.append("  X = crossline direction, Y = inline direction; it shows the amplitude map at this time level.")
    else:
        parts.append(f"- Y axis ({y_label}): {coords.get('y_min', '?')} ~ {coords.get('y_max', '?')}")
        parts.append(f"- Note: this is a vertical section; the Y axis shows {'depth increasing' if 'epth' in str(y_label) else 'time increasing'} from top to bottom.")

    parts.append("")

    if n_include > 0 or n_exclude > 0:
        parts.append("[Manual pick points]")
        if n_include > 0:
            parts.append(f"- Include points (green markers): {n_include}, target body areas marked by the user")
        if n_exclude > 0:
            parts.append(f"- Exclude points (red markers): {n_exclude}, background areas excluded by the user")
        parts.append("")

    if has_sam:
        parts.append("[SAM3 segmentation result]")
        parts.append(f"- Segmentation confidence: {sam.get('score', 0):.4f}")
        parts.append(f"- Segmented area fraction: {sam.get('area_pct', 0):.1f}%")
        parts.append("- The semi-transparent green overlay is the geological anomaly segmented by SAM3")
        parts.append("- Use the pick point positions and the SAM3 outline to analyse the geological meaning of this anomaly")
        parts.append("")

    parts.extend([
        "[Analyse along these dimensions]",
        "1. **Structure**: any signs of faults, folds, unconformities?",
        "2. **Stratigraphy**: identifiable reflectors, depositional sequences, onlap/downlap/toplap relations",
        "3. **Anomaly**: what geological body could the area outlined by the picks and SAM3 represent?",
        "   (e.g. channel sand, fan, reef/shoal, salt dome, igneous intrusion, gas bright spot)",
        "4. **Amplitude**: any strong amplitude anomalies (bright/flat spots), weak-amplitude zones, polarity reversals?",
        "5. **Overall assessment**: exploration significance of this section and suggested next interpretation steps",
        "",
        "Answer in English, clearly structured, with accurate technical terms.",
    ])

    return "\n".join(parts)


async def _analyze_anthropic(
    config: dict,
    api_key: str,
    image_base64: str,
    prompt: str,
) -> AsyncGenerator[str, None]:
    """Streaming Vision call to the Anthropic Messages API."""
    model = (config.get("model") or "").strip() or PROVIDER_DEFAULTS["anthropic"]["model"]
    payload = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }
    async for token in _stream_anthropic(api_key, payload, CHAT_TIMEOUT):
        yield token


async def _analyze_openai(
    config: dict,
    image_base64: str,
    prompt: str,
    is_local: bool = False,
    api_key: str | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming Vision call to an OpenAI-compatible API."""
    provider = "local" if is_local else "openai"
    base_url = _resolve_openai_base_url(config, provider)
    resolved_key = api_key if api_key is not None else _resolve_api_key(config, provider)[0]
    if is_local and not resolved_key:
        resolved_key = "not-needed"

    model = (config.get("model") or "").strip() or PROVIDER_DEFAULTS[provider]["model"]
    payload = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    async for token in _stream_openai_compatible(base_url, resolved_key, payload, CHAT_TIMEOUT):
        yield token
