r"""把「缺解析」的题导出成外部大模型求解用的 JSONL。

用法：

    python3 脚本/导出求解输入.py                 # 全部，一个 jsonl
    python3 脚本/导出求解输入.py --batch 20      # 另按每批 20 道切文件
    python3 脚本/导出求解输入.py --out 某文件.jsonl

字段与 `docs/求解要求_外部模型.md` 一致：

    key / type / stem / options / answer / has_figure / points / difficulty

`has_figure`：题干里有 `\includegraphics` / `tikzpicture`，或登记了配图。
这类题模型看不到图，要求里会让他返回 `needs_figure`，不要瞎猜。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store                                  # noqa: E402
from amti.schema import QTYPE_LABEL                     # noqa: E402

OUT_DIR = ROOT / "数据" / "题库审阅"


def to_record(q) -> dict:
    stem = q.stem or ""
    has_fig = (bool(q.figures)
               or "\\includegraphics" in stem
               or "tikzpicture" in stem
               # 图丢了但题干还说「如图」：模型看不到图，必须要求 needs_figure
               or any(k in stem for k in ("如图", "见图", "图中", "下图", "上图")))
    return {
        "key": q.key,
        "type": q.type,
        "type_label": QTYPE_LABEL.get(q.type, q.type),
        "stem": stem,
        "options": [[o.label, o.text] for o in q.options],
        "answer": q.answer or "",
        "has_figure": has_fig,
        "points": q.point_titles or list(q.points or []),
        "difficulty": q.difficulty,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="导出缺解析题的求解输入 JSONL")
    ap.add_argument("--out", default="", help="输出文件；默认 数据/题库审阅/求解输入_日期.jsonl")
    ap.add_argument("--batch", type=int, default=0,
                    help="同时按每批 N 道切到 数据/题库审阅/求解批次/")
    a = ap.parse_args()

    qs = [q for q in store.load_cached() if not q.has_solution]
    qs.sort(key=lambda q: (0 if q.kind == "高考" else 1, q.key))
    recs = [to_record(q) for q in qs]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT_DIR / (
        "求解输入_%s.jsonl" % _dt.date.today().strftime("%Y%m%d"))
    with out.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("缺解析 %d 道 → %s" % (len(recs), out))
    print("  有配图（模型看不到，会要求 needs_figure）：%d 道"
          % sum(1 for r in recs if r["has_figure"]))
    if a.batch and a.batch > 0:
        d = OUT_DIR / "求解批次"
        d.mkdir(parents=True, exist_ok=True)
        n = 0
        for i in range(0, len(recs), a.batch):
            n += 1
            p = d / ("批次_%03d.jsonl" % n)
            with p.open("w", encoding="utf-8") as f:
                for r in recs[i:i + a.batch]:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("  按每批 %d 道切了 %d 个文件 → %s" % (a.batch, n, d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
