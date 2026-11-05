r"""题库格式规范：给大模型看的**唯一一份**规则文本。

来源按优先级：
  1. `设计/题目规范.md`（内部完整版，本机有就用它）
  2. `docs/题目格式.md`（公开版，随仓库走）

两个都读不到就返回空串——调用方据此决定"不做规范化"，
而不是拿一份残缺的规则去让模型瞎改。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CANDIDATES = [ROOT / "设计" / "题目规范.md", ROOT / "docs" / "题目格式.md"]
_cache: str | None = None
_source: str = ""


def text() -> str:
    global _cache, _source
    if _cache is not None:
        return _cache
    for p in _CANDIDATES:
        if p.is_file():
            try:
                _cache = p.read_text(encoding="utf-8").strip()
                _source = str(p.relative_to(ROOT))
                return _cache
            except Exception:                                 # noqa: BLE001
                continue
    _cache = ""
    return _cache


def source() -> str:
    text()
    return _source
