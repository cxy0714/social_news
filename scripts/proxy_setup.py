"""Route RSS fetching through a local proxy for GFW-blocked sources.

Western RSS feeds (BBC, NYT, CBC, WaPo, Guardian, SCMP, ...) fail from the
campus network with TLS-handshake timeouts / `SSL: UNEXPECTED_EOF_WHILE_READING`
when reached directly. We funnel traffic through the local Clash proxy (default
127.0.0.1:7897) by exporting the standard proxy env vars, which urllib (used by
fetch_news / llm_client) honours automatically — no call site changes needed.

Hosts that must stay DIRECT are in NO_PROXY: the SJTU LLM gateway, the Claude
relay www.right.codes (proxying it actually breaks — it times out via Clash),
DeepSeek, and any *.cn source. Domestic RSS (人民网/中新网) are *.cn/*.com.cn
and covered by the .cn suffix + explicit hosts below.

Override via .env (all optional):
    PROXY_URL=http://127.0.0.1:7897   # empty string disables proxying
    NO_PROXY_EXTRA=host1,host2        # extra direct-connect hosts (appended)
"""
from __future__ import annotations

import os

_DEFAULT_PROXY = "http://127.0.0.1:7897"
_DEFAULT_NO_PROXY = [
    "localhost", "127.0.0.1", "::1",
    "models.sjtu.edu.cn",   # SJTU LLM gateway (domestic)
    "www.right.codes",  
    "www.rightapi.ai",  # Claude relay — direct only, breaks via proxy
    "api.deepseek.com",     # DeepSeek official
    ".cn",                  # domestic RSS (people.com.cn, chinanews.com.cn)
]


def setup_proxy() -> None:
    """Idempotently export proxy env vars from PROXY_URL (default Clash).

    Loads .env first (so a PROXY_URL/NO_PROXY_EXTRA override is honoured even
    when fetch_news.py runs standalone). load_dotenv never overwrites an env
    var that's already set, and the proxy vars use setdefault below, so calling
    this more than once is safe.
    """
    try:
        from llm_client import load_dotenv
        load_dotenv()
    except Exception:  # noqa: BLE001 — .env is optional; defaults suffice
        pass

    proxy = os.environ.get("PROXY_URL", _DEFAULT_PROXY).strip()
    if not proxy:
        return

    no_proxy = list(_DEFAULT_NO_PROXY)
    extra = os.environ.get("NO_PROXY_EXTRA", "").strip()
    if extra:
        no_proxy += [h.strip() for h in extra.split(",") if h.strip()]
    no_proxy_str = ",".join(no_proxy)

    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        os.environ.setdefault(key, proxy)
        os.environ.setdefault(key.lower(), proxy)
    os.environ["NO_PROXY"] = no_proxy_str
    os.environ["no_proxy"] = no_proxy_str
