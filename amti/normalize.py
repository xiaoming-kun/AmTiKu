r"""AmTiKu · 规范化器

**全库唯一把题目改成规范形态的地方。** 规范定义在 `设计/题目规范.md`。

    normalize(q) -> ["改了哪些项", ...]

调用点只有两个：

    录入时  `ingest` 调它（ENTRY 级，只碰新题）
    整库时  `python3 amti.py normalize --apply`（MIGRATE 级，需 --yes）

## 为什么合成一个模块

原先规则散在 `render_tex`（渲染时顺手修）、`rules.py`（四条 ENTRY 规则）、
外加一堆一次性脚本里。结果就是**同一个格式问题在不同地方各修一遍**，
修了 A 漏了 B——`\fillin[$\left[ 700,4900 \right)$]` 编译失败就是这么漏出来的：
规则只管"答案进不进括号"，不管"进了括号能不能编译"。

现在只有这一份，每条对应 `设计/题目规范.md` 的一节。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .schema import Option, Question

ENTRY = "ENTRY"
MIGRATE = "MIGRATE"

# ── 词法工具（按 **TeX 真实规则**） ──────────────────────────────────

_DELIM_CMD_RE = re.compile(
    r"\\(?:left|right|middle|bigl?|Bigl?|biggl?|Biggl?|bigr|Bigr|biggr|Biggr)"
    r"(?![a-zA-Z])")


def scan_bracket(s: str, i: int) -> tuple[str, int, bool]:
    r"""`s[i] == '['` → `(内容, 右括号之后的下标, 是否配平)`。

    ⚠️ **TeX 的可选参数扫描器只数 `[` 和 `]`，`{…}` 内部不计，
    别的什么都不认**——它不认识 `\left[`。
    实测：

        \fillin[$\sqrt[3]{\frac{3}{2}}$]      ✓  `[3]` 自带配对，数得平
        \fillin[$\left[ 700,4900 \right)$]    ✗  `\left[` 的 `[` 没人配，扫到文件末尾

    所以这里也**不能**对 `\left`/`\right` 特殊处理，否则会漏判。
    """
    d, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            k, dd = j, 0
            while k < n:
                if s[k] == "\\":
                    k += 2
                    continue
                if s[k] == "{":
                    dd += 1
                elif s[k] == "}":
                    dd -= 1
                    if dd == 0:
                        break
                k += 1
            j = k + 1
            continue
        if c == "[":
            d += 1
        elif c == "]":
            d -= 1
            if d == 0:
                return s[i + 1:j], j + 1, True
        j += 1
    return s[i + 1:], n, False


def needs_brace_protect(arg: str) -> bool:
    r"""参数能不能直接放在 `[…]` 里？

    含**未配平**的 `[` 就不行——TeX 会一路扫到文件末尾。
    已配平的（如 `\sqrt[3]{…}`）可以直接写。
    """
    if arg.lstrip().startswith("{"):
        return False                     # 已经保护过了
    d = 0
    i, n = 0, len(arg)
    while i < n:
        c = arg[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            k, dd = i, 0
            while k < n:
                if arg[k] == "{":
                    dd += 1
                elif arg[k] == "}":
                    dd -= 1
                    if dd == 0:
                        break
                k += 1
            i = k + 1
            continue
        if c == "[":
            d += 1
        elif c == "]":
            d -= 1
            if d < 0:
                return True
        i += 1
    return d != 0


def protect(arg: str) -> str:
    """给需要保护的参数套一层 `{}`。"""
    return "{%s}" % arg if needs_brace_protect(arg) else arg


def arg_window(text: str, start: int, cmd: re.Pattern) -> int:
    r"""可选参数最多能延伸到哪里。

    防止「配不平时退到最后一个 `]`」退过头，把后面那道题的括号也吞进来。
    边界取三者最近的一个：下一个同类命令、`\begin{` / `\end{`、空行。
    """
    stop = len(text)
    for pat in (cmd, re.compile(r"\\begin\{"), re.compile(r"\\end\{"),
                re.compile(r"\n\s*\n")):
        m = pat.search(text, start)
        if m:
            stop = min(stop, m.start())
    return stop


def put_cmd_arg(text: str, cmd: re.Pattern) -> str:
    r"""把需要的 `\<cmd>[参数]` 换成 `\<cmd>[{参数}]`。

    配得平的参数不用动；配不平的（`\left[` 那种）退到**本段最后一个 `]`**
    作为参数结尾——那才是作者想要的参数。
    """
    out, pos = [], 0
    for m in cmd.finditer(text):
        i = text.find("[", m.end())
        if i < 0 or i > m.end() + 4:
            continue
        arg, end, ok = scan_bracket(text, i)
        if not ok:
            stop = arg_window(text, i, cmd)
            last = text.rfind("]", i, stop)
            if last < 0:
                continue
            arg, end = text[i + 1:last], last + 1
            if not needs_brace_protect(arg):
                continue
        elif not needs_brace_protect(arg):
            continue
        out.append(text[pos:i])
        out.append("[" + "{%s}" % arg + "]")
        pos = end
    out.append(text[pos:])
    return "".join(out)


# ── 规范条目：每条对应 设计/题目规范.md 的一节 ──────────────────────

@dataclass
class Rule:
    name: str
    scope: str
    fn: Callable[[Question], bool]
    why: str = ""


RULES: list[Rule] = []
_BY: dict[str, Rule] = {}


def rule(*, name: str, scope: str, why: str):
    def deco(fn):
        r = Rule(name=name, scope=scope, fn=fn, why=why)
        RULES.append(r)
        _BY[name] = r
        return fn
    return deco


_CHOICE = ("single_choice", "multi_choice")
# 空作答括号的几种写法。**`$` 包着 `\quad` 的那种最容易漏**：
# `（$\quad$）` 看上去跟 `（\quad）` 差不多，但早先的正则只认后者——
# 结果规范化没认出它是作答位置，又在尾巴上追了一个 `\paren[D]`，
# 卷面上就印出**两个括号**。实测 350 道中招。
_ANY_PAREN = re.compile(r"[（(]\s*\$?\s*(?:\\quad|\\qquad)?\s*\$?\s*[）)]")
_TAIL_PAREN = re.compile(r"[（(]\s*(?:\\quad|\\qquad)?\s*[）)]\s*$")
_PAREN_FILLED = re.compile(r"\\paren\s*\[")
_BARE_PAREN_TAIL = re.compile(r"\\paren\s*$")
_BLANK_FILLIN = re.compile(r"\\fillin(?![a-zA-Z])\s*(?:\{\})?")
_FILLIN_FILLED = re.compile(r"\\fillin\s*\[")
from .schema import OPTION_LABELS   # noqa: E402

_FILLIN_CMD = re.compile(r"\\fillin(?![a-zA-Z])")
_PAREN_CMD = re.compile(r"\\paren(?![a-zA-Z])")
_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
_ENUM_OPT = re.compile(r"(\\begin\{enumerate\})\s*\[[^\]]*\]")


def split_answers(answer: str, holes: int) -> list[str]:
    """把答案串拆成 `holes` 段。分隔符三种写法都认，拆不出正确段数就返回空。"""
    for sep in ("；", ";", "，"):
        parts = [p.strip() for p in answer.split(sep) if p.strip()]
        if len(parts) == holes:
            return parts
    return []


_MULTI_HEAD = re.compile(r"^[）)（(、，,。.．\s]{0,4}(?:多选|多项选择|多选题)")


@rule(name="去题首杂标点", scope=MIGRATE,
      why="规范 §2.3：PDF 抽取把「（\\quad）」的后半个括号留在了题首，"
          "卷面上会印出一个孤零零的「）」。题干**不可能**以右括号开头")
def strip_lead_junk(q: Question) -> bool:
    r"""去掉题干开头的孤立右括号/右引号等杂标点。

    只认「右半边」的符号——左括号开头的题干是正常的（如「（1）求…」），
    右括号开头的不是。
    """
    new = _LEAD_JUNK.sub("", q.stem)
    if new == q.stem or not new.strip():
        return False
    q.stem = new
    return True


_LEAD_JUNK = re.compile(r"^[\s）)】\]》」』]+")


@rule(name="题干写「多选」的改判多选", scope=MIGRATE,
      why="规范 §2.1：题型以题干自述为准——模拟题在题首写「（多选）」，"
          "解析器却一律当单选，结果 347 道多选题被摆在单选区、"
          "答案也被 `clean_answer` 当成非法拒收")
def fix_multi_choice_type(q: Question) -> bool:
    r"""题干开头写着「（多选）」的单选题 → 改判为多选题。

    **为什么以题干为准**：高考卷的「多选」写在卷首说明里，题干不重复，
    所以高考题靠解析器判（已正确）；模拟题是一道一道独立的，出题人
    只能把「（多选）」写在题首，解析器没有依据，于是全判成了单选。

    只认**题首**的多选标记，且必须有 A/B/C/D 四个选项——正文里
    顺口提到「多项选择题」的（比如讲多选题评分规则的那类）不动。
    """
    if q.type != "single_choice":
        return False
    head = q.stem.lstrip()[:8]
    if not _MULTI_HEAD.search(head):
        return False
    if len(q.options) != 4:
        return False
    if [o.label for o in q.options] != list(OPTION_LABELS[:4]):
        return False
    q.type = "multi_choice"
    return True


# ── 题干末尾的出处 ────────────────────────────────────────────────────
#
# 千题册那几本书在 OCR 时把「出处」留在了题干末尾：
#
#     则使得 $\sin a_1\cdots\sin a_k<\frac{1}{10}$ 成立的最小正整数 $k$ 为 \fillin{}。
#
#     2025 四川遂宁中学二模            ← 这是出处，不是题目
#
# 留在题干里的后果很直接：**卷面上会把出处当题目印出来**。
_SRC_YEAR = re.compile(r"(?:19|20)\d{2}")
# 「命题」**不能**算关键词——「其中的真命题是（ ）」是题目正文，实测误伤 7 道
_SRC_KW = re.compile(r"模|卷|联考|统考|质检|调研|期中|期末|月考|真题|汇编"
                     r"|中学|附中|高中|学校|考试|模拟|协作体|联盟|百校")
# 题目正文里的常见词。命中就不当出处——宁可漏判，不可错删题干
_SRC_BODY = re.compile(r"命题|则|其中|下列|以上|正确|错误|个数|说法|结论|序号"
                       r"|值为|等于|求证|证明|解答|范围|最小值|最大值")


def looks_like_source(line: str) -> bool:
    r"""这一行像不像「出处」而不是题干正文。

    **宁可漏判，不可错删**：删错一行题干是数据事故，漏判一条只是卷面
    上多印一行字，还能补。所以判据都往保守里定。
    """
    line = line.strip()
    if not line or len(line) > 42:
        return False
    if "$" in line or "\\" in line:          # 含公式 → 是正文
        return False
    if re.search(r"[。！？?]", line):          # 有句末标点 → 是正文
        return False
    if _SRC_BODY.search(line):                 # 正文常用词
        return False
    return bool(_SRC_YEAR.search(line) or _SRC_KW.search(line))


@rule(name="题干末尾的出处移入 meta", scope=MIGRATE,
      why="规范 §2.6：出处是元数据、不是题干正文——留在题干里会被当题目印到卷面上")
def strip_trailing_source(q: Question) -> bool:
    r"""把题干**末尾**那行出处移到 `meta.source_label`。

    只动**最后一行**，而且只在它像出处时才动。年份也顺手提出来写进
    `meta.year`（原来那里放的是"书的年份"，比如千题册一律 2027；
    但一道 2021 新高考 I 卷的题，按 2021 找才对）。
    """
    lines = (q.stem or "").split("\n")
    idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip():
            idx = i
            break
    if idx is None or not looks_like_source(lines[idx]):
        return False

    # ⚠️ **删完不能变空**。有一道题的题干**整个**就是「太原二模」——
    # 说明它的正文在导入时就丢了。这时候把最后一行当出处删掉，
    # 剩下的就是空白，题目彻底没了。宁可留着这行，让人看得出来"这题不对"。
    rest = "\n".join(lines[:idx]).rstrip()
    if not rest.strip():
        return False

    label = lines[idx].strip().strip("（）()")
    q.stem = rest

    old_year = (q.meta or {}).get("year")
    q.meta.setdefault("source_in_stem", label)      # 留痕：原来长这样
    q.meta["source_label"] = label
    m = _SRC_YEAR.search(label)
    if m:
        y = int(m.group(0))
        if old_year and int(old_year) != y:
            q.meta["book_year"] = old_year          # 书的年份另存，不丢
        q.meta["year"] = y
    return True


# ── 句末标点 ──────────────────────────────────────────────────────────
#
# 中文行文里句末该用「。」。但库里的题是从各种 LaTeX 源码抠出来的，
# 那些源码习惯用半角句点——实测全库 **80,805 个句末句点是半角 `.`，
# 中文句号只有 1,228 个**。用户定的规矩：**一律统一成「。」**。
#
# 三处**不能动**，动了就是坏数据不是规范：
#   ① 数学模式里的 `.`（`$…$`、`\[…\]` 内）——那是公式的一部分，
#      换成「。」会渲染成乱码。实测 280 个（`cases` 环境末尾那种）。
#   ② 小数点（`3.14`）——靠前置断言 `(?<![\d.])` 排除。
#   ③ 省略号（`…`、`...`）——中间那两个点后面不跟空白，自然不匹配。
_SENT_DOT = re.compile(r"(?<![\d.])\.(?=\s|$)")


def _math_mask(text: str) -> list:
    r"""标出哪些位置在数学模式里（`$…$`、`\(…\)`、`\[…\]`）。

    只要一个布尔数组，不做真正的解析——**够用就行**：
    段落里数不清的 `$` 是靠配对来找的，落单的 `$`（本来就该被
    `定界符配对` 那条检查抓）在这里会让后面整段被当成数学模式，
    结果是"少改几个"，不会改错。**宁可漏改，不可改错。**
    """
    mask = [False] * len(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n and text[i + 1] in "([":
            close = "\\)" if text[i + 1] == "(" else "\\]"
            j = text.find(close, i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                mask[k] = True
            i = j
        elif c == "$":
            j = text.find("$", i + 1)
            j = n if j < 0 else j + 1
            for k in range(i, j):
                mask[k] = True
            i = j
        else:
            i += 1
    return mask


@rule(name="句末半角句点改中文句号", scope=ENTRY,
      why="中文行文句末用「。」。全库原有 80,805 个句末半角句点，"
          "中文句号只有 1,228 个——不统一，读起来别扭")
def sentence_period(q: Question) -> bool:
    r"""句末的 `.` 改成 `。`（数学模式内不动，见上面说明）。"""
    changed = False
    targets = ["stem", "answer", "solution"] + list(range(len(q.options or [])))
    for t in targets:
        text = (q.options[t].text if isinstance(t, int) else getattr(q, t)) or ""
        if "." not in text:
            continue
        mask = _math_mask(text)
        out, last = [], 0
        for m in _SENT_DOT.finditer(text):
            i = m.start()
            if mask[i]:
                continue                      # 数学模式里的，不动
            out.append(text[last:i])
            out.append("。")
            last = i + 1
            # 中文句号后面不留半角空格（`伴随. 如果` → `伴随。如果`）
            if text[last:last + 1] == " ":
                last += 1
        if not out:
            continue
        out.append(text[last:])
        new = "".join(out)
        if new == text:
            continue
        if isinstance(t, int):
            q.options[t].text = new
        else:
            setattr(q, t, new)
        changed = True

    # ⚠️ **作答位置里的句点也要管。**
    #
    # 填空题的答案**写在题干的 `\fillin[…]` 里**，而那个句点后面紧跟的是 `]`
    # 不是空白——上面那条 `(?=\s|$)` 就漏掉了它。
    # 偏偏**正文才是答案的真相**（`iter_questions` 从 `\fillin[…]` 读 answer，
    # 元数据行只是副本），所以 meta 改对了、正文没改＝白改：
    # 界面读出来还是旧的。实测 158 处。
    fixed = _slot_period(q.stem)
    if fixed:
        q.stem = fixed
        changed = True
    return changed


_SLOT_ANS = re.compile(r"\\(?:paren|fillin)\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]")


def _slot_period(stem: str) -> bool:
    r"""把 `\fillin[…X.]` 里末尾那个 `.` 改成 `。`。返回改没改。"""
    if not stem or "." not in stem:
        return False

    def sub(m):
        body = m.group(1)
        if not body.endswith("."):
            return m.group(0)
        return m.group(0)[:m.start(1) - m.start(0)] + body[:-1] + "。" + "]"

    new = _SLOT_ANS.sub(sub, stem)
    if new != stem:
        return new
    return False


@rule(name="行内公式统一用 $…$", scope=ENTRY,
      why="规范 §2.4：行内公式写 `$…$`、行间写 `\\[ … \\]`。"
          "`\\( … \\)` 虽然 LaTeX 也认，但库里 13000 多道有解析的题"
          "只有 51 道用它——**不统一，读起来和批量处理都别扭**")
def unify_inline_math(q: Question) -> bool:
    r"""把 `\( … \)` 改成 `$…$`。

    规范定的是 `$…$`（§2.4）。`\( … \)` 语法上等价，LaTeX 也认，
    所以以前一直放行——但**「合法」不等于「统一」**：库里 13000 多道
    有解析的题只有 51 道用它，混在一起读着别扭，批量处理时也得多想一步。

    只动**成对**的 `\( … \)`；落单的不碰（那多半是写坏了，
    该由规范审查去报，而不是这里猜着补）。
    """
    changed = False
    # ⚠️ **选项也要管**。早先只遍历了题干/答案/解析，漏了 `options`——
    # 结果一道题的选项 D 里还留着 `\( \)`，规范审查照样报（实测踩过）。
    targets = ["stem", "answer", "solution"]
    for i in range(len(q.options or [])):
        targets.append(("opt", i))
    for field in targets:
        if isinstance(field, tuple):
            txt = (q.options[field[1]].text or "")
        else:
            txt = getattr(q, field) or ""
        if "\\(" not in txt or "\\)" not in txt:
            continue
        out, i, n = [], 0, len(txt)
        while i < n:
            j = txt.find("\\(", i)
            if j < 0:
                out.append(txt[i:])
                break
            k = txt.find("\\)", j + 2)
            if k < 0:                      # 落单的 `\(`：原样留着
                out.append(txt[i:])
                break
            out.append(txt[i:j])
            out.append("$" + txt[j + 2:k] + "$")
            i = k + 2
            changed = True
        if "".join(out) != txt:
            changed = True
        if isinstance(field, tuple):
            q.options[field[1]].text = "".join(out)
        else:
            setattr(q, field, "".join(out))
    return changed


@rule(name="答案进作答括号", scope=ENTRY, why="规范 §2.2 单选/多选")
def answer_into_paren(q: Question) -> bool:
    if q.type not in _CHOICE or not q.answer.strip():
        return False
    if _PAREN_FILLED.search(q.stem):
        return False
    ans, body = q.answer.strip(), q.stem.rstrip()
    hits = list(_ANY_PAREN.finditer(body))
    if hits:
        m = hits[-1]
        q.stem = body[:m.start()] + r"\paren[" + ans + "]" + body[m.end():]
        return True
    m = _TAIL_PAREN.search(body)
    if m:
        q.stem = body[:m.start()].rstrip() + r" \paren[" + ans + "]"
        return True
    m = _BARE_PAREN_TAIL.search(body)
    if m:
        q.stem = body[:m.start()] + r"\paren[" + ans + "]"
        return True
    return False


@rule(name="作答括号跟随答案", scope=ENTRY,
      why="规范 §2.2：改了 `answer` 就得改卷面上的作答括号——"
          "只改字段的话，卷面印的还是旧答案（实测踩过）")
def paren_follows_answer(q: Question) -> bool:
    r"""已填的作答括号里**内容对不上答案**时，改成答案。

    `答案进作答括号` 那条规则只在括号**空着**时才填；括号里已经有旧答案时
    它直接返回 False。于是"改答案"只改了字段、没改题干——
    库里 meta 写着 `ACD`，题干里印的还是 `\paren[AC]`，**卷面上是错的**。

    只处理**恰好一个**作答位置的选择题：
    · 选择题只有一个 `\paren`，直接换掉即可；
    · 填空题可能有多个 `\fillin`（一空一个），哪个对哪个得看顺序和分隔符，
      这里**不猜**——那种情况交给 `多空答案分隔符统一` 那条规则。
    """
    if q.type not in _CHOICE or not q.answer.strip():
        return False
    ans = q.answer.strip()
    hits = list(re.finditer(r"\\paren\s*\[([^\]]*)\]", q.stem))
    if len(hits) != 1:
        return False
    if hits[0].group(1).strip() == ans:
        return False                      # 已经一致，不动
    m = hits[0]
    q.stem = q.stem[:m.start()] + r"\paren[" + ans + "]" + q.stem[m.end():]
    return True


@rule(name="去掉残留的空作答括号", scope=ENTRY,
      why="规范 §2.2：作答位置只留一个。题干里既有 `\\paren[…]` 又有"
          " `（$\\quad$）` 时，卷面上会印出**两个括号**（实测 350 道）")
def drop_leftover_blank(q: Question) -> bool:
    r"""题干里已经有 `\paren[…]`／`\fillin[…]` 了，就把残留的空括号删掉。

    `答案进作答括号` 那条规则**看到 `\paren[` 就提前返回**（它是"填空位"用的），
    所以对"已经填好、但旁边还留着一个空括号"的题干无能为力。
    那种题干印出来是这样的：

        ……则 $f^{-1}(2)$ 的值是（$\quad$） \paren[A]

    ——卷面上就是两个括号。这条规则专门收拾它。
    """
    s = q.stem or ""
    if not re.search(r"\\(paren|fillin)\s*(\[[^\]]*\])?", s):
        return False
    hits = list(_ANY_PAREN.finditer(s))
    if not hits:
        return False
    # 从后往前删，避免下标错位；顺带把删完留下的多余空格收一收
    out = s
    for m in reversed(hits):
        out = out[:m.start()] + out[m.end():]
    out = re.sub(r"[ \t]{2,}", " ", out)
    if out == s:
        return False
    q.stem = out
    return True


@rule(name="补作答题括号", scope=ENTRY, why="规范 §2.2：选择题每题都有作答括号")
def ensure_paren(q: Question) -> bool:
    if q.type not in _CHOICE or not q.answer.strip():
        return False
    if re.search(r"\\paren", q.stem):
        return False
    q.stem = q.stem.rstrip() + r" \paren[" + q.answer.strip() + "]"
    return True


# ⚠️ 这条必须排在「答案进填空位」**之前**——答案没洗干净，
# 就谈不上按分隔符拆段、往 `\fillin` 里放。实测踩过：放后面时
# `\begin{enumerate}` 外壳还在，split_answers 拆不出段数，填空位填不上。
@rule(name="答案去列表外壳", scope=ENTRY,
      why="规范 §2.2：答案是一串值，不该裹一层 `\\begin{enumerate}`")
def strip_answer_list(q: Question) -> bool:
    r"""把 `\begin{enumerate}\item A \item B\end{enumerate}` 形式的答案拆成 `A；B`。

    旧库有 7 道题的答案是这种「word 式」结构（LLM 生成的），
    填空题的空位根本没法跟它对应——`\fillin{}` 有两个，答案只有「一段」。
    """
    a = (q.answer or "").strip()
    if "\\begin{enumerate}" not in a:
        return False
    body = re.sub(r"\\begin\{enumerate\}", "", a)
    body = body.replace("\\end{enumerate}", "")
    items = [t.strip() for t in re.split(r"\\item\s*", body) if t.strip()]
    if not items:
        return False
    # 内层还嵌着列表的（1977 江苏连云港那类）不硬拆，交给人工
    if any("\\item" in t for t in items):
        return False
    q.answer = "；".join(items)
    return True


@rule(name="答案进填空位", scope=ENTRY, why="规范 §2.2 填空")
def answer_into_fillin(q: Question) -> bool:
    if q.type != "fill_in_blank" or not q.answer.strip():
        return False
    if _FILLIN_FILLED.search(q.stem):
        return False
    holes = list(_BLANK_FILLIN.finditer(q.stem))
    if not holes:
        return False
    parts = split_answers(q.answer, len(holes))
    if not parts:
        return False
    out, pos = [], 0
    for m, a in zip(holes, parts):
        out.append(q.stem[pos:m.start()])
        out.append(r"\fillin[" + protect(a) + "]")
        pos = m.end()
    out.append(q.stem[pos:])
    q.stem = "".join(out)
    return True


@rule(name="多空答案分隔符统一", scope=ENTRY, why="规范 §2.2：多空用 `；` 分隔")
def unify_sep(q: Question) -> bool:
    if q.type != "fill_in_blank" or "；" in q.answer:
        return False
    holes = len(re.findall(r"\\fillin(?![a-zA-Z])", q.stem))
    if holes < 2:
        return False
    parts = split_answers(q.answer, holes)
    if not parts:
        return False
    q.answer = "；".join(parts)
    return True


@rule(name="方括号参数保护", scope=ENTRY, why="规范 §2.3：不配平的 `[` 会让 TeX 扫到文件末尾")
def protect_brackets(q: Question) -> bool:
    changed = False
    new = put_cmd_arg(q.stem, _FILLIN_CMD)
    if new != q.stem:
        q.stem, changed = new, True
    new = put_cmd_arg(q.stem, _PAREN_CMD)
    if new != q.stem:
        q.stem, changed = new, True
    return changed


@rule(name="去注释", scope=ENTRY, why="规范 §2.8")
def strip_comments(q: Question) -> bool:
    changed = False
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        n = _COMMENT.sub("", t)
        if n != t:
            setattr(q, f, n)
            changed = True
    return changed


@rule(name="去列表选项", scope=ENTRY, why="规范 §2.7：不带 `[label=…]`")
def strip_enum_opt(q: Question) -> bool:
    changed = False
    for f in ("stem", "solution"):
        t = getattr(q, f) or ""
        n = _ENUM_OPT.sub(r"\1", t)
        if n != t:
            setattr(q, f, n)
            changed = True
    return changed


def _skip_args(s: str, i: int) -> int:
    r"""吃掉命令后面跟着的 `{}` / `[]` 参数，返回之后的下标。"""
    n = len(s)
    while i < n and s[i] in " \t":
        i += 1
    while i < n and s[i] in "[{":
        i = _skip_group(s, i, "[" if s[i] == "[" else "{")
        while i < n and s[i] in " \t":
            i += 1
    return i


def _skip_group(s: str, i: int, opener: str) -> int:
    r"""跳过一对配对的 `{…}` 或 `[…]`，返回右括号之后的下标。

    `[` 那一支要把内部的 `{…}` 当整体跳过（`\fillin[$\frac{3\pi}{2}$]` 里
    的 `{3\pi}` 不能影响方括号计数）；`{` 那一支只数花括号。
    **不要互相递归**——早先写成 `{` 分支递归自己，直接爆栈。
    """
    n = len(s)
    d, j = 0, i
    if opener == "{":
        while j < n:
            c = s[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                d += 1
            elif c == "}":
                d -= 1
                if d == 0:
                    return j + 1
            j += 1
        return n
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            j = _skip_group(s, j, "{")      # 花括号整块跳过
            continue
        if c == "[":
            d += 1
        elif c == "]":
            d -= 1
            if d == 0:
                return j + 1
        j += 1
    return n


def _tokenize(text: str) -> list[tuple[str, str]]:
    r"""切成 `("t", 文本)` / `("$", "$")` / `("c", 整条命令含参数)`。

    命令的参数**整条吞掉**，所以 `\fillin[$\frac{3\pi}{2}$]` 里那两个 `$`
    不会干扰公式边界。
    """
    toks: list[tuple[str, str]] = []
    i, n, buf = 0, len(text), []

    def flush():
        if buf:
            toks.append(("t", "".join(buf)))
            buf.clear()

    while i < n:
        m = _FILLIN_CMD.match(text, i) or _PAREN_CMD.match(text, i)
        if m:
            flush()
            end = _skip_args(text, m.end())
            toks.append(("c", text[i:end]))
            i = end
            continue
        if text[i] == "\\" and i + 1 < n:
            buf.append(text[i:i + 2])
            i += 2
            continue
        if text[i] == "$":
            flush()
            toks.append(("$", "$"))
            i += 1
            continue
        buf.append(text[i])
        i += 1
    flush()
    return toks


@rule(name="填空位移出数学模式", scope=ENTRY,
      why="规范 §2.2：空位在数学模式里会产生**嵌套 `$`**，是坏掉的 LaTeX")
def move_blanks_out_of_math(q: Question) -> bool:
    r"""把 `$A=\fillin[答案]$` 改成 `$A=$\fillin[答案]`。

    旧库把空位写在数学模式**里面**（`$d=\fillin{}$`）。答案被填进去时，
    若答案自己带 `$`（`\frac`、`\sqrt` 这类几乎都带），就变成：

        $\theta=\fillin[$\frac{3\pi}{2}$]$      ← 嵌套 `$`，坏掉的 LaTeX

    卷面上会画成 `θ = ____ [\frac{3\pi}{2}]`——**答案漏出来了**。
    实测踩过：2026 全国I卷#13、北京卷#14、天津卷#12/#14、上海卷（秋）#11。

    做法：**按整个数学段重写**，不是逐个命令就地切。
    命令本身会把公式的收尾 `$` 一起吃掉，逐命令切会让后面的公式错位
    （`$x=1$` 会掉到正文里）。按段重写就没有这个问题：

        `$\theta=` + cmd + `$`   →   `$\theta=$` + cmd
    """
    toks = _tokenize(q.stem)
    if not any(k == "c" for k, _ in toks):
        return False

    out: list[str] = []
    k, n = 0, len(toks)
    while k < n:
        kind, s = toks[k]
        if kind != "$":
            out.append(s)
            k += 1
            continue
        j = k + 1
        while j < n and toks[j][0] != "$":
            j += 1
        if j >= n:                       # 落单的 `$`，原样留着
            out.append(s)
            k += 1
            continue
        inner = toks[k + 1:j]
        body = "".join(t[1] for t in inner)
        # ⚠️ 公式里有**环境**（`\begin{cases}`、`array`、`matrix`…）时**不能切开**：
        # `\begin{cases}` 和 `\end{cases}` 会落到两段公式里，直接坏掉。
        # 实测：2004 全国I卷（理）#15 的 `a_n = \begin{cases}…\fillin{}…\end{cases}`
        # 就是这么被切坏的（12 个 `$` 变成 16 个 + 一个 `\$`）。
        #
        # 这种情形改成**留在公式里**，只把答案自带的 `$` 脱掉——
        # 已经在数学模式里，答案不需要自己的 `$`。
        # 公式里有 `\left…\right` 配对时**也不能切**：
        # `$O'\left($\fillin{}$,$\fillin{}$\right)$` 切开后
        # `\left(` 和 `\right)` 落到两段公式里，KaTeX 直接报
        # "Expected '\right', got 'EOF'"（实测 1999 上海卷（理）#5）。
        if "\\begin{" in body or "\\left" in body or "\\right" in body:
            fixed = []
            for kk, ss in inner:
                if kk == "c":
                    fixed.append(re.sub(r"(?<!\\)\$", "", ss))
                else:
                    fixed.append(ss)
            out.append("$" + "".join(fixed) + "$")
        elif not any(t[0] == "c" for t in inner):
            out.append("$" + body + "$")
        else:
            seg: list[str] = []
            for kk, ss in inner:
                if kk == "c":
                    body = "".join(seg).strip()
                    if body:
                        out.append("$%s$" % body)
                    out.append(ss)       # 命令落在数学模式**外面**
                    seg = []
                else:
                    seg.append(ss)
            body = "".join(seg).strip()
            if body:
                out.append("$%s$" % body)
        k = j + 1

    new = "".join(out)
    if new != q.stem:
        q.stem = new
        return True
    return False


@rule(name="答案里的说明归位", scope=ENTRY,
      why="规范 §2.2：选择题的 `answer` 只能是 A–D；说明文字归 `answer_note`")
def move_answer_note(q: Question) -> bool:
    r"""选择题的答案位置写的是**说明**时，把它挪到 `meta.answer_note`。

    旧库有一批题，答案栏写的是勘误说明：

        原题无正确选项
        题面数据与选项不相容.
        \\(\frac{1}{8}\\)（按题面计算；原题四个选项均不含此值）

    这些是**真实考卷本身有错**（或 OCR 录入有误）的题。三种做法里：

      * 硬塞一个 A–D  → **编造答案**，绝不能做
      * 整题丢掉      → 题目本身是好的（题干、选项都在），可惜
      * 说明归位      → **保留题目，答案留空，把为什么写清楚** ← 选这个

    留空之后 `schema` 不会报错——"答案为空"是**数据不完整**，
    不是"结构非法"，两者在 `problems()` 与 `missing()` 里分得很清楚。
    """
    ans = (q.answer or "").strip()
    if not ans or q.type not in ("single_choice", "multi_choice"):
        return False
    n = max(len(q.options), 4)
    letters = "".join(sorted(set(ans.upper())))
    if letters and all(c in OPTION_LABELS[:n] for c in letters):
        return False                      # 是正经答案，不动
    if q.meta.get("answer_note"):
        return False
    q.meta["answer_note"] = ans
    q.answer = ""
    return True


# 题干末尾内嵌的四选项：`……（ ）\n\nA. 甲\nB. 乙\nC. 丙\nD. 丁`
_INLINE_OPTS = re.compile(
    r"(?:^|\n)\s*A\s*[.、．]\s*(?P<A>[^\n]+)\s*\n"
    r"\s*B\s*[.、．]\s*(?P<B>[^\n]+)\s*\n"
    r"\s*C\s*[.、．]\s*(?P<C>[^\n]+)\s*\n"
    r"\s*D\s*[.、．]\s*(?P<D>[^\n]+)\s*$")


@rule(name="题干里的选项拆出来", scope=ENTRY,
      why="规范 §2.5：选项要进 `options`，不能混在题干里当正文")
def split_inline_options(q: Question) -> bool:
    r"""把**题干末尾内嵌的四个选项**拆到 `q.options`。

    OCR 有时把选项留在题干正文里，`options_json` 却被切坏：

        题干: ……体积的最大值为（ ）

        A. $\frac{2\sqrt{3}}{3}$
        B. $\frac{4\sqrt{3}}{3}$
        C. $2\sqrt{3}$
        D. $\frac{8\sqrt{3}}{3}$

    这种题在卷面上会把选项当正文印出来，而且没法和答案对应。
    旧库全书 6 道（都在模拟题里），模式很明确，所以做成规则而不是逐题改。
    """
    if q.type not in ("single_choice", "multi_choice"):
        return False
    # 只在**选项残缺**时动手，避免把正常题目的正文误拆
    if q.options and all(o.text.strip() for o in q.options):
        return False
    m = _INLINE_OPTS.search(q.stem)
    if not m:
        return False
    opts = [m.group(k).strip() for k in ("A", "B", "C", "D")]
    if any(not t for t in opts):
        return False
    q.stem = q.stem[:m.start()].rstrip()
    q.options = [Option(lab, txt) for lab, txt in zip("ABCD", opts)]
    return True


@rule(name="行间公式定界符去壳", scope=ENTRY,
      why="规范 §2.6：`$\\[…\\]$` 是坏的，KaTeX 不认 `\\[` 在数学模式里")
def unwrap_display_in_inline(q: Question) -> bool:
    r"""`$\[ … \]$` → `\[ … \]`。

    美元符里套行间公式定界符，两边都不认：KaTeX 报
    "Undefined control sequence: \["（实测 2009 上海卷（秋理）#4 的答案）。
    """
    pat = re.compile(r"\$\s*\\\[(.*?)\\\]\s*\$", re.S)
    changed = False
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        n = pat.sub(lambda m: "\\[%s\\]" % m.group(1), t)
        if n != t:
            setattr(q, f, n)
            changed = True
    return changed


# ── 入口 ────────────────────────────────────────────────────────────

def normalize(q: Question, scope: str = ENTRY) -> list[str]:
    """把一道题改成规范形态。返回生效的条目名。"""
    fired = []
    for r in RULES:
        if r.scope != scope:
            continue
        try:
            if r.fn(q):
                fired.append(r.name)
        except Exception as e:
            fired.append("%s(异常:%s)" % (r.name, type(e).__name__))
    return fired


def rules_of(scope: str = ENTRY) -> list[Rule]:
    return [r for r in RULES if r.scope == scope]


def get(name: str) -> Rule | None:
    return _BY.get(name)


# ── 自检 ────────────────────────────────────────────────────────────

def _selftest() -> int:
    from .schema import Option

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("normalize 自检")

    # 方括号保护：不配平的才保护
    check("`\\left[…\\right)` 判为需保护",
          needs_brace_protect(r"$\left[ 700,4900 \right)$"))
    check("`\\sqrt[3]{…}` 判为不需保护",
          not needs_brace_protect(r"$\sqrt[3]{\frac{3}{2}}$"))
    check("`$[1,3]$` 判为不需保护", not needs_brace_protect(r"$[1,3]$"))
    check("`$[1,3)$` 判为需保护", needs_brace_protect(r"$[1,3)$"))

    q = Question(key="t/1", type="fill_in_blank",
                 stem=r"范围为 \fillin[$\left[ 700,4900 \right)$]．",
                 answer=r"$\left[ 700,4900 \right)$")
    fired = normalize(q)
    check("填空参数被保护", r"\fillin[{" in q.stem, q.stem)
    check("自检报出改了什么", "方括号参数保护" in fired, str(fired))

    # 选择：答案进括号
    q2 = Question(key="t/2", type="single_choice",
                  stem=r"则 $A\cap B=$（\quad）", answer="B",
                  options=[Option("A", "a"), Option("B", "b")])
    normalize(q2)
    check("选择答案进 \\paren", r"\paren[B]" in q2.stem, q2.stem)

    # 填空：多空
    q3 = Question(key="t/3", type="fill_in_blank",
                  stem=r"$x=$ \fillin{} ，$y=$ \fillin{} 。", answer=r"$1$，$2$")
    normalize(q3)
    check("多空各归各位",
          r"\fillin[$1$]" in q3.stem and r"\fillin[$2$]" in q3.stem, q3.stem)
    check("多空分隔符统一成 ；", q3.answer == "$1$；$2$", q3.answer)

    # 注释 / 列表选项
    q4 = Question(key="t/4", type="detailed_answer",
                  stem="a % 注\n\\begin{enumerate}[label=(\\arabic*)]\n\\item x\n\\end{enumerate}")
    normalize(q4)
    check("注释被清", "%" not in q4.stem, repr(q4.stem))
    check("列表选项被去", "[label=" not in q4.stem, repr(q4.stem))

    # 题干写「多选」的单选题 → 改判多选（正反两组控制样本）
    def _mk(stem, typ="single_choice", n=4):
        return Question(key="t/m", type=typ, stem=stem,
                        options=[Option(OPTION_LABELS[i], "x") for i in range(n)])

    q_m = _mk(r"（多选）已知 $f(x)=x^{3}$，则（\quad）")
    check("题首「（多选）」改判多选", fix_multi_choice_type(q_m) and q_m.type == "multi_choice",
          q_m.type)
    check("改判后幂等", not fix_multi_choice_type(q_m), q_m.type)
    q_m2 = _mk(r"）（多选）已知体积为 2 的四棱锥，则（\quad）")
    check("题首有杂标点也认", fix_multi_choice_type(q_m2) and q_m2.type == "multi_choice",
          q_m2.type)
    # 反例一：正文里提到「多项选择题」（讲多选题评分规则的那类）不能误判
    q_n1 = _mk(r"新高考数学试卷共有 3 道多项选择题，每题有 $A$、$B$、$C$、$D$，"
               r"4 个选项，则得分情况为（\quad）")
    check("正文提「多项选择题」不动", not fix_multi_choice_type(q_n1), q_n1.type)
    # 反例二：选项数不是 4 的不动
    q_n2 = _mk(r"（多选）下列正确的是（\quad）", n=3)
    check("选项不足 4 个不动", not fix_multi_choice_type(q_n2), q_n2.type)
    # 反例三：本来就是多选的不动
    q_n3 = _mk(r"（多选）下列正确的是（\quad）", typ="multi_choice")
    check("已是多选不动", not fix_multi_choice_type(q_n3), q_n3.type)
    # 反例四：填空题里的「多选」不动
    q_n4 = _mk(r"（多选）说法正确的有 \fillin{}", typ="fill_in_blank", n=0)
    check("非单选题不动", not fix_multi_choice_type(q_n4), q_n4.type)

    # 题首杂标点
    q_j = Question(key="t/j", type="fill_in_blank", stem="）已知 $f(x)=x$，则 \fillin{}")
    check("题首右括号被去", strip_lead_junk(q_j) and q_j.stem.startswith("已知"), q_j.stem)
    check("去杂标点后幂等", not strip_lead_junk(q_j), q_j.stem)
    q_j2 = Question(key="t/j2", type="detailed_answer",
                    stem="（1）求 $f(x)$ 的单调区间；\n（2）若 $f(x)>0$，求 $a$．")
    check("「（1）」开头的题不动", not strip_lead_junk(q_j2), q_j2.stem)

    # 作答括号跟随答案：**改答案就得改卷面**
    q_p = Question(key="t/p", type="multi_choice", stem=r"则（\quad）\paren[AC]",
                   answer="ACD", options=[Option(x, "1") for x in "ABCD"])
    normalize(q_p)
    check("括号里的旧答案被改成新的", r"\paren[ACD]" in q_p.stem, q_p.stem)
    check("改完幂等", not normalize(q_p), q_p.stem)
    # 反例：括号里已经和答案一致 → 一个字都不动
    q_p2 = Question(key="t/p2", type="single_choice", stem=r"则\paren[B]", answer="B",
                    options=[Option(x, "1") for x in "ABCD"])
    check("已一致就不动", not normalize(q_p2), q_p2.stem)
    # 反例：填空题的多个 \fillin 不归这条管（顺序和分隔符得另判，不猜）
    q_p3 = Question(key="t/p3", type="fill_in_blank",
                    stem=r"\fillin[1] 与 \fillin[2]", answer="1；2")
    check("填空题的作答位不动", not paren_follows_answer(q_p3), q_p3.stem)

    # 幂等
    q5 = Question(key="t/5", type="single_choice", stem=r"则 $A\cap B=$（\quad）",
                  answer="B", options=[Option("A", "a"), Option("B", "b")])
    normalize(q5)
    before = q5.stem
    check("幂等：再跑一次不改", not normalize(q5) and q5.stem == before, q5.stem)

    print("normalize 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
