# -*- coding: utf-8 -*-
"""199 浙江金丽衢十二校2026届高三第一次联考 —— 成品 / 待复核 生成脚本。"""
import json
from pathlib import Path

OUT = Path("数据/录题/输出_v2")
STEM = "199_浙江金丽衢十二校2026届高三第一次联考"

Q = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知集合 $A=\{0,1,2\}$，$B=\left\{x\mid x^2<4\right\}$，则 $A\cap B=$",
        "选项": {
            "A": r"$\{0,1\}$",
            "B": r"$\{0,1,2\}$",
            "C": r"$(-2,2)$",
            "D": r"$(-2,2]$",
        },
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"直线 $\sqrt{3}x+y-1=0$ 的倾斜角为",
        "选项": {
            "A": r"$\dfrac{\pi}{6}$",
            "B": r"$\dfrac{\pi}{4}$",
            "C": r"$\dfrac{2\pi}{3}$",
            "D": r"$\dfrac{5\pi}{6}$",
        },
        "答案": "C", "解析": "解析无",
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知函数 $f(x)=\begin{cases}e^x+2, & x<1\\ \ln x, & x>1\end{cases}$，则 $f(f(2))=$",
        "选项": {
            "A": r"$\ln(\ln 2)$",
            "B": r"$\ln 2$",
            "C": r"$2$",
            "D": r"$4$",
        },
        "答案": "D", "解析": "解析无",
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知复数 $z=2+\mathrm{i}$，设 $z,\overline{z}$ 在复平面内对应的向量分别为 $\boldsymbol{a}$，$\boldsymbol{b}$，则 $\boldsymbol{a}\cdot\boldsymbol{b}=$",
        "选项": {
            "A": r"$\sqrt{5}$",
            "B": r"$3$",
            "C": r"$5$",
            "D": r"$3+2\mathrm{i}$",
        },
        "答案": "B", "解析": "解析无",
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知直线 $a,b$ 与平面 $\alpha,\beta$，则下列选项可使得 $a\parallel\alpha$ 的是",
        "选项": {
            "A": r"$a\parallel b,b\subset\alpha$",
            "B": r"$a\subset\beta,\beta\parallel\alpha$",
            "C": r"$a\parallel b,b\perp\alpha$",
            "D": r"$a\perp\beta,\beta\perp\alpha$",
        },
        "答案": "B", "解析": "解析无",
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"对实数 $x,y$，则“$|x|>|y|$”是“$x^2|x|>y^2|y|$”的",
        "选项": {
            "A": "充分不必要条件",
            "B": "必要不充分条件",
            "C": "充要条件",
            "D": "既不充分也不必要条件",
        },
        "答案": "C", "解析": "解析无",
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"已知三次函数 $y=x^3-6x^2+9x$，若不等式 $y\leqslant m$ 的解集为 $\{x|x\leqslant m\}$，则 $m$ 的值为",
        "选项": {"A": r"$0$", "B": r"$1$", "C": r"$2$", "D": r"$4$"},
        "答案": "D", "解析": "解析无",
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [1], "粗筛图": False, "粗筛表": False,
        "题干": r"某晚会由 $4$ 个歌舞节目和 $2$ 个机器人表演节目组成，若要求机器人表演节目不能相邻出演且前 $3$ 个节目中至少有一个是机器人表演节目，则不同的节目安排方法有（    ）种．",
        "选项": {"A": r"$216$", "B": r"$360$", "C": r"$432$", "D": r"$672$"},
        "答案": "C", "解析": "解析无",
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"有一组数据 $1,1,3,4,5,5,6,7$，则",
        "选项": {
            "A": r"该组数据的极差为 $6$",
            "B": r"该组数据的中位数为 $5$",
            "C": r"该组数据的平均数为 $4$",
            "D": r"将数据 $1$ 均改为 $3$ 后，方差会变大",
        },
        "答案": "AC", "解析": "解析无",
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2], "粗筛图": True, "粗筛表": False,
        "题干": r"$M$ 是坐标平面内一个动点，$MA$ 与直线 $y=x$ 垂直，垂足 $A$ 位于第一象限，$MB$ 与直线 $y=-x$ 垂直，垂足 $B$ 位于第四象限．若四边形 $OAMB$（$O$ 为原点）的面积为 $3$，设 $M(x,y)$ 的轨迹为曲线 $C$，则",
        "选项": {
            "A": r"$C$ 的方程为 $x^2-y^2=6(x>0)$",
            "B": r"$C$ 的方程为 $y^2-x^2=6(y>0)$",
            "C": r"$y-2x$ 的最大值为 $-3\sqrt{2}$",
            "D": r"$\dfrac{12-xy}{x^2}$ 的最大值为 $\dfrac{17}{8}$",
        },
        "答案": "ACD", "解析": "解析无",
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"已知矩形 $ABCD$，$AB=2$，$BC=1$，若点 $P$ 为边 $AB$ 上的一动点（不包括端点），现将 $\triangle ADP$ 沿着 $DP$ 翻折成 $\triangle A'DP$，使得平面 $A'PD\perp$ 平面 $PBCD$，并记为 $\tau_P(A)=A'$．则",
        "选项": {
            "A": r"存在点 $P$，使得 $A'D\perp PB$",
            "B": r"任意点 $P$，都有 $AA'\perp PD$",
            "C": r"存在两点 $\tau_{P_1}(A),\tau_{P_2}(A)$，使得它们所确定的直线与 $PB$ 垂直",
            "D": r"任意两点 $\tau_{P_1}(A),\tau_{P_2}(A)$，它们所确定的直线与平面 $PBCD$ 的所成角都小于 $45^\circ$",
        },
        "答案": "BCD", "解析": "解析无",
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"已知 $\alpha\in(0,\pi)$，满足 $\sin\left(\alpha+\dfrac{\pi}{2}\right)=\dfrac{1}{3}$，则 $\tan\alpha=$________．",
        "答案": r"$2\sqrt{2}$", "解析": "解析无",
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"已知公差为 $d$ 的等差数列 $\{a_n\}$ 的前 $n$ 项和为 $S_n$，$a_4=10$，$S_6$ 是 $\{S_n\}$ 中的唯一最大项，则 $d$ 的取值范围为________．",
        "答案": r"$\left(-5,-\dfrac{10}{3}\right)$（闭区间不扣分）", "解析": "解析无",
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [2], "粗筛图": False, "粗筛表": False,
        "题干": r"设离心率为 $e$ 的椭圆 $\dfrac{x^2}{a^2}+\dfrac{y^2}{b^2}=1(a>b>0)$ 的左焦点为 $F$，右顶点为 $A$．以 $AF$ 为直径的圆与该椭圆相交于点 $B$（异于点 $A$），过点 $B$ 作 $x$ 轴的垂线，设垂足为 $D$，记 $\triangle FBD,\triangle ABD,\triangle FBA$ 的面积分别为 $S_1,S_2,S_3$，若 $S_1,S_2,S_3$ 为以 $q$ 为公比的等比数列，则 $qe=$________．",
        "答案": r"$1$", "解析": "解析无",
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [3], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"已知函数 $f(x)=2\sqrt{3}\sin x\cos x-2\cos^2 x+1$．",
            r"（1）求函数 $f(x)$ 的最小正周期，以及在区间 $\left[0,\dfrac{\pi}{2}\right]$ 上的最小值；",
            r"（2）在 $\triangle ABC$ 中，角 $A,B,C$ 所对的边分别为 $a,b,c$．若 $f(A)=2$，$S_{\triangle ABC}=\sqrt{3}$，$b+c=5$，求 $a$ 的长．",
        ]),
        "答案": r"（1）最小正周期 $T=\pi$，在 $\left[0,\dfrac{\pi}{2}\right]$ 上的最小值为 $-1$；（2）$a=\sqrt{13}$",
        "解析": "\n".join([
            r"解：（1）$f(x)=\sqrt{3}\sin 2x-\cos 2x-1+1=2\sin\left(2x-\dfrac{\pi}{6}\right)$，",
            r"因此最小正周期为 $T=\dfrac{2\pi}{2}=\pi$，",
            r"当 $x\in\left[0,\dfrac{\pi}{2}\right]$ 时，$2x-\dfrac{\pi}{6}\in\left[-\dfrac{\pi}{6},\dfrac{5\pi}{6}\right]$，因此 $f(x)_{\min}=f(0)=-1$．",
            r"（2）由 $f(A)=2$ 得 $A=\dfrac{\pi}{3}+k\pi(k\in\mathbf{Z})$，又 $A\in(0,\pi)$ 故 $A=\dfrac{\pi}{3}$，",
            r"由 $S_{\triangle ABC}=\sqrt{3}$ 得 $\dfrac{1}{2}bc\sin A=\sqrt{3}$ 从而 $bc=4$，",
            r"由余弦定理得 $a=\sqrt{b^2+c^2-2bc\cos A}=\sqrt{(b+c)^2-2bc(1+\cos A)}=\sqrt{13}$．",
        ]),
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"已知抛物线 $C:y^2=2px(p>0)$ 的焦点为 $F$，$C$ 上有一点 $P(p,y_0)$ 到焦点 $F$ 的距离为 $3$，过焦点 $F$ 作直线与抛物线交于 $A,B$ 两点，$|AB|=6$，$O$ 为坐标原点．",
            r"（1）求点 $F$ 的坐标；",
            r"（2）求 $\triangle OAB$ 的面积．",
        ]),
        "答案": r"（1）$F(1,0)$；（2）$\sqrt{6}$",
        "解析": "\n".join([
            r"解：（1）由抛物线定义可得 $|PF|=\dfrac{3p}{2}=3$，因此 $p=2$",
            r"所以抛物线 $C$ 的方程为 $y^2=4x$，焦点 $F$ 的坐标为 $(1,0)$",
            r"（2）设直线 $AB$ 的方程为 $x=my+1$，与 $y^2=4x$ 联立，消元可得 $y^2-4my-4=0$，",
            r"$\Delta=16\left(m^2+1\right)$，",
            r"故 $|AB|=\sqrt{1+m^2}|y_1-y_2|=\sqrt{1+m^2}\dfrac{\sqrt{\Delta}}{|a|}=4\left(1+m^2\right)=6$；",
            r"得 $m=\pm\dfrac{\sqrt{2}}{2}$．",
            r"原点 $O$ 到直线 $AB$ 的距离为 $d=\dfrac{|1|}{\sqrt{1+m^2}}=\dfrac{1}{\sqrt{\dfrac{3}{2}}}=\dfrac{\sqrt{6}}{3}$，",
            r"所以 $S_{\triangle ABP}=\dfrac{1}{2}d\cdot|AB|=\sqrt{6}$．",
        ]),
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4], "粗筛图": False, "粗筛表": False,
        "题干": "\n".join([
            r"现将 $n+1$ 个黑球与 $n$ 个白球分装入甲、乙两袋中，通过掷骰子来决定每次操作，掷出奇数点则从甲袋中取一个球，掷出偶数点则从乙袋中取一个球，每次取出的球不放回．",
            r"（1）若 $n=4$，且甲袋中放有 $2$ 个黑球与 $2$ 个白球，求操作一次取出的球是白球的概率；",
            r"（2）若 $n>5$ 且甲袋中均为黑球，乙袋中均为白球，",
            r"（i）操作 $5$ 次时，求取出白球个数的数学期望；",
            r"（ii）设事件 $A$ 为“当白球取完时，黑球剩余数量不少于 $2$ 个”，求 $P(A)$．",
        ]),
        "答案": r"（1）$\dfrac{9}{20}$；（2）（i）$\dfrac{5}{2}$；（ii）$\dfrac{1}{2}$",
        "解析": "\n".join([
            r"解：（1）当 $n=4$ 时，甲袋中 $2$ 黑 $2$ 白，乙袋中 $3$ 黑 $2$ 白．",
            r"$\therefore p=\dfrac{1}{2}\times\dfrac{1}{2}+\dfrac{1}{2}\times\dfrac{2}{5}=\dfrac{1}{4}+\dfrac{1}{5}=\dfrac{9}{20}$．",
            r"（2）（i）取到白球等价于选中乙袋．",
            r"设取出白球个数为 $X$，则 $X\sim B\left(5,\dfrac{1}{2}\right)$．",
            r"$\therefore E(X)=5\times\dfrac{1}{2}=\dfrac{5}{2}$．",
            r"（ii）事件 $A$ 等价于前 $2n-1$ 次操作中就已经摸出所有白球，",
            r"即掷骰子至多 $2n-1$ 次就出现了 $n$ 次偶数，",
            r"（以此列式 $P(A)=\sum\limits_{k=n-1}^{2n-2}\dfrac{C_k^{n-1}}{2^{k+1}}$ 即可得分）",
            r"不妨设掷骰子掷满 $2n-1$ 次，",
            r"用 $Y$ 表示其中掷出偶数的次数，则 $Y\sim B\left(2n-1,\dfrac{1}{2}\right)$，所以",
            r"$P(A)=P(Y\ge n)=\left(\dfrac{1}{2}\right)^{2n-1}\left(C_{2n-1}^{n}+C_{2n-1}^{n+1}+\cdots+C_{2n-1}^{2n-1}\right)=\dfrac{1}{2}$．",
        ]),
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4], "粗筛图": True, "粗筛表": False,
        "题干": "\n".join([
            r"在正弦曲线 $y=\sin x$ 上有一点 $P_1(x_1,y_1)\left(0<x_1<\dfrac{\pi}{2}\right)$，按照如下方式依次构造点 $P_n(n=2,3,\cdots)$：作曲线在 $P_{n-1}$ 处的切线与 $x$ 轴交于点 $Q_{n-1}$，过点 $Q_{n-1}$ 作 $x$ 轴的垂线与正弦曲线交于点 $P_n$，记 $P_n$ 的坐标为 $(x_n,y_n)$，已知 $x_n\ne\dfrac{\pi}{2}+k\pi(k\in\mathbf{Z})$，设 $\tan x_1=\alpha x_1$．",
            r"（1）证明：$\alpha>1$；",
            r"（2）若对任意正整数 $n$，都有 $|x_{n+1}|<|x_n|$ 成立，求 $\alpha$ 的取值范围；",
            r"（3）若 $\alpha=\dfrac{3}{2}$，证明：对任意正整数 $n$，有 $\tan x_1+\tan x_3+\cdots+\tan x_{2n-1}<2x_1$ 成立．",
        ]),
        "答案": r"（1）见解析；（2）$\alpha\in(1,2)$；（3）见解析",
        "解析": "\n".join([
            r"解：（1）记函数 $f(x)=\tan x-x\left(0<x<\dfrac{\pi}{2}\right)$，则 $f'(x)=\dfrac{1}{\cos^2 x}-1>0$．",
            r"因此 $f(x)$ 在 $\left(0,\dfrac{\pi}{2}\right)$ 上单调递增，故 $f(x)>f(0)=0$，所以 $\tan x>x\left(0<x<\dfrac{\pi}{2}\right)$ 即 $\alpha>1$．",
            r"（2）由题意可得直线 $P_nQ_n$ 的方程为 $y-\sin x_n=\cos x_n\left(x-x_n\right)$，",
            r"将点 $Q_n\left(x_{n+1},0\right)$ 代入，得 $-\sin x_n=\cos x_n\left(x_{n+1}-x_n\right)$．",
            r"$x_{n+1}=x_n-\tan x_n$．",
            r"由题意得 $|x_2|<|x_1|$ 即 $|x_1-\tan x_1|<|x_1|$，由（1）得 $\alpha>1$，$(\alpha-1)x_1<x_1$ 即 $\alpha<2$．",
            r"另一方面，记函数 $g(x)=\dfrac{\tan x}{x}\left(0<x<\dfrac{\pi}{2}\right)$，则 $g'(x)=\dfrac{x-\sin x\cos x}{x^2\cos^2 x}$，令",
            r"$h(x)=x-\sin x\cos x\left(0<x<\dfrac{\pi}{2}\right)$，则 $h'(x)=1-\cos 2x>0$，故 $h(x)$ 在 $\left(0,\dfrac{\pi}{2}\right)$ 上单调递增，",
            r"故 $h(x)>h(0)=0$，即 $g'(x)>0$，故 $g(x)$ 在 $\left(0,\dfrac{\pi}{2}\right)$ 上单调递增．",
            r"而 $g\left(\dfrac{\pi}{4}\right)<2$，$g\left(\dfrac{5\pi}{12}\right)=\dfrac{12\left(2+\sqrt{3}\right)}{5\pi}>2$，由零点存在定理可得存在唯一 $x_0\in\left(0,\dfrac{\pi}{2}\right)$ 使得",
            r"$g(x_0)=2$ 即 $\tan x_0=2x_0$．",
            r"因此当 $x_n\in\left(0,x_0\right)$ 时，$g(x_n)\in(1,2)$，而 $g(x)$ 为偶函数，故当 $x_n\in\left(-x_0,0\right)$ 时，$g(x_n)\in(1,2)$．",
            r"当 $\alpha\in(1,2)$ 时，$x_1\in\left(0,x_0\right)$．假设 $n=k\left(k\in\mathbf{N}^*\right)$ 时 $x_k\in\left(-x_0,x_0\right)$，则",
            r"$\left|\dfrac{x_{k+1}}{x_k}\right|=\left|1-\dfrac{\tan x_k}{x_k}\right|=g(x_k)-1\in(0,1)$，故 $|x_{k+1}|<|x_k|<x_0$．由此归纳可得",
            r"$x_n\in\left(-x_0,x_0\right)\left(\forall n\in\mathbf{N}^*\right)$．",
            r"所以 $\left|\dfrac{x_{k+1}}{x_k}\right|\in(0,1)$ 即 $|x_{k+1}|<|x_k|$．",
            r"综上所述，$\alpha$ 的取值范围为 $\alpha\in(1,2)$．",
            r"（3）由（2）得当 $\alpha=\dfrac{3}{2}$ 时 $|x_{k+1}|<|x_k|$ 且 $\dfrac{x_{k+1}}{x_k}=1-\dfrac{\tan x_k}{x_k}=1-g(x_k)\in(-1,0)$，故",
            r"$x_{2n}<0$，$x_{2n-1}>0\left(\forall n\in\mathbf{N}^*\right)$．",
            r"另一方面，$\left|\dfrac{x_{n+1}}{x_n}\right|=g(x_n)-1<\alpha-1$，故 $\left|\dfrac{x_{n+2}}{x_n}\right|=\left(g(x_{2n-1})-1\right)\left(g(x_{2n})-1\right)<(\alpha-1)^2=\dfrac{1}{4}$",
            r"故 $\tan x_{2n+1}=x_{2n+1}-x_{2n+2}=\left|x_{2n+1}\right|+\left|x_{2n+2}\right|<\dfrac{1}{4}\left(x_{2n-1}-x_{2n}\right)=\dfrac{1}{4}\tan x_{2n-1}$",
            r"所以 $\tan x_1+\tan x_3+\cdots+\tan x_{2n-1}=\tan x_1\cdot\dfrac{1-\dfrac{1}{4^n}}{1-\dfrac{1}{4}}<\dfrac{3}{2}x_1\cdot\dfrac{4}{3}=2x_1$．",
        ]),
    },
]

P = [
    {
        "题号": 17, "题型": "detailed_answer", "页码": [3], "类型": "figure",
        "原文": "\n".join([
            r"如图，在三棱锥 $S-ABC$ 中，底面 $ABC$ 是正三角形，中心为 $O$，$SC=AB=6$，$\overrightarrow{CD}=2\overrightarrow{DS}$．",
            r"（1）证明：$OD\parallel$ 平面 $ABS$；",
            r"（2）若 $SA=SB=2\sqrt{3}$，",
            r"（i）证明：平面 $SOC\perp$ 平面 $ABC$；",
            r"（ii）求平面 $SOA$ 与平面 $ABC$ 夹角的正切值．",
        ]),
        "说明": "\n".join([
            r"试卷第 3 页 #17 题干说「如图」，右侧配一幅三棱锥直观图，按「带图题不录正文」整条不进成品。",
            r"图上标注：顶点 $S$ 在上方；底面正三角形 $ABC$ 中 $A$ 在左、$B$ 在下偏左、$C$ 在右；",
            r"$D$ 标在侧棱 $SC$ 上、靠近 $S$ 一侧（与 $\overrightarrow{CD}=2\overrightarrow{DS}$ 即 $D$ 为 $SC$ 靠 $S$ 的三等分点相符）；",
            r"$O$ 标在底面内部、靠近 $AC$ 一侧。实线画出 $SA$、$SB$、$SC$、$AB$、$BC$、$OD$，",
            r"底面上的 $AC$ 与 $AO$、$OC$ 一带用虚线（被遮挡）。图上没有标长度数值。",
            r"参考答案及评分标准第 2—3 页给的是完整证明过程，没有独立答案行：",
            r"（1）取 $AB$ 中点 $E$，连结 $OE,SE$，由 $O$ 是正三角形 $ABC$ 的中心得 $\overrightarrow{CO}=2\overrightarrow{OE}$，因此 $OD\parallel SE$，",
            r"而 $OD\not\subset$ 平面 $ABS$，$SE\subset$ 平面 $ABS$，所以 $OD\parallel$ 平面 $ABS$；",
            r"（2）（i）由 $SA=SB$ 得 $SE\perp AB$，又 $CE\perp AB$，$SE\cap CE=E$，故 $AB\perp$ 平面 $SCE$，",
            r"而 $AB\subset$ 平面 $ABC$，因此平面 $SOC\perp$ 平面 $ABC$；",
            r"（ii）答案册给「方法一」建系（$E$ 为原点，$EB$ 为 $x$ 轴，$EC$ 为 $y$ 轴，平面 $ABC$ 法向量 $\overrightarrow{n_1}=(0,0,1)$，",
            r"$O\left(0,\sqrt{3},0\right)$、$A(-3,0,0)$、$C\left(0,3\sqrt{3},0\right)$、$S\left(0,-\dfrac{\sqrt{3}}{3},\dfrac{2\sqrt{6}}{3}\right)$，",
            r"取 $\overrightarrow{n_2}=\left(1,-\sqrt{3},-\sqrt{6}\right)$，$\left|\cos\left\langle\overrightarrow{n_1},\overrightarrow{n_2}\right\rangle\right|=\dfrac{\sqrt{15}}{5}$）",
            r"与「方法二」几何法，两种方法结论一致：平面 $SOA$ 与平面 $ABC$ 夹角的正切值为 $\dfrac{\sqrt{6}}{3}$。",
        ]),
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1], "类型": "print-suspect",
        "原文": r"已知函数 $f(x)=\begin{cases}e^x+2, & x<1\\ \ln x, & x>1\end{cases}$，则 $f(f(2))=$",
        "说明": "\n".join([
            r"疑在哪：试卷第 1 页 #3 的分段函数只印了两个分支条件「$x<1$」与「$x>1$」，$x=1$ 处没有给表达式，定义域缺一块。",
            r"为何没改：答案册第 1 页给的答案是 D，$f(f(2))$ 只用到 $x>1$（$f(2)=\ln 2$）与 $x<1$（$f(\ln 2)=e^{\ln 2}+2=4$）两支，",
            r"从卷面看不出原意是把某一支改成 $\leqslant$ 还是漏印了 $x=1$，任何补全都等于改内容，故照录原卷印文。",
        ]),
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3], "类型": "print-suspect",
        "原文": r"所以 $S_{\triangle ABP}=\dfrac{1}{2}d\cdot|AB|=\sqrt{6}$．",
        "说明": "\n".join([
            r"疑在哪：答案册第 2 页 #16（2）最后一行印作「所以 $S_{\triangle ABP}=\dfrac{1}{2}d\cdot|AB|=\sqrt{6}$」，",
            r"而题干（2）问的是 $\triangle OAB$ 的面积，上一行的 $d$ 也明确写成「原点 $O$ 到直线 $AB$ 的距离」，",
            r"且 $P(p,y_0)$ 是题干里抛物线上那个定点、并不在直线 $AB$ 上，所以这个下标 $P$ 应为 $O$。",
            r"为何没改：已把该行裁出放大到 $3.2$ 倍重读，卷面确实印的是斜体 $P$，属答案册排印笔误；",
            r"按「内容一个字都不许改」照录入成品「解析」字段，只在此登记，不代它订正。",
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

# 自查：控制符 / $ 配对 / 相邻 $$
bad = []
for r in Q + P:
    vals = []
    for k, v in r.items():
        if isinstance(v, str):
            vals.append((k, v))
        elif isinstance(v, dict):
            vals += [(k + "." + a, b) for a, b in v.items()]
    for k, s in vals:
        ctrl = [c for c in s if ord(c) < 32 and c != "\n"]
        if ctrl:
            bad.append((r["题号"], k, ctrl))
        if "$$" in s:
            bad.append((r["题号"], k, "adjacent $$"))
        if s.count("$") % 2:
            bad.append((r["题号"], k, "odd $"))
assert not bad, bad

(OUT / f"{STEM}.成品.json").write_text(
    json.dumps(Q, ensure_ascii=False, indent=1) + "\n", "utf-8")
(OUT / f"{STEM}.待复核.json").write_text(
    json.dumps(P, ensure_ascii=False, indent=1) + "\n", "utf-8")
print("成品", len(Q), "待复核", len(P))
