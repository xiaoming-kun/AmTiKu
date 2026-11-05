r"""导出「机器解析质量抽检」PDF。

抽样：当前 `solution_source=workbuddy` 的解析，500 道 =
全部高风险（最多 50）+ 随机补足；随机种子固定，可复现。
只读题库，不改任何数据。
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from amti import paper, store          # noqa: E402
from amti.schema import QTYPE_LABEL    # noqa: E402
from amti.paths import ROOT as P       # noqa: E402

XELATEX = "/Users/ximing/texlive/2026/bin/universal-darwin/xelatex"
SEED = 20261018
N = 500
MAX_HIGH = 50


def risk_flags(q) -> list[str]:
    s = (q.solution or "").strip()
    f = []
    if s.startswith("依据库中源文件") or (s and s == (q.answer or "").strip()):
        f.append("只写答案")
    if re.search(r"(^|[。；;\s])略([。；;\s]|$)|解析略|略。", s):
        f.append("写略")
    if any(x in s for x in ("无法求解", "无法确定", "缺少", "无图", "题干不全", "题目不完整")):
        f.append("无法求解")
    if len(s) < 50:
        f.append("过短")
    if re.search(r"^(数学参考答案及评分意见|参考答案、提示及评分细则|第[（(]\d+[）)]问补充其他解法)", s):
        f.append("截断")
    return f


def choose(limit: int = N):
    qs = [q for q in store.load_all() if (q.meta or {}).get("solution_source") == "workbuddy"]
    high = [q for q in qs if risk_flags(q)]
    high.sort(key=lambda q: q.key)
    high = high[:MAX_HIGH]
    if len(high) > limit:
        high = high[:limit]
    hk = {q.key for q in high}
    rest = [q for q in qs if q.key not in hk]
    rng = random.Random(SEED)
    rng.shuffle(rest)
    need = max(0, limit - len(high))
    sample = high + rest[:need]
    return qs, high, sample


def build_tex(sample, total_work, high_n, limit: int) -> str:
    doc = paper.preamble(show_answers=True, graphicspath=str(P / "图片"),
                         extra=[r"\usepackage{fancyhdr}"])
    doc += [r"\begin{document}", r"\setlength{\parindent}{0pt}",
            r"\pagestyle{fancy}", r"\fancyhf{}",
            r"\fancyhead[L]{\small 机器解析质量抽检}",
            r"\fancyhead[R]{\small workbuddy}",
            r"\fancyfoot[C]{\small 第 \thepage\ 页 / 共 \pageref{LastPage} 页}"]
    # 封面
    doc += [
        r"\thispagestyle{empty}",
        r"\begin{center}",
        r"{\LARGE\bfseries 机器解析质量抽检}\\[6pt]",
        r"{\large workbuddy 生成解析 · %d 道}\\[16pt]" % limit,
        r"\end{center}",
        r"\begin{tabular}{@{}ll@{}}",
        r"生成日期 & 2026-10-18\\",
        r"当前 workbuddy 解析 & %d 道\\" % total_work,
        r"抽样 & %d 道高风险 + %d 道随机（seed %d）\\" % (high_n, limit - high_n, SEED),
        r"用途 & 人工抽查，不自动改题\\",
        r"\end{tabular}\par",
        r"\vspace{14pt}",
        r"\textbf{怎么看}\par",
        r"\begin{itemize}",
        r"  \item 先看题干和答案，再看解析；解析里的数学步骤按你平时的标准判断。",
        r"  \item 在每题下面的方框里勾一个：通过 / 只写答案 / 写略 / 无法求解 / 截断 / 答案不一致。",
        r"  \item “只写答案”=没有推导，只写“选 B/答案 C”；“写略”=出现“略/同理/略去”；",
        r"  \item “无法求解”=解析自己说缺条件/少图；“截断”=解析开头是答案页标题或半句话。",
        r"\end{itemize}",
        r"\textbf{这批怎么抽的}：高风险题全部放进前面；其余随机抽，用来估计整体缺陷率。",
        r"因此前面一段的缺陷率会偏高，不能直接当整体比例。",
        r"\vspace{8pt}",
        r"\textbf{汇总（看完后填）}\par",
        r"\vspace{4pt}",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 通过 \quad",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 只写答案 \quad",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 写略 \quad",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 无法求解 \quad",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 截断 \quad",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 答案不一致 \quad",
        r"\framebox[8pt]{\rule{0pt}{6pt}}\ 其他\par",
        r"\vspace{6pt}\hrule\vspace{8pt}",
    ]
    # 正文
    for i, q in enumerate(sample, 1):
        if i == 1:
            doc += [r"\section*{A. 高风险（全部）}", r"\vspace{-4pt}"]
        if i == high_n + 1:
            doc += [r"\clearpage", r"\section*{B. 随机抽样}", r"\vspace{-4pt}"]
        flags = risk_flags(q)
        meta = " · ".join(x for x in [
            QTYPE_LABEL.get(q.type, q.type), q.difficulty,
            str(q.meta.get("year") or ""), str(q.meta.get("source_label") or ""),
        ] if x)
        doc += [
            r"\needspace{18\baselineskip}",
            r"{\small\bfseries 抽检 %03d}\hfill{\scriptsize\ttfamily %s}\par" % (i, paper.esc_text(q.key)),
            r"{\scriptsize %s}\par" % paper.esc_text(meta),
        ]
        if flags:
            doc += [r"{\scriptsize\bfseries\color{red}风险标记：%s}\par" % paper.esc_text("、".join(flags))]
        doc += [
            r"\vspace{2pt}",
            paper.question_tex(q, show_answers=True, show_source=True),
            r"\vspace{2pt}\noindent"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 通过 \quad"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 只写答案 \quad"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 写略 \quad"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 无法求解 \quad"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 截断 \quad"
            r"\framebox[8pt]{\rule{0pt}{6pt}}\ 答案不一致\par",
            r"\vspace{4pt}\hrule\vspace{6pt}",
        ]
    doc += [r"\end{document}"]
    return "\n".join(doc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=N)
    ap.add_argument("--out", default="记录/机器解析抽检_20261018.pdf")
    a = ap.parse_args()
    qs, high, sample = choose(a.limit)
    print("workbuddy", len(qs), "high", len(high), "sample", len(sample))
    # 只保留实际用到的“高风险”数量（若 limit < high_n）
    high_n = min(len(high), len(sample))
    tex = build_tex(sample, len(qs), high_n, len(sample))
    texdir = ROOT / "数据" / "题库审阅"
    texdir.mkdir(parents=True, exist_ok=True)
    stem = "机器解析抽检_20261018" if a.limit == N else "机器解析抽检_pilot"
    texp = texdir / (stem + ".tex")
    texp.write_text(tex, encoding="utf-8")
    # manifest
    csvp = texdir / (stem + ".csv")
    with csvp.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["编号", "分区", "题号", "题型", "难度", "年份", "来源", "风险", "解析字数"])
        for i, q in enumerate(sample, 1):
            w.writerow([i, "高风险" if q in high else "随机", q.key,
                        QTYPE_LABEL.get(q.type, q.type), q.difficulty,
                        q.meta.get("year") or "", q.meta.get("source_label") or "",
                        "、".join(risk_flags(q)), len((q.solution or "").strip())])
    for run in (1, 2):
        r = subprocess.run([XELATEX, "-interaction=nonstopmode", "-halt-on-error",
                            "-output-directory", str(texdir), str(texp)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=900)
        print("xelatex", run, "exit", r.returncode)
        if r.returncode:
            print(r.stdout[-3000:])
            return 1
    pdf = texdir / (stem + ".pdf")
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    if pdf.exists():
        out.write_bytes(pdf.read_bytes())
    print("PDF", out, out.stat().st_size if out.exists() else "missing")
    print("TEX", texp)
    print("CSV", csvp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
