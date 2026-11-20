"""AmTiKu · 专题导出：把「讲义 + 配套练习」编成一份 PDF

讲义是桌面整理好的 elegantbook 单文件；练习来自题库。这里做的是：

    1. 取出讲义的导言区与正文（到 \\end{document} 为止）；
    2. 在导言区补三个宏：\\paren、\\fillin、\\needspace（题库题面里会用到）；
    3. 在正文后面追加「配套练习」：题干、选项、答案、解析；
    4. 在 ASCII 临时目录里 xelatex 两遍，产物缓存到 数据/专题/导出/。

版本：
    teacher=1  教师版：括号/横线上直接印答案，每题后附解析
    teacher=0  学生版：括号/横线留空，不印答案与解析

**不改桌面上的讲义**：每次都是读原件、拼一份临时的 merged.tex。
"""
from __future__ import annotations

from .paths import ROOT
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import store
from . import topics

from html.parser import HTMLParser

OUT_DIR = topics.TOPIC_DIR / "导出"
_PLACEHOLDER = "\\underline{\\hspace{2.2em}}"


def _macro_block(teacher: bool) -> str:
    paren = "（\\textbf{#1}）" if teacher else "（\\hspace{1.6em}）"
    fill = "\\underline{\\textbf{#1}}" if teacher else _PLACEHOLDER
    return (
        "\n% ===== 专题配套练习（amti.topic_export 注入）=====\n"
        "\\providecommand{\\needspace}[1]{}\n"
        f"\\providecommand{{\\paren}}[1][]{{{paren}}}\n"
        f"\\providecommand{{\\fillin}}[1][]{{{fill}}}\n"
        "\\graphicspath{{图片/}{figure/}}\n"
        "\\usepackage{tcolorbox}\n"
        "\\tcbuselibrary{breakable}\n"
        "\\newtcolorbox{amtiquest}{breakable,colback=gray!3,colframe=gray!45,"
        "boxrule=0.5pt,arc=1.5pt,left=9pt,right=9pt,top=6pt,bottom=6pt,"
        "before skip=7pt,after skip=7pt,fontupper=\\raggedright,"
        "before upper={\\parindent=0pt}}\n"
    )


def _split_tex(tex_path: Path) -> tuple[str, str]:
    src = tex_path.read_text(encoding="utf-8")
    i = src.index("\\begin{document}")
    j = src.index("\\end{document}")
    return src[:i], src[i + len("\\begin{document}"):j]


def _practice(questions: list, teacher: bool) -> str:
    out = ["\n\\clearpage\n\\markboth{配套练习}{}\n",
           "\\section*{配套练习（%d 题）}\n" % len(questions)]
    out.append("\\noindent\\textit{%s}\\par\\medskip\n" % (
        "教师版：答案与解析附在每题之后，讲课时可先遮住。"
        if teacher else "学生版：先做，答案与解析见教师版。"))
    for n, q in enumerate(questions, 1):
        out.append("\\begin{amtiquest}\n")
        out.append("\\noindent\\textbf{%d.}\\ %s\\par\n" % (n, (q.stem or "").strip()))
        opts = q.options or []
        if opts:
            parts = []
            for k, o in enumerate(opts):
                if isinstance(o, dict):
                    lab, text = o.get("label"), o.get("text", "")
                else:
                    lab, text = getattr(o, "label", ""), getattr(o, "text", "")
                parts.append("\\textbf{%s.}\\ %s" % (lab or chr(65 + k), text))
            rows = [" & ".join(parts[i:i + 2] + [""] * (2 - len(parts[i:i + 2]))) + " \\\\"
                    for i in range(0, len(parts), 2)]
            out.append("\\smallskip\n{\\small\\noindent\\begin{tabular}{@{}p{0.47\\linewidth}@{}p{0.47\\linewidth}@{}}\n%s\n\\end{tabular}\\par}\n"
                       % "\n".join(rows))
        if teacher:
            ans = (q.answer or "").strip()
            sol = (q.solution or "").strip()
            choice = q.type in ("single_choice", "multi_choice", "fill_in_blank")
            if ans and not choice and ans != "见解析":
                out.append("\\smallskip\n{\\small\\noindent\\textbf{答案：}%s\\par}\n" % ans)
            if sol:
                out.append("{\\small\\noindent\\textbf{解析：}%s\\par}\n" % sol)
        out.append("\\end{amtiquest}\n")
    return "".join(out)


class _Blocks(HTMLParser):
    """把网页版讲义切成顶层块，记住每块前面最近的标题（用于定位正文插题）。"""

    VOID = {"br", "img", "hr", "input", "meta", "link", "col", "source"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_lecture = False
        self.depth = 0
        self.cur = None
        self.entries: list[dict] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        if not self.in_lecture:
            if "lecture" in (dict(attrs).get("class") or "").split():
                self.in_lecture = True
                self.depth = 0
            return
        if self.depth == 0:
            self.cur = {"tag": tag, "text": ""}
            self.entries.append(self.cur)
        self.depth += 1

    def handle_endtag(self, tag):
        if tag in self.VOID or not self.in_lecture:
            return
        self.depth -= 1
        if self.depth <= 0:
            self.depth = 0
            self.cur = None

    def handle_data(self, data):
        if self.in_lecture and self.cur is not None:
            self.cur["text"] += data


def _norm(s: str) -> str:
    s = re.sub(r"\$[^$]*\$", "", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    return re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", s)


def _bid_headings(tid: str) -> list:
    """返回每个顶层块前面最近的 h2/h3 标题（没有则为 None）。"""
    p = topics.TOPIC_DIR / "讲义" / tid / "index.html"
    if not p.is_file():
        return []
    parser = _Blocks()
    parser.feed(p.read_text(encoding="utf-8"))
    heads: list = []
    last = None
    for e in parser.entries:
        if e["tag"] in ("h2", "h3", "h4"):
            last = e["text"].strip()
        heads.append(last)
    return heads


def _insert_placed(body: str, tid: str, qs: list, placements: dict,
                   teacher: bool) -> tuple:
    """把插在正文里的题按“所在小节的标题”塞回 LaTeX 正文。

    网页里插题记的是“第几个顶层块”；这里把块翻成它前面最近的 h2/h3 标题，
    再到 LaTeX 正文里找同名 \\section/\\subsection，插在该节内容之后。
    找不到标题的题不硬塞，留在最后的配套练习里，保证不丢题。
    """
    if not placements:
        return body, set()
    heads = _bid_headings(tid)
    back = {q.key: q for q in qs}
    secs = [(m.start(), m.group(1)) for m in
            re.finditer(r"\\(?:section|subsection)\{([^}]*)\}", body)]
    inserts: list = []
    inserted: set = set()
    n = 0
    for key, anchor in placements.items():
        q = back.get(key)
        if q is None:
            continue
        try:
            bid = int(str(anchor).split("|")[0])
        except Exception:
            continue
        head = heads[bid] if 0 <= bid < len(heads) else None
        pos = None
        if head:
            hn = _norm(head)
            for start, title in secs:
                tn = _norm(title)
                if tn and (tn == hn or tn.startswith(hn) or hn.startswith(tn)):
                    pos = start
                    break
        if pos is None:
            continue
        n += 1
        inserts.append((pos, _inline_q(n, q, teacher)))
        inserted.add(key)
    if not inserts:
        return body, set()
    for pos, block in sorted(inserts, key=lambda x: -x[0]):
        nxt = body.find("\\section", pos + 1)
        if nxt == -1:
            nxt = body.find("\\end{document}", pos)
        if nxt == -1:
            nxt = len(body)
        body = body[:nxt] + block + body[nxt:]
    return body, inserted


def _inline_q(n: int, q, teacher: bool) -> str:
    """正文中插入的随堂练习（题卡样式，教师版带答案与解析）。"""
    out = ["\n\\begin{amtiquest}\n",
           "\\noindent\\textbf{随堂练习 %d.}\\ %s\\par\n" % (n, (q.stem or "").strip())]
    opts = q.options or []
    if opts:
        parts = []
        for k, o in enumerate(opts):
            if isinstance(o, dict):
                lab, text = o.get("label"), o.get("text", "")
            else:
                lab, text = getattr(o, "label", ""), getattr(o, "text", "")
            parts.append("\\textbf{%s.}\\ %s" % (lab or chr(65 + k), text))
        rows = [" & ".join(parts[i:i + 2] + [""] * (2 - len(parts[i:i + 2]))) + " \\\\"
                for i in range(0, len(parts), 2)]
        out.append("\\smallskip\n{\\small\\noindent\\begin{tabular}{@{}p{0.47\\linewidth}@{}p{0.47\\linewidth}@{}}\n%s\n\\end{tabular}\\par}\n"
                   % "\n".join(rows))
    if teacher:
        ans = (q.answer or "").strip()
        sol = (q.solution or "").strip()
        if ans and ans != "见解析":
            out.append("\\smallskip\n{\\small\\noindent\\textbf{答案：}%s\\par}\n" % ans)
        if sol:
            out.append("{\\small\\noindent\\textbf{解析：}%s\\par}\n" % sol)
    out.append("\\end{amtiquest}\n")
    return "".join(out)


def _images(tex: str) -> list[str]:
    names = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex)
    return [n for n in dict.fromkeys(names) if n]


def build_pdf(tid: str, teacher: bool = True, *, force: bool = False) -> Path:
    """生成（或取缓存）专题讲练 PDF。返回文件路径；失败抛 RuntimeError。"""
    t = topics.get(tid)
    if not t:
        raise RuntimeError("没有这个专题")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{tid}-{'teacher' if teacher else 'student'}.pdf"
    tex_path = topics.TOPIC_DIR / (t.get("tex") or "")
    if not tex_path.is_file():
        raise RuntimeError("专题缺少讲义 tex 源文件")
    sel = topics.SEL_DIR / f"{tid}.json"
    stamps = [tex_path.stat().st_mtime, topics.MANIFEST.stat().st_mtime]
    if sel.is_file():
        stamps.append(sel.stat().st_mtime)
    if not force and out.exists() and out.stat().st_mtime >= max(stamps):
        return out

    by_key = {q.key: q for q in store.load_cached()}
    qs = [by_key[k] for k in t.get("questions") or [] if k in by_key]
    if not qs:
        raise RuntimeError("这个专题还没有精选题，导不出练习")

    preamble, body = _split_tex(tex_path)
    body, placed = _insert_placed(body, tid, qs, t.get("placements") or {}, teacher)
    rest = [q for q in qs if q.key not in placed]
    practice = _practice(rest, teacher) if rest else ""
    doc = (preamble + _macro_block(teacher) + "\\begin{document}"
           + body + practice + "\n\\end{document}\n")

    tmp = Path(tempfile.mkdtemp(prefix="amti-topic-"))   # 纯 ASCII 路径，绕开 kpathsea 的坑
    try:
        (tmp / "merged.tex").write_text(doc, encoding="utf-8")
        # 讲义自带 figure/（logo、封面）；题图从 图片/ 里按需搬
        src_fig = topics.TOPIC_DIR / "figure"
        if src_fig.is_dir():
            shutil.copytree(src_fig, tmp / "figure")
        img_dir = tmp / "图片"
        for name in _images(doc):
            src = ROOT / "图片" / Path(name).name
            if src.is_file():
                img_dir.mkdir(exist_ok=True)
                shutil.copy2(src, img_dir / Path(name).name)
        xe = shutil.which("xelatex")
        if not xe:
            raise RuntimeError("找不到 xelatex —— 导出讲练 PDF 需要 LaTeX 引擎")
        log = ""
        for _ in range(2):
            r = subprocess.run(
                [xe, "-interaction=nonstopmode", "-halt-on-error", "merged.tex"],
                cwd=tmp, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300)
            log = (r.stdout or "") + (r.stderr or "")
            if r.returncode != 0:
                raise RuntimeError("讲义编译失败：\n" + "\n".join(log.splitlines()[-8:]))
        pdf = tmp / "merged.pdf"
        if not pdf.is_file():
            raise RuntimeError("讲义编译没有产出 PDF")
        shutil.copy2(pdf, out)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
