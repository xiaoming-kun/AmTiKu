#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 #178 河北高三上学期金科联考二月份数学试卷（含答案） 的成品 / 待复核。

来源：`河北邯郸高三上学期金科联考二月份数学试卷.pdf` 4 页试卷
    + `26074C-HB-详解版答案-数学.pdf` 6 页「参考答案、提示及评分细则」。
卷面结构：一、选择题本题共 8 小题；二、选择题本题共 3 小题；
三、填空题本题共 3 小题（12–14）；四、解答题本题共 5 小题（15–19）。
正文一律 r-string；多行用 L([...]) 以真实换行拼接。
"""
import json
from pathlib import Path

OUT = Path("数据/录题/输出_v2")
NAME = "178_河北高三上学期金科联考二月份数学试卷（含答案）"


def L(*lines):
    return "\n".join(lines)


recs = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1],
        "题干": r"已知集合 $A\subseteq\{1,2,3,4\}$，若 $A\cup\{1\}=\{1,2,3\}$，则集合 $A$ 的个数为",
        "选项": {"A": r"$1$", "B": r"$2$", "C": r"$3$", "D": r"$4$"},
        "答案": "B",
        "解析": r"易知 $A=\{2,3\}$ 或 $A=\{1,2,3\}$．故选 B.",
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1],
        "题干": r"若复数 $z=2-\mathrm{i}$，则 $\left|\dfrac{z}{z-1}\right|=$",
        "选项": {
            "A": r"$\sqrt{10}$", "B": r"$\sqrt{5}$",
            "C": r"$\dfrac{\sqrt{10}}{2}$", "D": r"$\dfrac{\sqrt{5}}{2}$",
        },
        "答案": "C",
        "解析": L(
            r"由题意得 $\dfrac{z}{z-1}=\dfrac{2-\mathrm{i}}{1-\mathrm{i}}=\dfrac{(2-\mathrm{i})(1+\mathrm{i})}{(1-\mathrm{i})(1+\mathrm{i})}=\dfrac{3+\mathrm{i}}{2}$，所以 $\left|\dfrac{z}{z-1}\right|=\dfrac{\sqrt{10}}{2}$．故选 C.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1],
        "题干": r"已知抛物线 $C:y^{2}=2px(p>0)$ 的焦点为 $F$，点 $P(1,y_{0})$ 在抛物线 $C$ 上，若 $|PF|=3$，则 $|y_{0}|=$",
        "选项": {"A": r"$2$", "B": r"$2\sqrt{2}$", "C": r"$4$", "D": r"$4\sqrt{2}$"},
        "答案": "B",
        "解析": L(
            r"根据抛物线的定义，$|PF|=1+\dfrac{p}{2}=3$，所以 $p=4$，有 $y^{2}=8x$，代入 $x=1$，可得 $|y_{0}|=2\sqrt{2}$．故选 B.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [1],
        "题干": L(
            r"设 $m,n\in\mathbf{N}^{*}$，则「数列 $\{a_{n}\}$ 为等比数列」是「$a_{m+n}=a_{m}\cdot a_{n}$」的",
        ),
        "选项": {
            "A": "充分不必要条件", "B": "必要不充分条件",
            "C": "充要条件", "D": "既不充分也不必要条件",
        },
        "答案": "D",
        "解析": L(
            r"设 $a_{n}=2^{n-1}$，则 $a_{m+n}=2^{m+n-1}\neq a_{m}a_{n}=2^{m+n-2}$，充分性不成立；设 $a_{n}=0$，则 $\{a_{n}\}$ 不是等比数列，必要性不成立．故选 D.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1],
        "题干": r"若函数 $f(x)=\log_{2}(x^{2}-ax)$ 在 $[1,+\infty)$ 上单调递增，则实数 $a$ 的取值范围为",
        "选项": {
            "A": r"$(-\infty,1)$", "B": r"$(-\infty,1]$",
            "C": r"$(-\infty,2]$", "D": r"$[2,+\infty)$",
        },
        "答案": "A",
        "解析": L(
            r"当 $a\leqslant 0$ 时，$f(x)$ 的单调递减区间为 $(-\infty,a)$，单调递增区间为 $(0,+\infty)$，可得 $f(x)$ 在 $[1,+\infty)$ 上单调递增；当 $a>0$ 时，$f(x)$ 的单调递减区间为 $(-\infty,0)$，单调递增区间为 $(a,+\infty)$．若 $f(x)$ 在 $[1,+\infty)$ 上单调递增，有 $0<a<1$．由上知 $a<1$．故选 A.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [1],
        "题干": r"设 $a=\log_{5}2,b=\sin 1,c=\sin 2$，则",
        "选项": {
            "A": r"$c<a<b$", "B": r"$b<a<c$", "C": r"$a<b<c$", "D": r"$a<c<b$",
        },
        "答案": "C",
        "解析": L(
            r"易知 $b=\sin 1>\sin\dfrac{\pi}{4}=\dfrac{\sqrt{2}}{2}>\dfrac{1}{2}>\log_{5}2$，$c=\sin 2=\sin(\pi-2)>\sin 1$，所以 $a<b<c$．故选 C.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [2],
        "题干": r"已知某圆锥的底面半径为 $1$，若该圆锥的体积与其内切球的体积之比为 $\dfrac{9}{4}$，则该圆锥的体积为",
        "选项": {
            "A": r"$\dfrac{\sqrt{3}}{3}\pi$ 或 $\dfrac{2\sqrt{6}}{3}\pi$",
            "B": r"$\dfrac{\sqrt{3}}{3}\pi$",
            "C": r"$\dfrac{2\sqrt{6}}{3}\pi$",
            "D": r"$\dfrac{\sqrt{3}}{3}\pi$ 或 $\dfrac{\sqrt{6}}{3}\pi$",
        },
        "答案": "A",
        "解析": L(
            r"不妨设圆锥的高为 $h$，母线长为 $l$，则 $l^{2}=h^{2}+1$，根据等面积法，该圆锥内切球的半径为 $\dfrac{\dfrac{1}{2}\times 2\times h}{\dfrac{1}{2}(2l+2)}=\dfrac{h}{l+1}$，所以该圆锥的体积与其内切球体积之比为",
            r"$\dfrac{\dfrac{1}{3}\pi\times 1^{2}\times h}{\dfrac{4}{3}\pi\times\left(\dfrac{h}{l+1}\right)^{3}}=\dfrac{1}{4}\times\dfrac{(l+1)^{3}}{h^{2}}=\dfrac{1}{4}\times\dfrac{(l+1)^{3}}{l^{2}-1}=\dfrac{1}{4}\times\dfrac{(l+1)^{2}}{l-1}=\dfrac{9}{4}$，解得 $l=2$ 或 $l=5$，所以 $h=\sqrt{3}$ 或 $h=2\sqrt{6}$，所以该圆锥的体积为 $\dfrac{\sqrt{3}}{3}\pi$ 或 $\dfrac{2\sqrt{6}}{3}\pi$．故选 A.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [2],
        "题干": r"若 $\mathrm{e}^{m}+m=\ln(-n)+\dfrac{1}{n}=0$，则 $mn=$",
        "选项": {"A": r"$\dfrac{1}{\mathrm{e}}$", "B": r"$1$", "C": r"$2$", "D": r"$\mathrm{e}$"},
        "答案": "B",
        "解析": L(
            r"易知 $\mathrm{e}^{m}+m=0$，且 $\ln(-n)+\dfrac{1}{n}=0$，由 $\ln(-n)+\dfrac{1}{n}=0$，得 $\dfrac{1}{n}=-\ln(-n)=\ln\left(-\dfrac{1}{n}\right)$，所以 $\mathrm{e}^{\frac{1}{n}}=-\dfrac{1}{n}$，即 $\mathrm{e}^{\frac{1}{n}}+\dfrac{1}{n}=0$，因为函数 $f(x)=\mathrm{e}^{x}+x$ 单调递增，所以 $f(m)=f\left(\dfrac{1}{n}\right)=0$，所以 $m=\dfrac{1}{n}$，即 $mn=1$．故选 B.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [2],
        "题干": r"已知向量 $\boldsymbol{a}=(4,3),\boldsymbol{b}=(2\cos\theta,2\sin\theta)$，则",
        "选项": {
            "A": r"$|\boldsymbol{b}|=2$",
            "B": r"当 $\boldsymbol{a}\parallel\boldsymbol{b}$ 时，$\tan\theta=\dfrac{4}{3}$",
            "C": r"当 $\boldsymbol{a}\perp\boldsymbol{b}$ 时，$\sin\theta=\dfrac{4}{5}$",
            "D": r"$|\boldsymbol{a}-\boldsymbol{b}|$ 的最大值为 $7$",
        },
        "答案": "AD",
        "解析": L(
            r"对于 A 选项，因为 $\boldsymbol{b}=(2\cos\theta,2\sin\theta)$，所以 $|\boldsymbol{b}|=\sqrt{4\cos^{2}\theta+4\sin^{2}\theta}=2$，A 选项正确；",
            r"对于 B 选项，当 $\boldsymbol{a}\parallel\boldsymbol{b}$ 时，满足 $8\sin\theta-6\cos\theta=0$，即 $\tan\theta=\dfrac{3}{4}$，B 选项错误；",
            r"对于 C 选项，当 $\boldsymbol{a}\perp\boldsymbol{b}$ 时，$8\cos\theta+6\sin\theta=0$，解得 $\tan\theta=-\dfrac{4}{3}$，可得 $\sin\theta=\pm\dfrac{4}{5}$，C 选项错误；",
            r"对于 D 选项，$|\boldsymbol{a}-\boldsymbol{b}|\leqslant|\boldsymbol{a}|+|-\boldsymbol{b}|=5+2=7$，故 $|\boldsymbol{a}-\boldsymbol{b}|$ 的最大值为 $7$，D 选项正确．故选 AD.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2],
        "题干": r"已知 $(x+1)(2x+1)^{9}=a_{0}+a_{1}(x+1)+\cdots+a_{10}(x+1)^{10}$，则",
        "选项": {
            "A": r"$a_{1}=-1$",
            "B": r"$a_{0}+a_{1}+\cdots+a_{10}=1$",
            "C": r"$a_{0}+a_{2}+a_{4}+a_{6}+a_{8}+a_{10}=3^{9}+1$",
            "D": r"$a_{1}+2a_{2}+3a_{3}\cdots+10a_{10}=19$",
        },
        "答案": "ABD",
        "解析": L(
            r"对于 A 选项，$(x+1)(2x+1)^{9}=(x+1)\left[2(x+1)-1\right]^{9}$，所以 $a_{1}=\mathrm{C}_{9}^{9}(-1)^{9}=-1$，A 选项正确；",
            r"对于 B 选项，令 $x=0$，可得 $a_{0}+a_{1}+\cdots+a_{10}=1$，B 选项正确；",
            r"对于 C 选项，令 $x=-2$，可得 $a_{0}-a_{1}+a_{2}\cdots+a_{10}=3^{9}$，与 B 选项分析中的式子相加，可得 $2(a_{0}+a_{2}+a_{4}+a_{6}+a_{8}+a_{10})=3^{9}+1$，所以 $a_{0}+a_{2}+a_{4}+a_{6}+a_{8}+a_{10}=\dfrac{3^{9}+1}{2}$，C 选项错误；",
            r"对于 D 选项，设 $f(x)=(x+1)(2x+1)^{9}=a_{0}+a_{1}(x+1)+\cdots+a_{10}(x+1)^{10}$，则 $f^{\prime}(x)=(2x+1)^{9}+18(x+1)(2x+1)^{8}=a_{1}+2a_{2}(x+1)+\cdots+10a_{10}(x+1)$，令 $x=0$，可得 $a_{1}+2a_{2}\cdots+10a_{10}=19$，D 选项正确．故选 ABD.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2],
        "题干": r"已知曲线 $C:2x^{2}-xy+y^{2}=1$，点 $A$、$B$ 是曲线 $C$ 与 $x$ 轴的两个交点，点 $P(x_{0},y_{0})$ 为曲线 $C$ 上的动点，$O$ 为坐标原点，则",
        "选项": {
            "A": r"$|AB|=\sqrt{2}$",
            "B": r"$\triangle PAB$ 面积的最大值为 $\dfrac{\sqrt{2}}{2}$",
            "C": r"$-\dfrac{2\sqrt{7}}{7}\leqslant x_{0}\leqslant\dfrac{2\sqrt{7}}{7}$",
            "D": r"$\dfrac{6-2\sqrt{2}}{7}\leqslant|OP|^{2}\leqslant\dfrac{6+2\sqrt{2}}{7}$",
        },
        "答案": "ACD",
        "解析": L(
            r"对于 A 选项，令 $y=0$，解得 $x=\pm\dfrac{\sqrt{2}}{2}$，所以 $|AB|=\sqrt{2}$，A 选项正确；",
            r"对于 B 选项，因为 $2x^{2}-xy+y^{2}=2\left(x-\dfrac{y}{4}\right)^{2}+\dfrac{7y^{2}}{8}=1$，所以 $1-\dfrac{7y^{2}}{8}\geqslant 0$，解得 $-\dfrac{2\sqrt{14}}{7}\leqslant y\leqslant\dfrac{2\sqrt{14}}{7}$，所以 $\triangle PAB$ 面积的最大值为 $\dfrac{2\sqrt{7}}{7}$，B 选项错误；",
            r"对于 C 选项，$2x^{2}-xy+y^{2}=\left(y-\dfrac{x}{2}\right)^{2}+\dfrac{7x^{2}}{4}=1$，所以 $1-\dfrac{7x^{2}}{4}\geqslant 0$，解得 $-\dfrac{2\sqrt{7}}{7}\leqslant x_{0}\leqslant\dfrac{2\sqrt{7}}{7}$，C 选项正确；",
            r"对于 D 选项，不妨设 $P(r\cos\theta,r\sin\theta)$，则 $2r^{2}\cos^{2}\theta-r^{2}\sin\theta\cos\theta+r^{2}\sin^{2}\theta=1$，即 $r^{2}=\dfrac{1}{2\cos^{2}\theta-\sin\theta\cos\theta+\sin^{2}\theta}=\dfrac{1}{\dfrac{\cos 2\theta+1}{2}-\dfrac{\sin 2\theta}{2}+1}=\dfrac{1}{\dfrac{\sqrt{2}}{2}\cos\left(2\theta+\dfrac{\pi}{4}\right)+\dfrac{3}{2}}$，因为 $-1\leqslant\cos\left(2\theta+\dfrac{\pi}{4}\right)\leqslant 1$，所以 $\dfrac{6-2\sqrt{2}}{7}\leqslant r^{2}\leqslant\dfrac{6+2\sqrt{2}}{7}$，D 选项正确．故选 ACD.",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [2],
        "题干": r"设事件 $A$，$B$ 相互独立，$P(A)=\dfrac{1}{2}$，$P(B)=\dfrac{1}{3}$，则 $P(\overline{A}+B)=$ _____．",
        "选项": {},
        "答案": r"$\dfrac{2}{3}$",
        "解析": L(
            r"由于事件 $A$，$B$ 相互独立，所以事件 $\overline{A}$，$B$ 相互独立，所以 $P(\overline{A}+B)=P(\overline{A})+P(B)-P(\overline{A}B)=\dfrac{1}{2}+\dfrac{1}{3}-\dfrac{1}{2}\times\dfrac{1}{3}=\dfrac{2}{3}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [2],
        "题干": L(
            r"记函数 $f(x)=\sin(\omega x+\varphi)\left(\omega>0,0\leqslant\varphi\leqslant\dfrac{\pi}{2}\right)$ 的最小正周期为 $T$，且 $\pi<T\leqslant\dfrac{4\pi}{3}$，$f(x)\leqslant\left|f\left(\dfrac{\pi}{3}\right)\right|$，则 $f(x)$ 在 $\left(\dfrac{\pi}{6},\dfrac{5\pi}{9}\right)$ 上的值域为 _____．",
        ),
        "选项": {},
        "答案": r"$\left(\dfrac{1}{2},1\right]$",
        "解析": L(
            r"因为 $\pi<T\leqslant\dfrac{4\pi}{3}$，且 $T=\dfrac{2\pi}{\omega}$，所以 $\omega\in\left[\dfrac{3}{2},2\right)$．且 $f(x)\leqslant\left|f\left(\dfrac{\pi}{3}\right)\right|$，所以直线 $x=\dfrac{\pi}{3}$ 是曲线 $y=f(x)$ 的一条对称轴，所以 $\dfrac{\pi\omega}{3}+\varphi=\dfrac{\pi}{2}+k\pi(k\in\mathbf{Z})$，解得 $\omega=3k-\dfrac{3\varphi}{\pi}+\dfrac{3}{2}(k\in\mathbf{Z})$，且 $0\leqslant\varphi\leqslant\dfrac{\pi}{2}$，所以 $\omega\in\left[3k,3k+\dfrac{3}{2}\right](k\in\mathbf{Z})$，因为 $\omega\in\left[\dfrac{3}{2},2\right)$，解得 $\omega=\dfrac{3}{2}$，此时 $k=0$，$\varphi=0$，则 $f(x)=\sin\dfrac{3}{2}x$，且 $x\in\left(\dfrac{\pi}{6},\dfrac{5\pi}{9}\right)$，所以 $f(x)\in\left(\dfrac{1}{2},1\right]$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [2],
        "题干": L(
            r"德国数学家克雷尔于 $1816$ 年发现了三角形的布洛卡点，法国军官布洛卡于 $1875$ 年将此特殊点重新发现，并以他的名字命名至今．已知任意 $\triangle ABC$ 的内部必存在点 $P$，使得 $\angle PAB=\angle PBC=\angle PCA=\alpha$（或 $\angle PAC=\angle PBA=\angle PCB=\beta$），则 $P$ 称为 $\triangle ABC$ 的布洛卡点，$\alpha$（或 $\beta$）称为布洛卡角．一般地，对于任意三角形均有两个布洛卡点及两个布洛卡角，当三角形为正三角形时，两个布洛卡点重合，且两个布洛卡角相等．已知点 $M$ 为 $\triangle ABC$ 的一个布洛卡点，且 $\angle MAC\neq\angle MBA$．则 $\angle AMB+\angle ABC=$ _____；当 $MA=2MB$，且 $AC=2$ 时，$\triangle ABC$ 的面积的最大值为 _____．（注：第一空 $2$ 分，第二空 $3$ 分）",
        ),
        "选项": {},
        "答案": r"$\pi$；$1$",
        "解析": L(
            r"$\because$ 点 $M$ 为 $\triangle ABC$ 的一个布洛卡点，且 $\angle MAC\neq\angle MBA$，$\therefore\angle AMB+\angle ABC=\angle AMB+\angle ABM+\angle MBC=\angle AMB+\angle ABM+\angle MAB=\pi$，即 $\angle AMB+\angle ABC=\pi$，故应填 $\pi$（或 $180^{\circ}$）；",
            r"同理可知 $\angle AMC+\angle BAC=\pi$，不妨记 $BC=a$，$CA=b$，$AB=c$，$\angle BAM=\theta$，在 $\triangle MAB$ 中，由正弦定理得 $\dfrac{MB}{\sin\theta}=\dfrac{c}{\sin\angle AMB}=\dfrac{c}{\sin(\pi-\angle ABC)}=\dfrac{c}{\sin\angle ABC}$，$\therefore\dfrac{MB}{\sin\theta}=\dfrac{c}{\sin\angle ABC}$ ①，在 $\triangle MAC$ 中，由正弦定理得 $\dfrac{MA}{\sin\theta}=\dfrac{b}{\sin\angle AMC}=\dfrac{b}{\sin(\pi-\angle BAC)}=\dfrac{b}{\sin\angle BAC}$，$\therefore\dfrac{MA}{\sin\theta}=\dfrac{b}{\sin\angle BAC}$ ②，由 ①② 两式作商，可得 $\dfrac{MB}{MA}=\dfrac{c\sin\angle BAC}{b\sin\angle ABC}=\dfrac{ac}{b^{2}}=\dfrac{1}{2}$，所以 $b^{2}=2ac=4$，即 $ac=2$，",
            r"在 $\triangle ABC$ 中，由余弦定理得 $b^{2}=a^{2}+c^{2}-2ac\cos\angle ABC=4$，又 $a^{2}+c^{2}\geqslant 2ac$，故 $2ac(1-\cos\angle ABC)\leqslant 4$，$\therefore 1-\cos\angle ABC\leqslant 1$，$\therefore\cos\angle ABC\geqslant 0$，即 $\angle ABC\leqslant\dfrac{\pi}{2}$，$\therefore\triangle ABC$ 的面积 $S=\dfrac{1}{2}ac\sin\angle ABC=\sin\angle ABC\leqslant 1$，易知当 $a=c=\sqrt{2}$ 时取等号，即 $\triangle ABC$ 的面积最大值为 $1$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3],
        "题干": L(
            r"记 $S_{n}$ 为正项数列 $\{a_{n}\}$ 的前 $n$ 项和，$a_{1}=1$，$2S_{n}=a_{n}a_{n+1}$．",
            r"(1) 证明：$\{a_{n}\}$ 是等差数列；",
            r"(2) 定义数列 $\{b_{m}\}$：$b_{m}$ 表示满足 $3^{m}<a_{n}<3^{m+1}(m\in\mathbf{N}^{*})$ 的整数 $n$ 的个数，求数列 $\{a_{n}b_{n}\}$ 的前 $n$ 项 $T_{n}$．",
        ),
        "选项": {},
        "答案": L(
            r"(1) 由 $2a_{n}=a_{n}(a_{n+1}-a_{n-1})$ 及 $a_{n}>0$ 得 $a_{n+1}-a_{n-1}=2(n\geqslant 2)$，结合 $a_{2}=2$ 得 $a_{2n}=2n$、$a_{2n-1}=2n-1$，即可得 $a_{n}=n$，$a_{n}-a_{n-1}=1(n\geqslant 2)$，故 $\{a_{n}\}$ 是等差数列；",
            r"(2) $b_{m}=2\times 3^{m}-1$，$T_{n}=\dfrac{(2n-1)\cdot 3^{n+1}-n^{2}-n+3}{2}$．",
        ),
        "解析": L(
            r"(1) 因为 $2S_{n}=a_{n}a_{n+1}$，",
            r"所以 $n\geqslant 2$ 时，$2S_{n-1}=a_{n-1}a_{n}$，有 $2a_{n}=a_{n}(a_{n+1}-a_{n-1})$，",
            r"因为 $a_{n}>0$，所以 $a_{n+1}-a_{n-1}=2,n\geqslant 2$，",
            r"因为 $2a_{1}=a_{1}a_{2}$，所以 $a_{2}=2$，",
            r"所以 $a_{2n}=a_{2}+2(n-1)=2n,a_{2n-1}=a_{1}+2(n-1)=2n-1$，",
            r"可得 $a_{n}=n$，",
            r"则 $a_{n}-a_{n-1}=1(n\geqslant 2)$，即 $\{a_{n}\}$ 是等差数列．",
            r"(2) 由题意知 $b_{m}$ 表示 $3^{m}<a_{n}<3^{m+1}$ 中正整数 $n$ 的个数，",
            r"因为 $3^{m}<n<3^{m+1}$ 中有 $3^{m+1}-3^{m}-1$ 个自然数，",
            r"所以 $b_{m}=2\times 3^{m}-1$，",
            r"所以 $a_{n}b_{n}==2n\cdot 3^{n}-n$，",
            r"所以 $T_{n}=2(1\cdot 3^{1}+2\cdot 3^{2}+\cdots+n\cdot 3^{n})-(1+2+\cdots+n)$，",
            r"不妨设 $Q_{n}=1\cdot 3^{1}+2\cdot 3^{2}+\cdots+n\cdot 3^{n}$，",
            r"则 $3Q_{n}=1\cdot 3^{2}+2\cdot 3^{3}+\cdots+n\cdot 3^{n+1}$，",
            r"两式相减可得 $-2Q_{n}=3^{1}+3^{2}+3^{3}+\cdots+3^{n}-n\cdot 3^{n+1}=\dfrac{3(1-3^{n})}{1-3}-n\cdot 3^{n+1}$，",
            r"所以 $2Q_{n}=n\cdot 3^{n+1}-\dfrac{3(1-3^{n})}{1-3}=\dfrac{(2n-1)\cdot 3^{n+1}+3}{2}$，",
            r"所以 $T_{n}=2Q_{n}-(1+2+\cdots+n)=\dfrac{(2n-1)\cdot 3^{n+1}-n^{2}-n+3}{2}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"在平面直角坐标系 $xOy$ 中，已知等轴双曲线 $C:\dfrac{x^{2}}{a^{2}}-\dfrac{y^{2}}{b^{2}}=1(a>0,b>0)$ 的左、右焦点分别为 $F_{1}$、$F_{2}$，过点 $F_{2}$ 的直线与直线 $y=\dfrac{b}{a}x$ 交于点 $A$，且 $|AF_{2}|=b$，$|AF_{1}|=\sqrt{5}$．",
            r"(1) 求双曲线 $C$ 的方程；",
            r"(2) 设点 $D$、$E$ 分别为双曲线 $C$ 的左、右顶点，若点 $M$ 在直线 $x=\dfrac{1}{2}$ 上运动，且直线 $MD,ME$ 与双曲线 $C$ 分别交于 $P$、$Q$（不与 $D$、$E$ 重合）两点．",
            r"(i) 证明：直线 $PQ$ 恒过定点；",
            r"(ii) 是否存在点 $M$，使得 $\triangle MDE$ 与 $\triangle MPQ$ 的面积相等．",
        ),
        "选项": {},
        "答案": L(
            r"(1) $x^{2}-y^{2}=1$；",
            r"(2)(i) 直线 $PQ$ 恒过定点 $(2,0)$；(ii) 不存在点 $M$，使得 $\triangle MDE$ 与 $\triangle MPQ$ 的面积相等．",
        ),
        "解析": L(
            r"(1) 设 $|F_{1}F_{2}|=2c$，依题意，$a=b=\dfrac{c}{\sqrt{2}}$，",
            r"点 $F_{2}(c,0)$ 到直线 $bx-ay=0$ 的距离为 $\dfrac{|bc|}{\sqrt{a^{2}+b^{2}}}=b=|AF_{2}|$，$\therefore OA\perp AF_{2}$，",
            r"$\therefore A\left(\dfrac{c}{2},\dfrac{c}{2}\right)$，",
            r"$\therefore|AF_{1}|=\sqrt{\left(\dfrac{3c}{2}\right)^{2}+\left(\dfrac{c}{2}\right)^{2}}=\sqrt{5}$，解得 $c=\sqrt{2}$，",
            r"$\therefore a=1,b=1$，",
            r"$\therefore$ 双曲线 $C$ 的方程为 $x^{2}-y^{2}=1$．",
            r"(2)(i) 设 $M\left(\dfrac{1}{2},m\right)$，$P(x_{1},y_{1})$，$Q(x_{2},y_{2})$，",
            r"则直线 $MD,ME$ 的方程分别为 $y=\dfrac{2m}{3}(x+1)$，$y=-2m(x-1)$，",
            r"联立方程 $\begin{cases}y=\dfrac{2m}{3}(x+1)\\ x^{2}-y^{2}=1\end{cases}$，消去 $y$ 得 $(9-4m^{2})x^{2}-8m^{2}x-4m^{2}-9=0$，",
            r"$\therefore x_{1}=\dfrac{4m^{2}+9}{9-4m^{2}},y_{1}=\dfrac{2m}{3}\left(\dfrac{4m^{2}+9}{9-4m^{2}}+1\right)=\dfrac{12m}{9-4m^{2}}$，则 $P\left(\dfrac{4m^{2}+9}{9-4m^{2}},\dfrac{12m}{9-4m^{2}}\right)$，",
            r"联立方程 $\begin{cases}y=-2m(x-1)\\ x^{2}-y^{2}=1\end{cases}$，消去 $y$ 得 $(1-4m^{2})x^{2}+8m^{2}x-4m^{2}-1=0$，",
            r"$\therefore x_{2}=-\dfrac{4m^{2}+1}{1-4m^{2}},y_{2}=2m\left(\dfrac{4m^{2}+1}{1-4m^{2}}+1\right)=\dfrac{4m}{1-4m^{2}}$，则 $Q\left(-\dfrac{4m^{2}+1}{1-4m^{2}},\dfrac{4m}{1-4m^{2}}\right)$，",
            r"由对称性可知，直线 $PQ$ 过的定点在 $x$ 轴上，设为 $(t,0)$，",
            r"$\therefore\dfrac{\dfrac{12m}{9-4m^{2}}-0}{\dfrac{4m^{2}+9}{9-4m^{2}}-t}=\dfrac{\dfrac{4m}{1-4m^{2}}-0}{-\dfrac{4m^{2}+1}{1-4m^{2}}-t}$，",
            r"即 $\dfrac{12m}{4(t+1)m^{2}+9-9t}=\dfrac{4m}{4(t-1)m^{2}-t-1}$，",
            r"所以 $(8t-16)m^{2}+6t-12=0$，解得 $t=2$，",
            r"综上所述，直线 $PQ$ 恒过定点 $(2,0)$．",
            r"(ii) 易知 $\dfrac{S_{\triangle MDE}}{S_{\triangle MPQ}}=\dfrac{|MD|\cdot|ME|}{|MP|\cdot|MQ|}=\dfrac{\left|\dfrac{1}{2}-(-1)\right|}{\left|x_{P}-\dfrac{1}{2}\right|}\cdot\dfrac{\left|\dfrac{1}{2}-1\right|}{\left|x_{Q}-\dfrac{1}{2}\right|}$，",
            r"若存在点 $M$ 使得 $S_{\triangle MDE}=S_{\triangle MPQ}$，则 $\dfrac{S_{\triangle MDE}}{S_{\triangle MPQ}}=1$，有 $\dfrac{\dfrac{3}{4}}{\left|x_{P}-\dfrac{1}{2}\right|\cdot\left|x_{Q}-\dfrac{1}{2}\right|}=1$，",
            r"$\therefore\left|x_{P}-\dfrac{1}{2}\right|\cdot\left|x_{Q}-\dfrac{1}{2}\right|=\dfrac{3}{4}$，",
            r"即 $\left|\dfrac{4m^{2}+9}{9-4m^{2}}-\dfrac{1}{2}\right|\cdot\left|-\dfrac{4m^{2}+1}{1-4m^{2}}-\dfrac{1}{2}\right|=\dfrac{3}{4}$，",
            r"即 $\left|\dfrac{6m^{2}+\dfrac{9}{2}}{9-4m^{2}}\right|\cdot\left|\dfrac{2m^{2}+\dfrac{3}{2}}{1-4m^{2}}\right|=\dfrac{3}{4}$，即 $48m^{4}+72m^{2}+27=|48m^{4}-120m^{2}+27|$，",
            r"$\therefore 48m^{4}+72m^{2}+27=48m^{4}-120m^{2}+27$（舍），或 $48m^{4}+72m^{2}+27=-(48m^{4}-120m^{2}+27)$，",
            r"$\therefore 96m^{4}-48m^{2}+54=0$，$\therefore 16m^{4}-8m^{2}+9=0$，",
            r"$\because\Delta=8^{2}-4\times 16\times 9<0$，$\therefore$ 不存在点 $M$，使得 $\triangle MDE$ 与 $\triangle MPQ$ 的面积相等．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"已知函数 $f(x)=x\mathrm{e}^{2x}-a(\mathrm{e}^{x}-x)(a\in\mathbf{R})$．",
            r"(1) 若曲线 $y=f(x)$ 在点 $(0,f(0))$ 处的切线方程为 $y=x$，求 $f(x)$ 的极小值；",
            r"(2) 讨论关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数；",
            r"(3) 若某函数在区间 $[m,n]$ 上的值域恰为 $\left[\dfrac{\lambda}{n},\dfrac{\lambda}{m}\right]$，则称 $[m,n]$ 为该函数的「$\lambda$ 级转置区间」．已知函数 $g(x)=\dfrac{f(x)}{x\mathrm{e}^{x}}(x>0)$，当 $a=0$ 时，判断 $g(x)$ 是否存在「$\lambda$ 级转置区间」．若存在，求实数 $\lambda$ 的取值范围；若不存在，请说明理由．",
        ),
        "选项": {},
        "答案": L(
            r"(1) 极小值为 $f\left(-\dfrac{1}{2}\right)=-\dfrac{1}{2\mathrm{e}}$；",
            r"(2) 当 $a<-\dfrac{1}{\mathrm{e}}$ 时，$0$ 个；当 $a=-\dfrac{1}{\mathrm{e}}$ 或 $a\geqslant 0$ 时，$1$ 个；当 $-\dfrac{1}{\mathrm{e}}<a<0$ 时，$2$ 个；",
            r"(3) 存在，$\lambda$ 的取值范围为 $(\mathrm{e},+\infty)$．",
        ),
        "解析": L(
            r"(1) $f^{\prime}(x)=(1+2x)\mathrm{e}^{2x}-a(\mathrm{e}^{x}-1)$，$f^{\prime}(0)=1$，",
            r"$\therefore f(0)=-a=0$，解得 $a=0$，",
            r"$\therefore f(x)=x\mathrm{e}^{2x}$，$f^{\prime}(x)=(1+2x)\mathrm{e}^{2x}$，令 $f^{\prime}(x)=0$，解得 $x=-\dfrac{1}{2}$，",
            r"可得 $f(x)$ 在 $\left(-\infty,-\dfrac{1}{2}\right)$ 上单调递减，在 $\left(-\dfrac{1}{2},+\infty\right)$ 上单调递增．所以 $f(x)$ 在 $x=-\dfrac{1}{2}$ 处取得极小值．",
            r"$\therefore f(x)$ 的极小值为 $f\left(-\dfrac{1}{2}\right)=-\dfrac{1}{2\mathrm{e}}$．",
            r"(2) 由 $f(x)=x^{2}\mathrm{e}^{x}$ 得 $x\mathrm{e}^{2x}-(x^{2}+a)\mathrm{e}^{x}+ax=0$，即 $(\mathrm{e}^{x}-x)(x\mathrm{e}^{x}-a)=0$，",
            r"$\therefore\mathrm{e}^{x}-x=0$ 或 $x\mathrm{e}^{x}-a=0$，",
            r"令 $F(x)=\mathrm{e}^{x}-x$，则 $F^{\prime}(x)=\mathrm{e}^{x}-1$，",
            r"易知当 $x\in(-\infty,0)$ 时，$F^{\prime}(x)<0$；当 $x\in(0,+\infty)$ 时，$F^{\prime}(x)>0$，",
            r"$\therefore F(x)$ 在 $(-\infty,0)$ 上单调递减，在 $(0,+\infty)$ 上单调递增，",
            r"$\therefore F(x)\geqslant F(0)=1$，即 $\mathrm{e}^{x}-x\geqslant 1$，",
            r"$\therefore$ 方程 $\mathrm{e}^{x}-x=0$ 无解．",
            r"令 $G(x)=x\mathrm{e}^{x}$，则 $G^{\prime}(x)=(x+1)\mathrm{e}^{x}$，",
            r"易知当 $x\in(-\infty,-1)$ 时，$G^{\prime}(x)<0$；当 $x\in(-1,+\infty)$ 时，$G^{\prime}(x)>0$，",
            r"$\therefore G(x)$ 在 $(-\infty,-1)$ 上单调递减，在 $(-1,+\infty)$ 上单调递增，",
            r"$\therefore G(x)$ 的最小值为 $G(-1)=-\dfrac{1}{\mathrm{e}}$，",
            r"易知函数 $y=x\mathrm{e}^{x}$ 的大致图象如图所示，",
            r"① 当 $a<-\dfrac{1}{\mathrm{e}}$ 时，方程 $x\mathrm{e}^{x}=a$ 无解，此时关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数为 $0$；",
            r"② 当 $a=-\dfrac{1}{\mathrm{e}}$ 或 $a\geqslant 0$ 时，方程 $x\mathrm{e}^{x}=a$ 有唯一解，此时关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数为 $1$；",
            r"③ 当 $-\dfrac{1}{\mathrm{e}}<a<0$ 时，方程 $x\mathrm{e}^{x}=a$ 有两解，此时关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数为 $2$．",
            r"综上所述，当 $a<-\dfrac{1}{\mathrm{e}}$ 时，关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数为 $0$；当 $a=-\dfrac{1}{\mathrm{e}}$ 或 $a\geqslant 0$ 时，关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数为 $1$；当 $-\dfrac{1}{\mathrm{e}}<a<0$ 时，关于 $x$ 的方程 $f(x)=x^{2}\mathrm{e}^{x}$ 的实数解的个数为 $2$．",
            r"(3) 当 $a=0$ 时，$g(x)=\dfrac{f(x)}{x\mathrm{e}^{x}}=\mathrm{e}^{x}$，假设 $g(x)=\mathrm{e}^{x}(x>0)$ 存在「$\lambda$ 级转置区间」，",
            r"即存在正实数 $m,n,\lambda$，使得 $g(x)=\mathrm{e}^{x}$ 在区间 $[m,n]$ 上的值域恰为 $\left[\dfrac{\lambda}{n},\dfrac{\lambda}{m}\right]$，",
            r"易知 $g(x)=\mathrm{e}^{x}$ 在区间 $[m,n]$ 上单调递增，$\therefore\mathrm{e}^{m}=\dfrac{\lambda}{n}$，且 $\mathrm{e}^{n}=\dfrac{\lambda}{m}$，",
            r"$\therefore\ln\mathrm{e}^{m}=\ln\dfrac{\lambda}{n}$，即 $m=\ln\lambda-\ln n$，",
            r"$\therefore\dfrac{\lambda}{\mathrm{e}^{n}}=m=\ln\lambda-\ln n$，即 $\dfrac{\lambda}{\mathrm{e}^{n}}+\ln n-\ln\lambda=0$，同理可得 $\dfrac{\lambda}{\mathrm{e}^{m}}+\ln m-\ln\lambda=0$，",
            r"设函数 $h(x)=\dfrac{\lambda}{\mathrm{e}^{x}}+\ln x-\ln\lambda$，易知 $m,n$ 为 $h(x)$ 的两个零点，",
            r"$\therefore$ 函数 $h(x)$ 至少有两个零点，",
            r"对函数 $h(x)$ 求导得 $h^{\prime}(x)=-\dfrac{\lambda}{\mathrm{e}^{x}}+\dfrac{1}{x}=\dfrac{\dfrac{\mathrm{e}^{x}}{x}-\lambda}{\mathrm{e}^{x}},x\in(0,+\infty)$，",
            r"设 $\varphi(x)=\dfrac{\mathrm{e}^{x}}{x},x\in(0,+\infty)$，则 $\varphi^{\prime}(x)=\dfrac{(x-1)\mathrm{e}^{x}}{x^{2}},x\in(0,+\infty)$，",
            r"易知当 $x\in(0,1)$ 时，$\varphi(x)$ 单调递减，当 $x\in(1,+\infty)$ 时，$\varphi(x)$ 单调递增，$\therefore\varphi(x)\geqslant\varphi(1)=\mathrm{e}$，",
            r"① 当 $0<\lambda\leqslant\mathrm{e}$ 时，则 $h^{\prime}(x)\geqslant 0$，$\therefore h(x)$ 在 $(0,+\infty)$ 上单调递增，不可能有三个零点，不合题意；",
            r"② 当 $\lambda>\mathrm{e}$ 时，$h^{\prime}(x)$ 恰有两个零点 $x_{1},x_{2}$，",
            r"其中 $x_{1}\in(0,1),x_{2}\in(1,+\infty),\dfrac{\mathrm{e}^{x_{1}}}{x_{1}}=\dfrac{\mathrm{e}^{x_{2}}}{x_{2}}=\lambda$，",
            r"$\therefore h(x)$ 在 $(0,x_{1})$ 单调递增，在 $(x_{1},x_{2})$ 单调递减，在 $(x_{2},+\infty)$ 单调递增，",
            r"$\therefore h(x_{1})=\dfrac{\lambda}{\mathrm{e}^{x_{1}}}+\ln x_{1}-\ln\lambda=\dfrac{1}{x_{1}}+2\ln x_{1}-x_{1}$，",
            r"同理 $h(x_{2})=\dfrac{1}{x_{2}}+2\ln x_{2}-x_{2}$，",
            r"设 $\psi(x)=2\ln x-x+\dfrac{1}{x}$，则 $\psi^{\prime}(x)=\dfrac{-(x-1)^{2}}{x^{2}}\leqslant 0$，$\therefore\psi(x)$ 在 $(0,+\infty)$ 上单调递减，",
            r"$\because 0<x_{1}<1$，$\therefore\psi(x_{1})=2\ln x_{1}-x_{1}+\dfrac{1}{x_{1}}>\psi(1)=0$ 恒成立，即 $h(x_{1})>0$，",
            r"$\because x_{2}>1$，$\therefore\psi(x_{2})=2\ln x_{2}-x_{2}+\dfrac{1}{x_{2}}<\psi(1)=0$ 恒成立，即 $h(x_{2})<0$，",
            r"且当 $x\to 0$ 时，$h(x)\to-\infty$，当 $x\to+\infty$ 时，$h(x)\to+\infty$，",
            r"$\therefore$ 由零点存在性定理可知 $h(x)$ 在 $(0,x_{1}),(x_{1},x_{2}),(x_{2},+\infty)$ 上各有一个零点，即 $h(x)$ 有三个零点，符合题意，",
            r"$\therefore$ 当 $a=0$ 时，$g(x)$ 存在「$\lambda$ 级转置区间」，且 $\lambda$ 的取值范围为 $(\mathrm{e},+\infty)$．",
        ),
        "粗筛图": True, "粗筛表": False,
    },
]

pending = [
    {
        "题号": 15, "题型": "detailed_answer", "页码": [3], "类型": "table",
        "原文": L(
            r"为探究某药物在人体中的代谢情况，研究人员统计了血液中药物浓度 $y(\mathrm{mg/L})$ 与代谢时间 $x(\mathrm{h})$ 的相关数据，如下表所示：",
            r"(1) 若两组变量间的相关系数 $r$ 满足 $0.8\leqslant|r|<1$，则称其为高度相关，试判断血液中药物浓度与代谢时间是否高度相关，并说明理由 $\left(\dfrac{1}{\sqrt{17360}}\approx 0.0076\right.$，结果保留 $3$ 位小数$\left.\right)$；",
            r"(2) 建立 $y$ 关于 $x$ 的经验回归方程，并预测代谢 $6.2$ 小时后，血液中药物浓度．",
        ),
        "说明": L(
            r"试卷第 3 页 #15 题干里印着一张两行六列的表格（无表号），第 1 行表头为 $x$，其后五格依次 $2$、$3$、$4$、$5$、$6$；第 2 行表头为 $y$，其后五格依次 $58$、$42$、$30$、$12$、$8$。按「带图/带表题不录正文」，本题未进成品。",
            r"表格之后还印有两组随题材料，也一并登记在这里：参考数据 $\sum\limits_{i=1}^{5}(x_{i}-\overline{x})^{2}=10$，$\sum\limits_{i=1}^{5}(y_{i}-\overline{y})^{2}=1736$，$\sum\limits_{i=1}^{5}x_{i}y_{i}=470$；参考公式：相关系数 $r=\dfrac{\sum\limits_{i=1}^{n}(x_{i}-\overline{x})(y_{i}-\overline{y})}{\sqrt{\sum\limits_{i=1}^{n}(x_{i}-\overline{x})^{2}\sum\limits_{i=1}^{n}(y_{i}-\overline{y})^{2}}}=\dfrac{\sum\limits_{i=1}^{n}x_{i}y_{i}-n\overline{x}\overline{y}}{\sqrt{\sum\limits_{i=1}^{n}(x_{i}-\overline{x})^{2}\sum\limits_{i=1}^{n}(y_{i}-\overline{y})^{2}}}$，经验回归方程 $\hat{y}=\hat{a}+\hat{b}x$ 中斜率和截距最小二乘估计公式分别为 $\hat{b}=\dfrac{\sum\limits_{i=1}^{n}(x_{i}-\overline{x})(y_{i}-\overline{y})}{\sum\limits_{i=1}^{n}(x_{i}-\overline{x})^{2}}$，$\hat{a}=\overline{y}-\hat{b}\overline{x}$。",
            r"详解版答案第 2–3 页给的全解析结果：(1) $\overline{x}=4$，$\overline{y}=30$，$\sum\limits_{i=1}^{5}(x_{i}-\overline{x})(y_{i}-\overline{y})=\sum\limits_{i=1}^{5}x_{i}y_{i}-5\overline{x}\cdot\overline{y}=-130$，$r=\dfrac{-130}{\sqrt{10\times 1736}}\approx -130\times 0.0076=-0.988$，所以 $0.85\leqslant|r|<1$，血液中药物浓度与代谢时间是高度相关的；(2) $\hat{b}=-\dfrac{130}{10}=-13$，$\hat{a}=\overline{y}-\hat{b}\overline{x}=30-(-13)\times 4=82$，回归方程 $\hat{y}=-13x+82$，当 $x=6.2$ 时 $y\approx 1.4\,\mathrm{mg/L}$，即代谢 $6.2$ 小时后血液中药物浓度约为 $1.4\,\mathrm{mg/L}$。",
            r"注意：标答 (1) 末句写的是「所以 $0.85\leqslant|r|<1$」，而题干给的判据是 $0.8\leqslant|r|<1$，$0.85$ 疑为 $0.8$ 之误（已另登 print-suspect）。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [3], "类型": "print-suspect",
        "原文": r"所以 $0.85\leqslant|r|<1$，即血液中药物浓度与代谢时间是高度相关的．",
        "说明": L(
            r"题干 (1) 给的高度相关判据印作 $0.8\leqslant|r|<1$（试卷第 3 页），但详解版答案第 2 页 #15 (1) 收尾那句结论写成 $0.85\leqslant|r|<1$，两处阈值不一致。按「内容一个字都不许改」，两处都照原样登记，没有把答案里的 $0.85$ 改成 $0.8$、也没有反过来改题干。登记在此供人工判断哪一处是原意。本题因带表未进成品，故该疑点登在待复核里。",
        ),
    },
    {
        "题号": 17, "题型": "detailed_answer", "页码": [4], "类型": "figure",
        "原文": L(
            r"如图，在三棱锥 $P-ABC$ 中，$\triangle ABC$ 是边长为 $2\sqrt{3}$ 的等边三角形，$PB=PC=3$，$PB\perp AB$，$PC\perp AC$．",
            r"(1) 求 $P$ 到平面 $ABC$ 的距离；",
            r"(2) 求平面 $PBC$ 与平面 $PAB$ 夹角的余弦值．",
        ),
        "说明": L(
            r"题干以「如图」起头，试卷第 4 页 #17 右侧随题印着配图（无图号）：三棱锥 $P-ABC$，$P$ 在左上、$C$ 在上、$A$ 在右、$B$ 在下，$PA$、$PB$、$PC$、$AB$、$AC$ 画实线，$BC$ 画虚线（被遮挡的棱）。按规矩不录正文，故本题未进成品。",
            r"详解版答案第 3–4 页给的全解析结果：(1) 点 $P$ 到平面 $ABC$ 的距离为 $\sqrt{5}$；(2) 平面 $PBC$ 与平面 $PAB$ 夹角的余弦值为 $\dfrac{\sqrt{6}}{4}$。标答的 (1) 用「设 $O$ 为 $P$ 在底面 $ABC$ 的射影、$M$ 为 $BC$ 中点」推出 $\angle OBC=\angle OCB=30^{\circ}$、$OM=1$，再由 $PM=\sqrt{6}$ 得 $PO=\sqrt{5}$；(2) 另配了一幅建系图（无图号）：以 $O$ 为原点、$\overrightarrow{CB}$、$\overrightarrow{OA}$、$\overrightarrow{OP}$ 所在方向为 $x$、$y$、$z$ 轴正方向的空间直角坐标系，图上标 $P$、$C$、$A$、$B$、$M$、$O$ 与 $x$、$y$、$z$ 三轴，被遮挡的棱画虚线。交人工把两张图补进成品。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 17, "题型": "detailed_answer", "页码": [3], "类型": "print-suspect",
        "原文": r"$\therefore OM=1$，又 $PM=\sqrt{6}$，$\therefore PO=\sqrt{5}$．即点 $P$ 到平面 $ABC$ 的距离为 $\sqrt{5}$．",
        "说明": L(
            r"详解版答案第 3 页 #17 (1) 这一行里，$OM=1$ 由 $\angle OBC=\angle OCB=30^{\circ}$、$BC=2\sqrt{3}$ 可得（$OM=\sqrt{3}\tan 30^{\circ}=1$），但 $PM=\sqrt{6}$ 全篇没有出处，也没有说明 $PM$ 是哪一段、为何垂直于底面。按 (1) 的建系口径（$O$ 是 $P$ 在底面的射影、$M$ 是 $BC$ 中点、$z$ 轴沿 $\overrightarrow{OP}$），$P$、$O$、$M$ 三点共线，应有 $PM=PO=\sqrt{5}$，与 $\sqrt{6}$ 对不上；而 (2) 又印作 $P(0,0,\sqrt{5})$、$B(\sqrt{3},1,0)$、$M(0,1,0)$，按这三点算 $PM=\sqrt{0^{2}+1^{2}+(\sqrt{5})^{2}}=\sqrt{6}$，即 $\sqrt{6}$ 只有在 $P$ 的 $y$ 坐标为 $0$（$P$ 不在 $z$ 轴上）时才成立，与「$z$ 轴沿 $\overrightarrow{OP}$、$O$ 为原点」自相矛盾。",
            r"按「内容一个字都不许改」，成品/待复核里 $PM=\sqrt{6}$ 与 $P(0,0,\sqrt{5})$ 都照标答原样登记，没有替它改成 $\sqrt{5}$、也没有改坐标。最终两个答案 $\sqrt{5}$ 与 $\dfrac{\sqrt{6}}{4}$ 经独立复核自洽（用 $P(0,0,\sqrt{5})$ 与题面 $PA=PB=PC$ 反推，法向量 $\boldsymbol{n}_{1}=(0,\sqrt{5},1)$、$\boldsymbol{n}_{2}=(\sqrt{3},1,\frac{4}{\sqrt{5}})$，夹角余弦确为 $\dfrac{\sqrt{6}}{4}$），所以疑点只在「$PM=\sqrt{6}$ 这一步缺依据 + 建系口径与坐标不一致」。本题因带图未进成品，登在此处。",
        ),
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [5], "类型": "figure-in-solution",
        "原文": r"易知函数 $y=x\mathrm{e}^{x}$ 的大致图象如图所示，",
        "说明": L(
            r"题干纯文字、无图，已进成品，解析也整段录入。这里登记的是解析内部的图：详解版答案第 5 页 #19 (2) 在求出 $G(x)=x\mathrm{e}^{x}$ 的最小值 $G(-1)=-\dfrac{1}{\mathrm{e}}$ 之后，印「易知函数 $y=x\mathrm{e}^{x}$ 的大致图象如图所示」，右侧随文配一张无图号的函数图象：平面直角坐标系，$x$ 轴标 $-5$ 与 $0$，$y$ 轴标 $-1$、$0$、$2$；曲线过原点，在 $x<0$ 一侧贴 $x$ 轴下方、于 $x=-1$ 处取最低点后上升，$x>0$ 一侧急速上升；$x=-1$ 处画一条竖直虚线。解析随后 ①②③ 按 $a$ 与 $-\frac{1}{\mathrm{e}}$、$0$ 的比较讨论直线 $y=a$ 与该曲线的交点个数，这一步依赖此图。答案 (2)：$a<-\dfrac{1}{\mathrm{e}}$ 时 $0$ 个，$a=-\dfrac{1}{\mathrm{e}}$ 或 $a\geqslant 0$ 时 $1$ 个，$-\dfrac{1}{\mathrm{e}}<a<0$ 时 $2$ 个。交人工把图补进解析。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2], "类型": "print-suspect",
        "原文": r"D. $a_{1}+2a_{2}+3a_{3}\cdots+10a_{10}=19$",
        "说明": L(
            r"试卷第 2 页 #10 选项 D 印作「$a_{1}+2a_{2}+3a_{3}\cdots+10a_{10}=19$」，$3a_{3}$ 与省略号之间没有加号（同项 $a_{1}+2a_{2}+\cdots$ 前面两处都有加号）。详解版答案第 1 页 D 选项解析里同一式子也印作「$a_{1}+2a_{2}\cdots+10a_{10}=19$」，同样缺加号。按「内容一个字都不许改」，成品选项 D 与解析都照原样录入，没有替它补加号。从式子结构看本意应为 $a_{1}+2a_{2}+3a_{3}+\cdots+10a_{10}$。",
        ),
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [1], "类型": "print-suspect",
        "原文": r"对于 C 选项，令 $x=-2$，可得 $a_{0}-a_{1}+a_{2}\cdots+a_{10}=3^{9}$",
        "说明": L(
            r"详解版答案第 1 页 #10 C 选项解析：令 $x=-2$，则 $(x+1)(2x+1)^{9}=(-1)(-3)^{9}=3^{9}$，而右端 $a_{k}(x+1)^{k}=a_{k}(-1)^{k}$，故展开应为 $a_{0}-a_{1}+a_{2}-\cdots-a_{9}+a_{10}=3^{9}$，即奇偶项正负交错到 $a_{10}$ 为止；答案却写成 $a_{0}-a_{1}+a_{2}\cdots+a_{10}=3^{9}$（末项 $a_{10}$ 前是加号、且省略号处漏写符号）。随后「与 B 选项分析中的式子相加，可得 $2(a_{0}+a_{2}+a_{4}+a_{6}+a_{8}+a_{10})=3^{9}+1$」这一步按 $a_{0}-a_{1}+a_{2}-\cdots+a_{10}=3^{9}$ 才成立，且由此得 $a_{0}+a_{2}+\cdots+a_{10}=\dfrac{3^{9}+1}{2}$，与 C 选项的 $3^{9}+1$ 不符、故 C 判错，这条结论本身没问题。按「内容一个字都不许改」，成品解析照标答原样录入，没有替它补交错符号。",
        ),
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [2], "类型": "print-suspect",
        "原文": r"记函数 $f(x)=$ $\sin(\omega x$ $+$ $\varphi)\left(\omega>0,0\leqslant\varphi\leqslant\dfrac{\pi}{2}\right)$",
        "说明": L(
            r"试卷第 2 页 #13 的函数式里，$f(x)$ 与 $\sin$ 之间印的是一个居中的短横（排印位置偏高，像是把加号「$+$」印成了等号「$=$」），$\omega x$ 与 $\varphi$ 之间的加号也印得很淡、位置偏高（放大到 600 dpi 复核：$\omega x$ 与 $\varphi$ 之间确有一横一竖交叉的痕迹，判为加号；$f(x)$ 之后那一格只有一横、没有竖笔，判为等号）。按「内容一个字都不许改」，成品题干照原样录成「$f(x)=\sin(\omega x+\varphi)$」，即把 $f(x)$ 后那个符号按等号处理、$\omega x$ 与 $\varphi$ 之间按加号处理，两处都未替它改成加号或减号。详解版答案第 2 页 #13 解析里同一函数写作 $f(x)=\sin(\omega x+\varphi)$、并直接给出 $\varphi=0$ 时 $f(x)=\sin\dfrac{3}{2}x$，可佐证本意就是 $\sin(\omega x+\varphi)$。",
        ),
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3], "类型": "print-suspect",
        "原文": r"所以 $a_{n}b_{n}==2n\cdot 3^{n}-n$",
        "说明": L(
            r"详解版答案第 3 页 #16 (2) 这一行印的是两个连续的等号「$a_{n}b_{n}==2n\cdot 3^{n}-n$」，是排印重复。按「内容一个字都不许改」，成品解析照原样录入双等号，没有删掉多余的那个。另：同一页 (2) 开头「因为 $3^{m}<n<3^{m+1}$ 中有 $3^{m+1}-3^{m}-1$ 个自然数，所以 $b_{m}=2\times 3^{m}-1$」，$3^{m+1}-3^{m}-1=2\cdot 3^{m}-1$ 成立，此处无疑点。",
        ),
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4], "类型": "print-suspect",
        "原文": r"$\therefore x_{2}=-\dfrac{4m^{2}+1}{1-4m^{2}},y_{2}=2m\left(\dfrac{4m^{2}+1}{1-4m^{2}}+1\right)=\dfrac{4m}{1-4m^{2}}$",
        "说明": L(
            r"详解版答案第 4 页 #18 (2)(i) 求 $Q$ 的纵坐标这一行，中间步骤写的斜率是 $2m$，但本小问前面刚印过「直线 $ME$ 的方程为 $y=-2m(x-1)$」（$E$ 是右顶点 $(1,0)$），按 $y=-2m(x_{2}-1)=-2m\left(-\dfrac{4m^{2}+1}{1-4m^{2}}-1\right)=\dfrac{4m}{1-4m^{2}}$ 才是末项 $\dfrac{4m}{1-4m^{2}}$；即中间那一步的 $2m$ 疑为 $-2m$ 之误（写成 $2m$ 会得 $\dfrac{-4m}{1-4m^{2}}$，与末项差一个符号）。末项与 $Q$ 点坐标本身经独立复核正确。同一页 (ii) 另有一处：$\dfrac{S_{\triangle MDE}}{S_{\triangle MPQ}}=\dfrac{|MD|\cdot|ME|}{|MP|\cdot|MQ|}=\dfrac{\left|\dfrac{1}{2}-(-1)\right|}{\left|x_{P}-\dfrac{1}{2}\right|}\cdot\dfrac{\left|\dfrac{1}{2}-1\right|}{\left|x_{Q}-\dfrac{1}{2}\right|}$，第一个分子按 $D$ 为左顶点 $(-1,0)$、$M$ 在 $x=\dfrac{1}{2}$ 上应为 $\left|\dfrac{1}{2}-(-1)\right|=\dfrac{3}{2}$，与下一行「有 $\dfrac{\dfrac{3}{4}}{\left|x_{P}-\dfrac{1}{2}\right|\cdot\left|x_{Q}-\dfrac{1}{2}\right|}=1$」里的 $\dfrac{3}{4}=\dfrac{3}{2}\times\dfrac{1}{2}$ 相符，所以这一处不算错，登记只是为了说明 $\dfrac{3}{4}$ 的来源。",
            r"按「内容一个字都不许改」，成品解析两处都照标答原样录入（$y_{2}$ 那一步保留 $2m$、面积比保留 $\left|\dfrac{1}{2}-(-1)\right|$），没有替它改符号。",
        ),
    },
]

(OUT / (NAME + ".成品.json")).write_text(
    json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
(OUT / (NAME + ".待复核.json")).write_text(
    json.dumps(pending, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("成品", len(recs), "待复核", len(pending))
