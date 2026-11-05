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
# 空位写法有三种：裸 `\fillin`、`\fillin{}`、`\fillin[]`。**三种都要吃干净**——
# 老正则不吃 `[]`，于是「答案进填空位」替换完会留下一个空括号：`\fillin[2][]`（实测）。
_BLANK_FILLIN = re.compile(r"\\fillin(?![a-zA-Z])\s*(?:\{\}|\[\s*\])?")
# ⚠️ **空括号 `\fillin[]` 不算"填过"**——老正则 `\\fillin\s*\[` 把空括号也认成已填，
# 于是「答案进填空位」永远 return False：答案只写进 JSON 字段、正文里还是 `\fillin[]`，
# 而**正文才是真相**（`iter_questions` 从 `\fillin[…]` 推 answer）→ 表现就是
# "补答案显示成功、库里却永远没答案"（实测 224 道全中，接口/统计都跟着错）。
_FILLIN_FILLED = re.compile(r"\\fillin\s*\[\s*[^\]\s]")
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


# ── 卷面排版噪声：分值前缀 与 页眉页脚 ────────────────────────────────
#
# 用户 2026-09-18 报的（台账 D01 / D02）：
#   「题目非常不规范，分值没必要录入」「最后一句话明显是有问题的」
# 最后那句是页脚「2025年秋季学期高三年级12月质量检测数学试题 第 4 页 共 4 页」，
# 被 OCR 整页读进来挂在了题干尾巴上。
#
# ⚠️ 分值前缀不只是难看——它是台账 D03（解答题答案是「AA」）的**触发器**：
#     `16.（本小题满分15分）` 这一行会被 parse_answer_table 当成"题号行"
#     （nums=['16','15']：题号+分值），下一行的 LaTeX 变量名 OBB_{1}O_{1} 被
#     抠成答案字母 ['BB','AA']，于是 15→AA、16→BB。所以这条规则要**赶在**
#     答案表解析之前生效。
_SCORE_HEAD = re.compile(
    r"""^\s*(?:
        [（(]\s*(?:本小题|本题)?\s*(?:满分\s*)?\d{1,3}\s*分\s*[）)]   # （本小题满分17分）/（13分）
      | (?:本小题|本题)\s*(?:满分\s*)?\d{1,3}\s*分                   # 本小题满分17分（没括号）
      | 满分\s*\d{1,3}\s*分                                          # 满分17分
    )\s*[。，、；;,.．]?\s*""", re.X)   # 结尾那个孤零零的「。」一并带走
# 页脚：`第 3 页 共 8 页` / `第4页 共4页` / `第7页共8页`（空格有无都认）。
# ⚠️ **「共 N 页」不是可选的**：写成可选时，正文里的「人教A版必修第一册第 92 页上
# "探究与发现"…」会被当成页脚，整行删掉——实测把一道题截成了 9 个字。
# 真实页脚全都带「共」（`grep '第 *[0-9]* *页 *共'` 抽过全部变体）。
#
# 2026-10-28 照存量补的三档写法（机检数到 176 道，老规则只吃到 7 道，差的都是这三档）：
#   · **中间带标点/括号**：「试卷第5页，共5页」「答案第 6页，共 12页」「第1页[共11页]」
#   · **倒装**（共在前）：「高三数学试卷参考答案 共6页 第1页」「数学答案（共 8 页）第 3 页」
#   · **尾巴拖日期**：「高三数学 第2页 （共4页） （2025.10）」
# 「共 N 页」这一头**仍然不许省略**——上面那条伤还在，单独一个「第 N 页」只用于
# `_PG_ANY`（整行纯排版判定），不参与"从正文里剪"。
_PG = r"\d{1,3}"
_PG_SEP = r"(?:[，,、;：:\s]|[(（\[]\s*)*"                       # 页码两段之间
_PG_CLOSE = r"(?:\s*[)）\]])*"                                    # 「（共4页）」的收尾
_PG_DATE = r"(?:\s*[(（]\s*(?:19|20)\d{2}(?:[.．]\d{1,2})?\s*[)）])*"   # 拖在后面的日期
_PG_1 = r"第\s*%s\s*页%s共\s*%s\s*页%s%s" % (_PG, _PG_SEP, _PG, _PG_CLOSE, _PG_DATE)
_PG_2 = r"共\s*%s\s*页%s%s第\s*%s\s*页%s%s" % (_PG, _PG_SEP, _PG_CLOSE, _PG, _PG_CLOSE, _PG_DATE)
_FOOT = re.compile("(?:%s|%s)" % (_PG_1, _PG_2))
# 同一句页脚连着出现两遍以上：多栏版式把页脚在每个栏位都印了一次。
_FOOT_RUN = re.compile("%s(?:\\s*%s)+" % (_FOOT.pattern, _FOOT.pattern))

# 卷眉关键词：页脚前面那一小段卷名（「2025年秋季学期高三年级12月质量检测数学试题」）
_HEAD_KW = re.compile(
    r"数学|试题|试卷|答案|解析|联考|质检|检测|调研|测评|诊断|学情"
    r"|年级|学期|联盟|协作体|中学|高三|高二|高一|届|第")
# 「卷眉词汇表」：把一段话里这些词和数字/标点全抠掉，**什么都不剩**才认定它是卷眉。
# 这是"整行删"和"从关键词处剪"的分界线：
#   「2025年秋季学期高三年级12月质量检测数学试题」→ 抠完为空 → 整行删
#   「所以红桃 A 的左侧没有数字牌高三数学 答案」→ 剩「所以红桃的左的侧没的数字牌」→ 只剪不删
_HEAD_PIECE = re.compile(
    r"[0-9０-９A-Za-z\s·、，,（）()]|年|月|季|学期|届|高三|高二|高一|中|小"
    r"|数学|语文|英语|物理|化学|生物|政治|历史|地理|试题|试卷|答案|解析"
    r"|参考|评分|标准|及|联考|质检|质量|检测|调研|测评|诊断|学情|联盟|协作体"
    r"|中学|学校|市|省|区|县|第|页|共"
    # 下面这些是照真实卷眉补的（「2025年秋季学期高三年级12月质量检测」这种）：
    # 少了「级」，整条卷眉抠不干净，就只剪掉一半、留下「…高三年级」挂在正文尾巴上
    r"|年级|级|秋|春|夏|冬|返|校|考|联|盟|协|作|体")
_TERM = re.compile(r"[。！？；!?]")
# 正文虚词：排版行（卷眉/页脚）里不会出现这些字，正文里到处都是。
# 拿它区分"整行是排版"和"正文与页脚挤在一行"——比维护一张卷眉关键词表可靠得多。
_CONTENT_HINT = re.compile(r"的|是|则|求|若|设|已|知|有|为|得|故|且|或|中")
# ⚠️ `_CONTENT_HINT` 里的「中」会误伤校名（「重点高中智学联盟」），拿来判"整行是不是
# 卷眉"就删不掉。所以整行判定用这一张**只会出现在正文、绝不会出现在卷眉**的窄表：
# ⚠️ 单字「则」不能进来：答案册的「评分细**则**」天天带它（实测两处否决表都被
#    「细则」挡掉，卷眉行删不干净）。真句子里的「则」旁边一定还有「的/是/若/故」。
_HEAD_BLOCKER = re.compile(r"的|是|求|若|已|故|且|或|本|该")


def _is_running_head(seg: str) -> bool:
    """这一段是不是**纯粹**的卷眉（卷眉词抠完什么都不剩）。"""
    return not _HEAD_PIECE.sub("", seg or "").strip()


# 整行判定专用的页码 token：比 `_FOOT` 松一档，允许只有「第 N 页」没有「共」
# （「数学试题参考答案 第1页」就是这一档），也允许只有「（共 4 页）」
# （「咸阳市 2026 年高考数学模拟检测(一)-1-(共 4 页)」）。
_PG_LOOSE = re.compile(r"(?:%s|%s|第\s*%s\s*页%s%s|共\s*%s\s*页%s)"
                       % (_PG_1, _PG_2, _PG, _PG_CLOSE, _PG_DATE, _PG, _PG_CLOSE))
# 页码被换行**劈成两截**之后剩下的半截：「页，共18页」「1页 共4页」「第 4 页，共 4 页。」
# ——多栏 PDF 里「第 7」在上一栏末尾、「页，共18页」在下一栏开头，`_FOOT` 要求「第N页共M页」
# 连在一起就吃不到。这一档整行只可能是排版：一行除了页码什么都不剩。
_FOOT_FRAG = re.compile(
    r"^(?:第\s*)?(?:\d{1,3}\s*)?页\s*[，,、]?\s*[（(\[]?\s*共\s*\d{1,3}\s*页"
    r"\s*[)）\]]?\s*[。．]?$")
# 卷眉里必然出现的词（**不含「第」「页」**——那两个字页码本身就有，当判据等于没判）。
_HEAD_MARK = re.compile(
    r"数学|试题|试卷|答案|解析|参考|评分|标准|细则|意见|提示|说明|注意事项|绝密|启用"
    r"|联考|质检|质量|检测|调研|测评|诊断|学情|考试|模拟|期中|期末|月考|联盟|协作体"
    r"|中学|学校|年级|高三|高二|高一|资料库|出版|版权|群|微信|App|站")
# 🔴 **注释否决表**：本项目自己写在解析里的话，长得像卷眉但不是排版。
# 实测踩过：「解析无（原册第 1 页只印了答案表，#1 没有【解析】段．）」被整行判成页脚删掉，
# 11 道题的解析就这样空了。这类句子一定带「原册／解析无／待复核／照录…」这些词。
_HEAD_VETO = re.compile(
    r"解析无|待复核|已登记|照录|未录|只印|没有|原册|原卷|答案册|见解析|#\d|【解析】|疑为|应为")


def _is_paper_head_line(seg: str) -> bool:
    r"""整行是「卷名 + 页码」这一类排版行吗（用来决定"整行删"还是"从关键词处剪"）。

    五条一起卡，缺一条就会吃掉正文：
      · **必须**带页码 token，且带一个卷眉词（`_HEAD_MARK`）；
      · 不含 `$`——正文行几乎都带公式；
      · 不含 `_HEAD_BLOCKER` 那批只在正文里出现的虚词（「中」不算，「重点高中」是校名）；
      · 不含 `_HEAD_VETO`——我们自己写的注释长得像卷眉；
      · 没有句子标点、长度 ≤ 60。
    实测守住的两条伤：「人教A版必修第一册第 92 页上的探究…」靠「的」+没有卷眉词挡住，
    「一本书共 100 页，每天读 5 页」靠「本」挡住。
    """
    s = (seg or "").strip()
    if not s or "$" in s or len(s) > 60:
        return False
    if not _PG_LOOSE.search(s) or not _HEAD_MARK.search(s):
        return False
    # 行尾那个句号是 OCR 粘上去的（「数学参考答案及评分细则 （第2页，共4页）。」），
    # 只允许**行尾**有，句子中间的句号照样一票否决。
    s_body = re.sub(r"[。．]+$", "", s)
    if _HEAD_BLOCKER.search(s) or _HEAD_VETO.search(s) or _TERM.search(s_body):
        return False
    return True





@rule(name="去题干开头的分值", scope=ENTRY,
      why="用户 2026-09-18：分值没必要录入。而且它会诱发答案表误判"
          "（台账 D03：`16.（本小题满分15分）` 被当成题号行）")
def strip_score_head(q: Question) -> bool:
    r"""去掉题干开头的「（本小题满分 N 分）」「（N 分）」。

    **只动开头**：这里是录入当场的清理；解析里夹着的步骤分由后面的
    `strip_step_scores` 统一处理（2026-10-28 用户把台账 D09 的
    「有信息、留着」翻案了，改为全部删除）。
    """
    new = _SCORE_HEAD.sub("", q.stem or "", count=1)
    if new == (q.stem or "") or not new.strip():
        return False
    q.stem = new
    return True


# ── 解析里的步骤分与评分点线 ──────────────────────────────────────
# 2026-10-28 用户明确：「254 道解析里的步骤分（如「……（6分）」
# 「(本小题满分13分)」）——删除掉」，并点名 56 道「全角空格＋点线」
# （「　………5分」）与它同源。此前台账 D09 判「有信息、留着」，现翻案。
#
# 这些是答案册的**评分细则排版**，不是讲解：讲「这一步值 6 分」对读者
# 没有信息量，点线还把一行撑成两行。删的时候连点线、连它前面的逗号一起
# 带走，否则会留下一条光秃秃的「……」，或者一个悬空的「，」。
_SOL_SCORE_PAREN = re.compile(
    r"[（(]\s*(?:本小题|本题)?\s*(?:满分\s*|分值\s*)?\d{1,3}\s*分\s*[）)]")
# 题干里只认「（N分）」这一档——「（满分 150 分）」「（试卷满分 150 分）」
# 往往是题目**内容**（某次考试的满分），不能删（实测 3 道）。
_STEM_SCORE_PAREN = re.compile(r"[（(]\s*\d{1,3}\s*分\s*[）)]")
# 题干里的「（本小题 15 分）」「（本题满分 13 分）」。**不认**光秃秃的
# 「（满分 150 分）」——那是题目内容（「某次考试（满分 150 分）」），留着。
_STEM_SCORE_NAMED = re.compile(
    r"[（(]\s*(?:本小题|本题)\s*(?:满分\s*)?\d{1,3}\s*分\s*[）)]")
# 行首的「(★)」只跟分值一起出现（「(★)(15分)已知函数…」）才算分值噪声；
# 单独一个 (★) 是难度标记，不在本规则管辖内，不动。
_STAR_HEAD = re.compile(
    r"^[ \u3000]*[（(]★[）)][ \u3000]*(?=[（(]\s*\d{1,3}\s*分\s*[）)])")


def _sub_outside_slots(rx: re.Pattern, text: str, repl: str = "") -> str:
    r"""只替换 `\fillin[…]`／`\paren[…]` **外面**的文本。

    答案槽里偶有脏数据（「\fillin[解：…(2分)]」），那是要整条订正的，
    不是让格式规则从中间抠掉两字——抠完会留下一条更像样的坏数据。
    """
    from .latex_ir import bracket_arg

    out: list[str] = []
    i = last = 0
    n = len(text)
    while True:
        hits = [p for p in (text.find(r"\fillin", i), text.find(r"\paren", i)) if p >= 0]
        if not hits:
            break
        j = min(hits)
        k = j + (len(r"\fillin") if text.startswith(r"\fillin", j) else len(r"\paren"))
        while k < n and text[k] in " \t":
            k += 1
        if k < n and text[k] == "[":
            _arg, end = bracket_arg(text, k)
            out.append(rx.sub(repl, text[last:j]))
            out.append(text[j:end])
            last = i = end
        else:
            i = k
    out.append(rx.sub(repl, text[last:]))
    return "".join(out)
# 点线＋分值：「……（6分）」「..... 14分」「　………………5分」。
# 单个「…」「⋯」本身就是三点省略号，也算点线；单个 ASCII 句点不算
# （「0.5分」是正文里的扣分规则）。
_SCORE_LEADER = re.compile(
    r"[，,、；;]?[ \u3000]*(?:[.…⋯·]{2,}|[…⋯])[ \u3000]*"
    r"(?:[（(]\s*)?(?:本小题|本题)?\s*(?:满分\s*|分值\s*)?\d{1,3}\s*分(?:\s*[）)])?")
# 没有点线、也没有括号的「本小题满分 17 分」「满分13分」
_SOL_SCORE_BARE = re.compile(
    r"(?:本小题|本题)\s*(?:满分\s*)?\d{1,3}\s*分|满分\s*\d{1,3}\s*分")
# 有的答案册把分直接右对齐印在行尾（「……成立； 9分」），甚至单独一行「12分」。
# 只认行尾/整行：正文里「得分为 77.5 分」后面还跟着字，不会被吃。
_SCORE_TAIL = re.compile(
    r"(?m)^[ \u3000]*\d{1,2}\s*分[ \u3000]*$|[ \u3000]+\d{1,2}\s*分[ \u3000]*$")


def _tidy_score_gaps(text: str) -> str:
    r"""删完分值后的收尾：行尾空格、三连空行、整段首尾空行。"""
    t = re.sub(r"[ \t]+\n", "\n", text)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip("\n")


@rule(name="去解析里的步骤分与点线", scope=MIGRATE,
      why="用户 2026-10-28：解析里的「……（6分）」「满分13分」"
          "「　………5分」是答案册评分细则的排版，不是讲解，全部删掉"
          "（推翻台账 D09「有信息、留着」）。")
def strip_step_scores(q: Question) -> bool:
    changed = False

    old = q.solution or ""
    new = old
    applied = False
    for rx in (_SCORE_LEADER, _SOL_SCORE_PAREN, _SOL_SCORE_BARE, _SCORE_TAIL):
        newer = rx.sub("", new)
        applied = applied or newer != new
        new = newer
    if applied:
        new = _tidy_score_gaps(new)
        if new.strip():
            q.solution = new
            changed = True

    old = q.stem or ""
    new = _sub_outside_slots(_STAR_HEAD, old)
    for rx in (_SCORE_LEADER, _STEM_SCORE_PAREN, _STEM_SCORE_NAMED, _SCORE_TAIL):
        new = _sub_outside_slots(rx, new)
    if new != old:
        new = _tidy_score_gaps(new)
        if new.strip():
            q.stem = new
            changed = True

    return changed


@rule(name="去全角空格", scope=MIGRATE,
      why="用户 2026-10-28：全库 56 处 U+3000（「　……5分」的点线缩进、"
          "「①　所以」的分隔、行首缩进、填空位前的空格）。LaTeX 里全角空格"
          "没有排版意义，只会让源码多出一种看不见的字符。")
def strip_ideographic_space(q: Question) -> bool:
    changed = False
    for field in ("stem", "solution"):
        old = getattr(q, field) or ""
        if "\u3000" not in old:
            continue
        new = old.replace("\u3000", "")
        new = _tidy_score_gaps(new)
        if new != old and new.strip():
            setattr(q, field, new)
            changed = True
    for o in q.options:
        old = o.text or ""
        if "\u3000" in old:
            new = old.replace("\u3000", "").strip()
            if new:
                o.text = new
                changed = True
    return changed


# 卷面噪声的另外四类形态（机检 A8 数到 672 道，原来那条只认「页」字，
# 这四类**一个都进不去**——所以提级成 MIGRATE 后影响面只有 15 道）。
# ⚠️ 一律要求**整行就是它**（或行尾拖着的一小截），绝不吞整行正文：
#    「四、解答题」这种串在正文后面的，只剪掉后半截。
# 🔴 水印那一路**不能写 `.*?` 前缀**：加了前缀，「则 $6=a+b+c\geq3\sqrt{bc}$，3亿人都在用的扫描App」
#    这种"正文＋水印"的行会整条被判成噪声删掉——实测把厦门一中#15 的一整行推导删没了。
#    水印只当"剪断点"用（见 `_WATERMARK`），永远不参与"整行删"。
_WATERMARK = re.compile(
    r"Q{1,2}\s*(?:教师|学生)?\s*[群号]\s*[:：]?\s*\d{5,}"          # 「QQ 教师群：965672919」也认
    r"|微信公众号|工书号\s*[:：]?\s*\w+"
    r"|3\s*亿\s*人\s*都\s*在\s*用\s*的?\s*(?:扫描?\s*)?App"          # 「3 亿人都在用的扫描 App」
    r"|扫描\s*App|版权(?:声明|所有)|盗版必究|正式出版物"
    r"|资料库|青云解析|视频号|B\s*站\s*[:：]"
    r"|★[^★\n]{0,24}★|绝密\s*★?\s*启用前")
_JUNK_HINT = re.compile(
    r"页|参考答案|QQ|微信公众号|工书号|3\s*亿|扫描\s*App|选择题|填空题|解答题"
    r"|版权|资料库|青云|★|启用前|题号|题序")
_JUNK_LINE = re.compile(
    r"^\s*(?:"
    r"[一二三四五六七八九十]\s*[、.．]\s*(?:单项选择题|多选题|选择题|填空题|解答题|单选题)"   # 节标题（光杆）
    r"|(?:完整)?参考答案(?:及?解析)?|答案(?:及|与)?解析"                                     # 答案卷页眉
    r"|(?:数学|文科数学|理科数学)?(?:试题|试卷)?[（(]?第\s*\d+\s*[)）]?\s*(?:页|Page)"          # 页码变体
    # 「卷名 + 第N页（共M页）」整行页眉：上一支只认到「页」字为止，`(共4页)` 一挡就漏。
    # ⚠️ 前缀限长 24 字且**不含 `$`**：行里只要有数学式就不认，避免把正文吃掉。
    r"|[^$\n]{0,24}?第\s*\d+\s*页\s*[（(]\s*共\s*\d+\s*页\s*[)）][】\]]?"
    r")[\s:：]*$", re.I)
# 广告/署名行：**整行**只有水印和署名，没有数学、没有正文虚词。
# 有水印不等于能删整行——「则 $6=a+b+c\geq3\sqrt{bc}$，3亿人都在用的扫描App」那类
# 只能从水印处剪（见上面的 🔴 注），所以这里要「不含 `$` + 不含正文虚词 + 短」三条一起卡。
# 「则」同上：不能挡在广告行否决表里（「评分细则」不是广告，但也别让它连带失效）
_AD_LINE_BLOCKER = re.compile(r"的|是|求|若|已|故|且|或|本|该|在")
# 节标题**后面还拖着卷首说明**的：`三、填空题：本题共3小题，每小题5分，共15分。`
# 上一版只认光杆的「三、填空题」，所以这种带说明的一条没吃到（机检 A8 剩 659 道里的大头）。
# ⚠️ 判据是**整行只能由这些说明性词块和标点拼成**，且不含 `$`：
#    真题干「四、解答题：已知集合 A=…」里有数学，一条都不匹配，不会被误吃。
_SPEC_TAIL = re.compile(
    r"(?:本大题共\s*\d+\s*个?小题|本题共\s*\d+\s*个?小题|每小题\s*\d+\s*分"
    r"|共\s*\d+\s*分|满分\s*\d+\s*分"
    r"|在每小题给出的选项中|有多项符合题目要求|只有一项是符合题目要求的"
    r"|全部选对的得\s*\d+\s*分|部分选对的得\s*部分分|有选错的得\s*0?\s*分"
    r"|解答应写出必要的文字说明|证明过程或演算步骤"
    # 「解答应写出 / 解答时应写出 / 解答应该写出」这几种写法都出现过；
    # 后面跟「文字说明、证明过程或演算步骤」，单独拆成词块，免得整行匹配不上。
    r"|解答应(?:该|时)?写出|文字说明|证明过程|演算步骤"
    r"|请在答题卡指定区域内作答|考试总时间\s*\d+\s*分钟"
    r"|和|与|及|或"
    r"|[，,、；;：:\s.。（）()\[\]【】]|\d)+")
_JUNK_SECTION = re.compile(
    r"^\s*[一二三四五六七八九十]\s*[、.．。]\s*"
    r"(?:单项选择题|多项选择题|选择题|填空题|解答题|单选题)")
# 卷首说明里**绝不可能出现**的东西：数学式、下划线、行内代码。
# 实测 58 条"串进选项 D 的大题说明"里，`_SPEC_TAIL` 那张词表一条都没配上——
# 变体太多（「四个选项中」「有多项符合要求」「至少有两项符合题目要求」
# 「选对但不全的得部分分」「有错误的得 0 分」「请将答题卡上此题对应的上述选项的标号都涂黑」），
# 继续往词表里追加等于永远追不完。改成**反向判据**：节标题开头 + 后半截纯文字
# （不含 `$`、`\`、`=`、`^`、`_`、`{`）+ 不太长，就判卷首说明。
# 真题干「四、解答题：已知集合 $A=\{x|x^2<4\}$…」带数学式，一条都进不来。
_NO_MATH = re.compile(r"[\\=^_{}<>$\u2264\u2265]")


def _is_section_note(seg: str) -> bool:
    r"""整行是「节标题＋卷首说明」吗。节标题开头，后半截必须是纯说明文字。"""
    m = _JUNK_SECTION.match(seg or "")
    if not m:
        return False
    rest = seg[m.end():]
    if not rest.strip():
        return True                                   # 光杆节标题
    if len(rest) > 140 or _NO_MATH.search(rest):
        return False
    return True


def _is_ad_line(seg: str) -> bool:
    r"""整行是水印／署名／广告吗（群号、版权声明、资料库、★标语、扫描 App）。"""
    s = (seg or "").strip()
    if not s or "$" in s or len(s) > 44:
        return False
    if _AD_LINE_BLOCKER.search(s) or _HEAD_VETO.search(s):
        return False
    return bool(_WATERMARK.search(s))


# 带框卷眉「【××参考答案 第N页(共M页)】+ 条码」——实测 61 行，**全部**夹在推导中间：
# 前面是正文（常带 `$`），框后挂着「】」和一串书号条码（6060C／26-X-279C-1／X-G／W／B）。
# 这一档既不是"整行排版"（行里有正文），也剪不断（`_FOOT` 只吃页码本身，框和条码会留下），
# 所以单独摘除：只吃「【…第N页…】」和紧跟其后的条码，其余一个字不动。
_BRACKET_HEAD = re.compile(
    r"[【\[][^【】\[\]\n]{0,50}?第\s*\d{1,3}\s*页[^【】\[\]\n]{0,25}?[】\]]"
    r"(?:\s*[0-9A-Za-z][0-9A-Za-z\-\s·.]{0,12}[0-9A-Za-z])?")


def _cut_bracket_head(seg: str) -> str:
    r"""摘掉行中的「【卷名＋页码】（＋条码）」带框卷眉。"""
    out, pos = [], 0
    for m in _BRACKET_HEAD.finditer(seg or ""):
        g = m.group(0)
        if "$" in g or not _HEAD_MARK.search(g):
            continue                                   # 框里有公式或不像卷眉 → 不动
        out.append(seg[pos:m.start()])
        out.append("")
        pos = m.end()
    if not out:
        return seg
    out.append(seg[pos:])
    return "".join(out)



def _cut_footer(text: str) -> str:
    r"""删掉页眉页脚。返回新文本（没变就原样返回）。

    分三种情形，**都是从真实脏数据里量出来的**：

    1. 整行就是页脚（`第 3 页 共 8 页`）→ 整行删。
    2. 整行是「卷名 + 页脚」，且卷名前面没有句子 → 整行删
       （`2025年秋季学期高三年级12月质量检测数学试题 第 4 页 共 4 页`）。
    3. **正文和页脚挤在同一行** → 从卷眉关键词处剪，保住正文。
       实例：「所以红桃 A 的左侧没有数字牌高三数学 答案 第1页 共10页」
       —— 无脑删整行会把那句真题干掉，所以必须剪在「高三」处。

    换行两种写法都认：真换行和字面量 `\n`（`%% @q` 元数据里是双转义的）。
    """
    if not text or not _JUNK_HINT.search(text):
        return text
    lines = re.split(r"(\n|\\n)", text or "")     # 保留分隔符，拼回去不变形
    out: list[str] = []
    for seg in lines:
        if seg in ("\n", "\\n") or not seg:
            out.append(seg)
            continue
        cut = _cut_bracket_head(seg)
        if cut != seg:
            seg = cut
            if not seg.strip():
                continue                              # 整行就是「【卷名 第N页】条码」
        if _JUNK_LINE.match(seg.strip()):
            continue                                  # 整行就是排版噪声 → 丢掉
        if _is_section_note(seg.strip()):
            continue                                  # 「三、填空题：本题共3小题…」整行是卷首说明
        if _is_paper_head_line(seg.strip()):
            continue                                  # 「卷名 + 页码」整行是排版
        if _FOOT_FRAG.match(seg.strip()):
            continue                                  # 页码被换行劈开剩下的半截
        if _is_ad_line(seg.strip()):
            continue                                  # 群号／版权／资料库／★标语 整行是广告
        w = _WATERMARK.search(seg)                    # 水印只会贴在正文后面 → 从水印处剪断
        if w:
            seg = seg[:w.start()]
            if not seg.strip():
                continue
        out.append(_cut_footer_line(seg))
    text = "".join(out)
    # 删掉整行之后不许留下三个以上的空行（卷首块一行一行删，最容易攒出四五个）
    return re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", text)


def _cut_footer_line(line: str) -> str:
    # 页脚**连着抄了两遍以上**（多栏 PDF 把同一句页脚在每个栏位都印一次，实测
    # 「…第 4 页（共 6 页）第 4 页（共 6 页）第 4 页（共 6 页）…」）→ 整串摘掉。
    # 只有"重复"才敢这样删：单条页脚夹在正文中间可能是真在引用页码，见下面的保守分支。
    line = _FOOT_RUN.sub("", line)
    m = _FOOT.search(line)
    if not m:
        return line
    head, tail = line[:m.start()], line[m.end():]
    # 情形 2：**整行都是排版**（卷眉 + 页脚）。
    # 判据不是"关键词表命中"——那种写法遇到新卷名就漏：实测
    # 某些卷名（如「某省名校联盟2027届高三第一次学情诊断 数学试题卷」）里的「名/一/次」
    # 都不在词表里，整行删不掉，最后在题干里留下一整条卷眉。
    # 真正的区别是：**排版行里不会出现正文虚词**（的/是/则/求/若…），
    # 也不会出现公式。所以"没有句子标点 + 没有虚词 + 没有 $"就判为排版行。
    if not _TERM.search(head) and not _CONTENT_HINT.search(head) and "$" not in head:
        # ⚠️ 页脚**后面还挂着正文**的两种实测形状，绝不能整行删：
        #   「数学试题 第 2 页 (共 5 页)\fillin[综上所述，共有 $144+16+7=167$ 个]」
        #   「第2页，共4页\paren[D]」——删整行等于把作答位／答案一起删掉。
        return tail.strip()
    if tail.strip():
        # 页脚前后都是正文：宁可漏删不误删。带框卷眉
        # （「【××参考答案 第N页(共M页)】6060C」）走不到这里——那一种在
        # `_cut_bracket_head` 里已经摘干净了（实测这种形状 61 行，全是带框卷眉）。
        return line
    # 情形 3：正文在前、页脚在行尾 → 从最早的卷眉关键词处剪，保住正文
    cut = m.start()
    for p in range(len(head)):
        if _is_running_head(head[p:]):
            cut = p
            break
    return head[:cut]


@rule(name="去页眉页脚", scope=MIGRATE,
      why="台账 D02：页脚「第 N 页 共 M 页」和卷眉是印刷排版，不是题目内容。"
          "原来只挂在 ENTRY，所以**存量一道没清**——三轴机检在存量里数到 675 道"
          "题干/解析带卷面噪声，逐题审阅的 55 条待裁决里一大半也是它，故提级为 MIGRATE。"
          "顺带补上**选项**：机检抓到 `D.$c<a<b$ 浙江省 A9 协作体` 这种把卷眉吃进选项的。")
def strip_running_head(q: Question) -> bool:
    r"""题干、解析、**每个选项**一起去页眉页脚。"""
    changed = False
    for field in ("stem", "solution"):
        old = getattr(q, field) or ""
        new = _trim_edges(_cut_footer(old))
        if new != old:
            setattr(q, field, new)
            changed = True
    for o in q.options:
        new = _trim_edges(_cut_footer(o.text or ""))
        if new != (o.text or ""):
            o.text = new
            changed = True
    return changed


# ── 解析开头**重抄了一遍题干和选项** ──────────────────────────────
#
# 解析册里题目和解析排在一起，整页 OCR 下来就把「题干 + 四个选项 + 【答案】」
# 一起塞进了 `solution`。机检数到 156 道。卷面上就是**同一道题印两遍**；
# 更糟的是其中一批（如「2026届武汉九月调考#1」「（雅礼2次）#2」）除了重抄
# 一个字都没有——那道题其实**没有解析**，重抄把它伪装成了"解析齐全"。
#
# 判据必须做到"逐字对得上"才敢删：每一行要么等于题干，要么是「<标签>。＋该标签
# 选项的原文」，要么是光杆答案标记。对不上就**当场停**，后面的解析一个字不动。
# 所以「A。当 $a<0$ 时不成立，故 A 错误」这种**逐项分析**不会被吃——
# 它文字部分跟选项原文不一样。
_NORM_STRIP = re.compile(r"[\s$\\{}^_，。、；：:,.;!！?？（）()【】\[\]《》‘’“”—…]")
_ECHO_ANSWER = re.compile(
    r"^[【\[（(]?\s*(?:答案|故选|选|正确答案)\s*[】\]）)]?\s*[:：]?\s*[A-Da-d]{1,4}\s*[】\]）)]?。?$")
_ECHO_LABEL = re.compile(r"^\s*([A-D])\s*[。．.、]?\s*(.*)$", re.S)
_ECHO_STOP = re.compile(r"^[【\[]\s*(?:答案|参考答案|解析|试题解析|详解|名师解析|方法|考点)\s*】|"
                        r"^(?:故选|故选择|答案|选)\s*[:：]?", )


def _nrm(s: str) -> str:
    r"""比对用：**抹掉排版差异**，只留判定用的骨架。

    「题干＋选项」在答案册里重排过一遍，跟库里存的写法总有出入：
    `x^2` 对 `x^{2}`、`（p>0）` 对 `($p > 0$)`、`C 的方程为：$y=4x^2$` 对
    `$C$ 的方程为 $y=4x^{2}$`。原来只抹空白和 `$`，实测 90 多道的重抄因此一条都配不上。
    现在连**标点、花括号、`^`/`_`、`\left` 一类纯排版宏**一起抹掉。
    """
    s = _BRACKET_ARG.sub("", s or "")
    s = re.sub(r"\\(?:left|right|mathrm|mathit|mathbf|boldsymbol|mbox|text|operatorname)"
               r"(?![a-zA-Z])", "", s)
    return _NORM_STRIP.sub("", s)


_BRACKET_ARG = re.compile(r"\\(?:paren|fillin)\s*\[[^\]]*\]")


def _echo_line_kind(line: str, q: Question) -> str:
    r"""这一行是重抄的哪一类：`stem`／`opt`／`ans`，都不是就空串。"""
    s = line.strip()
    if not s:
        return ""
    n = _nrm(s)
    if not n:
        return ""
    stem = _nrm(q.stem)
    if stem and (n == stem or (len(n) >= 24 and stem.startswith(n) and len(n) >= 0.7 * len(stem))):
        return "stem"
    if _ECHO_ANSWER.match(s):
        return "ans"
    # 一行里可能连排四个选项（「A。x B。y C。z D。w」），也可能只有一个标签打头
    labs = [o.label for o in q.options if o.text]
    hit = 0
    for m in re.finditer(r"([A-D])\s*[。．.、]\s*([^A-D]{1,120})(?=\s*[A-D]\s*[。．.、]|$)", s):
        want = {o.label: _nrm(o.text) for o in q.options}.get(m.group(1), "")
        got = _nrm(m.group(2))
        # 前缀对得上**且长度差不多**才算原样重抄（差 8 字以内）
        if want and len(got) <= len(want) + 8 and got.startswith(want[:max(6, int(len(want) * 0.8))]):
            hit += 1
    if hit >= 2:
        return "opt"
    m = _ECHO_LABEL.match(s)
    if m and m.group(1) in labs:
        want = _nrm(next(o.text for o in q.options if o.label == m.group(1)))
        got = _nrm(m.group(2))
        if want and len(got) <= len(want) + 8 and got.startswith(want[:max(6, int(len(want) * 0.8))]):
            return "opt"
    return ""


@rule(name="去解析开头重抄的题干与选项", scope=MIGRATE,
      why="解析册整页录入时把「题干＋选项＋【答案】」一起抄进了 `solution`（机检 156 道）："
          "同一道题在卷面上印两遍，而且其中一批除了重抄什么都没有，"
          "把**没有解析**伪造成了**解析齐全**。逐字对得上题干／选项原文才删，对不上当场停。")
def strip_solution_echo(q: Question) -> bool:
    r"""删掉 `solution` 开头那段"重抄的题干＋选项＋答案标记"。"""
    if q.type not in ("single_choice", "multi_choice") or len(q.options) < 2:
        return False
    s = q.solution or ""
    if len(s) < 24:
        return False
    lines = s.split("\n")
    eat, kinds = 0, []
    for ln in lines[:16]:
        if not ln.strip():
            eat += 1                                   # 空行跟着一起吃（先记着，没坐实就回退）
            continue
        k = _echo_line_kind(ln, q)
        if not k:
            # 「【答案】/【解析】/故选」这类**分栏标记**证明前面那一段就是重抄：在这儿收口
            if _ECHO_STOP.match(ln.strip()) and "opt" in kinds:
                break
            break
        kinds.append(k)
        eat += 1
    else:
        eat = len(lines)
    if "opt" not in kinds or ("stem" not in kinds and len(kinds) < 2):
        return False
    # 只删到"坐实的最后一行"为止，后面挂的空行留着当分段
    while eat > 0 and not lines[eat - 1].strip():
        eat -= 1
    # ⚠️ **半截不吃**：选项列表没整块吃完就撤销。实测深圳中学#9 的四个选项排成五行，
    #   前三行跟库里原文对得上、第四行「D。已知事件 A，B 相互独立…」对不上，
    #   于是 A/B/C 被吃、D 留在解析开头——比原来更难看。
    #   判据只看形状：**紧接着一行还是以选项标签开头**就说明列表没吃完，整块不动。
    #   （⚠️ 别加长度上限：D 那行 60 字，按「短行才算选项」就漏了——实测就漏过。）
    # ⚠️ 要看**下一个非空行**：选项之间常夹空行，回退掉尾部空行后
    #    `lines[eat]` 正好是那个空行，直接判它就漏了（实测深圳中学#9 就这样溜过去）。
    nxt = next((l for l in lines[eat:] if l.strip()), "")
    if eat < len(lines) and re.match(r"^\s*[A-D]\s*[。．.、]", nxt):
        return False
    rest = "\n".join(lines[eat:]).strip()
    if rest == s.strip():
        return False
    # 吃完什么都没有 → 这道题**就是没有解析**。库里对此有唯一口径「解析无」
    # （`schema.NO_SOLUTION_MARKS`，待补/求解队列都按它筛），不要留空字符串。
    # 实测还有一种「只剩半截公式」：重抄之后剩下 `$\cdot 2$` —— 那不是解析，
    # 是推导被页码拦腰截断后的碎片，同样按「解析无」登记（别让它伪装成"有解析"）。
    if not rest or (len(rest) < 20 and not re.search(r"[\u4e00-\u9fff]", rest)):
        q.solution = "解析无"
    else:
        q.solution = rest
    return True


# ── 解析开头的**答案册卷首块** ──────────────────────────────────────
#
# 合一 PDF（试题＋答案册）逐页读下来，最后一道大题的解析前面常常挂着整张
# 答案册的封面：卷名、「数学参考答案及评分标准」、「绝密★启用前」、「注意事项」、
# 「题号 1 2 3 …／答案 A C B D …」对照表，甚至「命题、审题组教师 某某某」。
# 机检数到 33 道，形态都一样。这些一个字都不是解析。
#
# ⚠️ 只从**开头**连续吃，并且每行都要同时满足：不含 `$`、不长于 60 字、
# 命中卷首词表。碰见第一行真解析就停——所以不会往解析中间伸手。
_AK_MARK = re.compile(
    r"参考答案|试题答案|答案(?:及|与)(?:解析|评分|提示)|评分(?:标准|细则|意见|说明)"
    r"|细目表|注意事项|绝密|启用前|审题|命题人|资料库|祝大家|按参考答案给分|★")
# 答案册特有的**光杆行**：「（17分）」／「【试题解析】」这类栏目标记／「选择题参考答案」
_AK_PLAIN = re.compile(
    r"^[（(]\s*(?:本题|本小题)?(?:满分)?\s*\d{1,3}\s*分[）)]$"
    r"|^[【\[][^】\[\]\n]{2,16}[】\]]$"
    r"|^[一二三四五六七八九十]?、?[一二三四五六七八九十]?、?(?:单项选择|多项选择|选择|填空|解答)题(?:及)?(?:参考答案|答案)?$"
    # 光杆栏目名（答案册的分节标题）
    r"|^(?:选择题|填空题|解答题|单选题|多选题|题号|题序|答案|评分细则|试题|数学试题|数学)$")
# 对照表行：「题号 1 2 3 …」「答案 A C B D …」「1---8: CABCB BDC」
_AK_ROW = re.compile(
    r"^(?:题[号序]|答案)\s*[:：]?\s*(?:[0-9A-Za-z$\\{}（）()．.、，,;；\s/—–\-]|\s)+$"
    # 光杆数字行／光杆答案行（深圳中学那份把表头字丢在了上一行）
    r"|^\d{1,3}(?:\s+\d{1,3}){2,}$"
    r"|^(?:[A-D]{1,3}\s+){2,}[A-D]{1,3}$")
# 解析里的推导词——有这些就不是卷首块，绝不吃
# ⚠️ 别把单个「故」「则」列进来：「答案及评分细**则**」「命题与**故**事」这类卷首行
#    会被自己的否决表挡掉（实测 3 道「【答案及评分细则】（17分）」就这样漏网）。
#    真解析行几乎必然同时带「因为／所以／由／令」，用那些双字词足够。
_AK_VETO = re.compile(r"因为|所以|因此|可得|正确|错误|不成立|记为|设|证明|依题意|解[：:]|选[：:]")
# 强卷首词：只有这些才允许把行长放到 80（署名行／细目表行）
_AK_STRONG = re.compile(r"审题|命题人|细目表|注意事项|参考答案|资料库|评分(?:标准|细则|意见)")
# 卷名行（答案册封面第一行）：「昆明市第一中学 2026 届高三年级第五次联考」
# 「炎德·英才大联考雅礼中学 2026 届高三月考试卷(四)」。判据是"只由卷名成分拼成"：
# 没有 `$`、没有正文虚词、不以句子标点收尾、且必须同时出现**学校/联盟**和**考试**两类词。
# 「把另外 5 名教师记为其余教师。因为甲和乙不能同时去…」有「的/是」并以「。」收尾，进不来。
_PAPER_SCHOOL = re.compile(r"中学|学校|联盟|协作体|年级|高三|高二|高一|届|市|省|区")
_PAPER_EXAM = re.compile(
    r"联考|月考|质检|调研|诊断|检测|期中|期末|模拟|考试|测试|自测|摸底|适应性|学业水平|参考答案|试题|试卷")


def _is_paper_name_line(seg: str) -> bool:
    s = (seg or "").strip()
    if not s or "$" in s or len(s) > 45 or _HEAD_BLOCKER.search(s):
        return False
    if s[-1] in "。，；、,;":
        return False
    return bool(_PAPER_SCHOOL.search(s) and _PAPER_EXAM.search(s))


# 机构品牌前缀挂在解析**第一句前面**：「【锤子数学解析】$\because x…$」
_AK_BRAND = re.compile(r"^\s*【[^】\n]{2,14}解析】\s*")


# 「12. $\frac{2}{3}$ 13. $\frac{\pi}{8}$ 14. …」——填空题答案行**本来就带公式**，
# 只有"同一行里出现两个以上 `数字.` 序号"这一种形状才放行 `$`。解析行没有这个形状。
_AK_NUMBERED = re.compile(r"^(?:\d{1,2}\s*[.．]\s*\S+\s*){2,}")


def _is_answer_key_head(seg: str) -> bool:
    r"""这一行是不是答案册的卷首／对照表行（**保守判定**，宁可漏吃）。"""
    s = (seg or "").strip()
    if not s:
        return False
    if _AK_NUMBERED.match(s) and not _AK_VETO.search(s):
        return len(s) <= 90
    if "$" in s or s[-1] in "。，；、,;":           # 真句子才有的结尾
        return False
    # 「命题、审题组教师 杨昆华 刘皖明 …」这类署名行比一般卷首行长，命中强词就放宽
    limit = 80 if _AK_STRONG.search(s) else 40
    if len(s) > limit:
        return False
    if _AK_VETO.search(s):
        return False
    return bool(_AK_MARK.search(s) or _AK_ROW.match(s) or _AK_PLAIN.match(s)
                or _is_paper_name_line(s))


@rule(name="去解析开头的答案册卷首块", scope=MIGRATE,
      why="合一 PDF 把答案册封面（卷名／参考答案／绝密★启用前／注意事项／"
          "「题号 1 2 3…／答案 A C B D…」对照表／命题审题教师署名）整块挂进了"
          "最后一道大题的解析（机检 33 道）。另有「【××解析】」这类机构品牌前缀。")
def strip_answer_key_head(q: Question) -> bool:
    r"""删掉 `solution` 开头连续的答案册卷首行，和紧跟其后的机构品牌前缀。"""
    s = q.solution or ""
    if not s.strip() or len(s) < 8:
        return False
    lines = s.split("\n")
    eat, seen = 0, 0
    for ln in lines[:30]:
        if not ln.strip():
            eat += 1                                  # 空行不打断卷首块
            continue
        if not _is_answer_key_head(ln):
            break
        eat, seen = eat + 1, seen + 1
    if not seen:
        # 开头就是品牌前缀（「【锤子数学解析】$\because\dots$」）：摘掉前缀本身。
        mb = _AK_BRAND.match(s)
        if mb:
            q.solution = (s[mb.end():].strip() or "解析无")
            return True
        # 整块不在开头就在**结尾**：「题号 …」＋「答案 …」成对出现才算。
        for i in range(len(lines) - 1):
            a = (lines[i] or "").strip()
            if not re.match(r"^\s*题[号序]\s*[:：]?\s*\d", a):
                continue
            j, pair = i + 1, False
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and re.match(r"^\s*答案\s*[:：]?", lines[j].strip()):
                pair = True
            if not pair:
                continue
            k = j + 1
            while k < len(lines) and _is_answer_key_head(lines[k]):
                k += 1
            q.solution = "\n".join(lines[:i] + lines[k:]).strip()
            return True
        return False
    while eat > 0 and not lines[eat - 1].strip():
        eat -= 1                                      # 尾部空行留着当分段
    rest = "\n".join(lines[eat:])
    m = _AK_BRAND.match(rest)
    if m:
        rest = rest[m.end():]
    rest = rest.strip()
    q.solution = rest if rest else "解析无"
    return True


# ── 写法一致性：`$$…$$` 与重复标点 ─────────────────────────────────
# 答案册页脚：扫描件把「数学参考答案(雅礼版)-1」这类页脚印进解析**中间**。
# 实测 34 道 39 处，全部夹在推导两段之间（不是行首也不是行尾），所以「去页眉页脚」
# 那条（只看行首/行尾）抓不到。它的特征是固定的：书名前缀 + （某版）+ 连字符 + 数字。
_RE_BOOK_FOOTER = re.compile(
    r"数学参考答案[案]?\s*[（(][^）)]{0,20}[）)]\s*[-–—]\s*\d+")


@rule(name="去解析中间夹的答案册页脚", scope=MIGRATE,
      why="实测 34 道题的解析中间夹着「数学参考答案(雅礼版)-1」这类页脚"
          "（如「所以 $x_1,x_2<1$。\n\n数学参考答案案(一中版)-2\n\n定义:…」）。"
          "它既不是数学也不是人话，印到讲义上就是脏字；且「去页眉页脚」只认行首行尾，漏了这些。")
def strip_answer_book_footer(q: Question) -> bool:
    r"""删掉解析中间夹的「数学参考答案(某版)-N」。删完收一下多余空行。"""
    sol = q.solution or ""
    if not _RE_BOOK_FOOTER.search(sol):
        return False
    t = _RE_BOOK_FOOTER.sub("", sol)
    t = re.sub(r"[ \t]*\n{3,}", "\n\n", t)
    t = re.sub(r"\n[ \t]+\n", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    if t == sol:
        return False
    q.solution = t
    return True


# 录题时那道题的扫描图没读进来，worker 在解析开头留了一句「图未读入，依据题干推断」。
# 现在图就在库里（这 51 道全都有配图登记），这句话对学生是纯噪声，对我们也早已过期。
_RE_FIG_UNREAD = re.compile(
    r"（图未读入，依据题干(?:推断|求解)[。]?）|图未读入，依据题干(?:推断|求解)。")


@rule(name="补全来源标签截断的右括号", scope=MIGRATE,
      why="机检 21 道题（15 个不同写法）的 `meta.source_label` 停在「天津十二区毕业班联考（一」"
          "「海南学业水平诊断（四」这种半截上——答案册的卷名被按字符数截断了。"
          "这个字段直接印在讲义/卷面的**出处标签**上，缺右括号看着就是脏数据。"
          "只补一个 `）`，不改卷名本身；已经配平的不动。")
def close_source_label_paren(q: Question) -> bool:
    r"""`source_label` 里 `（` 比 `）` 多时，在末尾补上缺的右括号。"""
    lab = (q.meta or {}).get("source_label")
    if not isinstance(lab, str) or not lab.strip():
        return False
    miss = lab.count("（") - lab.count("）")
    if miss <= 0:
        return False
    q.meta["source_label"] = lab.rstrip() + "）" * miss
    return True


@rule(name="来源标签括号统一成全角", scope=MIGRATE,
      why="机检 36 道题的来源写成「陕西金太阳…联考(26-287C）」这种**一半半角一半全角**的括号，"
          "讲义的出处标签上就是两种宽度混排。只在**混用**时统一成全角；"
          "整体都用半角的（如 `强基(数学)`）不动——那是录入时的另一种一致体例，不是错。")
def unify_source_label_paren(q: Question) -> bool:
    lab = (q.meta or {}).get("source_label")
    if not isinstance(lab, str) or not lab:
        return False
    if not (("（" in lab or "）" in lab) and ("(" in lab or ")" in lab)):
        return False
    q.meta["source_label"] = lab.replace("(", "（").replace(")", "）")
    return True


_RE_PAGE_LABEL = re.compile(r"^\s*(\d{1,3})\s*$")


@rule(name="来源只剩扫描页号时补出书名", scope=MIGRATE,
      why="`*_images` 那几本书里 2,368 道题的 `meta.source_label` 就是一个页号（「197」「047」），"
          "因为录入时把扫描页当成了来源。这个字段会**原样印在讲义与卷面的出处标签上**，"
          "学生看到的就是一行「197」。改成「书名·第N页」：既保留了定位信息，又是个能读的来源。"
          "只碰纯数字的标签，其余一律不动。")
def expand_page_only_source_label(q: Question) -> bool:
    r"""`source_label` 是纯页号时，写成「书名·第N页」。"""
    md = q.meta or {}
    lab = md.get("source_label")
    if not isinstance(lab, str):
        return False
    m = _RE_PAGE_LABEL.match(lab)
    if not m:
        return False
    book = re.sub(r"_images\s*$", "", str(md.get("book") or q.key.split("/")[0])).strip()
    if not book:
        return False
    q.meta["source_label"] = "%s·第%s页" % (book, m.group(1))
    return True


@rule(name="去解析里的「图未读入」备注", scope=MIGRATE,
      why="机检 51 道题的解析开头或中间夹着「图未读入，依据题干推断」——那是录题时"
          "**图没进上下文**留下的工作备注，可这 51 道如今都有配图登记，备注早已过期。"
          "讲义上印出「图未读入」就是脏字。**只删这一句本身**：括号里带了内容"
          "（如「依据题干推断：展开图中的 $A$ 为圆锥顶点……」）的一律不动，"
          "那半句是解题依据，删了推导就断。")
def strip_figure_unread_note(q: Question) -> bool:
    r"""删掉纯噪声的「图未读入，依据题干推断」；带内容的括号不动。"""
    sol = q.solution or ""
    if "图未读入" not in sol:
        return False
    t = _RE_FIG_UNREAD.sub("", sol)
    if "图未读入" in t:
        return False          # 还有一句是带内容的读图说明，整题交人工
    t = re.sub(r"[ \t]*\n{3,}", "\n\n", t)
    t = re.sub(r"[ ]{2,}", " ", t).strip()
    if not t or t == sol:
        return False
    q.solution = t
    return True


@rule(name="去解析开头的栏目标记", scope=MIGRATE,
      why="答案册把「【解析】／【详解】／【试题解析】／【答案】」印在解析前面，整页读进来就成了"
          "解析正文的第一个词（机检 1242 道）。这些是**册子的栏目名**，不是讲解内容："
          "答案已经在 `answer` 字段和卷面作答位里，解析栏再印一遍就是重复，"
          "而且同一库里有的题带、有的题不带，导出后版式不齐。")
def strip_solution_tags(q: Question) -> bool:
    r"""删掉解析开头的栏目标记，和单独成行的「【答案】X」（仅当 X 就是答案栏那个值）。

    🔴 两条红线：
      · `【答案】X` **只有** X 与 `answer` 归一后相等才删——不相等时它是答案的
        唯一载体（台账里「作答位与答案栏同源」那一族坑就是这么来的），删了就丢答案；
      · 「【小问 1 详解】」这类**带编号的分段标题**不动：讲解正文靠它分段。
    """
    s = q.solution or ""
    if not s.strip():
        return False
    changed = False
    m = _LEAD_TAG.match(s)
    if m:
        tag, val = (m.group("tag") or "").strip(), (m.group("val") or "").strip()
        if tag.startswith("答案") and val:
            # 只有「跟答案栏一模一样」才连值一起删；不相等就一个字不动（那是答案的唯一载体）
            if _canon_tag(val) == _canon_tag(q.answer):
                s = s[:m.start()] + s[m.end():]
                changed = True
        else:
            # 纯栏目名：只删「【解析】」和紧跟的冒号/空格，后面一个字不动
            rest = s[m.end("tag") + 1:]                # 跳过「】」
            s = rest.lstrip(" \t:：")
            changed = True
    if changed:
        s = s.strip()
        # 「【解析】」整条解析就只有个栏目名 → 没有解析，按唯一口径写「解析无」
        q.solution = s if s else "解析无"
    # 单独成行的「【答案】X」夹在解析中间（实测一批湖北/江浙皖的题）
    ans = _canon_tag(q.answer)
    if ans:
        def _drop(m2: re.Match) -> str:
            return "" if _canon_tag(m2.group("val")) == ans else m2.group(0)
        s2 = _TAG_LINE.sub(_drop, q.solution or "")
        s2 = re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", s2)
        if s2 != (q.solution or ""):
            q.solution = s2.strip()
            changed = True
    return changed


_TAG_LINE = re.compile(r"(?m)^[ \t]*【\s*(?:答案|参考答案)\s*】\s*(?P<val>[^\n【】]{1,40}?)[ \t]*$")

# 解析开头的栏目标记：标签名 + 可选的「答案」值
_LEAD_TAG = re.compile(
    r"^[ \t]*【\s*(?P<tag>试题?解析|解析|详解|解答|分析|答案与解析|参考答案|答案|"
    r"考点|专题|点评|点睛|方法(?:总结|提炼|规律)?|一键|题后反思|错因分析)\s*】\s*"
    r"(?:[:：])?\s*(?P<val>[A-D]{1,4}|\$[^$]{1,24}\$)?[ \t]*")


def _canon_tag(s: str) -> str:
    r"""比对用：去掉空白、`$`、括号与中英标点，只留字母数字。"""
    return re.sub(r"[\s$\\{}（）()【】\[\]．.,，、;；:：]", "", s or "").upper()


@rule(name="双美元改行间", scope=MIGRATE,
      why="规范 §2.3 行间式写 `\\[ … \\]`，不用 `$$`。`$$` 走的是 plain-TeX 的老路，"
          "项目自己的块级 IR（`latex_blocks.scan_math`）只认 `\\[` 和 `$`——"
          "`conform` 把成对的 `$$` 记成风格提示不拦验收，所以存量一直留着（机检 10 道）。")
def double_dollar_to_display(q: Question) -> bool:
    r"""`$$ … $$` → 独立成行的 `/[ … /]`。"""
    changed = False
    pat = re.compile(r"\$\$([\s\S]+?)\$\$")
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        if "$$" not in t:
            continue

        def _repl(m):
            body = m.group(1).strip()
            return "\n\\[\n%s\n\\]\n" % body

        n = pat.sub(_repl, t)
        n = re.sub(r"\n{3,}", "\n\n", n)
        if n != t:
            setattr(q, f, n)
            changed = True
    return changed


@rule(name="重复标点归一", scope=MIGRATE,
      why="OCR 把行末标点和下一行行首标点叠在一起（实测 5 道「，，」）。"
          "规范 §3 的句末标点检查只管「半角点结尾」，看不见重复，"
          "于是卷面上印出「$c=\\sqrt{3}$，，求…」这样的双逗号。")
def collapse_double_punct(q: Question) -> bool:
    r"""把连着重复的中文标点收成一个（`，，`→`，`、`。。`→`。`）。"""
    pat = re.compile(r"([，。；、：])\s*\1+")
    changed = False
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        n = pat.sub(r"\1", t)
        if n != t:
            setattr(q, f, n)
            changed = True
    for o in q.options:
        n = pat.sub(r"\1", o.text or "")
        if n != (o.text or ""):
            o.text = n
            changed = True
    return changed





# 两头修剪：真空白和**字面量 `\n`**（`%% @q` 元数据里是双转义的，strip() 剪不掉）
_EDGE = re.compile(r"^(?:(?:\\n)|\s)+|(?:(?:\\n)|\s)+$")


def _trim_edges(s: str) -> str:
    return _EDGE.sub("", s or "")


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


# ── 题干开头的题型自述 ────────────────────────────────────────────────
#
# 模拟卷是一道一道独立出的，出题人只能把「（多选）」「（单选）」写在题首。
# 题型判对之后，这句自述就**多余**了：题型在 `type` 里，卷面分栏、界面标签、
# 组卷、导出全从 `type` 取，一个字段说了算。留在题干里的后果是它**跟着题干
# 一起印出去**——导出/讲义/搜索摘要里都是「（多选）已知……」，OCR 味。
# 2026-11-01 全库机检：`（多选）`/`(多选)` 328 道 + `（单选）` 5 道，横跨 8 本
# 模拟卷/千题册（都是逐题独立录入的，没有卷首「多选题」那一栏可依）。
#
# ⚠️ **只在自述与题型一致时才删**。题干这句是上一条 `fix_multi_choice_type`
#    的**唯一判据**，还判不准的题（选项不足 4 个等）把那句删了，以后就没法改判；
#    自述与 `type` 打架的（写「（单选）」却标成多选）删掉更是把线索灭了。
#    所以：① 规则顺序必须是「先改判、后删自述」；② 对不上的一律不动。
_TYPE_HEAD_MARK = re.compile(
    r"""^[\s\u3000]*[（(]\s*(多选|多项选择题|多选题|多项选择|"""
    r"""单项选择题|单项选择|单选题|单选)\s*[）)][\s\u3000]*""")
_TYPE_HEAD_OF_WORD = {
    "多选": "multi_choice", "多项选择": "multi_choice",
    "多选题": "multi_choice", "多项选择题": "multi_choice",
    "单选": "single_choice", "单项选择": "single_choice",
    "单选题": "single_choice", "单项选择题": "single_choice",
}


@rule(name="去题干开头的题型自述", scope=ENTRY,
      why="规范 §2.9：题干不写题型自述——题型由 `type` 表达，题首再顶一句"
          "「（多选）」/「（单选）」是重复标注，而且会跟着题干原样印进导出与"
          "讲义（全库 333 道）")
def strip_type_head(q: Question) -> bool:
    r"""题干开头写着「（多选）已知…」的 → 删掉那句自述。

    只删**题首**那一个，且必须与 `type` 对得上；正文里顺口提到「多项选择题」
    的（讲多选题评分规则的那类）一个字不动——那不是标记，是题目内容。
    """
    m = _TYPE_HEAD_MARK.match(q.stem or "")
    if not m or _TYPE_HEAD_OF_WORD.get(m.group(1)) != q.type:
        return False
    new = (q.stem or "")[m.end():]
    if not new.strip():
        return False
    q.stem = new
    return True


@rule(name="去题干开头的题型自述（存量）", scope=MIGRATE,
      why="上面那条是 ENTRY 规则，只管新录入的，存量一道都没改过；"
          "2026-11-01 全库机检 333 道（`（多选）`/`(多选)` 328 + `（单选）` 5），"
          "导出与讲义里一直是「（多选）已知……」")
def strip_type_head_existing(q: Question) -> bool:
    return strip_type_head(q)


# ── 缺图题去掉「如图」指代 ────────────────────────────────────────────
#
# 2026-11-04 用户要求：题干写了「如图」但 `figures` 为空的题，把「如图」删掉。
# 这些题本来就没有图，留着「如图」等于给读者一个不存在的参照；删掉后至少
# 文字自洽。**只删指代，不代表图已经有**——同时打 `meta.figure_missing`，
# 补图清单还能从元数据重建。
#
# 只处理**没有图**的题：有 `figures`、题干里还有 `\includegraphics` 或
# `tikzpicture` 的一律不碰，避免把真有图的题误伤。
_FIG_REF_RE = [
    # 括注里的图参照整个括号删掉，避免留下空括号「（）」
    (re.compile(r"[（(]\s*如图[^）)]{0,30}[)）]"), ""),
    # 残留的「（图 2）」：图已经被删掉，这个括注只会让人找一张不存在的图
    (re.compile(r"[（(]\s*图\s*\d+(?:\s*[-–—]\s*\d+)?\s*[)）]"), ""),
    (re.compile(r"如图\s*【缺[^】]*】"), ""),
    (re.compile(r"如图\s*\d+\s*[、和及]\s*图\s*\d+\s*所示(?:的)?"), ""),
    (re.compile(r"如图(?:\s*\d+(?:\s*[-–—]\s*\d+)?)?\s*所示(?:是|为)"), ""),
    (re.compile(r"如图(?:\s*\d+(?:\s*[-–—]\s*\d+)?)?\s*所示(?:的)?"), ""),
    (re.compile(r"如图(?:\s*\d+(?:\s*[-–—]\s*\d+)?)?\s*(?:是|为)"), ""),
    (re.compile(r"如图(?:\s*\d+(?:\s*[-–—]\s*\d+)?)?\s*中"), ""),
    (re.compile(r"如图(?:\s*\d+(?:\s*[-–—]\s*\d+)?)?\s*的?"), ""),
]


def _strip_figure_phrase(stem: str) -> str:
    s = stem
    for pat, repl in _FIG_REF_RE:
        s = pat.sub(repl, s)
    s = re.sub(r"^[\s，,。、；;：:]+", "", s)
    s = re.sub(r"([，,。；;])\s*\1+", r"\1", s)
    s = re.sub(r"[，,]\s*([。；;])", r"\1", s)
    s = re.sub(r"([。；;])\s*[，,]", r"\1", s)
    s = re.sub(r"[，,]\s*[.．]\s*$", "。", s)
    s = re.sub(r"[，,]\s*[.．]", "，", s)
    s = re.sub(r"[，,]\s*$", "。", s)
    return s.strip()


@rule(name="缺图题去掉「如图」指代", scope=MIGRATE,
      why="2026-11-04 用户要求：题干写「如图」但 figures 为空的题，删掉图形指代；"
          "同时打 meta.figure_missing，补图清单仍可从元数据重建。"
          "有图/TikZ/includegraphics 的题不碰。")
def strip_figure_phrase_without_figure(q: Question) -> bool:
    stem = q.stem or ""
    if q.figures or "\\includegraphics" in stem or "\\begin{tikzpicture}" in stem:
        return False
    if "如图" not in stem:
        return False
    new = _strip_figure_phrase(stem)
    if not new or new == stem:
        return False
    q.stem = new
    q.meta["figure_missing"] = True
    q.meta["figure_ref_removed"] = True
    return True


# ── 题干末尾的出处 ────────────────────────────────────────────────────
#
# 千题册那几本书在 OCR 时把「出处」留在了题干末尾：
#
#     则使得 $\sin a_1\cdots\sin a_k<\frac{1}{10}$ 成立的最小正整数 $k$ 为 \fillin{}。
#
#     某校 2025 届二模                ← 这是出处，不是题目
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
    # ⚠️ **已有 `source_label` 不许覆盖**。这规则的本意是"题干里那行出处挪进 meta"，
    # 但 meta 里往往早就有一个**又长又准**的来源名（key 的第一段就是它）。
    # 无条件覆盖会把「宁夏回族自治区银川一中2026-2027学年高三上学期第一次月考」
    # 换成从题干尾巴上剥下来的一截页眉「高三第一次月考 数」——出处反而被写坏。
    # 实测 3 道全中招，故只在 meta 里**空着**时才填。
    if not str((q.meta or {}).get("source_label") or "").strip():
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
#
# 第二个分支管「句点后面紧跟汉字」——原前瞻 `(?=\s|$)` 看不见这种，
# 热区复核（H24）就是撞上的：`…不成立.因此…` 会原样印给学生。
# 全库这种有 2,236 处，其中 1,609 处是「数学式收尾 `$` + 句点 + 汉字」
# （`…概率为 $\frac{1}{2}$.若第一局…`），老真题 OCR 出来的句读几乎全这样。
# ⚠️ 这一支**必须限定前一个字符**：只看「后面是汉字」会连
# `A.第一象限`、`B.第二象限` 这种**字母编号的选项列表**一起改掉
# （不限定前缀是 2,267 处，限定了才是 2,236 处，差的那 31 处全是误伤：
# `10\%.测试`、`….若`、`\perp BD$ .由`、`A.第一象限`）。
# 所以只认「汉字／数学式收尾 `$`／闭括号后面紧跟的句点」这一类。
_SENT_DOT = re.compile(
    r"(?<![\d.])\.(?=\s|$)"
    r"|(?<=[一-鿿$()）】」』”])\.(?=[一-鿿])")


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


@rule(name="句末半角句点改中文句号（存量）", scope=MIGRATE,
      why="上面那条是 ENTRY 规则，只管新录入的，**存量一道都没改过**；而它的前瞻"
          "`(?=\\s|$)` 还看不见「句点后面紧跟汉字」这一种（`…不成立.因此…`、"
          "`…概率为 $\\frac{1}{2}$.若…`）。2026-11-01 热区复核 H24 抓到后全库机检："
          "这种会**原样印给学生**，共 2,234 处（数学模式内的 2,518 处照旧不动）。"
          "实现复用 `sentence_period`，不另写一份——两处各写一遍必然分叉。")
def sentence_period_existing(q: Question) -> bool:
    return sentence_period(q)


# ①—⑩（U+2460 起）
@rule(name="术语订正：焦半距改回半焦距", scope=MIGRATE,
      why="热区复核（H33）抓到：188 道题的题干/解析里写「焦半距 $c=\\sqrt{a^2-b^2}$」，"
          "规范术语是**半焦距**（长半轴、短半轴、半焦距），词序被录入时写反了。"
          "其中 11 道已被组进过卷子——印出去就是教错名词。纯词序替换，不动任何式子。")
def fix_half_focal_term(q: Question) -> bool:
    changed = False
    for fld in ("stem", "answer", "solution"):
        old = getattr(q, fld) or ""
        if "焦半距" in old:
            setattr(q, fld, old.replace("焦半距", "半焦距"))
            changed = True
    for o in (q.options or []):
        if "焦半距" in (o.text or ""):
            o.text = o.text.replace("焦半距", "半焦距")
            changed = True
    return changed


CIRCLED = "".join(chr(c) for c in range(0x2460, 0x2460 + 10))
_CIRCLED_RE = re.compile("[" + CIRCLED + "]")
_ENUM_BLOCK = re.compile(r"\\begin\{enumerate\}[ \t]*\n?(.*?)\n?[ \t]*\\end\{enumerate\}",
                         re.S)


@rule(name="题干编号与答案编号对齐（enumerate → ①②③）", scope=MIGRATE,
      why="热区复核（H23）抓到一类**学生根本没法作答**的题：题干把四个命题写成 "
          "`\\begin{enumerate}\\item …`，两条渲染路径（`web/src/lib/qlatex.ts`、"
          "出卷的 exam-zh）都印成 **（1）（2）（3）（4）**，"
          "可答案栏写的是 `$②③④$`、解析说「命题①不正确」——卷面上不存在 ①②③ 这套编号。"
          "原卷（北京卷/全国卷这类多选题）印的就是 ①②③，是录入时把圈号换成了 enumerate。"
          "只对「**答案里出现圈号**且**题干（去掉作答位）没有圈号**」的题动手，"
          "把 enumerate 换成 ①②③ 逐行；小问用的（1）（2）不受影响。")
def align_enumerate_labels(q: Question) -> bool:
    st = q.stem or ""
    if "\\begin{enumerate}" not in st:
        return False
    if not _CIRCLED_RE.search(q.answer or ""):
        return False
    # 作答位里回显的答案带圈号不算「题干已有编号」
    body_wo_slot = re.sub(r"\\(?:paren|fillin)\s*\[(?:[^\[\]]|\[[^\]]*\])*\]", "", st)
    if _CIRCLED_RE.search(body_wo_slot):
        return False
    m = _ENUM_BLOCK.search(st)
    if not m:
        return False
    inner = m.group(1)
    if "\\item[" in inner:                       # 带自定义标号的 enumerate 不动
        return False
    parts = inner.split("\\item")
    n = len(parts) - 1
    if n < 2 or n > len(CIRCLED):
        return False
    new_inner = "".join(CIRCLED[i] + " " + parts[i + 1].lstrip() for i in range(n))
    q.stem = st[:m.start()] + new_inner.strip() + st[m.end():]
    return True


# 被 OCR 吃掉命令头的直方图纵轴标题：只剩一个无主的 `{$\frac{\text{频率}}{\text{组距}}$};`
_TIKZ_FREQ_ORPHAN = re.compile(
    r"^\s*;\s*\n^\s*\{\$\\frac\{\\text\{频率\}\}\{\\text\{组距\}\}\$\}\s*;\s*$",
    re.M)
_TIKZ_FREQ_ORPHAN_SOLO = re.compile(
    r"^\s*\{\$\\frac\{\\text\{频率\}\}\{\\text\{组距\}\}\$\}\s*;\s*$", re.M)
_TIKZ_AXIS_OPT = re.compile(r"\\begin\{axis\}\[(.*?)\]", re.S)


def _tikz_axis_top(text: str, pos: int) -> tuple[str, str] | None:
    r"""往上找最近的 `\begin{axis}[…]`，取出它的第一象限角 `(xmin, ymax)`。

    坐标只从**图自己写的** `xmin/xmax/ymin/ymax` 里读——不猜。读不到就返回 None，
    这条规则对那张图就不动。
    """
    ms = list(_TIKZ_AXIS_OPT.finditer(text, 0, pos))
    if not ms:
        return None
    opt = ms[-1].group(1)

    def g(k):
        m = re.search(k + r"\s*=\s*([-+0-9.eE]+)", opt)
        return m.group(1) if m else None
    x, y = g("xmin"), g("ymax")
    return (x, y) if x and y else None


@rule(name="补回被 OCR 吃掉的直方图纵轴标题", scope=MIGRATE,
      why="频率分布直方图的纵轴标题「频率/组距」在录入时被 OCR 吃掉了命令头，"
          "源码里只剩一个无主的 `{$\\frac{\\text{频率}}{\\text{组距}}$};`"
          "（前面还常跟一行秃 `;`）。全库 32 张图这样，**卷面上就是纵轴没有单位**，"
          "学生分不清轴上印的是频率还是频率/组距。"
          "位置从图自己写的 `xmin/ymax` 推（轴顶左侧），不猜别的数据。"
          "2026-11-01 热区复核（H19–H24）期间逐张渲染目视核对过。")
def restore_hist_yscale_label(q: Question) -> bool:
    r"""把无主片段换成 `\node[anchor=south east] at (axis cs:xmin,ymax) {…}`。"""
    changed = False

    def fix(text: str) -> str:
        out = text
        for pat in (_TIKZ_FREQ_ORPHAN, _TIKZ_FREQ_ORPHAN_SOLO):
            def sub(m):
                xy = _tikz_axis_top(out, m.start())
                if not xy:
                    return m.group(0)
                return (r"\node[anchor=south east, inner sep=1pt]"
                        r" at (axis cs:%s,%s) {$\frac{\text{频率}}{\text{组距}}$};" % xy)
            out = pat.sub(sub, out)
        return out

    for fld in ("stem", "solution"):
        old = getattr(q, fld) or ""
        new = fix(old)
        if new != old:
            setattr(q, fld, new)
            changed = True
    from . import latex_ir            # 局部 import：避开模块加载期的环
    for f in (q.figures or []):
        if getattr(f, "kind", "") == "tikz" and f.tikz:
            new = fix(f.tikz)
            if new != f.tikz:
                f.tikz = new
                f.id = latex_ir.tikz_id(new)     # 身份跟着源码走
                changed = True
    return changed


_SLOT_ANS = re.compile(r"\\(?:paren|fillin)\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]")
_SLOT_CMD = re.compile(r"\\(?:paren|fillin)(?![a-zA-Z])")


def iter_slots(text: str, cmd: re.Pattern = _SLOT_CMD):
    r"""按 **TeX 可选参数的规矩**数括号，读出 `\fillin[…]`／`\paren[…]` 的槽位。

    返回 `[(命令起点, `[` 的下标, 参数内容, 右括号之后的下标)]`；
    **括号配不平就返回 None**——读不准就一处都不改，别猜。

    ⚠️ 为什么不用正则：`_SLOT_ANS` 那类 `(?:[^\[\]]|\[[^\]]*\])*` 只认一层方括号、
    **不认 `{…}` 分组**，于是 `\fillin[{$(2,3]$}]`（答案里带右闭区间）会从中间被截断，
    截断点后面的 `}$}]` 掉回正文——实测端到端渲染那处 KaTeX 报错就是这么来的
    （`数学段只剩闭合符` 那族残形）。本模块只有 `scan_bracket` 懂 TeX，
    槽位也必须由它读。
    """
    out = []
    for m in cmd.finditer(text):
        i = text.find("[", m.end())
        if i < 0 or i - m.end() > 4:
            continue
        arg, end, ok = scan_bracket(text, i)
        if not ok:
            return None
        out.append((m.start(), i, arg, end))
    return out


def _slot_period(stem: str) -> bool:
    r"""把 `\fillin[…X.]` 里末尾那个 `.` 改成 `。`。返回新串（没改就返回假值）。"""
    if not stem or "." not in stem:
        return False
    slots = iter_slots(stem)
    if not slots:
        return False
    out, pos, changed = [], 0, False
    for start, bracket, arg, end in slots:
        body = arg[:-1] + "。" if arg.endswith(".") else arg
        changed = changed or body != arg
        out.append(stem[pos:bracket] + "[" + body + "]")
        pos = end
    out.append(stem[pos:])
    return "".join(out) if changed else False


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


# 解析开头的「答案：C」／「【答案】C」——**讲义、教案、别的题库最常见的写法**：
# 答案不写在作答位里，而是抄在解析第一行。本库的答案只有两个去处：字段 + 卷面
# 作答位（`\paren[…]`／`\fillin[…]`）。留在解析里，导出就跟着再印一遍。
_LEAD_ANSWER = re.compile(
    r"^[ \t]*(?:【\s*答案\s*】|答案\s*[:：])[ \t]*(?P<val>[^\n]*?)[ \t]*(?:\n|$)")
_ANSWER_TAIL_PUNCT = "。．.，,；;：: \t"


@rule(name="解析开头的答案搬进答案栏", scope=ENTRY,
      why="讲义／教案／别的题库把答案抄在解析第一行（「答案：C」），而本库的答案"
          "必须进 `answer` 字段与卷面作答位（`\\paren[…]`／`\\fillin[…]`）："
          "只留在解析里，卷面上没有作答括号，导出还会把答案印两遍。")
def answer_from_solution_head(q: Question) -> bool:
    r"""解析第一行的「答案：X」→ 答案栏，并把这一行从解析里删掉。

    🔴 四条守卫，缺一条都会把错答案写进库：

      · **只认解析开头**（第一行）。解析中间出现的「答案：」是在讲某一步，
        不是这道题的答案；
      · **只搬选择与填空**。解答题的答案栏按规范是「见解析」，解析开头的
        `\textbf{答案：}…` 是**讲解内容**（规范 §2.2 允许），不能搬走；
        只有「答案：见解析」这种**没有信息量**的一行才顺手删掉（导出会在
        解析前面自己印一遍 `\textbf{答案：}见解析`，留着就是印两遍）；
      · 选择题的值必须是**选项里真有的字母**（`A`–`D`，多选连写）。
        对不上就不认——宁可缺答案，也不给错答案；
      · 答案栏**已经有值**时，只删「跟它一模一样」的回声。值不一样＝两处
        打架，留着一字不动（那是改判的唯一线索，和 `条目标记` 同一口径）。
    """
    if q.type not in _CHOICE + ("fill_in_blank", "detailed_answer"):
        return False
    s = (q.solution or "").lstrip()
    m = _LEAD_ANSWER.match(s)
    if not m:
        return False
    val = m.group("val").strip().strip(_ANSWER_TAIL_PUNCT)
    if not val:
        return False
    if q.type == "detailed_answer":
        # 解答题的答案是「见解析」——这一行不承载信息，删掉；导出自己会印。
        # 写了具体结论的（`答案：$a=1$`）是讲解的一部分，**不搬也不删**。
        if _canon_tag(val) not in ("见解析", "答案见解析", "略", "无"):
            return False
        q.solution = s[m.end():].lstrip("\n \t")
        return True
    old = (q.answer or "").strip()
    if old:
        if _canon_tag(val) != _canon_tag(old):
            return False                 # 两处答案打架：不猜，留给人工
    elif q.type in _CHOICE:
        val = val.upper()
        if not re.fullmatch(r"[A-D]{1,4}", val):
            return False
        if not set(val) <= {o.label.upper() for o in q.options}:
            return False
    if not old:
        q.answer = val
    q.solution = s[m.end():].lstrip("\n \t")
    return True


@rule(name="去解析开头的栏目标记（录入）", scope=ENTRY,
      why="讲义／教案的解析开头常挂「【详解】」「【解析】」栏目名。那是册子的排版，"
          "不是讲解；录进来不删就跟着导出印（和 MIGRATE 那条同一份实现，"
          "分开注册是为了让存量与新录入各走各的档）。")
def strip_solution_tags_entry(q: Question) -> bool:
    return strip_solution_tags(q)


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

    还有一种**反过来**的写法（VLM 转录讲义时很常见）：

        ……则函数 $y=f(x)$ 的图象可能为（ \paren[] ）

    作答位被**原来那个空括号包在里面**了。这时不能删括号（它是题干的一部分），
    要**把作答位掏出来**：`……可能为 \paren[]`。不掏出来就还是印两个括号，
    而且 `_ANY_PAREN` 也匹配不到它（括号里不是空的），整条规则白跑。
    """
    s = q.stem or ""
    if not re.search(r"\\(paren|fillin)\s*(\[[^\]]*\])?", s):
        return False
    # ① 作答位被空括号包着 → 掏出来（先做，否则下面 `_ANY_PAREN` 认不出）
    out = re.sub(r"[（(]\s*(\\paren\s*\[[^\]]*\]|\\fillin\s*\[[^\]]*\])\s*[）)]",
                 r"\1", s)
    # ② 空括号**自己带着一对 `$…$`** 时，要连那对 `$` 一起删。
    # 只删括号会留下 `$$`：
    #     函数 $f(x)=…$ 的最小正周期为 $(\quad)$ \paren[]
    #   → 函数 $f(x)=…$ 的最小正周期为 $$ \paren[]
    # `$$` 是规范明令不许的、LaTeX 直接报「Display math should end with $$」，
    # 而 `chk_delim` **查不出来**（`$` 还是偶数个，配对"通过"）。
    # 实测：赵礼显讲义 p073 第 17 题就是这么坏掉的，全库两道检查都没报。
    out = re.sub(r"\$\s*[（(]\s*(?:\$?\s*(?:\\quad|\\qquad)?\s*\$?)\s*[）)]\s*\$",
                 "", out)
    # ③ 残留的**真正空**括号 → 删掉
    hits = list(_ANY_PAREN.finditer(out))
    for m in reversed(hits):
        out = out[:m.start()] + out[m.end():]
    out = re.sub(r"\$\$", r"\$", out)         # 兜底：删完不该再有相邻 `$`
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


# 卷面上的"空位"有好几种写法：`_____`、`\underline{\Delta}`、`\triangle`、
# `▲`。它们都得归成 `\fillin[]`——规范 §2.2 只认这一种。
_BLANK_ANY = re.compile(
    r"_{2,}|\\underline\s*\{[^{}]*\}|\\blacktriangle\s*|\\triangle\s*$")


@rule(name="补填空位", scope=ENTRY,
      why="规范 §2.2 填空：填空题必须有 `\\fillin` 空位。这是"
          "「补作答题括号」（选择题那边）的对称件——"
          "少它就会出现「填空题一个空位都没有」")
def ensure_fillin(q: Question) -> bool:
    r"""填空题没有空位就补一个（有答案才补，免得造出"永远填不上"的空位）。

    空位补在**句末标点之前**（卷面本来就是「……为____。」这个样子），
    没有句末标点就缀在末尾。已经归好的 `\fillin[]` 不再动。

    ⚠️ **三道守卫的顺序不能乱**——乱了两次，各改坏几千道，都是真事故：

    1. **题型必须先是填空题**。少了它，规则会对选择题/解答题也补空位
       （一次改坏 7519 道）。
    2. **自愈段**：空位已经在、但落在数学模式里 → 挪出来。这一步**不需要答案**，
       所以必须排在"没答案就返回"之前，否则这种既有毛病永远修不掉。
    3. **已经有 `\\fillin` 就不动**（包括**填好的** `\\fillin[$x$]`）。
       少了它，带答案的正常填空题会被追加第二个空位（一次改坏 3957 道）。
    """
    # 守卫 1：不是填空题，一律不管
    if q.type != "fill_in_blank":
        return False
    # 守卫 2（自愈）：空位已有但落在数学模式里（`则 $\mu =\fillin[]$。`）。
    # 这是本规则早先的产物（替换 `\underline{\Delta}` 时没把数学模式收尾），
    # 留着不管就会一直是嵌套 `$`。规则要能把自己改坏的地方修回来。
    m0 = re.search(r"\\fillin\s*\[\s*\]", q.stem)
    if m0:
        before = q.stem[:m0.start()]
        if before.count("$") % 2 == 1:                     # 在数学模式里 → 挪出来
            # ⚠️ **公式里有环境或 `\left…\right` 时不能就地切。**
            # 就地补一个 `$ ` 会把这个公式从中间截断：`\begin{cases}` 和
            # `\end{cases}` 落到两段公式里，直接坏掉。实测：
            #     `$a_n=\begin{cases} n, & \fillin[] \\ 1, & x>0 \end{cases}$`
            #   → `$a_n=\begin{cases} n, & $ \fillin[] \\ 1, & x>0 \end{cases}$`
            # `$` 个数还是偶数、`\begin/\end` 也都在，**两道检查都不会报**，
            # 但 `\end{cases}` 已经掉到数学模式外面了。
            # 这种情况交给 `填空位移出数学模式`（它有那条"有环境就不切、
            # 只把答案自带的 `$` 脱掉"的守卫），别在这里抢着做。
            if re.search(r"\\begin\{|\\left|\\right", before):
                return False
            raw_after = q.stem[m0.end():]
            # ⚠️ **空位必须是这一段公式的最后一样东西**，否则不能在这里切。
            # 公式里还有别的空位时切一刀，后半段就掉到数学模式外面：
            #     `$BD = \fillin[], \cos\angle ABD = \fillin[]$`
            #   → `$BD = $ \fillin[], \cos\angle ABD = \fillin[]$`
            # `$` 剩奇数个、整道题坏掉。这种交给 `填空位移出数学模式`，
            # 它**按整段公式重写**、在每个命令处切开，是对的。
            # 判断必须在下面"吃掉收尾 `$`"**之前**做——吃掉以后就看不出
            # 空位后面还有没有内容了。
            if raw_after.strip() and not raw_after.lstrip().startswith("$"):
                return False
            after = raw_after
            if after.startswith("$"):
                after = after[1:]
            # ⚠️ 两种"在数学模式里"要分开处理，混作一种会印出 `$$`：
            #   ① `则 $b=\fillin[]$。` —— 空位挂在**原来那个**公式的尾巴上，
            #      得就地给公式收尾：`则 $b=$ \fillin[]。`
            #   ② `…的值为 $\fillin[]$。` —— 空位被**单独**包了一对 `$…$`
            #      （VLM 转录最爱这么写）。这时 `before` 的末尾那个 `$`
            #      就是开这对的，再补一个 `$ ` 会得到 `$$`——KaTeX 直接报错，
            #      而且 `$$` 本身也是规范明令不许的。正确做法是**删掉这对**。
            if before.rstrip().endswith("$"):
                before = before.rstrip()[:-1].rstrip() + " "
            else:
                before = before + "$ "
            q.stem = before + r"\fillin[]" + after
            return True
        return False
    # **没答案就别补新空位**（补了也永远填不上）。注意这段必须排在
    # 自愈段**之后**——把数学模式里的旧空位挪出来不需要答案，
    # 排在前面会把「空位在数学模式里」这种既有毛病永远修不掉（真踩过）。
    if not q.answer.strip():
        return False
    # ⚠️ **这条守卫不能少**：只要题干里已经有 `\fillin`（哪怕是**填好的**
    # `\fillin[$x$]`），就不该再动它。
    # 我把这行连同上一段一起替换掉过一次 —— 结果带答案的正常填空题
    # 也被追加了一个空位，**一次改坏 3957 道**，规范审查从 2 处涨到 3972 处。
    # 教训：「已经填好的空位」必须有一条独立用例，不能只测「空位在外面」。
    if _FILLIN_CMD.search(q.stem):
        return False
    # ② 卷面上本来就有「下划线式」空位，把它换成 \fillin[]
    m = None
    for m in _BLANK_ANY.finditer(q.stem):
        pass                                  # 取**最后一个**空位
    if m:
        before = q.stem[:m.start()]
        after = q.stem[m.end():]
        # ⚠️ **空位可能落在数学模式里**（`则 $\mu =\underline{\Delta}$。`）。
        # 直接替换会得到 `则 $\mu =\fillin[]$。`——`\fillin` 在 `$…$` 里面，
        # 渲染时是嵌套数学模式（conform 报「空位在数学模式里」）。
        # 正确做法是**就地把数学模式收尾**：`则 $\mu =$ \fillin[]。`
        if before.count("$") % 2 == 1:                    # 当前位置在数学模式内
            if after.startswith("$"):
                after = after[1:]
            q.stem = before + "$ " + r"\fillin[]" + after
        else:
            q.stem = before + r"\fillin[]" + after
        return True
    # ② 空位被 OCR 弄丢了：补在句号之前
    end = re.search(r"[。．.]\s*$", q.stem)
    if end:
        q.stem = q.stem[:end.start()].rstrip() + r" \fillin[]" + q.stem[end.start():]
    else:
        q.stem = q.stem.rstrip() + r" \fillin[]"
    return True


@rule(name="解答题答案栏写「见解析」", scope=ENTRY,
      why="规范 §2.2：解答题的答案就是解析本身。答案栏空着，界面会显示「（暂时没有答案）」、"
          "导出也没有答案可印——用户要求统一写「见解析」，保证每道题都有答案")
def answer_for_detailed(q: Question) -> bool:
    r"""解答题答案栏空着 → 填「见解析」。**只填空的**，已经有答案的（旧数据里有写了结果的）不动。

    解答题没有作答位可内联（题干既无 `\paren` 也无 `\fillin`），`render_tex` 会把它
    写成解析开头的 `\textbf{答案：见解析}`，所以**往返可逆**（`roundtrip_problems` 可验）。
    """
    if q.type != "detailed_answer":
        return False
    if (q.answer or "").strip():
        return False
    q.answer = "见解析"
    return True


# 落单的 `$$`：不是行间公式（没有配对的收尾），却会**开一个数学模式**
# 把后面整段正文吞进去。实测（济南一模那道）：
#
#     …则椭圆 $\Gamma$ 的离心率为 $$ \fillin[$\frac{\sqrt{3}}{2}$]。
#
# xelatex 报 `Command \end{question} invalid in math mode`、**整份卷子出不来 PDF**；
# 而网页预览只是句号位置怪，看着像没事（`latex_blocks.scan_math` 找不到收尾
# `$$` 时把它当空公式处理）。`chk_delim` 也抓不到——`$$` 是两个美元符，
# 加进去 `$` 的**奇偶不变**，配对检查照样"通过"。
_LONE_DD = re.compile(r"(?<!\\)\$\$")


# 作答位参数里被塞进了**续段**——页脚、章节标题、QQ 群广告、答案册标题、解析正文。
# 实测 14 道，形状完全一样：
#
#     \fillin[$\sqrt{3}$ 或 $\sqrt{6}+\sqrt{3}$\n\n四、解答题:]
#
# TeX 的可选参数**不允许空行**，于是 xelatex 报
# «Paragraph ended before \fillin was complete»、**整份卷子出不来**；
# 而网页预览照常（块级 IR 自己找 `]`），所以三层验收全是绿的。
#
# 续段分三种处置，都无损：
#   ① 像卷面噪声 → 删（页脚/章节标题/群广告，永远不是题面内容）
#   ② `solution` 里已经有一份 → 删（重复）
#   ③ 其余 → 挪进 `solution`
_NOISE_HEAD = re.compile(
    r"^\s*(?:[一二三四五六七八九十]+\s*[、.．]?\s*(?:选择题|填空题|解答题|题)"
    r"|.{0,10}参考答案|答案第\s*\d+\s*页|第\s*\d+\s*页|共\s*\d+\s*页"
    r"|QQ\s*[教师学生]{0,2}群|教师群|学生群|部分小题答案详解|答案详解"
    r"|微信号|扫码|关注公众号|部分小题)")
_SLOT_ARGC = re.compile(r"\\(?:fillin|paren)(?![a-zA-Z])\s*\[")


@rule(name="答案栏尾部的分号与句号去掉", scope=MIGRATE,
      why="三轴机检 A10/A12：答案表是按列排的，抽取时把**列分隔符**一起抄了进来，"
          "于是答案栏长成 `$\\frac{4}{15}$;`、`$(-2,1)$;`；另一路是**句末的「。」被当成答案的一部分**，"
          "于是卷面上 `\fillin[$6$。]。` 印出两个句号。"
          "实测存量：分号 7 道、句号 181 道（全是填空题，高考真题 156／模拟 25）。"
          "⚠️ 只砍**收尾**的那一个：多空答案写成 `$1$；$2$` 的收尾是数值，不动；"
          "砍完为空也不动（答案栏不能被规则清空）。")
def strip_answer_trailing_semicolon(q: Question) -> bool:
    r"""答案栏结尾的分号／句号（连同 `\fillin[…]`／`\paren[…]` 里同源的残留）一起去掉。"""
    a = q.answer or ""
    new_a = re.sub(r"[;；。\s]+$", "", a)
    if new_a == a or not new_a:
        return False
    q.answer = new_a
    # 作答位与答案栏**同源**（ENTRY 期规则只在录入时同步过一次），不同步就会
    # 卷面印旧值、字段是新值。
    old_slot = re.compile(r"\\(fillin|paren)(?![a-zA-Z])\s*\[" + re.escape(a) + r"\]")
    q.stem = old_slot.sub(lambda m: "\\" + m.group(1) + "[" + new_a + "]", q.stem or "")
    return True


@rule(name="作答位参数里的续段挪出参数", scope=MIGRATE,
      why="TeX 规则 + 规范 §2.2：`\\fillin[…]`／`\\paren[…]` 的可选参数**不能含空行**"
          "（TeX 的可选参数扫描器遇到空段就停），含了 xelatex 报 "
          "«Paragraph ended before \\fillin was complete»，**该题所在的整份卷子出不来**")
def split_blank_arg_tail(q: Question) -> bool:
    r"""`\fillin[答案\n\n后面的东西]` → 参数只留第一段；续段按上面三条处置。"""
    moved: list[str] = []
    changed = False
    for fld in ("stem", "answer", "solution"):
        t = getattr(q, fld) or ""
        if not t:
            continue
        pos, out, hit = 0, [], False
        for m in _SLOT_ARGC.finditer(t):
            if m.start() < pos:                # 落在上一个参数内部
                continue
            arg, nxt, balanced = scan_bracket(t, m.end() - 1)
            if not balanced:
                continue
            mt = re.search(r"\n[ \t]*\n", arg)
            if not mt:
                pos = nxt
                continue
            out.append(t[pos:m.end()])         # `\fillin[`
            out.append(arg[:mt.start()].rstrip())
            out.append("]")
            tail = arg[mt.end():].strip()
            if tail:
                moved.append(tail)
            pos, hit = nxt, True
        if hit:
            out.append(t[pos:])
            setattr(q, fld, "".join(out))
            changed = True
    # `answer` 栏**本身**也要同步截断：答案是从题干那个槽**推导**出来的
    # （`latex_ir` 的 `fillin_answers`/`paren_answers`），槽截了、字段不截，
    # 元数据就和卷面不一致了。规范里答案段用 `；` 分隔，**合法答案不含空行**，
    # 所以遇到空行必然是续段。
    ans = q.answer or ""
    ma = re.search(r"\n[ \t]*\n", ans)
    if ma:
        moved.append(ans[ma.end():].strip())
        q.answer = ans[:ma.start()].rstrip()
        changed = True
    if moved:
        sol = (q.solution or "").strip()
        if sol == "解析无":
            sol = ""
        extra = [x for x in moved
                 if not _NOISE_HEAD.match(x) and x not in sol]
        if extra:
            add = "\n\n".join(extra)
            q.solution = (sol + "\n\n" + add) if sol else add
            changed = True
    return changed


@rule(name="落单的美元符双写", scope=MIGRATE,
      why="规范 §2.3：行间公式写 `\\[ … \\]`。落单的 `$$` 会吞掉后面整段正文，"
          "xelatex 直接报 `Command \\end{question} invalid in math mode`——"
          "**这一道题所在的那份卷子整个出不来**")
def strip_lone_double_dollar(q: Question) -> bool:
    r"""字段里有**恰好一个** `$$` → 删掉它。

    ⚠️ **只碰"恰好一个"的情形**：这时哪个多余一目了然，删掉就恢复正常。
    出现 3 个、5 个（凑不成对、又不只一个）的**一律不动**——那说明还丢过公式，
    得回原卷看，不是能自动拍板的（宁缺勿错）。

    成对的 `$$…$$` **不归这条管**：它能正常渲染，只是不合规范 §2.3，
    属于风格问题，不该混进"批量改数据"里（`conform.style_double_dollar`
    会提示，但不拦验收）。
    """
    hit = False
    for fld in ("stem", "answer", "solution"):
        t = getattr(q, fld) or ""
        if len(_LONE_DD.findall(t)) != 1:
            continue
        t2 = re.sub(r"[ \t]{2,}", " ", _LONE_DD.sub("", t))
        if t2 != t:
            setattr(q, fld, t2)
            hit = True
    return hit


# 数学模式里的 `//`：KaTeX / xelatex 都把它排成**两道斜杠**，不是平行号。
# 实测全库 200+ 处，卷面上就是 `DE//BC` 而不是 `DE∥BC`——编译不报错、
# 渲染也"成功"，只有人眼看得出错，所以只能在这里拦。
_MATH_SEG_N = re.compile(
    r"(?<!\$)\$(?!\$)([^$]*)\$(?!\$)|\\\[(.*?)\\\]|\\\((.*?)\\\)", re.S)
_SLASH_PAR = re.compile(r"\s*(?<![\\:/])//(?![:/])\s*")
# `\mbox{ // }` 是**文本模式**：前端把 `\mbox` 展开成 `\text`，里面写数学命令
# `\parallel` 会报 `Undefined control sequence`；写 `$\parallel$` 又会被前端的
# 数学分段器按 `$` 切断（实测 8 处 KaTeX 报错）。整个盒子只有平行号时，
# **直接换成数学模式里的 `\parallel`**，盒子不要了。
# 实测只出现在「2024 全国优质模拟题精选三月班」的 4 道题里。
_TEXTBOX_ONLY_PAR = re.compile(
    r"\\(?:mbox|text|textrm)\s*\{\s*(?:\$\s*\\parallel\s*\$|\\parallel|//)\s*\}")


def _fix_slash_math(t: str) -> str:
    r"""只替换**数学段内部**的 `//`；正文里的 `//`（链接、注释）不动。

    `\parallel` 后面补一个空格：`a//b` → `a\parallel b`，
    否则会拼成不存在的命令 `\parallelb`。
    """
    if not t:
        return t
    # 先修已经存在的 `\mbox{ // }` / `\mbox{ \parallel }` / `\mbox{ $\parallel$ }`
    # （不依赖还有没有 `//`——上一版只在替换 `//` 时顺手处理，改坏的存量没人再管）。
    t = _TEXTBOX_ONLY_PAR.sub(r" \\parallel ", t)
    if "//" not in t:
        return t
    out: list[str] = []
    pos = 0
    for m in _MATH_SEG_N.finditer(t):
        idx = next(i for i, g in enumerate(m.groups()) if g is not None)
        body = m.groups()[idx]
        if not _SLASH_PAR.search(body):
            continue
        start, end = m.start(idx + 1), m.end(idx + 1)
        out.append(t[pos:start])
        out.append(_SLASH_PAR.sub(r" \\parallel ", body))
        pos = end
    if not out:
        return t
    out.append(t[pos:])
    res = "".join(out)
    # 替换完 `//` 再扫一遍：`\mbox{ // }` → `\mbox{ \parallel }` 也要把盒子去掉
    return _TEXTBOX_ONLY_PAR.sub(r" \\parallel ", res)


@rule(name="数学里的 // 改 \\parallel", scope=MIGRATE,
      why="`//` 在数学模式里会被排成两道斜杠（`DE//BC`），不是平行号 `∥`；"
          "xelatex 与 KaTeX 都不报错，属于「编译成功 ≠ 卷面正确」")
def fix_slash_parallel(q: Question) -> bool:
    hit = False
    for fld in ("stem", "answer", "solution"):
        t = getattr(q, fld) or ""
        t2 = _fix_slash_math(t)
        if t2 != t:
            setattr(q, fld, t2)
            hit = True
    for o in q.options:
        t = o.text or ""
        t2 = _fix_slash_math(t)
        if t2 != t:
            o.text = t2
            hit = True
    return hit


@rule(name="解答题答案栏统一「见解析」", scope=MIGRATE,
      why="规范 §2.2 定的是解答题答案栏写「见解析」，可存量里有 500 道把结果写进了答案栏"
          "（实测还有写成「解答题」「C」这种占位/串到选择题栏的）——同一个字段两种口径，"
          "组卷答案页与界面就没法一视同仁地印。⚠️ **只归一解析栏真有推导的那些**："
          "答案栏是唯一载体的（解析空／「解析无」）一律不动，那等于把答案删了")
def unify_detailed_answer(q: Question) -> bool:
    if q.type != "detailed_answer":
        return False
    a = (q.answer or "").strip()
    if not a or a == "见解析":
        return False
    s = (q.solution or "").strip()
    if not s or s == "解析无":
        return False                      # 答案栏是唯一载体，动了就是丢信息
    q.answer = "见解析"
    return True


_PART_HEAD = re.compile(r"^[ \t]*[（(]\s*([1-4])\s*[)）][ \t]*")


@rule(name="解答题小问改用 enumerate", scope=ENTRY,
      why="库里 4385 道解答题的小问都是 `\\begin{enumerate}\\item …`，前端 `qlatex.ts:convertEnumerate` "
          "与出卷的 exam-zh 都按这一种实现（成对的转换函数，只统一一半就会"
          "预览和导出不一致）。新录的题里另有 847 道写成手写 `(1)(2)`，形制分叉")
def parts_to_enumerate(q: Question) -> bool:
    r"""解答题题干里行首的 `(1)(2)…` 分问 → `\\begin{enumerate}\\item …\\end{enumerate}`。

    四道保险，缺一条就不改（宁可留着原样，也不能把题干改坏）：

    1. **已经有 `\\item`／`enumerate` 的不动**——那是目标形制，重复包裹会套娃。
    2. **数学段里出现过 `(数字)` 的整题不动**。`$f(1)=2$`、`$a_1(1)$` 这类括号
       和分问编号长得一样；实测全库有 35 道解答题踩这个。
    3. **编号必须从 1 起严格递增**（1,2 / 1,2,3 / 1,2,3,4），至少两问。
       题干里引用上一问的「由(1)得」会被行首正则捞到，实测有 29 道长成
       `121`、`122`、`13`、`1212` 这种序列——这些一律不改。
    4. 编号必须**在行首**，不在句中（句中出现的多半是「高一（1）班」这类内容）。
    """
    if q.type != "detailed_answer":
        return False
    st = q.stem or ""
    if r"\item" in st or r"\begin{enumerate}" in st:
        return False
    for i, seg in enumerate(st.split("$")):                 # 保险 2
        if i % 2 and re.search(r"[（(]\s*[1-9]\s*[)）]", seg):
            return False
    lines = st.split("\n")
    hits = [(n, int(_PART_HEAD.match(l).group(1)))
            for n, l in enumerate(lines) if _PART_HEAD.match(l)]
    if len(hits) < 2:                                       # 保险 3
        return False
    if [g for _n, g in hits] != list(range(1, len(hits) + 1)):
        return False
    head = "\n".join(lines[:hits[0][0]]).rstrip()
    parts = []
    for j, (n, _g) in enumerate(hits):
        end = hits[j + 1][0] if j + 1 < len(hits) else len(lines)
        body = "\n".join(lines[n:end])
        body = _PART_HEAD.sub("", body, count=1).strip()    # 去掉手写编号，编号由环境渲染
        body = re.sub(r"\n{2,}", "\n", body).strip()
        if not body:
            return False
        parts.append(body)
    new = ("\n".join(["\\begin{enumerate}"] + ["\\item " + t for t in parts]
                      + ["\\end{enumerate}"]))
    stem = (head + "\n" if head else "") + new
    if stem == st:
        return False
    q.stem = stem
    return True


# ── 小问的小问：行首 `(i)(ii)`（含大写 I/II）→ 第二层 enumerate ──────────
#
# 渲染器（`qlatex.ts::convertEnumerate`）
# 对嵌套 enumerate 的层级样式是：第 1 层（1）（2），第 2 层 ①②③。
# 存量题里大量小问的小问仍写成行首 `(i)(ii)`——它不是 enumerate，渲染时
# 和上一问挤在同一段，卷面看不出层级（用户 2026-11-02 报的）。
_ROMAN_PART = re.compile(r"^([ \t]*)[（(]\s*(i{1,3}|iv|v)\s*[)）][ \t]*", re.I)
_ROMAN_NUM = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
_DIGIT_PART = re.compile(r"^([ \t]*)[（(]\s*([1-9])\s*[)）][ \t]*")
_PART_ANY = re.compile(
    r"^([ \t]*)[（(]\s*([1-9]|i{1,3}|I{1,3}|iv|IV)\s*[)）][ \t]*")


def _math_line_flags(lines: list[str]) -> list[bool]:
    r"""每行**行首**是否在数学模式里（`$` 与 `\[ … \]`）。

    行首编号必须不在数学里：`$f(1)$`、`$S_n(1)$` 这类括号和分问编号
    长得一样；但它们不在行首，或者整行在 math 里，不能当分问。
    """
    flags: list[bool] = []
    math = display = False
    for ln in lines:
        flags.append(math or display)
        i = 0
        while i < len(ln):
            if ln[i] == "\\":
                if ln.startswith("\\[", i):
                    display = True; i += 2; continue
                if ln.startswith("\\]", i):
                    display = False; i += 2; continue
                i += 2; continue
            if ln[i] == "$":
                math = not math
            i += 1
    return flags


def _top_parts_to_enum(stem: str) -> str:
    r"""无 enumerate 的解答题：行首 `(1)(2)` → 顶层 enumerate（存量版）。

    与 ENTRY 的 `parts_to_enumerate` 同一目标，但判断数学模式改成**逐行**：
    那条规则见到数学段里有 `(数字)` 就整题不动——`$S_n(1)$` 这种写法很常见，
    于是带嵌套小问的题永远改不到。这里只排除**行首本身在数学里**的编号。
    """
    if "\\begin{enumerate}" in stem or "\\item" in stem:
        return stem
    lines = stem.split("\n")
    flags = _math_line_flags(lines)
    hits = []
    for n, ln in enumerate(lines):
        if not flags[n]:
            m = _PART_ANY.match(ln)
            if not m:
                continue
            raw = m.group(2)
            val = int(raw) if raw.isdigit() else _ROMAN_NUM.get(raw.lower())
            if val:
                hits.append((n, val, raw.isdigit()))
    if len(hits) < 2:
        return stem
    # **只认第一套编号**：顶层是 (1)(2)，后面的 (i)(ii) 是它的小问，
    # 不能把两套混成一个 1..4 的序列。顶层若是 (I)(II)，同理。
    family = hits[0][2]
    fam = [h for h in hits if h[2] == family]
    if len(fam) < 2 or [v for _n, v, _d in fam] != list(range(1, len(fam) + 1)):
        return stem
    hits = fam
    first = hits[0][0]
    lead = "\n".join(lines[:first]).rstrip()
    parts: list[list[str]] = []
    for j, (n, _v, _d) in enumerate(hits):
        end = hits[j + 1][0] if j + 1 < len(hits) else len(lines)
        c = [lines[n]] + lines[n + 1:end]
        c[0] = _PART_ANY.sub("", c[0], count=1).strip()
        parts.append(c)
    out = ([lead + "\n"] if lead else []) + ["\\begin{enumerate}"]
    for c in parts:
        out.append("\\item " + c[0])
        out.extend(c[1:])
    out.append("\\end{enumerate}")
    return "\n".join(out)


def _nest_roman(stem: str) -> str:
    r"""顶层 enumerate 的 item 里，行首 `(i)(ii)` 块 → 嵌套 enumerate。

    只认**第 1 层 item 内、行首、不在数学里、从 i 起连续、至少两个**的编号；
    块里已经有嵌套环境就整块不动（避免套娃/错配）。
    """
    if "\\begin{enumerate}" not in stem:
        return stem
    lines = stem.split("\n")
    flags = _math_line_flags(lines)
    depth = 0
    in_item = False
    out: list[str] = []
    i = 0
    changed = 0
    while i < len(lines):
        ln = lines[i]
        d0 = depth
        if d0 == 1 and ln.lstrip().startswith("\\item"):
            in_item = True
        m = (_ROMAN_PART.match(ln) if (d0 == 1 and in_item and not flags[i]) else None)
        if m is not None:
            # 往前看一块：到下一个顶层 \item / \end{enumerate} 为止
            j = i
            marks: list[int] = []
            block: list[str] = []
            ok = True
            while j < len(lines):
                l2 = lines[j]
                s2 = l2.lstrip()
                if s2.startswith("\\item") or s2.startswith("\\end{enumerate}"):
                    break
                if "\\begin{enumerate}" in l2 or "\\end{enumerate}" in l2:
                    ok = False
                    break
                mm = _ROMAN_PART.match(l2)
                if mm is not None and not flags[j]:
                    marks.append(_ROMAN_NUM.get(mm.group(2).lower(), 0))
                block.append(l2)
                j += 1
            if ok and len(marks) >= 2 and marks == list(range(1, len(marks) + 1)):
                subs: list[list[str]] = []
                cur: list[str] = []
                for l3 in block:
                    if _ROMAN_PART.match(l3):
                        if cur:
                            subs.append(cur)
                        cur = [_ROMAN_PART.sub("", l3, count=1)]
                    else:
                        cur.append(l3)
                if cur:
                    subs.append(cur)
                out.append("\\begin{enumerate}")
                for c in subs:
                    out.append("\\item " + c[0].strip())
                    out.extend(c[1:])
                out.append("\\end{enumerate}")
                changed += 1
                i = j
                continue
        out.append(ln)
        depth += ln.count("\\begin{enumerate}") - ln.count("\\end{enumerate}")
        i += 1
    return "\n".join(out) if changed else stem


@rule(name="小问的小问改用嵌套 enumerate", scope=MIGRATE,
      why="解答题的小问下还有小问时，应写成第二层 enumerate（渲染成 ①②③）。"
          "存量里还有约 465 道写成行首 `(i)(ii)`/`(1)(2)`：导出的题目把 (i)(ii) "
          "和上一问挤在同一段，层级看不出来，用户手工改不过来。规则只认行首、"
          "连续、不在数学里的编号，且只换编号不改文字；改完再跑一次不动。")
def nest_sub_questions(q: Question) -> bool:
    r"""解析题的小问/小问的小问 → 嵌套 enumerate（**存量迁移**）。

    先补顶层（无 enumerate 的 `(1)(2)`），再把 item 里的 `(i)(ii)` 包成第二层。
    幂等：已经是目标形制的题，两遍跑完原样返回。
    """
    if q.type != "detailed_answer":
        return False
    st = q.stem or ""
    new = _nest_roman(_top_parts_to_enum(st))
    if new == st:
        return False
    q.stem = new
    return True


@rule(name="小问的小问改用嵌套 enumerate（录入）", scope=ENTRY,
      why="新录的题如果顶层小问已经是 enumerate、里面又写了行首 `(i)(ii)`，"
          "录入时就该包成第二层——否则预览和导出又是同一段，等到整库迁移才补。")
def nest_sub_questions_entry(q: Question) -> bool:
    r"""录入侧：只补第二层（顶层 `(1)(2)` 由 `parts_to_enumerate` 负责）。"""
    if q.type != "detailed_answer":
        return False
    st = q.stem or ""
    new = _nest_roman(st)
    if new == st:
        return False
    q.stem = new
    return True


@rule(name="解答题不留空作答位", scope=ENTRY,
      why="规范 §2.2：解答题的答案是「见解析」，题干里不该留空的 `\\paren[]`／`\\fillin[]`"
          "——留着渲染器就以为答案能内联，反而不写「答案：见解析」，答案就丢了")
def drop_blank_slot_in_detailed(q: Question) -> bool:
    r"""解答题题干里去掉**空**的作答位（`\paren[]`、`\fillin[]`、`\fillin{}`）；填了内容的不动。

    实测 4 道解答题的题干尾部残留 `\paren[]`（早年题型改造留下的），
    导致 `q.answer` 写进去却在 `render → parse` 往返里丢掉。
    """
    if q.type != "detailed_answer":
        return False
    out = re.sub(r"\\paren\s*\[\s*\]", "", q.stem)
    out = re.sub(r"\\fillin\s*\[\s*\]|\\fillin\s*\{\s*\}", "", out)
    out = re.sub(r"[ \t]+(?=[\n。，．,])", "", out)
    if out == q.stem:
        return False
    q.stem = out
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


@rule(name="填空位跟随答案", scope=ENTRY,
      why="规范 §2.2：改了 `answer` 就得改卷面上的填空位——"
          "「答案进填空位」只管空位，已填过的旧值它直接跳过，"
          "于是改答案只改了字段、卷面印的还是旧答案"
          "（与「作答括号跟随答案」同一类坑，选择题当年修了、填空题漏了；"
          "实测 2020新高考I#16 改答案后 `\\fillin` 里还是旧值）")
def fillin_follows_answer(q: Question) -> bool:
    r"""已填的填空位内容与答案不一致时，改成答案。

    正文才是答案的真相（读库时 `answer` 由 `\fillin[…]` 推出），字段与卷面
    不一致＝下次写库就把错的那个固化下来。拆段规则与「答案进填空位」完全
    一致（`split_answers`）：拆不出与空位数相同的段就**不猜**，原样不动。
    """
    if q.type != "fill_in_blank" or not q.answer.strip():
        return False
    holes = iter_slots(q.stem, _FILLIN_CMD)
    if not holes:
        return False
    parts = split_answers(q.answer, len(holes))
    if len(parts) != len(holes):
        return False
    if all(slot[2].strip() == p.strip() for slot, p in zip(holes, parts)):
        return False                      # 已经一致，不动
    out, pos = [], 0
    for (start, _bracket, _arg, end), p in zip(holes, parts):
        out.append(q.stem[pos:start])
        out.append(r"\fillin[" + protect(p) + "]")
        pos = end
    out.append(q.stem[pos:])
    q.stem = "".join(out)
    return True


_ARC_CMD = re.compile(r"\\(over|under)paren\s*\{")


@rule(name="弧记号改用 overset", scope=ENTRY,
      why="KaTeX 没有 `\\overparen`／`\\underparen`（那是 amsmath 给 LaTeX 用的），"
          "录进来端到端渲染就报 `Undefined control sequence: \\overparen`。"
          "库里已有 44 道写的是 `\\overset{\\frown}{AB}`，同一个意思同一个写法")
def arc_to_overset(q: Question) -> bool:
    changed = False
    for target in ("stem", "answer", "solution"):
        t = getattr(q, target) or ""
        if r"\overparen" not in t and r"\underparen" not in t:
            continue
        setattr(q, target, _ARC_CMD.sub(
            lambda mo: (r"\overset" if mo.group(1) == "over" else r"\underset")
            + r"{\frown}{", t))
        changed = True
    for i, o in enumerate(q.options):
        if r"\overparen" in o.text or r"\underparen" in o.text:
            o.text = _ARC_CMD.sub(
                lambda mo: (r"\overset" if mo.group(1) == "over" else r"\underset")
                + r"{\frown}{", o.text)
            changed = True
    return changed


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


# 百分号：**裸 `%` 在 LaTeX 里是注释符**，会把该行剩下的全吃掉。
#
# 实测（2026-10-02，其他杂项那批）：模型把百分比写成 `6%`、`0.1%`、
# `4.56%`。而「去注释」那条规则只遍历 `stem/answer/solution`、
# **不碰 `options`** —— 于是选项里的裸 `%` 活到了卷面上。印出来时
# `\item 在犯错误的概率不超过 0.1% 的前提下，认为…` 会被注释成
# `\item 在犯错误的概率不超过 0.1`，**后半句静默消失**。
# 主题库 30040 道里带裸 `%` 的是 **0 道** —— 规范本来就是写 `\%`。
#
# 判据只看**百分比语境**：`%` 前面紧跟数字或 `)`/`}`/`]`。
# 真注释（`% 2025 高考题`，前面是空白或行首）不动，交给「去注释」。
# ⚠️ 必须定义在「去注释」**之前**（规则按定义顺序跑），否则
# `(?<!\\)%[^\n]*` 会先把百分比连同后半行一起删掉，没得转义。
_PERCENT = re.compile(r"(?<=[0-9\)\}\]])%")


@rule(name="转义百分号", scope=ENTRY,
      why="规范 §2.8：裸 `%` 是 LaTeX 注释符，会把该行剩下的吃掉")
def escape_percent(q: Question) -> bool:
    changed = False
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        n = _PERCENT.sub(r"\\%", t)
        if n != t:
            setattr(q, f, n)
            changed = True
    # ⚠️ **选项也要清**：「去注释」只遍历上面三个字段、不碰 `options`。
    for o in q.options or []:
        t = o.text or ""
        n = _PERCENT.sub(r"\\%", t)
        if n != t:
            o.text = n
            changed = True
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
        # ★ 先看一个**安全切法**：空位紧贴在公式收尾的 `$` 前面
        # （`$\tan\left(\alpha+\frac{\pi}{4}\right) = \paren[]$`）。
        # 按空位切**不会**把 `\left`/`\right`、`\begin{cases}` 拆散——
        # 它们整对留在前半段里，所以这一种可以放心切，先于下面那条保守守卫。
        # 实测来源：赵礼显讲义转录，`\left…\right` 后面跟空作答位的选择题，
        # 单纯靠"有 `\left` 就不切"会漏掉，空位就一直留在数学模式里。
        #
        # ⚠️ **条件必须卡死**，第一版只判了"空位在收尾"，结果一个公式里两个空位时
        # 从尾巴上切一刀，前一个空位留在数学模式里、后一个跑到外面——
        # `$BD = \fillin[], \cos\angle ABD = \fillin[]$` 被切成
        # `$BD = \fillin[], \cos\angle ABD =$` + `\fillin[]`，`$` 还剩奇数个
        # （实测赵礼显讲义 p132 第 4 题）。所以要求：
        # 前半段里**没有别的空位**、`\left/\right` 与 `\begin/\end` 都**各配各的**。
        if "\\begin{" in body or "\\left" in body or "\\right" in body:
            m_tail = re.search(r"\s*\\(paren|fillin)\s*\[\s*\]\s*$", body)
            head = body[:m_tail.start()].rstrip() if m_tail else ""
            if (m_tail and head
                    and not re.search(r"\\(paren|fillin)\s*[\[\{]", head)
                    and head.count("\\left") == head.count("\\right")
                    and head.count("\\begin{") == head.count("\\end{")):
                out.append("$%s$" % head)
                out.append("\\" + m_tail.group(1) + "[]")
                k = j + 1
                continue
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


@rule(name="裸数学符号进数学模式", scope=MIGRATE,
      why="规范 §2.3：行内公式一律 `$…$`。实测 118 道题的正文里躺着裸 Unicode 运算符"
          "（`A∩B`、`DE∥平面`、`a≥0`、`M≠Ø`、`16 π`、`0∈∅`）——网页预览靠系统字体凑得出字形，"
          "XeLaTeX 走的是数学字体，符号不在字体表里就成缺字或 `?`，属于**预览能过、印出来坏**。")
def unicode_math_to_tex(q: Question) -> bool:
    r"""把**数学模式之外**的裸运算符换成 `$\\perp$` 这类写法。

    只碰运算符本身、不扩大范围：`A∩B` → `A$\\cap$B`。
    实测刻意**不处理**的三类，都是有真实正文用法的：
      · `…`（省略号，728 处）与 `·`（「阿尔·卡西」人名）——是中文标点；
      · `√`、`×`、`→`（实测三种正文用法：「“√”表示购买，“×”表示未购买」的图例、
        手机号码的占位符「×××××××」、状态转移「（开，关）→（关，关）」）——
        这三个**曾经进过映射**，干跑就把 2007 福建（文）#12 的占位符变成了
        `$\\times$$\\times$$\\times$…`，只能撤掉，留给整段重排；
      · `°`、`²`、`³`（「°C」「σ²」）——要连着上下标一起改才对称，留给整段重排。
    """
    changed = False
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        n = _wrap_bare_symbols(t)
        if n != t:
            setattr(q, f, n)
            changed = True
    for o in q.options:
        n = _wrap_bare_symbols(o.text or "")
        if n != (o.text or ""):
            o.text = n
            changed = True
    return changed


# 符号 → 数学命令。**只列"在正文里必定是数学"的那些**。
_BARE_MATH = {
    "⊥": r"\perp", "∥": r"\parallel", "≥": r"\geq", "≤": r"\leq", "≠": r"\neq",
    "∈": r"\in", "∉": r"\notin", "⊆": r"\subseteq", "⊇": r"\supseteq",
    "⊂": r"\subset", "⊃": r"\supset", "∪": r"\cup", "∩": r"\cap",
    "∅": r"\varnothing", "Ø": r"\varnothing", "∞": r"\infty",
    "±": r"\pm", "÷": r"\div",
    "⇒": r"\Rightarrow", "⇔": r"\Leftrightarrow",
    "π": r"\pi",
}
_BARE_RX = re.compile("[" + "".join(re.escape(c) for c in _BARE_MATH) + "]")
# 数学区间的四种写法：$…$（单个 $）、\[…\]、\(…\)
_MATH_SPAN = re.compile(r"(?<!\\)\\\[.*?\\\]|(?<!\\)\\\(.*?\\\)"
                        r"|(?<!\\)\$(?!\$)[^$]*?(?<!\\)\$", re.S)


def _wrap_bare_symbols(text: str) -> str:
    r"""只在**正文段**（数学区间之外）里替换符号，逐段替换后拼回去。

    拼回去的时候盯着边界：新插的 `$…$` 紧挨着一个**本来就有的** `$…$` 就是
    `$\Rightarrow$$\\sin A$`，照样是相邻双美元。所以只要"上一段以我们插入的
    `$` 收尾、下一段以 `$` 开头"就先补一个空格。
    """
    if not text or not _BARE_RX.search(text):
        return text
    out: list[str] = []
    pos = 0
    tail_inserted = False                # 上一段结尾是不是我们插进去的 `$`

    def push(chunk: str, head_ins: bool, tail_ins: bool) -> None:
        nonlocal tail_inserted
        if not chunk:
            return
        # 两个方向都要管：我们插的 `$` 挨着原文的 `$`（前一个或后一个）都算相邻双美元
        if chunk.startswith("$") and (tail_inserted or (out and out[-1].endswith("$"))):
            out.append(" ")
        out.append(chunk)
        tail_inserted = tail_ins

    for m in _MATH_SPAN.finditer(text):
        seg, head, tail_ = _split_bare(text[pos:m.start()])
        push(seg, head, tail_)
        push(m.group(0), False, False)   # 原有数学段：不算我们插的
        pos = m.end()
    seg, head, tail_ = _split_bare(text[pos:])
    push(seg, head, tail_)
    return "".join(out)


def _split_bare(seg: str) -> tuple[str, bool, bool]:
    """`_sub_bare` 的三值版：返回（结果，开头是否我们插的 `$`，结尾是否我们插的 `$`）。"""
    t, ins = _sub_bare(seg)
    return t, (t.startswith("$") and t != seg), ins


def _sub_bare(seg: str) -> tuple[str, bool]:
    r"""正文段里逐个包符号。返回（结果，结尾是否为我们插入的 `$…$`）。

    🔴 相邻的两个 `$` 之间必须补一个空格：`$\\perp$$\\parallel$` 这种相邻双美元
    是项目里记过的头号坑——「会吞掉后面整段正文，xelatex 报
    `\\end{question} invalid in math mode`」。这版规则第一跑就在 74 道题里造出
    12 处不规范（保定一模#15 一道就 8 处），所以前后邻居都要管。
    """
    if not seg or not _BARE_RX.search(seg):
        return seg, False
    out: list[str] = []
    last = ""                            # 已拼出去的最后一个字符
    inserted = False                     # 最后拼的是不是我们插的 `$…$`
    i = 0
    for m in _BARE_RX.finditer(seg):
        gap = seg[i:m.start()]
        out.append(gap)
        if gap:
            last, inserted = gap[-1], False
        piece = "$" + _BARE_MATH[m.group(0)] + "$"
        nxt = seg[m.end()] if m.end() < len(seg) else ""
        if last == "$":
            out.append(" ")
            last = " "
        out.append(piece)
        last, inserted = piece[-1], True
        if nxt == "$":                    # 后面紧跟原文里的 `$`
            out.append(" ")
            last, inserted = " ", False
        i = m.end()
    tail = seg[i:]
    out.append(tail)
    if tail:
        inserted = False
    return "".join(out), inserted


@rule(name="align系环境改规范行间", scope=MIGRATE,
      why="规范 §2.3：行间式写 `\\[ … \\]`。库里 7 道用了 `align*`——KaTeX 只有在"
          "**display 模式**下才接受它（inline 模式直接报 “can be used only in display mode”），"
          "`\\(...\\)`、`$…$` 里一旦套上就炸；改成 `\\\\[ \\\\begin{aligned}…\\\\end{aligned} \\\\]` "
          "两种渲染器都稳，写法也跟全库其余 8 万个行间式一致。")
def align_to_aligned(q: Question) -> bool:
    r"""`\\begin{align*} … \\end{align*}` → `\\[ \\begin{aligned} … \\end{aligned} \\]`。"""
    changed = False
    for f in ("stem", "answer", "solution"):
        t = getattr(q, f) or ""
        if "\\begin{align" not in t:
            continue
        n = _ALIGN_ENV.sub(
            lambda m: "\n\\[\n\\begin{aligned}" + m.group(1).strip("\n ")
                      + "\\end{aligned}\n\\]\n", t)
        n = re.sub(r"\n{3,}", "\n\n", n)
        if n != t:
            setattr(q, f, n)
            changed = True
    return changed


_ALIGN_ENV = re.compile(r"\\begin\{align\*?\}([\s\S]*?)\\end\{align\*?\}")


# ── 入口 ────────────────────────────────────────────────────────────

def _resync_tikz(q: Question) -> bool:
    r"""题干/解析里的 TikZ 被改写过 → **图登记跟着改**。

    为什么必须同步：一张 TikZ 图在两处各存一份——正文里的
    `\begin{tikzpicture}…`（真相）和 `figures[].tikz`（出卷子时拿去渲染，
    也是 `tikzfig.to_image` **逐字比对**的钥匙）。规则只要动过正文里那段
    源码（实测：`行内公式统一用 $…$` 把节点标签的 `\(B\)` 改成 `$B$`），
    两份就对不上，后果是**渲染好了也换不上图**——卷子里退回内联 TikZ，
    正是 `tikzfig` 开头说的「抽到才炸」。

    只换 `kind == "tikz"` 的登记项，位图那部分原样不动（它们的 id 是文件名，
    还带着 `source`/`width`，不该按正文重算）。`tikz_id` 由源码哈希得出，
    源码变了 id 跟着变——与 `latex_ir.tikz_id` 的约定一致。
    """
    from .latex_ir import derive_figures
    old = [f for f in q.figures if f.kind == "tikz"]
    new = [f for f in derive_figures(q.stem, q.solution, *(o.text for o in q.options))
           if f.kind == "tikz"]
    if [f.tikz for f in old] == [f.tikz for f in new]:
        return False
    it = iter(new)
    out = []
    for f in q.figures:                      # 位置不变，只把 tikz 那几项换掉
        if f.kind != "tikz":
            out.append(f)
            continue
        nf = next(it, None)
        if nf is not None:
            out.append(nf)
    out.extend(it)
    q.figures = out
    return True


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
    # **改完正文，图登记跟着改**——不同步的话，出卷子时「渲染好了也换不上图」，
    # 而且没有任何检查会报（实测干跑全绿，导出时才露）。见上面的说明。
    _resync_tikz(q)
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

    # 外部材料形态：答案抄在解析第一行（「答案：C」），题干还是「（\quad）」
    q_ext = Question(key="t/ext", type="single_choice",
                     stem=r"则 $A\cup B=$（\quad）",
                     options=[Option("A", "a"), Option("B", "b"),
                              Option("C", "c"), Option("D", "d")],
                     answer="", solution="答案：C。\n\n【详解】因为……")
    normalize(q_ext)
    check("解析第一行的「答案：C」搬进答案栏",
          q_ext.answer == "C" and r"\paren[C]" in q_ext.stem,
          "%r | %s" % (q_ext.answer, q_ext.stem))
    check("答案行与「【详解】」都从解析里去掉",
          q_ext.solution == "因为……", repr(q_ext.solution))
    check("🔴 搬答案幂等（再跑一次不报改动）",
          not answer_from_solution_head(q_ext) and "答案" not in (q_ext.solution or ""),
          repr(q_ext.solution))

    # 答案栏已有值：只删一模一样的回声；打架时一个字不动
    q_echo = Question(key="t/echo", type="single_choice", stem=r"则（\quad）",
                      options=[Option("A", "a"), Option("B", "b"),
                               Option("C", "c"), Option("D", "d")],
                      answer="C", solution="答案：C。\n讲解。")
    normalize(q_echo)
    check("答案栏已有同值：删掉解析里的回声", q_echo.solution == "讲解。", q_echo.solution)
    q_conflict = Question(key="t/conf", type="single_choice", stem=r"则（\quad）",
                          options=[Option("A", "a"), Option("B", "b"),
                                   Option("C", "c"), Option("D", "d")],
                          answer="B", solution="答案：C。\n讲解。")
    normalize(q_conflict)
    check("🔴 答案栏与解析打架：留着一字不动、不猜",
          q_conflict.answer == "B" and q_conflict.solution.startswith("答案：C"),
          "%r | %r" % (q_conflict.answer, q_conflict.solution))

    # 解答题的「答案：」是讲解内容（规范 §2.2 允许 `\textbf{答案：}`），不搬
    q_da = Question(key="t/da", type="detailed_answer", answer="见解析",
                    stem="求 $a$。", solution="答案：$a=1$。\n因为……")
    normalize(q_da)
    check("解答题的「答案：」不搬走", q_da.solution.startswith("答案：$a=1$"),
          repr(q_da.solution))

    # 填空：解析第一行的答案 → 答案栏 → `\fillin[…]`
    q_fi = Question(key="t/fi", type="fill_in_blank", answer="",
                    stem=r"则 $x=$ \fillin{} 。", solution="答案：$2$。\n因为……")
    normalize(q_fi)
    check("填空的「答案：$2$」搬进填空位",
          q_fi.answer == "$2$" and r"\fillin[$2$]" in q_fi.stem,
          "%r | %s" % (q_fi.answer, q_fi.stem))

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
    # ── 百分号：裸 `%` 是注释符，会把该行剩下吃掉 ────────────────────
    # 实测（其他杂项那批）：模型把百分比写成 `6%`、`0.1%`，而「去注释」
    # 只遍历 stem/answer/solution、**不碰 options** —— 选项里的裸 `%`
    # 活到卷面上，把 `…0.1% 的前提下，认为…` 印成 `…0.1`（后半句消失）。
    q5 = Question(key="k", type="single_choice", stem="求合格率。",
                  answer="", solution="",
                  options=[Option(label="A", text="在不超过 0.1% 的前提下，认为有关"),
                           Option(label="B", text="$0.1\\%$"),
                           Option(label="C", text="25%")])
    normalize(q5)
    check("选项里的百分比被转义", q5.options[0].text == "在不超过 0.1\\% 的前提下，认为有关",
          repr(q5.options[0].text))
    check("百分比转义**不删正文**（这是关键）",
          "的前提下，认为有关" in q5.options[0].text, repr(q5.options[0].text))
    check("已转义的 \\% 不动", q5.options[1].text == "$0.1\\%$", repr(q5.options[1].text))
    check("行尾百分比也转义", q5.options[2].text == "25\\%", repr(q5.options[2].text))
    # 真注释（前面是空白/行首）不能被当成百分比
    q6 = Question(key="k", type="detailed_answer", stem="求值。\n% 2025 高考题",
                  answer="", solution="")
    normalize(q6)
    check("真注释仍然被去掉", "%" not in q6.stem, repr(q6.stem))
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

    # 题干开头的题型自述：题型判对之后把这句多余的标记删掉
    q_h1 = _mk(r"（多选）已知 $f(x)=x^{3}$，则（\quad）", typ="multi_choice")
    check("题首「（多选）」被删", strip_type_head(q_h1)
          and q_h1.stem.startswith("已知 $f(x)"), q_h1.stem)
    check("删标记后幂等", not strip_type_head(q_h1), q_h1.stem)
    q_h2 = _mk(r"(多选) 已知正实数 $a$、$b$，则（\quad）", typ="multi_choice")
    check("半角「(多选)」也认", strip_type_head(q_h2)
          and q_h2.stem.startswith("已知正实数"), q_h2.stem)
    q_h2b = _mk(r"（单选）已知函数 $y=f(x)$，则（\quad）")
    check("题首「（单选）」也删", strip_type_head(q_h2b)
          and q_h2b.stem.startswith("已知函数"), q_h2b.stem)
    # 反例一：题型还不是多选 —— 这句是 `fix_multi_choice_type` 的唯一判据，不许删
    q_h3 = _mk(r"（多选）下列正确的是（\quad）", n=3)
    check("🔴 题型不是多选的**不许**删标记", not strip_type_head(q_h3)
          and "（多选）" in q_h3.stem, q_h3.stem)
    # 反例二：正文中间提到「多项选择题」是题目内容，不是标记
    q_h4 = _mk(r"新高考数学试卷共有 3 道多项选择题，则得分情况为（\quad）",
               typ="multi_choice")
    check("🔴 题干中间的「多项选择题」不动", not strip_type_head(q_h4), q_h4.stem)
    # 反例三：填空题/解答题里的不动
    q_h5 = _mk(r"（多选）说法正确的有 \fillin{}", typ="fill_in_blank", n=0)
    check("🔴 填空题不动", not strip_type_head(q_h5), q_h5.stem)
    # 反例四：自述与 `type` 打架（写「（单选）」却标成多选）→ 删了就把线索灭了
    q_h5b = _mk(r"（单选）已知 $a>0$，则（\quad）", typ="multi_choice")
    check("🔴 自述与题型对不上的一律不动", not strip_type_head(q_h5b)
          and q_h5b.stem.startswith("（单选）"), q_h5b.stem)
    # 端到端：单选 + 4 选项，改判 → 删标记，一次 MIGRATE 全做完，且顺序不能反
    q_h6 = _mk(r"（多选）已知正方体的棱长为 2，则（\quad）")
    normalize(q_h6, MIGRATE)
    check("MIGRATE：先改判多选、再删题首标记",
          q_h6.type == "multi_choice" and q_h6.stem.startswith("已知正方体"), q_h6.stem)

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

    # ── 卷面排版噪声（台账 D01/D02）────────────────────────────────
    # 用例全部取自真实脏数据，不要改成"想象出来的"形式。
    from .schema import Option as _Opt                     # noqa: F401
    for raw, want in [
        ("（本小题满分 17 分）\n已知函数 $f(x)=x$", "已知函数 $f(x)=x$"),
        ("(本小题满分15分)\n某大学一兴趣小组", "某大学一兴趣小组"),
        ("（13分）已知 $a,b,c$ 分别为", "已知 $a,b,c$ 分别为"),
        # 分值后面常跟一个句号，要一并带走（不然留下个孤零零的「。」）
        ("(本小题满分 15 分)。\n\n已知抛物线 $C$", "已知抛物线 $C$"),
        ("(15分)  已知双曲线 $C$", "已知双曲线 $C$"),
        ("本小题满分17分\n已知函数", "已知函数"),
        # **不能误伤**：题干里正常的数字+分，以及"分形"这种词
        ("已知 $x$ 的分式方程", "已知 $x$ 的分式方程"),
        ("3 分钟内心率", "3 分钟内心率"),
        ("（1）求 $a$ 的值", "（1）求 $a$ 的值"),
    ]:
        _q = Question(key="t/score", type="detailed_answer", stem=raw)
        strip_score_head(_q)
        check("去分值：%r" % raw[:14], _q.stem == want, repr(_q.stem))
    _q = Question(key="t/score2", type="detailed_answer", stem="（17分）")
    check("去分值：整段都是分值就保留（不能清成空题）", _q.stem == "（17分）"
          or not strip_score_head(_q), repr(_q.stem))

    for raw, want in [
        # 整行就是页脚
        ("已知 $a=1$。\n\n第 3 页 共 8 页", "已知 $a=1$。"),
        # 卷名 + 页脚，整行是排版
        ("已知 $a=1$。\n\n2025年秋季学期高三年级12月质量检测数学试题 第 4 页 共 4 页",
         "已知 $a=1$。"),
        ("已知 $a=1$。\n第7页共8页", "已知 $a=1$。"),
        # 正文与页脚挤在同一行 —— **不能把正文删掉**
        ("所以红桃 A 的左侧没有数字牌高三数学 答案 第1页 共10页",
         "所以红桃 A 的左侧没有数字牌"),
        ("恰好被安排在 $A$ 家庭有 60 种不同安排方法。\n\n第 3 页 共 8 页",
         "恰好被安排在 $A$ 家庭有 60 种不同安排方法。"),
        # 字面量 \n（%% @q 元数据里是双转义的）也要认
        ("已知 $a=1$。\\n\\n第 3 页 共 8 页", "已知 $a=1$。"),
        # **不能误伤**：正文里出现「第 N 页」以外的“页”
        ("一本书共 100 页，每天读 5 页", "一本书共 100 页，每天读 5 页"),
        # **剪剩半截卷眉**也要整行删（实测 `2027届高三8月底学情调研·数学 第3页 共4页`）
        ("已知 $a=1$。\n2027届高三8月底学情调研·数学 第3页 共4页", "已知 $a=1$。"),
        ("已知 $a=1$。\nZ20名校联盟2027届高三第一次学情诊断 数学试题卷 第3页 共4页",
         "已知 $a=1$。"),
        # **真踩过的坑**：`共 N 页` 写成可选时，这一行被当成页脚整行删掉，
        # 一道题被截成 9 个字（千题册 053#76）。页脚必须有「共」。
        ("人教 A 版必修第一册第 92 页上“探究与发现”的学习内容是“探究函数”",
         "人教 A 版必修第一册第 92 页上“探究与发现”的学习内容是“探究函数”"),
    ]:
        _q = Question(key="t/foot", type="detailed_answer", stem=raw)
        strip_running_head(_q)
        check("去页脚：%r" % raw[:18], _q.stem.strip() == want, repr(_q.stem))

    # 补填空位：卷面上"空位"有四种写法，都得归成 `\fillin[]`
    for raw, tail in [
        ("已知 $a=1$，则 $b=$ _____。", r"$b=$ \fillin[]。"),
        # 空位原本在数学模式里 → 就地把数学收尾，空位挪到外面
        (r"已知 $a=1$，则 $b=\underline{\Delta}$。", r"$b=$ \fillin[]。"),
        # 空位补在**句末标点之前**（卷面就是「……的值____。」这个样子）
        ("已知 $a=1$，求 $b$ 的值。", r"求 $b$ 的值 \fillin[]。"),
    ]:
        _q = Question(key="t/fill", type="fill_in_blank", stem=raw, answer="2")
        check("补填空位：%r" % raw[:12], ensure_fillin(_q)
              and _q.stem.endswith(tail), repr(_q.stem[-24:]))
    _q = Question(key="t/fill2", type="fill_in_blank",
                  stem=r"则 $b=\fillin[]$。", answer="2")
    check("补填空位：**在数学模式里的旧空位要挪出来**", ensure_fillin(_q)
          and _q.stem == r"则 $b=$ \fillin[]。", repr(_q.stem))
    # 空位被**单独**包了一对 `$…$`（VLM 转录的常见写法）。这时不能补
    # `$ `——`before` 末尾已经是 `$`，补了就是 `$$`（KaTeX 直接报错）。
    _q = Question(key="t/fill3", type="fill_in_blank",
                  stem=r"则 $\max M$ 的最小值为 $\fillin[]$。", answer="2")
    check("补填空位：空位自成一对的 `$…$` 要整对删掉（不许出 `$$`）",
          ensure_fillin(_q)
          and _q.stem == r"则 $\max M$ 的最小值为 \fillin[]。"
          and "$$" not in _q.stem, repr(_q.stem))
    _q = Question(key="t/fill5", type="fill_in_blank",
                  stem=r"则 $b=$ \fillin[]。", answer="2")
    check("补填空位：已在外面就不动", not ensure_fillin(_q), repr(_q.stem))
    # **填好的空位更不能动**——漏了这条守卫，一次改坏 3957 道（真踩过）
    _q = Question(key="t/fill6", type="fill_in_blank",
                  stem=r"则该双曲线的离心率为\fillin[$\frac{3}{2}$]。"
                       r"\includegraphics[width=6cm]{x.png}",
                  answer=r"$\frac{3}{2}$")
    check("补填空位：**已填好的空位一个字都不动**", not ensure_fillin(_q),
          repr(_q.stem))
    _q = Question(key="t/fill4", type="fill_in_blank",
                  stem=r"则 $\mu =\underline{\Delta}$。", answer="2")
    ensure_fillin(_q)
    check("补填空位：空位在数学模式里要就地收尾（不许嵌套 $）",
          _q.stem.count("$") % 2 == 0 and r"$ \fillin[]" in _q.stem, repr(_q.stem))
    # 空位紧贴公式收尾 `$`、公式里又有 `\left…\right`：**这一种能安全切开**，
    # 别被"有 \left 就不切"那条保守守卫拦下（赵礼显讲义转录实测）。
    _q = Question(key="t/mv1", type="single_choice",
                  stem=r"已知 $\tan\left(\alpha+\frac{\pi}{4}\right) = \paren[]$ 则 $\alpha=$",
                  answer="", options=[Option(x, "1") for x in "ABCD"])
    normalize(_q, ENTRY)
    check("空位在 `\\left…\\right` 公式尾巴上也要挪出来",
          r"=$\paren[]" in _q.stem and _q.stem.count("$") % 2 == 0, repr(_q.stem))
    # 反例：`\begin{cases}` 里的空位**不能**切（切了环境会分家）
    _q = Question(key="t/mv2", type="fill_in_blank",
                  stem=r"$a_n=\begin{cases} n, & \fillin[] \\ 1, & x>0 \end{cases}$",
                  answer="")
    normalize(_q, ENTRY)
    # 反例要求的是"`\begin{cases}` 和 `\end{cases}` **在同一段公式里**"——
    # 只查两个串在不在，等于没查（第一版就是这么放的，实际已经被切成两段了）
    _seg = (_q.stem[_q.stem.index(r"\begin{cases}"):_q.stem.index(r"\end{cases}")]
            if r"\begin{cases}" in _q.stem and r"\end{cases}" in _q.stem else "$")
    # 空括号**自己带着一对 `$…$`**（`$(\quad)$`）：只删括号会留下 `$$`，
    # 而 `chk_delim` 查不出来（`$` 还是偶数个）。实测赵礼显讲义 p073 第 17 题。
    _q = Question(key="t/dd", type="single_choice",
                  stem=r"函数 $f(x)=\frac{\tan x}{1+\tan^2 x}$ 的最小正周期为 $(\quad)$ \paren[]",
                  answer="", options=[Option(x, "1") for x in "ABCD"])
    normalize(_q, ENTRY)
    check("空括号自带 `$…$` 时要连 `$` 一起删（不许出 `$$`）",
          "$$" not in _q.stem and _q.stem.endswith(r"\paren[]"),
          repr(_q.stem))
    check("反例：`\\begin{cases}` 里的空位不切（环境不许分家）",
          _q.stem.count("$") % 2 == 0 and "$" not in _seg, repr(_q.stem))
    _dq = Question(key="t/det3", type="detailed_answer",
                    stem="求 $x$ 的最小值\\paren[]。", answer="", solution="……")
    normalize(_dq, ENTRY)
    check("解答题不留空作答位", "\\paren" not in _dq.stem and _dq.answer == "见解析", repr(_dq.stem))
    # 解答题答案栏：空 → 「见解析」（用户要求：保证每道题都有答案）
    _dt = Question(key="t/det", type="detailed_answer", stem="求 $x+\\frac1x$ 的最小值。",
                   answer="", solution="由均值不等式得最小值为 $2$。")
    normalize(_dt, ENTRY)
    check("解答题答案栏空 → 见解析", _dt.answer == "见解析", repr(_dt.answer))
    _dt2 = Question(key="t/det2", type="detailed_answer", stem="求 $x$。",
                    answer="12", solution="……")
    normalize(_dt2, ENTRY)
    check("解答题已有答案不动", _dt2.answer == "12", repr(_dt2.answer))
    # ⚠️ 空括号的三条回归（实测 224 道补答案"成功"却没落进正文，根因就在这两行正则）：
    #   `_FILLIN_FILLED` 曾把 `\fillin[]` 当"已填" → 规则永不生效；
    #   `_BLANK_FILLIN` 又不吃 `[]` → 修了前者就会留下 `\fillin[2][]`。
    for _stem, _tag in ((r"最小值为 \fillin[]。", "空方括号"),
                        (r"最小值为 \fillin{}。", "空花括号"),
                        (r"最小值为 \fillin。", "裸命令")):
        _x = Question(key="t/fillhole", type="fill_in_blank", stem=_stem,
                      answer="2", solution="解析无")
        normalize_one = None
        normalize(_x, ENTRY)
        check("答案进填空位：%s 要就地填成 `\\fillin[2]`（不留空括号）" % _tag,
              _x.stem.endswith(r"\fillin[2]。"), repr(_x.stem))
    _y = Question(key="t/fillfilled", type="fill_in_blank",
                  stem=r"最小值为 \fillin[7]。", answer="7", solution="解析无")
    normalize(_y, ENTRY)
    check("答案进填空位：已填的括号不许被重复插入",
          _y.stem.count(r"\fillin") == 1, repr(_y.stem))

    # ⚠️ **答案里带 `]`（右闭区间）的那一类**：槽位必须由 `iter_slots` 按 TeX 的
    # 可选参数规则读。以前用正则 `(?:[^\[\]]|\[[^\]]*\])*` 数括号，它不认 `{…}` 分组，
    # 于是 `\fillin[{$(2,3]$}]` 从中间被截断，尾巴 `}$}]` 掉回正文——
    # 入库后端到端渲染就那一处 KaTeX 报错（长沙湖南师大附中月考（五）#13）。
    _z = Question(key="t/bracket", type="fill_in_blank",
                  stem=r"取值范围为\fillin[]。", answer=r"$(2,3]$", solution="解析无")
    normalize(_z, ENTRY)
    check("答案带右闭区间：填进槽位后没有尾巴掉回正文",
          _z.stem.endswith(r"\fillin[{$(2,3]$}]。"), repr(_z.stem))
    _again = _z.stem
    normalize(_z, ENTRY)
    check("答案带右闭区间：再规范化一遍**不叠尾巴**（正文才是答案的真相）",
          _z.stem == _again, repr(_z.stem))
    _w = Question(key="t/paren-br", type="fill_in_blank",
                  stem=r"解集为\fillin[{$[0,1]$}]。", answer=r"{$[0,1]$}",
                  solution="解析无")
    normalize(_w, ENTRY)
    check("槽位里已有配对花括号时不被截断",
          _w.stem.endswith(r"\fillin[{$[0,1]$}]。"), repr(_w.stem))
    check("iter_slots：配不平的槽位返回 None（读不准就不改）",
          iter_slots(r"x\fillin[$\left[0,1$]。") is None,
          str(iter_slots(r"x\fillin[$\left[0,1$]。")))

    # KaTeX 没有 `\overparen`（那是 amsmath 给 LaTeX 的），库里 44 道用的是
    # `\overset{\frown}{}`——入库时必须自动换掉，否则层③ 端到端渲染就红
    _arc = Question(key="t/arc", type="fill_in_blank",
                    stem=r"弧 $\overparen{AB}$ 所对圆心角为 $\dfrac{\pi}{3}$",
                    answer=r"$\dfrac{\pi}{3}$", solution="解析无")
    arc_to_overset(_arc)
    check("弧记号：\\overparen 换成 \\overset{\\frown}{}",
          r"\overset{\frown}{AB}" in _arc.stem and "overparen" not in _arc.stem,
          repr(_arc.stem))
    _arc2 = Question(key="t/arc2", type="single_choice",
                     stem=r"$\overparen{AB}$、$\underparen{CD}$ 相等吗",
                     options=[Option("A", r"$\overparen{AB}$"), Option("B", "是")],
                     answer="A", solution="解析无")
    arc_to_overset(_arc2)
    check("弧记号：选项里也换、underparen 也换",
          "overparen" not in _arc2.stem and "underparen" not in _arc2.stem
          and "overparen" not in _arc2.options[0].text,
          repr(_arc2.stem + _arc2.options[0].text))
    # 去解析中间夹的答案册页脚：正向删、幂等、**不碰数学**
    _qf = Question(key="t/foot", type="single_choice", stem="x", answer="A",
                   options=[Option("A", "1"), Option("B", "2")],
                   solution="所以 $x_1,x_2<1$。\n\n数学参考答案（一中版）-2\n\n故 $x=1$。")
    check("去页脚：删掉中间夹的页脚、保留两侧推导",
          strip_answer_book_footer(_qf)
          and "数学参考答案" not in _qf.solution
          and _qf.solution.startswith("所以 $x_1,x_2<1$。")
          and _qf.solution.endswith("故 $x=1$。"),
          repr(_qf.solution))
    check("去页脚：幂等", not strip_answer_book_footer(_qf), repr(_qf.solution))
    _qf2 = Question(key="t/foot2", type="single_choice", stem="x", answer="A",
                    options=[Option("A", "1")], solution="由 $a>0$ 得结论。")
    check("去页脚：没有页脚的题不动", not strip_answer_book_footer(_qf2), repr(_qf2.solution))

    _mp = Question(key="t/mixparen", type="single_choice", stem="x", answer="A",
                   options=[Option("A", "1")], meta={"source_label": "金太阳联考(26-287C）"})
    check("来源标签：半角+全角混用时统一成全角",
          unify_source_label_paren(_mp) and _mp.meta["source_label"] == "金太阳联考（26-287C）",
          repr(_mp.meta["source_label"]))
    check("来源标签：整体半角的不动",
          not unify_source_label_paren(Question(
              key="t/mixparen2", type="single_choice", stem="x", answer="A",
              options=[Option("A", "1")], meta={"source_label": "强基(数学)卷"})))
    check("来源标签：整体全角的不动",
          not unify_source_label_paren(Question(
              key="t/mixparen3", type="single_choice", stem="x", answer="A",
              options=[Option("A", "1")], meta={"source_label": "强基（数学）卷"})))

    _pg = Question(key="2027千题册经典重点册（上）_images/197#38", type="multi_choice",
                   stem="x", answer="A", options=[Option("A", "1")],
                   meta={"source_label": "197", "book": "2027千题册经典重点册（上）_images"})
    check("来源页号：补成「书名·第N页」",
          expand_page_only_source_label(_pg)
          and _pg.meta["source_label"] == "2027千题册经典重点册（上）·第197页",
          repr(_pg.meta["source_label"]))
    check("来源页号：真卷名不动",
          not expand_page_only_source_label(Question(
              key="t/pg2", type="multi_choice", stem="x", answer="A", options=[Option("A", "1")],
              meta={"source_label": "2024年新高考I卷", "book": "高考真题汇编"})))
    check("来源页号：没有该字段不动",
          not expand_page_only_source_label(Question(
              key="t/pg3", type="multi_choice", stem="x", answer="A", options=[Option("A", "1")])))

    # 来源标签补右括号：只补不删，配平的不动
    _sl = Question(key="t/srclab", type="single_choice", stem="x", answer="A",
                   options=[Option("A", "1"), Option("B", "2")],
                   meta={"source_label": "海南学业水平诊断（四"})
    check("来源标签：截断的补一个右括号",
          close_source_label_paren(_sl) and _sl.meta["source_label"] == "海南学业水平诊断（四）",
          repr(_sl.meta["source_label"]))
    check("来源标签：配平的不动",
          not close_source_label_paren(Question(
              key="t/srclab2", type="single_choice", stem="x", answer="A",
              options=[Option("A", "1")], meta={"source_label": "强基中学（三）卷"})))
    check("来源标签：没有该字段的不动",
          not close_source_label_paren(Question(key="t/srclab3", type="single_choice",
                                               stem="x", answer="A", options=[Option("A", "1")])))

    # 去「图未读入」备注：纯噪声删、带内容的读图说明**不删**
    _fu = Question(key="t/figunread", type="detailed_answer", stem="x", answer="见解析",
                   solution="图未读入，依据题干推断。建系 $A(0,0,0)$，得 $x=1$。")
    check("去图未读入：删开头那句、留推导",
          strip_figure_unread_note(_fu)
          and "图未读入" not in _fu.solution
          and _fu.solution.startswith("建系 $A(0,0,0)$"), repr(_fu.solution))
    check("去图未读入：幂等", not strip_figure_unread_note(_fu), repr(_fu.solution))
    _fu2 = Question(key="t/figunread2", type="detailed_answer", stem="x", answer="见解析",
                    solution="（图未读入，依据题干推断：$A$ 为圆锥顶点。）故 $V=1$。")
    check("去图未读入：括号里带读图内容的不删",
          not strip_figure_unread_note(_fu2) and "图未读入" in _fu2.solution,
          repr(_fu2.solution))
    _fu3 = Question(key="t/figunread3", type="detailed_answer", stem="x", answer="见解析",
                    solution=r"由对称性，$EF\parallel AB$。（图未读入，依据题干求解）设棱长为 $1$。")
    check("去图未读入：夹在中间的也删、前后文字不动",
          strip_figure_unread_note(_fu3)
          and _fu3.solution.startswith("由对称性") and _fu3.solution.endswith("设棱长为 $1$。"),
          repr(_fu3.solution))

    # MIGRATE 落单的 `$$`：**恰好一个**才删；3 个（说明还丢过公式）不动；
    # 成对的 `$$…$$` 不归这条管（那是风格，不是错）。
    _dd = Question(key="t/dd2", type="fill_in_blank",
                   stem=r"则椭圆 $\Gamma$ 的离心率为 $$ \fillin[$\frac{\sqrt{3}}{2}$]。",
                   answer="")
    check("MIGRATE 落单 `$$`：删掉且不留双空格",
          strip_lone_double_dollar(_dd) and "$$" not in _dd.stem
          and _dd.stem == r"则椭圆 $\Gamma$ 的离心率为 \fillin[$\frac{\sqrt{3}}{2}$]。",
          repr(_dd.stem))
    check("MIGRATE 落单 `$$`：幂等（再跑一次不报改动）",
          not strip_lone_double_dollar(_dd), repr(_dd.stem))
    _dd2 = Question(key="t/dd3", type="fill_in_blank", stem="$a$$ + $$b$", answer="")
    check("MIGRATE 落单 `$$`：3 个时**不动**（还丢过公式，得回原卷看）",
          not strip_lone_double_dollar(_dd2), repr(_dd2.stem))
    _dd3 = Question(key="t/dd4", type="fill_in_blank", stem="$$x=1$$", answer="")
    check("MIGRATE 落单 `$$`：成对的 `$$…$$` 不算落单，不动",
          not strip_lone_double_dollar(_dd3), repr(_dd3.stem))

    # MIGRATE 数学里的 `//`：只改数学段，正文里的不动；`a//b` 要留空格
    _sp = Question(key="t/slash1", type="detailed_answer",
                   stem=r"$DE // BC$，且 $a//b$。", answer="见解析")
    fix_slash_parallel(_sp)
    check("数学里的 `//` 改 `\\parallel`（a//b 不会拼成 \\parallelb）",
          _sp.stem == r"$DE \parallel BC$，且 $a \parallel b$。", repr(_sp.stem))
    _sp4 = Question(key="t/slash4", type="detailed_answer",
                    stem=r"$AP\,\mbox{ // } BC$", answer="见解析")
    fix_slash_parallel(_sp4)
    check("`\\mbox{}` 里的 `//` 直接换成数学 `\\parallel`（文本模式不认数学命令）",
          _sp4.stem == r"$AP\, \parallel  BC$", repr(_sp4.stem))
    _sp2 = Question(key="t/slash2", type="detailed_answer",
                    stem="见 https://example.com/a//b 这里正文的 // 不算平行号",
                    answer="见解析")
    check("正文里的 `//`（URL）不动", not fix_slash_parallel(_sp2), repr(_sp2.stem))
    _sp3 = Question(key="t/slash3", type="single_choice",
                    stem=r"$l_1 // l_2$", answer="A",
                    options=[Option("A", r"$a // b$"), Option("B", r"$c\parallel d$")])
    fix_slash_parallel(_sp3)
    check("选项里的 `//` 也改", _sp3.options[0].text == r"$a \parallel b$",
          repr(_sp3.options[0].text))

    # MIGRATE「解答题答案栏统一见解析」：解析栏有推导才收口，答案栏是唯一载体的不动
    _u1 = Question(key="t/unify1", type="detailed_answer", stem="求 $f(x)$ 的极值。",
                   answer="(1) $1$；(2) $-1$", solution="对 $f(x)$ 求导得 $f'(x)=2x$，\
故极大值为 $1$，极小值为 $-1$。")
    check("MIGRATE 解答题答案栏：解析有推导 → 收口成「见解析」",
          unify_detailed_answer(_u1) and _u1.answer == "见解析", repr(_u1.answer))
    _u2 = Question(key="t/unify2", type="detailed_answer", stem="解不等式。",
                   answer="$x>2$", solution="解析无")
    check("MIGRATE 解答题答案栏：解析空着 → **不动**（答案栏是唯一载体，动了就是丢信息）",
          not unify_detailed_answer(_u2) and _u2.answer == "$x>2$", repr(_u2.answer))
    _u3 = Question(key="t/unify3", type="detailed_answer", stem="见解析样。",
                   answer="见解析", solution="推导略。")
    check("MIGRATE 解答题答案栏：已经是「见解析」→ 不报改动",
          not unify_detailed_answer(_u3), repr(_u3.answer))

    _q = Question(key="t/fill3", type="fill_in_blank", stem="求 $b$。", answer="")
    check("补填空位：没答案就不补（免得造出永远填不上的空位）",
          not ensure_fillin(_q), repr(_q.stem))

    _q = Question(key="t/foot2", type="detailed_answer", stem="求 $x$。",
                  solution="由题意得 $x=1$。\n\n数学试题 第2页 共4页")
    strip_running_head(_q)
    check("去页脚：解析里也清", _q.solution.strip() == "由题意得 $x=1$。",
          repr(_q.solution))

    # 机检新轴：`第N页（共M页）` 这一档页眉，老规则只认到「页」字，被 `(共4页)` 挡住
    _q = Question(key="t/foot3", type="detailed_answer",
                  stem=r"设 $A=\{1,2\}$，求 $A\cap B$。" "\n\n" r"数学试题 第2页(共4页)",
                  answer="见解析")
    strip_running_head(_q)
    check("去页脚：带「(共N页)」的整行页眉删掉",
          _q.stem == r"设 $A=\{1,2\}$，求 $A\cap B$。", repr(_q.stem))

    _q = Question(key="t/foot4", type="fill_in_blank",
                  stem="则满足 $x^2<4$ 的 $x$ 有第 3 页（共 4 页）几个？\n\\fillin[3]",
                  answer="3")
    strip_running_head(_q)
    check("去页脚：页眉**混在正文同一行**时整行保留（宁可漏删不误删）",
          "第 3 页（共 4 页）" in _q.stem, repr(_q.stem))

    _q = Question(key="t/foot5", type="detailed_answer",
                  stem="已知 $f(x)=x^2$。\n\n高三基础测试 数学 试题卷 第5页（共6页）",
                  answer="见解析")
    strip_running_head(_q)
    check("去页脚：「卷名＋页码」整行删（前缀 24 字内、不含 $）",
          _q.stem == "已知 $f(x)=x^2$。", repr(_q.stem))

    # 机检剩 120 道：**下一节的卷首说明**被粘在题干末尾。老正则只认
    # 「本题共 N 小题」，漏了「本大题共 N 小题」和「解答应(该|时)写出」，
    # 整行 match 不上，于是「四、解答题：…」留在题干里一起印到卷面上。
    _q = Question(key="t/foot6", type="fill_in_blank",
                  stem="则 $a=$ \\fillin[1]。\n\n"
                       "四、解答题：本大题共 5 小题，共 77 分。"
                       "解答应写出文字说明、证明过程或演算步骤。",
                  answer="1")
    strip_running_head(_q)
    check("去页脚：下一节的卷首说明整行删（本大题共/解答应写出）",
          "四、解答题" not in _q.stem and _q.stem.startswith("则 $a=$"),
          repr(_q.stem))

    # **控制样本**：真正的题目以「四、解答题：」开头、后面带数学 → 不许删
    _q = Question(key="t/foot7", type="detailed_answer",
                  stem="四、解答题：已知集合 $A=\\{1,2\\}$，求 $A\\cup B$。",
                  answer="见解析")
    strip_running_head(_q)
    check("去页脚：以节标题开头但含数学的真题干**不动**",
          _q.stem.startswith("四、解答题：已知集合"), repr(_q.stem))

    _q = Question(key="t/semi2", type="fill_in_blank",
                  stem="解集为\\fillin[$(-2,1)$。]。", answer="$(-2,1)$。")
    strip_answer_trailing_semicolon(_q)
    check("答案栏尾部句号去掉：作答位与答案栏**同源**一起改",
          _q.answer == "$(-2,1)$" and _q.stem == "解集为\\fillin[$(-2,1)$]。",
          repr(_q.answer) + " / " + repr(_q.stem))

    _q = Question(key="t/semi3", type="fill_in_blank",
                  stem="两空分别为\\fillin[$1$；$2$。]与\\fillin[$3$。]",
                  answer="$1$；$2$。")
    _old = _q.answer
    strip_answer_trailing_semicolon(_q)
    check("答案栏尾部句号：只砍收尾那一个，多空答案不动第一个空",
          _q.answer == "$1$；$2$" and _old == "$1$；$2$。", repr(_q.answer))

    _q = Question(key="t/semi4", type="fill_in_blank", stem="值为\\fillin[。]", answer="。")
    strip_answer_trailing_semicolon(_q)
    check("答案栏尾部句号：砍完为空就**不动**（答案栏不能被规则清空）",
          _q.answer == "。", repr(_q.answer))

    _q = Question(key="t/src2", type="detailed_answer",
                  stem="已知 $f(x)=x^2$，求最小值。\n\n高三第一次月考 数", answer="见解析")
    _q.meta = {"source_label": "宁夏回族自治区银川一中2026-2027学年高三上学期第一次月考"}
    strip_trailing_source(_q)
    check("出处进 meta：**不覆盖**已有的长出处名（只留 source_in_stem 痕迹）",
          _q.meta["source_label"] == "宁夏回族自治区银川一中2026-2027学年高三上学期第一次月考"
          and _q.meta.get("source_in_stem") == "高三第一次月考 数",
          repr(_q.meta))

    _q = Question(key="t/src3", type="detailed_answer",
                  stem="已知 $f(x)=x^2$，求最小值。\n\n太原一模", answer="见解析")
    _q.meta = {}
    strip_trailing_source(_q)
    check("出处进 meta：meta 里**空着**时才填 source_label",
          _q.meta.get("source_label") == "太原一模", repr(_q.meta))

    # ── 2026-10-28 全库格式体检补的档 ────────────────────────────
    # 老 `_FOOT` 只认「第N页共M页」，实测 176 道页眉页脚只吃到 7 道。
    _q = Question(key="t/ff1", type="detailed_answer", answer="见解析",
                  stem="已知 $f(x)=x^2$。",
                  solution="试卷第 1 页，共 5 页\n所以 $f(x)$ 的最小值是 $0$。")
    check("去页脚：带**逗号**的「第 1 页，共 5 页」整行删",
          strip_running_head(_q) and "共 5 页" not in _q.solution, repr(_q.solution))

    _q = Question(key="t/ff2", type="fill_in_blank", answer="3",
                  stem=r"则 $a=$\fillin[3]。\n\n高三数学试卷参考答案 共6页 第1页")
    strip_running_head(_q)
    check("去页脚：**倒装**（共在前）的页眉整行删",
          "共6页" not in _q.stem, repr(_q.stem))

    _q = Question(key="t/ff3", type="fill_in_blank", answer=r"167",
                  stem="数学试题 第 2 页 (共 5 页)\\fillin[综上所述，共有 $167$ 个]")
    strip_running_head(_q)
    check("去页脚：页脚**后面还挂着作答位**时只删页脚，`\\fillin` 一个字不动",
          _q.stem.startswith(r"\fillin[") and "共 5 页" not in _q.stem, repr(_q.stem))

    _q = Question(key="t/ff4", type="single_choice", answer="B",
                  stem=r"则 $m=\,$\paren[B]",
                  options=[Option("A", r"$\sqrt2$"), Option("B", r"$\sqrt3$"),
                           Option("C", "1"), Option("D", "2")],
                  solution=r"$[e,+\infty)$ $f(x)=\frac{e^x}{ax}-x$，"
                           r"【高三学情检测·数学卷参考答案 第2页(共5页)】 6009C" + "\n"
                           + r"令 $t=x-\ln x$。")
    strip_running_head(_q)
    check("去页脚：**带框卷眉＋书号条码**夹在推导中间时摘掉",
          "6009C" not in _q.solution and "共5页" not in _q.solution
          and r"令 $t=x-\ln x$。" in _q.solution, repr(_q.solution))

    _q = Question(key="t/ff5", type="single_choice", answer="D",
                  stem=r"下列命题正确的是$\paren[D]",
                  options=[Option("A", "$1$"), Option("B", "$2$"), Option("C", "$3$"),
                           Option("D", "$$4$$\n\n二、选择题：本题共 3 小题，每小题 6 分，共 18 分。"
                                            "在每小题给出的四个选项中，有多项符合题目要求。"
                                            "全部选对的得 6 分，部分选对得部分分，有选错的得 0 分。")])
    strip_running_head(_q)
    check("去页脚：**下一大题的栏头说明**串在选项 D 里 → 整行删（词表追不完，改成反向判据）",
          "每小题" not in _q.options[3].text and "$4$" in _q.options[3].text,
          repr(_q.options[3].text))

    _q = Question(key="t/ff6", type="fill_in_blank", answer="3",
                  stem="则满足 $x^2<4$ 的 $x$ 有几个？\n\\fillin[3]\n\n"
                       "人教A版必修第一册第 92 页上的探究与发现")
    strip_running_head(_q)
    check("去页脚：正文里**引用教材页码**的句子不许删",
          "第 92 页" in _q.stem, repr(_q.stem))

    _q = Question(key="t/ff6b", type="single_choice", answer="A",
                  stem=r"则 $a=$\paren[A]",
                  options=[Option(x, "$1$") for x in "ABCD"],
                  solution="不等式化简后为 $a<4$。\n页，共18页\n当且仅当 $a=3$ 取等。")
    strip_running_head(_q)
    check("去页脚：页码被换行**劈成两截**剩下的「页，共18页」整行删",
          "共18页" not in _q.solution and "当且仅当" in _q.solution, repr(_q.solution))

    _q = Question(key="t/ff6c", type="detailed_answer", answer="见解析",
                  stem="求角 $A$。",
                  solution="由余弦定理得 $A=\\frac{\\pi}{3}$。\n数学参考答案及评分细则 （第2页，共4页）。")
    strip_running_head(_q)
    check("去页脚：卷眉行**行尾多粘一个句号**也要整行删（句中句号照旧一票否决）",
          "共4页" not in _q.solution, repr(_q.solution))

    _q = Question(key="t/ff7", type="single_choice", answer="A",
                  stem=r"$z=\mathrm{i}$，则\paren[A]",
                  options=[Option("A", "$1$"), Option("B", "$2$"),
                           Option("C", "$3$"), Option("D", "$4$")],
                  solution="解析无（原册第 1 页只印了答案表，#1 没有【解析】段．）")
    strip_running_head(_q)
    check("🔴 去页脚：我们自己的**「解析无（原册第 N 页…）」注释**不许当页脚删掉",
          _q.solution.startswith("解析无"), repr(_q.solution))

    _q = Question(key="t/ff8", type="single_choice", answer="A",
                  stem=r"$z=\mathrm{i}$，则\paren[A]",
                  options=[Option("A", "$1$"), Option("B", "$2$"),
                           Option("C", "$3$"), Option("D", "$4$")],
                  solution="QQ 教师群：965672919\n版权声明：本试题卷为华中师范大学出版社正式出版物，"
                           "版权所有，盗版必究。\n3 亿人都在用的扫描 App\n由 $z^2=-1$ 选 A。")
    strip_running_head(_q)
    check("去页脚：**群号／版权声明／扫描 App 水印**整行删，解析正文留下",
          _q.solution.strip() == "由 $z^2=-1$ 选 A。", repr(_q.solution))

    _q = Question(key="t/ec1", type="single_choice", answer="A",
                  stem=r"双曲线 $C$ 的离心率为\paren[A]",
                  options=[Option("A", r"$\sqrt2$"), Option("B", r"$\sqrt3$"),
                           Option("C", "2"), Option("D", r"$2\sqrt2$")],
                  solution="双曲线 $C$ 的离心率为\nA。$\\sqrt2$ B。$\\sqrt3$ C。2 D。$2\\sqrt2$\n"
                           "依题意 $b/a=1$，所以 $e=\\sqrt2$。")
    check("去重抄：解析开头的**题干＋选项**整块删，真解析不动",
          strip_solution_echo(_q) and _q.solution.startswith("依题意"), repr(_q.solution))

    _q = Question(key="t/ec2", type="single_choice", answer="A",
                  stem=r"则\paren[A]",
                  options=[Option("A", r"$\sqrt2$"), Option("B", r"$\sqrt3$"),
                           Option("C", "2"), Option("D", "3")],
                  solution="A。当 $a<0$ 时不成立，故 A 错误；\nB。由 $a>0$ 得成立，故 B 正确。")
    check("去重抄：**逐项分析**（「A。……故 A 错误」）不是重抄，不许吃",
          not strip_solution_echo(_q), repr(_q.solution))

    _q = Question(key="t/ec3", type="single_choice", answer="B",
                  stem=r"则 $M=\sqrt{y-x}+\sqrt{z-y}$ 的最大值是\paren[B]",
                  options=[Option("A", "0"), Option("B", r"$2+1$"),
                           Option("C", r"$2\sqrt2$"), Option("D", "3")],
                  solution="则 $M=\\sqrt{y-x}+\\sqrt{z-y}$ 的最大值是\nA。0 B。$2+1$\n"
                           "C。2，2\nD。3\n【答案】B")
    check("去重抄：选项列表**只吃了一半**就对不上原文 → 整块不动（宁可漏吃）",
          not strip_solution_echo(_q), repr(_q.solution))

    _q = Question(key="t/ak1", type="detailed_answer", answer="见解析",
                  stem="已知函数 $f(x)$。",
                  solution="炎德·英才大联考雅礼中学 2026 届高三月考试卷(四)\n数学参考答案\n"
                           "注意事项：\n题号 1 2 3 4 5 6 7 8\n答案 A C B D D A B B\n"
                           "解：(1) 由 $f'(x)=0$ 得 $x=1$。")
    check("去卷首块：答案册封面（卷名／参考答案／题号答案对照表）整块删",
          strip_answer_key_head(_q) and _q.solution.startswith("解：(1)"), repr(_q.solution))

    _q = Question(key="t/ak2", type="detailed_answer", answer="见解析",
                  stem="甲、乙、丙三名教师分配到四个地区。",
                  solution="把另外 5 名教师记为其余教师。因为甲和乙不能同时去，且甲、丙必须同去或同不去，"
                           "分三类计数。\n第一类，甲、丙同去。")
    check("🔴 去卷首块：真题解析开头「把另外 5 名教师记为…因为…」带「教师」**不许误吃**",
          not strip_answer_key_head(_q), repr(_q.solution))

    _q = Question(key="t/ak3", type="detailed_answer", answer="见解析",
                  stem="安排三名主力队员。",
                  solution="三名主力队员必须分别占据第一、三、五位置，有\n\\[\n3!\n\\]\n种安排。")
    check("🔴 去卷首块：「第一、三、五位置」这种序数列举**不许误吃**",
          not strip_answer_key_head(_q), repr(_q.solution))

    _q = Question(key="t/ak4", type="detailed_answer", answer="见解析",
                  stem="已知 $f(x)=x+\\sin x$。",
                  solution="【锤子数学解析】$\\because x\\in\\mathbb{R}$，$\\therefore f(x)$ 为奇函数。")
    strip_answer_key_head(_q)
    check("去卷首块：解析开头的**机构品牌前缀**摘掉",
          _q.solution.startswith("$\\because"), repr(_q.solution))

    _q = Question(key="t/ak5", type="detailed_answer", answer="见解析",
                  stem="在 $\\triangle ABC$ 中，求角 $A$。",
                  solution="【答案及评分细则】（17分）\n\n解：(1) 由余弦定理，得 $a^2=b^2+c^2$。")
    strip_answer_key_head(_q)
    check("去卷首块：「【答案及评分细**则**】（17分）」不许被否决表里的「则」挡住",
          _q.solution.startswith("解：(1)"), repr(_q.solution))

    # ── 解析开头的栏目标记 ──────────────────────────────────
    _q = Question(key="t/tg1", type="single_choice", answer="B",
                  stem=r"则 $a=$\paren[B]",
                  options=[Option(x, "$1$") for x in "ABCD"],
                  solution="【解析】由题意得 $a=1$，故选 B。")
    strip_solution_tags(_q)
    check("去标记：「【解析】」这种纯栏目名删掉，讲解一个字不动",
          _q.solution == "由题意得 $a=1$，故选 B。", repr(_q.solution))

    _q = Question(key="t/tg2", type="single_choice", answer="A",
                  stem=r"则 $a=$\paren[A]",
                  options=[Option(x, "$1$") for x in "ABCD"],
                  solution="【答案】A\n\n因为 $f(x)$ 为奇函数，故选 A。")
    strip_solution_tags(_q)
    check("去标记：「【答案】X」与答案栏一致 → 是重复，连值一起删",
          _q.solution.startswith("因为"), repr(_q.solution))

    _q = Question(key="t/tg3", type="single_choice", answer="A",
                  stem=r"则 $a=$\paren[A]",
                  options=[Option(x, "$1$") for x in "ABCD"],
                  solution="【答案】BCD\n\n画图即知。")
    strip_solution_tags(_q)
    check("🔴 去标记：「【答案】X」与答案栏**不一致**时一个字不动（那是答案的唯一载体）",
          _q.solution.startswith("【答案】BCD"), repr(_q.solution))

    _q = Question(key="t/tg4", type="detailed_answer", answer="见解析",
                  stem="求 $f(x)$ 的单调区间。",
                  solution="【小问 1 详解】\n因为 $f'(x)>0$，单调递增。\n\n【小问 2 详解】\n略。")
    strip_solution_tags(_q)
    check("去标记：「【小问 1 详解】」这种**分段标题**不许动",
          "【小问 1 详解】" in _q.solution, repr(_q.solution))

    _q = Question(key="t/tg5", type="single_choice", answer="C",
                  stem=r"则 $a=$\paren[C]",
                  options=[Option(x, "$1$") for x in "ABCD"],
                  solution="【解析】")
    strip_solution_tags(_q)
    check("去标记：整条解析只有栏目名 → 按唯一口径写「解析无」",
          _q.solution == "解析无", repr(_q.solution))

    _q = Question(key="t/un1", type="single_choice", answer="A",
                  stem=r"若 $a>0$，则 DE∥平面 α，$b≥0$ 且 A∩B 非空，选\paren[A]",
                  options=[Option(x, "$1$") for x in "ABCD"])
    unicode_math_to_tex(_q)
    check("裸符号进数学模式：正文里的 ∥、∩ 包上 $…$",
          "DE$\\parallel$平面" in _q.stem and "A$\\cap$B" in _q.stem, repr(_q.stem))
    check("🔴 裸符号：**已经在 `$…$` 里的** `$b≥0$` 一个字不动",
          "$b≥0$" in _q.stem, repr(_q.stem))

    _q = Question(key="t/un2", type="detailed_answer", answer="见解析",
                  stem="统计表如下，其中“√”表示购买，“×”表示未购买。")
    unicode_math_to_tex(_q)
    check("裸符号：图例里的引号符号不做数学化（整类不碰）",
          "“√”表示购买" in _q.stem, repr(_q.stem))

    _q = Question(key="t/un3", type="detailed_answer", answer="\u89c1\u89e3\u6790",
                  stem="\u6c42\u8303\u56f4\u3002",
                  solution="\u2234$0<B<1$\u21d2$\\frac{1}{2}$\uff0c\u4e14 $a$\u2264$b$\uff0ca\u22a5\u2225b")
    unicode_math_to_tex(_q)
    check("\U0001F534 \u88f8\u7b26\u53f7\uff1a\u7edd\u4e0d\u5141\u8bb8\u9020\u51fa\u76f8\u90bb\u53cc\u7f8e\u5143 `$\u2026$$\u2026$`\uff08\u4f1a\u541e\u6389\u540e\u9762\u6574\u6bb5\u6b63\u6587\uff09",
          "$$" not in _q.solution and "\\Rightarrow" in _q.solution, repr(_q.solution))



    _q = Question(key="t/al1", type="detailed_answer", answer="见解析",
                  stem=r"求 $|AF|\cdot|BF|$。",
                  solution="又\n\n" + r"\begin{align*}" + "\n"
                           + r"|AF| \cdot |BF|" + "\n" + r"&= 9 \\" + "\n"
                           + r"&= 12" + "\n" + r"\end{align*}" + "\n\n成立。")
    align_to_aligned(_q)
    check("align* 改规范行间：换成 \\\\[ \\\\begin{aligned}…\\\\end{aligned} \\\\]",
          r"\begin{aligned}" in _q.solution and "align*" not in _q.solution
          and _q.solution.count(r"\[") == _q.solution.count(r"\]")
          and r"&= 12" in _q.solution, repr(_q.solution))

    _q = Question(key="t/dd1", type="detailed_answer", answer="见解析",
                  stem="求 $|AM|$。", solution="于是\n$$|AM|^2=16.$$\n令 $s=2t^2+8t+16$。")
    check("双美元改行间：`$$…$$` → `\\[ … \\]`",
          double_dollar_to_display(_q) and "$$" not in _q.solution
          and _q.solution.count("\\[") == _q.solution.count("\\]"), repr(_q.solution))

    _q = Question(key="t/dp1", type="detailed_answer", answer="见解析",
                  stem=r"若 $c=\sqrt{3}$，，求面积。")
    check("重复标点归一：`，，` → `，`",
          collapse_double_punct(_q) and _q.stem.endswith(r"若 $c=\sqrt{3}$，求面积。"),
          repr(_q.stem))

    _q = Question(key="t/dp2", type="detailed_answer", answer="见解析",
                  stem=r"已知 $a_1=1$，，公比 $q=2$。")
    collapse_double_punct(_q)
    check("重复标点归一：数学式**外面**的重复标点收掉，式子本身不动",
          _q.stem == r"已知 $a_1=1$，公比 $q=2$。", repr(_q.stem))

    # ── 解析里的步骤分与点线（台账 D09 翻案）──────────────────────
    _q = Question(key="t/ss1", type="detailed_answer", answer="见解析",
                  stem=r"已知函数 $f(x)=x^2$。",
                  solution="由题意得 $f'(x)=2x$。 ……（6分）\n\n"
                           "（2）所以 $a=1$，…… 4分\n\n"
                           "（本小题满分 13 分）\n成立； 9分\n12分")
    strip_step_scores(_q)
    check("去步骤分：括号分、点线分、满分头、行尾裸分一起删",
          "分" not in _q.solution.split("由题意得")[1].replace("满分", "")
          and "……" not in _q.solution and _q.solution.startswith("由题意得 $f'(x)=2x$。"),
          repr(_q.solution))

    _q = Question(key="t/ss2", type="detailed_answer", answer="见解析",
                  stem=r"解：$f(x)=1$。　……………………………………………………5分" + "\n" + r"所以 $f(x)>0$。",
                  solution=r"$f(x)=1$。　……………………………………………………5分" + "\n" + r"所以 $f(x)>0$。")
    strip_step_scores(_q)
    check("去步骤分：全角空格＋长点线＋分数整条带走，不留秃点线",
          "…" not in _q.solution and "$f(x)>0$" in _q.solution and "$f(x)>0$" in _q.stem,
          repr(_q.solution) + " / " + repr(_q.stem))

    _q = Question(key="t/ss3", type="single_choice", answer="C",
                  stem=r"某次考试（满分 150 分）成绩如下。",
                  options=[Option(x, "$%d$" % i) for i, x in enumerate("ABCD", 1)],
                  solution=r"由 $P=\frac{1}{2}$ 得答案 C。")
    check("🔴 去步骤分：题干里的「（满分 150 分）」是题目内容，**不许**删",
          not strip_step_scores(_q) and "满分 150 分" in _q.stem, repr(_q.stem))

    _q = Question(key="t/ss4", type="detailed_answer", answer="见解析",
                  stem=r"已知 $a>0$。",
                  solution=r"所以 $a=1$。 ……12" + "\n\n" + r"分" + "\n" + r"令 $t=1$。")
    strip_step_scores(_q)
    check("🔴 去步骤分：点线后的分数被换行劈成「……12／／分」也要删干净",
          "分" not in _q.solution and "令 $t=1$" in _q.solution, repr(_q.solution))

    _q = Question(key="t/is1", type="fill_in_blank", answer="2",
                  stem="①　所以 $a=1$，为　\\fillin[2]。",
                  solution="　若 $a=1$，则成立。")
    strip_ideographic_space(_q)
    check("去全角空格：56 处 U+3000 全部清掉（题干／解析／选项）",
          "\u3000" not in _q.stem and "\u3000" not in _q.solution
          and _q.stem.startswith("①所以"), repr(_q.stem) + " / " + repr(_q.solution))

    # ── 句末半角句点：紧跟汉字那一种（H24 抓的盲区）─────────────────
    _q = Question(key="t/dot1", type="single_choice", answer="B",
                  stem=r"则 $a$，$b$ 满足 $a<b$.因此选 B。",
                  options=[Option(x, "$%d$" % i) for i, x in enumerate("ABCD", 1)],
                  solution=r"取 $a=1$，$b=2$.又 $\frac{1}{2}=0.5$.故 $a<b$。")
    sentence_period(_q)
    check("句点后面紧跟汉字 → 改成句号（题干与解析都改）",
          "满足 $a<b$。因此" in _q.stem and "b=2$。又" in _q.solution,
          repr(_q.stem) + " / " + repr(_q.solution))
    check("🔴 小数点不受影响：`0.5` 还是 `0.5`",
          "0.5" in _q.solution, repr(_q.solution))

    _q = Question(key="t/dot2", type="single_choice", answer="A",
                  stem=r"复数 $z$ 对应的点位于",
                  options=[Option("A", "第一象限"), Option("B", "第二象限")],
                  solution=r"A.第一象限对；B.第二象限错。10\%.测试 不改。")
    sentence_period(_q)
    check("🔴 字母编号的选项列表 `A.第一象限` **不许**被改成 `A。`",
          "A.第一象限" in _q.solution and "B.第二象限" in _q.solution
          and "10\\%." in _q.solution, repr(_q.solution))

    _q = Question(key="t/dot3", type="fill_in_blank", answer="$[1,3)$",
                  stem=r"解集为 $[1,3)$.则 $a=1$。",
                  solution=r"分情况 $\begin{cases}1.a\\ 2.b\end{cases}$。成立。")
    sentence_period(_q)
    check("数学式收尾 `$` 后的句点改成句号，式子里的点一个不动",
          "$[1,3)$。则" in _q.stem and r"1.a" in _q.solution and r"2.b" in _q.solution,
          repr(_q.stem) + " / " + repr(_q.solution))

    # ── 题干 enumerate ↔ 答案 ①②③ 对不上（H23 抓的「没法作答」）──────
    _enum = ("给出下列四个命题：\n\\begin{enumerate}\n\\item 甲；\n\\item 乙；\n"
             "\\item 丙；\n\\item 丁。\n\\end{enumerate}\n其中正确的命题是\\fillin[$②③④$]。")
    _q = Question(key="t/enum1", type="fill_in_blank", answer="$②③④$", stem=_enum,
                  solution="命题①不正确；命题②正确。")
    check("答案写①②③、题干却只有 enumerate → 题干换成 ①②③",
          align_enumerate_labels(_q) and "\\begin{enumerate}" not in _q.stem
          and "① 甲" in _q.stem and "④ 丁" in _q.stem
          and r"\fillin[$②③④$]" in _q.stem, repr(_q.stem))

    _q = Question(key="t/enum2", type="detailed_answer", answer="见解析",
                  stem="解下列各题：\n\\begin{enumerate}\n\\item 求 $a$；\n\\item 求 $b$。\n\\end{enumerate}",
                  solution="（1）$a=1$；（2）$b=2$。")
    check("🔴 小问用的 enumerate（答案不是圈号）**不许**被改",
          not align_enumerate_labels(_q) and "\\begin{enumerate}" in _q.stem,
          repr(_q.stem))

    _q = Question(key="t/enum3", type="fill_in_blank", answer="$①③$",
                  stem="① 甲；② 乙；③ 丙。正确的是\\fillin[$①③$]。",
                  solution="①对。")
    check("🔴 题干本来就有圈号的不动", not align_enumerate_labels(_q), repr(_q.stem))

    _q = Question(key="t/enum4", type="fill_in_blank", answer="$①②$",
                  stem="\\begin{enumerate}\\item[(i)] 甲；\\item[(ii)] 乙。\\end{enumerate}"
                       " 正确的是\\fillin[$①②$]。", solution="")
    check("🔴 `\\item[...]` 自定义标号的不硬拆", not align_enumerate_labels(_q),
          repr(_q.stem))

    # ── 改过正文里的 TikZ → 图登记跟着改（不然出卷子换不上图）──────────
    from .schema import Figure
    from .latex_ir import tikz_id as _tid

    _tk_src = ("\\begin{tikzpicture}\n\\draw (0,0)--(2,0);\n"
               "\\node at (1,1) {\\(A\\)};\n\\end{tikzpicture}")
    _q = Question(key="t/tz1", type="detailed_answer", answer="见解析",
                  stem="如图，" + _tk_src + "，求 $AB$。", solution="略。",
                  figures=[Figure(id=_tid(_tk_src), kind="tikz", tikz=_tk_src,
                                  source="tikz")])
    check("行内公式规则改写了图里的 `\\(…\\)`（前提）", unify_inline_math(_q))
    check("改完登记源与正文**逐字一致**", _resync_tikz(_q)
          and _q.figures[0].tikz == _tk_src.replace("\\(A\\)", "$A$"), repr(_q.figures[0].tikz))
    check("源码变了 id 跟着变", _q.figures[0].id == _tid(_q.figures[0].tikz),
          _q.figures[0].id)
    check("同步幂等", not _resync_tikz(_q))

    # 反例一：图在**解析**里（题干没有 tikz）——登记项一个都不许丢
    _q = Question(key="t/tz2", type="detailed_answer", answer="见解析",
                  stem="求 $AB$。", solution="如图：" + _tk_src,
                  figures=[Figure(id=_tid(_tk_src), kind="tikz", tikz=_tk_src)])
    check("🔴 题干没有 tikz 时不动登记（图在解析里）",
          not _resync_tikz(_q) and len(_q.figures) == 1, repr(len(_q.figures)))

    # 反例二：位图登记原样保留，别按正文重算
    _q = Question(key="t/tz3", type="detailed_answer", answer="见解析",
                  stem="如图，" + _tk_src + "\\includegraphics[width=6cm]{abc.png}",
                  solution="略。",
                  figures=[Figure(id="abc.png", kind="bitmap", source="tikz-original",
                                  width="6cm"),
                           Figure(id="tikz-old", kind="tikz", tikz="\\begin{tikzpicture}\\end{tikzpicture}")])
    _resync_tikz(_q)
    check("🔴 位图的 id/来源/宽度不动", _q.figures[0].id == "abc.png"
          and _q.figures[0].source == "tikz-original" and _q.figures[0].width == "6cm",
          repr([(f.id, f.kind) for f in _q.figures]))
    check("位图在前、tikz 在后（顺序不乱）", [f.kind for f in _q.figures] == ["bitmap", "tikz"],
          repr([(f.id, f.kind) for f in _q.figures]))

    # ── 直方图纵轴标题被 OCR 吃掉命令头 ────────────────────────────
    _tk = ("如图，\\begin{tikzpicture}\\begin{axis}[width=6cm,"
           "xmin=90, xmax=132, ymin=0, ymax=0.045]"
           "\\addplot coordinates {(95,0.002) (100,0.012)};"
           "\\draw[->] (axis cs:90,0) -- (axis cs:90,0.045);\n;\n"
           "{$\\frac{\\text{频率}}{\\text{组距}}$};\n\\end{axis}\\end{tikzpicture}，则……")
    _q = Question(key="t/tf1", type="fill_in_blank", answer="$\\sqrt{2}$",
                  stem="椭圆长半轴 $a=2$，短半轴 $b=\\sqrt{2}$，则焦半距为\\fillin[$\\sqrt{2}$]。",
                  solution="焦半距 $c=\\sqrt{a^2-b^2}=\\sqrt{2}$。")
    fix_half_focal_term(_q)
    check("术语订正：「焦半距」改成「半焦距」（题干与解析都改，式子一个字不动）",
          "半焦距" in _q.stem and "半焦距" in _q.solution and "焦半距" not in _q.stem
          and r"$c=\sqrt{a^2-b^2}=\sqrt{2}$" in _q.solution, repr(_q.stem))
    check("🔴 术语订正幂等", not fix_half_focal_term(_q), repr(_q.solution))

    from .schema import Figure
    _q = Question(key="t/tk1", type="detailed_answer", answer="见解析", stem=_tk,
                  figures=[Figure(id="tikz-x", kind="tikz", tikz=_tk,
                                  width="0.9\\linewidth")])
    check("无主的「频率/组距」片段被补成轴顶的节点（题干与图登记一起改）",
          restore_hist_yscale_label(_q)
          and r"\node[anchor=south east, inner sep=1pt] at (axis cs:90,0.045)" in _q.stem
          and r"{$\frac{\text{频率}}{\text{组距}}$};" in _q.stem
          and _q.figures[0].tikz == _q.stem
          and _q.figures[0].id.startswith("tikz-") and _q.figures[0].id != "tikz-x"
          and "\n;\n" not in _q.stem, repr(_q.stem)[:200])
    check("🔴 改完再过一遍不重复插（幂等）",
          not restore_hist_yscale_label(_q), repr(_q.stem)[:120])

    _q = Question(key="t/tk2", type="detailed_answer", answer="见解析",
                  stem="\\begin{tikzpicture}\\begin{axis}[width=6cm]"
                       "\\addplot coordinates{(0,0)};\n"
                       "{$\\frac{\\text{频率}}{\\text{组距}}$};\n\\end{axis}\\end{tikzpicture}")
    check("🔴 轴上没写 xmin/ymax、推不出位置的**不动**（不猜坐标）",
          not restore_hist_yscale_label(_q), repr(_q.stem)[:120])

    # ── 小问的小问：行首 (i)(ii) → 嵌套 enumerate（两层）──────────────
    _q = Question(key="t/nest", type="detailed_answer", answer="见解析",
                  stem="已知数列。\n(1) 证明；\n(2) 记 $S_n(1)$。\n(i) 求 $S_n(1)$；\n(ii) 证明。")
    _fired = normalize(_q, MIGRATE)
    check("小问的小问改成嵌套 enumerate",
          "小问的小问改用嵌套 enumerate" in _fired
          and _q.stem.count("\\begin{enumerate}") == 2
          and _q.stem.count("\\end{enumerate}") == 2
          and "(i)" not in _q.stem and "(ii)" not in _q.stem
          and "S_n(1)" in _q.stem, repr(_q.stem))
    check("🔴 嵌套迁移幂等（再跑一遍不动）",
          not normalize(_q, MIGRATE), repr(_q.stem))

    _q = Question(key="t/nest2", type="detailed_answer", answer="见解析",
                  stem=("\\begin{enumerate}\n\\item 第一问；\n\\item 第二问。\n"
                        "(i) 小问一；\n(ii) 小问二。\n\\end{enumerate}"))
    normalize(_q, MIGRATE)
    check("已有顶层 enumerate 时只加第二层",
          _q.stem.count("\\begin{enumerate}") == 2
          and _q.stem.count("\\item") == 4, repr(_q.stem))

    # 编号不连续 / 单个 (i) 不动——不能把正文当分问
    _q = Question(key="t/nest3", type="detailed_answer", answer="见解析",
                  stem="\\begin{enumerate}\n\\item 正文。\n(iii) 只有一条。\n\\end{enumerate}")
    check("单个/不连续的 (i) 不动", not normalize(_q, MIGRATE), repr(_q.stem))

    print("normalize 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
