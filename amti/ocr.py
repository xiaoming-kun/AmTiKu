#!/usr/bin/env python3
r"""OCR 后端：一张图 → 文字（dots.ocr，跑在 llama.cpp 上）。

**只干这一件事**：把图片发给 OCR 模型、拿回文字。不认识"试卷""题目""答案"
这些概念——那是 `record2.py`（切题/配对）和 `pagegeom.py`（页面几何）的活。

为什么单独一个模块：
* 后端会换（PaddleOCR-VL → dots.ocr → 以后别的），**换后端不该动业务代码**；
* 这里有两个**必须集中管**的坑：图像 token 预算、服务健康检查。

## 换后端时要改什么

只有 `MODEL` / `API` / `_BODY` / `HEALTH` 四处。业务侧只调 `ocr_image()`。

## 两个坑（都真踩过）

1. **图太大 → 服务端 400**。实测横版半页 440 万像素 = 10419 个图像 token，
   而 llama-server 按 `-np 2` 分槽，单槽只有 8192 → 直接
   `request (10419 tokens) exceeds the available context size`。
   所以**一律先 `record.shrink()` 压到 200 万像素再发**。
2. **服务没起就发** → 连接被拒，批量跑一晚上全是空产物。
   `alive()` 先探活，调用方**必须先查**（`record2` 里就是这么做的）。
"""
from __future__ import annotations

import base64
import json
import time
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:1236/v1/chat/completions"
HEALTH = "http://127.0.0.1:1236/health"
MODEL = "dots.ocr"
MAX_PIXELS = 2_000_000
TIMEOUT = 900

_PROMPT = "Extract the text content from this image."


def alive(timeout: int = 5) -> bool:
    """OCR 服务通不通。**批量跑之前一定要查**——不通就整晚白跑。"""
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout) as r:
            return r.status == 200
    except Exception:                                      # noqa: BLE001
        return False


def _body(img_b64: str, maxtok: int) -> bytes:
    return json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": _PROMPT},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + img_b64}}]}],
        "temperature": 0.0, "max_tokens": maxtok}).encode()


def ocr_image(img: Path, *, maxtok: int = 6000, retry: int = 2,
              shrink_to: int = MAX_PIXELS) -> str:
    r"""一张图 → 文字。失败重试（本地服务偶发抽风，**别让一页拖垮整场**）。

    ⚠️ 失败时返回 `"[OCR失败 …]"` 而不是抛异常：一页坏了要能继续跑完，
    坏页在产物里看得见（`record2` 会把带这个标记的页报成"失败页"）。
    """
    from . import record as R                    # 局部导入，避免模块循环
    img = R.shrink(img, max_px=shrink_to)
    b64 = base64.b64encode(img.read_bytes()).decode()
    body = _body(b64, maxtok)
    last = ""
    for k in range(retry + 1):
        try:
            req = urllib.request.Request(
                API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                d = json.loads(r.read().decode())
            return (d["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:                              # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, e)
            if k < retry:
                time.sleep(1.5)
    return "[OCR失败 %s]" % last


def _selftest() -> int:
    """只测纯函数（不发请求）。**服务相关的行为由 `record2` 的端到端用例覆盖。**"""
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("ocr 自检")
    b = json.loads(_body("QUJD", 1234).decode())
    check("请求体是 OpenAI 兼容格式", b["messages"][0]["content"][1]["type"] == "image_url")
    check("图像走 data URI", b["messages"][0]["content"][1]["image_url"]["url"]
          .startswith("data:image/png;base64,"), b["messages"][0]["content"][1])
    check("max_tokens 传下去了", b["max_tokens"] == 1234)
    check("温度 0（可复现）", b["temperature"] == 0.0)
    check("模型名配的是 dots.ocr", MODEL == "dots.ocr", MODEL)
    check("像素预算 ≤ 200 万", MAX_PIXELS <= 2_000_000, str(MAX_PIXELS))

    print("ocr 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
