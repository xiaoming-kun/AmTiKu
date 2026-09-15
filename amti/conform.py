r"""AmTiKu · 规范化验证

回答一个问题：**库里的题目是不是都长成同一个样子？**

`schema.problems()` 管的是「字段自不自洽」（单选题有没有答案、填空题有没有空），
这里管的是「**写法是不是规范**」——同一件事有没有两种写法、有没有夹带私货。

九项检查，每一项都对应一个真实踩过的坑或刚定的规范：

    1. 环境配对        `\begin{X}` 必须有 `\end{X}`（旧项目配错跨层，389 处漏 `\end`）
    2. 定界符配对      `$…$`、`\[…\]`、`\(…\)` 都要成对（落单的 `$` 会吞掉半页正文）
    3. 数学里的中文    裸中文进数学模式，XeLaTeX 会用数学字体排，字形不对
    4. 私有宏          项目自己的宏（`\fig`/`\blank`…）不该出现在正文里
    5. 答案写法        选择用 `\paren[答案]`、填空用 `\fillin[答案]`（高考模板的写法）
    6. 填空位          填空题的 `\fillin` 个数要和答案段数对得上
    7. 图片引用        必须是内容寻址名，且文件真在 `图片/` 里
    8. 注释残留        主文件里的 `%` 注释应当已被清掉
    9. 列表选项        `\begin{enumerate}[label=…]` 这种要归一掉（旧项目在这里把 `\arabic*` 弄坏过）

用法：

    python3 -m amti.conform          # 全库检查，有问题返回码 1
"""
from __future__ import annotations

import re
import sys

from . import images as im
from . import knowledge as kb
from .schema import Question

from amti.logutil import get_logger

log = get_logger(__name__)

# ── 私有宏：**只有本项目自己发明过、现已废弃**的写法 ──────────────
#
# ⚠️ 别把 exam-zh / unicode-math 自带的宏列进来。实测踩过：
# `\symbfit`（向量粗斜体）、`\uppi`、`\iu`、`\eu`、`\mbox` 都是**合法宏**，
# 高考模板里就在用它们。`\symbfit` 一度被我误列为私有宏，报了 11 处假问题。
# 加进这个清单前，先实测一个最小文档能不能编译。
PRIVATE_MACROS = [r"\fig", r"\blank", r"\parenblank", r"\questionfig"]

_CMD = re.compile(r"\\([a-zA-Z]+)")
_BEGIN = re.compile(r"\\begin\{([a-zA-Z*]+)\}")
_END = re.compile(r"\\end\{([a-zA-Z*]+)\}")
_ENUM_OPT = re.compile(r"\\begin\{enumerate\}\s*\[[^\]]*\]")
_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
# 数学模式里的裸中文（排除 `\text{…}` 里的）
_MATH_SEG = re.compile(r"(?<!\$)\$(?!\$)([^$]*)\$(?!\$)|\\\[(.*?)\\\]|\\\((.*?)\\\)", re.S)
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _fields(q: Question) -> list[tuple[str, str]]:
    return [("stem", q.stem), ("answer", q.answer), ("solution", q.solution)] + \
           [("opt%s" % o.label, o.text) for o in q.options]


# ── 各项检查：返回 (定位, 说明) ──────────────────────────────────────

def chk_env(text: str):
    """环境配对。用栈而不是计数——嵌套同名环境时计数会错。"""
    stack: list[str] = []
    for m in re.finditer(r"\\(begin|end)\{([a-zA-Z*]+)\}", text):
        kind, env = m.group(1), m.group(2)
        if kind == "begin":
            stack.append(env)
        elif not stack:
            return "`\\end{%s}` 没有对应的 `\\begin`" % env
        elif stack[-1] != env:
            return "`\\begin{%s}` 与 `\\end{%s}` 没对上" % (stack[-1], env)
        else:
            stack.pop()
    return ("有 `\\begin{%s}` 没闭合" % stack[-1]) if stack else None


def chk_delim(text: str):
    r"""定界符配对（先剥**转义的** `\$`）。

    ⚠️ 只剥真正的转义 `\$`（字面美元符）。
    `\\$` 是「表格换行 `\\` + 公式开始 `$`」——用 `text.replace(r"\$", "")`
    会把后一个反斜杠连着 `$` 一起删掉，公式凭空少一个定界符，
    **合法的题被判成不配对**。
    实测：2008 江苏卷#7 的 `序号\\$(i)$`、2010 广东卷（理）#13 的
    `{$s_1=s_1+x_i$\\$s_2=…$}` 都中过这个假阳性。
    """
    t = re.sub(r"(?<!\\)\\\$", "", text)
    if t.count("$") % 2:
        return "`$` 个数是奇数（%d 个）" % t.count("$")
    # `\\[0.5ex]` 是 **cases/aligned 里的行距**（`\\` 换行 + `[..]` 间距），
    # 不是行间公式的 `\[`。少了 `(?<!\\)` 这个前置否定，合法 LaTeX 会被误判。
    # 实测：2025 北京卷#19 的 `\begin{cases}…\\[0.5ex]…` 就中过。
    if (len(re.findall(r"(?<!\\)\\\[", t))
            != len(re.findall(r"(?<!\\)\\\]", t))):
        return "`\\[` 与 `\\]` 不配对"
    if len(re.findall(r"\\\(", t)) != len(re.findall(r"\\\)", t)):
        return "`\\(` 与 `\\)` 不配对"
    return None


def chk_cjk_in_math(text: str):
    r"""数学模式里的裸中文。`\text{…}` 里的不算。

    `\text` 与 `{` 之间**允许空格**：`\text { 或 }` 也是合法 LaTeX。
    老写法只认 `\text{`，于是白名单内的中文被误报成裸中文
    （实测：2025 全国优质模拟题精选#35、2027千题册创新拔高册（下）#45）。
    """
    for m in _MATH_SEG.finditer(text):
        body = next((g for g in m.groups() if g is not None), "")
        stripped = body
        for cmd in ("text", "mathrm", "mbox", "textnormal", "operatorname"):
            stripped = re.sub(r"\\%s\s*\{[^{}]*\}" % cmd, "", stripped)
        if _CJK.search(stripped):
            hit = _CJK.search(stripped)
            return "数学模式里有裸中文：…%s…" % stripped[max(0, hit.start() - 8):hit.start() + 8]
    return None


def chk_private(text: str):
    for mac in PRIVATE_MACROS:
        if re.search(re.escape(mac) + r"(?![a-zA-Z])", text):
            return "出现私有宏 `%s`" % mac
    return None


def chk_answer_write(q: Question):
    r"""答案写法：选择用 `\paren[…]`、填空用 `\fillin[…]`（高考模板的写法）。"""
    if not q.answer.strip():
        return None
    if q.type in ("single_choice", "multi_choice"):
        if re.search(r"\\paren\s*\[", q.stem):
            return None
        return "选择题答案没写进 `\\paren[…]`"
    if q.type == "fill_in_blank":
        if re.search(r"\\fillin\s*\[", q.stem):
            return None
        return "填空题答案没写进 `\\fillin[…]`"
    return None


def chk_inline_delim(text: str):
    r"""**行内公式必须写 `$…$`，不许写 `\( … \)`。**

    规范 §2.4 定的是 `$…$`。`\( … \)` 语法上等价、LaTeX 也认，
    所以早先只是"放行"——结果库里混进了 51 道用 `\( \)` 的题，
    而有解析的题一共 13000 多道：**同一种东西两种写法**。

    「合法」不等于「统一」。这里按用户要求**从严**：出现 `\(` 或 `\)`
    就报，规范化器会把它们改成 `$…$`。

    注意别和这些搞混：
      · `\\[ … \\]`（行间公式）——规范就是这么定的，**不报**；
      · `\left( … \right)`、`\bigl(`——是"左括号命令"，不是定界符；
      · `(?<!\\)\\\\(` 这种——`\\` 是表格换行，后面跟 `(`，不算。
    """
    # `\(` 或 `\)`：反斜杠 + 圆括号，且前面不是反斜杠（排除 `\\(`）
    hits = re.findall(r"(?<!\\)\\[()]", text)
    if hits:
        return (r"行内公式要用 `$…$`，不要用 `\( … \)`（发现 %d 处）"
                % len(hits))
    return None


def chk_fillin_count(q: Question):
    """填空位个数 vs 答案段数。对不上说明答案和空位错位了。"""
    if q.type != "fill_in_blank":
        return None
    holes = len(re.findall(r"\\fillin(?![a-zA-Z])", q.stem))
    if holes == 0:
        return "填空题一个 `\\fillin` 都没有"
    parts = [p for p in re.split(r"[；;]", q.answer) if p.strip()]
    if parts and len(parts) != holes:
        return "空位 %d 个，答案 %d 段" % (holes, len(parts))
    return None


def chk_figures(q: Question, resolve=None):
    r"""图片引用检查。

    `resolve(name) -> bool` 决定「这张图算不算有」：

    * **全库校验**（默认）——必须在 `图片/` 里，因为库是自包含的
    * **录入干跑**——还没复制过去，得看**源目录能不能找到**（`ingest` 传进来）

    早先这里写死查 `图片/`，于是录入干跑把 8 张「还在源目录、尚未复制」
    的图报成违规。**检查要跟着阶段走**，不然复核永远过不了。
    """
    can = resolve or (lambda n: (im.IMG_DIR / n).is_file())
    refs = []
    for _f, v in _fields(q):
        refs += im.collect(v)
    for name in refs:
        if not can(name):
            return "图片 `%s` 找不到" % name
        # 两种内容寻址名都收：
        #   `0123456789abcdef.png`  位图，hash 取自**图片字节**（images.py 的老规矩）
        #   `tikz-0123456789abcdef.pdf`  TikZ 预渲染的矢量图，hash 取自**TikZ 源码**
        # 后者也是内容寻址——源码变了 hash 就变，不会张冠李戴；
        # 加 `tikz-` 前缀是为了跟位图一眼分开，也免得图片入库时被当成陌生文件。
        if not re.fullmatch(r"(tikz-)?[0-9a-f]{16}\.[a-z0-9]+", name):
            return "图片 `%s` 不是内容寻址名" % name
    return None


def chk_comment(text: str):
    m = _COMMENT.search(text)
    return ("残留注释：%s" % m.group(0)[:30]) if m else None


def chk_enum_opt(text: str):
    m = _ENUM_OPT.search(text)
    return ("`enumerate` 带选项：%s" % m.group(0)[:36]) if m else None



def _walk_block_text(b: dict):
    r"""遍历一个块（含嵌套格、嵌套块）里所有会当**文字**画出来的字符串。"""
    # ⚠️ **不要把数学块的 `tex` 算进来**——那是交给 KaTeX 的，本来就该是
    # LaTeX。第一版把 `{"t":"math","tex":"V=\\frac{1}{3}…"}` 也算成残留，
    # 一下虚报 1253 处，绝大多数是假阳性。**检查器自己也会骗人**，
    # 所以它也得先被验一遍——一个漏报的检查比没有检查更危险。
    if b.get("t") == "raw" and isinstance(b.get("s"), str):
        yield b["s"]
    for nd in (b.get("in") or []):
        if nd.get("t") in ("s", "raw"):
            yield nd.get("s", "")
    for row in (b.get("rows") or []):
        for c in row:
            if c.get("blocks"):
                for sub in c["blocks"]:
                    yield from _walk_block_text(sub)
            for nd in (c.get("in") or []):
                if nd.get("t") in ("s", "raw"):
                    yield nd.get("s", "")
    for it in (b.get("items") or []):
        for sub in it:
            yield from _walk_block_text(sub)
    for sub in (b.get("blocks") or []):
        yield from _walk_block_text(sub)


def chk_sentence_period(text: str):
    r"""**中文行文里句末要用「。」，不用「.」。**

    依据见 `设计/高考模板.tex`：注意事项那种纯中文句子一律「。」，
    解答也是（`由 $f(x)=f(-x)$，得 $a=1$。`——**句末是数学照样用「。」**）。

    三处不算错，**不报**：
      · 数学模式里的 `.`（`$…$`、`\[…\]` 内）——那是公式的一部分
      · 小数点（`3.14`）——靠前置断言排除
      · 省略号（`…`、`...`）——中间的点后面不跟空白，自然不匹配
    """
    from .normalize import _math_mask, _SENT_DOT
    if "." not in (text or ""):
        return None
    mask = _math_mask(text)
    hits = [m.start() for m in _SENT_DOT.finditer(text) if not mask[m.start()]]
    if hits:
        i = hits[0]
        return ("中文行文句末要用「。」，这里用了「.」（发现 %d 处，如 `%s.`）"
                % (len(hits), text[max(0, i - 12):i]))
    return None


def chk_blank_leftover(q: Question):
    r"""**题干里不该同时有作答括号和空括号。**

    规范 §2.2：一道题的作答位置只有一个。

    踩过的坑：题干写成 `…的值是（$\quad$）`，规范化在尾巴上补了 `\paren[A]`，
    但**原来那个空括号没删**——卷面上就印出两个括号。350 道中招。

    （`（\quad）`、`（$\quad$）`、`（ ）` 三种写法都算空括号。）
    """
    s = q.stem or ""
    if not re.search(r"\\(paren|fillin)\s*(\[[^\]]*\])?", s):
        return None
    # 把作答命令本身挖掉，再看还有没有空括号
    rest = re.sub(r"\\(paren|fillin)\s*(\[[^\]]*\])?", "", s)
    m = re.search(r"[（(]\s*\$?\s*(?:\\quad|\\qquad)?\s*\$?\s*[）)]", rest)
    if m:
        return "题干里既有作答括号又留着空括号 `%s`，卷面上会印出两个" % m.group(0)
    return None


def chk_blank_not_in_math(q: Question):
    r"""空位不能在数学模式**里面**。

    `$\theta=\fillin[答案]$` 是坏掉的 LaTeX——旧库把空位写在 `$…$` 内，
    答案填进去后若自带 `$`，就变成嵌套美元符。卷面上会把答案画出来：

        θ = ____ [\frac{3\pi}{2}]

    ⚠️ `chk_delim` **查不出来**：嵌套后 `$` 是 4 个，偶数，配对"通过"了。

    判定要按**整段公式**看，不能只看命令之前那截：
    `$f(\theta)=\fillin[\frac{1}{\sin\left(\frac{\pi}{6}-\theta\right)}]$`
    里的 `\left` 在**答案参数内部**，只看前半截会漏判，把它当成违规
    （实测 2012 上海卷（秋理）#10、2026 上海卷（秋）#9）。

    放行条件：整段公式里有 `\begin{…}` 或 `\left…\right`——
    那种情形**切不开**（切了 `\begin{cases}` 和 `\end{cases}` 会分家），
    `normalize` 会把答案自带的 `$` 脱掉，是合法形态。
    """
    from . import normalize as _norm
    cmd = re.compile(r"\\(fillin|paren)(?![a-zA-Z])")
    for f, t in _fields(q):
        if not t:
            continue
        # 先按「命令参数整条吞掉」切成 token，再找成对的 `$`
        toks = _norm._tokenize(t)
        k, n = 0, len(toks)
        while k < n:
            if toks[k][0] != "$":
                k += 1
                continue
            j = k + 1
            while j < n and toks[j][0] != "$":
                j += 1
            if j >= n:
                break
            inner = toks[k + 1:j]
            body = "".join(x[1] for x in inner)
            has_cmd = any(x[0] == "c" and cmd.match(x[1]) for x in inner)
            if has_cmd and not any(x in body for x in
                                   ("\\begin{", "\\left", "\\right")):
                return "[%s] 空位在数学模式里（会产生嵌套 `$`）" % f
            k = j + 1
    return None


def chk_solution_not_json(q: Question):
    r"""解析不能是 JSON。

    旧库有 16 道题的 `solution` 字段存的是 `options_json` 的内容
    （`[{"label": "A", "text": "2"}, …]`）或一个空数组 `[]`——
    导出到卷面上就是一大串花括号，等于没有解析。
    实测踩过：手工录入的 7 + 9 道。

    判据：能 `json.loads` 成 list/dict 的，一定不是解析。
    """
    import json as _json
    for f, t in _fields(q):
        if f != "solution":
            continue
        t = (t or "").strip()
        if not t:
            continue
        try:
            d = _json.loads(t)
        except ValueError:
            continue
        if isinstance(d, (list, dict)):
            return "解析是 JSON（%s…），不是解析正文" % t[:40]
    return None


def chk_render_leak(q: Question):
    r"""渲染后文本节点里**不该残留任何 LaTeX 命令**。

    `render.tsx` 只认 IR，落进 `{"t":"s"}` 的文字会**原样显示**。
    所以文本节点里出现 `\frac`、`\item` 这类，卷面上就是反斜杠加字母。

    这一条覆盖面最广——`\fillin` 少吞参数、列表没识别、环境没配对……
    各种解析漏洞最后都会表现为"文字里剩了命令"。**用渲染结果反查解析**，
    比逐条猜哪里会漏要靠得住。实测抓到过 `\frac`/`\symbfit`/`\makebox` 等 138 处。
    """
    from . import latex_blocks as lb
    leak = re.compile(r"\\[a-zA-Z]+")
    for f, t in _fields(q):
        if not t:
            continue
        try:
            blocks = lb.parse_blocks(t)
        except Exception:
            log.warning("块解析失败，跳过该字段", exc_info=True)
            continue
        for b in blocks:
            # ⚠️ **块自己的 `s` 也要查**。只查 `in` 会漏掉整块没被识别的情况
            # （`{"t":"raw","s":"\\begin{tabular}"}` 就是这么漏过去的，
            # 前端 check.mjs 抓到了、conform 却没抓到）。
            for text_ in _walk_block_text(b):
                m = leak.search(text_)
                if m:
                    return "[%s] 渲染后残留 `%s`（会显示成反斜杠）" % (f, m.group(0))
    return None


CHECKS = [
    ("环境配对", chk_env, "text"),
    ("定界符配对", chk_delim, "text"),
    ("行内公式定界符", chk_inline_delim, "text"),
    ("句末标点", chk_sentence_period, "text"),
    ("数学里的中文", chk_cjk_in_math, "text"),
    ("私有宏", chk_private, "text"),
    ("注释残留", chk_comment, "text"),
    ("列表选项", chk_enum_opt, "text"),
    ("答案写法", chk_answer_write, "q"),
    ("填空位数", chk_fillin_count, "q"),
    ("图片引用", chk_figures, "q", True),      # 需要 image_resolver
    ("空括号残留", chk_blank_leftover, "q"),
    ("空位位置", chk_blank_not_in_math, "q"),
    ("渲染残留", chk_render_leak, "q"),
    ("解析非JSON", chk_solution_not_json, "q"),
]


def run(questions=None, *, image_resolver=None) -> list[dict]:
    """跑全部检查。返回问题列表（空 = 全部规范）。

    `image_resolver(name) -> bool` 只在录入干跑时传——
    那时候图还在源目录，没复制进 `图片/`。
    """
    from . import store
    qs = questions if questions is not None else store.load_all()
    bad: list[dict] = []
    for q in qs:
        for name, fn, kind, *extra in CHECKS:
            if kind == "q":
                why = fn(q, image_resolver) if extra else fn(q)
                if why:
                    bad.append({"key": q.key, "check": name, "field": "", "why": why})
                continue
            for field, text in _fields(q):
                why = fn(text)
                if why:
                    bad.append({"key": q.key, "check": name,
                                "field": field, "why": why})
    return bad


def main() -> int:
    from collections import Counter
    from . import store

    qs = store.load_all()
    print("规范化验证：%d 道题，%d 项检查\n" % (len(qs), len(CHECKS)))
    bad = run(qs)

    by_check = Counter(b["check"] for b in bad)
    for name, _fn, _k, *_x in CHECKS:
        n = by_check.get(name, 0)
        print("  %-12s %s" % (name, "✓" if not n else "✗ %d 处" % n))

    if bad:
        print("\n明细（前 20 条）：")
        for b in bad[:20]:
            print("  %s [%s%s] %s" % (b["key"], b["check"],
                                      "/" + b["field"] if b["field"] else "",
                                      b["why"][:70]))
        print("\n共 %d 处不规范" % len(bad))
        return 1
    print("\n✓ 全部规范")
    return 0


# ── 自检：**先证明检查器管用，再说"全部规范"** ────────────────────
#
# 「✓ 全部规范」本身不是证据——它只说明"没报"，不说明"检查器管用"。
# 实测踩过两次：一次误报 1253 处（把数学块的 tex 当成残留），
# 一次漏报（只看行内节点，不看块自己的 `s`）。
# 所以每一项检查都要有一个**必须被抓到的坏样本**和一个**必须放过的干净样本**。

def _q(stem="", answer="", solution="", qtype="fill_in_blank", options=None):
    from .schema import Option
    return Question(key="自检/1", type=qtype, stem=stem, answer=answer,
                    solution=solution, options=options or [])


# (检查名, 坏样本, 干净样本)。**类型要和检查函数对得上**——
# 文本类检查收字符串，题目类检查收 Question。
def _qs(text):
    """文本类检查的样本：**直接给字符串**。"""
    return text


def _qpt(text, **kw):
    """题目类检查的样本。`kw` 直接透传给 `_q`（如 solution=…）。"""
    return _q(text, **kw)


_CONTROLS: list[tuple[str, object, object]] = [
    ("环境配对", _qs(r"\begin{question} 少了结尾"),
     _qs(r"\begin{question} 正常 \end{question}")),
    ("定界符配对", _qs("$x$ 与 $y"), _qs("$x$ 与 $y$")),
    # 行内公式定界符：规范是 `$…$`，`\( \)` 要报（用户要求从严）。
    # 注意坏样本要用**转义写法**拼，别直接写进源码——`"\(` 在 Python 里
    # 是非法转义，会出 SyntaxWarning（踩过）。
    ("行内公式定界符", _qs("\\(" + "x=1" + "\\)"),
     _qs("$x=1$")),
    # 句末标点：坏样本是"中文句子用了半角句点"（真实踩过 8 万处）
    ("句末标点", _qs("所以 $x=1$" + chr(46)),
     _qs("所以 $x=1$。")),
    ("数学里的中文", _qs("$x_中$"), _qs(r"$x$ 中文在外面")),
    ("私有宏", _qs(r"\fig{a.png}"), _qs(r"\includegraphics{a.png}")),
    ("注释残留", _qs("题干 % 这是注释"), _qs("题干没有注释")),
    ("列表选项", _qs(r"\begin{enumerate}[label=x] \item a \end{enumerate}"),
     _qs(r"\begin{enumerate} \item a \end{enumerate}")),
    ("答案写法", _qpt(r"$A\cap B=$（\quad）"), _qpt(r"$A\cap B=$\paren[B]")),
    # 坏样本：**两个空位、答案只有一段**（真实踩过：2025 北京卷#12 漏了一个空位）
    ("填空位数",
     _qpt(r"$x=$ \fillin{} 且 $y=$ \fillin{}"),
     _qpt(r"$x=$ \fillin{}")),
    # 空括号残留：坏样本是"作答括号 + 空括号"并存（真实踩过 350 道）
    ("空括号残留",
     _qpt(r"则 $x$ 的值为（$\quad$） \paren[A]"),
     _qpt(r"则 $x$ 的值为\paren[A]")),
    ("空位位置", _qpt(r"$\theta=\fillin[$\frac{3\pi}{2}$]$"),
     _qpt(r"$\theta=$\fillin[$\frac{3\pi}{2}$]")),
    ("解析非JSON", _qpt("", solution='[{"label":"A","text":"2"}]'),
     _qpt("", solution="由基本不等式得 $\\frac1a+\\frac1b\\ge 4$．")),

    # 坏样本用一个**解析器不认识的命令**——它一定会以原文显形。
    # （别拿 `\resizebox` 当坏样本：那个已经修好了，不再是坏样本）
    ("渲染残留", _qpt(r"前 \weirdcmd{后}"),
     _qpt("纯文字，没有命令")),
]


def _selftest() -> int:
    print("conform 自检（**先证明检查器管用**）")
    fails = 0
    by_name = {n: (f, k) for n, f, k, *_ in CHECKS}

    # 文本类样本是字符串，题目类样本是 Question，**各自直接传**。
    # 早先按 kind 去取 `.stem`，结果题目类检查收到字符串就崩了。
    def call(fn, kind, sample):
        return fn(sample)

    for name, bad, good in _CONTROLS:
        hit = by_name.get(name)
        if hit is None:
            print("  ✗ %-12s 检查项不存在" % name)
            fails += 1
            continue
        fn, kind = hit
        # 这几项要看 answer 字段，按检查项各给各的
        if name == "答案写法":
            bad.answer, bad.type = "B", "single_choice"
            good.answer, good.type = "B", "single_choice"
        if name == "填空位数":
            bad.answer = "$1$"          # 两空一段 → 该报
            good.answer = "$1$"         # 一空一段 → 不该报
        got_bad = call(fn, kind, bad)
        got_good = call(fn, kind, good)
        ok = bool(got_bad) and not got_good
        print("  %s %-12s 坏样本%s  干净样本%s" % (
            "✓" if ok else "✗", name,
            "抓到" if got_bad else "**漏了**",
            "放过" if not got_good else "**误报**"))
        if not ok:
            fails += 1
    print("conform 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys as _s
    if "--selftest" in _s.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
