r"""把全库按每 100 题切成一份 PDF，供逐题人工审阅。

- 全局序号从 000001 开始，固定按 `store.load_all()` 的顺序；
- 每份：封面 + 100 道题（题干/选项/答案/解析/来源/检查框）；
- 另出 `索引.csv`：全局序号、册号、题号、题型、难度、年份、来源、解析来源、解析字数；
- 只读题库，不改数据。
"""
from __future__ import annotations

import argparse
import copy
import csv
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from amti import paper, store          # noqa: E402
from amti.schema import QTYPE_LABEL    # noqa: E402
from amti.paths import ROOT as P       # noqa: E402

XELATEX = "/Users/ximing/texlive/2026/bin/universal-darwin/xelatex"
PER = 100


def safe_q(q):
    """审阅版不再做兼容替换：5 道原始 LaTeX 问题已按订正台账修好。"""
    return q


def tex_for(batch: int, items: list[tuple[int, object]], total: int) -> str:
    lo = items[0][0]
    hi = items[-1][0]
    doc = paper.preamble(show_answers=True, graphicspath=str(P / "图片"),
                         extra=[r"\usepackage{fancyhdr}"])
    doc += [r"\begin{document}", r"\setlength{\parindent}{0pt}",
            r"\pagestyle{fancy}", r"\fancyhf{}",
            r"\fancyhead[L]{\small 全库题目审阅}",
            r"\fancyhead[R]{\small 第 %03d 册 · %06d--%06d}" % (batch, lo, hi),
            r"\fancyfoot[C]{\small 第 \thepage\ 页}"]
    doc += [
        r"\thispagestyle{empty}",
        r"\begin{center}",
        r"{\LARGE\bfseries 全库题目审阅}\\[8pt]",
        r"{\large 第 %03d 册 · 全局序号 %06d--%06d}\\[14pt]" % (batch, lo, hi),
        r"{\small 共 %d 道；按题库当前顺序固定编号，不随界面排序变化}\\[6pt]" % total,
        r"\end{center}",
        r"\vspace{8pt}",
        r"\textbf{检查方式}\par",
        r"\begin{itemize}",
        r"  \item 先看题干和答案，再看解析；发现错误在题下勾“有问题”，最好写一句原因。",
        r"  \item 题号是全局序号，从 000001 到 %06d；每册 100 道。" % total,
        r"  \item 机器解析（解析来源 workbuddy）要重点看：只写答案、写略、无法求解、截断、答案不一致。",
        r"  \item 图题注意图是否与题干匹配；缺图/错图也勾“有问题”。",
        r"\end{itemize}",
        r"\vspace{8pt}\hrule\vspace{8pt}",
        r"\clearpage",
    ]
    for no, q0 in items:
        q = safe_q(q0)
        meta = " · ".join(x for x in [
            QTYPE_LABEL.get(q.type, q.type), q.difficulty,
            str(q.meta.get("year") or ""), str(q.meta.get("source_label") or ""),
            ("解析来源 " + str(q.meta.get("solution_source"))) if q.meta.get("solution_source") else "",
        ] if x)
        flags = []
        if not q.answer.strip():
            flags.append("缺答案")
        if not q.has_solution:
            flags.append("缺解析")
        if not q.points:
            flags.append("缺考点")
        if flags:
            meta += " · " + "、".join(flags)
        doc += [
            r"\needspace{18\baselineskip}",
            r"{\Large\bfseries %06d}\hfill{\scriptsize\ttfamily %s}\par" % (no, paper.esc_text(q.key)),
            r"{\scriptsize %s}\par" % paper.esc_text(meta),
            *([r"{\scriptsize\bfseries\color{red}%s}\par" % paper.esc_text(q.meta["_review_note"])]
              if q.meta.get("_review_note") else []),
            r"\vspace{2pt}",
            paper.question_tex(q, show_answers=True, show_source=True),
            r"\vspace{2pt}\noindent"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 通过 \quad"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 有问题（原因：\rule{6cm}{0.4pt}）\par",
            r"\vspace{4pt}\hrule\vspace{6pt}",
        ]
    doc += [r"\end{document}"]
    return "\n".join(doc)


def do_batch(batch: int, items: list[tuple[int, object]], total: int, outdir: Path):
    work = outdir / "_tex" / ("batch_%03d" % batch)
    work.mkdir(parents=True, exist_ok=True)
    texp = work / ("batch_%03d.tex" % batch)
    texp.write_text(tex_for(batch, items, total), encoding="utf-8")
    r = subprocess.run([XELATEX, "-interaction=nonstopmode", "-halt-on-error",
                        "-output-directory", str(work), str(texp)],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, timeout=900)
    pdf = work / ("batch_%03d.pdf" % batch)
    if r.returncode or not pdf.exists():
        return batch, False, (r.stdout or "")[-1500:]
    lo, hi = items[0][0], items[-1][0]
    out = outdir / ("第%03d册_%06d-%06d.pdf" % (batch, lo, hi))
    out.write_bytes(pdf.read_bytes())
    for f in work.glob("*.aux"):
        f.unlink(missing_ok=True)
    for f in work.glob("*.log"):
        f.unlink(missing_ok=True)
    for f in work.glob("*.out"):
        f.unlink(missing_ok=True)
    return batch, True, str(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="记录/全库审阅_20261018")
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--to", dest="end", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit-batches", type=int, default=0)
    a = ap.parse_args()
    qs = list(store.load_all())
    total = len(qs)
    end = a.end or total
    start = max(1, a.start)
    outdir = ROOT / a.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    # 索引
    with (outdir / "索引.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["全局序号", "册号", "题号", "题型", "难度", "年份", "来源", "解析来源", "解析字数"])
        for i, q in enumerate(qs, 1):
            w.writerow([f"{i:06d}", (i - 1) // PER + 1, q.key,
                        QTYPE_LABEL.get(q.type, q.type), q.difficulty,
                        q.meta.get("year") or "", q.meta.get("source_label") or "",
                        q.meta.get("solution_source") or "", len((q.solution or "").strip())])
    batches = []
    for b, lo in enumerate(range(start, min(end, total) + 1, PER), 1):
        hi = min(lo + PER - 1, total)
        items = [(i, qs[i - 1]) for i in range(lo, hi + 1)]
        batches.append((b + (start - 1) // PER, items))
    if a.limit_batches:
        batches = batches[:a.limit_batches]
    print("total", total, "batches", len(batches), "out", outdir)
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        futs = [ex.submit(do_batch, b, items, total, outdir) for b, items in batches]
        for n, fut in enumerate(as_completed(futs), 1):
            b, ok, msg = fut.result()
            print(("✓" if ok else "✗"), b, msg)
            if not ok:
                failed.append((b, msg))
    print("done", len(batches) - len(failed), "/", len(batches), "failed", len(failed))
    if failed:
        (outdir / "失败.txt").write_text("\n\n".join("batch %s\n%s" % x for x in failed), encoding="utf-8")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
