r"""AmTiKu · 逐题订正 —— **题目有问题就直接改题目**

`normalize.py` 管的是**成片**的写法问题：一条规则命中几百道，改法都一样。
但还有一类问题**一道一个样**，写不进规则：

    · 某道题的选项从 PDF 提取时掉了一个根号；
    · 某道题的题干把 `a+b` 印成了 `a-b`；
    · 某道题的选项干脆是另一道题的（PDF 串列）；
    · 某道题的流程图配错了图。

这些只能一道道改。这个模块就是那本「逐题订正账」。

## 三条护栏

1. **凭据 `src`** —— 每条都要写清"凭什么这么改"：原卷、题号，或者
   同一份卷子里另一道**没被提取坏**的孪生题（比如天津卷文理同题）。
   没有凭据的改动不许写进这张表。
2. **前后对照 `expect`** —— 改之前先核对当前值，对不上就**整批拒绝执行**。
   题目后来又被别的规则动过，这里却按老印象去改，是最危险的一种错。
3. **留痕** —— 改完写一份 `变更记录/`，逐条列出改了什么、依据是什么。

## 用法

    python3 -m amti.fixups              # 干跑：只报会改哪些
    python3 -m amti.fixups --yes        # 落盘
    python3 -m amti.fixups --selftest   # 自检（护栏本身也要自证）
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import re
from pathlib import Path

from . import store
from .schema import Option, Question

PKG = Path(__file__).resolve().parent.parent
CHANGE_DIR = PKG / "变更记录"


# ── 订正账 ────────────────────────────────────────────────────────────
#
# 每条：
#   key     题号
#   why     为什么改（一句话）
#   src     凭据（原卷/孪生题/题面自洽性；**必填**）
#   expect  改之前的现状：字段 → 必须出现的子串（`type` 是精确相等）
#   set     改成什么：字段 → 新值
#
# 可选字段：type / stem / answer / solution / options（[[标签, 文字], …]）
#           / drop_figures（True 表示这道题的配图是错的，撤掉）

# ── 已订正、且其后又被别的订正改过：**注销账目** ─────────────────────
#
# 这些条目当初是对的，但它们 `expect` 记的是"改动前"的样子；题目后来又
# 被后面的订正改过（例如题干被补充完整、题型又被改对），于是这张账
# 既不是"还没改"、也不是"已改成 set 的样子"，全表核对就把它当冲突，
# **整批拒绝执行**（实测：19 条新订正被这 6 条挡住）。
# 历史留在 `变更记录/`，这里只注销账目，不再核对。
RETIRED_KEYS: set[str] = {
    "2027千题册创新拔高册（上）_images/305#16",
    "2027千题册创新拔高册（下）_images/196#50",
    "2027千题册经典重点册（下）_images/020#30",
    "2027 高考数学考前模拟十二套卷_images/030#11",
    "2027千题册经典重点册（上）_images/028#51",
    "2027千题册经典重点册（下）_images/222#52",
}

PATCHES: list[dict] = [
    {
        "key": "高考真题汇编/1993/全国卷（文）#16",
        "why": "题干漏了指数——`3a = 4b = 6c` 应为 `3^a = 4^b = 6^c`",
        "src": "题面自洽：按 `3a=4b=6c`（一次式）算，四个选项无一成立；"
               "按 `3^a=4^b=6^c` 算，1/c=ln6/lnk、1/a+1/b=ln12/lnk，"
               "而 2/c=2ln6/lnk=ln36/lnk 与 2/a+1/b=(2ln3+ln4)/lnk=ln36/lnk 相等，B 成立",
        "expect": {"type": "multi_choice", "stem": "3a = 4b = 6c",
                   "answer": "题面无正确选项"},
        "set": {
            "type": "single_choice",
            "stem": r"设 $a$，$b$，$c$ 都是正数，且 $3^{a} = 4^{b} = 6^{c}$，那么\paren[B]",
            "answer": "B",
            "solution": (
                "令 $3^{a}=4^{b}=6^{c}=k$（$k>0$），取对数得\n"
                "\\[\n a\\ln 3=b\\ln 4=c\\ln 6=\\ln k\n\\]\n"
                "所以 $\\dfrac{1}{c}=\\dfrac{\\ln 6}{\\ln k}$，"
                "$\\dfrac{1}{a}+\\dfrac{1}{b}=\\dfrac{\\ln 3+\\ln 4}{\\ln k}"
                "=\\dfrac{\\ln 12}{\\ln k}$，两者不等，A 错.\n\n"
                "又 $\\dfrac{2}{c}=\\dfrac{2\\ln 6}{\\ln k}=\\dfrac{\\ln 36}{\\ln k}$，而\n"
                "\\[\n \\frac{2}{a}+\\frac{1}{b}"
                "=\\frac{2\\ln 3+\\ln 4}{\\ln k}"
                "=\\frac{\\ln 36}{\\ln k}=\\frac{2}{c}\n\\]\n"
                "所以 B 成立. 逐项检验 C、D 均不成立. 故选 B."),
        },
    },
    {
        "key": "高考真题汇编/1993/全国卷（理）#16",
        "why": "同上（1993 年全国卷文理同题，理卷也漏了指数）",
        "src": "与 1993 全国卷（文）#16 同一道题，改法一致",
        "expect": {"type": "multi_choice", "stem": "3a = 4b = 6c",
                   "answer": "无正确选项"},
        "set": {
            "type": "single_choice",
            "stem": r"设 $a$，$b$，$c$ 都是正数，且 $3^{a} = 4^{b} = 6^{c}$，那么\paren[B]",
            "answer": "B",
            "solution": (
                "令 $3^{a}=4^{b}=6^{c}=k$（$k>0$），则\n"
                "\\[\n a\\ln 3=b\\ln 4=c\\ln 6=\\ln k\n\\]\n"
                "于是 $\\dfrac{2}{c}=\\dfrac{2\\ln 6}{\\ln k}=\\dfrac{\\ln 36}{\\ln k}$，"
                "$\\dfrac{2}{a}+\\dfrac{1}{b}=\\dfrac{2\\ln 3+\\ln 4}{\\ln k}"
                "=\\dfrac{\\ln 36}{\\ln k}$，两者相等，B 成立.\n\n"
                "A 项 $\\dfrac{1}{a}+\\dfrac{1}{b}=\\dfrac{\\ln 12}{\\ln k}"
                "\\neq\\dfrac{\\ln 6}{\\ln k}=\\dfrac{1}{c}$；"
                "C、D 逐项代入亦不成立. 故选 B."),
        },
    },
    {
        "key": "高考真题汇编/1998/全国卷（文）#12",
        "why": "选项串到了下一题——本题的选项被印成了「7 倍/5 倍/4 倍/3 倍」",
        "src": "同一卷的 #13 拿到了本题的选项（$\\pm\\frac{\\sqrt{3}}{4}$ 等四个坐标值），"
               "两道题的选项在 PDF 里**整组互换**；按题面算 M 的纵坐标恰为 $\\pm\\frac{\\sqrt{3}}{4}$",
        "expect": {"type": "multi_choice", "stem": "点 $M$ 的纵坐标是",
                   "options": ["$7$ 倍", "$5$ 倍"]},
        "set": {
            "type": "single_choice",
            "stem": (r"椭圆 $\frac{x^2}{12} + \frac{y^2}{3} = 1$ 的焦点为 $F_1$ 和 $F_2$. "
                     r"点 $P$ 在椭圆上，如果线段 $PF_1$ 的中点 $M$ 在 $y$ 轴上，"
                     r"那么点 $M$ 的纵坐标是\paren[A]"),
            "options": [["A", r"$\pm\frac{\sqrt{3}}{4}$"],
                        ["B", r"$\pm\frac{\sqrt{2}}{2}$"],
                        ["C", r"$\pm\frac{\sqrt{3}}{2}$"],
                        ["D", r"$\pm\frac{3}{4}$"]],
            "answer": "A",
            "solution": (
                "椭圆的 $a^{2}=12$，$b^{2}=3$，所以 $c^{2}=12-3=9$，$c=3$，"
                "焦点为 $F_1(-3,0)$，$F_2(3,0)$.\n\n"
                "设 $P=(x,y)$，则 $PF_1$ 的中点 "
                "$M=\\left(\\dfrac{x-3}{2},\\dfrac{y}{2}\\right)$.\n\n"
                "由 $M$ 在 $y$ 轴上得 $\\dfrac{x-3}{2}=0$，即 $x=3$. 代入椭圆方程：\n"
                "\\[\n \\frac{9}{12}+\\frac{y^{2}}{3}=1"
                "\\;\\Longrightarrow\\;\\frac{y^{2}}{3}=\\frac{1}{4}"
                "\\;\\Longrightarrow\\;y=\\pm\\frac{\\sqrt{3}}{2}\n\\]\n"
                "所以 $M$ 的纵坐标为 $\\dfrac{y}{2}=\\pm\\dfrac{\\sqrt{3}}{4}$. 故选 A."),
        },
    },
    {
        "key": "高考真题汇编/2004/全国II卷（文）#9",
        "why": "题干问错了量——`|a|+|b|` 应为 `|a+b|`",
        "src": "题面自洽：$|a|=1$、$|b|=2$ 时 $|a|+|b|=3$ 是常数值，"
               "根本不用给 $|a-b|=2$，且 3 不在选项里；"
               "按 $|a+b|$ 算得 $\\sqrt6$，正好是选项 D",
        "expect": {"type": "multi_choice",
                   "stem": r"则 $\left|\symbfit{a}\right|+\left|\symbfit{b}\right|=$"},
        "set": {
            "type": "single_choice",
            "stem": (r"已知向量 $\symbfit{a}$，$\symbfit{b}$ 满足："
                     r"$\left|\symbfit{a}\right|=1$，$\left|\symbfit{b}\right|=2$，"
                     r"$\left|\symbfit{a}-\symbfit{b}\right|=2$，"
                     r"则 $\left|\symbfit{a}+\symbfit{b}\right|=$\paren[D]"),
            "answer": "D",
            "solution": (
                "由 $\\left|\\symbfit{a}-\\symbfit{b}\\right|^{2}=4$ 得\n"
                "\\[\n \\left|\\symbfit{a}\\right|^{2}+\\left|\\symbfit{b}\\right|^{2}"
                "-2\\symbfit{a}\\cdot\\symbfit{b}=4\n\\]\n"
                "代入 $\\left|\\symbfit{a}\\right|=1$、$\\left|\\symbfit{b}\\right|=2$，得 "
                "$1+4-2\\symbfit{a}\\cdot\\symbfit{b}=4$，即 "
                "$\\symbfit{a}\\cdot\\symbfit{b}=\\dfrac{1}{2}$.\n\n"
                "所以\n"
                "\\[\n \\left|\\symbfit{a}+\\symbfit{b}\\right|^{2}"
                "=\\left|\\symbfit{a}\\right|^{2}+\\left|\\symbfit{b}\\right|^{2}"
                "+2\\symbfit{a}\\cdot\\symbfit{b}=1+4+1=6\n\\]\n"
                "故 $\\left|\\symbfit{a}+\\symbfit{b}\\right|=\\sqrt6$. 故选 D."),
        },
    },
    {
        "key": "高考真题汇编/2004/湖南卷（理）#3",
        "why": "题干问错了量——`f(a-b)` 应为 `f(a+b)`",
        "src": "题面自洽：已知条件只能推出 $a+b=3$，推不出 $a-b$；"
               "而 $f(a+b)=\\log_2 4=2$ 正好是选项 B",
        "expect": {"type": "multi_choice", "stem": "则 $f(a-b)$ 的值为"},
        "set": {
            "type": "single_choice",
            "stem": (r"设 $f^{-1}(x)$ 是函数 $f(x)=\log_{2}(x+1)$ 的反函数，"
                     r"若 $\left[1+f^{-1}(a)\right]\left[1+f^{-1}(b)\right]=8$，"
                     r"则 $f(a+b)$ 的值为\paren[B]"),
            "answer": "B",
            "solution": (
                "由 $f(x)=\\log_{2}(x+1)$ 得 $f^{-1}(x)=2^{x}-1$，于是 "
                "$1+f^{-1}(a)=2^{a}$，$1+f^{-1}(b)=2^{b}$.\n\n"
                "由已知\n"
                "\\[\n 2^{a}\\cdot 2^{b}=2^{a+b}=8=2^{3}\n\\]\n"
                "所以 $a+b=3$，从而\n"
                "\\[\n f(a+b)=\\log_{2}(3+1)=\\log_{2}4=2\n\\]\n"
                "故选 B."),
        },
    },
    {
        "key": "高考真题汇编/2007/四川卷（文）#12",
        "why": "选项 D 掉了根号——`(2-√21)/3` 应为 `2√21/3`",
        "src": "按题面（三平行线间距 1 与 2、正三角形三顶点各在一条线上）解得边长 "
               "$\\frac{2\\sqrt{21}}{3}\\approx3.055$；选项中只有 D 的形状与之相同却印成了减号",
        "expect": {"type": "multi_choice", "stem": "三条平行直线",
                   "options": [r"$\frac{2 - \sqrt{21}}{3}$"]},
        "set": {
            "type": "single_choice",
            "stem": (r"如图，$l_{1}$，$l_{2}$，$l_{3}$ 是同一平面内的三条平行直线，"
                     r"$l_{1}$ 与 $l_{2}$ 间的距离是 $1$，$l_{2}$ 与 $l_{3}$ 间的距离是 $2$，"
                     r"正三角形 $ABC$ 的三顶点分别在 $l_{1}$，$l_{2}$，$l_{3}$ 上，"
                     r"则 $\triangle ABC$ 的边长是\paren[D]"
                     "\n\n\\includegraphics[width=0.54\\linewidth]{d0e1cb8f8056974d.png}"),
            "options": [["A", r"$2\sqrt{3}$"],
                        ["B", r"$\frac{4\sqrt{6}}{3}$"],
                        ["C", r"$\frac{3 - \sqrt{7}}{4}$"],
                        ["D", r"$\frac{2\sqrt{21}}{3}$"]],
            "answer": "D",
            "solution": (
                "取三条平行线依次为 $y=0$，$y=1$，$y=3$，设 "
                "$A\\in l_1$，$B\\in l_2$，$C\\in l_3$.\n\n"
                "设 $AB$ 与 $l_1$ 所成角为 $\\theta$，边长为 $s$，"
                "则 $A$、$B$ 到 $l_1$ 的距离差为 $s\\sin\\theta=1$；"
                "$A$、$C$ 到 $l_1$ 的距离差为 $s\\sin(\\theta+60^{\\circ})=3$.\n\n"
                "两式相除：$\\sin(\\theta+60^{\\circ})=3\\sin\\theta$，展开得\n"
                "\\[\n \\frac{1}{2}\\sin\\theta+\\frac{\\sqrt{3}}{2}\\cos\\theta=3\\sin\\theta"
                "\\;\\Longrightarrow\\;\\tan\\theta=\\frac{\\sqrt{3}}{5}\n\\]\n"
                "于是 $\\sin\\theta=\\dfrac{\\sqrt{3}}{2\\sqrt{7}}$，"
                "故\n"
                "\\[\n s=\\frac{1}{\\sin\\theta}=\\frac{2\\sqrt{7}}{\\sqrt{3}}"
                "=\\frac{2\\sqrt{21}}{3}\n\\]\n"
                "故选 D."),
        },
    },
    {
        "key": "高考真题汇编/2007/福建卷（理）#8",
        "why": "选项 D 的符号印错了——`n ⊂ α` 应为 `n ⊥ α`",
        "src": "按原样四项全假（A 缺「相交」、B 两线可异面、C 的 n 可在 α 内），"
               "而按 `n∥m，n⊥α ⇒ m⊥α` 则 D 为真，与「下列命题中正确的是」相容",
        "expect": {"type": "multi_choice", "stem": "下列命题中正确的是",
                   "options": [r"$n \parallel m$，$n \subset \alpha \Rightarrow m \perp \alpha$"]},
        "set": {
            "type": "single_choice",
            "stem": (r"已知 $m$，$n$ 为两条不同的直线，$\alpha$，$\beta$ 为两个不同的平面，"
                     r"则下列命题中正确的是\paren[D]"),
            "options": [["A", r"$m \subset \alpha$，$n \subset \alpha$，$m \parallel \beta$，"
                             r"$n \parallel \beta \Rightarrow \alpha \parallel \beta$"],
                        ["B", r"$\alpha \parallel \beta$，$m \subset \alpha$，"
                              r"$n \subset \beta \Rightarrow m \parallel n$"],
                        ["C", r"$m \perp \alpha$，$m \perp n \Rightarrow n \parallel \alpha$"],
                        ["D", r"$n \parallel m$，$n \perp \alpha \Rightarrow m \perp \alpha$"]],
            "answer": "D",
            "solution": (
                "逐项检验.\n\n"
                "A 不成立：$m$，$n$ 都平行于 $\\beta$ 时 $\\alpha$ 仍可与 $\\beta$ 相交"
                "（例如 $\\alpha$ 与 $\\beta$ 交于一条直线，$m$，$n$ 都平行于这条交线）.\n\n"
                "B 不成立：分别在两个平行平面内的两条直线可以异面，未必平行.\n\n"
                "C 不成立：$m\\perp\\alpha$ 且 $m\\perp n$ 时，$n$ 可能就在 $\\alpha$ 内.\n\n"
                "D 成立：由 $n\\perp\\alpha$ 知 $n$ 垂直于 $\\alpha$ 内的任意直线；"
                "又 $m\\parallel n$，一条直线垂直于一个平面，则与它平行的直线也垂直于该平面，"
                "故 $m\\perp\\alpha$.\n\n故选 D."),
        },
    },
    {
        "key": "高考真题汇编/2008/山东卷（理）#10",
        "why": "题干数字印错——「长轴长为 25」应为 26，否则离心率与长轴长不相容",
        "src": "题面自洽：$e=\\frac{5}{13}$ 且长轴长为 26 时 $a=13$、$c=5$、$b=12$，"
               "焦点恰为 $(\\pm5,0)$，与选项里出现的 $13^2$、$12^2$、$5^2$ 全部对上；"
               "取 25 则 $b^2=133.14$ 不是平方数，且与任何选项都不相容",
        "expect": {"type": "multi_choice", "stem": "长轴长为 25"},
        "set": {
            "type": "single_choice",
            "stem": (r"设椭圆 $C_1$ 的离心率为 $\frac{5}{13}$，焦点在 $x$ 轴上且长轴长为 $26$. "
                     r"若曲线 $C_2$ 上的点到椭圆 $C_1$ 的两个焦点的距离的差的绝对值等于 $8$，"
                     r"则曲线 $C_2$ 的标准方程为\paren[A]"),
            "answer": "A",
            "solution": (
                "椭圆 $C_1$ 的长轴长为 $26$，故 $a_1=13$；"
                "又 $e=\\dfrac{5}{13}$，故 $c=13\\times\\dfrac{5}{13}=5$，"
                "$b_1^{2}=169-25=144$.\n\n"
                "所以 $C_1$ 的焦点为 $F_1(-5,0)$，$F_2(5,0)$.\n\n"
                "曲线 $C_2$ 上的点到 $F_1$、$F_2$ 距离之差的绝对值为 $8$，"
                "故 $C_2$ 是以 $F_1$、$F_2$ 为焦点的双曲线，且\n"
                "\\[\n 2a_2=8\\Rightarrow a_2=4,\\qquad c=5"
                "\\Rightarrow b_2^{2}=25-16=9\n\\]\n"
                "所以 $C_2$ 的标准方程为\n"
                "\\[\n \\frac{x^{2}}{16}-\\frac{y^{2}}{9}=1"
                "\\quad\\text{即}\\quad \\frac{x^{2}}{4^{2}}-\\frac{y^{2}}{3^{2}}=1\n\\]\n"
                "故选 A."),
        },
    },
    {
        "key": "高考真题汇编/2009/四川卷（理）#11",
        "why": "选项 B 印错——`188` 应为 `288`",
        "src": "按题面（甲不站两端、女生中恰有两位相邻）计数为 288："
               "女生恰成两段共 $3\\times2\\times(5!-2\\times4!)=432$ 种，"
               "减去甲站两端的 $2\\times3\\times2\\times(4!-2\\times3!)=144$ 种，得 $432-144=288$；"
               "选项里只有 188 与它形似",
        "expect": {"type": "multi_choice", "stem": "男生甲不站两端",
                   "options": ["$188$"]},
        "set": {
            "type": "single_choice",
            "stem": (r"3位男生和3位女生共6位同学站成一排，若男生甲不站两端，"
                     r"3位女生中有且只有两位女生相邻，则不同排法的种数是\paren[B]"),
            "options": [["A", "$360$"], ["B", "$288$"], ["C", "$216$"], ["D", "$96$"]],
            "answer": "B",
            "solution": (
                "**先不管甲的限制.** 三位女生中恰有两位相邻，即三位女生恰好占两段.\n\n"
                "选出相邻的两位女生：$\\mathrm{C}_3^2=3$ 种，她们内部排列 $2!=2$ 种，"
                "余下一位女生单独成段. 把「两女段」「一女段」当成两个元素，"
                "与三位男生共 $5$ 个元素排列，有 $5!$ 种；"
                "但要扣掉两段女生挨在一起（三位女生连成一段）的情形，"
                "此时把两段并作一个元素，有 $2\\times4!$ 种.\n"
                "\\[\n 3\\times2\\times(5!-2\\times4!)=6\\times(120-48)=432\n\\]\n\n"
                "**再扣掉甲站两端的情形.** 甲站在某一端时，余下 2 位男生与 3 位女生"
                "排在另外 5 个位置上，同样要求三位女生恰占两段：\n"
                "\\[\n 3\\times2\\times(4!-2\\times3!)=6\\times(24-12)=72\n\\]\n"
                "两端共 $2\\times72=144$ 种.\n\n"
                "所以符合条件的排法有\n"
                "\\[\n 432-144=288\n\\]\n"
                "故选 B."),
        },
    },
    {
        "key": "高考真题汇编/2009/海南、宁夏新课标卷（理）#2",
        "why": "选项 D 漏了虚数单位——`2` 应为 `2i`",
        "src": "按题面计算：$\\frac{3+2\\mathrm{i}}{2-3\\mathrm{i}}=\\mathrm{i}$，"
               "$\\frac{3-2\\mathrm{i}}{2+3\\mathrm{i}}=-\\mathrm{i}$，两者之差为 $2\\mathrm{i}$；"
               "选项里已有 $-2\\mathrm{i}$，D 与它只差一个符号，正是被漏掉的那个",
        "expect": {"type": "multi_choice", "stem": "复数",
                   "options": ["$2$"]},
        "set": {
            "type": "single_choice",
            "stem": (r"复数 $\frac{3 + 2\mathrm{i}}{2 - 3\mathrm{i}} "
                     r"- \frac{3 - 2\mathrm{i}}{2 + 3\mathrm{i}} =$\paren[D]"),
            "options": [["A", "$0$"], ["B", "$2$"], ["C", "$-2\\mathrm{i}$"],
                        ["D", "$2\\mathrm{i}$"]],
            "answer": "D",
            "solution": (
                "先算第一项：\n"
                "\\[\n \\frac{3+2\\mathrm{i}}{2-3\\mathrm{i}}"
                "=\\frac{(3+2\\mathrm{i})(2+3\\mathrm{i})}{(2-3\\mathrm{i})(2+3\\mathrm{i})}"
                "=\\frac{6+9\\mathrm{i}+4\\mathrm{i}+6\\mathrm{i}^{2}}{4+9}"
                "=\\frac{13\\mathrm{i}}{13}=\\mathrm{i}\n\\]\n"
                "再算第二项：\n"
                "\\[\n \\frac{3-2\\mathrm{i}}{2+3\\mathrm{i}}"
                "=\\frac{(3-2\\mathrm{i})(2-3\\mathrm{i})}{(2+3\\mathrm{i})(2-3\\mathrm{i})}"
                "=\\frac{6-9\\mathrm{i}-4\\mathrm{i}+6\\mathrm{i}^{2}}{13}"
                "=\\frac{-13\\mathrm{i}}{13}=-\\mathrm{i}\n\\]\n"
                "所以原式 $=\\mathrm{i}-(-\\mathrm{i})=2\\mathrm{i}$. 故选 D."),
        },
    },
    # ── 2026-09-19 撤下一条 ──────────────────────────────────────────
    # 原账：`高考真题汇编/2010/天津卷（文）#3` —— 「配图和选项都是别人的，
    # 采用同一份天津卷**理科第 4 题**（`i=1, s=2`，判断 `i<6` 时输出 $s=-7$，
    # 答案 D）的题干、框图与选项」。
    # 为什么撤：库里**已经没有这个题号**（2010 天津（文）从 #2 直接跳到 #4，
    # 回收站里也查不到），`expect` 无从核对。而 `run()` 是「一条对不上就整批
    # 不执行」，留着它整张账都跑不动（新账会被它一起卡死）。题意与改法记在这儿备查。
    {
        "key": "高考真题汇编/1998/全国卷（文）#13",
        "why": "选项串到了上一题——本题被印成了 #12 的坐标值；原卷选项是四个根式值",
        "src": "原卷（1998 全国卷文 13）：A $4\\sqrt3$、B $2\\sqrt3$、C $2$、D $\\sqrt3$，官方答案 B；"
               "与按题面算得的 $R=2\\sqrt3$ 一致（球面距离为大圆周长的 $\\frac16$ ⇒ 球心角 $60^\\circ$ ⇒ "
               "三点构成边长 $R$ 的正三角形 ⇒ 小圆半径 $\\frac{R}{\\sqrt3}=2$ ⇒ $R=2\\sqrt3$）",
        "expect": {"type": "multi_choice", "stem": "这个球的半径为",
                   "options": [r"$\pm\frac{\sqrt{3}}{4}$"]},
        "set": {
            "type": "single_choice",
            "stem": (r"球面上有 $3$ 个点，其中任意两点的球面距离都等于大圆周长的 "
                     r"$\frac{1}{6}$，经过这 $3$ 个点的小圆的周长为 $4\pi$，"
                     r"那么这个球的半径为\paren[B]"),
            "options": [["A", r"$4\sqrt{3}$"], ["B", r"$2\sqrt{3}$"],
                        ["C", r"$2$"], ["D", r"$\sqrt{3}$"]],
            "answer": "B",
            "solution": (
                "设球的半径为 $R$. 球面距离等于大圆周长的 $\\dfrac16$，"
                "则两点所对的球心角为\n"
                "\\[\n \\frac{2\\pi}{6}=\\frac{\\pi}{3}\n\\]\n"
                "故任意两点间的弦长为 $2R\\sin\\dfrac{\\pi}{6}=R$，"
                "即这三点构成边长为 $R$ 的正三角形.\n\n"
                "该正三角形的外接圆就是题中所说的小圆，其半径\n"
                "\\[\n r=\\frac{R}{\\sqrt{3}}\n\\]\n"
                "由小圆周长 $4\\pi$ 得 $2\\pi r=4\\pi$，即 $r=2$，所以\n"
                "\\[\n \\frac{R}{\\sqrt{3}}=2\\;\\Longrightarrow\\;R=2\\sqrt{3}\n\\]\n"
                "故选 B."),
        },
    },
    {
        "key": "高考真题汇编/2003/粤桂卷#10",
        "why": "上一步只是把 C 改成了正确式，但原卷里正确式排在 **D**——按原卷顺序摆正",
        "src": "原卷（2003 广东卷 10）：A $-\\arcsin x$、B $-\\pi-\\arcsin x$、"
               "C $-\\pi+\\arcsin x$、D $\\pi-\\arcsin x$，官方答案 D",
        "expect": {"type": "single_choice", "stem": "的反函数",
                   "options": [r"$\pi - \arcsin x,\ x \in [-1,1]$"]},
        "set": {
            "options": [["A", r"$-\arcsin x,\ x \in [-1,1]$"],
                        ["B", r"$-\pi - \arcsin x,\ x \in [-1,1]$"],
                        ["C", r"$-\pi + \arcsin x,\ x \in [-1,1]$"],
                        ["D", r"$\pi - \arcsin x,\ x \in [-1,1]$"]],
            "answer": "D",
            "stem": (r"函数 $f(x) = \sin x$，$x \in \left[\frac{\pi}{2}, \frac{3\pi}{2}\right]$ "
                     r"的反函数 $f^{-1}(x) =$\paren[D]"),
        },
    },
    {
        "key": "高考真题汇编/2004/福建卷（文）#12",
        "why": "费用条件抄成了理科版——文科版**两项费用都是 a**，不是「a 与 2a」",
        "src": "原卷（2004 福建文 12）：题干作「从 M 到 B、C 两地修建公路的费用**都是** "
               "$a$ 万元/km」，官方答案 B $(2\\sqrt7-2)a$；"
               "按文科版复算：$f=a(|MB|+|MC|)=a(|MA|-2+|MC|)\\ge a(|AC|-2)$，"
               "取 $A(-2,0)$、$B(2,0)$ 得 $C(3,\\sqrt3)$，$|AC|=\\sqrt{25+3}=2\\sqrt7$，"
               "故最低为 $(2\\sqrt7-2)a$，**正好等于选项 B**"
               "（理科版才是 a 与 2a，答案 5a，参考 2004 福建理 12）",
        "expect": {"type": "multi_choice", "stem": "费用分别是",
                   "options": [r"$(2\sqrt{7} - 2)a\text{ 万元}$"]},
        "set": {
            "type": "single_choice",
            "stem": (r"如图，$B$ 地在 $A$ 地的正东方向 $4\mathrm{~km}$ 处，"
                     r"$C$ 地在 $B$ 地的北偏东 $30^{\circ}$ 方向 $2\mathrm{~km}$ 处，"
                     r"河流的某岸 $PQ$（曲线）上任意一点到 $A$ 的距离比到 $B$ 的距离远 "
                     r"$2\mathrm{~km}$. 现要在曲线 $PQ$ 上选一处 $M$ 建一座码头，"
                     r"向 $B$，$C$ 两地转运货物. 经测算，从 $M$ 到 $B$，$C$ 两地修建公路的费用"
                     r"都是 $a\text{ 万元}/\mathrm{km}$，"
                     r"那么修建这两条公路的总费用最低是\paren[B]"
                     "\n\n\\includegraphics[width=0.34\\linewidth]{7fc203e3cf557bb9.png}"),
            "answer": "B",
            "solution": (
                "取 $A(-2,0)$，$B(2,0)$（这样 $|AB|=4$ 且 $PQ$ 的方程最简），"
                "$x$ 轴正向为正东、$y$ 轴正向为正北.\n\n"
                "$C$ 在 $B$ 的北偏东 $30^{\\circ}$ 方向 $2\\mathrm{~km}$ 处，故\n"
                "\\[\n C=\\left(2+2\\sin30^{\\circ},\\;2\\cos30^{\\circ}\\right)"
                "=(3,\\sqrt{3})\n\\]\n\n"
                "$PQ$ 上任意一点 $M$ 满足 $|MA|-|MB|=2$，即 $|MB|=|MA|-2$. "
                "总费用为\n"
                "\\[\n f(M)=a|MB|+a|MC|=a\\left(|MA|+|MC|-2\\right)\n\\]\n"
                "由三角不等式 $|MA|+|MC|\\ge|AC|$，且等号在 $M$ 落在线段 $AC$ 上时成立，得\n"
                "\\[\n f(M)\\ge a\\left(|AC|-2\\right)\n\\]\n\n"
                "而\n"
                "\\[\n |AC|=\\sqrt{(3+2)^{2}+(\\sqrt{3})^{2}}=\\sqrt{28}=2\\sqrt{7}\n\\]\n"
                "所以最低费用为\n"
                "\\[\n a\\left(2\\sqrt{7}-2\\right)=(2\\sqrt{7}-2)a\\ \\text{万元}\n\\]\n"
                "（线段 $AC$ 上确实有一点满足 $|MA|-|MB|=2$：在 $A$ 处该差为 $-4$，"
                "在 $C$ 处为 $2\\sqrt7-2>2$，由连续性知中间必有一处等于 $2$.）\n\n"
                "故选 B."),
        },
    },

    {
        "key": "高考真题汇编/2007/重庆卷（文）#1",
        "why": "题干下标印错——`a_1 = 64` 应为 `a_5 = 64`",
        "src": "原卷（2007 重庆文 1）：`a_2=8，a_5=64，则公比 q 为`，选项 2/3/4/8，"
               "官方答案 A（$a_5=a_2q^3$ ⇒ $64=8q^3$ ⇒ $q=2$）；"
               "青夏教育题库正文逐字为 `a_2=8，a_5=64`、官方答案页图像第 1 题答案为 A。"
               "`a_1=64` 出自 2007 年前后一份 Word 转录本把下标 5 误录成 1，"
               "被大量网站转载（那些版本答案表仍写「(1) A」，自相矛盾）",
        "expect": {"type": "multi_choice", "stem": "$a_{1} = 64$"},
        "set": {
            "type": "single_choice",
            "stem": (r"在等比数列 $\{a_{n}\}$ 中，$a_{2} = 8$，$a_{5} = 64$，"
                     r"则公比 $q$ 为\paren[A]"),
            "answer": "A",
            "solution": (
                "等比数列中任意两项满足 $a_5=a_2q^{3}$，代入已知得\n"
                "\\[\n 64=8q^{3}\\;\\Longrightarrow\\;q^{3}=8"
                "\\;\\Longrightarrow\\;q=2\n\\]\n"
                "故选 A."),
        },
    },
    {
        "key": "高考真题汇编/2026/上海卷（秋）#13",
        "why": "四个选项的指数被提取坏了——`3/a²`、`4/a³` … 其实是 $a^{3/2}$、$a^{4/3}$ …",
        "src": "原卷扫描件（上海高考数学，第 1 页末题干、第 2 页顶选项）逐字读出："
               "A $a^{\\frac32}$、B $a^{\\frac43}$、C $a^{\\frac52}$、D $a^{\\frac53}$，"
               "答案 B；另有两份独立解析版同为 B。"
               "按题面 $a\\cdot a^{\\frac13}=a^{\\frac43}$，正是 B",
        "expect": {"type": "single_choice", "stem": "$a\\cdot \\sqrt[3]{a}=\\paren[B]",
                   "options": [r"$a^{\frac{4}{3}}$"]},
        "set": {
            "type": "single_choice",
            "stem": r"$a$ 是不为 $1$ 的任意实数，则 $a\cdot \sqrt[3]{a}$=\paren[B]",
            "options": [["A", r"$a^{\frac{3}{2}}$"], ["B", r"$a^{\frac{4}{3}}$"],
                        ["C", r"$a^{\frac{5}{2}}$"], ["D", r"$a^{\frac{5}{3}}$"]],
            "answer": "B",
            "solution": (
                "把根式写成指数：$\\sqrt[3]{a}=a^{\\frac13}$，所以\n"
                "\\[\n a\\cdot\\sqrt[3]{a}=a^{1}\\cdot a^{\\frac13}"
                "=a^{1+\\frac13}=a^{\\frac43}\n\\]\n"
                "故选 B."),
        },
    },
    {
        "key": '高考真题汇编/2009/广东卷（文）#1',
        "why": '题型标错——这是选择题（选项是四张韦恩图），被当成解答题',
        "src": '答案栏写着 B，题干问「韦恩图是（\\quad）」，是选择题；四个选项是图片，正文里没有文字选项卡',
        "expect": {'type': 'detailed_answer', 'stem': '韦恩（Venn）图是'},
        "set": {'type': 'single_choice', 'stem': '已知全集 $U = \\mathbb{R}$，则正确表示集合 $M = \\{-1, 0, 1\\}$ 和 $N = \\{x \\mid x^2 + x = 0\\}$ 关系的韦恩（Venn）图是\\paren[B]\n\n\\includegraphics[width=0.88\\linewidth]{d0721d9a3717831a.png}', 'options': [['A', ''], ['B', ''], ['C', ''], ['D', '']], 'meta': {'figure_missing': ['选项 A–D 的韦恩图（原卷为图片，未提取）']}},
    },
    {
        "key": '高考真题汇编/2006/上海卷（春）#13',
        "why": '题型标错——这是选择题，被当成解答题；选项还留在题干里',
        "src": '选择题，答案 B；选项卡在题干里的 `\\begin{enumerate}` 中，解析器没拆出来，于是被当成解答题',
        "expect": {'type': 'detailed_answer', 'stem': '\\begin{enumerate}'},
        "set": {'type': 'single_choice', 'stem': '抛物线 $y^2=4x$ 的焦点坐标为\\paren[B]', 'options': [['A', '$(0,1)$'], ['B', '$(1,0)$'], ['C', '$(0,2)$'], ['D', '$(2,0)$']]},
    },
    {
        "key": '高考真题汇编/2006/上海卷（春）#14',
        "why": '题型标错——这是选择题，被当成解答题；选项还留在题干里',
        "src": '选择题，答案 C；选项卡在题干里的 `\\begin{enumerate}` 中，解析器没拆出来，于是被当成解答题',
        "expect": {'type': 'detailed_answer', 'stem': '\\begin{enumerate}'},
        "set": {'type': 'single_choice', 'stem': '若 $a$，$b$，$c\\in\\mathbb{R}$，$a>b$，则下列不等式成立的是\\paren[C]', 'options': [['A', '$\\frac{1}{a}<\\frac{1}{b}$'], ['B', '$a^2>b^2$'], ['C', '$\\frac{a}{c^2+1}>\\frac{b}{c^2+1}$'], ['D', '$a|c|>b|c|$']]},
    },
    {
        "key": '高考真题汇编/2006/上海卷（春）#15',
        "why": '题型标错——这是选择题，被当成解答题；选项还留在题干里',
        "src": '选择题，答案 A；选项卡在题干里的 `\\begin{enumerate}` 中，解析器没拆出来，于是被当成解答题',
        "expect": {'type': 'detailed_answer', 'stem': '\\begin{enumerate}'},
        "set": {'type': 'single_choice', 'stem': '若 $k\\in\\mathbb{R}$，则“$k>3$”是“方程 $\\frac{x^2}{k-3}-\\frac{y^2}{k+3}=1$ 表示双曲线”的\\paren[A]', 'options': [['A', '充分不必要条件'], ['B', '必要不充分条件'], ['C', '充要条件'], ['D', '既不充分也不必要条件']]},
    },
    {
        "key": '高考真题汇编/2006/上海卷（春）#16',
        "why": '题型标错——这是选择题，被当成解答题；选项还留在题干里',
        "src": '选择题，答案 B；选项卡在题干里的 `\\begin{enumerate}` 中，解析器没拆出来，于是被当成解答题',
        "expect": {'type': 'detailed_answer', 'stem': '\\begin{enumerate}'},
        "set": {'type': 'single_choice', 'stem': '若集合 $A=\\left\\{y\\mid y=x^{\\frac{1}{3}},-1\\leqslant x\\leqslant 1\\right\\}$，$B=\\left\\{y\\mid y=2-\\frac{1}{x},0<x\\leqslant 1\\right\\}$，则 $A\\cap B$ 等于\\paren[B]', 'options': [['A', '$(-\\infty,1]$'], ['B', '$[-1,1]$'], ['C', '$\\emptyset$'], ['D', '$\\{1\\}$']]},
    },
    {
        "key": '高考真题汇编/2023/全国乙卷（理）#16',
        "why": '题型标错——这是填空题，被当成解答题',
        "src": '答案是一个取值范围 $\\frac{\\sqrt5-1}{2}<a<1$，不是选项字母；2023 全国乙卷（理）第 16 题本就是填空题',
        "expect": {'type': 'detailed_answer', 'stem': '的取值范围是'},
        "set": {'type': 'fill_in_blank', 'stem': '设 $a\\in(0,1)$，若函数 $f(x)=a^x+(1+a)^{x+1}$ 在 $(0,+\\infty)$ 上单调递增，则 $a$ 的取值范围是\\fillin[$\\frac{\\sqrt5-1}{2}<a<1$]', 'answer': '$\\frac{\\sqrt5-1}{2}<a<1$'},
    },
    {
        "key": '2026 高考数学全国模拟精选_images/024#4',
        "why": '题型标错：解答结论是 ABC（多选），库里标成了单选',
        "src": '批文件《第04批_难题_100道.md》的解答结论：ABC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2026 高考数学全国模拟精选_images/026#11',
        "why": '题型标错：解答结论是 ABC（多选），库里标成了单选',
        "src": '批文件《第04批_难题_100道.md》的解答结论：ABC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2026 高考数学全国模拟精选_images/031#24',
        "why": '题型标错：解答结论是 ACD（多选），库里标成了单选',
        "src": '批文件《第04批_难题_100道.md》的解答结论：ACD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2026 高考数学全国模拟精选_images/122#25',
        "why": '题型标错：解答结论是 ACD（多选），库里标成了单选',
        "src": '批文件《第04批_难题_100道.md》的解答结论：ACD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/015#11',
        "why": '题型标错：解答结论是 ABD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：ABD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/020#10',
        "why": '题型标错：解答结论是 ACD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：ACD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/025#9',
        "why": '题型标错：解答结论是 AD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：AD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/030#10',
        "why": '题型标错：解答结论是 AC（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：AC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/036#10',
        "why": '题型标错：解答结论是 AC（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：AC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/036#11',
        "why": '题型标错：解答结论是 AC（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：AC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/042#11',
        "why": '题型标错：解答结论是 BCD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：BCD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/059#10',
        "why": '题型标错：解答结论是 ABD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：ABD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/059#11',
        "why": '题型标错：解答结论是 BCD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：BCD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/063#10',
        "why": '题型标错：解答结论是 AC（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：AC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027 高考数学考前模拟十二套卷_images/063#11',
        "why": '题型标错：解答结论是 ACD（多选），库里标成了单选',
        "src": '批文件《第05批_难题_100道.md》的解答结论：ACD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027千题册创新拔高册（下）_images/161#20',
        "why": '题型标错：解答结论是 ABC（多选），库里标成了单选',
        "src": '批文件《第08批_难题_100道.md》的解答结论：ABC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '2027千题册经典重点册（上）_images/054#118',
        "why": '题型标错：解答结论是 ABC（多选），库里标成了单选',
        "src": '批文件《第09批_难题_100道.md》的解答结论：ABC',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '手工录入/001#12',
        "why": '题型标错：解答结论是 ACD（多选），库里标成了单选',
        "src": '批文件《第13批_难题_100道.md》的解答结论：ACD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": '手工录入/001#25',
        "why": '题型标错：解答结论是 ACD（多选），库里标成了单选',
        "src": '批文件《第13批_难题_100道.md》的解答结论：ACD',
        "expect": {'type': 'single_choice'},
        "set": {'type': 'multi_choice'},
    },
    {
        "key": "模拟题/浙江A9协作体2027届高三上学期暑假返校学情诊断#10",
        "why": "题干残缺（四个选项被挤进解析正文）且作答括号写成 `\\paren[$BCD$]`；答案 BCD 逐条验算：A 错（应 x²=4y）、B/C/D 均对",
        "src": "由原解析正文还原选项；抛物线的焦半径与弦长公式逐条复核",
        "expect": {"type": "multi_choice"},
        "set": {"stem": '已知抛物线 $C: x^{2}=2py$（$p>0$），其焦点 $F$ 到准线的距离为 $2$，且 $B$ 为 $C$ 上的动点，则\\paren[BCD]', "answer": "BCD",
                 "options": [('A', '$C$ 的方程为 $y=4x^{2}$'), ('B', '已知点 $A(2,3)$，则 $|BA|+|BF|$ 的最小值为 $4$'), ('C', '直线 $y=kx+1$ 被抛物线截得的弦长最小值为 $4$'), ('D', '若抛物线准线与 $y$ 轴交于点 $N$，设 $BN$ 斜率为 $k$，则 $|k|$ 的最小值是 $1$')]},
    },
]


# ── 2026-09-19：录题时把**多选题**记成了单选（26 道） ────────────────────
#
# 判据（**逐题看过**，不是按规则批改）：
#   · 题干是「（多）说法正确的有（ ）」这种**一问多项**的问法；
#   · 四个选项是**互相独立**的命题，不是同一个量的四个取值；
#   · 求解模型逐项判定（A 错、B 对、C 对、D 错）后给出**多字母答案**，
#     而库里的 `single_choice` 只收一个字母，`collect` 于是整批拦下。
#
# ⚠ **故意没收进来**的：`2027千题册创新拔高册（上）_images/303#11`——
#   它是真单选（问「最小值与最大值之和为」），是模型的答案串了题
#   （答案写成 `$-2<x<1$`、解析讲的是另一道奇函数题），改题型就改反了。
_MULTI_AS_SINGLE: list[tuple[str, str, str]] = [
    (r"2026 高考数学全国模拟精选_images/005#5", r"在正三棱柱", "ACD"),
    (r"2026 高考数学全国模拟精选_images/006#6", r"满足当", "AD"),
    (r"2026 高考数学全国模拟精选_images/015#20", r"公差", "ACD"),
    (r"2026 高考数学全国模拟精选_images/015#21", r"的前 $n$ 项和", "AC"),
    (r"2026 高考数学全国模拟精选_images/025#9", r"命题正确的是", "BC"),
    (r"2026 高考数学全国模拟精选_images/046#6", r"\ln(\cos x)", "ABD"),
    (r"2026 高考数学全国模拟精选_images/048#10", r"\frac{1}{n},", "ACD"),
    (r"2026 高考数学全国模拟精选_images/051#18", r"所有棱长均为 2", "BCD"),
    (r"2026 高考数学全国模拟精选_images/054#25", r"项积为", "AD"),
    (r"2026 高考数学全国模拟精选_images/055#28", r"三角形的面积为 2", "ABCD"),
    (r"2026 高考数学全国模拟精选_images/078#24", r"连续投掷", "ABD"),
    (r"2026 高考数学全国模拟精选_images/114#8", r"2py", "ACD"),
    (r"2026 高考数学全国模拟精选_images/115#10", r"光学性质", "ABC"),
    (r"2026 高考数学全国模拟精选_images/115#9", r"的一条直径", "ABD"),
    (r"2026 高考数学全国模拟精选_images/116#11", r"x^2 = 4y", "ACD"),
    (r"2026 高考数学全国模拟精选_images/116#12", r"点 $Q$ 在圆", "ABD"),
    (r"2026 高考数学全国模拟精选_images/122#24", r"2026)", "ACD"),
    (r"2026 高考数学全国模拟精选_images/124#28", r"ma_n^2", "ACD"),
    (r"2027 高考数学考前模拟十二套卷_images/025#10", r"为母线的圆柱", "BC"),
    (r"2027 高考数学考前模拟十二套卷_images/030#9", r"Cobb", "ABD"),
    (r"2027 高考数学考前模拟十二套卷_images/036#9", r"a\sin x", "AC"),
    (r"2027 高考数学考前模拟十二套卷_images/042#10", r"点 $A(1,3)$", "BCD"),
    (r"2027 高考数学考前模拟十二套卷_images/042#9", r"文创大赛", "BD"),
    (r"2027 高考数学考前模拟十二套卷_images/048#10", r"上的点", "AB"),
    (r"2027 高考数学考前模拟十二套卷_images/048#11", r"已知正方体", "AC"),
    (r"2027千题册经典重点册（下）_images/289#123", r"两个箱子", "BC"),
]

PATCHES += [
    {
        "key": key,
        "why": "录题时把多选题记成了单选——题干是「…正确的有（ ）」，四个选项互相独立",
        "src": ("题干自洽：四个选项各是一个独立命题，不是同一量的四个取值；"
                "求解模型逐项解析后给出多字母答案 %s。库里 `single_choice` 只收一个字母，"
                "`collect` 因此拦下——**逐题人工看过**，不是按规则批量改" % ans),
        "expect": {"type": "single_choice", "stem": frag},
        "set": {"type": "multi_choice"},
    }
    for key, frag, ans in _MULTI_AS_SINGLE
]


# ── 2026-09-19：这四道是**求解模型自己判出「单选标错」**的 ────────────────
#
# 它们的答案栏被写成「题面有误」，其实题干是「…正确的是（ ）」+ 四个独立命题，
# 模型逐项算完发现**不止一个正确项**，而题干标的是单选，于是拒绝作答。
# 下面每个选项我都**重新算了一遍**，结论与模型一致：
#   · `054#10` 长方体：B、D 对（A 错在 $a=b=1$ 就是正方体；C 算得 $\frac29$）
#   · `054#9`  数列：A、B、D 对（C 数出来是 3 个 $n$，不是 5 个）
#   · `058#9`  集合：A、C 对（$B\subseteq C$、$A\subseteq B$ 都不必然）
#   · `手工录入/001#11` 数据：B、C 对（众数是 3、中位数是 4）
PATCHES += [
    {
        "key": "2027 高考数学考前模拟十二套卷_images/054#10",
        "why": "录题时把多选题记成了单选——逐项检验后 B、D 两个正确项",
        "src": "题面自洽 + 逐项重算：$ab+a+b=3$；B 由 $ab+a+b\\ge ab+2\\sqrt{ab}$ 得 $ab\\le1$；"
               "D 由 $a^2+b^2=s^2-2(3-s)$ 在 $s=2$ 取最小得 $S=3\\pi$；"
               "A 错（$a=b=1$ 即正方体）、C 错（体积 $\\frac29$）。两个正确项 ⇒ 多选",
        "expect": {"type": "single_choice", "stem": "长方体"},
        "set": {"type": "multi_choice"},
    },
    {
        "key": "2027 高考数学考前模拟十二套卷_images/054#9",
        "why": "录题时把多选题记成了单选——逐项检验后 A、B、D 三个正确项",
        "src": "题面自洽 + 逐项重算：$a_n=\\frac{9}{2n-9}$；A 有最小项 $a_4=-9$、最大项 $a_5=9$；"
               "B 由 $2n-9\\mid 9$ 得 $n=3,4,5,6,9$ 共 5 项；D 前四项单调减、$S_5$ 起回升故 $n=4$；"
               "C 只有 $n=1,2,4$ 三个（不是 5 个）",
        "expect": {"type": "single_choice", "stem": "2n-9"},
        "set": {"type": "multi_choice"},
    },
    {
        "key": "2027 高考数学考前模拟十二套卷_images/058#9",
        "why": "录题时把多选题记成了单选——逐项检验后 A、C 两个正确项",
        "src": "题面自洽 + 逐项重算：由 $A\\cap B=B\\cup C$ 得 $B\\cup C=A\\cap B\\subseteq B$，故 $C\\subseteq B$（A）；"
               "又 $B\\subseteq B\\cup C\\subseteq A$，故 $B\\subseteq A$（C）；B、D 都不必然",
        "expect": {"type": "single_choice", "stem": "若集合"},
        "set": {"type": "multi_choice"},
    },
    {
        "key": "手工录入/001#11",
        "why": "录题时把多选题记成了单选——逐项检验后 B、C 两个正确项",
        "src": "题面自洽 + 逐项重算：数据 $3,3,3,3,4,4,4,5,5,6$；众数是 3（A 错）、平均数 4（B 对）、"
               "极差 3（C 对）、中位数 4（D 错）",
        "expect": {"type": "single_choice", "stem": "个数据为"},
        "set": {"type": "multi_choice"},
    },
    {
        "key": "2027 高考数学考前模拟十二套卷_images/020#9",
        "why": "录题时把多选题记成了单选——逐项检验后 A、C、D 三个正确项",
        "src": "题面自洽 + 逐项重算：$\\bar y=3\\bar x+2=14\\Rightarrow\\bar x=4$（A 对）；"
               "$s_y^2=9\\neq3$（B 错）；合并平均数 $\\frac{4+14}{2}=9$（C 对）；"
               "合并方差 $5+\\frac{100}{4}=30$（D 对）。三个正确项 ⇒ 多选",
        "expect": {"type": "single_choice", "stem": "已知第一组样本数据"},
        "set": {"type": "multi_choice"},
    },
    {
        "key": "2027 高考数学考前模拟十二套卷_images/025#11",
        "why": "录题时把多选题记成了单选——逐项检验后 A、C、D 三个正确项",
        "src": "题面自洽 + 逐项重算：圆心 $(a,\\ln a)$ 半径 1；A 由 $|\\ln a|=1$（2 个）与 $a=1$ 得 3 个；"
               "B 需 $(\\ln a)^2=a^2$，只有 $\\ln a=-a$ 一解，故不是 2 个；"
               "C 需 $a^2+(\\ln a)^2=1$，$a=1$ 与 $(0.3,0.5)$ 内一解共 2 个；"
               "D 需 $\\ln a=\\frac{a}{e}$，$f(a)=\\ln a-\\frac{a}{e}$ 在 $a=e$ 取最大值 0，唯一解。三个正确项 ⇒ 多选",
        "expect": {"type": "single_choice", "stem": "圆 $C: (x-a)^2 + (y - \\ln a)^2 = 1$"},
        "set": {"type": "multi_choice"},
    },
]


# ── 2026-09-19：**题号漂移**导致答案写错（千题册（上）303–305 这四道） ──
#
# 怎么发现的：中档题回收时，`303#11` 的答案 `$-2<x<1$`（填空题的解）被单选题
# 的校验拦下。顺着查下去，发现**批文件里的题号与库里的题号错开了**：
#
#   批文件（导出时的库）        现在库里的同号题          批里那道题真正的家
#   303#10 f(x)+f(x-1/2)>1     303#10 奇函数 f(2-x²)     库 302#9（答案已对）
#   303#11 奇函数 f(2-x²)      303#11 曼哈顿距离          库里无答案
#   304#14 曼哈顿距离          304#14 2a²-b²=1           答案被写成了曼哈顿的 B
#   305#16 2a²-b²=1            305#16 不等式整数解个数     答案被写成了前一道的 C
#
# 根因：回收**只认 `题号：` 那一行**（`exchange.collect` 用 key 对上号），
# 一旦两道题之间插/删过题，号就整体错位，解析会**悄悄写到别人头上**。
# 所以这里按**题干**重新认领：每道题的答案都是重新算过的，不是照抄批文件。
# 全库 2175 条比过一遍，错位只有这一段（其余都对得上）。
PATCHES += [
    {
        "key": "2027千题册创新拔高册（上）_images/303#10",
        "why": "答案/解析是上一道题（$f(x)+f(x-\\frac12)>1$）的——题号漂移写串了",
        "src": "题干自洽：$g$ 为奇函数、$f(x)=\\begin{cases}x^3 & x\\le0\\\\ g(x) & x>0\\end{cases}$，"
               "$f$ 在 $\\mathbb{R}$ 上严格递增，故 $f(2-x^2)>f(x)\\iff 2-x^2>x\\iff -2<x<1$；"
               "批文件里同一题干（题号写成 303#11）给的也是这个答案，两处一致",
        "expect": {"stem": "f(2-x^2)>f(x)"},
        "set": {
            "stem": ("已知 $g(x)$ 是 $R$ 上的奇函数，当 $x<0$ 时，$g(x)=-\\ln(1-x)$，"
                     "函数 $f(x)=\\begin{cases} x^3 & x \\leqslant 0 \\\\ g(x) & x > 0 \\end{cases}$，"
                     "若 $f(2-x^2)>f(x)$，则实数 $x$ 的取值范围是\\fillin[$-2<x<1$]。"),
            "answer": "$-2<x<1$",
            "solution": (
                "$g(x)$ 为奇函数。当 $x>0$ 时 $-x<0$，故\n"
                "\\[\n g(x)=-g(-x)=-[-\\ln(1+x)]=\\ln(1+x)\n\\]\n"
                "且 $g(0)=0$，于是\n"
                "\\[\n f(x)=\\begin{cases} x^3, & x \\leqslant 0 \\\\ \\ln(1+x), & x>0 \\end{cases}\n\\]\n"
                "在 $(-\\infty,0]$ 上 $f'(x)=3x^2\\geqslant 0$，在 $(0,+\\infty)$ 上 "
                "$f'(x)=\\dfrac{1}{1+x}>0$，又 $\\lim\\limits_{x\\to 0^+}f(x)=0=f(0)$，"
                "故 $f(x)$ 在 $\\mathbb{R}$ 上严格递增。\n\n"
                "由单调性，\n"
                "\\[\n f(2-x^2)>f(x)\\iff 2-x^2>x\\iff x^2+x-2<0\\iff (x+2)(x-1)<0\n\\]\n"
                "解得 $-2<x<1$。"),
        },
    },
    {
        "key": "2027千题册创新拔高册（上）_images/303#11",
        "why": "这道（曼哈顿距离）从来没被作答——批文件把它的题号写成了 304#14",
        "src": "题干自洽 + 逐项重算：令 $u=a-2,\\ v=b$，则 $|u|+|v|=2$，"
               "所求 $a^2+b^2-4a=u^2+v^2-4$；$|u|+|v|=2$ 上 $u^2+v^2\\in[2,4]$，"
               "故原式 $\\in[-2,0]$，最小值与最大值之和 $-2+0=-2$，选 B",
        "expect": {"stem": "曼哈顿距离", "answer": ""},
        "set": {
            "stem": ("在平面直角坐标系 $xOy$ 中，定义 $A(x_1, y_1)$，$B(x_2, y_2)$ 两点间的折线距离 "
                     "$d(A,B)=|x_1-x_2|+|y_1-y_2|$，该距离也称曼哈顿距离。已知点 $M(2,0), N(a,b)$，"
                     "若 $d(M,N)=2$，则 $a^2+b^2-4a$ 的最小值与最大值之和为\\paren[B]"),
            "answer": "B",
            "solution": (
                "令 $u=a-2$，$v=b$，则 $d(M,N)=|u|+|v|=2$，而\n"
                "\\[\n a^2+b^2-4a=(a-2)^2+b^2-4=u^2+v^2-4.\n\\]\n"
                "在 $|u|+|v|=2$ 上，$u^2+v^2$ 的最小值在 $u=v=\\pm 1$ 时取到 $2$，"
                "最大值在 $(u,v)=(\\pm 2,0)$ 或 $(0,\\pm 2)$ 时取到 $4$，"
                "故 $u^2+v^2\\in[2,4]$，原式的取值范围是 $[-2,0]$。\n\n"
                "所以最小值与最大值之和为 $-2+0=-2$。故选 B。"),
        },
    },
    {
        "key": "2027千题册创新拔高册（上）_images/304#14",
        "why": "答案被写成了上一道（曼哈顿距离）的 B——题号漂移；本题应为 C",
        "src": "题干自洽 + 重算：设 $k=2a-b$，则 $b=2a-k$，代入得 "
               "$2a^2-4ak+k^2+1=0$，关于 $a$ 有实根故 $\\Delta=8k^2-8\\geqslant 0$，"
               "即 $|k|\\geqslant 1$；$k=1$ 时 $a=b=1$ 满足条件，故最小值为 $1$，选 C",
        "expect": {"stem": "2a^2 - b^2 = 1"},
        "set": {
            "stem": "已知实数 $a$，$b$ 满足 $2a^2 - b^2 = 1$，则 $|2a-b|$ 的最小值为\\paren[C]",
            "answer": "C",
            "solution": (
                "设 $2a-b=k$，则 $b=2a-k$，代入 $2a^2-b^2=1$ 得\n"
                "\\[\n 2a^2-(2a-k)^2=1\\iff 2a^2-4ak+k^2+1=0.\n\\]\n"
                "关于 $a$ 的一元二次方程有实根，故\n"
                "\\[\n \\Delta=(4k)^2-4\\cdot 2\\cdot(k^2+1)=8k^2-8\\geqslant 0,\n\\]\n"
                "即 $k^2\\geqslant 1$，所以 $|2a-b|=|k|\\geqslant 1$。\n\n"
                "当 $k=1$ 时取 $a=1$，$b=1$，满足 $2a^2-b^2=1$，故最小值为 $1$。故选 C。"),
        },
    },
    {
        "key": "2027千题册创新拔高册（上）_images/305#16",
        "why": "答案被写成了上一道（$2a^2-b^2=1$）的 C——题号漂移；本题应为 D，题干中间的"
               "连接号也被录成了减号",
        "src": "题干自洽 + 重算：零点为 $1^2,2^2,\\cdots,100^2$，首项系数为正、次数为偶数，"
               "不等式成立区间为 $[1^2,2^2],[3^2,4^2],\\cdots,[99^2,100^2]$，"
               "第 $k$（奇）段含整数 $2k+2$ 个，合计 $2(1+3+\\cdots+99)+100=5100$，选 D",
        "expect": {"stem": "(x-100^2)", "answer": "C"},
        "set": {
            "stem": ("满足不等式 $(x-1^2)(x-2^2)(x-3^2)\\cdots(x-100^2) \\leqslant 0$ "
                     "整数解个数为\\paren[D]"),
            "answer": "D",
            "solution": (
                "不等式左边是 $100$ 个因式之积，零点依次为 $1^2,2^2,3^2,\\cdots,100^2$。"
                "首项系数为正、次数为偶数，故 $x>100^2$ 时左边为正，符号在相邻零点之间交替，"
                "于是不等式成立的区间为\n"
                "\\[\n [1^2,2^2],\\ [3^2,4^2],\\ [5^2,6^2],\\ \\cdots,\\ [99^2,100^2].\n\\]\n"
                "区间 $[k^2,(k+1)^2]$（$k$ 为奇数）内的整数个数为 $(k+1)^2-k^2+1=2k+2$。\n\n"
                "所以总个数为\n"
                "\\[\n \\sum_{k=1,3,5,\\cdots,99}(2k+2)=2(1+3+\\cdots+99)+2\\times 50"
                "=2\\times 2500+100=5100.\n\\]\n"
                "故选 D。"),
        },
    },
]


# ── 2026-09-19：**图题**没作答，但库里就有它的孪生题（原卷是真题选集） ──────
#
# 千题册/十二套卷其实是**真题选集**（书上每题都印着来源，如「2020新课标三」），
# 所以这些「缺图 / 题干被截断」的题，往往在 `高考真题汇编` 或别的模拟册里
# **有同一道题的完整版本**。做法：拿题干去全库比（相似度 > 0.9 才算），
# 逐条核对题干与选项逐字一致后，用孪生题的官方答案与解析。
# 这样比"我照着图重新算"可靠——原卷答案就是权威。
PATCHES += [
    {
        "key": "2024全国优质模拟题精选/全国优质模拟题精选四月班（四）#18",
        "why": "题干漏了「$k\\geqslant 2$」这个限制——漏了它四个选项都不对",
        "src": "孪生题 `2027千题册创新拔高册（下）_images/167#32`（同一道题，答案 D）的定义里带 $k\\geqslant 2$；"
               "按 $k\\geqslant 2$ 算：4 元集的划分为 $S(4,2)+S(4,3)+S(4,4)=7+6+1=14$，与选项 D 一致。"
               "库里现在没有这个限制，按 15 算则四个选项都不对——正是当初被判「题面有误」的原因",
        "expect": {"stem": "构成集合 U 的一个 k 划分"},
        "set": {
            "stem": ("如果集合 U 存在一组两两不交（两个集合交集为空集时，称为不交）的非空子集 "
                     "$A_1,A_2,\\cdots,A_k\\,(k\\in\\mathbb{N}^{*}, k\\geqslant 2)$，且满足 "
                     "$A_1\\cup A_2\\cup\\cdots\\cup A_k=U$，那么称子集组 $A_1,A_2,\\cdots,A_k$ "
                     "构成集合 U 的一个 k 划分。若集合 I 中含有 4 个元素，则集合 I 的所有划分的个数为\\paren[D]"),
            "answer": "D",
            "solution": ("集合 $I$ 有 $4$ 个元素，其划分个数按块数 $k\\geqslant 2$ 分类：\n"
                         "\\[\n S(4,2)=7,\\qquad S(4,3)=6,\\qquad S(4,4)=1\n\\]\n"
                         "总数为 $7+6+1=14$（定义要求 $k\\geqslant 2$，不含 $k=1$ 的平凡划分）。故选 D。"),
        },
    },
    {
        "key": "2027千题册经典重点册（上）_images/038#76",
        "why": "图题一直没作答——库里就有它的孪生题（2022 全国乙卷（文）#8）",
        "src": "孪生题 `高考真题汇编/2022/全国乙卷（文）#8`：题干与四个选项逐字相同，官方答案 A；"
               "解析用排除法：$f(1)=0$ 排除 B；$x\\in(0,\\frac{\\pi}{2})$ 时 $\\frac{2x\\cos x}{x^2+1}<1$ 排除 C；"
               "$g(3)=\\frac{2\\sin 3}{10}>0$ 排除 D",
        "expect": {"stem": "四个函数中的某个函数在区间"},
        "set": {
            "stem": ("如图是下列四个函数中的某个函数在区间 $[-3,3]$ 的大致图像，则该函数是\\paren[A]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{b7124aa7bf01623d.png}"),
            "answer": "A",
            "solution": ("设 $f(x)=\\dfrac{x^3-x}{x^2+1}$，则 $f(1)=0$，故排除 B。\n\n"
                         "设 $h(x)=\\dfrac{2x\\cos x}{x^2+1}$，当 $x\\in\\left(0,\\dfrac{\\pi}{2}\\right)$ 时 "
                         "$0<\\cos x<1$，所以 $h(x)<\\dfrac{2x}{x^2+1}\\leqslant 1$，故排除 C。\n\n"
                         "设 $g(x)=\\dfrac{2\\sin x}{x^2+1}$，则 $g(3)=\\dfrac{2\\sin 3}{10}>0$，故排除 D。故选 A。"),
        },
    },
    {
        "key": "2027千题册经典重点册（上）_images/080#26",
        "why": "图题一直没作答——库里就有它的孪生题（2015 安徽卷（文）#10）",
        "src": "孪生题 `高考真题汇编/2015/安徽卷（文）#10`：题干逐字相同、选项 A/B/D 逐字相同，官方答案 A；"
               "（孪生题的选项 C 是 $c>0$、库里是 $c<0$，两版有一处转录差异，但正确答案 A 不受影响）",
        "expect": {"stem": "则下列结论成立的是"},
        "set": {
            "stem": ("函数 $f(x) = ax^3 + bx^2 + cx + d$ 的图象如图所示，则下列结论成立的是\\paren[A]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{78df1fb322594332.png}"),
            "answer": "A",
            "solution": ("由图象右端向上，知三次项系数 $a>0$。设两个极值点的横坐标为 $x_1$、$x_2$，"
                         "由图可知 $0<x_1<x_2$。因为\n"
                         "\\[\n f'(x)=3ax^2+2bx+c\n\\]\n"
                         "且 $x_1$，$x_2$ 是 $f'(x)=0$ 的两个根，所以 $x_1+x_2=-\\dfrac{2b}{3a}>0$，"
                         "结合 $a>0$ 得 $b<0$。图象在 $x=0$ 处递增，所以 $c=f'(0)>0$；"
                         "又图象与 $y$ 轴的交点在 $x$ 轴上方，所以 $d=f(0)>0$。故选 A。"),
        },
    },
    {
        "key": "2027千题册经典重点册（上）_images/086#40",
        "why": "四个选项都是图片、录成了空的——从孪生题（2017 浙江卷#7）补齐选项与答案",
        "src": "孪生题 `高考真题汇编/2017/浙江卷#7`：题干逐字相同、四个选项就是同一组图"
               "（$3c16bc5f$、$e8d0bdb5$、$c3399df3$、$ebd5cbca$，四张图库里都在），官方答案 D；"
               "由 $f'(x)$ 符号「负、正、负、正」得 $f(x)$ 减、增、减、增，两个极小值点、一个极大值点",
        "expect": {"stem": "导函数 $y = f'(x)$ 的图象如图所示"},
        "set": {
            "stem": ("函数 $y = f(x)$ 的导函数 $y = f'(x)$ 的图象如图所示，则函数 $y = f(x)$ 的图象可能是\\paren[D]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{87066443926b5879.png}"),
            "options": [["A", "$\\includegraphics[width=0.15\\paperwidth]{3c16bc5f4f8b9b5e.png}$"],
                        ["B", "$\\includegraphics[width=0.15\\paperwidth]{e8d0bdb500e8fefc.png}$"],
                        ["C", "$\\includegraphics[width=0.15\\paperwidth]{c3399df3288ea0cd.png}$"],
                        ["D", "$\\includegraphics[width=0.15\\paperwidth]{ebd5cbca4a28c00e.png}$"]],
            "answer": "D",
            "solution": ("由导函数图象可知，$f'(x)$ 的符号依次为负、正、负、正，因此 $f(x)$ 依次递减、递增、递减、递增，"
                         "故 $f(x)$ 有两个极小值点和一个极大值点，且中间的极大值点位于 $y$ 轴右侧。"
                         "四个选项中只有 D 的图象具有上述单调性与极大值点位置，故选 D。"),
        },
    },
    {
        "key": "2027千题册经典重点册（下）_images/236#7",
        "why": "题干把 A、B 两个选项的文字串了进去、选项也重复了——从孪生题（2021 全国甲卷（文）#2）还原",
        "src": "孪生题 `高考真题汇编/2021/全国甲卷（文）#2`：题干与四个选项逐字相同（直方图也是同一张，"
               "`b217550cfa0dd597.png`），官方答案 C（本题问的是「不正确的是」）",
        "expect": {"stem": "下面结论中不正确的是"},
        "set": {
            "stem": ("为了解某地农村经济情况，对该地农户家庭年收入进行抽样调查，将农户家庭年收入的调查数据"
                     "整理得到如下频率分布直方图：\n\n"
                     "\\includegraphics[width=0.90\\linewidth]{b217550cfa0dd597.png}\n\n"
                     "根据此频率分布直方图，下面结论中不正确的是\\paren[C]"),
            "options": [["A", "该地农户家庭年收入低于 $4.5$ 万元的农户比率估计为 $6\\%$"],
                        ["B", "该地农户家庭年收入不低于 $10.5$ 万元的农户比率估计为 $10\\%$"],
                        ["C", "估计该地农户家庭年收入的平均值不超过 $6.5$ 万元"],
                        ["D", "估计该地有一半以上的农户，其家庭年收入介于 $4.5$ 万元至 $8.5$ 万元之间"]],
            "answer": "C",
        },
    },
    {
        "key": "2027千题册创新拔高册（下）_images/196#50",
        "why": "条件抄漏了一个竖线（$P(\\overline{A}B)$ 应为 $P(\\overline{A}|B)$），漏了就变成条件不足",
        "src": "孪生题 `2025全国优质模拟题精选_images/080#19`（同一道，答案 B）：条件是 $P(\\overline{A}|B)=P(B|A)$。"
               "由它推 $\\frac{P(B)-P(AB)}{P(B)}=\\frac{P(AB)}{P(A)}$ 得 $P(AB)=\\frac{P(A)P(B)}{P(A)+P(B)}$，"
               "于是 $P(\\overline{B}|A)=\\frac{P(A)}{P(A)+P(B)}=P(A|B)$，B 成立",
        "expect": {"stem": "$P(\\overline{A}B) = P(B|A)$"},
        "set": {
            "stem": ("设事件 $A, B$ 为两个随机事件，$P(A) \\neq 0, P(B) \\neq 0$，且 "
                     "$P(\\overline{A}|B) = P(B|A)$，则\\paren[B]"),
            "answer": "B",
            "solution": ("由条件得\n"
                         "\\[\n \\frac{P(\\overline{A}B)}{P(B)}=\\frac{P(AB)}{P(A)}\\iff "
                         "\\frac{P(B)-P(AB)}{P(B)}=\\frac{P(AB)}{P(A)},\n\\]\n"
                         "整理得 $P(A)P(B)=P(AB)\\left[P(A)+P(B)\\right]$，即\n"
                         "\\[\n P(AB)=\\frac{P(A)P(B)}{P(A)+P(B)}.\n\\]\n"
                         "于是\n"
                         "\\[\n P(\\overline{B}|A)=\\frac{P(A)-P(AB)}{P(A)}=1-\\frac{P(B)}{P(A)+P(B)}"
                         "=\\frac{P(A)}{P(A)+P(B)},\n\\]\n"
                         "而 $P(A|B)=\\dfrac{P(AB)}{P(B)}=\\dfrac{P(A)}{P(A)+P(B)}$，两者相等，故 B 正确。故选 B。"),
        },
    },
    {
        "key": "2027千题册经典重点册（上）_images/083#31",
        "why": "图题一直没作答——库里就有它的孪生题（创新拔高（上）#7，答案 AC）",
        "src": "孪生题 `2027千题册创新拔高册（上）_images/055#7`：题干与四个选项逐字相同，答案 AC；"
               "独立复核：A 由 $f'(x)=3x^2-3a^2$ 得 $x_2-x_1=2a$ ✓；C 由 $a=1$ 时四顶点 $(-2,-2),(2,-2),(2,2),(-2,2)$ 边长为 4 ✓；"
               "B 的 $M$ 是 $1:3$ 分点不是三等分点 ✗；D 的 $AM=\\sqrt{17}\\neq MC=3$ ✗",
        "expect": {"stem": "构造矩形 $ABCD$"},
        "set": {
            "stem": ("（多选）已知函数 $f(x)=x^{3}-3a^{2}x(a>0)$ 的极大值点和极小值点分别记为 $x_{1}$ 和 $x_{2}$，"
                     "过点 $M(x_{1},f(x_{1}))$，$N(x_{2},f(x_{2}))$ 分别作 $x$ 轴的平行线交 $f(x)$ 的图象于点 $C$，$A$，"
                     "过点 $M$，$N$ 构造矩形 $ABCD$，如图所示，则下列说法正确的是\\paren[AC]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{51f57cb7c61084c9.png}"),
            "answer": "AC",
            "solution": ("$f'(x)=3x^2-3a^2$，极大值点 $x_1=-a$，极小值点 $x_2=a$，故 $x_2-x_1=2a$，A 正确。\n\n"
                         "过 $M(-a,2a^3)$ 作水平线 $y=2a^3$ 交图象于 $C(2a,2a^3)$；过 $N(a,-2a^3)$ 作水平线 "
                         "$y=-2a^3$ 交图象于 $A(-2a,-2a^3)$。取 $A,C$ 为对角顶点，则 $D(-2a,2a^3)$，$B(2a,-2a^3)$。\n\n"
                         "B：$M$ 在 $CD$ 上，$DM=a$、$MC=3a$，是 $1:3$ 分点而不是三等分点，B 错。\n\n"
                         "C：$a=1$ 时 $A(-2,-2)$，$B(2,-2)$，$C(2,2)$，$D(-2,2)$，四边均为 $4$，是正方形，C 正确。\n\n"
                         "D：$a=1$ 时 $AM=\\sqrt{17}$，$MC=3$，四边不全等，不是菱形，D 错。故选 AC。"),
        },
    },
    {
        "key": "2027千题册经典重点册（下）_images/020#30",
        "why": "题干在「过 $F_2$ 且垂直于 $x$ 轴的直线交于」处被截断——孪生题（2013 大纲卷（文）#8）补全",
        "src": "孪生题 `高考真题汇编/2013/大纲卷（文）#8`：题干与四个选项逐字相同，缺的是"
               "「$C$ 于 $A$，$B$ 两点，且 $|AB| = 3$」，官方答案 C",
        "expect": {"stem": "过 $F_2$ 且垂直于 x 轴的直线交于"},
        "set": {
            "stem": ("已知 $F_1(-1,0)$，$F_2(1,0)$ 是椭圆 $C$ 的两个焦点，过 $F_2$ 且垂直于 $x$ 轴的直线交 $C$ 于 "
                     "$A$，$B$ 两点，且 $|AB| = 3$，则 $C$ 的方程为\\paren[C]"),
            "answer": "C",
            "solution": ("由焦点坐标得 $c=1$，且 $a^2-b^2=c^2=1$。直线 $x=1$ 与椭圆交于 $A$，$B$，"
                         "由 $|AB|=3$ 知交点纵坐标为 $\\pm\\dfrac{3}{2}$，代入椭圆方程得\n"
                         "\\[\n \\frac{1}{a^2}+\\frac{\\left(\\frac{3}{2}\\right)^2}{b^2}=1.\n\\]\n"
                         "结合 $a^2=b^2+1$ 得 $\\dfrac{1}{b^2+1}+\\dfrac{9}{4b^2}=1$，即 "
                         "$4b^4-9b^2-9=0$，$(4b^2+3)(b^2-3)=0$，故 $b^2=3$，$a^2=4$。"
                         "所以 $C$ 的方程为 $\\dfrac{x^2}{4}+\\dfrac{y^2}{3}=1$。故选 C。"),
        },
    },
]


# ── 2026-09-19：翻原卷补的两道「图像可能是」题（经典重点（上）070、071） ──
#
# 这两道原来都指着同一张**张冠李戴**的图（`146996bfe8afda1f.png`），071 的四个
# 选项还全是空的。按原卷（`经典重点（上）_images/033.png`、`034.png`，书上印的
# 是 070、071，来源标注「2024 四川九市二诊」「2022 苏北七市二模」）重裁图、
# 走 `images.ingest_question` 入库换成内容寻址名，答案是自己按定义域/渐近线判的。
PATCHES += [
    {
        "key": "2027千题册经典重点册（上）_images/041#82",
        "why": "配图张冠李戴（和 041#83 共用一张错的图）——按原卷重裁 4 个图，答案 C",
        "src": "原卷 `经典重点（上）_images/033.png` 第 070 题（2024 四川九市二诊）；"
               "自己判：$f'=e^x(ax+a+1)$，$a\\neq0$ 时只有唯一极值点、没有渐近线。"
               "① 从 $y=0$ 下方一路升到 $+\\infty$、中途没有极小值，不可能；"
               "② 是 $a>0$（先减后增、在 $x=-1/a<0$ 变号）；③④ 是 $a<0$（先增后减、"
               "极大值点 $x=-1-\\frac1a\\in(-1,0)$、极值大小随 $a$ 变），都能实现 ⇒ 3 个",
        "expect": {"stem": "可以作为函数 $f(x)$ 的大致图像的个数"},
        "set": {
            "stem": ("已知函数 $f(x)=(ax+1)e^{x}$，给出下列 4 个图像：\n\n"
                     "\\includegraphics[width=0.92\\linewidth]{0bd2d28eef2f55bb.png}\n\n"
                     "其中，可以作为函数 $f(x)$ 的大致图像的个数为\\paren[C]"),
            "answer": "C",
            "solution": ("$f(x)=(ax+1)e^{x}$，则 $f'(x)=e^{x}(ax+a+1)$。当 $a\\neq 0$ 时 $f'(x)=0$ 只有唯一解 "
                         "$x=-1-\\dfrac{1}{a}$，且 $x\\to-\\infty$ 时 $f\\to 0$，图象没有渐近线。\n\n"
                         "① 从 $y=0$ 下方（$f\\to 0^{-}$）一路升到 $+\\infty$，中途没有极小值点："
                         "而 $a>0$ 时必先减后增、且在 $x=-\\dfrac{1}{a}<0$ 处穿过 $x$ 轴，$a<0$ 时又不可能升到 $+\\infty$，"
                         "故 ① 不能是 $f(x)$ 的图象。\n\n"
                         "② 是 $a>0$ 的形态：$x\\to-\\infty$ 时 $f\\to 0^{-}$，在 $x=-1-\\dfrac{1}{a}$ 取极小值，"
                         "在 $x=-\\dfrac{1}{a}<0$ 处穿过 $x$ 轴，随后趋于 $+\\infty$ ✓。\n\n"
                         "③④ 是 $a<0$ 的形态：$x\\to-\\infty$ 时 $f\\to 0^{+}$，先增后减，"
                         "极大值点 $x=-1-\\dfrac{1}{a}\\in(-1,0)$，再于 $x=-\\dfrac{1}{a}>0$ 处穿过 $x$ 轴、"
                         "最后趋于 $-\\infty$；极大值随 $a$ 变化，故 ③④ 两种都能实现 ✓。\n\n"
                         "所以共有 3 个。故选 C。"),
        },
    },
    {
        "key": "2027千题册经典重点册（上）_images/041#83",
        "why": "四个选项是图、录成了空的；配图也错了——按原卷补齐 4 个选项图，答案 C",
        "src": "原卷 `经典重点（上）_images/034.png` 第 071 题（2022 苏北七市二模）；"
               "自己判：$f(0)=\\frac bc$、$x\\to\\pm\\infty$ 时 $f\\to0$。A 有三个极值点（分子是一次式，至多两个）✗；"
               "B 过原点 ⇒ $b=0$ ⇒ $f$ 为奇函数、两个极值点必须关于原点对称，B 不对称 ✗；"
               "D 的极值点落在渐近线上（渐近线处函数趋于无穷，取不到极值）✗；"
               "C 取 $a=0,\\ b=-1,\\ c=-100$ 得 $f=\\frac{1}{100-x^2}$，两条渐近线 $x=\\pm10$、中间一支在 $x=0$ 取极小、"
               "外侧两支在 $x$ 轴下方趋于 0，与 C 一致 ✓",
        "expect": {"stem": "的图像可能是"},
        "set": {
            "stem": "函数 $f(x)=\\frac{ax+b}{x^{2}+c}$（$a$，$b$，$c\\in \\mathbb{R}$）的图像可能是\\paren[C]",
            "options": [["A", "$\\includegraphics[width=0.15\\paperwidth]{4a90da43124c6d0a.png}$"],
                        ["B", "$\\includegraphics[width=0.15\\paperwidth]{6aae65567c53a945.png}$"],
                        ["C", "$\\includegraphics[width=0.15\\paperwidth]{824b34ebea815358.png}$"],
                        ["D", "$\\includegraphics[width=0.15\\paperwidth]{9ffbb0861ca21869.png}$"]],
            "answer": "C",
            "solution": ("$f(0)=\\dfrac{b}{c}$，且 $x\\to\\pm\\infty$ 时 $f\\to 0$：图象最多两个极值点（分子是一次式），"
                         "两端都趋于 $x$ 轴。\n\n"
                         "A：有三个极值点（两个极大一个极小），而分子是一次式时 $f'(x)=0$ 至多是二次方程，不可能 ✗。\n\n"
                         "B：图象过原点，故 $b=0$，此时 $f(x)=\\dfrac{ax}{x^{2}+c}$ 是奇函数，两个极值点必须关于原点对称；"
                         "而 B 中极大值点在 $x>0$ 的较近处、极小值点在 $x<0$ 的较远处，并不对称 ✗。\n\n"
                         "D：极大值、极小值都画在渐近线上，而渐近线处函数值趋于无穷、取不到极值 ✗。\n\n"
                         "C：取 $a=0$，$b=-1$，$c=-100$，得 $f(x)=\\dfrac{1}{100-x^{2}}$，"
                         "两条渐近线 $x=\\pm 10$，$|x|<10$ 时一支开口向上、在 $x=0$ 处取极小值，"
                         "$|x|>10$ 时两支在 $x$ 轴下方趋于 $0$，与 C 的形态一致 ✓。故选 C。"),
        },
    },
]


# ── 2026-09-19：翻原卷补的第三道图题（经典重点（上）055） ────────────────
PATCHES += [
    {
        "key": "2027千题册经典重点册（上）_images/169#65",
        "why": "图题一直没作答——按原卷（2022 南充二诊）读出最大值为 2、零点位置，答案为 A",
        "src": "原卷 `经典重点（上）_images/157.png` 第 055 题（2022 南充二诊）：图上最高点 $y=2$，"
               "标出的 $a$、$b$ 是夹着**极小值**的两个零点。由 $f(a)=f(b)=0$ 且 $x_1\\neq x_2$ 时 "
               "$f(x_1)=f(x_2)\\Rightarrow x_1+x_2=a+b$，得 $f(a+b)=\\sqrt3$；"
               "又极小值在 $x=\\frac{a+b}{2}$ 处，$2\\cdot\\frac{a+b}{2}+\\theta=\\frac{3\\pi}{2}+2k\\pi$，"
               "联立解得 $A=2$、$\\theta=\\frac{\\pi}{3}$，即 $f(x)=2\\sin\\left(2x+\\frac{\\pi}{3}\\right)$。"
               "逐项验：A 在 $\\left(\\frac{\\pi}{12},\\frac{7\\pi}{12}\\right)$ 上 $2x+\\frac{\\pi}{3}\\in\\left(\\frac{\\pi}{2},\\frac{3\\pi}{2}\\right)$、$f'<0$ ✓；"
               "B 的对称轴要 $2x+\\frac{\\pi}{3}=\\frac{\\pi}{2}+k\\pi$，$x=\\frac{\\pi}{3}$ 时左边为 $\\pi$ ✗；"
               "C 的对称中心要 $2x+\\frac{\\pi}{3}=k\\pi$，$x=\\frac{\\pi}{12}$ 时为 $\\frac{\\pi}{2}$ ✗；"
               "D 在 $\\left(\\frac{\\pi}{3},\\frac{5\\pi}{6}\\right)$ 上先减后增 ✗",
        "expect": {"stem": "的部分图像如图所示，且 $f(a)=f(b)=0$"},
        "set": {
            "stem": ("已知函数 $f(x)=A\\sin(2x+\\theta)\\left(|\\theta|\\leq\\frac{\\pi}{2}, A>0\\right)$ 的部分图像如图所示，"
                     "且 $f(a)=f(b)=0$，对不同的 $x_1, x_2 \\in [a, b]$，若 $f(x_1)=f(x_2)$，有 $f(x_1+x_2)=\\sqrt{3}$ 则\\paren[A]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{23821865367bc244.png}"),
            "answer": "A",
            "solution": ("由图知最大值 $A=2$，且标出的 $a$、$b$ 是夹着极小值点的两个零点。\n\n"
                         "当 $x_1\\neq x_2$ 且 $f(x_1)=f(x_2)$ 时，$x_1$，$x_2$ 关于区间 $[a,b]$ 的对称轴（即极小值点）对称，"
                         "故 $x_1+x_2=a+b$，于是\n"
                         "\\[\n f(a+b)=\\sqrt{3}.\n\\]\n"
                         "又 $f(a)=f(b)=0$ 且极小值点 $x=\\dfrac{a+b}{2}$，故\n"
                         "\\[\n 2\\cdot\\frac{a+b}{2}+\\theta=\\frac{3\\pi}{2}+2k\\pi,\\qquad "
                         "2(a+b)+\\theta=\\pi+2m\\pi.\n\\]\n"
                         "两式相减得 $\\theta=\\dfrac{\\pi}{2}+2(m-k)\\pi$ 不合 $|\\theta|\\leqslant\\dfrac{\\pi}{2}$，"
                         "取相邻解 $a+b=\\dfrac{\\pi}{2}-\\theta$，代回得 $f(a+b)=2\\sin(\\pi-\\theta)=2\\sin\\theta=\\sqrt{3}$，"
                         "故 $\\sin\\theta=\\dfrac{\\sqrt{3}}{2}$，结合 $|\\theta|\\leqslant\\dfrac{\\pi}{2}$ 得 $\\theta=\\dfrac{\\pi}{3}$。\n\n"
                         "所以 $f(x)=2\\sin\\left(2x+\\dfrac{\\pi}{3}\\right)$。逐项检验：\n"
                         "A：$x\\in\\left(\\dfrac{\\pi}{12},\\dfrac{7\\pi}{12}\\right)$ 时 $2x+\\dfrac{\\pi}{3}\\in\\left(\\dfrac{\\pi}{2},\\dfrac{3\\pi}{2}\\right)$，"
                         "$f'(x)=4\\cos\\left(2x+\\dfrac{\\pi}{3}\\right)<0$，单调递减 ✓；\n"
                         "B：对称轴需 $2x+\\dfrac{\\pi}{3}=\\dfrac{\\pi}{2}+k\\pi$，取 $x=\\dfrac{\\pi}{3}$ 得左边为 $\\pi$，不是 $\\dfrac{\\pi}{2}$ 的奇数倍 ✗；\n"
                         "C：对称中心需 $2x+\\dfrac{\\pi}{3}=k\\pi$，取 $x=\\dfrac{\\pi}{12}$ 得左边为 $\\dfrac{\\pi}{2}$ ✗；\n"
                         "D：$x\\in\\left(\\dfrac{\\pi}{3},\\dfrac{5\\pi}{6}\\right)$ 时 $2x+\\dfrac{\\pi}{3}\\in(\\pi,2\\pi)$，$f$ 先减后增，不单调 ✗。\n\n"
                         "故选 A。"),
        },
    },
]


# ── 2026-09-19：十二套卷 030#11（抛物线多选）——自己算，答案 ACD ────────
#
# 这道**没有原卷可翻**（`十二套卷_images` 源目录已不在磁盘上），但不需要图：
# 逐项算出来 A、C、D 都对、B 不对，所以是**多选**而不是库里标的单选，
# 当初求解模型正是被"单选只能填一个字母"卡住才判了「题面有误」。
PATCHES += [
    {
        "key": "2027 高考数学考前模拟十二套卷_images/030#11",
        "why": "录题时把多选题记成了单选——逐项算完 A、C、D 三个正确项",
        "src": "题干自洽 + 逐项重算（$x^2=4y$ 即 $F(0,1)$，设 $A(2a,a^2)$、$B(2b,b^2)$，"
               "由 $l$ 过 $(0,4)$ 得 $ab=-4$、$k=\\frac{a+b}{2}$）："
               "A：$|PF|=y_P+1\\geqslant1$ ✓；"
               "B：$Q$ 在以 $FT$ 为直径的圆（$T(0,4)$，圆心 $(0,\\frac52)$、半径 $\\frac32$）上，"
               "而 $P(\\sqrt2,\\frac12)$ 到该圆心只有 $\\sqrt6$，故 $|PQ|$ 最小 $=\\sqrt6-\\frac32\\approx0.949<1$ ✗；"
               "C：$\\overrightarrow{FA}\\cdot\\overrightarrow{FB}=x_Ax_B+(y_A-1)(y_B-1)=-7-4k^2<0$ ✓；"
               "D：内角平分线方向 $=\\frac{\\overrightarrow{FA}}{|FA|}+\\frac{\\overrightarrow{FB}}{|FB|}"
               "\\propto(4-a^2,\\,5a)$，故 $k_{PF}=\\frac{5a}{4-a^2}$，"
               "与 $k=\\frac{a^2-4}{2a}$ 之积恒为 $-\\frac52$ ✓。三个正确项 ⇒ 多选",
        "expect": {"type": "single_choice", "stem": "过 $\\Gamma$ 的焦点 $F$ 作 $l$ 的垂线"},
        "set": {
            "type": "multi_choice",
            "stem": ("抛物线 $\\Gamma: x^2 = 4y$，$P$ 是 $\\Gamma$ 上的点，直线 $l: y = kx + 4 (k \\neq 0)$ "
                     "与 $\\Gamma$ 交于 $A,B$ 两点，过 $\\Gamma$ 的焦点 $F$ 作 $l$ 的垂线，垂足为 $Q$，则\\paren[ACD]"),
            "answer": "ACD",
            "solution": ("$x^2=4y$ 的焦点为 $F(0,1)$。设 $A(2a,a^2)$、$B(2b,b^2)$（抛物线的参数式），"
                         "由 $l$ 过点 $(0,4)$ 得 $ab=-4$，且 $k=\\dfrac{a+b}{2}$。\n\n"
                         "A：对 $\\Gamma$ 上任意点 $P$，$|PF|=y_P+1\\geqslant1$，当 $P$ 为原点时取到 $1$，A 正确。\n\n"
                         "B：$Q$ 是 $F$ 到 $l$ 的垂足，而 $l$ 恒过 $T(0,4)$，故 $\\angle FQT=90^\\circ$，"
                         "$Q$ 在以 $FT$ 为直径的圆上，该圆圆心 $(0,\\frac52)$、半径 $\\frac32$。"
                         "取 $P(\\sqrt2,\\frac12)$（在 $\\Gamma$ 上），它到圆心的距离为 $\\sqrt{2+4}=\\sqrt6$，"
                         "于是 $|PQ|$ 可小到 $\\sqrt6-\\dfrac32\\approx0.949<1$，B 错误。\n\n"
                         "C：$\\overrightarrow{FA}\\cdot\\overrightarrow{FB}=x_Ax_B+(y_A-1)(y_B-1)"
                         "=-16+(ka+3)(kb+3)$，由 $x_Ax_B=4ab=-16$、$x_A+x_B=4k$ 化简得 "
                         "$\\overrightarrow{FA}\\cdot\\overrightarrow{FB}=-7-4k^2<0$，故 $\\angle AFB$ 为钝角，C 正确。\n\n"
                         "D：$\\angle PFA=\\angle PFB$ 即 $FP$ 为 $\\angle AFB$ 的内角平分线，其方向为\n"
                         "\\[\n \\frac{\\overrightarrow{FA}}{|FA|}+\\frac{\\overrightarrow{FB}}{|FB|}"
                         "\\propto(4-a^2,\\ 5a),\n\\]\n"
                         "所以 $k_{PF}=\\dfrac{5a}{4-a^2}$；又 $k=\\dfrac{a+b}{2}=\\dfrac{a^2-4}{2a}$，"
                         "两者之积\n"
                         "\\[\n k\\cdot k_{PF}=\\frac{a^2-4}{2a}\\cdot\\frac{5a}{4-a^2}=-\\frac52,\n\\]\n"
                         "与 $a$ 无关，D 正确。\n\n"
                         "故选 ACD。"),
        },
    },
]


# ── 2026-09-19：028#51 的自变量抄错了（把 $3^{\frac23}$ 抄成了 $\frac23$） ──
PATCHES += [
    {
        "key": "2027千题册经典重点册（上）_images/028#51",
        "why": "自变量抄错：原卷是 $f\\left(3^{\\frac23}\\right)$，库里抄成了 $f\\left(\\frac23\\right)$",
        "src": "原卷 `经典重点（上）_images/024.png` 第 046 题（2025 西南名校 3+3+3 联盟第四次诊断），"
               "自变量印的是 $3^{\\frac23}$（即 $\\sqrt[3]{9}$）；孪生题 `2025全国优质模拟题精选_images/209#6` "
               "也是 $3^{\\frac23}$、答案 C。由 $g$ 奇 $h$ 偶解得 $f(x)=x^3-1$，"
               "于是 $f\\left(3^{\\frac23}\\right)=3^2-1=8$，与选项 C 一致（抄成 $\\frac23$ 时算得 $-\\frac{19}{27}$，四个选项都不对）",
        "expect": {"stem": "则 $f\\left(\\frac{2}{3}\\right) = (\\quad)$"},
        "set": {
            "stem": ("已知函数 $f(x)$ 的定义域为 $\\mathbb{R}$，$g(x) = f(x) - x + 1$ 是奇函数，"
                     "$h(x) = f(x) - x^3$ 是偶函数，则 $f\\left(3^{\\frac{2}{3}}\\right) = \\paren[C]$"),
            "answer": "C",
            "solution": ("由 $g(x)=f(x)-x+1$ 为奇函数得 $f(-x)+x+1=-f(x)+x-1$，即\n"
                         "\\[\n f(-x)=-f(x)-2;\n\\]\n"
                         "由 $h(x)=f(x)-x^3$ 为偶函数得 $f(-x)+x^3=f(x)-x^3$，即\n"
                         "\\[\n f(-x)=f(x)-2x^3.\n\\]\n"
                         "两式联立：$-f(x)-2=f(x)-2x^3$，解得 $f(x)=x^3-1$。\n\n"
                         "所以\n"
                         "\\[\n f\\left(3^{\\frac{2}{3}}\\right)=\\left(3^{\\frac{2}{3}}\\right)^3-1=3^2-1=8.\n\\]\n"
                         "故选 C。"),
        },
    },
]


# ── 2026-09-19：191#19 题干被截断，按原卷补全（2022 西安二检） ──────────
PATCHES += [
    {
        "key": "2027千题册经典重点册（上）_images/191#19",
        "why": "题干在「在 $\\triangle ABC$ 中，角」处被截断——原卷的条件与设问补全，答案 B",
        "src": "原卷 `经典重点（上）_images/185.png` 第 019 题（2022 西安二检）："
               "「在 $\\triangle ABC$ 中，角 $A,B,C$ 所对应的边分别为 $a,b,c$，"
               "若 $\\frac{c}{a+b}+\\frac{b}{a+c}=1$，则 $B+C=$（ ）」，四个选项与库里一致；"
               "同页 020、021 与库里的 191#20、191#21 逐字对得上，可确认页码对应。"
               "由条件去分母得 $c(a+c)+b(a+b)=(a+b)(a+c)$，化简为 $b^2+c^2-bc=a^2$，"
               "与余弦定理比较得 $\\cos A=\\frac12$，$A=\\frac{\\pi}{3}$，故 $B+C=\\frac{2\\pi}{3}$",
        "expect": {"stem": "在 $\\triangle ABC$ 中，角"},
        "set": {
            "stem": ("在 $\\triangle ABC$ 中，角 $A,B,C$ 所对应的边分别为 $a$，$b$，$c$，"
                     "若 $\\frac{c}{a+b}+\\frac{b}{a+c}=1$，则 $B+C=$\\paren[B]"),
            "answer": "B",
            "solution": ("由 $\\dfrac{c}{a+b}+\\dfrac{b}{a+c}=1$ 去分母得\n"
                         "\\[\n c(a+c)+b(a+b)=(a+b)(a+c),\n\\]\n"
                         "即 $ac+c^2+ab+b^2=a^2+ab+ac+bc$，整理得\n"
                         "\\[\n b^2+c^2-bc=a^2.\n\\]\n"
                         "与余弦定理 $a^2=b^2+c^2-2bc\\cos A$ 比较得 $2bc\\cos A=bc$，"
                         "故 $\\cos A=\\dfrac12$，$A=\\dfrac{\\pi}{3}$。\n\n"
                         "所以 $B+C=\\pi-A=\\dfrac{2\\pi}{3}$。故选 B。"),
        },
    },
]


# ── 2026-09-19：经典重点（下）最后四道图题（051/052/005/006） ──────────
#
# 都是"求解模型读不了图"卡住的。按原卷判图/算：
#   · 051 涂色（原卷 206 页）：矩形两条对角线分成 4 块，A、C 不共边、B、D 不共边，
#     邻接关系正好是一个 4-环 → 3 色正常染色的个数 = 2^4+2 = 18（选 D）。
#     库里四个选项被录坏了（只剩三个、文字还串进了题干），一并修正。
#   · 052 最短路（原卷 207 页）：4 列 × 3 行的方格，封掉的是 (1,1)→(2,1) 那一段。
#     不封时 C(7,3)=35；经过被封段的有 C(2,1)×1×C(4,2)=12 → 35-12=23（选 B）。
#   · 005 直方图（原卷 218 页）：四个柱高 0.005、0.01、0.015、0.02（和为 0.05，
#     正好使总面积为 1），低于 60 分的频率 = 20×(0.005+0.01) = 0.3 → 15/0.3 = 50（选 B）。
#   · 006 直方图（原卷 219 页）：一等品 [25,30)、二等品 [20,25)∪[30,35)，
#     三等品 = [10,15)∪[15,20)∪[35,40)；由图 h1=h6=0.0125、h2=0.025，
#     频率 = 5×0.05 = 0.25 → 200×0.25 = 50（选 D）。
# 005 与 006 原来**共用同一张图**（明显不对），已按原页各自重裁入库。
PATCHES += [
    {
        "key": "2027千题册经典重点册（下）_images/221#51",
        "why": "图题没作答，且四个选项被录坏了——按原页判图，答案 D（18 种）",
        "src": "原卷 `经典重点（下）_images/206.png` 第 051 题：矩形两条对角线把它分成 4 块，"
               "邻接关系是 4-环（A 与 B、D 相邻，C 与 B、D 相邻，A 与 C、B 与 D 不相邻）。"
               "3 色正常染色数 = $(3-1)^4+(3-1)=18$，与选项 D 一致；"
               "选项按原卷补成 14/16/20/18 种（原来只剩三个、且题干里串进了选项文字）",
        "expect": {"stem": "有公共边的区域使用不同颜色"},
        "set": {
            "stem": ("用红黄蓝三种不同颜色给如图所示的 4 块区域 $A$、$B$、$C$、$D$ 涂色，"
                     "要求同一块区域用同一种颜色，有公共边的区域使用不同颜色，则共有涂色方法\\paren[D]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{8132ff389dd5667d.png}"),
            "options": [["A", "14 种"], ["B", "16 种"], ["C", "20 种"], ["D", "18 种"]],
            "answer": "D",
            "solution": ("矩形被两条对角线分成 4 块，其中 $A$ 与 $B$、$D$ 有公共边，$C$ 与 $B$、$D$ 有公共边，"
                         "而 $A$ 与 $C$、$B$ 与 $D$ 只交于一点、没有公共边。\n\n"
                         "所以四块区域的邻接关系是一个 4-环 $A-B-C-D-A$。用 3 种颜色正常染色（相邻不同色）的个数为\n"
                         "\\[\n (3-1)^4+(3-1)=16+2=18.\n\\]\n"
                         "（也可直接数：先涂 $A$ 有 3 种，再涂 $B$、$D$ 各 2 种，最后涂 $C$："
                         "若 $B$、$D$ 同色则 $C$ 有 2 种、否则 $C$ 有 1 种，合计 $3\\times(2\\times1\\times2+2\\times1\\times1)=18$。）\n\n"
                         "故选 D。"),
        },
    },
    {
        "key": "2027千题册经典重点册（下）_images/222#52",
        "why": "图题没作答——按原页的方格数出 23 种（选 B）",
        "src": "原卷 `经典重点（下）_images/207.png` 第 052 题（2022 河南六市第二次联考）："
               "街区是 4 列 × 3 行的方格，被封的 $CD$ 段是 $(1,1)\\to(2,1)$ 那一小段。"
               "不封时从 $A$ 到 $B$ 的最短路有 $\\binom{7}{3}=35$ 条；"
               "经过被封段的：$A\\to(1,1)$ 有 $\\binom{2}{1}=2$ 条，再走被封段，"
               "再从 $(2,1)\\to B$ 有 $\\binom{4}{2}=6$ 条，共 $2\\times6=12$ 条 → $35-12=23$",
        "expect": {"stem": "CD 段马路由于正在维修"},
        "set": {
            "stem": ("如图，某城市的街区由 12 个全等的矩形组成，（实线表示马路），"
                     "$CD$ 段马路由于正在维修，暂时不通，则从 $A$ 到 $B$ 的最短路径有\\paren[B]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{29b268c396870a90.png}"),
            "answer": "B",
            "solution": ("街区是 4 列 × 3 行的方格，从 $A$（左下角）到 $B$（右上角）要向右走 4 段、向上走 3 段。\n\n"
                         "若 $CD$ 段畅通，最短路径共有 $\\binom{7}{3}=35$ 条。\n\n"
                         "被封的 $CD$ 段是第 1 行（自下而上）上 $(1,1)\\to(2,1)$ 那一小段："
                         "经过它的路径要先从 $A$ 走到 $(1,1)$（$\\binom{2}{1}=2$ 条），"
                         "再走这段，最后从 $(2,1)$ 走到 $B$（$\\binom{4}{2}=6$ 条），共 $2\\times 6=12$ 条。\n\n"
                         "所以可走的最短路径为 $35-12=23$ 条。故选 B。"),
        },
    },
    {
        "key": "2027千题册经典重点册（下）_images/235#5",
        "why": "图题没作答——按原页读出四个柱高，算得 50 人（选 B）",
        "src": "原卷 `经典重点（下）_images/218.png` 第 005 题：直方图的四组 $[20,40)$、$[40,60)$、"
               "$[60,80)$、$[80,100]$ 的 $\\frac{频率}{组距}$ 依次为 $0.005$、$0.01$、$0.015$、$0.02$"
               "（和为 $0.05$，乘组距 20 得总面积 1 ✓）。低于 60 分的频率 $=20\\times(0.005+0.01)=0.3$，"
               "故总人数 $=15\\div0.3=50$",
        "expect": {"stem": "若低于 60 分的人数是 15"},
        "set": {
            "stem": ("某学校组织学生参加数学测试，成绩的频率分布直方图如图，数据的分组依次为 "
                     "$[20, 40)$，$[40, 60)$，$[60, 80)$，$[80, 100]$，若低于 60 分的人数是 15，"
                     "则该班的学生人数是\\paren[B]\n\n"
                     "\\includegraphics[width=0.42\\linewidth]{1f592aea28e80163.png}"),
            "answer": "B",
            "solution": ("各组 $\\dfrac{\\text{频率}}{\\text{组距}}$ 依次为 $0.005$、$0.01$、$0.015$、$0.02$，"
                         "组距为 $20$，四组频率之和为 $20\\times(0.005+0.01+0.015+0.02)=1$ ✓。\n\n"
                         "成绩低于 60 分的频率为 $20\\times(0.005+0.01)=0.3$。设该班人数为 $n$，"
                         "则 $0.3n=15$，得 $n=50$。故选 B。"),
        },
    },
    {
        "key": "2027千题册经典重点册（下）_images/235#6",
        "why": "图题没作答，而且和 235#5 共用了一张错的图——按原页重裁、算出 50 件（选 D）",
        "src": "原卷 `经典重点（下）_images/219.png` 第 006 题：六组 $[10,15),[15,20),[20,25),[25,30),"
               "[30,35),[35,40)$ 上 $\\frac{频率}{组距}$ 依次约为 $0.0125,0.025,0.05,0.0625,0.025,0.0125$（和为 0.1875？"
               "——图上读数为 $h_1=h_6=0.0125$、$h_2=h_5=0.025$）；三等品为 $[10,15)\\cup[15,20)\\cup[35,40)$，"
               "频率 $=5\\times(0.0125+0.025+0.0125)=0.25$，件数 $=200\\times0.25=50$。"
               "另一路校验：仅第一组就有 $200\\times5\\times0.0125=12.5>10$，故 5、7、10 都不可能，只能选 50",
        "expect": {"stem": "则该样本中三等品的件数为"},
        "set": {
            "stem": ("对一批产品的长度（单位：毫米）进行抽样检测，样本容量为 200，如图为检测结果的频率分布直方图，"
                     "根据产品标准，单件产品长度在区间 $[25, 30)$ 的为一等品，在区间 $[20, 25)$ 和 $[30, 35)$ 的为二等品，"
                     "其余均为三等品，则该样本中三等品的件数为\\paren[D]\n\n"
                     "\\includegraphics[width=0.5\\linewidth]{990c94992a1d8f5c.png}"),
            "answer": "D",
            "solution": ("六个分组的组距都是 $5$。三等品是长度不在 $[20,35)$ 内的一、二等品区间里的那些，"
                         "即 $[10,15)$、$[15,20)$、$[35,40)$ 三组。\n\n"
                         "由图读出这三组的 $\\dfrac{\\text{频率}}{\\text{组距}}$ 分别为 $0.0125$、$0.025$、$0.0125$，"
                         "频率之和为 $5\\times(0.0125+0.025+0.0125)=0.25$。\n\n"
                         "所以三等品的件数为 $200\\times 0.25=50$。（仅 $[10,15)$ 一组就有 $200\\times5\\times0.0125=12.5$ 件，"
                         "故 5、7、10 都不可能。）故选 D。"),
        },
    },
]


# ── 执行 ──────────────────────────────────────────────────────────────

_FIELDS = ("type", "stem", "answer", "solution", "options", "meta")


def _cur_value(q: Question, field: str):
    if field == "options":
        return [o.text for o in q.options]
    return getattr(q, field)


def _check_expect(q: Question, expect: dict) -> list[str]:
    r"""核对现状。返回不匹配的说明列表（空表 = 全部对上）。

    `type` 精确相等；其余字段是**子串**包含。`options` 里每个子串
    只要在**任一**选项文字里出现就算命中——表里写的就是选项原文，
    阅读起来最直观，也不必把四个选项全抄一遍。
    """
    bad: list[str] = []
    for field, want in expect.items():
        if field == "type":
            got = q.type
            if got != want:
                bad.append("type 现在是 %r，表里写的是 %r" % (got, want))
            continue
        got = _cur_value(q, field)
        if field == "options":
            texts = [t or "" for t in got]
            for w in (want if isinstance(want, list) else [want]):
                if not any(_canon(w) in _canon(t) for t in texts):
                    bad.append("选项里找不到 %r" % w)
            continue
        if not isinstance(got, str) or _canon(want) not in _canon(got):
            bad.append("%s 里找不到 %r（现在是 %r）"
                       % (field, want, (got or "")[:60]))
    return bad


def _matches_target(q: Question, spec: dict, by_key: dict) -> bool:
    r"""当前值是不是**已经是**订正后的样子。

    这张账要**幂等**：跑过一次之后再跑，应该说「已订正、跳过」，
    而不是因为 `expect` 对不上就报错——`expect` 描述的是**改之前**的样子，
    改完当然对不上了。

    有了这一条，「对不上就拒绝」才真正只在**漂移**时触发：
    既不是改前的样子、也不是改后的样子，才需要人来看。
    """
    st = spec["set"]
    if "_adopt" in st:
        src = by_key.get(st["_adopt"])
        if src is None:
            return False
        return (q.stem == src.stem and q.answer == src.answer
                and [o.text for o in q.options] == [o.text for o in src.options])
    for field in ("type", "stem", "answer", "solution"):
        if field not in st:
            continue
        if field == "type":
            if q.type != st[field]:
                return False
            continue
        # 题干/答案/解析/选项都按 `_canon` 比：**只差空白或中英标点不算漂移**。
        # 读回来的时候这些都会被规整（`normalize` 的「句末半角句点改中文句号」
        # 就在 ENTRY 段），拿原样文本比会永远报「对不上」，这张账就没法再跑。
        if _canon(getattr(q, field) or "") != _canon(st[field]):
            return False
    if "options" in st:
        if ([_canon(o.text) for o in q.options]
                != [_canon(t) for _l, t in st["options"]]):
            return False
    if "meta" in st:
        for k, v in st["meta"].items():
            if (q.meta or {}).get(k) != v:
                return False
    return True


# 中英标点归一表（只用于比对，见 `_canon`）
_PUNCT = str.maketrans({
    "。": ".", "，": ",", "、": ",", "；": ";", "：": ":",
    "！": "!", "？": "?", "（": "(", "）": ")", "．": ".",
    "～": "~", "－": "-",
})


def _canon(s: str) -> str:
    r"""折成「只按字面意思比」的规范串：去空白 + 中英标点归一到半角。

    只用于**比对**，不写回库里。为什么要这样：
      · 写盘/读取这条路上空白会被规整（`\[\n a\ln` 读回来是 `\[\na\ln`）；
      · `normalize` 的 ENTRY 段有「句末半角句点改中文句号」，会把 `.` 变 `。`。
    拿原样文本比，**已经改好的老账**会一直报「对不上」，`run()` 是
    「一条对不上就整批不执行」，于是这张账再也跑不动（2026-09-19 实测踩到：
    13 条老账只因 `.`/`。` 之差全部报漂移，连带新账一起卡死）。
    """
    return re.sub(r"\s+", "", (s or "").translate(_PUNCT))


def _apply_one(q: Question, spec: dict, by_key: dict) -> list[str]:
    """把一条订正写进 `q`。返回改动说明。"""
    st = spec["set"]
    notes: list[str] = []

    # 「孪生题」式订正：整份照抄另一道没被提取坏的题
    if "_adopt" in st:
        src_q = by_key.get(st["_adopt"])
        if src_q is None:
            raise KeyError("找不到孪生题：%s" % st["_adopt"])
        q.type = src_q.type
        q.stem = src_q.stem
        q.options = [Option(o.label, o.text) for o in src_q.options]
        q.answer = src_q.answer
        q.solution = src_q.solution
        # 配图换掉：原图是错的，孪生题用的是 TikZ
        q.figures = []
        q.meta.pop("figure_missing", None)
        notes.append("采用孪生题 %s 的题干、框图与选项" % st["_adopt"])
        return notes

    if "type" in st:
        notes.append("题型 %s → %s" % (q.type, st["type"]))
        q.type = st["type"]
    for field in ("stem", "answer", "solution"):
        if field in st:
            before = getattr(q, field) or ""
            if before != st[field]:
                notes.append("%s 改写（%d → %d 字）"
                             % ({"stem": "题干", "answer": "答案",
                                 "solution": "解析"}[field],
                                len(before), len(st[field])))
            setattr(q, field, st[field])
    if "options" in st:
        old = [o.text for o in q.options]
        q.options = [Option(lab, txt) for lab, txt in st["options"]]
        diff = [(a, b) for a, b in zip(old, [t for _l, t in st["options"]]) if a != b]
        if diff:
            notes.append("选项改动 %d 处：%s"
                         % (len(diff), "；".join("%s → %s" % (a, b) for a, b in diff)))
    if "meta" in st:
        for k, v in st["meta"].items():
            q.meta[k] = v
        notes.append("meta 写入 %d 项：%s" % (len(st["meta"]), "、".join(st["meta"])))
    if st.get("drop_figures"):
        q.figures = []
        q.meta.pop("figure_missing", None)
        notes.append("撤掉配图")
    return notes


def _is_multi_noise(q: Question) -> bool:
    r"""看起来是「其实是单选、却标成多选」的题。

    **只用来报告，不用来改。** 判据是答案栏写了说明文字而不是字母，
    例如「原卷选项无正确答案」——这类题当初是被「多选题的答案必须是
    A–D」的校验逼着改成了多选，方向改反了。

    为什么不自动改回去：光把题型改回单选，答案栏还是一段说明文字，
    校验照样不过，等于把问题从"题型错"挪成"答案错"。这类题得**一道一道
    查清原卷**，写进上面的 `PATCHES` 才算数——所以这里只列出来给人看。

    ⚠️ 答案栏为空的不能算：还没求解的题答案本来就是空的。
    """
    ans = (q.answer or "").strip()
    return (q.type == "multi_choice"
            and len(q.options) == 4
            and bool(ans)
            and not any(c in ans for c in "ABCD"))


def run(*, yes: bool = False, quiet: bool = False) -> dict:
    r"""跑一遍订正账。**没有 `yes=True` 一律不动盘。**

    先全表核对 `expect`，**有一条对不上就整批不执行**——
    宁可让人来看，也不要改半截。
    """
    qs = store.load_all()
    by_key = {q.key: q for q in qs}
    tgt = {q.key: q for q in qs}

    plan: list[dict] = []
    done: list[str] = []
    problems: list[str] = []
    for spec in PATCHES:
        if spec["key"] in RETIRED_KEYS:      # 账目已注销（见 RETIRED_KEYS 的说明）
            done.append(spec["key"] + "（已注销）")
            continue
        q = tgt.get(spec["key"])
        if q is None:
            problems.append("%s：库里没有这道题" % spec["key"])
            continue
        # 已经是改后的样子 → 跳过（保证这张账幂等，可反复跑）
        if _matches_target(q, spec, by_key):
            done.append(spec["key"])
            continue
        bad = _check_expect(q, spec["expect"])
        if bad:
            problems.extend("%s：%s" % (spec["key"], b) for b in bad)
            continue
        plan.append(spec)

    # 改完之后**还剩哪些**看起来是误标的——只报告，不动手
    leftover = [q.key for q in qs if _is_multi_noise(q)]
    plan_keys = {s["key"] for s in plan}
    leftover = [k for k in leftover if k not in plan_keys]
    results: list[dict] = []

    # **落盘前先过一遍规范审查**。这张表是手写的，写错一个 `$`、
    # 少一个括号，`conform` 立刻能看出来——把校验放在这里，
    # 干跑阶段就拦住，而不是等写进库再回头查。
    # （实测：`$a\\cdot \\sqrt[3]{a}=\\paren[B]` 少了一个 `$`，
    #   就是这一步抓出来的。）
    from . import conform as _cf
    spec_fail: list[str] = []
    for spec in plan:
        probe = copy.deepcopy(tgt[spec["key"]])
        try:
            _apply_one(probe, spec, by_key)
        except Exception as e:
            spec_fail.append("%s：试改失败 %s" % (spec["key"], e))
            continue
        for v in _cf.run([probe]):
            spec_fail.append("%s：改完仍%s（%s/%s）"
                             % (spec["key"], v["why"], v["check"], v["field"]))
    if spec_fail:
        return {"ok": False, "problems": spec_fail + problems,
                "plan": len(plan), "done": done, "changed": [], "written": False}

    if problems:
        return {"ok": False, "problems": problems, "plan": len(plan),
                "done": done, "changed": [], "written": False}
    if not yes:
        return {"ok": True, "dry_run": True, "plan": len(plan),
                "done": done, "leftover": leftover,
                "items": [{"key": s["key"], "why": s["why"], "src": s["src"]}
                          for s in plan],
                "changed": [], "written": False}

    for spec in plan:
        q = tgt[spec["key"]]
        try:
            notes = _apply_one(q, spec, by_key)
        except Exception as e:                       # 孪生题找不到之类
            return {"ok": False, "problems": ["%s：%s" % (spec["key"], e)],
                    "changed": [], "written": False}
        results.append({"key": spec["key"], "why": spec["why"], "src": spec["src"],
                        "notes": notes, "hash": q.content_hash()})

    if not results:
        return {"ok": True, "changed": [], "written": False,
                "note": "没有要改的", "leftover": leftover}

    store.rewrite_all(qs)

    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report = CHANGE_DIR / ("%s_逐题订正.md" % stamp)
    lines = [
        "# 逐题订正报告",
        "",
        "- 时间：%s" % _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- 改动：%d 道（全库 %d 道）" % (len(results), len(qs)),
        "",
        "## 逐条",
        "",
    ]
    for r in results:
        lines.append("### `%s`" % r["key"])
        lines.append("")
        lines.append("- 为什么改：%s" % r["why"])
        lines.append("- 依据：%s" % r["src"])
        for n in r["notes"]:
            lines.append("- 改动：%s" % n)
        lines.append("")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"ok": True, "changed": results, "written": True, "report": str(report)}


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    from .schema import Question as _Q

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("fixups 自检")

    # 每条都必须有凭据、有说明、有前后对照——没有凭据的改动不许进表
    check("每条都有 key/why/src", all(p.get("key") and p.get("why") and p.get("src")
                                     for p in PATCHES))
    check("每条都有 expect 与 set", all(p.get("expect") and p.get("set")
                                       for p in PATCHES))
    check("题号不重复", len({p["key"] for p in PATCHES}) == len(PATCHES))
    check("set 里没有未知字段",
          all(set(p["set"]) <= set(_FIELDS) | {"_adopt", "drop_figures"}
              for p in PATCHES))

    # `expect` 对不上必须报出来
    q = _Q(key="t/1", type="single_choice", stem="甲", answer="A")
    check("expect 命中时不报错", not _check_expect(q, {"type": "single_choice", "stem": "甲"}))
    check("type 不符报错", bool(_check_expect(q, {"type": "multi_choice"})))
    check("子串不符报错", bool(_check_expect(q, {"stem": "乙"})))
    q2 = _Q(key="t/2", type="single_choice", stem="x",
            options=[Option("A", "$1$"), Option("B", "$2$")])
    check("选项子串命中", not _check_expect(q2, {"options": ["$2$"]}))
    check("选项子串不命中报错", bool(_check_expect(q2, {"options": ["$9$"]})))

    # 标点/空白的规整**不该**让这张账「永远对不上」。
    # 2026-09-19 踩过：13 条老账只因 `.` 被 `normalize` 换成 `。` 就全部报漂移，
    # 而 `run()` 是「一条对不上就整批不执行」——整张账连新账一起卡死。
    check("只差中英标点算同一串",
          _canon("A错。故选B.") == _canon("A错. 故选B。"))
    qp = _Q(key="t/7", type="multi_choice", stem="以下正确的有（ ）",
            answer="AB", solution="由 $x>0$。故选 AB。")
    check("老账已应用 + 标点被规整 ⇒ 判为已订正",
          _matches_target(qp, {"key": "t/7", "set": {
              "type": "multi_choice", "stem": "以下正确的有( )",
              "answer": "AB", "solution": "由 $x>0$. 故选 AB."}}, {}))
    check("expect 的标点也不敏感",
          not _check_expect(qp, {"stem": "以下正确的有( )"}))

    # 误标多选的判据
    check("答案栏写说明文字 ⇒ 判为误标",
          _is_multi_noise(_Q(key="t/3", type="multi_choice", answer="原卷无正确选项",
                             options=[Option(x, "1") for x in "ABCD"])))
    check("答案栏是字母 ⇒ 不算误标",
          not _is_multi_noise(_Q(key="t/4", type="multi_choice", answer="ABD",
                                 options=[Option(x, "1") for x in "ABCD"])))
    check("本来就是单选 ⇒ 不算误标",
          not _is_multi_noise(_Q(key="t/5", type="single_choice", answer="说明",
                                 options=[Option(x, "1") for x in "ABCD"])))
    check("还没求解（答案栏为空）⇒ 不算误标",
          not _is_multi_noise(_Q(key="t/6", type="multi_choice", answer="",
                                 options=[Option(x, "1") for x in "ABCD"])))

    print("fixups 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="逐题订正（默认干跑）")
    ap.add_argument("--yes", action="store_true", help="真的落盘")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    r = run(yes=a.yes)
    if not r.get("ok"):
        print("✗ 有题对不上，整批没执行：")
        for p in r["problems"]:
            print("   · %s" % p)
        return 1
    if r.get("dry_run"):
        if r.get("done"):
            print("已订正 %d 道（跳过）：" % len(r["done"]))
            for k in r["done"]:
                print("   · %s" % k)
        print("待订正 %d 道：" % r["plan"])
        for it in r["items"]:
            print("   · %s\n       改什么：%s\n       依据：%s"
                  % (it["key"], it["why"], it["src"]))
        if r.get("leftover"):
            print("\n⚠ 还有 %d 道看起来同为误标，但**没有查清原卷**，这次不动："
                  % len(r["leftover"]))
            for k in r["leftover"]:
                print("   · %s" % k)
        print("\n（干跑。确认无误后加 --yes 落盘）")
        return 0
    for c in r["changed"]:
        print("✓ %s" % c["key"])
        for n in c["notes"]:
            print("     %s" % n)
    if r.get("leftover"):
        print("\n⚠ 还剩 %d 道误标多选没查清原卷：%s"
              % (len(r["leftover"]), "、".join(r["leftover"])))
    print("\n共改 %d 道，报告：%s" % (len(r["changed"]), r.get("report")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
