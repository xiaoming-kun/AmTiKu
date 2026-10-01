#!/usr/bin/env python3
r"""赵礼显讲义转录稿 → **可以直接 xelatex 编译的独立 LaTeX 文档**。

只做"拼装"，不自己写导言区和单题渲染——那两样全项目各只有一份：

    amti.paper.preamble(...)   导言区（`_preamble` 的公开入口）
    amti.paper.question_tex()  单题 LaTeX（高考卷形态、答案标红开关、选项自适应列数）
    amti.latex_ir         把 `out/*.tex` 读回 `Question`

**为什么必须走共用入口**：`paper.py` 的注释里记着两次真事故——谁自己另抄一份
导言区，就会漏装某个自定义样式，"抽到那类题整份卷子编译不过"。所以这里
一行 `\documentclass` 都不写。

    python3 脚本/赵礼显讲义出卷.py                # 全部 44 讲
    python3 脚本/赵礼显讲义出卷.py --only 暑假第1讲,秋季第5讲
    python3 脚本/赵礼显讲义出卷.py --compile      # 顺手用 xelatex 编出 PDF
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import latex_ir                                    # noqa: E402
from amti.schema import Question                             # noqa: E402
# ⚠️ 必须 `from amti import paper`：`paper.py` 里是相对导入（`from . import generate`），
# 当顶层模块 import 会直接 ImportError。仓库根下那份 `paper.py` 是同一内容的副本。
from amti import paper as P                                  # noqa: E402

WORK = ROOT / "数据/录题/赵礼显"
OUT = WORK / "out"
DEST = WORK / "预览"
TITLE = "赵礼显 · 2027 届高三数学暑秋讲义（转录稿·学生版·无答案）"


def load_questions(only: set[str] | None) -> list[tuple[str, str, Question]]:
    """→ [(讲次, 题型小节, Question)]，按文件名（讲次）排序。"""
    got: list[tuple[str, str, Question]] = []
    for f in sorted(OUT.glob("*.tex")):
        lect = f.stem
        if only and lect not in only:
            continue
        text = f.read_text(encoding="utf-8")
        for blk in latex_ir.split_questions(text):
            q = latex_ir.parse_question(blk)
            if q is None:
                print("  ⚠️ %s 有一块解析不出来，跳过" % lect)
                continue
            got.append((lect, (q.meta.get("section") or "").strip(), q))
    return got


def build(rows: list[tuple[str, str, Question]]) -> str:
    doc: list[str] = P.preamble(
        title=TITLE,
        graphicspath=str(ROOT / "图片"),
        show_answers=False,          # 学生版：作答位空着、解析不显示
        columns=4,
        first_line="% 由 脚本/赵礼显讲义出卷.py 生成；题库源在 数据/录题/赵礼显/out/",
    )
    doc += [r"\begin{document}", r"\maketitle", ""]
    doc += [
        r"{\small\color{gray}",
        r"本题库为扫描讲义《赵礼显 2027 届高三数学暑秋讲义》的机器转录稿，"
        r"用于校对识别质量。全书没有答案，故作答位一律留空。",
        r"\\[2pt] 计 %d 讲、%d 道题。\par}" % (
            len({r[0] for r in rows}), len(rows)),
        "",
        # ⚠️ **`tocdepth` 必须自己抬起来**：exam-zh 默认把它压到 0 以下，
        # `\tableofcontents` 于是只印出「目录」两个字、条目不显示——
        # 而且 `.toc` 文件里条目是**齐的**，看文件完全看不出问题，
        # 只有把 PDF 的文本层抽出来看才发现（"构建成功 ≠ 渲染正确"）。
        r"\setcounter{tocdepth}{1}",
        r"\tableofcontents",
        r"\clearpage",
        "",
    ]
    cur_lect, cur_sec = None, None
    for lect, sec, q in rows:
        if lect != cur_lect:
            cur_lect, cur_sec = lect, None
            doc += [r"\section{%s}" % P.esc_text(_lect_title(rows, lect))]
        if sec and sec != cur_sec:
            cur_sec = sec
            doc += [r"\subsection*{%s}" % P.esc_text(sec)]
        doc += [P.question_tex(q, show_answers=False), ""]
    doc += [r"\end{document}", ""]
    return "\n".join(doc)


_TITLES: dict[str, str] = {}


def _lect_title(rows, lect: str) -> str:
    """讲次短名 → 卷面标题（用转录回来的**书上的长标题**，不是我编的短名）。"""
    for le, _s, q in rows:
        if le == lect:
            full = (q.meta.get("lecture_title") or "").strip()
            return "%s　%s" % (lect, full) if full else lect
    return lect


def main() -> int:
    ap = argparse.ArgumentParser(description="赵礼显讲义 → 独立 LaTeX 文档")
    ap.add_argument("--only", default="", help="只出这几讲，逗号分隔的短名")
    ap.add_argument("--compile", action="store_true", help="顺手 xelatex 编 PDF")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    rows = load_questions(only)
    if not rows:
        print("没有可出的题——先跑 build")
        return 1
    DEST.mkdir(parents=True, exist_ok=True)
    name = a.out or ("赵礼显讲义.tex" if not only else "赵礼显讲义-样张.tex")
    tex = DEST / name
    tex.write_text(build(rows), encoding="utf-8")
    print("写出 %s（%d 道题，%d 字节）" % (tex, len(rows), tex.stat().st_size))

    if a.compile:
        # **三趟**：目录（`\tableofcontents`）会让页数变化，而页脚「共 N 页」
        # 走的是 `lastpage` 宏、读的是**上一趟**写下的 `.aux`。只跑两趟时
        # 真实 10 页、页脚印"共 8 页"——这种"构建成功 ≠ 内容正确"的坑，
        # 项目里已经踩过一次（见 AGENTS.md 六·2）。第三趟把页码收稳。
        # `-interaction=nonstopmode` 是不让一个排版小毛病把整趟编译卡在
        # 交互提示上（批处理必须有这一条）。
        for i in (1, 2, 3):
            r = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 "-file-line-error", tex.name],
                cwd=DEST, capture_output=True, text=True)
            print("  xelatex 第 %d 趟：退出码 %d" % (i, r.returncode))
            if r.returncode != 0:
                lines = (r.stdout or "").splitlines()
                print("\n".join(lines[-25:]))
                return 1
        pdf = tex.with_suffix(".pdf")
        print("PDF：%s（%.1f MB）" % (pdf, pdf.stat().st_size / 1e6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
