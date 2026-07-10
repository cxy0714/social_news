#!/usr/bin/env python3
"""LLM provider 抽象层（零第三方依赖，仅标准库）。

一个环境变量 LLM_PROVIDER 切换整套后端：
- deepseek —— OpenAI 兼容的 /chat/completions（官方 api.deepseek.com 或交大网关）
- claude   —— Anthropic 官方 /v1/messages

对外只暴露一个函数：chat_json(system, user) -> dict。
它要求模型返回**严格 JSON**，解析失败会重试；两家 API 的差异都封在内部。

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


_PROVIDERS = {"deepseek": _call_deepseek, "claude": _call_claude}


def provider_name() -> str:
    return _env("LLM_PROVIDER", "deepseek").lower()


def model_label() -> str:
    """当前 provider + 模型名，用于日志和 digest 采集说明。"""
    p = provider_name()
    if p == "claude":
        return f"claude:{_env('ANTHROPIC_MODEL', 'claude-opus-4-8')}"
    return f"deepseek:{_env('DEEPSEEK_MODEL', 'deepseek-chat')}"


def chat_json(system: str, user: str) -> dict:
    """调用当前 provider，要求严格 JSON 输出，带超时与重试。"""
    provider = provider_name()
    call = _PROVIDERS.get(provider)
    if call is None:
        raise LLMError(f"未知 LLM_PROVIDER: {provider!r}（应为 deepseek 或 claude）")
    timeout = int(_env("LLM_TIMEOUT", "180") or "180")
    attempts = int(_env("LLM_MAX_ATTEMPTS", "3") or "3")
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return _extract_json(call(system, user, timeout))
        except (urllib.error.URLError, urllib.error.HTTPError, LLMError,
                json.JSONDecodeError, KeyError, TimeoutError) as e:
            last_err = e
            if i < attempts:
                time.sleep(min(2 ** i, 20))  # 指数退避
    raise LLMError(f"LLM 调用失败（{attempts} 次）：{type(last_err).__name__}: {last_err}")
