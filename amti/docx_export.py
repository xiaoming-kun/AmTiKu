"""AmTiKu · Word（DOCX）导出

PDF 仍走 exam-zh；Word 走另一条**干净 Markdown → Pandoc** 的路径：

    Question → latex_blocks 块级 IR → Markdown → pandoc → .docx

为什么不用 Pandoc 直接转 exam-zh 的 TeX：exam-zh 的 `question/choices/
solution` 环境和自定义宏 Pandoc 不认，实测会把 `\\symbfit`、选项标签、
分数表弄成半截文本。Markdown 路径只依赖 `$...$` 公式和图片，Pandoc
处理得最好。

**这不是第二套 LaTeX 解析器**：正文仍由 `latex_blocks.parse_blocks`
解析，这里只负责把 IR 画成 Markdown。

Pandoc 是外部依赖；没装就明确报错，不静默退回“假 Word”。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import latex_blocks as lb
from . import paper as _paper
from . import store
from .images import IMG_DIR
from .paths import OUT_DIR

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")
_DISPLAY_TYPES = ("single_choice", "multi_choice")


def _md_text(s: str) -> str:
    r"""正文转义；不碰 `$…$`（公式由 IR 单独产出）。"""
    return _MD_SPECIAL.sub(r"\\\1", str(s or ""))


def _fix_tex(tex: str) -> str:
    """把 exam-zh/项目自定义宏换成 Pandoc 认的写法。"""
    s = str(tex or "")
    s = s.replace(r"\symbfit", r"\boldsymbol").replace(r"\symbf", r"\mathbf")
    s = s.replace(r"\iu", r"\mathrm{i}").replace(r"\upi", r"\pi")
    s = s.replace(r"\eu", r"\mathrm{e}")
    s = re.sub(r"\\R(?![a-zA-Z])", r"\\mathbb{R}", s)
    s = re.sub(r"\\Z(?![a-zA-Z])", r"\\mathbb{Z}", s)
    s = re.sub(r"\\N(?![a-zA-Z])", r"\\mathbb{N}", s)
    s = s.replace(r"\leqslant", r"\leq").replace(r"\geqslant", r"\geq")
    s = s.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
    s = s.replace(r"\mbox", r"\text")
    return s.replace("\n", " ").strip()


def _inline(nodes) -> str:
    out: list[str] = []
    for n in nodes or ():
        t = n.get("t")
        if t == "s":
            out.append(_md_text(n.get("s", "")))
        elif t == "m":
            out.append("$%s$" % _fix_tex(n.get("s", "")))
        elif t == "fig":
            out.append(_img(n.get("id", "")))
        elif t == "blank":
            out.append("______")
        elif t == "paren":
            out.append("（　　）")
        elif t == "br":
            out.append("  \n")
        elif t == "sp":
            out.append("　")
        elif t == "raw":
            out.append(_md_text(n.get("s", "")))
    return "".join(out)


def _img(name: str) -> str:
    n = str(name or "")
    if not n or Path(n).name != n or not (IMG_DIR / n).is_file():
        return ""
    return "![图](%s)" % n


def _blocks(blocks, indent: str = "") -> str:
    out: list[str] = []
    for b in blocks or ():
        t = b.get("t")
        if t == "p":
            out.append(indent + _inline(b.get("in", [])))
        elif t == "math":
            out.append(indent + "$$%s$$" % _fix_tex(b.get("tex", "")))
        elif t == "list":
            lines: list[str] = []
            for i, item in enumerate(b.get("items", [])):
                marker = ("%d. " % (i + 1)) if b.get("ordered") else "- "
                inner = _blocks(item, indent + "   ").splitlines() or [""]
                inner[0] = indent + marker + inner[0].lstrip()
                lines.extend(inner)
            out.append("\n".join(lines))
        elif t == "table":
            rows = b.get("rows") or []
            if not rows:
                continue

            def cell(c) -> str:
                if "in" in c:
                    v = _inline(c.get("in", []))
                elif "blocks" in c:
                    v = _blocks(c.get("blocks", []))
                else:
                    v = ""
                return v.replace("|", r"\|").replace("\n", " ").strip()

            ncol = max(len(r) for r in rows)
            first = list(rows[0]) + [{}] * (ncol - len(rows[0]))
            lines = ["| " + " | ".join(cell(c) for c in first) + " |",
                     "|" + "|".join(["---"] * ncol) + "|"]
            for r in rows[1:]:
                r = list(r) + [{}] * (ncol - len(r))
                lines.append("| " + " | ".join(cell(c) for c in r) + " |")
            out.append("\n".join(lines))
        elif t == "box":
            out.append(_blocks(b.get("blocks", []), indent))
        elif t == "fig":
            out.append(indent + _img(b.get("id", "")))
        elif t == "raw":
            out.append(indent + "（图：%s，Word 版不渲染）" % b.get("env", "TikZ"))
    return "\n\n".join(x for x in out if x and x.strip())


def _question_md(q, n: int, show_source: bool) -> str:
    head = "**%d.** " % n
    src = _paper.source_label(q) if show_source else ""
    if src:
        head += "（%s）" % _md_text(src)
    body = _blocks(lb.parse_blocks(q.stem, parts=True))
    parts = [head + body]
    if q.options:
        opts = []
        for o in q.options:
            txt = _blocks(lb.parse_blocks(o.text, parts=True))
            opts.append("%s. %s" % (_md_text(o.label), txt))
        # 两个空格 + 换行 = Markdown 硬换行，Word 里四个选项不会挤成一行
        parts.append("  \n".join(opts))
    return "\n\n".join(parts)


def _answer_md(q, n: int) -> str:
    parts = []
    if (q.answer or "").strip():
        parts.append("**%d.** 答案：%s" % (n, _fix_tex(q.answer)))
    sol = _blocks(lb.parse_blocks(q.solution, parts=True)) if q.solution else ""
    if sol:
        parts.append("解析：" + sol)
    return "\n\n".join(parts)


def render_markdown(questions, *, title: str = "", show_answers: bool = False,
                    answers_at_end: bool = False,
                    show_source: bool = True) -> str:
    groups = [("一、选择题", _DISPLAY_TYPES),
              ("二、填空题", ("fill_in_blank",)),
              ("三、解答题", ("detailed_answer",))]
    known = {t for _sec, types in groups for t in types}
    # **先按卷面顺序排好，再统一编号**：答案页/题号必须与卷面一致，
    # 不能按传入 keys 的原始顺序编号（组卷可能把解答题排在前面）。
    sections = [(sec, [q for q in questions if q.type in types])
                for sec, types in groups]
    rest = [q for q in questions if q.type not in known]
    if rest:
        sections.append(("其他", rest))
    ordered = [(sec, qs) for sec, qs in sections if qs]

    title = (title or "数学试卷").strip()
    out = ["# " + _md_text(title), "", "共 %d 题。" % len(questions), ""]
    n = 0
    for sec, qs in ordered:
        out += ["## " + sec, ""]
        for q in qs:
            n += 1
            out += [_question_md(q, n, show_source), ""]
            if show_answers and not answers_at_end:
                a = _answer_md(q, n)
                if a:
                    out += [a, ""]

    if show_answers and answers_at_end:
        out += ["## 参考答案与解析", ""]
        n = 0
        for _sec, qs in ordered:
            for q in qs:
                n += 1
                a = _answer_md(q, n)
                if a:
                    out += [a, ""]
    return "\n".join(out).rstrip() + "\n"


def export_docx(keys: list[str], *, title: str = "",
                show_answers: bool = False, answers_at_end: bool = False,
                show_source: bool = True) -> dict:
    keys = [k for k in dict.fromkeys(k.strip() for k in keys or []) if k]
    if not keys:
        return {"ok": False, "error": "没有选题目"}
    by = store.read_many(keys)
    missing = [k for k in keys if k not in by]
    if missing:
        return {"ok": False, "error": "这些题不存在：%s" % "、".join(missing[:5])}
    qs = [by[k] for k in keys]

    pandoc = shutil.which("pandoc")
    if not pandoc:
        return {"ok": False,
                "error": "没有找到 pandoc。Word 导出需要 Pandoc（brew install pandoc / choco install pandoc）。"}

    md = render_markdown(qs, title=title, show_answers=show_answers,
                         answers_at_end=answers_at_end, show_source=show_source)
    out_dir = OUT_DIR / "Word"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", (title or "数学试卷")).strip("_")[:80] or "数学试卷"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    docx_path = out_dir / ("%s_%s.docx" % (safe, stamp))

    tmp = Path(tempfile.mkstemp(prefix="amti-docx-", suffix=".md")[1])
    try:
        tmp.write_text(md, encoding="utf-8")
        r = subprocess.run(
            [pandoc, str(tmp), "-f", "markdown+tex_math_dollars",
             "-t", "docx", "-o", str(docx_path),
             "--resource-path", str(IMG_DIR)],
            capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            return {"ok": False,
                    "error": "Pandoc 转换失败：%s" % (r.stderr or r.stdout or "")[:500]}
        if not docx_path.is_file() or docx_path.stat().st_size == 0:
            return {"ok": False, "error": "Pandoc 没有产出 DOCX"}
        rel = docx_path.relative_to(OUT_DIR).as_posix()
        return {"ok": True, "docx_abs": str(docx_path), "docx_rel": rel,
                "n": len(qs), "bytes": docx_path.stat().st_size,
                "warnings": (r.stderr or "")[:800]}
    finally:
        tmp.unlink(missing_ok=True)


def _selftest() -> int:
    from .schema import Option, Question

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    q = Question(key="t/1", type="single_choice",
                 stem=r"已知 $\cos B=\frac{3}{4}$，则 \paren[A]",
                 options=[Option("A", r"$\frac{3}{5}$"), Option("B", r"$\frac{4}{5}$")],
                 answer="A", solution=r"由 $\sin^2 B+\cos^2 B=1$ 得 $\sin B=\frac{4}{5}$。")
    md = render_markdown([q], title="测试卷", show_answers=True, answers_at_end=True)
    check("标题", md.startswith("# 测试卷"))
    check("选项 A/B", "A. " in md and "B. " in md)
    check("公式保留", r"$\cos B" in md or r"$\boldsymbol" in md)
    check("答案页", "参考答案与解析" in md and "答案：A" in md)
    check("没有 \\symbfit", r"\symbfit" not in md)
    print("docx_export 自检 %s（%d 项失败）"
          % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
