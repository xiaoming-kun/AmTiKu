#!/usr/bin/env python3
r"""题目层冲突：按考点“多数票”回填考点星级/难度。

规则（保守版）：

1. 只看**主考点**下题目自带的 `difficulty`/`stars` 配对值；
2. 该考点至少要有 **3 个**自带样本；
3. 取配对值的众数；若并列，保留考点现值、不裁决；
4. 含「综合 / 进阶 / 压轴」的考点**不降级**（防止把压轴题降成简单题）；
5. 考点值改后，题目自带值仍然保留为 override——只把与考点新值不一致的
   题导成 `冲突离群题.csv` 供人工复核。

用法：
    python3 脚本/元数据_冲突多数票.py          # 干跑
    python3 脚本/元数据_冲突多数票.py --yes    # 落盘
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as _dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import knowledge, store  # noqa: E402

KB = ROOT / "知识点.json"
OUT_DIR = ROOT / "题库评价"
CHANGE_DIR = ROOT / "变更记录"
CALIB = ROOT / "数据" / "冲突校准.json"
STAR_DIFF = {"简单题": 1, "中档题": 2, "难题": 3}
DIFF_STAR = {1: "简单题", 2: "中档题", 3: "难题", 4: "难题"}
GUARD = re.compile(r"综合|进阶|压轴")


def _dist(d) -> dict:
    return {f"{k[0]}/{k[1]}": v for k, v in d.items()}


def _pair(q) -> tuple[str, int] | None:
    """题目的自带（难度, 星级）配对；没有自带值返回 None。"""
    m = q.meta or {}
    d = (m.get("difficulty") or "").strip()
    s = m.get("stars")
    if not isinstance(s, int) or s <= 0:
        s = STAR_DIFF.get(d, 0)
    if not d and s > 0:
        d = DIFF_STAR.get(s, "")
    if not d and not s:
        return None
    return d, int(s)


def _propose(qs) -> tuple[dict[str, tuple[str, int]], list[dict], list[dict]]:
    by = collections.defaultdict(list)
    for q in qs:
        if q.points:
            by[q.points[0]].append(q)
    new: dict[str, tuple[str, int]] = {}
    changed: list[dict] = []
    kept: list[dict] = []
    for pid, arr in by.items():
        cur = (knowledge.difficulty_of(pid), knowledge.stars_of(pid))
        pairs = [p for p in (_pair(q) for q in arr) if p]
        c = collections.Counter(pairs)
        n = sum(c.values())
        row = {"point": pid, "title": knowledge.title_of(pid), "n": n,
               "current": cur, "dist": dict(c)}
        if n < 3:
            new[pid] = cur
            row["reason"] = "自带样本少于 3"
            kept.append(row)
            continue
        top = c.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            new[pid] = cur
            row["reason"] = "众数并列"
            kept.append(row)
            continue
        best, count = top[0]
        if GUARD.search(knowledge.title_of(pid)) and best[1] < cur[1]:
            new[pid] = cur
            row["reason"] = "综合/进阶/压轴题不降级"
            kept.append(row)
            continue
        new[pid] = best
        if best != cur:
            row.update({"best": best, "count": count})
            changed.append(row)
    return new, changed, kept


def _write_points(new: dict[str, tuple[str, int]]) -> None:
    lines = KB.read_text(encoding="utf-8").splitlines(keepends=True)
    done = 0
    for pid, (diff, star) in new.items():
        idx = next((i for i, ln in enumerate(lines)
                    if re.search(r'"id"\s*:\s*"%s"' % re.escape(pid), ln)), None)
        if idx is None:
            raise SystemExit(f"知识点库里找不到 {pid}")
        # stars 在 id 之前，difficulty 在 id 之后
        for j in range(idx, max(-1, idx - 500), -1):
            m = re.match(r'^(\s*)"stars"\s*:\s*(\d+)\s*,\s*$', lines[j])
            if m:
                lines[j] = f'{m.group(1)}"stars": {star},\n'
                break
        else:
            raise SystemExit(f"{pid} 前 500 行里找不到 stars")
        for j in range(idx, min(len(lines), idx + 8)):
            m = re.match(r'^(\s*)"difficulty"\s*:\s*"([^"]*)"\s*,?\s*$', lines[j])
            if m:
                # difficulty 是点对象的最后一个字段，后面直接是 `}`；
                # 这里绝不能补逗号（会写出非法 JSON）。
                lines[j] = f'{m.group(1)}"difficulty": "{diff}"\n' 
                break
        else:
            raise SystemExit(f"{pid} 后 8 行里找不到 difficulty")
        done += 1
    if done != len(new):
        raise SystemExit(f"只写了 {done} 个点，预期 {len(new)}")
    tmp = KB.with_suffix(".json.tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(KB)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="落盘；默认只干跑")
    args = ap.parse_args()

    qs = store.load_all()
    new, changed, kept = _propose(qs)

    # 统计改后冲突
    stars_conf = diff_conf = 0
    outliers = []
    for q in qs:
        pid = (q.points or [None])[0]
        if not pid or pid not in new:
            continue
        own = _pair(q)
        if not own:
            continue
        pd, ps = new[pid]
        if own != (pd, ps):
            outliers.append((q, pid, own, (pd, ps)))
            if own[1] != ps:
                stars_conf += 1
            if own[0] != pd:
                diff_conf += 1

    print(f"考点总数 {len(new)}；改判 {len(changed)}；保留 {len(kept)}")
    print(f"预计改后冲突：星级 {stars_conf}、难度 {diff_conf}")
    print(f"离群题（自带值 ≠ 考点新值）：{len(outliers)}")
    for r in changed[:10]:
        print("  ", r["point"], r["title"][:30], r["current"], "→", r["best"],
              f"({r['count']}/{r['n']})")

    if not args.yes:
        print("\n（干跑。确认后加 --yes 落盘）")
        return 0

    _write_points(new)

    calibrated = sorted(pid for pid in new if pid not in {r["point"] for r in kept})
    CALIB.parent.mkdir(parents=True, exist_ok=True)
    CALIB.write_text(json.dumps({
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rule": "主考点至少 3 个题目自带（难度,星级）样本；取众数；并列保留；综合/进阶/压轴不降级",
        "points": calibrated,
        "changed": [r["point"] for r in changed],
        "kept": [r["point"] for r in kept],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # 离群题清单
    out_csv = OUT_DIR / "冲突离群题.csv"
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["key", "point", "point_title", "own_difficulty", "own_stars",
                    "point_difficulty", "point_stars", "type", "answer", "stem"])
        for q, pid, own, pnt in outliers:
            w.writerow([q.key, pid, knowledge.title_of(pid), own[0], own[1],
                        pnt[0], pnt[1], q.type, q.answer,
                        re.sub(r"\s+", " ", q.stem or "")[:180]])
    # 未裁决考点清单
    keep_csv = OUT_DIR / "冲突未裁决考点.csv"
    with keep_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["point", "title", "n", "current_difficulty", "current_stars",
                    "reason", "distribution"])
        for r in kept:
            w.writerow([r["point"], r["title"], r["n"], r["current"][0], r["current"][1],
                        r["reason"], json.dumps(_dist(r["dist"]), ensure_ascii=False)])

    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    report = CHANGE_DIR / (
        "%s_元数据_冲突多数票.md" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    lines = [
        "# 元数据迁移：题目层冲突多数票",
        "",
        f"- 时间：{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 改判考点：{len(changed)} / {len(new)}",
        f"- 离群题：{len(outliers)}",
        f"- 预计冲突：星级 {stars_conf}、难度 {diff_conf}",
        "",
        "## 改判考点",
        "",
        "| 考点 | 题数 | 旧值 | 新值 | 众数票 |",
        "|---|---:|---|---|---:|",
    ]
    for r in changed:
        lines.append("| `%s` %s | %d | %s/%d | %s/%d | %d/%d |"
                     % (r["point"], r["title"].split("  ·")[0], r["n"],
                        r["current"][0], r["current"][1],
                        r["best"][0], r["best"][1], r["count"], r["n"]))
    lines += ["", "## 未裁决考点", "", "| 考点 | 题数 | 原因 | 分布 |", "|---|---:|---|---|"]
    for r in kept:
        lines.append("| `%s` %s | %d | %s | `%s` |"
                     % (r["point"], r["title"].split("  ·")[0], r["n"],
                        r["reason"], json.dumps(_dist(r["dist"]), ensure_ascii=False)))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("✓ 已落盘")
    print("  离群题：", out_csv)
    print("  未裁决：", keep_csv)
    print("  校准登记：", CALIB)
    print("  变更记录：", report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
