r"""AmTiKu · Question → exam-zh LaTeX

主文件里"人读的那一半"由本模块生成。它是 **IR 的第一个消费端**，
也是唯一产出主文件 LaTeX 的地方。

**写法对齐高考真题模板**（2021 全国乙卷，见 `设计/高考模板.tex`）：

    \begin{question}
      设集合 $A=\{x\mid-2<x<4\}$，$B=\{2,3,4,5\}$，则 $A\cap B=$\paren[B]
      \begin{choices}
        \item $\{2\}$
        ...
      \end{choices}
      \begin{solution}          ← **在环境内部**，不是外面
        ...
      \end{solution}
    \end{question}

三条与旧写法的区别，都是照着模板改的：

1. **答案写进 `\paren[…]` / `\fillin[…]`，不再用 `\item*` 和 `\textbf{答案：}`。**
   `\paren[B]` 会在卷面上右对齐印出「（ B ）」，这是高考卷的样子；
   答案显不显示由 `\examsetup{paren/show-answer, fillin/show-answer}` 一个开关控制，
   不用为了出学生版重写一遍源文件。
2. **`solution` 环境搬到题目环境内部。**
3. **选项不再打星号。**

旧项目的教训：主文件和语料各存一份内容，靠"记得同步"维持一致 → 出过不一致。
这里两块内容（`%% @q` 元数据 + LaTeX）**由同一个 Question 对象生成**，
结构上不可能不一致。
"""
from __future__ import annotations

import re

from .schema import Question

# 题型 → 环境
ENV_OF = {
    "single_choice": "question",
    "multi_choice": "question",
    "fill_in_blank": "question",
    "detailed_answer": "problem",
}

def source_tag(q: Question) -> str:
    r"""试卷上标注的来源，形如 `（2026年新课标I卷-6）`。

    用户要求的格式：**年份 + 年 + 卷别 + 破折号 + 题号**，用括号括起来。
    卷别取 `meta.region`（如「新课标I卷」）；题号取 key 的 `#` 之后那截。
    缺年份或缺卷别就返回空——不硬凑一个假的来源。
    """
    y = q.meta.get("year")
    region = (q.meta.get("region") or "").strip()
    if not region:
        lab = (q.meta.get("source_label") or "").strip()
        region = lab.split("年")[-1] if "年" in lab else lab
    # **题号优先用原卷的**（`meta.source_no`）——key 里那截是新库自己的序号，
    # 不是原卷题号。单题录入时这个区别很要命：卷面上要标的是「第 7 题」，
    # 不是「新库第 13028 道」。
    num = str(q.meta.get("source_no") or "").strip()
    if not num:
        num = q.key.rsplit("#", 1)[-1] if "#" in q.key else ""
    if not (y and region and num):
        return ""
    # ⚠️ **卷别是卷首文字时不要印。** 有些书（`_images` 那几本）的 OCR 把
    # 卷首的「满分：150 分，考试时间：120 分钟」当成了卷别，出处就印成
    # 「（2027 年满分：150 分，-1）」——卷面上很难看。
    # 这不是"改数据"（数据留给用户自己处理），而是**渲染层的兜底**：
    # 明显不是卷名的，宁可不印，也别印一串垃圾上去。
    if _NON_REGION.search(region):
        return ""
    return "（%s年%s-%s）" % (y, region, num)


# 卷首说明性文字的特征。真正的卷别（如「新课标I卷」「上海卷（秋理）」）不会命中。
_NON_REGION = re.compile(r"满分|考试时间|分钟|答题|注意事项|姓名|准考证|页数|共\s*\d+\s*题")


def question_to_tex(q: Question, *, with_solution: bool = True,
                    with_source: bool = False,
                    choices_columns: int = 0) -> str:
    r"""渲染成 exam-zh 标准形态（对齐高考模板）。

    `choices_columns > 0` 时给这道题**单独**设选项列数（`\begin{choices}[columns=N]`）——
    短选项一行四个、长选项一行两个，见 `paper.choices_columns`。

    `with_solution=False` 时省略 `\begin{solution}` 块——
    即"只出题目不出解答"。注意**答案本身不受它影响**：
    答案写在 `\paren[…]`/`\fillin[…]` 里，用 `\examsetup` 的开关控制显示。
    """
    env = ENV_OF.get(q.type, "question")
    out: list[str] = []

    # 解答题带分值选项；exam-zh 靠它算分
    opt = ""
    if q.type == "detailed_answer" and q.meta.get("points"):
        opt = f"[points = {q.meta['points']}]"

    # ⚠️ **这里不做任何规范化。** 答案怎么进 `\paren[…]`/`\fillin[…]`
    # 是 **ENTRY 级规则**（amti/rules.py）在**录入时**做掉的，
    # 渲染端只管把已经规范的题干原样写出来。
    #
    # 早先这里自己塞了一套「隐式修正」，后果是：只要改一次渲染逻辑，
    # 全库数据在你重新导出时就悄悄变了——那正是顶层设计 §4.3 要禁止的
    # 「把 MIGRATE 级规则当 ENTRY 级用」。
    stem = q.stem.rstrip()
    placed = bool(re.search(r"\\paren\s*\[|\\fillin\s*\[", stem))

    out.append(f"\\begin{{{env}}}{opt}")
    # ⚠️ **TikZ→图片的替换不在这里做。**
    #
    # 这里**同时是写库路径**：`store.render_question` 就是拿这个函数把
    # 题目序列化回 `.tex` 的。把替换塞在这儿，等于"每次写库都把题干里的
    # TikZ 悄悄改成 `\includegraphics`"——实测污染了 236 道题。
    #
    # 这正是顶层设计 §4.3 明令禁止的「把渲染期的改动当成数据」。
    # 替换改到 `paper._q_tex` 里做：**只有出卷子时才换**，数据一个字不动。
    out.append(stem)

    # 来源标注：单独一行、小字，跟在题干后面。
    # **由调用方决定加不加**（测试卷要，高考卷不要——高考卷是仿真卷面）。
    #
    # ⚠️ 这里必须是**单**反斜杠。原先写成 raw string 却打了两个反斜杠
    # （`r"{\\small\\color{gray} "`），LaTeX 把 `\\` 当成换行，
    # 于是卷面上真的印出了「small」和「colorgray」两行字。
    if with_source:
        tag = source_tag(q)
        if tag:
            out.append(r"{\small\color{gray} " + tag + "}")

    if q.options:
        # 选项列数：**这道题单独设**，不走全局。一道卷子里既有
        # 「A. 1  B. 2」这种短选项，也有整句话的长选项，一刀切必然有一头难看。
        out.append("\\begin{choices}" + (
            "[columns = %d]" % choices_columns if choices_columns else ""))
        for o in q.options:
            out.append(f"  \\item {o.text.strip()}")
        out.append("\\end{choices}")

    # 解答：**写在题目环境内部**（高考模板的写法）
    body: list[str] = []
    if q.answer.strip() and not placed:
        # 答案没地方内联（题干没有作答括号／空位数对不上），退回解析里写
        body.append("\\textbf{答案：}" + q.answer.strip())
    if q.solution.strip():
        body.append(q.solution.strip())
    if with_solution and body:
        out.append("\\begin{solution}")
        out.extend(body)
        out.append("\\end{solution}")

    out.append(f"\\end{{{env}}}")
    return "\n".join(out)


def to_markdown(q: Question) -> str:
    """给 LLM 用的纯文本形态（打标签时喂题目）。"""
    parts = [q.stem]
    if q.options:
        parts.append("\n".join(f"{o.label}. {o.text}" for o in q.options))
    if q.answer:
        parts.append(f"答案：{q.answer}")
    if q.solution:
        parts.append(f"解析：{q.solution}")
    return "\n".join(parts)


if __name__ == "__main__":
    from .latex_ir import parse_question
    from .schema import Option

    fails = 0

    def check(name, cond, extra=""):
        global fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("render_tex 自检")

    # 契约变了：**渲染端不做规范化**。规范化是 ENTRY 级规则（rules.py）
    # 在录入时做掉的。所以这里的输入已经是规范形态。
    q = Question(
        key="t/1", type="single_choice",
        stem=r"设集合 $A=\{1,2,3\}$，$B=\{2,3,4\}$，则 $A\cap B=$ \paren[B]",
        options=[Option("A", r"$\{2\}$"), Option("B", r"$\{2,3\}$")],
        answer="B", solution=r"由交集定义得 $\{2,3\}$。")
    tex = question_to_tex(q)
    check("题目环境", tex.startswith("\\begin{question}"), tex[:40])
    check("solution 在 question 内部",
          tex.index("\\begin{solution}") < tex.index("\\end{question}"), tex)
    check(r"渲染端不动题干（\paren 原样）", r"\paren[B]" in tex, tex)
    check(r"不再输出 \item*", r"\item*" not in tex, tex)

    back = parse_question(tex)
    check("往返：题型", back.type == q.type, back.type)
    check("往返：答案", back.answer == "B", repr(back.answer))
    check("往返：选项数", len(back.options) == 2, str(len(back.options)))
    check("往返：解析没混进题干",
          "solution" not in back.stem and "交集定义" not in back.stem, back.stem)

    # 答案没内联时，退回解析里写 `\textbf{答案：}`
    q2 = Question(key="t/2", type="detailed_answer", stem="求 $x$．",
                  answer="$x=1$", solution="移项得 $x=1$．")
    t2 = question_to_tex(q2)
    check("答案没处内联时写进解析",
          r"\textbf{答案：}$x=1$" in t2, t2)

    # 幂等：渲染过的再渲染一次必须一模一样
    for name, qq in (("选择题", q), ("解答题", q2)):
        t1 = question_to_tex(qq)
        check("幂等：%s 二次渲染不变" % name,
              t1 == question_to_tex(parse_question(t1)), t1)

    print("render_tex 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    raise SystemExit(1 if fails else 0)
