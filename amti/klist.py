r"""AmTiKu · 知识清单 —— 讲义内容源的**唯一入口**

## 这是什么

`待解/知识清单/` 下那本《高中数学知识清单》（20 个分文件、252 节、208 张
TikZ 图、136 张表）是**讲义模块的讲解内容源**。本模块把它变成应用能直接用的东西：

    书 .tex ──dialect()──▶ 应用方言 LaTeX ──latex_blocks.parse_blocks()──▶ 块级 IR
                                                                          │
                                            讲义/知识清单.json ◀──────────┘

## 为什么必须有它（而不是让前端去读 .tex）

* **全项目只有 `latex_ir.py` / `latex_blocks.py` 懂 LaTeX**（AGENTS.md 的唯一
  入口规矩）。书里另有 500 多种**它自己的**宏与环境（`\thead` `\numline`
  `\lra` `\abs` `appenum` `notebox`…），`parse_blocks` 不认，会整片漏成 raw。
  这些「书方言 → 应用方言」的展开只写在这里；前端与 Slidev 导出都只消费
  展开后的 IR，不再各自正则一遍。
* **TikZ 画不进 HTML**。`latex_blocks` 只能把它标成 raw 块，前端显示
  「HTML 画不了」。所以这里把每张图**预渲染成 PNG** 落 `图片/`（沿用
  `tikzfig.py` 的内容寻址命名与「只换渲染好的」策略），正文里换成
  `\includegraphics` —— 浏览器与导出 PDF 看到的是同一张图。
* **书的分类法 ≠ 题库的分类法**。书按教材编（必修1 第一章 1.1.3），题库按
  考纲编（`知识点.json` 的 152 个考点，1.1.3＝集合的基本运算）。两套编号
  不同源：实测纯标题匹配只有 21/152 可信，所以映射是**人工核定后固化**的
  `讲义/知识清单映射.json`；本模块只负责读它、校验它、给候选（`suggest()`）。

## 数据落在哪

| 文件 | 是什么 | 进 git |
|---|---|---|
| `待解/知识清单/*.tex` | 内容源（书本身） | 否 |
| `讲义/知识清单.json` | 生成物：节点 + 块级 IR，**运行时唯一依赖** | 否 |
| `讲义/知识清单映射.json` | 考点 ↔ 节点，**人工核定** | 否 |
| `讲义/知识清单图.json` | 图的尺寸清单（渲染时写） | 否 |
| `图片/klist-*.png` | 预渲染出来的图 | 否 |

五个都在 `待解/` `讲义/` `图片/` 下 —— 按项目规矩（`.gitignore`「git 只管代码、
配置、文档；数据由快照/备份负责」）**一个都不进 git**。所以：
`讲义/知识清单映射.json` 那 152 条人工核定**没有第二份**，别随手删。

书不在时应用照常跑（只读生成物）；**只有重新生成才需要书**。

三个命令（都要有书）：

    python3 -m amti.klist build      # 重新解析书 → 讲义/知识清单.json
    python3 -m amti.klist figs       # 书里的 TikZ → 图片/klist-*.png（画过的跳过）
    python3 -m amti.klist check      # 自检（也是 `amti.py accept` 层① 的一项）
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import latex_blocks as lb
from .export import IMG_DIR
from .logutil import get_logger
from .paths import ROOT

log = get_logger(__name__)

# ── 路径 ─────────────────────────────────────────────────────────────

STORE = ROOT / "讲义" / "知识清单.json"
MAPFILE = ROOT / "讲义" / "知识清单映射.json"
FIGMAN = ROOT / "讲义" / "知识清单图.json"
FIG_PREFIX = "klist-"
FIG_DPI = 220
# 生成物格式版本。**改了 IR 的含义就要 +1** —— `fingerprint()` 只看书变没变，
# 不看解析器变没变；不 bump 的话旧生成物会被当成"还是新的"，界面上不提示重建。
STORE_VERSION = 2

# 书里不用作内容源的文件
_NOT_CONTENT = {"preamble.tex", "main.tex", "quickref.tex"}


def book_dir() -> Path:
    r"""书所在目录。默认 `待解/知识清单`，可用 `数据/知识清单位置.txt` 改。

    跟 `paths.resolve_out_dir()` 一个套路：个人路径不进源码，配置文件放
    不进 git 的 `数据/` 下。
    """
    cfg = ROOT / "数据" / "知识清单位置.txt"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                p = Path(line).expanduser()
                if not p.is_absolute():
                    p = ROOT / p
                return p
    except OSError:
        pass
    return ROOT / "待解" / "知识清单"


def book_files() -> list[Path]:
    r"""按 `main.tex` 的 `\input` 顺序列出内容分文件（顺序＝成书顺序）。"""
    d = book_dir()
    main = d / "main.tex"
    order: list[str] = []
    if main.is_file():
        for m in re.finditer(r"\\input\{([^}]+)\}", main.read_text(encoding="utf-8")):
            name = m.group(1)
            if not name.endswith(".tex"):
                name += ".tex"
            if name not in _NOT_CONTENT:
                order.append(name)
    files = [d / n for n in order if (d / n).is_file()]
    if files:
        return files
    # 没有 main.tex（或 \input 全对不上）就退回字典序，至少不空手
    return sorted(p for p in d.glob("*.tex")
                  if p.name not in _NOT_CONTENT
                  and not p.name.startswith(("gen-", "_chk_")))


def fingerprint() -> str:
    """书的指纹：文件名 + 大小 + mtime。用来判断生成物过没过期。"""
    h = hashlib.sha256()
    for p in book_files():
        st = p.stat()
        h.update(("%s|%d|%d\n" % (p.name, st.st_size, int(st.st_mtime))).encode())
    return h.hexdigest()[:16]


# ── 书方言 → 应用方言 ────────────────────────────────────────────────

# 行尾的 `%` 在 LaTeX 里**吃掉换行**（不是插入空格）。书里大量用它续行，
# 所以连换行一起删；`latex_blocks` 自己的注释剥离不删换行，这里必须先做。
_COMMENT_JOIN = re.compile(r"(?<!\\)%[^\n]*(\n|$)")

# 文档级命令：与内容无关，整条删掉（含参数）
_DOC_JUNK = [
    r"\\documentclass\s*(\[[^\]]*\])?\s*\{[^}]*\}",
    r"\\usepackage\s*(\[[^\]]*\])?\s*\{[^}]*\}",
    r"\\input\s*\{[^}]*\}",
    r"\\begin\{document\}", r"\\end\{document\}",
    r"\\ctexset\s*\{",           # 参数是嵌套花括号，下面按配对扫
    r"\\setcounter\s*\{[^}]*\}\s*\{[^}]*\}",
    r"\\addtocounter\s*\{[^}]*\}\s*\{[^}]*\}",
    r"\\setlength\s*\{[^}]*\}\s*\{[^}]*\}",
    r"\\addcontentsline\s*\{[^}]*\}\s*\{[^}]*\}\s*\{",   # 第三参可能带嵌套
    r"\\renewcommand\s*\{[^}]*\}\s*(\[\d+\])?\s*\{",
    r"\\newcommand\s*\{[^}]*\}\s*(\[\d+\])?\s*\{",
    r"\\arrayrulecolor\s*\{[^}]*\}",
    r"\\pagenumbering\s*\{[^}]*\}",
    r"\\markboth\s*\{[^}]*\}\s*\{[^}]*\}",
    r"\\thispagestyle\s*\{[^}]*\}",
    r"\\pagestyle\s*\{[^}]*\}",
    # 书里 `\begingroup … \endgroup` 只用来圈住 `\small` 这类字号设置
    r"\\begingroup\b", r"\\endgroup\b",
    # 两处 `\hfill` 是「左右各一张图」的对齐指令，没有参数
    r"\\hfil(?:l)?\b",
]
_JUNK_RE = re.compile("|".join(_DOC_JUNK))

# longtable 的重复表头/表尾标记，以及 booktabs 的行距微调：都是排版指令
_TABLE_JUNK = re.compile(
    r"\\end(?:first|last)?(?:head|foot)\b\s*|\\addlinespace\s*(\[[^\]]*\])?"
    r"|\\kill\b|\\tabularnewline\b")

# 行距可选参数：`\\[3pt]` → `\\`。留着会被 `split_top` 切进下一格当正文。
_ROW_SPACING = re.compile(r"\\\\(\s*)\[[^\]]*\]")

# 环境改名：书里的自定义环境 → `latex_blocks` 认得的标准环境
_ENV_RENAME = {
    "notebox": "quote",       # mdframed 的灰底框
    "mdframed": "quote",
    "defn": "quote",          # 定义/定理框
}

# 只解一层花括号参数、把内容原样放回来的宏（表格里最多）
_UNWRAP = {"thead", "makecell", "shortstack", "scalebox", "resizebox",
           "fbox", "framebox", "textcircled", "centerline", "textsc"}
# 这几个的参数里 `\\` 是「换行」，进 HTML 表格后用空格接上
_UNWRAP_ROWJOIN = {"thead", "makecell", "shortstack"}
# `\multirow{2}{*}{X}` / `\multicolumn` 由 latex_blocks 处理，multirow 要自己拆
_MULTIROW = re.compile(r"\\multirow(?![a-zA-Z])")

# 书自定义的数学宏（preamble.tex 里的 \newcommand）→ 标准 LaTeX。
# 顺序无关：替换时用 (?![a-zA-Z]) 卡住词尾，`\ra` 不会咬到 `\rangle`。
_MATH_NOARG = {
    "R": r"\mathbb{R}", "N": r"\mathbb{N}", "Z": r"\mathbb{Z}",
    "Q": r"\mathbb{Q}", "C": r"\mathbb{C}",
    "cu": r"\complement", "definedby": r"\triangleq", "supose": r"\colon",
    "lra": r"\longrightarrow", "ra": r"\rightarrow",
    "Lra": r"\Longleftrightarrow", "Ra": r"\Longrightarrow",
    "dg": r"^{\circ}", "sq": r"\square", "rd": r"\,\mathrm{d}",
    "para": r"\parallel",
}
_MATH_ONEARG = {
    "ang": r"\angle %s", "trip": r"\triangle %s",
    "set": r"\left\{ %s \right\}",
    "abs": r"\left| %s \right|", "norm": r"\left\| %s \right\|",
    "vec": r"\overrightarrow{%s}",
}
_SRCMISS_DEFAULT = "源文件此处缺失，按通行教材补录"

# `\numline[可选]{正文}` 的展开式，与 preamble.tex 里的定义逐字一致
_NUMLINE_DEF = r"""\begin{tikzpicture}[>=Stealth, %s]
    \draw[axl] (-3.6,0) -- (3.6,0) node[right, font=\small] {$x$};
    \foreach \x/\l in {-3/-3,-2/-2,-1/-1,1/1,2/2,3/3}
      \draw (\x,2pt) -- (\x,-2pt) node[below, font=\tiny] {\l};
    \node[below, font=\tiny] at (0,-1pt) {$O$};
    %s
  \end{tikzpicture}"""


def _brace_arg(s: str, i: int) -> tuple[str | None, int]:
    r"""跳过空白后若 `s[i]=='{'`，返回 (内容, 内容后的下标)；否则 (None, i)。"""
    j = i
    while j < len(s) and s[j] in " \t":
        j += 1
    if j < len(s) and s[j] == "{":
        k = lb.skip_brace(s, j)
        return s[j + 1:k - 1], k
    return None, i


def _opt_arg(s: str, i: int) -> tuple[str | None, int]:
    j = i
    while j < len(s) and s[j] in " \t":
        j += 1
    if j < len(s) and s[j] == "[":
        k = lb.skip_opt(s, j)
        return s[j + 1:k - 1], k
    return None, i


def _strip_comments(src: str) -> str:
    return _COMMENT_JOIN.sub("", src)


def _drop_junk(src: str) -> str:
    r"""删文档级/排版级命令。**带嵌套花括号的**要按配对扫，不能用正则。"""
    out = []
    i = 0
    while True:
        m = _JUNK_RE.search(src, i)
        if not m:
            out.append(src[i:])
            break
        out.append(src[i:m.start()])
        j = m.end()
        # 这几条正则是**开在参数中间**收尾的（`\ctexset{`、`\addcontentsline{..}{..}{`、
        # `\renewcommand{..}{`），后面的嵌套参数得自己跳过。
        tail = m.group(0)
        if tail.endswith("{"):
            j = lb.skip_brace(src, j - 1)
            # `\renewcommand{\x}[1]{...}` 跳完一个还可能有一个
            if tail.startswith("\\renewcommand") or tail.startswith("\\newcommand"):
                _, k = _brace_arg(src, j)
                if k > j:
                    j = k
        i = j
    src = "".join(out)
    src = _TABLE_JUNK.sub(" ", src)
    return _ROW_SPACING.sub(r"\\\\", src)


def _expand_numline(src: str) -> str:
    r"""把 `\numline[...]{...}` 展成它本来会画出的那个 tikzpicture。

    数轴（不等式解集）在书里全用这个宏，不展开就是一句 raw 宏、图也没了。
    展开必须**在抽图之前**做，这样展开出来的 tikzpicture 一样能被渲染成 PNG。
    """
    out = []
    i = 0
    while True:
        m = re.compile(r"\\numline(?![a-zA-Z])\*?").search(src, i)
        if not m:
            out.append(src[i:])
            break
        out.append(src[i:m.start()])
        opt, j = _opt_arg(src, m.end())
        body, k = _brace_arg(src, j)
        if body is None:
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(_NUMLINE_DEF % (opt or "", body))
        i = k
    return "".join(out)


def _number_appenum(src: str) -> str:
    r"""附录的 `appenum` 清单：**把原书编号写成字面文字**，环境换成 itemize。

    为什么不能直接当有序列表：附录是一条从 1 数到 203 的长清单，被标题切成
    4 段分文件续号（`\setcounter{appenumi}{93}`）。前端画有序列表是各段
    从 1 重新数，于是「94. 椭圆的内外部」会显示成「1.」——**编号即内容**，
    错了就是错。所以编号落成文字、列表改成无序，前端就不会再自己编号。

    顺带处理原书那处印错的「53.」：它写作 `\item[\textbf{53.}]`，
    **不占号**，原样保留。
    """
    out = []
    i = 0
    while True:
        b = src.find("\\begin{appenum}", i)
        if b < 0:
            out.append(src[i:])
            break
        e = src.find("\\end{appenum}", b)
        if e < 0:
            out.append(src[i:])
            break
        body = src[b + len("\\begin{appenum}"):e]
        out.append(src[i:b])
        out.append("\\begin{itemize}")
        out.append(_number_items(body))
        out.append("\\end{itemize}")
        i = e + len("\\end{appenum}")
    return "".join(out)


def _number_items(body: str) -> str:
    r"""给 `body` 里**顶层**的每个无标签 `\item` 前置原书编号。"""
    m = re.search(r"\\setcounter\s*\{\s*(?:appenumi|enumi)\s*\}\s*\{(\d+)\}", body)
    n = int(m.group(1)) if m else 0
    if m:
        body = body[:m.start()] + body[m.end():]
    out = []
    i = 0
    depth = 0
    while i < len(body):
        if body.startswith("\\begin{", i):
            depth += 1
        elif body.startswith("\\end{", i):
            depth = max(0, depth - 1)
        if depth == 0:
            im = re.compile(r"\\item(?![a-zA-Z])\s*\*?").match(body, i)
            if im:
                j = im.end()
                # 带 `[标签]` 的（原书那处印错的 53.）不占号、原样留着
                lab, k = _opt_arg(body, j)
                if lab is None:
                    n += 1
                    out.append(body[i:j])
                    out.append("\\textbf{%d.}\\quad " % n)
                    i = j
                    continue
                else:
                    out.append(body[i:k])
                    i = k
                    continue
        out.append(body[i])
        i += 1
    return "".join(out)


_LIST_ENV = re.compile(r"\\begin\{list\}")
_ITEM_LABEL = re.compile(r"\\item\s*\[([^\]]*)\]")


def _expand_list_env(src: str) -> str:
    r"""`\begin{list}{}{\setlength…}` → `itemize`，**标签并进正文**。

    `latex_blocks` 的 `_ITEM_RE` 会把 `\item[(1)]` 的方括号标签直接吃掉，
    前端又用 `<ul>` 画圆点——原书「(1)…(5)」这五条焦点弦结论的编号
    就没了。所以跟附录 `appenum` 同一套处理：编号当正文字符留下。
    """
    out = []
    i = 0
    while True:
        m = _LIST_ENV.search(src, i)
        if not m:
            out.append(src[i:])
            break
        out.append(src[i:m.start()])
        j = m.end()
        for _ in range(2):                       # 丢掉 `{}{\setlength…}` 两个参数
            _, j = _brace_arg(src, j)
        e = src.find("\\end{list}", j)
        if e < 0:
            out.append(src[m.start():])
            break
        body = _ITEM_LABEL.sub(lambda mm: "\\item %s\\quad " % mm.group(1),
                               src[j:e])
        out.append("\\begin{itemize}" + body + "\\end{itemize}")
        i = e + len("\\end{list}")
    return "".join(out)


_PARAGRAPH = re.compile(r"\\paragraph\s*\*?\s*\{([^}]*)\}")


def _expand_paragraph(src: str) -> str:
    r"""`\paragraph{系列1：…}` → 独立成段的加粗小标题。

    `\paragraph` 是比 `\subsubsection` 更低一级的标题。它不建节点
    （`_HEAD_RE` 里没有），当正文里的加粗段处理——书里只有引言的
    「系列1..4」四处用它。
    """
    return _PARAGRAPH.sub(lambda m: "\n\n\\textbf{%s}\n\n" % m.group(1), src)


def _rename_envs(src: str) -> str:
    # `defn` 的可选参数是框标题（默认「定义」）——**先单独处理**，
    # 否则跟 notebox 一起改成 quote 之后就分不清谁该带标题了。
    def _defn(m: re.Match) -> str:
        return "\\begin{quote}\\textbf{%s}\\quad " % (m.group(1) or "定义")
    src = re.sub(r"\\begin\{defn\}\s*(\[([^\]]*)\])?", _defn, src)
    src = src.replace("\\end{defn}", "\\end{quote}")
    for a, b in _ENV_RENAME.items():
        src = src.replace("\\begin{%s}" % a, "\\begin{%s}" % b)
        src = src.replace("\\end{%s}" % a, "\\end{%s}" % b)
    return src


def _unwrap_macros(src: str) -> str:
    r"""`\thead{X}` → `X` 之类：解掉一层参数、内容原样放回。

    这些宏全是**排版壳**（表头加粗居中、格子内换行、缩放、画框），
    内容才是要的。`latex_blocks` 不认它们，会整条漏成 raw 宏——书里
    `\thead` 有 407 处，不拆表格就全花了。
    """
    names = sorted(_UNWRAP, key=len, reverse=True)
    pat = re.compile(r"\\(?:%s)(?![a-zA-Z])\*?" % "|".join(names))
    for _ in range(4):                      # 可能套着（\thead{\makecell{..}}）
        out = []
        i = 0
        changed = False
        while True:
            m = pat.search(src, i)
            if not m:
                out.append(src[i:])
                break
            out.append(src[i:m.start()])
            name = m.group(0)[1:].rstrip("*")
            _, j = _opt_arg(src, m.end())    # 丢掉 [c] [b] 这类对齐参数
            if name in ("scalebox", "resizebox"):
                _, j = _brace_arg(src, j)    # 再丢掉缩放系数那一个参数
            inner, k = _brace_arg(src, j)
            if inner is None:
                out.append(m.group(0))
                i = m.end()
                continue
            if name in _UNWRAP_ROWJOIN:
                inner = re.sub(r"\\\\(\s*\[[^\]]*\])?", " ", inner)
            if name == "textcircled":
                inner = _circled(inner)
            out.append(inner)
            i = k
            changed = True
        src = "".join(out)
        if not changed:
            break
    # `\multirow{2}{*}{X}` → X（前两个参数是行数与宽度）
    out = []
    i = 0
    while True:
        m = _MULTIROW.search(src, i)
        if not m:
            out.append(src[i:])
            break
        out.append(src[i:m.start()])
        _, j = _brace_arg(src, m.end())
        _, j = _brace_arg(src, j)
        _, j = _opt_arg(src, j)
        inner, k = _brace_arg(src, j)
        if inner is None:
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(inner)
        i = k
    return "".join(out)


_CIRCLED_NUM = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _circled(inner: str) -> str:
    r"""`\textcircled{\scriptsize 3}` → `③`（书里 134 处，全是这种序号）。"""
    t = re.sub(r"\\[a-zA-Z]+\*?", "", inner)
    t = re.sub(r"[{}\s\\]", "", t)
    if t.isdigit() and 1 <= int(t) <= 20:
        return _CIRCLED_NUM[int(t) - 1]
    return "（%s）" % t if t else ""


def _expand_math_macros(src: str) -> str:
    for name, rep in _MATH_NOARG.items():
        src = re.sub(r"\\%s(?![a-zA-Z])" % re.escape(name), rep.replace("\\", "\\\\"), src)
    for name, fmt in _MATH_ONEARG.items():
        pat = re.compile(r"\\%s(?![a-zA-Z])\*?" % re.escape(name))
        for _ in range(3):
            out = []
            i = 0
            changed = False
            while True:
                m = pat.search(src, i)
                if not m:
                    out.append(src[i:])
                    break
                out.append(src[i:m.start()])
                _, j = _opt_arg(src, m.end())       # `\abs*{x}` 的星号/定界符参数
                inner, k = _brace_arg(src, j)
                if inner is None:
                    out.append(m.group(0))
                    i = m.end()
                    continue
                out.append(fmt % inner)
                i = k
                changed = True
            src = "".join(out)
            if not changed:
                break
    return src


def _expand_markers(src: str) -> str:
    r"""`\srcgap{X}`（补录段）与 `\srcmiss[X]`（源文件缺）→ 可读文字。

    这两个是**转录期的记号**，不是数学内容：书里它们靠颜色和小字号区分，
    到应用里得变成看得懂的话，否则「哪些是原书没有的」这条信息就丢了。
    """
    out = []
    i = 0
    while True:
        m = re.compile(r"\\(srcgap|srcmiss)(?![a-zA-Z])").search(src, i)
        if not m:
            out.append(src[i:])
            break
        out.append(src[i:m.start()])
        opt, j = _opt_arg(src, m.end())
        inner, k = _brace_arg(src, j)
        if m.group(1) == "srcgap":
            if inner is None:
                out.append(m.group(0))
                i = m.end()
                continue
            out.append("\n\n\\textbf{【补录】%s}\n\n" % inner.strip())
            i = k
        else:
            out.append("（%s）" % (opt or inner or _SRCMISS_DEFAULT))
            i = k if inner is not None else (j if opt is not None else m.end())
    return "".join(out)


_FIG_SENTINEL = "\x00KFIG%d\x00"


def _protect_figures(src: str) -> tuple[str, list[str]]:
    r"""把图整块抠出来换成占位符，返回 (占位后的正文, 图源码列表)。

    dialect 那些展开是给**正文**准备的，跑进图里就是破坏：
    `\scalebox{1.6}{通径}` 被拆壳（标签小了 1.6 倍）、`\\[2pt]` 被收成
    `\\`（节点里两行贴在一起）。而图压根不需要展开——渲染时用的就是书
    自己的 `preamble.tex`，`\cu` `\dg` `\ang` `\para` 这些书里都有定义。
    """
    figs: list[str] = []

    def cut(m: re.Match) -> str:
        figs.append(m.group(0))
        return _FIG_SENTINEL % (len(figs) - 1)

    src = _TIKZ_RE.sub(cut, src)
    src = _AXIS_RE.sub(cut, src)        # 裸 axis（没包 tikzpicture 的）
    return src, figs


def _restore_figures(src: str, figs: list[str]) -> str:
    for i, t in enumerate(figs):
        src = src.replace(_FIG_SENTINEL % i, t)
    return src


def dialect(src: str) -> str:
    """书 LaTeX → 应用方言（`latex_blocks` + KaTeX 都认的标准写法）。"""
    src = _strip_comments(src)
    # `_number_appenum` 要读 `\setcounter{appenumi}{93}` 才知道从几号续，
    # 必须排在 `_drop_junk`（它把 setcounter 整条删掉）**前面**。
    src = _expand_numline(src)
    # `\numline` 会**凭空生成** tikzpicture，所以保护要排在它后面。
    src, figs = _protect_figures(src)
    src = _number_appenum(src)
    src = _expand_list_env(src)
    src = _expand_paragraph(src)
    src = _drop_junk(src)
    src = _rename_envs(src)
    src = _unwrap_macros(src)
    src = _expand_markers(src)
    src = _expand_math_macros(src)
    return _restore_figures(src, figs)


# ── 图：TikZ → PNG ───────────────────────────────────────────────────

_TIKZ_RE = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.S)
_AXIS_RE = re.compile(r"\\begin\{axis\}.*?\\end\{axis\}", re.S)


def fig_key(tikz: str) -> str:
    """图的**内容寻址**名字（与 `tikzfig.py` 同一套思路：源码变→名字变）。"""
    return FIG_PREFIX + hashlib.sha256(tikz.strip().encode("utf-8")).hexdigest()[:16]


def fig_path(tikz: str) -> Path:
    return IMG_DIR / (fig_key(tikz) + ".png")


def collect_tikz(src: str) -> list[str]:
    r"""书里所有图的源码。**裸 `\begin{axis}`** 也要（自己包一层 tikzpicture）。"""
    out = list(_TIKZ_RE.findall(src))
    for m in _AXIS_RE.finditer(src):
        # 只收不在 tikzpicture 里的那些
        head = src[:m.start()]
        if head.count("\\begin{tikzpicture}") == head.count("\\end{tikzpicture}"):
            out.append("\\begin{tikzpicture}\n" + m.group(0) + "\n\\end{tikzpicture}")
    return out


def _fig_preamble() -> str:
    r"""渲染单张图用的导言区：**直接用书自己的 `preamble.tex`**。

    故意不另抄一份样式：书里 204 张图全靠 `stdaxis`/`fn`/`flowdec`/`curveA`
    这些自定义样式和颜色，抄一份就必然与书分叉（AGENTS.md 的头号坑）。
    `standalone` 只缺一个中文字体入口，补 `\usepackage{ctex}` 即可。
    """
    pre = book_dir() / "preamble.tex"
    if not pre.is_file():
        raise FileNotFoundError(
            "渲染图要书自己的导言区，但找不到 %s。\n"
            "图已经渲染过的话不用管这条（应用读 图片/klist-*.png 就够了）；"
            "要重画就得先有书源文件。" % pre)
    return ("\\documentclass[border=2cm]{standalone}\n"
            "\\usepackage{ctex}\n"
            + pre.read_text(encoding="utf-8")
            + "\n\\begin{document}\n")


def _content_box(page) -> "object":
    r"""PDF 页上**实际画了东西**的包围盒（矢量 ∪ 文字）。

    不能信 `standalone` 的 tightpage 裁切：它给的裁切窗口会**偏**（实测
    必修3 那张更相减损术框图，上边和左边被切掉、右边多留白），而窗口
    大小又碰巧差不多，肉眼看像「图小了」而不是「裁偏了」。这里留 2cm
    大边距编译保证什么都画得下，再按内容盒自己裁。
    """
    import fitz
    r = None
    for d in page.get_drawings():
        r = d["rect"] if r is None else r | d["rect"]
    for b in page.get_text("blocks"):
        r = fitz.Rect(b[:4]) if r is None else r | fitz.Rect(b[:4])
    if r is None or r.is_empty:
        return page.rect
    return r + (-1, -1, 1, 1)


def _render_one(tikz: str, preamble: str, timeout: int = 180,
                force: bool = False) -> tuple[bool, str]:
    dst = fig_path(tikz)
    if dst.is_file() and not force:
        return True, ""
    body = tikz.strip()
    if "\\begin{tikzpicture}" not in body:
        body = "\\begin{tikzpicture}\n" + body + "\n\\end{tikzpicture}"
    work = Path(tempfile.mkdtemp(prefix="klist-fig-"))
    try:
        (work / "f.tex").write_text(preamble + body + "\n\\end{document}\n",
                                    encoding="utf-8")
        try:
            p = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "f.tex"],
                cwd=work, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "渲染超时（%d 秒）" % timeout
        except FileNotFoundError:
            return False, "找不到 xelatex（TeX Live 没装或不在 PATH）"
        pdf = work / "f.pdf"
        if p.returncode != 0 or not pdf.is_file():
            txt = (p.stdout or b"").decode("utf-8", "ignore")
            errs = [l for l in txt.split("\n") if l.startswith("!")]
            return False, (errs[0][:200] if errs else txt[-200:])
        try:
            import fitz
        except ImportError:
            return False, "缺 PyMuPDF（pip install pymupdf）：PDF 转不了 PNG"
        doc = fitz.open(pdf)
        try:
            page = doc[0]
            box = _content_box(page)
            pix = page.get_pixmap(dpi=FIG_DPI, clip=box)
            IMG_DIR.mkdir(parents=True, exist_ok=True)
            pix.save(dst)
            figman_put(fig_key(tikz), {
                "w_pt": round(box.width, 2),
                "h_pt": round(box.height, 2),
                "w_cm": round(box.width / 28.45, 2),
                "h_cm": round(box.height / 28.45, 2),
                "px": [pix.width, pix.height],
                "dpi": FIG_DPI,
                "bytes": dst.stat().st_size,
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        finally:
            doc.close()
        return True, ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def render_figures(*, force: bool = False, jobs: int = 4,
                   only: str = "", verbose: bool = True) -> dict:
    r"""把书里的图全画成 PNG 落 `图片/`。

    按源码 sha 缓存：**画过的不再画**，所以可以随时中断、重跑续上。
    渲染需要书源文件（要它的 `preamble.tex`）与 TeX Live。
    """
    tikzs = book_tikz()
    todo = []
    for t in tikzs:
        if force or not fig_path(t).is_file():
            if only and only not in t:
                continue
            todo.append(t)
    if verbose:
        print("书里的图：%d 张（去重后），待渲染 %d 张" % (len(tikzs), len(todo)))
    if not todo:
        return {"total": len(tikzs), "todo": 0, "ok": 0, "fail": 0, "errors": []}
    try:
        preamble = _fig_preamble()
    except FileNotFoundError as e:
        return {"total": len(tikzs), "todo": len(todo), "ok": 0, "fail": len(todo),
                "errors": [str(e)]}
    errors = []
    ok = 0
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        futs = {ex.submit(_render_one, t, preamble, 180, force): t for t in todo}
        for n, f in enumerate(list(futs), 1):
            good, err = f.result()
            if good:
                ok += 1
            else:
                errors.append({"key": fig_key(futs[f]), "err": err,
                               "head": futs[f].strip()[:80]})
            if verbose and (n % 20 == 0 or n == len(todo)):
                print("  %d/%d 成功 %d 失败 %d" % (n, len(todo), ok, len(errors)))
    return {"total": len(tikzs), "todo": len(todo), "ok": ok,
            "fail": len(errors), "errors": errors[:40]}


def load_figman() -> dict:
    try:
        return json.loads(FIGMAN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_figman(man: dict) -> None:
    FIGMAN.parent.mkdir(parents=True, exist_ok=True)
    tmp = FIGMAN.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(FIGMAN)


# 图是并行渲染的，而清单是「读—改—写」整个文件：不加锁就会互相覆盖，
# 少记几条尺寸（`substitute_figures` 于是拿不到宽度）。
_FIGMAN_LOCK = threading.Lock()


def figman_put(key: str, entry: dict) -> None:
    with _FIGMAN_LOCK:
        man = load_figman()
        man[key] = entry
        save_figman(man)


def substitute_figures(src: str) -> tuple[str, int, int]:
    r"""把 tikzpicture 换成 `\includegraphics`。返回 (新正文, 换了几张, 还缺几张)。

    **只换渲染好的**——没渲染过的原样留着，`latex_blocks` 会把它标成 raw 块，
    前端显示「TikZ 图形 · HTML 画不了」占位。这跟 `tikzfig.to_image()` 一个
    脾气：没跑过渲染不会让讲义变空，只是回到老样子。

    宽度用**图的自然厘米数**：`_width_pct` 按 15cm 版心折算成百分比，
    于是浏览器里的图与书里的图一样大（相对版心）。
    """
    man = load_figman()
    done = pend = 0

    def sub(m: re.Match) -> str:
        nonlocal done, pend
        code = m.group(0)
        p = fig_path(code)
        if not p.is_file():
            pend += 1
            return code
        done += 1
        info = man.get(fig_key(code)) or {}
        cm = float(info.get("w_cm") or 7.0)
        cm = max(1.0, min(15.0, cm))
        return "\\includegraphics[width=%.2fcm]{%s}" % (cm, p.name)

    src = _TIKZ_RE.sub(sub, src)

    def sub_axis(m: re.Match) -> str:
        nonlocal done, pend
        head = src[:m.start()]
        if head.count("\\begin{tikzpicture}") != head.count("\\end{tikzpicture}"):
            return m.group(0)                     # 在 tikzpicture 里，不动
        code = "\\begin{tikzpicture}\n" + m.group(0) + "\n\\end{tikzpicture}"
        p = fig_path(code)
        if not p.is_file():
            pend += 1
            return m.group(0)
        done += 1
        info = man.get(fig_key(code)) or {}
        cm = max(1.0, min(15.0, float(info.get("w_cm") or 7.0)))
        return "\\includegraphics[width=%.2fcm]{%s}" % (cm, p.name)

    src = _AXIS_RE.sub(sub_axis, src)
    return src, done, pend


# ── 节点：把书切成可寻址的块 ─────────────────────────────────────────

_HEAD_RE = re.compile(r"\\(chapter|section|subsection|subsubsection)\*?\s*\{")
_LEVELS = ("chapter", "section", "subsection", "subsubsection")


def clean_title(t: str) -> str:
    r"""标题去掉排版壳：`\quad` → 空格，宏与花括号剥掉。"""
    t = re.sub(r"\\quad|\\qquad|\\,|\\;|\\enspace|\\ ", " ", t)
    t = re.sub(r"\\[a-zA-Z]+\*?", "", t)
    t = re.sub(r"[{}$\\]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def _slug(t: str) -> str:
    s = clean_title(t)
    s = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:60] or "node"


def _raw_nodes() -> list[dict]:
    r"""切节点，**只切不译**：每个节点带元信息与原文 body。

    `parse_nodes` 与 `book_tikz` 都要走这一遍，而且必须**完全同源**——
    图的 sha 是按 dialect 之后的正文算的，谁少跑一步就对不上号。
    """
    out: list[dict] = []
    used: dict[str, int] = {}
    for p in book_files():
        base = p.name[:-4]
        raw = p.read_text(encoding="utf-8")
        heads = []
        for m in _HEAD_RE.finditer(raw):
            title, after = _brace_arg(raw, m.end() - 1)
            if title is None:
                continue
            heads.append((m.start(), after, m.group(1), title))
        trail = dict.fromkeys(_LEVELS, "")
        spans: list[tuple[int, int, str, str, int]] = []
        for i, (st, af, lv, ti) in enumerate(heads):
            end = heads[i + 1][0] if i + 1 < len(heads) else len(raw)
            spans.append((af, end, lv, ti, raw[:st].count("\n") + 1))
        if not spans:                       # 整个文件没有标题
            spans = [(0, len(raw), "chapter", base, 1)]
        # 文件开头、第一个标题之前的内容也不能丢
        if heads and heads[0][0] > 0:
            pre = raw[:heads[0][0]]
            if _meaningful(pre):
                spans.insert(0, (0, heads[0][0], "file", base + "（卷首）", 1))
        for bs, be, lv, ti, line in spans:
            if lv != "file":
                idx = _LEVELS.index(lv)
                trail[lv] = ti
                for k in _LEVELS[idx + 1:]:
                    trail[k] = ""
            nid = "%s/%s" % (base, _slug(ti))
            if nid in used:
                used[nid] += 1
                nid = "%s-%d" % (nid, used[nid])
            else:
                used[nid] = 1
            out.append({"id": nid, "file": base, "line": line, "level": lv,
                        "title": clean_title(ti),
                        "chapter": clean_title(trail["chapter"] or ""),
                        "section": clean_title(trail["section"] or ""),
                        "body": raw[bs:be]})
    return out


def book_tikz() -> list[str]:
    r"""书里所有图的源码（去重、**按 substitute 时看到的同一份文本**收）。

    ⚠️ 不能从原文收：`dialect()` 会展开 `\numline`（凭空多出 tikzpicture）、
    也会改图里的 `\lra` 这类自定义宏，sha 就与 `substitute_figures` 要找的
    那个对不上（实测差 17 张）。
    """
    out: list[str] = []
    seen: set[str] = set()
    for n in _raw_nodes():
        if not _meaningful(n["body"]):
            continue
        for t in collect_tikz(dialect(n["body"])):
            k = fig_key(t)
            if k not in seen:
                seen.add(k)
                out.append(t)
    return out


def parse_nodes(*, substitute: bool = True) -> list[dict]:
    r"""把整本书切成节点（带块级 IR）。

    **切分在原文上做**（不是 dialect 之后）——dialect 会删注释、并行尾，
    行号就漂了；而节点要带行号，方便回书里对。切完再逐节点 dialect。
    """
    nodes: list[dict] = []
    for r in _raw_nodes():
        nid, body = r["id"], r["body"]
        meta = {k: r[k] for k in ("id", "file", "line", "level", "title",
                                  "chapter", "section")}
        if not _meaningful(body):
            nodes.append({**meta, "blocks": [], "n_fig": 0, "n_fig_pending": 0,
                          "n_table": 0, "chars": 0})
            continue
        src = dialect(body)
        if substitute:
            src, nfig, npend = substitute_figures(src)
        else:
            nfig = npend = 0
        blocks = lb.parse_blocks(src)
        _fix_fig_widths(blocks)          # 百分比在表格格子里是错的，见该函数
        nodes.append({**meta,
                      "blocks": blocks,
                      "n_fig": nfig, "n_fig_pending": npend,
                      "n_table": _count(blocks, "table"),
                      "chars": len(lb.blocks_to_text(blocks))})
    return nodes


def _meaningful(s: str) -> bool:
    t = _strip_comments(s)
    t = re.sub(r"\\[a-zA-Z]+\*?|[{}$\[\]%&\\]|\s", "", t)
    return len(t) > 0


# `latex_blocks._width_pct` 把图的宽度折算成「占 15cm 版心的百分之几」。
# **在表格格子里这个百分比是错的**：CSS 的百分比宽度按**包含块**（那个格子）
# 算，不按页面 —— 书的「示意图」列里那 0.9cm 的小图被算成格子的 7%，
# 缩到只剩一个点（导出 PDF 里肉眼验证过）。210 张书图里 **129 张就在格子里**，
# 不是边角情况。这里换回**绝对厘米**：与容器无关，格子内外一样大，也与书里一样大。
_BOOK_TEXT_CM = 15.0


def _abs_fig_width(w) -> str:
    m = re.match(r"(\d+(?:\.\d+)?)%$", str(w or "").strip())
    if not m:
        return w
    return "%.2fcm" % max(0.3, float(m.group(1)) / 100.0 * _BOOK_TEXT_CM)


def _fix_fig_widths(blocks: list[dict]) -> None:
    """就地（递归）把图宽从百分比换成绝对厘米，见 `_BOOK_TEXT_CM`。"""
    def inline(ins: list) -> None:
        for x in ins or []:
            if x.get("t") == "fig":
                x["width"] = _abs_fig_width(x.get("width"))

    for b in blocks or []:
        t = b.get("t")
        if t == "fig":
            b["width"] = _abs_fig_width(b.get("width"))
        elif t == "p":
            inline(b.get("in"))
        elif t == "list":
            for it in b.get("items") or []:
                _fix_fig_widths(it)
        elif t == "box":
            _fix_fig_widths(b.get("blocks"))
        elif t == "table":
            for row in b.get("rows") or []:
                for c in row:
                    if "blocks" in c:
                        _fix_fig_widths(c["blocks"])
                    inline(c.get("in"))


def _count(blocks: list[dict], t: str) -> int:
    n = 0
    for b in blocks:
        if b.get("t") == t:
            n += 1
        if b.get("t") == "list":
            for it in b["items"]:
                n += _count(it, t)
        elif b.get("t") == "box":
            n += _count(b["blocks"], t)
        elif b.get("t") == "table":
            for row in b["rows"]:
                for c in row:
                    if "blocks" in c:
                        n += _count(c["blocks"], t)
    return n


def unknown_macros(blocks: list[dict]) -> dict:
    """IR 里还剩多少**没展开的书方言**（raw 行内宏）。用于自检与体检。"""
    from collections import Counter
    cnt: Counter = Counter()

    def walk(bs):
        for b in bs:
            t = b.get("t")
            if t == "p":
                for n in b.get("in", []):
                    if n.get("t") == "raw":
                        cnt[n.get("s", "?").strip()[:40]] += 1
            elif t == "list":
                for it in b["items"]:
                    walk(it)
            elif t == "box":
                walk(b["blocks"])
            elif t == "table":
                for row in b["rows"]:
                    for c in row:
                        if "blocks" in c:
                            walk(c["blocks"])
                        for n in c.get("in", []):
                            if n.get("t") == "raw":
                                cnt[n.get("s", "?").strip()[:40]] += 1
    walk(blocks)
    return dict(cnt)


# ── 存取 ─────────────────────────────────────────────────────────────

_CACHE: dict = {}


def build(*, verbose: bool = True) -> dict:
    """重新生成 `讲义/知识清单.json`。"""
    files = book_files()
    if not files:
        return {"ok": False, "error": "找不到书：%s（见 数据/知识清单位置.txt）"
                % book_dir()}
    nodes = parse_nodes()
    unknown: dict = {}
    for n in nodes:
        u = unknown_macros(n["blocks"])
        for k, v in u.items():
            unknown[k] = unknown.get(k, 0) + v
    st = {
        "version": STORE_VERSION,
        "built_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "book_dir": str(book_dir().relative_to(ROOT)) if str(book_dir()).startswith(
            str(ROOT)) else book_dir().name,
        "fingerprint": fingerprint(),
        "files": [p.name for p in files],
        "stats": {
            "nodes": len(nodes),
            "files": len(files),
            "chars": sum(n["chars"] for n in nodes),
            "figs": sum(n["n_fig"] for n in nodes),
            "figs_pending": sum(n["n_fig_pending"] for n in nodes),
            "tables": sum(n["n_table"] for n in nodes),
            "unknown_macros": sum(unknown.values()),
        },
        "unknown_macros": dict(sorted(unknown.items(),
                                      key=lambda kv: -kv[1])[:200]),
        "nodes": nodes,
    }
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(STORE)
    _CACHE.clear()
    if verbose:
        s = st["stats"]
        print("知识清单：%d 个节点 / %d 字 / 图 %d 张（未渲染 %d）/ 表 %d 张"
              % (s["nodes"], s["chars"], s["figs"], s["figs_pending"], s["tables"]))
        print("  未展开的书方言宏：%d 处（%d 种）"
              % (s["unknown_macros"], len(st["unknown_macros"])))
        print("  → %s（%.1f KB）" % (STORE.name, STORE.stat().st_size / 1024))
    return {"ok": True, **st["stats"]}


def load() -> dict:
    """读生成物（按 mtime 缓存）。**不需要书在。**"""
    try:
        mt = STORE.stat().st_mtime
    except OSError:
        return {}
    if _CACHE.get("mt") == mt and _CACHE.get("st"):
        return _CACHE["st"]
    try:
        st = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("知识清单生成物读不了：%s", STORE)
        return {}
    _CACHE.update(mt=mt, st=st)
    return st


def stale() -> bool:
    """生成物过期没有？（书比生成物新，或生成物是旧格式）"""
    st = load()
    if not st:
        return True
    if st.get("version") != STORE_VERSION:
        return True
    try:
        return st.get("fingerprint") != fingerprint()
    except OSError:
        return False


def nodes() -> list[dict]:
    return load().get("nodes", [])


def sources() -> dict[str, dict]:
    r"""节点 id → **原文**节点（`body` 是书里没加工过的 LaTeX 源文本）。

    `nodes()` 存的是块级 IR——前端能渲染，但它出不了 LaTeX。要把讲解原样搬进
    新生成的讲义，就得回到源文本这一份。切一本书不便宜，所以缓存在模块上。
    """
    if "src" not in _CACHE:
        _CACHE["src"] = {n["id"]: n for n in _raw_nodes()}
    return _CACHE["src"]


def index() -> dict:
    if "idx" not in _CACHE or _CACHE.get("idx_mt") != _CACHE.get("mt"):
        _CACHE["idx"] = {n["id"]: n for n in nodes()}
        _CACHE["idx_mt"] = _CACHE.get("mt")
    return _CACHE["idx"]


def get_node(nid: str) -> dict | None:
    return index().get(nid)


def tree() -> list[dict]:
    """给前端的目录树（不带正文，免得一次拉 1MB）。"""
    roots: list[dict] = []
    stack: list[tuple[int, dict]] = []
    for n in nodes():
        lv = _LEVELS.index(n["level"]) if n["level"] in _LEVELS else -1
        item = {"id": n["id"], "title": n["title"], "level": n["level"],
                "file": n["file"], "line": n["line"],
                "chars": n["chars"], "n_fig": n["n_fig"], "n_table": n["n_table"],
                "kids": []}
        while stack and stack[-1][0] >= lv:
            stack.pop()
        if stack:
            stack[-1][1]["kids"].append(item)
        else:
            roots.append(item)
        stack.append((lv, item))
    return roots


def search(q: str, *, limit: int = 60) -> list[dict]:
    r"""按标题 + 正文找节点，标题命中的排前面。

    正文走 `blocks_to_text`（一次性缓存），所以这就是**书里那句原话**
    的搜索 —— 老师记得「子集、真子集、集合相等」这句话，但不记得它在
    哪一节，这是最常用的入口。
    """
    q = (q or "").strip()
    if not q:
        return []
    texts = _texts()
    hits: list[tuple[int, dict, str]] = []
    for n in nodes():
        if q in n["title"]:
            hits.append((0, n, ""))
            continue
        body = texts.get(n["id"], "")
        i = body.find(q)
        if i >= 0:
            hits.append((1, n, body[max(0, i - 10):i + 50]))
    hits.sort(key=lambda x: (x[0], -x[1]["chars"]))
    return [{"id": n["id"], "title": n["title"], "file": n["file"],
             "level": n["level"], "line": n["line"], "chars": n["chars"],
             "n_fig": n["n_fig"], "n_table": n["n_table"], "hit": snip}
            for _, n, snip in hits[:limit]]


# ── 考点映射 ─────────────────────────────────────────────────────────

def load_map() -> dict:
    """`{考点id: [节点id,…]}`。人工核定过的那份。"""
    try:
        d = json.loads(MAPFILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d.get("points", d) if isinstance(d, dict) else {}


def map_report() -> dict:
    """映射体检：考点覆盖率、悬空节点、没被任何考点引用的节点。"""
    from . import knowledge
    m = load_map()
    ids = index()
    allp = {p["id"] for p in knowledge.all_points()}
    dangling = sorted({nid for v in m.values() for nid in v if nid not in ids})
    covered = {p for p, v in m.items() if v and p in allp}
    used = {nid for v in m.values() for nid in v}
    return {
        "map_file": MAPFILE.exists(),
        "points_total": len(allp),
        "points_mapped": len(covered),
        "points_missing": sorted(allp - covered),
        "unknown_points": sorted(set(m) - allp),
        "dangling_nodes": dangling,
        "nodes_total": len(ids),
        "nodes_used": len(used & set(ids)),
        "nodes_orphan": sorted(set(ids) - used),
    }


def _terms(text: str) -> set[str]:
    """中文 2–4 字滑窗词（停用字打头/收尾的碎片丢掉）。"""
    t = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    t = re.sub(r"[{}$\\&^_~\[\]]", " ", t)
    t = re.sub(r"\s+", "", t)
    stop = set("的了和与及在是有为对由到之中上下一个不这那就都也很或以于把被让给从向"
               "一二三四五六七八九十百千万第本节章节点常用方法公式概念题型易错进阶综合"
               "问题应用求解判断证明计算")
    out = set()
    for seg in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        for n in (4, 3, 2):
            for i in range(len(seg) - n + 1):
                w = seg[i:i + n]
                if w[0] in stop or w[-1] in stop:
                    continue
                out.add(w)
    return out


def node_text(n: dict) -> str:
    try:
        return lb.blocks_to_text(n["blocks"])
    except Exception:
        return n["title"]


def _texts() -> dict[str, str]:
    """`{节点id: 纯文本}`（搜索用，按 mtime 缓存）。"""
    if "texts" not in _CACHE or _CACHE.get("texts_mt") != _CACHE.get("mt"):
        _CACHE["texts"] = {n["id"]: node_text(n) for n in nodes()}
        _CACHE["texts_mt"] = _CACHE.get("mt")
    return _CACHE["texts"]


def suggest(*, top: int = 6) -> list[dict]:
    r"""给每个考点算候选节点（IDF 加权的内容重合度）。

    **只是候选**：书按教材编、题库按考纲编，两套不同源，实测纯标题匹配只有
    21/152 可信。所以这里出候选、人过一遍，结果固化进 `知识清单映射.json`。
    """
    from . import knowledge
    import math
    ns = nodes()
    nt = [_terms(n["title"] * 3 + " " + node_text(n)) for n in ns]
    df: dict = {}
    for ts in nt:
        for w in ts:
            df[w] = df.get(w, 0) + 1
    N = max(1, len(ns))
    out = []
    for p in knowledge.all_points():
        src = p["title"]
        for v in (p.get("fields") or {}).values():
            if isinstance(v, list):
                src += " " + " ".join(str(x) for x in v)
            else:
                src += " " + str(v)
        pt = _terms(src)
        if not pt:
            continue
        w = {x: math.log(1 + N / (1 + df.get(x, 0))) for x in pt}
        tot = sum(w.values()) or 1.0
        scored = []
        for n, ts in zip(ns, nt):
            if len(ts) < 30:
                continue
            hit = sum(w[x] for x in pt & ts)
            scored.append((round(hit / tot, 4), n["id"], n["title"]))
        scored.sort(key=lambda x: -x[0])
        out.append({"pid": p["id"], "title": p["title"],
                    "cands": scored[:top]})
    return out


# ── 自检 ─────────────────────────────────────────────────────────────

def _selftest() -> int:
    bad = 0

    def check(name, ok, extra=""):
        nonlocal bad
        print("%-46s %s %s" % (name, "OK" if ok else "✗ 不对", extra))
        if not ok:
            bad += 1

    check("dialect: \\lra 展开", r"\longrightarrow" in dialect(r"$a\lra b$"))
    check("dialect: \\ra 不咬 \\rangle",
          r"\rangle" in dialect(r"$\langle a,b\rangle$"))
    check("dialect: \\R 展开", r"\mathbb{R}" in dialect(r"$x\in\R$"))
    check("dialect: \\abs 展开",
          r"\left| x \right|" in dialect(r"$\abs{x}$"))
    check("dialect: \\abs* 展开",
          r"\left| x \right|" in dialect(r"$\abs*{x}$"))
    check("dialect: \\dg 展开", r"^{\circ}" in dialect(r"$90\dg$"))
    check("dialect: \\thead 拆壳",
          "易错点" in dialect(r"\thead{易错点}") and "thead" not in dialect(r"\thead{易错点}"))
    check("dialect: \\thead 里的 \\ 变空格",
          dialect(r"\thead{a\\b}") == "a b")
    check("dialect: \\textcircled 变带圈数字",
          "③" in dialect(r"\textcircled{\scriptsize 3}"))
    check("dialect: 注释连换行一起吃掉",
          dialect("甲%注\n乙") == "甲乙")
    check("dialect: appenum 编号落成文字",
          "94." in dialect("\\begin{appenum}\n\\setcounter{appenumi}{93}\n"
                           "\\item 甲\n\\item 乙\n\\end{appenum}"))
    check("dialect: appenum 变 itemize",
          "\\begin{itemize}" in dialect("\\begin{appenum}\\item 甲\\end{appenum}"))
    app = dialect("\\begin{appenum}\n\\setcounter{appenumi}{93}\n"
                  "\\item 甲\n\\item[\\textbf{53.}] 乙\n\\item 丙\n\\end{appenum}")
    check("dialect: 带标签的 \\item 不占号",
          "94." in app and "95." in app and "96." not in app)
    check("dialect: notebox 变 quote",
          "\\begin{quote}" in dialect("\\begin{notebox}甲\\end{notebox}"))
    check("dialect: \\\\[3pt] 收成 \\\\",
          "\\\\[" not in dialect("\\begin{tabular}{cc}a\\\\[3pt]b\\end{tabular}"))
    check("dialect: \\numline 展成 tikzpicture",
          "\\begin{tikzpicture}" in dialect("\\numline{\\draw (0,0) -- (1,0);}"))
    check("dialect: \\srcgap 变【补录】",
          "【补录】" in dialect("\\srcgap{这是补的}"))
    check("dialect: \\multirow 拆壳",
          "甲" in dialect("\\multirow{2}{*}{甲}")
          and "multirow" not in dialect("\\multirow{2}{*}{甲}"))
    _lst = dialect("\\begin{list}{}{\\setlength{\\leftmargin}{2em}}\n"
                   "\\item[(1)] 甲\n\\item[(2)] 乙\n\\end{list}")
    check("dialect: list 环境变 itemize",
          "\\begin{itemize}" in _lst and "setlength" not in _lst)
    check("dialect: list 的方括号标签落成正文",
          _lst.count("(1)") == 1 and "\\item[" not in _lst)
    check("dialect: \\paragraph 变加粗段",
          "\\textbf{系列1}" in dialect("\\paragraph{系列1}")
          and "paragraph" not in dialect("\\paragraph{系列1}"))
    check("dialect: \\textsc 拆壳",
          "（I）" in dialect("\\textsc{（I）}")
          and "textsc" not in dialect("\\textsc{（I）}"))
    check("dialect: 排版指令整条丢掉",
          dialect("甲\\hfill 乙\\begingroup\\endgroup") .strip() == "甲 乙")
    # 图里的 `\scalebox{1.6}{通径}`、`\\[2pt]`、`\cu` 必须**原样留着**：
    # 渲染图用的是书自己的 preamble，展开只会把图画小、画歪。
    _fig = ("\\begin{tikzpicture}\\node{\\scalebox{1.6}{通径}\\\\[2pt]$\\cu_U A$};"
            "\\end{tikzpicture}")
    check("dialect: 图里的内容一个字不动", dialect(_fig) == _fig)
    check("dialect: 图外的照样展开",
          "\\complement" in dialect(_fig + "$\\cu_U A$"))

    check("fig_key 稳定且带前缀", fig_key("\\begin{tikzpicture}\\end{tikzpicture}")
          .startswith(FIG_PREFIX))
    check("collect_tikz 收裸 axis",
          len(collect_tikz("\\begin{axis}\\addplot{x};\\end{axis}")) == 1)

    check("clean_title 去 \\quad",
          clean_title(r"1.1.3\quad 集合的基本运算") == "1.1.3 集合的基本运算")

    st = load()
    if st:
        ids = index()
        check("生成物有节点", len(st.get("nodes", [])) > 100,
              "%d 个" % len(st.get("nodes", [])))
        check("节点 id 唯一", len(ids) == len(st.get("nodes", [])))
        rep = map_report()
        if rep["map_file"]:
            check("映射无悬空节点", not rep["dangling_nodes"],
                  str(rep["dangling_nodes"][:3]))
            check("映射无未知考点", not rep["unknown_points"],
                  str(rep["unknown_points"][:3]))
            check("考点全覆盖", rep["points_missing"] == [],
                  "缺 %d 个" % len(rep["points_missing"]))
        else:
            print("%-46s —  %s" % ("映射三项（悬空/未知考点/全覆盖）",
                                   "还没建 %s，跳过" % MAPFILE.name))
        left = st.get("stats", {}).get("unknown_macros", 0)
        check("没剩下未展开的书方言宏", left == 0, "%d 处" % left)
        hits = search("子集")
        check("搜索能命中正文", bool(hits), "%d 条" % len(hits))
        check("空搜索不返回", search("") == [] and search("   ") == [])
    else:
        print("（还没生成 讲义/知识清单.json，跳过生成物自检）")
    print("知识清单自检：%s" % ("%d 项失败" % bad if bad else "全过"))
    return bad


def main(argv: list[str] | None = None) -> int:
    r"""`python3 -m amti.klist [check|build|figs|suggest|map]`（默认自检）。

    这几个命令**只有重新生成才需要**：应用运行时只读
    `讲义/知识清单.json` 与 `图片/klist-*.png`，书不在也照跑。
    """
    import sys
    cmd = list(argv if argv is not None else sys.argv[1:]) or ["check"]
    what = cmd[0]
    if what in ("check", "--selftest", "-s"):
        return 1 if _selftest() else 0
    if what == "build":
        return 0 if build().get("ok") else 1
    if what == "figs":
        r = render_figures(force="--force" in cmd)
        for e in r["errors"][:10]:
            print("  ✗ %s：%s" % (e["key"], e["err"]))
        print("图：%d 张（待渲染 %d，成功 %d，失败 %d）"
              % (r["total"], r["todo"], r["ok"], r["fail"]))
        return 1 if r["fail"] else 0
    if what == "suggest":
        print(json.dumps(suggest(), ensure_ascii=False, indent=1))
        return 0
    if what == "map":
        rep = map_report()
        print("考点 %d/%d 已映射，节点 %d/%d 被引用"
              % (rep["points_mapped"], rep["points_total"],
                 rep["nodes_used"], rep["nodes_total"]))
        for k, v in (("没映射的考点", rep["points_missing"]),
                     ("映射里的未知考点", rep["unknown_points"]),
                     ("指向不存在节点的引用", rep["dangling_nodes"])):
            if v:
                print("  ✗ %s %d：%s" % (k, len(v), v[:5]))
        return 1 if (rep["points_missing"] or rep["unknown_points"]
                     or rep["dangling_nodes"]) else 0
    print("\n用法：python3 -m amti.klist [check|build|figs|suggest|map]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
