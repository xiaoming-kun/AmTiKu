import json, re, sys
from pathlib import Path

sys.path.insert(0, ".")
from amti.record2 import FIG_WORD, TABLE_WORD

OUT = Path("数据/录题/输出_v2")
NAME = "246_2026届湖北襄阳高三3月调研"

Q = []


def rec(n, t, page, stem, opts, ans, sol):
    Q.append({
        "题号": n, "题型": t, "页码": page, "题干": stem, "选项": opts,
        "答案": ans, "解析": sol,
        "粗筛图": bool(FIG_WORD.search(stem)), "粗筛表": bool(TABLE_WORD.search(stem)),
    })


rec(1, "single_choice", [1],
    r"设集合 $P=\{2,4,6,8,10\}$，$Q=\{x|2x>7,x\in\mathbf{R}\}$，则 $P\cap Q=$",
    {"A": r"$\{8,10\}$", "B": r"$\{6,8,10\}$", "C": r"$\{4,6,8,10\}$", "D": r"$\{2,4,6,8,10\}$"},
    "C", "解析无")

rec(2, "single_choice", [1],
    r"设 $\mathrm{i}$ 是虚数单位，$\mathrm{i}z=5+4\mathrm{i}$，则 $z=$",
    {"A": r"$-5-4\mathrm{i}$", "B": r"$4-5\mathrm{i}$", "C": r"$4+5\mathrm{i}$", "D": r"$5+4\mathrm{i}$"},
    "B", "解析无")

rec(3, "single_choice", [1],
    r"已知向量 $\overrightarrow{a}=(t,1)$，$\overrightarrow{b}=(2,-3)$，且 $\overrightarrow{a}//(\overrightarrow{a}-\overrightarrow{b})$，则 $t=$",
    {"A": r"$-\dfrac{2}{3}$", "B": r"$\dfrac{2}{3}$", "C": r"$-\dfrac{3}{2}$", "D": r"$\dfrac{3}{2}$"},
    "A", "解析无")

rec(4, "single_choice", [1],
    r"把函数 $y=f(x)$ 图象上所有点的横坐标伸长到原来的 $2$ 倍，纵坐标不变，再把所得曲线向左平移 $\dfrac{\pi}{3}$ 个单位长度，得到函数 $y=\sin\left(\dfrac{x}{2}-\dfrac{\pi}{12}\right)$ 的图象，则 $f(x)=$",
    {"A": r"$\sin\left(\dfrac{x}{2}-\dfrac{7\pi}{12}\right)$", "B": r"$\sin\left(x+\dfrac{\pi}{4}\right)$",
     "C": r"$\sin\left(2x-\dfrac{7\pi}{12}\right)$", "D": r"$\sin\left(x-\dfrac{\pi}{4}\right)$"},
    "D", "解析无")

rec(5, "single_choice", [1],
    r"设 $a=\log_5 4$，$b=\log_6 5$，$c=\log_4 3$，则",
    {"A": r"$a<c<b$", "B": r"$a<b<c$", "C": r"$b<c<a$", "D": r"$c<a<b$"},
    "D", "解析无")

rec(6, "single_choice", [1],
    r"已知椭圆 $C_1$ 与双曲线 $C_2$ 有相同的左焦点 $F_1$ 和右焦点 $F_2$，$P$ 为椭圆 $C_1$ 与双曲线 $C_2$ 在第一象限内的一个公共点，设椭圆 $C_1$ 与双曲线 $C_2$ 的离心率分别为 $e_1,e_2$，且 $\dfrac{e_1}{e_2}=\dfrac{1}{3}$，若 $\angle F_1PF_2=\dfrac{\pi}{3}$，则双曲线 $C_2$ 的渐近线方程为",
    {"A": r"$y=\pm3x$", "B": r"$y=\pm\sqrt{2}x$", "C": r"$y=\pm\sqrt{5}x$", "D": r"$y=\pm2x$"},
    "B", "解析无")

rec(7, "single_choice", [2],
    "\n".join([
        r"在一次游泳比赛结束后，甲、乙、丙、丁进入前 $4$ 名，且这 $4$ 人无并列名次。赛完他们出场后，场外一个未看到比赛结果的游泳爱好者跟他们了解比赛结果：",
        r"甲说：我是第四名",
        r"乙说：我不是第二名或第四名",
        r"丙说：我排在乙前面",
        r"丁说：我是第一名",
        r"他们 $4$ 人中只有一个人说的是假话，下列正确的是",
    ]),
    {"A": r"丙是第一名", "B": r"乙是第二名", "C": r"甲是第三名", "D": r"丁是第四名"},
    "A", "解析无")

rec(8, "single_choice", [2],
    r"已知数列 $\{a_n\}$ 为等差数列，首项 $a_1=m$（$m$ 为整数），公差 $d=2$，前 $n$ 项和 $S_n=700$，则满足题意的 $n$ 的所有取值的和为",
    {"A": r"$3720$", "B": r"$4320$", "C": r"$2940$", "D": r"$1736$"},
    "D",
    "\n".join([
        r"解析：$a_n=m+2(n-1)$，$S_n=nm+\dfrac{2n(n-1)}{2}=700$，$n(m+n-1)=700=2^2\times5^2\times7$",
        r"所以 $n$ 的取值为 $2^2\times5^2\times7$ 的所有因数，所以所求和为 $(1+2+2^2)\times(1+5+5^2)\times(1+7)=1736$ 所以选 D",
    ]))

rec(9, "multi_choice", [2],
    r"下列说法正确的是",
    {"A": r"若事件 $A$ 与事件 $B$ 相互独立，$P(A)=0.1$，$P(B)=0.2$，则 $P(A\cup B)=0.28$",
     "B": r"若样本数据 $x_1,x_2,\cdots,x_n$ 的方差为 $4$，则数据 $2x_1-3,2x_2-3,\cdots,2x_n-3$ 的方差为 $8$",
     "C": r"一个盒子中有 $3$ 个黑球，$2$ 个白球，$1$ 个红球，不放回地抽取两次，每次抽一个球，则事件“至少有一个红球”与事件“两个球颜色相同”互斥",
     "D": r"$1,2,3,\cdots,2024,2025,2026$ 这 $2026$ 个数的上四分位数是 $507$"},
    "AC", "解析无")

rec(10, "multi_choice", [2],
    r"已知菱形 $ABCD$ 中，$AB=2$，$\angle ABC=60^\circ$，现将 $\triangle ADC$ 沿对角线 $AC$ 折起至 $\triangle PAC$，连接 $PB$，形成三棱锥 $P-ABC$，则下列说法正确的是",
    {"A": r"二面角 $P-AC-B$ 的大小为 $120^\circ$ 时，平面 $PAB\perp$ 平面 $PBC$",
     "B": r"在折起的过程中，存在某个位置使 $PA\perp BC$",
     "C": r"$\angle PAB=90^\circ$ 时，三棱锥 $P-ABC$ 的体积为 $\dfrac{2\sqrt{2}}{3}$",
     "D": r"三棱锥 $P-ABC$ 的体积最大时，其外接球的表面积为 $\dfrac{20\pi}{3}$"},
    "BCD", "解析无")

rec(11, "multi_choice", [2],
    r"已知 $f(x)=x^3+ax^2+cx+d$，则下列结论正确的是",
    {"A": r"$y=f(x)$ 的对称中心为 $\left(-\dfrac{a}{3},f\left(-\dfrac{a}{3}\right)\right)$",
     "B": r"若 $y=f(x)$ 存在两个极值点 $x_1$、$x_2$，且 $x_1<x_2$，则 $y=f\left(\dfrac{3x_2-x_1}{2}\right)$ 与 $y=f(x)$ 有 $3$ 个交点",
     "C": r"若 $f(1)=2026$，$f(2)=4052$，则 $f(5)-f(-2)=14266$",
     "D": r"若 $c=0$，$d=-(1-a)^2$，$f(x)=0$ 有三个不等实根 $\alpha,\beta,\gamma$，且 $\dfrac{\alpha}{\beta\gamma}+\dfrac{\beta}{\alpha\gamma}+\dfrac{\gamma}{\alpha\beta}>\dfrac{3}{2}$，则实数 $a$ 的取值范围是 $\left(\dfrac{3}{4},1\right)\cup(1,3)\cup(3,3+\sqrt{6})$"},
    "ACD",
    "\n".join([
        r"【详解】A. $\because f(x)=x^3+ax^2+cx+d$，$\therefore f'(x)=3x^2+2ax+c$，$f''(x)=6x+2a=0$",
        r"$\therefore x=-\dfrac{a}{3}$，$\therefore y=f(x)$ 的对称中心为 $\left(-\dfrac{a}{3},f\left(-\dfrac{a}{3}\right)\right)$；所以 A 对",
        r"B. 证明：设 $f(x)=f(m)$，则 $0=f(x)-f(m)=x^3+ax^2+bx+c-f(m)=(x-x_1)^2(x-m)$",
        r"利用方程左右两边 $x^2$ 的系数相等，得到 $a=-m-2x_1$",
        r"又 $x_1,x_2$ 为 $f'(x)=3x^2+2ax+c=0$，所以 $x_1+x_2=-\dfrac{2a}{3}$",
        r"所以：$m=-2x_1-a=x_2+\dfrac{x_2-x_1}{2}$，所以 B 错",
        r"C 有题意知，$1$ 和 $2$ 是 $f(x)-2026x=0$ 的两根，设 $f(x)-2026x=(x-1)(x-2)(x-k)$",
        r"则 $f(5)-f(-2)=2026\times5+12\times(5-k)-[2026\times(-2)+12(-2-k)]=14266$",
        r"D. $f(x)=x^3+ax^2+cx+d=x^3+ax^2-(1-a)^2=(x-\alpha)(x-\beta)(x-\gamma)$",
        r"所以：$\begin{cases}\alpha+\beta+\gamma=-a\\ \alpha\beta+\beta\gamma+\alpha\gamma=0\\ \alpha\beta\gamma=(1-a)^2\end{cases}$，$\dfrac{\alpha}{\beta\gamma}+\dfrac{\beta}{\alpha\gamma}+\dfrac{\gamma}{\alpha\beta}=\dfrac{\alpha^2+\beta^2+\gamma^2}{\alpha\beta\gamma}=\dfrac{a^2}{(1-a)^2}>\dfrac{3}{2}$ 解得 $(3-\sqrt{6},\ 1)\cup(1,3+\sqrt{6})$",
        r"又有 $f(x)=x^3+ax^2-(1-a)^2$ 三个不等实根，所以极大值大于 $0$，极小值小于 $0$",
        r"$\therefore f'(x)=3x^2+2ax=3x(x+\dfrac{2a}{3})$",
        r"又实数 $a$ 为正，所以 $f(x)$ 在 $(-\infty,\ -\dfrac{2a}{3})$ 为增，在 $(-\dfrac{2a}{3},\ 0)$ 为减，$(0,\ +\infty)$ 为增，所以 $\begin{cases}f(-\dfrac{2a}{3})>0\\ f(0)<0\end{cases}$",
        r"所以 $a>\dfrac{3}{4}$，且 $a\neq3$，所以 $\left(\dfrac{3}{4},\ 1\right)\cup(1,3)\cup(3,3+\sqrt{6})$",
        r"所以 D 对，故选 ACD",
    ]))

rec(12, "fill_in_blank", [3],
    r"曲线 $y=\dfrac{2x-4}{x+1}$ 在点 $(1,-1)$ 处的切线方程为________．",
    {}, r"$3x-2y-5=0$", "解析无")

rec(13, "fill_in_blank", [3],
    r"已知等比数列 $\{a_n\}$ 满足 $a_1=1$，$a_3a_5=16(a_4-4)$，则 $a_2=$ ________．",
    {}, r"$2$", "解析无")

rec(14, "fill_in_blank", [3],
    r"已知 $f(x)=2\sin x+3\cos x$，若 $f(x_1)=f(x_2)$，且 $x_1-x_2\neq2n\pi$（$n\in\mathbf{Z}$），则 $\sin(x_1+x_2)=$ ________",
    {}, r"$\dfrac{12}{13}$",
    "\n".join([
        r"【详解】$\because2\sin x_1+3\cos x_1=2\sin x_2+3\cos x_2$",
        r"$\therefore2(\sin x_1-\sin x_2)=3(\cos x_2-\cos x_1)$",
        r"$\therefore2\cos(\dfrac{x_1+x_2}{2})\sin(\dfrac{x_1-x_2}{2})=-3\sin(\dfrac{x_1+x_2}{2})\sin(\dfrac{x_2-x_1}{2})$",
        r"$\therefore\tan(\dfrac{x_1+x_2}{2})=\dfrac{2}{3}$，$\therefore\sin(x_1+x_2)=\dfrac{2\times\dfrac{2}{3}}{1+(\dfrac{2}{3})^2}=\dfrac{12}{13}$",
    ]))

rec(16, "detailed_answer", [3],
    "\n".join([
        r"在 $\triangle ABC$ 中，$\angle A,\angle B,\angle C$ 所对的边分别为 $a,b,c$，$M$ 为边 $BC$ 所在直线上一点．",
        r"(1)若 $\angle BAC=\dfrac{2}{3}\pi$，$AM$ 平分 $\angle BAC$，$AM=2$，$BC=3\sqrt{7}$，求 $\triangle ABC$ 的周长；",
        r"(2)若 $AM\perp BC$，且 $AM=\dfrac{3}{4}a$，求 $\dfrac{(b+c)^2}{bc}$ 的最大值和最小值．",
    ]),
    {},
    "\n".join([
        r"(1) $\triangle ABC$ 的周长为 $9+3\sqrt{7}$；",
        r"(2) 最大值 $\dfrac{2\sqrt{13}}{3}+2$ 和最小值 $4$",
    ]),
    "\n".join([
        r"解：(1) 由题意得 $\dfrac{1}{2}bc\dfrac{\sqrt{3}}{2}=\dfrac{1}{2}\times2b\dfrac{\sqrt{3}}{2}+\dfrac{1}{2}\times2c\dfrac{\sqrt{3}}{2}$",
        r"所以 $bc=2(b+c)$ ①",
        r"又 $63=b^2+c^2+bc$ ②",
        r"由①②解得 $b+c=9$，所以 $\triangle ABC$ 的周长为 $9+3\sqrt{7}$",
        r"(2) $\because\dfrac{1}{2}bc\sin A=\dfrac{1}{2}a\times\dfrac{3}{4}a\Rightarrow a^2=\dfrac{4}{3}bc\sin A$，",
        r"又 $\cos A=\dfrac{b^2+c^2-a^2}{2bc}$，$\therefore b^2+c^2=a^2+2bc\cos A=\dfrac{4}{3}bc\sin A+2bc\cos A$",
        r"$\therefore\dfrac{(b+c)^2}{bc}=\dfrac{b^2+c^2+2bc}{bc}=\dfrac{b^2+c^2}{bc}+2=\dfrac{4}{3}\sin A+2\cos A+2=\dfrac{2\sqrt{13}}{3}(\dfrac{2}{\sqrt{13}}\sin A+\dfrac{3}{\sqrt{13}}\cos A)+2=\dfrac{2\sqrt{13}}{3}\sin(A+\phi)+2\leqslant\dfrac{2\sqrt{13}}{3}+2$ 当且仅当 $\sin A=\dfrac{2\sqrt{13}}{13}$ 时取=，",
        r"又 $\dfrac{(b+c)^2}{bc}\geqslant4$ 当且仅当 $b=c$ 时取=，所以 $\dfrac{(b+c)^2}{bc}$ 的最大值 $\dfrac{2\sqrt{13}}{3}+2$ 和最小值 $4$．",
    ]))

rec(17, "detailed_answer", [3],
    "\n".join([
        r"已知函数 $f(x)=x-1-a\ln x$．",
        r"(1)若 $f(x)\geqslant0$ 恒成立，求 $a$ 的取值集合；",
        r"(2)当 $a\geqslant\dfrac{1}{2}$ 时，证明：当 $x>1$ 时，$\dfrac{1}{a}f(x)<e^{x-1}-1$ 恒成立．",
    ]),
    {},
    "\n".join([
        r"(1) $a=1$；",
        r"(2) 证明见解析",
    ]),
    "\n".join([
        r"解析：(1) $f(x)$ 的定义域为 $(0,+\infty)$．",
        r"①若 $a\leqslant0$，因为 $f\left(\dfrac{1}{2}\right)=-\dfrac{1}{2}+a\ln2<0$，所以不满足题意；",
        r"②若 $a>0$，由 $f'(x)=1-\dfrac{a}{x}=\dfrac{x-a}{x}$ 知，当 $x\in(0,a)$ 时，$f'(x)<0$；当 $x\in(a,+\infty)$ 时，$f'(x)>0$，所以 $f(x)$ 在 $(0,a)$ 单调递减，在 $(a,+\infty)$ 单调递增，故 $f(x)$ 在 $x=a$ 时取得最小值点．",
        r"所以 $f(a)=a-1-a\ln a\geqslant0$，",
        r"令 $g(a)=a-1-a\ln a$，则 $g'(a)=1-\ln a-1=-\ln a$",
        r"当 $a>1$ 时，$g'(a)<0$，$g(a)$ 单减；当 $0<a<1$ 时，$g'(a)>0$，$g(a)$ 单增；",
        r"又 $g(1)=0$，所以 $f(a)=a-1-a\ln a\geqslant0$ 的解为 $a=1$，故 $a=1$．",
        r"(2) $a\geqslant\dfrac{1}{2}$，且 $x>1$ 时，$e^{x-1}-1-\dfrac{1}{a}f(x)=e^{x-1}-\dfrac{1}{a}(x-1)+\ln x-1\geqslant e^{x-1}-2x+1+\ln x$，",
        r"令 $g(x)=e^{x-1}-2x+1+\ln x(x>1)$，下证 $g(x)>0$ 即可．",
        r"$g'(x)=e^{x-1}-2+\dfrac{1}{x}$，再令 $h(x)=g'(x)$，则 $h'(x)=e^{x-1}-\dfrac{1}{x^2}$，",
        r"显然 $h'(x)$ 在 $(1,+\infty)$ 上递增，则 $h'(x)>h'(1)=e^0-1=0$，",
        r"即 $g'(x)=h(x)$ 在 $(1,+\infty)$ 上递增，",
        r"故 $g'(x)>g'(1)=e^0-2+1=0$，即 $g(x)$ 在 $(1,+\infty)$ 上单调递增，",
        r"故 $g(x)>g(1)=e^0-2+1+\ln1=0$，问题得证．",
    ]))

rec(19, "detailed_answer", [4],
    "\n".join([
        r"集合 $M=\{0,1,2,3,\cdots,n\}$，$T=\{(a_0,a_1,a_2,\cdots,a_n)|a_i\in M(i=0,1,2,\cdots,n),\sum\limits_{i=0}^{n}a_i=2n\}$，对 $T$ 中的两个不同元素 $X=(x_0,x_1,x_2,\cdots,x_n)$ 和 $Y=(y_0,y_1,y_2,\cdots,y_n)$，若存在一个函数 $f:M\to M$ 满足：",
        r"①$f(f(x))=x$，$\forall x\in M$",
        r"②$y_i=f(x_i)$，$\forall\ i\in\{0,1,2,\cdots,n\}$",
        r"③$(x_i+y_i)\in\{0,n,2n\}$，$\forall\ i\in\{0,1,2,\cdots,n\}$",
        r"则称：$X$ 与 $Y$ 是 $T$ 中的一对“友好元素”．",
        r"(1)当 $n=4$ 时，若 $X=(0,0,1,3,4)$，写出 $X$ 对应的一个“友好元素”；",
        r"(2)若 $X=(x_0,x_1,x_2,\cdots,x_n)$ 和 $Y=(y_0,y_1,y_2,\cdots,y_n)$ 是 $T$ 中的一对“友好元素”，且满足 $\max\{x_0,x_1,\cdots,x_n\}=n$，规定：随机变量 $\zeta$ 服从分布 $P(\zeta=x_i)=\dfrac{y_i}{2n}(i=0,1,2\cdots,n)$，当 $n=6$ 时，试写出 $E(\zeta)=\dfrac{13}{3}$ 的分布列及其对应的一对“友好元素”$X$ 与 $Y$；",
        r"(3)当 $n\geqslant4$ 时，若 $A=(a_0,a_1,a_2,\cdots,a_n)\in T$ 且满足 $\max\{a_0,a_1,a_2,\cdots,a_n\}=n$，证明：若存在 $B$ 使得 $A$ 与 $B$ 是 $T$ 中的一对“友好元素”，则 $A$ 中有且仅有 $n-2$ 个 $0$．",
    ]),
    {},
    "\n".join([
        r"(1) $Y=(0,0,3,1,4)$；",
        r"(2) 分布列见解析，$X=(0,0,0,0,2,4,6)$，$Y=(0,0,0,0,4,2,6)$；",
        r"(3) 证明见解析",
    ]),
    "\n".join([
        r"[解析](1) 当 $n=4$ 时，由 $X=(0,0,1,3,4)$，需构造 $Y=(y_0,y_1,y_2,y_3,y_4)$ 满足",
        r"①$f(f(x))=x,\forall x\in M$",
        r"②$y_i=f(x_i)$",
        r"③$x_i+y_i\in\{0,4,8\},\forall i\in\{0,1,2,3,4\}$",
        r"设 $f(0)=0$，$f(1)=3$，$f(2)=2$，$f(3)=1$，$f(4)=4$，则 $f(x)$ 满足①②③，此时 $Y=(0,0,3,1,4)$；故 $Y=(0,0,3,1,4)$ 满足题意．",
        r"(1) 取 $X=(0,0,0,0,2,4,6)$，$Y=(0,0,0,0,4,2,6)$ 满足 $x_i+y_i\in\{0,6,12\}$ 且满足 $f(0)=0,f(1)=5,f(2)=4,f(4)=2,f(3)=3$，$f(5)=1,f(6)=6$",
        r"$\zeta$ 的分布列为 $\begin{array}{|c|c|c|c|c|}\hline \zeta & 0 & 2 & 4 & 6\\\hline p & 0 & \dfrac{1}{3} & \dfrac{1}{6} & \dfrac{1}{2}\\\hline\end{array}$",
        r"$E(x_i)=\sum\limits_{i=0}^{n}x_i\cdot\dfrac{y_i}{2n}=2\times\dfrac{1}{3}+4\times\dfrac{1}{6}+6\times\dfrac{1}{2}=\dfrac{13}{3}$，所以 $X=(0,0,0,0,2,4,6)$，$Y=(0,0,0,0,4,2,6)$（其他合理答案，同样给分，如：$X=(0,0,0,2,6,4,0)$，$Y=(0,0,0,4,6,2,0)$ 等)．",
        r"(3) 当 $n\geqslant4$ 时，若 $A=(a_0,a_1,a_2,\cdots,a_n)\in T$ 且满足 $\max\{a_0,a_1,\cdots,a_n\}=n$ 不妨令 $a_0=n$",
        r"①由于 $a_0+a_1+a_2+\cdots+a_n=2n$，所以 $a_1,a_2,\cdots,a_n$ 不可能都是 $0$．",
        r"②若 $A$ 中有 $n-1$ 个 $0$，不妨设 $a_1\neq0$，$a_2=\cdots=a_n=0$，则 $a_1=n$，此时 $A=(n,n,0,0,\cdots,0)$，根据题意 $a_i+b_i\in\{0,n,2n\}$，则 $B=(n,n,0,0,\cdots,0)$，$B=(0,0,n,n,\cdots,n)$，",
        r"但是当 $B=(n,n,0,0,\cdots,0)$ 时与 $A\neq B$ 矛盾，所以不成立；",
        r"当 $B=(0,0,n,n,\cdots,n)$ 时，$b_0+b_1+b_2+b_3+\cdots b_n=0+0+n+n\cdots n=(n-1)n>2n(n\geqslant4)$，与 $\sum\limits_{i=0}^{n}b_i=2n$ 矛盾．",
        r"所以 $A$ 中不可能有 $n-1$ 个 $0$．",
        r"③若 $A$ 中有 $n-2$ 个 $0$，不妨设 $a_1\neq0,a_2\neq0$，则 $A=(n,a_1,a_2,0,0\cdots,0)$，其中 $a_1+a_2=n$，则存在函数 $f$ 使得：",
        r"$f(n)=n,f(a_1)=n-a_1,f(a_2)=n-a_2,f(n-a_1)=a_1,f(n-a_2)=a_2,f(0)=0$，",
        r"即存在 $B=(n,n-a_1,n-a_2,0,0,\cdots,0)$ 使得 $A$ 与 $B$ 是T中的友好元素．",
        r"④若 $A$ 中 $0$ 的个数小于等于 $n-3$ 个，不妨设 $A=(n,a_1,a_2,a_3,a_4\cdots,a_n)$，",
        r"其中 $a_1\neq0,a_2\neq0,a_3\neq0$，$a_4,a_5,\cdots,a_n\geqslant0$，则 $a_1+a_2+a_3\leqslant n$．",
        r"假设存在 $B$，则有两种可能：",
        r"第一种：$B=(n,n-a_1,n-a_2,n-a_3,f(a_4),\cdots,f(a_n))$，其中若 $a_j\neq0,(j=4,5,\cdots,n)$，则 $f(a_j)=n-a_j$；若 $a_j=0,(j=4,5,\cdots,n)$，则 $f(a_j)=0$，此时，",
        r"$b_0+b_1+b_2+\cdots+b_n\geqslant n+n-a_1+n-a_2+n-a_3=4n-(a_1+a_2+a_3)\geqslant4n-n=3n$，不符合题意；",
        r"第二种：$B=(0,n-a_1,n-a_2,n-a_3,n-a_4,\cdots,n-a_n)$，则",
        r"$b_0+b_1+b_2+\cdots+b_n\geqslant0+n-a_1+n-a_2+\cdots+n-a_n=n^2-(a_1+a_2+\cdots+a_n)=n^2-n>2n(n\geqslant4)$．",
        r"即这两种情况都有 $\sum\limits_{i=0}^{n}b_i>2n$，矛盾．",
        r"综上可知，当 $n\geqslant4$ 时，若存在序列B使得A与B为一对“友好元素”，则 $A$ 中有 $n-2$ 个 $0$．",
    ]))

# ---------------- 待复核 ----------------
R = []


def pd(n, t, page, kind, raw, note):
    R.append({"题号": n, "题型": t, "页码": page, "类型": kind, "原文": raw, "说明": note})


pd(4, "single_choice", [1], "figure",
   r"把函数 $y=f(x)$ 图象上所有点的横坐标伸长到原来的 $2$ 倍，纵坐标不变，再把所得曲线向左平移 $\dfrac{\pi}{3}$ 个单位长度，得到函数 $y=\sin\left(\dfrac{x}{2}-\dfrac{\pi}{12}\right)$ 的图象，则 $f(x)=$",
   r"粗筛命中：题干两处出现「图象」字样（命中 FIG_WORD），卷面第 1 页。核对结论：试卷与答案册本题**均无配图**，「横坐标伸长到原来的 $2$ 倍」「向左平移 $\dfrac{\pi}{3}$ 个单位长度」都是变换条件而非引用某幅图，属纯文字题，题干与四个选项已完整录入成品 #4，不需要补图。参考答案：D。")

pd(15, "detailed_answer", [3], "figure",
   "\n".join([
       r"如图，正三角形 $ABC'$ 和平行四边形 $ABDE$ 在同一个平面内，其中 $AB=4$，$BD=AD=\sqrt{31}$，$AB,DE$ 的中点分别为 $F,G$．将 $\triangle ABC'$ 沿直线 $AB$ 翻折到 $\triangle ABC$，使二面角 $C-AB-D$ 为 $120^\circ$，设 $CE$ 的中点为 $H$．",
       r"(1)求证：平面 $CDF//$ 平面 $AGH$；",
       r"(2)求平面 $CDE$ 与平面 $DEF$ 的夹角的余弦值．",
   ]),
   "\n".join([
       r"试卷第 3 页 #15 题干下方印着**两张并排的配图、中间一个向右箭头**（表示翻折过程）：左图是平面图形，平行四边形 $ABDE$（$A$ 上、$B$ 左下、$D$ 下、$E$ 右）与正三角形 $ABC'$（$C'$ 在左上）共边 $AB$，$F$ 标在 $AB$ 上、$G$ 标在 $DE$ 上；右图是翻折后的三棱锥状立体图，$C$ 为顶点，$H$ 标在 $CE$ 中点处，底面 $B,F,D,G,E$ 依次铺开，虚线表示被遮的棱。题干自带「如图」，按规矩不录正文。答案册第 2 页另印一幅以 $F$ 为原点、$FD,FA$ 为 $x,y$ 轴、过 $F$ 平行于 $OC$ 的直线为 $z$ 轴的建系图（图上标 $C,H,A,E,O,F,D,G,B$ 与三轴）。",
       r"答案册第 1–2 页的完整解答，答案 (2) 余弦值为 $\dfrac{4\sqrt{19}}{19}$：",
       r"(1) 证明：因为四边形 ABDE 为平行四边形，F、G 分别为 AB、DE 的中点，所以四边形 FDGA 为平行四边形，所以 FD//AG。又 H、G 分别为 CE、DE 的中点，所以 HG//CD。因为 FD、CD⊄ 平面 AGH，AG、HG⊂平面 AGH，所以 FD//平面 AGH，CD//平面 AGH，因为 FD、CD⊂平面 CDF，FD∩CD=D，所以平面 CDF//平面 AGH。",
       r"(2) 因为三角形 ABC 为正三角形，BD=AD，F 为 AB 的中点，所以 AB⊥CF，AB⊥DF，所以 ∠CFD 为二面角 C−AB−D 的平面角，又 CF∩DF=F，所以 AB⊥平面 CFD，因为 AB⊂平面 ABDE，所以平面 CFD⊥平面 ABDE。作 CO⊥平面 ABDE 于 O，则 O 在直线 DF 上。又二面角 C−AB−D 的平面角为 ∠CFD=120°，所以 O 在线段 DF 的延长线上。易知 CF=2√3，则 FO=√3，CO=3。以 F 为原点，FD、FA 所在直线分别为 x 轴、y 轴，过点 F 平行于 OC 的直线为 z 轴，建立空间直角坐标系，如图，因为 AB=4，BD=AD=√31，所以 DF=3√3，则 A(0,2,0),B(0,−2,0),D(3√3,0,0),E(3√3,4,0),C(−√3,0,3)，",
       r"由(2)知 CD向量=(4√3,0,−3),DE向量=(0,4,0)，设平面 CDE 的法向量为 n=(x,y,z)，则由 n⊥CD,n⊥DE，得 {4√3x−3z=0, 4y=0} 令 z=4√3，得 n=(3,0,4√3)。易知平面 DEF 的一个法向量 m=(0,0,1)，所以平面 CDE 与平面 DEF 的夹角的余弦值为 |cos<n,m>|=|n·m|/(|n||m|)=4√19/19。（几何法酌情给分）",
   ]))

pd(18, "detailed_answer", [4], "figure",
   "\n".join([
       r"如图，设抛物线方程为 $y^2=2px(p>0)$，点 $P$ 为直线 $x=-2p$ 上任意一点，过 $P$ 作抛物线的切线，切点分别为 $M,N$．",
       r"(Ⅰ)若 $M$ 的坐标为 $(x_1,y_1)$，求证：直线 $PM$ 的方程为 $y_1y=p(x+x_1)$；",
       r"(Ⅱ)已知 $P$ 点的坐标为 $(-2p,4)$，$|MN|=8\sqrt{10}$，求此时抛物线的方程；",
       r"(Ⅲ)是否存在点 $P(-2P,y_0)$，使得点 $H$ 关于直线 $MN$ 的对称点 $D$ 在抛物线 $y^2=2px(p>0)$ 上，其中点 $H$ 满足 $\overrightarrow{OH}=\overrightarrow{OM}+\overrightarrow{ON}$（$O$ 为坐标原点）．若存在，求出所有适合题意的点 $P$ 的坐标；若不存在，请说明理由．",
   ]),
   "\n".join([
       r"试卷第 4 页 #18 题干右下方印一幅配图：直角坐标系（标 $O$、$x$、$y$）中画开口向右的抛物线，其左侧一条竖线即 $x=-2p$，竖线上一点标 $P$，从 $P$ 向抛物线引两条切线，切点分别标 $M$（第一象限）与 $N$（第四象限），并画出弦 $MN$。题干自带「如图」，按规矩不录正文。",
       r"答案册第 3 页的完整解答，答案 (Ⅱ) $y^2=8x$ 或 $y^2=4x$；(Ⅲ) 仅存在一点 $P(-2p,0)$ 适合题意：",
       r"(I) 证明：由 $y^2=2px(p>0)$ 得 $y=\pm\sqrt{2px}$，当 $y=\sqrt{2px}$ 时，$y'=\dfrac{p}{\sqrt{2px}}$，所以 $k_{PM}=\dfrac{p}{\sqrt{2px_1}}$，则 $PM$ 的方程为：$y=\dfrac{p}{\sqrt{2px_1}}(x-x_1)+y_1$，又 $y_1=\sqrt{2px_1}$，整理得：$yy_1=p(x+x_1)$。同理，当 $y=-\sqrt{2px}$ 时，PM：$yy_1=p(x+x_1)$。",
       r"(II) 解：同(1)：设 $N(x_2,y_2)$，则 PN 的方程为 $yy_2=p(x+x_2)$，又 P 点的坐标为 $(-2p,4)$，则 $4y_1=p(-2p+x_1)$，又 $y_1^2=2px_1$，所以 $y_1^2-8y_1-4p^2=0$，同理 $y_2^2-8y_2-4p^2=0$，所以 $y_1,y_2$ 是方程 $y^2-8y-4p^2=0$ 的两根，因此 $y_1+y_2=8$，$y_1y_2=-4p^2$，又 $k_{MN}=\dfrac{y_1-y_2}{\frac{y_1^2}{2p}-\frac{y_2^2}{2p}}=\dfrac{2p}{y_1+y_2}=\dfrac{p}{4}$，由弦长公式得 $|MN|=\sqrt{1+\dfrac{1}{k^2}}\sqrt{(y_1+y_2)^2-4y_1y_2}=\sqrt{1+\dfrac{16}{p^2}}\sqrt{64+16p^2}=8\sqrt{10}$，所以 $p=4$ 或 $2$，因此所求抛物线方程为 $y^2=8x$ 或 $y^2=4x$；",
       r"(III) 解：设 $D(x_3,y_3)$，由题意得 $H(x_1+x_2,y_1+y_2)$，则 HD 的中点坐标为 $T(\dfrac{x_1+x_2+x_3}{2},\dfrac{y_1+y_2+y_3}{2})$，由(1)(2)可知：直线 MN 的方程为 $yy_0=p(x-2p)$，由点 T 在直线 MN 上，并注意到点 $(\dfrac{x_1+x_2}{2},\dfrac{y_1+y_2}{2})$ 也在直线 MN 上，代入得 $y_3y_0=px_3$。若 $D(x_3,y_3)$ 在抛物线上，则 $y_3^2=2px_3=2y_0y_3$，因此 $y_3=0$ 或 $y_3=2y_0$，即 $D(0,0)$ 或 $D(\dfrac{2y_0^2}{p},2y_0)$。",
       r"(1) 当 $y_0=0$ 时，则 $y_1+y_2=2y_0=0$，此时，点 $P(-2p,0)$ 适合题意。",
       r"(2) 当 $y_0\neq0$，对于 $D(0,0)$，此时 $H(\dfrac{y_1^2+y_2^2}{2p},2y_0)$，$k_{DH}=\dfrac{2y_0}{\frac{y_1^2+y_2^2}{2p}}=\dfrac{4py_0}{y_1^2+y_2^2}$，又 $k_{MN}=\dfrac{p}{y_0}$，MN⊥DH，所以 $k_{MN}\cdot k_{DH}=\dfrac{p}{y_0}\cdot\dfrac{4py_0}{y_1^2+y_2^2}=\dfrac{4p^2}{y_1^2+y_2^2}=-1$，即 $y_1^2+y_2^2=-4p^2$，矛盾。对于 $D(\dfrac{2y_0^2}{p},2y_0)$，因为 $H(\dfrac{y_1^2+y_2^2}{2p},2y_0)$，此时直线 DH 平行于 x 轴，又 $k_{MN}=\dfrac{p}{y_0}$，所以直线 MN 与直线 DH 不垂直，与题设矛盾，所以 $y_0\neq0$ 时，不存在符合题意的 P 点。综上所述，仅存在一点 $P(-2p,0)$ 适合题意。",
   ]))

pd(18, "detailed_answer", [4], "print-suspect",
   r"(Ⅲ)是否存在点 $P(-2P,y_0)$，使得点 $H$ 关于直线 $MN$ 的对称点 $D$ 在抛物线 $y^2=2px(p>0)$ 上",
   r"试卷第 4 页 #18(Ⅲ) 的点坐标印作 $P(-2P,y_0)$，横括号里用了**大写的 $P$**，而同题 (Ⅱ) 印的是 $P$ 点的坐标为 $(-2p,4)$、题干开头又写「点 $P$ 为直线 $x=-2p$ 上任意一点」，故此处大写 $P$ 疑为小写 $p$ 的排印错误。按「一个字都不许改」照录原印文（成品与待复核的「原文」都保留 $-2P$），未作订正；答案册第 3 页该问的解答全程用小写 $p$（$P(-2p,0)$），不受此处影响。请人工对照纸质原卷确认。")

pd(11, "multi_choice", [2], "figure-in-solution",
   r"【详解】A. $\because f(x)=x^3+ax^2+cx+d$，$\therefore f'(x)=3x^2+2ax+c$，$f''(x)=6x+2a=0$ …… $\therefore x=-\dfrac{a}{3}$",
   r"答案册第 1 页 #11 详解 A 项旁印一幅配图：直角坐标系（标 $o$、$x$、$y$）里画一条三次曲线（先升后降再升），横轴上自左向右依次标 $o$、$n$、$x_1$、$x_2$、$m$ 等记号，用于说明极值点与对称中心的位置关系。本题题干为纯文字、正文与解析已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

pd(19, "detailed_answer", [4], "table",
   r"$\zeta$ 的分布列为（答案册第 3 页印一张两行五列表格）",
   "\n".join([
       r"答案册第 3 页 #19 第 (2) 问的解答里把 $\zeta$ 的分布列印成一张 $2$ 行 $5$ 列表格：第一行 $\zeta$、$0$、$2$、$4$、$6$；第二行 $p$、$0$、$\dfrac{1}{3}$、$\dfrac{1}{6}$、$\dfrac{1}{2}$。四格概率之和 $0+\dfrac{1}{3}+\dfrac{1}{6}+\dfrac{1}{2}=1$，且 $2\times\dfrac{1}{3}+4\times\dfrac{1}{6}+6\times\dfrac{1}{2}=\dfrac{13}{3}$ 与该问要求的 $E(\zeta)=\dfrac{13}{3}$ 自洽。#19 题干纯文字、卷面未印图表，正文与解析已照录入成品，这张表在成品的解析里按本项目惯例转写成了 array 阵列；本条登记是为了请人工逐格核对原表数值与转写是否一致。",
       r"另需点名两处答案册自身的排印问题（均照录未改）：①答案册把第 (2) 问的解答**标号印成了「(1)」**（同一页上先有真正的 (1) 的解答，紧接着又出现一个「(1) 取 $X=(0,0,0,0,2,4,6)$……」，按内容应是 (2)）；②期望那行印作 $E(x_i)=\sum_{i=0}^{n}x_i\cdot\dfrac{y_i}{2n}$，左端写作 $E(x_i)$ 而题中随机变量是 $\zeta$。",
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
