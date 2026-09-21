"""AmTiKu · 从旧题库迁移（**一次性工具，源可能已删**）

⚠️ 旧项目 `deepseek/习题/题库/` 已经清理过，这个脚本**大概率已经跑不了**。
留着是为了记录当初是怎么迁的（字段形状、坑在哪）。真要重跑，
先把旧库 `题库.db` 放回原路径。


旧库的字段是历史积累的（`options_json` 字符串、`figures_json`、考点混在
`question_points` 表里）。这里只做**形状转换**，不做任何语义修正——
修正属于迁移规则（MIGRATE 级），必须显式声明、dry-run、留记录。

用法：
    python3 -m amti.migrate --db 旧库路径 --limit 100        # 先小批量试
    python3 -m amti.migrate --db 旧库路径                    # 全量
    python3 -m amti.migrate --db 旧库路径 --limit 100 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import os
from pathlib import Path

from .latex_ir import derive_figures
from .schema import Option, Question
from . import store

OLD_DB = Path(os.environ.get("AMTIKU_OLD_DB", "旧题库.db"))      # 旧版 v1 数据库（已废弃的工具）
OLD_IMG = Path(os.environ.get("AMTIKU_OLD_IMG", "旧题库图片"))

IMG_RE = re.compile(r"\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")


def old_key(r) -> str:
    return f"{r['book']}/{r['page']}#{r['number']}"


def to_question(r, points: list[str], point_source: str = "") -> Question:
    """旧行 → 新 Question。**只转形状，不改内容。**"""
    opts = [Option(o.get("label", ""), o.get("text", ""))
            for o in json.loads(r["options_json"] or "[]")]

    stem = r["content"] or ""
    solution = (r["solution"] or "").strip()

    # 配图**从正文推导**，不读 `figures_json`——实测它不全
    # （2024 新高考I卷#7 正文有 \\includegraphics，figures_json 却是 []）。
    # 而且必须和 `parse_question` 用同一个函数，否则写入/读出指纹对不上。
    figs = derive_figures(stem, solution, *(o.text for o in opts))

    q = Question(
        key=old_key(r), type=r["qtype"] or "detailed_answer",
        stem=stem, options=opts,
        answer=(r["answer"] or "").strip(),
        solution=solution,
        figures=figs,
        meta={k: v for k, v in (
            ("book", r["book"]), ("year", r["book_year"]),
            ("source_label", r["source_label"]), ("region", r["region"]),
            # 标签来源：将来重打标签时，知道哪些是自动的该换掉
            ("point_source", point_source),
        ) if v not in (None, "")},
        points=points,
    )
    return q


def load_points(conn) -> tuple[dict[int, list[str]], dict[int, str]]:
    r"""考点标签：按**质量分级**取，并记录来源。

    旧库有三种来源，质量依次递减：

        llm       大模型判的        最好
        existing  源语料自带的      可靠
        auto      TF-IDF 算的       兜底

    原计划是"LLM 打完标签就删掉 auto"，但 LLM 只跑到 61% 就停了——
    **auto 现在还是很多题唯一的标签**。所以按「llm > existing > auto」
    的优先级取，没有高质量的才退化到 auto，并把来源记进 meta，
    将来重打标签时知道哪些是该换掉的。
    """
    ORDER = {"llm": 0, "existing": 1, "auto": 2}
    by_q: dict[int, list[tuple[int, str, str, float]]] = {}
    for r in conn.execute(
            "SELECT question_id, point_id, role, source, COALESCE(score,0) s "
            "FROM question_points WHERE source IN ('llm','existing','auto')"):
        by_q.setdefault(r["question_id"], []).append(
            (ORDER.get(r["source"], 9), r["point_id"], r["role"], r["s"]))

    points: dict[int, list[str]] = {}
    source_of: dict[int, str] = {}
    for qid, items in by_q.items():
        # 先按来源质量，再让主考点在前（难度取自 points[0]），最后按分数
        items.sort(key=lambda x: (x[0], x[2] != "primary", -x[3]))
        best = min(x[0] for x in items)
        source_of[qid] = {0: "llm", 1: "existing"}.get(best, "auto")
        # 只取该题**最高质量那一档**的标签，不把 auto 混进来凑数
        points[qid] = [x[1] for x in items if x[0] == best]
    return points, source_of


def main() -> int:
    ap = argparse.ArgumentParser(description="从旧题库迁移到 AmTiKu")
    ap.add_argument("--db", default=str(OLD_DB))
    ap.add_argument("--limit", type=int, default=0, help="只迁前 N 道（0=全部）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--types", default="", help="只要这些题型，逗号分隔")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    pts, pt_src = load_points(conn)

    where, params = [], []
    if args.types:
        ts = [t.strip() for t in args.types.split(",") if t.strip()]
        where.append("qtype IN (%s)" % ",".join("?" * len(ts)))
        params += ts
    # 均匀抽样：按 id 排序取，保证四类题型都有
    sql = "SELECT * FROM questions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id"
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"

    rows = list(conn.execute(sql, params))
    print(f"读取 {len(rows)} 行（限 {args.limit or '全部'}）")

    qs, bad = [], []
    for r in rows:
        q = to_question(r, pts.get(r["id"], []), pt_src.get(r["id"], ""))
        probs = q.problems()
        if probs:
            bad.append((q.key, probs))
        qs.append(q)

    print(f"转换完成：{len(qs)} 道，其中 {len(bad)} 道不满足新 schema")
    if bad:
        from collections import Counter
        c = Counter(p.split("：")[0].split("，")[0] for _k, ps in bad for p in ps)
        print("  不合法原因分布：")
        for k, v in c.most_common(8):
            print(f"    {v:5}  {k[:52]}")

    if args.dry_run:
        print("\n[干跑] 不写任何东西。前 3 道预览：")
        for q in qs[:3]:
            print(f"  {q.key}  [{q.type}]  {q.stem[:60]}")
        return 0

    log = store.append(qs)
    print(f"\n写入 {len(log)} 条：")
    for line in log[:5]:
        print("  ", line)
    if len(log) > 5:
        print(f"   … 其余 {len(log)-5} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
