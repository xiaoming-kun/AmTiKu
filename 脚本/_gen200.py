# -*- coding: utf-8 -*-
"""200 湖北圆创2026届高三2月 —— 成品 / 待复核 生成脚本。"""
import json
from pathlib import Path

OUT = Path("数据/录题/输出_v2")
STEM = "200_湖北圆创2026届高三2月"

Q = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"若复数 $z$ 满足 $(1-\mathrm{i})z=1+2\mathrm{i}$，则 $z$ 的虚部是",
        "选项": {"A": r"$-\dfrac{3}{2}$", "B": r"$-\dfrac{1}{2}$", "C": r"$\dfrac{3}{2}$", "D": r"$\dfrac{1}{2}$"},
        "答案": "C",
        "解析": r"解：$z=\dfrac{1+2\mathrm{i}}{1-\mathrm{i}}=\dfrac{(1+2\mathrm{i})(1+\mathrm{i})}{2}=\dfrac{-1+3\mathrm{i}}{2}$，虚部是 $\dfrac{3}{2}$，所以选 C。",
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"若集合 $A=\{x\mid x^2-3x-4\leqslant 0\}$，$B=\{x\mid y=\ln(1-x)\}$，则 $A\cap B=$",
        "选项": {"A": r"$[-1,1)$", "B": r"$[-1,1]$", "C": r"$(-1,1)$", "D": r"$(-1,1]$"},
        "答案": "A",
        "解析": r"解：因为 $A=\{x\mid -1\leqslant x\leqslant 4\}$，$B=\{x\mid x<1\}$，所以 $A\cap B=\{x\mid -1\leqslant x<1\}$，所以选 A。",
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"命题“对 $\forall x\in[1,2],x^2-ax+1<0$”为假命题的一个充分不必要条件是",
        "选项": {"A": r"$a\geqslant 2$", "B": r"$a\leqslant 2$", "C": r"$a\leqslant 3$", "D": r"$a>3$"},
        "答案": "B",
        "解析": "\n".join([
            r"解：原命题等价于“$\exists x\in[1,2],x^2-ax+1\geqslant 0$”为真命题，所以 $a\leqslant\left(\dfrac{x^2+1}{x}\right)_{\max}=\dfrac{5}{2}$．",
            r"又 $(-\infty,2]\subsetneq\left(-\infty,\dfrac{5}{2}\right]$，所以选 B．",
        ]),
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [1], "粗筛图": True, "粗筛表": False,
        "题干": r"若将函数 $f(x)=\cos(2x+\varphi)\left(|\varphi|<\dfrac{\pi}{2}\right)$ 的图象向右平移 $\dfrac{\pi}{3}$ 个单位长度，所得图象对应的函数为奇函数．则 $\varphi$ 的值是",
        "选项": {"A": r"$\dfrac{\pi}{3}$", "B": r"$\dfrac{\pi}{4}$", "C": r"$-\dfrac{\pi}{6}$", "D": r"$\dfrac{\pi}{6}$"},
        "答案": "D",
        "解析": "\n".join([
            r"解：平移后的图象对应的函数为 $y=\cos\left[2\left(x-\dfrac{\pi}{3}\right)+\varphi\right]=\cos\left(2x-\dfrac{2\pi}{3}+\varphi\right)$．",
            r"因为 $y=\cos\left(2x-\dfrac{2\pi}{3}+\varphi\right)$ 是奇函数，所以 $-\dfrac{2\pi}{3}+\varphi=\dfrac{\pi}{2}(2k+1)(k\in\mathbf{Z})$，",
            r"即 $\varphi=k\pi+\dfrac{7\pi}{6},(k\in\mathbf{Z})$．又 $|\varphi|<\dfrac{\pi}{2}$，所以 $\varphi=\dfrac{\pi}{6}$．所以选 D．",
        ]),
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知向量 $\boldsymbol{a},\boldsymbol{b}$ 满足 $|\boldsymbol{a}|=2$，$\boldsymbol{b}$ 在 $\boldsymbol{a}$ 上的投影向量是 $-\dfrac{1}{2}\boldsymbol{a}$，则 $|2\boldsymbol{a}-\boldsymbol{b}|$ 的最小值为",
        "选项": {"A": r"$5$", "B": r"$4$", "C": r"$3$", "D": r"$2$"},
        "答案": "A",
        "解析": "\n".join([
            r"解：因为 $\boldsymbol{b}$ 在 $\boldsymbol{a}$ 上的投影向量是 $-\dfrac{1}{2}\boldsymbol{a}$，",
            r"所以 $|\boldsymbol{b}|\cos\langle\boldsymbol{a},\boldsymbol{b}\rangle=-1$，$|\boldsymbol{b}|_{\min}=1$．",
            r"所以 $|2\boldsymbol{a}-\boldsymbol{b}|^2=4a^2-4\boldsymbol{a}\cdot\boldsymbol{b}+\boldsymbol{b}^2=16+b^2-8|\boldsymbol{b}|\cos\langle\boldsymbol{a},\boldsymbol{b}\rangle$．",
            r"所以 $|2\boldsymbol{a}-\boldsymbol{b}|_{\min}=5$，所以选 A．",
            r"另解：作图可知 $|2\boldsymbol{a}-\boldsymbol{b}|_{\min}=5$．",
        ]),
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [1], "粗筛图": True, "粗筛表": False,
        "题干": r"已知双曲线 $C:\dfrac{x^2}{4}-y^2=1$，$O$ 是坐标原点，$P$ 是 $C$ 上的一点，过 $P$ 的直线分别与 $C$ 的两条渐近线交于 $P_1,P_2$ 两点，且 $\overrightarrow{PP_2}=2\overrightarrow{P_1P}$，则 $\triangle OP_1P_2$ 的面积是",
        "选项": {"A": r"$\dfrac{5}{8}$", "B": r"$\dfrac{5}{4}$", "C": r"$\dfrac{7}{4}$", "D": r"$\dfrac{9}{4}$"},
        "答案": "D",
        "解析": "\n".join([
            r"解：设 $P_1(x_1,y_1),P_2(x_2,y_2),P_0(x_0,y_0)$，则 $\overrightarrow{PP_2}=(x_2-x_0,y_2-y_0)$，$\overrightarrow{P_1P}=(x-x_1,y-y_1)$．",
            r"因为 $\overrightarrow{PP_2}=2\overrightarrow{P_1P}$，所以 $\begin{cases}x_2-x_0=2(x_0-x_1),\\ y_2-y_0=2(y_0-y_1).\end{cases}$",
            r"所以 $\begin{cases}x_0=\dfrac{x_2+2x_1}{3},\\ y_0=\dfrac{y_2+2y_1}{3}=\dfrac{x_1-\dfrac{1}{2}x_2}{3}.\end{cases}$",
            r"所以 $x_0^2-4y_0^2=\dfrac{8}{9}x_1x_2=4$．即 $x_1x_2=\dfrac{9}{2}$．",
            r"设渐近线 $y=\dfrac{1}{2}x$ 的倾斜角为 $\alpha$，则 $\tan\alpha=\dfrac{1}{2}$，所以 $\sin 2\alpha=2\sin\alpha\cos\alpha=\dfrac{4}{5}$．",
            r"因为 $|OP_1|=\sqrt{x_1^2+y_1^2}=\sqrt{x_1^2+\dfrac{1}{4}x_1^2}=\dfrac{\sqrt{5}}{2}|x_1|$，同理 $|OP_2|=\dfrac{\sqrt{5}}{2}|x_2|$，",
            r"所以 $S_{\triangle OP_1P_2}=\dfrac{1}{2}|OP_1||OP_2|\sin 2\alpha=\dfrac{1}{2}\cdot\dfrac{\sqrt{5}}{2}|x_1|\cdot\dfrac{\sqrt{5}}{2}|x_2|\cdot\sin 2\alpha=\dfrac{9}{4}$．所以选 D．",
        ]),
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知实数 $x,y$ 满足 $(x-2)^2+(y-2)^2=\dfrac{4}{5}$，则 $\omega=\dfrac{xy}{2x^2+y^2}$ 的最小值是",
        "选项": {"A": r"$\dfrac{1}{3}$", "B": r"$\dfrac{\sqrt{2}}{4}$", "C": r"$\dfrac{\sqrt{2}}{9}$", "D": r"$\dfrac{2}{9}$"},
        "答案": "D",
        "解析": "\n".join([
            r"解：显然 $xy\neq 0$，所以 $\omega=\dfrac{1}{2\cdot\dfrac{x}{y}+\dfrac{y}{x}}$．令 $y=kx$，则 $\omega=\dfrac{1}{k+\dfrac{2}{k}}$．",
            r"考虑圆 $C$ 上的点 $P(x,y)$ 满足 $y=kx$，则直线 $y=kx$ 与圆 $C$ 有公共点．",
            r"所以 $\dfrac{|2k-2|}{1+k^2}\leqslant\dfrac{2}{\sqrt{5}}$，解得 $\dfrac{1}{2}\leqslant k\leqslant 2$．",
            r"记 $u(k)=k+\dfrac{2}{k}$，则 $u(k)$ 在 $\left[\dfrac{1}{2},\sqrt{2}\right]$ 单调递减，在 $\left[\sqrt{2},2\right]$ 单调递增．",
            r"所以 $u(k)_{\max}=u\left(\dfrac{1}{2}\right)=\dfrac{9}{2}$．从而 $\omega=\dfrac{1}{k+\dfrac{2}{k}}$ 的最小值为 $\dfrac{2}{9}$．所以选 D．",
        ]),
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"袋中有 $9$ 个除了颜色外完全相同的小球，其中有 $3$ 个白球，$2$ 个红球，$4$ 个黄球．从中不放回地取球，每次取一个球，当三种颜色的球都取到时停止．记停止时取出的球的个数为 $X$，则 $P(X=5)=$",
        "选项": {"A": r"$\dfrac{1}{63}$", "B": r"$\dfrac{3}{64}$", "C": r"$\dfrac{13}{63}$", "D": r"$\dfrac{4}{63}$"},
        "答案": "C",
        "解析": "\n".join([
            r"解：前 $4$ 次只取到红球和黄球，第 $5$ 次取到白球，$P_1=\dfrac{(A_6^4-A_4^4)C_3^1}{A_9^5}$；",
            r"前 $4$ 次只取到白球和黄球，第 $5$ 次取到红球，$P_2=\dfrac{(A_7^4-A_4^4)C_2^1}{A_9^5}$；",
            r"前 $4$ 次只取到白球和红球，第 $5$ 次取到黄球，$P_3=\dfrac{A_5^4C_4^1}{A_9^5}$．",
            r"所以 $P=P_1+P_2+P_3=\dfrac{13}{63}$，所以选 C．",
        ]),
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"下列说法中正确的是",
        "选项": {
            "A": r"若 $x>1$，则 $x+\dfrac{1}{x}$ 的最小值为 $2$",
            "B": r"若 $x<0$，则 $x+\dfrac{1}{x}$ 的最大值为 $-2$",
            "C": r"若 $a>0,b>0$，且 $a+b=1$，则 $\sqrt{a}+\sqrt{b}$ 的最大值为 $\sqrt{2}$",
            "D": r"若 $ab>0$，则 $\dfrac{a}{b}+\dfrac{b}{a}$ 的最小值为 $2$",
        },
        "答案": "BCD",
        "解析": "\n".join([
            r"解：对于 A，$x+\dfrac{1}{x}\geqslant 2\sqrt{x\cdot\dfrac{1}{x}}=2$，当且仅当 $x=1$ 时等号成立，但 $x>1$，所以等号取不到，故 A 错误；",
            r"对于 B，因为 $x<0$，所以 $-x>0$，所以 $-x+\dfrac{1}{-x}\geqslant 2\sqrt{-x\cdot\dfrac{1}{-x}}=2$，所以 $x+\dfrac{1}{x}\leqslant -2$．",
            r"当且仅当 $x=-1$ 时等号成立，所以 $x+\dfrac{1}{x}$ 的最大值为 $-2$，故 B 正确；",
            r"对于 C，$\sqrt{a}+\sqrt{b}=\sqrt{a+b+2\sqrt{ab}}=\sqrt{1+2\sqrt{ab}}\leqslant\sqrt{1+a+b}=\sqrt{2}$，当且仅当 $a=b=\dfrac{1}{2}$ 时取等号，故 C 正确；",
            r"对于 D，若 $ab>0$，则 $\dfrac{a}{b}>0,\dfrac{b}{a}>0$，所以 $\dfrac{a}{b}+\dfrac{b}{a}\geqslant 2\sqrt{\dfrac{a}{b}\cdot\dfrac{b}{a}}=2$，当且仅当 $a=b$ 时等号成立，故 D 正确．",
            r"所以选 BCD．",
        ]),
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"记 $\triangle ABC$ 的内角 $A,B,C$ 的对边分别为 $a,b,c$，下列说法中正确的是",
        "选项": {
            "A": r"若 $\sin A>\sin B$，则 $A>B$",
            "B": r"若 $\cos 2A>\cos 2B$，则 $A<B$",
            "C": r"若 $\cos A<\sin B$，则 $\triangle ABC$ 为锐角三角形",
            "D": r"若 $A=\dfrac{\pi}{3},b=2$，且 $\triangle ABC$ 为锐角三角形，则 $a$ 的取值范围是 $[2,2\sqrt{3})$",
        },
        "答案": "AB",
        "解析": "\n".join([
            r"解：对于 A，由 $\sin A>\sin B$ 及正弦定理可知：$a>b$．",
            r"又因为“三角形中大边对大角”，所以 $A>B$，故 A 正确；",
            r"对于 B，由 $\cos 2A>\cos 2B$，得 $1-2\sin^2 A>1-2\sin^2 B$，从而 $\sin^2 A<\sin^2 B$．",
            r"又 $\sin A>0,\sin B>0$，所以 $\sin A<\sin B$．由正弦定理得 $a<b$，从而 $A<B$，故 B 正确；",
            r"对于 C，当 $A=\dfrac{2\pi}{3},B=\dfrac{\pi}{4}$ 时，满足 $\cos A<\sin B$，但 $\triangle ABC$ 为钝角三角形，故 C 错误；",
            r"对于 D，因为 $A=\dfrac{\pi}{3},0<B<\dfrac{\pi}{2},0<C=\pi-\dfrac{\pi}{3}-B<\dfrac{\pi}{2}$，所以 $\dfrac{\pi}{6}<B<\dfrac{\pi}{2}$．所以 $\sin B\in\left(\dfrac{1}{2},1\right)$．",
            r"由 $\dfrac{a}{\sin A}=\dfrac{b}{\sin B}$，得 $\dfrac{a}{\sin\dfrac{\pi}{3}}=\dfrac{2}{\sin B}$，所以 $a=\dfrac{\sqrt{3}}{\sin B}$，所以 $a\in(\sqrt{3},2\sqrt{3})$，故 D 错误．",
            r"所以选 AB．",
        ]),
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"设 $(x-2)^6=a_0+a_1x+a_2x^2+\cdots+a_6x^6$，则 $a_3=$________（用数字作答）．",
        "答案": r"$-160$",
        "解析": "\n".join([
            r"解：展开式的通项为 $T_{r+1}=C_6^rx^{6-r}(-2)^r,r=0,1,\cdots,6$．",
            r"当 $6-r=3$ 时，$r=3$．所以 $a_3=(-2)^3C_6^3=-160$．",
            r"所以填 $-160$．",
        ]),
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"已知数列 $\{a_n\}$ 满足 $a_1=1,a_na_{n+1}=2^{n+1}$，且 $\lambda-a_n\leqslant 0$ 对 $\forall n\in\mathbf{N}^*$ 恒成立，则 $\lambda$ 的取值范围是________．",
        "答案": r"$(-\infty,1]$",
        "解析": "\n".join([
            r"解：因为 $a_na_{n+1}=2^{n+1}$，所以 $a_{n+1}a_{n+2}=2^{n+2}$，所以 $\dfrac{a_{n+2}}{a_n}=2$．",
            r"当 $n$ 为偶数时，$a_n=2^{\frac{n}{2}+1}$，所以 $\lambda\leqslant a_2=4$；",
            r"当 $n$ 为奇数时，$a_n=2^{\frac{n+1}{2}-1}$，所以 $\lambda\leqslant a_1=1$．综上，知 $\lambda\leqslant 1$．",
            r"所以填 $(-\infty,1]$．",
        ]),
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"已知函数 $f(x)=\begin{cases}ax+1, & 0<x<2,\\ x\left|x-a\right|, & x\geqslant 2\end{cases}$ 有最小值，则 $a$ 的取值范围是________．",
        "答案": r"$\left[\dfrac{3}{2},+\infty\right)$",
        "解析": "\n".join([
            r"解：①若 $a\leqslant 0$．当 $0<x<2$ 时，$2a+1<f(x)<1$；当 $x\geqslant 2$ 时，$f(x)=x(x-a)\geqslant 2(2-a)$．",
            r"依题意需 $2(2-a)\leqslant 2a+1$，解得 $a\geqslant\dfrac{3}{4}$（舍去）．",
            r"②若 $a\geqslant 2$．当 $0<x<2$ 时，$1<f(x)<2a+1$；当 $x\geqslant 2$ 时，$f(x)=\begin{cases}x(x-a), & x>a,\\ x(a-x), & 2\leqslant x\leqslant a.\end{cases}$",
            r"此时 $f(x)\geqslant 0$，则 $f(x)_{\min}=0$．",
            r"③若 $0<a<2$．当 $0<x<2$ 时，$1<f(x)<2a+1$；当 $x\geqslant 2$ 时，$f(x)=x(x-a)\geqslant 2(2-a)$．",
            r"则需 $2(2-a)\leqslant 1$，解得 $\dfrac{3}{2}\leqslant a<2$．",
            r"综上，$a\geqslant\dfrac{3}{2}$．所以填 $\left[\dfrac{3}{2},+\infty\right)$．",
        ]),
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [3], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"在 $\triangle ABC$ 中，内角 $A$、$B$、$C$ 所对的边分别为 $a,b,c$，$\sqrt{3}\sin A-\cos A=\dfrac{\sqrt{3}a-b}{c}$，$C$ 为锐角．",
            r"(1)求 $C$；",
            r"(2)若 $c=1$，延长 $AB$ 至 $D$，使得 $BD=2AB$，$\angle BCD=\dfrac{\pi}{6}$，求 $\triangle ABC$ 的面积．",
        ]),
        "答案": r"(1) $C=\dfrac{\pi}{6}$；(2) $\dfrac{\sqrt{3}}{2}$",
        "解析": "\n".join([
            r"解：(1)因为 $\sqrt{3}\sin A-\cos A=\dfrac{\sqrt{3}a-b}{c}$，由正弦定理，得",
            r"$\sqrt{3}\sin A\sin C-\cos A\sin C=\sqrt{3}\sin A-\sin B$．",
            r"又 $B=\pi-(A+C)$，所以 $\sin B=\sin(A+C)=\sin A\cos C+\cos A\sin C$，",
            r"所以 $\sqrt{3}\sin A\sin C=\sqrt{3}\sin A-\sin A\cos C$．",
            r"因为 $A\in(0,\pi)$，所以 $\sin A\neq 0$，所以 $\sqrt{3}\sin C+\cos C=\sqrt{3}$，即 $\sin\left(C+\dfrac{\pi}{6}\right)=\dfrac{\sqrt{3}}{2}$．",
            r"因为 $C\in\left(0,\dfrac{\pi}{2}\right)$，所以 $C+\dfrac{\pi}{6}\in\left(\dfrac{\pi}{6},\dfrac{2\pi}{3}\right)$，所以 $C+\dfrac{\pi}{6}=\dfrac{\pi}{3}$，即 $C=\dfrac{\pi}{6}$．",
            r"(2)在 $\triangle ABC$ 中，由正弦定理得 $\dfrac{c}{\sin\dfrac{\pi}{6}}=\dfrac{a}{\sin A}$①．",
            r"在 $\triangle BCD$ 中，$BD=2c$，$\angle BDC=\dfrac{2\pi}{3}-A$，",
            r"所以 $\dfrac{2c}{\sin\dfrac{\pi}{6}}=\dfrac{a}{\sin\left(\dfrac{2\pi}{3}-A\right)}$②．",
            r"由①②解得 $\cos A=0$．因为 $A\in(0,\pi)$，所以 $A=\dfrac{\pi}{2}$．",
            r"因为 $c=1,\angle ACB=\dfrac{\pi}{6}$，所以 $b=\sqrt{3}$．",
            r"所以 $S_{\triangle ABC}=\dfrac{1}{2}bc=\dfrac{1}{2}\times 1\times\sqrt{3}=\dfrac{\sqrt{3}}{2}$．",
        ]),
    },
    {
        "题号": 17, "题型": "detailed_answer", "页码": [3], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"已知函数 $f(x)=\dfrac{1}{2}x^2-ax-a\ln x$．",
            r"(1)求 $f(x)$ 的单调区间；",
            r"(2)是否存在正实数 $a$，使得 $f(x)$ 仅有 $1$ 个零点？若存在，求出 $a$ 的值；若不存在，说明理由．",
        ]),
        "答案": r"(1) 见解析；(2) 存在，$a=\dfrac{1}{2}$",
        "解析": "\n".join([
            r"解：(1)$f(x)$ 的定义域为 $(0,+\infty)$，$f'(x)=x-a-\dfrac{a}{x}=\dfrac{x^2-ax-a}{x}$．",
            r"①当 $a\leqslant 0$ 时，因为 $x>0$，所以 $f'(x)>0$．",
            r"所以 $f(x)$ 的单调递增区间为 $(0,+\infty)$，无单调递减区间；",
            r"②当 $a>0$ 时，由 $f'(x)>0$ 及 $x>0$，得 $x>\dfrac{a+\sqrt{a^2+4a}}{2}$．",
            r"所以 $f(x)$ 的单调递增区间为 $\left(\dfrac{a+\sqrt{a^2+4a}}{2},+\infty\right)$，单调递减区间为 $\left(0,\dfrac{a+\sqrt{a^2+4a}}{2}\right)$．",
            r"(2)由(1)知，当 $a>0$ 时，$f(x)$ 在 $\left(0,\dfrac{a+\sqrt{a^2+4a}}{2}\right)$ 上单调递减，在 $\left(\dfrac{a+\sqrt{a^2+4a}}{2},+\infty\right)$ 单调递增．",
            r"根据指数函数、对数函数和一次函数的增长特点，知",
            r"当 $x\to 0$ 时，$f(x)\to+\infty$；当 $x\to+\infty$ 时，$f(x)\to+\infty$．",
            r"由题意，当 $f(x)$ 仅有 $1$ 个零点时，$f\left(\dfrac{a+\sqrt{a^2+4a}}{2}\right)=0$．",
            r"令 $x_0=\dfrac{a+\sqrt{a^2+4a}}{2}$，则 $\begin{cases}f(x_0)=0,\\ f'(x_0)=0,\end{cases}$ 即 $\begin{cases}\dfrac{1}{2}x_0^2-ax_0-a\ln x_0=0,\\ x_0^2-ax_0-a=0.\end{cases}$",
            r"化简得：$2\ln x_0+x_0-1=0(*)$",
            r"令 $g(x)=2\ln x+x-1$，则 $g'(x)=\dfrac{2}{x}+1>0$．",
            r"所以 $g(x)$ 在 $(0,+\infty)$ 上单调递增，且 $g(1)=0$．",
            r"所以方程 $(*)$ 的解为 $x_0=1$．",
            r"从而 $1-a-a=0$，解得 $a=\dfrac{1}{2}$．",
            r"所以，存在满足条件的 $a$，且 $a=\dfrac{1}{2}$．",
        ]),
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"已知椭圆 $\Gamma:x^2+\dfrac{y^2}{4}=1$ 的左、右顶点分别为 $A_1,A_2$，上、下顶点分别为 $B_1,B_2$，记四边形 $A_1B_1A_2B_2$ 的内切圆为 $C$，$P$ 为 $\Gamma$ 上任意一点，过 $P$ 作 $C$ 的两条切线分别交 $\Gamma$ 于 $M$、$N$ 两点．",
            r"(1)求 $C$ 的标准方程；",
            r"(2)求证：直线 $MN$ 过定点；",
            r"(3)求 $|MP|+|NP|$ 的最小值．",
        ]),
        "答案": r"(1) $x^2+y^2=\dfrac{4}{5}$；(2) 直线 $MN$ 过定点 $O(0,0)$；(3) $\dfrac{8\sqrt{5}}{5}$",
        "解析": "\n".join([
            r"(1)由题意，知 $A_2(1,0),B_1(0,2)$，所以直线 $A_2B_1$ 方程为 $\dfrac{x}{1}+\dfrac{y}{2}=1$，即 $2x+y-2=0$．",
            r"内切圆的圆心 $C$(即原点 $O$)到直线 $A_2B_1$ 的距离为 $\dfrac{2}{\sqrt{1+2^2}}=\dfrac{2}{\sqrt{5}}$，即圆 $C$ 的半径 $r=\dfrac{2}{\sqrt{5}}$．",
            r"所以圆 $C$ 的标准方程为 $x^2+y^2=\dfrac{4}{5}$．",
            r"(2)设直线 $PM$ 方程为 $mx+ny=1$，由直线 $PM$ 与圆 $C$ 相切，可知原点 $O$ 到直线 $PM$ 距离 $d=\dfrac{1}{\sqrt{m^2+n^2}}=\dfrac{2}{\sqrt{5}}$，整理得 $m^2+n^2=\dfrac{5}{4}$．",
            r"将直线 $PM$ 的方程代入椭圆 $\Gamma$，可得 $x^2+\dfrac{y^2}{4}=(mx+ny)^2$，整理得 $(1-4n^2)\left(\dfrac{y}{x}\right)^2-8mn\dfrac{y}{x}+4-4m^2=0$．",
            r"所以 $\dfrac{y_1y_2}{x_1x_2}=\dfrac{4-4m^2}{1-4n^2}=\dfrac{4-4m^2}{1-4\left(\dfrac{5}{4}-m^2\right)}=-1$，即 $k_{OP}\cdot k_{OM}=-1$，所以 $OP\perp OM$．",
            r"同理 $OP\perp ON$，故 $M$、$O$、$N$ 三点共线，所以直线 $MN$ 过定点 $O(0,0)$．",
            r"(3)由(2)知 $M$、$O$、$N$ 三点共线，所以 $|MP|+|NP|=2|MP|=2\sqrt{|OM|^2+|OP|^2}$",
            r"设 $OP:y=kx$，代入椭圆方程得 $x^2+\dfrac{(kx)^2}{4}=1$，则 $x^2=\dfrac{4}{k^2+4}$．",
            r"所以 $|OP|^2=x^2+y^2=(1+k^2)x^2=\dfrac{4(1+k^2)}{4+k^2}$．",
            r"同理 $|OM|^2=\dfrac{4\left[1+\left(-\dfrac{1}{k}\right)^2\right]}{4+\left(-\dfrac{1}{k}\right)^2}=\dfrac{4(k^2+1)}{4k^2+1}$．",
            r"所以 $\dfrac{1}{|OP|^2}+\dfrac{1}{|OM|^2}=\dfrac{4+k^2}{4(1+k^2)}+\dfrac{4k^2+1}{4(1+k^2)}=\dfrac{5}{4}$．",
            r"因为 $(|OM|^2+|OP|^2)\left(\dfrac{1}{|OM|^2}+\dfrac{1}{|OP|^2}\right)\geqslant 4$．",
            r"所以 $|MP|=\sqrt{|OM|^2+|OP|^2}\geqslant\dfrac{4\sqrt{5}}{5}$．",
            r"所以 $|MP|+|NP|=2|MP|=2\sqrt{|OM|^2+|OP|^2}\geqslant\dfrac{8\sqrt{5}}{5}$．",
            r"当且仅当 $|OP|=|OM|=\dfrac{2\sqrt{10}}{5}$ 时取等号，所以 $|MP|+|NP|$ 的最小值为 $\dfrac{8\sqrt{5}}{5}$．",
        ]),
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"为提高学生的身体素质，某学校每天免费给学生提供水果和牛奶两种营养餐，且每人每天只能选择其中一种．经过统计分析发现：学生第一天选择水果和牛奶的概率均为 $\dfrac{1}{2}$．若前一天选择水果则第二天选择水果的概率为 $\dfrac{1}{3}$，选择牛奶的概率为 $\dfrac{2}{3}$；若前一天选择牛奶则第二天选择水果的概率为 $\dfrac{1}{2}$，选择牛奶的概率也是 $\dfrac{1}{2}$，如此往复．",
            r"(1)求某同学第 $n$ 天选择水果的概率 $P_n$；",
            r"(2)若某同学累计 $n$ 次选择水果时共花了 $X_n$ 天，求 $E(X_n)$；",
            r"(3)若某同学累计 $n$ 次选择牛奶时共花了 $Y_n$ 天，求 $E(Y_n)$．",
        ]),
        "答案": r"(1) $P_n=\dfrac{3}{7}+\dfrac{1}{14}\left(-\dfrac{1}{6}\right)^{n-1}$；(2) $E(X_n)=\dfrac{7n-1}{3}$；(3) $E(Y_n)=\dfrac{7n}{4}$",
        "解析": "\n".join([
            r"解：(1)由题意得 $P_n=\dfrac{1}{3}P_{n-1}+\dfrac{1}{2}(1-P_{n-1})=-\dfrac{1}{6}P_{n-1}+\dfrac{1}{2}$，且 $P_1=\dfrac{1}{2}$．",
            r"所以 $P_n-\dfrac{3}{7}=-\dfrac{1}{6}\left(P_{n-1}-\dfrac{3}{7}\right)$．",
            r"所以数列 $\left\{P_n-\dfrac{3}{7}\right\}$ 是以 $P_1-\dfrac{3}{7}=\dfrac{1}{14}$ 为首项，$-\dfrac{1}{6}$ 为公比的等比数列．",
            r"所以 $P_n-\dfrac{3}{7}=\dfrac{1}{14}\left(-\dfrac{1}{6}\right)^{n-1}$，所以 $P_n=\dfrac{3}{7}+\dfrac{1}{14}\left(-\dfrac{1}{6}\right)^{n-1}$．",
            r"(2)若第一天选择水果，目标达成，概率为 $\dfrac{1}{2}$；",
            r"若第一天选中牛奶，目标未达成，第二天选中水果的概率为 $\dfrac{1}{2}$，与第一天选中水果的概率相同，而目标还是选中水果，根据题设，因此还需要 $E(X_1)$ 天，所以 $X_1$ 的分布列为",
            r"\[ \begin{array}{|c|c|c|}\hline X_1 & 1 & 1+E(X_1) \\ \hline P & \dfrac{1}{2} & \dfrac{1}{2} \\ \hline\end{array} \]",
            r"所以 $E(X_1)=1+\dfrac{1}{2}E(X_1)$，解得 $E(X_1)=2$．",
            r"首先达累计 $n-1$ 天选水果时，由题设，花了 $E(X_{n-1})$ 天．",
            r"接着再选一天，如果选中水果，则目标达成，概率为 $\dfrac{1}{3}$；如果选中牛奶，则目标未达成，由于选中牛奶时，下一天选中水果的概率为 $\dfrac{1}{2}$，与第一天选中水果的概率相同，而还需要累计 $1$ 天选中水果达标，故还需要 $E(X_1)$ 天，所以达成目标一共需要 $E(X_{n-1})+1+E(X_1)=E(X_{n-1})+3$ 天．",
            r"所以 $X_n$ 的分布列为",
            r"\[ \begin{array}{|c|c|c|}\hline X_n & E(X_{n-1})+1 & E(X_{n-1})+3 \\ \hline P & \dfrac{1}{3} & \dfrac{2}{3} \\ \hline\end{array} \]",
            r"所以 $E(X_n)=E(X_{n-1})+\dfrac{7}{3}$．",
            r"所以 $E(X_n)=E(X_1)+\dfrac{7}{3}(n-1)=\dfrac{7n-1}{3}$．",
            r"(3)设第一天选牛奶的概率为 $\dfrac{2}{3}$ 时，首次选中牛奶时共选了 $Z_1$ 天．",
            r"同求 $E(X_1)$，可求得 $Z_1$ 的分布列为",
            r"\[ \begin{array}{|c|c|c|}\hline Z_1 & 1 & 1+E(Z_1) \\ \hline P & \dfrac{2}{3} & \dfrac{1}{3} \\ \hline\end{array} \]",
            r"所以 $E(Z_1)=1+\dfrac{1}{3}E(Z_1)$，解得 $E(Z_1)=\dfrac{3}{2}$．",
            r"第一天如果选中牛奶，目标达成，概率为 $\dfrac{1}{2}$；",
            r"第一天如果选中水果，目标未达成，第二天选中牛奶的概率为 $\dfrac{2}{3}$，故还需要 $E(Z_1)=\dfrac{3}{2}$ 天，合计 $\dfrac{5}{2}$ 天．",
            r"所以 $E(Y_1)=1\times\dfrac{1}{2}+\dfrac{5}{2}\times\dfrac{1}{2}=\dfrac{7}{4}$．",
            r"首先达累计 $n-1$ 天选中牛奶时，由题设，花了 $E(Y_{n-1})$ 天．",
            r"接着再选一天，如果选中牛奶，则目标达成，概率为 $\dfrac{1}{2}$；如果选中水果，则目标未达成，由于选中水果时，下一天选中水果的概率为 $\dfrac{2}{3}$，故还需要 $E(Z_1)=\dfrac{3}{2}$ 天，所以达成目标一共需要 $E(Y_{n-1})+\dfrac{5}{2}$ 天．",
            r"所以 $Y_n$ 的分布列为",
            r"\[ \begin{array}{|c|c|c|}\hline Y_n & E(Y_{n-1})+1 & E(Y_{n-1})+\dfrac{5}{2} \\ \hline P & \dfrac{1}{2} & \dfrac{1}{2} \\ \hline\end{array} \]",
            r"所以 $E(Y_n)=E(Y_{n-1})+\dfrac{7}{4}$．",
            r"所以 $E(Y_n)=E(Y_1)+\dfrac{7}{4}(n-1)=\dfrac{7n}{4}$．",
        ]),
    },
]

P = [
    {
        "题号": 11, "题型": "multi_choice", "页码": [2], "类型": "figure",
        "原文": "\n".join([
            r"如图，在三棱锥 $P-ABC$ 中，$AB\perp AC$，$AB=2AC=2$，$BP=2$．设直线 $PB$ 与平面 $ABC$ 所成的角为",
            r"$\theta$，则下列说法中正确的是",
            r"A. 存在点 $P$，使得 $PB\perp AC$",
            r"B. 恰存在两条直线 $PB$，使得直线 $PB$ 与直线 $BA$、$BC$ 所成的角均为 $\dfrac{\pi}{6}$",
            r"C. 当 $\theta=\dfrac{\pi}{4}$ 时，$\angle PBC$ 的余弦值的取值范围是 $\left[0,\dfrac{\sqrt{2}}{2}\right)$",
            r"D. 当 $\theta=\dfrac{\pi}{3}$ 时，二面角 $P-AC-B$ 的取值范围是 $\left[\dfrac{\pi}{6},\dfrac{\pi}{3}\right]$",
        ]),
        "说明": "\n".join([
            r"试卷第 2 页 #11 题干说「如图」，右侧配一幅三棱锥直观图，按「带图题不录正文」整条不进成品。",
            r"图上标注：$P$ 在上方为顶点；$A$ 标在图形中部，$B$ 在左下、$C$ 在右侧；",
            r"实线画出 $PA$、$PB$、$PC$、$BC$，虚线画出底面上的 $AB$、$AC$（被遮挡）。图上没有标长度数值。",
            r"答案册第 1 页答案表给出 #11 选 ABD；第 3 页给出逐项详解：",
            r"A 当直线 $PB$ 在平面 $ABC$ 上的投影为直线 $BA$ 时，$CA\perp$ 平面 $PAB$，从而 $AC\perp PB$，故 A 正确；",
            r"B 由 $\tan\angle ABC=\dfrac{1}{2}<\sqrt{3}$ 得 $\angle ABC<\dfrac{\pi}{3}$，恰存在两条直线 $PB$ 与 $BA$、$BC$ 所成角均为 $\dfrac{\pi}{3}$，故 B 正确；",
            r"C 由 $\cos\angle PBC=\cos\theta\cdot\cos\angle CBD$，$\theta=\dfrac{\pi}{4}$ 时 $\cos\angle PBC\in\left[-\dfrac{\sqrt{2}}{2},\dfrac{\sqrt{2}}{2}\right]$，故 C 错误；",
            r"D $\tan\angle PMQ=\dfrac{PQ}{QM}=\dfrac{\sqrt{3}}{QM}$，$QM\in[1,3]$，所以二面角 $P-AC-B$ 的范围是 $\left[\dfrac{\pi}{6},\dfrac{\pi}{3}\right]$，故 D 正确。",
            r"注意 B 项：试卷题干与选项印的是「所成的角均为 $\dfrac{\pi}{6}$」，详解里写的是「所成的角为 $\dfrac{\pi}{3}$」，两处不一致，已另登记 print-suspect。",
        ]),
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3], "类型": "figure",
        "原文": "\n".join([
            r"如图，在长方体 $ABCD-A_1B_1C_1D_1$ 中，底面 $ABCD$ 是边长为 $2$ 的正方形，高为 $4$，$M$、$N$ 分别为 $AB$，",
            r"$DD_1$ 的中点．",
            r"(1)求证：$MN\parallel$ 平面 $A_1BCD_1$；",
            r"(2)若 $P$ 为直线 $A_1B_1$ 上的动点，当二面角 $P-MC-N$ 的正弦值最大时，求 $A_1P$ 的长．",
        ]),
        "说明": "\n".join([
            r"试卷第 3 页 #16 题干说「如图」，右下配一幅长方体直观图，按「带图题不录正文」整条不进成品。",
            r"试卷图上标注：长方体 $ABCD-A_1B_1C_1D_1$，上底面 $A_1B_1C_1D_1$、下底面 $ABCD$；",
            r"$M$ 标在下底面边 $AB$ 上、$N$ 标在侧棱 $DD_1$ 上、$P$ 标在上底面边 $A_1B_1$ 靠近 $A_1$ 处；",
            r"虚线画出 $MN$、$MC$、$NC$、$MP$ 等辅助线。图上没有标长度数值。",
            r"答案册第 5 页 #16(2) 另印一幅「以 $A$ 为坐标原点的空间直角坐标系」同款长方体图，",
            r"三条坐标轴标 $x$（沿 $AB$ 方向）、$y$（沿 $AD$ 方向）、$z$（沿 $AA_1$ 方向），并在同一位置标出 $P$、$M$、$N$、$Q$。",
            r"参考答案：(1) 取 $CD_1$ 的中点 $Q$，连接 $NQ,BQ$，由 $N$ 为 $DD_1$ 的中点得 $NQ\parallel CD$ 且 $NQ=\dfrac{1}{2}CD$，",
            r"又 $M$ 为 $AB$ 的中点得 $BM\parallel CD$ 且 $BM=\dfrac{1}{2}CD$，所以 $NQ\parallel BM$ 且 $NQ=BM$，四边形 $BMNQ$ 为平行四边形，",
            r"则 $MN\parallel BQ$，又 $MN\not\subset$ 平面 $A_1BCD_1$ 且 $BQ\subset$ 平面 $A_1BCD_1$，所以 $MN\parallel$ 平面 $A_1BCD_1$；",
            r"(2) 建系后 $M(1,0,0),C(2,2,0),N(0,2,2)$，设 $P(t,0,4)$，取 $\boldsymbol{m}=(4,-2,1-t)$、$\boldsymbol{n}=(2,-1,2)$，",
            r"$\cos\langle\boldsymbol{m},\boldsymbol{n}\rangle=\dfrac{2}{3}\cdot\dfrac{6-t}{\sqrt{(t-1)^2+20}}$，正弦最大即余弦为 $0$，得 $t=6$，此时 $A_1P=6$。",
        ]),
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1], "类型": "figure-in-solution",
        "原文": r"另解：作图可知 $|2\boldsymbol{a}-\boldsymbol{b}|_{\min}=5$．",
        "说明": "\n".join([
            r"题干纯文字、无图，已照常录入成品 #5（含「解」与「另解」两段逐字照录）。",
            r"这里登记的是答案册第 1 页 #5 详解右侧印着的一幅向量示意图：",
            r"一条水平向右的实线箭头标 $\boldsymbol{a}$；从同一起点向左上方引一条实线箭头标 $\boldsymbol{b}$；",
            r"另有虚线把两箭头的端点与起点连成一个三角形（表示 $\boldsymbol{b}$ 在 $\boldsymbol{a}$ 反方向上的投影）。图上没有标数值。",
            r"这幅图只服务于「另解」，正文里的代数解法已完整给出 $|2\boldsymbol{a}-\boldsymbol{b}|_{\min}=5$，答案 A。",
        ]),
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4], "类型": "table",
        "原文": r"所以 $X_1$ 的分布列为 …… 所以 $X_n$ 的分布列为 …… 可求得 $Z_1$ 的分布列为 …… 所以 $Y_n$ 的分布列为",
        "说明": "\n".join([
            r"题干纯文字、正文已入库（成品 #19），这里登记的不是题干里的表，而是答案册详解里印着的四张两行三列分布列表。",
            r"成品 #19 的解析里已把它们原样转成 $\begin{array}{|c|c|c|}\end{array}$ 表格录入，人工请按答案册逐格核对：",
            r"① 第 7 页 $X_1$ 表：第一行表头 $X_1$，其后 $1$、$1+E(X_1)$；第二行表头 $P$，其后 $\dfrac{1}{2}$、$\dfrac{1}{2}$。",
            r"② 第 8 页 $X_n$ 表：第一行表头 $X_n$，其后 $E(X_{n-1})+1$、$E(X_{n-1})+3$；第二行表头 $P$，其后 $\dfrac{1}{3}$、$\dfrac{2}{3}$。",
            r"③ 第 8 页 $Z_1$ 表：第一行表头 $Z_1$，其后 $1$、$1+E(Z_1)$；第二行表头 $P$，其后 $\dfrac{2}{3}$、$\dfrac{1}{3}$。",
            r"④ 第 8 页 $Y_n$ 表：第一行表头 $Y_n$，其后 $E(Y_{n-1})+1$、$E(Y_{n-1})+\dfrac{5}{2}$；第二行表头 $P$，其后 $\dfrac{1}{2}$、$\dfrac{1}{2}$。",
            r"四张表后面紧跟的递推式与结果都直接引用表里的数，最终答案 (1) $P_n=\dfrac{3}{7}+\dfrac{1}{14}\left(-\dfrac{1}{6}\right)^{n-1}$；(2) $E(X_n)=\dfrac{7n-1}{3}$；(3) $E(Y_n)=\dfrac{7n}{4}$。",
        ]),
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [1], "类型": "print-suspect",
        "原文": r"A. $\dfrac{1}{3}$  B. $\dfrac{\sqrt{2}}{4}$  C. $\dfrac{\sqrt{2}}{9}$  D. $\dfrac{2}{9}$",
        "说明": "\n".join([
            r"疑在哪：试卷第 1 页最下方（#7 的四个选项所在那一行）整行扫描失焦，A、B 两项的字形糊在一起；",
            r"C、D 两项清晰，读作 $\dfrac{\sqrt{2}}{9}$ 与 $\dfrac{2}{9}$。",
            r"为什么只能这样录：源 PDF 第 1 页内嵌图只有 $1190\times1684$（约 $144$ dpi），",
            r"取页已经把它渲染到 $1500\times2123$，再用 $500/600/900$ dpi 重裁与自动对比度增强都不增加细节，",
            r"所以 A、B 无法从像素上直接确认。",
            r"判读依据（供人工复核）：答案册第 2 页详解给出 $\omega=\dfrac{1}{k+\frac{2}{k}}$，$k\in\left[\dfrac{1}{2},2\right]$，",
            r"$u(k)=k+\dfrac{2}{k}\in\left[2\sqrt{2},\dfrac{9}{2}\right]$，故 $\omega$ 的最小值为 $\dfrac{2}{9}$、最大值为 $\dfrac{1}{2\sqrt{2}}=\dfrac{\sqrt{2}}{4}$，",
            r"且 $u(2)=3$ 对应 $\dfrac{1}{3}$。把 A、B 读作 $\dfrac{1}{3}$ 与 $\dfrac{\sqrt{2}}{4}$ 既与残存字形（A 分子是窄的「1」、分母两瓣；",
            r"B 分子带根号、分母上半有孔）相符，也正好是本题两个最自然的干扰值。C 项 $\dfrac{\sqrt{2}}{9}$ 与 B 项字形不同，可排除重复。",
            r"未做任何改正或补全，按上述判读照录，交人工对照清晰原卷复核这两项。",
        ]),
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2], "类型": "print-suspect",
        "原文": r"B. 恰存在两条直线 $PB$，使得直线 $PB$ 与直线 $BA$、$BC$ 所成的角均为 $\dfrac{\pi}{6}$",
        "说明": "\n".join([
            r"疑在哪：试卷第 2 页 #11 的 B 项印「与直线 $BA$、$BC$ 所成的角均为 $\dfrac{\pi}{6}$」，",
            r"而答案册第 3 页详解对同一项写的是「恰存在两条直线 $PB$，使得它与直线 $BA$、$BC$ 所成的角为 $\dfrac{\pi}{3}$，",
            r"此时点 $P$ 在平面 $ABC$ 上的投影在 $\angle ABC$ 的平分线上，故 B 正确」，两处角度值不一致。",
            r"为何没改：卷面这一行清晰可读，确实印的是 $\dfrac{\pi}{6}$，属试卷与详解之间的排版分歧，",
            r"看不出哪一份才是原意（$\angle ABC<\dfrac{\pi}{3}$ 这一判据对 $\dfrac{\pi}{3}$ 才成立），",
            r"故成品与登记都按试卷印文照录 $\dfrac{\pi}{6}$，不代它订正。",
        ]),
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4], "类型": "print-suspect",
        "原文": r"时，下一天选中水果的概率为 $\dfrac{2}{3}$，故还需要 $E(Z_1)=\dfrac{3}{2}$ 天，所以达成目标一共需要 $E(Y_{n-1})+\dfrac{5}{2}$ 天．",
        "说明": "\n".join([
            r"疑在哪：答案册第 8 页 #19(3) 这一句印「由于选中水果时，下一天选中水果的概率为 $\dfrac{2}{3}$」，",
            r"按题干「前一天选择水果则第二天选择水果的概率为 $\dfrac{1}{3}$，选择牛奶的概率为 $\dfrac{2}{3}$」，",
            r"此处应为「下一天选中牛奶的概率为 $\dfrac{2}{3}$」，才与它引用的 $Z_1$（首次选中牛奶）对得上；",
            r"同一页前面那句「第一天如果选中水果，目标未达成，第二天选中牛奶的概率为 $\dfrac{2}{3}$」用的就是「牛奶」。",
            r"为何没改：已把该行裁出放大 $2.4$ 倍重读，卷面确实印的是「水果」，属详解笔误；",
            r"按「内容一个字都不许改」照录入成品「解析」字段，只在此登记。",
        ]),
    },
]

for r in Q:
    for k in ("题干", "答案", "解析"):
        if isinstance(r.get(k), str):
            r[k] = r[k].replace("\\n", "\n")
for r in P:
    for k in ("原文", "说明"):
        r[k] = r[k].replace("\\n", "\n")

bad = []
for r in Q + P:
    vals = []
    for k, v in r.items():
        if isinstance(v, str):
            vals.append((k, v))
        elif isinstance(v, dict):
            vals += [(k + "." + a, b) for a, b in v.items()]
    for k, s in vals:
        ctrl = [hex(ord(c)) for c in s if ord(c) < 32 and c != "\n"]
        if ctrl:
            bad.append((r["题号"], k, ctrl))
        if "$$" in s:
            bad.append((r["题号"], k, "adjacent $$"))
        if s.count("$") % 2:
            bad.append((r["题号"], k, "odd $"))
        if "见待复核登记" in s or ("答案册第" in s and k in ("题干", "解析", "答案")):
            bad.append((r["题号"], k, "self-comment leaked"))
assert not bad, bad

(OUT / f"{STEM}.成品.json").write_text(
    json.dumps(Q, ensure_ascii=False, indent=1) + "\n", "utf-8")
(OUT / f"{STEM}.待复核.json").write_text(
    json.dumps(P, ensure_ascii=False, indent=1) + "\n", "utf-8")
print("成品", len(Q), "待复核", len(P))
