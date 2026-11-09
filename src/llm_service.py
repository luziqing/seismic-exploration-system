"""
LLM 服务 — 多模型提供商抽象层 (Anthropic / OpenAI / Local)
配置持久化到 data/llm_config.json，通过 API 读写。
SDK 懒加载：import 放在函数内部，服务启动不依赖 LLM SDK 存在。
"""

import json
import logging
from pathlib import Path
from typing import AsyncGenerator

logger = logging.getLogger("sam3-server")

# ── 路径常量 ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "llm_config.json"

# ── 默认配置 ──────────────────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = (
    "你是一位地震数据解释与地质分析专家助手，名称 SGSeg AI。"
    "你擅长地震剖面解读、层位追踪、断层识别、沉积相分析、"
    "以及 SAM3 分割模型的交互式点提示建议。"
    "请用中文简洁准确地回答用户的专业问题。"
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


# ── 内部函数 ──────────────────────────────────────────────────

def _load_config() -> dict:
    """加载配置，首次运行时自动创建默认配置文件"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
            # 补齐缺失字段
            for key, val in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = val
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("LLM 配置读取失败: %s，使用默认值", e)
    # 首次创建
    _save_config_raw(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def _save_config_raw(config: dict):
    """写入原始配置到文件"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _mask_api_key(key: str) -> str:
    """脱敏显示 API key：保留后 4 位"""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return "*" * (len(key) - 4) + key[-4:]


# ── 公开 API ──────────────────────────────────────────────────

def get_config() -> dict:
    """返回当前配置，API key 脱敏"""
    config = _load_config()
    result = dict(config)
    if result.get("api_key"):
        result["api_key"] = _mask_api_key(result["api_key"])
    else:
        result["api_key"] = ""
    return result


def update_config(new_config: dict) -> dict:
    """保存新配置。如果 api_key 为脱敏值（全是 *），保留原 key"""
    old = _load_config()
    merged = dict(old)

    for key in ("provider", "model", "local_url", "system_prompt"):
        if key in new_config and new_config[key]:
            merged[key] = new_config[key]

    # API key：如果传入的是脱敏值（全 *）或空，保留原值
    new_key = new_config.get("api_key", "")
    if new_key and not new_key.startswith("*") and new_key != "****":
        merged["api_key"] = new_key

    _save_config_raw(merged)
    logger.info("LLM 配置已更新: provider=%s, model=%s", merged["provider"], merged["model"])
    return get_config()


def list_providers() -> list[dict]:
    """列出可用提供商及其默认配置"""
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
    执行 LLM 对话，生成 SSE 文本块。

    Args:
        messages: [{"role": "user"/"assistant"/"system", "content": "..."}]
        stream: 是否流式输出
    Yields:
        每次 yield 一个 token 字符串
    """
    config = _load_config()
    provider = config.get("provider", "local")

    if not config.get("api_key") and provider != "local":
        raise ValueError("API Key 未设置，请在 AI 助手设置中配置")

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
        raise ValueError(f"不支持的提供商: {provider}")


async def _chat_anthropic(config: dict, messages: list[dict]) -> AsyncGenerator[str, None]:
    """使用 Anthropic SDK 流式调用"""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=config["api_key"])
    system_prompt = config.get("system_prompt", "")

    # Anthropic 要求 system 为顶层参数，不能放在 messages 里
    user_messages = [m for m in messages if m.get("role") != "system"]
    # 如果 messages 中没有 system 角色，使用配置中的 system_prompt
    system_msg = next((m for m in messages if m.get("role") == "system"), None)
    effective_system = (system_msg["content"] if system_msg else "") or system_prompt

    logger.info("Anthropic 流式调用: model=%s, messages=%d", config["model"], len(user_messages))
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
    VLM 地震切片智能解读。发送画布截图+结构化上下文，
    让视觉语言模型分析拾取点、SAM3 分割区域及地质特征。

    Args:
        image_base64: 画布截图的 base64 编码 (不含 data: 前缀)
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
        每次 yield 一个 token 字符串
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
        raise ValueError(f"不支持的提供商: {provider}")


def _build_analysis_prompt(context: dict) -> str:
    """构建地质解读分析提示词"""
    direction = context.get("direction", "inline")
    dir_cn = {"inline": "主测线 (Inline)", "crossline": "联络测线 (Crossline)",
              "timeslice": "时间切片 (TimeSlice)"}.get(direction, direction)
    line_label = context.get("line_label", "未知")
    volume_name = context.get("volume_name", "未知")
    coords = context.get("coords", {})
    x_label = coords.get("x_label", "X")
    y_label = coords.get("y_label", "Y")
    time_at_slice = context.get("time_at_slice")

    # 拾取点信息
    picks = context.get("picks", {})
    n_include = picks.get("include", 0)
    n_exclude = picks.get("exclude", 0)

    # SAM3 分割信息
    sam = context.get("sam_mask", {})
    has_sam = sam.get("score", 0) > 0

    parts = [
        f"请对这张地震剖面图片进行专业地质解读。",
        f"",
        f"【剖面信息】",
        f"- 数据体: {volume_name}",
        f"- 剖面类型: {dir_cn}",
        f"- {line_label}",
        f"- X 轴 ({x_label}): {coords.get('x_min', '?')} ~ {coords.get('x_max', '?')}",
    ]

    if direction == "timeslice":
        parts.append(f"- Y 轴 ({y_label}): {coords.get('y_max', '?')} ~ {coords.get('y_min', '?')}")
        if time_at_slice is not None:
            parts.append(f"- 当前时间层位: ~{time_at_slice} ms")
        parts.append(f"- 注意: 这是水平切片（俯视图），不是垂直剖面。")
        parts.append(f"  X=Crossline 方向, Y=Inline 方向，展示的是该时间层位的平面振幅分布。")
    else:
        parts.append(f"- Y 轴 ({y_label}): {coords.get('y_min', '?')} ~ {coords.get('y_max', '?')}")
        parts.append(f"- 注意: 这是垂直剖面，Y 轴从上到下表示{ '深度增加' if 'epth' in str(y_label) else '时间增加' }。")

    parts.append(f"")

    if n_include > 0 or n_exclude > 0:
        parts.append(f"【人工拾取点】")
        if n_include > 0:
            parts.append(f"- Include 点 (绿色标记): {n_include} 个 — 用户标记的目标地质体区域")
        if n_exclude > 0:
            parts.append(f"- Exclude 点 (红色标记): {n_exclude} 个 — 用户排除的背景区域")
        parts.append(f"")

    if has_sam:
        parts.append(f"【SAM3 智能分割结果】")
        parts.append(f"- 分割置信度: {sam.get('score', 0):.4f}")
        parts.append(f"- 分割面积占比: {sam.get('area_pct', 0):.1f}%")
        parts.append(f"- 图中半透明绿色覆盖区域即为 SAM3 自动分割的地质异常体")
        parts.append(f"- 结合拾取点位置和 SAM3 分割轮廓，分析该异常体的地质意义")
        parts.append(f"")

    parts.append(f"【请从以下维度进行分析】")
    parts.append(f"1. **构造特征**: 是否有断层、褶皱、不整合面等构造迹象？")
    parts.append(f"2. **地层特征**: 可识别的反射层位、沉积层序、上超/下超/顶超等接触关系")
    parts.append(f"3. **异常体解读**: 拾取点和 SAM3 分割所圈定的区域可能代表什么地质体？")
    parts.append(f"   （如河道砂体、扇体、礁滩、盐丘、火成岩侵入体、含气亮点等）")
    parts.append(f"4. **振幅特征**: 是否有强振幅异常（亮点/平点）、弱振幅带、极性反转等？")
    parts.append(f"5. **综合评价**: 该剖面的勘探意义和建议的后续解释方向")
    parts.append(f"")
    parts.append(f"请用中文回答，结构清晰，专业术语准确。")

    return "\n".join(parts)


async def _analyze_anthropic(config: dict, image_base64: str,
                              prompt: str) -> AsyncGenerator[str, None]:
    """Anthropic Vision API 流式调用"""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=config["api_key"])

    # 确定图片 MIME 类型
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

    logger.info("Anthropic Vision 分析: model=%s", config["model"])
    async with client.messages.stream(
        model=config["model"],
        max_tokens=4096,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _analyze_openai(config: dict, image_base64: str,
                           prompt: str, is_local: bool = False) -> AsyncGenerator[str, None]:
    """OpenAI Vision API 流式调用 (同时用于 Local)"""
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

    logger.info("OpenAI Vision 分析: model=%s, local=%s", config["model"], is_local)
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
    """使用 OpenAI SDK 流式调用 (同时用于 Local OpenAI-compatible API)"""
    from openai import AsyncOpenAI

    kwargs: dict = {"api_key": config["api_key"] or "not-needed"}
    if is_local:
        kwargs["base_url"] = config.get("local_url", "http://localhost:11434/v1")

    client = AsyncOpenAI(**kwargs)

    system_prompt = config.get("system_prompt", "")
    full_messages = list(messages)
    if system_prompt and not any(m.get("role") == "system" for m in full_messages):
        full_messages.insert(0, {"role": "system", "content": system_prompt})

    logger.info("OpenAI 流式调用: model=%s, local=%s, messages=%d",
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
