#!/usr/bin/env python3
"""补录一批已入库题目的「出处/年份」（只改 meta，不动正文/考点/答案）。

背景：2026-11-03 多题录入学 v1.7.13 引入逐题 label 后，界面单卷会给每张卡
发 `label: '' / year: ''`；旧后端把空串当“明确清空”，把左栏全局出处 pop 掉了。
已在 v1.7.13 修复；这个脚本用于修复**修复前已经落库**的那几批。

用法：
    # 先看会改哪些（默认 dry-run）
    python3 脚本/补录出处.py --region 湖北 --label "2026届湖北……质量检测" --year 2026
    # 确认后加 --apply
    python3 脚本/补录出处.py --region 湖北 --label "…" --year 2026 --apply

只选 `book` 匹配、`region` 匹配、**source_label 为空**的题；不动 key，
所以旧 key 里的 `录入` 仍在，但界面/导出显示的出处会用新 meta。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="2026精选模拟题")
    ap.add_argument("--region", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--apply", action="store_true", help="真的写库；不加只干跑")
    args = ap.parse_args()
    label = args.label.strip()
    if not label:
        print("出处不能为空", file=sys.stderr)
        return 2
    hit: list[tuple[str, str]] = []

    def fn(qs):
        for q in qs:
            if (q.meta.get("book") == args.book
                    and q.meta.get("region") == args.region
                    and not q.meta.get("source_label")):
                hit.append((q.key, q.meta.get("source_no") or ""))
                q.meta["source_label"] = label
                q.meta["year"] = args.year
        return qs

    rep = store.update(fn, dry_run=not args.apply)
    print(("已写入" if args.apply else "dry-run：将写入")
          + " %d 道（%s / %s / %d）" % (len(hit), args.book, args.region, args.year))
    for k, no in hit:
        print("  %-42s 题号 %s" % (k, no))
    print("  volumes=%s" % rep.get("volumes"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
