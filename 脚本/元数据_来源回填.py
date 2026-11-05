#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""答案/解析来源回填：把“没记来源”变成显式的 `legacy`。

现状（2026-11-03）：29,276 道里 25,348 道没有 `answer_source`、24,360 道没有
`solution_source`。缺字段不等于答案错，但它让“这道题的答案是人定的、模型算的、
还是从原卷抄的”无法回答，也没法按可信度抽检。

这个脚本**只补 meta，不动正文**：
  · 缺 `answer_source`    → `legacy`（历史存量，来源未登记）
  · 缺 `solution_source`  → `legacy`
  · 有 `difficulty` 但缺 `difficulty_source` → `human`（当年是人工/规则定的）

为什么不猜成“原卷答案”：高考真题里也有后来人工改过的（`fixed_at`），
统一写“原卷”是**伪造凭据**；`legacy` 至少诚实，筛选时能一眼挑出来复核。

用法：
    python3 脚本/元数据_来源回填.py          # 干跑
    python3 脚本/元数据_来源回填.py --apply  # 落盘（一次整库写回）
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store  # noqa: E402


def fill(qs):
    n = Counter()
    for q in qs:
        if "answer_source" not in q.meta:
            q.meta["answer_source"] = "legacy"
            n["answer_source"] += 1
        if "solution_source" not in q.meta:
            q.meta["solution_source"] = "legacy"
            n["solution_source"] += 1
        if q.meta.get("difficulty") and "difficulty_source" not in q.meta:
            q.meta["difficulty_source"] = "human"
            n["difficulty_source"] += 1
        # 人改过答案/解析的，视为已复核；时间用当时的 edited_at。
        # 没有 edited_at 的老数据用一个明确的迁移日，不冒充“今天”。
        if (q.meta.get("answer_source") == "human"
                and not q.meta.get("reviewed_at")):
            q.meta["reviewed_at"] = q.meta.get("edited_at") or "2026-11-03"
            n["reviewed_at"] += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    qs, sig = store.load_for_update()
    before = Counter(q.content_hash() for q in qs)
    n = fill(qs)
    after = Counter(q.content_hash() for q in qs)
    if before != after:
        raise SystemExit("内容指纹变了——这个脚本只能改 meta，已中止")
    print("将补：%s" % "、".join("%s %d 道" % (k, v) for k, v in n.items()))
    if not a.apply:
        print("\n干跑结束；加 --apply 落盘。")
        return 0
    rep = store.rewrite_all(qs, based_on=sig)
    print("已写回：%d 卷 / %d 道" % (rep["volumes"], rep["count"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
