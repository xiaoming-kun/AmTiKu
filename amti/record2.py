#!/usr/bin/env python3
r"""录题 v2：**版面优先 + 模型只做决策 + 校验闸门**。

     PDF ──pagegeom(L0)──▶ 页图 ──ocr(dots.ocr)──▶ 整页文本
          ──27B（**按卷**切题/配对）──▶ 行号区间 + 原文引用
          ──校验闸门──▶ 成品（干净、可溯源）/ 拒收 / 待复核

跟 v1（`record.py`）的根本差别：**v1 是"整页 OCR 一次，再拿正则猜结构"；
v2 是"OCR 只管认字，结构由模型按行号指认，内容一律从原文取"。**
台账 D01–D12 里绝大多数缺陷都出在"猜结构"上。

三条规矩（用户定的，写死在代码里，**不交给模型判**）：

1. **题型按题号定**：1-8 单选、9-11 多选、12-14 填空、15-19 解答。
2. **带图题、带表题一律不录正文**，但**每一道都登记原卷位置**。
   ⚠️ 文字信号（「如图/图象」）**只能当粗筛，不能当判据**——实测纯代数题
   （「图象过点(4,16)」）也会命中。所以粗筛命中的进「待复核」，**先照录**，
   等复核（27B 看图 / 版面检测）有结论再决定，**不许自动跳题**。
3. **题目 ↔ 答案 ↔ 解析一一对应**；没有解析写「解析无」。

两阶段跑（内存不够两个模型同时驻留）：

    python3 -m amti.record2 scan  <一场考试目录>     # 只开 OCR 服务
    python3 -m amti.record2 struct <一场考试目录>    # 只开 27B
    python3 -m amti.record2 run   <一场考试目录>     # 两个都开着时一次跑完
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import lms as L
from . import quality as QLT
from . import normalize as N
from . import ocr
from . import pagegeom as G
from . import record as R
from .schema import Option, Question

# ── 规矩：题号 → 题型（用户 2026-09-18 定）──────────────────────────
BY_NO: dict[int, str] = {}
for _i in range(1, 9):
    BY_NO[_i] = "单选"
for _i in range(9, 12):
    BY_NO[_i] = "多选"
for _i in range(12, 15):
    BY_NO[_i] = "填空"
for _i in range(15, 20):
    BY_NO[_i] = "解答"
TYPE_EN = {"单选": "single_choice", "多选": "multi_choice",
           "填空": "fill_in_blank", "解答": "detailed_answer"}
EN2TYPE = {v: k for k, v in TYPE_EN.items()}

# 粗筛（**不是判据**）：题干提到这些词才可能是图题
FIG_WORD = re.compile(
    r"如图|图中|图象|图像|图形|图所示|如下图|右图|左图|三视图|直观图"
    r"|程序框图|散点图|茎叶图|频率分布直方图|统计图|条形图|扇形图|折线图")
TABLE_WORD = re.compile(r"下表|列联表|统计表|表格|频数分布表|临界值表")

# 清洗用（**只在这里出现一次**，别再散落到别处）
SCORE_HEAD = re.compile(
    r"^\s*(?:[（(]\s*(?:本小题|本题)?\s*(?:满分\s*)?\d{1,3}\s*分\s*[）)]"
    r"|(?:本小题|本题)\s*(?:满分\s*)?\d{1,3}\s*分|满分\s*\d{1,3}\s*分)\s*")
# 页脚**必须带「共 N 页」**——写成可选会把正文里的「第 92 页」当页脚
# （实测把千题册一道题截成了 9 个字）。判据跟 normalize.py 保持同一套。
FOOT = re.compile(r"第\s*\d{1,3}\s*页\s*共\s*\d{1,3}\s*页")
# 卷面印刷坏字当题号：`f1`、`I`、`|`… **后面必须跟空格、空格后是中文或公式**，
# 才认定是题号。要求空格是关键——`f(x)=…` 这种正常开头没有空格，不会被误剪。
# 末了的 `(?:\s*[0-9]{1,2})?` 是为了 `f 1 已知函数` 这种——OCR 有时在
# 坏字母和数字之间插空格。第一次没写这段，只剪掉了 `f`，产物里留了个孤零零的 1。
BROKEN_HEAD = re.compile(
    r"^\s*[fFlI|£¥1]{1,3}(?:\s*[0-9]{1,2})?\s+(?=[\u4e00-\u9fa5$\\])")
OPT_SPLIT = re.compile(r"(?<![A-Za-z0-9])[ABCD]\s*[.．、]\s*")
# 版面家具（不是题目）：小节标题、卷抬头、答题说明
FURNITURE = re.compile(
    r"^\s*#|^\s*[一二三四五六]\s*[、.．]|^第\s*[ⅠⅡⅢIVX]+\s*卷"
    r"|本试卷分|满分\s*\d+\s*分|考试时间|请在答题卡|全部选对|部分选对|有选错"
    r"|答题前|准考证|贴条形码|超出黑色矩形边框|请在各题目的答题区域内作答")
ANSWER_IN_SOL = re.compile(r"故选\s*[:：]?\s*([A-D]{1,4})")
# 会让 **KaTeX 渲染失败**的四种写法。全部来自 v1 那批产物的实测
# （`amti.py accept` 层③ 报的 40 处，逐条看出来的），闸门必须先挡住：
#   `a &lt; -1`        HTML 实体——`<` 被转义了，KaTeX 认不得 `&`
#   `\n\cdot`          字面量 \n——换行被当成命令（双转义那个老问题）
#   `\{ a>0 \atop …}`   `\{` 没闭合
#   `(\tanh x)^'`     先上标后撇号，KaTeX 直接报错
BAD_TEX = [
    (re.compile(r"&(?:lt|gt|amp|quot|nbsp|#\d+);"), "HTML 实体（&lt; 之类）"),
    (re.compile(r"\\n(?![a-zA-Z])"), "字面量 \\n"),
    (re.compile(r"\^\s*['\u2032]"), "先上标后撇号 ^'"),
]

SYS_ASK = """你在给数学题库做**切题**。输入是一整份试卷的 OCR 文本，每行前面有行号，
页与页之间有一行 `=== 第N页 ===`（那一行没有行号，不属于任何题）。

**只判断每道题的边界**，不要改写、补全、解答或纠正原文。

只输出一个 JSON 对象（不要代码块、不要解释）：
{"questions":[{"n":1,"start":5,"end":12,"options":{"A":7,"B":8,"C":9,"D":10},
  "quote":"已知全集为U, 若B∩(C_UA)=∅"}]}

* start/end：**整份卷子连续编号**的行号（含两端），题干和选项都要包进去。
  一道题如果**跨页**（题在某页末尾、选项在下页开头），start/end 要**跨过页标记**，不要切断。
* options：选项字母 → 行号；一行里并排几个选项就都指向那一行；定位不到给 {}，不要编。
* quote：从原文**逐字**摘 10-25 字作为题头，改一个字就算错。
* 考试说明、页脚、答题卡提示、小节标题**都不是题目**。
* 按题号（1~19）给全，**不要漏、不要合并**。
"""

SYS_ANS = """你在给数学题库做**答案与解析的配对**。输入是一整份**答案卷**的 OCR 文本，
每行前面有行号，页与页之间有 `=== 第N页 ===`（没有行号）。

只输出一个 JSON 对象（不要代码块、不要解释）：
{"items":[{"n":15,"answer":"60","start":12,"end":30,"quote":"由正弦定理得"}]}

* n：题号（1~19）。
* answer：这道题的**答案本身**，要短——填空题就是那个值（如 `60`、`√3`），
  选择题就是字母（如 `A`、`CD`）。**答案就是解析开头那串字母/数字时也要单独摘出来。**
  解答题（15~19）没有单一答案就给 ""。找不到明确答案也给 ""，不要拿整段解析充数。
* start/end：这道题的**解析**占的行号（含两端）；跨页要跨过页标记。
* quote：从原文**逐字**摘 10-25 字作为这道题的开头，改一个字就算错。
* ⚠️ **答案汇总表（形如 `1-4: DBDA; 5-8: CBDD`）只是答案，不是解析**。
  解析要取这道题**后面那段逐题讲解**；取不到就留空，**不许拿汇总表充数**
  （实测成都七中：前 8 题的解析全被填成了那一行汇总表）。
* 按题号给全，**不要漏、不要合并**。
"""


# ── 纯函数（自检覆盖）────────────────────────────────────────────────
def norm(s: str) -> str:
    r"""归一化到可比对的形式（去空白、`$`、反斜杠、花括号）。"""
    return re.sub(r"[\s$\\{}]", "", s or "")


def cut_before_quote(text: str, quote: str) -> tuple[str, str]:
    r"""用**已校验的引用**当锚，剪掉题干开头卷面印坏的题号。返回 `(新文本, 剪掉的)`。

    ⚠️ 用引用而不用正则：引用是逐字核对过、必然在原文里的，
    拿它当锚**不会误剪正文**。`BROKEN_HEAD` 只是引用不可用时的兜底。
    """
    q = norm(quote)
    if len(q) < 6 or not text:
        return text, ""
    lines = text.splitlines()
    head = lines[0]
    k = norm(head).find(q[:8])
    if k <= 0 or k > 8:
        return text, ""
    # 找"扁平化后第 k 个字符"在**原串**里的下标。
    # ⚠️ 是 `k + 1` 不是 `k`：`cnt` 从 1 开始数，而 `k` 是 0 基下标。
    # 写成 `k` 会少剪一个字符——实测把 `f1 已知函数…` 剪成了 `1 已知函数…`，
    # 日志却显示"剪坏字 f"（因为它确实只剪了 f）。
    cnt, cut = 0, -1
    for i, ch in enumerate(head):
        if norm(ch):
            cnt += 1
        if cnt == k + 1:
            cut = i
            break
    if cut <= 0:
        return text, ""
    lines[0] = head[cut:]
    return "\n".join(lines), head[:cut]


def split_stem_options(lines: list[str]) -> tuple[str, dict]:
    r"""段落 → `(题干, {A: 文本, …})`。

    **一行里并排四个选项**（`A. 1  B. 2  C. 3  D. 4`）是常态，必须拆开——
    v1 的"数行首有几个 A."把 4 个选项数成 1 个，我把这个错误又犯过一次。
    """
    stem_lines: list[str] = []
    opts: dict[str, str] = {}
    for ln in lines:
        hits = list(OPT_SPLIT.finditer(ln))
        if len(hits) >= 2:
            head = ln[:hits[0].start()].strip()
            if head:
                stem_lines.append(head)
            for k, m in enumerate(hits):
                end = hits[k + 1].start() if k + 1 < len(hits) else len(ln)
                opts[m.group(0)[0]] = ln[m.end():end].strip()
        elif len(hits) == 1 and hits[0].start() <= 2:
            opts[hits[0].group(0)[0]] = ln[hits[0].end():].strip()
        else:
            stem_lines.append(ln)
    return "\n".join(stem_lines).strip(), opts


def clean_fields(stem: str, solution: str, *, qtype: str, opts: dict,
                 quote: str = "") -> tuple[str, str, dict, list[str]]:
    r"""清洗：去题号 → 去分值 → 剪卷面坏字 → 补缺失选项 → fixup。

    ⚠️ **顺序不能反**：`fixup` 必须在所有"剪"的动作**之后**跑。
    写反过一次——日志里明明写着「剪掉卷面坏字 f1」，产物里那个 `f1` 还在，
    因为 `fixup` 的结果是在剪之前算好、后面一直用的是它。
    """
    notes: list[str] = []
    # OCR 把答案册的「### 2. A」标题原样读进来，闸门看见行首 `#` 就当版面家具
    # （`^\s*#`），整卷解析被拒——实测第六套 19 题拒了 11 题。标题只留文字。
    s = re.sub(r"(?m)^\s*#{1,6}\s*", "", stem or "")
    s = re.sub(r"^\s*\d{1,2}\s*[.．、]\s*", "", s)
    s2 = SCORE_HEAD.sub("", s)
    if s2 != s:
        notes.append("去分值")
    s, cut = cut_before_quote(s2, quote)
    if cut:
        notes.append("剪坏字 %r" % cut.strip())
    else:
        m = BROKEN_HEAD.match(s)
        if m:
            notes.append("剪坏字 %r" % m.group(0).strip())
            s = s[m.end():]
    # 选项标签补全：卷面把 `A.` 印成认不出的符号时，OCR 只能读到 B/C/D
    # （A10 第 11 题原图印的是个「£/匚」样的坏字）。**这不是重扫能解决的——
    # 信息在图上就不存在**，只能靠结构推断：选择题必是 A、B、C、D 四个。
    if qtype in ("single_choice", "multi_choice") and \
            set(opts) == {"B", "C", "D"}:
        tail = [x for x in s.splitlines() if x.strip()]
        if len(tail) >= 2 and not tail[-1].rstrip().endswith(("（ ）", "( )", "（）")):
            opts = dict(opts)
            opts["A"] = re.sub(r"^[^A-Da-d]{1,3}\s*", "", tail[-1]).strip()
            s = "\n".join(tail[:-1])
            notes.append("补回 A 选项")
    stem2 = R.fixup(s)
    sol0 = re.sub(r"(?m)^\s*#{1,6}\s*", "", solution or "")
    sol2 = R.fixup(FOOT.sub("", sol0))
    if stem2 != s:
        notes.append("LaTeX修复")
    if sol2 != (solution or ""):
        notes.append("解析去页脚")
    return stem2, sol2, opts, notes


_BS_WS = set(chr(92) + " \t\r\n")     # 「只剩反斜杠和空白」的字符集

#: 填空位：项目规范写法是 `\fillin`；卷面/讲义上是下划线、全角空格括号
BLANK = re.compile(r"\\fillin|＿{2,}|_{3,}|（\s{2,}）|\(\s{2,}\)")
#: 题干里并排出现的选项标签（`A．` `B．`）——选项没切出来时也能据此判"这是选择题"
OPT_TAG = re.compile(r"(?<![A-Za-z0-9])[ABCD]\s*[.．、]")
#: 题干**末尾的空括号**（0–1 个空格）——选择题的作答位，选项丢了它还在
CHOICE_HOLE = re.compile(r"[（(]\s{0,2}[）)]\s*[。.]?\s*$")


def classify_type(stem: str, opts: dict, answer: str, hint: str = "") -> tuple[str, str]:
    r"""**题型由文本定，不由模型定。** 返回 `(题型, 依据)`。

    模型只负责"这一块从哪行到哪行"，题型是看得见的东西：

    1. 有 3 个以上选项（或题干里并排出现 A．B．C．D．）→ 选择题；
       * 答案是多个字母（`BCD`）→ 多选；
       * 答案是单个字母 → 单选；
       * **没答案**（学生版讲义）→ 单选，并标"待核"——单选还是多选，
         题干上真的看不出来，不能猜。
    2. 没有选项、题干末尾是空括号 `（ ）` → 仍是选择题（**选项没认出来**），
       让闸门按"选项 0 个"拒掉、进"未入库"——比静默当成解答题强；
    3. 没有选项、题干里有空位（`\\fillin` / `____` / `（　　）`）→ 填空；
    4. 都没有 → 解答。

    `hint` 是模型给的题型，**只在"有选项但没答案"时**用来区分单选/多选。
    """
    has_opts = len(opts) >= 3 or len(OPT_TAG.findall(stem or "")) >= 3
    ans = (answer or "").strip()
    if has_opts:
        if re.fullmatch(r"[A-D]{2,4}", ans):
            return "multi_choice", "选项 + 答案是多字母"
        if re.fullmatch(r"[A-D]", ans):
            return "single_choice", "选项 + 答案是单字母"
        if hint == "multi_choice":
            return "multi_choice", "选项 + 模型提示（无答案，待核）"
        return "single_choice", "选项 + 无答案（默认单选，待核）"
    if BLANK.search(stem or ""):
        return "fill_in_blank", "题干有空位"
    if CHOICE_HOLE.search(stem or ""):
        # 有作答位、却没有选项 —— 选项在版面上丢了（另一列/图里）。
        # 当成解答题入库会是一道"没有选项的选择题"，所以判选择、交给闸门拒。
        return "single_choice", "题干末尾有空括号（选项没认出来）"
    return "detailed_answer", "无选项、无空位"


def gate(qtype: str, stem: str, opts: dict, answer: str,
         solution: str) -> list[str]:
    r"""校验闸门：**不过就拒收**，不静默入库。返回问题清单（空 = 通过）。"""
    why: list[str] = []
    if not (stem or "").strip():
        why.append("题干为空")
    # 选择题**必须四个选项 A–D**。写成"少于 2 个"会放过"少了 A 选项"这种
    # 真缺陷——A10 第 11 题就是这么漏过去的。
    # 四个是标答；**3 个放行**（OCR 常把某个选项的标签丢掉，我们从题干预末
    # 捞回来的就是 3–4 个）。少于 3 才是真残缺，仍然拒。
    if qtype in ("single_choice", "multi_choice") and len(opts) < 3:
        why.append("选项 %d 个（应为 4）" % len(opts))
    if qtype in ("single_choice", "multi_choice", "fill_in_blank") and \
            len((answer or "").strip()) > 40:
        why.append("客观题答案 %d 字（像整段解析）" % len(answer.strip()))
    if qtype in ("single_choice", "multi_choice") and answer and \
            not re.fullmatch(r"[A-D]{1,4}", answer.strip()):
        why.append("选择题答案是 %r（应为字母）" % answer[:12])
    for txt, tag in ((stem, "题干"), (solution, "解析")):
        if (txt or "").count("$") % 2:
            why.append("%s `$` 不成对" % tag)
        if re.search(r"(?<!\\)%", txt or ""):
            why.append("%s 有裸 %%（会注释掉后面）" % tag)
        if FURNITURE.search(txt or ""):
            why.append("%s 里混着版面家具" % tag)
        if FOOT.search(txt or ""):
            why.append("%s 里还有页脚" % tag)
        for pat, name in BAD_TEX:
            if pat.search(txt or ""):
                why.append("%s 有%s（KaTeX 会报错）" % (tag, name))
        # 数学段里**只剩反斜杠和空白** = 原卷此处印漏了一整个式子（实测 328 宝鸡 #3，
        # 卷面印成「“$ac>bc$” 是        ” 的」）。KaTeX 报 `Unexpected character: '\'`。
        # ⚠️ 必须按 `$` 切段再判，不能直接写正则：`$9$\\` 换行 `$7$` 这种
        #    「闭段$ + 反斜杠 + 开段$」会被跨段配对误判，实测误伤存量表题 35 道；
        #    也不能用 `seg.strip() == ""`——strip() 不去反斜杠，`"\\ "` 永远非空。
        for i, seg in enumerate((txt or "").split("$")):
            if i % 2 and seg and set(seg) <= _BS_WS and "\\" in seg:
                why.append("%s 有只含反斜杠的空数学段（原卷此处印漏，KaTeX 会报错）" % tag)
                break
        # **行间公式的 `\[` / `\]` 不能夹在 `$…$` 里。** 模型常把行内公式的
        # 收尾 `$` 漏掉（写成 `…=2\sqrt2\[`），再靠后面某个 `$` 凑成偶数，
        # 于是「`$` 成对」这条放过去了；可 KaTeX 在段内遇到 `\[` 直接报
        # `Undefined control sequence`（实测：湖南雅礼 #15 的解析就这么进库的，
        # 端到端渲染红了两处）。这里按段判，不跨段配对。
        if QLT.display_in_inline(txt or ""):
            why.append("%s 的 `\\[…\\]` 夹在 `$…$` 里（行内公式漏了收尾 `$`）" % tag)        # **别数 `\{` 和 `\}`**：它们是字面大括号，本来就不必成对
        # （`\left\{ x \right.` 是合法写法，`\{a,b\}` 才是成对）。
        # 真该查的是 `\left` 与 `\right` —— 少了 `\right` 才是真断。
        # 实测：保定 4 道题全被这一条误杀，解析内容其实完整。
        if (txt or "").count(r"\left") != (txt or "").count(r"\right"):
            why.append("%s 的 `\\left` 与 `\\right` 不配平" % tag)
    return why


def covered_pages(lines: list[tuple[int, str, int]], rng) -> list[int]:
    """某道题的行区间覆盖了哪几页（登记位置要用）。"""
    s, e = rng
    return sorted({p for n, _t, p in lines if isinstance(s, int)
                   and isinstance(e, int) and s <= n <= e})


#: 大题标题：`## 一、单选题` / `三、 填空题`
SECTION = re.compile(
    r"^#*\s*[一二三四五六七八]\s*[、.．]\s*(单选题|多选题|填空题|解答题|选择题)")
_SECTION_TYPE = {"单选题": "single_choice", "多选题": "multi_choice",
                 "填空题": "fill_in_blank", "解答题": "detailed_answer"}


def section_types(lines: list[tuple[int, str, int]]) -> list[tuple[int, str]]:
    r"""「行号 → 题型」锚点，来自卷面的大题标题。

    **题型不该靠题号猜**：`BY_NO` 是按新高考 19 题写的；碰到 22 题的老卷子
    （实测 26届拼好卷第六套），第 20–22 题是**真题**，按 1–19 判就成了"越界"，
    30 道题被白扔。而卷面上本来就写着 `## 一、单选题 / ## 二、多选题 /
    ## 三、填空题 / ## 四、解答题`。
    """
    out: list[tuple[int, str]] = []
    for n, t, _p in lines:
        m = SECTION.match((t or "").strip())
        if not m:
            continue
        qt = _SECTION_TYPE.get(m.group(1), "")
        if qt and (not out or out[-1][1] != qt):
            out.append((n, qt))
    return out


def type_at(secs: list[tuple[int, str]], line) -> str:
    r"""某一行落在哪个大题下。"""
    cur = ""
    for n, qt in secs:
        if n > line:
            break
        cur = qt
    return cur


def balanced_slice(idx: dict[int, str], s, e, limit: int = 4) -> tuple[str, int]:
    r"""切一段，**把边界挪到公式配平的地方**。

    模型给的行区间常把 `$…$` / `\(…\)` 切成两半：区间里有 `\(`，右边的 `\)`
    落在下一行。闸门按"`$` 不成对"整题拒——题本身是好的（实测第六套 22 道
    里 8 道这么被拒）。

    往后多带几行直到配平；**遇到下一题的题号就停**，不许吞下一题。
    """
    if not isinstance(s, int) or not isinstance(e, int) or s > e:
        return "", e
    txt, k = "", e
    for k in range(e, e + limit + 1):
        if k not in idx:
            break
        if k > e and re.match(r"^\s*\d{1,2}\s*[.．、]", idx[k]):
            break
        txt = "\n".join(idx[i] for i in range(s, k + 1) if i in idx)
        if txt.count("$") % 2 == 0 and txt.count("\\(") == txt.count("\\)"):
            return txt, k
    return txt, k


def retype_by_no(qs: list, *, book: str = "模拟题") -> dict:
    r"""按题号重判题型（规矩 R1）——**存量清洗用**。

    只改 `type`，改完按新题型**补作答位**（复用 `normalize` 里的规则，
    不在这里另写一套）。**数据不全的不改**，进 `pending` 待重扫：

    * 选择题：必须 4 个选项且答案非空，否则改了就是个"没有选项的选择题"
    * 填空题：题干里得有空位、或者有答案能填进去，否则就是个"没有空位的填空题"
      ——实测 333 道 OCR 把空位丢了、答案也是空的，**改了反而是造破题**

    返回 `{"changed": [...], "pending": [...], "pairs": {(旧,新): 数量}}`。
    """
    import collections
    pairs = collections.Counter()
    changed, pending = [], []
    for q in qs:
        if q.meta.get("book") != book:
            continue
        no = q.meta.get("source_no")
        if not isinstance(no, int) or no not in BY_NO:
            continue
        want = TYPE_EN[BY_NO[no]]
        if q.type == want:
            continue
        opts = len(q.options or [])
        ans = (q.answer or "").strip()
        why = ""
        if want in ("single_choice", "multi_choice"):
            if opts != 4:
                why = "选择题但选项 %d 个" % opts
            elif not ans:
                why = "选择题但没答案"
        elif want == "fill_in_blank":
            if r"\fillin" not in q.stem and not ans:
                why = "填空题但空位和答案都没有"
        # **题干里粘着版面家具的，一律不重判**：实测有一道题的题干里
        # 粘进了整块答案速查表（`2 3 4 5 6 7 8 / C B A C A B D B / 二、多选题…`），
        # 它原本是"解答题"所以规范不查作答位；改成选择题后旧伤立刻暴露。
        # 这种题该去重扫，不该靠改标签"修好"。
        if not why and FURNITURE.search(q.stem or ""):
            why = "题干里粘着版面家具（需重扫）"
        if why:
            pending.append({"key": q.key, "旧": q.type, "新": want, "原因": why})
            continue
        old = q.type
        q.type = want
        # 作答位交给 normalize 的规则，别在这里手写
        for rname in ("补作答题括号", "答案进作答括号", "作答括号跟随答案",
                      "答案进填空位", "去掉残留的空作答括号"):
            r = N.get(rname)
            if r:
                try:
                    r.fn(q)
                except Exception:                          # noqa: BLE001
                    pass
        pairs[(old, want)] += 1
        changed.append(q.key)
    return {"changed": changed, "pending": pending, "pairs": dict(pairs)}


# ── 带模型/文件的部分 ───────────────────────────────────────────────
#: 冷启动重试的等待基数（秒）。自检里置 0，免得为一个用例白等 6 秒。
RETRY_WAIT = 2.0


def est_tokens(s: str) -> int:
    r"""粗估 token 数（**中文不是「2 字符 1 token」**）。

    实测：26届拼好卷答案 260 页、487,593 字，服务端数出来 **301,911
    token**（0.62 字/token）。原来的 `len(doc)//2` 估成 243,796，比真值
    少 19% —— 于是 `ensure_ctx` 以为 262144 的上下文够用，请求发出去当场
    400 `exceed_context_size_error`，整卷白跑。

    公式里的 LaTeX（`\frac{a}{b}`、成串括号）比汉字更费 token，所以取
    0.65 字/token 再留一点余量：估高了只是上下文多占一点，估低了就是整卷
    白跑。
    """
    return int(len(s or "") * 0.65) + 200


def _post(url: str, model: str, msgs: list, *, maxtok: int,
          extra: dict | None = None, timeout: int = 3600) -> dict:
    body = {"model": model, "messages": msgs, "temperature": 0.0,
            "max_tokens": maxtok}
    body.update(extra or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    # **冷启动重试**：模型刚被 JIT 拉起的那几秒，接口会先回 400/503。
    # 等两秒再打一次基本就好了，比让整卷任务失败划算得多。
    #
    # ⚠️ 失败详情**必须在 except 里当场抄走**。`except … as e:` 的 `e` 在这个
    # block 结束时就删掉了（Python 的隐式 `del e`），出了循环再 `e.code`
    # 必然 `UnboundLocalError` —— 实测把「请求 301911 token，超过 262144
    # 上下文」的真话吞成了 "cannot access local variable 'e'"，查了半天。
    fail = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "ignore").strip()[:600]
            except Exception:                                # noqa: BLE001
                detail = ""
            fail = "HTTP %s %s" % (e.code, detail)
            if e.code in (400, 503) and attempt < 2:
                time.sleep(RETRY_WAIT * (attempt + 1))
                continue
            break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            # 连不上 / 超时 / 连接被掐：没有 HTTP 正文可读，只有原因
            fail = "%s: %s" % (type(e).__name__, getattr(e, "reason", e))
            break
    raise RuntimeError("大模型接口调用失败：%s（请求 %d 字符）"
                       % (fail or "未知原因", len(json.dumps(body)))) from None


def grab_json(s: str):
    """抠 JSON：扛住 ```围栏、前后废话、以及被 max_tokens 截断。"""
    if not s:
        return None
    s = re.sub(r"^\s*```(?:json)?|```\s*$", "", s.strip(), flags=re.M)
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    body = m.group(0)
    for cand in (body, body.rstrip().rstrip(",") + "}]}"):
        try:
            return json.loads(cand)
        except ValueError:
            pass
    for key in ("questions", "items"):
        m2 = re.search(r'"%s"\s*:\s*\[(.*)' % key, body, re.S)
        if m2:
            got = []
            for o in re.findall(r"\{[^{}]*\}", m2.group(1)):
                try:
                    got.append(json.loads(o))
                except ValueError:
                    pass
            if got:
                return {key: got}
    return None


def work_of(p) -> Path:
    r"""路径 → 工作区目录。

    ⚠️ **传进来的可能是目录，也可能是个 PDF**，两种都要认。而且
    **目录绝不能拿 `.stem`**：`Path("…/187.湖南长郡中学…").stem` 是 `"187"`
    （`stem` 在**第一个点**就截断了，不是只去后缀）——于是它去找
    `数据/录题/187/pages`，那里恰好有个同名目录、却没有页图，
    最后拿目录去 `fitz.open()`，报一句看不懂的 `FileDataError`（实测踩过）。
    """
    p = Path(p)
    return p if p.is_dir() else R.WORK / p.stem


def v2_dir(pdf) -> Path:
    """v2 的缓存目录。**跟 v1 的 `pages/`、`scan/` 分开**，免得互相踩。"""
    return work_of(pdf) / "v2"


def scan_pdf(pdf: Path, *, force: bool = False) -> list[dict]:
    r"""一份 PDF → 每页文本（**按页**）。结果落在 `v2/txt/`，可续跑。

    识别走 `amti/paddle.py`（PaddleOCR-VL-1.6，逐页）。产出的 rows
    下游直接用：page / img / txt / chars。
    """
    from . import engine
    return engine.get().scan(pdf, work_of(pdf), force=force)
    w = work_of(pdf)
    d = w / "v2"
    (d / "txt").mkdir(parents=True, exist_ok=True)
    imgs = sorted((w / "pages").glob("p???.png"))
    if not imgs:
        if w.is_dir():
            raise RuntimeError("没有页图缓存、也没有 PDF 可渲染：%s" % w)
        imgs = R.pages_of(pdf, w / "pages")
    pages: list[Path] = []
    for p in imgs:
        pages += G.split_spread(p, d / "pages")
    rows = []
    for i, img in enumerate(pages, 1):
        dst = d / "txt" / ("p%02d_%s.txt" % (i, img.stem))
        if dst.exists() and not force:
            t = dst.read_text(encoding="utf-8")
        else:
            t = ocr.ocr_image(img)
            dst.write_text(t, encoding="utf-8")
        rows.append({"page": i, "img": str(img), "txt": str(dst), "chars": len(t)})
    (d / "pages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return rows


def build_doc(rows: list[dict]) -> tuple[str, list[tuple[int, str, int]]]:
    r"""多页文本 → **连续行号的整卷文本**（页标记不占行号）。

    **跨页问题就解决在这里**：题目在页尾、选项在下页开头时，
    模型看到的是连续文本，start/end 自然跨过页标记，不会把选项切掉。
    """
    lines: list[tuple[int, str, int]] = []
    out = []
    for m in rows:
        out.append("=== 第%d页 ===" % m["page"])
        for ln in Path(m["txt"]).read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            lines.append((len(lines) + 1, ln, m["page"]))
            out.append("%3d| %s" % (lines[-1][0], ln))
    return "\n".join(out), lines


def _guard_thinking(d: dict, role: str, maxtok: int) -> None:
    r"""拦「思考把预算吃光、正文一个字没写」——**它不报错，只返回 0 题块**。

    实测（2026-10-28，MLX 版 27B）：LM Studio 的 MLX 引擎不吃
    `reasoning_effort`，模型默认 xhigh 思考，7999 个 token 全在 reasoning 上，
    `finish=length`、`items=[]`，整卷白跑 532 秒。这条守卫把它变成一句
    看得懂的错，指向真正的修法（`amti/lms.py` 的 `ensure_no_think()`）。
    """
    u = d.get("usage") or {}
    total = u.get("completion_tokens") or 0
    think = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    finish = (d.get("choices") or [{}])[0].get("finish_reason")
    if finish == "length" and total and think >= total:
        raise RuntimeError(
            "模型把 %d token 全花在思考上、正文没写出来（%s）。"
            "这是运行时没关思考：MLX 引擎不吃 `reasoning_effort`，"
            "靠模型模板里的 `enable_thinking = false` 才关得掉"
            "（`amti/lms.py` 的 `ensure_no_think()` 会自动补；"
            "补了还这样，就把 maxtok 从 %d 调大或换回 GGUF）。"
            % (total, role, maxtok))


def structure(rows: list[dict], role: str, *, save: Path | None = None,
              model: str = "") -> dict:
    r"""整卷文本 → 模型给的题块/答案块（**带引用，供校验**）。

    `model` 留空用 `R.MODEL`（27B）。抄答案那一路可以传 9B——实测同一块
    答案 9B 快 1.8 倍（324s/7937 字 vs 360s/4857 字），格式照样对。
    """
    doc, lines = build_doc(rows)
    sys_prompt = SYS_ASK if role == "试卷" else SYS_ANS
    # 解析动辄上千字，8000 会**写到一半被截断**（左边花括号开着就断了），
    # 然后被闸门当"不配平"整题拒掉。答案那一路给到 16000。
    maxtok = 16000 if role == "答案" else 8000
    # 上下文要按「文档 + 系统提示 + 输出预留」一起算：只算文档会漏掉输出，
    # 恰好卡在上限时照样 400。不超过上限也由 `ensure_ctx` 兜底报错。
    need = est_tokens(doc) + est_tokens(sys_prompt) + maxtok
    # 上下文不够会直接 400（而且报错只说 Bad Request）。这里按文档长度
    # 自动确保 27B 以足够大的上下文加载，并拿到**当前有效的 identifier**。
    ok, ident, why = L.ensure_ctx(model or R.MODEL, need_tokens=need)
    if not ok:
        raise RuntimeError(why)
    d = _post(R.API, ident,
              [{"role": "system", "content": sys_prompt},
               {"role": "user", "content": doc}],
              maxtok=maxtok,
              extra={"reasoning_effort": "none"})
    _guard_thinking(d, role, maxtok)
    raw = d["choices"][0]["message"].get("content") or ""
    key = "questions" if role == "试卷" else "items"
    items = (grab_json(raw) or {}).get(key) or []
    flat = norm("\n".join(t for _n, t, _p in lines))
    for it in items:
        it["_引用对"] = bool(norm(it.get("quote") or "")) and norm(it["quote"]) in flat
    res = {"role": role, "items": items, "lines": lines,
           "usage": d.get("usage") or {},
           "finish": d["choices"][0].get("finish_reason"), "raw": raw}
    if save:
        save.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


# ── 题目 ↔ 解析 的配对 ────────────────────────────────────────────
#
# **不能只靠题号**。实测的三种现场：
#   ① 合订本：十一套卷各有一套 1–19，`ans_by_n[题号]` 后一个覆盖前一个，
#      第 5 题会配上第 5 套的解析，**一声不吭**；
#   ② 扫描件题号读错（19 读成 1g、11 读成 ll），题号对不上但顺序是对的；
#   ③ 解析缺了几题，块数比题目少。
#
# 所以配对的依据按可信度降级：题号 → 顺序 → 内容单调对齐；都不成立就
# **不配**（写"解析无"），绝不猜。每一对都记下依据，界面上看得见。

#: 题块里抓"像公式/数字/词"的记号，用来算两段文字的重合度
_TOKEN = re.compile(r"\\[A-Za-z]+|[A-Za-z]{2,}|\d+(?:\.\d+)?|[\u4e00-\u9fa5]{2,}")
#: 内容对齐的最低分。低于它就当没配上——宁可"解析无"，也不拼一个错的。
ALIGN_MIN = 0.22


def _doc_order(items: list[dict]) -> list[tuple[int, dict]]:
    r"""模型给的 items → 按**文档顺序**（起始行号）排的 `[(题号, item)]`。

    ⚠️ 按题号排会把"多套合订"排成 1,1,1,2,2,2…，看起来像一份卷，
    实际三段来自三套——`ans_by_n` 就是在那里串的。
    """
    out = []
    for it in items or []:
        try:
            n = int(it.get("n"))
        except (TypeError, ValueError):
            continue
        s = it.get("start")
        out.append((n, s if isinstance(s, int) else 10 ** 9, it))
    out.sort(key=lambda x: (x[1], x[0]))
    return [(n, it) for n, _s, it in out]


def _sig(s: str) -> set[str]:
    return set(_TOKEN.findall(s or ""))


def _sim(a: str, b: str) -> float:
    r"""两段文字的重合度（0–1）。分母取小的那边：解析通常比题干长得多。"""
    A, B = _sig(a), _sig(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def _a_text(a: dict, idx_a: dict[int, str]) -> str:
    s, e = a.get("start"), a.get("end")
    if not (isinstance(s, int) and isinstance(e, int) and s <= e):
        return a.get("quote") or ""
    return "\n".join(idx_a[i] for i in range(s, e + 1) if i in idx_a)


def align(qs: list[tuple[int, dict]], as_: list[tuple[int, dict]],
          idx_a: dict[int, str]) -> tuple[dict[int, tuple[dict, str]], dict]:
    r"""题目序列 ↔ 解析序列 → `{题目下标: (解析块, 依据)}` + 统计。

    三级依据（降级）：

    1. **题号**：两边都完整、都严格递增、且是同一个题号集合 → 按题号配；
    2. **顺序**：块数一样 → 第 k 块配第 k 块（一一对应时几乎总对）；
    3. **内容**：块数不一样 → 单调对齐（允许空配），分数够才配。

    "单调"是硬约束：不允许交叉。第 5 题配到第 3 题的解析，无论分多高都算错。
    """
    nq, na = len(qs), len(as_)
    if not nq:
        return {}, {"未配": 0}
    if not na:
        return {}, {"未配": nq, "说明": "没有解析块"}
    qn = [n for n, _ in qs]
    an = [n for n, _ in as_]
    # ① 题号
    if (len(set(qn)) == nq and len(set(an)) == na
            and qn == sorted(qn) and an == sorted(an) and set(qn) == set(an)):
        pos = {n: i for i, n in enumerate(an)}
        return ({i: (as_[pos[n]][1], "题号") for i, n in enumerate(qn)},
                {"题号": nq})
    # ② 顺序
    if nq == na:
        return ({i: (as_[i][1], "顺序") for i in range(nq)}, {"顺序": nq})
    # ③ 内容（单调对齐）
    pairs = _align_by_content(qs, as_, idx_a)
    return pairs, {"内容": len(pairs), "未配": nq - len(pairs),
                   "说明": "块数 %d↔%d，按内容单调对齐" % (nq, na)}


def _align_by_content(qs, as_, idx_a) -> dict[int, tuple[dict, str]]:
    r"""块数不等时的单调对齐（DP，允许两侧空配）。

    `dp[i][j]` = 前 i 题配前 j 份解析的最高总分；转移只有三种：
    跳过一题 / 跳过一份解析 / 配一对（加分 = 重合度）。
    回溯后，单对分数低于 `ALIGN_MIN` 的**不算配上**。
    """
    n, m = len(qs), len(as_)
    atext = [_a_text(a, idx_a) for _n, a in as_]
    score = [[0.0] * m for _ in range(n)]
    for i, (_n, q) in enumerate(qs):
        qtext = q.get("quote") or ""
        for j in range(m):
            score[i][j] = _sim(qtext, atext[j])
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(dp[i - 1][j], dp[i][j - 1])
            if score[i - 1][j - 1] >= ALIGN_MIN:
                best = max(best, dp[i - 1][j - 1] + score[i - 1][j - 1])
            dp[i][j] = best
    pairs: dict[int, tuple[dict, str]] = {}
    i, j = n, m
    while i > 0 and j > 0:
        if score[i - 1][j - 1] >= ALIGN_MIN and abs(
                dp[i][j] - (dp[i - 1][j - 1] + score[i - 1][j - 1])) < 1e-9:
            pairs[i - 1] = (as_[j - 1][1], "内容")
            i, j = i - 1, j - 1
        elif dp[i][j] == dp[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return pairs


#: 答案卷的逐题标题：`### 1. B` / `3. A` / `22.（1）`
ANS_HEAD = re.compile(
    r"^#*\s*(?:\\\[|\\\()?\s*(\d{1,2})\s*[.．]\s*"
    r"(?=[A-D]{1,4}\b|[\d\-−$（(]|见解析|证明)")
#: 解析里写的「【答案】B」
ANS_TAG = re.compile(r"【答\s*案】\s*([^\n【]{1,40})")


def _find_line(lines: list[tuple[int, str, int]], quote: str) -> int | None:
    r"""锚点 → 行下标。锚点是模型逐字抄的 10–25 字，**精确查找**就能定位。

    ⚠️ 这是本轮最重要的取舍：**不让模型数行号**。实测模型给的 `start/end`
    常把公式切成两半（第六套 22 道里 8 道因此被闸门按"$ 不成对"拒掉），
    而它抄的锚点在原文里 22/22 逐字命中。让它给锚点、代码自己找位置。
    """
    q = norm(quote or "")
    if len(q) < 6:
        return None
    q = q[:24]
    for i, (_n, t, _p) in enumerate(lines):
        if q in norm(t):
            return i
    return None


def question_blocks(lines: list[tuple[int, str, int]],
                    items: list[dict]) -> list[dict]:
    r"""试题 → 题块：**起点由锚点定，终点 = 下一题起点 − 1**。

    这样切出来的块天然把选项包在里面，也**不可能切在公式中间**（边界永远
    落在两道题之间）。锚点找不到才退回模型给的行号，并标 `src="行号"` 以便追查。
    """
    out: list[dict] = []
    for it in items or []:
        i = _find_line(lines, it.get("quote") or "")
        if i is not None:
            out.append({"n": it.get("n"), "start": lines[i][0], "item": it,
                        "src": "锚点"})
            continue
        s, e = it.get("start"), it.get("end")
        if isinstance(s, int) and isinstance(e, int) and s <= e:
            out.append({"n": it.get("n"), "start": s, "end": e, "item": it,
                        "src": "行号"})
    out.sort(key=lambda b: b["start"])
    for k, b in enumerate(out):
        if "end" not in b:
            b["end"] = (out[k + 1]["start"] - 1) if k + 1 < len(out) else lines[-1][0]
    return out


def answer_blocks(lines: list[tuple[int, str, int]]) -> list[dict]:
    r"""答案卷 → 逐题块，**不用模型**。

    答案册的版式是规则的：每题一行 `### 12. AC`。按「1、2、3…」严格递增的
    标题行切块，块 = 本条标题行 → 下一条前一行。实测第六套切出 22 段、
    题号 1..22 一条不差，比模型给的 19 段还全、还快。
    """
    seq: list[tuple[int, int]] = []
    seen: set[int] = set()
    for n, t, _p in lines:
        m = ANS_HEAD.match((t or "").strip())
        if not m:
            continue
        no = int(m.group(1))
        # **允许跳号**：实测第一套的标题从 `2. B` 开始（1/7/9 被 OCR 并进了
        # 别的行）。要求严格 +1 的话一块都认不出，整卷变成"无解析"。
        if no in seen or (seq and no <= seq[-1][1]):
            continue
        seen.add(no)
        seq.append((n, no))
    if len(seq) < 2:
        return []
    out = []
    for i, (line, no) in enumerate(seq):
        end = seq[i + 1][0] - 1 if i + 1 < len(seq) else lines[-1][0]
        out.append({"n": no, "start": line, "end": end})
    return out


def _trim_edges(texts: list[str]) -> list[str]:
    r"""削掉块首尾的空白行、页眉页脚、大题标题。

    终点取"下一题前一行"，会把夹在两题之间的 `## 二、多选题`、`第 II 卷`
    一起带进来——那不是题干，不削掉闸门会按"版面家具"整题拒。
    """
    def junk(t: str) -> bool:
        t = (t or "").strip()
        return not t or bool(FURNITURE.search(t)) or bool(SECTION.match(t))

    i, j = 0, len(texts)
    while i < j and junk(texts[i]):
        i += 1
    while j > i and junk(texts[j - 1]):
        j -= 1
    return texts[i:j]


def _answer_of(head: str, sol: str, qtype: str) -> str:
    r"""答案从**标题行**取（`### 12. AC`），取不到再看解析里的「【答案】」。"""
    m = ANS_HEAD.match((head or "").strip())
    rest = (head or "").strip()[m.end():].strip() if m else ""
    if rest.endswith("\\]") or rest.endswith("\\)"):
        rest = rest[:-2].strip()
    if qtype in ("single_choice", "multi_choice"):
        mm = re.match(r"^([A-D]{1,4})\b", rest)
        if mm:
            return mm.group(1)
        mm = ANS_TAG.search(sol or "")
        return mm.group(1).strip() if mm and re.fullmatch(r"[A-D]{1,4}",
                                                          mm.group(1).strip()) else ""
    if qtype == "fill_in_blank":
        # 填空题的答案常是跨行的公式：`15. $\frac{...}$`，标题行只截到一半。
        # 按 `$` 配平往后接解析的前几行，**别把答案截成半个公式**
        # （实测 "$ \fr" 就是截断出来的）。
        out = rest
        for ln in (sol or "").splitlines():
            if out and out.count("$") % 2 == 0:
                break
            if ln.strip() and not re.match(r"^\s*\d{1,2}[.．、]", ln):
                out = (out + " " + ln.strip()).strip()
        return out[:120]
    return "见解析"


def assemble(st_q: dict, st_a: dict, label: str, *,
             answer_table: dict[int, str] | None = None) -> dict:
    r"""题块 + 答案块 → 成品（清洗 + 闸门 + 溯源）。

    **边界怎么定的**（质量的关键，不再让模型数行号）：

    * 试题：模型只给"锚点"（逐字摘的 10–25 字）→ 精确定位起点 →
      **终点 = 下一题起点 − 1**；
    * 答案：答案册版式规则（`### 12. AC`）→ **正则切块**，不用模型；
    * 配对：两边题号集合一致就按题号，否则按文档顺序；
    * 首尾夹着的页眉/大题标题由 `_trim_edges` 削掉。

    `answer_table` 是卷首那张「题号/答案」速查表（有就校验，没有就算了）。
    """
    lines_q = st_q["lines"]
    lines_a = st_a["lines"]
    idx = {n: (t, p) for n, t, p in lines_q}
    idx_a = {n: t for n, t, _p in lines_a}
    book, reject, pending, covered = [], [], [], set()
    secs = section_types(lines_q)

    qb = question_blocks(lines_q, st_q["items"])
    ab = answer_blocks(lines_a)
    # 正则切不全的（跳号、版式不规整）→ 用模型的答案块补缺口，只补没有的题号
    have = {b["n"] for b in ab}
    for n, it in _doc_order(st_a["items"]):
        if n in have:
            continue
        s0, e0 = it.get("start"), it.get("end")
        if isinstance(s0, int) and isinstance(e0, int) and s0 <= e0:
            ab.append({"n": n, "start": s0, "end": e0, "src": "模型"})
    ab.sort(key=lambda b: b["start"])
    a_by_n = {b["n"]: b for b in ab}
    qn = [b["n"] for b in qb]
    pairs: dict[int, tuple[dict, str]] = {}
    # **按题号逐个配**，不要求两边题号集合完全相等：答案册常有几题的标题
    # 被 OCR 读花（实测第一套 1/7/9 被读成 `### \[1.\ D`），旧写法一题不配、
    # 整卷 21 道全"无解析"。少配一题由它空着，不能因此把整卷拖垮。
    hits = sum(1 for b in qb if b["n"] in a_by_n)
    if ab and hits >= max(1, int(len(qb) * 0.6)):
        pairs = {i: (a_by_n[b["n"]], "题号")
                 for i, b in enumerate(qb) if b["n"] in a_by_n}
        pinfo = {"题号": len(pairs)}
        if len(pairs) < len(qb):
            pinfo["未配"] = len(qb) - len(pairs)
    elif ab and len(ab) == len(qb):
        pairs = {i: (ab[i], "顺序") for i in range(len(qb))}
        pinfo = {"顺序": len(pairs)}
    else:
        pinfo = {"未配": len(qb),
                 "说明": "答案块 %d、题目块 %d" % (len(ab), len(qb))}

    table = answer_table or {}
    seen: dict[int, bool] = {}
    for i, b in enumerate(qb):
        try:
            n = int(b["n"])
        except (TypeError, ValueError):
            continue
        if n in seen:
            # 同一题号出现两次 → 入库键会撞。宁可拒，不要静默覆盖。
            reject.append({"题号": n, "题型": "",
                           "题干": (b["item"].get("quote") or "")[:80],
                           "页码": covered_pages(lines_q, (b["start"], b["end"])),
                           "行": [b["start"], b["end"]],
                           "原因": ["题号重复出现（同一份文件里第 %d 题出现了两次）" % n]})
            continue
        seen[n] = True
        s, e = b["start"], b["end"]
        covered.update(range(s, e + 1))
        pages = covered_pages(lines_q, (s, e))
        seg = _trim_edges([idx[k][0] for k in range(s, e + 1) if k in idx])
        stem_raw, opts = split_stem_options(seg)
        a, basis = pairs.get(i, ({}, ""))
        asol: list[str] = []
        if a:
            asol = _trim_edges([idx_a[k] for k in range(a["start"], a["end"] + 1)
                                if k in idx_a])
            # 答案块的第一行是标题（`### 2. B`），不是解析内容——削掉，
            # 否则每道题的解析都以 "2. B " 开头（实测第一套 20 道全带）
            if asol:
                asol[0] = re.sub(r"^\s*#*\s*\d{1,2}\s*[.．]\s*[A-D]{1,4}\b\s*",
                                 "", asol[0])
        qtype = type_at(secs, s) or TYPE_EN.get(BY_NO.get(n, ""), "")
        if not qtype:
            qtype, _why = classify_type(stem_raw, opts, "", hint=b["item"].get("type") or "")
        stem, sol, opts, notes = clean_fields(
            stem_raw, "\n".join(asol), qtype=qtype, opts=opts,
            quote=b["item"].get("quote") or "")
        answer = _answer_of(idx_a.get(a["start"], "") if a else "", sol, qtype)
        # 答案回收：解析里写着「故选 CD」而答案栏是空的（选择题 25.7% 缺答案
        # 就是这条路径没生效）。**只认「故选」后面那一段**，不拿正则从整段抠字母
        # ——`OBB_1O_1` 那种 LaTeX 变量名到处都有，抠出来的"答案"全是错的（台账 D03）。
        if not answer and qtype in ("single_choice", "multi_choice"):
            m = ANSWER_IN_SOL.search(sol)
            if m:
                answer = m.group(1)
                notes.append("从「故选」回收答案")
        # 选项标签丢了 → 从题干预末几行捞回来（只对选择题）
        if qtype in ("single_choice", "multi_choice"):
            stem, opts = _recover_inline_options(stem, opts)
        # 卷首速查表校验：跟配出来的答案不一致 → **只标记，不改**
        table_hit = ""
        if table and qtype in ("single_choice", "multi_choice") and n in table:
            want = table[n]
            if answer and set(answer) != set(want):
                table_hit = "%s≠%s" % (want, answer)
        # **先修再判**：`\left`/`\right` 数量不等这种硬伤能确定地修掉，
        # 放在闸门后面的话，题已经被拒了、修了也白修（实测保定第 1 题）。
        stem = QLT.repair_math(stem)
        sol = QLT.repair_math(sol)
        why = gate(qtype, stem, opts, answer, sol)
        rec = {"题号": n, "题型": qtype, "页码": pages, "行": [s, e],
               "题干": stem, "选项": opts, "答案": answer, "解析": sol,
               "清洗": notes, "引用对": b["src"] == "锚点",
               "答案引用对": bool(a),
               "配对": basis, "速查表": table_hit,
               "粗筛图": bool(FIG_WORD.search(stem)),
               "粗筛表": bool(TABLE_WORD.search(stem))}
        if why:
            rec["原因"] = why
            reject.append(rec)
            continue
        if rec["粗筛图"] or rec["粗筛表"]:
            # **文字信号只当粗筛**：实测纯代数题（「图象过点(4,16)」）也会命中。
            # 按"疑似就跳过"会把好题丢掉 → 标待复核、**先照录**。
            pending.append({"题号": n, "粗筛命中": "图" if rec["粗筛图"] else "表",
                            "页码": pages, "行": [s, e], "题干开头": stem[:50]})
        book.append(rec)
    orphans = [(n, t, p) for n, t, p in lines_q
               if n not in covered and not FURNITURE.search(t)]
    return {"label": label, "book": book, "reject": reject,
            "pending": pending, "orphans": orphans, "lines": lines_q,
            # 配对方式统计：界面上要看得见「这卷是按题号配的还是按顺序配的」
            "配对": pinfo, "速查表": table}


def run(src: Path, *, phase: str = "run", label: str = "") -> dict:
    r"""一场考试跑完 v2。`phase` 决定只扫（scan）/ 只结构化（struct）/ 全跑。"""
    pdfs = sorted(src.glob("*.pdf"))
    paper, answers, sheets = G.pick_pdfs(pdfs)
    label = label or src.name
    out = {"label": label, "试题": paper.name if paper else None,
           "答案": [a.name for a in answers],
           "答题卡": [s.name for s in sheets], "phase": phase}
    if paper is None:
        out["error"] = "没有试题 PDF（只有答案/答题卡）"
        return out
    if phase in ("scan", "run"):
        # 识别引擎自带服务检查（paddle.ensure），不再过 1236 那道闸
        out["页"] = {paper.name: scan_pdf(paper)}
        for a in answers:
            out["页"][a.name] = scan_pdf(a)
    if phase == "scan":
        return out
    if phase in ("struct", "run"):
        d = v2_dir(paper)
        st_q = structure(json.loads((d / "pages.json").read_text(encoding="utf-8")),
                         "试卷", save=d / "struct_试卷.json")
        st_a = {"items": [], "lines": []}
        if answers:
            da = v2_dir(answers[0])
            if (da / "pages.json").exists():
                st_a = structure(json.loads((da / "pages.json").read_text(encoding="utf-8")),
                                 "答案", save=da / "struct_答案.json")
            else:
                out["warning"] = "答案卷没有扫描产物，跳过配对"
        out.update(assemble(st_q, st_a, label))
    return out


# 交接文档 §5 那份 JSON 用的是**英文键**（`no`/`type`/`stem`/`options`/`answer`/`solution`），
# 流水线内部的成品记录用**中文键**（`题号`/`题型`/`题干`/`选项`/`答案`/`解析`）。
#
# **两份都收**：文档是给大模型看的、代码是给流水线用的，让它们对不上是纯坑——
# 实测照着文档写好的 JSON 直接喂进 `rec_to_question`，第一行就
# `KeyError: '题号'`（交接文档 §11 的例子当时就是这么写的，等于跑不通）。
_DOC_KEYS = {"no": "题号", "type": "题型", "stem": "题干", "options": "选项",
             "answer": "答案", "solution": "解析", "pages": "页码", "quote": "原文",
             "figure": "有图", "table": "有表"}


def _as_rec(rec: dict) -> dict:
    r"""英文键（交接文档 §5）→ 中文键（内部）。本来就是中文键的原样返回。"""
    if not isinstance(rec, dict) or "题号" in rec:
        return rec
    out = dict(rec)
    for en, zh in _DOC_KEYS.items():
        if en in out and zh not in out:
            out[zh] = out.pop(en)
    return out


def rec_to_question(rec: dict, label: str, book: str = "模拟题") -> Question:
    r"""成品记录 → 入库用的 `Question`，**并走项目唯一的规范化入口**。

    `rec` 中英文键都认（见 `_as_rec`）：交接文档 §5 给大模型看的 JSON 和
    流水线内部的成品记录，键名不一样。

    `book` 是**书名**，同时决定入库 key 的第一段（库里普遍就是 `书/出处#题号`）。
    ⚠️ 这里原来写死 `模拟题`：录入界面上「书名」填了 `高考真题汇编` 也白填，
    入库后 `kind` 永远是「模拟」、按高考筛不出来；题目一旦从 `ingest`
    升级还有个更隐蔽的后果——同卷的 key 与库里已有那条对不上，
    于是**多出一道重复题**而不是更新原来那道。

    ⚠️ 闸门只保证"数据齐、不脏"，**不等于符合项目规范**。实测：回原卷修完
    13 道之后 `conform` 报 35 处（句末标点 18、答案写法 14、填空位数 3），
    全都得靠 `normalize(ENTRY)` ——少了这一步，修完的题照样不合规。
    """
    rec = _as_rec(rec)
    book = (book or "").strip() or "模拟题"
    q = Question(
        key="%s/%s#%d" % (book, label, rec["题号"]), type=rec["题型"],
        stem=rec["题干"],
        options=[Option(k, v) for k, v in sorted((rec.get("选项") or {}).items())],
        answer=rec.get("答案") or "", solution=rec.get("解析") or "",
        # 考点写进 meta：入库时 `ingest` 会把它带进题库，
        # 否则界面里永远是「未标注」，还得人工再点一遍。
        # 考点是 Question 的**顶层字段**（`store.question_from_block` 只读
        # 顶层 `points`），塞进 meta 里界面是看不见的 —— 实测踩过。
        points=rec.get("points") or ([rec["point"]] if rec.get("point") else []),
        meta={"book": book, "source_label": label, "source_no": rec["题号"]})
    N.normalize(q, N.ENTRY)
    return q


def write_output(res: dict, out_dir: Path) -> None:
    """成品 / 登记 / 待复核 / 报告 四份都落盘（人工只看报告）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", res.get("label") or "卷")[:60]
    (out_dir / (tag + ".成品.json")).write_text(
        json.dumps(res.get("book") or [], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / (tag + ".待复核.json")).write_text(
        json.dumps(res.get("pending") or [], ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# %s" % res.get("label"), "",
          "| 指标 | 值 |", "|---|---|",
          "| 切出题数 | %d |" % len(res.get("book") or []),
          "| 拒收 | %d |" % len(res.get("reject") or []),
          "| 待复核（图/表粗筛） | %d |" % len(res.get("pending") or []),
          "| 孤儿行 | %d |" % len(res.get("orphans") or []),
          ""]
    for r in res.get("reject") or []:
        md += ["- **拒收 #%s**：%s" % (r["题号"], "；".join(r["原因"])), ""]
    for n, t, p in (res.get("orphans") or [])[:30]:
        md += ["- 孤儿行 p%s 行%d：%s" % (p, n, t[:70])]
    md += ["", "## 逐题", ""]
    for b in res.get("book") or []:
        md += ["### %s. %s（第 %s 页）" % (b["题号"], b["题型"],
                                        ",".join(map(str, b["页码"]))), "",
               b["题干"][:600], ""]
        if b["选项"]:
            md += ["**选项**：" + "　".join("%s. %s" % (k, v)
                                            for k, v in sorted(b["选项"].items())), ""]
        md += ["**答案**：%s" % (b["答案"] or "（无）"), "",
               "**解析**：%s" % (b["解析"][:400] or "（无）"), ""]
    (out_dir / (tag + ".报告.md")).write_text("\n".join(md), encoding="utf-8")


# ── 自检：用例全部取自 A10 试点的**真实脏数据** ──────────────────────
# ── v1 兼容入口：给审阅界面/脚本用（一份合订 PDF → 入库用的 tex）──────────
#: 答案区标题。**必须是"短行里含参考答案"**，不能要求整行只有四个字——
#: 实际卷子里长这样（成都七中 2607）：
#:     "2027届高三上期第七周数学周测参考答案和评分标准"
#: 死抠 `^参考答案$` 会一个都匹配不上，于是整卷 19 道题全部"无解析"。
ANSWER_HEAD = re.compile(r"^\s*[^\n]{0,80}参考答案[^\n]{0,12}$")
# 实测标题能长成《重庆南开中学高 2027 级高三（上）数学练习（八）10.18》参考答案
# —— 前缀 40 多字，原来的 24 字上限匹配不上，整卷 19 题全部"无解析"。

#: 解析成片出现的标记。一页里 ≥2 处、而上一页 0 处 → 这页是解析的开头
ANALYSIS_TAG = re.compile(r"【(?:分析|详解|解析|点睛|小问\d*详解)")
#: 「题号 … 答案 …」速查表的表头（中间可能隔着几十个字）
TABLE_HEAD = re.compile(r"题\s*号[\s\S]{0,200}?答\s*案")
#: OCR 把表格读成 HTML，<td> 一格一格
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)


def split_answer_pages(rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    r"""合订本 → （试题页, 答案页, 判断依据）。

    **不只认「参考答案」四个字**：实测有的解析直接接在最后一题后面、
    有的标题写成「答案与解析」、还有的先给一张速查表。所以在每个页边界上
    数三个信号，够分才切：

      +3 标题行（参考答案 / 答案与解析 …）
      +3 本页【分析】/【详解】≥ 2 处，而上一页 0 处（解析成片开始）
      +2 本页有「题号 … 答案」速查表
      +2 题号在本页从 1 重新开始，而上一页已经写到 15 题以后

    ≥3 分才切；只有 2 分 → **不切**，把候选页放回 `info` 让人点（不猜）。
    都没有 → 全当试题，答案为空（`ingest` 会整批拒收——"没有解析不许入库"）。
    """
    if len(rows) < 2:
        return rows, [], {"at": None, "cands": []}
    cands = []
    for i in range(1, len(rows)):
        cur = Path(rows[i]["txt"]).read_text(encoding="utf-8")
        prv = Path(rows[i - 1]["txt"]).read_text(encoding="utf-8")
        head = next((ln.strip() for ln in cur.splitlines() if ln.strip()), "")
        why, s = [], 0
        if ANSWER_HEAD.match(head) or re.match(r"^\s*答\s*案\s*与?\s*解\s*析", head):
            s += 3
            why.append("标题")
        if len(ANALYSIS_TAG.findall(cur)) >= 2 and not ANALYSIS_TAG.search(prv):
            s += 3
            why.append("【分析】成片出现")
        if TABLE_HEAD.search(cur):
            s += 2
            why.append("答案速查表")
        if (re.match(r"^\s*1\s*[.、．]", head)
                and re.search(r"(?:1[5-9]|2[0-5])\s*[.、．]", prv)):
            s += 2
            why.append("题号从 1 重来")
        if s:
            cands.append({"page": i + 1, "score": s, "why": why})
    if not cands:
        return rows, [], {"at": None, "cands": []}
    best = max(cands, key=lambda c: c["score"])
    if best["score"] >= 3:
        i = best["page"] - 1
        return rows[:i], rows[i:], {"at": best["page"], "score": best["score"],
                                    "why": best["why"], "cands": cands}
    return rows, [], {"at": None, "cands": [c for c in cands if c["score"] >= 2]}


def parse_answer_table(rows: list[dict], pages: int = 3) -> dict[int, str]:
    r"""卷首「题号 / 答案」速查表 → `{题号: 答案}`。

    OCR 把表格读成了 HTML（`<td>` 一格一格），正好省得猜版式。只认前几页：
    正文里也有表格，往后翻只会把题干里的数字当答案。

    读不到就返回空表——**不猜**。空表 = 不做校验，不是"没有冲突"。
    """
    out: dict[int, str] = {}
    for r in rows[:pages]:
        try:
            text = Path(r["txt"]).read_text(encoding="utf-8")
        except OSError:
            continue
        if "<td" not in text:
            continue
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in TD.findall(text)]
        # **不要求有「题号」这一格**：实测拼好卷的答案册，OCR 把表头那格吞了，
        # 只剩 `1 2 3 … | | 答案 | D B A …`。所以以「答案」为中心：
        # 往前收数字（跳过空格子），往后收字母，两侧数量相等才认。
        for k, c in enumerate(cells):
            if c not in ("答案", "答　案"):
                continue
            nums, j = [], k - 1
            while j >= 0:
                if cells[j].isdigit():
                    nums.append(int(cells[j]))
                elif cells[j]:
                    break
                j -= 1
            nums.reverse()
            ans, j = [], k + 1
            while (j < len(cells)
                   and re.fullmatch(r"[A-D]{1,4}", cells[j] or "")):
                ans.append(cells[j])
                j += 1
            # 两侧一样长、题号递增，才当速查表。**上限 30**：11–12 题常被
            # 排版拆成单独一行，所以下限只取 2，不能取 3（实测会漏掉 11、12 题）。
            if (2 <= len(nums) == len(ans) <= 30
                    and nums == sorted(set(nums))):
                for n, a in zip(nums, ans):
                    out.setdefault(n, a)
    return out


def _recover_inline_options(stem: str, opts: dict) -> tuple[str, dict]:
    r"""选择题的选项**没有 A/B/C/D 标签**时，从题干末尾把几行短式捞回来。

    实测重庆南开那份：OCR 把四个选项排成四行纯式子（`$3-3i$` / `$-\sqrt2+…$`），
    字母标签在另一列、没被读进来。于是 `\begin{choices}` 只有一个空 item，
    闸门按"选项 1 个（应为 4）"把整题拒掉——题其实是好的。

    只对选择题、只从末尾取 3–4 行、且每行都必须很短，尽量不误伤解答题。
    """
    if len(opts) >= 4:
        return stem, opts
    lines = [l for l in (stem or "").splitlines() if l.strip()]
    tail: list[str] = []
    while lines and len(tail) < 4:
        last = lines[-1].strip()
        if len(last) <= 48 and re.match(r"^(?:\$|[A-D][.、．])", last):
            tail.insert(0, lines.pop())
        else:
            break
    if not 3 <= len(tail) <= 4:
        return stem, opts
    for i, t in enumerate(tail):
        opts.setdefault("ABCD"[i], re.sub(r"^[A-D][.、．]\s*", "", t))
    return "\n".join(lines).strip(), opts


def _norm_txt(s: str) -> str:
    return re.sub(r"[\s$\\{}^_\u3000]", "", s or "")


TAG_SYS = """你在给高中数学题标考点。输入是考点清单（编号 + 名称）和一批题目。

只输出一个 JSON 对象，题号 → 考点编号数组，如 {"1":["1.1.3"],"2":["3.2.1","3.1.2"]}。
规则：
* 编号必须**来自清单**，不许自己编；认不出就给 []。
* 每题给 **1–2 个**：第一个是最贴切的主考点，第二个只在确实跨考点时才给。
* 不要解释、不要代码块。
"""

#: 多题录入用的轻量标注模型。用户点名要 qwen3.5；9B 比 27B 快约 1.8 倍，
#: 标考点/难度这种粗活够用。可用环境变量 `AMTIKU_TAG_MODEL` 换回 27B。
TAG_MODEL = os.environ.get("AMTIKU_TAG_MODEL", "qwen3.5-9b-mlx")

#: 标注模型的常驻时长。9B 只占 ~6GB，但没必要像求解 27B 那样钉一周；
#: 标完 30 分钟没用就自动退回，别让"顺手标一次"长期占内存。
TAG_TTL = int(os.environ.get("AMTIKU_TAG_TTL", "1800"))

TAG_SYS_DIFF = """你在给高中数学题标考点和难度。输入是考点清单（编号 + 名称）和一道题。

只输出一个 JSON 对象：{"points":["1.1.3"],"difficulty":"中档题"}。
规则：
* points 给 **1–2 个**，编号必须**来自清单**，第一个是最贴切的主考点；认不出给 []。
* difficulty 只能是 简单题 / 中档题 / 难题 之一，按题目实际难度判断。
* 不要解释、不要代码块。
"""

#: 第一次全量清单没标上时的**补标**提示：只给本地粗筛出来的候选。
#: 153 条全塞给 9B 时它常"找不到"；缩到二三十条，命中率明显高。
TAG_SYS_SHORT = """你在给高中数学题标考点和难度。下面只给**可能相关**的候选考点（不是全部清单）。

只输出一个 JSON 对象：{"points":["编号"],"difficulty":"简单题|中档题|难题"}。
规则：
* 从候选里选 1–2 个最贴切的，第一个为主考点。
* 候选里确实没有合适的才给 []；不要自己编号。
* difficulty 只能是 简单题 / 中档题 / 难题 之一。
* 不要解释、不要代码块。
"""


def _point_ids(values) -> list[str]:
    r"""从模型输出里抠出考点编号。

    ⚠️ 补标提示会把候选行写成 `8.3.4 数量积的性质与应用`，小模型经常
    **连标题一起抄回**。只认整串等于编号会一个都收不到（实测 3 道全丢），
    所以这里取每项开头的编号。
    """
    from . import knowledge as kb
    out: list[str] = []
    for x in values or []:
        m = re.search(r"\d+(?:\.\d+){1,3}", str(x))
        if m:
            out.append(m.group(0))
    return [p for p in dict.fromkeys(out) if kb.get(p)][:2]


def _chinese_grams(text: str, *, nmin: int = 2, nmax: int = 4) -> set[str]:
    r"""中文 n-gram（去掉 LaTeX 命令）。给「候选考点」做粗筛用。"""
    t = re.sub(r"\\[a-zA-Z]+", " ", text or "")
    out: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", t):
        for n in range(nmin, nmax + 1):
            for i in range(len(run) - n + 1):
                out.add(run[i:i + n])
    return out


def _shortlist_points(stem: str, options: list[str], *, limit: int = 24) -> list[dict]:
    r"""本地粗筛「可能相关的考点」，只用于 9B 的**第二轮补标**。

    不追求精确——最终仍由模型从候选里选、并校验编号。目的只是把 153 条
    压到二三十条，让 9B 别在长清单里迷路。分数 = 中文 n-gram 的 IDF 重叠，
    题干/选项里原样出现考点名的再给一个强提示。
    """
    from . import knowledge as kb
    docs: list[tuple[str, str, str]] = []
    for p in kb.all_points():
        pid = p.get("id")
        if not pid:
            continue
        fields = p.get("fields") or {}
        ftxt = " ".join(
            str(v) for vv in fields.values()
            for v in (vv if isinstance(vv, list) else [vv]))
        title = p.get("title") or kb.title_of(pid)
        docs.append((pid, title, " ".join([
            title, p.get("section", "") or "", p.get("topic", "") or "", ftxt])))
    q = (stem or "") + " " + " ".join(options or [])
    # LaTeX 里认不出的数学对象：给几个别名，否则「向量题」会全军覆没。
    if "\\overrightarrow" in q or "\\vec" in q:
        q += " 向量 数量积 平面向量"
    if re.search(r"\\(?:sin|cos|tan)", q):
        q += " 三角函数"
    qg = _chinese_grams(q)
    if not qg:
        return []
    df: dict[str, int] = {}
    for _pid, _title, text in docs:
        for g in _chinese_grams(text):
            df[g] = df.get(g, 0) + 1
    n = len(docs)
    scored: list[tuple[float, str, str]] = []
    for pid, title, text in docs:
        tg = _chinese_grams(text)
        s = 0.0
        for g in qg & tg:
            s += math.log((n + 1) / (df.get(g, 1) + 1)) * (1.5 if len(g) >= 3 else 1.0)
        for run in re.findall(r"[\u4e00-\u9fff]{2,}", q):
            if run in title:
                s += 6.0
                break
        if s > 0:
            scored.append((s, pid, title))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"id": pid, "title": title} for _s, pid, title in scored[:limit]]


def _tag_reply(raw: str, *, with_difficulty: bool) -> tuple[list[str], str]:
    r"""解析模型的标注结果。**宁可不标，也不留非法编号**。

    JSON 解析失败时退回正则——小模型偶尔会在 JSON 外面多说一句
    "这道题考查…"，但编号本身仍可用。难度只在 JSON 里认，正则猜不了。
    """
    from . import knowledge as kb
    raw = re.sub(r"^```[a-zA-Z]*\n|```$", "", (raw or "").strip()).strip()
    if with_difficulty:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                pts = d.get("points") or []
                if isinstance(pts, str):
                    pts = [pts]
                pts = [str(x).strip() for x in pts if str(x).strip()]
                diff = str(d.get("difficulty") or "").strip()
                if diff not in ("简单题", "中档题", "难题"):
                    diff = ""
                return (_point_ids(pts), diff)
            except ValueError:
                pass
    ids = re.findall(r"\d+(?:\.\d+){1,3}", raw)
    return (_point_ids(ids), "")


def tag_points_detailed(book: list[dict], *, workers: int = 4, timeout: int = 600,
                        model: str = "", with_difficulty: bool = False,
                        retry_empty: bool = False) -> dict:
    r"""逐题打考点（可选难度），返回 `{n, n_diff, failed, error, model}`。

    **一题一次调用**，不把整卷塞进一个请求：

      * 一题最多几千 token，永远碰不到上下文上限；
      * 某题模型抽风，只毁这一题，不会把整批 JSON 带偏；
      * 并发开路，19 题在 9B 上约 30–50 秒。

    代价是每道题都要重新 prefill 一遍考点清单（153 条），但输出只有几个 token，
    真正慢的就是 prefill，所以并发一开就把这点亏吃回来了。

    `model=""` 用默认 27B（`record2` 老行为）；多题录入传 `qwen3.5-9b-mlx`
    并开 `with_difficulty=True`，让它顺带定难度。

    `retry_empty=True`：全量清单没标上的题，再拿**本地粗筛出的候选**补标
    一次。9B 面对 153 条清单经常"找不到"；缩到二三十条后命中率明显高。
    仍标不上就留空——**宁缺勿错**，不硬编一个。
    """
    from concurrent.futures import ThreadPoolExecutor
    from . import knowledge as kb
    from . import lms as L

    items = [r for r in book if (r.get("题干") or "").strip()]
    if not items:
        return {"n": 0, "n_diff": 0, "failed": 0, "error": "", "model": model or R.MODEL}
    lst = "\n".join("%s %s" % (p.get("id"), kb.title_of(p.get("id")))
                     for p in kb.all_points() if p.get("id"))
    tag_model = model or R.MODEL
    # 9B 的轻量标注：8k 上下文足够（153 个考点约 5k token）。
    # 27B 保持老口径（32k），别把整卷结构化那条线改坏。
    ok, ident, why = (L.ensure_ctx(tag_model, min_ctx=8192, ttl=TAG_TTL)
                      if model else L.ensure_ctx(tag_model, need_tokens=6000))
    if not ok:
        return {"n": 0, "n_diff": 0, "failed": len(items),
                "error": why, "model": tag_model}
    sys_prompt = TAG_SYS_DIFF if with_difficulty else TAG_SYS

    def one(r: dict) -> tuple[list[str], str]:
        opts = "\n".join("%s. %s" % (a, b) for a, b in (r.get("选项") or {}).items())
        body = ("考点清单：\n%s\n\n题目（题型 %s）：\n%s%s"
                % (lst, r.get("题型") or "", (r.get("题干") or "")[:1200],
                   ("\n" + opts[:600]) if opts else ""))
        try:
            d = _post(R.API, ident,
                      [{"role": "system", "content": sys_prompt},
                       {"role": "user", "content": body}],
                      maxtok=200 if with_difficulty else 120,
                      extra={"reasoning_effort": "none"}, timeout=timeout)
            raw = (d["choices"][0]["message"].get("content") or "").strip()
            return _tag_reply(raw, with_difficulty=with_difficulty)
        except Exception:                                     # noqa: BLE001
            return [], ""

    n_ok = n_diff = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        results = list(ex.map(one, items))
    for r, (ids, diff) in zip(items, results):
        if ids:
            r["points"] = ids
            r["point"] = ids[0]
            r["point_title"] = kb.title_of(ids[0])
            n_ok += 1
        if diff:
            r["difficulty"] = diff
            n_diff += 1

    # ── 第二轮：只补第一轮没拿到考点的题，用本地粗筛的候选 ──
    retried = filled = 0
    if retry_empty and with_difficulty:
        miss = [r for r in items if not r.get("points")]
        retried = len(miss)

        def one_short(r: dict) -> tuple[list[str], str]:
            cands = _shortlist_points(
                r.get("题干") or "", list((r.get("选项") or {}).values()))
            if not cands:
                return [], ""
            lst2 = "\n".join("%s %s" % (p["id"], p["title"]) for p in cands)
            opts = "\n".join("%s. %s" % (a, b)
                             for a, b in (r.get("选项") or {}).items())
            body = ("候选考点：\n%s\n\n题目（题型 %s）：\n%s%s"
                    % (lst2, r.get("题型") or "", (r.get("题干") or "")[:1200],
                       ("\n" + opts[:600]) if opts else ""))
            try:
                d = _post(R.API, ident,
                          [{"role": "system", "content": TAG_SYS_SHORT},
                           {"role": "user", "content": body}],
                          maxtok=200, extra={"reasoning_effort": "none"},
                          timeout=timeout)
                raw = (d["choices"][0]["message"].get("content") or "").strip()
                return _tag_reply(raw, with_difficulty=True)
            except Exception:                                 # noqa: BLE001
                return [], ""

        if miss:
            with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
                more = list(ex.map(one_short, miss))
            for r, (ids, diff) in zip(miss, more):
                if ids:
                    r["points"] = ids
                    r["point"] = ids[0]
                    r["point_title"] = kb.title_of(ids[0])
                    n_ok += 1
                    filled += 1
                if diff and not r.get("difficulty"):
                    r["difficulty"] = diff
                    n_diff += 1

    # `failed` = 最终**没有考点**的题数。哪怕模型给了难度，没考点就是没标上；
    # 界面要据此提示"还有几道要手标/重试"，不能报 0 让人以为全标好了。
    failed = sum(1 for r in items if not r.get("points"))
    return {"n": n_ok, "n_diff": n_diff, "failed": failed,
            "retried": retried, "filled": filled,
            "error": "", "model": tag_model}


def tag_points(book: list[dict], *, workers: int = 4, timeout: int = 600,
               model: str = "", with_difficulty: bool = False,
               retry_empty: bool = False) -> int:
    r"""逐题打考点（就地写 `rec["point"]`），返回打上的数量。"""
    return tag_points_detailed(book, workers=workers, timeout=timeout,
                               model=model,
                               with_difficulty=with_difficulty,
                               retry_empty=retry_empty)["n"]


#: 「这题八成有图」的**兜底**关键词。只在**没切到图**时用来挂原页，
#: 不是判据——切图靠坐标，这里只是防止"图被并进文字块"时整题看不到图。
FIG_HINT = re.compile(
    r"如图|图中|图象|图像|图形|三棱锥|四棱锥|三棱柱|棱台|棱锥|圆锥|圆柱"
    r"|正方体|长方体|外接球|内切球|截面|展开图|三视图|直观图|频率分布直方图")


OPT_SYS = r"""你在抄一道选择题的**四个选项**。

只输出这一段，不要题干、不要解析、不要解释：

\begin{choices}
\item …
\item …
\item …
\item …
\end{choices}

按图上 A/B/C/D 的顺序；看不清的那一项写 `\item` 空着，**不要编**。"""


def complete_options(pdf, work, book, *, limit: int = 6, on_event=None) -> int:
    r"""选项不全的选择题 → **裁图放大，让 27B 只抄四个选项**。

    OCR 常把选项标签整排丢掉（实测重庆那份 9 道题），规则回收只能捞回 3 个
    （最后一行粘在别的文字上）。这一步直接看图，补回第 4 个。
    只对"选项 < 4 的选择题"做，最多 6 题，避免整卷变慢。
    """
    import base64
    import io

    from PIL import Image

    todo = [r for r in book
            if r.get("题型") in ("single_choice", "multi_choice")
            and len(r.get("选项") or {}) < 4][:limit]
    if not todo:
        return 0
    ok, ident, _why = L.ensure_ctx(R.MODEL, need_tokens=9000)
    if not ok:
        return 0

    try:
        from . import engine
        lay = engine.get().layout(work)
    except Exception:                                         # noqa: BLE001
        lay = {}

    def _n(x):
        return re.sub(r"[\s$\\{}^_]", "", x or "")

    n_ok = 0
    for r in todo:
        pages = r.get("页码") or []
        y = r.get("_yrange") or []
        if not pages:
            continue
        if not y:                     # 被拒的题没走过分图，按题干现找位置
            head = _n(r.get("题干"))[:12]
            for a, b2, t, _x0, _x1 in (lay.get(int(pages[0]), {}) or {}).get("texts", []):
                if head and head in _n(t):
                    y = [a, b2]
                    break
        png = Path(work) / "pages" / ("p%03d.png" % int(pages[0]))
        if not png.is_file():
            continue
        if on_event:
            on_event({"type": "stage", "text": "补选项：第 %s 题" % r.get("题号")})
        try:
            img = Image.open(png).convert("RGB")
            if len(y) == 2:
                top = max(0, int(float(y[0]) * img.height) - 20)
                bot = min(img.height, int(float(y[1]) * img.height) + 20)
                if bot - top > 60:
                    img = img.crop((0, top, img.width, bot))
            if img.width < 1700:
                k = 1700 / img.width
                img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            d = _post(R.API, ident,
                      [{"role": "system", "content": OPT_SYS},
                       {"role": "user", "content": [
                           {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                           {"type": "text", "text": "第 %s 题的四个选项。" % r.get("题号")}]}],
                      maxtok=1200, extra={"reasoning_effort": "none"})
            raw = (d["choices"][0]["message"].get("content") or "")
            items = re.findall(r"\\item\s*(.*)", raw)
            items = [i.strip() for i in items if i.strip()][:4]
            if len(items) == 4:
                for i, txt in enumerate(items):
                    r.setdefault("选项", {})["ABCD"[i]] = txt
                n_ok += 1
        except Exception:                                     # noqa: BLE001
            continue
    return n_ok


#: 题干/解析里的「（图）」占位行。PaddleOCR / 模型都用它标"原卷这里有一张图"。
FIG_PH = re.compile(r"(?m)^[ \t]*（图）[ \t]*$")

#: 插图引用。宽度跟库里存量写法一致，用 `\linewidth` 的比例。
FIG_TEX = "\\includegraphics[width=0.4\\linewidth]{%s}"
FIG_TEX_OPT = "\\includegraphics[width=0.15\\paperwidth]{%s}"

#: 页面上新的题号（`4.（本题5分）…`）。用来给 `assign_figs` 划题与题的边界。
_QNO = re.compile(r"^\s*(\d{1,2})\s*[.．、]")


def attach_figs(rec: dict) -> int:
    r"""把按坐标切好的插图写进题干/解析，替掉 `（图）` 占位。

    返回挂上的张数。**必须在清洗题干之前调用**——`（图）` 占位行是这张图
    唯一的位置信息；先洗掉再挂，就只能一律堆到末尾了。

    规则：
      * 按「题干 → 解析」的阅读顺序一对一替占位行；
      * 占位行比图多（同一张图被识别成"图块 + text_image"两段）→ 多的删掉；
      * 图比占位行多 → 剩下的追加到题干末尾；
      * 选项图（`opt_figs`）写进对应选项，不占题干的位置。

    ⚠️ 2026-10-27 之前这里**什么也没做**：图只挂在 `kept["figs"]` 上给界面看，
    正文里永远只有一个 `（图）`——录完的题全都没有图。这是那个 bug 的修复点。
    """
    figs = [str(n) for n in (rec.get("figs") or []) if n]
    opts = rec.get("opt_figs") or {}
    if opts:
        used = set()
        for label, name in sorted(opts.items()):
            if not name:
                continue
            rec.setdefault("选项", {})[label] = "$%s$" % (FIG_TEX_OPT % name)
            used.add(str(name))
        figs = [n for n in figs if n not in used]
    if not figs:
        return 0

    refs = [FIG_TEX % n for n in figs]
    put = 0

    def repl(_m):
        nonlocal put
        if put >= len(refs):
            return ""                      # 多出来的占位行：删掉
        ref = refs[put]
        put += 1
        return "\n\n" + ref + "\n"

    for field in ("题干", "解析"):
        text = rec.get(field) or ""
        if text:
            rec[field] = FIG_PH.sub(repl, text)

    if put < len(refs):                    # 没占位的图：挂到题干末尾
        rec["题干"] = ((rec.get("题干") or "").rstrip() + "\n\n"
                       + "\n\n".join(refs[put:]))
        put = len(refs)
    return put


def assign_figs(book: list[dict], layout: dict) -> None:
    r"""按坐标把图分到题（就地改 `rec["figs"]`）。

    题目区间 = **本题起点 → 下一题起点**（同一页内按 y 排）。
    起点怎么找：拿题干头 12 个字去该页的文本块里做包含匹配；
    另外从版面里**补一遍题号边界**——被拒收的题不会出现在 `book` 里，
    但它的位置仍然是一道边界，不补的话上一题会把它的图一起吞掉。
    匹配不上就退回"整页的图都给它"——宁可多给，不要漏。
    """
    starts: dict[int, list[tuple[float, int]]] = {}
    for r in book:
        pages = r.get("页码") or []
        if not pages:
            continue
        lay = layout.get(pages[0]) or {}
        head = _norm_txt(r.get("题干"))[:12]
        y0, xs = None, (0.0, 1.0)
        for a, _b, txt, x0, x1 in lay.get("texts", []):
            if head and head in _norm_txt(txt):
                y0, xs = a, (x0, x1)
                break
        r["_y0"] = y0
        r["_xs"] = xs
        if y0 is not None:
            starts.setdefault(pages[0], []).append((y0, r["题号"]))
    # 版面里的题号边界：`4.（本题5分）…` 这种块的第一行。
    for page, lay in layout.items():
        for a, _b, txt, _x0, _x1 in lay.get("texts", []):
            m = _QNO.match(txt)
            if m:
                starts.setdefault(page, []).append((a, int(m.group(1))))
    for v in starts.values():
        v.sort()

    for r in book:
        pages = r.get("页码") or []
        if not pages:
            r["figs"] = []
            continue
        lay = layout.get(pages[0]) or {}
        y0 = r.get("_y0")
        if y0 is None:                       # 找不到起点：整页都给
            r["figs"] = [n for _y, n in lay.get("images", [])]
            continue
        nxt = [y for y, _n in starts.get(pages[0], []) if y > y0 + 1e-6]
        y1 = min(nxt) if nxt else 1.0
        r["_yrange"] = [round(y0, 4), round(y1, 4)]   # 归一化纵向区间（裁图用）
        # 纵向 + **横向**：同页两栏时只按 y 会把另一栏的图挂过来。
        lo, hi = r.get("_xs", (0.0, 1.0))
        lo, hi = lo - 0.12, hi + 0.12
        keyed = [(k, n) for k, n in lay.get("images", [])
                 if (y0 - 0.004) / 0.05 <= k[0] < y1 / 0.05
                 and lo <= k[1] <= hi]
        keyed.sort(key=lambda kn: kn[0])
        r["figs"] = [n for _k, n in keyed]

        # **选项本身是图**（四选一的图象题）：四个空选项 + 四张图，
        # 按阅读顺序一一配上，界面才能画出 A./B./C./D. 各自的图。
        opts = r.get("选项") or {}
        if (r["figs"] and opts and len(opts) == len(r["figs"])
                and all(not (v or "").strip() for v in opts.values())):
            r["opt_figs"] = {k: r["figs"][i] for i, k in enumerate(sorted(opts))}
            # 题干里那些「（图）」占位行这时候已经没意义了，留着只会串行
            r["题干"] = re.sub(r"(?m)^\s*（图）\s*$", "", r.get("题干") or "")
            r["题干"] = re.sub(r"\n{3,}", "\n\n", r["题干"]).strip()
        r.pop("_y0", None)


def _audit(pdf: Path, work: Path, ev) -> None:
    r"""双 OCR 对账：**只记账，不改正文**。

    第二个引擎（GLM-OCR）跑一遍同一批页图，跟 Paddle 的文本比字数/题号。
    差异页写进 `v2/ocr_check.json`，失败不拦流程——它是体检，不是闸门。
    """
    try:
        from . import dual
        r = dual.audit_pages(work, pdf)
        if r.get("可疑"):
            ev("双 OCR 对账：%d 页有差异（见 v2/ocr_check.json）" % len(r["可疑"]))
    except Exception as e:                                     # noqa: BLE001
        ev("双 OCR 对账跳过：%s" % str(e)[:60])


def run_v2(pdf, *, answers=None, book: str = "模拟题", label: str = "",
           year: int | None = None, force: bool = False, on_event=None,
           dual_ocr: bool = False, answer_model: str = "",
           **_ignored) -> dict:
    r"""一份 PDF → `record.run()` 同构的结果（供批量录题脚本直接替换）。

    **只产文本，不写库**：tex 交给 `ingest.preview/commit` 那条唯一入口。
    返回值里 `stats` / `kept` / `dropped` / `register` 的字段名与 v1 一致，
    调用方不用改。
    """
    from . import store

    pdf = Path(pdf)
    label = label or pdf.stem

    def ev(text: str) -> None:
        if on_event:
            on_event({"type": "stage", "text": text})

    ev("识别卷面（PaddleOCR-VL）")
    rows = scan_pdf(pdf, force=force)
    if dual_ocr:
        _audit(pdf, work_of(pdf), ev)
    if on_event:                      # 整卷解析是一次性的，没有逐页回调；
        on_event({"type": "page", "page": len(rows), "total": len(rows),
                  "cached": force is False})   # 补一条，进度条才有分母

    if answers:
        # **两份 PDF**：试卷一份、答案一份。答案那份单独扫描，
        # 不再去试题里找「参考答案」分界——合订本才需要那一步。
        ev("识别答案卷")
        a_rows = scan_pdf(Path(answers), force=force)
        if dual_ocr:
            _audit(Path(answers), work_of(Path(answers)), ev)
        q_rows = rows
        split_info: dict = {"at": None, "why": ["答案在另一个文件"]}
    else:
        q_rows, a_rows, split_info = split_answer_pages(rows)
        if split_info.get("at"):
            ev("解析从第 %d 页开始（%s）" % (split_info["at"],
                                        "、".join(split_info["why"])))
        elif split_info.get("cands"):
            # 只有 2 分：不切，但把候选页码留着，界面能看见"我怀疑在哪"
            ev("没找到解析分界（候选页：%s）"
               % ",".join(str(c["page"]) for c in split_info["cands"]))

    ev("结构化试题（%d 页）" % len(q_rows))
    st_q = structure(q_rows, "试卷")
    st_a = {"items": [], "lines": []}
    if a_rows:
        # **答案卷能按标题正则切块，就不用调模型**：21 页答案的 prefill 要
        # 三分钟，而 `### 12. AC` 这种标题是规则文本，正则切得又快又全。
        # 切不出来（版式不规整）才退回模型。
        a_lines = build_doc(a_rows)[1]
        ab = answer_blocks(a_lines)
        if len(ab) >= 2:
            st_a = {"items": [], "lines": a_lines}
        else:
            ev("结构化答案（%d 页）" % len(a_rows))
            st_a = structure(a_rows, "答案", model=answer_model)

    # 卷首速查表：有就拿来做交叉校验（没有就跳过，不猜）
    table = parse_answer_table(a_rows) if a_rows else {}
    if table:
        ev("速查表：读到 %d 个答案，待校验" % len(table))
    res = assemble(st_q, st_a, label, answer_table=table)
    res["答案分界"] = split_info
    # **一道都没收下就别让流程继续往下走**：最像"OCR 坏了"的那种现场，
    # 其实多半是两份 PDF 传反了（实测：pdf=…答案.pdf、answers=…试卷.pdf，
    # 答案卷被当试卷切，每道题都"选项 0 个"，界面上看着一片狼藉）。
    if not res["book"] and res["reject"]:
        raise RuntimeError(
            "一道题都没收下（%d 道被拒，第一道的原因是：%s）。\n"
            "先看两份 PDF 有没有传反——试卷那栏放试卷、答案那栏放答案；"
            "再确认扫描件没掉行（第 1 题题干在不在）。"
            % (len(res["reject"]), (res["reject"][0].get("原因") or ["?"])[0]))

    # 按块裁好的插图：数学卷里「四选一的图象题」正文全是 `（图）` 占位，
    # 不给图根本没法审。拿不到就空着，不影响别的。
    try:
        from . import engine
        eng = engine.get()
        eng.figures(pdf, work_of(pdf))             # 保证裁图与版面都落盘
        assign_figs(res["book"], eng.layout(work_of(pdf)))
    except Exception:                                         # noqa: BLE001
        pass

    # 选项不全的选择题：看图补（最多 6 题）
    try:
        complete_options(pdf, work_of(pdf), res["book"], on_event=on_event)
        # 被拒的选择题也补一遍，补到 4 个就复判、能过就收回来
        retry = [r for r in res["reject"]
                 if r.get("题型") in ("single_choice", "multi_choice")
                 and len(r.get("选项") or {}) < 4]
        if retry:
            complete_options(pdf, work_of(pdf), retry, on_event=on_event)
            for r in list(retry):
                if len(r.get("选项") or {}) < 4:
                    continue
                why = gate(r["题型"], r["题干"], r["选项"], r["答案"], r["解析"])
                if not why:
                    res["reject"].remove(r)
                    r.pop("原因", None)
                    res["book"].append(r)
            res["book"].sort(key=lambda x: int(x["题号"]))
    except Exception:                                         # noqa: BLE001
        pass

    # 打考点：一题一次。失败不影响出题，宁可空着。
    if on_event:
        ev("标考点（%d 题）" % len(res["book"]))
    try:
        tag_points(res["book"])
    except Exception:                                         # noqa: BLE001
        pass
    tex = []
    kept = []
    for rec in res["book"]:
        # 题干像有图、但坐标里没切到图 → 标记为"挂原页"，界面直接给整页
        fallback = (not (rec.get("figs") or [])
                    and bool(rec.get("页码"))
                    and bool(FIG_HINT.search(rec.get("题干") or "")))
        # **先留档再清洗**：把要删掉的东西记进 数据/录题/噪声样本.jsonl，
        # 攒够样本再一次性定规则，比"见一个补一条正则"靠谱。
        try:
            from . import noise as NZ
            NZ.record(label, rec["题号"], "题干", rec["题干"])
            NZ.record(label, rec["题号"], "解析", rec["解析"])
        except Exception:                                     # noqa: BLE001
            pass
        # 识别结果里可能混进 HTML，题干和解析都要清
        rec["题干"] = QLT.strip_html(rec["题干"])
        rec["解析"] = QLT.strip_html(rec["解析"])
        # **配图要赶在清洗前挂**：`（图）` 占位行是它唯一的位置信息。
        # 只把图挂在 `kept["figs"]` 上给界面看、正文留个占位符，录进库就是
        # 一道没图的题——2026-10-27 之前一直如此。
        try:
            attach_figs(rec)
        except Exception:                                     # noqa: BLE001
            pass
        # 占位行这时已经被图替掉了；剩下没图可替的才清掉
        rec["题干"] = re.sub(r"(?m)^\s*（图）\s*$", "", rec["题干"] or "")
        rec["题干"] = re.sub(r"\n{3,}", "\n\n", rec["题干"]).strip()
        rec["题干"] = QLT.fix_blanks(rec["题干"], rec["答案"], rec["题型"])
        rec["题干"] = QLT.repair_math(rec["题干"])
        rec["解析"] = QLT.repair_math(rec["解析"])
        # **转 Question 必须在清洗之后。** 原先在清洗前就建好了 `q`，
        # 后面只改 `rec`，于是落盘的 tex 还是带 `（图）` 的旧题干——实测踩过。
        try:
            q = rec_to_question(rec, label, book)
        except Exception as e:                                # noqa: BLE001
            res["reject"].append(dict(rec, 原因=["转 Question 失败：%s" % e]))
            continue
        # 正文里的 `\includegraphics` 是图的唯一真相：`figures` 必须由它推导，
        # 否则元数据行（以及内容指纹）和正文对不上。
        from .latex_ir import derive_figures
        q.figures = derive_figures(q.stem, q.solution, *(o.text for o in q.options))
        single = store.render_question(q)
        tex.append((q.meta.get("source_no") or rec["题号"], single))
        kept.append({"n": rec["题号"],
                     "type": EN2TYPE.get(rec["题型"], rec["题型"]),
                     "figure": bool(rec.get("粗筛图")) or bool(rec.get("figs"))
                               or bool(fallback),
                     "stem": rec["题干"],
                     "pages": rec.get("页码") or [],
                     "figs": rec.get("figs") or [],
                     "yrange": rec.get("_yrange") or [],
                     "opt_figs": rec.get("opt_figs") or {},
                     "fig_fallback": bool(fallback),
                     "point": rec.get("point") or "",
                     "point_title": rec.get("point_title") or "",
                     "points": rec.get("points") or (
                         [rec["point"]] if rec.get("point") else []),
                     "quality": QLT.check(QLT.repair_math(rec["题干"]),
                                          QLT.repair_math(rec["解析"]),
                                          rec["答案"],
                                          # ⚠️ `quality.check` 只认英文题型枚举。
                                          # 这里原来传的是中文「单选」——于是
                                          # "选择题没有答案/答案不是 A–D/选项只有 N 个"
                                          # 整族检查**一次都没跑过**，选择题坏答案照样绿。
                                          EN2TYPE.get(rec["题型"], rec["题型"]),
                                          rec.get("选项") or {}),
                     "ans": rec["答案"], "sol": rec["解析"],
                     # 配对依据（题号/顺序/内容）+ 速查表冲突，界面直接显示
                     "pair": rec.get("配对") or "",
                     "table": rec.get("速查表") or "",
                     # 存成 [[label, text], …]：审阅界面按数组渲染，
                     # patch 接口也按数组重建 tex；存 dict 两处都会炸。
                     "options": [[k, v] for k, v in sorted((rec["选项"] or {}).items())],
                     "tex": single})
    tex.sort(key=lambda kv: kv[0])
    body = "\n\n".join(t for _n, t in tex)

    # P0 质检：解析串题 / 题干串行 / 选项异常
    prev_sol = ""
    for k in kept:
        extra = QLT.check_ownership(k.get("sol") or "", k["n"], prev_sol)
        extra += QLT.check_stem_leak(k.get("stem") or "", k["n"])
        extra += QLT.check_options_sane({o[0]: o[1] for o in (k.get("options") or [])})
        if extra:
            q = k.get("quality") or {}
            q["issues"] = list(q.get("issues") or []) + extra
            if q.get("level") == "高":
                q["level"] = "中"
            k["quality"] = q
        # 渲染失败 / 串题 / 混题 属于"入不了库"的硬伤，直接降到低分档
        if any(str(i).startswith(("公式渲染失败", "解析开头", "题干里混入"))
               for i in (k["quality"].get("issues") or [])):
            k["quality"]["level"] = "低"
        prev_sol = k.get("sol") or ""

    # KaTeX 真渲染：一次 node 进程批量校验，把"渲染就炸"的题标出来
    try:
        from . import render_check as RC
        if RC.available() and kept:
            errs = RC.check([{"id": k["n"],
                              "segs": RC.segments(k["stem"]) + RC.segments(k["sol"])}
                             for k in kept])
            for k in kept:
                es = errs.get(k["n"]) or []
                if es:
                    k["quality"]["issues"] = list(k["quality"].get("issues") or []) + \
                        ["公式渲染失败：%s" % es[0]]
                    if k["quality"].get("level") == "高":
                        k["quality"]["level"] = "中"
    except Exception:                                         # noqa: BLE001
        pass

    # **没入库的题要留账**：闸门拒收的、转 Question 失败的，全都在这儿。
    # 只留在任务 JSON 里不够——任务目录是给"这一次运行"用的，
    # 过几天清掉就再也说不清"这份卷子当时少了哪几道、为什么"。
    # 所以按卷落一份，跟中间产物放一起，不跟题库混。
    side = work_of(pdf) / "未入库.json"
    side.parent.mkdir(parents=True, exist_ok=True)
    lost = res["reject"]
    side.write_text(json.dumps(lost, ensure_ascii=False, indent=1), encoding="utf-8")
    (side.parent / "未入库.md").write_text(
        "# %s · 未入库 %d 道\n\n" % (label, len(lost))
        + "\n".join("- **第 %s 题**（%s）：%s\n  > %s" % (
            r.get("题号"), r.get("题型"), "；".join(r.get("原因") or []),
            (r.get("题干") or "")[:80].replace("\n", " "))
          for r in lost)
        + "\n", encoding="utf-8")

    stats = {
        "卷": label, "出处": "%s%s" % (year or "", label), "标题": label,
        "页数": len(rows), "识别到": len(res["book"]),
        "录入": len(kept), "带图丢弃": 0, "带图登记位置": len(res["pending"]),
        "未录入": len(res["reject"]),
        "无解析": sum(1 for q in kept if not q["sol"].strip()),
        "已打考点": 0, "失败页": [],
        # 配对怎么配上的、速查表有没有对不上的 —— 「这卷可不可信」的核心指标
        "配对": res.get("配对") or {},
        "速查表冲突": sum(1 for q in kept if q.get("table")),
        "每题配对": {q["n"]: q.get("pair") or "" for q in kept},
        # 同一文件合订时：解析从第几页开始、凭什么判的
        "答案分界": res.get("答案分界") or {},
        "题型": {t: sum(1 for q in kept if q["type"] == t)
                 for t in ("单选", "多选", "填空", "解答")},
    }
    return {"tex": body, "kept": kept, "dropped": [], "register": res["pending"],
            "lost": res["reject"], "stats": stats, "scans": rows,
            "label": label, "year": year or 0, "title": label}


def _selftest() -> int:
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("record2 自检")

    # 题型按题号（规矩 R1）
    check("题型按题号：1-8 单选", all(BY_NO[i] == "单选" for i in range(1, 9)))
    check("题型按题号：9-11 多选", all(BY_NO[i] == "多选" for i in range(9, 12)))
    check("题型按题号：12-14 填空", all(BY_NO[i] == "填空" for i in range(12, 15)))
    check("题型按题号：15-19 解答", all(BY_NO[i] == "解答" for i in range(15, 20)))

    # 键名兼容：交接文档 §5 的**英文键**（给大模型看的）与流水线的**中文键**都要认。
    # 实测坑：照文档写好的 JSON 直接喂 `rec_to_question`，第一行就 KeyError: '题号'。
    doc_rec = {"no": 13, "type": "fill_in_blank",
               "stem": "若 $S_{15}=5(a_{2}+a_{7}+a_{k})$，则正整数 $k$ 的值为\\fillin{}",
               "options": {}, "answer": "15", "solution": "解析无", "pages": [3]}
    q1 = rec_to_question(doc_rec, "键名自检")
    q2 = rec_to_question({"题号": 13, "题型": "fill_in_blank", "题干": doc_rec["stem"],
                          "选项": {}, "答案": "15", "解析": "解析无"}, "键名自检")
    check("英文键（文档 §5）能直接入库",
          q1.key == "模拟题/键名自检#13" and q1.answer == "15", q1.key + repr(q1.answer))
    check("英文键与中文键结果一致",
          (q1.key, q1.answer, q1.stem) == (q2.key, q2.answer, q2.stem))
    check("空位被规范化填上答案", "\\fillin[15]" in q1.stem, q1.stem)

    # 书名必须带进 key 与 meta：写死「模拟题」会让高考卷永远是"模拟"，
    # 还会跟库里同卷的 key 对不上（升级变成重复入库）。
    q3 = rec_to_question(doc_rec, "键名自检", book="高考真题汇编")
    check("书名决定入库 key（不是写死模拟题）",
          q3.key == "高考真题汇编/键名自检#13", q3.key)
    check("书名决定 meta.book 与 kind",
          q3.meta.get("book") == "高考真题汇编" and q3.kind == "高考",
          "%r / %r" % (q3.meta.get("book"), q3.kind))

    # 配图：图只挂在 `figs` 上、正文留个 `（图）`，录进库就是没图的题。
    # 2026-10-27 实测：界面里裁图好好的，入库后题干只有「（图）」。
    r1 = {"题干": "如图，求 $x$。\n（图）\n（图）", "解析": "", "figs": ["a.jpg"]}
    check("配图：一张图替掉两行占位（同一张图被识别成两段）",
          attach_figs(r1) == 1 and r1["题干"].count("includegraphics") == 1
          and "（图）" not in r1["题干"], r1["题干"])
    r2 = {"题干": "题干。", "解析": "", "figs": ["a.jpg", "b.jpg"]}
    check("配图：没有占位就挂到末尾",
          attach_figs(r2) == 2 and "a.jpg" in r2["题干"] and "b.jpg" in r2["题干"])
    r3 = {"题干": "哪个图象对？", "解析": "", "选项": {"A": "", "B": ""},
          "figs": ["a.jpg", "b.jpg"], "opt_figs": {"A": "a.jpg", "B": "b.jpg"}}
    check("配图：选项图写进选项、不占题干",
          attach_figs(r3) == 0 and "a.jpg" in r3["选项"]["A"]
          and "（图）" not in r3["题干"])

    # 分图边界：被拒收的题不在 book 里，但它的位置仍是边界；
    # 不补边界的话，上一题会把下一题的图一起吞掉（实测第 6 题拿到第 7 题的梯形）。
    _lay = {1: {"texts": [(0.10, 0.20, "1. 第一题", 0.0, 1.0),
                          (0.60, 0.70, "2. 第二题", 0.0, 1.0)],
                "images": [((3, 0.5), "a.jpg"), ((13, 0.5), "b.jpg")]}}
    _book = [{"题号": 1, "题干": "第一题", "页码": [1], "选项": {}}]
    assign_figs(_book, _lay)
    check("分图：下一题被拒收时，不能把它的图挂到上一题",
          _book[0]["figs"] == ["a.jpg"], str(_book[0]["figs"]))

    # 选项切分：**一行并排四个**（A10 的常态）
    stem, opts = split_stem_options(["1. 已知集合 ( )",
                                     "A. $\\{1,2\\}$ B. $\\{0,1\\}$ C. $x$ D. $y$"])
    check("一行四个选项要拆开", set(opts) == {"A", "B", "C", "D"} and
          opts["B"] == "$\\{0,1\\}$", str(opts))
    check("题干与选项分开", stem == "1. 已知集合 ( )", stem)
    stem2, opts2 = split_stem_options(["f1 已知函数 ( )", "I. 函数有相同的极小值",
                                       "B. 若方程有唯一实根", "C. 若 $x_1>0$",
                                       "D. 当 $a>1$ 时"])
    check("坏标签（I.）留在题干里等补全", set(opts2) == {"B", "C", "D"}, str(opts2))

    # 引用锚剪枝：`f1 已知函数…` 要一刀剪掉 **f1 两个字符**（不是只剪 f）
    _t, _c = cut_before_quote("f1 已知函数 $f(x) = xe^x$", "已知函数 $f(x) = xe^x$")
    check("引用锚剪枝：坏字要剪干净", _t.startswith("已知函数") and _c.strip() == "f1",
          "%r / %r" % (_t[:14], _c))
    check("引用锚剪枝：引用不在开头就不动",
          cut_before_quote("已知函数 $f(x)$，求 $f(1)$", "求 $f(1)$")[0]
          == "已知函数 $f(x)$，求 $f(1)$")
    check("引用锚剪枝：引用太短不当锚",
          cut_before_quote("f1 已知函数", "已知")[0] == "f1 已知函数")

    # 清洗：分值 / 页脚 / 卷面坏字，**顺序**是关键
    s, sol, o, notes = clean_fields(
        "15. (13分) 已知函数 $f(x)=x$。", "由题意得 $x=1$。\n\n数学试题 第2页 共4页",
        qtype="detailed_answer", opts={})
    check("去分值：题干", s == "已知函数 $f(x)=x$。", repr(s))
    check("去页脚：解析", "第2页" not in sol and "由题意得" in sol, repr(sol))
    check("记了清洗动作", "去分值" in notes and "解析去页脚" in notes, str(notes))
    # 用例照 A10 第 11 题的**真实现场**写：两行——坏题号那行是题干，
    # 第二行是印坏标签的 A 选项（原图印成「£/匚」样，OCR 读成 `I.`）。
    s2, _sol2, o2, notes2 = clean_fields(
        "f1 已知函数 $f(x) = xe^x$，则下列说法正确的是 ( )\n"
        "I. 函数 $f(x),g(x)$ 有相同的极小值",
        "", qtype="multi_choice", opts={"B": "b", "C": "c", "D": "d"})
    check("剪掉卷面坏字 f1", s2.startswith("已知函数"), repr(s2[:20]))
    check("补回缺失的 A 选项", set(o2) == {"A", "B", "C", "D"} and o2["A"], str(o2))
    check("补回的 A 选项内容对", o2.get("A", "").startswith("函数 $f(x)"), str(o2))
    check("A 那一行已从题干移走", "极小值" not in s2, repr(s2))
    s3, _s3, _o3, _n3 = clean_fields("f(x) = x^2 的最小值是 $0$。", "",
                                     qtype="fill_in_blank", opts={})
    check("正常公式开头**不能**被当坏字剪", s3.startswith("f(x)"), repr(s3))

    # 答案册的 Markdown 标题 `### 2. A`：闸门把行首 `#` 当版面家具，
    # 实测第六套 19 题拒了 11 题。标题只留文字。
    _s4, _sol4, _o4, _n4 = clean_fields(
        "已知 $x$ 求 $y$", "### 2. A\n【分析】由题意得", qtype="single_choice",
        opts={"A": "1", "B": "2", "C": "3", "D": "4"})
    check("解析开头的 ### 标题要剥掉，否则整卷被判版面家具",
          "###" not in _sol4 and not gate("single_choice", _s4, _o4, "A", _sol4),
          _sol4[:20])

    # 闸门
    # 标答是四个，但 OCR 常丢掉某个选项的标签；**3 个放行**（`clean_fields`
    # 会从题干末尾把它捞回来），2 个才是真残缺。
    check("闸门：选项只有 2 个 → 拒收",
          any("选项" in w for w in gate("multi_choice", "x ( )",
                                        {"B": "b", "C": "c"}, "BC", "s")))
    check("闸门：选项有 3 个 → 放行（缺的标签能补回来）",
          not any("选项" in w for w in gate("multi_choice", "x ( )",
                                            {"B": "b", "C": "c", "D": "d"},
                                            "BCD", "s")))
    check("闸门：四个选项 → 过",
          not gate("multi_choice", "x ( )", {"A": "a", "B": "b", "C": "c", "D": "d"},
                   "BCD", "故选 BCD"))
    check("闸门：客观题答案是整段解析 → 拒收",
          any("整段解析" in w for w in gate("fill_in_blank", "x = ___", {}, "长" * 50, "")))
    check("闸门：`$` 不成对 → 拒收",
          any("不成对" in w for w in gate("fill_in_blank", "求 $x 的值（", {}, "1", "")))
    check("闸门：`$` 成对就不报", not any(
        "不成对" in w for w in gate("fill_in_blank", "求 $x$ 的值（", {}, "1", "")))
    # 行内公式漏收尾 `$`，`\[` 被并进 `$…$`：`$` 数是偶数，只查"成对"放过去，
    # 但 KaTeX 在段内遇到 `\[` 直接报错（湖南雅礼 #15 就是这么进库的）。
    check("闸门：`\\[…\\]` 夹在 `$…$` 里 → 拒收",
          any("夹在" in w for w in gate(
              "fill_in_blank", "x = ___", {}, "1",
              "$a=2\\sqrt{2}\\[x\\]$")))
    check("闸门：行内公式闭合、另起行间公式 → 不报", not any(
        "夹在" in w for w in gate(
            "fill_in_blank", "x = ___", {}, "1",
            "$a=2\\sqrt{2}$\n\\[x\\]")))
    # 反向：`$x$ ，\[\n…\n\] $y$`（行间公式夹在两个行内段**之间**）是合法写法，
    # 不能因为"两个 `$` 中间有 `\[`"就误判。
    check("闸门：行间公式夹在两个行内段之间 → 不报", not any(
        "夹在" in w for w in gate(
            "fill_in_blank", "x = ___", {}, "1",
            "当 $x$ ，\n\\[\ny=1\n\\]\n$y$ 成立")))
    # `cases` 里换行带行距 `\\[4pt]` 很常见，那不是行间公式定界符
    check("闸门：`cases` 里的 `\\\\[4pt]` 不算行间公式", not any(
        "夹在" in w for w in gate(
            "fill_in_blank", "x = ___", {}, "1",
            "$\\begin{cases}a\\\\[4pt]b\\end{cases}$")))
    check("闸门：残留页脚 → 拒收",
          any("页脚" in w for w in gate("fill_in_blank", "求 $x$ 的值。第 3 页 共 8 页",
                                        {}, "1", "")))
    check("闸门：版面家具 → 拒收",
          any("家具" in w for w in gate("fill_in_blank", "一、选择题：本题共8小题",
                                        {}, "1", "")))
    # KaTeX 四类硬伤（accept 层③ 实测的 40 处）
    check("闸门：HTML 实体 → 拒收",
          any("HTML 实体" in w for w in gate("fill_in_blank", "若 $a &lt; -1$", {}, "1", "")))
    check("闸门：字面量 \\n → 拒收",
          any("字面量" in w for w in gate("fill_in_blank", "求 $\\n\\cdot x$", {}, "1", "")))
    check("闸门：`^'` → 拒收",
          any("撇号" in w for w in gate("fill_in_blank", "求 $(\\tanh x)^'$", {}, "1", "")))
    check("闸门：`\\left` 缺 `\\right` → 拒收",
          any("不配平" in w for w in gate("fill_in_blank", "得 $\\left\\{ a>0$",
                                        {}, "1", "")))
    check("闸门：`\\left…\\right.` 合法就不报", not any(
        "不配平" in w for w in gate("fill_in_blank", "得 $\\left\\{ a>0 \\right.$",
                                    {}, "1", "")))

    check("闸门：选择题答案是中文 → 拒收",
          any("应为字母" in w for w in gate("single_choice", "x ( )",
                                            {"A": "a", "B": "b", "C": "c", "D": "d"},
                                            "第一", "")))

    # **题型由文本定，不由模型定**（讲义没有 1–19 的题号，只能看题长什么样）
    _opts4 = {"A": "a", "B": "b", "C": "c", "D": "d"}
    check("题型：四选项 + 答案 BCD → 多选",
          classify_type("x（ ）", _opts4, "BCD")[0] == "multi_choice")
    check("题型：四选项 + 答案 A → 单选",
          classify_type("x（ ）", _opts4, "A")[0] == "single_choice")
    check("题型：四选项但没答案 → 单选，且标「待核」",
          classify_type("x（ ）", _opts4, "")[0] == "single_choice"
          and "待核" in classify_type("x（ ）", _opts4, "")[1])
    check("题型：`\\fillin` → 填空",
          classify_type("求 $x$ 的值 \\fillin{}", {}, "")[0] == "fill_in_blank")
    check("题型：`____` → 填空",
          classify_type("则 $a=$ ____", {}, "")[0] == "fill_in_blank")
    check("题型：无选项无空位 → 解答",
          classify_type("证明 $a>b$", {}, "")[0] == "detailed_answer")
    check("题型：选项没切出来、题干里有 A．B．C．D．→ 仍判选择",
          classify_type("已知 A．1 B．2 C．3 D．4", {}, "B")[0] == "single_choice")
    check("题型：末尾空括号、选项丢了 → 判选择（交给闸门拒，不当解答入库）",
          classify_type("已知集合 $A$，则下列正确的是（ ）", {}, "")[0]
          == "single_choice")

    # 跨页：一条题的区间跨过页标记时，页码要算两页
    lines = [(1, "8. 题干", 1), (2, "A. 甲", 1), (3, "B. 乙", 2), (4, "C. 丙", 2)]
    check("跨页题覆盖两页", covered_pages(lines, (1, 4)) == [1, 2],
          str(covered_pages(lines, (1, 4))))
    check("单页题只算一页", covered_pages(lines, (3, 4)) == [2], str(covered_pages(lines, (3, 4))))

    # 抠 JSON：围栏 / 前后废话 / 截断
    check("抠 JSON：带 ```json 围栏", grab_json('```json\n{"questions":[{"n":1}]}\n```')
          == {"questions": [{"n": 1}]})
    _cut = grab_json('{"questions":[{"n":1,"start":2},{"n":2,"star')
    check("抠 JSON：被截断也能收下完整的对象",
          (_cut or {}).get("questions") == [{"n": 1, "start": 2}], str(_cut))

    # token 估计：**汉字不能按 2 字符 1 token 算**。数字取自 26届拼好卷答案：
    # 487,593 字 → 服务端 301,911 token。
    _n = est_tokens("字" * 487593)
    check("48.8 万字要估到 30 万 token 以上（旧写法只估 24 万）",
          300000 < _n < 340000, str(_n))

    # 接口报错**不能把真话吞掉**。`except … as e:` 的 e 出块即删，之前的
    # 写法把「请求 301911 token 超过 262144 上下文」报成了 UnboundLocalError。
    import io as _io
    import urllib.error as _ue
    import urllib.request as _ur
    _old_open, _old_wait = _ur.urlopen, RETRY_WAIT
    globals()["RETRY_WAIT"] = 0.0

    def _raise_http(status: int, body: bytes):
        def f(*_a, **_k):
            raise _ue.HTTPError("http://x", status, "Bad Request", {},
                                _io.BytesIO(body))
        return f

    def _raise_net(*_a, **_k):
        raise _ue.URLError(ConnectionRefusedError(61, "Connection refused"))

    def _err_of() -> str:
        try:
            _post("http://x", "m", [], maxtok=1)
        except RuntimeError as ex:
            return str(ex)
        return ""

    try:
        _ur.urlopen = _raise_http(400, b'{"message":"request (301911 tokens) '
                                       b'exceeds the available context size '
                                       b'(262144 tokens)"}')
        _m400 = _err_of()
        _ur.urlopen = _raise_http(503, b"")
        _m503 = _err_of()
        _ur.urlopen = _raise_net
        _mnet = _err_of()
    finally:
        _ur.urlopen = _old_open
        globals()["RETRY_WAIT"] = _old_wait
    check("接口 400 → 报错里带状态码和原文",
          "400" in _m400 and "exceeds the available context size" in _m400, _m400)
    check("接口 503 → 报错里带状态码", "503" in _m503, _m503)
    check("连不上 → 报错里带原因（不是 UnboundLocalError）",
          "URLError" in _mnet and "Connection refused" in _mnet, _mnet)

    # ── 题目 ↔ 解析 的配对 ──────────────────────────────────────
    def _qs(*spec):
        return [(n, {"n": n, "start": s, "quote": q}) for n, s, q in spec]

    def _as(*spec):
        return [(n, {"n": n, "start": s, "end": e}) for n, s, e in spec]

    idx_a = {10: "已知函数 $f(x)=x^2$ 在区间上的最小值", 11: "由题意得 3",
             12: "解方程组得 x=2", 14: "概率为 1/4",
             30: "甲乙丙丁戊己", 31: "子丑寅卯辰巳"}
    q1 = _qs((1, 1, "已知函数 $f(x)=x^2$ 在区间上的最小值"), (2, 5, "解方程组得 x"),
             (3, 9, "概率为 1/4"))
    a1 = _as((1, 10, 11), (2, 12, 12), (3, 14, 14))
    pairs, info = align(q1, a1, idx_a)
    check("题号完整且一致 → 全按题号配",
          all(v[1] == "题号" for v in pairs.values()) and len(pairs) == 3, str(info))

    # 题号被 OCR 读乱（1,7,3），但块数一样 → 按顺序配，不能按题号
    q2 = _qs((1, 1, "a"), (7, 5, "b"), (3, 9, "c"))
    pairs2, info2 = align(q2, a1, idx_a)
    check("题号乱序但块数相同 → 按顺序配",
          [v[1] for v in pairs2.values()] == ["顺序"] * 3, str(info2))

    # 解析少了一题 → 内容对齐：配上的两题必须找对
    a2 = _as((1, 10, 11), (2, 14, 14))
    pairs3, info3 = align(q1, a2, idx_a)
    got = {i: (p[1]) for i, p in pairs3.items()}
    check("解析缺一题 → 按内容配，不能整体错位",
          set(got) == {0, 2} and all(v == "内容" for v in got.values()),
          "%s %s" % (got, info3))

    # 内容对不上（换个题）→ 宁可不配
    a3 = _as((1, 30, 30), (2, 31, 31))
    pairs4, _i4 = align(q1, a3, idx_a)
    check("内容对不上 → 不配（不猜）", len(pairs4) == 0, str(pairs4))

    # 速查表：OCR 的 HTML 表格 → {题号: 答案}
    import tempfile as _tf
    with _tf.TemporaryDirectory() as _td:
        tp = Path(_td) / "p01.md"
        tp.write_text(
            "<table><tr><td>题号</td><td>1</td><td>2</td><td>3</td></tr>"
            "<tr><td>答案</td><td>D</td><td>BC</td><td>A</td></tr></table>",
            encoding="utf-8")
        tb = parse_answer_table([{"page": 1, "txt": str(tp)}])
        check("速查表：读出 3 个答案", tb == {1: "D", 2: "BC", 3: "A"}, str(tb))

        # 合订本：解析从第 2 页开始（标题 + 【分析】成片）
        for k, body in ((1, "1. 已知函数\n2. 求导\n19. 最后一题"),
                        (2, "参考答案\n【分析】由题意得\n【详解】所以")):
            (Path(_td) / ("p%02d.md" % k)).write_text(body, encoding="utf-8")
        rows = [{"page": k, "txt": str(Path(_td) / ("p%02d.md" % k))} for k in (1, 2)]
        qq, aa, _si = split_answer_pages(rows)
        check("合订本：认出解析在第 2 页", len(qq) == 1 and len(aa) == 1,
              str(_si))

    # ── 切块：锚点定位（试题）/ 标题正则（答案）─────────────────
    _L = [(1, "第一题 已知集合 $A=\\{1,2\\}$，则（ ）", 1),
          (2, "A. 1 B. 2 C. 3 D. 4", 1),
          (3, "## 二、多选题", 1),
          (4, "第二题 已知 $x>0$，则（ ）", 2),
          (5, "A. 甲 B. 乙 C. 丙 D. 丁", 2),
          (6, "第三题 求证：$a>b$。", 2)]
    _items = [{"n": 1, "quote": "已知集合 $A=\\{1,2\\}$，则"},     # 锚点命中
              {"n": 2, "quote": "已知 $x>0$，则"},                 # 锚点命中
              {"n": 3, "quote": "这句话原文里没有"}]
    _qb = question_blocks(_L, _items)
    check("切块：锚点定位（不靠模型给的行号）",
          [b["start"] for b in _qb] == [1, 4] and _qb[0]["src"] == "锚点",
          str([(b["start"], b["src"]) for b in _qb]))
    check("切块：终点 = 下一题起点 − 1（选项自然包含）",
          (_qb[0]["start"], _qb[0]["end"]) == (1, 3), str(_qb[0]))
    check("切块：块尾的大题标题要削掉",
          [t for t in _trim_edges([_L[1][1], _L[2][1]])] == [_L[1][1]],
          str(_trim_edges([_L[1][1], _L[2][1]])))

    _A = [(10, "### 1. B", 1), (11, "【分析】由题意得…", 1),
          (12, "### 2. AC", 2), (13, "【详解】…", 2),
          (14, "### 3. 7", 2)]
    _ab = answer_blocks(_A)
    check("切块：答案册按标题正则切（不用模型）",
          [(b["n"], b["start"], b["end"]) for b in _ab]
          == [(1, 10, 11), (2, 12, 13), (3, 14, 14)], str(_ab))
    check("切块：答案从标题行取（### 2. AC → AC）",
          _answer_of("### 2. AC", "", "multi_choice") == "AC")
    check("切块：正文里 `5. 正文` 这种不算答案标题",
          [b["n"] for b in answer_blocks([(1, "### 1. A", 1), (2, "5. 正文", 1),
                                          (3, "### 3. C", 1)])] == [1, 3],
          str(answer_blocks([(1, "### 1. A", 1), (2, "5. 正文", 1), (3, "### 3. C", 1)])))
    check("切块：跳号也认（第一套标题就是 2、3、4…，缺 1/7/9）",
          [b["n"] for b in answer_blocks([(1, "2. B", 1), (2, "3. A", 1)])] == [2, 3])

    # qwen3.5 标注的解析：考点必须来自清单，难度只收三档；坏 JSON 退正则。
    check("标注：JSON 里的考点+难度",
          _tag_reply('{"points":["1.1.1","不存在的"],"difficulty":"难题"}',
                     with_difficulty=True) == (["1.1.1"], "难题"))
    check("标注：围栏/多余解释也能收",
          _tag_reply('```json\n{"points":["1.1.1"],"difficulty":"中档题"}\n```',
                     with_difficulty=True) == (["1.1.1"], "中档题"))
    check("标注：非法难度丢掉，不拦考点",
          _tag_reply('{"points":["1.1.1"],"difficulty":"很难"}',
                     with_difficulty=True) == (["1.1.1"], ""))
    check("标注：JSON 失败退回正则",
          _tag_reply("最贴切的是 1.1.1", with_difficulty=True) == (["1.1.1"], ""))
    check("标注：老口径（只考点）仍走正则",
          _tag_reply('{"1":["1.1.1"]}', with_difficulty=False) == (["1.1.1"], ""))
    # 小模型常把候选行整行抄回；只认整串编号会把它们全丢掉（实测 4 道全丢）。
    check("标注：编号带标题也能抠出来",
          _tag_reply('{"points":["8.3.4 数量积的性质与应用"],"difficulty":"中档题"}',
                     with_difficulty=True) == (["8.3.4"], "中档题"))
    check("标注：编号前有 `第` 字也能抠出来",
          _point_ids(["第 5.2.3 题"]) == ["5.2.3"], str(_point_ids(["第 5.2.3 题"])))

    # 第二轮补标的本地粗筛：候选要包含正确考点，才谈得上让 9B 选。
    _c1 = [p["id"] for p in _shortlist_points("已知抛物线 $x^2=2py(p>0)$ 上两点", [])]
    _c2 = [p["id"] for p in _shortlist_points(r"已知 $S_n$ 是等比数列 \(\{a_n\}\) 的前 $n$ 项和", [])]
    _c3 = [p["id"] for p in _shortlist_points(
        r"在 $	riangle ABC$ 中，$AD \perp BC$，则 $\overrightarrow{AD}=$", [])]
    check("粗筛：抛物线题候选里有抛物线", "5.2.3" in _c1, str(_c1[:12]))
    check("粗筛：等比数列题候选里有等比数列", "7.3.1" in _c2, str(_c2[:12]))
    check("粗筛：向量题候选里有数量积", "8.3.4" in _c3, str(_c3[:12]))
    check("粗筛：不会把全部 153 条都塞回去", len(_c1) <= 24, str(len(_c1)))

    print("record2 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def _main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    what = sys.argv[1]
    if what == "selftest":
        return _selftest()
    if what == "reassemble":
        # 不重跑模型：拿已落的 struct JSON 重跑清洗+闸门。
        # 改清洗规则时要一遍遍看效果，**每次重跑 27B（3 分钟）太浪费**。
        src = Path(sys.argv[2])
        paper, answers, _sh = G.pick_pdfs(sorted(src.glob("*.pdf")))
        d = v2_dir(paper)
        st_q = json.loads((d / "struct_试卷.json").read_text(encoding="utf-8"))
        st_a = {"items": [], "lines": []}
        if answers:
            fa = v2_dir(answers[0]) / "struct_答案.json"
            if fa.exists():
                st_a = json.loads(fa.read_text(encoding="utf-8"))
        res = assemble(st_q, st_a, src.name)
        write_output(res, R.WORK / "输出_v2")
        print("重装配：%s  成品 %d / 拒收 %d / 待复核 %d / 孤儿 %d"
              % (src.name, len(res["book"]), len(res["reject"]),
                 len(res["pending"]), len(res["orphans"])))
        return 0
    if what in ("scan", "struct", "run"):
        t0 = time.time()
        res = run(Path(sys.argv[2]), phase=what)
        if res.get("error"):
            print("✗ %s" % res["error"])
            return 1
        print("%s：%s  用时 %.0fs" % (what, res.get("label"), time.time() - t0))
        for k in ("book", "reject", "pending", "orphans"):
            if k in res:
                print("  %-9s %d" % (k, len(res[k])))
        if "book" in res:
            write_output(res, R.WORK / "输出_v2")
            print("  产物 → %s" % (R.WORK / "输出_v2"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
