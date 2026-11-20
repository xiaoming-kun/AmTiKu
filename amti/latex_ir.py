"""AmTiKu · LaTeX → 结构化字段（唯一解析器）

**全项目只有这一个地方懂 LaTeX。** 网页渲染、PDF 导出、规范校验、搜索索引
全都消费它的输出，不得各自再写一套正则。

旧项目最大的技术债就是三套解析器（校验/导出/前端各一份），
`\\fig` 要在三处都改，修一处漏两处是结构性的必然。

## 真相的归属

主文件里每题有两块，**职责不重叠**：

    %% @q {...}          ← 只有 LaTeX 表达不了的：key / 来源 / 标签 / 分值
    \\begin{question}…    ← 题目本身：题干 / 选项 / 答案 / 解析   ← **真相**

所以**直接编辑 LaTeX 正文是有效的**（那才是真相），元数据行不用手改。
读完两边合并成 Question，再算指纹——手工改题干会被 `audit --diff` 抓到。
"""
from __future__ import annotations

import hashlib
import re

from .schema import Figure, Option, Question

# 题目环境
BODY_ENV_RE = re.compile(
    r"\\begin\{(?P<env>question|problem)\}(?:\[(?P<opt>[^\]]*)\])?"
    r"(?P<body>.*?)\\end\{(?P=env)\}", re.S)
CHOICES_RE = re.compile(r"\\begin\{choices\}(.*?)\\end\{choices\}", re.S)
SOLUTION_RE = re.compile(r"\\begin\{solution\}(.*?)\\end\{solution\}", re.S)
ITEM_RE = re.compile(r"\\item(\*?)\s*(.*?)(?=\\item|$)", re.S)
POINTS_RE = re.compile(r"points\s*=\s*([0-9.]+)")
ANSWER_CMD_RE = re.compile(r"\\textbf\{答案：\}([^\n]*)")
FILLIN_RE = re.compile(r"\\fillin(?![a-zA-Z])")
FIG_OPT_RE = re.compile(r"\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
# 答案的两种内联写法（exam-zh 标准，见 /tmp 里的高考模板）：
#   \paren[B]     选择/多选题——答案印在做答括号里
#   \fillin[$42$] 填空题——答案印在横线上
# ⚠️ 这两种写法**不能用 `\[([^\]]*)\]` 这种正则取参数**——
# `\fillin[$\sqrt[3]{\frac{3}{2}}$]` 里 `\sqrt[3]` 自带一个 `]`，
# 非贪婪到第一个 `]` 就收尾，答案会被截成 `$\sqrt[3`（实测踩过）。
# 区间 `[0,1]`、`\sqrt[3]`、`\left[\right]` 全会中招，必须做**配对扫描**。
PAREN_CMD_RE = re.compile(r"\\paren(?![a-zA-Z])")
FILLIN_CMD_RE = re.compile(r"\\fillin(?![a-zA-Z])")


# `\left` / `\right` 家族 + `\middle`。后面紧跟的那个字符是定界符，不参与配对。
_DELIM_CMD_RE = re.compile(
    r"\\(?:left|right|middle|bigl?|Bigl?|biggl?|Biggl?|bigr|Bigr|biggr|Biggr)"
    r"(?![a-zA-Z])")


def bracket_arg(s: str, i: int) -> tuple[str | None, int]:
    r"""`s[i] == '['` → `(内容, 右括号之后的下标)`。配对扫描，认嵌套。"""
    if i >= len(s) or s[i] != "[":
        return None, i
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            # `\left[` / `\right)` 这类**定界符命令**：整条吃掉，
            # 后面那个字符是「画出来的括号」，不是配对用的括号。
            # 少了这一条，`[$\left[ 700,4900 \right)$]` 会被判成配不平——
            # 而 `\left[…\right)` 是**完全合法的 LaTeX**（2026 北京卷#13 实测）。
            m = _DELIM_CMD_RE.match(s, j)
            if m:
                j = m.end()
                while j < n and s[j] in " \t":
                    j += 1
                if j < n and s[j] == "\\":
                    j += 2
                elif j < n:
                    j += 1
                continue
            j += 2
            continue
        if c == "{":
            k = j
            d = 0
            while k < n:
                if s[k] == "\\":
                    k += 2
                    continue
                if s[k] == "{":
                    d += 1
                elif s[k] == "}":
                    d -= 1
                    if d == 0:
                        break
                k += 1
            j = k + 1
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def _cmd_args(s: str, m: re.Match) -> tuple[list[str], int]:
    """取一个命令后面紧跟的 `{...}` / `[...]` 参数，返回 (参数列表, 新下标)。"""
    args, j, n = [], m.end(), len(s)
    while j < n and s[j] in " \t\n":
        j += 1
    while j < n and s[j] in "{[":
        if s[j] == "{":
            k, d = j, 0
            while k < n:
                if s[k] == "\\":
                    k += 2
                    continue
                if s[k] == "{":
                    d += 1
                elif s[k] == "}":
                    d -= 1
                    if d == 0:
                        break
                k += 1
            args.append(s[j + 1:k])
            j = k + 1
        else:
            val, j2 = bracket_arg(s, j)
            if val is None:
                break
            args.append(val)
            j = j2
        while j < n and s[j] in " \t\n":
            j += 1
    return args, j


def _wrap_bare_math(a: str) -> str:
    r"""答案在**数学模式内**的空位里时本来不带 `$`，但 `answer` 字段需要。

    `$a_{n} = egin{cases} 1, & n=1,\ illin[rac{n!}{2}], & n\geqslant 2.\end{cases}$`
    这种（空位切不出去，见 `latex_blocks._emit_math`）抽出来的答案是
    `rac{n!}{2}`——没有 `$`，前端会当**正文**画出来，显示成反斜杠。

    判据：**没有 `$` 且含反斜杠命令**才包。`0`、`2` 这种纯数字不用包。
    """
    a = (a or "").strip()
    if not a or "$" in a:
        return a
    # **已经是数学定界符的不要再包一层**：
    # `\[ … \]` / `\( … \)` 本身就是数学，包成 `$\[…\]$` 反而坏掉
    # （KaTeX 报 "Undefined control sequence: \["，实测 2009 上海卷（秋理）#4）。
    if a.startswith("\\[") or a.startswith("\\(") or a.startswith("$$"):
        return a
    return "$%s$" % a if "\\" in a else a


def paren_answers(stem: str) -> list[str]:
    r"""题干里所有 `\paren[答案]` 的答案（按出现顺序）。"""
    out = []
    for m in PAREN_CMD_RE.finditer(stem):
        args, _ = _cmd_args(stem, m)
        for a in args:
            if a.strip():
                out.append(a.strip())
    return out


def fillin_answers(stem: str) -> list[str]:
    r"""题干里所有 `\fillin[答案]` 的答案（按出现顺序）。"""
    out = []
    for m in FILLIN_CMD_RE.finditer(stem):
        args, _ = _cmd_args(stem, m)
        for a in args:
            if a.strip():
                out.append(a.strip())
    return out


# ── 搜索用的数学文本归一化（**有损，只服务于检索**） ─────────────
#
# 这不是第二套结构解析：`parse_question` 仍然是题目字段的唯一来源。
# 这里只把 LaTeX 压成“人会在搜索框里写”的扁平文本，供内容库建索引、
# 供 search 生成等价写法。两列：
#
#   严格：保留空格/`^`/`_`，用于精确优先
#   宽松：去空格、去 `^_`、去单 token 括号，用于容错召回
#
#   \cos B          -> cos b          / cosb
#   \frac{3}{4}     -> 3/4            / 3/4
#   \dfrac{\pi}{4}  -> pi/4           / pi/4   （宽松去括号）
#   \sqrt{3}        -> sqrt(3)        / sqrt3
#   x^{2}           -> x^2            / x2
#   \sin^2 A        -> sin^2 a        / sin2a
#   \triangle ABC   -> triangle abc   / triangleabc

_FRAC_CMD_RE = re.compile(r"\\(?:d|t)?frac(?![a-zA-Z])")
_SQRT_CMD_RE = re.compile(r"\\sqrt(?![a-zA-Z])")
_SLOT_CMD_RE = re.compile(r"\\(?:paren|fillin)(?![a-zA-Z])")
_KEEP_ARG_CMD_RE = re.compile(
    r"\\(?:text|mathrm|mathbf|mathit|mathbb|mathcal|mathsf|textbf|textit|"
    r"mbox|operatorname)(?![a-zA-Z])")
_DROP_ARG_CMD_RE = re.compile(
    r"\\(?:includegraphics|fig|label|ref|eqref|hspace|vspace)(?![a-zA-Z])")
_BEGIN_END_RE = re.compile(r"\\(?:begin|end)\s*\{[^{}]*\}")
_MATH_CMD_RE = re.compile(r"\\([a-zA-Z]+)\*?")

#: 命令名 → 搜索文本。函数名保留，公式才有意义；运算符统一成 ASCII。
_MATH_CMD = {
    "cdot": "*", "times": "*", "div": "/", "ast": "*",
    "le": "<=", "leq": "<=", "leqslant": "<=",
    "ge": ">=", "geq": ">=", "geqslant": ">=",
    "ne": "!=", "neq": "!=", "approx": "~=",
    "to": "->", "rightarrow": "->", "leftarrow": "<-",
    "Rightarrow": "=>", "Leftrightarrow": "<=>",
    "pm": "+-", "mp": "-+",
    "pi": "pi", "alpha": "alpha", "beta": "beta", "gamma": "gamma",
    "delta": "delta", "epsilon": "epsilon", "varepsilon": "epsilon",
    "theta": "theta", "lambda": "lambda", "mu": "mu", "nu": "nu",
    "xi": "xi", "rho": "rho", "sigma": "sigma", "tau": "tau",
    "phi": "phi", "varphi": "phi", "chi": "chi", "psi": "psi",
    "omega": "omega", "Gamma": "gamma", "Delta": "delta",
    "Theta": "theta", "Lambda": "lambda", "Pi": "pi", "Sigma": "sigma",
    "Phi": "phi", "Psi": "psi", "Omega": "omega",
    "sin": "sin", "cos": "cos", "tan": "tan", "cot": "cot",
    "sec": "sec", "csc": "csc", "arcsin": "arcsin", "arccos": "arccos",
    "arctan": "arctan", "log": "log", "ln": "ln", "lg": "lg",
    "lim": "lim", "sum": "sum", "prod": "prod", "int": "int",
    "triangle": "triangle", "angle": "angle", "parallel": "//",
    "perp": "perp", "circ": "deg", "degree": "deg",
    "infty": "inf", "inf": "inf",
}

#: 整条丢掉（排版命令/环境名/图片引用），不进入搜索文本。
_DROP_CMD = {
    "left", "right", "middle", "big", "Big", "bigg", "Bigg",
    "bigl", "Bigl", "biggl", "Biggl", "bigr", "Bigr", "biggr", "Biggr",
    "displaystyle", "textstyle", "scriptstyle", "limits", "nolimits",
    "quad", "qquad", "enspace", "thinspace", "medspace", "thickspace",
    "hfill", "vfill", "newline", "linebreak", "item", "caption",
    "centering", "begin", "end", "label", "ref", "eqref",
}

#: Unicode 数学符号 → ASCII（老师从 Word/网页粘过来的常见写法）。
_MATH_TRANS = str.maketrans({
    "×": "*", "·": "*", "÷": "/", "≤": "<=", "≥": ">=",
    "≠": "!=", "≈": "~=", "π": "pi", "△": "triangle",
    "∠": "angle", "°": "deg", "√": "sqrt", "±": "+-",
    "∞": "inf", "∈": "in", "∪": "union", "∩": "intersect",
    "→": "->", "⇒": "=>", "⇔": "<=>", "％": "%",
})


def _math_arg(s: str, i: int) -> tuple[str, int]:
    r"""读一个 `{…}` 或单字符参数（`\frac12` 这种也认）。"""
    n = len(s)
    while i < n and s[i] in " \t\n":
        i += 1
    if i >= n:
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < n:
            if s[j] == "\\":
                j += 2
                continue
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], n
    if s[i] == "\\" and i + 1 < n:
        return s[i:i + 2], i + 2
    return s[i], i + 1


def _expand_math_cmds(s: str) -> str:
    r"""先把 `\frac`/`\sqrt`/`\text`/`\paren` 这些**带参数**的命令摊平。

    只递归展开这一层；剩下不认识的反斜杠命令交给后面的正则映射。
    """
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        if s[i] != "\\":
            out.append(s[i])
            i += 1
            continue

        m = _FRAC_CMD_RE.match(s, i)
        if m:
            a, j = _math_arg(s, m.end())
            b, j2 = _math_arg(s, j)
            out.append("(%s)/(%s)" % (_expand_math_cmds(a),
                                      _expand_math_cmds(b)))
            i = j2
            continue

        m = _SQRT_CMD_RE.match(s, i)
        if m:
            j = m.end()
            k = j
            while k < n and s[k] in " \t":
                k += 1
            idx = ""
            if k < n and s[k] == "[":
                val, k2 = bracket_arg(s, k)
                if val is not None:
                    idx, j = val, k2
            a, j2 = _math_arg(s, j)
            if idx:
                out.append("root(%s,%s)" % (_expand_math_cmds(idx).strip(),
                                            _expand_math_cmds(a)))
            else:
                out.append("sqrt(%s)" % _expand_math_cmds(a))
            i = j2
            continue

        m = _SLOT_CMD_RE.match(s, i)
        if m:
            j = m.end()
            k = j
            while k < n and s[k] in " \t":
                k += 1
            if k < n and s[k] == "[":
                val, k2 = bracket_arg(s, k)
                if val is not None:
                    out.append(" " + _expand_math_cmds(val) + " ")
                    i = k2
                    continue
            i = j
            continue

        m = _KEEP_ARG_CMD_RE.match(s, i)
        if m:
            a, j = _math_arg(s, m.end())
            out.append(" " + _expand_math_cmds(a) + " ")
            i = j
            continue

        m = _DROP_ARG_CMD_RE.match(s, i)
        if m:
            j = m.end()
            while True:
                k = j
                while k < n and s[k] in " \t":
                    k += 1
                if k < n and s[k] == "{":
                    _, j = _math_arg(s, k)
                    continue
                if k < n and s[k] == "[":
                    _, k2 = bracket_arg(s, k)
                    if k2 > k:
                        j = k2
                        continue
                break
            i = j
            continue

        # 不认识的反斜杠命令：保留一个字符，后面的正则统一处理
        out.append(s[i])
        i += 1
    return "".join(out)


def math_text(s: str) -> tuple[str, str]:
    r"""LaTeX/纯文本 → `(严格, 宽松)` 两列搜索文本。

    严格保留空格与 `^_`，宽松去掉它们（并把 `sin(b)` 压成 `sinb`），
    这样 `cosB` / `cos B` / `\cos(B)` 能命中同一道题。中文和标点全部丢弃
    ——中文检索走全文索引，不在这列里。
    """
    s = s or ""
    if s.lstrip().startswith("%% @q"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
    s = s.replace("$$", " ").replace("$", " ")
    # 图形代码不是公式：整段丢掉，免得 `draw (1,2)` 混进检索
    s = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", " ", s, flags=re.S)
    s = re.sub(r"\\begin\{pgfpicture\}.*?\\end\{pgfpicture\}", " ", s, flags=re.S)
    # `cosB` / `sinA`：先拆成 `cos B`，否则后面会被当成一个单词
    s = re.sub(
        r"\b(sin|cos|tan|cot|sec|csc|arcsin|arccos|arctan|log|ln|lg|lim)"
        r"(?=[A-Za-z])", r"\1 ", s)
    s = _BEGIN_END_RE.sub(" ", s)
    s = _expand_math_cmds(s)
    # \left \right 家族、间距命令
    s = re.sub(
        r"\\(?:left|right|middle|bigl?|Bigl?|biggl?|Biggl?|"
        r"bigr|Bigr|biggr|Biggr)(?![a-zA-Z])", " ", s)
    s = re.sub(r"\\(?:quad|qquad|,|;|!|:| )", " ", s)
    # 保留参数的命令已经被摊平，这里只清掉残留的命令名
    s = _KEEP_ARG_CMD_RE.sub(" ", s)

    def _cmd(m: re.Match) -> str:
        name = m.group(1)
        if name in _MATH_CMD:
            return " " + _MATH_CMD[name] + " "
        if name in _DROP_CMD:
            return " "
        return " " + name + " "

    s = _MATH_CMD_RE.sub(_cmd, s)
    s = (s.replace("{", " ").replace("}", " ")
          .replace("&", " ").replace("\\\\", " "))
    s = s.replace("\\%", "%").replace("\\_", "_")
    s = s.translate(_MATH_TRANS)
    # 全角数字/字母 → 半角
    s = "".join(
        chr(ord(c) - 0xFEE0)
        if ("０" <= c <= "９" or "Ａ" <= c <= "Ｚ" or "ａ" <= c <= "ｚ")
        else c for c in s)
    # 只留数学字符；中文、标点、表格线全部丢掉
    s = re.sub(r"[^0-9A-Za-z+\-*/=<>^_().,!|~ ]+", " ", s)
    # 运算符两侧不留空格：`x^ 2`、`sin ^2 a`、`( pi )/(4)` 都收干净
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\s*([=<>+\-*/^_,!|])\s*", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < 2:
        return "", ""
    strict = s.lower()
    loose = re.sub(r"\s+", "", strict)
    loose = loose.replace("*", "")          # `2*x` 与 `2x` 视为同一写法
    loose = re.sub(r"[\^_]", "", loose)     # `x^2` 与 `x2`
    loose = re.sub(r"\(([a-z0-9.]+)\)", r"\1", loose)  # `sin(b)` → `sinb`
    return strict, loose
# 题干末尾的作答括号，可能是 `（\quad）`、`(\quad)`、`\paren`
TAIL_PAREN_RE = re.compile(r"[（(]\s*(?:\\quad|\\qquad)?\s*[）)]\s*$")
WIDTH_RE = re.compile(r"width\s*=\s*([^,\]]+)")
TIKZ_RE = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", re.S)

ENV_TYPE = {"question": "single_choice", "problem": "detailed_answer"}


def _clean(s: str) -> str:
    """去掉外围空白与缩进（不改内容）。"""
    s = (s or "").strip()
    s = re.sub(r"(?m)^[ \t]+", "", s)          # 去掉每行行首缩进
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def tikz_id(src: str) -> str:
    r"""TikZ 源码的稳定身份：`tikz-` + 源码 sha256 前 12 位。

    读（`parse_question`）和写（`migrate.to_question`）都走这里——
    改了源码就是换了 id，图的缓存文件名（`tikzfig._key`）另算，别混用。
    """
    return "tikz-" + hashlib.sha256((src or "").encode("utf-8")).hexdigest()[:12]


def derive_figures(*chunks: str) -> list[Figure]:
    r"""从正文片段推导配图。**正文是唯一真相。**

    旧库的 `figures_json` 实测不全——2024 新高考I卷#7 正文里有
    `\includegraphics`，`figures_json` 却是 `[]`。所以谁都不能拿它当真相。

    这个函数必须被 `parse_question`（读）和 `migrate.to_question`（写）
    **共用**。两处各写一遍的话，写入时算的指纹和读出时算的对不上，
    迁移工具会误报「内容变化」——实测踩过。
    """
    figures: list[Figure] = []
    seen: set[str] = set()
    for chunk in chunks:
        if not chunk:
            continue
        for opt, name in FIG_OPT_RE.findall(chunk):
            name = name.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            w = WIDTH_RE.search(opt or "")
            figures.append(Figure(id=name, kind="bitmap", source="inline",
                                  width=w.group(1).strip() if w else "0.4\\linewidth"))
    # TikZ 图没有文件，源码就在正文里，XeLaTeX 直接编译。
    # 给它一个由源码算出的稳定 id，好当身份用（去重、指纹）。
    for chunk in chunks:
        for src in TIKZ_RE.findall(chunk or ""):
            tid = tikz_id(src)
            if tid in seen:
                continue
            seen.add(tid)
            figures.append(Figure(id=tid, kind="tikz", tikz=src, source="tikz"))
    return figures


def preserve_figures(old: str, new: str) -> tuple[str, list[str]]:
    r"""把旧正文里、新正文丢掉的配图原样补到新正文末尾。

    单题"重写解析"时模型经常只复述文字、把 `\includegraphics` / TikZ 漏掉。
    正文是配图的唯一真相，漏掉就等于把图删了。这里做最后一道兜底：
    旧正文里有、新正文里没有的图，原文追加到末尾；返回补了哪些 id。
    调用方（AI 校对 / 重写 / 写回接口）都必须过这一道。
    """
    if not old or not new:
        return new, []
    old_figs = derive_figures(old)
    if not old_figs:
        return new, []
    new_ids = {f.id for f in derive_figures(new)}
    missing = [f for f in old_figs if f.id not in new_ids]
    if not missing:
        return new, []
    snippets: list[str] = []
    for f in missing:
        if f.kind == "tikz" and f.tikz:
            # Figure.tikz 存的就是完整的 begin/end 源码
            snippets.append(f.tikz.strip())
            continue
        raw = next((m.group(0) for m in FIG_OPT_RE.finditer(old)
                    if m.group(2).strip() == f.id), "")
        snippets.append(raw or r"\includegraphics[width=%s]{%s}" % (f.width, f.id))
    out = (new.rstrip() + "\n\n" + "\n\n".join(snippets)).strip()
    return out, [f.id for f in missing]


def parse_question(text: str) -> Question | None:
    r"""把一段「元数据 + LaTeX」解析成 Question。

    `text` 是主文件里的一个题块（不含 `%% @q` 行也行——那种情况 key 为空）。
    """
    m = BODY_ENV_RE.search(text)
    if not m:
        return None

    env = m.group("env")
    body = m.group("body")
    # ⚠️ 高考模板把 `\begin{solution}` 写在 `question`/`problem` **内部**，
    # 所以 body 会连解析一起抓到。先摘掉，不然题干里会混进整段解答。
    body = SOLUTION_RE.sub("", body, count=1)

    # ── 选项：从 `choices` 里抽，`\item*` 是正确项 ──
    options: list[Option] = []
    answer = ""
    cm = CHOICES_RE.search(body)
    if cm:
        stars: list[str] = []
        for i, (star, txt) in enumerate(ITEM_RE.findall(cm.group(1))):
            label = chr(ord("A") + i)
            options.append(Option(label, _clean(txt)))
            if star:
                stars.append(label)
        answer = "".join(stars)
        body = body[:cm.start()] + body[cm.end():]      # 选项从题干里摘掉

    stem = _clean(body)

    # ── 答案：`\paren[B]`（选择）与 `\fillin[$x$]`（填空）──────────────
    # 这是**高考模板的标准写法**：答案就写在做答括号／横线上，
    # 显示与否交给 `\examsetup{paren/show-answer, fillin/show-answer}` 控制。
    # 早先用 `\item*` 标正确项，卷面上不会有那个右对齐的「（ B ）」。
    if not answer:
        pa = paren_answers(stem)
        if pa:
            answer = pa[-1]
    fa = fillin_answers(stem)
    if fa and not answer:
        answer = "；".join(_wrap_bare_math(a) for a in fa)

    # ── 解析：`solution` 环境 ──
    solution = ""
    sm = SOLUTION_RE.search(text)
    if sm:
        sol = _clean(sm.group(1))
        am = ANSWER_CMD_RE.search(sol)
        if am and not answer:
            answer = am.group(1).strip()
            sol = (sol[:am.start()] + sol[am.end():]).strip()
        solution = sol

    # ── 题型：环境 → 选项 → 填空特征 ──
    #
    # 顺序很关键：**多选只能在"有选项"时判**。早先把「答案长度 > 1」放在
    # 选项判断之前，于是填空题的长答案（`$\left( x-y \right)…$`）被误判成
    # 多选题——实测 25 道填空题全中。往返测试抓到的就是这个。
    if env == "problem":
        qtype = "detailed_answer"
    elif options:
        qtype = "multi_choice" if len(answer) > 1 else "single_choice"
    elif FILLIN_RE.search(stem):
        qtype = "fill_in_blank"
    else:
        qtype = "detailed_answer"      # 没选项也没空的 question 环境，按解答题处理

    meta: dict = {}
    pm = POINTS_RE.search(m.group("opt") or "")
    if pm:
        meta["points"] = float(pm.group(1)) if "." in pm.group(1) else int(pm.group(1))

    # ── 配图：**从正文推导**，和题干/选项/答案一样，正文是唯一真相 ──
    #
    # 早先这里不填 figures，后果是连锁的：
    #   * 读回来的 Question 里 figures 永远是 []，而它在 HASH_FIELDS 里，
    #     等于「图换了，指纹不变」；
    #   * 整卷重写时把元数据里的图记录一并抹掉（figures 变 []）。
    # 宽度也以正文的 `[width=…]` 为准——元数据里的旧值可能和正文不一致。
    #
    # ⚠️ 必须显式带上 `options`：选项在**上面已经被从 `body` 里摘掉了**
    # （`body = body[:cm.start()] + body[cm.end():]`），所以只传 body 会漏掉
    # 选项里的图。2026 上海春卷#15 四个选项各是一张图，就是这样漏的。
    # 扫描范围要和 `schema.problems()` 的图片检查**一致**，否则两边打架。
    figures = derive_figures(body, solution, *(o.text for o in options))

    return Question(key="", type=qtype, stem=stem, options=options,
                    answer=answer, solution=solution, figures=figures, meta=meta)


def split_questions(master_text: str) -> list[str]:
    """把主文件切成一个个题块（每块从 `%% @q` 到下一块之前）。"""
    idx = [m.start() for m in re.finditer(r"^%% @q ", master_text, re.M)]
    if not idx:
        return []
    idx.append(len(master_text))
    return [master_text[idx[i]:idx[i + 1]].strip() for i in range(len(idx) - 1)]


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    """回归用例。每条都对应一次真实踩过的坑。"""
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("latex_ir 自检")

    # 历史坑 1：`\fillin[$\sqrt[3]{...}$]` 里的 `]` 让正则提前收尾，
    #            答案被截成 `$\sqrt[3`（2026 全国I卷#14 实际发生）
    t = r"\begin{question}最大值 $q$ 为 \fillin[$\sqrt[3]{\frac{3}{2}}$]．\end{question}"
    q = parse_question(t)
    check("答案里的 `]` 不被截断", q.answer == r"$\sqrt[3]{\frac{3}{2}}$", repr(q.answer))

    # 历史坑 2：答案本身带方括号（区间、根式）
    t2 = r"\begin{question}解集为 \paren[[0,1]]\end{question}"
    q2 = parse_question(t2)
    check("区间答案不被截断", q2.answer == "[0,1]", repr(q2.answer))
    # 括号不配对时**不能瞎猜**，宁可认不出来
    t2b = r"\begin{question}解集为 \paren[[0,1)]\end{question}"
    check("括号不配对时不硬拆", parse_question(t2b).answer == "",
          repr(parse_question(t2b).answer))

    # 历史坑 2b：`\left[` / `\right)` 是定界符命令，不参与方括号配对
    t2c = r"\begin{question}范围为 $f$ 的取值 \fillin[$\left[ 700,4900 \right)$]\end{question}"
    q2c = parse_question(t2c)
    check(r"`\left[…\right)` 能正确读出",
          q2c.answer == r"$\left[ 700,4900 \right)$", repr(q2c.answer))

    # 历史坑 3：solution 写在 question 内部时不能混进题干
    t3 = ("\\begin{question}题干\\begin{solution}解析\\end{solution}"
          "\\end{question}")
    q3 = parse_question(t3)
    check("内嵌 solution 不混进题干",
          "解析" not in q3.stem and q3.solution == "解析", repr(q3.stem))

    # 历史坑 4：多个填空位要各取各的答案
    t4 = (r"\begin{question}$x=$ \fillin[$1$] 且 $y=$ \fillin[$\sqrt[3]{8}$]"
          r"\end{question}")
    q4 = parse_question(t4)
    check("多空答案各归各位", q4.answer == r"$1$；$\sqrt[3]{8}$", repr(q4.answer))

    # 历史坑 5：选项里也有图（上海春卷#15 四个选项各一张图）
    t5 = (r"\begin{question}图形大致为（\quad）"
          r"\begin{choices}"
          r"\item $\includegraphics[width=0.15\paperwidth]{aaaa1111bbbb2222.png}$"
          r"\item $\includegraphics{cccc3333dddd4444.png}$"
          r"\end{choices}\end{question}")
    q5 = parse_question(t5)
    ids = sorted(f.id for f in q5.figures)
    check("选项里的图也要登记进 figures",
          ids == ["aaaa1111bbbb2222.png", "cccc3333dddd4444.png"], str(ids))

    # 搜索归一化：老师在搜索框里写 cosB / 3/4 / x2，要能落到同一串
    check("公式：cosB 归一", math_text(r"\cos B") == ("cos b", "cosb"),
          str(math_text(r"\cos B")))
    check("公式：分数", math_text(r"\frac{3}{4}") == ("(3)/(4)", "3/4"),
          str(math_text(r"\frac{3}{4}")))
    check("公式：根式", math_text(r"\sqrt{3}") == ("sqrt(3)", "sqrt3"),
          str(math_text(r"\sqrt{3}")))
    check("公式：上标", math_text(r"x^{2}") == ("x^2", "x2"),
          str(math_text(r"x^{2}")))
    check("公式：三角平方", math_text(r"\sin^2 A") == ("sin^2 a", "sin2a"),
          str(math_text(r"\sin^2 A")))
    check("公式：三角形",
          math_text(r"\triangle ABC") == ("triangle abc", "triangleabc"),
          str(math_text(r"\triangle ABC")))
    check("纯中文不进公式列", math_text("三角形形状判断") == ("", ""),
          str(math_text("三角形形状判断")))

    print("latex_ir 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys as _sys
    if "--selftest" in _sys.argv:
        raise SystemExit(_selftest())

    from .render_tex import question_to_tex

    q = Question(
        key="t/1", type="single_choice",
        stem=r"不等式 $\frac{x-4}{x-1}\geqslant 2$ 的解集是（\quad）",
        options=[Option("A", r"$\{x \mid -2\leqslant x\leqslant 1\}$"),
                 Option("B", r"$\{x \mid -2\leqslant x<1\}$")],
        answer="B",
        solution=r"原不等式等价于 $\frac{-x-2}{x-1}\geqslant 0$。",
        meta={"points": 5})

    tex = question_to_tex(q)
    back = parse_question(tex)
    print("渲染 → 解析 往返：")
    print("  题型   ", back.type, "==", q.type, "✓" if back.type == q.type else "✗")
    print("  题干   ", "✓" if back.stem == q.stem else "✗\n    前: %r\n    后: %r" % (q.stem, back.stem))
    print("  选项数 ", len(back.options), "==", len(q.options), "✓" if len(back.options) == len(q.options) else "✗")
    print("  答案   ", back.answer, "==", q.answer, "✓" if back.answer == q.answer else "✗")
    print("  解析   ", "✓" if back.solution == q.solution else "✗")
    print("  分值   ", back.meta.get("points"), "✓" if back.meta.get("points") == 5 else "✗")
    print()
    # 关键：直接改 LaTeX 正文，指纹要变
    h1 = parse_question(tex).content_hash()
    h2 = parse_question(tex.replace(r"\{x \mid -2\leqslant x<1\}", r"\{x \mid x<1\}")).content_hash()
    print("手改 LaTeX 正文后指纹变化：", "✓" if h1 != h2 else "✗", h1, "→", h2)
