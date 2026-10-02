#!/usr/bin/env python3
"""LLM provider 抽象层（零第三方依赖，仅标准库）。

环境变量 LLM_PROVIDER（单 provider）或 LLM_PROVIDERS（按顺序的 fallback 链）切换后端：
- deepseek          —— OpenAI 兼容的 /chat/completions，端点由 DEEPSEEK_API_BASE 决定
                       （默认主用交大网关 https://models.sjtu.edu.cn/api/v1）
- deepseek-official —— 同一套协议，走 DeepSeek 官方 api.deepseek.com（备用，DEEPSEEK_OFFICIAL_*）
- claude            —— Anthropic 官方 /v1/messages
- gpt               —— OpenAI 兼容的 /chat/completions（可接 RightAPI 等中转站）

对外只暴露一个函数：chat_json(system, user, providers=None) -> dict。
它要求模型返回**严格 JSON**，解析失败会重试；多家 API 的差异都封在内部。

环境变量见仓库根目录 .env.example。本模块也顺带提供 load_dotenv()，
让脚本无需第三方库即可读取 .env。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path


def load_dotenv(path: str | os.PathLike | None = None) -> None:
    """极简 .env 加载器：把 KEY=VALUE 读进 os.environ（不覆盖已存在的）。"""
    env_path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


UA = "SocialNewsDigest/1.0 (+https://github.com/) Python-urllib"


class LLMError(RuntimeError):
    pass


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_json(text: str) -> dict:
    """从模型输出里抠出 JSON 对象：先直接 parse，失败再截首个 {...} 块。"""
    text = text.strip()
    # 去掉可能的 ```json ... ``` 围栏
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, depth = text.find("{"), 0
    if start >= 0:
        for i in range(start, len(text)):
            depth += (text[i] == "{") - (text[i] == "}")
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise LLMError("模型未返回可解析的 JSON")


def _call_deepseek(system: str, user: str, timeout: int) -> str:
    """OpenAI 兼容 /chat/completions（DeepSeek 官方或交大网关）。"""
    base = _env("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
    key = _env("DEEPSEEK_API_KEY")
    model = _env("DEEPSEEK_MODEL", "deepseek-chat")
    if not key:
        raise LLMError("缺少 DEEPSEEK_API_KEY（检查 .env）")
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
               "User-Agent": UA}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    resp = _post(url, headers, payload, timeout)
    return resp["choices"][0]["message"]["content"]


def _call_deepseek_official(system: str, user: str, timeout: int) -> str:
    """DeepSeek 官方 API（备用）。协议与 _call_deepseek 完全一致，只是另一套端点配置。

    与 DEEPSEEK_*（主用，本机指向交大网关）分开命名，才能在 LLM_PROVIDERS 里
    同时挂上「校园网关 + 官方 API」两条腿。"""
    os.environ.setdefault("DEEPSEEK_OFFICIAL_API_BASE", "https://api.deepseek.com")
    os.environ.setdefault("DEEPSEEK_OFFICIAL_MODEL", "deepseek-flash")
    return _call_openai_compatible("DEEPSEEK_OFFICIAL", system, user, timeout)


def _call_openai_compatible(prefix: str, system: str, user: str, timeout: int) -> str:
    """调用 OpenAI 兼容网关。prefix 为环境变量前缀（如 GPT）。"""
    base = _env(f"{prefix}_API_BASE").rstrip("/")
    key = _env(f"{prefix}_API_KEY")
    model = _env(f"{prefix}_MODEL")
    if not base:
        raise LLMError(f"缺少 {prefix}_API_BASE（检查 .env）")
    if not key:
        raise LLMError(f"缺少 {prefix}_API_KEY（检查 .env）")
    if not model:
        raise LLMError(f"缺少 {prefix}_MODEL（检查 .env）")
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
               "User-Agent": UA}
    payload = {"model": model,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "temperature": 0.3,
               "response_format": {"type": "json_object"}, "stream": False}
    resp = _post(url, headers, payload, timeout)
    return resp["choices"][0]["message"]["content"]


def _call_gpt(system: str, user: str, timeout: int) -> str:
    """调用 GPT 的 OpenAI 兼容中转接口（例如 RightAPI）。"""
    # RightAPI 的 Claude/Codex 上游可共用同一把 key；显式 GPT_* 配置优先。
    os.environ.setdefault("GPT_API_BASE", "https://www.rightapi.ai/codex/v1")
    os.environ.setdefault("GPT_MODEL", "gpt-5.6-luna")
    if not _env("GPT_API_KEY") and _env("ANTHROPIC_API_KEY"):
        os.environ["GPT_API_KEY"] = _env("ANTHROPIC_API_KEY")
    return _call_openai_compatible("GPT", system, user, timeout)


def _call_claude(system: str, user: str, timeout: int) -> str:
    """Anthropic 官方 /v1/messages。"""
    base = _env("ANTHROPIC_API_BASE", "https://api.anthropic.com").rstrip("/")
    key = _env("ANTHROPIC_API_KEY")
    model = _env("ANTHROPIC_MODEL", "claude-opus-4-8")
    if not key:
        raise LLMError("缺少 ANTHROPIC_API_KEY（检查 .env）")
    url = f"{base}/v1/messages"
    headers = {"Content-Type": "application/json", "x-api-key": key,
               "anthropic-version": "2023-06-01", "User-Agent": UA}
    payload = {
        "model": model,
        "max_tokens": 8192,
        "temperature": 0.3,
        "system": system + "\n\n只输出一个 JSON 对象，不要任何额外文字或 markdown 围栏。",
        "messages": [{"role": "user", "content": user}],
        # 流式：大输出（整份 digest）非流式会 >100s 触发网关 524，流式持续吐字节可避免。
        "stream": True,
    }
    return _stream_claude(url, headers, payload, timeout)


def _stream_claude(url: str, headers: dict, payload: dict, timeout: int) -> str:
    """读 Anthropic SSE 流，拼接所有 text_delta。"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    chunks: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body or body == "[DONE]":
                continue
            try:
                evt = json.loads(body)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "content_block_delta":
                delta = evt.get("delta", {})
                if delta.get("type") == "text_delta":
                    chunks.append(delta.get("text", ""))
            elif evt.get("type") == "error":
                raise LLMError(f"Anthropic 流错误：{evt.get('error')}")
    return "".join(chunks)


_PROVIDERS = {
    "deepseek": _call_deepseek,
    "deepseek-official": _call_deepseek_official,
    "claude": _call_claude,
    "gpt": _call_gpt,
}

# provider → 读取 key 的环境变量前缀（"未配置就跳过" 的判断依据）。
_PROVIDER_KEY_PREFIX = {
    "deepseek": "DEEPSEEK",
    "deepseek-official": "DEEPSEEK_OFFICIAL",
    "claude": "ANTHROPIC",
    "gpt": "GPT",
}

# .env.example 里的占位符：视同没填，免得拿假 key 打一次必然 401 的请求。
_PLACEHOLDER = re.compile(r"replace[-_]?me|your[-_]?key", re.IGNORECASE)


def _has_key(name: str) -> bool:
    value = _env(name)
    return bool(value) and not _PLACEHOLDER.search(value)


def provider_name() -> str:
    return _env("LLM_PROVIDER", "deepseek").lower()


def provider_chain() -> list[str]:
    """容灾链：LLM_PROVIDERS（逗号分隔，按顺序降级）优先，否则退化为单个 LLM_PROVIDER。"""
    raw = _env("LLM_PROVIDERS")
    chain = [p.strip().lower() for p in raw.split(",") if p.strip()] if raw else []
    return chain or [provider_name()]


def provider_configured(provider: str) -> bool:
    """该 provider 的 key 是否已就绪（链上没配 key 的会被跳过，而不是报错中断）。"""
    p = (provider or "").lower()
    if p == "gpt":
        # RightAPI 的 Claude/Codex 上游可共用同一把 key。
        return _has_key("GPT_API_KEY") or _has_key("ANTHROPIC_API_KEY")
    prefix = _PROVIDER_KEY_PREFIX.get(p)
    return bool(prefix) and _has_key(f"{prefix}_API_KEY")


def _base_gateway() -> str:
    """主 DeepSeek 端点的简称：交大网关 → sjtu，官方 → official，其它中转站 → 主机名。"""
    host = re.sub(r"^https?://", "", _env("DEEPSEEK_API_BASE", "https://api.deepseek.com"))
    host = host.split("/")[0].split(":")[0].lower()
    if not host:
        return "unknown"
    if "sjtu" in host:
        return "sjtu"
    if "deepseek" in host:
        return "official"
    return host


def provider_label(provider: str) -> str:
    """provider + 模型名 + 实际端点，用于日志和 digest 采集说明（如 deepseek@sjtu:deepseek-chat）。"""
    p = (provider or "").lower()
    if p == "deepseek":
        return f"deepseek@{_base_gateway()}:{_env('DEEPSEEK_MODEL', 'deepseek-chat')}"
    if p == "deepseek-official":
        return f"deepseek@official:{_env('DEEPSEEK_OFFICIAL_MODEL', 'deepseek-flash')}"
    if p == "claude":
        return f"claude:{_env('ANTHROPIC_MODEL', 'claude-opus-4-8')}"
    if p == "gpt":
        return f"gpt:{_env('GPT_MODEL', '未配置')}"
    return p or "unknown"


def model_label() -> str:
    return provider_label(provider_name())


def chat_json(system: str, user: str, providers: list[str] | None = None) -> dict:
    """按 provider 链调用，返回首个成功解析的严格 JSON（失败重试、逐个降级）。

    - providers 默认取 LLM_PROVIDERS 容灾链；显式传入（如 --provider）则只走该名单。
    - 链上没配 key 的 provider 直接跳过并提示，不当成错误。
    - 重试是**轮转**的：每轮把链上每个可用 provider 各试一次，所以主用端挂了最多等
      一个 LLM_TIMEOUT 就切到备用端，而短暂抖动还能靠后面的轮次救回来。
    - 成功后把该 provider 写回 LLM_PROVIDER，让 model_label() 标注真正的产出方。
    """
    chain = [p.strip().lower() for p in (providers or provider_chain()) if p and p.strip()]
    timeout = int(_env("LLM_TIMEOUT", "300") or "300")
    attempts = max(1, int(_env("LLM_MAX_ATTEMPTS", "3") or "3"))
    notes: list[str] = []
    usable: list[str] = []
    for p in chain:
        if p not in _PROVIDERS:
            notes.append(f"{p}: 未知 provider")
        elif not provider_configured(p):
            notes.append(f"{p}: 未配置 API key")
            print(f"⚠ provider {p} 未在 .env 里填 key，跳过。")
        else:
            usable.append(p)
    if not usable:
        raise LLMError("没有可用的 LLM provider（" + ("；".join(notes) or "链为空") + "）")

    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        for provider in usable:
            try:
                data = _extract_json(_PROVIDERS[provider](system, user, timeout))
            except (urllib.error.URLError, urllib.error.HTTPError, LLMError,
                    json.JSONDecodeError, KeyError, TimeoutError) as e:
                last_err = e
                print(f"✗ {provider_label(provider)} 第 {i}/{attempts} 轮失败："
                      f"{type(e).__name__}: {e}")
                continue
            os.environ["LLM_PROVIDER"] = provider
            return data
        if i < attempts:
            time.sleep(min(2 ** i, 20))  # 指数退避
    tail = f"；链上其它问题：{'；'.join(notes)}" if notes else ""
    raise LLMError(f"所有 provider 均失败（{attempts} 轮）："
                   f"{type(last_err).__name__}: {last_err}{tail}")
