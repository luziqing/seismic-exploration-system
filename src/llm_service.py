"""
LLM service: provider abstraction layer (Anthropic / OpenAI / Local)
Config is persisted to data/llm_config.json and read/written through the API.
SDKs are lazy-loaded: imports live inside functions, so the server starts without the LLM SDKs installed.
"""

import json
import logging
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger("sam3-server")

# ── Path constants ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "llm_config.json"

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
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
}

PROVIDER_DEFAULTS = {
    "anthropic": {"model": "claude-sonnet-4-20250514"},
    "openai": {"model": "gpt-4o"},
    "local": {"model": "qwen2.5:7b", "local_url": "http://localhost:11434/v1"},
}


# ── Internal helpers ──────────────────────────────────────────

def _load_config() -> dict:
    """Load the config; create the default config file on first run"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            # fill in missing fields
            for key, val in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = val
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to read LLM config: %s; using defaults", e)
    # first run: create it
    _save_config_raw(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def _save_config_raw(config: dict):
    """Write the raw config to file"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _mask_api_key(key: str) -> str:
    """Mask the API key for display: keep the last 4 characters"""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


# ── Public API ────────────────────────────────────────────────

def get_config() -> dict:
    """Return the current config with the API key masked"""
    config = _load_config()
    result = dict(config)
    if result.get("api_key"):
        result["api_key"] = _mask_api_key(result["api_key"])
    else:
        result["api_key"] = ""
    return result


def update_config(new_config: dict) -> dict:
    """Save a new config. If api_key is the masked value (all *), keep the existing key"""
    old = _load_config()
    merged = dict(old)

    for key in ("provider", "model", "local_url", "system_prompt"):
        if key in new_config and new_config[key]:
            merged[key] = new_config[key]

    # API key: keep the existing value if the input is the masked value (all *) or empty
    new_key = new_config.get("api_key", "")
    if new_key and not new_key.startswith("*") and new_key != "****":
        merged["api_key"] = new_key

    _save_config_raw(merged)
    logger.info("LLM config updated: provider=%s, model=%s", merged["provider"], merged["model"])
    return get_config()


def list_providers() -> list[dict]:
    """List the available providers and their default config"""
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
            "needs_url": False,
        },
        {
            "id": "local",
            "name": "Local (Ollama/vLLM)",
            "default_model": PROVIDER_DEFAULTS["local"]["model"],
            "default_url": PROVIDER_DEFAULTS["local"]["local_url"],
            "needs_url": True,
        },
    ]


async def chat(messages: list[dict], stream: bool = True) -> AsyncGenerator[str, None]:
    """
    Run an LLM chat and yield SSE text chunks.

    Args:
        messages: [{"role": "user"/"assistant"/"system", "content": "..."}]
        stream: whether to stream the output
    Yields:
        one token string per yield
    """
    config = _load_config()
    provider = config.get("provider", "local")

    if not config.get("api_key") and provider != "local":
        raise ValueError("API key is not set; configure it in the AI assistant settings")

    if provider == "anthropic":
        async for token in _chat_anthropic(config, messages):
            yield token
    elif provider == "openai":
        async for token in _chat_openai(config, messages, is_local=False):
            yield token
    elif provider == "local":
        async for token in _chat_openai(config, messages, is_local=True):
            yield token
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def _chat_anthropic(config: dict, messages: list[dict]) -> AsyncGenerator[str, None]:
    """Streaming call through the Anthropic SDK"""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=config["api_key"])
    system_prompt = config.get("system_prompt", "")

    # Anthropic requires system as a top-level parameter, not inside messages
    user_messages = [m for m in messages if m.get("role") != "system"]
    # if messages has no system role, use system_prompt from the config
    system_msg = next((m for m in messages if m.get("role") == "system"), None)
    effective_system = (system_msg["content"] if system_msg else "") or system_prompt

    logger.info("Anthropic streaming call: model=%s, messages=%d", config["model"], len(user_messages))
    async with client.messages.stream(
        model=config["model"],
        max_tokens=4096,
        system=effective_system,
        messages=user_messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def analyze_image(image_base64: str, context: dict) -> AsyncGenerator[str, None]:
    """
    VLM interpretation of a seismic slice. Sends a canvas screenshot plus structured context
    so a vision-language model can analyse the pick points, SAM3 segmented regions and geological features.

    Args:
        image_base64: base64 of the canvas screenshot (without the data: prefix)
        context: {
            "direction": "inline"/"crossline"/"timeslice",
            "line_index": 1511, "line_label": "IL 1511",
            "volume_name": "...",
            "picks": {"include": 3, "exclude": 1},
            "sam_mask": {"score": 0.85, "area_pct": 12.3},
            "coords": {"x_min": 2200, "x_max": 4000, "y_min": 800, "y_max": 2500},
            "y_unit": "Time (ms)" / "Depth (m)",
        }
    Yields:
        one token string per yield
    """
    config = _load_config()
    provider = config.get("provider", "local")

    prompt = _build_analysis_prompt(context)

    if provider == "anthropic":
        async for token in _analyze_anthropic(config, image_base64, prompt):
            yield token
    elif provider in ("openai", "local"):
        is_local = (provider == "local")
        async for token in _analyze_openai(config, image_base64, prompt, is_local):
            yield token
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _build_analysis_prompt(context: dict) -> str:
    """Build the geological interpretation prompt"""
    direction = context.get("direction", "inline")
    dir_cn = {"inline": "Inline", "crossline": "Crossline",
              "timeslice": "Time slice"}.get(direction, direction)
    line_label = context.get("line_label", "unknown")
    volume_name = context.get("volume_name", "unknown")
    coords = context.get("coords", {})
    x_label = coords.get("x_label", "X")
    y_label = coords.get("y_label", "Y")
    time_at_slice = context.get("time_at_slice")

    # pick point info
    picks = context.get("picks", {})
    n_include = picks.get("include", 0)
    n_exclude = picks.get("exclude", 0)

    # SAM3 segmentation info
    sam = context.get("sam_mask", {})
    has_sam = sam.get("score", 0) > 0

    parts = [
        f"Give a professional geological interpretation of this seismic image.",
        f"",
        f"[Section info]",
        f"- Volume: {volume_name}",
        f"- Section type: {dir_cn}",
        f"- {line_label}",
        f"- X axis ({x_label}): {coords.get('x_min', '?')} ~ {coords.get('x_max', '?')}",
    ]

    if direction == "timeslice":
        parts.append(f"- Y axis ({y_label}): {coords.get('y_max', '?')} ~ {coords.get('y_min', '?')}")
        if time_at_slice is not None:
            parts.append(f"- Current time level: ~{time_at_slice} ms")
        parts.append(f"- Note: this is a horizontal slice (map view), not a vertical section.")
        parts.append(f"  X = crossline direction, Y = inline direction; it shows the amplitude map at this time level.")
    else:
        parts.append(f"- Y axis ({y_label}): {coords.get('y_min', '?')} ~ {coords.get('y_max', '?')}")
        parts.append(f"- Note: this is a vertical section; the Y axis shows { 'depth increasing' if 'epth' in str(y_label) else 'time increasing' } from top to bottom.")

    parts.append(f"")

    if n_include > 0 or n_exclude > 0:
        parts.append(f"[Manual pick points]")
        if n_include > 0:
            parts.append(f"- Include points (green markers): {n_include}, target body areas marked by the user")
        if n_exclude > 0:
            parts.append(f"- Exclude points (red markers): {n_exclude}, background areas excluded by the user")
        parts.append(f"")

    if has_sam:
        parts.append(f"[SAM3 segmentation result]")
        parts.append(f"- Segmentation confidence: {sam.get('score', 0):.4f}")
        parts.append(f"- Segmented area fraction: {sam.get('area_pct', 0):.1f}%")
        parts.append(f"- The semi-transparent green overlay is the geological anomaly segmented by SAM3")
        parts.append(f"- Use the pick point positions and the SAM3 outline to analyse the geological meaning of this anomaly")
        parts.append(f"")

    parts.append(f"[Analyse along these dimensions]")
    parts.append(f"1. **Structure**: any signs of faults, folds, unconformities?")
    parts.append(f"2. **Stratigraphy**: identifiable reflectors, depositional sequences, onlap/downlap/toplap relations")
    parts.append(f"3. **Anomaly**: what geological body could the area outlined by the picks and SAM3 represent?")
    parts.append(f"   (e.g. channel sand, fan, reef/shoal, salt dome, igneous intrusion, gas bright spot)")
    parts.append(f"4. **Amplitude**: any strong amplitude anomalies (bright/flat spots), weak-amplitude zones, polarity reversals?")
    parts.append(f"5. **Overall assessment**: exploration significance of this section and suggested next interpretation steps")
    parts.append(f"")
    parts.append(f"Answer in English, clearly structured, with accurate technical terms.")

    return "\n".join(parts)


async def _analyze_anthropic(config: dict, image_base64: str,
                              prompt: str) -> AsyncGenerator[str, None]:
    """Streaming call to the Anthropic Vision API"""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=config["api_key"])

    # determine the image MIME type
    media_type = "image/png"

    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_base64,
            },
        },
        {"type": "text", "text": prompt},
    ]

    logger.info("Anthropic Vision analysis: model=%s", config["model"])
    async with client.messages.stream(
        model=config["model"],
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _analyze_openai(config: dict, image_base64: str,
                           prompt: str, is_local: bool = False) -> AsyncGenerator[str, None]:
    """Streaming call to the OpenAI Vision API (also used for Local)"""
    from openai import AsyncOpenAI

    kwargs: dict = {"api_key": config["api_key"] or "not-needed"}
    if is_local:
        kwargs["base_url"] = config.get("local_url", "http://localhost:11434/v1")

    client = AsyncOpenAI(**kwargs)

    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
            {"type": "text", "text": prompt},
        ],
    }]

    logger.info("OpenAI Vision analysis: model=%s, local=%s", config["model"], is_local)
    stream = await client.chat.completions.create(
        model=config["model"],
        messages=messages,
        stream=True,
        max_tokens=4096,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
    """Streaming call through the OpenAI SDK (also used for local OpenAI-compatible APIs)"""
    from openai import AsyncOpenAI

    kwargs: dict = {"api_key": config["api_key"] or "not-needed"}
    if is_local:
        kwargs["base_url"] = config.get("local_url", "http://localhost:11434/v1")

    client = AsyncOpenAI(**kwargs)

    system_prompt = config.get("system_prompt", "")
    full_messages = list(messages)
    if system_prompt and not any(m.get("role") == "system" for m in full_messages):
        full_messages.insert(0, {"role": "system", "content": system_prompt})

    logger.info("OpenAI streaming call: model=%s, local=%s, messages=%d",
                config["model"], is_local, len(full_messages))
    stream = await client.chat.completions.create(
        model=config["model"],
        messages=full_messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
