import json, re, sys
from pathlib import Path

sys.path.insert(0, ".")
from amti.record2 import FIG_WORD, TABLE_WORD

OUT = Path("数据/录题/输出_v2")
NAME = "243_福建泉州养正中学、安溪一中、惠安一中、泉州实验中2026届高三下学期开学"

Q = []


def rec(n, t, page, stem, opts, ans, sol):
    Q.append({
        "题号": n, "题型": t, "页码": page, "题干": stem, "选项": opts,
        "答案": ans, "解析": sol,
        "粗筛图": bool(FIG_WORD.search(stem)), "粗筛表": bool(TABLE_WORD.search(stem)),
    })


rec(1, "single_choice", [1],
    r"已知集合 $A=\left\{x|\dfrac{2}{x}\geqslant1\right\}$，集合 $B=\{x|\sqrt{x+1}\leqslant2\}$，则 $A\cap B=$",
    {"A": r"$(-\infty,2]$", "B": r"$(0,5]$", "C": r"$(0,2]$", "D": r"$[1,5]$"},
    "C",
    "\n".join([
        r"【分析】求出集合 $A$、$B$，利用交集的定义可求得集合 $A\cap B$．",
        r"【详解】由 $\dfrac{2}{x}\geqslant1$ 得 $1-\dfrac{2}{x}=\dfrac{x-2}{x}\leqslant0$，解得 $0<x\leqslant2$，即 $A=\left\{x|\dfrac{2}{x}\geqslant1\right\}=\{x|0<x\leqslant2\}$，又 $B=\{x|\sqrt{x+1}\leqslant2\}=\{x|0\leqslant x+1\leqslant4\}=\{x|-1\leqslant x\leqslant3\}$，故 $A\cap B=\{x|0<x\leqslant2\}=(0,2]$．",
    ]))

rec(2, "single_choice", [1],
    r"已知复数 $z$ 满足 $\dfrac{5-z}{2z}=1+2\mathrm{i}$，则 $|z|=$",
    {"A": r"$1$", "B": r"$2$", "C": r"$3$", "D": r"$4$"},
    "A",
    "\n".join([
        r"【分析】变形给定等式得 $5=z(3+4\mathrm{i})$，再利用复数的除法求出 $z$，进而求出其模．",
        r"【详解】由 $\dfrac{5-z}{2z}=1+2\mathrm{i}$，得 $5-z=2z(1+2\mathrm{i})$，即 $5=z(3+4\mathrm{i})$，因此 $z=\dfrac{5(3-4\mathrm{i})}{(3+4\mathrm{i})(3-4\mathrm{i})}=\dfrac{5(3-4\mathrm{i})}{25}=\dfrac{3-4\mathrm{i}}{5}=\dfrac{3}{5}-\dfrac{4}{5}\mathrm{i}$，所以 $|z|=\sqrt{\left(\dfrac{3}{5}\right)^2+\left(-\dfrac{4}{5}\right)^2}=1$．",
    ]))

rec(3, "single_choice", [1],
    r"已知 $a+b=6$，若在 $a,b$ 之间插入 $n$ 个数 $x_1,x_2,\cdots,x_n$，使得这 $n+2$ 个数成等差数列，若 $\sum\limits_{i=1}^{n}x_i=36$，则 $n=$",
    {"A": r"$10$", "B": r"$12$", "C": r"$14$", "D": r"$24$"},
    "B",
    "\n".join([
        r"【分析】根据等差数列的性质求解即可．",
        r"【详解】因为 $a,x_1,x_2,\cdots,x_n,b$ 成等差数列，所以 $x_1+x_n=6$，$\sum\limits_{i=1}^{n}x_i=\dfrac{n(x_1+x_n)}{2}$，所以 $3n=36$，可得 $n=12$．",
    ]))

rec(4, "single_choice", [1],
    r"已知椭圆 $C:\dfrac{x^2}{25}+\dfrac{y^2}{16}=1$ 的一个焦点为 $F$，点 $P$，$Q$ 是 $C$ 上关于原点对称的两点，则 $|PF|^2+8|QF|$ 的取值范围是",
    {"A": r"$[63,79]$", "B": r"$[64,79]$", "C": r"$[64,78]$", "D": r"$[64,80]$"},
    "D",
    "\n".join([
        r"【分析】由 $A$ 是左焦点，连接 $AP,AQ,FP,FQ$，利用椭圆对称性及定义，将目标式化为 $|PF|^2+8|QF|=|PF|^2-8|PF|+80$，结合 $a-c\leqslant|PF|\leqslant a+c$ 及二次函数性质求范围．",
        r"【详解】椭圆 $C:\dfrac{x^2}{25}+\dfrac{y^2}{16}=1$ 的长半轴长 $a=5$，半焦距 $c=\sqrt{25-16}=3$，由椭圆的对称性，不妨令 $F$ 为右焦点，$A$ 是左焦点，连接 $AP,AQ,FP,FQ$，又 $P,Q$ 关于原点对称，则四边形 $APFQ$ 为平行四边形或 $P,Q$ 为左右顶点，则 $|AQ|=|PF|$，$|AP|=|QF|$，由 $|PF|+|PA|=|QF|+|QA|=2a=10$，则 $|PF|+|QF|=10$，故 $|QF|=10-|PF|$，则 $|PF|^2+8|QF|=|PF|^2-8|PF|+80=(|PF|-4)^2+64$，而 $2\leqslant|PF|\leqslant8$，所以 $|PF|^2+8|QF|\in[64,80]$．",
    ]))

rec(5, "single_choice", [1],
    r"$(x^2-x+y)^6$ 的展开式中 $x^5y^3$ 的系数为",
    {"A": r"$60$", "B": r"$20$", "C": r"$-20$", "D": r"$-60$"},
    "D",
    "\n".join([
        r"【分析】利用二项展开式的通项公式可求 $x^5y^3$ 的系数．",
        r"【详解】$(x^2-x+y)^6=[(x^2-x)+y]^6$，展开式的通项公式为 $T_{r+1}=\mathrm{C}_6^r(x^2-x)^{6-r}y^r$，令 $r=3$，故 $T_4=T_{3+1}=\mathrm{C}_6^3(x^2-x)^3y^3$，$(x^2-x)^3$ 的展开式的通项公式为 $S_{k+1}=\mathrm{C}_3^k x^{2(3-k)}(-x)^k=(-1)^k\mathrm{C}_3^k x^{6-k}$，令 $6-k=5$，则 $k=1$，故 $x^5y^3$ 的系数为 $\mathrm{C}_6^3(-1)^1\mathrm{C}_3^1=-60$．",
    ]))

rec(6, "single_choice", [1],
    r"若对任意 $x_1,x_2\in(0,2]$，且 $x_1\neq x_2$，都有 $\dfrac{\ln\dfrac{x_2}{x_1}+\dfrac{a(x_1-x_2)}{(x_1+1)(x_2+1)}}{x_2-x_1}>-1$，则 $a$ 的取值范围是",
    {"A": r"$\left(-\infty,\dfrac{27}{4}\right]$", "B": r"$(-\infty,2]$",
     "C": r"$\left(-\infty,\dfrac{27}{2}\right]$", "D": r"$(-\infty,8]$"},
    "A",
    "\n".join([
        r"【分析】不妨假设 $x_1<x_2$，由题意可得 $\ln x_2+\dfrac{a}{x_2+1}+x_2>\ln x_1+\dfrac{a}{x_1+1}+x_1$，即函数 $h(x)=\ln x+\dfrac{a}{x+1}+x$ 在 $(0,2]$ 上单调递增，再根据 $h'(x)\geqslant0$ 在 $(0,2]$ 上恒成立，可得到 $a\leqslant\dfrac{(x+1)^3}{x}$，然后求出函数 $\varphi(x)=\dfrac{(x+1)^3}{x}$ 的最小值，即可解出．",
        r"【详解】不妨假设 $x_1<x_2$，则 $\dfrac{\ln\dfrac{x_2}{x_1}+\dfrac{a(x_1-x_2)}{(x_1+1)(x_2+1)}}{x_2-x_1}>-1$ 可变形为 $\ln x_2+\dfrac{a}{x_2+1}+x_2>\ln x_1+\dfrac{a}{x_1+1}+x_1$，即函数 $h(x)=\ln x+\dfrac{a}{x+1}+x$ 在 $(0,2]$ 上单调递增，所以 $h'(x)\geqslant0$ 在 $(0,2]$ 上恒成立，即 $\dfrac{1}{x}-\dfrac{a}{(x+1)^2}+1\geqslant0$，化简得 $a\leqslant\dfrac{(x+1)^3}{x}$，设 $\varphi(x)=\dfrac{(x+1)^3}{x}$，$\varphi'(x)=\dfrac{(x+1)^2(2x-1)}{x^2}$，易知函数 $\varphi(x)$ 在 $\left(0,\dfrac{1}{2}\right)$ 上单调递减，在 $\left(\dfrac{1}{2},2\right)$ 上单调递增，所以 $\varphi(x)_{\min}=\varphi\left(\dfrac{1}{2}\right)=\dfrac{27}{4}$，即 $a\leqslant\dfrac{27}{4}$．",
    ]))

rec(7, "single_choice", [1],
    "\n".join([
        r"在空间中，我们把点集 $M=\{(x,y,z)|x^2+y^2=r^2,r>0,z\in\mathbf{R}\}$ 表示的曲面 $T$ 称为圆柱面，借助比利时数学家 Dandelin 的思想我们不难发现：任意不与 $z$ 轴平行或垂直的平面截 $T$ 所得封闭曲线为椭圆．设圆柱面 $E:\{(x,y,z)|x^2+y^2=1,z\in\mathbf{R}\}$，正四棱锥 $P-ABCD$ 的五个顶点均在 $E$ 上，且 $z$ 轴与面 $ABCD$ 的夹角为 $\dfrac{\pi}{4}$，则正四棱锥 $P-ABCD$ 的体积为",
    ]),
    {"A": r"$\dfrac{3\sqrt{2}}{4}$", "B": r"$\dfrac{8\sqrt{2}}{9}$", "C": r"$\dfrac{8\sqrt{5}}{3}$", "D": r"$\dfrac{6}{2}$"},
    "B",
    "\n".join([
        r"【分析】利用题意结合给定定义得到椭圆方程，进而求出底面面积，最后利用棱锥的体积公式表示出体积．",
        r"【详解】由题意可知圆柱面的半径为 $1$，如图，平面 $ABCD$ 截圆柱面所得的截面为椭圆，记椭圆与过点 $P$ 的母线的交点为 $M$，该椭圆的半短轴长即为圆柱面的半径 $1$．因为四棱锥 $P-ABCD$ 为正四棱锥，所以四边形 $ABCD$ 为正方形，设正方形 $ABCD$ 的中心为 $O$，则 $PO\perp$ 平面 $ABCD$，故 $\overrightarrow{PO}$ 为平面 $ABCD$ 的法向量，因为 $z$ 轴与面 $ABCD$ 的夹角为 $\dfrac{\pi}{4}$，$PM//z$ 轴，$\angle MPO=\dfrac{\pi}{4}$，因为 $PO\perp$ 平面 $ABCD$，$OM\subset$ 平面 $ABCD$，所以 $PO\perp OM$，所以 $\triangle POM$ 为等腰直角三角形，又点 $O$ 到直线 $PM$ 的距离为 $1$，所以椭圆的长轴长为 $2\sqrt{2}$，$PO=\sqrt{2}$，如图建立平面直角坐标系，则椭圆方程为 $\dfrac{x^2}{2}+y^2=1$，四边形 $ABCD$ 为椭圆的内接正方形，由对称性可得直线 $BD$ 的方程为 $y=x$，联立 $\begin{cases}\dfrac{x^2}{2}+y^2=1\\ y=x\end{cases}$，消 $y$ 得到 $x^2=\dfrac{2}{3}$，故图中点 $D$ 的坐标为 $\left(\dfrac{\sqrt{6}}{3},\dfrac{\sqrt{6}}{3}\right)$，所以四边形 $ABCD$ 的面积 $S=\dfrac{2\sqrt{6}}{3}\times\dfrac{2\sqrt{6}}{3}=\dfrac{8}{3}$，所以四棱锥 $P-ABCD$ 的体积 $V=\dfrac{1}{3}S\cdot PO=\dfrac{1}{3}\times\dfrac{8}{3}\times\sqrt{2}=\dfrac{8\sqrt{2}}{9}$．",
    ]))

rec(8, "single_choice", [1],
    r"已知函数 $f(x)=\sin ax\tan bx(a>0,b>0)$，若 $f(x)\geqslant0$，则 $\log_{\sqrt{2}}\dfrac{a}{1+ab}$ 的最大值为",
    {"A": r"$-2$", "B": r"$-1$", "C": r"$1$", "D": r"$2$"},
    "B",
    "\n".join([
        r"【分析】根据题意，可得 $\sin ax$ 与 $\tan bx$ 周期相同，即 $a=2b$，再利用基本不等式求最值．",
        r"【详解】因为函数 $f(x)\geqslant0$ 恒成立，所以 $\sin ax$ 与 $\tan bx$ 同号或为 $0$，则 $\sin ax$ 与 $\tan bx$ 周期相同，即 $\dfrac{2\pi}{a}=\dfrac{\pi}{b}$，可得 $a=2b>0$，则 $\dfrac{a}{1+ab}=\dfrac{2b}{1+2b^2}=\dfrac{2}{\frac{1}{b}+2b}$，所以 $\dfrac{1}{b}+2b\geqslant2\sqrt{\dfrac{1}{b}\cdot2b}=2\sqrt{2}$，则 $\dfrac{2}{\frac{1}{b}+2b}\leqslant\dfrac{\sqrt{2}}{2}$，当且仅当 $\dfrac{1}{b}=2b$，即 $b=\dfrac{\sqrt{2}}{2}$ 时，等号成立，所以 $\log_{\sqrt{2}}\dfrac{a}{1+ab}\leqslant\log_{\sqrt{2}}\dfrac{\sqrt{2}}{2}=-1$．",
    ]))

rec(9, "multi_choice", [2],
    r"已知函数 $f(x)=\dfrac{4}{e^x-1}+2$，则",
    {"A": r"曲线 $f(x)$ 与 $y$ 轴无公共点",
     "B": r"曲线 $y=f(x)$ 关于原点对称",
     "C": r"$f(a^2+1)<f(2a)$",
     "D": r"不存在 $M>0$，$|f(x)|\leqslant M$"},
    "ABD",
    "\n".join([
        r"【分析】利用指数函数的性质及函数的单调性、奇偶性一一判定选项即可．",
        r"【详解】对于 $A$ 项，由 $f(x)=\dfrac{4}{e^x-1}+2$ 可知 $\mathrm{e}^x-1\neq0$，所以 $x\neq0$，即其定义域为 $(-\infty,0)\cup(0,+\infty)$，$A$ 正确；",
        r"对于 $B$ 项，$f(x)=\dfrac{2(\mathrm{e}^x+1)}{\mathrm{e}^x-1}$，$f(-x)=\dfrac{2(\mathrm{e}^{-x}+1)}{\mathrm{e}^{-x}-1}=\dfrac{2(\mathrm{e}^x+1)}{1-\mathrm{e}^x}$，显然 $f(x)=-f(-x)$，所以 $f(x)$ 为奇函数，$B$ 正确；",
        r"对于 $C$ 项，由 $A$ 项结论可知显然错误；",
        r"对于 $D$ 项，由指数函数的性质知：当 $x\in(-\infty,0)\cup(0,+\infty)$ 时，$\mathrm{e}^x-1\in(-1,0)\cup(0,+\infty)$，所以 $\dfrac{4}{\mathrm{e}^x-1}\in(-\infty,-4)\cup(0,+\infty)$，则 $f(x)\in(-\infty,-2)\cup(2,+\infty)$，故 $D$ 正确．",
    ]))

rec(10, "multi_choice", [2],
    r"已知 $A$，$B$ 为随机事件，且 $P(A)=0.5$，$P(B)=0.4$，则下列结论正确的是",
    {"A": r"若 $A$，$B$ 互斥，则 $P(A\cup B)=0.9$",
     "B": r"若 $A$，$B$ 相互独立，则 $P(A\overline{B})=0.2$",
     "C": r"若 $A$，$B$ 相互独立，则 $P(A\cup B)=0.7$",
     "D": r"若 $P(B|A)=0.5$，则 $P(B|\overline{A})=0.3$"},
    "ACD",
    "\n".join([
        r"【分析】根据互斥事件、相互独立事件的概率公式以及条件概率公式逐个计算，分别对每个选项进行分析判断．",
        r"【详解】对于 $A$ 选项，若 $A$，$B$ 互斥，根据互斥事件的概率加法公式 $P(A\cup B)=P(A)+P(B)$．已知 $P(A)=0.5$，$P(B)=0.4$，则 $P(A\cup B)=0.5+0.4=0.9$，所以 $A$ 选项正确．",
        r"对于 $B$ 选项，若 $A$，$B$ 相互独立，则 $A$ 与 $\overline{B}$ 也相互独立．因为 $P(\overline{B})=1-P(B)=1-0.4=0.6$，所以 $P(A\overline{B})=P(A)P(\overline{B})=0.5\times0.6=0.3\neq0.2$，所以 $B$ 选项错误．",
        r"对于 $C$ 选项，若 $A$，$B$ 相互独立，则 $P(AB)=P(A)P(B)=0.5\times0.4=0.2$．根据概率的加法公式 $P(A\cup B)=P(A)+P(B)-P(AB)$，将 $P(A)=0.5$，$P(B)=0.4$，$P(AB)=0.2$ 代入可得：$P(A\cup B)=0.5+0.4-0.2=0.7$，所以 $C$ 选项正确．",
        r"对于 $D$ 选项，已知 $P(B|A)=\dfrac{P(AB)}{P(A)}=0.5$，$P(A)=0.5$，则 $P(AB)=0.5\times0.5=0.25$．$P(\overline{A})=1-P(A)=1-0.5=0.5$，$P(B\overline{A})=P(B)-P(AB)=0.4-0.25=0.15$．根据条件概率公式 $P(B|\overline{A})=\dfrac{P(B\overline{A})}{P(\overline{A})}=\dfrac{0.15}{0.5}=0.3$，所以 $D$ 选项正确．",
    ]))

rec(11, "multi_choice", [2],
    "\n".join([
        r"已知数列 $\{a_n\}$ 的前 $n$ 项和为 $S_n$，满足 $a_1=2$，$a_3=8$，$a_{n+1}+a_{n-1}=2a_n(n\geqslant2)$，数列 $\{b_n\}$ 满足 $b_1=2$，$b_{n+1}=2b_n$，记 $c_n=a_{b_n}$，数列 $\{c_n\}$ 的前 $n$ 项和为 $T_n$，则下列说法正确的是",
        r"A. $S_n=\dfrac{3n^2+n}{2}$",
        r"B. $T_n=3\cdot2^{n+1}-7$",
        r"C. 若 $T_n\leqslant2025$，则 $n$ 的最大值为 $8$",
        r"D. 满足 $2S_n\geqslant b_n$ 的最大 $n$ 值为 $8$",
    ]),
    {},
    "AC",
    "\n".join([
        r"【分析】根据已知及等差数列的定义确定数列 $\{a_n\}$ 是等差数列，进而求公差并写出 $S_n$ 判断 $A$；根据等比数列的定义写出 $\{b_n\}$ 的通项公式，进而得到 $c_n=3\cdot2^n-1$，应用分组求和、等比数列的前 $n$ 项和公式求 $T_n$ 判断 $B$；首先判断 $T_n$ 的单调性，再由不等式恒成立求 $n$ 的最大值判断 $C$；设 $f(n)=b_n-2S_n=2^n-3n^2-n$ 并判断 $f(n+1)-f(n)=2^n-6n-4$ 的单调性，进而确定 $n$ 的最大值",
        r"【详解】对于 $A$，因为 $a_{n+1}+a_{n-1}=2a_n(n\geqslant2)$，所以 $a_{n+1}-a_n=a_n-a_{n-1}$，所以数列 $\{a_n\}$ 是等差数列，设公差为 $d$，因为 $a_1=2$，$a_3=8$，所以 $2d=8-2=6$，解得 $d=3$，所以 $a_n=a_1+(n-1)d=3n-1$，$S_n=\dfrac{n(a_1+a_n)}{2}=\dfrac{3n^2+n}{2}$，正确；",
        r"对于 $B$，因为 $b_1=2$，$b_{n+1}=2b_n$，所以 $\dfrac{b_{n+1}}{b_n}=2$，所以数列 $\{b_n\}$ 是公比为 $2$ 的等比数列，所以 $b_n=b_1q^{n-1}=2\times2^{n-1}=2^n$，所以 $c_n=a_{b_n}=3b_n-1=3\cdot2^n-1$，所以 $T_n=3\cdot\dfrac{2(1-2^n)}{1-2}-n=3\cdot2^{n+1}-n-6$，错误．",
        r"对于 $C$，由 $B$ 知 $T_n=3\cdot2^{n+1}-n-6$，所以 $T_{n+1}-T_n=3\cdot2^{n+2}-3\cdot2^{n+1}-1=3\cdot2^{n+1}-1>0$ 恒成立，所以数列 $\{T_n\}$ 单调递增，当 $n=8$ 时，$T_8=3\cdot2^9-8-6=1522<2025$，当 $n=9$ 时，$T_9=3\cdot2^{10}-9-6=3057>2025$，所以 $n$ 的最大值为 $8$，正确；",
        r"对于 $D$，设 $f(n)=b_n-2S_n=2^n-3n^2-n$，则 $f(n+1)-f(n)=2^{n+1}-3(n+1)^2-n-1-(2^n-3n^2-n)=2^n-6n-4$，令 $g(n)=2^n-6n-4$，所以 $g(n+1)-g(n)=2^n-6$，当 $n\geqslant3$ 时，$g(n+1)-g(n)>0$，即 $g(n+1)>g(n)$，所以当 $n\geqslant3$ 时，$g(n)$ 单调递增，即当 $n\geqslant3$ 时 $f(n+1)-f(n)=2^n-6n-4$ 单调递增，当 $n=1$ 时，$f(2)-f(1)=-8<0$，即 $f(1)>f(2)$；当 $n=2$ 时，$f(3)-f(2)=-12<0$，即 $f(2)>f(3)$；当 $n=3$ 时，$f(4)-f(3)=-14<0$，即 $f(3)>f(4)$；当 $n=4$ 时，$f(5)-f(4)=-12<0$，即 $f(4)>f(5)$；当 $n=5$ 时，$f(6)-f(5)=-2<0$，即 $f(5)>f(6)$；当 $n=6$ 时，$f(7)-f(6)=24>0$，即 $f(7)>f(6)$，所以当 $1\leqslant n\leqslant6$ 时，$f(n)=2^n-3n^2-n$ 单调递减，当 $n\geqslant6$ 时，$f(n)=2^n-3n^2-n$ 单调递增，因为 $f(1)=-2<0$，$f(7)=-19<0$，$f(8)=56>0$，所以满足 $2S_n\geqslant b_n$，$n$ 的最大值为 $7$，错误．",
        r"【点睛】关键点点睛：根据已知求出 $S_n$，$b_n$，$T_n$ 的通项公式为关键．",
    ]))

rec(12, "fill_in_blank", [2],
    r"已知向量 $\boldsymbol{a}=(1,-1)$，$\boldsymbol{b}=(m,1)$．若 $\boldsymbol{a}\perp\boldsymbol{b}$，则 $|\boldsymbol{b}|=$________．",
    {}, r"$\sqrt{2}$",
    "\n".join([
        r"【分析】根据 $\boldsymbol{a}\perp\boldsymbol{b}$ 得到 $\boldsymbol{a}\cdot\boldsymbol{b}=m-2=0$，解得答案．",
        r"【详解】$\boldsymbol{a}\perp\boldsymbol{b}$，则 $\boldsymbol{a}\cdot\boldsymbol{b}=(1,-2)\cdot(m,1)=m-2=0$，解得 $m=2$，所以 $|\boldsymbol{b}|=2$．故答案为 $\sqrt{2}$．",
    ]))

rec(13, "fill_in_blank", [2],
    r"已知抛物线 $C_1:y^2=4x$ 的焦点为 $F_1$，抛物线 $C_2:y^2=16x$ 的焦点为 $F_2$，若直线 $y=m(m>0)$ 分别与 $C_1$，$C_2$ 交于 $P$，$Q$ 两点，且 $|PF_1|-|QF_2|=3$，则 $m=$ ________．",
    {}, r"$4\sqrt{2}$",
    "\n".join([
        r"【分析】根据抛物线 $C_1$ 方程求出准线方程；设 $P(x_1,y_1),Q(x_2,y_2)$，利用抛物线定义求出 $|PF_1|=x_1+1,|QF_2|=x_2+4$，运算得解．",
        r"【详解】由抛物线 $C_1:y^2=4x$，可得 $F_1(1,0)$，抛物线 $C_1$ 的准线方程为 $x=-1$．设 $P(x_1,y_1),Q(x_2,y_2)$，则 $|PF_1|=x_1+1,|QF_2|=x_2+4$，故 $|PF_1|-|QF_2|=x_1-x_2-3=3$，所以 $x_1-x_2=6$，所以 $\dfrac{m^2}{4}-\dfrac{m^2}{16}=6$，解得 $m=4\sqrt{2}$．故答案为：$m=4\sqrt{2}$．",
    ]))

rec(14, "fill_in_blank", [2],
    "\n".join([
        r"马尔科夫链是概率统计中的一个重要模型，也是机器学习和人工智能的基石，为状态空间中经过从一个状态到另一个状态的转换的随机过程，该过程要求具备“无记忆”的性质：下一状态的概率分布只能由当前状态决定，在时间序列中它前面的事件均与之无关．甲口袋中各装有 $1$ 个黑球和 $2$ 个白球，乙口袋中装有 $2$ 个黑球和 $1$ 个白球，现从甲、乙两口袋中各任取一个球交换放入另一口袋，重复进行 $n(n\in\mathbf{N})$ 次这样的操作，记口袋甲中黑球的个数为 $X_n$，恰有 $1$ 个黑球的概率为 $p_n$，则 $p_1$ 的值是 ________；$X_n$ 的数学期望 $E(X_n)$ 是 ________．",
    ]),
    {}, r"$\dfrac{4}{9}$，$\dfrac{3}{2}-\dfrac{1}{2}\left(\dfrac{1}{3}\right)^n$",
    "\n".join([
        r"【分析】利用全概率公式求出 $p_1$；利用期望的计算公式求出 $E(X_n)$ 有关的递推式，然后构造等比数列求通项即可．",
        r"【详解】考虑到乙袋中拿出的球可能是黑的也可能是白的，由全概率公式可得 $p_1=\dfrac{1}{3}\times\dfrac{2}{3}+\dfrac{2}{3}\times\dfrac{1}{3}=\dfrac{4}{9}$；记 $X_{n-1}$ 取 $0,1,2,3$ 的概率分别为 $p_0,p_1,p_2,p_3$，推导 $X_n$ 的分布列：$P(X_n=1)=p_0+\dfrac{4}{9}p_1+\dfrac{4}{9}p_2$，$P(X_n=2)=\dfrac{4}{9}p_1+\dfrac{4}{9}p_2+p_3$，$P(X_n=3)=\dfrac{1}{9}p_2$，则 $E(X_n)=0\cdot P(X_n=0)+1\cdot P(X_n=1)+2\cdot P(X_n=2)+3\cdot P(X_n=3)=p_0+\dfrac{4}{3}p_1+\dfrac{5}{3}p_2+2p_3=1+\dfrac{1}{3}(p_1+2p_2+3p_3)=1+\dfrac{1}{3}E(X_{n-1})$，则 $E(X_n)-\dfrac{3}{2}=\dfrac{1}{3}\left[E(X_{n-1})-\dfrac{3}{2}\right]$，故 $E(X_n)-\dfrac{3}{2}=\left[E(X_1)-\dfrac{3}{2}\right]\times\left(\dfrac{1}{3}\right)^{n-1}$，给合 $E(X_1)=\dfrac{4}{3}$，可知 $E(X_n)=\dfrac{3}{2}-\dfrac{1}{2}\left(\dfrac{1}{3}\right)^n$．故答案为：$\dfrac{4}{9}$，$\dfrac{3}{2}-\dfrac{1}{2}\left(\dfrac{1}{3}\right)^n$．",
    ]))

rec(15, "detailed_answer", [2],
    "\n".join([
        r"已知 $a,b,c$ 分别是 $\triangle ABC$ 内角 $A,B,C$ 的对边，$a^2+b^2-c^2=\sqrt{2}ab$．",
        r"(1)若 $c=\sqrt{2},a=1$，求 $\triangle ABC$ 的面积；",
        r"(2)若 $\overrightarrow{AD}=\overrightarrow{DB},\cos B=\dfrac{2\sqrt{5}}{5}$，求 $\angle BCD$ 的正切值．",
    ]),
    {},
    "\n".join([
        r"(1) $\dfrac{\sqrt{3}+1}{4}$；",
        r"(2) $\dfrac{1}{4}$",
    ]),
    "\n".join([
        r"【分析】(1) 由 $a^2+b^2-c^2=\sqrt{2}ab$ 及余弦定理求出 $C$，再由正弦定理求出 $A$，由内角和求出 $B$，由面积公式求解；(2) 在 $\triangle BCD$ 中，有 $\dfrac{DB}{\sin\alpha}=\dfrac{CD}{\sin B}$，在 $\triangle ACD$ 中，有 $\dfrac{DA}{\sin(45^\circ-\alpha)}=\dfrac{CD}{\sin A}$，两式相比化简求值．",
        r"【详解】(1) 因为 $a^2+b^2-c^2=\sqrt{2}ab$，所以 $\cos C=\dfrac{a^2+b^2-c^2}{2ab}=\dfrac{\sqrt{2}}{2}$．因为 $0^\circ<C<180^\circ$，所以 $C=45^\circ$，因为 $\dfrac{a}{\sin A}=\dfrac{c}{\sin C}$，$c=\sqrt{2},a=1$，所以 $\dfrac{1}{\sin A}=\dfrac{\sqrt{2}}{\sin45^\circ}$．所以 $\sin A=\dfrac{1}{2}$，又 $a<c$，所以 $A=30^\circ$，所以 $B=105^\circ$，$\sin105^\circ=\sin(60^\circ+45^\circ)=\dfrac{\sqrt{3}}{2}\times\dfrac{\sqrt{2}}{2}+\dfrac{1}{2}\times\dfrac{\sqrt{2}}{2}=\dfrac{\sqrt{6}+\sqrt{2}}{4}$，所以 $S_{\triangle ABC}=\dfrac{1}{2}ac\sin B=\dfrac{1}{2}\times1\times\sqrt{2}\times\dfrac{\sqrt{6}+\sqrt{2}}{4}=\dfrac{\sqrt{3}+1}{4}$．",
        r"(2) 因为 $\overrightarrow{AD}=\overrightarrow{DB}$，所以 $D$ 为 $AB$ 中点．由题设 $a^2+b^2-c^2=\sqrt{2}ab$ 及余弦定理可得 $C=45^\circ$，因为 $\cos B=\dfrac{2\sqrt{5}}{5}$，所以 $\sin B=\dfrac{\sqrt{5}}{5}$．$\sin A=\sin(B+C)=\dfrac{\sqrt{5}}{5}\times\dfrac{\sqrt{2}}{2}+\dfrac{2\sqrt{5}}{5}\times\dfrac{\sqrt{2}}{2}=\dfrac{3\sqrt{10}}{10}$．设 $\angle BCD=\alpha$，在 $\triangle BCD$ 中，有 $\dfrac{DB}{\sin\alpha}=\dfrac{CD}{\sin B}$ ①，在 $\triangle ACD$ 中，有 $\dfrac{DA}{\sin(45^\circ-\alpha)}=\dfrac{CD}{\sin A}$ ②，②相除，得：$\dfrac{\sin(45^\circ-\alpha)}{\sin\alpha}=\dfrac{3\sqrt{2}}{2}$，所以 $\dfrac{\sqrt{2}}{2}\left(\dfrac{\cos\alpha}{\sin\alpha}-1\right)=\dfrac{3\sqrt{2}}{2}$，所以 $\dfrac{\cos\alpha}{\sin\alpha}=4$，即 $\tan\alpha=\dfrac{1}{4}$，所以 $\angle BCD$ 的正切值为 $\dfrac{1}{4}$．",
    ]))

rec(18, "detailed_answer", [4],
    "\n".join([
        r"已知函数 $f(x)=\ln x-ax$．",
        r"(1)讨论 $f(x)$ 的单调性；",
        r"(2)若 $f(x)$ 有两个零点 $x_1$，$x_2$，且 $b$ 满足 $ax_1x_2+b(x_1+x_2)<0$ 恒成立，求 $b$ 的取值范围．",
    ]),
    {},
    "\n".join([
        r"(1) 答案见解析；",
        r"(2) $\left(-\infty,-\dfrac{1}{2}\right]$",
    ]),
    "\n".join([
        r"【分析】(1) 求导 $f'(x)=\dfrac{1}{x}-a=\dfrac{1-ax}{x}$，讨论 $a\leqslant0$，$a>0$ 得到函数的单调区间；(2) 由题可得 $0<a<\dfrac{1}{e}$ 时，$f(x)$ 有两个零点 $x_1,x_2$，不妨设 $x_1<x_2$，进而可得 $\ln\dfrac{x_2}{x_1}+b\dfrac{x_2^2-x_1^2}{x_1x_2}=\ln\dfrac{x_2}{x_1}+b\left(\dfrac{x_2}{x_1}-\dfrac{x_1}{x_2}\right)<0$，令 $\dfrac{x_2}{x_1}=t(t>1)$，即 $\ln t+b\left(t-\dfrac{1}{t}\right)<0$ 在 $t\in(1,+\infty)$ 上恒成立，再根据函数的单调性得到取值范围．",
        r"【详解】(1) $f(x)$ 的定义域为 $(0,+\infty)$ 且 $f'(x)=\dfrac{1}{x}-a=\dfrac{1-ax}{x}(x>0)$．①当 $a\leqslant0$ 时，$f'(x)>0$，$f(x)$ 在 $(0,+\infty)$ 上单调递增；②当 $a>0$ 时，令 $f'(x)=0$，则 $x=\dfrac{1}{a}$，当 $0<x<\dfrac{1}{a}$ 时，$f'(x)>0$；当 $x>\dfrac{1}{a}$ 时，$f'(x)<0$，所以 $f(x)$ 在 $\left(0,\dfrac{1}{a}\right)$ 上单调递增，在 $\left(\dfrac{1}{a},+\infty\right)$ 上单调递减．",
        r"(2) 由(1)可知，当 $a\leqslant0$ 时，$f(x)$ 单调递增，至多有一个零点，舍去；若 $a>0$ 时，由 $x\to0^+$，$f(x)\to-\infty$，$x\to+\infty$，$f(x)\to-\infty$，则要使 $f(x)$ 有两个零点，只需 $f\left(\dfrac{1}{a}\right)=-\ln a-1>0$，从而 $0<a<\dfrac{1}{e}$．故 $0<a<\dfrac{1}{e}$ 时，$f(x)$ 有两个零点 $x_1,x_2$，不妨设 $x_1<x_2$．由(1)易知 $0<x_1<\dfrac{1}{a}<x_2$，$\therefore\begin{cases}\ln x_1=ax_1,\\ \ln x_2=ax_2,\end{cases}\therefore\ln\dfrac{x_2}{x_1}=a(x_2-x_1)$，$\therefore a=\dfrac{\ln x_2-\ln x_1}{x_2-x_1}$，$ax_1x_2+b(x_1+x_2)=\ln\dfrac{x_2}{x_1}\cdot\dfrac{x_1x_2}{x_2-x_1}+b(x_1+x_2)<0$，即 $\ln\dfrac{x_2}{x_1}+b\dfrac{x_2^2-x_1^2}{x_1x_2}=\ln\dfrac{x_2}{x_1}+b\left(\dfrac{x_2}{x_1}-\dfrac{x_1}{x_2}\right)<0$．令 $\dfrac{x_2}{x_1}=t(t>1)$，$\therefore\ln t+b\left(t-\dfrac{1}{t}\right)<0$ 在 $t\in(1,+\infty)$ 上恒成立．因为 $\ln t>0$，$t-\dfrac{1}{t}>0$，易知 $b<0$，令 $g(t)=\ln t+b\left(t-\dfrac{1}{t}\right)$，则 $g(1)=0$，$g'(t)=\dfrac{1}{t}+b\left(1+\dfrac{1}{t^2}\right)=\dfrac{b(1+t^2)+t}{t^2}=\dfrac{bt^2+t+b}{t^2}(t>1)$．令 $h(t)=bt^2+t+b$，$h(1)=1+2b$，对称轴 $t_0=-\dfrac{1}{2b}$．①若 $h(1)\leqslant0$，即 $b\leqslant-\dfrac{1}{2}$ 时，$t_0\leqslant1$，故 $h(t)<0$，$g(t)$ 在 $(1,+\infty)$ 上单调递减，则 $g(t)<g(1)=0$，符合题意；②若 $h(1)>0$，即 $0>b>-\dfrac{1}{2}$ 时，$t_0>1$，故存在唯一 $t_1\in(1,+\infty)$，有 $h(t_1)=0$，从而 $g(t)$ 在 $(1,t_1)$ 上单调递增，在 $(t_1,+\infty)$ 上单调递减，从而 $g(t_1)>g(1)=0$，不合题意．综上所述，$b$ 的取值范围是 $\left(-\infty,-\dfrac{1}{2}\right]$．",
    ]))

rec(19, "detailed_answer", [4],
    "\n".join([
        r"设抛物线 $C_1:y^2=2px$（$p$ 为常数，且 $p>0$）的焦点为 $F$，准线为 $l$，点 $A$ 在 $C_1$ 上且位于第一象限，过点 $A$ 作 $l$ 的垂线，垂足为 $H$．",
        r"(1)若点 $A$ 的坐标为 $(1,4)$，求 $|HF|$．",
        r"(2)设过 $F$，$A$，$H$ 三点可作椭圆 $C_2$，且 $C_2$ 的两个焦点均在 $x$ 轴上，记 $x$ 轴正半轴上的焦点为 $B$，且 $B$ 在 $F$ 的左侧．",
        r"(i)证明：$\triangle AHB$ 的周长为定值．",
        r"(ii)证明：$C_2$ 的离心率大于 $\dfrac{1}{4}$．",
    ]),
    {},
    "\n".join([
        r"(1) $4\sqrt{5}$；",
        r"(2)(i) 证明见解析；(ii) 证明见解析．",
    ]),
    "\n".join([
        r"【分析】(1) 将点代入抛物线求参数，进而确定焦点和 $H$ 的坐标，应用两点间距离公式求距离；(2)(i) 设 $A(x_0,y_0)$，$x_0>0$，$y_0>0$，$H\left(-\dfrac{p}{2},y_0\right)$，$F\left(\dfrac{p}{2},0\right)$，分析得 $C_2$ 的中心 $O'\left(\dfrac{2x_0-p}{4},0\right)$，$C_2$ 长半轴长 $a=|x_F-x_{O'}|=\dfrac{3p-2x_0}{4}$，设 $C_2$ 的左焦点为 $B'$，$|HB|=|AB'|$，结合周长为 $L=|AH|+|AB|+|HB|$，椭圆和抛物线的定义即可证；(ii) 首先得到 $x_B=\dfrac{2x_0-p}{4}+\dfrac{e(3p-2x_0)}{4}$，从而有 $e>\dfrac{p-2x_0}{3p-2x_0}$，短半轴长为 $b$，则 $b^2=a^2(1-e^2)$，最后结合 $A(x_0,y_0)$ 在椭圆上及 $y_0^2=2px_0$，整理化简得到 $e^2=\dfrac{p-6x_0}{p-2x_0}$，进而得 $x_0<\dfrac{p}{6}$，再应用分析法即可证．",
        r"【详解】(1) 将点 $A(1,4)$ 的坐标代入 $y^2=2px$，得 $4^2=2p\cdot1$，解得 $p=8$，则 $C_1$ 的方程为 $y^2=16x$，$F(4,0)$，$l$ 的方程为 $x=-4$，则 $H(-4,4)$，故 $|HF|=\sqrt{(4+4)^2+(0-4)^2}=4\sqrt{5}$；",
        r"(2)(i) 设 $A(x_0,y_0)$，$x_0>0$，$y_0>0$，则 $y_0^2=2px_0$，由题意知 $H\left(-\dfrac{p}{2},y_0\right)$，$F\left(\dfrac{p}{2},0\right)$，因为 $C_2$ 经过 $A,H$ 两点，且这两个点的纵坐标相同，根据椭圆的对称性，得 $C_2$ 的短轴必在线段 $AH$ 的垂直平分线上，且 $C_2$ 的中心 $O'$ 的横坐标 $x_{O'}=\dfrac{x_0-\frac{p}{2}}{2}=\dfrac{2x_0-p}{4}$，又 $C_2$ 的焦点均在 $x$ 轴上，所以 $O'$ 在 $x$ 轴上，即 $O'\left(\dfrac{2x_0-p}{4},0\right)$．设 $C_2$ 的长半轴长为 $a$，则 $a=|x_F-x_{O'}|=\dfrac{p}{2}-\dfrac{2x_0-p}{4}=\dfrac{3p-2x_0}{4}>0$．设 $C_2$ 的左焦点为 $B'$，则 $|HB|=|AB'|$，则 $\triangle AHB$ 的周长 $L=|AH|+|AB|+|HB|=|AH|+(|AB|+|AB'|)=|AH|+2a$．因为 $|AH|=x_0+\dfrac{p}{2}$，且 $2a=\dfrac{3p-2x_0}{2}$，所以 $L=x_0+\dfrac{p}{2}+\dfrac{3p-2x_0}{2}=2p$，故 $\triangle AHB$ 的周长为定值．",
        r"(ii) 设 $C_2$ 的焦距为 $2c$，离心率为 $e$，则 $c=ae$，由(i)，$F$ 为 $C_2$ 的右顶点，$B$ 为右焦点，则 $x_B=x_{O'}+c=x_{O'}+ae=\dfrac{2x_0-p}{4}+\dfrac{e(3p-2x_0)}{4}$．由 $B$ 在 $x$ 正半轴上知 $x_B>0$，则 $2x_0-p+e(3p-2x_0)>0$，所以 $e>\dfrac{p-2x_0}{3p-2x_0}$，设 $C_2$ 的短半轴长为 $b$，则 $b^2=a^2(1-e^2)$，将点 $A(x_0,y_0)$ 的坐标代入 $C_2$ 的方程 $\dfrac{(x-x_{O'})^2}{a^2}+\dfrac{y^2}{a^2(1-e^2)}=1$，并结合 $y_0^2=2px_0$，得 $\dfrac{(x_0-x_{O'})^2}{a^2}+\dfrac{2px_0}{a^2(1-e^2)}=1$，整理得 $\dfrac{2px_0}{1-e^2}=a^2-(x_0-x_{O'})^2$，代入 $a$ 与 $x_{O'}$，化简得 $\dfrac{2px_0}{1-e^2}=\dfrac{p(p-2x_0)}{2}$，解得 $e^2=\dfrac{p-6x_0}{p-2x_0}$，因为点 $A$ 在第一象限且 $F$ 为 $C_2$ 的右顶点，所以 $\dfrac{p}{2}>x_0$，即 $p>2x_0$，由 $\dfrac{p-6x_0}{p-2x_0}>0$ 知，$p-6x_0>0$，则 $x_0<\dfrac{p}{6}$，所以 $e>\dfrac{p-2x_0}{3p-2x_0}=1+\dfrac{2p}{2x_0-3p}>1+\dfrac{2p}{2\times\frac{p}{6}-3p}=\dfrac{1}{4}$，故 $C_2$ 的离心率大于 $\dfrac{1}{4}$，得证．",
    ]))

# ---------------- 待复核 ----------------
R = []


def pd(n, t, page, kind, raw, note):
    R.append({"题号": n, "题型": t, "页码": page, "类型": kind, "原文": raw, "说明": note})


pd(16, "detailed_answer", [3], "figure",
   "\n".join([
       r"如图，在三棱锥 $D-ABC$ 中，平面 $DAB\perp$ 平面 $ABC$，$AB\perp AC$，$AB\perp AD$，$AB=AC=AD=2$，$E$，$F$ 分别为 $DA$，$DC$ 的中点．",
       r"(1)求 $BC$ 与平面 $BEF$ 所成角的正弦值；",
       r"(2)线段 $BF$ 的延长线上是否存在点 $M$，使得平面 $BEF$ 与平面 $ACM$ 夹角的余弦值为 $\dfrac{3\sqrt{10}}{10}$？若存在，求出 $\dfrac{BM}{BF}$ 的值，若不存在，说明理由．",
   ]),
   "\n".join([
       r"试卷第 3 页 #16 题干右侧印一幅三棱锥直观图：$D$ 为顶点，$A$（中下）、$B$（左下）、$C$（右下）为底面三点，$E$ 标在棱 $DA$ 上、$F$ 标在棱 $DC$ 上，$EF$、$BE$、$BF$、$AC$ 等以虚线/实线区分。题干自带「如图」，按规矩不录正文。答案册第 4 页另印两幅以 $A$ 为原点、$AB,AC,AD$ 为 $x,y,z$ 轴正方向的建系图（第二幅多标出点 $M$）。",
       r"答案册第 3–4 页的完整解答，答案 (1) $\dfrac{\sqrt{10}}{10}$；(2) 存在，$\dfrac{BM}{BF}=2$：",
       r"(1) 因为平面 $DAB\perp$ 平面 $ABC$，平面 $DAB\cap$ 平面 $ABC=AB$，$AB\perp AC$，$AC\subset$ 平面 $ABC$，所以 $AC\perp$ 平面 $DAB$，因为 $AB,AD\subset$ 平面 $DAB$，所以 $AC\perp AB$，$AC\perp AD$，又 $AB\perp AD$，因为 $AB=AC=2$，所以 $BC=\sqrt{AC^2+AB^2}=2\sqrt{2}$．以 $A$ 为原点，$AB$、$AC$、$AD$ 为 $x,y,z$ 轴正方向建系，则 $B(2,0,0),E(0,0,1),C(0,2,0),F(0,1,1)$，所以 $\overrightarrow{BC}=(-2,2,0),\overrightarrow{BE}=(-2,0,1),\overrightarrow{BF}=(-2,1,1)$，设平面 $BEF$ 的法向量 $\boldsymbol{n}=(x,y,z)$，则 $\begin{cases}\boldsymbol{n}\cdot\overrightarrow{BE}=0\\ \boldsymbol{n}\cdot\overrightarrow{BF}=0\end{cases}$，即 $\begin{cases}-2x+z=0\\ -2x+y+z=0\end{cases}$，令 $x=1$，则 $z=2,y=0$，所以 $\boldsymbol{n}=(1,0,2)$，设 $BC$ 与平面 $BEF$ 所成角为 $\theta$，则 $\sin\theta=|\cos\langle\boldsymbol{n},\overrightarrow{BC}\rangle|=\dfrac{|-2|}{\sqrt{8}\times\sqrt{5}}=\dfrac{\sqrt{10}}{10}$，所以 $BC$ 与平面 $BEF$ 所成角的正弦值 $\dfrac{\sqrt{10}}{10}$．",
       r"(2) 假设存在点 $M$，设 $\dfrac{BM}{BF}=\lambda(\lambda>1)$，则 $\overrightarrow{BM}=\lambda\overrightarrow{BF}=(-2\lambda,\lambda,\lambda)$，所以 $\overrightarrow{AM}=\overrightarrow{AB}+\overrightarrow{BM}=(2-2\lambda,\lambda,\lambda)$，$\overrightarrow{AC}=(0,2,0)$，设平面 $ACM$ 的法向量 $\boldsymbol{m}=(x_1,y_1,z_1)$，则 $\begin{cases}\boldsymbol{m}\cdot\overrightarrow{AM}=0\\ \boldsymbol{m}\cdot\overrightarrow{AC}=0\end{cases}$，即 $\begin{cases}(2-2\lambda)x_1+\lambda y_1+\lambda z_1=0\\ 2y_1=0\end{cases}$，令 $z_1=1$，则 $x_1=\dfrac{\lambda}{2\lambda-2},y_1=0$，即 $\boldsymbol{m}=\left(\dfrac{\lambda}{2\lambda-2},0,1\right)$，所以 $\cos\langle\boldsymbol{m},\boldsymbol{n}\rangle=\dfrac{\left|\dfrac{\lambda}{2\lambda-2}+2\right|}{\sqrt{\left(\dfrac{\lambda}{2\lambda-2}\right)^2+1}\cdot\sqrt{5}}=\dfrac{3\sqrt{10}}{10}$，整理得 $7\left(\dfrac{\lambda}{2\lambda-2}\right)^2-\dfrac{8\lambda}{2\lambda-2}+1=0$，解得 $\dfrac{\lambda}{2\lambda-2}=1$ 或 $\dfrac{1}{7}$，所以 $\lambda=2$ 或 $\lambda=-\dfrac{2}{5}$（舍），所以存在点 $M$ 使得平面 $BEF$ 与平面 $ACM$ 夹角的余弦值为 $\dfrac{3\sqrt{10}}{10}$，且 $\dfrac{BM}{BF}=2$．",
   ]))

pd(17, "detailed_answer", [3], "table",
   "\n".join([
       r"规定抽球试验规则如下：盒子中初始装有白球和红球各一个，每次有放回的任取一个，连续取两次将以上过程记为一轮．如果每一轮取到的两个球都是白球，则记该轮为成功，否则记为失败．在抽取过程中，如果某一轮成功，则停止；否则，在盒子中再放入一个红球，然后接着进行下一轮抽球，如此不断继续下去，直至成功．",
       r"(1)某人进行该抽球试验时，最多进行三轮，即使第三轮不成功，也停止抽球，记其进行抽球试验的轮次数为随机变量 $X$，求 $X$ 的分布列和数学期望；",
       r"(2)为验证抽球试验成功的概率不超过 $\dfrac{1}{2}$，有 $1000$ 名数学爱好者独立的进行该抽球试验，记 $t$ 表示成功时抽球试验的轮次数，$y$ 表示对应的人数，部分统计数据如下：",
       r"$\begin{array}{|c|c|c|c|c|c|}\hline t & 1 & 2 & 3 & 4 & 5\\\hline y & 232 & 98 & 60 & 40 & 20\\\hline\end{array}$",
       r"求 $y$ 关于 $t$ 的回归方程 $\hat{y}=\dfrac{\hat{b}}{t}+\hat{a}$，并预测成功的总人数（精确到 $1$）；",
       r"(3)证明：$\dfrac{1}{2^2}+\left(1-\dfrac{1}{2^2}\right)\dfrac{1}{3^2}+\left(1-\dfrac{1}{2^2}\right)\left(1-\dfrac{1}{3^2}\right)\dfrac{1}{4^2}+\cdots+\left(1-\dfrac{1}{2^2}\right)\left(1-\dfrac{1}{3^2}\right)\cdots\left(1-\dfrac{1}{n^2}\right)\dfrac{1}{(n+1)^2}<\dfrac{1}{2}$．",
       r"附：回归方程 $y=bx+a$ 中 $b$ 和 $a$ 的最小二乘估计公式：$\hat{b}=\dfrac{\sum_{i=1}^{n}x_iy_i-n\bar{x}\cdot\bar{y}}{\sum_{i=1}^{n}x_i^2-n\bar{x}^2}$，$\hat{a}=\bar{y}-\hat{b}\bar{x}$；参考数据：$\sum_{i=1}^{5}x_i^2=1.46$，$\bar{x}=0.46$，$\bar{x}^2=0.212$（其中 $x_i=\dfrac{1}{t_i}$，$\bar{x}=\dfrac{1}{5}\sum_{i=1}^{5}x_i$）．",
   ]),
   "\n".join([
       r"试卷第 3 页 #17 的 (2) 里印一张 $2$ 行 $6$ 列的统计表：第一行 $t$、$1$、$2$、$3$、$4$、$5$；第二行 $y$、$232$、$98$、$60$、$40$、$20$。整题带表，按规矩不录正文（本条「原文」即卷面全文转录，含附公式与参考数据）。",
       r"答案册第 4 页另印一张 $2$ 行 $4$ 列的 $X$ 分布列表：第一行 $X$、$1$、$2$、$3$；第二行 $P$、$\dfrac{1}{4}$、$\dfrac{1}{12}$、$\dfrac{2}{3}$（三格之和为 $1$）。",
       r"答案册给的完整解答：(1) 由题知 $X$ 的取值可能为 $1,2,3$，所以 $P(X=1)=\left(\dfrac{1}{\mathrm{C}_2^1}\right)^2=\dfrac{1}{4}$；$P(X=2)=\left[1-\left(\dfrac{1}{\mathrm{C}_2^1}\right)^2\right]\left(\dfrac{1}{\mathrm{C}_3^1}\right)^2=\dfrac{1}{12}$；$P(X=3)=\left[1-\left(\dfrac{1}{\mathrm{C}_2^1}\right)^2\right]\left[1-\left(\dfrac{1}{\mathrm{C}_3^1}\right)^2\right]=\dfrac{2}{3}$；数学期望为 $E(X)=1\times\dfrac{1}{4}+2\times\dfrac{1}{12}+3\times\dfrac{2}{3}=\dfrac{3+2+24}{12}=\dfrac{29}{12}$。",
       r"(2) 令 $x_i=\dfrac{1}{t_i}$，则 $\hat{y}=\hat{b}x+\hat{a}$，由题知：$\sum_{i=1}^{5}x_iy_i=315$，$\bar{y}=90$，所以 $\hat{b}=\dfrac{\sum_{i=1}^{5}x_iy_i-5\bar{x}\cdot\bar{y}}{\sum_{i=1}^{5}x_i^2-5\bar{x}^2}=\dfrac{315-5\times0.46\times90}{1.46-5\times0.212}=\dfrac{108}{0.4}=270$，所以 $\hat{a}=90-270\times0.46=-34.2$，$\hat{y}=270x-34.2$，故所求的回归方程为 $\hat{y}=\dfrac{270}{t}-34.2$，所以，估计 $t=6$ 时，$y\approx11$；估计 $t=7$ 时，$y\approx4$；估计 $t\geqslant8$ 时，$y<0$；预测成功的总人数为 $450+11+4=465$。",
       r"(3) 由题知，在前 $n$ 轮就成功的概率为 $P=\dfrac{1}{2^2}+\left(1-\dfrac{1}{2^2}\right)\dfrac{1}{3^2}+\left(1-\dfrac{1}{2^2}\right)\left(1-\dfrac{1}{3^2}\right)\dfrac{1}{4^2}+\cdots+\left(1-\dfrac{1}{2^2}\right)\left(1-\dfrac{1}{3^2}\right)\cdots\left(1-\dfrac{1}{n^2}\right)\dfrac{1}{(n+1)^2}$，又因为在在前 $n$ 轮没有成功的概率为 $1-P=\left(1-\dfrac{1}{2^2}\right)\times\left(1-\dfrac{1}{3^2}\right)\times\cdots\times\left[1-\dfrac{1}{(n+1)^2}\right]$",
       r"$=\left(1-\dfrac{1}{2}\right)\left(1+\dfrac{1}{2}\right)\times\left(1-\dfrac{1}{3}\right)\left(1+\dfrac{1}{3}\right)\times\cdots\times\left(1-\dfrac{1}{n}\right)\left(1+\dfrac{1}{n}\right)\times\left(1-\dfrac{1}{n+1}\right)\left(1+\dfrac{1}{n+1}\right)$",
       r"$=\left(\dfrac{1}{2}\right)\times\left(\dfrac{3}{2}\right)\times\left(\dfrac{2}{3}\right)\times\left(\dfrac{4}{3}\right)\times\cdots\times\left(\dfrac{n-1}{n}\right)\times\left(\dfrac{n+1}{n}\right)\times\left(\dfrac{n}{n+1}\right)\times\left(\dfrac{n+2}{n+1}\right)=\dfrac{n+2}{2n+2}=\dfrac{\frac{1}{2}(2n+2)+1}{2n+2}=\dfrac{1}{2}+\dfrac{1}{2n+2}>\dfrac{1}{2}$，故原不等式成立。",
   ]))

pd(4, "single_choice", [1], "figure-in-solution",
   r"【详解】……由椭圆的对称性，不妨令 $F$ 为右焦点，$A$ 是左焦点，连接 $AP,AQ,FP,FQ$……",
   r"答案册第 1 页 #4 详解旁印一幅配图：直角坐标系（标 $O$、$x$、$y$）中画长轴在 $x$ 轴的椭圆，标出左顶点方向的点 $A$、右焦点 $F$、椭圆上第一象限的点 $P$ 与第三象限的点 $Q$，并连出四边形 $APFQ$ 的对角线。本题题干为纯文字、正文与解析已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

pd(7, "single_choice", [1], "figure-in-solution",
   r"【详解】……如图，平面 $ABCD$ 截圆柱面所得的截面为椭圆……如图建立平面直角坐标系，则椭圆方程为 $\dfrac{x^2}{2}+y^2=1$……",
   r"答案册第 1–2 页 #7 详解里印两幅配图：①一幅圆柱面直观图，画竖直圆柱（上下底圆心标 $P$ 所在母线一端与 $O'$，轴为 $z$ 轴，另标 $x$、$y$ 轴），柱面上标 $P$、$A$、$D$、$C$、$B$、$M$、$O$ 等点并画出斜截所得的椭圆截面；②一幅平面直角坐标系（标 $O$、$x$、$y$）中的椭圆，内接正方形四顶点标 $A$、$D$、$C$、$B$，并画出对角线。本题题干为纯文字、正文与解析已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

pd(13, "fill_in_blank", [2], "figure-in-solution",
   r"【详解】由抛物线 $C_1:y^2=4x$，可得 $F_1(1,0)$……",
   r"答案册第 3 页 #13 详解旁印一幅配图：直角坐标系（标 $O$、$x$、$y$）中画两条开口向右的抛物线，分别标注 $y^2=4x$ 与 $y^2=16x$，横轴上标两焦点 $F_1$、$F_2$，一条水平线标作 $y=m$，与两抛物线分别交于 $Q$、$P$ 两点。本题题干为纯文字、正文与解析已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

pd(19, "detailed_answer", [4], "figure-in-solution",
   r"【详解】(2)(i) 设 $A(x_0,y_0)$……即 $O'\left(\dfrac{2x_0-p}{4},0\right)$．",
   r"答案册第 5 页 #19 详解右上方印一幅配图：直角坐标系（标 $O$、$x$、$y$）中画一条开口向右的抛物线与一个中心在 $x$ 轴上的椭圆，标出点 $H$（左上）、$A$（右上）、$B'$（左）、$O'$、$O$、$B$、$F$（右），并连出 $\triangle AHB$ 的三边与准线竖线。本题题干为纯文字、正文与解析已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

pd(7, "single_choice", [1], "print-suspect",
   r"D. $\dfrac{6}{2}$",
   r"试卷第 1 页 #7 的选项 D 印作分数 $\dfrac{6}{2}$，但分子 $6$ 的上方另有一条短横线（像 $\overline{6}$ 或一个多余的墨痕），无法排除原稿是 $\dfrac{5}{2}$ 之类。已用 500dpi 裁图放大核对，字形仍是 $6$ 加一条顶线，看不清是排印残留还是本意如此。按「一个字都不许改」照录为 $\dfrac{6}{2}$ 未作订正。本题答案为 B（$\dfrac{8\sqrt{2}}{9}$），D 项取何值都不影响判分，但请人工对照纸质原卷确认。")

pd(12, "fill_in_blank", [2], "print-suspect",
   r"【详解】$\boldsymbol{a}\perp\boldsymbol{b}$，则 $\boldsymbol{a}\cdot\boldsymbol{b}=(1,-2)\cdot(m,1)=m-2=0$，解得 $m=2$，所以 $|\boldsymbol{b}|=2$．故答案为 $\sqrt{2}$．",
   "\n".join([
       r"答案册第 3 页 #12 的详解与卷面、与自己给的答案都矛盾：卷面第 2 页题干印的是 $\boldsymbol{a}=(1,-1)$（已用 500dpi 裁图核对，确为 $-1$ 不是 $-2$），详解却把 $\boldsymbol{a}$ 写成 $(1,-2)$、解得 $m=2$、并写「所以 $|\boldsymbol{b}|=2$」，而同一行的「故答案为」与答案表都印 $\sqrt{2}$。",
       r"按卷面 $\boldsymbol{a}=(1,-1)$ 算：$\boldsymbol{a}\cdot\boldsymbol{b}=m-1=0$，$m=1$，$|\boldsymbol{b}|=\sqrt{1^2+1^2}=\sqrt{2}$，与标答一致；按详解的 $(1,-2)$ 算则得 $\sqrt{5}$，对不上标答。可见是详解里的 $(1,-2)$ 与 $|\boldsymbol{b}|=2$ 两处排印错误。",
       r"处置：题干照卷面录 $\boldsymbol{a}=(1,-1)$，答案照答案表录 $\sqrt{2}$，详解**逐字照录未改**（含 $(1,-2)$ 与 $|\boldsymbol{b}|=2$），冲突只登记在此，请人工定夺是否订正解析。",
   ]))

# ---------------- 自查 ----------------
vals = []
for r in Q:
    vals += [(r["题号"], "题干", r["题干"]), (r["题号"], "答案", r["答案"]), (r["题号"], "解析", r["解析"])]
    for k, v in r["选项"].items():
        vals.append((r["题号"], "选项" + k, v))
bad = []
for n, k, s in vals:
    if s.count("$") % 2:
        bad.append(("dollar-odd", n, k))
    if "$$" in s:
        bad.append(("doubledollar", n, k))
    if re.search(r"\\n(?![a-zA-Z])", s):
        bad.append(("literal-n", n, k))
    if re.search(r"\\_\{[^}]*[一-鿿][^}]*\}", s.replace("\\text", "")):
        bad.append(("cn-subscript", n, k))
    if [c for c in s if ord(c) < 32 and c != "\n"]:
        bad.append(("ctrl", n, k))
for r in Q:
    for k in ("解析", "题干", "答案"):
        if "见待复核" in r[k]:
            bad.append(("self-note-in-body", r["题号"], k))
for r in R:
    for k in ("原文", "说明"):
        r[k] = r[k].replace("\\n", "\n")
        if re.search(r"\\n(?![a-zA-Z])", r[k]):
            bad.append(("literal-n-pending", r["题号"], k))
        if [c for c in r[k] if ord(c) < 32 and c != "\n"]:
            bad.append(("ctrl-pending", r["题号"], k))
assert not bad, bad

Q.sort(key=lambda x: x["题号"])
(OUT / f"{NAME}.成品.json").write_text(json.dumps(Q, ensure_ascii=False, indent=1) + "\n", "utf-8")
(OUT / f"{NAME}.待复核.json").write_text(json.dumps(R, ensure_ascii=False, indent=1) + "\n", "utf-8")
print("成品", len(Q), "待复核", len(R), "题号", [r["题号"] for r in Q])
