"""AmTiKu · 讲义 tex → HTML（KaTeX 渲染）

桌面上的讲义是 elegantbook 的 LaTeX。这里把它拆成「网页版讲义」：

    tex 正文  ──预处理──▶  pandoc  ──▶  HTML 片段
                 │
                 ├─ TikZ 图：单独编译成 PNG（KaTeX 管不了 TikZ）
                 ├─ \\begin{equation}/align：编号、去掉 label，\\eqref 换成 (n)
                 └─ definition/theorem/proposition：保留成 div，标题由我们补

产物（缓存，不进 git）：
    数据/专题/讲义/<考点id>/index.html
    数据/专题/讲义/<考点id>/fig-N.png

前端拿到 HTML 后，把 `<span class="math inline|display">` 里的 TeX 交给 KaTeX 渲染。
"""
from __future__ import annotations

from .paths import ROOT
import html as html_mod
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import topics

LECT_DIR = topics.TOPIC_DIR / "讲义"

# 环境 → 显示名（和讲义里 \renewcommand{\definitionname}{知识点} 对齐）
ENV_NAME = {
    "definition": "知识点",
    "theorem": "方法",
    "proposition": "核心思路",
    "example": "例",
    "introduction": "内容提要",
}

_TIKZ = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.S)
_EQ = re.compile(r"\\begin\{equation\}(.*?)\\end\{equation\}", re.S)
_ALIGN = re.compile(r"\\begin\{align\}(.*?)\\end\{align\}", re.S)


def _body(tex_path: Path) -> str:
    s = tex_path.read_text(encoding="utf-8")
    i = s.index("\\begin{document}")
    j = s.index("\\end{document}")
    return s[i + len("\\begin{document}"):j]


def _number_equations(body: str) -> tuple[str, dict[str, int]]:
    r"""给 equation/align 编号，\label → 编号，\eqref 换成 (n)。"""
    labels: dict[str, int] = {}
    n = 0

    def eq(m: re.Match) -> str:
        nonlocal n
        n += 1
        inner = m.group(1)
        for lab in re.findall(r"\\label\{([^}]+)\}", inner):
            labels[lab] = n
        inner = re.sub(r"\\label\{[^}]+\}", "", inner)
        inner = re.sub(r"\\notag|\\nonumber", "", inner)
        return "\\begin{equation}" + inner + "\\end{equation}"

    def al(m: re.Match) -> str:
        nonlocal n
        n += 1
        inner = m.group(1)
        for lab in re.findall(r"\\label\{([^}]+)\}", inner):
            labels[lab] = n
        inner = re.sub(r"\\label\{[^}]+\}", "", inner)
        inner = re.sub(r"\\notag|\\nonumber", "", inner)
        return "\\begin{align}" + inner + "\\end{align}"

    body = _EQ.sub(eq, body)
    body = _ALIGN.sub(al, body)
    body = re.sub(r"\\eqref\{([^}]+)\}", lambda m: "(%d)" % labels.get(m.group(1), 0), body)
    body = re.sub(r"\\label\{[^}]+\}", "", body)
    return body, labels


def _preamble_macros(tex_path: Path) -> str:
    r"""讲义导言区里自定义的 \newcommand（图里会用，比如 \va=\boldsymbol{a}）。"""
    src = tex_path.read_text(encoding="utf-8")
    pre = src[:src.index("\\begin{document}")]
    keep = []
    lines = pre.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"\s*\\(?:newcommand|providecommand|DeclareMathOperator)\b", line):
            buf = line
            # 宏体可能跨行（\drawcube 这种带 % 换行的），按花括号配平接着收
            while buf.count("{") > buf.count("}") and i + 1 < len(lines):
                i += 1
                buf += "\n" + lines[i]
            keep.append(buf)
        i += 1
    return "\n".join(keep)


def _compile_fig(code: str, out_png: Path, extra: str = "") -> bool:
    """一个 tikzpicture → standalone PDF → PNG（300dpi）。"""
    doc = (r"\documentclass[tikz,border=6pt]{standalone}" "\n"
           r"\usepackage{ctex}\usepackage{amsmath,amssymb}\usepackage{xcolor}" "\n"
           r"\usepackage{tikz,pgfplots}\pgfplotsset{compat=1.17}" "\n"
           r"\usetikzlibrary{arrows.meta,calc,positioning,decorations.markings,angles,quotes,"
           r"intersections,patterns,patterns.meta,3d,through,backgrounds,fit,shapes.geometric}" "\n"
           r"\usepgfplotslibrary{groupplots,fillbetween}" "\n"
           + (extra + "\n" if extra else "")
           + r"\begin{document}" "\n" + code + "\n" + r"\end{document}" "\n")
    tmp = Path(tempfile.mkdtemp(prefix="amti-fig-"))
    try:
        (tmp / "f.tex").write_text(doc, encoding="utf-8")
        r = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "f.tex"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        if r.returncode != 0 or not (tmp / "f.pdf").exists():
            return False
        import pymupdf
        with pymupdf.open(tmp / "f.pdf") as d:
            pix = d[0].get_pixmap(dpi=300)
            out_png.parent.mkdir(parents=True, exist_ok=True)
            pix.save(out_png)
        return True
    except Exception:
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _env_titles(body: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for env in ENV_NAME:
        out[env] = re.findall(
            r"\\begin\{%s\}(?:\[([^\]]*)\])?" % env, body)
    return out


_ENV_RE = re.compile(r"\\(begin|end)\{([^{}]+)\}")
_SRC_MARK = "AMTIKASRC"
_SRC_RE = re.compile(r"<p>\s*<code>\s*AMTIKASRC(\d+)\s*</code>\s*</p>", re.I)


def _source_units(body: str) -> list[tuple[int, int]]:
    """把 TeX 正文切成顶层段落/环境，返回原文中的 [start, end)。

    不追求完整 TeX 解析：只要不在 \\begin...\\end 或显示公式内部切断，
    就能把网页块和源码位置对上。切不准时前端会回退到整节编辑。
    """
    units: list[tuple[int, int]] = []
    depth = 0
    math = 0
    start = 0
    pos = 0
    for line in body.splitlines(keepends=True):
        if not line.strip() and depth == 0 and math == 0:
            a, b = start, pos
            while a < b and body[a].isspace(): a += 1
            while b > a and body[b - 1].isspace(): b -= 1
            if b > a: units.append((a, b))
            start = pos + len(line)
        for m in _ENV_RE.finditer(line):
            depth += 1 if m.group(1) == "begin" else -1
            if depth < 0: depth = 0
        # \[ ... \] / $$ 里可能有空行，先不要切
        if line.count("\\[") > line.count("\\]"):
            math = 1
        elif line.count("\\]") > line.count("\\["):
            math = 0
        if line.count("$$") % 2:
            math = 0 if math else 1
        if math < 0: math = 0
        pos += len(line)
    a, b = start, len(body)
    while a < b and body[a].isspace(): a += 1
    while b > a and body[b - 1].isspace(): b -= 1
    if b > a: units.append((a, b))
    return units


def _inject_source_markers(body: str, units: list[tuple[int, int]]) -> str:
    out: list[str] = []
    last = 0
    for i, (a, _b) in enumerate(units):
        out.append(body[last:a])
        out.append("\n\n\\texttt{%s%04d}\n\n" % (_SRC_MARK, i))
        last = a
    out.append(body[last:])
    return "".join(out)


def _wrap_source(h: str, units: list[tuple[int, int]], base: int) -> str:
    h = _SRC_RE.sub(lambda m: "@@AMTIKA_SRC_%s@@" % m.group(1), h)
    parts = re.split(r"@@AMTIKA_SRC_(\d+)@@", h)
    out: list[str] = []
    if parts and parts[0].strip():
        out.append(parts[0])
    for i in range(1, len(parts), 2):
        idx = int(parts[i])
        content = parts[i + 1] if i + 1 < len(parts) else ""
        if idx >= len(units) or not content.strip():
            continue
        a, b = units[idx]
        out.append('<div class="lec-src" data-tex-start="%d" data-tex-end="%d">\n%s\n</div>'
                   % (base + a, base + b, content))
    return "\n".join(out)


def build(tid: str, *, force: bool = False) -> Path | None:
    """生成（或复用）某份讲义的 HTML。返回 index.html 路径。"""
    t = topics.get(tid)
    if not t:
        return None
    tex = topics.TOPIC_DIR / (t.get("tex") or "")
    if not tex.is_file():
        return None
    out_dir = LECT_DIR / tid
    index = out_dir / "index.html"
    if not force and index.exists() and index.stat().st_mtime >= tex.stat().st_mtime:
        try:
            if "data-tex-start=" in index.read_text(encoding="utf-8"):
                return index
        except OSError:
            pass

    full_tex = tex.read_text(encoding="utf-8")
    body = _body(tex)
    base = full_tex.find(body)
    if base < 0:
        base = 0
    units = _source_units(body)
    body = _inject_source_markers(body, units)
    macros = _preamble_macros(tex)
    titles = _env_titles(body)
    body, _labels = _number_equations(body)
    body = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]+\}", "", body)

    # TikZ → PNG
    figs: list[str] = []

    def fig_repl(m: re.Match) -> str:
        figs.append(m.group(0))
        n = len(figs)
        if _compile_fig(m.group(0), out_dir / f"fig-{n}.png", macros):
            return "\\begin{center}\\includegraphics[width=0.78\\linewidth]{fig-%d}\\end{center}" % n
        return ""

    body = _TIKZ.sub(fig_repl, body)

    tmp = Path(tempfile.mkdtemp(prefix="amti-lect-"))
    try:
        (tmp / "b.tex").write_text(body, encoding="utf-8")
        r = subprocess.run(["pandoc", "-f", "latex", "-t", "html5", "--katex",
                            "b.tex", "-o", "b.html"],
                           cwd=tmp, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        if r.returncode != 0:
            return None
        h = (tmp / "b.html").read_text(encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 环境标题（pandoc 会丢掉可选标题，按出现顺序补回去）
    counters = {k: 0 for k in ENV_NAME}
    for env, label in ENV_NAME.items():
        pat = re.compile(r'<div class="%s">' % env)

        def repl(_m: re.Match, env=env, label=label) -> str:
            i = counters[env]
            counters[env] += 1
            title = titles.get(env, [])
            opt = title[i] if i < len(title) else ""
            head = ("%s · %s" % (label, opt)) if opt else label
            return '<div class="%s"><div class="env-title">%s</div>' % (
                env, html_mod.escape(head))

        h = pat.sub(repl, h)

    # 图、表、锚点
    h = re.sub(r'<img src="(fig-\d+)"[^>]*>',
               lambda m: '<img class="lec-fig" src="/api/topics/%s/lecture/%s.png" alt="" />'
               % (tid, m.group(1)), h)
    h = h.replace("<table", '<table class="lec-table"')
    h = h.replace('<span id="', '<span class="anchor" id="')
    h = _wrap_source(h, units, base)
    # 知识点库里的易错点/总结/前后关系，一并排进讲义正文（界面统一，不再单独挂卡片）
    t = topics.get(tid) or {}

    def _rich(x) -> str:
        """转义 HTML，但把 $...$ 包成前端 KaTeX 认的 math span。"""
        esc = html_mod.escape(str(x))
        return re.sub(r"\$([^$]+)\$", r'<span class="math inline">\1</span>', esc)

    extra = ['<h2>易错点与总结</h2>']
    for sec in t.get("summary") or []:
        items = "".join("<li>%s</li>" % _rich(x) for x in sec.get("items") or [])
        extra.append('<div class="lec-extra-row"><span class="lec-tag">%s</span>'
                     '<ul class="lec-extra-list">%s</ul></div>' % (html_mod.escape(sec["label"]), items))
    rel = []
    if t.get("pre"):
        rel.append("<span>先修</span>" + "".join(
            '<i>%s</i>' % html_mod.escape(x["title"]) for x in t["pre"]))
    if t.get("post"):
        rel.append("<span>后续</span>" + "".join(
            '<i>%s</i>' % html_mod.escape(x["title"]) for x in t["post"]))
    if rel:
        extra.append('<div class="lec-rel">%s</div>' % "".join(rel))
    h += "\n" + "".join(extra)

    # pandoc 会把 `1.3\quad 集合` 拼成「1.3集合」；标题里的编号后补一个空格
    h = re.sub(r'(<h[123][^>]*>)(\d+(?:\.\d+)*)(?=[\u4e00-\u9fa5])', r'\1\2 ', h)
    h = '<div class="lecture">\n' + h + "\n</div>\n"

    out_dir.mkdir(parents=True, exist_ok=True)
    index.write_text(h, encoding="utf-8")
    return index
