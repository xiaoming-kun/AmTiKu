r"""DeepSeek 视觉接口：资料页图 → 结构化题目。

## 它只做一件事

**把页图读成题目，不写库。** 写库仍然只走 `amti/ingest.py` 那条唯一入口
（AGENTS.md 第三节）；这里连 `store` 都不 import。

## 为什么 key 存在本地明文里

`数据/AI设置.json`，`chmod 600`，跟 `删题口令.txt` 一个待遇。
这个项目是单机单人的：密钥就在用户自己电脑上，做加密也只是把钥匙
放在同一台机器上，除了让人误以为"很安全"没有任何收益。
真正的边界是**只监听 127.0.0.1 + Origin 白名单**（见 `web/server.py`），
以及**界面永远拿不回明文 key**（只回末四位）。

## 模型名为什么可配

DeepSeek 的文档里 `deepseek-v4-flash-vision-exp` 已经下线、请求转给
`deepseek-flash`。名字会被官方改，所以不写死在代码里；默认值给最新的，
改不动的时候用户自己能改。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .paths import ROOT

#: 配置落盘位置。和 `数据/` 下其它运行时文件放在一起。
CFG_PATH = ROOT / "数据" / "AI设置.json"

#: 默认值。`base_url` 不带 `/v1`（DeepSeek 两种都收，它以 `/chat/completions` 为准）。
DEFAULTS: dict = {
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-flash",
    "api_key": "",
    # 每次给模型几页。页数越多，单次越慢、输出越长越容易被截断。
    "pages_per_call": 6,
    # 并发几路。DeepSeek 不吃本地算力，2 路足以把 100 页压到几分钟。
    "workers": 2,
}

#: 单页渲染 dpi。150dpi 的 A4 ≈ 1.7MP，正好吃满 DeepSeek 的图片预算
#: （每张图约 1024 token、约 1300×1300 封顶）。再高也会被它压回去。
DEFAULT_DPI = 150

#: 估算费用用的单价（CNY / 1M tokens）。**以 DeepSeek 控制台为准**，
#: 只用于界面上那句「本次约 ¥x」，不是账单。模型改名/降价时改这里。
PRICES: dict[str, dict] = {
    "deepseek-flash": {"in": 0.5, "out": 2.0},
}


def cost_cny(model: str, usage: dict) -> float:
    """按 token 用量估算一次/一批调用的费用（元）。"""
    p = PRICES.get(model) or PRICES["deepseek-flash"]
    inp = int((usage or {}).get("prompt_tokens") or 0)
    out = int((usage or {}).get("completion_tokens") or 0)
    return round(inp / 1_000_000 * p["in"] + out / 1_000_000 * p["out"], 4)


class AIError(RuntimeError):
    """给人看的错误：`str(e)` 直接上界面。"""


def _env() -> dict:
    """环境变量覆盖（测试/高级用户）。不写盘，优先级最高。"""
    out: dict = {}
    key = os.environ.get("AMTIKU_DEEPSEEK_KEY", "").strip()
    base = os.environ.get("AMTIKU_DEEPSEEK_BASE_URL", "").strip()
    model = os.environ.get("AMTIKU_DEEPSEEK_MODEL", "").strip()
    if key:
        out["api_key"] = key
    if base:
        out["base_url"] = base
    if model:
        out["model"] = model
    return out


def load() -> dict:
    """读配置（默认值 + 文件 + 环境变量）。"""
    cfg = dict(DEFAULTS)
    try:
        if CFG_PATH.is_file():
            data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in DEFAULTS:
                    if k in data and data[k] not in (None, ""):
                        cfg[k] = data[k]
                # 空串也要能覆盖默认（比如用户清空 key）
                if "api_key" in data:
                    cfg["api_key"] = str(data.get("api_key") or "")
    except (OSError, ValueError):
        pass
    cfg.update(_env())
    cfg["base_url"] = str(cfg.get("base_url") or DEFAULTS["base_url"]).strip().rstrip("/")
    cfg["model"] = str(cfg.get("model") or DEFAULTS["model"]).strip()
    cfg["api_key"] = str(cfg.get("api_key") or "").strip()
    try:
        cfg["pages_per_call"] = max(1, min(12, int(cfg.get("pages_per_call") or 6)))
    except (TypeError, ValueError):
        cfg["pages_per_call"] = 6
    try:
        cfg["workers"] = max(1, min(4, int(cfg.get("workers") or 2)))
    except (TypeError, ValueError):
        cfg["workers"] = 2
    return cfg


def save(patch: dict) -> dict:
    """改配置。**只接白名单字段**，别把整个请求体写进文件。

    `api_key` 传空串 = 清空；传 `None` / 不传 = 不动。
    """
    cur = load()
    for k in ("base_url", "model", "pages_per_call", "workers"):
        if k in patch and patch[k] not in (None, ""):
            cur[k] = patch[k]
    if "api_key" in patch and patch["api_key"] is not None:
        cur["api_key"] = str(patch["api_key"]).strip()
    base = str(cur["base_url"]).strip().rstrip("/")
    if not (base.startswith("http://") or base.startswith("https://")):
        raise AIError("接口地址要以 http:// 或 https:// 开头")
    cfg = {
        "base_url": base,
        "model": str(cur["model"]).strip() or DEFAULTS["model"],
        "api_key": str(cur["api_key"]).strip(),
        "pages_per_call": int(cur["pages_per_call"]),
        "workers": int(cur["workers"]),
    }
    CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CFG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        CFG_PATH.chmod(0o600)          # 只有本用户可读；Windows 上是空操作
    except OSError:
        pass
    return load()


def mask(key: str) -> str:
    """只漏末四位。短 key 干脆一点不漏。"""
    k = (key or "").strip()
    if len(k) < 12:
        return "已保存" if k else ""
    return "…" + k[-4:]


def status() -> dict:
    """给界面看的**只读**状态：配没配、模型、地址、key 末四位。"""
    cfg = load()
    return {
        "configured": bool(cfg["api_key"]),
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "key_hint": mask(cfg["api_key"]),
        "pages_per_call": cfg["pages_per_call"],
        "workers": cfg["workers"],
        "cfg_path": str(CFG_PATH),
    }


# ── HTTP ──────────────────────────────────────────────────────────────

def _url(cfg: dict) -> str:
    base = cfg["base_url"].rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _err_text(e: urllib.error.HTTPError) -> str:
    """把 HTTP 错误翻译成"下一步该干什么"。"""
    try:
        body = e.read().decode("utf-8", "ignore")
    except Exception:                      # noqa: BLE001
        body = ""
    detail = ""
    try:
        j = json.loads(body)
        detail = str((j.get("error") or {}).get("message")
                     or j.get("message") or j.get("detail") or "")
    except ValueError:
        detail = body.strip()[:300]
    if e.code == 401:
        return "API Key 不对或已失效 —— 去 platform.deepseek.com 重新复制一个，再填一次"
    if e.code == 402:
        return "账户余额不足 —— 去 DeepSeek 控制台充值后再试（读题按 token 计费，几毛钱能读上百页）"
    if e.code == 429:
        return "请求太频繁被限流 —— 等十几秒再试（或把「并发」调成 1）"
    if e.code == 400:
        return "请求被拒绝：%s" % (detail or "模型名可能改了，去设置里核对")
    if e.code >= 500:
        return "DeepSeek 服务端暂时出错（%d）—— 过一会儿重试即可" % e.code
    return "调用失败（HTTP %d）：%s" % (e.code, detail or "没有更多信息")


def _post(cfg: dict, payload: dict, *, timeout: float = 240) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _url(cfg), data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
            "Accept": "application/json",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        raise AIError(_err_text(e)) from None
    except urllib.error.URLError as e:
        raise AIError("连不上 DeepSeek（%s）—— 检查网络/代理，或接口地址填错了"
                      % getattr(e, "reason", e)) from None
    except TimeoutError:
        raise AIError("等太久没响应（超过 %d 秒）—— 页数调少一点再试" % int(timeout)) from None
    try:
        return json.loads(raw)
    except ValueError:
        raise AIError("DeepSeek 返回的不是 JSON（前 200 字：%s）" % raw[:200]) from None


def _content_of(data: dict) -> str:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise AIError("返回里没有 choices：%s" % json.dumps(data, ensure_ascii=False)[:300]) from None
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):              # 少数情况下是分块
        return "".join(str(b.get("text") or "") for b in c if isinstance(b, dict))
    return "" if c is None else str(c)


def chat(prompt: str, images: list[bytes] | None = None, *,
         system: str = "", timeout: float = 240, max_tokens: int = 32000,
         json_mode: bool = False, on_usage=None) -> str:
    """一次调用。`images` 是 PNG/JPEG 的字节，按顺序放进同一条 user 消息。

    ## 一定是**非思考模式**（`thinking: disabled`）

    `deepseek-flash` 默认开思考，而且默认 `reasoning_effort=high`。实测一份
    答案册 2 页：思考烧掉 **7443** 个 token、最终只吐出 580 字，还常常把
    8192 的输出额度吃光 → 返回空内容，界面上表现成「模型没回 JSON：」。
    关掉思考后同一批 **2.5 秒**、289 token 就抄完了。抄录/结构化不需要推理，
    这条必须关。

    `json_mode=True` 时带 `response_format=json_object`：官方保证返回合法
    JSON（非 JSON 内容会被替换成空格）。代价是**必须**在提示词里明确要求 JSON。

    DeepSeek 的限制：图片只能出现在 user 消息里；每张图约 1024 token；
    `detail=original` 才能保住公式细节（`low` 会缩到 512×512，公式直接糊）。
    """
    cfg = load()
    if not cfg["api_key"]:
        raise AIError("还没填 API Key —— 点「AI 读资料」旁边的设置，填一次就行")
    blocks: list[dict] = [{"type": "text", "text": prompt}]
    for raw in (images or []):
        if not raw:
            continue
        import base64
        b64 = base64.b64encode(raw).decode("ascii")
        blocks.append({"type": "image_url",
                       "image_url": {"url": "data:image/png;base64," + b64,
                                     "detail": "original"}})
    messages: list[dict] = []
    if system.strip():
        messages.append({"role": "system", "content": system.strip()})
    messages.append({"role": "user", "content": blocks})
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        # 抄录不是推理：关思考，否则输出额度会被思维链吃光（见上面那段）
        "thinking": {"type": "disabled"},
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        data = _post(cfg, payload, timeout=timeout)
    except AIError as e:
        # 换了个兼容端点、或者官方改了参数名：去掉"可选"参数再试一次。
        msg = str(e)
        if not any(k in msg for k in ("max_tokens", "temperature", "thinking",
                                      "response_format", "请求被拒绝")):
            raise
        for k in ("max_tokens", "temperature", "thinking", "response_format"):
            payload.pop(k, None)
        data = _post(cfg, payload, timeout=timeout)
    ch = (data.get("choices") or [{}])[0]
    # **先记 usage 再判截断**：截断的那次调用也已经计费，不能漏记。
    usage = data.get("usage") or {}
    if on_usage is not None and usage:
        try:
            on_usage(usage)
        except Exception:                    # noqa: BLE001
            pass
    if str(ch.get("finish_reason") or "") == "length":
        raise AIError("这一批输出被截断了（max_tokens 用完）——把「每批页数」调小再试")
    return _content_of(data)


def check() -> dict:
    """连通性测试：一句话、零图片，测的是 key/地址/模型名三件事。"""
    t0 = time.time()
    cfg = load()
    if not cfg["api_key"]:
        raise AIError("还没填 API Key")
    text = chat("只回一个字：好", timeout=30, max_tokens=8).strip()
    return {"ok": True, "ms": int((time.time() - t0) * 1000),
            "model": cfg["model"], "reply": text[:20]}


def cfg_path() -> Path:
    return CFG_PATH
