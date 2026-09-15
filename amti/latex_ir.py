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
            tid = "tikz-" + hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]
            if tid in seen:
                continue
            seen.add(tid)
            figures.append(Figure(id=tid, kind="tikz", tikz=src, source="tikz"))
    return figures


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
