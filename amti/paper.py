"""AmTiKu · 三种卷型

**高考卷**（`gaokao`）—— 照高考真题的样子排
    标题 + 科目 + 信息行 + 注意事项 + 四个大题分节（带"只有一项符合"这类说明）

**测试题**（`test`）—— 考点专练
    * 开头**小字**列出本次覆盖的考点
    * 不分正式大题，按题型简单分节

**讲义**（`handout`）—— 一题一页 · A4 横版（见 `_render_handout`）

三种模式与 `export.py` 共用同一套渲染，只是头部分节不同。

两条对三种卷型一视同仁的规矩（用户的要求）：

  1. **每题默认印出处**——`（2023新高考II卷）`（**不带原卷题号**），并进题干同一行，
     实现只有一份（`_stem_with_source`，复用 `source_label`）；
  2. **卷面上不印难度**——难度是**内部排版**用的（解答题留白按难度给，
     见 `BLANK_BY_DIFFICULTY`），印给学生看没有意义：星级和「简单/中档/难题」
     从来不是题目自带的属性，出处的线索价值高得多。
"""
from __future__ import annotations

import copy as _copy
import re

from . import generate as gen
from . import latex_blocks as lb
from .schema import Question
from .render_tex import question_to_tex

# ── 答案标红（出卷子时）────────────────────────────────────────────────
#
# 用户要求：**答案要标红**，一眼能看到。
# 只在**卷面上会显示答案**的时候才染（学生版里答案本来就不印，
# 染了会把一对空括号也弄成红的）；**题库里存的 LaTeX 一个字都不动**——
# 这纯粹是出卷子这一步的修饰，和 `tikzfig.to_image` 一个性质。
#
# 为什么整块染色（把 `\paren[A]` 连括号一起包进 color 组）而不是只染里面的
# 字母：`exam-zh` 要按括号里的内容算宽度，把 `\textcolor` 塞进参数里有风险。
#
# ⚠️ **必须用"命名颜色"**：exam-zh 会把题干捕获进宏里，正文里写
# `{\color{#d22116}…}` 的 `#` 会被当成宏参数符，直接报
# `Illegal parameter number in definition of \XC@@tmp`（实测编译失败）。
# 所以导言区 `\definecolor`，正文只写颜色名。
ANS_RED = "amtiAnsRed"                     # 颜色名（定义见导言区）
ANS_RED_HEX = "D22116"                     # 与讲义/网页同一个红
_ANS_DEFINE = r"\definecolor{%s}{HTML}{%s}" % (ANS_RED, ANS_RED_HEX)

# 品牌页眉页脚。**这是版式，不是水印**：只占页边距里的页眉/页脚位，
# 不压正文、不斜铺、不影响阅读；和水印的区别是可以直接删掉而不伤内容。
BRAND_NAME = "AmTiKu"
BRAND_HEX = "CE338A"                       # 与网页/讲义同一个品牌色
BRAND_LABEL = "高中数学题库"

_ANS_MACRO = re.compile(r"(\\(?:paren|fillin)\s*\[|\\fillin\s*\{)")


def red_answer_macros(tex: str) -> str:
    r"""把 `\paren[…]` / `\fillin[…]` 整块染红（**只在出卷子时调用**）。

    ⚠️ 这里**不能**用 `[^\]]*` 去匹配作答位：答案里带右闭区间（`[4,5]`）时，
    第一个 `]` 就提前收尾，于是 `{\color{…}\fillin[…=[4,5}` 后面漏出一个 `}`，
    编译报 «Argument of \fillin has an extra }»——整份讲义直接出不来。
    收尾位置交给 `_blank_arg_end`（同一个配平扫描器，两份逻辑不许分叉）。
    """
    out: list[str] = []
    i = 0
    while True:
        m = _ANS_MACRO.search(tex, i)
        if not m:
            out.append(tex[i:])
            break
        open_ch = m.group(1)[-1]
        if open_ch == "[":
            end = _blank_arg_end(tex, m.end() - 1)
        else:
            end = tex.find("}", m.end())
        if end < 0:
            out.append(tex[i:])
            break
        out.append(tex[i:m.start()])
        out.append("{\\color{%s}%s}" % (ANS_RED, tex[m.start():end + 1]))
        i = end + 1
    return "".join(out)

# ── 按位置定难度 ──────────────────────────────────────────────────────
#
# 高考数学的惯例：**难度由题目在卷中的位置决定**，不是题目自带的属性。
#
# ⚠️ **难度不印到卷面上**（用户要求：跟讲义一样，印出处、不印难度）。
# 它现在的唯一去处是**解答题留白**（`blank_for`）：压轴题多留两行地方。
# 四条规律其实是一个模型：
#
#     前 N 个 → 简单题        后 M 个 → 难题        中间 → 中档题
#
#   选择题（8 道）  前 3 简单   后 2 难    中间 3 中档
#   多选题（3 道）  第 1 简单   第 3 难    第 2 中档
#   填空题（3 道）  第 1 简单   第 3 难    第 2 中档
#   解答题（5 道）  无         后 2 难    前 3 中档
#
# 所以每种题型只需要两个数：前面几个算简单、后面几个算难。
# 考点超过这个数就改用双栏排（notice 单栏列表会吃掉整页）
NOTICE_MAX_ITEMS = 10

POSITION_RULE = {
    "single_choice":   {"easy": 3, "hard": 2},
    "multi_choice":    {"easy": 1, "hard": 1},
    "fill_in_blank":   {"easy": 1, "hard": 1},
    "detailed_answer": {"easy": 0, "hard": 2},
}


def position_difficulty(qtype: str, index: int, total: int) -> str:
    r"""按题目在本题型中的位置定难度。`index` 从 0 开始。

    题数不是标准值时按同一模型收敛：简单和难各自**按比例缩放**，
    并且保证「简单段」与「难段」不重叠（题太少时以"后段难"为先，
    因为卷尾难是更强的规律）。
    """
    rule = POSITION_RULE.get(qtype)
    if not rule or total <= 0:
        return "中档题"

    easy, hard = rule["easy"], rule["hard"]
    # 题数比标准值少时按比例缩，但不缩到 0（除非规则本来就是 0）
    std = 8 if qtype == "single_choice" else 3
    if total < std:
        if easy:
            easy = max(1, round(easy * total / std))
        if hard:
            hard = max(1, round(hard * total / std))
    # 两段不许重叠：留至少一个中档位（题够多时）
    if total >= 3 and easy + hard > total - 1:
        easy = max(0, total - 1 - hard)

    if index < easy:
        return "简单题"
    if index >= total - hard:
        return "难题"
    return "中档题"


# 库里用到的**自定义 pgfplots 轴样式**。
#
# 有一批题的 TikZ 图是从原卷源码里抠出来的，用了原卷**预导言区**自定义的
# `exam statistical histogram`（频率分布直方图）。那个定义只存在于原卷源码里，
# 拷进我们库就丢了——少一条，卷子/讲义就是
#     ! Package pgfkeys Error: I do not know the key '/tikz/exam statistical histogram'
#
# ⚠️ **只留一份，两条导言路径共用。** 上次讲义另抄一份导言时漏了它，
# 讲义一编译就死；这次又漏了一次（600 道抽样抓到的）。
# 同一个东西有两份副本，早晚会漏——所以提成常量。
PGFPLOTS_STYLES: list[str] = [
    r"\pgfplotsset{",
    r"  exam statistical histogram/.style={",
    r"    ybar interval,",
    r"    bar width=1,",
    r"    axis lines=left,",
    r"    axis line style={-latex},",
    r"    tick align=outside,",
    r"    scaled y ticks=false,",
    r"    clip=false,",
    r"    tick label style={font=\normalsize},",
    r"    label style={font=\normalsize},",
    r"  },",
    # 另外两个是同一批图里用到的（`render-tikz` 当初就渲染不出这 4 道）：
    #   `exam statistical bar`  —— 条形图，样式只出绘图类型，外观题里都自己写了
    #   `exam statistical line` —— 折线图，题里写死了 `axis lines=none, ticks=none`
    r"  exam statistical bar/.style={ybar, bar width=1},",
    r"  exam statistical line/.style={sharp plot},",
    # ⚠️ 图例标签**不能写在 `\pgfplotsset` 里**：它是 `\node[...]` 的选项，
    # TikZ 找的是 `/tikz/` 作用域，而 `\pgfplotsset` 定义的是 `/pgfplots/`。
    # 写在里面就是"定义了但找不到"——报错还是 `I do not know the key`。
    # 这个用 `\tikzset` 单独定义，见 `TIKZ_STYLES`。,
    r"}",
]


# 需要用 `\tikzset`（`/tikz/` 作用域）定义的样式——**和 `PGFPLOTS_STYLES` 分开**。
# 判据：这个样式是给 `\node[...]` / `\draw[...]` 用的，还是给 `\begin{axis}[...]` 用的。
TIKZ_STYLES: list[str] = [
    r"\tikzset{",
    r"  exam statistical legend label/.style={anchor=west, inner sep=1pt,"
    r" font=\normalsize},",
    r"}",
]


def freq_label_cmd() -> str:
    r"""`\frequencyylabel[偏移]{x}{y}{文字}`——直方图上的 y 轴刻度标注。

    这个命令也是原卷预导言区里的，库里只有 `2009/浙江卷（文）#14` 用到。
    按调用形态反推：在轴坐标 `(x,y)` 处放一个右对齐的小标签。
    """
    return (r"\newcommand{\frequencyylabel}[4][0pt]{%" + "\n"
            r"  \node[anchor=east, inner sep=1pt, xshift=#1]"
            r" at (axis cs:#2,#3) {#4};}")


def _cap_figure_height(tex: str, cap: str = r"0.46\textheight") -> str:
    r"""给 `\includegraphics` 补一个高度上限。

    和原来的 `width` 一起用 `keepaspectratio`，等价于"宽高都不超过各自的限"，
    不会把图拉变形。讲义是一题一页，图一高就整张飞到下一页，
    那页只剩一张图——实测踩过。
    """
    def sub(m):
        opts = m.group(1) or ""
        if "height" in opts:
            return m.group(0)
        merged = (opts.strip("[]") + ", height=" + cap + ", keepaspectratio").lstrip(", ")
        return "\\includegraphics[" + merged + "]{" + m.group(2) + "}"
    return re.sub(r"\\includegraphics\s*(\[[^\]]*\])?\s*\{([^}]*)\}", sub, tex)


# 模拟题出处名的**脏数据过滤器**。
#
# 老数据的 `meta.source_label` 常是卷头/页码被误当卷名（实测：
# 「满分：150 分，考试时间：120 分钟」「004」），直接拿来当标签很荒唐。
# 命中这些词就当成"没有详细信息"→ 用兜底标签。
_LABEL_JUNK = re.compile(
    r"满分|考试时间|共\s*\d+\s*页|第\s*\d+\s*页|答题卡|评分标准|参考答案|须知|"
    r"^\s*\d+\s*$")

# 老 `meta.source_label` 里常把原卷题号粘在卷名后面（611 道，如
# 「浙江七彩阳光联盟返校考第 6 题」）。出卷子**不印原卷题号**，
# 所以清洗出处名时把尾巴上的「第 N 题」剪掉。
_SOURCE_NO_TAIL = re.compile(r"\s*第\s*[0-9一二三四五六七八九十百]+\s*题\s*$")


def _clean_head(s) -> str:
    r"""把出处名洗干净：去扩展名、去 `_images` 这种录入后缀、去首尾符号。"""
    s = re.sub(r"\.(pdf|docx?)$", "", str(s or "").strip(), flags=re.I)
    s = _SOURCE_NO_TAIL.sub("", s.replace("_images", ""))
    return s.strip(" _-—·、")


def _sim_head(q) -> str:
    r"""模拟题的出处名。**取不到详细信息就用「精选模拟题」。**

    三个来源，按可靠程度排：
      1. `模拟题/<卷名>#N` 的 key 段——**key 是题库唯一真相**（3699 道走这条）；
      2. `meta.source_label`——但老数据常是脏的（「满分：150 分…」「004」），要过滤；
      3. key 的第一段（书册类，`2027千题册经典重点册（上）_images/085#12`）
         → 洗成「2027千题册经典重点册（上）」。
    都没有 → 「精选模拟题」（用户定的兜底话术）。
    """
    key = str(getattr(q, "key", "") or "")
    if key.startswith("模拟题/") and "#" in key:
        head = _clean_head(key.split("/", 1)[1].rsplit("#", 1)[0])
        if head and not _LABEL_JUNK.search(head):
            return head
    meta = getattr(q, "meta", None) or {}
    head = _clean_head(meta.get("source_label"))
    if head and not _LABEL_JUNK.search(head) and len(head) <= 40:
        return head
    head = _clean_head(key.split("/", 1)[0] if "/" in key else "")
    if (head and not _LABEL_JUNK.search(head) and 4 <= len(head) <= 40
            and re.search(r"[\u4e00-\u9fff]", head)):
        return head
    return "精选模拟题"


def source_label(q) -> str:
    r"""出处标签，如「2024新高考I卷」「武汉市2027届高中毕业生九月调研考试」。

    * **高考题**：`meta.year` + `meta.region`（老数据从 key 兜底）。
    * **模拟题**：卷名（卷名怎么取见 `_sim_head`）；取不到就写
      「精选模拟题」——用户的要求：**模拟题也要带标签**，没有详细信息
      就用这句兜底。
    * 其它 kind（目前没有）：不给标签。

    ⚠️ **不印原卷题号**（「第 2 题」）。用户 2026-11-05 明确要求：
    「比如这个第几题，完全没必要」。原卷题号对做题的人没用，反而像
    从别处剪贴来的；要看出处，年份/卷别就够了。题目在**本卷**里的题号
    由 LaTeX 环境自己排，和这里无关。

    标签在卷面上**并进题干同一行**（`（标签）题干…`），方便学生回查原卷。
    这套取值规则在 `_stem_with_source` 里只此一份。
    """
    kind = getattr(q, "kind", "")
    key = str(getattr(q, "key", "") or "")
    if kind == "高考":
        meta = getattr(q, "meta", None) or {}
        year = str(meta.get("year") or "").strip()
        region = str(meta.get("region") or "").strip()
        # 卷别兜底：老数据可能没有 region，从 key 里取（高考真题汇编/2024/新高考I卷#1）
        if not region and "/" in key:
            parts = key.split("/")
            if len(parts) >= 3:
                region = parts[-1].split("#")[0].strip()
        return _SOURCE_NO_TAIL.sub("", f"{year}{region}")
    if kind == "模拟":
        return _sim_head(q)
    return ""


def _stem_with_source(tex: str, q: Question) -> str:
    r"""把出处并进题干**第一行**：`（2023新高考II卷）题干……`

    为什么插在第一个换行之后：`question_to_tex` 的第一行是
    `\begin{question}` / `\begin{problem}[points = 12]`，插在它前面会被
    exam-zh 当成环境自己的参数吃掉。题干与出处**同一行**是用户的要求
    （跟讲义一致）——出处是这道题的定语，另起一行容易被当成题面的一部分。

    出处实现**只有一份**：`source_label()`——高考题「年份 + 卷别」，
    模拟题「卷名」，信息不全兜底「精选模拟题」；**不印原卷题号**。这里再抄
    一份的话，卷面和讲义早晚会印出两个不同的出处（本项目最忌讳的
    "预览与导出不一致"）。

    卷名是**纯文本**，走 `_esc_text` 转义——库里真有卷名带 `_`、`#` 的题，
    不转义会被 TeX 当数学下标/宏参数，整份卷子编译不过。
    """
    lab = source_label(q)
    if not lab:
        return tex
    head, sep, rest = tex.partition("\n")
    if not sep:
        return tex
    return head + sep + "（" + _esc_text(lab) + "）" + rest.lstrip("\n")


def _texpath(p: str) -> str:
    r"""把路径转成 LaTeX 能吃的写法。

    Windows 上 `Path.resolve()` 给的是 `D:\a\AmTiKu\...`——**反斜杠在 TeX 里是命令前缀**，
    直接塞进 `\graphicspath{{...}}` 会报 "Undefined control sequence"（Windows 上一导出
    带图的卷子就必然失败，macOS 因为路径本来就是 / 所以一直没暴露）。统一成正斜杠。
    """
    return str(p).replace("\\", "/")


# 标题是**用户输入的纯文本**（"高三_第一次月考"、"100%模拟"），直接塞进
# `\title{}` 里，`_` `%` `&` 这些字符会让编译停在 "! Missing $ inserted."——
# 用户看到的就是"导出失败"+一段看不懂的日志，实际只是标题里有个下划线。
_TEX_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
                "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
                "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _esc_text(s: str) -> str:
    r"""转义标题里的 LaTeX 特殊字符（一次扫一遍，避免 `\` 被二次转义）。"""
    return "".join(_TEX_SPECIAL.get(ch, ch) for ch in s)


def _cjk_fontset_opt(comma: bool = False) -> str:
    r"""中文字体集选项。默认 `fontset=fandol`（TeX 自带、跨平台），
    `AMTIKU_CJK_FONTSET=system` 时返回空串（交给 ctex 按平台自动挑）。

    为什么默认 Fandol：ctex 在 Windows 上默认要 SimSun/SimHei，
    而英文版 Windows / 精简系统 / Windows Server 没有这些字体，
    导出会以 "The font SimHei cannot be found" 失败（CI 上就是这么挂的）。
    """
    import os
    if os.environ.get("AMTIKU_CJK_FONTSET", "").lower() == "system":
        return ""
    return (", fontset=fandol" if comma else "[fontset=fandol]")


def _brand_page_style(label: str = BRAND_LABEL) -> list[str]:
    r"""AmTiKu 的**页眉页脚版式**（不是水印）。

    为什么在 `\AtBeginDocument` 里重定义 `plain`，而不是在导言区直接
    `\fancypagestyle{plain}`：

    * `exam-zh` 自己在 `\AtEndPreamble` 里重定义 `plain`，并在
      `\AtBeginDocument` 里 `\pagestyle{plain}`；直接写会被它盖掉。
    * `elegantnote`（讲义）在类加载时就定义了 `fancy-note` / `plain`。
    * 两个文档类的 hook 顺序不同，统一在**正文开始那一刻**接管 `plain`，
      两种文档都吃同一份版式；调用方在正文里再 `\pagestyle{fancy}`
      （如全库审阅脚本）仍然能覆盖它，不会被这里锁死。

    版式本身只占页眉/页脚，不碰版心：

        ┌────────────────────────────────────┐
        │ AmTiKu                    高中数学题库 │  ← 页眉（品牌色 + 灰标签）
        │ ────────────────────────────────── │  ← 0.4pt 细线
        │                                    │
        │              正文                   │
        │                                    │
        │        AmTiKu · 第 1 页 / 共 17 页    │  ← 页脚（居中、灰色小字）
        └────────────────────────────────────┘

    页脚保留原来的页码功能，只是前面带上品牌名；不印网址、不印二维码，
    也不用半透明大字——那些才是水印。
    """
    return [
        r"\definecolor{amtibrand}{HTML}{" + BRAND_HEX + r"}",
        r"\usepackage{xcolor}",
        r"\usepackage{fancyhdr}",
        r"\usepackage{lastpage}",
        r"\newcommand{\amtipagestyle}{%",
        r"  \fancyhf{}%",
        # 抬高 1.5pt：不然 0.4pt 的细线会贴着字底，看着像给字号加了下划线
        r"  \fancyhead[L]{\raisebox{1.5pt}{\small\color{amtibrand}\bfseries "
        + BRAND_NAME + r"}}%",
        r"  \fancyhead[R]{\raisebox{1.5pt}{\small\color{gray}"
        + _esc_text(label) + r"}}%",
        r"  \fancyfoot[C]{\footnotesize\color{gray}" + BRAND_NAME
        + r" · 第 \thepage 页 / 共 \pageref{LastPage} 页}%",
        r"  \renewcommand{\headrulewidth}{0.4pt}%",
        # 细线用浅灰，不抢字；品牌色只留给 AmTiKu 这个字标
        r"  \renewcommand{\headrule}{{\color{gray!45}\hrule height 0.4pt "
        r"width \headwidth}}%",
        r"  \renewcommand{\footrulewidth}{0pt}%",
        r"}",
        r"\AtBeginDocument{%",
        r"  \fancypagestyle{plain}{\amtipagestyle}%",
        r"  \pagestyle{plain}%",
        r"  \thispagestyle{plain}%",
        r"}",
    ]


# 讲义可选的几种字号（ctex 的 `\zihao` 编号 → 实际磅值）。
#
#   `-4` 小四 12pt    `4` 四号 14pt    `3` 三号 16pt    `2` 二号 22pt
#
# exam-zh 题干默认是**五号 10.5pt**，在 iPad 上偏小；**默认给小四 12pt**。
HANDOUT_SIZES: dict[str, str] = {
    "-4": "小四 12pt",
    "4": "四号 14pt",
    "3": "三号 16pt",
    "2": "二号 22pt",
}
HANDOUT_FONT_DEFAULT = "-4"


# **解答题留白按难度给。**
#
# 一律 4cm 的问题：简单题（三角函数、数列）写三五行就完了，4cm 空着浪费纸；
# 压轴题（导数、解析几何）要写半页，4cm 根本不够写。真卷子的留白也是
# 跟着题目难度走的。
#
# 单位 cm。要"一律多少"就给 `problem_blank_cm` 传正数，那张表就不生效。
BLANK_BY_DIFFICULTY: dict[str, float] = {
    "简单题": 3.0,
    "中档题": 5.0,
    "难题": 8.0,
}


def blank_for(diff: str, uniform: float = 0.0) -> float:
    r"""这道解答题后面留多少。

    `uniform > 0` 一律用它；`uniform < 0` 表示**不留白**（紧凑版）；
    `uniform == 0`（默认）按难度 3/5/8cm。
    """
    if uniform < 0:
        return 0.0
    if uniform > 0:
        return uniform
    return BLANK_BY_DIFFICULTY.get(diff, 5.0)


# ⚠️ **选项列数不许在 Python 里估算**——这里原先有一个 `choices_columns()`，
# 按源码长度猜宽度（每个 `$…$` 一律折 5 个半角宽），对数学公式完全失准：
# `$\{x\mid x<-1\}\cup\{x\mid x>2\}$` 排出来近 5cm，源码里却只是个 `$…$`，
# 于是被判成「短选项」→ 4 列 → C/D 在自己的格子里折行，卷面上就是
# 「A B C D 挤一行，尾巴掉到下一行」（用户报的 2018 全国 I 卷（理）第 2 题）。
#
# 真实宽度**只有 TeX 自己量得准**，而 exam-zh 的 `choices` 本来就量：
# 不给 `columns` 时它把每个选项排成 hbox 取自然宽度，再算一行摆几列
# （`columns = 0` = 自动，见 `exam-zh-choices.sty` 的
# `\__examzh_choices_calc_columns:`，最大列数 `max-columns` 默认 4，
# 算出来比 4 小就 4→2→1 折半）。所以这里**只传 0**，让模板去量。
#
# `default_columns > 0` 才是"整份文档钉死列数"（调用方明确要求时才这么用）。


_BLANK_ARG = re.compile(r"\\(?:fillin|paren)\s*\[")


def _escaped_at(s: str, i: int) -> bool:
    r"""`s[i]` 是否被反斜杠转义：看前面连续反斜杠的奇偶。

    `\\$` 是换行命令 `\\` 后接数学定界符，不是 `\$`；只看紧邻一个字符
    会把表格里的 `\\$(i)$` 判成转义美元符，进而把数学模式判反。
    """
    bs = 0
    j = i - 1
    while j >= 0 and s[j] == "\\":
        bs += 1
        j -= 1
    return bs % 2 == 1


def _dollars_odd(s: str) -> bool:
    """串里未转义的 `$` 是奇数个 ⇒ 这一段停在数学模式中间。"""
    return sum(1 for i, c in enumerate(s) if c == "$" and not _escaped_at(s, i)) % 2 == 1


def _blank_arg_end(s: str, lb: int) -> int:
    r"""`s[lb]` 是 `\fillin[` 的 `[`，返回**本该收尾**的那个 `]` 的下标（找不到 -1）。

    TeX 的可选参数扫描器**只数花括号、不数 `$`**，所以 `\fillin[$A=[4,5]$]`
    会在 `[4,5]` 那个 `]` 上就断掉，剩下 `5]$]` 漏进正文——编译停在
    «Argument of \fillin has an extra }»。判据：花括号平衡**且** `$` 成双的
    那个 `]` 才是真收尾。
    """
    depth, j = 0, lb
    # 只在 400 字符里找收尾：找不到就说明这题的 `]` 根本不是这个套路，
    # 宁可原样放过去（顶多这一题排错），也不能一路吃到**下一道题**的 `]`——
    # 那会把中间整段吞进作答位里，坏得静悄悄。
    stop = min(len(s), lb + 400)
    while j < stop:
        c = s[j]
        # 越过空段或环境边界就说明这个 `[` 压根没配对的 `]`（实测
        # «Paragraph ended before \fillin was complete» 就是这么来的）。
        if s.startswith("\n\n", j) or s.startswith("\\end{", j) \
                or s.startswith("\\begin{", j):
            return -1
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "]" and depth <= 0 and not _dollars_odd(s[lb + 1:j]):
            return j
        j += 1
    return -1


def fix_blank_brackets(tex: str) -> str:
    r"""作答位 `\fillin[…]` / `\paren[…]` 的两道渲染期保险（不动数据）。

    **① 答案里带 `]`**（右闭区间、`\left(…\right]`）：TeX 扫可选参数**只认第一个
    `]`**，于是 `\fillin[$\left(e,\frac{e^2}{2}\right]$]` 在 `\right]` 那儿就断了，
    剩下的 `$]` 漏进正文 → «Missing $ inserted» 整份讲义断在半路。
    解法：把整个参数包进 `{…}` —— 花括号里的 `]` 处在 1 层括号内，不再是终止符。
    （早先改成 `\rbrack` 是错的：`\right\rbrack` 里 `\right` 后面必须跟定界符，
    实测 «Extra }, or forgotten $»。）

    **② 作答位落在数学式里**：exam-zh 把可选参数按**正文**排，所以
    `$\left(\fillin[\frac{1}{c}-\frac{1}{b}]\right)$` 这种（答案没带 `$`）
    会 «Missing $ inserted»。判据：这个 `\fillin` 前面未转义的 `$` 是奇数个
    （＝在数学式里）而参数里一个 `$` 都没有 → 给参数补上 `$…$`。
    """
    out: list[str] = []
    i = 0
    while True:
        m = _BLANK_ARG.search(tex, i)
        if not m:
            out.append(tex[i:])
            break
        lb = m.end() - 1
        end = _blank_arg_end(tex, lb)
        if end < 0:
            out.append(tex[i:])
            break
        body = tex[lb + 1:end]
        wrapped = body
        if _dollars_odd(tex[:lb]) and "$" not in body and "\\" in body:
            wrapped = "$" + body + "$"                   # 规则 ②
        if _blank_needs_wrap(wrapped):
            wrapped = "{" + wrapped + "}"                # 规则 ①
        out.append(tex[i:lb + 1] + wrapped + "]")
        i = end + 1
    return "".join(out)


def _blank_needs_wrap(body: str) -> bool:
    r"""参数里存在**花括号第 0 层**的 `]` ⇒ TeX 就在那儿收尾，必须包一层 `{…}`。

    注意判据是「有没有」而不是「平衡的是哪个」：TeX 扫可选参数时，花括号能保护
    `]`，但 `$…$` 不能——所以 `$\left(e,\frac{e^2}{2}\right]$` 里那个 `\right]`
    必须包起来。（`\{` `\}` 是转义字符，不算开合括号，跳过。）
    """
    depth, i = 0, 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c == "]" and depth == 0:
            return True
        i += 1
    return False


_BLANK_RUN = re.compile(r"_{2,}")
# 「别当正文处理」的环境：公式环境 + 图环境。图里那些 `\addplot`、坐标里的逗号
# 既不是正文也不该被转义，判成数学模式一并跳过最省事。
_OPAQUE_ENVS = lb.DISPLAY_MATH_ENVS | lb.MATH_ONLY_ENVS | lb.RAW_ENVS
_ENV_TOGGLE = re.compile(r"\\(begin|end)\{([^{}]*)\}")


def map_text_mode(tex: str, fn) -> str:
    r"""只对**数学模式之外**的片段套用 `fn`，数学式一个字不动。

    数学模式认四种写法：`$…$`、`\[…\]`、`\(…\)`、公式环境。环境名直接取
    `latex_blocks` 的 `DISPLAY_MATH_ENVS | MATH_ONLY_ENVS`——「哪些环境是数学」
    这件事全项目只许有一份答案，另抄一份就会两边判得不一样。

    出题时凡是要动正文（转义裸 `_`、包 unicode 符号），**必须**走这里：
    不判数学模式就动手，会把 `$x_i$` 改成 `$x\_i$`，公式当场塌成下划线。
    """
    out: list[str] = []
    buf = ""
    dollar = False
    depth = 0
    i, n = 0, len(tex)

    def in_math() -> bool:
        return dollar or depth > 0

    def flush():
        nonlocal buf
        if buf:
            out.append(buf if in_math() else fn(buf))
            buf = ""

    while i < n:
        c = tex[i]
        if c == "$" and not _escaped_at(tex, i):
            flush()
            dollar = not dollar
            out.append(c)
            i += 1
            continue
        if tex.startswith(("\\[", "\\("), i):
            flush()
            depth += 1
            out.append(tex[i:i + 2])
            i += 2
            continue
        if tex.startswith(("\\]", "\\)"), i):
            flush()
            depth = max(0, depth - 1)
            out.append(tex[i:i + 2])
            i += 2
            continue
        m = _ENV_TOGGLE.match(tex, i)
        if m:
            flush()
            if m.group(2) in _OPAQUE_ENVS:
                depth += 1 if m.group(1) == "begin" else -1
                depth = max(0, depth)
            out.append(m.group(0))
            i = m.end()
            continue
        buf += c
        i += 1
    flush()
    return "".join(out)


def fix_text_specials(tex: str) -> str:
    r"""正文（数学模式之外）里四类「LaTeX 吃了就停编译」的写法（渲染期改动，不动数据）。

    1. **裸横线 `_____`**：一批解析把原卷的作答位一起抄进来了（`概率为_____。`）。
       连续两个以上换成 `\underline{\hspace{…}}`。
    2. **单个 `_` / `^`**：如 `C_RN`（补集没包 `$`）。正文模式里 `_` 直接
       «Missing $ inserted»，整段解析掉进数学模式——后面每个汉字都报
       «no 所 (U+6240) in font NewCMMath»，一份讲义断在半路。
    3. **裸 `#`**：录题时留在解析里的元话（`（原册第 1 页里 #10 只印了答案…）`），
       全文 27 处；`#` 是宏参数占位符，两种模式里都炸。
    4. **裸 `%`**：吃掉行尾剩下的文字（历史上丢过 246 个汉字）。

    ⚠️ 这些是**数据缺陷**，正解是 `fixups.py` 逐题清；这里只是别让出卷/出讲义
    为它们整个失败。`&` **不动**——表格里它是列分隔符。
    """
    def one(chunk: str) -> str:
        chunk = _BLANK_RUN.sub(
            lambda m: r"\underline{\hspace{%dem}}" % min(12, len(m.group(0))), chunk)
        chunk = re.sub(r"(?<!\\)_", r"\_", chunk)
        chunk = re.sub(r"(?<!\\)\^", r"\textasciicircum{}", chunk)
        chunk = re.sub(r"(?<!\\)#", r"\#", chunk)
        chunk = re.sub(r"(?<!\\)%", r"\%", chunk)
        return chunk

    return map_text_mode(tex, one)


_BEGIN_BARE = re.compile(r"(\\begin\{(?:question|problem|solution)\})(\n)(\[)")


def guard_leading_bracket(tex: str) -> str:
    r"""环境第一行就以 `[` 开头时，给环境补一个空的 `{}`。

    库里有一批多问题干写作「[甲] …」「[乙] …」。`\begin{problem}` 后面紧跟
    `[...]` 会被 exam-zh 当成**自己的**可选参数吃掉，报
    «The key 'exam-zh/problem/甲' is unknown»，那一题的排版整个乱掉。
    补一个空组 `{}` 就把可选参数的扫描堵住了，卷面一个字不变。

    ⚠️ **`solution` 也必须算进来**（2026-10-01 补）。原来只护了
    `question`/`problem`，于是**解析以 `[解]` 开头**的题一编就炸：
    `\begin{solution}` 后面的 `[解]` 被当成可选参数，报
    «The key 'exam-zh/solution/解' is unknown»，**整份卷子出不来**。
    实测全库 3 道（四川绵阳南山中学 2026 届高三第五次教学质检 #7/#8/#14）——
    都是"解析栏一个字都不显示"的坏法，只有跑 xelatex 才查得出来。
    """
    # **不设 count**：题干和解析可能各自都以 `[` 开头，只补第一处会漏掉另一处
    # （原来写的是 `count=1`，那时只认 `question`/`problem`，所以没露出来）。
    return _BEGIN_BARE.sub(lambda m: m.group(1) + "{}" + m.group(2) + m.group(3),
                           tex)


_PAPER_NOISE = re.compile(r"解答题|选择题|填空题|第\s*\d+\s*页|共\s*\d+\s*页|参考答案")


def blank_args_ok(tex: str) -> bool:
    r"""题干里的 `\fillin[` / `\paren[` 是不是**每一个**都能正常收尾。

    收尾都找不到（越过空段/环境边界）就是数据缺陷：TeX 会一路吃到下一段，
    报 «Paragraph ended before \fillin was complete»，整份产物断在这儿。
    全库实测 26 道这样（题干里 `\fillin[$\sqrt{34}$。` 后面没有 `]`），
    另有 11 道答案位把「四、解答题：…」「第 3 页（共 7 页）」这类卷尾噪声吞了进去
    ——编译得过，但印出来是垃圾。两种都判不合格，交给选题/组卷自己避开。
    """
    for m in _BLANK_ARG.finditer(tex or ""):
        lb = m.end() - 1
        end = _blank_arg_end(tex, lb)
        if end < 0:
            return False
        if _PAPER_NOISE.search(tex[lb + 1:end]):
            return False
    return True


_AMP_RAW = re.compile(r"(?<!\\)&")
_TAB_BEGIN = re.compile(r"\\begin\{tabular\*?\}")
_TAB_END = re.compile(r"\\end\{tabular\*?\}")


def guard_sheet_slots(tex: str) -> str:
    r"""**表格行里**第二个及以后的作答位，各包一层 `{}`。

    为什么：exam-zh 在**学生版**（`fillin/show-answer=false` +
    `fillin/no-answer-type=none`）下，`\fillin` 展开成的那串东西
    **在同一表格行的第二个及以后**会收不了组，xelatex 报
    «Missing \endgroup inserted»、**整份卷子出不来**。

    实测最小复现（讲义版 `show-answer=true` 反而正常，所以肉眼看不出来）：

        \begin{tabular}{|c|c|c|}
        \hline $P$ & \fillin[$0.1$] & \fillin[$0.6$] \\ \hline
        \end{tabular}                 → Missing \endgroup inserted

        … & {\fillin[$0.1$]} & {\fillin[$0.6$]} …   → 通过

    全库实测 4 道（都在 `高考真题汇编/2000~2004/全国卷` 的概率分布表里）。

    ⚠️ **两条护栏，都是踩过才知道要加的**（第一版没有，把别的题改坏了）：

    1. **只在 `tabular` 里动手**。第一版按"这一行有 `&`"判断，结果
       `\begin{cases} … & … \end{cases}` 里的 `&` 也被当成表格分隔符——
       实测把「湘豫名校联考#13」（题干里有 `cases`）改成了
       `{\fillin[}$\begin{cases}…`，报 «Argument of \fillin has an extra }»。
       这是条**新造出来的坏**，编译体检里 27 道变成了 1 道新的。
    2. **收尾 `]` 定位不到就一个字都不动**。`_blank_arg_end` 是"花括号平衡
       且 `$` 成双"的严格判据，比 TeX 的可选参数扫描器**更严**，会返回 -1。
       第一版在 -1 时只把 `\fillin[` 包进组，等于把参数从中间砍断。
    """
    lines = tex.split("\n")
    in_tab = 0
    for k, line in enumerate(lines):
        if _TAB_BEGIN.search(line):
            in_tab += 1
        elif _TAB_END.search(line):
            in_tab = max(0, in_tab - 1)
            continue
        if not in_tab or "&" not in line:
            continue
        pos, out, hit = 0, [], False
        for m in _BLANK_ARG.finditer(line):
            if m.start() < pos:
                continue
            end = _blank_arg_end(line, m.end() - 1)
            if end < 0:                      # 定位不到收尾 → 不动它
                pos = m.end()
                continue
            out.append(line[pos:m.start()])
            seg = line[m.start():end + 1]
            has_amp = bool(_AMP_RAW.search(line[:m.start()]))
            out.append("{%s}" % seg if has_amp else seg)
            pos, hit = end + 1, True
        if hit:
            out.append(line[pos:])
            lines[k] = "".join(out)
    return "\n".join(lines)


def _q_tex(q: Question, show_answers: bool, *, default_columns: int = 0,
           show_source: bool = True, with_solution: bool = True) -> str:
    r"""一道题的 LaTeX（三种卷型共用）。

    · **解析常驻源文件**，显不显示交给 `\examsetup{solution/show-solution}`——
      这是高考模板的做法：不用为了出学生版重写一遍源文件；
    · `show_source=True`（默认）时在题干**同一行**前面并上出处
      `（2023新高考II卷）`，见 `_stem_with_source`；
    · 卷面上**不印难度**（用户要求）——难度只影响解答题留白。

    `default_columns`：**0（默认）＝每题让 exam-zh 按实测宽度自动挑列数**；
    给正数＝整份文档钉死这么多列。为什么不在 Python 里估算见上面那段长注释。
    """
    cols = default_columns if default_columns > 0 else 0
    # 行内 `（1）`/`(i)` 小问前补空行（排版用，数据不动）。
    # 只改**题干**：答案/解析/选项里的 `(1)` 多是引用，补空行会把排版弄碎。
    _qq = _copy.copy(q)
    _qq.stem = lb.break_inline_parts(q.stem)
    tex = question_to_tex(_qq, with_solution=with_solution, with_source=False,
                          choices_columns=cols, skip_no_solution=True,
                          skip_empty_choices=True)
    # 作答位里的多余 `]` 会把可选参数提前收尾（«extra }» 停编译）——出题时修，
    # 数据一个字不动。见 `fix_blank_brackets`。
    tex = fix_blank_brackets(tex)
    tex = guard_sheet_slots(tex)            # 表格行里第 2+ 个作答位要包组
    tex = fix_text_specials(tex)            # 解析里抄来的 `_____` 与裸 `#` 同上
    tex = guard_leading_bracket(tex)        # 题干以 `[甲]` 开头时别让环境吞掉
    # **把题干里嵌着的 TikZ 换成预渲染好的矢量图**——只在这一步做。
    #
    # 为什么不在 `render_tex` 里做：那个函数**同时是写库路径**
    # （`store.render_question` 用它序列化），塞在那儿等于每次写库都
    # 偷偷改数据（实测污染 236 道）。这里只影响"出卷子"。
    #
    # 不换的话，卷子就得在导言区备齐所有 TikZ 依赖——库里的图是从各种
    # 真题源码抠出来的，各用各的宏包和自定义样式，**补不完**，
    # 一缺就是"抽到才炸、整份卷子出不来"。
    # `to_image` 只换**渲染过**的；没渲染过的原样走内联 TikZ。
    from . import tikzfig as _tz
    tex, _n = _tz.to_image(tex, q.figures)
    # **答案标红**：只在"卷面上真的显示答案"时才染（学生版不染，见模块顶部说明）。
    if show_answers:
        tex = red_answer_macros(tex)
    # **出处并进题干第一行**——三种卷型一视同仁（见模块开头）。
    # 放在最后：先让上面几道修把题干整好，再往上加字，
    # `guard_leading_bracket` 补的那个 `{}` 也不会被这句顶开。
    if show_source:
        tex = _stem_with_source(tex, q)
    return tex


def _qid_mark(q: Question) -> str:
    r"""每题前面那行「这是哪道题」的注释。

    为什么值得占一行：卷子是程序拼出来的，xelatex 报错只会给一个**行号**
    （`l.4213`），而没人知道 4213 行是哪道题。有了这行注释，
    `amti/texdiag.py` 就能把行号翻成题目 key，用户看到的从
    「第 4213 行 Undefined control sequence」变成
    「`模拟题/…联考#17` 这道题用了个不认识的宏」。

    `%` 是 LaTeX 注释，**不会印到卷面上**，对 PDF 零影响。
    这一招是跟 MathBank 学的（它的 `latex_diagnostics.py:66-73` 从
    `% MathBank-Question-ID:` 一路向上找最近的标记）。

    默认**不开**（`qid_marks=False`）：开了会在导出源码里多出 N 行注释，
    而只有"要编译"的那条路才需要它（见 `amti/export.py`）。
    """
    from .texdiag import QID_PREFIX
    return QID_PREFIX + (q.key or "")


def render_paper(questions: list[Question], *, mode: str = "gaokao",
                 title: str = "", subject: str = "数学", show_answers: bool = False,
                 answers_at_end: bool = False, show_source: bool = True,
                 bottom_sep: str = "0.6em", problem_blank_cm: float = 0.0,
                 columns: int = 0, graphicspath: str = "",
                 handout_font: str = HANDOUT_FONT_DEFAULT,
                 qid_marks: bool = False, answer_sheet: bool = False,
                 detail_one_page: bool = True,
                 score_box: bool = True, seal_line: bool = True) -> str:
    r"""渲染成完整的 exam-zh 文档。`mode` 取 `gaokao` / `test` / `handout`。

    `qid_marks=True` 时在每题前面加一行 `% AMTIKU-Q: <key>` 注释，
    供编译失败时把行号定位回题目（见 `_qid_mark`）。注释不上卷面。

    三种"答案怎么放"：

    | `show_answers` | `answers_at_end` | 效果 |
    |---|---|---|
    | False | — | **学生卷**：作答位置空着，解答题留白，没有答案 |
    | True  | False | **讲义卷**：答案就在括号里、解析紧跟题目 |
    | False | True  | **真题卷**：卷面上干干净净，**答案与解析统一放在卷末** |

    第三种才是真实高考卷的做法——卷子上只有题目，答案另附。
    `problem_blank_cm`：解答题留白。**留空（0）＝按难度自动**（3/5/8cm），
    给正数则一律用它；**给负数 = 不留白**（界面的「紧凑版」）。

    `answers_at_end` 会把 `show_answers` 的效果**收起来**：
    括号不显示答案，题目后面不带 `solution` 环境，改成卷末一节。

    `show_source`（**默认开**）：每题题干前并上出处
    `（2023新高考II卷）`，**不带原卷题号**，跟讲义一致；界面上的「印出处」
    开关可以整套关掉（有的卷子不需要出处）。
    """
    if mode == "handout":
        return _render_handout(questions, title=title, columns=columns,
                               qid_marks=qid_marks, show_source=show_source,
                               graphicspath=_texpath(graphicspath), font=handout_font)
    if mode not in ("gaokao", "test"):
        raise ValueError(f"未知卷型 {mode!r}")

    total_score = _total(questions)
    # 答案放卷末时，卷面上的括号和解析都要收起来——不然答案会印两遍
    if answers_at_end:
        show_answers = False

    # 导言区走**共用的一份**（`_preamble`）——讲义模式当初另抄一份，
    # 漏了自定义 pgfplots 样式，一编译就死。两份导言就是两份真相。
    doc: list[str] = _preamble(title=title, graphicspath=_texpath(graphicspath),
                               show_answers=show_answers, bottom_sep=bottom_sep,
                               columns=columns)
    doc.append(r"\begin{document}")
    return _paper_body(doc, questions, mode=mode, subject=subject,
                       show_answers=show_answers, answers_at_end=answers_at_end,
                       columns=columns, graphicspath=_texpath(graphicspath),
                       bottom_sep=bottom_sep, problem_blank_cm=problem_blank_cm,
                       total_score=total_score, show_source=show_source,
                       qid_marks=qid_marks, answer_sheet=answer_sheet,
                       detail_one_page=detail_one_page,
                       score_box=score_box, seal_line=seal_line)


def _preamble(*, title: str = "", graphicspath: str = "",
              show_answers: bool = False, answers_at_end: bool = False,
              bottom_sep: str = "0.6em", columns: int = 0,
              landscape: bool = False, big_font: bool = False,
              first_line: str = "", extra: list[str] | None = None) -> list[str]:
    r"""**全项目唯一产出导言区的地方。**

    ⚠️ 讲义模式刚加时我另抄了一份导言，漏掉了 `exam statistical histogram`
    这个自定义 pgfplots 样式——结果讲义一编译就死
    （`I do not know the key '/tikz/exam statistical histogram'`），
    界面上只剩残留的旧预览，看着像"题目不显示"。
    **两份导言就是两份真相**，改了这份忘了那份，早晚出事。所以合成一份。
    """
    out = [
        first_line or "% 由 AmTiKu 生成，请勿手改；改题目请改 题目/*.tex 后重新导出。",
        # 中文字体：**默认用 TeX 自带的 Fandol**，不依赖系统字体。
        # 坑（CI 上暴露的）：ctex 在 Windows 上会自动挑 SimSun/SimHei，英文版 Windows、
        # 精简系统、Windows Server 上根本没这些字体 → 导出直接报
        # "The font SimHei cannot be found" 而失败。Fandol 随 TeX 分发、跨平台一致，
        # 这样**同一份 .tex 在任何机器上编出来的 PDF 都一样**。
        # 想让本机系统字体生效（好看些但不保证别处能编）：设 AMTIKU_CJK_FONTSET=system
        r"\documentclass%s{exam-zh}" % _cjk_fontset_opt(),
        # 题库里有用 \diaghead（斜线分栏表头）的题，它是 makecell 提供的宏。
        # 只装包不 \usepackage 依然报 Undefined control sequence（全库体检抓到过一道）。
        r"\usepackage{makecell}",
        r"\usepackage{siunitx}",
        r"\usepackage{multicol}",
        # 答案标红要用 `\color`（exam-zh 自己多半也装过 xcolor，
        # 这里显式装一次，免得换模板时突然没有颜色宏）。
        r"\usepackage{xcolor}",
        _ANS_DEFINE,
        # 有些题的配图是 pgfplots 画的（`\begin{axis}`），没有这个包编译不了。
        # `compat` 是 pgfplots 自己要求的版本声明，不写会警告。
        r"\usepackage{pgfplots}",
        # **把库里 TikZ 图真正用到的库一次性装上。**
        #
        # 这些图是从各种真题源码里抠出来的，各用各的库。少装一个，编译就报
        # `Unknown arrow tip kind Stealth` 这种错，**整份卷子出不来**——
        # 而且是抽到那道题才炸，很难提前发现。
        #
        # 下面这几个是按全库 TikZ 代码**反推**出来的（扫出多少处写在后面）：
        #   shapes.geometric x91   angles x90   arrows.meta x11
        #   calc x8                positioning x3
        # 多装几个库几乎不花时间，比"抽到才炸"划算得多。
        r"\usetikzlibrary{arrows.meta, calc, angles, quotes, positioning, shapes.geometric}",
        # ⚠️ **补上库里用到的自定义 pgfplots 样式。**
        #
        # 有一批题的 TikZ 图是从原卷源码里抠出来的，里面用了原卷**预导言区**
        # 自定义的轴样式 `exam statistical histogram`（频率分布直方图）。
        # 那个定义只存在于原卷源码里，拷进我们库里就丢了——
        # 结果只要一套卷子抽到这类题，**整份卷子编译不过**：
        #     ! Package pgfkeys Error: I do not know the key
        #       '/tikz/exam statistical histogram'
        # 全库 30 处用到了它，实测踩过。
        #
        # 定义按"这 30 处每一条都显式写了什么"反推：它们全都自己写了
        # width/xmin/xmax/ymin/ymax/axis lines/clip，所以这里只补
        # **共同的绘图类型和轴外观**——`ybar interval` 尤其不能少：
        # 有 4 处 `\addplot` 一个选项都没写，完全靠样式给。
        *PGFPLOTS_STYLES,
        *TIKZ_STYLES,
        freq_label_cmd(),
        r"\usepackage{lastpage}",
        # `\needspace`：题干和选项别被分页拆开
        r"\usepackage{needspace}",
        # **品牌页眉页脚**（版式，不是水印）。放在 `extra` 之前：
        # 调用方若要加自己的 `\AtBeginDocument`，注册得比这里晚，仍然能覆盖。
        *_brand_page_style(BRAND_LABEL),
        # **调用方自带的导言片段**（要补自己的自定义宏时用）。放在宏包之后、
        # 之类的定义，不碰版式开关。默认空，现有导出一个字节都不变。
        *(extra or []),
        (r"\graphicspath{" + "".join("{" + x + "/}" for x in (graphicspath,)) + "}"
         if graphicspath else ""),
        "",
    ]
    if landscape:
        # **横版**。exam-zh 自己只在 a3 分支里设 landscape，a4 得我们自己加。
        out.append(r"\geometry{landscape, margin=1.7cm}")
    out += [
        r"\examsetup{",
        r"  page/size=a4paper,",
        r"  paren/show-paren=true,",
        f"  paren/show-answer={'true' if show_answers else 'false'},",
        f"  fillin/show-answer={'true' if show_answers else 'false'},",
        # 不显示答案时，exam-zh 默认在空位上画个**黑色三角**当标记（模板的
        # `▲`）。看着像个墨点，不如留一条干净的下划线。`none` 就是不画。
        r"  fillin/no-answer-type=none,",
        "  solution/show-solution=" + ("show-stay," if show_answers else "hide,"),
        r"  solution/label-indentation=false,",
        f"  question/bottom-sep = {bottom_sep},",
        f"  problem/bottom-sep = {bottom_sep},",
        # 0 = **自动**：exam-zh 每个 `choices` 环境自己量选项宽度、自己定列数
        # （`\begin{choices}` 会把全局值清成 0 再算，所以真正生效的是每题那份
        # `[columns = N]`，见 `_q_tex`）。这里保持 0，别写成 4。
        f"  choices/columns = {columns},",
        r"}",
        "",
        # `\everymath` 让行内公式也用 displaystyle——高考卷的分数是"大"的
        r"\everymath{\displaystyle}",
        "",
    ]
    if big_font:
        out += [r"\zihao{4}", ""]     # iPad 上看得清
    if title:
        out += [r"\title{" + _esc_text(title) + "}", r"\subject{数学}"]
    return out


def preamble(**kw) -> list[str]:
    r"""`_preamble` 的**公开入口**——外部模块要拼整份文档就从这儿拿导言区。

    存在唯一理由：导言区只许有一份。外部模块自己抄一份，就会重现
    上面那条「漏装 `exam statistical histogram` 一编译就死」的坑。
    """
    return _preamble(**kw)


def question_tex(q, *, show_answers: bool = True, columns: int = 0,
                 show_source: bool = False, with_solution: bool = True) -> str:
    r"""**出题用**的单题 LaTeX（走 `_q_tex`：嵌在题干里的 TikZ 换成预渲染图、
    答案标红、按需并上出处）。

    和 `preamble()` 一个道理：`_q_tex` 里那步「TikZ→图片」是**渲染期**改动，
    只许在出题时做。别处再抄一遍，就会出现「每次写库悄悄改题干」那种事故。

    `show_source` 这里**默认关**（与 `render_paper` 相反）：本函数的调用方是
    脚本里的"分层训练"块，出处由那些文档自己决定要不要；`render_paper` 那条卷子路径一律走默认开的开关。
    """
    return _q_tex(q, show_answers, default_columns=columns,
                  show_source=show_source, with_solution=with_solution)


def texpath(p) -> str:
    """`_texpath` 的公开入口：把路径转成 LaTeX 能吃的写法（反斜杠→正斜杠）。"""
    return _texpath(str(p))


def esc_text(s: str) -> str:
    """`_esc_text` 的公开入口：纯文本进 LaTeX 标题/表格前的特殊字符转义。"""
    return _esc_text(s)


def _paper_body(doc: list[str], questions: list[Question], *,
                mode: str, subject: str, show_answers: bool,
                answers_at_end: bool, columns: int, graphicspath: str,
                bottom_sep: str, problem_blank_cm: float,
                total_score: int, show_source: bool = False,
                qid_marks: bool = False, answer_sheet: bool = False,
                detail_one_page: bool = True,
                score_box: bool = True, seal_line: bool = True) -> str:
    r"""卷子正文（分节、出题、卷末答案册）。导言区由 `_preamble` 出。"""
    numbering: list[tuple[int, Question]] = []      # (卷面题号, 题)
    no = 0
    # `\secret`（绝密★启用前）是**高考卷专属**——测试卷是校内练习，
    # 盖这个戳不合场合。放在 `\maketitle` 之前才生效。
    if mode == "gaokao":
        doc.append(r"\secret")
    doc.append(r"\maketitle")

    if mode == "gaokao":
        doc += _gaokao_head(questions, total_score)
    else:
        doc += _test_head(questions, subject=subject)
    if score_box:
        doc += _score_box()
    if seal_line:
        doc += _seal_line()

    # ── 分节 ──
    by_sec: dict[str, list[Question]] = {}
    for q in questions:
        by_sec.setdefault(q.type, []).append(q)

    for t in ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer"):
        items = by_sec.get(t)
        if not items:
            continue
        # `\section{}` 由 exam-zh 自动编号成「一、选择题：…」并加粗——
        # 早先手写 `\noindent{\bfseries 一、选择题…}`，编号要自己维护
        # 解答题一页一题时，**分节标题也要跟第一题同页**：
        # 先把新页开了，再写标题；否则标题在页底、题目被 `\newpage` 推到下一页，
        # 就出现“二、解答题”孤零零挂在上一页底部（实测踩过）。
        one_page_section = (t == "detailed_answer" and not show_answers
                            and detail_one_page)
        if one_page_section:
            doc.append(r"\newpage")
        # 小节标题不要孤零零掉在页底：下面至少留 12 行（标题 + 首题开头）
        doc.append(r"\needspace{12\baselineskip}")
        if mode == "gaokao":
            doc.append(r"\section{" + _gaokao_section(t, len(items)) + "}")
        else:
            doc.append(r"\section{" + _test_section(t, len(items)) + "}")
            # 测试卷每节题号重新从 1 开始（模板的做法）。
            # ⚠️ 是 **1** 不是 0——写 0 会让这一节从「0.」开始，模板原文是笔误。
            doc.append(r"\examsetup{question/index = 1}")
        doc.append("")
        for i, q in enumerate(items):
            # **记下这道题在卷面上的题号**——卷末的答案册要用。
            # 高考卷连续编号；测试卷每节从 1 重来（`question/index = 1` 那句）。
            no += 1
            if mode != "gaokao" and i == 0:
                no = 1
            numbering.append((no, q))
            idx = len(numbering)
            diff = position_difficulty(t, i, len(items))
            # ⚠️ **`\filbreak`：把「这道题 + 它的留白」绑成一块。**
            #
            # 留白是 `\vspace*` 追加在**题目之后**的。不加 `\filbreak` 时，
            # 如果"题目 + 留白"在当前页放不下，TeX 会把留白**单独甩到下一页顶部**
            # ——于是出现"上一页底部满满当当、下一页顶上空白一大块、题目从中间开始"
            # 这种谁看谁别扭的版面（实测第 3 页顶部就空了两厘米多）。
            #
            # `\filbreak` 是 LaTeX 里"这一块放不下就整块挪走"的老办法：
            # 从它到**下一个 `\filbreak`** 之间的内容视为一块。
            # 上面刚说过留白跟在题目后头，所以这一块正好是"题 + 留白"。
            # 解答题“一页一题”：每道解答题从新页开始，题目后把余下版面填满，
            # 学生直接在题目下面作答。老师版（带解析）不分页，否则解析也会被拆散。
            one_page = (t == "detailed_answer" and not show_answers
                        and detail_one_page)
            if one_page and i:
                doc.append(r"\newpage")
            elif not one_page and i:
                doc.append(r"\filbreak")
            # 起始 label 必须在**分页之后**：解答题第二题起先 `\newpage`，
            # 若 label 写在 newpage 前，会被记在上一页，误报“跨页”。
            if qid_marks:
                doc.append(f"\\label{{amtiq{idx}}}")
                if t == "detailed_answer":
                    doc.append(f"% AMTIKU-DETAIL: {idx}")
            # **题干和它的选项不许被分页拆开。**
            #
            # 不加这句时，一道题可以"题干在这页末尾、选项跑到下页开头"——
            # 学生翻页才能看到选项，很别扭。`\needspace{6\baselineskip}`
            # 的意思是"下面至少还要留得下 6 行，否则现在就把这一页断掉"。
            #
            # 6 行是个折中：够装下"题干 2-3 行 + 选项 2 行"，
            # 又不会因为要求太高而在页底留下大片空白。
            doc.append(r"\needspace{6\baselineskip}")
            if qid_marks:
                doc.append(_qid_mark(q))
            doc.append(_q_tex(q, show_answers and not answers_at_end,
                              default_columns=columns,
                              show_source=show_source))
            # 解答题留白：**必须 `\vspace*`**（带星号）——
            # 不带星号的 `\vspace` 在分页处会被丢弃，题目落在页底时留白凭空消失
            if t == "detailed_answer" and not show_answers:
                if one_page:
                    # 填满本页剩余高度：题短就多留白，题长就自然少留
                    doc.append(r"\vspace*{\fill}")
                else:
                    cm = blank_for(diff, problem_blank_cm)
                    if cm > 0:
                        doc.append(f"\\vspace*{{{cm:.2f}cm}}")
            if qid_marks:
                doc.append(f"\\label{{amtiqend{idx}}}")
            doc.append("")

    if answers_at_end and numbering:
        doc += _answers_section(numbering)
    if answer_sheet:
        doc += _answer_sheet(numbering)

    doc.append(r"\end{document}")
    return "\n".join(doc)


def _score_box() -> list[str]:
    r"""卷头**总分框**：题号 / 一、二、三、四 / 总分，老师批完填分用。"""
    return [
        r"\begin{center}",
        r"\renewcommand{\arraystretch}{1.5}",
        r"\begin{tabular}{|c|c|c|c|c|c|}",
        r"\hline",
        r"题号 & 一 & 二 & 三 & 四 & 总分 \\",
        r"\hline",
        r"得分 & & & & & \\",
        r"\hline",
        r"\end{tabular}",
        r"\end{center}",
        "",
    ]


def _seal_line() -> list[str]:
    r"""第一页左侧**密封线**：竖线 + 旋转文字，装在页边距里，不压正文。"""
    return [
        r"\begin{tikzpicture}[remember picture, overlay]",
        r"\draw[line width=0.4pt] "
        r"([xshift=1.15cm]current page.north west) -- "
        r"([xshift=1.15cm]current page.south west);",
        r"\node[rotate=90, anchor=south, font=\small] at "
        r"([xshift=0.55cm,yshift=3cm]current page.south west) "
        r"{密封线内不要答题};",
        r"\end{tikzpicture}",
        "",
    ]


def _answer_sheet(numbering: list[tuple[int, Question]]) -> list[str]:
    r"""卷末附一页**答题卡**：选择题填涂 + 填空题横线。

    **不含解答题**：解答题已经“一页一题、题目下面填满空白”，
    学生直接在卷面上作答；再给解答题留框纯属重复，还浪费纸。
    """
    if not numbering:
        return []
    out = [r"\newpage", r"\section*{答题卡}", ""]
    out.append(r"\begin{center}")
    out.append(r"姓名：\underline{\hspace{3.6cm}}\quad "
               r"班级：\underline{\hspace{3.2cm}}\quad "
               r"考号：\underline{\hspace{3.6cm}}")
    out.append(r"\end{center}")
    out.append("")

    for title, types in (
        ("一、选择题（在对应选项上打勾或涂黑）", ("single_choice", "multi_choice")),
        ("二、填空题（把答案写在横线上）", ("fill_in_blank",)),
    ):
        items = [(i, q) for i, (_no, q) in enumerate(numbering, start=1)
                 if q.type in types]
        if not items:
            continue
        out.append(r"\noindent{\bfseries " + title + "}")
        out.append("")
        for i, q in items:
            if q.type in ("single_choice", "multi_choice"):
                opts = r"\quad ".join(r"$\square$ " + c for c in "ABCD"[:max(2, len(q.options))])
                out.append(r"\noindent %d.\quad %s" % (i, opts))
            elif q.type == "fill_in_blank":
                out.append(r"\noindent %d.\quad "
                           r"\underline{\hspace{0.82\linewidth}}" % i)
            else:
                continue
            out.append(r"\vspace{0.35em}")
        out.append("")
    return out


def _render_handout(questions: list[Question], *, title: str = "",
                    columns: int = 0, graphicspath: str = "",
                    font: str = HANDOUT_FONT_DEFAULT,
                    qid_marks: bool = False, show_source: bool = True) -> str:
    r"""**讲义模式：一题一页，A4 横版，无答案。**

    用途是**在 iPad 上用笔讲课**：一道题一屏，讲完翻下一页就是下一题。

    ## 为什么换成了 elegantnote

    原来用 exam-zh 出讲义，观感差：题干和选项挤在一起、行距紧、
    没有层次。`elegantnote` 是专为**电子阅读**设计的文档类
    （默认就是给 pad/kindle 用的），行距、留白、标题层次都更舒服。

    ## 两个文档类怎么融合

    `exam-zh` 和 `elegantnote` **都是文档类**（各自 `\LoadClass` 了别的类），
    LaTeX 里没法嵌套。所以走"**宿主 + 兼容层**"：

    | | 谁负责 |
    |---|---|
    | 版心、字体、颜色、标题层次、页脚 | **elegantnote**（当 `\documentclass`） |
    | `question` / `choices` / `\paren` / `\fillin` | **我们自己定义**（兼容层） |

    兼容层要跟 exam-zh 的写法对齐，因为题库里的题干就是那么写的。
    三处都是**没有答案的形态**——讲义本来就不印答案：

      `\paren[…]`  → `（　　）`     右对齐的空括号
      `\fillin[…]`  → 下划线横线    括号/花括号/光杆三种写法都吃
      `choices`     → A. B. C. D.   一行一个

    ## 主色

    用 AmTiKu 的品牌色 `RGB(206,51,138)` 覆盖掉 elegantnote 的默认蓝，
    这样讲义和 App 是一套配色。
    """
    # 字号：elegantnote 的 `fontsize` 只认 10/11/12pt，换算成 pt 传进去
    pt = {"-4": "12pt", "4": "14pt", "3": "16pt", "2": "22pt"}.get(font, "12pt")
    doc: list[str] = [
        "% 由 AmTiKu 生成（讲义模式：一题一页 · A4 横版 · 无答案）",
        r"\documentclass[cn, device=normal, 11pt%s]{elegantnote}" % _cjk_fontset_opt(True),
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{enumitem}",
        r"\usepackage{graphicx}",
        r"\usepackage{tikz}",
        r"\usepackage{pgfplots}",
        r"\pgfplotsset{compat=1.18}",
        r"\usetikzlibrary{arrows.meta, calc, angles, quotes, positioning, shapes.geometric}",
        # 自定义 pgfplots 样式：**和普通卷型共用同一份常量**，别再抄一遍
        *PGFPLOTS_STYLES,
        *TIKZ_STYLES,
        freq_label_cmd(),
        # 版心：A4 横版。elegantnote 的 device 只有 pc/pad/kindle/normal/screen，
        # 都不合意，所以加载完自己盖一层 geometry。
        r"\geometry{landscape, margin=1.7cm}",
        # 主色换成 AmTiKu 品牌色（elegantnote 的 \section、标题都用 ecolor）
        r"\definecolor{ecolor}{RGB}{206,51,138}",
        # **品牌页眉页脚**：讲义也是 AmTiKu 出的，页码照样保留。
        *_brand_page_style("高中数学讲义"),
        # 行内公式也用 displaystyle——iPad 上分数才看得清
        r"\everymath{\displaystyle}",
        "",
    ]
    # 字号：elegantnote 只认 10/11/12pt，我们要的档位靠 `\fontsize` 自己设。
    # ⚠️ **第二个参数是行距**，必须给足——写成和字号一样（12pt/12pt）会挤成一团。
    # 中文正文行距取字号的 1.4 倍左右比较舒服。
    if pt != "11pt":
        lead = "%.1fpt" % (float(pt[:-2]) * 1.4)
        doc.append(r"\AtBeginDocument{\fontsize{%s}{%s}\selectfont}" % (pt, lead))
    doc += [
        "",
        "% ── exam-zh 兼容层（题库的题干按 exam-zh 的写法存的） ──",
        # ⚠️ **必须用 xparse 的 `o`，不能用 `\@ifnextchar[` + `[#1]`。**
        #
        # 普通 TeX 的可选参数扫描器**不数方括号**，遇到第一个 `]` 就断：
        #     \fillin[$[-1,1]$]  →  只取到 `$[-1,1`，剩下的 `$]` 漏到正文里
        #     → `! Missing $ inserted`，整份讲义编译不过。
        # xparse 的 `o` 取的是**配平内容**，`$[-1,1]$` 能整个拿到 ✓
        # 实测 250 道抽样里有 3 道栽在这上面。
        r"\NewDocumentCommand{\paren}{o}{\hfill（\hspace{2.2em}）}",
        # 填空横线：`\fillin[..]`、`\fillin{}`、光杆 `\fillin` 三种写法都要吃。
        # 只声明 `o` 就够：方括号被吃掉；`{}` 是个空组，排出来什么都没有；
        # 光杆后面没东西，也不出错。
        r"\NewDocumentCommand{\fillin}{o}{\underline{\hspace{2.6cm}}}",
        r"\newenvironment{choices}%",
        r"  {\begin{enumerate}[label=\Alph*., leftmargin=2em, itemsep=0.25em,"
        r" topsep=0.4em, parsep=0pt]}%",
        r"  {\end{enumerate}}",
        r"\newenvironment{question}{\par\medskip}{\par}",
        # `\symbfit` 是 **unicode-math 的命令**（粗斜体向量），库里用了 12018 次。
        # exam-zh 加载了 unicode-math 所以一直没事；elegantnote 没加载，
        # 不补就是 `Undefined control sequence`，整份讲义编译不过。
        # 用 `\boldsymbol` 顶上——观感一致（希腊字母也变粗斜体），不用为此
        # 引入 unicode-math（那会改动整套数学字体，风险大得多）。
        r"\newcommand{\symbfit}[1]{\boldsymbol{#1}}",
        r"\newcommand{\symbf}[1]{\mathbf{#1}}",
        # 解答题走 `problem` 环境（`question_to_tex` 对 detailed_answer 用它，
        # 还带 `[points = 12]` 这样的可选参数）——**别忘了它**，漏了整个讲义编译不过
        r"\newenvironment{problem}[1][]{\par\medskip}{\par}",
        # 题头：品牌色的「例 N」（难度星已按用户要求去掉，见模块开头）
        r"\newcommand{\hwlabel}[1]{%",
        r"  {\color{ecolor}\bfseries\large 例\,#1}\par\vspace{0.35em}}",
        "",
        (r"\graphicspath{" + "".join("{" + x + "/}" for x in (graphicspath,)) + "}"
         if graphicspath else ""),
        r"\begin{document}",
    ]
    if title:
        doc += [r"\begin{center}{\LARGE\bfseries\color{ecolor} " + _esc_text(title)
                + r"}\end{center}", r"\vspace{1em}"]

    for i, q in enumerate(questions, 1):
        # 从第二题起**先换页**：第一页不留空白页，最后一页也不多一页空白
        if i > 1:
            doc.append(r"\newpage")
        if qid_marks:
            doc.append(_qid_mark(q))
        # 题头：例 N（难度已不印，见模块开头）
        doc.append(r"\hwlabel{%d}" % i)
        _qq = _copy.copy(q)
        _qq.stem = lb.break_inline_parts(q.stem)
        tex = question_to_tex(_qq, with_solution=False, with_source=False)
        # TikZ 换成预渲染的矢量图（同其他卷型，见 `_q_tex` 里的说明）
        from . import tikzfig as _tz
        tex, _n = _tz.to_image(tex, q.figures)
        # **出处并进题干第一行**（同其他卷型，见 `_stem_with_source`）
        if show_source:
            tex = _stem_with_source(tex, q)
        # **给图限高。** 一题一页，图太高就会被挤到下一页——
        # 实测例 6 的频率分布直方图就整张飞到了第 7 页，那页只剩一张图。
        # 加 `height` 后 `keepaspectratio` 会同时满足宽和高两个上限，
        # 即"最宽不超过原设定、最高不超过半页"，图不会被裁变形。
        tex = _cap_figure_height(tex)
        # **题目下方整片留白**：`\vfill` 把剩下的空间全撑开，正好是笔写区。
        doc += [tex, r"\vfill", ""]

    doc.append(r"\end{document}")
    return "\n".join(doc)


def _answers_section(numbering: list[tuple[int, Question]]) -> list[str]:
    r"""卷末的**参考答案与解析**。

    为什么自己写题号而不靠 `\ref`：exam-zh 的题号计数器在"测试卷每节重来"
    的设定下不好从外部引用，而**卷面题号我们在渲染时就知道了**（`numbering`）。
    自己写反而更稳，也不怕以后换模板。

    每道题一段：题号 + 答案（解答题写「见解析」）+ 解析正文。
    按 `\section` 起一节，和卷面的分节在同一层级。
    """
    out = [r"\filbreak", r"\section{参考答案与解析}", ""]
    for no_, q in numbering:
        ans = (q.answer or "").strip()
        # 「解析无」是占位符：答案册里不印这四个字（印了等于把"没有解析"当解析）
        sol = (q.solution or "").strip() if q.has_solution else ""
        if not ans and not sol:
            continue
        # 解答题的答案本来就是"见解析"；这里再兜一次底，
        # 免得出现"题号后面空着"的答案册
        if q.type == "detailed_answer" and not ans:
            ans = "见解析"
        # 题号**和答案**都加粗——对答案的时候是扫的，字重比字号管用；
        # 答案另外**标红**（用户要求：一眼能对上）。
        out.append(r"\noindent\textbf{%d.}\quad{\color{%s}\textbf{%s}}"
                   % (no_, ANS_RED, ans or "（暂无）"))
        out.append("")
        if sol:
            out.append(sol)
            out.append("")
        out.append(r"\vspace{0.8em}")
        out.append("")
    return out


# ── 卷头 ──────────────────────────────────────────────────────────────

def _default_title(mode: str) -> str:
    return "数学试卷" if mode == "gaokao" else "考点测试"


def _total(qs: list[Question]) -> int:
    from collections import Counter
    return gen.total_score(Counter(q.type for q in qs))


def _gaokao_head(qs: list[Question], total: int) -> list[str]:
    r"""高考卷卷头。**说明行与注意事项照抄真题模板**（设计/高考模板.tex）。

    早先用的是 `\information{满分 … }` 一行，和真题的版面对不上：真题是
    「本试卷共 N 页，M 题。全卷满分 150 分。考试用时 120 分钟。」这样一句
    正文，下面才是「注意事项：」加四条。
    """
    pages = r"\pageref{LastPage}"
    return [
        "本试卷共 " + pages + " 页，" + str(len(qs)) + " 题。"
        "全卷满分 " + str(total) + " 分。考试用时 120 分钟。",
        "",
        r"\begin{notice}",
        r"  \item 答卷前，考生务必将自己的姓名、考生号、考场号和座位号填写答题卡上，"
        r"用 2B 铅笔将试卷类型（B）填涂在答题卡相应位置上，"
        r"将条形码横贴在答题卡右上角“条形码粘贴处”。",
        r"  \item 作答选择题时，选出每小题答案后，用 2B 铅笔在答题卡上对应题目选项的"
        r"答案信息点涂黑；如需改动，用橡皮擦干净后，再选涂其他答案。"
        r"答案不能答在试卷上。写在试卷、草稿纸和答题卡上的非答题区域均无效。",
        r"  \item 非选择题必须用黑色字迹的钢笔或签字笔作答，答案必须写在答题卡各题目"
        r"指定区域内相应位置上；如需改动，先划掉原来的答案，然后再写上新答案；"
        r"不准使用铅笔和涂改液。不按以上要求作答无效。",
        r"  \item 考生必须保持答题卡的整洁。考试结束后，将试卷和答题卡一并交回。",
        r"\end{notice}",
        "",
    ]


def _test_head(qs: list[Question], *, subject: str = "数学") -> list[str]:
    r"""测试卷卷头。**照抄 `设计/测试卷模板.tex`**：

        \information{姓名…, 班级…, 学号…}      ← 学生填的抬头
        \begin{notice} \item 考点… \end{notice} ← **考点写进注意事项**

    考点早先是 `{\small\color{gray} 本次覆盖考点：1) …}` 挤成一行，
    模板的做法是逐条列在 `notice` 里——更好读，也更好核对覆盖范围。
    """
    from collections import Counter

    # 考点清单：按出现次数排，同次数的保持稳定顺序
    cnt: Counter = Counter()
    for q in qs:
        for t in q.point_titles:
            cnt[t] += 1
    points = [t for t, _n in cnt.most_common()]

    # **卷面上不印难度**（用户要求：跟讲义一样，只印出处）。
    # 原来这里印一行「难度分布：★ 3 · ★★ 5 …」，现在只留题量；
    # 难度仍在内部用来定解答题留白（`blank_for`）。
    out = [
        r"\information{",
        r"  姓名\underline{\hspace{6em}},",
        r"  班级\underline{\hspace{6em}},",
        r"  学号\underline{\hspace{6em}}",
        r"}",
        "",
        "本试卷共 " + str(len(qs)) + " 题。",
        "",
    ]
    # 考点清单。模板用 `notice` 逐条列——**考点少的时候很好读，多了会吃掉整页**。
    # 实测把一张完整高考卷丢进测试模式会产生 35 个考点，单栏列表排满第一页。
    # 所以分两档：≤10 条照模板用 notice；更多就改双栏紧凑排。
    if points:
        if len(points) <= NOTICE_MAX_ITEMS:
            out.append(r"\begin{notice}")
            out += [r"  \item " + t for t in points]
            out.append(r"\end{notice}")
        else:
            out.append(r"{\bfseries 本次覆盖考点（共 " + str(len(points)) + r" 个）}")
            out.append(r"\begin{multicols}{2}")
            out.append(r"\begin{enumerate}")
            out += [r"  \item " + t for t in points]
            out.append(r"\end{enumerate}")
            out.append(r"\end{multicols}")
    out.append(r"\vspace{0.6em}")
    return out


def _gaokao_section(t: str, n: int) -> str:
    r"""大题标题。

    ⚠️ **不要写「一、」「二、」前缀**——`\section{}` 会自己编号，
    写了就变成「一、一、选择题」。分值按真实卷算，解答题不是均分的。
    """
    if t == "single_choice":
        return (f"选择题：本题共 {n} 小题，每小题 5 分，共 {n*5} 分。"
                "在每小题给出的四个选项中，只有一项是符合题目要求的。")
    if t == "multi_choice":
        return (f"多选题：本题共 {n} 小题，每小题 6 分，共 {n*6} 分。"
                "在每小题给出的选项中，有多项符合题目要求。"
                "全部选对的得 6 分，部分选对的得部分分，有选错的得 0 分。")
    if t == "fill_in_blank":
        return f"填空题：本题共 {n} 小题，每小题 5 分，共 {n*5} 分。"
    scores = gen.answer_scores(n)
    detail = "、".join(str(x) for x in scores)
    return (f"解答题：本题共 {n} 小题，共 {sum(scores)} 分"
            + (f"（{detail} 分）" if len(set(scores)) > 1 else "")
            + "。解答应写出文字说明、证明过程或演算步骤。")


def _test_section(t: str, n: int) -> str:
    r"""测试卷分节标题。带题量与分值，和模板一致。"""
    label = {"single_choice": "选择题", "multi_choice": "多选题",
             "fill_in_blank": "填空题", "detailed_answer": "解答题"}[t]
    if t == "detailed_answer":
        scores = gen.answer_scores(n)
        return (f"{label}（本题共 {n} 小题，共 {sum(scores)} 分。"
                "解答应写出文字说明、证明过程或演算步骤）")
    s = gen.MINOR_SCORE.get(t, 5)
    return f"{label}（本题共 {n} 小题，每小题 {s} 分，共 {n*s} 分）"
