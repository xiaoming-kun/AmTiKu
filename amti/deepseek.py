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
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from amti.logutil import get_logger

from .paths import ROOT

log = get_logger(__name__)

#: 配置落盘位置。和 `数据/` 下其它运行时文件放在一起。
CFG_PATH = ROOT / "数据" / "AI设置.json"
#: 每次 DeepSeek 调用的用量流水；给「录入」首页显示今日/累计花费。
USAGE_PATH = ROOT / "数据" / "AI用量.jsonl"
_USAGE_LOCK = threading.Lock()

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


def record_usage(usage: dict, model: str = "") -> None:
    """把一次调用的 token/估算费用追加到本地流水。失败绝不影响主请求。"""
    u = usage or {}
    if not u:
        return
    model = model or load()["model"]
    row = {
        "ts": int(time.time()),
        "date": time.strftime("%Y-%m-%d"),
        "model": model,
        "prompt_tokens": int(u.get("prompt_tokens") or 0),
        "completion_tokens": int(u.get("completion_tokens") or 0),
        "total_tokens": int(u.get("total_tokens") or 0),
        "cost_cny": cost_cny(model, u),
    }
    try:
        with _USAGE_LOCK:
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            with USAGE_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:                    # 记账失败不影响调用，但必须留痕
        log.warning("AI 用量流水写失败（本次调用照常计费）：%s", e)


def usage_summary() -> dict:
    """今日 / 累计的 token 与估算费用。只读本地流水。"""
    today = time.strftime("%Y-%m-%d")
    out = {
        "ok": True, "date": today, "model": load()["model"],
        "today": {"cost_cny": 0.0, "tokens": 0, "calls": 0},
        "total": {"cost_cny": 0.0, "tokens": 0, "calls": 0},
        "since": "", "unit": "CNY",
        "note": "估算价，以 DeepSeek 控制台账单为准；从本地流水启用后开始累计",
    }
    try:
        if not USAGE_PATH.is_file():
            return out
        with USAGE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                tok = int(r.get("total_tokens") or 0)
                cost = float(r.get("cost_cny") or 0)
                out["total"]["tokens"] += tok
                out["total"]["cost_cny"] += cost
                out["total"]["calls"] += 1
                if str(r.get("date") or "") == today:
                    out["today"]["tokens"] += tok
                    out["today"]["cost_cny"] += cost
                    out["today"]["calls"] += 1
                if not out["since"]:
                    out["since"] = str(r.get("date") or "")
    except OSError as e:                    # 读不到就当空账，但别装没事
        log.warning("AI 用量流水读失败，本次按空账显示：%s", e)
    out["total"]["cost_cny"] = round(out["total"]["cost_cny"], 4)
    out["today"]["cost_cny"] = round(out["today"]["cost_cny"], 4)
    return out


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


_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def json_obj(raw: str) -> dict:
    """模型返回的 JSON → dict；容忍 ```json 围栏和前后解释。

    `json_mode=True` 不保证只回 JSON，所以先剥围栏，再退一步抓第一个大括号块。
    各 AI 模块原来各抄一份，改这里一处即可。
    """
    s = _FENCE.sub("", str(raw or "").strip()).strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except ValueError:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return {}
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}


def chat_messages(messages: list[dict], images: list[bytes] | None = None, *,
                  timeout: float = 240, max_tokens: int = 32000,
                  json_mode: bool = False, on_usage=None) -> str:
    """按完整 messages 调一次模型；图片附到最后一条 user 消息。

    这是持久会话的底层：调用方负责保存/恢复 messages，本函数不猜历史。
    """
    cfg = load()
    if not cfg["api_key"]:
        raise AIError("还没填 API Key —— 点「DeepSeek 录题」里的设置，填一次就行")
    msgs: list[dict] = [dict(m) for m in (messages or [])]
    if not msgs:
        raise AIError("messages 为空")
    if images:
        imgs = []
        for raw in images:
            if not raw:
                continue
            import base64
            b64 = base64.b64encode(raw).decode("ascii")
            imgs.append({"type": "image_url",
                         "image_url": {"url": "data:image/png;base64," + b64,
                                       "detail": "original"}})
        if imgs:
            # 图片只能放 user 消息；附到最后一条 user 上。
            idx = next((i for i in range(len(msgs) - 1, -1, -1)
                        if msgs[i].get("role") == "user"), -1)
            if idx < 0:
                msgs.append({"role": "user", "content": imgs})
            else:
                old = msgs[idx].get("content")
                if isinstance(old, list):
                    msgs[idx]["content"] = old + imgs
                else:
                    msgs[idx]["content"] = [{"type": "text", "text": str(old or "")}] + imgs
    payload = {
        "model": cfg["model"], "messages": msgs, "temperature": 0,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"}, "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        data = _post(cfg, payload, timeout=timeout)
    except AIError as e:
        msg = str(e)
        if not any(k in msg for k in ("max_tokens", "temperature", "thinking",
                                      "response_format", "请求被拒绝")):
            raise
        for k in ("max_tokens", "temperature", "thinking", "response_format"):
            payload.pop(k, None)
        data = _post(cfg, payload, timeout=timeout)
    ch = (data.get("choices") or [{}])[0]
    usage = data.get("usage") or {}
    if on_usage is not None and usage:
        try:
            on_usage(usage)
        except Exception as e:               # 回调是调用方的事，不能拖垮请求
            log.warning("on_usage 回调失败（费用已记流水，界面统计可能少一笔）：%s", e)
    if usage:
        record_usage(usage, cfg["model"])
    if str(ch.get("finish_reason") or "") == "length":
        raise AIError("这一批输出被截断了（max_tokens 用完）——把「每批页数」调小再试")
    return _content_of(data)


def chat(prompt: str, images: list[bytes] | None = None, *,
         system: str = "", timeout: float = 240, max_tokens: int = 32000,
         json_mode: bool = False, on_usage=None) -> str:
    """单轮便捷入口：内部转成 messages 后走 chat_messages。"""
    msgs: list[dict] = []
    if system.strip():
        msgs.append({"role": "system", "content": system.strip()})
    msgs.append({"role": "user", "content": prompt})
    return chat_messages(msgs, images, timeout=timeout, max_tokens=max_tokens,
                         json_mode=json_mode, on_usage=on_usage)

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
