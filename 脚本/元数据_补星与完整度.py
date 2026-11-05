#!/usr/bin/env python3
r"""元数据补星 + 试卷完整度标记（只改元数据，不动正文）。

做三件事：

1. **63 个 0 星知识点补星**：按知识点已有的 `difficulty` 用
   `简单题→1 / 中档题→2 / 难题→3` 补齐；这是知识点库既定的星级口径，
   不新造难度。
2. **试卷完整度标记**：`模拟题`/`高考真题汇编` 中题量 < 10 的试卷，
   给该卷所有题写 `meta.paper_complete=false`、`meta.paper_size=n`；
   同时生成 `数据/试卷完整度.json`（卷级清单）。
3. **stars=0 语义**：本次不改数据字段，`0` 一律表示“未评级”；
   由前端显示“未评级”，不再显示空白。

用法：
    python3 脚本/元数据_补星与完整度.py          # 干跑
    python3 脚本/元数据_补星与完整度.py --yes    # 落盘
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store  # noqa: E402

KB = ROOT / "知识点.json"
PAPER_META = ROOT / "数据" / "试卷完整度.json"
CHANGE_DIR = ROOT / "变更记录"
STAR_OF_DIFF = {"简单题": 1, "中档题": 2, "难题": 3}
PARTIAL_BOOKS = ("模拟题", "高考真题汇编")
PARTIAL_THRESHOLD = 10


def _fill_point_stars() -> tuple[dict[str, int], list[dict]]:
    """返回 {pid: star} 与逐点明细；不写盘。"""
    data = json.loads(KB.read_text(encoding="utf-8"))
    proposed: dict[str, int] = {}
    rows: list[dict] = []
    for topic in data.get("topics", []):
        for sec in topic.get("sections", []):
            for p in sec.get("points", []):
                if int(p.get("stars") or 0) != 0:
                    continue
                diff = (p.get("difficulty") or "").strip()
                star = STAR_OF_DIFF.get(diff, 2)
                proposed[p["id"]] = star
                rows.append({
                    "id": p["id"], "title": p.get("title", ""),
                    "difficulty": diff, "stars": star,
                    "why": f"按知识点难度「{diff or '空'}」补为 {star} 星",
                })
    return proposed, rows


def _write_point_stars(proposed: dict[str, int]) -> None:
    r"""只替换目标点对象里那一行 `"stars": 0,`，保留原文件排版。"""
    lines = KB.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = 0
    for pid, star in proposed.items():
        # 点对象的 `"id"` 在 `stars` 之后；从这里往前找最近的 `"stars": 0`
        idx = next((i for i, ln in enumerate(lines)
                    if re.search(r'"id"\s*:\s*"%s"' % re.escape(pid), ln)), None)
        if idx is None:
            raise SystemExit(f"知识点库里找不到 {pid}")
        for j in range(idx, max(-1, idx - 500), -1):
            m = re.match(r'^(\s*)"stars"\s*:\s*0\s*,\s*$', lines[j])
            if m:
                lines[j] = f'{m.group(1)}"stars": {star},\n'
                changed += 1
                break
        else:
            raise SystemExit(f"{pid} 前 500 行里找不到 \"stars\": 0")
    if changed != len(proposed):
        raise SystemExit(f"只改了 {changed} 个点，预期 {len(proposed)}")
    tmp = KB.with_suffix(".json.tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(KB)


def _paper_meta(qs) -> tuple[dict[str, dict], list[str]]:
    counter = collections.Counter()
    for q in qs:
        if q.meta.get("book") in PARTIAL_BOOKS:
            counter[q.key.split("#")[0]] += 1
    partial = {k: n for k, n in counter.items() if n < PARTIAL_THRESHOLD}
    return partial, sorted(partial)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="落盘；默认只干跑")
    args = ap.parse_args()

    proposed, rows = _fill_point_stars()
    qs, sig = store.load_for_update()
    partial, partial_keys = _paper_meta(qs)

    # 试卷完整度：给该卷所有题打标；非残缺卷清掉旧标（可重复跑）
    for q in qs:
        paper = q.key.split("#")[0]
        if paper in partial:
            q.meta["paper_complete"] = False
            q.meta["paper_size"] = partial[paper]
        else:
            q.meta.pop("paper_complete", None)
            q.meta.pop("paper_size", None)

    print("0 星知识点：", len(proposed), "个")
    print("  补星分布：", dict(collections.Counter(proposed.values())))
    print("题量 <10 的试卷：", len(partial), "套，涉及",
          sum(partial.values()), "道题")
    print("  模拟题：", sum(1 for k in partial_keys if k.startswith("模拟题/")))
    print("  高考真题：", sum(1 for k in partial_keys if k.startswith("高考真题汇编/")))

    if not args.yes:
        print("\n（干跑。确认后加 --yes 落盘）")
        for r in rows[:8]:
            print(f"  ★{r['stars']} {r['id']} {r['title'][:40]} ← {r['why']}")
        return 0

    _write_point_stars(proposed)
    store.rewrite_all(qs, based_on=sig)

    PAPER_META.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "threshold": PARTIAL_THRESHOLD,
        "note": "题量少于 threshold 的试卷，疑似只录入了一部分；组卷/筛选时按节选处理。",
        "papers": {
            k: {"n": partial[k], "complete": False,
                "reason": f"仅录入 {partial[k]} 题（少于 {PARTIAL_THRESHOLD} 题）"}
            for k in partial_keys
        },
    }
    PAPER_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    report = CHANGE_DIR / (
        "%s_元数据_补星与完整度.md" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    lines = [
        "# 元数据迁移：知识点补星 + 试卷完整度",
        "",
        f"- 时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 0 星知识点补星：{len(proposed)} 个",
        f"- 题量 <{PARTIAL_THRESHOLD} 的试卷：{len(partial)} 套 / {sum(partial.values())} 题",
        "",
        "## 知识点补星",
        "",
        "| 考点 | 难度 | 星级 | 依据 |",
        "|---|---|---:|---|",
    ]
    for r in rows:
        lines.append("| `%s` %s | %s | %d | %s |"
                     % (r["id"], r["title"].split("  ·")[0],
                        r["difficulty"] or "空", r["stars"], r["why"]))
    lines += ["", "## 题量不足的试卷", "", "| 试卷 | 题数 |", "|---|---:|"]
    for k in partial_keys:
        lines.append("| `%s` | %d |" % (k, partial[k]))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("✓ 已落盘")
    print("  知识点：", KB)
    print("  试卷清单：", PAPER_META)
    print("  变更记录：", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
