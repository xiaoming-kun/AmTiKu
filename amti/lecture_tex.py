"""AmTiKu · 小初章节讲义：高中模板的 LaTeX 渲染器

小学/初中讲义不再走「开源 Markdown 阅读器」，而是和高中专题一样：
**每章一份 elegantbook `.tex` → PDF → 网页版 HTML**。

本模块只做三件事：
  1. 把 `数据/专题/小初/content/<章id>.json` 渲染成与高中同款的 `.tex`；
  2. 调 `xelatex` 编译，检查页数、文本层与常见错误；
  3. 汇总成 `数据/专题/小初/manifest.json`，交给 `amti.topics` 统一读取。

模板的导言区、环境名、TikZ 设置、表格/小结/教材溯源的位置，全部照抄
`数据/专题/1.1.1.tex`。内容 JSON 只写正文，不碰导言区——这样 120 章
的版式不会各写各的。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .paths import ROOT

BASE = ROOT / "数据" / "专题" / "小初"
CONTENT = BASE / "content"
DOSSIER = BASE / "dossiers"
MANIFEST = BASE / "manifest.json"
FIGURE = ROOT / "数据" / "专题" / "figure"

STAGE_NAME = {"primary": "小学", "junior": "初中"}

# 与 `数据/专题/1.1.1.tex` 逐字一致的导言区；只替换标题类字段。
PREAMBLE = r"""% ============================================================
%  {title}
%  {stage_name}数学讲义 · {book}
%  说明：本文件为一节独立讲义，仅含核心知识点与必要文字叙述，
%        不含习题；图形一律使用 TikZ 绘制；结论用表格归纳。
%  由 amti.lecture_tex 从 content/{cid}.json 渲染，请勿手改。
% ============================================================
\documentclass[lang=cn,newtx,12pt,scheme=chinese]{{elegantbook}}

\title{{{title}}}
\subtitle{{{subtitle}}}

\author{{AmTiKu {stage_name}讲义组}}
\institute{{{stage_name}数学讲义}}
\date{{2026/11/7}}
\version{{1.0}}
\bioinfo{{难度}}{{{difficulty}}}
\setcounter{{tocdepth}}{{3}}

\logo{{figure/logo-blue.png}}
\cover{{figure/cover.jpg}}

% ===== 自定义定理类环境的中文标题 =====
\renewcommand{{\definitionname}}{{知识点}}
\renewcommand{{\theoremname}}{{方法}}
\renewcommand{{\propositionname}}{{核心思路}}

% ===== TikZ 绘图支持 =====
\usepackage{{tikz}}
\usepackage{{tcolorbox}}
\usepackage{{pgfplots}}
\pgfplotsset{{compat=1.17}}
\usetikzlibrary{{arrows.meta,calc,positioning,decorations.markings}}
\tikzset{{>=Stealth}}

\begin{{document}}
\renewcommand{{\xchaptertitle}}{{}}\newcommand{{\lecturenumber}}{{{seq}}}
\renewcommand{{\thesection}}{{\lecturenumber.\arabic{{section}}}}

\chapter{{{title}}}

\begin{{introduction}}
{outline}
\end{{introduction}}

{intro}

"""

POSTAMBLE = r"""
%==============================================================
\section{{易错点与本节小结}}

\begin{{table}}[htbp]
\centering
\small
\caption{{本节易错点速查}}
\label{{tab:pitfalls-{cid}}}
\begin{{tabular}}{{@{{}}p{{0.30\linewidth}}p{{0.60\linewidth}}@{{}}}}
\toprule
\textbf{{易错点}} & \textbf{{正确做法}} \\
\midrule
{pitfalls}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{proposition}}[本节小结] \label{{pro:summary-{cid}}}
\begin{{enumerate}}
{summary}
\end{{enumerate}}
\end{{proposition}}

\begin{{tcolorbox}}[breakable,colback=blue!2,colframe=blue!35,title=教材溯源,fonttitle=\bfseries,left=8pt,right=8pt]
\small
{source_note}
\end{{tcolorbox}}

\end{{document}}
"""

FORBIDDEN_WORDS = ("练习", "习题", "作业", "下列各题", "选择题", "填空题")
FORBIDDEN_CMDS = (
    "\\documentclass", "\\usepackage", "\\begin{document}", "\\end{document}",
    "\\chapter", "\\section", "\\subsection", "\\includegraphics", "\\input",
    "\\include", "\\maketitle", "\\tableofcontents", "\\appendix",
    "\\begin{problemset}", "\\begin{question}", "\\begin{problem}",
    "\\begin{exercise}", "\\begin{ex}",
)


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _dossier(cid: str) -> dict:
    p = DOSSIER / f"{cid}.json"
    return _read_json(p) if p.is_file() else {}


def load_content(cid: str) -> dict:
    return _read_json(CONTENT / f"{cid}.json")


def _stage_name(stage: str) -> str:
    return STAGE_NAME.get(stage, "小初")


def _outline_lines(items: list) -> str:
    return "\n".join("\t\\item %s" % str(x).strip() for x in items)


def _pitfall_rows(items: list) -> str:
    rows = []
    for it in items:
        wrong = str(it.get("wrong") or "").strip()
        right = str(it.get("right") or "").strip()
        rows.append("%s & %s \\\\" % (wrong, right))
    return "\n".join(rows)


def _summary_lines(items: list) -> str:
    return "\n".join("\t\\item %s" % str(x).strip() for x in items)


def _env_balance(src: str) -> str:
    stack: list[str] = []
    for m in re.finditer(r"\\(begin|end)\{([^{}]+)\}", src):
        kind, name = m.group(1), m.group(2).strip()
        if kind == "begin":
            stack.append(name)
        else:
            if not stack or stack[-1] != name:
                return "环境不配对：\\end{%s} 对不上 %s" % (
                    name, stack[-1] if stack else "（空）")
            stack.pop()
    return "环境未闭合：%s" % "、".join(stack) if stack else ""


def _brace_balance(src: str) -> str:
    s = re.sub(r"\\[{}]", "", src)
    depth = 0
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return "花括号多了一个 }"
    return "花括号没有闭合（差 %d 个 }）" % depth if depth else ""




def _bare_math(src: str) -> str:
    """去掉数学环境/公式后，检查正文里是否还有裸 ^ _ \\frac 等。"""
    s = src
    # 数学/图表环境整段去掉
    s = re.sub(r"\\begin\{(equation\*?|align\*?|tikzpicture|tabular|array|cases|"
               r"matrix|pmatrix|bmatrix|vmatrix|aligned|gathered|split)\}.*?"
               r"\\end\{\1\}", "", s, flags=re.S)
    # 行间/行内公式
    s = re.sub(r"\$\$.*?\$\$", "", s, flags=re.S)
    s = re.sub(r"\$[^$]*\$", "", s)
    s = re.sub(r"\\\[.*?\\\]", "", s, flags=re.S)
    s = re.sub(r"\\\(.*?\\\)", "", s, flags=re.S)
    # label/ref/begin/end 的花括号参数不算公式
    s = re.sub(r"\\(?:label|ref|eqref|begin|end|includegraphics|url)\{[^}]*\}", "", s)
    if re.search(r"[\^_]", s):
        return "正文里有裸 ^ 或 _，公式没放数学模式"
    if re.search(r"\\(?:frac|sqrt|cdot|times|le|ge|ne|pm|sum|int)\b", s):
        return "正文里有裸 LaTeX 公式命令，没放数学模式"
    return ""

def validate_content(c: dict, cid: str) -> list[str]:
    """内容 JSON 的结构与硬性规矩；返回问题列表（空 = 通过）。"""
    bad: list[str] = []
    for k in ("title", "subtitle", "intro", "outline", "sections",
              "summary", "pitfalls", "source_note"):
        if k not in c:
            bad.append("缺字段 %s" % k)
    if bad:
        return bad
    if not str(c.get("title") or "").strip():
        bad.append("title 为空")
    if len(str(c.get("intro") or "").strip()) < 60:
        bad.append("intro 太短（至少 60 字，要有一段引子）")
    outline = c.get("outline") or []
    if not (4 <= len(outline) <= 9):
        bad.append("outline 要 4–9 条，现在 %d 条" % len(outline))
    sections = c.get("sections") or []
    if not (3 <= len(sections) <= 7):
        bad.append("sections 要 3–7 节，现在 %d 节" % len(sections))
    total = len(str(c.get("intro") or ""))
    for i, s in enumerate(sections, 1):
        if not isinstance(s, dict) or not str(s.get("title") or "").strip():
            bad.append("第 %d 节缺 title" % i)
            continue
        body = str(s.get("body") or "")
        total += len(body)
        if len(body) < 120:
            bad.append("第 %d 节正文太短（%d 字）" % (i, len(body)))
        for cmd in FORBIDDEN_CMDS:
            if cmd in body:
                bad.append("第 %d 节出现了不该有的命令 %s" % (i, cmd))
        for w in FORBIDDEN_WORDS:
            if w in body:
                bad.append("第 %d 节出现了「%s」——讲义不排习题" % (i, w))
    if total < 1200:
        bad.append("正文总字数 %d，偏少（目标 1800–4000）" % total)
    summary = c.get("summary") or []
    if not (4 <= len(summary) <= 9):
        bad.append("summary 要 4–9 条，现在 %d 条" % len(summary))
    pitfalls = c.get("pitfalls") or []
    if not (2 <= len(pitfalls) <= 6):
        bad.append("pitfalls 要 2–6 条，现在 %d 条" % len(pitfalls))
    for i, p in enumerate(pitfalls, 1):
        if not isinstance(p, dict) or not str(p.get("wrong") or "").strip() \
                or not str(p.get("right") or "").strip():
            bad.append("第 %d 条易错点缺 wrong/right" % i)
    src = "\n".join(str(s.get("body") or "") for s in sections)
    src += "\n" + str(c.get("intro") or "")
    all_text = "\n".join([str(c.get("intro") or ""), str(c.get("title") or ""),
                          str(c.get("subtitle") or "")] +
                         [str(x) for x in outline] +
                         [str(s.get("title") or "") + "\n" + str(s.get("body") or "")
                          for s in sections] +
                         [str(x) for x in summary] +
                         [str(p.get("wrong") or "") + " " + str(p.get("right") or "")
                          for p in pitfalls])
    for cmd in FORBIDDEN_CMDS:
        if cmd in all_text:
            bad.append("出现了不该有的命令 %s（内容 JSON 只写正文）" % cmd)
    if "~" in all_text:
        bad.append("正文里有裸 ~：中文范围请写“1 到 5”或 $1\\sim5$，别用 ~")
    if all_text.count("$") % 2:
        bad.append("全文的 $ 数量是奇数（可能漏了闭合）")
    if "\\begin{figure}" not in src and "\\begin{table}" not in src:
        bad.append("正文至少要有一幅 TikZ 图或一张表格（别只有段落）")
    envblocks = sum(src.count("\\begin{%s}" % e) for e in
                    ("definition", "theorem", "proposition", "example"))
    if envblocks < 2:
        bad.append("至少要有 2 个知识点/方法/核心思路/例 环境，现在 %d 个" % envblocks)
    for msg in (_env_balance(src), _brace_balance(src), _bare_math(all_text)):
        if msg:
            bad.append(msg)
    if re.search(r"\\label\{[^}]*\}", src):
        labels = re.findall(r"\\label\{([^}]*)\}", src)
        if len(labels) != len(set(labels)):
            bad.append("正文里有重复的 \\label")
    note = str(c.get("source_note") or "")
    if len(note) < 10:
        bad.append("source_note 太短，要写清教材位置/来源")
    if re.search(r"第\s*\d+\s*页", note):
        bad.append("source_note 不要写具体页码（容易编错）；只写册/章/单元")
    return bad


_CHAPTER_INDEX: dict = {"key": None, "exact": {}, "point": {}}


def _chapter_index() -> dict:
    """知识地图的 (学段,册,章) 与考点索引；只建一次。"""
    from . import knowledge_map
    tree = knowledge_map.tree()
    key = (tree.get("version"), tree.get("updated"), tree.get("total"))
    if _CHAPTER_INDEX.get("key") == key:
        return _CHAPTER_INDEX
    exact, point = {}, {}
    for st in tree.get("stages", []):
        sk = st.get("key", "")
        for b in st.get("books", []):
            bn = b.get("name", "")
            for c in b.get("chapters", []):
                ct = c.get("title", "")
                exact[(sk, bn, ct)] = (bn, ct)
                for p in c.get("points", []):
                    if p.get("id"):
                        point[p["id"]] = (bn, ct)
    _CHAPTER_INDEX.update({"key": key, "exact": exact, "point": point})
    return _CHAPTER_INDEX


def _norm_chapter(s: str) -> str:
    # 教材标题里全角/半角波浪号混用是实际出现过的（x11.2 等 5 章），
    # 归一化只用于**找对应关系**，找到后仍使用知识地图的原文标题。
    return str(s or "").replace("～", "~").replace("－", "-").strip()


def _resolve_book_chapter(stage: str, book: str, chapter: str,
                          points: list[dict]) -> tuple[str, str, bool]:
    idx = _chapter_index()
    hit = idx["exact"].get((stage, book, chapter))
    if hit:
        return hit[0], hit[1], True
    for (sk, bn, ct), val in idx["exact"].items():
        if sk == stage and _norm_chapter(bn) == _norm_chapter(book) \
                and _norm_chapter(ct) == _norm_chapter(chapter):
            return val[0], val[1], True
    # 标题本身对不上（或教材版本改了章名）时，用考点反查。
    votes: dict[tuple[str, str], int] = {}
    for p in points:
        pid = str((p or {}).get("id") or "")
        val = idx["point"].get(pid)
        if val:
            votes[val] = votes.get(val, 0) + 1
    if votes:
        (bn, ct), _n = max(votes.items(), key=lambda kv: kv[1])
        return bn, ct, True
    return book, chapter, False


def render_tex(cid: str) -> dict:
    """content JSON → `.tex`，返回元信息。不编译。"""
    c = load_content(cid)
    d = _dossier(cid)
    bad = validate_content(c, cid)
    if bad:
        raise ValueError("内容不合规：\n- " + "\n- ".join(bad))
    stage = str(d.get("stage") or c.get("stage") or "primary")
    book = str(d.get("book") or c.get("book") or "")
    chapter = str(d.get("chapter") or c.get("chapter") or c.get("title") or "")
    book, chapter, _mapped = _resolve_book_chapter(
        stage, book, chapter, d.get("points") or [])
    seq = str(d.get("seq") or c.get("seq") or "1")
    title = str(c.get("title") or chapter).strip()
    subtitle = str(c.get("subtitle") or ("%s · %s" % (book, chapter))).strip()
    difficulty = str(c.get("difficulty") or "★").strip()
    outline = _outline_lines(c.get("outline") or [])
    intro = str(c.get("intro") or "").strip()
    body_parts = []
    for s in c.get("sections") or []:
        body_parts.append("\n\\section{%s}\n\n%s\n" % (
            str(s.get("title") or "").strip(), str(s.get("body") or "").strip()))
    body = "".join(body_parts)
    pitfalls = _pitfall_rows(c.get("pitfalls") or [])
    summary = _summary_lines(c.get("summary") or [])
    source_note = str(c.get("source_note") or "").strip()
    head = PREAMBLE.format(
        title=title, stage_name=_stage_name(stage), book=book, cid=cid,
        subtitle=subtitle, difficulty=difficulty, seq=seq,
        outline=outline, intro=intro,
    )
    tail = POSTAMBLE.format(cid=cid, pitfalls=pitfalls, summary=summary,
                            source_note=source_note)
    tex = head + body + tail
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / f"{cid}.tex").write_text(tex, encoding="utf-8")
    return {"id": cid, "title": title, "stage": stage, "book": book,
            "chapter": chapter, "seq": seq, "difficulty": difficulty,
            "tex": str(BASE / f"{cid}.tex")}


def _ensure_figures() -> None:
    dst = BASE / "figure"
    if dst.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("logo-blue.png", "cover.jpg"):
        src = FIGURE / name
        if src.is_file():
            shutil.copy2(src, dst / name)


def compile_tex(cid: str, timeout: int = 240) -> dict:
    """xelatex 两遍；返回 ok / pages / log 摘要。"""
    _ensure_figures()
    tex = BASE / f"{cid}.tex"
    if not tex.is_file():
        return {"ok": False, "error": "没有 .tex，先 render", "pages": 0}
    xe = shutil.which("xelatex")
    if not xe:
        return {"ok": False, "error": "找不到 xelatex", "pages": 0}
    logs = []
    for _ in range(2):
        r = subprocess.run(
            [xe, "-interaction=nonstopmode", "-halt-on-error", tex.name],
            cwd=BASE, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
        logs.append((r.stdout or "") + (r.stderr or ""))
        if r.returncode != 0:
            tail = "\n".join(logs[-1].splitlines()[-30:])
            return {"ok": False, "error": "LaTeX 编译失败：\n" + tail, "pages": 0}
    pdf = BASE / f"{cid}.pdf"
    if not pdf.is_file():
        return {"ok": False, "error": "没有产出 PDF", "pages": 0}
    pages = 0
    text = ""
    try:
        import pymupdf
        with pymupdf.open(pdf) as doc:
            pages = doc.page_count
            text = "\n".join(page.get_text() for page in doc)
    except Exception as e:                       # 没装 pymupdf 就只报页数 0
        return {"ok": True, "error": "", "pages": 0, "warn": "读不了 PDF：%s" % e}
    if pages < 2:
        return {"ok": False, "error": "只有 %d 页，内容太少" % pages, "pages": pages}
    if pages > 10:
        return {"ok": False, "error": "有 %d 页，超出 3–5 页的目标" % pages,
                "pages": pages}
    if len(text.strip()) < 800:
        return {"ok": False, "error": "PDF 文本层只有 %d 字，可能是空壳" % len(text),
                "pages": pages}
    return {"ok": True, "error": "", "pages": pages, "chars": len(text.strip())}


def check_one(cid: str) -> dict:
    try:
        meta = render_tex(cid)
    except Exception as e:
        return {"ok": False, "error": str(e), "pages": 0}
    res = compile_tex(cid)
    res.update({"id": cid, "title": meta.get("title")})
    return res


def _summary_cards(c: dict) -> list[dict]:
    cards = []
    pits = ["%s——%s" % (str(p.get("wrong") or "").strip(),
                        str(p.get("right") or "").strip())
            for p in (c.get("pitfalls") or []) if p.get("wrong")]
    if pits:
        cards.append({"label": "易错点", "items": pits})
    if c.get("summary"):
        cards.append({"label": "本节小结", "items": [str(x) for x in c["summary"]]})
    return cards


def _source_note(d: dict, c: dict) -> str:
    return str(c.get("source_note") or "").strip()


def sync_manifest() -> dict:
    """扫描 content/，把能对上 dossier 的条目写进 manifest.json。"""
    topics = []
    missing = []
    for p in sorted(CONTENT.glob("*.json")):
        cid = p.stem
        try:
            c = _read_json(p)
            d = _dossier(cid)
            if not d:
                missing.append(cid)
                continue
            stage = str(d.get("stage") or c.get("stage") or "")
            if stage not in ("primary", "junior"):
                missing.append(cid)
                continue
            book = str(d.get("book") or c.get("book") or "")
            chapter = str(d.get("chapter") or c.get("chapter") or "")
            book, chapter, mapped = _resolve_book_chapter(
                stage, book, chapter, d.get("points") or [])
            if not mapped:
                missing.append(cid)
                continue
            title = str(c.get("title") or chapter)
            topics.append({
                "id": cid,
                "stage": stage,
                "title": title,
                "topic": book,
                "section": chapter,
                "book": book,
                "chapter": chapter,
                "stars": int(c.get("stars") or d.get("stars") or 1),
                "difficulty": str(c.get("difficulty") or "基础"),
                "pdf": "小初/%s.pdf" % cid,
                "tex": "小初/%s.tex" % cid,
                "summary": _summary_cards(c),
                "points": [x.get("id") for x in (d.get("points") or []) if x.get("id")],
                "source": (d.get("source")
                           or (d.get("existing") or {}).get("source") or {}),
                "seq": d.get("seq") or 0,
            })
        except Exception:
            missing.append(cid)
    order = {"primary": 0, "junior": 1}
    topics.sort(key=lambda t: (order.get(t["stage"], 9), t.get("seq") or 0, t["id"]))
    data = {
        "version": 1,
        "updated": time.strftime("%Y-%m-%d"),
        "note": "小初章节讲义：与高中专题同一套 elegantbook 模板；内容源在 content/*.json。",
        "topics": topics,
    }
    BASE.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(MANIFEST)
    return {"ok": True, "topics": len(topics), "missing": missing}


def build_html(cid: str, force: bool = True) -> dict:
    """先生成 manifest，再交给 amti.lecture_html 转网页版。"""
    from . import topics as _topics
    _topics._CACHE.update({"key": None, "v": None})
    from . import lecture_html
    p = lecture_html.build(cid, force=force)
    if not p:
        return {"ok": False, "error": "网页版生成失败"}
    h = p.read_text(encoding="utf-8")
    checks = {
        "lecture": '<div class="lecture">' in h,
        "h2": h.count("<h2") >= 3,
        "env": any('class="%s"' % x in h for x in
                   ("definition", "theorem", "proposition", "example")),
        "table": 'class="lec-table"' in h,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        return {"ok": False, "error": "网页版结构缺：" + "、".join(bad)}
    return {"ok": True, "html": str(p), "chars": len(h)}


def _all_ids() -> list[str]:
    return sorted(p.stem for p in CONTENT.glob("*.json"))


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "help"
    ids = argv[2:] or _all_ids()
    if cmd == "validate":
        bad = 0
        for cid in ids:
            try:
                c = load_content(cid)
            except Exception as e:
                bad += 1
                print("ERR", cid, "读不了 JSON：", e)
                continue
            issues = validate_content(c, cid)
            if issues:
                bad += 1
                print("ERR", cid)
                for x in issues:
                    print("   -", x)
            else:
                print("OK", cid)
        print("共 %d，失败 %d" % (len(ids), bad))
        return 0 if not bad else 1
    if cmd == "render":
        for cid in ids:
            try:
                m = render_tex(cid)
                print("OK render", cid, m["title"])
            except Exception as e:
                print("ERR render", cid, e)
        return 0
    if cmd == "check":
        bad = 0
        for cid in ids:
            r = check_one(cid)
            if r.get("ok"):
                print("OK", cid, "%s 页 %s 字" % (r.get("pages"), r.get("chars")))
            else:
                bad += 1
                print("ERR", cid, (r.get("error") or "").strip().splitlines()[0])
        print("共 %d，失败 %d" % (len(ids), bad))
        return 0 if not bad else 1
    if cmd == "sync":
        r = sync_manifest()
        print("manifest:", r)
        return 0 if not r.get("missing") else 1
    if cmd == "html":
        bad = 0
        for cid in ids:
            r = build_html(cid)
            if r.get("ok"):
                print("OK html", cid, r.get("chars"))
            else:
                bad += 1
                print("ERR html", cid, r.get("error"))
        return 0 if not bad else 1
    if cmd == "all":
        bad = 0
        for cid in ids:
            r = check_one(cid)
            if not r.get("ok"):
                bad += 1
                print("ERR", cid, (r.get("error") or "").strip().splitlines()[0])
        print("编译：%d 章，失败 %d" % (len(ids), bad))
        print(sync_manifest())
        for cid in ids:
            r = build_html(cid)
            if not r.get("ok"):
                bad += 1
                print("ERR html", cid, r.get("error"))
        print("总失败", bad)
        return 0 if not bad else 1
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
