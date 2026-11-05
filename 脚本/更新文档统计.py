#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""README 的题库统计表：**从题库生成，不手写**。

手写数字的结局已经见过了：README 还停在 20,934 道，库里已经 29,276 道。
这个脚本只改 README「一、现在有什么」那张表里的 6 行，别的一概不动。

用法（仓库根目录）：

    python3 脚本/更新文档统计.py          # 改写 README
    python3 脚本/更新文档统计.py --check  # 只检查，不一致就退出码 1

`--check` 可以挂进发版流程；日常改完题库顺手跑一下，别让数字漂。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store  # noqa: E402

README = ROOT / "README.md"

#: 表里的行首标签 → 生成函数。顺序无关，按标签找行。
ROWS = ("题目", "年代", "答案", "解析", "配图", "考点")


def _pct(n: int, total: int) -> str:
    if total and n == total:
        return "100%"
    return f"{100.0 * n / total:.1f}%" if total else "0%"


def collect() -> dict[str, str]:
    qs = store.load_all()
    total = len(qs)
    gaokao = sum(1 for q in qs if q.kind == "高考")
    moni = total - gaokao
    years = [q.meta.get("year") for q in qs
             if isinstance(q.meta.get("year"), int)]
    figs = sum(1 for q in qs if q.figures)
    ans = sum(1 for q in qs if (q.answer or "").strip())
    sol = sum(1 for q in qs if q.has_solution)
    points = len({p for q in qs for p in q.points})
    lo, hi = (min(years), max(years)) if years else ("?", "?")
    return {
        "题目": f"| 题目 | {total:,} 道（高考真题汇编 {gaokao:,} · 模拟题 {moni:,}） |",
        "年代": f"| 年代 | {lo}–{hi} |",
        "答案": f"| 答案 | **{ans:,} 道（{_pct(ans, total)}）** |",
        "解析": f"| 解析 | {sol:,} 道（{_pct(sol, total)}） |",
        "配图": f"| 配图 | {figs:,} 道有图 |",
        "考点": f"| 考点 | {points} 个考点（课标体系，见 `demo数据/知识点.json`） |",
    }


def rewrite(text: str, rows: dict[str, str]) -> tuple[str, list[str]]:
    """只替换「| 标签 | … |」整行。返回 (新文本, 变化说明)。"""
    changes: list[str] = []
    for label in ROWS:
        pat = re.compile(r"^\| %s \|.*$" % re.escape(label), re.M)
        m = pat.search(text)
        if not m:
            raise SystemExit(f"README 里找不到「| {label} |」这一行，先手工补上表头")
        if m.group(0) != rows[label]:
            changes.append(f"{label}: {m.group(0)}  →  {rows[label]}")
            text = text[:m.start()] + rows[label] + text[m.end():]
    return text, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只检查，不改文件；不一致退出码 1")
    a = ap.parse_args()
    rows = collect()
    old = README.read_text(encoding="utf-8")
    new, changes = rewrite(old, rows)
    if a.check:
        if changes:
            print("README 统计与题库不一致：")
            for c in changes:
                print("  " + c)
            print("\n跑 `python3 脚本/更新文档统计.py` 更新。")
            return 1
        print("README 统计与题库一致 ✓")
        return 0
    if not changes:
        print("README 统计已是最新 ✓")
        return 0
    README.write_text(new, encoding="utf-8")
    print("已更新 README：")
    for c in changes:
        print("  " + c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
