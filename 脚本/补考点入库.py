#!/usr/bin/env python3
r"""给「还没打知识点标签」的题补 `points`（难度随之按主考点派生）。

## 这件事的唯一入口

* 标签的**读**：`schema.Question.difficulty` / `points`（难度由主考点派生，
  见 `amti/knowledge.py`——难度不单独存，考点库 152 个考点的难度是齐的）。
* 标签的**写**：`store.rewrite_all()`（与界面 `PATCH /api/questions/{key}`
  走的是同一条路），本脚本只是把标签批量喂给它。
* 一道题的正文（题干/选项/答案/解析/配图）**一个字节都不许变**——
  落盘前逐题比对 `content_hash()`，指纹变了就整批拒绝。
* 已有考点的题**不覆盖**（防丢人工标签）；标签里的考点 id 必须在
  `知识点.json` 里存在，1–3 个且不重复。

## 输入（`.tobias/分类/最终标签.json`，一次性产物）

`[{"key": …, "points": ["5.2.1"], "source": "llm|dup", "note": "…"}, …]`
——由逐题读题干的模型分类结果与查重孪生题的继承结果合并而来，
合并规则：孪生题题干与本题近乎一致（相似度 ≥0.95）时信继承，否则信分类。

## 用法

    python3 脚本/补考点入库.py            # 干跑：校验 + 报告会改什么
    python3 脚本/补考点入库.py --yes      # 落盘（写库 + 变更记录/ 报告）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import conform, knowledge, store  # noqa: E402

WORK = ROOT / ".tobias" / "分类"
PLAN_FILE = WORK / "最终标签.json"
CHANGE_DIR = ROOT / "变更记录"

SRC_CN = {"llm": "模型逐题分类（读题干/选项选考点）",
          "dup": "孪生题继承（题干近乎一致的查重命中）"}


def load_plan() -> dict[str, dict]:
    """读合并好的标签表并全量校验。返回 {key: {points, source, note}}。"""
    if not PLAN_FILE.exists():
        raise SystemExit("缺少 %s" % PLAN_FILE)
    rows = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    kb = knowledge._index()
    plan: dict[str, dict] = {}
    problems: list[str] = []
    for row in rows:
        key, pts = row.get("key"), [str(p).strip() for p in (row.get("points") or [])]
        if not key:
            problems.append("有一行没有 key")
            continue
        if key in plan:
            problems.append("%s：标签表里重复" % key)
        if not 1 <= len(pts) <= 3:
            problems.append("%s：考点数 %d（要 1–3 个）" % (key, len(pts)))
        if len(set(pts)) != len(pts):
            problems.append("%s：考点重复 %s" % (key, pts))
        bad = [p for p in pts if p not in kb]
        if bad:
            problems.append("%s：考点不存在 %s" % (key, bad))
        if row.get("source") not in SRC_CN:
            problems.append("%s：source 非法 %r" % (key, row.get("source")))
        plan[key] = {"points": pts, "source": row["source"],
                     "note": row.get("note", "")}
    if problems:
        raise SystemExit("标签校验失败（%d 条）：\n  " % len(problems)
                         + "\n  ".join(problems[:20]))
    return plan


def run(apply: bool = False) -> dict:
    plan = load_plan()

    qs = store.load_all()
    by_key = {q.key: q for q in qs}
    hash_before = {q.key: q.content_hash() for q in qs}

    todo: list[tuple[str, dict]] = []
    problems: list[str] = []
    for key, row in sorted(plan.items()):
        q = by_key.get(key)
        if q is None:
            problems.append("%s：库里没有这道题" % key)
            continue
        if q.points:
            problems.append("%s：已有考点 %s，不覆盖（防丢人工标签）" % (key, q.points))
            continue
        q.points = list(row["points"])
        q.meta["point_source"] = row["source"]
        todo.append((key, row))

    # 正文一个字节都不许变
    changed = [k for k in hash_before if by_key[k].content_hash() != hash_before[k]]
    if changed:
        return {"ok": False,
                "problems": ["内容指纹变了（动了正文），整批拒绝：%s" % changed[:5]] + problems}

    # 改完必须仍然合规
    viol = conform.run([by_key[k] for k, _r in todo])
    if viol:
        return {"ok": False,
                "problems": ["改完不规范：%s（%s/%s）" % (v["why"], v["check"], v["field"])
                             for v in viol] + problems}

    # 改完后的难度分布（全库；难度由主考点派生）
    diff_after = Counter((q.difficulty or "未定") for q in by_key.values())
    out = {"ok": True, "plan": len(todo), "dry_run": not apply, "problems": problems,
           "by_source": dict(Counter(r["source"] for _k, r in todo)),
           "difficulty_after": dict(diff_after)}

    if not apply:
        for key, row in todo[:15]:
            out.setdefault("items", []).append(
                "%s → %s（%s）" % (key, "、".join(row["points"]), SRC_CN[row["source"]]))
        if len(todo) > 15:
            out["items"].append("… 共 %d 道" % len(todo))
        return out

    # ── 落盘：唯一入口 store.rewrite_all（两阶段写盘 + 自带回滚） ──
    store.rewrite_all(list(by_key.values()))
    store.cache_clear()

    # 写完从磁盘回读验一遍：考点写进去了、正文指纹没动
    back = {q.key: q for q in store.load_all()}
    bad = [k for k, row in todo
           if k not in back or back[k].points != row["points"]
           or back[k].content_hash() != hash_before[k]]
    if bad:
        return {"ok": False, "problems": ["回读校验失败：%s" % bad[:5]]}

    # 留痕
    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rep = CHANGE_DIR / ("%s_补考点.md" % stamp)
    lines = [
        "# 补考点与难度",
        "",
        "- 时间：%s" % _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- 改动：%d 道题补 `points`（全库 %d 道）" % (len(todo), len(back)),
        "- 依据：" + "；".join("%s %d 道" % (SRC_CN[k], v)
                              for k, v in Counter(r["source"] for _k, r in todo).items()),
        "- 难度：不单独写，由**主考点**派生（`knowledge.difficulty_of`）；"
          "原有 `meta.difficulty` 人工标注保留不动",
        "- 正文：未改（逐题比对 `content_hash()`，0 处变化）",
        "",
        "## 改完后的难度分布（全库）",
        "",
        "| 难度 | 道数 |",
        "|---|---|",
    ]
    for d in ("简单题", "中档题", "难题", "未定"):
        lines.append("| %s | %d |" % (d, diff_after.get(d, 0)))
    lines += ["", "## 逐条", ""]
    for key, row in todo:
        note = "（%s）" % row["note"] if row["note"] else ""
        lines.append("- `%s` → %s%s" % (key, "、".join(row["points"]), note))
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out.update(written=True, report=str(rep))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="补考点（默认干跑）")
    ap.add_argument("--yes", action="store_true", help="真的落盘")
    a = ap.parse_args()

    r = run(apply=a.yes)
    if not r.get("ok"):
        print("✗ 没有落盘：")
        for p in r["problems"]:
            print("   · %s" % p)
        return 1
    if r["dry_run"]:
        print("待补考点 %d 道（%s）" % (r["plan"], r["by_source"]))
        for it in r.get("items", []):
            print("   · %s" % it)
        print("改完后难度分布：%s" % r["difficulty_after"])
        print("\n（干跑。确认无误后加 --yes 落盘）")
        return 0
    print("✓ 已补 %d 道（%s），报告：%s" % (r["plan"], r["by_source"], r["report"]))
    print("  改完后难度分布：%s" % r["difficulty_after"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
