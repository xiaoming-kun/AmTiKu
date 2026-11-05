r"""normalize 规则干跑比对 —— 落盘前先看**影响面**和**护栏**。

    python3 脚本/规则干跑.py 去解析开头的答案册卷首块
    python3 脚本/规则干跑.py 全部 --样 12

护栏（任何一条报警都要人读过才敢 --yes）：
  作答位   `\fillin`／`\paren` 的个数变了        → 答案载体被动过
  清空     非空字段被改成空
  配对     `$` 奇偶、花括号／`\begin` 差值变了   → 公式被吞
  大段     单字段一次删掉超过 300 字
  选项     选项数量或对原文的删改超出预期
"""
from __future__ import annotations

import argparse
import copy
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amti import normalize as N, store

FIELDS = ("stem", "answer", "solution")


def snap(q):
    d = {f: getattr(q, f) or "" for f in FIELDS}
    d["opts"] = [o.text for o in q.options]
    return d


def pair_delta(t):
    # `$` 只看**奇偶**（成对删掉一段公式是正常改动，数量变化不该报警）
    return (t.count("$") % 2, t.count("{") - t.count("}"),
            t.count("\\begin{") - t.count("\\end{"))


def run(names, samples=6, show_all=False):
    qs = store.load_all()
    rules = [N.get(n) for n in names]
    missing = [n for n, r in zip(names, rules) if r is None]
    if missing:
        print("找不到规则：%s" % "、".join(missing))
        return 2
    hits, guards = [], []
    for q in qs:
        p = copy.deepcopy(q)
        fired = [r.fn(p) for r in rules]
        if not any(fired):
            continue
        hits.append((q, p))
        a, b = snap(q), snap(p)
        for f in FIELDS:
            if a[f] == b[f]:
                continue
            if a[f].count("\\fillin") != b[f].count("\\fillin") or \
               a[f].count("\\paren") != b[f].count("\\paren"):
                guards.append(("作答位", q.key, f))
            if b[f].strip() == "" and a[f].strip():
                guards.append(("清空", q.key, f, a[f][:60]))
            if pair_delta(a[f]) != pair_delta(b[f]):
                guards.append(("配对", q.key, f, pair_delta(a[f]), pair_delta(b[f])))
            if len(a[f]) - len(b[f]) > 300:
                guards.append(("大段-%d" % (len(a[f]) - len(b[f])), q.key, f))
        if len(a["opts"]) != len(b["opts"]):
            guards.append(("选项数", q.key))
        for i, (x, y) in enumerate(zip(a["opts"], b["opts"])):
            if x == y:
                continue
            if x.count("$") != y.count("$"):
                guards.append(("选项$", q.key, i))
            if y.strip() == "" and x.strip():
                guards.append(("选项清空", q.key, i))

    print("影响 %d / %d 道" % (len(hits), len(qs)))
    print("护栏告警 %d 条" % len(guards))
    for g in guards[:40]:
        print("   !", g)
    empty_after = sum(1 for _a, b in hits if (b.solution or "").strip() in ("解析无", ""))
    if empty_after:
        print("   注：改动后解析变成占位/空的 %d 道" % empty_after)

    show = hits if show_all else hits[:samples]
    for a, b in show:
        sa, sb = snap(a), snap(b)
        print("=" * 96)
        print(a.key)
        for f in FIELDS:
            if sa[f] != sb[f]:
                print("  --%s 前: %s" % (f, sa[f][:240].replace("\n", "⏎")))
                print("     %s 后: %s" % (f, sb[f][:240].replace("\n", "⏎") or "（空）"))
        for i, (x, y) in enumerate(zip(sa["opts"], sb["opts"])):
            if x != y:
                print("  --opt%s 前: %r" % ("ABCD"[i], x[:120]))
                print("        后: %r" % y[:120])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rules", nargs="+")
    ap.add_argument("--样", type=int, default=6)
    ap.add_argument("--全", action="store_true")
    a = ap.parse_args()
    if a.rules == ["全部"]:
        names = [r.name for r in N.RULES if r.scope == N.MIGRATE]
    else:
        names = a.rules
    return run(names, a.样, a.全)


if __name__ == "__main__":
    raise SystemExit(main())
