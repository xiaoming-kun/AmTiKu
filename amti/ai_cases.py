r"""AI 失败案例库：错误类型 + 错版 + 修好后的版本。

- 只存本地，不入题库；
- 用于「相似失败」检索和回归，不把全部历史喂给模型；
- 没有修好版本的失败也存，但 resolved=false，不能当正例。
"""
from __future__ import annotations

import json
import re
import threading
import time

from .paths import ROOT

PATH = ROOT / "数据" / "AI失败案例.jsonl"
_LOCK = threading.Lock()


def _types(errors: list[str]) -> list[str]:
    out = []
    for e in errors or []:
        s = str(e).strip()
        if not s:
            continue
        # 取冒号前的检查名；没有就取前 24 字
        t = re.split(r"[：:]", s, maxsplit=1)[0].strip()[:24]
        if t and t not in out:
            out.append(t)
    return out[:8]


def record(*, kind: str, errors: list[str], wrong: str, fixed: str,
           resolved: bool, source_no: str = "", note: str = "") -> None:
    row = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": kind, "source_no": source_no,
        "error_types": _types(errors),
        "errors": [str(x)[:300] for x in (errors or [])[:12]],
        "wrong": str(wrong or "")[:6000],
        "fixed": str(fixed or "")[:6000],
        "resolved": bool(resolved), "note": str(note or "")[:300],
    }
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load(limit: int = 5000) -> list[dict]:
    if not PATH.is_file():
        return []
    out = []
    try:
        for line in PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def search(tex: str, errors: list[str], limit: int = 2) -> list[dict]:
    """只取 resolved 的同类案例；按错误类型命中 + 题面关键词重合排序。"""
    want = set(_types(errors))
    q = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_]{3,}", str(tex or ""))[:400])
    scored = []
    for c in _load():
        if not c.get("resolved") or not c.get("fixed"):
            continue
        hit = len(want & set(c.get("error_types") or []))
        words = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_]{3,}",
                               str(c.get("wrong") or ""))[:400])
        overlap = len(q & words)
        if hit or overlap >= 3:
            scored.append((hit * 10 + min(overlap, 12), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max(0, min(5, limit))]]


def stats() -> dict:
    rows = _load()
    return {"total": len(rows),
            "resolved": sum(1 for r in rows if r.get("resolved")),
            "unresolved": sum(1 for r in rows if not r.get("resolved"))}
