"""LaTeX 正文 → 块级 IR。**全项目唯一的正文解析器。**

为什么必须有它
--------------
前端一度自己写了一份 LaTeX→HTML 解析器（`web/src/lib/render.tsx`），
和 Python 这份重复。实测它至少错四处，全部是真实报障：

  1. `readEnv` 结束位置用了 `env.length + 5`，少算一个字符
     → 答案末尾漏出一个孤零零的 `}`。
  2. 不跳过 `tabular` 的 `{列格式}`
     → 表格第一行变成 `{|c|cccccccccc|ccccccccc|}`。
  3. `\\item` 无脑切分，不认嵌套
     → 内层 enumerate 被拍平，`\\end{enumerate}` 直接漏到页面上。
  4. `center` / `minipage` 没处理
     → `\\begin{center}` 当正文显示。

全量库 20706 题里 25.1% 带列表、2.3% 带表格、2.3% 带 center，
靠在前端打补丁是追不平的。所以这里定死分工：

    **Python 解析一次 → 块级 IR → 前端只负责画。**
    前端不再碰 LaTeX 语法，只把 `math` 节点交给 KaTeX。

IR 结构（全部可 JSON 序列化）
----------------------------
块：
    {"t":"p",     "in":[Inline,…]}                    段落
    {"t":"math",  "tex":"…", "display":true}          独立公式
    {"t":"list",  "ordered":bool, "items":[[Block]]}  列表（可嵌套）
    {"t":"table", "rows":[[Cell,…]]}                  表格
    {"t":"box",   "kind":"center", "width":…,
                  "blocks":[Block]}                   居中/小页容器
    {"t":"fig",   "id":"….png", "width":"40%"}        独立插图
    {"t":"raw",   "env":"tikzpicture", "tex":"…"}      HTML 画不了，交回前端提示

行内：
    {"t":"s",     "s":"文本"}
    {"t":"m",     "s":"TeX", "display":bool}
    {"t":"fig",   "id":"….png", "width":"40%"}
    {"t":"blank"}                                      \\fillin 的空
    {"t":"paren"}                                      括号空（exam-zh 的 \\paren）
    {"t":"br"}                                         强制换行
    {"t":"sp"}                                          \\quad 之类的空白
    {"t":"raw",   "s":"\\foo"}                         没见过的宏——显式标出来，不静默吞掉
"""

from __future__ import annotations

import re

# ── 环境分类 ─────────────────────────────────────────────

LIST_ENVS = {"enumerate", "itemize", "description"}
TABLE_ENVS = {"tabular", "tabularx", "longtable"}
BOX_ENVS = {"center", "flushleft", "flushright", "minipage", "quote", "verse",
            "multicols", "figure", "table", "subfigure", "adjustbox"}
RAW_ENVS = {"tikzpicture", "pgfpicture", "circuitikz", "axis"}
DISPLAY_MATH_ENVS = {
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "displaymath",
    "alignat", "alignat*", "flalign", "flalign*",
}
# 只在数学模式里出现。顶层碰到也当公式块，绝不按正文渲染。
MATH_ONLY_ENVS = {"cases", "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix",
                  "smallmatrix", "array", "aligned", "alignedat", "gathered",
                  "subarray", "split", "dcases", "rcases"}

# 这些宏吃一个 `{…}` 参数，整个丢掉
_DROP_ARG = {"label", "index", "tag", "vspace", "hspace", "cline", "caption",
             "nonumber", "notag", "hfill", "hfil", "pageref", "ref", "cite"}
# 这些宏吃一个 `{…}` 参数，但要保留内容
_UNWRAP_ARG = {"textbf", "textit", "textrm", "textsf", "texttt", "textnormal",
               "emph", "mbox", "hbox", "fbox", "underline", "mathrm", "mathbf",
               "mathit", "mathsf", "mathtt", "operatorname", "text",
               "ensuremath", "textsuperscript", "textsubscript", "bm",
               "boldsymbol", "vec", "overline", "widehat", "widetilde"}
# 这两个吃两个参数，保留第二个
_UNWRAP_2ARG = {"parbox", "raisebox"}
# 这些**先吃若干 `[可选参数]`，再吃一个 `{…}` 并保留内容**。
# `\makebox[0.22\linewidth][c]{\includegraphics…}` 就是这么写的——
# 只认 `{}{}`（老写法）会把整条命令当正文漏到卷面上。
# 实测：2000 大纲卷（理）、2010 新课标卷（文/理）、2014 广东卷（文）、
#       2009 湖北卷（理）、2008 四川延考卷（理）等 8 卷都因此报「渲染残留」。
# ⚠️ **不要放 `resizebox` / `scalebox`**：它们吃的是 `{}{}{}` 三个花括号参数，
# 放进来会被当"吃一个 `[…]` 再留一个 `{…}`"处理，
# 于是 `\resizebox{!}{\linewidth}{内容}` 的 `{\linewidth}` 被当内容展开、
# 泄漏到卷面上（实测 2023 北京卷#18 等 3 道）。
# 它们由下面的 `resizebox` 专用分支处理。
_UNWRAP_OPT_ARG = {"makebox", "framebox", "raisebox",
                   "adjustbox", "rotatebox"}
# `\parbox[位置][高][内位]{宽}{内容}`——**宽度也是花括号参数**，
# 要吃掉再保留内容。放进 `_UNWRAP_OPT_ARG` 会把 `{\linewidth}` 当内容展开，
# 泄漏出 `\linewidth`（实测 2014 山东卷（文）#11）。
_UNWRAP_WIDTH_ARG = {"parbox"}
# `\diaghead{左上}{右下}` 是 diagbox 的**斜线表头**，两个参数都是文字，
# 拼成「左上/右下」显示即可。不处理会以原文显形
# （实测：2027千题册经典重点册（下）#39）。
_UNWRAP_DIAG = {"diaghead", "diagbox"}
# 看一眼就知道、但**不该显示**的空格类命令
_DROP_ARG = _DROP_ARG | {"phantom", "hphantom", "vphantom", "smash", "rlap",
                         "llap", "mathstrut", "strut", "vspace", "hspace"}
# 无参数、直接丢
_DROP_BARE = {"noindent", "centering", "small", "large", "Large", "LARGE", "huge",
              "normalsize", "tiny", "bfseries", "itshape", "rmfamily", "sffamily",
              "ttfamily", "rm", "bf", "it", "tt", "newline", "par", "hline",
              "toprule", "midrule", "bottomrule", "hdashline", "left", "right",
              "displaystyle", "textstyle", "scriptstyle", "limits", "nolimits",
              "quad", "qquad", "centering", "arraystretch", "cline", "hline",
              "bigskip", "medskip", "smallskip", "clearpage", "newpage"}

_FIG_RE = re.compile(r"\\includegraphics\s*(\[[^\]]*\])?\s*\{([^}]*)\}")
_BEGIN_RE = re.compile(r"\\begin\s*\{([a-zA-Z*]+)\}")
_CMD_RE = re.compile(r"\\([a-zA-Z]+)\s*\*?")
_ITEM_RE = re.compile(r"\\item(?![a-zA-Z])\s*\*?\s*(\[[^\]]*\])?")
_MULTICOL_RE = re.compile(r"\\multicolumn\s*\{(\d+)\}\s*\{")
_RULE_LINE_RE = re.compile(
    r"\\(?:hline|toprule|midrule|bottomrule|hdashline|cline\s*\{[^}]*\})")
_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
# 「文字符号」命令：直接换成对应字符。
# 少了这张表，`\textasciitilde` 会以原文显形（2023 新高考I卷#10 的声压级表）
_TEXT_SYMBOLS = {
    "textasciitilde": "~", "textbackslash": "\\", "textasciicircum": "^",
    "textbar": "|", "textless": "<", "textgreater": ">",
    "textbraceleft": "{", "textbraceright": "}", "textunderscore": "_",
    "ldots": "…", "dots": "…", "textellipsis": "…",
    "textquotedblleft": "“", "textquotedblright": "”",
    "textquoteleft": "‘", "textquoteright": "’",
    "textendash": "–", "textemdash": "—", "textdegree": "°",
}
_ESCAPED = {"%": "%", "&": "&", "_": "_", "#": "#", "$": "$",
            "{": "{", "}": "}", " ": " ", "-": "", "/": "",
            ",": "", ";": "", ":": "", "!": ""}


# ── 底层扫描：一律做括号/环境配对，不用非贪婪正则 ──────────

def skip_brace(s: str, i: int) -> int:
    """`s[i] == '{'`，返回配对 `}` 之后的下标。"""
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def skip_opt(s: str, i: int) -> int:
    """`s[i] == '['`，返回配对 `]` 之后的下标（跳过其中的 `{}`）。"""
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            i = skip_brace(s, i)
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def read_env(s: str, i: int):
    """`s[i:]` 以 `\\begin{env}` 开头 → `(env, body_start, body_end, end)`。

    同名环境按深度配对，`\\begin{tabular}…\\end{tabular}` 相邻两张表不会串。
    """
    m = _BEGIN_RE.match(s, i)
    if not m:
        return None
    env = m.group(1)
    body_start = m.end()
    open_tag, close_tag = "\\begin{%s}" % env, "\\end{%s}" % env
    depth = 1
    j = body_start
    n = len(s)
    while j < n:
        o = s.find(open_tag, j)
        c = s.find(close_tag, j)
        if c < 0:                      # 环境没闭合：吃到结尾，不吞掉后续内容
            return env, body_start, n, n
        if 0 <= o < c:
            depth += 1
            j = o + len(open_tag)
            continue
        depth -= 1
        if depth == 0:
            return env, body_start, c, c + len(close_tag)
        j = c + len(close_tag)
    return env, body_start, n, n


def scan_math(s: str, i: int):
    """`s[i:]` 是一个数学片段 → `(tex, end, display)`；不是则 `None`。"""
    if s.startswith("$$", i):
        j = s.find("$$", i + 2)
        j = len(s) if j < 0 else j
        return s[i + 2:j], min(j + 2, len(s)), True
    if s.startswith("\\[", i):
        j = s.find("\\]", i + 2)
        j = len(s) if j < 0 else j
        return s[i + 2:j], min(j + 2, len(s)), True
    if s.startswith("\\(", i):
        j = s.find("\\)", i + 2)
        j = len(s) if j < 0 else j
        return s[i + 2:j], min(j + 2, len(s)), False
    if s[i] == "$":
        j = i + 1
        n = len(s)
        while j < n:
            if s[j] == "\\":
                j += 2
                continue
            if s[j] == "$":
                return s[i + 1:j], j + 1, False
            j += 1
        return None                    # 落单的 `$`，当普通字符，不吞正文
    return None


def split_top(s: str, sep: str) -> list[str]:
    """按**顶层**分隔符切分；跳过 `{…}`、`$…$`、`\\begin…\\end` 内部。"""
    out, cur, i, n = [], [], 0, len(s)
    brace = env = 0
    in_math = False
    while i < n:
        c = s[i]
        if c == "\\":
            if not (brace or env or in_math):
                if sep == "\\\\" and s.startswith("\\\\", i):
                    out.append("".join(cur)); cur = []; i += 2; continue
                if sep == "&":
                    pass
            if s.startswith("\\begin{", i):
                env += 1
            elif s.startswith("\\end{", i):
                env = max(0, env - 1)
            elif s.startswith("\\[", i):
                in_math = True
            elif s.startswith("\\]", i):
                in_math = False
            cur.append(c)
            if i + 1 < n:
                cur.append(s[i + 1]); i += 2; continue
            i += 1; continue
        if c == "{":
            brace += 1
        elif c == "}":
            brace = max(0, brace - 1)
        elif c == "$":
            in_math = not in_math
        if not (brace or env or in_math) and c == sep and sep != "\\\\":
            out.append("".join(cur)); cur = []; i += 1; continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def _strip_rules(s: str) -> str:
    """去掉 `\\hline` / `\\cline{…}` / booktabs 横线，但保留换行结构。"""
    return _RULE_LINE_RE.sub("", s)


# ── 行内解析 ─────────────────────────────────────────────

def _width_pct(opt: str | None) -> str:
    """`width=0.4\\linewidth` → `40%`；`width=6cm` → 按 15cm 版心折算。"""
    if not opt:
        return "45%"
    m = re.search(r"width\s*=\s*([\d.]+)\s*\\(?:line|text)?width", opt)
    if m:
        return "%d%%" % max(5, min(100, round(float(m.group(1)) * 100)))
    m = re.search(r"width\s*=\s*([\d.]+)\s*(cm|mm|in|pt)", opt)
    if m:
        v, unit = float(m.group(1)), m.group(2)
        cm = {"cm": v, "mm": v / 10, "in": v * 2.54, "pt": v / 28.45}[unit]
        return "%d%%" % max(5, min(100, round(cm / 15.0 * 100)))
    return "45%"


def _fig_inline(opt: str | None, name: str) -> dict:
    return {"t": "fig", "id": name.strip(), "width": _width_pct(opt)}


# exam-zh 的 `\fillin` / `\paren` 是**文本命令**，但原始语料里常写在 `$…$` 内部
# （如 `$\log_3 \frac{1}{27}=\fillin{}$`，旧库原样如此，不是归一化搬进去的）。
# XeLaTeX 编译正常、PDF 里就是个空位；KaTeX 不认它，会把它当普通文本画出来。
# 所以这里按它把数学片段断开——前后两段交 KaTeX，空位走 blank 节点。
# 这样 HTML 与 PDF 表现一致，也不必去改存量题目的内容指纹。
_MATH_SPECIAL_RE = re.compile(
    r"\\(fillin|paren)(?![a-zA-Z])\s*\*?(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\})?")


def _skip_cmd_args(s: str, i: int) -> int:
    r"""吃掉命令后面跟着的 `{}` / `[]` 参数，返回之后的下标。

    `\fillin` / `\paren` 都长这样：

        \fillin                什么都不带
        \fillin{}              空花括号
        \fillin[$42$]          **方括号里是答案**
        \paren[B]

    ⚠️ 答案必须**整段吞掉**。少吞了就会连答案一起画在卷面上：

        $\theta=\fillin[$\frac{3\pi}{2}$]$   →   θ = ____ [\frac{3\pi}{2}]

    实测：2026 全国I卷#13、北京卷#14、天津卷#14、上海卷（秋）#11 都中过。
    注意 `\fillin` 有**两处**处理代码——`$…$` 外的走 `inline()`，
    `$…$` 里的走这里。两处都得吞参数，只改一处会漏掉一半的题。
    """
    n = len(s)
    while i < n and s[i] in " \t":
        i += 1
    while i < n and s[i] in "[{":
        i = skip_opt(s, i) if s[i] == "[" else skip_brace(s, i)
        while i < n and s[i] in " \t":
            i += 1
    return i


_DELIM_CHARS = "()[]|./{<>"


def _unpair_delims(tex: str) -> str:
    r"""把 `\left` / `\right` 换成**不要求配对**的 `\bigl` / `\bigr`。

    公式一旦被 `\fillin` 切开，`\left(` 和 `\right)` 就落到两段里了，
    KaTeX 会报 "Expected '\right', got 'EOF'"。
    实测：1999 上海卷（理）#5 的 `$O'\left(\fillin[2],\fillin[2]\right)$`。

    `\bigl(` / `\bigr)` 是独立合法的，尺寸也接近，切开的每一段都能单独渲染。

    只在**后面真的跟着定界符**时才换——`\bigl` 后面没东西照样报错。
    """
    def sub(m):
        cmd, rest = ("\\bigl", tex[m.end():]) if m.group(1) == "left" else \
                     ("\\bigr", tex[m.end():])
        k = 0
        while k < len(rest) and rest[k] == " ":
            k += 1
        if k < len(rest) and rest[k] in _DELIM_CHARS:
            return cmd
        return m.group(0)
    return re.sub(r"\\(left|right)(?![a-zA-Z])", sub, tex)


def _emit_math(tex: str, display: bool, out: list[dict]) -> None:
    """把一段数学切成 `[math, blank/paren, math, …]`。"""
    hits = list(_MATH_SPECIAL_RE.finditer(tex))
    # ⚠️ 公式里有**环境**（`\begin{cases}`、`array`、`matrix`…）时**不能切**：
    # `\begin{cases}` 和 `\end{cases}` 会落到两段公式里，
    # KaTeX 直接报 "Expected & or \\\\ or \cr"（实测 2004 全国I卷（理）#15）。
    #
    # 代价是这一段的空位不再画成下划线，整段交给 KaTeX 渲染。
    # **宁可少一个装饰，也不能渲染报错**——报错是整页都看不出东西。
    if not hits or "\\begin{" in tex:
        # 切不开时，把 `\fillin[答案]` / `\paren[答案]` 换成 **KaTeX 认得的空位**：
        #   \fillin[答案] → \underline{\hspace{2em}}
        #   \paren[答案]  → (\quad)
        # 答案仍然不显示（这是卷面该有的样子），但公式能正常渲染。
        safe = _MATH_SPECIAL_RE.sub(
            lambda m: ("\\underline{\\hspace{2em}}"
                       if m.group(1) == "fillin" else "(\\quad)"), tex)
        out.append({"t": "m", "s": safe, "display": display})
        return
    # 切开之后就不再是一个整体公式了，逐段按**行内**渲染，
    # 否则每段都按行间公式排版，会竖着叠成好几行。
    pos = 0
    for m in hits:
        head = tex[pos:m.start()]
        if head.strip():
            out.append({"t": "m", "s": head.strip(), "display": False})
        out.append({"t": "blank" if m.group(1) == "fillin" else "paren"})
        # **必须吃掉命令后面的参数**（方括号里就是答案），否则答案漏到卷面上
        pos = _skip_cmd_args(tex, m.end())
    tail = tex[pos:]
    if tail.strip():
        out.append({"t": "m", "s": tail.strip(), "display": False})
    # 切开之后每段都得能**单独**渲染，`\left…\right` 要拆成独立的定界符
    for nd in out:
        if nd["t"] == "m":
            nd["s"] = _unpair_delims(nd["s"])


def inline(s: str) -> list[dict]:
    """把一段正文（可能混着公式/图/空）切成行内节点序列。"""
    out: list[dict] = []
    text: list[str] = []

    def flush() -> None:
        if text:
            t = "".join(text)
            if t:
                out.append({"t": "s", "s": t})
            text.clear()

    i, n = 0, len(s)
    while i < n:
        c = s[i]

        # ── 数学 ──
        if c == "$" or s.startswith("\\[", i) or s.startswith("\\(", i):
            r = scan_math(s, i)
            if r and r[0].strip():
                tex, end, disp = r
                flush()
                fm = _FIG_RE.fullmatch(tex.strip())
                if fm:
                    # 整段公式其实就是一张图（旧项目在这里炸过 814 处）
                    out.append(_fig_inline(fm.group(1), fm.group(2)))
                else:
                    _emit_math(tex.strip(), bool(disp), out)
                i = end
                continue

        # ── 反斜杠命令 ──
        if c == "\\":
            if i + 1 >= n:
                break
            nxt = s[i + 1]

            if nxt == "\\":                                   # 强制换行
                flush(); out.append({"t": "br"})
                i += 2
                if i < n and s[i] == "[":
                    i = skip_opt(s, i)
                continue
            if nxt in _ESCAPED:                               # \% \& \_ \,
                if nxt == " ":
                    text.append(" ")
                elif nxt not in ",;:!-/":
                    text.append(_ESCAPED[nxt])
                i += 2
                continue

            m = _FIG_RE.match(s, i)
            if m:
                flush(); out.append(_fig_inline(m.group(1), m.group(2)))
                i = m.end(); continue

            # ⚠️ `\fillin` 后面**可能是方括号答案**（`\fillin[$\frac{3}{2}$]`），
            # 也可能是花括号（`\fillin{}`），还可能什么都不带。
            # 早先只跳花括号，于是方括号连答案一起被当成正文画出来：
            #     `则 \sin B=\fillin[$\frac{3\sqrt{15}}{16}$]`
            #   → 「则 sinB = ____ [\frac{3\sqrt{15}}{16}]」
            # 实测 2026 天津卷#12 报障。两种都要跳过。
            m = re.match(r"\\fillin(?![a-zA-Z])", s[i:])
            if m:
                flush(); out.append({"t": "blank"})
                i = _skip_cmd_args(s, i + m.end())
                continue

            if re.match(r"\\paren(?![a-zA-Z])", s[i:]):
                flush(); out.append({"t": "paren"})
                i = _skip_cmd_args(s, i + len("\\paren"))
                continue

            m = _MULTICOL_RE.match(s, i)                       # 表格里才该出现
            if m:
                j = skip_brace(s, m.end() - 1)                 # 跳过列格式
                k = skip_brace(s, j) if j < n and s[j] == "{" else j
                inner = s[j + 1:k - 1] if k > j else ""
                sub = inline(inner)
                flush()
                out.extend(sub)
                i = k; continue

            m = _CMD_RE.match(s, i)
            if m:
                name = m.group(1)
                j = m.end()
                if name in _TEXT_SYMBOLS:                 # \textasciitilde → ~
                    flush(); text.append(_TEXT_SYMBOLS[name]); i = j; continue
                if name in _DROP_BARE:
                    i = j; continue
                if name in ("quad", "qquad"):
                    flush(); out.append({"t": "sp"}); i = j; continue
                # `\diaghead{学员}{科目}` → 「学员/科目」
                if name in _UNWRAP_DIAG and j < n and s[j] == "{":
                    k = skip_brace(s, j)
                    if k < n and s[k] == "{":
                        e = skip_brace(s, k)
                        flush()
                        out.extend(inline(s[j + 1:k - 1] + "/" + s[k + 1:e - 1]))
                        i = e; continue
                    i = k; continue
                # `\parbox[位置][高]{宽}{内容}`：吃掉宽度，保留内容
                if name in _UNWRAP_WIDTH_ARG and j < n:
                    k = j
                    while k < n and s[k] == "[":
                        k = skip_opt(s, k)
                        while k < n and s[k] in " \t":
                            k += 1
                    if k < n and s[k] == "{":
                        k = skip_brace(s, k)              # 宽度，丢
                    if k < n and s[k] == "{":
                        e = skip_brace(s, k)
                        flush(); out.extend(inline(s[k + 1:e - 1]))
                        i = e; continue
                    i = k; continue
                # `\makebox[宽][对齐]{内容}`：先吃 `[…]`，再保留 `{…}`
                if name in _UNWRAP_OPT_ARG and j < n:
                    k = j
                    while k < n and s[k] == "[":
                        k = skip_opt(s, k)
                        while k < n and s[k] in " \t":
                            k += 1
                    if k < n and s[k] == "{":
                        e = skip_brace(s, k)
                        flush(); out.extend(inline(s[k + 1:e - 1]))
                        i = e; continue
                    i = k; continue
                # `\resizebox{!}{\linewidth}{内容}`：吃两个参数，**保留第三个**
                # （2023 北京卷#18 用它把大表格缩到页宽）
                if name == "resizebox" and j < n and s[j] == "{":
                    k = skip_brace(s, j)
                    k2 = skip_brace(s, k) if k < n and s[k] == "{" else k
                    if k2 < n and s[k2] == "{":
                        e = skip_brace(s, k2)
                        flush(); out.extend(inline(s[k2 + 1:e - 1])); i = e; continue
                    i = k2; continue
                if name in _UNWRAP_2ARG and j < n and s[j] == "{":
                    k = skip_brace(s, j)
                    if k < n and s[k] == "{":                  # 保留第二个参数
                        e = skip_brace(s, k)
                        flush(); out.extend(inline(s[k + 1:e - 1])); i = e; continue
                    i = k; continue
                if name in _DROP_ARG and j < n and s[j] == "{":
                    i = skip_brace(s, j); continue
                if name in _UNWRAP_ARG and j < n and s[j] == "{":
                    k = skip_brace(s, j)
                    flush(); out.extend(inline(s[j + 1:k - 1])); i = k; continue
                if name == "rule":
                    # `\rule[升降]{宽}{高}`——升降是**方括号**，
                    # 老写法只认 `{`，于是带 `[...]` 的 `\rule` 会整条漏到卷面上
                    # （实测 2009 湖北卷（理）#10 的 makebox 里就有一个）
                    while j < n and s[j] == "[":
                        j = skip_opt(s, j)
                    while j < n and s[j] == "{":
                        j = skip_brace(s, j)
                    i = j; continue
                # 没见过的宏：保留原文，让它在页面上显形，而不是静默消失
                flush()
                raw = s[i:j]
                if j < n and s[j] == "{":
                    k = skip_brace(s, j)
                    raw = s[i:k]; j = k
                out.append({"t": "raw", "s": raw})
                i = j; continue

            text.append(nxt)                                   # 未知转义：留字符
            i += 2
            continue

        text.append(c)
        i += 1

    flush()
    return _merge_text(out)


def _merge_text(nodes: list[dict]) -> list[dict]:
    """合并相邻文本、把纯空白文本压成规范形式。"""
    out: list[dict] = []
    for nd in nodes:
        if nd["t"] == "s":
            t = re.sub(r"[ \t]*\n[ \t]*", "\n", nd["s"])
            if not t:
                continue
            if out and out[-1]["t"] == "s":
                out[-1]["s"] += t
            else:
                out.append({"t": "s", "s": t})
        else:
            out.append(nd)
    # 段首段尾空白丢掉
    if out and out[0]["t"] == "s":
        out[0]["s"] = out[0]["s"].lstrip()
    if out and out[-1]["t"] == "s":
        out[-1]["s"] = out[-1]["s"].rstrip()
    return [x for x in out if not (x["t"] == "s" and not x["s"])]


# ── 块解析 ───────────────────────────────────────────────

def _flush(buf: list[str], blocks: list[dict]) -> None:
    if not buf:
        return
    raw = "".join(buf).strip()
    buf.clear()
    if not raw.strip():
        return
    nodes = inline(raw)
    if not nodes:
        return
    # 段落里夹着插图时拆出来，让图独占一行（居中、好排版）
    run: list[dict] = []
    for nd in nodes:
        if nd["t"] == "fig":
            if run:
                blocks.append({"t": "p", "in": run}); run = []
            blocks.append({"t": "fig", "id": nd["id"], "width": nd["width"]})
        else:
            run.append(nd)
    if run:
        blocks.append({"t": "p", "in": run})


def _make_list(env: str, body: str) -> dict:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    i, n = 0, len(body)
    while i < n:
        if body.startswith("\\begin{", i):
            depth += 1
        elif body.startswith("\\end{", i):
            depth = max(0, depth - 1)
        if depth == 0:
            m = _ITEM_RE.match(body, i)
            if m:
                parts.append("".join(cur)); cur = []
                i = m.end(); continue
        cur.append(body[i]); i += 1
    parts.append("".join(cur))

    head = parts[0].strip()
    items = [parse_blocks(p) for p in parts[1:]]
    ordered = env != "itemize"
    node: dict = {"t": "list", "ordered": ordered, "items": items}
    if head and env == "description":
        node["head"] = inline(head)
    return node


def _take_minipage_args(body: str):
    m = re.match(r"\s*(\[[^\]]*\])?", body)
    i = m.end()
    if i < len(body) and body[i] == "{":
        k = skip_brace(body, i)
        return body[k:], body[i + 1:k - 1]
    return body, None


def _cell_has_table(cell: str) -> bool:
    r"""单元格里有没有**嵌套的表格**。

    老卷子常拿 `tabular` 套 `tabular` 做排版：外面两列放两张数表、
    表头单元格里再套一个两行的小表。`inline()` 认不出嵌套的
    `\begin{tabular}`，会把它们当普通文字漏出去
    （实测：2026 北京卷#21、2016 天津卷（文）#16）。
    """
    return bool(re.search(r"\\begin\{(?:%s)\}" % "|".join(TABLE_ENVS), cell))


def _make_table(env: str, src: str, bs: int, be: int) -> dict:
    body = src[bs:be]
    # 跳过列格式 `{…}`：tabularx 是 `{宽度}{列格式}` 两个
    for _ in range(2 if env == "tabularx" else 1):
        s = body.lstrip()
        if s[:1] != "{":
            break
        body = s[skip_brace(s, 0):]
    body = _strip_rules(body)

    rows: list[list[dict]] = []
    for raw_row in split_top(body, "\\\\"):
        if not raw_row.strip():
            continue
        cells: list[dict] = []
        for raw_cell in split_top(raw_row, "&"):
            span = 1
            cell = raw_cell
            m = _MULTICOL_RE.match(cell.lstrip())
            if m:
                span = int(m.group(1))
                s = cell.lstrip()
                j = skip_brace(s, m.end() - 1)
                k = skip_brace(s, j) if j < len(s) and s[j] == "{" else j
                cell = s[j + 1:k - 1] if k > j else ""
            if _cell_has_table(cell):
                # 嵌套表格：整格按**块**解析，画的时候再嵌一层表格
                cells.append({"blocks": parse_blocks(cell), "span": span})
            else:
                c = inline(cell)
                if c or span > 1:
                    cells.append({"in": c, "span": span})
        if any(c.get("in") or c.get("blocks") for c in cells) or len(cells) > 1:
            rows.append(cells)
    return {"t": "table", "rows": rows, "env": env}


def parse_blocks(src: str) -> list[dict]:
    """正文 LaTeX → 块级 IR。"""
    if not src:
        return []
    src = _COMMENT_RE.sub("", src)

    blocks: list[dict] = []
    buf: list[str] = []
    i, n = 0, len(src)

    while i < n:
        # ── 环境 ──
        if src.startswith("\\begin{", i):
            r = read_env(src, i)
            if r:
                env, bs, be, end = r
                if env in LIST_ENVS:
                    _flush(buf, blocks); blocks.append(_make_list(env, src[bs:be]))
                elif env in TABLE_ENVS:
                    _flush(buf, blocks); blocks.append(_make_table(env, src, bs, be))
                elif env in BOX_ENVS:
                    _flush(buf, blocks)
                    body, width = (src[bs:be], None)
                    if env == "minipage":
                        body, width = _take_minipage_args(body)
                    blocks.append({"t": "box", "kind": env, "width": width,
                                   "blocks": parse_blocks(body)})
                elif env in RAW_ENVS:
                    _flush(buf, blocks)
                    blocks.append({"t": "raw", "env": env, "tex": src[i:end]})
                elif env in DISPLAY_MATH_ENVS or env in MATH_ONLY_ENVS:
                    _flush(buf, blocks)
                    blocks.append({"t": "math", "tex": src[i:end], "display": True})
                else:
                    # 没见过的环境：当透明容器递归，总比把 `\begin{xxx}` 漏到页面上好
                    _flush(buf, blocks)
                    blocks.extend(parse_blocks(src[bs:be]))
                i = end
                continue

        # ── 行内公式：整段吃进 buf ──
        # 不能让它里面的 `\begin{cases}` 走到上面的环境分支去当块环境。
        if src[i] == "$":
            r = scan_math(src, i)
            if r:
                buf.append(src[i:r[1]]); i = r[1]
                continue

        # ── 行间公式 ──
        if src.startswith("\\[", i) or src.startswith("$$", i):
            r = scan_math(src, i)
            if r:
                _flush(buf, blocks)
                tex = r[0].strip()
                # ⚠️ **行间公式里也可能有空位**（`\[\frac{1}{a_1}+…=\fillin{}.\]`）。
                # 整段交给 KaTeX 会把 `\fillin{}` 当未知命令报错，
                # 所以也要切开——和行内公式走同一条 `_emit_math`。
                nodes: list[dict] = []
                _emit_math(tex, True, nodes)
                if any(nd["t"] in ("blank", "paren") for nd in nodes):
                    # 用 `p` 而不是 `box`：渲染端的 `box` 收 `blocks`，
                    # `p` 才收 `in`。空位切出来的就是行内节点序列。
                    blocks.append({"t": "p", "in": nodes})
                else:
                    blocks.append({"t": "math", "tex": tex, "display": True})
                i = r[1]
                continue

        buf.append(src[i]); i += 1

    _flush(buf, blocks)
    return blocks


# ── 工具 ─────────────────────────────────────────────────

def blocks_to_text(blocks: list[dict]) -> str:
    """IR → 纯文本（搜索/摘要用）。"""
    out: list[str] = []

    def walk(bs: list[dict]) -> None:
        for b in bs:
            t = b["t"]
            if t == "p":
                out.append(inlines_to_text(b["in"]))
            elif t == "math":
                out.append(b["tex"])
            elif t == "list":
                for it in b["items"]:
                    walk(it)
            elif t == "table":
                for row in b["rows"]:
                    out.append(" ".join(inlines_to_text(c["in"]) for c in row))
            elif t == "box":
                walk(b["blocks"])
            elif t == "fig":
                pass
            elif t == "raw":
                out.append(b.get("env") or b.get("tex", ""))

    walk(blocks)
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def inlines_to_text(nodes: list[dict]) -> str:
    out = []
    for nd in nodes:
        t = nd["t"]
        if t == "s":
            out.append(nd["s"])
        elif t == "m":
            out.append(nd["s"])
        elif t == "raw":
            out.append(nd["s"])
        elif t == "blank":
            out.append("____")
        elif t == "paren":
            out.append("（  ）")
        elif t == "br":
            out.append(" ")
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def health(blocks: list[dict]) -> list[str]:
    """自检：IR 里不该再出现块级 LaTeX 语法。返回问题列表，空表示干净。"""
    bad: list[str] = []
    LEAK = re.compile(r"\\(?:begin|end)\{[a-zA-Z*]+\}|\\item(?![a-zA-Z])")

    def walk(bs: list[dict], path: str) -> None:
        for k, b in enumerate(bs):
            t = b["t"]
            if t == "p":
                for nd in b["in"]:
                    if nd["t"] in ("s", "raw") and LEAK.search(nd.get("s", "")):
                        bad.append("%s[%d].p %r" % (path, k, nd["s"][:60]))
            elif t == "list":
                for j, it in enumerate(b["items"]):
                    walk(it, "%s[%d].item%d" % (path, k, j))
            elif t == "table":
                for r, row in enumerate(b["rows"]):
                    for c, cell in enumerate(row):
                        for nd in cell["in"]:
                            if nd["t"] in ("s", "raw") and LEAK.search(nd.get("s", "")):
                                bad.append("%s[%d].r%dc%d %r" % (path, k, r, c, nd["s"][:60]))
            elif t == "box":
                walk(b["blocks"], "%s[%d].%s" % (path, k, b["kind"]))

    walk(blocks, "")
    return bad


# ── 自检 ─────────────────────────────────────────────────

def _selftest() -> int:
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("latex_blocks 自检")

    # 1. 嵌套列表（报障：内层拍平 + `\end{enumerate}` 漏出）
    src = (r"\begin{enumerate} \item $\log_{3}9=2$. \item \begin{enumerate} "
           r"\item $2n$； \item $(-1)^n$. \end{enumerate} \item $x^2+y^2=16$. \end{enumerate}")
    bs = parse_blocks(src)
    check("嵌套列表 → 1 个 list", len(bs) == 1 and bs[0]["t"] == "list", repr(bs)[:120])
    check("外层 3 项", len(bs[0]["items"]) == 3, str(len(bs[0]["items"])))
    check("内层嵌在第 2 项里",
          bs[0]["items"][1][0]["t"] == "list" and len(bs[0]["items"][1][0]["items"]) == 2,
          repr(bs[0]["items"][1])[:160])
    check("没有 LaTeX 语法残留", not health(bs), str(health(bs)))

    # 2. 表格（报障：列格式变第一行）+ 相邻两表
    src = (r"\begin{center}\begin{tabular}{|c|cc|}\hline 对数表\\ \hline "
           r"$N$ & 0 & 1\\ \hline 23 & 3617 & 3636\\ \hline\end{tabular}"
           r"\begin{tabular}{|c|cc|}\hline 反对数表\\ \hline .48 & 3020 & 3027\\ \hline\end{tabular}\end{center}")
    bs = parse_blocks(src)
    check("center 包两张表 → 1 个 box", len(bs) == 1 and bs[0]["t"] == "box", repr(bs)[:120])
    tabs = [b for b in bs[0]["blocks"] if b["t"] == "table"]
    check("两张表没被吞成一张", len(tabs) == 2, "实际 %d" % len(tabs))
    check("列格式没变成第一行",
          tabs and tabs[0]["rows"][0][0]["in"][0]["s"].strip() == "对数表",
          repr(tabs[0]["rows"][0])[:120] if tabs else "")
    check("表格 3 列", tabs and len(tabs[0]["rows"][1]) == 3,
          str(len(tabs[0]["rows"][1])) if tabs else "")

    # 3. minipage 宽度参数
    bs = parse_blocks(r"\begin{minipage}{0.9\linewidth}正弦对数表\end{minipage}")
    check("minipage 宽度被吃掉", bs[0]["t"] == "box" and bs[0]["width"] == r"0.9\linewidth"
          and inlines_to_text(bs[0]["blocks"][0]["in"]) == "正弦对数表", repr(bs)[:160])

    # 4. 数学模式里的 cases/matrix 不能被当块环境
    bs = parse_blocks(r"设 $f(x)=\begin{cases}x,&x>0\\-x,&x\le0\end{cases}$，则")
    check("$…$ 里的 cases 留在公式内",
          len(bs) == 1 and bs[0]["t"] == "p"
          and any(n["t"] == "m" and "cases" in n["s"] for n in bs[0]["in"]), repr(bs)[:160])
    bs = parse_blocks("\\[ \\begin{vmatrix}1&2\\\\3&4\\end{vmatrix}=1 \\]")
    check("\\[…\\] 里的 vmatrix 不被拆",
          len(bs) == 1 and bs[0]["t"] == "math" and "vmatrix" in bs[0]["tex"], repr(bs)[:120])

    # 5. 被 `$` 包住的图（旧项目在这里炸过 814 处）
    bs = parse_blocks(r"如图 $\includegraphics[width=0.4\linewidth]{abc123.png}$ 所示")
    figs = [b for b in bs if b["t"] == "fig"]
    check("$…$ 里的图仍认出", len(figs) == 1 and figs[0]["id"] == "abc123.png", repr(bs)[:160])
    check("图宽度 0.4\\linewidth → 40%", figs and figs[0]["width"] == "40%",
          figs[0]["width"] if figs else "")
    check("图被拆成独立块、文字留在段落里",
          [b["t"] for b in bs] == ["p", "fig", "p"], str([b["t"] for b in bs]))

    # 6. 落单的 `$` 不能吞掉正文
    bs = parse_blocks("价格是 $ 100 元，含税")
    check("落单 $ 不吞正文",
          inlines_to_text(bs[0]["in"]) == "价格是 $ 100 元，含税",
          repr(inlines_to_text(bs[0]["in"])))

    # 7. tikz 走 raw，不静默消失
    bs = parse_blocks(r"\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}")
    check("tikz → raw 块", len(bs) == 1 and bs[0]["t"] == "raw" and bs[0]["env"] == "tikzpicture",
          repr(bs)[:120])

    # 8. 没见过的宏要显形（不静默吞）
    bs = parse_blocks(r"设 \foo{甲} 为所求")
    check("未知宏标成 raw",
          any(n["t"] == "raw" and "foo" in n["s"] for n in bs[0]["in"]), repr(bs)[:160])

    # 9. 真实题目全文（1977 江苏连云港市初试卷#1 的解析）
    src = (r"\begin{enumerate}" "\n" r"\item 在 $a>0$ 时，得 $\log_{3}9=2$." "\n"
           r"\item" "\n" r"\begin{enumerate}" "\n" r"\item 首项为 $2$." "\n"
           r"\item 公比为 $-1$." "\n" r"\end{enumerate}" "\n"
           r"\item 圆的方程为 $x^2+y^2=r^2$." "\n" r"\end{enumerate}")
    bs = parse_blocks(src)
    check("真实解析：无语法残留", not health(bs), str(health(bs)))
    check("真实解析：3 项且第 2 项嵌 2 项",
          len(bs[0]["items"]) == 3 and len(bs[0]["items"][1][0]["items"]) == 2,
          repr(bs)[:200])

    # 11. `\fillin` 写在 `$…$` 里面（旧库原样如此，报障：显示成字面 `\fillin`）
    bs = parse_blocks(r"$\log_3 \frac{1}{27}=\fillin{}$.")
    nodes = bs[0]["in"]
    check("数学里的 \\fillin 变成空位",
          [n["t"] for n in nodes] == ["m", "blank", "s"], repr(nodes)[:160])
    check("空位前的公式保留",
          nodes[0]["t"] == "m" and "frac{1}{27}" in nodes[0]["s"], repr(nodes[0]))
    check("空位后没有多余公式", nodes[-1]["s"].strip() == ".", repr(nodes[-1]))

    bs = parse_blocks(r"当 $x=0$ 时，$f(0)=\fillin{}$；当 $x=-1$ 时，$f(-1)=\fillin{}$；")
    kinds = [n["t"] for n in bs[0]["in"]]
    check("一题多个数学内空位", kinds.count("blank") == 2, str(kinds))

    bs = parse_blocks(r"$\log_3 \frac{1}{27}=\fillin{}$.")
    check("断开的公式按行内渲染（不叠成多行）",
          all(not n.get("display") for n in bs[0]["in"] if n["t"] == "m"),
          repr(bs[0]["in"])[:120])

    # 11b. `\fillin[答案]` 的方括号答案要吞掉（2026 天津卷#12 报障）
    bs = parse_blocks(r"则 $\sin B=$\fillin[$\frac{3\sqrt{15}}{16}$].")
    kinds = [n["t"] for n in bs[0]["in"]]
    txt = inlines_to_text(bs[0]["in"])
    check("\fillin[答案] 不把答案画出来", "frac" not in txt and "[" not in txt, repr(txt))
    check("仍然产出空位", "blank" in kinds, str(kinds))
    bs = parse_blocks(r"则 $A\cap B=$\paren[B]")
    check(r"\paren[答案] 同理：只剩空括号",
          any(n["t"] == "paren" for n in bs[0]["in"])
          and "B" not in "".join(n.get("s", "") for n in bs[0]["in"]
                                 if n["t"] in ("s", "raw")),
          repr(bs[0]["in"]))

    # 11c. `\makebox[宽][对齐]{内容}` 与 `\rule[升降]{宽}{高}`（方括号参数）
    bs = parse_blocks(r"前\makebox[0.22\linewidth][c]{\includegraphics{a.png}}后")
    txt = inlines_to_text(bs[0]["in"])
    check("makebox 方括号参数被吃掉", "makebox" not in txt and "linewidth" not in txt, repr(txt))
    bs = parse_blocks(r"\rule[-18pt]{0pt}{43pt}文字")
    txt = inlines_to_text(bs[0]["in"])
    check("rule 方括号参数被吃掉", "rule" not in txt, repr(txt))

    # 12. 每个块类型都能 JSON 序列化
    import json
    try:
        json.dumps(bs, ensure_ascii=False)
        check("IR 可 JSON 序列化", True)
    except TypeError as e:
        check("IR 可 JSON 序列化", False, str(e))

    print("latex_blocks 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
