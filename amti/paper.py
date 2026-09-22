"""AmTiKu · 两种卷型

**高考卷**（`gaokao`）—— 照高考真题的样子排
    标题 + 科目 + 信息行 + 注意事项 + 四个大题分节（带"只有一项符合"这类说明）

**测试题**（`test`）—— 考点专练
    * 开头**小字**列出本次覆盖的考点
    * **每道题标出难度等级**（从主考点派生）
    * 不分正式大题，按题型简单分节

两种模式与 `export.py` 共用同一套渲染，只是头部和每题前缀不同。
"""
from __future__ import annotations

import re

from . import generate as gen
from .schema import Question
from .render_tex import question_to_tex, source_tag

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

_ANS_MACRO = re.compile(r"(\\paren\s*\[[^\]]*\]|\\fillin\s*\[[^\]]*\]|"
                        r"\\fillin\s*\{[^}]*\})")


def red_answer_macros(tex: str) -> str:
    r"""把 `\paren[…]` / `\fillin[…]` 整块染红（**只在出卷子时调用**）。"""
    return _ANS_MACRO.sub(lambda m: "{\\color{%s}%s}" % (ANS_RED, m.group(1)), tex)

# 难度 → 显示
DIFF_STARS = {"简单题": 1, "中档题": 2, "难题": 3}

# ── 按位置定难度 ──────────────────────────────────────────────────────
#
# 高考数学的惯例：**难度由题目在卷中的位置决定**，不是题目自带的属性。
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


def layout_difficulty(questions: list) -> list[tuple]:
    """算出整卷的「题号 → 难度」布局，用于预览。"""
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for q in questions:
        groups[q.type].append(q)
    out = []
    for t in ("single_choice", "multi_choice", "fill_in_blank", "detailed_answer"):
        items = groups.get(t, [])
        for i, q in enumerate(items):
            out.append((t, i + 1, len(items), position_difficulty(t, i, len(items)), q))
    return out


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


def _star_line(diff: str) -> str:
    """难度 → `〔★★〕`。讲义题头用。"""
    n = DIFF_STARS.get(diff, 0)
    return ("〔" + star_tex(n) + "〕") if n else ""


def star_tex(n: int) -> str:
    r"""n 颗星，用于 LaTeX。

    ⚠️ **必须走 `$\star$`，不能直接写 `★`(U+2605)。**
    实测：`★ ● ■ ▲ ☆` 这些字符在 fandol / NewCM 字体里**都没有字形**，
    编译出来是一排豆腐块 □。`\textbullet` 和 `$\circ$` 有字形，但
    `$\star$` 最像星级标记。
    """
    return ("$" + r"\star" * n + "$") if n else ""


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
    r"""这道解答题后面留多少。`uniform > 0` 时一律用它。"""
    if uniform and uniform > 0:
        return uniform
    return BLANK_BY_DIFFICULTY.get(diff, 5.0)


def _star(diff: str, stars: int) -> str:
    return star_tex(stars or DIFF_STARS.get(diff, 0))


def choices_columns(q: Question, default: int = 4) -> int:
    r"""按选项长短挑列数。

    不能**数字符**——源码长度和排出来的宽度差得远：

        $\frac{1}{2}$        源码 13 个字符，排出来只有两三个字的宽
        样本 $x_1$ 的标准差    17 个字符，排出来真的宽

    所以：把行内公式挖掉，剩下的按"中文算 2、其它算 1"计；每个公式
    再折 5 个半角宽。

    判据按**高考卷的惯例**定：一行两个是常态，四个都特别短才排一行四个，
    整句话的选项单独占一行。
    """
    if not q.options:
        return default

    def width(t: str) -> int:
        t = t or ""
        math = re.findall(r"\$[^$]*\$", t)
        plain = re.sub(r"\$[^$]*\$", "", t)
        return sum(2 if ord(c) > 0x2E80 else 1 for c in plain) + len(math) * 5

    n = max(width(o.text) for o in q.options)
    if n <= 7:
        return 4
    if n <= 34:
        return 2
    return 1


def _q_tex(q: Question, mode: str, show_answers: bool,
           diff_override: str = "", default_columns: int = 4,
           show_source: bool = False, with_solution: bool = True) -> str:
    # **解析常驻源文件**，显不显示交给 `\examsetup{solution/show-solution}`——
    # 这是高考模板的做法：不用为了出学生版重写一遍源文件。
    #
    # **测试卷**要标来源，高考卷不标——高考卷是仿真卷面，多一行小字就不像真题了。
    #
    # 来源**不走 `with_source`**：那样会另起一行排在题干后面，
    # 题号、难度、来源散成三处。这里统一拼成一个前缀，**跟难度并排**：
    #
    #     〔★★★〕（2026年新课标I卷-6）题干……
    # **选项列数按内容自适应。**
    # exam-zh 默认 `choices/columns = 4`（一行四个），短选项很好看；
    # 但选项一长（比如「样本 $x_1$ 的标准差」这种），四列会挤成一团、
    # 或者自动折成两行且对不齐。所以按最长选项的长度挑列数：
    #   ≤ 12 字  → 4 列（一行摆下）
    #   ≤ 26 字  → 2 列（两行两列，高考卷最常见的排法）
    #   更长     → 1 列（一行一个）
    cols = choices_columns(q, default_columns)
    tex = question_to_tex(q, with_solution=with_solution, with_source=False,
                          choices_columns=cols)
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
    if mode != "test":
        return tex
    # 测试模式：题干第一行前加灰色前缀（`\small\color{gray}` 不抢视线）。
    # **难度按位置定**（`diff_override`），不是题目自带的那套星级——
    # 高考卷的难度本来就是由位置决定的（见 POSITION_RULE 的说明）。
    #
    # **只标星星，不写「简单题/中档题/难题」**——星星自己会说话，
    # 加上文字反而占地方、抢视线。
    diff = diff_override or q.difficulty
    n = DIFF_STARS.get(diff, 0)
    star = "〔" + star_tex(n) + "〕" if n else ""
    # **出处默认不印。** 用户的判断：那串东西没有意义——
    #   · 高考题印 `（2024年新高考I卷-1）`：题目本身就是真题，读者知道；
    #   · 模拟题印 `（2027年004-3）`：`004` 是原书的页码，不是卷名。
    # 占地方、还容易被误当成题面的一部分。**要印就显式开 `show_source`。**
    src = source_tag(q) if show_source else ""
    if not (star or src):
        return tex                       # 两样都没有就不留空壳
    head, _sep, rest = tex.partition("\n")
    return (head + "\n" + r"{\small\color{gray}" + star + src + "}"
            + rest.lstrip("\n"))


def render_paper(questions: list[Question], *, mode: str = "gaokao",
                 title: str = "", subject: str = "数学", show_answers: bool = False,
                 answers_at_end: bool = False, show_source: bool = False,
                 bottom_sep: str = "0.6em", problem_blank_cm: float = 0.0,
                 columns: int = 4, graphicspath: str = "",
                 handout_font: str = HANDOUT_FONT_DEFAULT) -> str:
    r"""渲染成完整的 exam-zh 文档。`mode` 取 `gaokao` / `test` / `handout`。

    三种"答案怎么放"：

    | `show_answers` | `answers_at_end` | 效果 |
    |---|---|---|
    | False | — | **学生卷**：作答位置空着，解答题留白，没有答案 |
    | True  | False | **讲义卷**：答案就在括号里、解析紧跟题目 |
    | False | True  | **真题卷**：卷面上干干净净，**答案与解析统一放在卷末** |

    第三种才是真实高考卷的做法——卷子上只有题目，答案另附。
    `problem_blank_cm`：解答题留白。**留空（0）＝按难度自动**（3/5/8cm），
    给正数则一律用它。

    `answers_at_end` 会把 `show_answers` 的效果**收起来**：
    括号不显示答案，题目后面不带 `solution` 环境，改成卷末一节。
    """
    if mode == "handout":
        return _render_handout(questions, title=title, columns=columns,
                               graphicspath=graphicspath, font=handout_font)
    if mode not in ("gaokao", "test"):
        raise ValueError(f"未知卷型 {mode!r}")

    total_score = _total(questions)
    # 答案放卷末时，卷面上的括号和解析都要收起来——不然答案会印两遍
    if answers_at_end:
        show_answers = False

    # 导言区走**共用的一份**（`_preamble`）——讲义模式当初另抄一份，
    # 漏了自定义 pgfplots 样式，一编译就死。两份导言就是两份真相。
    doc: list[str] = _preamble(title=title, graphicspath=graphicspath,
                               show_answers=show_answers, bottom_sep=bottom_sep,
                               columns=columns)
    doc.append(r"\begin{document}")
    return _paper_body(doc, questions, mode=mode, subject=subject,
                       show_answers=show_answers, answers_at_end=answers_at_end,
                       columns=columns, graphicspath=graphicspath,
                       bottom_sep=bottom_sep, problem_blank_cm=problem_blank_cm,
                       total_score=total_score, show_source=show_source)
def _preamble(*, title: str = "", graphicspath: str = "",
              show_answers: bool = False, answers_at_end: bool = False,
              bottom_sep: str = "0.6em", columns: int = 4,
              landscape: bool = False, big_font: bool = False,
              first_line: str = "") -> list[str]:
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
        out += [r"\title{" + title + "}", r"\subject{数学}"]
    return out


def _paper_body(doc: list[str], questions: list[Question], *,
                mode: str, subject: str, show_answers: bool,
                answers_at_end: bool, columns: int, graphicspath: str,
                bottom_sep: str, problem_blank_cm: float,
                total_score: int, show_source: bool = False) -> str:
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
            if i:
                doc.append(r"\filbreak")
            # **题干和它的选项不许被分页拆开。**
            #
            # 不加这句时，一道题可以"题干在这页末尾、选项跑到下页开头"——
            # 学生翻页才能看到选项，很别扭。`\needspace{6\baselineskip}`
            # 的意思是"下面至少还要留得下 6 行，否则现在就把这一页断掉"。
            #
            # 6 行是个折中：够装下"题干 2-3 行 + 选项 2 行"，
            # 又不会因为要求太高而在页底留下大片空白。
            doc.append(r"\needspace{6\baselineskip}")
            doc.append(_q_tex(q, mode, show_answers and not answers_at_end,
                              diff_override=diff, default_columns=columns,
                              show_source=show_source))
            # 解答题留白：**必须 `\vspace*`**（带星号）——
            # 不带星号的 `\vspace` 在分页处会被丢弃，题目落在页底时留白凭空消失
            if t == "detailed_answer" and not show_answers:
                cm = blank_for(diff, problem_blank_cm)
                if cm > 0:
                    doc.append(f"\\vspace*{{{cm:.2f}cm}}")
            doc.append("")

    if answers_at_end and numbering:
        doc += _answers_section(numbering)

    doc.append(r"\end{document}")
    return "\n".join(doc)


def _render_handout(questions: list[Question], *, title: str = "",
                    columns: int = 4, graphicspath: str = "",
                    font: str = HANDOUT_FONT_DEFAULT) -> str:
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
        # 题头：品牌色的「例 N」+ 灰色星级
        r"\newcommand{\hwlabel}[2]{%",
        r"  {\color{ecolor}\bfseries\large 例\,#1}\hspace{0.7em}%",
        r"  {\small\color{gray}#2}\par\vspace{0.35em}}",
        "",
        (r"\graphicspath{" + "".join("{" + x + "/}" for x in (graphicspath,)) + "}"
         if graphicspath else ""),
        r"\begin{document}",
    ]
    if title:
        doc += [r"\begin{center}{\LARGE\bfseries\color{ecolor} " + title
                + r"}\end{center}", r"\vspace{1em}"]

    for i, q in enumerate(questions, 1):
        # 从第二题起**先换页**：第一页不留空白页，最后一页也不多一页空白
        if i > 1:
            doc.append(r"\newpage")
        # 题头：例 N + 难度星（`star_tex` 走 `$\star$`，字面 `★` 会变豆腐块）
        star = _star_line(q.difficulty)
        label = star
        doc.append(r"\hwlabel{%d}{%s}" % (i, label))
        tex = question_to_tex(q, with_solution=False, with_source=False)
        # TikZ 换成预渲染的矢量图（同其他卷型，见 `_q_tex` 里的说明）
        from . import tikzfig as _tz
        tex, _n = _tz.to_image(tex, q.figures)
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
        sol = (q.solution or "").strip()
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

    # 难度分布也是星星，和每题的标记统一
    diffs = Counter(d for _t, _i, _n, d, _q in layout_difficulty(qs))
    diff_txt = " · ".join(
        f"{star_tex(DIFF_STARS.get(k, 0))} {v}" for k, v in
        sorted(diffs.items(), key=lambda x: DIFF_STARS.get(x[0], 9)))

    out = [
        r"\information{",
        r"  姓名\underline{\hspace{6em}},",
        r"  班级\underline{\hspace{6em}},",
        r"  学号\underline{\hspace{6em}}",
        r"}",
        "",
        "本试卷共 " + str(len(qs)) + " 题 · 难度分布：" + diff_txt + "。",
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
