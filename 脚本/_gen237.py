#!/usr/bin/env python3
r"""生成 #237 广东梅州市2026届高三下学期3月总复习质检 的成品 + 待复核。

所有含反斜杠的正文一律用 r"..."，防止 \v/\f/\b/\a/\e/\r 被 Python 当转义吃掉。
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "数据/录题/输出_v2"
NO = 237
NAME = "广东梅州市2026届高三下学期3月总复习质检"

recs = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1],
        "题干": r"在复平面内，复数 $(1+\mathrm{i})(m-2\mathrm{i})$ 对应的点在第三象限，则实数 $m$ 的取值范围是",
        "选项": {
            "A": r"$(-\infty,-2)$",
            "B": r"$(-2,0)$",
            "C": r"$(0,2)$",
            "D": r"$(2,+\infty)$",
        },
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1],
        "题干": r"已知 $\{a_n\}$ 为等差数列，$a_3=2$，$a_4=6$，则 $a_5+a_6=$",
        "选项": {"A": r"$36$", "B": r"$24$", "C": r"$18$", "D": r"$12$"},
        "答案": "B", "解析": "解析无",
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1],
        "题干": r"为督导学生体育锻炼，某中学举行一分钟跳绳测试，其成绩 $X$（单位：次）近似服从正态分布 $N(160,\sigma^2)$，且 $P(120<X<160)=0.45$，则该校 $2000$ 名学生中约有（ ）人一分钟跳绳超过 $200$ 次．",
        "选项": {"A": r"$100$", "B": r"$150$", "C": r"$200$", "D": r"$250$"},
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [2],
        "题干": r"已知全集 $U=A\cup B=\{1,2,3,4,5\}$，$A\cap(\complement_U B)=\{2,4\}$，则下列结论不一定成立的是",
        "选项": {
            "A": r"$\{2,4\}\subseteq A$",
            "B": r"$(\complement_U A)\subseteq B$",
            "C": r"$\{1,3,5\}\subseteq B$",
            "D": r"$\{1,3\}\subseteq\complement_U A$",
        },
        "答案": "D", "解析": "解析无",
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [2],
        "题干": r"已知椭圆 $C:\dfrac{x^2}{9}+\dfrac{y^2}{m}=1$ 与双曲线 $\Gamma:x^2-\dfrac{y^2}{m}=1$ 有着公共的焦点 $F_1$、$F_2$，椭圆 $C$ 与双曲线 $\Gamma$ 的一个交点为 $Q$，则 $\triangle F_1QF_2$ 的面积为",
        "选项": {"A": r"$3$", "B": r"$4$", "C": r"$5$", "D": r"$6$"},
        "答案": "B", "解析": "解析无",
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [2],
        "题干": r"甲乙两人下棋比赛，规则是谁先赢 2 局，谁便赢得奖金 $5400$ 元．根据以往的交手记录，每局甲赢的概率为 $\dfrac{2}{3}$，乙赢的概率为 $\dfrac{1}{3}$，且每局比赛相互独立．然而因突发事件，比赛未能举行，为公平服众，奖金按照比赛正常进行时各自赢得比赛的概率之比进行分配，则甲分得奖金（ ）元．",
        "选项": {"A": r"$3600$", "B": r"$3800$", "C": r"$4000$", "D": r"$4200$"},
        "答案": "C", "解析": "解析无",
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [2],
        "题干": r"某个弹簧振子在振动过程中的位移 $y$（单位：$\mathrm{cm}$）与时间 $t$（单位：$\mathrm{s}$）之间的关系为 $y=10\sin\dfrac{\pi}{2}t$，则当位移 $y=6\mathrm{cm}$ 时，弹簧振子的瞬时速度大小为（ ）$\mathrm{cm/s}$．",
        "选项": {"A": r"$4\pi$", "B": r"$5\pi$", "C": r"$6\pi$", "D": r"$8\pi$"},
        "答案": "A", "解析": "解析无",
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [2],
        "题干": r"已知实数 $a$ 和 $b$（其中 $b>1$）满足方程：$\dfrac{1}{e^a}+2\ln b=a+\dfrac{1}{b}$，则下列不等式成立的是",
        "选项": {
            "A": r"$e^a>b^2$",
            "B": r"$a^2>e^b$",
            "C": r"$a>2b$",
            "D": r"$a>\ln b$",
        },
        "答案": "D", "解析": "解析无",
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [4],
        "题干": r"关于函数 $f(x)=\sin x\cdot\sin 3x$，以下结论正确的有（ ）",
        "选项": {
            "A": r"$f(x)$ 是轴对称图形",
            "B": r"$f(x)$ 的最大值为 $1$",
            "C": r"$f(x)$ 是以 $\pi$ 为一个周期的周期函数",
            "D": r"$f(x)$ 在 $[0,\pi]$ 上有 $4$ 个零点",
        },
        "答案": "ACD", "解析": "解析无",
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [4],
        "题干": r"已知某趟往返梅州与广州的高铁，沿途共有梅州西、兴宁南、五华、河源东、惠州北、广州等 $6$ 个站点，则此趟高铁沿途需要准备________种不同的车票．",
        "选项": {},
        "答案": r"$30$", "解析": "解析无",
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [4],
        "题干": r"在平面直角坐标系 $xOy$ 中，点 $P$ 的坐标为 $(-1,1)$，点 $Q$ 为圆 $C:(x-2)^2+y^2=2$ 上的动点，则 $\overrightarrow{OP}\cdot\overrightarrow{OQ}$ 的最小值为________．",
        "选项": {},
        "答案": r"$-4$", "解析": "解析无",
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [4],
        "题干": r"数列扩充是指在一个有穷数列中按一定规则插入一些项得到一个新的数列．初始数列 $\left\{a_k^{(0)}\right\}$ 经过 $n$ 次扩充后的新数列记为 $\left\{a_k^{(n)}\right\}$，项数记为 $P_n$，所有项的和记为 $S_n$．现若扩充规则为每相邻两项之间插入这两项的和，如：数列 $\{a,b,c\}$ 经过一次扩充后得到数列 $\left\{a_k^{(1)}\right\}=\{a,a+b,b,b+c,c\}$，$P_1=5$，$S_1=2a+3b+2c$．已知初始数列 $\left\{a_k^{(0)}\right\}=\{-3,1,3\}$，则 $P_n=$\fillin[]；$S_n=$\fillin[]．",
        "选项": {},
        "答案": r"$P_n=2^n+1$；$S_n=3^n$",
        "解析": "解析无",
    },
    {
        "题号": 17, "题型": "detailed_answer", "页码": [5],
        "题干": r"在 $\triangle ABC$ 中，角 $A,B,C$ 所对的边分别为 $a,b,c$，已知 $b=\dfrac{\sqrt{3}}{3}c\sin A+a\cos C$ ．"
        + "\n" + r"(1) 求角 $A$ 的大小；"
        + "\n" + r"(2) 若 $D$ 为边 $BC$ 上一点，满足 $BD=2CD$，且 $AD=2$，求 $\triangle ABC$ 的面积最大值．",
        "选项": {},
        "答案": r"(1) $A=\dfrac{\pi}{3}$；(2) $\triangle ABC$ 的面积最大值为 $\dfrac{3\sqrt{3}}{2}$",
        "解析": r"(1) 因为 $b=\dfrac{\sqrt{3}}{3}c\sin A+a\cos C$，由正弦定理，得：$2R\sin B=\dfrac{\sqrt{3}}{3}2R\sin C\sin A+2R\sin A\cos C$，所以 $\sin B=\dfrac{\sqrt{3}}{3}\sin C\sin A+\sin A\cos C$，而 $B=\pi-(A+C)$，即有 $\sin(A+C)=\dfrac{\sqrt{3}}{3}\sin C\sin A+\sin A\cos C$，所以 $\sin A\cos C+\cos A\sin C=\dfrac{\sqrt{3}}{3}\sin C\sin A+\sin A\cos C$，所以 $\cos A\sin C=\dfrac{\sqrt{3}}{3}\sin C\sin A$，又 $0<C<\pi$，所以 $\sin C\neq0$，于是 $\cos A=\dfrac{\sqrt{3}}{3}\sin A$，所以 $\tan A=\sqrt{3}$，又因为 $0<A<\pi$，故 $A=\dfrac{\pi}{3}$。"
        + "\n" + r"(2) 因为 $D$ 为边 $BC$ 上，满足 $BD=2CD$，所以 $\overrightarrow{BD}=2\overrightarrow{DC}$，所以 $\overrightarrow{AD}-\overrightarrow{AB}=2(\overrightarrow{AC}-\overrightarrow{AD})$，于是 $\overrightarrow{AD}=\dfrac{1}{3}\overrightarrow{AB}+\dfrac{2}{3}\overrightarrow{AC}$，所以 $\overrightarrow{AD}^2=\dfrac{1}{9}\overrightarrow{AB}^2+\dfrac{4}{9}\overrightarrow{AC}^2+\dfrac{4}{9}\overrightarrow{AB}\cdot\overrightarrow{AC}$，即有 $|\overrightarrow{AD}|^2=\dfrac{1}{9}|\overrightarrow{AB}|^2+\dfrac{4}{9}|\overrightarrow{AC}|^2+\dfrac{4}{9}|\overrightarrow{AB}|\cdot|\overrightarrow{AC}|\cos\dfrac{\pi}{3}$，即 $2^2=\dfrac{1}{9}c^2+\dfrac{4}{9}b^2+\dfrac{4}{9}c\cdot b\cdot\cos\dfrac{\pi}{3}$，所以 $4=\dfrac{1}{9}c^2+\dfrac{4}{9}b^2+\dfrac{2}{9}c\cdot b\geq2\times\dfrac{c}{3}\times\dfrac{2b}{3}+\dfrac{2}{9}c\cdot b=\dfrac{2}{3}bc$，所以 $4\geq\dfrac{2}{3}bc$，即 $bc\leq6$，当且仅当 $\dfrac{c}{3}=\dfrac{2b}{3}$ 时，即 $c=2b=2\sqrt{3}$ 时，取等号，$S_{\triangle ABC}=\dfrac{1}{2}bc\sin A=\dfrac{1}{2}bc\sin\dfrac{\pi}{3}=\dfrac{\sqrt{3}}{4}bc\leq\dfrac{\sqrt{3}}{4}\times6=\dfrac{3\sqrt{3}}{2}$，$\triangle ABC$ 的面积最大值为 $\dfrac{3\sqrt{3}}{2}$。",
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [6],
        "题干": r"(1) 求函数 $f(x)=x\ln x$ 在区间 $\left[\dfrac{1}{3},3\right]$ 上的值域；"
        + "\n" + r"(2) 设函数 $g(x)=\dfrac{1}{2}x^2-ax-\dfrac{1}{2}-x\ln x$ ．"
        + "\n" + r"①求证：当 $a=0$ 时，$g(x)$ 有唯一零点；"
        + "\n" + r"②若 $x_1,x_2$ 分别是 $g(x)$ 的两个不相等的极值点，求证：$x_1+x_2>a+2$ ．",
        "选项": {},
        "答案": r"(1) $f(x)$ 的值域为 $\left[-\dfrac{1}{\mathrm{e}},3\ln3\right]$；(2) ①②证明见解析",
        "解析": r"(1) 解：对函数 $f(x)$ 求导，得 $f'(x)=\ln x+1$ ．由 $f'(x)=0$，得 $x=\dfrac{1}{\mathrm{e}}$，当 $x\in\left[\dfrac{1}{3},\dfrac{1}{\mathrm{e}}\right)$，$f'(x)<0$，$f(x)$ 在 $\left[\dfrac{1}{3},\dfrac{1}{\mathrm{e}}\right)$ 上单调递减；当 $x\in\left(\dfrac{1}{\mathrm{e}},3\right]$，$f'(x)>0$，$f(x)$ 在 $\left(\dfrac{1}{\mathrm{e}},3\right]$ 上单调递增，所以 $f(x)_{\min}=f\left(\dfrac{1}{\mathrm{e}}\right)=-\dfrac{1}{\mathrm{e}}$ ．因为 $f(3)=3\ln3>f\left(\dfrac{1}{3}\right)=-\dfrac{\ln3}{3}$，所以 $f(x)_{\max}=f(3)=3\ln3$ ．故 $f(x)$ 在 $\left[\dfrac{1}{3},3\right]$ 上的值域为 $\left[-\dfrac{1}{\mathrm{e}},3\ln3\right]$ ．"
        + "\n" + r"(2) 证明：①当 $a=0$ 时，$g(x)=\dfrac{1}{2}x^2-\dfrac{1}{2}-x\ln x$，$x\in(0,+\infty)$，则 $g'(x)=x-\ln x-1$ ．令 $h(x)=g'(x)$，$x\in(0,+\infty)$，则 $h'(x)=\dfrac{x-1}{x}$ ．由 $h'(x)=0$，得 $x=1$，当 $x\in(0,1)$ 时，$h'(x)<0$，$h(x)$ 单调递减；当 $x\in(1,+\infty)$ 时，$h'(x)>0$，$h(x)$ 单调递增，所以 $h(x)\geq h(1)=0$，即 $g'(x)\geq0$，因此 $g(x)$ 在 $(0,+\infty)$ 上单调递增．而 $g(1)=\dfrac{1}{2}\times1-\dfrac{1}{2}-1\times\ln1=0$，当 $x\in(0,1)$ 时，$g(x)<g(1)=0$；当 $x\in(1,+\infty)$ 时，$g(x)>g(1)=0$；所以 $g(x)$ 在 $(0,+\infty)$ 上有唯一零点 $x=1$ ．"
        + "\n" + r"② 对函数 $g(x)$ 求导，得 $g'(x)=x-\ln x-1-a$，$x\in(0,+\infty)$ ．由①，得 $g'(x)$ 在 $(0,1)$ 上单调递减，在 $(1,+\infty)$ 上单调递增，$g'(x)\geq g'(1)=-a$ ．因为 $x\to0$，$g'(x)\to+\infty$；$x\to+\infty$，$g'(x)\to+\infty$，所以要使得 $g(x)$ 有两个不等的极值点，即 $g'(x)$ 有两个不等的零点，则 $g'(1)=-a<0$，即 $a>0$ ．不妨设 $0<x_1<1<x_2$，则 $x_1-\ln x_1-a-1=0$，$x_2-\ln x_2-a-1=0$，即 $x_1-\ln x_1=a+1$，$x_2-\ln x_2=a+1$ ．要证 $x_1+x_2>a+2$，即证 $x_2>a+2-x_1=1-\ln x_1$ ．下证：$x_2>a+2-x_1=1-\ln x_1$ ．令 $\varphi(x)=g'(x)-g'(1-\ln x)=x-1+\ln(1-\ln x)$，$x\in(0,1)$，则 $\varphi'(x)=1-\dfrac{1}{x(1-\ln x)}=\dfrac{x(1-\ln x)-1}{x(1-\ln x)}$ ．令 $t(x)=x(1-\ln x)-1$，$x\in(0,1)$，则 $t'(x)=-\ln x>0$，所以 $t(x)$ 在 $(0,1)$ 上单调递增，则 $t(x)<t(1)=0$，即 $\varphi'(x)<0$，所以 $\varphi(x)$ 在 $(0,1)$ 上单调递减，则 $\varphi(x)>\varphi(1)=0$，即 $g'(x)>g'(1-\ln x)$ ．因为 $x_1\in(0,1)$，所以 $g'(x_1)>g'(1-\ln x_1)$，即 $g'(x_2)=0=g'(x_1)>g'(1-\ln x_1)$ ．因为 $g'(x)$ 在 $(1,+\infty)$ 上单调递增，且 $x_2,1-\ln x_1\in(1,+\infty)$，所以 $x_2>1-\ln x_1$，即证得 $x_1+x_2>a+2$ ．",
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [6],
        "题干": r"(1) 一个袋子中有 $30$ 个大小相同的球，其中有 $10$ 个红球、$20$ 个白球，从中随机放回地逐次摸一个球作为样本，$5$ 次摸球后停止，用 $X$ 表示停止时摸出红球的次数．"
        + "\n" + r"①求 $X$ 的分布列和数学期望；"
        + "\n" + r"②若用样本中红球的比例估计总体中红球的比例，求误差的绝对值不超过 $0.2$ 的概率．"
        + "\n" + r"(2) 某节目上，有三扇关闭的门，其中一扇门后面为汽车，另两扇门后面为山羊，节目参加者从这三扇门中选择一扇，然后所选之门后面的物品则归其所有．当参加者选定一扇门后，节目主持人开启了剩余两扇门中后面为山羊的一扇门，并询问节目参加者是否更换选择．"
        + "\n" + r"问：参加者这时候更换选择会更好吗？请用概率解释．（备注：汽车的价值要远大于羊．）",
        "选项": {},
        "答案": r"(1) ① 分布列见解析，$E(X)=\dfrac{5}{3}$；② $\dfrac{160}{243}$；(2) 换门更好：不换门选中汽车的概率是 $P(A)=\dfrac{1}{3}$，换门选中汽车的概率是 $P(B)=\dfrac{2}{3}$",
        "解析": r"(1) ① 每次有放回的抽取，每次抽到红球的概率为 $p=\dfrac{1}{3}$，所以 $X\sim B\left(5,\dfrac{1}{3}\right)$，即 $P(X=k)=C_5^k\left(\dfrac{1}{3}\right)^k\left(1-\dfrac{1}{3}\right)^{5-k}$，$k=0,1,2,3,4,5$，得到 $X$ 的分布列为"
        + "\n" + r"\["
        + "\n" + r"\begin{array}{|c|c|c|c|c|c|c|}\hline X & 0 & 1 & 2 & 3 & 4 & 5\\\hline P & \dfrac{32}{243} & \dfrac{80}{243} & \dfrac{80}{243} & \dfrac{40}{243} & \dfrac{10}{243} & \dfrac{1}{243}\\\hline\end{array}"
        + "\n" + r"\]"
        + "\n" + r"期望为 $E(X)=np=5\times\dfrac{1}{3}=\dfrac{5}{3}$ ．"
        + "\n" + r"② 依题意，样本比例为 $\dfrac{X}{5}$，现要求 $\left|\dfrac{X}{5}-\dfrac{1}{3}\right|\leq0.2$，得 $\dfrac{2}{3}\leq X\leq\dfrac{8}{3}$，即 $X=1,2$，所以用样本中红球的比例估计总体的误差绝对值不超过 $0.2$ 的概率为 $P(X=1)+P(X=2)=\dfrac{80}{243}+\dfrac{80}{243}=\dfrac{160}{243}$ ．"
        + "\n" + r"(2) 记 $A$ 表示初始选择时选得汽车的事件，$B$ 表示更换选择后选得汽车的事件，则 $P(A)=\dfrac{1}{3}$，$P(\overline{A})=\dfrac{2}{3}$，所以 $P(B\mid A)=0$，$P(B\mid\overline{A})=1$，则 $P(B)=P(A)\cdot P(B\mid A)+P(\overline{A})\cdot P(B\mid\overline{A})=\dfrac{1}{3}\times0+\dfrac{2}{3}\times1=\dfrac{2}{3}$，因此不换门选中汽车的概率是 $P(A)=\dfrac{1}{3}$，换门选中汽车的概率是 $P(B)=\dfrac{2}{3}$，故而得结论：当主持人开启剩余之山羊门后，节目参加者换门更好，因为此时其获得汽车的概率是不换门的两倍。",
    },
]

for r in recs:
    r.setdefault("选项", {})
    r["粗筛图"] = False
    r["粗筛表"] = False

review = [
    {
        "题号": 9, "题型": "multi_choice", "页码": [3], "类型": "figure",
        "原文": r"近年中国新能源汽车进入高速发展时期，为了了解消费者的购车类型与地域是否具有相关性，某品牌车商随机调查了甲、乙两地各 200 名消费者，得出统计图如下：（题 9 图）根据此统计图，下列结论正确的是 A. 在所调查的甲地购车者中，购买燃油车的人数比新能源车的多 20 人；B. 在所调查的乙地购车者中，若用分层随机抽样抽取 20 人，则其中新能源车主有 12 人；C. 根据小概率值 α=0.001 的独立性检验，消费者的购车类型与地域有关；D. 从所调查消费者中随机选一人，在已知其为新能源车主的条件下，其来自甲地的概率为 0.4",
        "说明": r"试卷第 3 页 #9 印有一幅标题为「车型与地区」的百分比堆积条形图：纵轴 $0\%\sim100\%$（每 $20\%$ 一条虚线刻度），横轴两个类别「甲地」「乙地」；图例为斜线填充＝燃油车、点状填充＝新能源车。读数为甲地燃油车占 $60\%$、新能源车占 $40\%$；乙地燃油车占 $40\%$、新能源车占 $60\%$。四个选项全部要从这幅图的百分比读出（尤其 A 的「多 20 人」与 D 的条件概率），按规矩不录正文。答案册第 1 页只有答案表，对本题**没有任何解析**。答案 BCD。",
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [3], "类型": "table",
        "原文": r"附：$\chi^2=\dfrac{n(ad-bc)^2}{(a+b)(c+d)(a+c)(b+d)}$，$n=a+b+c+d$．",
        "说明": r"试卷第 3 页 #9 选项下方先印独立性检验统计量公式 $\chi^2=\dfrac{n(ad-bc)^2}{(a+b)(c+d)(a+c)(b+d)}$（$n=a+b+c+d$），紧接着印一张两行四列的临界值表：第一行 $\alpha$ 取 $0.05$、$0.01$、$0.001$，第二行 $x_\alpha$ 依次取 $3.841$、$6.635$、$10.828$。选项 C 的独立性检验结论必须由这张表比对，按规矩不录正文。",
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [4], "类型": "figure",
        "原文": r"如图，在四棱锥 E-ABCD 中，底面 ABCD 为直角梯形，AD∥BC，AD⊥CD，EC⊥平面 ABCD，AD=CE=2，BC=CD=1，M、N 分别为棱 DE、CE 上的动点，设 $\overrightarrow{DM}=\lambda\overrightarrow{DE}$（$0\leq\lambda\leq1$），$\overrightarrow{CN}=\mu\overrightarrow{CE}$（$0\leq\mu\leq1$），则 A. 当 μ=0 时，存在 λ，使得 MN∥平面 ABE；B. 当 μ=0 时，存在 λ，使得 AN⊥BM；C. 当 μ=1/2，且 AN 与 BM 相交时，λ=2/3；D. 三棱锥 E-BCD 的外接球在底面 ABCD 上的截痕长为 $\dfrac{\sqrt{2}\pi}{2}$",
        "说明": r"试卷第 4 页 #11 题干右侧印有「题 11 图」：四棱锥 $E-ABCD$，顶点 $E$ 在上，底面直角梯形 $ABCD$ 中 $D$ 左下、$A$ 右下、$C$ 居中偏左、$B$ 居中偏右；$M$ 标在棱 $DE$ 上、$N$ 标在棱 $CE$ 上，$CD$、$CB$、$BD$、$MN$、$NB$ 等用虚线。底面各顶点的左右前后位置关系只能从这幅图确认，按规矩不录正文。答案册第 1 页只有答案表，对本题**没有任何解析**。答案 AC。",
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [5], "类型": "figure",
        "原文": r"如图，$F$ 是抛物线 $C:y^2=2px$（$p>0$）的焦点，$P$ 是抛物线 $C$ 在第一象限上的一点，$\angle OFP=60^{\circ}$，$|PF|=2$．(1) 求抛物线 $C$ 的方程；(2) 求抛物线 $C$ 在点 $P$ 处的切线方程．",
        "说明": r"试卷第 5 页 #15 题干右侧印有「题 15 图」：平面直角坐标系中开口向右的抛物线，$P$ 标在第一象限的曲线上，$F\left(\dfrac{p}{2},0\right)$ 标在 $x$ 轴正半轴，$OP$、$PF$ 连成实线、$P$ 向 $x$ 轴作虚线垂线。按规矩不录正文。"
        + "\n" + r"答案册（第 1—2 页）给出的完整解答：(1) 抛物线 $C:y^2=2px\,(p>0)$ 的准线 $l:x=-\dfrac{p}{2}$；如图，过 $P$ 作 $PM\perp OF$，垂足为 $M$，过 $P$ 作 $PN\perp l$，垂足为 $N$；设 $P(x_0,y_0)$，$x_0>0,y_0>0$，由抛物线定义知 $PN=x_0+\dfrac{p}{2}=PF=2$；在 $Rt\triangle PMF$ 中，$PF=2$，$\angle PFM=60^{\circ}$，所以 $MF=1$，即有 $x_0=\dfrac{p}{2}-1$，于是有 $\left(\dfrac{p}{2}-1\right)+\dfrac{p}{2}=2$，解得 $p=3$，因此抛物线 $C$ 的方程为 $y^2=6x$。(2) 由 (1) 得 $x_0=\dfrac{p}{2}-1=\dfrac{1}{2}$，代入抛物线 $C$ 的方程得 $y_0^2=6\times\dfrac{1}{2}=3$，$y_0=\sqrt{3}$，所以 $P\left(\dfrac{1}{2},\sqrt{3}\right)$；可设抛物线 $C$ 在点 $P$ 处的切线方程为 $y-\sqrt{3}=k\left(x-\dfrac{1}{2}\right)$，联立方程 $\begin{cases}y-\sqrt{3}=k\left(x-\dfrac{1}{2}\right),\\ y^2=6x\end{cases}$；显然切线不平行 $x$ 轴，故其斜率 $k\neq0$，将 $x=\dfrac{1}{k}(y-\sqrt{3})+\dfrac{1}{2}$ 代入，消去 $x$，整理得：$y^2-\dfrac{6}{k}y+\left(\dfrac{6\sqrt{3}}{k}-3\right)=0$，因为相切，有 $\Delta=\left(-\dfrac{6}{k}\right)^2-4\left(\dfrac{6\sqrt{3}}{k}-3\right)=0$，即有：$36-24\sqrt{3}k+12k^2=12(k-\sqrt{3})^2=0$，因此 $k=\sqrt{3}$，所以抛物线 $C$ 在点 $P$ 处的切线方程为 $y-\sqrt{3}=\sqrt{3}\left(x-\dfrac{1}{2}\right)$，即 $2\sqrt{3}x-2y+\sqrt{3}=0$。（答案册此页另印一幅带准线 $l$、垂足 $M$、$N$ 的辅助图。）",
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [5], "类型": "figure",
        "原文": r"如图，在斜三棱柱 ABC-A₁B₁C₁ 中，侧面 ABB₁A₁⊥底面 ABC，△ABC 是等腰直角三角形，AC⊥BC，△ABA₁ 是边长为 2 的等边三角形．(1) 求点 A 到平面 A₁BC 的距离；(2) 求二面角 A-A₁B-C 的正弦值．",
        "说明": r"试卷第 5 页 #16 题干右侧印有「题 16 图」：斜三棱柱 $ABC-A_1B_1C_1$，$A_1$、$B_1$ 在上、$C_1$ 居中，$A$ 左、$B$ 右、$C$ 在下，$AB$、$AC$、$A_1C$、$A_1B$ 等以虚线表示被遮的棱。顶点上下左右关系与哪些棱为虚线全靠这幅图，按规矩不录正文。"
        + "\n" + r"答案册（第 2—3 页）给出的完整解答：(1) 取 $AB$ 中点 $O$，连接 $CO,A_1O$。由题意，易得 $CO\perp AB,A_1O\perp AB$，$A_1O=\sqrt{3}$。法一：因为侧面 $ABB_1A_1\perp$ 底面 $ABC$，侧面 $ABB_1A_1\cap$ 底面 $ABC=AB$，所以 $A_1O\perp$ 平面 $ABC$，所以 $A_1O$ 是三棱锥 $A_1-ABC$ 的高；又因为在 $Rt\triangle A_1OC$ 中，$A_1C=\sqrt{A_1O^2+OC^2}=2$，而 $A_1B=2,BC=\sqrt{2}$，所以 $\triangle A_1BC$ 为等腰三角形，且边 $BC$ 上的高等于 $\sqrt{2^2-\left(\dfrac{\sqrt{2}}{2}\right)^2}=\dfrac{\sqrt{7}}{\sqrt{2}}$，所以 $S_{\triangle A_1BC}=\dfrac{1}{2}\times\sqrt{2}\times\dfrac{\sqrt{7}}{\sqrt{2}}=\dfrac{\sqrt{7}}{2}$；记点 $A$ 到平面 $A_1BC$ 的距离为 $h_A$，由 $V_{A-A_1BC}=V_{A_1-ABC}$，得 $\dfrac{1}{3}S_{\triangle A_1BC}\cdot h_A=\dfrac{1}{3}S_{\triangle ABC}\cdot A_1O$，即 $\dfrac{1}{3}\times\dfrac{\sqrt{7}}{2}\times d=\dfrac{1}{3}\times\left(\dfrac{1}{2}\times2\times1\right)\times\sqrt{3}$，于是得 $h_A=\dfrac{2\sqrt{21}}{7}$。法二：以 $O$ 为原点，分别以 $OC,OB,OA_1$ 所在直线为 $x,y,z$ 轴，建立坐标系 $O-xyz$，易知 $O(0,0,0),B(0,1,0),A(0,-1,0),C(1,0,0),A_1(0,0,\sqrt{3}),B_1(0,2,\sqrt{3})$，所以 $\overrightarrow{BA_1}=(0,-1,\sqrt{3}),\overrightarrow{BC}=(1,-1,0)$；设平面 $A_1BC$ 的法向量为 $\vec{n}=(x_1,y_1,z_1)$，所以 $\begin{cases}\vec{n}\cdot\overrightarrow{A_1B}=-y_1+\sqrt{3}z_1=0\\ \vec{n}\cdot\overrightarrow{BC}=x_1-y_1=0\end{cases}$，令 $y_1=\sqrt{3}$，得 $x_1=\sqrt{3},z_1=1$，得到平面 $A_1BC$ 的一个法向量 $\vec{n}=(\sqrt{3},\sqrt{3},1)$；又因为 $\overrightarrow{AA_1}=(0,1,\sqrt{3})$，所以点 $A$ 到平面 $A_1BC$ 的距离等于 $\dfrac{|\overrightarrow{AA_1}\cdot\vec{n}|}{|\vec{n}|}=\dfrac{2\sqrt{3}}{\sqrt{3+3+1}}=\dfrac{2\sqrt{21}}{7}$。(2) 法一：设点 $A$ 在平面 $A_1BC$ 上的投影为 $H$，$A_1B$ 的中点为 $M$，连结 $AM$ 和 $HM$，因为 $\triangle ABA_1$ 是边长为 2 的等边三角形，所以 $AM\perp A_1B$，且 $AM=\sqrt{3}$；而 $AH\perp$ 平面 $A_1BC$，所以 $HM\perp A_1B$，因此 $\angle AMH$ 为二面角 $A-A_1B-C$ 的平面角；在 $Rt\triangle AHM$ 中，$\sin\angle AMH=\dfrac{AH}{AM}=\dfrac{h_A}{\sqrt{3}}=\dfrac{\dfrac{2\sqrt{3}}{\sqrt{7}}}{\sqrt{3}}=\dfrac{2\sqrt{7}}{7}$。（答案册此处另印一幅带 $H$、$M$ 及红色虚线的辅助立体图。）法二：易知 $\overrightarrow{OC}=(1,0,0)$ 为平面 $AA_1B$ 的一个法向量，又由（1）知平面 $A_1BC$ 的法向量为 $\vec{n}=(1,1,\dfrac{\sqrt{3}}{3})$，所以 $\cos\langle\vec{n},\overrightarrow{OC}\rangle=\dfrac{\vec{n}\cdot\overrightarrow{OC}}{|\vec{n}|\cdot|\overrightarrow{OC}|}=\dfrac{1}{\sqrt{1+1+\dfrac{1}{3}}\cdot1}=\dfrac{\sqrt{21}}{7}$，因此二面角 $A-A_1B-C$ 的正弦值为 $\sqrt{1-\left(\dfrac{\sqrt{21}}{7}\right)^2}$，即为 $\dfrac{2\sqrt{7}}{7}$。",
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [6], "类型": "table",
        "原文": r"答案册第 7 页 (1)①「得到 $X$ 的分布列为」后印一张两行七列表格",
        "说明": r"表在**答案册**第 7 页（试卷第 6 页 #19 题干本身不带表）：两行七列，第一行 $X$ 取 $0$、$1$、$2$、$3$、$4$、$5$，第二行 $P$ 依次为 $\dfrac{32}{243}$、$\dfrac{80}{243}$、$\dfrac{80}{243}$、$\dfrac{40}{243}$、$\dfrac{10}{243}$、$\dfrac{1}{243}$。已按项目惯例把这张表转成 `array` 阵列写进 #19 的 `解析`（`tidy` 修 0、干跑通过），本条登记是为了核数值：六格分子相加 $32+80+80+40+10+1=243$，概率之和恰为 $1$，与 $X\sim B\left(5,\dfrac{1}{3}\right)$ 一致；$E(X)=\dfrac{5}{3}$、$P(X=1)+P(X=2)=\dfrac{160}{243}$ 均取自该表。请人工核对转录有无错格。",
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [4], "类型": "print-suspect",
        "原文": r"卷面题干：数列 $\{a,b,c\}$ 经过一次扩充后得到数列 $\left\{a_k^{(1)}\right\}=\{a,a+b,b,b+c,c\}$，$P_1=5$，$S_1=2a+3b+2c$……则 $P_n=$________；$S_n=$________．　答案册第 1 页：$P_n=2^n+1$；$S_n=3^n$",
        "说明": r"疑在哪：答案册给的 $P_n=2^n+1$ 与**同一道题卷面自带的示例**矛盾——卷面明写 $P_1=5$，而 $2^1+1=3\neq5$；按扩充规则（每相邻两项之间插入这两项的和）项数满足 $P_{n+1}=2P_n-1$、$P_0=3$，解为 $P_n=2^{n+1}+1$（$P_1=5$、$P_2=9$ 才对得上）。$S_n=3^n$ 那半句自洽（$S_0=1$、$S_1=3$）。为何没改：规范 §7.3 规定内容一个字都不许改、不许自行解题订正标答，故成品里 `答案` 字段照录 $P_n=2^n+1$；$S_n=3^n$ 照录。已在本条留证，交人工核对时决定。",
    },
]

for r in review:
    r.setdefault("原文", "")

# ---- 落盘前自查（都是踩过的坑，判据与闸门/记忆对齐）----
import re

def vals(rec):
    out = [rec.get("题干") or "", rec.get("答案") or "", rec.get("解析") or ""]
    out += list((rec.get("选项") or {}).values())
    return out

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
        if "见待复核" in s:
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
