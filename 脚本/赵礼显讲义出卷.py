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
import json
import re
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

# 这几个是**默认值**（赵礼显那一批）。别的批次用 `--work` 覆盖——
# 复制一份脚本出来改路径 = 两个真相，改一处忘一处（KaTeX 检查器同理）。
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
        # ⚠️ **必须自己把 `%% @q {...}` 那行读出来。**
        # `latex_ir.parse_question(blk)` 只解析**正文**，返回的 `meta` 是**空的** ——
        # 于是 `meta.get("section")` 永远是 None，产物里一个小节标题都不会有，
        # 而且 `lecture_title`、`origin_pdf_page`、`figure_todo` 这些也全被丢掉。
        # （`store.py` 那条路是**另外**解析 `%% @q` 行的，所以在题库里看不出来。）
        blocks = list(re.finditer(r"^%% @q (\{.*?\})\n(.*?)(?=^%% @q |\Z)",
                                  text, re.M | re.S))
        if not blocks:
            print("  ⚠️ %s 里没有 `%%%% @q` 元数据行，跳过" % lect)
            continue
        for m in blocks:
            try:
                meta = json.loads(m.group(1))
            except Exception:                               # noqa: BLE001
                print("  ⚠️ %s 有一条元数据坏了，跳过" % lect)
                continue
            q = latex_ir.parse_question(m.group(2))
            if q is None:
                print("  ⚠️ %s 有一块解析不出来，跳过" % lect)
                continue
            # ⚠️ `section` 是**嵌套**在 `meta` 里的：
            # `{"key":…, "stem":…, "meta":{"book":…, "section":…}}`。
            # 第一版把**外层**整个赋给 `q.meta`，于是 `q.meta.get("section")`
            # 还是拿不到（要 `q.meta["meta"]["section"]`）—— 白修一轮。
            # `Question.meta` 对应的就是**内层**那本账。
            inner = meta.get("meta") or {}
            q.meta = inner
            # ⚠️ 取 `section` 也得从**内层**取。第一版这里还写着
            # `meta.get("section")`（外层）—— `q.meta` 修对了、这一行没跟着改，
            # 于是产物里照样一个小节都没有。**改一处要顺着看它周围的取值。**
            got.append((lect, (inner.get("section") or "").strip(), q))
    return got


def build(rows: list[tuple[str, str, Question]]) -> str:
    doc: list[str] = P.preamble(
        title=TITLE,
        graphicspath=str(ROOT / "图片"),
        show_answers=False,          # 学生版：作答位空着、解析不显示
        columns=4,
        first_line="%% 由 脚本/赵礼显讲义出卷.py 生成；题库源在 %s"
                   % OUT.relative_to(ROOT),
    )
    doc += [r"\begin{document}", r"\maketitle", ""]
    doc += [
        r"{\small\color{gray}",
        r"本稿为 %s 的机器转录稿，用于校对识别质量。" % P.esc_text(TITLE),
        r"原资料没有答案栏，故作答位一律留空。",
        r"\\[2pt] 计 %d 份、%d 道题。\par}" % (
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
            doc += [r"\subsection*{%s}" % _sec_tex(sec)]
        doc += [P.question_tex(q, show_answers=False), ""]
    doc += [r"\end{document}", ""]
    return "\n".join(doc)


_TITLES: dict[str, str] = {}


def _sec_tex(s: str) -> str:
    r"""小节名 → `\subsection*` 里的写法：**数学部分保持数学**，其余转义。

    ⚠️ 实测：小节名「选项包含 `$(-1)^n$` 的问题」整串走 `P.esc_text`
    转义后，PDF 上印成**字面的 `$(-1)^n$`**（连 `$` 都留在纸上、
    数学没渲染）—— 因为 `esc_text` 是给**纯文本标题**用的，
    而小节名里带数学。按 `$` 切开、奇数段送数学、偶数段转义即可。
    """
    out, math = [], False
    for part in s.split("$"):
        out.append(part if math else P.esc_text(part))
        math = not math
    return "$".join(out)


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
    ap.add_argument("--work", default="", help="产物目录（out/ 在其中），默认赵礼显那批")
    ap.add_argument("--title", default="", help="卷面标题")
    a = ap.parse_args()

    global WORK, OUT, DEST, TITLE
    if a.work:
        WORK = (ROOT / a.work) if not Path(a.work).is_absolute() else Path(a.work)
        OUT, DEST = WORK / "out", WORK / "预览"
        TITLE = a.title or ("%s 转录稿（学生版·无答案）" % WORK.name)
    elif a.title:
        TITLE = a.title

    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    rows = load_questions(only)
    if not rows:
        print("没有可出的题——先跑 build")
        return 1
    DEST.mkdir(parents=True, exist_ok=True)
    name = a.out or (("%s.tex" % WORK.name) if not only
                     else "%s-样张.tex" % WORK.name)
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
        # ⚠️ **趟数不能写死。** 原来写的是"跑三趟"，注释里的理由是
        # "目录会让页数变化、`lastpage` 读的是上一趟的 `.aux`"。
        # 但 2026-10-02 实测：只有 2 份材料时，目录在第 2→3 趟之间
        # **才**从 1 页涨到 2 页 —— 真实 8 页、页脚却印「共 6 页」，
        # 而且三趟都退出码 0、PDF 也正常生成，**只有把文本层抽出来看才发现**。
        # （赵礼显那批 44 讲、目录一开始就是多页，三趟碰巧够。所以这个
        #    bug 一直藏着。）
        # 改成**迭代到收敛**：页数不再变、且 `.aux` 里记的 `LastPage`
        # 等于真实页数时，再跑尾趟把页脚收稳。
        def _pages(p: Path) -> int:
            try:
                import fitz
                with fitz.open(p) as d:
                    return d.page_count
            except Exception:                               # noqa: BLE001
                return -1

        def _lastpage(p: Path) -> str:
            try:
                m = re.search(r"\\newlabel\{LastPage\}\{\{[^}]*\}\{([^}]*)\}",
                              p.read_text(encoding="latin-1"))
                return m.group(1) if m else ""
            except Exception:                               # noqa: BLE001
                return ""

        def _run(i: int) -> int:
            r = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
                 "-file-line-error", tex.name],
                cwd=DEST, capture_output=True, text=True)
            print("  xelatex 第 %d 趟：退出码 %d" % (i, r.returncode))
            if r.returncode != 0:
                print("\n".join((r.stdout or "").splitlines()[-25:]))
            return r.returncode

        aux, pdfp = tex.with_suffix(".aux"), tex.with_suffix(".pdf")
        rc, prev_lp, i = 0, None, 0
        while i < 8:
            i += 1
            rc = _run(i)
            if rc != 0:
                return 1
            n, lp = _pages(pdfp), _lastpage(aux)
            # ⚠️ **判据是 `lastpage` 稳不稳，不是"PDF 总页数 == lastpage"。**
            # 我第一版就是拿这两个比，结果永远不收敛——因为 exam-zh 的页面
            # 分两段：「封面 + 目录」是前置页，正文**另外从 1 编**。
            # 实测 8 页的 PDF：物理 1=封面、物理 2=目录（不编号）、
            # 物理 3–8 编号 1–6，`lastpage=6` **完全正确**。
            # 拿总页数去比等于把"前置页"也算成正文，会误报成一个不存在的 bug。
            stable = (lp != "" and lp == prev_lp)
            print("     PDF %s 页（含封面/目录），正文页脚 lastpage=%s%s"
                  % (n, lp or "?", "   ← 已收敛" if stable else ""))
            if stable:
                i += 1
                rc = _run(i)                    # 尾趟：把页脚印成收稳后的值
                if rc != 0:
                    return 1
                print("     收稳：正文页脚 lastpage=%s" % _lastpage(aux))
                break
            prev_lp = lp
        else:
            print("  ⚠️ 跑了 8 趟还没收敛，页脚「共 N 页」可能是旧值——"
                  "去 PDF 文本层核一遍")
        pdf = tex.with_suffix(".pdf")
        print("PDF：%s（%.1f MB）" % (pdf, pdf.stat().st_size / 1e6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
