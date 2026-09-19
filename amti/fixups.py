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
