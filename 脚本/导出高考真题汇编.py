#!/usr/bin/env python3
r"""把题库里的**全部高考真题**排成一份可编译的 LaTeX 汇编。

输出（默认）：`~/Desktop/家教/latex讲义/高考真题汇编/`

    高考数学真题汇编.tex    ← 唯一交付物
    图片/                    ← 正文引用到的图片（内容寻址名）
    build/                   ← xelatex 的中间文件与 PDF

结构：按年份倒序分章（2026 → 1991），同一年内按卷别分节，
题号在每一年内从 1 连续编号；卷末是「参考答案与解析」，年份/题号与题目一一对应。

题目怎么排由 `amti/paper.py` 唯一负责（`preamble()` + `question_tex()`），
本脚本只做「分章分节、编号、答案册」这些文档级编排——不另写一份题目渲染。

用法：

    python3 脚本/导出高考真题汇编.py                # 生成 + 编译
    python3 脚本/导出高考真题汇编.py --no-compile   # 只生成 .tex
    python3 脚本/导出高考真题汇编.py --years 2024,2025  # 只导这两年（试排）
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import paper, store  # noqa: E402
from amti.paths import ROOT as PKG  # noqa: E402

TITLE = "高考数学真题汇编"
IMG_DIR = PKG / "图片"
DEFAULT_OUT = Path.home() / "Desktop" / "家教" / "latex讲义" / "高考真题汇编"

# 卷别的排版顺序：先全国卷（新高考 → 新课标 → 全国 → 大纲），再各省市，
# 最后是跨省联合命题。表里没有的卷别排在最后、按名字排。
REGION_ORDER = [
    "新高考I卷", "新高考II卷",
    "新课标I卷", "新课标II卷", "新课标卷",
    "全国甲卷", "全国乙卷", "全国I卷", "全国II卷", "全国III卷", "全国IV卷", "全国卷",
    "大纲I卷", "大纲II卷", "大纲卷",
    "北京卷", "天津卷", "上海卷", "江苏卷", "浙江卷", "山东卷", "广东卷",
    "福建卷", "湖北卷", "湖南卷", "重庆卷", "四川卷", "陕西卷", "安徽卷",
    "江西卷", "辽宁卷", "河南卷",
    "京蒙皖卷", "京皖卷", "京湘鄂云琼贵卷", "三南卷", "苏豫粤桂卷",
    "豫粤卷", "粤桂卷", "海南、宁夏新课标卷", "四川延考卷",
]
REGION_RANK = {name: i for i, name in enumerate(REGION_ORDER)}

# 同一卷别的文/理、春/秋顺序
SUFFIX_RANK = {
    "": 0, "（文）": 1, "（理）": 2,
    "（春）": 3, "（春文）": 4, "（春理）": 5,
    "（秋）": 6, "（秋文）": 7, "（秋理）": 8,
}

# 题库里这两张 TikZ 图的源码在录入时被 OCR 带坏了：`\frequencyylabel` 那几行
# 前面混进了 `[line width=0.8pt]{0.52}{0};` 这种无主片段，xelatex 直接报
# Undefined control sequence。**只在这一处、只对导出文本**删掉这几行——
# 题库数据一个字不动（改数据得走 fixups，不是导出脚本的事）。
_BAD_TIKZ_LINES = [
    re.compile(r"^\[line width=0\.8pt\]\{0\.52\}\{0\};\s*$", re.M),
    re.compile(r"^\{\$\\frac\{\\text\{频率\}\}\{\\text\{组距\}\}\$\};\s*$", re.M),
    re.compile(r"^;\s*$", re.M),
]


def clean_tex(tex: str) -> str:
    """导出期的兜底修补（不写回题库）。"""
    for pat in _BAD_TIKZ_LINES:
        tex = pat.sub("", tex)
    return tex


def region_base(region: str) -> str:
    return re.sub(r"（.*?）", "", region or "")


def region_key(region: str):
    base = region_base(region)
    suffix = (region or "")[len(base):]
    return (
        REGION_RANK.get(base, len(REGION_ORDER)),
        base,
        SUFFIX_RANK.get(suffix, 99),
        suffix,
        region or "",
    )


def qno(q) -> int:
    """原卷题号（没有就退到 key 末尾那截），用来在同一卷内排序。"""
    raw = str(q.meta.get("source_no") or "").strip()
    if not raw:
        raw = q.key.rsplit("#", 1)[-1] if "#" in q.key else ""
    m = re.search(r"\d+", raw)
    return int(m.group(0)) if m else 0


def load_gaokao(years: set[int] | None) -> dict[int, list]:
    qs = [q for q in store.load_unique() if q.kind == "高考"]
    by_year: dict[int, list] = {}
    for q in qs:
        try:
            y = int(q.meta.get("year"))
        except (TypeError, ValueError):
            continue
        if years and y not in years:
            continue
        by_year.setdefault(y, []).append(q)
    for y, items in by_year.items():
        items.sort(key=lambda q: (region_key(q.meta.get("region") or "未标注卷别"), qno(q), q.key))
    return by_year


def build_tex(by_year: dict[int, list], *, with_answers: bool = True) -> str:
    years = sorted(by_year, reverse=True)
    total = sum(len(v) for v in by_year.values())
    regions = {(q.meta.get("region") or "未标注卷别") for v in by_year.values() for q in v}

    head = [
        "% " + "=" * 72,
        "%% 高考数学真题汇编（%d--%d）" % (min(years), max(years)),
        "% 由 AmTiKu 题库自动生成，请勿手改；题目有误请改 题目/*.tex 后重新导出。",
        "% 编译：xelatex 两遍（目录与交叉引用）。",
        "% 只要题目、不要答案：把下面 \\AMTIanswerstrue 改成 \\AMTIanswersfalse。",
        "% " + "=" * 72,
    ]

    doc: list[str] = paper.preamble(graphicspath="图片", show_answers=False)
    # 这是一本「汇编」，不是一份卷子：页脚只留页码，去掉「数学试题第 N 页（共 M 页）」。
    doc += [
        r"\examsetup{page/show-head=false, page/show-foot=true,"
        r" page/foot-content={第;页}}",
        "",
        r"\newif\ifAMTIanswers",
        r"\AMTIanswerstrue",
        r"\AtBeginDocument{\hypersetup{bookmarksdepth=2}}",
        "",
        r"\begin{document}",
        r"\pagenumbering{Roman}",
    ]

    # ── 扉页 ──
    doc += [
        r"\begin{titlepage}",
        r"\centering",
        r"\vspace*{3.6cm}",
        r"{\Huge\bfseries " + TITLE + r"}\par",
        r"\vspace{1.2em}",
        r"{\LARGE %d--%d}\par" % (min(years), max(years)),
        r"\vspace{2.6em}",
        r"{\large 共 %s 题\quad %d 年\quad %d 个卷别}\par"
        % (f"{total:,}".replace(",", r"\,"), len(years), len(regions)),
        r"\vspace{0.9em}",
        r"{\large 题目卷\quad{}·\quad{}参考答案与解析}\par",
        r"\vfill",
        r"{\large AmTiKu 题库导出}\par",
        r"\vspace{0.5em}",
        r"{\large \today}\par",
        r"\end{titlepage}",
    ]

    # ── 使用说明 ──
    doc += [
        r"\chapter*{使用说明}",
        r"\phantomsection",
        r"\addcontentsline{toc}{chapter}{使用说明}",
        "",
        r"本册收录题库中全部\textbf{高考真题}，共 %s 题，来自 %d 个年份、%d 个卷别。" %
        (f"{total:,}".replace(",", r"\,"), len(years), len(regions)),
        "",
        r"\begin{itemize}",
        r"  \item 按年份倒序分章（%d $\to$ %d），同一年内按卷别分节；" % (max(years), min(years)),
        r"        题号在每一年内从 1 连续编号。",
        r"  \item 每题题干前标注出处，如「（2026 新高考I卷 第1题）」。",
        r"  \item 卷末为「参考答案与解析」，按年份、题号与题目一一对应；"
        r"选择题答案标红，解答题答案栏写「见解析」并附完整解析。",
        r"  \item 本文件用 XeLaTeX 编译两遍即可。只要题目、不要答案时，",
        r"        把导言区的 \verb|\AMTIanswerstrue| 改为 \verb|\AMTIanswersfalse|。",
        r"\end{itemize}",
        "",
        r"\tableofcontents",
        r"\pagenumbering{arabic}",
    ]

    # ── 题目 ──
    for y in years:
        items = by_year[y]
        doc.append(r"\chapter{%d 年}" % y)
        # 同一年内按卷别分节；分节内题干连续编号（exam-zh 在 \chapter 处重置题号）
        by_region: dict[str, list] = {}
        for q in items:
            by_region.setdefault(q.meta.get("region") or "未标注卷别", []).append(q)
        for region in sorted(by_region, key=region_key):
            doc.append(r"\section{%s}" % paper.esc_text(region))
            for i, q in enumerate(by_region[region]):
                if i:
                    doc.append(r"\filbreak")
                doc.append(r"\needspace{4\baselineskip}")
                doc.append(clean_tex(paper.question_tex(
                    q, show_answers=False, show_source=True, with_solution=False)))
                doc.append("")

    # ── 参考答案与解析 ──
    if with_answers:
        doc += [
            r"\ifAMTIanswers",
            r"\chapter*{参考答案与解析}",
            r"\phantomsection",
            r"\addcontentsline{toc}{chapter}{参考答案与解析}",
        ]
        for y in years:
            doc.append(r"\section*{%d 年}" % y)
            doc.append(r"\phantomsection")
            doc.append(r"\addcontentsline{toc}{section}{%d 年}" % y)
            # 与题干同一顺序、同一编号（每章从 1 起）
            idx = 0
            for region in sorted({q.meta.get("region") or "未标注卷别" for q in by_year[y]},
                                 key=region_key):
                for q in [x for x in by_year[y]
                          if (x.meta.get("region") or "未标注卷别") == region]:
                    idx += 1
                    ans = paper.fix_text_specials((q.answer or "").strip()) or "见解析"
                    doc.append(r"\noindent\textbf{%d.}\quad{\color{%s}\textbf{%s}}"
                               % (idx, paper.ANS_RED, ans))
                    doc.append("")
                    if q.has_solution:
                        doc.append(paper.fix_text_specials((q.solution or "").strip()))
                        doc.append("")
                    doc.append(r"\vspace{0.8em}")
                    doc.append("")
        doc.append(r"\fi")

    doc.append(r"\end{document}")
    return "\n".join(head + doc)


def collect_images(tex: str) -> set[str]:
    r"""正文/解析里所有 `\includegraphics{...}` 的文件名。"""
    return set(re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", tex))


def copy_images(names: set[str], out_dir: Path) -> tuple[int, list[str]]:
    img_out = out_dir / "图片"
    img_out.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = []
    for name in sorted(names):
        src = IMG_DIR / name
        if not src.is_file():
            missing.append(name)
            continue
        dst = img_out / name
        if not dst.is_file() or dst.stat().st_size != src.stat().st_size:
            shutil.copy2(src, dst)
            copied += 1
    return copied, missing


def compile_tex(out_dir: Path, tex_name: str, *, timeout: int = 3600) -> tuple[bool, str]:
    build = out_dir / "build"
    build.mkdir(exist_ok=True)
    cmd = ["xelatex", "-interaction=nonstopmode", "-halt-on-error",
           "-output-directory=build", tex_name]
    for run in (1, 2):
        t0 = time.time()
        try:
            p = subprocess.run(cmd, cwd=out_dir, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "第 %d 遍编译超时（%d 秒）" % (run, timeout)
        log = (out_dir / "build" / (Path(tex_name).stem + ".log"))
        tail = ""
        if log.is_file():
            text = log.read_text("utf-8", "ignore")
            errs = [ln for ln in text.splitlines() if ln.startswith("!")]
            tail = errs[0] if errs else text[-400:]
        if p.returncode != 0:
            return False, "第 %d 遍编译失败（%.1fs）：%s" % (run, time.time() - t0, tail[:300])
    pdf = build / (Path(tex_name).stem + ".pdf")
    if not pdf.is_file():
        return False, "编译结束但没有产出 PDF"
    shutil.copy2(pdf, out_dir / pdf.name)
    return True, "%.1f KB" % (pdf.stat().st_size / 1024)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--years", default="", help="只导这些年份，如 2024,2025")
    ap.add_argument("--no-answers", action="store_true", help="不生成答案册")
    ap.add_argument("--no-compile", action="store_true", help="只写 .tex，不编译")
    ap.add_argument("--limit", type=int, default=0, help="每年最多取几题（试排）")
    a = ap.parse_args(argv)

    years = {int(x) for x in re.findall(r"\d{4}", a.years)} if a.years else None
    by_year = load_gaokao(years)
    if not by_year:
        print("没有找到符合条件的高考题")
        return 1
    if a.limit:
        by_year = {y: v[:a.limit] for y, v in by_year.items()}

    tex = build_tex(by_year, with_answers=not a.no_answers)
    a.out.mkdir(parents=True, exist_ok=True)
    tex_name = "高考数学真题汇编.tex"
    (a.out / tex_name).write_text(tex, encoding="utf-8")

    names = collect_images(tex)
    copied, missing = copy_images(names, a.out)

    total = sum(len(v) for v in by_year.values())
    print("已写 %s" % (a.out / tex_name))
    print("  年份 %d 个，题目 %d 道，图片 %d 个（新复制 %d）"
          % (len(by_year), total, len(names), copied))
    if missing:
        print("  ⚠️ 缺图 %d 个：%s" % (len(missing), ", ".join(missing[:8])))

    if a.no_compile or a.limit:
        return 0

    ok, msg = compile_tex(a.out, tex_name)
    print(("  ✓ 编译通过：%s" if ok else "  ✗ 编译失败：%s") % msg)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
