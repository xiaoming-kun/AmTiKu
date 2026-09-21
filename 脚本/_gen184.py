#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 #184 2026届云南省昆明一中高三1月复习诊断（第六次联考） 的成品 / 待复核。

来源：`昆明市第一中学2026届高三年级第六次联考数学+答案.pdf` 共 9 页，
    试卷与答案是同一份文件（队列里 试卷[] 与 答案[] 指向同一个 PDF）：
    卷面正文为第 1–4 页「数学试卷·第 N 页（共 4 页）」，
    第 5–9 页为「昆明市第一中学 2026 届高三年级第六次联考 数学参考答案」（页脚自标 1–5）。
卷面结构：一、单项选择题 8 小题（1–8）；二、多项选择题 3 小题（9–11）；
三、填空题 3 小题（12–14）；四、解答题 5 小题（15–19）。
正文一律 r-string；多行用 L([...]) 以真实换行拼接。
"""
import json
from pathlib import Path

OUT = Path("数据/录题/输出_v2")
NAME = "184_2026届云南省昆明一中高三1月复习诊断（第六次联考）"


def L(*lines):
    return "\n".join(lines)


recs = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1],
        "题干": r"校园 AI 编程创意赛有 $17$ 位同学参赛，他们的作品评分互不相同，只有评分在前 $9$ 名的同学能晋级决赛．若某同学知道自己的作品评分后，想判断自己能否晋级，则他只需要知道这 $17$ 位同学评分的",
        "选项": {"A": "众数", "B": "中位数", "C": "平均数", "D": "极差"},
        "答案": "B",
        "解析": r"因为 $17$ 位同学的评分，中位数是第 $9$ 名，所以知道中位数即可判断是否在前 $9$，选 B.",
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1],
        "题干": r"$x(1+3x)^{3}$ 的展开式中 $x^{3}$ 的系数为",
        "选项": {"A": r"$3$", "B": r"$9$", "C": r"$18$", "D": r"$27$"},
        "答案": "D",
        "解析": r"$x^{3}$ 的系数为 $C_{3}^{2}\cdot 3^{2}=27$，选 D.",
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1],
        "题干": r"已知命题 $p:\forall x\in\mathbf{R}$，$ax^{2}+2ax-3\leqslant 0$ 为真命题，则实数 $a$ 的取值范围是",
        "选项": {
            "A": r"$(-3,+\infty)$", "B": r"$(-\infty,-\dfrac{1}{3})$",
            "C": r"$\left[-\dfrac{1}{3},0\right)$", "D": r"$[-3,0]$",
        },
        "答案": "D",
        "解析": L(
            r"因为命题 $p:\forall x\in\mathbf{R}$，$ax^{2}+2ax-3\leqslant 0$ 为真命题，所以不等式 $ax^{2}+2ax-3\leqslant 0$ 的解集为 $\mathbf{R}$，",
            r"若 $a=0$，则不等式可化为 $-3\leqslant 0$，成立；若 $a\neq 0$，则根据一元二次不等式解集的形式可知：",
            r"$\begin{cases}a<0\\ \Delta=4a^{2}+12a\leqslant 0\end{cases}$，解得 $-3\leqslant a<0$，综上所述，选 D.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [1],
        "题干": r"已知 $\alpha$，$\beta$ 为两个平面，$m$，$n$ 是两条直线，$m\subset\alpha$，$n\subset\beta$，则下列命题正确的是",
        "选项": {
            "A": r"若 $m\parallel\beta$，则 $\alpha\parallel\beta$",
            "B": r"若 $\alpha\parallel\beta$，则 $m\parallel n$",
            "C": r"若 $m\perp\beta$，则 $\alpha\perp\beta$",
            "D": r"若 $\alpha\perp\beta$，则 $m\perp\beta$",
        },
        "答案": "C",
        "解析": r"如果一个平面经过另一个平面的垂线，那么这两个平面垂直，选 C.",
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1],
        "题干": r"已知双曲线 $C:\dfrac{x^{2}}{a^{2}}-\dfrac{y^{2}}{b^{2}}=1(a>0,b>0)$ 的右焦点为 $F$，$O$ 为坐标原点，以 $OF$ 为直径的圆与双曲线的其中一条渐近线交于点 $A$（除原点外），若 $|OA|=b$，则双曲线 $C$ 的离心率为",
        "选项": {"A": r"$\sqrt{2}$", "B": r"$\sqrt{3}$", "C": r"$2$", "D": r"$3$"},
        "答案": "A",
        "解析": r"因为 $|OF|=c$，且为直径，所以 $\angle OAF=\dfrac{\pi}{2}$，结合渐近线斜率，则 $|OA|=b=a$，$|AF|=b$，所以 $e=\sqrt{2}$，选 A.",
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [1],
        "题干": r"昆明马拉松活动中，将 $4$ 名志愿者分配到 $3$ 个不同的服务点参加志愿工作，每人只去 $1$ 个服务点，每个服务点至少安排 $1$ 人，则不同的安排方法种类数为",
        "选项": {"A": r"$12$", "B": r"$36$", "C": r"$48$", "D": r"$72$"},
        "答案": "B",
        "解析": L(
            r"将 $4$ 名志愿者分配到 $3$ 个不同的服务点参加志愿工作，每人只去 $1$ 个服务点，每个服务点至少安排 $1$ 人，则不同的安排方法种类数为 $C_{4}^{2}A_{3}^{3}=36$，选 B.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [2],
        "题干": r"化简 $\tan 50^{\circ}\cos 20^{\circ}(\tan 40^{\circ}-\sqrt{3})=$",
        "选项": {
            "A": r"$-1$", "B": r"$-\dfrac{\sqrt{3}}{2}$",
            "C": r"$\dfrac{\sqrt{3}}{2}$", "D": r"$1$",
        },
        "答案": "A",
        "解析": L(
            r"$\tan 50^{\circ}\cos 20^{\circ}(\tan 40^{\circ}-\sqrt{3})=\dfrac{\sin 50^{\circ}}{\cos 50^{\circ}}\cos 20^{\circ}\left(\dfrac{\sin 40^{\circ}-\sqrt{3}\cos 40^{\circ}}{\cos 40^{\circ}}\right)=\dfrac{\cos 20^{\circ}\cdot 2\sin(40^{\circ}-60^{\circ})}{\cos 50^{\circ}}$",
            r"$=\dfrac{-2\cos 20^{\circ}\sin 20^{\circ}}{\cos 50^{\circ}}=\dfrac{-\sin 40^{\circ}}{\cos 50^{\circ}}=-1$，选 A.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [2],
        "题干": r"已知 $PA\perp PB$，$PA>PB$，以 $A$，$B$ 为焦点的椭圆经过点 $P$，且该椭圆的离心率大于 $\dfrac{\sqrt{5}}{3}$，则 $\tan\angle ABP$ 的取值范围为",
        "选项": {
            "A": r"$(1,2)$", "B": r"$(2,3)$", "C": r"$(2,+\infty)$", "D": r"$(3,+\infty)$",
        },
        "答案": "C",
        "解析": L(
            r"设 $|PA|=m$，$|PB|=n$，因为 $PA\perp PB$，所以 $|AB|=\sqrt{m^{2}+n^{2}}$，令 $\tan\angle ABP=\dfrac{PA}{PB}=\dfrac{m}{n}=t(t>1)$，",
            r"该椭圆离心率为 $e=\dfrac{c}{a}=\dfrac{2c}{2a}=\dfrac{|AB|}{|PA|+|PB|}=\dfrac{\sqrt{m^{2}+n^{2}}}{m+n}=\dfrac{\sqrt{\left(\dfrac{m}{n}\right)^{2}+1}}{\dfrac{m}{n}+1}=\dfrac{\sqrt{t^{2}+1}}{t+1}>\dfrac{\sqrt{5}}{3}$，解得 $t<\dfrac{1}{2}$ 或 $t>2$，结合 $t>1$，所以 $t>2$，则 $\tan\angle ABP$ 的取值范围为 $(2,+\infty)$，选 C.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [2],
        "题干": r"已知 $z_{1},z_{2}$ 是两个虚数，则下列结论中正确的是",
        "选项": {
            "A": r"若 $z_{1}=\overline{z_{2}}$，则 $z_{1}z_{2}$ 均为实数",
            "B": r"若 $z_{1}+z_{2}$ 为实数，则 $z_{1}=\overline{z_{2}}$",
            "C": r"若 $z_{1}$，$z_{2}$ 均为纯虚数，则 $\dfrac{z_{1}}{z_{2}}$ 为实数",
            "D": r"若 $\dfrac{z_{1}}{z_{2}}$ 为实数，则 $z_{1},z_{2}$ 均为纯虚数",
        },
        "答案": "AC",
        "解析": L(
            r"设 $z_{1}=a+b\mathrm{i}$，$z_{2}=c+d\mathrm{i}$$(a,b,c,d\in\mathbf{R},b\neq 0,d\neq 0)$．",
            r"若 $z_{1}=\overline{z_{2}}$，则 $a=c$，$b+d=0$，所以 $z_{1}z_{2}=a^{2}+b^{2}\in\mathbf{R}$，A 正确；",
            r"若 $z_{1}+z_{2}$ 为实数，则 $b+d=0$，但 $a$ 与 $c$ 不一定相等，B 错误；",
            r"若 $z_{1}$，$z_{2}$ 均为纯虚数，则 $a=c=0$，所以 $\dfrac{z_{1}}{z_{2}}=\dfrac{b}{d}\in\mathbf{R}$，C 正确；",
            r"取 $z_{1}=2+2\mathrm{i}$，$z_{2}=1+\mathrm{i}$，则 $\dfrac{z_{1}}{z_{2}}$ 为实数，但 $z_{1}$，$z_{2}$ 不是纯虚数，D 错误，选 AC.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2],
        "题干": r"已知函数 $f(x)=2\sqrt{3}\sin\omega x\cos\omega x+2\cos^{2}\omega x-1$ $(\omega>0)$，若 $f(x)$ 在区间 $\left(\dfrac{\pi}{2},\pi\right)$ 内不存在对称轴，则 $\omega$ 的值可以为",
        "选项": {
            "A": r"$\dfrac{1}{6}$", "B": r"$\dfrac{1}{3}$",
            "C": r"$\dfrac{7}{12}$", "D": r"$1$",
        },
        "答案": "ABC",
        "解析": L(
            r"$f(x)=2\sqrt{3}\sin\omega x\cos\omega x+2\cos^{2}\omega x-1=\sqrt{3}\sin 2\omega x+\cos 2\omega x=2\sin(2\omega x+\dfrac{\pi}{6})$，",
            r"由 $2\omega x+\dfrac{\pi}{6}=k\pi+\dfrac{\pi}{2}$，$(k\in\mathbf{Z})$，得 $f(x)$ 的对称轴为 $x=\dfrac{k\pi+\dfrac{\pi}{3}}{2\omega}$，$(k\in\mathbf{Z})$，",
            r"由题意知，$\dfrac{k\pi+\dfrac{\pi}{3}}{2\omega}\leqslant\dfrac{\pi}{2}$ 且 $\dfrac{(k+1)\pi+\dfrac{\pi}{3}}{2\omega}\geqslant\pi$，即 $k+\dfrac{1}{3}\leqslant\omega\leqslant\dfrac{3k+4}{6}$，$(k\in\mathbf{Z})$，又因为 $\omega>0$，所以 $k=0$ 或 $k=-1$ 符合题意，从而 $\omega\in\left(0,\dfrac{1}{6}\right]\cup\left[\dfrac{1}{3},\dfrac{2}{3}\right]$，选 ABC.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2],
        "题干": r"已知直线 $l:mx-y-2m+4=0(m\in R)$ 及圆 $C:(x-3)^{2}+(y-5)^{2}=5$，则下列选项中正确的是",
        "选项": {
            "A": "直线 $l$ 过定点 $(2,4)$",
            "B": r"直线 $l$ 截圆 $C$ 所得弦长最小值为 $2\sqrt{3}$",
            "C": "存在 $m$，使得直线 $l$ 与圆 $C$ 相切",
            "D": "存在 $m$，使得圆 $C$ 关于直线 $l$ 对称",
        },
        "答案": "ABD",
        "解析": L(
            r"对于 A，直线 $l:mx-y-2m+4=0(m\in\mathbf{R})$，可得，$m(x-2)-(y-4)=0$，可得直线经过定点 $(2,4)$，A 正确；",
            r"对于 B，圆 $C:(x-3)^{2}+(y-5)^{2}=5$，圆的圆心 $(3,5)$，半径为 $\sqrt{5}$，圆的圆心到定点 $(2,4)$ 的距离为 $\sqrt{(3-2)^{2}+(5-4)^{2}}=\sqrt{2}$，所以直线 $l$ 截圆 $C$ 所得弦长最小值为 $2\sqrt{(\sqrt{5})^{2}-(\sqrt{2})^{2}}=2\sqrt{3}$，B 正确；",
            r"对于 C，因为圆的圆心到定点 $(2,4)$ 的距离为 $\sqrt{2}<\sqrt{5}$（半径），所以直线与圆的位置关系是相交，不存在 $m$，使得直线 $l$ 与圆 $C$ 相切，C 错误；",
            r"对于 D，当直线 $l:mx-y-2m+4=0(m\in\mathbf{R})$ 经过圆的圆心时，存在 $m$，使得圆 $C$ 关于直线 $l$ 对称，D 正确，选 ABD.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [2],
        "题干": r"已知事件 $A$ 和 $B$ 互斥，且 $P(A\cup B)=0.9$，$P(\overline{B})=0.4$，则 $P(A)$ 为 _____．",
        "选项": {},
        "答案": r"$0.3$",
        "解析": L(
            r"由 $P(\overline{B})=0.4$ 得 $P(B)=1-P(\overline{B})=1-0.4=0.6$，又 $P(A\cup B)=P(A)+P(B)=0.9$，所以 $P(A)=P(A\cup B)-P(B)=0.9-0.6=0.3$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [2],
        "题干": r"在 $\triangle ABC$ 中，角 $A$，$B$，$C$ 的对边分别是 $a$，$b$，$c$，已知 $b\sin C=c\sin\dfrac{B}{2}$，则角 $B=$ _____．",
        "选项": {},
        "答案": r"$\dfrac{2\pi}{3}$",
        "解析": L(
            r"由 $b\sin C=c\sin\dfrac{B}{2}$ 得 $\sin B\sin C=\sin C\sin\dfrac{B}{2}$，因为 $\sin C\neq 0$，所以 $\sin B=\sin\dfrac{B}{2}$，即 $2\sin\dfrac{B}{2}\cos\dfrac{B}{2}=\sin\dfrac{B}{2}$，因为 $\sin\dfrac{B}{2}\neq 0$，则因为 $\cos\dfrac{B}{2}=\dfrac{1}{2}$，所以 $\dfrac{B}{2}=\dfrac{\pi}{3}$，从而 $B=\dfrac{2\pi}{3}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [2],
        "题干": r"已知函数 $f(x)=a\mathrm{e}^{x}-\ln x$ 在区间 $(1,2)$ 上单调递增，则 $a$ 的最小值为 _____．",
        "选项": {},
        "答案": r"$\mathrm{e}^{-1}$",
        "解析": L(
            r"依题可知，$f'(x)=a\mathrm{e}^{x}-\dfrac{1}{x}\geqslant 0$ 在 $(1,2)$ 上恒成立，显然 $a>0$，所以 $x\mathrm{e}^{x}\geqslant\dfrac{1}{a}$，",
            r"设 $g(x)=x\mathrm{e}^{x},x\in(1,2)$，所以 $g'(x)=(x+1)\mathrm{e}^{x}>0$，所以 $g(x)$ 在 $(1,2)$ 上单调递增，",
            r"$g(x)>g(1)=\mathrm{e}$，故 $\mathrm{e}\geqslant\dfrac{1}{a}$，即 $a\geqslant\dfrac{1}{\mathrm{e}}=\mathrm{e}^{-1}$，即 $a$ 的最小值为 $\mathrm{e}^{-1}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3],
        "题干": L(
            r"已知数列 $\{a_{n}\}$ 中，$a_{1}=1$，$a_{n+1}=a_{n}+2n$，",
            r"(1) 求 $a_{n}$；",
            r"(2) 若 $b_{n}=a_{n}+2n-1$，$\left\{\dfrac{1}{b_{n}}\right\}$ 的前 $n$ 项和为 $S_{n}$，证明：$S_{n}<1$．",
        ),
        "选项": {},
        "答案": L(
            r"(1) $a_{n}=n^{2}-n+1$；(2) 证得 $S_{n}=1-\dfrac{1}{n+1}<1$．",
        ),
        "解析": L(
            r"(1) 由题意，$a_{n}-a_{n-1}=2(n-1)$，$a_{n-1}-a_{n-2}=2(n-2)$，$\cdots$，$a_{2}-a_{1}=2$，",
            r"累加得，$a_{n}-a_{1}=2(1+2+\cdots+n-1)=n(n-1)$，则 $a_{n}=n^{2}-n+1$，经检验 $n=1$ 时也成立．",
            r"(2) 由题意 $b_{n}=a_{n}+2n-1=n^{2}+n$，$\dfrac{1}{b_{n}}=\dfrac{1}{n(n+1)}=\dfrac{1}{n}-\dfrac{1}{n+1}$，",
            r"$S_{n}=\dfrac{1}{b_{1}}+\dfrac{1}{b_{2}}+\cdots+\dfrac{1}{b_{n}}=1-\dfrac{1}{2}+\dfrac{1}{2}-\dfrac{1}{3}+\cdots+\dfrac{1}{n}-\dfrac{1}{n+1}=1-\dfrac{1}{n+1}$，",
            r"因为 $n\in\mathbf{N}^{*}$，$\dfrac{1}{n+1}>0$，所以 $S_{n}<1$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"已知抛物线 $E:y^{2}=4x$ 的焦点为 $F$，过点 $A(0,y_{0})$ 的直线 $l$ 与 $E$ 相交于 $B(x_{1},y_{1})$，$C(x_{2},y_{2})$ 两点，且 $y_{0}>0$，",
            r"(1) 若 $F$ 为线段 $AC$ 的中点，",
            r"（i）求直线 $l$ 的斜率；",
            r"（ii）求 $|AC|$；",
            r"(2) 若点 $P(x_{3},2y_{0})$ 在抛物线 $E$ 上，满足 $BP\perp BC$，求 $y_{2}$ 取值范围．",
        ),
        "选项": {},
        "答案": L(
            r"(1)（i）直线 $l$ 的斜率为 $-2\sqrt{2}$；（ii）$|AC|=6$；(2) $y_{2}$ 取值范围为 $\left(-\infty,-\dfrac{8}{3}\right]$．",
        ),
        "解析": L(
            r"(1)（i）由题意知，焦点 $F(1,0)$，因为 $F$ 为线段 $AC$ 的中点，所以 $1=\dfrac{0+x_{2}}{2}$，即 $x_{2}=2$，",
            r"所以 $y_{2}=-2\sqrt{2}$，即 $C(2,-2\sqrt{2})$，所以直线 $l$ 的斜率为 $k_{l}=\dfrac{0+2\sqrt{2}}{1-2}=-2\sqrt{2}$．",
            r"（ii）$|AC|=2|FC|=2\sqrt{1+(2\sqrt{2})^{2}}=6$．",
            r"(2) 由题意知，直线 $BC$ 的斜率为 $k_{BC}=\dfrac{y_{2}-y_{1}}{x_{2}-x_{1}}=\dfrac{y_{2}-y_{1}}{\frac{y_{2}^{2}}{4}-\frac{y_{1}^{2}}{4}}=\dfrac{4}{y_{2}+y_{1}}$，同理直线 $BP$ 的斜率为 $k_{BP}==\dfrac{4}{y_{1}+2y_{0}}$，",
            r"因为 $BP\perp BC$，所以 $k_{BC}k_{BP}=-1$，所以 $2y_{0}=\dfrac{-16-y_{1}^{2}-y_{1}y_{2}}{y_{1}+y_{2}}$，",
            r"又因为直线 $BC$ 的方程为 $y-y_{1}==\dfrac{4}{y_{1}+y_{2}}(x-x_{1})$，所以点 $A(0,y_{0})$ 在直线 $BC$ 上，",
            r"所以 $y_{0}-y_{1}==\dfrac{4}{y_{1}+y_{2}}(-x_{1})=\dfrac{-y_{1}^{2}}{y_{1}+y_{2}}$，所以 $2y_{0}=\dfrac{2y_{1}y_{2}}{y_{1}+y_{2}}$，所以 $\dfrac{2y_{1}y_{2}}{y_{1}+y_{2}}=\dfrac{-16-y_{1}^{2}-y_{1}y_{2}}{y_{1}+y_{2}}$，",
            r"所以 $y_{2}=-\dfrac{16}{3y_{1}}-\dfrac{y_{1}}{3}$，因为 $y_{1}>0$，所以 $y_{2}=-(\dfrac{16}{3y_{1}}+\dfrac{y_{1}}{3})\leqslant -2\sqrt{\dfrac{16}{9}}=-\dfrac{8}{3}$，当且仅当 $\dfrac{16}{3y_{1}}=\dfrac{y_{1}}{3}$，",
            r"即 $y_{1}=4$ 满足，所以 $y_{2}$ 取值范围为 $\left(-\infty,-\dfrac{8}{3}\right]$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"已知函数 $f(x)=x-1-\ln x$．",
            r"(1) 证明：$\ln x\leqslant x-1$；",
            r"(2) 证明：$\sum\limits_{i=1}^{n}\dfrac{1}{i}>\ln(n+1)$$(n\in\mathbf{N}_{+})$；",
            r"(3) 若 $f(x)\geqslant mx-x\mathrm{e}^{x}$$(m\in\mathbf{R})$ 恒成立，求实数 $m$ 的取值范围．",
        ),
        "选项": {},
        "答案": L(
            r"(1)(2) 见解析；(3) 实数 $m$ 的取值范围是 $(-\infty,2]$．",
        ),
        "解析": L(
            r"(1) 因为函数 $f(x)=x-1-\ln x$ $(x>0)$，",
            r"所以 $f'(x)=1-\dfrac{1}{x}$，$f'(x)\leqslant 0\Leftrightarrow 0<x\leqslant 1$，$f'(x)\geqslant 0\Leftrightarrow x\geqslant 1$，",
            r"所以 $f(x)$ 在 $(0,1)$ 单调递减，在 $(1,+\infty)$ 单调递增，",
            r"所以 $f(x)\geqslant f(1)=0$，所以 $f(x)=x-1-\ln x\geqslant 0$ 恒成立，所以 $\ln x\leqslant x-1$．",
            r"(2) 由 (1) 知 $f(x)=x-1-\ln x\geqslant 0$$(a\in\mathbf{R})$ 恒成立，所以 $x-1\geqslant\ln x$，当且仅当 $x=1$ 时等号成立，",
            r"所以 $x\geqslant\ln(x+1)$，当且仅当 $x=0$ 时等号成立，所以 $\dfrac{1}{i}>\ln\left(1+\dfrac{1}{i}\right)$（其中 $i=1,2,3\cdots n$，$n\in\mathbf{N}_{+}$）．",
            r"即 $\dfrac{1}{i}>\ln\left(1+\dfrac{1}{i}\right)$，则 $\sum\limits_{i=1}^{n}\dfrac{1}{i}>\sum\limits_{i=1}^{n}\ln\dfrac{1+i}{i}=\ln\left(\dfrac{2}{1}\times\dfrac{3}{2}\times\cdots\times\dfrac{n+1}{n}\right)=\ln(n+1)$，",
            r"所以 $\sum\limits_{i=1}^{n}\dfrac{1}{i}>\ln(n+1)$$(n\in\mathbf{N}_{+})$．",
            r"(3) $f(x)\geqslant mx-x\mathrm{e}^{x}$$(m\in\mathbf{R})$ 恒成立，",
            r"即 $x-\ln x+x\mathrm{e}^{x}-1\geqslant mx$ 在 $x\in(0,+\infty)$ 恒成立，",
            r"即 $m\leqslant\dfrac{x+x\mathrm{e}^{x}-\ln x-1}{x}=1+\mathrm{e}^{x}-\dfrac{\ln x}{x}-\dfrac{1}{x}$ 在 $(0,+\infty)$ 恒成立，令 $h(x)=1+\mathrm{e}^{x}-\dfrac{\ln x}{x}-\dfrac{1}{x}$ $(x>0)$，",
            r"所以 $h'(x)=\mathrm{e}^{x}+\dfrac{1}{x^{2}}+\dfrac{\ln x-1}{x^{2}}=\mathrm{e}^{x}+\dfrac{\ln x}{x^{2}}$，",
            r"令 $h'(x)>0$，即 $\mathrm{e}^{x}+\dfrac{\ln x}{x^{2}}>0$，整理得：$x^{2}\mathrm{e}^{x}+\ln x>0$",
            r"令 $\varphi(x)=x^{2}\mathrm{e}^{x}+\ln x$ $(x>0)$，所以 $\varphi'(x)=(x^{2}+2x)\mathrm{e}^{x}+\dfrac{1}{x}>0$ 在 $(0,+\infty)$ 恒成立",
            r"所以 $\varphi(x)$ 在 $(0,+\infty)$ 上单调递增，因为 $\varphi(1)=\mathrm{e}+0=\mathrm{e}>0$，$\varphi(\dfrac{1}{\mathrm{e}})=(\dfrac{1}{\mathrm{e}})^{2}\times\mathrm{e}^{\frac{1}{\mathrm{e}}}-1=\mathrm{e}^{\frac{1}{\mathrm{e}}-2}-1<0$",
            r"所以 $\exists x_{0}\in(\dfrac{1}{\mathrm{e}},1)$ 使得 $\varphi(x_{0})=0$，即 $x_{0}^{2}\mathrm{e}^{x_{0}}+\ln x_{0}=0$",
            r"当 $x\in(0,x_{0})$ 时，$\varphi(x)<0$，当 $x\in(x_{0},+\infty)$ 时，$\varphi(x)>0$，",
            r"所以当 $x\in(0,x_{0})$ 时，$h'(x)<0$，当 $x\in(x_{0},+\infty)$ 时，$h'(x)>0$，",
            r"所以 $h(x)$ 在 $x\in(0,x_{0})$ 上单调递减，在 $x\in(x_{0},+\infty)$ 上单调递增，",
            r"所以 $h(x)_{\min}=h(x_{0})=1+\mathrm{e}^{x_{0}}-\dfrac{\ln x_{0}}{x_{0}}-\dfrac{1}{x_{0}}$，因为 $x_{0}^{2}\mathrm{e}^{x_{0}}+\ln x_{0}=0$，所以 $x_{0}\mathrm{e}^{x_{0}}=\dfrac{-\ln x_{0}}{x_{0}}=\ln\dfrac{1}{x_{0}}\cdot\mathrm{e}^{\ln\frac{1}{x_{0}}}$，",
            r"令函数 $y=x\mathrm{e}^{x}$，因为 $y=x\mathrm{e}^{x}$ 在 $(0,+\infty)$ 上单调递增，",
            r"所以 $x_{0}=\ln\dfrac{1}{x_{0}}$，即 $\mathrm{e}^{x_{0}}=\dfrac{1}{x_{0}}$",
            r"所以 $h(x)_{\min}=h(x_{0})=1+\mathrm{e}^{x_{0}}-\dfrac{\ln x_{0}}{x_{0}}-\dfrac{1}{x_{0}}=1+\dfrac{\ln x_{0}}{\ln x_{0}}=2$",
            r"所以 $m\leqslant 2$，所以实数 $m$ 的取值范围是 $(-\infty,2]$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
]

pending = [
    {
        "题号": 15, "题型": "detailed_answer", "页码": [3], "类型": "table",
        "原文": L(
            r"北京冬奥会的成功举办，不仅让世界进一步了解新时代的中国，而且极大促进了全国群众参与冰雪运动，此后每年冬季，全国多地群众都会积极参与冰雪运动．某城市为调查居民对冰雪运动的了解情况，随机抽取了该市男女市民各 $60$ 人进行统计，统计结果如下表：（单位：人）",
            r"已知从参与调查的男性市民中随机抽取一名，他了解冰雪运动的概率为 $\dfrac{3}{4}$．",
            r"(1) 求表中 $m$，$n$，$P$，$q$ 的值；",
            r"(2) 根据小概率值 $\alpha=0.05$ 的独立性检验，分析并判断该市居民对冰雪运动的了解是否与性别有关联．",
        ),
        "说明": L(
            r"试卷卷面第 3 页 #15 印着两张表格（均无表号），按「带图/带表题不录正文」，本题未进成品。",
            r"第一张是 $2\times 2$ 列联表，四行四列：第 1 行表头依次为「性别」、「冰雪运动」（跨两列合并）、「合计」；第 2 行在「冰雪运动」下分「了解」「不了解」两个子列；第 3 行「男」$=m$、$n$、$60$；第 4 行「女」$=p$、$q$、$60$；第 5 行「合计」$=80$、$40$、$120$。",
            r"第二张是临界值表，两行四列：第 1 行 $P(\chi^{2}\geqslant k)$ 依次 $0.050$、$0.010$、$0.005$；第 2 行 $k$ 依次 $3.841$、$6.635$、$7.879$。表格左边还印着附：$\chi^{2}=\dfrac{n(ad-bc)^{2}}{(a+b)(c+d)(a+c)(b+d)}$，$n=a+b+c+d$。",
            r"参考答案（合并 PDF 第 7 页，答案册页脚自标「3」）给的全解析结果：(1) $m=60\times\dfrac{3}{4}=45$，所以 $n=15$，$p=35$，$q=25$；(2) 零假设 $H_{0}$：该市市民对冰雪运动的了解与性别无关联，$\chi^{2}=\dfrac{120\times(45\times 25-35\times 15)^{2}}{60\times 60\times 80\times 40}=\dfrac{15}{4}=3.75<3.841$，因此根据小概率值 $\alpha=0.05$ 的独立性检验，不能判断该市居民对冰雪运动的了解与性别有关联。",
            r"另：题干里第 4 个字母卷面印作大写「$P$」（「求表中 $m$，$n$，$P$，$q$ 的值」），而表格里那一格印的是小写 $p$，标答也按小写 $p=35$ 给值；按「内容一个字都不许改」照原样登记，未统一大小写。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 17, "题型": "detailed_answer", "页码": [4], "类型": "figure",
        "原文": L(
            r"如图，几何体是由两个共底面 $ABCD$ 的四棱锥拼接而成，$P$，$D$，$S$ 共线，且 $PS\perp$ 平面 $ABCD$，正方形 $ABCD$ 的边长为 $2$，$PD=DS=2$．",
            r"(1) 求证：$PC\perp SB$；",
            r"(2) 求平面 $PAB$ 与平面 $SBC$ 的夹角的大小．",
        ),
        "说明": L(
            r"题干以「如图」起头，试卷卷面第 4 页 #17 右侧随题印着配图（无图号）：上下两个共底面 $ABCD$ 的四棱锥，$P$ 在最上、$S$ 在最下，正方形 $ABCD$ 中 $D$ 在左上、$C$ 在右上、$A$ 在左、$B$ 在右；$PA$、$PB$、$PC$、$SA$、$SB$、$SC$、$AB$、$BC$ 画实线，$PD$、$DS$（即 $PS$ 一段）、$AD$、$DC$、$AC$ 画虚线，$BC$ 一侧另有一段描成蓝色。按规矩不录正文，故本题未进成品。",
            r"参考答案（合并 PDF 第 7 页）给的全解析结果：(1) 由 $PS\perp$ 平面 $ABCD$ 得 $BC\perp PD$，又 $BC\perp CD$、$PD\cap CD=D$，故 $BC\perp$ 平面 $PDC$，得 $BC\perp PC$；由正方形边长 $2$、$PD=DS=2$ 得 $PC=CS=2\sqrt{2}$、$PS=4$，于是 $PC^{2}+CS^{2}=PS^{2}$，得 $PC\perp CS$，又 $BC\cap SC=C$，故 $PC\perp$ 平面 $SCB$，所以 $PC\perp SB$。(2) 以 $D$ 为原点、$DA$、$DC$、$DP$ 分别为 $x$、$y$、$z$ 轴建系（标答另配一张无图号建系图，图上多了 $x$、$y$、$z$ 三条带箭头坐标轴，$z$ 轴向上穿过 $P$、$y$ 轴向右穿过 $C$、$x$ 轴向左下穿过 $A$，其余顶点标注与试卷原图一致），得 $P(0,0,2)$、$C(0,2,0)$、$A(2,0,0)$、$B(2,2,0)$，取平面 $SCB$ 的法向量为 $\overrightarrow{PC}=(0,2,-2)$，设平面 $PAB$ 的法向量 $\vec{n}=(x,y,z)$ 由 $\begin{cases}\vec{n}\cdot\overrightarrow{AB}=0\\ \vec{n}\cdot\overrightarrow{AP}=0\end{cases}$ 即 $\begin{cases}2y=0\\ -2x+2z=0\end{cases}$，取 $x=1$ 得 $\vec{n}=(1,0,1)$，$\cos<\overrightarrow{PC},\vec{n}>=\dfrac{-2}{2\sqrt{2}\times\sqrt{2}}=-\dfrac{1}{2}$，所以平面 $PAB$ 与平面 $SBC$ 的夹角的大小为 $60^{\circ}$。",
            r"标答 (2) 给的建系与各点坐标经独立复核自洽（$DA$、$DC$、$DP$ 两两垂直，$PC\perp$ 平面 $SCB$ 亦成立），无疑点。交人工把两张图补进成品。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [1], "类型": "print-suspect",
        "原文": r"本试卷共 4 页，22 题．全卷满分 150 分．考试用时 120 分钟．",
        "说明": L(
            r"试卷卷面第 1 页卷首语印作「本试卷共 $4$ 页，$22$ 题」，但全卷实际只有 $19$ 题：四个大题的卷面自述分别是「一、单项选择题：本题共 $8$ 小题」（$1$–$8$）、「二、多项选择题：本题共 $3$ 小题」（$9$–$11$）、「三、填空题：本题共 $3$ 小题」（$12$–$14$）、「四、解答题：本题共 $5$ 小题，其中第 $15$ 题 $13$ 分，第 $16$、$17$ 题 $15$ 分，第 $18$、$19$ 题 $17$ 分，共 $77$ 分」（$15$–$19$），$8+3+3+5=19$，且参考答案（合并 PDF 第 5–9 页）也只编到 $19$ 题、没有 $20$–$22$ 题。",
            r"「共 $4$ 页」与卷页脚「数学试卷·第 N 页（共 4 页）」一致，所以只有题数「$22$」对不上（疑为沿用别卷模板未改）。按「内容一个字都不许改」，未替它把 $22$ 改成 $19$；卷首语本身属考试说明、按规范不进题干，故只登记在此。",
        ),
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4], "类型": "print-suspect",
        "原文": r"同理直线 $BP$ 的斜率为 $k_{BP}==\dfrac{4}{y_{1}+2y_{0}}$，……又因为直线 $BC$ 的方程为 $y-y_{1}==\dfrac{4}{y_{1}+y_{2}}(x-x_{1})$，……所以 $y_{0}-y_{1}==\dfrac{4}{y_{1}+y_{2}}(-x_{1})=\dfrac{-y_{1}^{2}}{y_{1}+y_{2}}$，",
        "说明": L(
            r"参考答案（合并 PDF 第 8 页）#18 (2) 这一整段里有三处把等号印成了两个连续的等号「$==$」：$k_{BP}==$、$y-y_1==$、$y_0-y_1==$。同一小问其余各式（如 $k_{BC}=\dfrac{4}{y_{2}+y_{1}}$、$2y_{0}=\dfrac{2y_{1}y_{2}}{y_{1}+y_{2}}$）都只有一个等号，可确认是排印重复。",
            r"按「内容一个字都不许改」，成品解析照标答原样保留这三处「$==$」，没有删掉多余的等号。另需说明：把这三处按单个等号读，整段推导是自洽的（由 $k_{BC}k_{BP}=-1$ 得 $2y_{0}=\dfrac{-16-y_{1}^{2}-y_{1}y_{2}}{y_{1}+y_{2}}$，与 $2y_{0}=\dfrac{2y_{1}y_{2}}{y_{1}+y_{2}}$ 联立解得 $y_{2}=-\dfrac{16}{3y_{1}}-\dfrac{y_{1}}{3}$，再用均值不等式得 $y_{2}\leqslant -\dfrac{8}{3}$，等号在 $y_{1}=4$ 时取到），末答 $\left(-\infty,-\dfrac{8}{3}\right]$ 不受影响。",
        ),
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4], "类型": "print-suspect",
        "原文": L(
            r"(2) 由 (1) 知 $f(x)=x-1-\ln x\geqslant 0$$(a\in\mathbf{R})$ 恒成立，所以 $x-1\geqslant\ln x$，当且仅当 $x=1$ 时等号成立，",
            r"所以 $h(x)_{\min}=h(x_{0})=1+\mathrm{e}^{x_{0}}-\dfrac{\ln x_{0}}{x_{0}}-\dfrac{1}{x_{0}}=1+\dfrac{\ln x_{0}}{\ln x_{0}}=2$",
        ),
        "说明": L(
            r"参考答案（合并 PDF 第 8–9 页）#19 解析里有两处排印疑点，均照原样录入、没有改动：",
            r"(a) (2) 开头「由 (1) 知 $f(x)=x-1-\ln x\geqslant 0$$(a\in\mathbf{R})$ 恒成立」中的「$(a\in\mathbf{R})$」无所指——本题全卷只有参数 $m$，(1)(2) 两问里没有任何 $a$，(1) 的结论也只是 $x-1-\ln x\geqslant 0$$(x>0)$。疑为沿用含参题模板留下的残迹。",
            r"(b) (3) 倒数第二行「$h(x)_{\min}=h(x_{0})=1+\mathrm{e}^{x_{0}}-\dfrac{\ln x_{0}}{x_{0}}-\dfrac{1}{x_{0}}=1+\dfrac{\ln x_{0}}{\ln x_{0}}=2$」，中间那步写成「$1+\dfrac{\ln x_{0}}{\ln x_{0}}$」，与前一项之间缺了代入过程的痕迹：按上一行 $\mathrm{e}^{x_{0}}=\dfrac{1}{x_{0}}$ 与 $x_{0}^{2}\mathrm{e}^{x_{0}}+\ln x_{0}=0$ 推出的 $\ln x_{0}=-x_{0}$，正确展开应是 $1+\dfrac{1}{x_{0}}-\dfrac{-x_{0}}{x_{0}}-\dfrac{1}{x_{0}}=1+1=2$，末值 $2$ 本身无误。",
        ),
    },
]

(OUT / (NAME + ".成品.json")).write_text(
    json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
(OUT / (NAME + ".待复核.json")).write_text(
    json.dumps(pending, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("成品", len(recs), "待复核", len(pending))
