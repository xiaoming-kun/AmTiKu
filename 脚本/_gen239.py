import json, re, sys
from pathlib import Path

sys.path.insert(0, ".")
from amti.record2 import FIG_WORD, TABLE_WORD

OUT = Path("数据/录题/输出_v2")
NAME = "239_G12浙江名校协作体2026届高三下学期3月联考"

V = r"\overrightarrow"


def T(stem, *opts):
    return stem


Q = []


def rec(n, t, page, stem, opts, ans, sol):
    Q.append({
        "题号": n, "题型": t, "页码": page, "题干": stem, "选项": opts,
        "答案": ans, "解析": sol,
        "粗筛图": bool(FIG_WORD.search(stem)), "粗筛表": bool(TABLE_WORD.search(stem)),
    })


rec(1, "single_choice", [1],
    r"已知 $z=1+\sqrt{3}\mathrm{i}$，其中 $\mathrm{i}$ 为虚数单位，则 $z\cdot\overline{z}=$",
    {"A": r"$-2$", "B": r"$2$", "C": r"$-4$", "D": r"$4$"},
    "D", "解析无")

rec(2, "single_choice", [1],
    r"已知 $(1+2x)^4=a_0+a_1x+a_2x^2+a_3x^3+a_4x^4$，则 $a_3=$",
    {"A": r"$32$", "B": r"$16$", "C": r"$8$", "D": r"$4$"},
    "A", "解析无")

rec(3, "single_choice", [1],
    r"体积为 $\dfrac{32\pi}{3}$ 的球的表面积为",
    {"A": r"$4\pi$", "B": r"$8\pi$", "C": r"$16\pi$", "D": r"$32\pi$"},
    "C", "解析无")

rec(4, "single_choice", [1],
    r"已知向量 $\overrightarrow{a}=(x,2)$，$\overrightarrow{b}=(2,1)$，若 $(\overrightarrow{a}+2\overrightarrow{b})\perp\overrightarrow{b}$，则 $x=$",
    {"A": r"$-2$", "B": r"$2$", "C": r"$-6$", "D": r"$6$"},
    "C", "解析无")

rec(5, "single_choice", [1],
    r"已知双曲线 $\dfrac{x^2}{a^2}-\dfrac{y^2}{b^2}=1(a>0,b>0)$ 的左焦点为 $F$，$B$ 为虚轴端点，直线 $FB$ 与渐近线 $y=-\dfrac{b}{a}x$ 交于点 $P$，若 $\overrightarrow{FP}=2\overrightarrow{PB}$，则该双曲线的离心率是",
    {"A": r"$\dfrac{3}{2}$", "B": r"$2$", "C": r"$\dfrac{5}{2}$", "D": r"$3$"},
    "B", "解析无")

rec(6, "single_choice", [1],
    r"已知函数 $f(x)=\sin^2\left(\dfrac{\omega x}{2}+\dfrac{\pi}{4}\right)(\omega>0)$ 在区间 $\left[-\dfrac{\pi}{2},\dfrac{2\pi}{3}\right]$ 上单调递增，则 $\omega$ 取值范围为",
    {"A": r"$\left(0,\dfrac{3}{4}\right]$", "B": r"$(0,1]$",
     "C": r"$\left[\dfrac{3}{4},1\right]$", "D": r"$[1,+\infty)$"},
    "A", "解析无")

rec(7, "single_choice", [1],
    r"已知数列 $\{a_n\}$ 满足 $\dfrac{2}{a_1a_2}+\dfrac{2^2}{a_2a_3}+\cdots+\dfrac{2^n}{a_na_{n+1}}+\dfrac{1}{a_{n+1}}=1(n\in\mathbf{N}^*)$，且 $a_3=6$，则",
    {"A": r"$a_2=2a_1$", "B": r"$a_1=2a_2$", "C": r"$a_1=7a_4$", "D": r"$a_4=7a_1$"},
    "D", "解析无")

rec(8, "single_choice", [2],
    r"若曲线族（具有某种共同性质的所有曲线的集合）满足条件：存在直线 $l$，使得曲线族中存在无数个点在该直线上，称该曲线族是“完美的”，下列曲线族是“完美的”是",
    {"A": r"$(x-a)^2+(y-a^2)^2=\dfrac{a^2}{2}(a\in\mathbf{N}^*)$",
     "B": r"$(x-a^2)^2+(y-a)^2=\dfrac{a}{2}(a\in\mathbf{N}^*)$",
     "C": r"$(x-a)^2+(y-\sqrt{a})^2=\dfrac{a^2}{2}(a\in\mathbf{N}^*)$",
     "D": r"$(x-\sqrt{a})^2+(y-a)^2=\dfrac{a}{2}(a\in\mathbf{N}^*)$"},
    "C", "解析无")

rec(10, "multi_choice", [2],
    r"在正三棱柱 $ABC-A_1B_1C_1$ 中，$AB=AA_1=1$，点 $P$ 满足 $\overrightarrow{AP}=x\overrightarrow{AB}+y\overrightarrow{AC}+z\overrightarrow{AA_1}$，$x,y,z\in[0,1]$，则",
    {"A": r"当 $x=y=z=\dfrac{1}{2}$ 时，$\left|\overrightarrow{AP}\right|=1$",
     "B": r"当 $x+y+z=1$ 时，$AP$ 与 $BB_1$ 异面",
     "C": r"若 $BC\perp$ 面 $APA_1$，则 $x=y$",
     "D": r"若点 $P$ 在平面 $BA_1C_1$ 内，则 $x+z=1$"},
    "ACD", "解析无")

rec(11, "multi_choice", [2, 3],
    r"已知集合 $A=\{a_1,a_2,\cdots,a_n\}(n\geq3)$，其中 $a_1<a_2<a_3<\cdots<a_n$，且 $a_i\in\mathbf{N}^*$，$i=1,2,\cdots,n$，定义 $A$ 的和集 $A+A=\{a_i+a_j|a_i,a_j\in A\}$，则",
    {"A": r"若 $\{a_n\}$ 是等差数列，则 $A+A$ 的元素个数为 $2n-1$",
     "B": r"若 $\{a_n\}$ 是等比数列，则 $A+A$ 的元素个数为 $\dfrac{n^2+n}{2}$",
     "C": r"若 $A+A$ 的元素个数为 $2n-1$，则 $\{a_n\}$ 是等差数列",
     "D": r"若 $A+A$ 的元素个数为 $\dfrac{n^2+n}{2}$，则 $\{a_n\}$ 是等比数列"},
    "ABC", "解析无")

rec(12, "fill_in_blank", [3],
    r"曲线 $y=\dfrac{1}{2}x^2+\ln x$ 在点 $\left(1,\dfrac{1}{2}\right)$ 处的切线方程为________．",
    {}, r"$y=2x-\dfrac{3}{2}$", "解析无")

rec(13, "fill_in_blank", [3],
    r"已知 $\theta\in\left(0,\dfrac{\pi}{2}\right)$，$\tan\left(\dfrac{\pi}{4}-\theta\right)=\dfrac{3}{2}\tan\theta$，则 $\sin2\theta$ 的值为________．",
    {}, r"$\dfrac{3}{5}$", "解析无")

rec(14, "fill_in_blank", [3],
    r"某校数学教师命制一张试卷，试卷要求考查函数、几何、概率统计三个板块内容，其中函数题 $3$ 道、几何题 $2$ 道、概率统计题 $2$ 道，且同板块试题难度互不相同．现要求同一板块的试题不相邻且难度从易到难，则该试卷不同的排版方案有________种（用数字作答）．",
    {}, r"$38$", "解析无")

rec(15, "detailed_answer", [3],
    "\n".join([
        r"已知公差不为零的等差数列 $\{a_n\}$ 的前 $5$ 项和为 $35$，且 $a_1,a_2,a_6$ 成等比数列．",
        r"(1) 求数列 $\{a_n\}$ 的通项公式；",
        r"(2) 数列 $\{b_n\}$ 满足 $b_n=\dfrac{1}{a_na_{n+1}}$，求证：$b_1+b_2+\cdots+b_n<\dfrac{1}{3}$．",
    ]),
    {},
    "\n".join([
        r"(1) $a_n=3n-2$；",
        r"(2) $b_1+b_2+\cdots+b_n<\dfrac{1}{3}$",
    ]),
    "\n".join([
        r"(1) 设数列 $\{a_n\}$ 的通项公式为 $a_n=a_1+(n-1)d,d\neq0$，由 $a_1+a_2+\cdots+a_5=5a_3=5(a_1+2d)=35$，故 $a_1+2d=7$；又 $a_1,a_2,a_6$ 成等比数列，故 $(a_1+d)^2=a_1(a_1+5d)$，解得 $d^2=3a_1d$，因为 $d\neq0$，故 $d=3a_1$ 代入 $a_1+2d=7$ 可得 $a_1=1,d=3$，故 $a_n=3n-2$．",
        r"(2) $b_n=\dfrac{1}{a_na_{n+1}}=\dfrac{1}{(3n-2)(3n+1)}=\dfrac{1}{3}\left(\dfrac{1}{3n-2}-\dfrac{1}{3n+1}\right)$，故 $b_1+b_2+\cdots+b_n=\dfrac{1}{3}\left(1-\dfrac{1}{4}+\dfrac{1}{4}-\dfrac{1}{7}+\cdots+\dfrac{1}{3n-2}-\dfrac{1}{3n+1}\right)=\dfrac{1}{3}\left(1-\dfrac{1}{3n+1}\right)<\dfrac{1}{3}$．",
    ]))

rec(16, "detailed_answer", [3],
    "\n".join([
        r"已知锐角 $\triangle ABC$ 中，角 $A,B,C$ 的对边分别为 $a,b,c$，且 $\sin2B=\dfrac{1}{2}b\cdot\cos B$，$a=2\sqrt{3}$．",
        r"(1) 求 $A$；",
        r"(2) 在以下三个条件中选择一个作为已知，求 $b$．",
        r"①$\triangle ABC$ 面积为 $3\sqrt{3}$；②$BC$ 边上的的中线长为 $3$；③$b,a,c$ 成等差数列．",
    ]),
    {},
    "\n".join([
        r"(1) $A=\dfrac{\pi}{3}$；",
        r"(2) 选择①②③中任一条件，均得 $b=2\sqrt{3}$",
    ]),
    "\n".join([
        r"(1) 由 $\sin2B=\dfrac{1}{2}b\cdot\cos B$，$2\sin B\cos B=\dfrac{1}{2}b\cdot\cos B$，由于 $\triangle ABC$ 是锐角三角形，故 $\dfrac{b}{\sin B}=4$，由正弦定理 $\dfrac{a}{\sin A}=\dfrac{b}{\sin B}$，故 $A=\dfrac{\pi}{3}$．",
        r"(2) 由余弦定理 $a^2=b^2+c^2-2bc\cos A$，得到 $12=b^2+c^2-bc$．",
        r"选择①$\triangle ABC$ 面积为 $3\sqrt{3}$：$S=\dfrac{1}{2}bc\sin\dfrac{\pi}{3}=3\sqrt{3}$，$bc=12$，又由于 $12=b^2+c^2-bc$，得 $b=2\sqrt{3}$．",
        r"选择②$BC$ 的中线 $AE$ 长为 $3$：$\overrightarrow{AE}=\dfrac{1}{2}\left(\overrightarrow{AB}+\overrightarrow{AC}\right)$，$b^2+c^2+bc=36$，又由于 $12=b^2+c^2-bc$，得 $b=2\sqrt{3}$．",
        r"选择③$b,a,c$ 成等差数列：$b+c=4\sqrt{3}$，又由于 $12=b^2+c^2-bc$，得 $b=2\sqrt{3}$．",
    ]))

rec(19, "detailed_answer", [4],
    "\n".join([
        r"已知 $a,b$ 是实数，函数 $f(x)=e^{ax}+bx-\dfrac{\sqrt{e}}{2}$，其中 $e$ 是自然对数的底数．",
        r"(1) 当 $a=1$ 时，讨论 $f(x)$ 的单调区间；",
        r"(2) 若对任意的 $b<-\sqrt{e}$，$f(x)$ 均有极小值点 $x_0$，且 $f(x_0)<0$，求实数 $a$ 的取值范围；",
        r"(3) 若方程 $f(x)=\dfrac{\sqrt{e}}{2}$ 有两个根 $x_1,x_2(x_1<x_2)$，当 $|ax_1-ax_2|$ 取最小值时，求 $\dfrac{b}{a}$ 的值．",
    ]),
    {},
    "\n".join([
        r"(1) 当 $b\geq0$ 时 $f(x)$ 单调递增；当 $b<0$ 时，$f(x)$ 在 $(-\infty,\ln(-b))$ 单调递减，在 $(\ln(-b),+\infty)$ 单调递增；",
        r"(2) $0<a\leq1$；",
        r"(3) $\dfrac{b}{a}=-\sqrt{e}$",
    ]),
    "\n".join([
        r"(1) $f'(x)=e^x+b$，当 $b\geq0$ 时，$f'(x)>0$，故 $f(x)$ 单调递增；当 $b<0$ 时，令 $f'(x)=0\Leftrightarrow e^x+b=0$，解得 $x=\ln(-b)$，故 $f(x)$ 在 $(-\infty,\ln(-b))$ 单调递减，在 $(\ln(-b),+\infty)$ 单调递增．",
        r"(2) 当 $b<-\sqrt{e}$ 时，当 $a\leq0$ 时，$f'(x)=ae^{ax}+b<0$，故 $f(x)$ 单调递减，故 $f(x)$ 不可能有极小值点；当 $a>0$ 时，$f(x)$ 在 $\left(-\infty,\dfrac{1}{a}\ln\left(\dfrac{-b}{a}\right)\right)$ 单调递减，在 $\left(\dfrac{1}{a}\ln\left(\dfrac{-b}{a}\right),+\infty\right)$ 单调递增．因此 $f(x)$ 均有极小值点 $x_0=\dfrac{1}{a}\ln\left(\dfrac{-b}{a}\right)$，且 $f\left(\dfrac{1}{a}\ln\left(\dfrac{-b}{a}\right)\right)<0$，$f\left(\dfrac{1}{a}\ln\left(\dfrac{-b}{a}\right)\right)=e^{\ln\left(\frac{-b}{a}\right)}+\dfrac{b}{a}\ln\left(\dfrac{-b}{a}\right)-\dfrac{\sqrt{e}}{2}=\dfrac{-b}{a}+\dfrac{b}{a}\ln\left(\dfrac{-b}{a}\right)-\dfrac{\sqrt{e}}{2}<0$，令 $t=\dfrac{-b}{a}\in\left(\dfrac{\sqrt{e}}{a},+\infty\right)$，故对任意的 $t\in\left(\dfrac{\sqrt{e}}{a},+\infty\right)$，$g(t)=t-t\ln t-\dfrac{\sqrt{e}}{2}<0$．$g'(t)=-\ln t$，故 $g(t)$ 在 $(0,1)$ 上单调递增，在 $(1,+\infty)$ 单调递减，$g(1)=1-\dfrac{\sqrt{e}}{2}>0$，$g(\sqrt{e})=0$，且 $x\to0$ 时，$g(t)\to-\dfrac{\sqrt{e}}{2}$；$x\to+\infty$ 时，$g(t)\to-\infty$；$g(t)$ 的图像如右图，故 $\dfrac{\sqrt{e}}{a}\geq\sqrt{e}$ 恒成立，故 $0<a\leq1$．",
        r"(3) 方程 $f(x)=\dfrac{\sqrt{e}}{2}$ 有两个根 $x_1,x_2(x_1<x_2)$，由（2）可知 $a>0$，否则 $f(x)$ 单调，不可能有两个根，方程 $f(x)=\dfrac{\sqrt{e}}{2}$ 有两个根 $x_1,x_2(x_1<x_2)$ 等价于 $e^{ax}+bx=\sqrt{e}$ 有两个根 $x_1,x_2(x_1<x_2)$，令 $F(x)=e^{ax}+bx-\sqrt{e}$，由 $F(0)=1-\sqrt{e}<0$；当 $x\to-\infty$，$F(x)\to+\infty$；当 $x\to+\infty$，$F(x)\to+\infty$，故可知 $x_1<0<x_2$．记 $s=ax$，上式等价于 $e^s+\dfrac{b}{a}s=\sqrt{e}$ 有两个根 $s_1,s_2(s_1<0<s_2)$，$\begin{cases}e^{s_1}+\dfrac{b}{a}s_1=\sqrt{e},\\ e^{s_2}+\dfrac{b}{a}s_2=\sqrt{e},\end{cases}$ 两式相减可得 $e^{s_1}(e^{s_2-s_1}-1)+\dfrac{b}{a}(s_2-s_1)=0$，记 $\Delta s=s_2-s_1>0$，故上式可写成 $e^{s_1}(e^{\Delta s}-1)+\dfrac{b}{a}\Delta s=0$，故 $\dfrac{e^{\Delta s}-1}{\Delta s}=-\dfrac{b}{ae^{s_1}}$（*），又 $\dfrac{b}{a}=-\dfrac{e^{s_1}-\sqrt{e}}{s_1}$ 代入（*）得 $\dfrac{e^{\Delta s}-1}{\Delta s}=\dfrac{e^{s_1}-\sqrt{e}}{s_1e^{s_1}}$，令 $h(s)=\dfrac{e^s-1}{s}(s>0)$，$k(s)=\dfrac{e^s-\sqrt{e}}{se^s}(s<0)$，故 $h'(s)=\dfrac{(s-1)e^s+1}{s^2}$，令 $w(s)=(s-1)e^s+1$，$w'(s)=se^s>0$，故 $w(s)>w(0)=0$，故 $h(s)$ 是单调递增，要求 $\Delta s$ 的最小值，就是求 $h(s)$ 的最小值．下面考虑 $k(s)$ 的最小值．$k'(s)=\dfrac{-e^s+\sqrt{e}(x+1)}{s^2e^s}$，令 $p(s)=-e^s+\sqrt{e}(x+1)$，$p'(s)=-e^s+\sqrt{e}$，当 $s<\dfrac{1}{2}$ 时，$p'(s)>0$，$p(s)$ 单调递增；当 $s>\dfrac{1}{2}$ 时，$p'(s)<0$，$p(s)$ 单调递减；$p\left(\dfrac{1}{2}\right)=\dfrac{\sqrt{e}}{2}$，$p(-1)=-\dfrac{1}{e}$（$p(s)$ 的图像如右图所示）故存在 $s_0\in(-1,0)$ 使得 $p(s_0)=0$，即 $-e^{s_0}+\sqrt{e}(s_0+1)=0$，所以 $s\in(-\infty,s_0)$ 时，$k'(s)<0$，$k(s)$ 单调递减；$s\in(s_0,0)$ 时，$k'(s)>0$，$k(s)$ 单调递增；故 $k(s)\geq k(s_0)$，即 $s=s_0$ 时，$k(s)$ 取最小值．故 $\dfrac{b}{a}=-\dfrac{e^{s_0}-\sqrt{e}}{s_0}=-\sqrt{e}$．",
    ]))

# ---------------- 待复核 ----------------
R = []


def pd(n, t, page, kind, raw, note):
    R.append({"题号": n, "题型": t, "页码": page, "类型": kind, "原文": raw, "说明": note})


pd(9, "multi_choice", [2], "table",
   "\n".join([
       r"为测试一种新研发药物的有效性，研究人员对某种动物种群进行试验，从该试验种群中随机抽查了 $100$ 只，得到如下数据（单位：只）：",
       r"$\begin{array}{|c|c|c|c|}\hline & 发病 & 未发病 & 合计\\\hline 使用药物 & 5 & 45 & 50\\\hline 未使用药物 & 25 & 25 & 50\\\hline 合计 & 30 & 70 & 100\\\hline\end{array}$",
       r"从该动物种群中任取 $1$ 只，记事件 $A$ 表示此动物发病，事件 $B$ 表示此动物使用药物，定义 $A$ 的权值 $R_1=\dfrac{P(A)}{1-P(A)}$，在 $B$ 发生的条件下 $A$ 的权值 $R_2=\dfrac{P(A|B)}{1-P(A|B)}$，则",
       r"A. $R_1$ 的估值为 $\dfrac{3}{7}$，$R_2$ 的估值为 $\dfrac{1}{9}$　B. $R_1$ 的估值为 $\dfrac{3}{7}$，$R_2$ 的估值为 $\dfrac{1}{10}$",
       r"C. $\dfrac{R_2}{R_1}$ 可化为 $\dfrac{P(B|A)}{P(B|\overline{A})}$　D. $\dfrac{R_2}{R_1}$ 可化为 $\dfrac{P(A|B)}{P(A|\overline{B})}$",
   ]),
   "试卷第 2 页 #9 题干中间印一张列联表（$4$ 行 $4$ 列，含合计行与合计列）：表头自第二列起为「发病」「未发病」「合计」；「使用药物」一行依次为 $5$、$45$、$50$；「未使用药物」一行依次为 $25$、$25$、$50$；「合计」一行依次为 $30$、$70$、$100$。四个选项全部要由这张表算出（$R_1$、$R_2$ 的估值与两个比值化简），按规矩不录正文。答案册第 1 页只有答案表，对本题**没有任何解析**。答案 $AC$。")

pd(17, "detailed_answer", [3], "figure",
   "\n".join([
       r"如图，在三棱锥 $P-ABC$ 中，$D$ 是棱 $AB$ 的中点，$PA=\sqrt{2},PC=2,\triangle ABC$ 是边长为 $2$ 的正三角形，平面 $ABC\perp$ 平面 $PAB$．",
       r"(1) 证明：$PD\perp AB$；",
       r"(2) 点 $E$ 满足 $\overrightarrow{DE}=\lambda\overrightarrow{CP}(0<\lambda<1)$，且 $BC//$ 平面 $PAE$，",
       r"(i) 求 $\lambda$ 的值；(ii) 求直线 $CE$ 与平面 $PAE$ 所成角的正弦值．",
   ]),
   r"试卷第 3 页 #17 题干右下方印一幅三棱锥直观图：图上标出 $P$（顶点）、$A$（右下）、$B$（图内偏左）、$C$（左下）、$D$（底边靠中）、$E$（$P$ 的右下方）六个点，实线表示可见棱、虚线表示被遮的棱。题干自带「如图」，按规矩不录正文。答案册第 2–3 页给了完整解答（含综合法与坐标法两种）：(1) 由正三角形得 $CD\perp AB$、$CD=\sqrt{3}$，又面 $ABC\perp$ 面 $PAB$ 得 $CD\perp$ 面 $PAB$，故 $CD\perp PD$，由 $CD=\sqrt{3},PC=2$ 得 $PD=1$，再由 $PD^2+AD^2=PA^2$ 得 $PD\perp AB$；(2)(i) $\lambda=\dfrac{1}{2}$；(ii) 直线 $CE$ 与平面 $PAE$ 所成角的正弦值为 $\dfrac{2\sqrt{3}}{7}$。坐标法里建系取 $D$ 为原点、$DC,DA,DP$ 为 $x,y,z$ 轴，$A(0,1,0),B(0,-1,0),C(\sqrt{3},0,0),P(0,0,1)$，面 $PAE$ 的法向量 $\overrightarrow{n}=\left(-\dfrac{1}{2},\dfrac{\sqrt{3}}{2},\dfrac{\sqrt{3}}{2}\right)$。")

pd(18, "detailed_answer", [4], "figure",
   "\n".join([
       r"已知椭圆 $C:\dfrac{4}{3}x^2+2y^2=1$，动点 $P(x_0,y_0)$ 在抛物线 $y^2=x+1$ 上，过点 $P$ 作椭圆的两条切线分别交抛物线于不同的两点 $A(x_1,y_1),B(x_2,y_2)$．",
       r"(1) 求椭圆 $C$ 的焦距；",
       r"(2) 若切线 $AP$ 与椭圆的切点恰好是 $AP$ 的中点，求直线 $AP$ 的方程；",
       r"(3) 证明：直线 $AB$ 经过定点，并写出定点坐标．",
   ]),
   r"试卷第 4 页 #18 题干下方印一幅配图：直角坐标系（标 $x$、$y$、$O$）里画一个中心在原点、长轴在 $x$ 轴上的椭圆，与一条开口向右的抛物线；抛物线上第一象限一点 $P$ 向椭圆引两条切线，一条交抛物线于第二象限的点 $A$，另一条交抛物线于第四象限的点 $B$。题干本身没有「如图」二字、粗筛词表抓不到，是逐页看图发现的，按带图题规矩不录正文。答案册第 3–4 页给了完整解答：(1) 由题意 $a^2=\dfrac{3}{4},b^2=\dfrac{1}{2}$，$\therefore c^2=\dfrac{1}{4},c=\dfrac{1}{2}$，焦距 $2c=1$；(2) 设直线 $AP:x=my+n$、切点为 $E$，由 $\Delta=0$ 得 $4n^2=2m^2+3$，则 $y_E=-\dfrac{m}{2n}$，又由 $y^2=x+1$ 得 $y_E=\dfrac{m}{2}$，$\therefore$ 直线 $AP$ 的方程为 $x=\pm\dfrac{\sqrt{2}}{2}y-1$ 或 $x=\pm\dfrac{\sqrt{3}}{2}$（此处印文符号疑点另立一条 print-suspect）；(3) 由 $k_{AP}=\dfrac{1}{y_0+y_1}$ 得直线 $AP:x+1-(y_0+y_1)y+y_0y_1=0$，与椭圆联立由相切得 $(2-4y_0^2)y_1^2-4y_0y_1+2y_0^2-1=0$，同理 $y_1,y_2$ 是关于 $y$ 的方程 $(2-4y_0^2)y^2-4y_0y+2y_0^2-1=0$ 的两根，韦达定理得 $y_1y_2=-\dfrac{1}{2}$，故直线 $AB:x-(y_1+y_2)y+\dfrac{1}{2}=0$，即直线 $AB$ 经过定点 $\left(-\dfrac{1}{2},0\right)$。")

pd(18, "detailed_answer", [4], "print-suspect",
   r"$\therefore-\dfrac{m}{2n}=\dfrac{m}{2},\therefore n=1,m=\pm\dfrac{\sqrt{2}}{2}$ 或 $m=0,n=\pm\dfrac{\sqrt{3}}{2}$，$\therefore$ 直线 $AP$ 的方程为 $x=\pm\dfrac{\sqrt{2}}{2}y-1$ 或 $x=\pm\dfrac{\sqrt{3}}{2}$",
   r"答案册第 3 页 #18(2) 自相矛盾：由 $-\dfrac{m}{2n}=\dfrac{m}{2}$ 解得印作 $n=1$，但同一行紧接着写出的直线方程是 $x=\pm\dfrac{\sqrt{2}}{2}y-1$，把 $n=1$ 代回 $x=my+n$ 应得 $x=\pm\dfrac{\sqrt{2}}{2}y+1$；只有按 $n=-1$ 才与后文一致（且 $n=-1$ 同样满足前一行 $4n^2=2m^2+3$，代回 $4x^2+6y^2=3$ 判别式亦为 $0$、切点纵坐标 $-\dfrac{m}{2n}=\dfrac{m}{2}$ 成立）。已用 450dpi 裁图逐字核对，答案册确实印的是 $n=1$，不是看错。因本题按带图题不录正文，此处**照录原印文未作任何改动**，疑点只登记在待复核，请人工定夺。")

pd(16, "detailed_answer", [3], "print-suspect",
   r"②$BC$ 边上的的中线长为 $3$",
   "试卷第 3 页 #16(2) 条件②印作「$BC$ 边上的的中线长为 $3$」，「的」字重复，疑为「$BC$ 边上的中线长为 $3$」。按原卷照录未改。答案册第 2 页该处印作「选择②$BC$ 的中线 $AE$ 长为 $3$」，语义一致，不影响解题与答案。")

pd(19, "detailed_answer", [4], "print-suspect",
   r"且 $x\to0$ 时，$g(t)\to-\dfrac{\sqrt{e}}{2}$；$x\to+\infty$ 时，$g(t)\to-\infty$；$g(t)$ 的图像如右图，$k'(s)=\dfrac{-e^s+\sqrt{e}(x+1)}{s^2e^s}$，令 $p(s)=-e^s+\sqrt{e}(x+1)$",
   r"答案册第 4–5 页 #19 解析里有两处把函数自变量印成 $x$、而上下文用的是 $t$ 与 $s$：①「且 $x\to0$ 时，$g(t)\to-\dfrac{\sqrt{e}}{2}$；$x\to+\infty$ 时，$g(t)\to-\infty$」，前文 $g$ 的自变量是 $t\in\left(\dfrac{\sqrt{e}}{a},+\infty\right)$；②「$k'(s)=\dfrac{-e^s+\sqrt{e}(x+1)}{s^2e^s}$，令 $p(s)=-e^s+\sqrt{e}(x+1)$」，而答案册第 6 页紧接着写「$p\left(\dfrac{1}{2}\right)=\dfrac{\sqrt{e}}{2}$，$p(-1)=-\dfrac{1}{e}$，即 $-e^{s_0}+\sqrt{e}(s_0+1)=0$」，同一处印成 $s+1$。按 $s$ 读数值才自洽（$p\left(\dfrac{1}{2}\right)=-\sqrt{e}+\dfrac{3}{2}\sqrt{e}=\dfrac{\sqrt{e}}{2}$、$p(-1)=-e^{-1}+0=-\dfrac{1}{e}$）。成品解析按答案册印文逐字照录，未作订正。")

pd(19, "detailed_answer", [4], "figure-in-solution",
   r"$g(t)=t-t\ln t-\dfrac{\sqrt{e}}{2}<0$ …… $g(t)$ 的图像如右图",
   r"答案册第 4 页右下角印 $g(t)=t-t\ln t-\dfrac{\sqrt{e}}{2}$ 的图像一幅：方格网坐标系，横轴标 $0$、$1$、$2$、$3$，纵轴标 $1$、$-1$；曲线自 $t\to0^+$ 处（纵坐标趋 $-\dfrac{\sqrt{e}}{2}$）上升，在 $t=1$ 处取极大值 $1-\dfrac{\sqrt{e}}{2}>0$，随后下降、约在 $t=\sqrt{e}$ 处穿过横轴。本题题干为纯文字、正文已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

pd(19, "detailed_answer", [6], "figure-in-solution",
   r"$p(s)=-e^s+\sqrt{e}(s+1)$ ……（$p(s)$ 的图像如右图所示）",
   r"答案册第 6 页右上方印 $p(s)$ 的图像一幅：方格网坐标系，横轴标 $-2$、$-1$、$0$、$1$、$2$，纵轴标 $1$、$-1$；曲线先升后降，在 $s=\dfrac{1}{2}$ 处取最大值 $\dfrac{\sqrt{e}}{2}$，与横轴两交点分别落在 $(-1,0)$ 内与 $1$ 右侧。本题题干为纯文字、正文已照录入成品，此条仅登记解析配图，未据图增删任何文字。")

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
    if re.search(r"_{\{[^}]*[一-鿿]", s) and r"\\text" not in s:
        bad.append(("cn-subscript", n, k))
    if [c for c in s if ord(c) < 32 and c != "\n"]:
        bad.append(("ctrl", n, k))
for r in R:
    for k in ("原文", "说明"):
        r[k] = r[k].replace(r"\\n", "\n")
        if re.search(r"\\n(?![a-zA-Z])", r[k]):
            bad.append(("literal-n-pending", r["题号"], k))
        if [c for c in r[k] if ord(c) < 32 and c != "\n"]:
            bad.append(("ctrl-pending", r["题号"], k))
for r in Q:
    for k in ("解析", "题干"):
        if "见待复核" in r[k] or "答案册" in r[k]:
            bad.append(("self-note-in-body", r["题号"], k))
assert not bad, bad

Q.sort(key=lambda x: x["题号"])
(OUT / f"{NAME}.成品.json").write_text(json.dumps(Q, ensure_ascii=False, indent=1) + "\n", "utf-8")
(OUT / f"{NAME}.待复核.json").write_text(json.dumps(R, ensure_ascii=False, indent=1) + "\n", "utf-8")
print("成品", len(Q), "待复核", len(R), "题号", [r["题号"] for r in Q])
