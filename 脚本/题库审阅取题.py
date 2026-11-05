#!/usr/bin/env python3
r"""逐题审阅 · 取题切片（给并行审阅用，只读不改）。

    python3 脚本/题库审阅取题.py --sim --start 0 --count 40

`--sim` 只走模拟题（错误密度高，先啃）；`--start/--count` 是**过滤后**的下标，
所以多路并行时各段互不重叠。已经审过的题按 `逐题进度.json` 自动跳过，
因此重跑、续跑都不会重复。

输出是给人（或大模型）读的紧凑文本，不是机器格式——审阅者要**自己算一遍**再判。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store                                   # noqa: E402
from amti.paths import ROOT as RROOT                     # noqa: E402

CURSOR = RROOT / "数据" / "题库审阅" / "逐题进度.json"


def pool(sim_only: bool = False, skip_done: bool = True):
    done = set()
    if skip_done and CURSOR.exists():
        done = set(json.loads(CURSOR.read_text(encoding="utf-8")).get("判定", {}))
    out = []
    for q in store.load_cached():
        if sim_only and not q.key.startswith("模拟题/"):
            continue
        if q.key in done:
            continue
        out.append(q)
    return out


def dump(q, cap_sol=1400) -> str:
    def flat(s, n):
        s = re.sub(r"\s+", " ", s or "").strip()
        return s if len(s) <= n else s[:n] + "…"
    lines = [f"◆ {q.key}",
             f"  题型={q.type} 答案={q.answer!r} 考点={q.points} "
             f"自带难度={q.meta.get('difficulty') or '—'}"]
    lines.append("  题干: " + flat(q.stem, 700))
    if q.options:
        lines.append("  选项: " + " ｜ ".join(f"{o.label}. {flat(o.text, 60)}"
                                             for o in q.options))
    if q.figures:
        lines.append(f"  配图: {len(q.figures)} 张")
    lines.append("  解析: " + (flat(q.solution, cap_sol) or "（解析无）"))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="只走模拟题")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--list-count", action="store_true", help="只报可审总数")
    a = ap.parse_args()
    ps = pool(a.sim)
    if a.list_count:
        print(len(ps))
        return 0
    for q in ps[a.start:a.start + a.count]:
        print(dump(q), "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
