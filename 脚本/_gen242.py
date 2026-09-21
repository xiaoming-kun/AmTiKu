import json, re, sys
from pathlib import Path

sys.path.insert(0, ".")
from amti.record2 import FIG_WORD, TABLE_WORD

OUT = Path("数据/录题/输出_v2")
NAME = "242_2026届福建百校高三下学期阶段性自测"

Q = []


def rec(n, t, page, stem, opts, ans, sol):
    Q.append({
        "题号": n, "题型": t, "页码": page, "题干": stem, "选项": opts,
        "答案": ans, "解析": sol,
        "粗筛图": bool(FIG_WORD.search(stem)), "粗筛表": bool(TABLE_WORD.search(stem)),
    })


rec(1, "single_choice", [1],
    r"复数 $z=2+\mathrm{i}^7(1-2\mathrm{i})$ 的模为",
    {"A": r"$1$", "B": r"$\sqrt{2}$", "C": r"$2$", "D": r"$\sqrt{7}$"},
    "A",
    r"由 $z=2-\mathrm{i}(1-2\mathrm{i})=-\mathrm{i}$，有 $|z|=1$．")

rec(2, "single_choice", [1],
    r"已知集合 $A=\{x|x^2>1\}$，$B=(a,+\infty)$，若 $A\cup B=\mathbf{R}$，则实数 $a$ 的取值范围为",
    {"A": r"$(-\infty,1)$", "B": r"$(-\infty,1]$", "C": r"$(-\infty,-1)$", "D": r"$(-\infty,-1]$"},
    "C",
    r"由 $A=(-\infty,-1)\cup(1,+\infty)$，若 $A\cup B=\mathbf{R}$，有 $a<-1$．")

rec(3, "single_choice", [1],
    r"已知样本数据 $1,2,4,6,m$，若删除 $4$ 后的新数据与原数据的平均数相同，则 $m=$",
    {"A": r"$4$", "B": r"$5$", "C": r"$6$", "D": r"$7$"},
    "D",
    r"由题意可知 $4$ 是样本数据的平均数，有 $1+2+4+6+m=4\times5$，可得 $m=7$．")

rec(4, "single_choice", [1],
    r"函数 $f(x)=(\log_2x+1)\left(\log_{\frac{1}{2}}x+5\right)$ 的最大值为",
    {"A": r"$7$", "B": r"$9$", "C": r"$10$", "D": r"$13$"},
    "B",
    r"令 $t=\log_2x(t\in\mathbf{R})$，有 $f(x)=(t+1)(-t+5)=-t^2+4t+5=-(t-2)^2+9\leqslant9$，可得函数 $f(x)$ 的最大值为 $9$．")

rec(5, "single_choice", [1],
    r"已知圆 $C_1:x^2+y^2=4$，圆 $C_2:(x-2)^2+(y-2)^2=8$，则圆 $C_1$ 和圆 $C_2$ 的公共弦长为",
    {"A": r"$3$", "B": r"$\sqrt{11}$", "C": r"$2\sqrt{3}$", "D": r"$\sqrt{14}$"},
    "D",
    r"圆 $C_2$ 的一般方程为 $x^2+y^2-4x-4y=0$，两圆方程作差可得公共弦的方程为 $x+y-1=0$，可得圆 $C_1$ 和圆 $C_2$ 的公共弦长为 $2\sqrt{4-\left(\dfrac{1}{\sqrt{2}}\right)^2}=\sqrt{14}$．")

rec(6, "single_choice", [1],
    r"已知 $\cos(\alpha-\beta)=-\dfrac{3}{4}$，$\tan\alpha\tan\beta=2$，则 $\cos(\alpha+\beta)=$",
    {"A": r"$\dfrac{1}{4}$", "B": r"$\dfrac{1}{3}$", "C": r"$\dfrac{2}{3}$", "D": r"$\dfrac{3}{5}$"},
    "A",
    r"由 $\tan\alpha\tan\beta=2$，有 $\sin\alpha\sin\beta=2\cos\alpha\cos\beta$，又由 $\cos(\alpha-\beta)=\cos\alpha\cos\beta+\sin\alpha\sin\beta=-\dfrac{3}{4}$，可得 $\sin\alpha\sin\beta=-\dfrac{1}{2}$，$\cos\alpha\cos\beta=-\dfrac{1}{4}$．可得 $\cos(\alpha+\beta)=\cos\alpha\cos\beta-\sin\alpha\sin\beta=-\dfrac{1}{4}-\left(-\dfrac{1}{2}\right)=\dfrac{1}{4}$．")

rec(7, "single_choice", [1],
    r"在计算机科学中，八进制是一种数字表示法，它使用 $0\sim7$ 这八个数字来表示数值．例如，八进制数 $2051$ 换算成十进制数是 $2\times8^3+0\times8^2+5\times8^1+1\times8^0=1065$．那么八进制数 $\underbrace{333\cdots3}_{20\text{个}3}$ 换算成十进制数 $m$，则十进制数 $m$ 的个位数字为",
    {"A": r"$4$", "B": r"$5$", "C": r"$6$", "D": r"$7$"},
    "B",
    r"由 $m=3\times8^0+3\times8^1+3\times8^2+\ldots+3\times8^{19}=3\times\dfrac{1-8^{20}}{1-8}=\dfrac{3(8^{20}-1)}{7}=\dfrac{(10-7)(8^{20}-1)}{7}=\dfrac{10(8^{20}-1)}{7}-(8^{20}-1)$，又由 $8^{20}-1=(7+1)^{20}-1$ 是 $7$ 的倍数，可得 $\dfrac{10(8^{20}-1)}{7}$ 是 $10$ 的倍数．又由 $8^{20}-1=(10-2)^{20}-1$，可得 $8^{20}-1$ 的个位数与 $2^{20}-1$ 的个位数相同，又由 $2^{20}-1=4\times2^{18}-1=4\times(10-2)^6-1$，可得 $2^{20}-1$ 的个位数与 $4\times2^6-1=255$ 的个位数相同．可得 $8^{20}-1$ 的个位数为 $5$，进而可得十进制数 $m$ 的个位数为 $5$．")

rec(8, "single_choice", [2],
    r"已知椭圆 $C:\dfrac{x^2}{a^2}+\dfrac{y^2}{b^2}=1(a>b>0)$ 的左、右焦点分别为 $F_1$、$F_2$，$A$ 是椭圆 $C$ 的上顶点，直线 $AF_1$ 与椭圆相交于另一点 $B$，若 $|BF_2|=\dfrac{3}{2}|AB|$，则椭圆 $C$ 的离心率为",
    {"A": r"$\dfrac{\sqrt{2}}{3}$", "B": r"$\dfrac{\sqrt{3}}{3}$", "C": r"$\dfrac{\sqrt{6}}{3}$", "D": r"$\dfrac{\sqrt{2}}{4}$"},
    "C",
    r"设 $|F_1F_2|=2c$，$|BF_1|=m$，$|AF_1|=|AF_2|=a$，有 $|BF_2|=2a-m$，又由 $|BF_2|=\dfrac{3}{2}|AB|$，有 $2a-m=\dfrac{3}{2}(a+m)$，可得 $m=\dfrac{a}{5}$，可得 $|BF_1|=\dfrac{a}{5}$，$|BF_2|=\dfrac{9}{5}a$．又由 $\cos\angle AF_1F_2=\dfrac{c}{a}$，在 $\triangle BF_1F_2$ 中由余弦定理，有 $\left(\dfrac{a}{5}\right)^2+4c^2-2\times\dfrac{a}{5}\times2c\times\left(-\dfrac{c}{a}\right)=\left(\dfrac{9a}{5}\right)^2$，有 $2a^2=3c^2$，可得 $e=\dfrac{c}{a}=\dfrac{\sqrt{6}}{3}$．")

rec(10, "multi_choice", [2],
    "\n".join([
        r"已知焦点为 $F$ 的抛物线 $C:y^2=2px(p>0)$ 的准线为 $x=-1$，过点 $F$ 的直线与抛物线 $C$ 交于 $A$、$B$ 两点，$O$ 为坐标原点，直线 $AO$、$BO$ 分别与准线相交于 $M$、$N$ 两点，则",
        r"A. $p=2$",
        r"B. 若 $\left||AF|-|BF|\right|=\dfrac{3}{2}$，则直线 $AB$ 的斜率的绝对值为 $2$",
        r"C. $AN//BM$",
        r"D. $FM\perp FN$",
    ]),
    {},
    "ACD",
    "\n".join([
        r"设 $A$，$B$ 的坐标分别为 $(x_1,y_1)$，$(x_2,y_2)$，直线 $AB$ 的方程为 $my=x-1$，联立方程 $\begin{cases}y^2=4x\\ my=x-1\end{cases}$，消去 $x$ 后有 $y^2-4my-4=0$，有 $y_1+y_2=4m$，$y_1y_2=-4$，可得 $x_1x_2=\dfrac{y_1^2y_2^2}{16}=1$．",
        r"对于 A 选项，由抛物线 $C$ 的准线为 $x=-1$，有 $-\dfrac{p}{2}=-1$，可得 $p=2$，故 A 选项正确；",
        r"对于 B 选项，由 $\left||AF|-|BF|\right|=\left|(x_1+1)-(x_2+1)\right|=\dfrac{3}{2}$，有 $|x_1-x_2|=\dfrac{3}{2}$，代入 $x_1x_2=1$，有 $\left|x_1-\dfrac{1}{x_1}\right|=\dfrac{3}{2}$，解得 $x_1=\dfrac{1}{2}$ 或 $2$，可得 $\begin{cases}x_1=\dfrac{1}{2}\\ y_1=\pm\sqrt{2}\end{cases}$ 或 $\begin{cases}x_1=2\\ y_1=\pm2\sqrt{2}\end{cases}$，可得直线 $AB$ 的斜率的绝对值为 $\dfrac{2\sqrt{2}-0}{2-1}=2\sqrt{2}$，故 B 选项错误；",
        r"对于 C 选项，直线 $OA$ 的方程为 $y=\dfrac{y_1}{x_1}x$，代入 $x=-1$，有 $y=-\dfrac{y_1}{x_1}=-\dfrac{4}{y_1}=\dfrac{y_1y_2}{y_1}=y_2$，可得点 $M$ 的坐标为 $(-1,y_2)$，同理可得点 $N$ 的坐标为 $(-1,y_1)$，可得 $AN//BM$，故 C 选项正确；",
        r"对于 D 选项，由 $\overrightarrow{FN}=(-2,y_1)$，$\overrightarrow{FM}=(-2,y_2)$，有 $\overrightarrow{FN}\cdot\overrightarrow{FM}=4+y_1y_2=4-4=0$，可得 $FM\perp FN$，故 D 选项正确．",
    ]))

rec(11, "multi_choice", [2],
    "\n".join([
        r"已知函数 $f(x)=2ax^3-3ax^2+2(a\in\mathbf{R})$，下列说法正确的是",
        r"A. 若 $x=0$ 是函数 $f(x)$ 的极大值点，则实数 $a$ 的取值范围为 $(-\infty,0)$",
        r"B. 当 $a\neq0$ 时，函数 $g(x)=f\left(x+\dfrac{1}{2}\right)+\dfrac{a}{2}-2$ 为奇函数",
        r"C. 若过点 $P(1,0)$ 有三条直线与曲线 $y=f(x)$ 相切，则实数 $a$ 的取值范围为 $\left(\dfrac{8}{5},2\right)$",
        r"D. 若函数 $f(x)$ 有 $3$ 个零点，则这 $3$ 个零点之和为 $\dfrac{3}{2}$",
    ]),
    {},
    "BCD",
    "\n".join([
        r"对于 A 选项，由 $f'(x)=6ax^2-6ax=6ax(x-1)$，当 $a=0$ 时，$f(x)=2$，$f(x)$ 没有极值；当 $a>0$ 时，令 $f'(x)>0$，可得 $x>1$ 或 $x<0$，可得函数 $f(x)$ 的减区间为 $(0,1)$，增区间为 $(-\infty,0)$，$(1,+\infty)$，此时 $x=0$ 为函数 $f(x)$ 的极大值点；当 $a<0$ 时，令 $f'(x)>0$，可得 $0<x<1$，可得函数 $f(x)$ 的减区间为 $(-\infty,0)$，$(1,+\infty)$，增区间为 $(0,1)$，此时 $x=0$ 为函数 $f(x)$ 的极小值点，故 A 选项错误；",
        r"对于 B 选项，由 $g(x)=f\left(x+\dfrac{1}{2}\right)+\dfrac{a}{2}-2=2a\left(x+\dfrac{1}{2}\right)^3-3a\left(x+\dfrac{1}{2}\right)^2+2+\dfrac{a}{2}-2=2ax^3-\dfrac{3}{2}ax$，有 $g(-x)=-g(x)$，可得函数 $g(x)$ 为奇函数，故 B 选项正确；",
        r"对于 C 选项，设切点为 $M(m,f(m))$，可得函数 $f(x)$ 在点 $M$ 处的切线方程为 $y-(2am^3-3am^2+2)=(6am^2-6am)(x-m)$，代入 $P(1,0)$ 有 $-(2am^3-3am^2+2)=(6am^2-6am)(1-m)$，整理为 $a(4m^3-9m^2+6m)=2$，若过点 $P(1,0)$ 有三条直线与曲线 $y=f(x)$ 相切，可得关于 $m$ 的方程 $a(4m^3-9m^2+6m)=2$ 有且仅有 $3$ 个根，显然 $a\neq0$，上述方程可化为 $4m^3-9m^2+6m=\dfrac{2}{a}$．令 $h(x)=4x^3-9x^2+6x$，有 $h'(x)=12x^2-18x+6=6(2x-1)(x-1)$，可得函数 $h(x)$ 的减区间为 $\left(\dfrac{1}{2},1\right)$，增区间为 $\left(-\infty,\dfrac{1}{2}\right)$，$(1,+\infty)$，又由 $h\left(\dfrac{1}{2}\right)=\dfrac{5}{4}$，$h(1)=1$．可得 $1<\dfrac{2}{a}<\dfrac{5}{4}$，可得 $\dfrac{8}{5}<a<2$，故 C 选项正确；",
        r"对于 D 选项，显然 $a\neq0$，设 $f(x_1)=f(x_2)=f(x_3)=0$，又由 $2ax_1^3-3ax_1^2+2=2ax_2^3-3ax_2^2+2$，可得 $2(x_1^2+x_1x_2+x_2^2)=3(x_1+x_2)$，同理可得 $2(x_1^2+x_1x_3+x_3^2)=3(x_1+x_3)$，将上面两式作差，可得 $x_1+x_2+x_3=\dfrac{3}{2}$，故 D 选项正确．",
    ]))

rec(13, "fill_in_blank", [2],
    r"已知在前 $n$ 项和为 $S_n$ 的等比数列 $\{a_n\}$ 中，$3a_1=a_2+2$ 且 $S_6=9S_3$，记 $b_n=|2\log_2a_n-25|$，则数列 $\{b_n\}$ 的前 $20$ 项的和为________．",
    {}, r"$208$",
    r"设数列 $\{a_n\}$ 的公比为 $q$，由 $S_6=9S_3$，有 $S_3+q^3S_3=9S_3$，可得 $q=2$，又由 $3a_1=a_2+2$，有 $3a_1=2a_1+2$，可得 $a_1=2$，可得 $a_n=2^n$．有 $b_n=|2\log_22^n-25|=|2n-25|$，可得数列 $\{b_n\}$ 的前 $20$ 项的和为 $(1+3+\cdots+23)+(1+3+\cdots+15)=\dfrac{12\times(1+23)}{2}+\dfrac{8\times(1+15)}{2}=208$．")

rec(14, "fill_in_blank", [3],
    r"已知函数 $f(x)=2\sin\left(\omega x-\dfrac{\pi}{4}\right)$（其中 $\omega>0$）在区间 $(1,2)$ 上没有零点，则 $\omega$ 的取值范围为________．",
    {}, r"$\left(0,\dfrac{\pi}{8}\right]\cup\left[\dfrac{\pi}{4},\dfrac{5\pi}{8}\right]$",
    "\n".join([
        r"令 $\omega x-\dfrac{\pi}{4}=-\pi$ 或 $0$ 或 $\pi$ 或 $2\pi$，可得 $x=-\dfrac{3\pi}{4\omega}$ 或 $\dfrac{\pi}{4\omega}$ 或 $\dfrac{5\pi}{4\omega}$ 或 $\dfrac{9\pi}{4\omega}$．由函数 $f(x)$ 在区间 $(1,2)$ 上没有零点，可得 $\dfrac{\pi}{\omega}\geqslant2-1$，可得 $0<\omega\leqslant\pi$．有 $\dfrac{5\pi}{4\omega}\geqslant\dfrac{5}{4}$ 且 $\dfrac{9\pi}{4\omega}\geqslant\dfrac{9}{4}$．若函数 $f(x)$ 在区间 $(1,2)$ 上没有零点，有 $\dfrac{\pi}{4\omega}\geqslant2$ 或 $\begin{cases}\dfrac{\pi}{4\omega}\leqslant1\\ \dfrac{5\pi}{4\omega}\geqslant2\end{cases}$，可得 $0<\omega\leqslant\dfrac{\pi}{8}$ 或 $\dfrac{\pi}{4}\leqslant\omega\leqslant\dfrac{5\pi}{8}$．",
    ]))

rec(15, "detailed_answer", [3],
    "\n".join([
        r"在 $\triangle ABC$ 中，内角 $A,B,C$ 所对的边分别为 $a,b,c$，且 $\cos2A=\cos2C+2\sin^2B+2\sin A\sin B$．",
        r"(1)求 $C$；",
        r"(2)若 $a=b+1$，$c=\sqrt{7}$，求 $\triangle ABC$ 的内切圆的半径．",
    ]),
    {},
    "\n".join([
        r"(1) $C=\dfrac{2\pi}{3}$；",
        r"(2) 内切圆的半径为 $\dfrac{3\sqrt{3}-\sqrt{21}}{2}$",
    ]),
    "\n".join([
        r"(1) 由 $\cos2A=\cos2C+2\sin^2B+2\sin A\sin B$，有 $1-2\sin^2A=1-2\sin^2C+2\sin^2B+2\sin A\sin B$，可得 $\sin^2A+\sin^2B-\sin^2C=-\sin A\sin B$．又由正弦定理，有 $a^2+b^2-c^2=-ab$．又由余弦定理，有 $\cos C=\dfrac{a^2+b^2-c^2}{2ab}=\dfrac{-ab}{2ab}=-\dfrac{1}{2}$．又由 $0<C<\pi$，可得 $C=\dfrac{2\pi}{3}$．",
        r"(2) 由(1)有 $a^2+b^2-c^2=-ab$，代入 $a=b+1$，$c=\sqrt{7}$，有 $(b+1)^2+b^2-(\sqrt{7})^2=-b(b+1)$，解得 $b=1$ 或 $b=-2$(舍去)．又由 $b=1$，可得 $a=2$．可得 $\triangle ABC$ 的面积为 $\dfrac{1}{2}\times1\times2\times\sin\dfrac{2\pi}{3}=\dfrac{\sqrt{3}}{2}$．设 $\triangle ABC$ 的内切圆的半径为 $r$，有 $\dfrac{1}{2}(a+b+c)r=\dfrac{\sqrt{3}}{2}$，代入 $a=2$，$b=1$，$c=\sqrt{7}$，有 $\dfrac{1}{2}(3+\sqrt{7})r=\dfrac{\sqrt{3}}{2}$，可得 $r=\dfrac{3\sqrt{3}-\sqrt{21}}{2}$，故 $\triangle ABC$ 的内切圆的半径为 $\dfrac{3\sqrt{3}-\sqrt{21}}{2}$．",
    ]))

rec(16, "detailed_answer", [3],
    "\n".join([
        r"为全面提升青少年消防安全意识和自防自救能力，$7$ 月 $24$ 日，某消防救援支队走进社区暑期爱心课堂，为孩子们带来了一堂生动有趣的“消防安全知识课”．",
        r"(1)已知爱心课堂共有 $10$ 名学生，其中有 $6$ 名男生，$4$ 名女生，从这 $10$ 名学生中任选 $3$ 名学生，记这 $3$ 名学生中女生的人数为 $X$，求 $X$ 的分布列和数学期望；",
        r"(2)课后设置消防安全有奖知识竞答，每道题答对的概率为 $0.4$，若小王同学希望答对的题目至少有 $4$ 道，则小王同学至少要抢答多少道题？",
    ]),
    {},
    "\n".join([
        r"(1) $E(X)=\dfrac{6}{5}$，分布列见解析；",
        r"(2) 小王同学至少要抢答 $10$ 道题",
    ]),
    "\n".join([
        r"(1) $X$ 可能的取值为 $0,1,2,3$．有 $P(X=0)=\dfrac{\mathrm{C}_6^3}{\mathrm{C}_{10}^3}=\dfrac{20}{120}=\dfrac{1}{6}$；$P(X=1)=\dfrac{\mathrm{C}_6^2\mathrm{C}_4^1}{\mathrm{C}_{10}^3}=\dfrac{60}{120}=\dfrac{1}{2}$；$P(X=2)=\dfrac{\mathrm{C}_6^1\mathrm{C}_4^2}{\mathrm{C}_{10}^3}=\dfrac{36}{120}=\dfrac{3}{10}$；$P(X=3)=\dfrac{\mathrm{C}_4^3}{\mathrm{C}_{10}^3}=\dfrac{4}{120}=\dfrac{1}{30}$．",
        r"可得 $X$ 的分布列为：",
        r"\[",
        r"\begin{array}{|c|c|c|c|c|}\hline X & 0 & 1 & 2 & 3\\\hline P & \dfrac{1}{6} & \dfrac{1}{2} & \dfrac{3}{10} & \dfrac{1}{30}\\\hline\end{array}",
        r"\]",
        r"$E(X)=0\times\dfrac{1}{6}+1\times\dfrac{1}{2}+2\times\dfrac{3}{10}+3\times\dfrac{1}{30}=\dfrac{6}{5}$．",
        r"(2) 设小王同学至少抢答 $n$ 道题，这 $n$ 道题中答对的题数为 $Y$，有 $Y\sim B(n,0.4)$．有 $0.4n\geqslant4$，可得 $n\geqslant10$，故小王同学至少要抢答 $10$ 道题．",
    ]))

rec(18, "detailed_answer", [4],
    "\n".join([
        r"已知等轴双曲线 $C:\dfrac{x^2}{a^2}-\dfrac{y^2}{b^2}=1(a>0,b>0)$ 的左、右顶点分别为 $A_1$、$A_2$，且 $|A_1A_2|=2\sqrt{2}$．不在 $x$ 轴上的点 $B_1$、$B_2$ 关于原点 $O$ 对称，且点 $B_1$、$B_2$ 都在双曲线 $C$ 上，过点 $B_1$、$B_2$ 分别作以线段 $A_1A_2$ 为直径的圆的一条切线，这两条切线相交于点 $P$．",
        r"(1)求双曲线 $C$ 的标准方程；",
        r"(2)求点 $P$ 的横坐标；",
        r"(3)求 $\triangle PB_1B_2$ 的面积的最小值．",
    ]),
    {},
    "\n".join([
        r"(1) $\dfrac{x^2}{2}-\dfrac{y^2}{2}=1$；",
        r"(2) 点 $P$ 的横坐标为 $-1$ 或 $1$；",
        r"(3) $\triangle PB_1B_2$ 的面积的最小值为 $4$",
    ]),
    "\n".join([
        r"(1) 由双曲线为等轴双曲线，有 $a=b$，又由 $|A_1A_2|=2\sqrt{2}$，有 $2a=2\sqrt{2}$，可得 $a=\sqrt{2}$，$b=\sqrt{2}$，故双曲线 $C$ 的标准方程为 $\dfrac{x^2}{2}-\dfrac{y^2}{2}=1$．",
        r"(2) 设 $B_1(m,n)$，$B_2(-m,-n)$(其中 $n\neq0$)，有 $\dfrac{m^2}{2}-\dfrac{n^2}{2}=1$，可得 $m^2=n^2+2$．设直线 $B_1P$ 的方程为 $y-n=k_1(x-m)$，直线 $B_2P$ 的方程为 $y+n=k_2(x+m)$．由直线 $B_1P$ 和直线 $B_2P$ 都与圆 $O$ 相切，有 $\begin{cases}\dfrac{|k_1m-n|}{\sqrt{1+k_1^2}}=\sqrt{2}\\ \dfrac{|k_2m-n|}{\sqrt{1+k_2^2}}=\sqrt{2}\end{cases}$．",
        r"可得 $k_1$，$k_2$ 是关于 $k$ 的方程 $\dfrac{|km-n|}{\sqrt{1+k^2}}=\sqrt{2}$ 的两个根，整理为 $(m^2-2)k^2-2mnk+n^2-2=0$，有 $k_1+k_2=\dfrac{2mn}{m^2-2}$，$k_1k_2=\dfrac{n^2-2}{m^2-2}$．",
        r"联立直线 $B_1P$ 和直线 $B_2P$ 方程消去 $y$ 后，有 $(k_2-k_1)x=2n-m(k_1+k_2)$，代入 $k_1+k_2=\dfrac{2mn}{m^2-2}$，有 $(k_2-k_1)x=2n-\dfrac{2m^2n}{m^2-2}$，整理为 $(k_2-k_1)x=-\dfrac{4n}{m^2-2}$，",
        r"又由 $(k_2-k_1)^2=(k_2+k_1)^2-4k_1k_2=\dfrac{4m^2n^2}{(m^2-2)^2}-\dfrac{4(n^2-2)}{m^2-2}=\dfrac{8(m^2+n^2-2)}{(m^2-2)^2}=\dfrac{8(n^2+2+n^2-2)}{(m^2-2)^2}=\dfrac{16n^2}{(m^2-2)^2}$，",
        r"有 $k_2-k_1=\pm\dfrac{4n}{m^2-2}$，代入 $(k_2-k_1)x=\dfrac{4n}{m^2-2}$ 可得 $x=\pm1$，故点 $P$ 的横坐标为 $-1$ 或 $1$．",
        r"(3) 由圆的对称性，可知 $S_{\triangle PB_1B_2}=2S_{\triangle OPB_2}=|OB_2|\times|OP|$．又由圆的对称性，不妨设点 $P$ 的横坐标为 $1$，又由 $OP\perp OB_2$，可得直线 $OP$ 的方程为 $y=-\dfrac{m}{n}x$，取 $x=1$，可得点 $P$ 的坐标为 $\left(1,-\dfrac{m}{n}\right)$，有 $|OP|=\sqrt{1+\dfrac{m^2}{n^2}}$，$|OB_2|=\sqrt{m^2+n^2}$．",
        r"可得 $S_{\triangle PB_1B_2}=\sqrt{1+\dfrac{m^2}{n^2}}\times\sqrt{m^2+n^2}=\dfrac{m^2+n^2}{|n|}=\dfrac{(n^2+2)+n^2}{|n|}=\dfrac{2(n^2+1)}{|n|}\geqslant\dfrac{4|n|}{|n|}=4$(当且仅当 $n=1$ 或 $-1$ 时取等号)，故 $\triangle PB_1B_2$ 的面积的最小值为 $4$．",
    ]))

rec(19, "detailed_answer", [4],
    "\n".join([
        r"已知函数 $f(x)=x+(x-1)\ln(x+1)$．",
        r"(1)证明：$f(x)\geqslant0$；",
        r"(2)证明：$\sum\limits_{i=1}^{n}\dfrac{1}{i+2}<\ln(n+1)$；",
        r"(3)若 $x_1\neq x_2$ 且 $f(x_1)=f(x_2)$，证明：$x_1+x_2>0$．",
    ]),
    {},
    "证明见解析",
    "\n".join([
        r"(1) 证明：由 $x+1>0$，可得 $x>-1$，可知函数 $f(x)$ 的定义域为 $(-1,+\infty)$，又由 $f'(x)=1+\ln(x+1)+\dfrac{x-1}{x+1}=\ln(x+1)+\dfrac{2x}{x+1}$．令 $g(x)=\ln(x+1)+\dfrac{2x}{x+1}$，有 $g'(x)=\dfrac{1}{x+1}+\dfrac{2}{(x+1)^2}>0$，可得函数 $g(x)$ 单调递增，又由 $g(0)=0$，可知当 $x<0$ 时，$g(x)<0$；当 $x>0$ 时，$g(x)>0$．可得函数 $f(x)$ 的减区间为 $(-1,0)$，增区间为 $(0,+\infty)$，可得 $f(x)\geqslant f(0)=0$，所以 $f(x)\geqslant0$．",
        r"(2) 证明：由(1)可知，不等式 $x+(x-1)\ln(x+1)\geqslant0$($x=0$ 时取等号)恒成立．当 $-1<x<1$ 时，不等式 $x+(x-1)\ln(x+1)>0$ 可化为 $\ln(x+1)<\dfrac{x}{1-x}$，取 $x=-\dfrac{1}{n+1}$，有 $\ln\left(-\dfrac{1}{n+1}+1\right)<\dfrac{-\dfrac{1}{n+1}}{1-\left(-\dfrac{1}{n+1}\right)}$，有 $\ln\dfrac{n}{n+1}<-\dfrac{1}{n+2}$，可得 $\dfrac{1}{n+2}<\ln\dfrac{n+1}{n}$，",
        r"有 $\sum\limits_{i=1}^{n}\dfrac{1}{i+2}<\ln\dfrac{2}{1}+\ln\dfrac{3}{2}+\cdots+\ln\dfrac{n+1}{n}=\ln\left(\dfrac{2}{1}\times\dfrac{3}{2}\times\cdots\times\dfrac{n+1}{n}\right)=\ln(n+1)$，故不等式 $\sum\limits_{i=1}^{n}\dfrac{1}{i+2}<\ln(n+1)$ 成立．",
        r"(3) 证明：不妨设 $x_1<x_2$，由函数 $f(x)$ 的减区间为 $(-1,0)$，增区间为 $(0,+\infty)$，可得 $-1<x_1<0<x_2$．",
        r"①当 $x_2\geqslant1$ 时，又由 $-1<x_1<0$，可得 $x_1+x_2>-1+1=0$，",
        r"②当 $0<x_2<1$ 时，由 $f(x_1)-f(-x_2)=f(x_2)-f(-x_2)=[x_2+(x_2-1)\ln(x_2+1)]-[-x_2+(-x_2-1)\ln(-x_2+1)]=2x_2+(x_2-1)\ln(x_2+1)+(x_2+1)\ln(1-x_2)$．令 $h(x)=2x+(x-1)\ln(x+1)+(x+1)\ln(1-x)$，其中 $0\leqslant x<1$，有 $h'(x)=2+\ln(x+1)+\dfrac{x-1}{x+1}+\ln(1-x)-\dfrac{x+1}{1-x}=\ln(1-x^2)-\left(\dfrac{1-x}{x+1}+\dfrac{x+1}{1-x}\right)+2$．",
        r"又由 $\dfrac{1-x}{x+1}+\dfrac{1+x}{1-x}\geqslant2\sqrt{\dfrac{1-x}{x+1}\times\dfrac{1+x}{1-x}}=2$(当且仅当 $\dfrac{1-x}{x+1}=\dfrac{1+x}{1-x}$ 即 $x=0$ 时取等号)．又由 $0<1-x^2\leqslant1$，可得 $\ln(1-x^2)\leqslant\ln1=0$，有 $h'(x)\leqslant0-2+2=0$，可得函数 $h(x)$ 单调递减，又由 $h(0)=0$，可得 $h(x)\leqslant0$(当且仅当 $x=0$ 时取等号)．",
        r"又由 $0<x_2<1$，有 $f(x_1)-f(-x_2)<0$，可得 $f(x_1)<f(-x_2)$，又由 $-1<x_1<0$，$-1<-x_2<0$ 及函数 $f(x)$ 在 $(-1,0)$ 上单调递减，有 $x_1>-x_2$，即 $x_1+x_2>0$．",
        r"由①②可知，若 $x_1\neq x_2$ 且 $f(x_1)=f(x_2)$，则不等式 $x_1+x_2>0$ 成立．",
    ]))

# ---------------- 待复核 ----------------
R = []


def pd(n, t, page, kind, raw, note):
    R.append({"题号": n, "题型": t, "页码": page, "类型": kind, "原文": raw, "说明": note})


pd(9, "multi_choice", [2], "figure",
   "\n".join([
       r"如图，在棱长为 $2$ 的正方体 $ABCD-A_1B_1C_1D_1$ 中，点 $P$ 是线段 $BD$ 上的一个动点，则",
       r"A. 正方体 $ABCD-A_1B_1C_1D_1$ 的体积为 $8$",
       r"B. 正方体 $ABCD-A_1B_1C_1D_1$ 的外接球的表面积为 $8\pi$",
       r"C. $AC\perp PD_1$",
       r"D. 直线 $PD_1$ 与底面 $ABCD$ 所成的角的正切值的取值范围为 $[1,+\infty)$",
   ]),
   r"试卷第 2 页 #9 题干右侧印一幅正方体直观图：下底面按 $A$（左前）、$B$（右前）、$C$（右后）、$D$（左后，虚线交点）标注，上底面为 $A_1$、$B_1$、$C_1$、$D_1$，$P$ 标在底面对角线 $BD$ 上靠 $B$ 一侧，并画出 $D_1$ 到 $P$ 的虚线段。题干自带「如图」，按规矩不录正文。答案册第 1 页给了逐项解析，答案 $AC$：A 由棱长为 $2$ 得体积为 $8$，正确；B 由 $BD_1=2\sqrt{3}$ 得外接球表面积为 $4\pi\times(\sqrt{3})^2=12\pi$，错误；C 由 $AC\perp BD$、$AC\perp DD_1$ 得 $AC\perp$ 平面 $BB_1D_1D$，又 $PD_1\subset$ 平面 $BB_1D_1D$，故 $AC\perp PD_1$，正确；D 由 $DD_1\perp$ 底面 $ABCD$ 得所成角为 $\angle D_1PD$，$\tan\angle DPD_1=\dfrac{DD_1}{DP}=\dfrac{2}{DP}\in\left[\dfrac{\sqrt{2}}{2},+\infty\right)$，与选项印的 $[1,+\infty)$ 不符，错误。")

pd(12, "fill_in_blank", [2], "figure",
   r"如图，在边长为 $1$ 的正六边形 $ABCDEF$ 中，$|\overrightarrow{ED}+\overrightarrow{EB}|=$________．",
   r"试卷第 2 页 #12 题干下方印一幅正六边形图：六个顶点按 $A$（左下）、$B$（右下）、$C$（右）、$D$（右上）、$E$（左上）、$F$（左）标注，边长为 $1$。题干自带「如图」，按规矩不录正文。答案册第 2 页另印一幅同形六边形图（多标了中心点 $O$ 与虚线 $EB$、$EC$、$OC$），并给出解析：连接 $BE$，取线段 $BE$ 的中点为 $O$，连接 $OC,EC$，由 $\overrightarrow{ED}+\overrightarrow{EB}=\overrightarrow{ED}+2\overrightarrow{EO}$，及 $\overrightarrow{ED}\cdot\overrightarrow{EO}=\dfrac{1}{2}$ 有 $|\overrightarrow{ED}+\overrightarrow{EB}|^2=|\overrightarrow{ED}|^2+4\overrightarrow{ED}\cdot\overrightarrow{EO}+4|\overrightarrow{EO}|^2=7$，可得 $|\overrightarrow{ED}+\overrightarrow{EB}|=\sqrt{7}$。答案 $\sqrt{7}$。")

pd(17, "detailed_answer", [3], "figure",
   "\n".join([
       r"如图，在直四棱柱 $ABCD-A_1B_1C_1D_1$ 中，底面 $ABCD$ 是等腰梯形，$AD//BC$，$AB=CD=1$，$BC=\sqrt{2}$，$AD=2\sqrt{2}$，点 $P$ 是线段 $AD_1$ 的中点．",
       r"(1)证明：$CP//$ 平面 $AA_1B_1B$；",
       r"(2)证明：$CD\perp$ 平面 $AA_1B_1B$；",
       r"(3)若 $AA_1=2\sqrt{2}$，求 $CP$ 与平面 $CC_1D_1D$ 所成的角的正弦值．",
   ]),
   "\n".join([
       r"试卷第 3 页 #17 题干右下方印一幅直四棱柱直观图：上底面标 $A_1$、$B_1$、$C_1$、$D_1$，下底面标 $A$、$B$、$C$、$D$，$P$ 标在侧面内靠 $AD_1$ 中点处，$AD_1$、$PD$、$AC$ 等以虚线表示。题干自带「如图」，按规矩不录正文。答案册第 4 页另印一幅以 $A$ 为原点、过 $A$ 在底面内作 $AD$ 垂线为 $x$ 轴、$AD$ 为 $y$ 轴、$AA_1$ 为 $z$ 轴的空间直角坐标系建系图（图上多标了棱 $AA_1$ 的中点 $Q$ 与底边 $AD$ 的中点 $O$）。",
       r"答案册第 4 页的完整解答：(1) 取棱 $AA_1$ 的中点为 $Q$，连接 $PQ,BQ$，由 $AP=PD_1$、$AQ=QA_1$ 得 $PQ//A_1D_1$ 且 $A_1D_1=2PQ$；又 $BC//AD$ 且 $AD=2BC$、$AD//A_1D_1$，得 $BC//PQ$ 且 $BC=PQ$，故四边形 $BCPQ$ 为平行四边形，$\therefore BQ//CP$，由 $BQ\subset$ 平面 $ABB_1A_1$、$CP\not\subset$ 平面 $ABB_1A_1$ 得 $CP//$ 平面 $AA_1B_1B$。",
       r"(2) 取棱 $AD$ 的中点为 $O$，由 $AD//BC$、$AB=CD=1$、$BC=\sqrt{2}$、$AD=2\sqrt{2}$、$AO=OD$ 得 $OB=1$、$AO=\sqrt{2}$，由 $OB=1$、$AO=\sqrt{2}$、$AB=1$ 得 $AO^2=AB^2+OB^2$，$\therefore OB\perp AB$；由 $BC=OD=\sqrt{2}$、$BC//OD$ 得四边形 $BCDO$ 为平行四边形，$\therefore CD//BO$，又 $OB\perp AB$ 得 $CD\perp AB$；直四棱柱中 $AA_1$ 为侧棱、$CD\subset$ 底面 $ABCD$ 得 $AA_1\perp CD$，由 $AA_1\perp CD$、$AB\perp CD$、$AA_1\cap AB=A$、$AA_1$、$AB\subset$ 平面 $AA_1B_1B$ 得 $CD\perp$ 平面 $AA_1B_1B$。",
       r"(3) 由 $OB\perp AB$、$AB=OB=1$ 得 $\angle OAB=\dfrac{\pi}{4}$，建系后 $A(0,0,0)$、$D(0,2\sqrt{2},0)$、$B\left(\dfrac{\sqrt{2}}{2},\dfrac{\sqrt{2}}{2},0\right)$、$C\left(\dfrac{\sqrt{2}}{2},\dfrac{3\sqrt{2}}{2},0\right)$、$A_1(0,0,2\sqrt{2})$、$D_1(0,2\sqrt{2},2\sqrt{2})$、$P(0,\sqrt{2},\sqrt{2})$，$\overrightarrow{CP}=\left(-\dfrac{\sqrt{2}}{2},-\dfrac{\sqrt{2}}{2},\sqrt{2}\right)$；设平面 $CC_1D_1D$ 的法向量 $\boldsymbol{m}=(x,y,z)$，由 $\overrightarrow{DD_1}=(0,0,2\sqrt{2})$、$\overrightarrow{CD}=\left(-\dfrac{\sqrt{2}}{2},\dfrac{\sqrt{2}}{2},0\right)$ 取 $x=1,y=1,z=0$ 得 $\boldsymbol{m}=(1,1,0)$，$\overrightarrow{CP}\cdot\boldsymbol{m}=-\sqrt{2}$、$|\overrightarrow{CP}|=\sqrt{3}$、$|\boldsymbol{m}|=\sqrt{2}$，$\cos\langle\overrightarrow{CP},\boldsymbol{m}\rangle=-\dfrac{\sqrt{3}}{3}$，故 $CP$ 与平面 $CC_1D_1D$ 所成的角的正弦值为 $\dfrac{\sqrt{3}}{3}$。",
   ]))

pd(16, "detailed_answer", [3], "table",
   r"可得 $X$ 的分布列为：（答案册第 3 页印一张两行五列表格）",
   r"答案册第 3 页 #16(1) 末尾把 $X$ 的分布列印成一张 $2$ 行 $5$ 列表格：第一行 $X$、$0$、$1$、$2$、$3$；第二行 $P$、$\dfrac{1}{6}$、$\dfrac{1}{2}$、$\dfrac{3}{10}$、$\dfrac{1}{30}$。四格概率之和 $\dfrac{5}{30}+\dfrac{15}{30}+\dfrac{9}{30}+\dfrac{1}{30}=1$，自洽。#16 题干纯文字，正文与解析已照录入成品，这张表在成品的解析里按本项目惯例转写成了 array 阵列（保留原句「可得 $X$ 的分布列为：」）；本条登记是为了请人工核对原表数值与转写是否一致。")

pd(18, "detailed_answer", [4], "print-suspect",
   r"整理为 $(k_2-k_1)x=-\dfrac{4n}{m^2-2}$ …… 有 $k_2-k_1=\pm\dfrac{4n}{m^2-2}$，代入 $(k_2-k_1)x=\dfrac{4n}{m^2-2}$ 可得 $x=\pm1$",
   r"答案册第 5 页 #18(2) 前后两行符号不一致：前面「整理为」印作 $(k_2-k_1)x=-\dfrac{4n}{m^2-2}$，后面「代入」时印作 $(k_2-k_1)x=\dfrac{4n}{m^2-2}$（少一个负号）。因下一步取 $k_2-k_1=\pm\dfrac{4n}{m^2-2}$，两种写法都得出 $x=\pm1$，结论与标答不受影响，故**照录原印文未作订正**，只在此登记，请人工决定是否补负号。")

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
