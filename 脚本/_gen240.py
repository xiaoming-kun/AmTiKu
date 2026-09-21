#!/usr/bin/env python3
r"""生成 #240 2026届深圳一模数学 的成品 + 待复核。

所有含反斜杠的正文一律用 r"..."，防止 \v/\f/\b/\a/\e/\r 被 Python 当转义吃掉。
"""
import json
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "数据/录题/输出_v2"
NO = 240
NAME = "2026届深圳一模数学"

recs = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1],
        "题干": r"样本数据 $4,6,10,16$ 的平均数为",
        "选项": {"A": r"$6$", "B": r"$7$", "C": r"$8$", "D": r"$9$"},
        "答案": "D", "解析": "解析无",
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1],
        "题干": r"复数 $z=\sin 1+\mathrm{i}\cos 1$，则 $|z|=$",
        "选项": {"A": r"$1$", "B": r"$2$", "C": r"$3$", "D": r"$4$"},
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1],
        "题干": r"已知抛物线 $y^2=4x$ 上的一点 $M$ 的横坐标为 $1$，则点 $M$ 到焦点的距离为",
        "选项": {"A": r"$1$", "B": r"$2$", "C": r"$3$", "D": r"$4$"},
        "答案": "B", "解析": "解析无",
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [1],
        "题干": r"函数 $f(x)=\sin(\omega x-\dfrac{\pi}{4})(\omega>0)$ 的最小正周期为 $\pi$，其图象的对称中心可以为",
        "选项": {
            "A": r"$(\dfrac{5\pi}{8},0)$",
            "B": r"$(\dfrac{\pi}{2},0)$",
            "C": r"$(\dfrac{3\pi}{8},0)$",
            "D": r"$(\dfrac{\pi}{4},0)$",
        },
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1],
        "题干": r"设 $f(x)$ 是定义在 $\mathbf{R}$ 上的奇函数，$f(2+x)=f(-x)$，$f(-1)=1$，则 $f(9)=$",
        "选项": {"A": r"$-1$", "B": r"$0$", "C": r"$1$", "D": r"$2$"},
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [1],
        "题干": r"已知 $\cos\theta=\dfrac{4}{5}$，$\theta\in(0,\dfrac{\pi}{2})$，则 $\sin(\theta-\dfrac{\pi}{4})=$",
        "选项": {
            "A": r"$-\dfrac{\sqrt{2}}{5}$",
            "B": r"$-\dfrac{\sqrt{2}}{10}$",
            "C": r"$\dfrac{\sqrt{2}}{10}$",
            "D": r"$\dfrac{\sqrt{2}}{5}$",
        },
        "答案": "B", "解析": "解析无",
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [2],
        "题干": r"已知向量 $\vec{a}=(2,4)$，$\vec{a}\cdot\vec{b}=10$，则向量 $\vec{b}$ 在向量 $\vec{a}$ 上的投影向量为",
        "选项": {
            "A": r"$(4,2)$",
            "B": r"$(2,4)$",
            "C": r"$(\sqrt{2},2\sqrt{2})$",
            "D": r"$(1,2)$",
        },
        "答案": "D", "解析": "解析无",
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [2],
        "题干": r"若实数 $x,y,z$ 满足 $\sqrt{x}=2^{-y}=-\log_2 z$，则 $x,y,z$ 的大小关系不可能是",
        "选项": {
            "A": r"$z>x>y$",
            "B": r"$z>y>x$",
            "C": r"$y>x>z$",
            "D": r"$y>z>x$",
        },
        "答案": "C", "解析": "解析无",
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [2],
        "题干": r"在正三棱台 $ABC-A_1B_1C_1$ 中，$D$ 为 $BC$ 的中点，则",
        "选项": {
            "A": r"$A_1D\parallel AB$",
            "B": r"$AD\parallel$ 平面 $A_1B_1C_1$",
            "C": r"$AD\perp A_1C_1$",
            "D": r"$BC\perp$ 平面 $AA_1D$",
        },
        "答案": "BD", "解析": "解析无",
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2],
        "题干": r"设双曲线 $\Gamma:x^2-y^2=1$ 的左、右焦点分别为 $F_1$，$F_2$．过 $F_1$ 的直线 $l$ 与 $\Gamma$ 的两条渐近线的交点分别为 $A$、$B$，$A$ 为 $F_1B$ 的中点，$O$ 为坐标原点．则",
        "选项": {
            "A": r"$\triangle AOB$ 是直角三角形",
            "B": r"$\triangle BOF_2$ 是等腰直角三角形",
            "C": r"$|AB|=\sqrt{5}$",
            "D": r"直线 $l$ 的斜率为 $\pm\dfrac{1}{3}$",
        },
        "答案": "ABD", "解析": "解析无",
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2],
        "题干": r"将一枚质地均匀的硬币连续投掷 $n$ 次，定义随机变量 $X_n$ 为结果中连续出现正面的最大次数．若始终未出现正面，规定 $X_n=0$．例如，投掷结果为“正反正正”时，连续出现正面的次数为 $1$ 和 $2$，故 $X_4=2$．则",
        "选项": {
            "A": r"$P(X_2=2)=\dfrac{1}{4}$",
            "B": r"$E(X_3)=\dfrac{11}{8}$",
            "C": r"$P(X_6=4)=[P(X_3=2)]^2$",
            "D": r"$E(X_n)\leqslant\dfrac{n}{2}$",
        },
        "答案": "ABD", "解析": "解析无",
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [2],
        "题干": r"在 $\triangle ABC$ 中，已知 $A=\dfrac{\pi}{4}$，$B=\dfrac{5\pi}{12}$，$a=2$，则 $c=$ ________．",
        "选项": {},
        "答案": r"$\sqrt{6}$", "解析": "解析无",
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [2],
        "题干": r"已知等差数列 $\{a_n\}$ 的前 $n$ 项和为 $S_n$，且 $3S_5=8S_3$，$S_4=26$，则 $a_5=$ ________．",
        "选项": {},
        "答案": r"$14$", "解析": "解析无",
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [2],
        "题干": r"已知 $a_1,a_2,\cdots,a_8$ 是 $8$ 个正整数，记 $S=\{a_{i_1}+a_{i_2}+\cdots+a_{i_7}|1\leqslant i_1<i_2<\cdots<i_7\leqslant8\}$，其中 $i_1,i_2,\cdots,i_7\in\mathbf{N}^*$，若 $S=\{82,83,84,85,86,87,89\}$，则这 $8$ 个正整数中的最大数与最小数的和为________．",
        "选项": {},
        "答案": r"$23$", "解析": "解析无",
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [2],
        "题干": r"已知数列 $\{a_n\}$ 是等比数列，$a_1=2$，$a_2=4$，数列 $\{b_n\}$ 满足：$a_1b_1+a_2b_2+\cdots+a_nb_n=n\cdot a_{n+1}$．"
        + "\n" + r"(1) 求 $\{a_n\},\{b_n\}$ 的通项公式；"
        + "\n" + r"(2) 求数列 $\{\dfrac{1}{b_n\cdot b_{n+1}}\}$ 的前 $n$ 项和 $S_n$．",
        "选项": {},
        "答案": r"(1) $a_n=2^n$（$n\in\mathbf{N}^*$），$b_n=n+1$（$n\in\mathbf{N}^*$）；(2) $S_n=\dfrac{n}{2n+4}$",
        "解析": r"解：(1) 设等比数列 $\{a_n\}$ 的公比为 $q$，则 $q=\dfrac{a_2}{a_1}=2$，所以 $a_n=2^n$，$n\in\mathbf{N}^*$，因为 $2b_1+2^2b_2+\cdots+2^nb_n=n\cdot2^{n+1}$，当 $n\geqslant2$ 时，$2b_1+2^2b_2+\cdots+2^{n-1}b_{n-1}=(n-1)\cdot2^n$，两式相减得 $2^n\cdot b_n=(n+1)\cdot2^n$，则 $n\geqslant2$ 时，$b_n=n+1$；当 $n=1$ 时，$b_1=2$ 符合该式；所以 $b_n=n+1$，$n\in\mathbf{N}^*$．"
        + "\n" + r"(2) 由于 $\dfrac{1}{b_n\cdot b_{n+1}}=\dfrac{1}{(n+1)\cdot(n+2)}=\dfrac{1}{n+1}-\dfrac{1}{n+2}$，$S_n=(\dfrac{1}{2}-\dfrac{1}{3})+(\dfrac{1}{3}-\dfrac{1}{4})+\cdots+(\dfrac{1}{n+1}-\dfrac{1}{n+2})=\dfrac{1}{2}-\dfrac{1}{n+2}=\dfrac{n}{2n+4}$，所以 $S_n=\dfrac{n}{2n+4}$．",
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3],
        "题干": r"某智能系统用于处理判断题（答案只有“对”和“错”），系统内设有两个独立的预测模型，分别记为模型甲和模型乙．系统的答案输出规则如下：系统首先同时向模型甲与模型乙提问，若两者答案一致，则直接输出该答案；若两者答案不一致，系统将重新向模型甲提问一次，并以模型甲此次给出的答案作为最终输出答案．已知模型甲回答正确的概率为 $p$（$0<p<1$），模型乙回答正确的概率为 $0.75$，假设各模型每次回答相互独立．"
        + "\n" + r"(1) 当 $p=0.85$ 时，求系统第一次同时向两个模型提问时，两个模型答案不同的概率；"
        + "\n" + r"(2) 若系统最终输出正确答案的概率不低于 $0.88$，求 $p$ 的最小值．",
        "选项": {},
        "答案": r"(1) $0.325$；(2) $p$ 的最小值为 $0.8$",
        "解析": r"解：(1) 不妨设事件 $A=$“模型甲回答正确”，事件 $B=$“模型乙回答正确”，则 $\overline{A}=$“模型甲回答错误”，$\overline{B}=$“模型乙回答错误”，由于 $A$ 与 $B$ 相互独立，$A$ 与 $\overline{B}$，$\overline{A}$ 与 $B$，$\overline{A}$ 与 $\overline{B}$ 都相互独立，由题意可得，$P(A)=p=0.85$，$P(B)=0.75$，$P(\overline{A})=1-0.85=0.15$，$P(\overline{B})=1-0.75=0.25$，分析可得，“在第一次提问中两个模型答案不同”的概率为 $P(A\overline{B}\cup\overline{A}B)$，且 $A\overline{B}$ 与 $\overline{A}B$ 互斥，根据概率的加法公式和事件的独立性定义，得 $P(A\overline{B}\cup\overline{A}B)=P(A\overline{B})+P(\overline{A}B)=P(A)P(\overline{B})+P(\overline{A})P(B)=0.85\times0.25+0.15\times0.75=0.325$，故在第一次提问中两个模型答案不同的概率为 $0.325$．"
        + "\n" + r"(2) 系统最终输出正确答案可分为第一次输出正确答案和第二次输出正确答案，系统第一次输出正确答案的概率为：$P(AB)=0.75p$，由（1）可知，在第一次提问中两个模型答案不同的概率为：$P(A\overline{B}\cup\overline{A}B)=P(A\overline{B})+P(\overline{A}B)=P(A)P(\overline{B})+P(\overline{A})P(B)=0.25p+0.75(1-p)=0.75-0.5p$，系统第二次输出正确答案的概率为：$P(A\overline{B}\cup\overline{A}B)P(A)=(0.75-0.5p)\cdot p=-0.5p^2+0.75p$，设系统最终输出正确答案的概率为 $P'$，则 $P'=0.75p+(-0.5p^2+0.75p)=-0.5p^2+1.5p$，于是 $P'\geqslant0.88$，解得 $0.8\leqslant p\leqslant2.2$，又由 $p\in(0,1)$，于是 $0.8\leqslant p<1$，则 $p$ 的最小值为 $0.8$．",
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4],
        "题干": r"已知函数 $f(x)=\ln x-a\sqrt{x+1}+4$．"
        + "\n" + r"(1) 当 $a=\sqrt{3}$ 时，求 $f(x)$ 的单调区间；"
        + "\n" + r"(2) 若 $f(x)$ 有两个零点．"
        + "\n" + r"(i) 求 $a$ 的取值范围；"
        + "\n" + r"(ii) 证明：$f(x)<\dfrac{2}{\sqrt{a^2+1}-1}$．",
        "选项": {},
        "答案": r"(1) 单调递增区间为 $(0,2)$，单调递减区间为 $(2,+\infty)$；(2)(i) $a\in(0,2\sqrt{2})$；(ii) 证明见解析",
        "解析": r"解：(1) 由于 $f'(x)=\dfrac{1}{x}-\dfrac{\sqrt{3}}{2\sqrt{x+1}}=\dfrac{2\sqrt{x+1}-\sqrt{3}x}{2x\sqrt{x+1}}$（$x>0$）令 $f'(x)=0$，$x=2$，令 $f'(x)>0$，$x\in(0,2)$，$f(x)$ 在 $(0,2)$ 上单调递增；令 $f'(x)<0$，$x\in(2,+\infty)$，$f(x)$ 在 $(2,+\infty)$ 上单调递减；所以 $f(x)$ 的单调递增区间为 $(0,2)$，单调递减区间为 $(2,+\infty)$．"
        + "\n" + r"(2) 由于 $f'(x)=\dfrac{1}{x}-\dfrac{a}{2\sqrt{x+1}}=\dfrac{2\sqrt{x+1}-ax}{2x\sqrt{x+1}}=\dfrac{-a^2x^2+4x+4}{2x\sqrt{x+1}\cdot(2\sqrt{x+1}+ax)}$（$x>0$）若 $a\leqslant0$，$2\sqrt{x+1}-ax>0$，$f'(x)>0$，于是 $f(x)$ 在 $(0,+\infty)$ 上单调递增，至多与 $x$ 轴只有一个交点，矛盾，所以 $a>0$，令 $f'(x)=0$，则等价于 $a^2x^2-4x-4=0$，易得 $\Delta=16+16a^2>0$，因为 $x>0$，则 $x=\dfrac{2(1+\sqrt{1+a^2})}{a^2}$，令 $x_0=\dfrac{2(1+\sqrt{1+a^2})}{a^2}$，则 $f(x)$ 在 $(0,x_0)$ 上单调递增，在 $(x_0,+\infty)$ 上单调递减，则 $f(x)_{\max}=f(x_0)=\ln x_0-a\sqrt{x_0+1}+4$，因为 $a^2x_0^2-4x_0-4=0$ 即 $a^2=\dfrac{4(x_0+1)}{x_0^2}$，所以 $f(x)_{\max}=\ln x_0-\dfrac{2}{x_0}+2$，显然 $f(x_0)\leqslant0$ 不符合题意，故 $f(x_0)>0$，即 $\ln x_0-\dfrac{2}{x_0}+2>0$，令 $h(x)=\ln x-\dfrac{2}{x}+2$（$x>0$）则 $h'(x)=\dfrac{1}{x}+\dfrac{2}{x^2}>0$，则 $h(x)$ 在 $(0,+\infty)$ 上单调递增，且 $h(1)=0$，由于 $h(x_0)=\ln x_0-\dfrac{2}{x_0}+2>0$，所以 $x_0>1$，由于 $\dfrac{a}{2}=\sqrt{\dfrac{1}{x_0^2}+\dfrac{1}{x_0}}$，令 $t=\dfrac{1}{x_0}\in(0,1)$，$y=t^2+t$ 在 $(0,1)$ 上单调递增，则 $a\in(0,2\sqrt{2})$，由于 $x_0=\dfrac{2(1+\sqrt{1+a^2})}{a^2}>\dfrac{2}{a}>\dfrac{\sqrt{2}}{2}>\dfrac{1}{\mathrm{e}^4}$，$f(\dfrac{1}{\mathrm{e}^4})=-a\sqrt{\dfrac{1}{\mathrm{e}^4}+1}<0$，由零点存在性定理，存在 $x_1\in(\dfrac{1}{\mathrm{e}^4},x_0)$ 使得 $f(x_1)=0$，当 $x>0$ 时，易证 $\ln x\leqslant x-1$，则 $\ln\sqrt[4]{x}\leqslant\sqrt[4]{x}-1$ 即 $\ln x\leqslant4\sqrt[4]{x}-4$，由于 $f(x)=\ln x-a\sqrt{x+1}+4<\ln x-a\sqrt{x}+4\leqslant4\sqrt[4]{x}-a\sqrt{x}=\sqrt[4]{x}(4-a\sqrt[4]{x})$，取 $x_2\in(x_0,+\infty)$，且 $x_2>\dfrac{256}{a^4}$，则 $f(x_2)<0$，由零点存在性定理，存在 $x_3\in(x_0,x_2)$ 使得 $f(x_3)=0$，所以当 $a\in(0,2\sqrt{2})$ 时，$f(x)$ 在 $(0,+\infty)$ 上有两个零点．"
        + "\n" + r"(3) 由 (2) 可知，$f(x)_{\max}=\ln x_0-\dfrac{2}{x_0}+2$，其中 $x_0=\dfrac{2(1+\sqrt{a^2+1})}{a^2}$，则 $x_0=\dfrac{2(1+\sqrt{a^2+1})}{a^2}=\dfrac{2}{\sqrt{a^2+1}-1}$，下证：$\ln x_0-\dfrac{2}{x_0}+2<x_0$（$x_0>1$）即证：$\ln x_0-\dfrac{2}{x_0}-x_0+2<0$，设 $m(x)=\ln x-\dfrac{2}{x}-x+2$（$x>1$）$m'(x)=\dfrac{1}{x}+\dfrac{2}{x^2}-1=\dfrac{-x^2+x+2}{x^2}=\dfrac{(-x+2)(x+1)}{x^2}$，令 $m'(x)=0$，$x=2$，于是 $m(x)$ 在 $(1,2)$ 上单调递增，在 $(2,+\infty)$ 上单调递减，则 $m(x)\leqslant m(2)=\ln2-1<0$，即证．",
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4],
        "题干": r"已知 $A_1,A_2$ 为椭圆 $C_1:\dfrac{x^2}{3}+\dfrac{y^2}{b^2}=1(0<b<\sqrt{3})$ 的左，右顶点，$M$ 为 $C_1$ 上的一点，$N$ 为双曲线 $C_2:\dfrac{x^2}{3}-\dfrac{y^2}{b^2}=1$ 上的一点（$M$，$N$ 两点不同于 $A_1,A_2$ 两点），设直线 $A_1M,A_2M,A_1N$，$A_2N$ 的斜率分别为 $k_1,k_2,k_3,k_4$，且 $k_1+k_2+k_3+k_4=0$．"
        + "\n" + r"(1) 设 $O$ 为坐标原点，证明：$O,M,N$ 三点共线；"
        + "\n" + r"(2) 设 $C_1$、$C_2$ 的右焦点分别为 $F_1$、$F_2$，$M$、$N$ 均在第一象限，直线 $NF_1$ 与直线 $MF_2$ 相交于点 $P$，$k_1^2+k_2^2+k_3^2+k_4^2=8$．"
        + "\n" + r"(i) 证明：$MF_1\parallel NF_2$；"
        + "\n" + r"(ii) 证明：$\angle A_1PF_1=\angle A_2PF_2$．",
        "选项": {},
        "答案": r"(1)(2)(i)(ii) 证明见解析",
        "解析": r"解：(1) 设 $M(x_1,y_1)$，$N(x_2,y_2)$，则 $k_1=\dfrac{y_1}{x_1+\sqrt{3}}$，$k_2=\dfrac{y_1}{x_1-\sqrt{3}}$，因为 $\dfrac{x_1^2}{3}+\dfrac{y_1^2}{b^2}=1$，可知：$x_1^2-3=-\dfrac{3}{b^2}y_1^2$，则 $k_1k_2=\dfrac{y_1^2}{x_1^2-3}=\dfrac{y_1^2}{-\dfrac{3}{b^2}y_1^2}=-\dfrac{b^2}{3}$，$k_1+k_2=\dfrac{2x_1y_1}{x_1^2-3}=-\dfrac{2}{3}b^2\dfrac{x_1}{y_1}$，因为 $\dfrac{x_2^2}{3}-\dfrac{y_2^2}{b^2}=1$，可知：$x_2^2-3=\dfrac{3}{b^2}y_2^2$，则 $k_3k_4=\dfrac{y_2^2}{x_2^2-3}=\dfrac{y_2^2}{\dfrac{3}{b^2}y_2^2}=\dfrac{b^2}{3}$，$k_3+k_4=\dfrac{2x_2y_2}{x_2^2-3}=\dfrac{2}{3}b^2\dfrac{x_2}{y_2}$，由 $k_1+k_2+k_3+k_4=0$ 可知：$x_1y_2-x_2y_1=0$，可知：$\overrightarrow{OM}\parallel\overrightarrow{ON}$，因此，$O,M,N$ 三点共线．"
        + "\n" + r"(2) (i) 由 $k_1^2+k_2^2+k_3^2+k_4^2=8$ 可得：$(k_1+k_2)^2+(k_3+k_4)^2-2(k_1k_2+k_3k_4)=8$，由（1）可知：$k_1k_2+k_3k_4=0$，则 $(k_1+k_2)^2+(k_3+k_4)^2=8$，又 $k_1+k_2+k_3+k_4=0$，则 $(k_1+k_2)^2=4$，因为 $M,N$ 都在第一象限，所以 $k_1+k_2=-2$，$k_3+k_4=2$，所以 $\dfrac{x_1}{y_1}=\dfrac{x_2}{y_2}=\dfrac{3}{b^2}$，结合 $\dfrac{x_1^2}{3}+\dfrac{y_1^2}{b^2}=1$，$\dfrac{x_2^2}{3}-\dfrac{y_2^2}{b^2}=1$ 可知：$y_1=\dfrac{b^2}{\sqrt{3+b^2}}$，$y_2=\dfrac{b^2}{\sqrt{3-b^2}}$，则 $M(\dfrac{3}{\sqrt{3+b^2}},\dfrac{b^2}{\sqrt{3+b^2}})$，$N(\dfrac{3}{\sqrt{3-b^2}},\dfrac{b^2}{\sqrt{3-b^2}})$，又 $\overrightarrow{F_1M}=(x_1-\sqrt{3-b^2},y_1)$，$\overrightarrow{F_2N}=(x_2-\sqrt{3+b^2},y_2)$ 则 $(x_1-\sqrt{3-b^2})y_2-(x_2-\sqrt{3+b^2})y_1=x_1y_2-x_2y_1+\sqrt{3+b^2}y_1-\sqrt{3-b^2}y_2=\sqrt{3+b^2}y_1-\sqrt{3-b^2}y_2=0$，由此可知：$MF_1\parallel NF_2$．"
        + "\n" + r"(ii) 由（i）可知：$k_{NF_1}=\dfrac{\dfrac{b^2}{\sqrt{3-b^2}}}{\dfrac{3}{\sqrt{3-b^2}}-\sqrt{3-b^2}}=\dfrac{b^2}{3-(3-b^2)}=1$，$k_{MF_2}=\dfrac{\dfrac{b^2}{\sqrt{3+b^2}}}{\dfrac{3}{\sqrt{3+b^2}}-\sqrt{3+b^2}}=\dfrac{b^2}{3-(3+b^2)}=-1$，直线 $F_1N$：$y=x-\sqrt{3-b^2}$，直线 $F_2M$：$y=-x+\sqrt{3+b^2}$，设点 $P(x_0,y_0)$，于是 $x_0-y_0=\sqrt{3-b^2}$，$x_0+y_0=\sqrt{3+b^2}$，则 $(x_0-y_0)^2+(x_0+y_0)^2=6$，即 $x_0^2+y_0^2=3$，则点 $P$ 的轨迹是以 $O$ 为圆心，$\sqrt{3}$ 为半径的圆，则 $\angle A_1PA_2=\dfrac{\pi}{2}$，又直线 $F_1N$ 与直线 $F_2M$ 垂直，则 $\angle F_1PF_2=\dfrac{\pi}{2}$ 于是 $\angle A_1PF_1+\angle F_1PA_2=\angle F_1PA_2+\angle A_2PF_2$，所以 $\angle A_1PF_1=\angle A_2PF_2$．",
    },
]

for r in recs:
    r.setdefault("选项", {})
    r["粗筛图"] = False
    r["粗筛表"] = False

review = [
    {
        "题号": 17, "题型": "detailed_answer", "页码": [3], "类型": "figure",
        "原文": r"已知球 $O$ 的半径为 $1$，在球 $O$ 的内接八面体 $PABCDQ$ 中，顶点 $P,Q$ 分别在平面 $ABCD$ 两侧，且四棱锥 $P-ABCD$ 与 $Q-ABCD$ 都是正四棱锥．(1) 如图 1，若点 $O$ 在平面 $ABCD$ 上，求证：$PA\parallel$ 平面 $QBC$；(2) 如图 2，若二面角 $P-AB-Q$ 的正切值为 $-3$，求该内接八面体的体积．",
        "说明": r"试卷第 3 页 #17 题干下方并排印两幅图：**图 1** 圆（球 $O$ 的截面）内接八面体，$P$ 在上、$Q$ 在下，正方形 $ABCD$ 水平穿过圆心 $O$，$A$ 左、$C$ 右、$D$ 中上、$B$ 中下，$PA$、$PB$、$PC$、$PD$、$QA$、$QB$、$QC$、$QD$ 为实线，$AC$、$BD$、$PQ$ 为虚线；**图 2** 同一种八面体但正方形 $ABCD$ 上移到圆心 $O$ 之上（$P$ 到平面 $ABCD$ 的距离小于 $Q$ 到该平面的距离）。(1)(2) 两问各自对应一幅图，点与球心的上下位置关系只能从图读出，按规矩不录正文。"
        + "\n" + r"答案册（第 4—5 页）给出的完整解答：(1) 如图，连接 $AC$，则 $AC$ 必过点 $O$，在四边形 $PAQC$ 中，由于对角线 $AC$，$PQ$ 互相平分，则四边形 $PAQC$ 为平行四边形，故 $PA\parallel QC$，由于 $PA\not\subset$ 平面 $QBC$ 且 $QC\subset$ 平面 $QBC$，所以 $PA\parallel$ 平面 $QBC$。(2) 如图，记正方形 $ABCD$ 的中心为 $N$，取 $AB$ 中点 $M$，连接 $PM$，$QM$，$NA$，$NB$，由于 $PA=PB$，则 $PM\perp AB$，同理可证 $QM\perp AB$，则 $\angle PMQ$ 为二面角 $P-AB-Q$ 的平面角，又 $NA=NB$，则 $NM\perp AB$，则 $\angle PMN$ 为二面角 $P-AB-N$ 的平面角，$\angle QMN$ 为二面角 $Q-AB-N$ 的平面角，不妨设点 $O$ 在 $N$ 的下方，设 $ON=x$（$0<x<1$），则 $NB=\sqrt{1-x^2}=NA$，$AB=\sqrt{2-2x^2}$，$NM=\dfrac{\sqrt{1-x^2}}{\sqrt{2}}$，$PN=1-x$，$QN=1+x$，于是 $\tan\angle PMN=\dfrac{PN}{MN}=\dfrac{\sqrt{2}\cdot(1-x)}{\sqrt{1-x^2}}=\sqrt{2}\cdot\sqrt{\dfrac{1-x}{1+x}}$，$\tan\angle QMN=\dfrac{QN}{MN}=\dfrac{\sqrt{2}\cdot(1+x)}{\sqrt{1-x^2}}=\sqrt{2}\cdot\sqrt{\dfrac{1+x}{1-x}}$，于是 $\tan\angle PMQ=\tan(\angle PMN+\angle QMN)=\dfrac{\tan\angle PMN+\tan\angle QMN}{1-\tan\angle PMN\cdot\tan\angle QMN}$，$\tan\angle PMQ=\sqrt{2}\cdot\dfrac{\sqrt{\dfrac{1-x}{1+x}}+\sqrt{\dfrac{1+x}{1-x}}}{1-2}=-\sqrt{2}\cdot(\sqrt{\dfrac{1-x}{1+x}}+\sqrt{\dfrac{1+x}{1-x}})=-3$，由于 $0<\sqrt{\dfrac{1-x}{1+x}}<1$，则 $\sqrt{\dfrac{1-x}{1+x}}=\dfrac{\sqrt{2}}{2}$，解得 $x=\dfrac{1}{3}$，则 $AB=\dfrac{4}{3}$，则 $V=\dfrac{1}{3}\times PQ\times S_{四边形ABCD}=\dfrac{1}{3}\times2\times(\dfrac{4}{3})^2=\dfrac{32}{27}$，即内接八面体的体积为 $\dfrac{32}{27}$。（答案册第 4 页、第 5 页各另印一幅带 $M$、$N$ 辅助点的同型立体图。）",
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4], "类型": "figure-in-solution",
        "原文": "",
        "说明": r"答案册第 7 页 (1) 的解答右侧印一幅平面直角坐标系图：以原点为圆心的圆（椭圆 $C_1$）与左右开口的双曲线 $C_2$ 共用 $x$ 轴上的顶点 $A_1$、$A_2$，第一象限标 $M$、$N$ 两点，$x$ 轴上标 $F_1$、$F_2$，并画出直线 $NF_1$ 与 $MF_2$ 相交。本题卷面**不带图**，图只在解析中间，仅作理解辅助，#19 的题干与解析均已正常录入。",
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4], "类型": "print-suspect",
        "原文": r"卷面 #18 只有两问：(1) 当 $a=\sqrt{3}$ 时求单调区间；(2) 若 $f(x)$ 有两个零点，(i) 求 $a$ 的取值范围；(ii) 证明 $f(x)<\dfrac{2}{\sqrt{a^2+1}-1}$。　答案册第 6 页把证明那一段另起一行标成「(3) 由 (2) 可知……」",
        "说明": r"疑在哪：答案册的解答编号比卷面多一档——卷面是 (1)(2)(i)(ii) 四小问，答案册排成 (1)(2)(3)，其中它的「(2)」对应卷面 (2)(i)、它的「(3)」对应卷面 (2)(ii)。为何没改：规范 §7.3 规定内容一个字都不许改，`解析` 字段照答案册原编号「(1)(2)(3)」逐字誊录，未擅自改成 (1)(2)(i)(ii)；本条登记是为了让人工核对时不误判成「漏了一问」。另：答案册第 6 页 (2) 段中先后出现 $x_0=\dfrac{2(1+\sqrt{1+a^2})}{a^2}$ 与 (3) 段中 $x_0=\dfrac{2(1+\sqrt{a^2+1})}{a^2}$，二者是同一式的不同写法，**不算错**，一并记下以免误判为排印错误。",
    },
]

for r in review:
    r.setdefault("原文", "")

# ---- 落盘前自查（判据与闸门/记忆对齐）----
def vals(rec):
    return ([rec.get("题干") or "", rec.get("答案") or "", rec.get("解析") or ""]
            + list((rec.get("选项") or {}).values()))

bad = []
for rec in recs:
    for s in vals(rec):
        for c in s:
            if ord(c) < 32 and c != "\n":
                bad.append(("ctrl", rec["题号"], hex(ord(c))))
        if "$$" in s:
            bad.append(("dollar-pair", rec["题号"], s[:40]))
        if s.count("$") % 2:
            bad.append(("dollar-odd", rec["题号"], s[:40]))
        if "见待复核" in s or "答案册" in s.replace("见解析", ""):
            bad.append(("self-note", rec["题号"], s[:40]))
        for m in re.finditer(r"_\{([^}]*[一-鿿][^}]*)\}", s):
            if "\\text" not in m.group(1):
                bad.append(("cn-subscript", rec["题号"], m.group(1)))
        if re.search(r"\\n(?![a-zA-Z])", s):
            bad.append(("literal-n", rec["题号"], s[:40]))
for x in review:
    for k in ("原文", "说明"):
        if re.search(r"\\n(?![a-zA-Z])", x[k]):
            bad.append(("review-literal-n", x["题号"], k))
assert not bad, bad

p1 = OUT / f"{NO}_{NAME}.成品.json"
p2 = OUT / f"{NO}_{NAME}.待复核.json"
p1.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
p2.write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("成品", len(recs), "题；待复核", len(review), "条")
print(p1.name)
