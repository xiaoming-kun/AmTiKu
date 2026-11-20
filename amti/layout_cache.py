"""AmMath · **跨页题档案**（派生的排版缓存）

一次导出里，如果某道题被分页拆成两页，排版器会给它"从新页开始"的强制断页
（见 `paper` 的 `force_newpage`）。这个信息对**同一道题**是可复用的：
下次再组进卷子，直接按档案预先断页，省掉一遍"先编出来看看"的探测编译。

缓存是**派生数据**：删了只会多跑一遍编译，不影响任何题目/PDF。
按 `layout.VERSION` 失效——排版参数一改，旧档案里的"会跨页"就未必成立了。

位置：`数据/缓存/排版档案.json`（和 content.sqlite 一样在缓存目录里）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import layout as L

from .paths import ROOT as _ROOT

# 和 `content_store` 同一套：**数据目录**下的 `数据/缓存/`（打包后跟着 exe 走）
FILE = Path(_ROOT) / "数据" / "缓存" / "排版档案.json"


def _load() -> dict:
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("v") == L.VERSION:
            return d
    except (OSError, ValueError):
        pass
    return {"v": L.VERSION, "split": {}}


def profile(mode: str) -> str:
    """档案分档：卷型不同，同样的题排版结果也不同。"""
    return "%s/v%d" % (mode, L.VERSION)


def known_splitters(keys: list[str], mode: str) -> set[str]:
    r"""这些题里**已知会跨页**的（当前卷型 + 当前排版参数下）。"""
    d = _load()
    tag = profile(mode)
    out = set()
    for k in keys:
        rec = d["split"].get(k)
        if rec and rec.get("profile") == tag:
            out.add(k)
    return out


def mark_splitters(keys: list[str], mode: str) -> int:
    """记下"这些题在这套参数下会跨页"。返回新增条数。"""
    if not keys:
        return 0
    d = _load()
    tag = profile(mode)
    now = time.strftime("%Y-%m-%d %H:%M")
    n = 0
    for k in keys:
        rec = d["split"].setdefault(k, {})
        if rec.get("profile") != tag:
            n += 1
        rec.update({"profile": tag, "at": now})
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf-8")
        tmp.replace(FILE)
    except OSError:
        return 0                     # 缓存写不进去不影响出卷子
    return n


def forget(keys: list[str]) -> int:
    """把题从档案里去掉（改排版 / 人工纠错时用）。"""
    d = _load()
    n = 0
    for k in keys:
        if d["split"].pop(k, None) is not None:
            n += 1
    if n:
        try:
            FILE.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")
        except OSError:
            pass
    return n


def status() -> dict:
    """体检用：档案多少条、多少题、什么时候写的。"""
    d = _load()
    ats = [r.get("at") for r in d["split"].values() if r.get("at")]
    try:
        size = FILE.stat().st_size
    except OSError:
        size = 0
    return {"file": str(FILE), "exists": FILE.exists(), "v": d.get("v"),
            "n": len(d["split"]), "bytes": size,
            "latest": max(ats) if ats else None}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        try:
            FILE.unlink()
        except OSError:
            pass
        print("已清空排版档案")
    else:
        print(status())
