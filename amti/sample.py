"""抽取有代表性的测试集（100 道）。

按旧库的真实特征分布设计配额，**稀有特征全取**、常见特征按比例：

    特征                全库       配额   说明
    有 TikZ 矢量图       122 道     5     稀有，必须覆盖
    有表格               386 道     5
    有位图              2345 道    25     用户特别要求
    无答案              9626 道    15     占 46%，是主流形态
    无解析              4978 道    10
    带小问列表           5171 道    20
    其余补齐                       20
    ────────────────────────────────────
    合计                          100

同时保证**四类题型各 25 道**。
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

# 旧项目的库。**只用于「从旧库抽样」这个一次性用途**，
# 主流程（录入/组卷/导出）都不碰它。文件不在了就自己报错，不会静默出错。
OLD_DB = Path("/Users/ximing/Documents/deepseek/习题/题库/题库.db")

# (类别名, SQL 条件, 配额)
# 所有类别都**必须有解析**——没有解析的题测不出渲染和导出的完整链路
REQUIRE_SOLUTION = "COALESCE(solution,'') <> ''"

CATEGORIES = [
    ("tikz",       "tikz <> '' OR content LIKE '%tikzpicture%'", 5),
    ("table",      "content LIKE '%tabular%' AND content NOT LIKE '%tikzpicture%'", 5),
    ("bitmap",     "content LIKE '%includegraphics%' AND tikz = ''", 25),
    ("no_answer",  "COALESCE(answer,'')=''", 10),   # 有解析但答案字段空
    ("enumerate",  "content LIKE '%enumerate%'", 25),
    ("rest",       "1=1", 30),
]
CATEGORIES = [(n, f"({c}) AND {REQUIRE_SOLUTION}", q) for n, c, q in CATEGORIES]

TYPES = ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer")


# 每类题型内的特征上限。**用上限，不用优先级排序**——
# 优先级排序会让稀有特征被抽光（实测：122 道 TikZ 抽进来 65 道，占样本 65%，
# 完全失去代表性）。上限保证「每种特征都覆盖到，但不喧宾夺主」。
CAPS = [
    ("tikz",      "content LIKE '%tikzpicture%'", 2),
    ("table",     "content LIKE '%tabular%' AND content NOT LIKE '%tikzpicture%'", 2),
    ("bitmap",    "content LIKE '%includegraphics%' AND content NOT LIKE '%tikzpicture%'", 5),
    ("enumerate", "content LIKE '%enumerate%' AND content NOT LIKE '%includegraphics%'", 6),
]


def pick_by_type(conn, per_type: int, used: set[int]) -> list[tuple[str, int]]:
    """每个题型各抽 per_type 道；题内按**特征配额**取，最后用普通题补足。

    这样四类题型均衡，且每种特征都有覆盖但不超标。
    """
    out: list[tuple[str, int]] = []
    for t in TYPES:
        got: list[int] = []
        # ① 按配额取稀有特征
        for _name, cond, cap in CAPS:
            rows = conn.execute(
                f"SELECT id FROM questions WHERE qtype = ? AND {REQUIRE_SOLUTION} "
                f"AND COALESCE(content,'') <> '' AND ({cond}) ORDER BY id",
                (t,)).fetchall()
            n = 0
            for r in rows:
                if n >= cap or len(got) >= per_type:
                    break
                if r["id"] in used:
                    continue
                used.add(r["id"]); got.append(r["id"]); n += 1
        # ② 普通题补足
        if len(got) < per_type:
            rows = conn.execute(
                f"SELECT id FROM questions WHERE qtype = ? AND {REQUIRE_SOLUTION} "
                "AND COALESCE(content,'') <> '' ORDER BY id", (t,)).fetchall()
            for r in rows:
                if len(got) >= per_type:
                    break
                if r["id"] in used:
                    continue
                used.add(r["id"]); got.append(r["id"])
        out += [(t, i) for i in got]
        print(f"  {t:16} 取 {len(got):3} 道")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="抽有代表性的测试集")
    ap.add_argument("--db", default=str(OLD_DB))
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default="/tmp/ruku/sample.db")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    used: set[int] = set()
    per_type = max(1, args.n // len(TYPES))
    print(f"按题型各抽 {per_type} 道（类内优先稀有特征）：")
    chosen = pick_by_type(conn, per_type, used)

    # ── 组成报告 ──
    ids = [i for _t, i in chosen]
    marks = ",".join("?" * len(ids))
    rows = {r["id"]: r for r in conn.execute(
        f"SELECT * FROM questions WHERE id IN ({marks})", ids)}

    from collections import Counter
    print(f"\n共 {len(ids)} 道，特征分布：")
    feats = {
        "有 TikZ":      lambda r: bool(r["tikz"]) or "tikzpicture" in (r["content"] or ""),
        "有表格":        lambda r: "tabular" in (r["content"] or ""),
        "有位图":        lambda r: "includegraphics" in (r["content"] or ""),
        "带小问列表":     lambda r: "enumerate" in (r["content"] or ""),
        "有答案":        lambda r: bool((r["answer"] or "").strip()),
        "有解析":        lambda r: bool((r["solution"] or "").strip()),
    }
    for label, fn in feats.items():
        n = sum(1 for i in ids if fn(rows[i]))
        print(f"  {label:10} {n:3} 道  {n}%")
    print("\n题型分布：", dict(Counter(rows[i]["qtype"] for i in ids)))
    miss = [i for i in ids if not (rows[i]["solution"] or "").strip()]
    print("无解析：", len(miss), "道", "✓ 全部带解析" if not miss else "✗")
    print("来源分布：", dict(Counter(rows[i]["book"][:14] for i in ids).most_common(5)))

    # ── 导出成独立库 ──
    out = Path(args.out)
    out.unlink(missing_ok=True)
    dst = sqlite3.connect(out)
    conn.backup(dst)
    dst.execute("CREATE TEMP TABLE keep(id INTEGER)")
    dst.executemany("INSERT INTO keep VALUES(?)", [(i,) for i in ids])
    dst.execute("DELETE FROM questions WHERE id NOT IN (SELECT id FROM keep)")
    dst.execute("DELETE FROM question_points WHERE question_id NOT IN (SELECT id FROM keep)")
    dst.commit()
    print(f"\n→ {out}（{dst.execute('SELECT COUNT(*) FROM questions').fetchone()[0]} 道）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
