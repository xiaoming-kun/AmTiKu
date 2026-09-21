#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 #179 湖南省长沙市2026年高三年级模拟考试数学 的成品 / 待复核。

来源：`【数学试卷】长沙市2026年高三模拟考试.pdf` 6 页
    （PDF 第 1 页是封面「注意事项+姓名/准考证号」、第 2 页空白，卷面正文在 PDF 第 3–6 页，
      卷面自标「数学试题第 1 页（共 4 页）」～「第 4 页」）
    + `【数学参考答案】长沙市2026年高三模拟考试.pdf` 7 页（卷面自标「数学试题与参考答案第 N 页（共 7 页）」）。
成品「页码」一律用**卷面页码 1–4**（与既有各场口径一致），说明文字里另标 PDF 页。
卷面结构：一、选择题本大题共 8 小题；二、选择题本大题共 3 小题；
三、填空题本大题共 3 小题（12–14）；四、解答题本大题共 5 小题（15–19）。
正文一律 r-string；多行用 L([...]) 以真实换行拼接。
"""
import json
from pathlib import Path

OUT = Path("数据/录题/输出_v2")
NAME = "179_湖南省长沙市2026年高三年级模拟考试数学"


def L(*lines):
    return "\n".join(lines)


recs = [
    {
        "题号": 1, "题型": "single_choice", "页码": [1],
        "题干": r"已知命题 $p:\forall x\in\mathbf{R}$，$\cos x\leqslant 1$，则 $\neg p$ 为",
        "选项": {
            "A": r"$\exists x\in\mathbf{R}$，$\cos x>1$",
            "B": r"$\exists x\in\mathbf{R}$，$\cos x\leqslant 1$",
            "C": r"$\exists x\notin\mathbf{R}$，$\cos x>1$",
            "D": r"$\exists x\notin\mathbf{R}$，$\cos x\leqslant 1$",
        },
        "答案": "A", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 2, "题型": "single_choice", "页码": [1],
        "题干": r"复数 $\dfrac{5}{1-2\mathrm{i}}$ 的共轭复数是",
        "选项": {
            "A": r"$-1+2\mathrm{i}$", "B": r"$-1-2\mathrm{i}$",
            "C": r"$1+2\mathrm{i}$", "D": r"$1-2\mathrm{i}$",
        },
        "答案": "D", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 3, "题型": "single_choice", "页码": [1],
        "题干": r"已知 $a+b=6$，若在 $a,b$ 之间插入 $3$ 个数 $x_{1}$，$x_{2}$，$x_{3}$，使得这 $5$ 个数成等差数列，则 $x_{1}+x_{2}+x_{3}=$",
        "选项": {"A": r"$6$", "B": r"$9$", "C": r"$12$", "D": r"$18$"},
        "答案": "B", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 4, "题型": "single_choice", "页码": [1],
        "题干": r"「$x<0$」是「$x+\dfrac{1}{x}\leqslant -2$」的",
        "选项": {
            "A": "充分不必要条件", "B": "必要不充分条件",
            "C": "充要条件", "D": "既不充分也不必要条件",
        },
        "答案": "C", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 5, "题型": "single_choice", "页码": [1],
        "题干": r"已知椭圆的长轴长、短轴长与焦距依次成等比数列，则其离心率为",
        "选项": {
            "A": r"$\dfrac{3}{5}$", "B": r"$\dfrac{\sqrt{3}-1}{2}$",
            "C": r"$\dfrac{\sqrt{5}-1}{2}$", "D": r"$\dfrac{\sqrt{5}+1}{2}$",
        },
        "答案": "C", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 6, "题型": "single_choice", "页码": [1],
        "题干": r"已知函数 $f(x)=\begin{cases}(2a-1)x+4a,\ x<1,\\ x^{2}-ax+5,\ \ \ \ x\geqslant 1,\end{cases}$ 若 $f(x)$ 是 $\mathbf{R}$ 上的单调递增函数，则实数 $a$ 的取值范围是",
        "选项": {
            "A": r"$\left(\dfrac{1}{2},1\right)$", "B": r"$\left(\dfrac{1}{2},1\right]$",
            "C": r"$\left(\dfrac{1}{2},2\right]$", "D": r"$\left[\dfrac{1}{2},+\infty\right)$",
        },
        "答案": "B", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 7, "题型": "single_choice", "页码": [2],
        "题干": L(
            r"已知某四棱锥的一条侧棱垂直于底面，其底面为平行四边形，且 $8$ 条棱的长度构成的集合为 $\{1,\sqrt{2},\sqrt{3}\}$，则满足条件的四棱锥的个数为",
            r"注：若两个几何体经过调整位置后重合或者关于某平面对称，算同种形状．",
        ),
        "选项": {"A": r"$2$", "B": r"$4$", "C": r"$6$", "D": r"$8$"},
        "答案": "C", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 8, "题型": "single_choice", "页码": [2],
        "题干": L(
            r"根据预报数据，某港口某一天的水深 $y$（单位：$\mathrm{m}$）与时间 $x$（单位：$\mathrm{h}$）的关系可以用函数 $y=\sqrt{2}\sin\dfrac{\pi}{8}x+5.5$ 来近似描述．现有一艘货船准备在这天 $4:00$ 进入港口并及时卸货，已知该船空船时的吃水深度（船底与水面的距离）为 $2.5\mathrm{m}$，在卸货过程中，其吃水深度以 $\dfrac{\pi}{8}\mathrm{m/h}$ 的速度减少，且安全间隙（船底与海底的距离）为 $1.5\mathrm{m}$．若要保证该船能在当天安全驶出港口，则其卸货前的吃水最大深度约为",
        ),
        "选项": {
            "A": r"$3.85\ \mathrm{m}$", "B": r"$4.85\ \mathrm{m}$",
            "C": r"$5.35\ \mathrm{m}$", "D": r"$5.40\ \mathrm{m}$",
        },
        "答案": "C",
        "解析": L(
            r"由题意可知，该船空船时不受水深影响．设其卸货前的吃水深度为 $d$，在 $x\ \mathrm{h}$ 时的安全水深为 $y\ \mathrm{m}$，则 $y=d+1.5-\dfrac{\pi}{8}(x-4)(x\geqslant 4)$（*）．",
            r"设 $f(x)=\sqrt{2}\sin\dfrac{\pi}{8}x+5.5(x\in[4,12])$，则 $f^{\prime}(x)=\dfrac{\sqrt{2}\pi}{8}\cos\dfrac{\pi}{8}x$．当方程（*）对应的直线与曲线 $y=f(x)$ 相切时，$d$ 达到最大值．此时，$f^{\prime}(x)=-\dfrac{\pi}{8}$，解得 $x=10$ 或 $x=6$（舍）；由 $f(10)=4.5$，可得 $d+1.5-\dfrac{\pi}{8}(10-4)=4.5$，解得 $d=3+\dfrac{3\pi}{4}$，则 $d\approx 5.35\ \mathrm{m}$．",
        ),
        "粗筛图": True, "粗筛表": False,
    },
    {
        "题号": 9, "题型": "multi_choice", "页码": [2],
        "题干": r"在军训打靶测试中，四位同学各射靶 $5$ 次，分别记录每次射击所命中的环数．根据这四名同学射击成绩的统计结果，可以判断出可能出现 $10$ 环的是",
        "选项": {
            "A": "平均数为 $8$，极差为 $3$",
            "B": "中位数为 $8$，平均数为 $8$",
            "C": "中位数为 $7$，众数为 $9$",
            "D": "平均数为 $7$，方差为 $2.4$",
        },
        "答案": "ABD", "解析": "解析无", "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 10, "题型": "multi_choice", "页码": [2],
        "题干": r"已知函数 $f(x)$ 的定义域为 $(-\infty,0)\cup(0,+\infty)$，且 $f(xy)=\dfrac{f(x)}{y}+\dfrac{f(y)}{x}$．当 $x>1$ 时，$f(x)>0$，则",
        "选项": {
            "A": r"$f(1)=0$",
            "B": r"$f(x)$ 是偶函数",
            "C": r"当 $-1<x<0$ 时，$f(x)>0$",
            "D": r"$x=1$ 为 $f(x)$ 的极值点",
        },
        "答案": "AC",
        "解析": L(
            r"令 $x=y=1$，则 $f(1)=2f(1)$，解得 $f(1)=0$，即 A 正确．",
            r"令 $x=y=-1$，则 $f(1)=-f(-1)-f(-1)=-2f(-1)$，解得 $f(-1)=0$；令 $y=-1$，则 $f(-x)=-f(x)+\dfrac{f(-1)}{x}=-f(x)$，可得 $f(x)$ 为奇函数，即 B 错误．",
            r"当 $0<x<1$ 时，令 $y=\dfrac{1}{x}$，有 $f(1)=xf(x)+\dfrac{f(\frac{1}{x})}{x}$，则 $f(\dfrac{1}{x})=-x^{2}f(x)>0$，可得 $f(x)<0$．而 $f(x)$ 为奇函数，则 $-1<x<0$ 时，$f(x)>0$，即 C 正确．",
            r"将 $f(xy)=\dfrac{f(x)}{y}+\dfrac{f(y)}{x}$ 两边同时乘以 $xy$，得到 $xy\cdot f(xy)=xf(x)+yf(y)$，可设 $xf(x)=\ln|x|(x\neq 0)$，则 $f(x)=\dfrac{\ln|x|}{x}$．当 $x>0$ 时，$f(x)=\dfrac{\ln x}{x}$，则 $f^{\prime}(x)=\dfrac{1-\ln x}{x^{2}}$，可得 $f(x)$ 在 $(0,\mathrm{e})$ 上单调递增，在 $(\mathrm{e},+\infty)$ 上单调递减，此时，$x=1$ 不为 $f(x)$ 的极值点，即 D 错误．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2],
        "题干": r"已知直线 $l$ 与圆 $C:(x-5)^{2}+y^{2}=9$ 相切于点 $P$，与抛物线 $E:y^{2}=2x$ 相交于 $M$，$N$ 两点，点 $F$ 为抛物线 $E$ 的焦点．下列说法正确的是",
        "选项": {
            "A": r"记点 $M$ 的横坐标为 $x_{M}$，则 $|MP|=|x_{M}-4|$",
            "B": r"$|MN|$ 的最小值为 $4$",
            "C": r"当点 $P$ 在直线 $x=4$ 的左侧时，$\triangle MNF$ 的周长为定值 $9$",
            "D": r"当点 $P$ 在直线 $x=4$ 的右侧时，$\triangle MNF$ 的周长有最小值 $25$",
        },
        "答案": "AC",
        "解析": L(
            r"$|MP|=\sqrt{|MC|^{2}-|PC|^{2}}=\sqrt{(x_{M}-5)^{2}+y_{M}^{2}-9}=\sqrt{(x_{M}-5)^{2}+2x_{M}-9}=|x_{M}-4|$，可知选项 A 正确．",
            r"如下两图所示，过点 $M$，作直线 $x=4$ 的垂线，垂足为 $H_{1}$，作准线 $x=-\dfrac{1}{2}$ 的垂线，垂足为 $H_{2}$；过点 $N$，作直线 $x=4$ 的垂线，垂足为 $H_{3}$，作准线 $x=-\dfrac{1}{2}$ 的垂线，垂足为 $H_{4}$．",
            r"根据左图，当点 $P$ 在直线 $x=4$ 的左侧时，可知 $|MN|=|MH_{1}|+|NH_{3}|$，为直角梯形 $MH_{1}H_{3}N$ 的中位线长的两倍．若 $M$，$N$ 在 $x$ 轴的两侧时，$|MN|$ 有最小值为 $4$；若 $M$，$N$ 在 $x$ 轴的同一侧时，当 $x_{P}\to 4$ 时，$|MN|\to 0$，即选项 B 错误．",
            r"如左图，根据以上证明，可知 $|MP|=|MH_{1}|$，$|NP|=|NH_{3}|$；再根据抛物线定义，可知 $|MF|=|MH_{2}|$，$|NF|=|NH_{4}|$．从而，$\triangle MNF$ 的周长为 $|H_{1}H_{2}|+|H_{3}H_{4}|=2|4-(-\dfrac{1}{2})|=9$，即选项 C 正确．",
            r"如右图，当点 $P$ 在直线 $x=4$ 的右侧时，同理可得 $|MF|+|NF|-|MN|=9$．若 $M$，$N$ 在 $x$ 轴的两侧时，而 $|MN|=|MH_{1}|+|NH_{3}|$，为直角梯形 $MH_{1}H_{3}N$ 的中位线长的两倍，则 $|MN|$ 有最小值为 $8$，此时，则 $\triangle MNF$ 的周长为 $9+2|MN|$，其最小值为 $25$；若 $M$，$N$ 在 $x$ 轴的同一侧时，当 $x_{P}\to 4$ 时，$|MN|\to 0$，$\triangle MNF$ 的周长趋于 $9$，此时不存在最小值，即选项 D 错误．",
        ),
        "粗筛图": True, "粗筛表": False,
    },
    {
        "题号": 12, "题型": "fill_in_blank", "页码": [3],
        "题干": r"函数 $f(x)=\tan(\dfrac{\pi}{4}x+\dfrac{\pi}{4})$ 的一个对称中心为 _____．",
        "选项": {},
        "答案": r"$(2k-1,0)$（其中 $k\in\mathbf{Z}$，任写一个满足条件的都可以）",
        "解析": "解析无",
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 13, "题型": "fill_in_blank", "页码": [3],
        "题干": r"在 $\triangle ABC$ 中，$\overrightarrow{AD}=\dfrac{1}{3}\overrightarrow{AB}$，点 $E$ 为 $CD$ 中点．若 $AC=2$，$AB=3$，则 $\overrightarrow{AE}\cdot\overrightarrow{CD}=$ _____．",
        "选项": {},
        "答案": r"$-\dfrac{3}{2}$",
        "解析": L(
            r"由 $\overrightarrow{AE}=\dfrac{1}{2}\overrightarrow{AC}+\dfrac{1}{2}\overrightarrow{AD}$，$\overrightarrow{CD}=\overrightarrow{AD}-\overrightarrow{AC}$，且 $AD=1$，可知 $\overrightarrow{AE}\cdot\overrightarrow{CD}=(\dfrac{1}{2}\overrightarrow{AC}+\dfrac{1}{2}\overrightarrow{AD})\cdot(\overrightarrow{AD}-\overrightarrow{AC})=\dfrac{1}{2}\overrightarrow{AD}^{2}-\dfrac{1}{2}\overrightarrow{AC}^{2}=\dfrac{1}{2}\times 1^{2}-\dfrac{1}{2}\times 2^{2}=-\dfrac{3}{2}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [3],
        "题干": r"已知点 $A$，$B$，$C$，$D$ 均在半径为 $\sqrt{2}$ 的球 $O$ 的球面上，$AB\perp AC$，$BC=2$，$AD=\sqrt{6}$，则四面体 $D-ABC$ 的体积的最大值为 _____．",
        "选项": {},
        "答案": r"$\dfrac{3+\sqrt{3}}{6}$",
        "解析": L(
            r"如图所示，由题意可知，点 $A$ 在以 $BC$ 为直径的截面圆 $O^{\prime}$ 上运动，则 $AB^{2}+AC^{2}=4$，可得 $S_{\triangle ABC}=\dfrac{1}{2}AB\cdot AC\leqslant\dfrac{1}{4}(AB^{2}+AC^{2})=1$，当且仅当 $AB=AC=\sqrt{2}$ 时取等号．",
            r"连接 $OA$，$OD$，在 $\triangle OAD$ 中，$AD=\sqrt{6}$，$OA=OD=\sqrt{2}$，由余弦定理可得 $\cos\angle OAD=\dfrac{\sqrt{3}}{2}$，则点 $D$ 的轨迹是以直线 $OA$ 为中心轴的圆锥与该球面的截面圆 $E$，其半径 $DE=\sqrt{6}\sin\angle DAE=\dfrac{\sqrt{6}}{2}$，且 $AE=\sqrt{6}\cos\angle DAE=\dfrac{3\sqrt{2}}{2}$．",
            r"当 $AB=AC$ 时，$(S_{\triangle ABC})_{\max}=1$，此时过点 $D$，作 $DH\perp$ 平面 $ABC$ 于点 $H$．根据对称性，垂足 $H$ 必在 $AO^{\prime}$ 上，易知 $\angle OAO^{\prime}=45^{\circ}$，则 $\angle DAH=75^{\circ}$．当点 $D$ 到平面 $ABC$ 的距离最大时，$DH=AD\cdot\sin 75^{\circ}=\dfrac{3+\sqrt{3}}{2}$，故四面体 $D-ABC$ 的体积的最大值为 $V_{\text{三棱锥}D-ABC}=\dfrac{1}{3}\cdot S_{\triangle ABC}\cdot DH=\dfrac{1}{3}\times 1\times\dfrac{3+\sqrt{3}}{2}=\dfrac{3+\sqrt{3}}{6}$．",
        ),
        "粗筛图": True, "粗筛表": False,
    },
    {
        "题号": 15, "题型": "detailed_answer", "页码": [3],
        "题干": L(
            r"已知 $\triangle ABC$ 的三个内角 $A$，$B$，$C$ 满足 $\sin B+\sin(A-B)=\sin C$．",
            r"(1) 求 $A$；",
            r"(2) 若 $\overrightarrow{AB}\cdot\overrightarrow{AC}=2$，且 $BC=3$，求 $\triangle ABC$ 的内切圆半径．",
        ),
        "选项": {},
        "答案": L(
            r"(1) $A=\dfrac{\pi}{3}$；(2) $\triangle ABC$ 的内切圆半径为 $\dfrac{\sqrt{7}-\sqrt{3}}{2}$．",
        ),
        "解析": L(
            r"(1) 由 $\sin B+\sin(A-B)=\sin C$，可得 $\sin B+\sin(A-B)=\sin(A+B)$，即 $\sin B+\sin A\cos B-\cos A\sin B=\sin A\cos B+\cos A\sin B$，化简 $\sin B=2\cos A\sin B$，有 $\cos A=\dfrac{1}{2}$．又 $A\in(0,\pi)$，则 $A=\dfrac{\pi}{3}$．",
            r"(2) 记 $\triangle ABC$ 的角 $A,B,C$ 所对的边长分别为 $a,b,c$，由 $\overrightarrow{AB}\cdot\overrightarrow{AC}=2$，可得 $|\overrightarrow{AB}||\overrightarrow{AC}|\cos A=2$，则 $bc=4$．",
            r"由余弦定理，$a^{2}=b^{2}+c^{2}-2bc\cos A=(b+c)^{2}-3bc$，而 $a=3$，可得 $b+c=\sqrt{21}$．",
            r"设 $\triangle ABC$ 的内切圆半径为 $r$，则 $S_{\triangle ABC}=\dfrac{1}{2}bc\sin A=\dfrac{1}{2}(a+b+c)r$，可得 $r=\dfrac{bc\sin A}{a+b+c}=\dfrac{4\times\dfrac{\sqrt{3}}{2}}{3+\sqrt{21}}=\dfrac{\sqrt{7}-\sqrt{3}}{2}$，故 $\triangle ABC$ 的内切圆半径为 $\dfrac{\sqrt{7}-\sqrt{3}}{2}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 17, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"已知 $A$ 为双曲线 $C:x^{2}-\dfrac{y^{2}}{b^{2}}=1(b>0)$ 的右顶点，过点 $T(0,t)$ 的直线 $l$ 与双曲线 $C$ 的左右两支分别相交于 $M$，$N$ 两点．",
            r"(1) 若直线 $l$ 的斜率为 $2$，求 $b$ 的取值范围；",
            r"(2) 设直线 $AM$，$AN$ 分别与 $y$ 轴相交于 $P$，$Q$ 两点，若 $|AT|^{2}=|PT|\cdot|QT|$，求双曲线 $C$ 的方程．",
        ),
        "选项": {},
        "答案": L(
            r"(1) $b$ 的取值范围是 $(2,+\infty)$；(2) 双曲线 $C$ 的方程为 $x^{2}-y^{2}=1$．",
        ),
        "解析": L(
            r"依题意，直线 $l$ 的斜率存在．设直线 $l$ 的方程为 $y=kx+t$，联立直线 $l$ 与双曲线方程，即 $\begin{cases}y=kx+t\\ x^{2}-\dfrac{y^{2}}{b^{2}}=1\end{cases}$，可得 $(b^{2}-k^{2})x^{2}-2ktx-t^{2}-b^{2}=0$．",
            r"由 $\Delta=4k^{2}t^{2}+4(b^{2}-k^{2})(b^{2}+t^{2})>0$，可得 $k^{2}<t^{2}+b^{2}$，且 $x_{M}+x_{N}=\dfrac{2kt}{b^{2}-k^{2}}$，$x_{M}x_{N}=-\dfrac{b^{2}+t^{2}}{b^{2}-k^{2}}$．",
            r"(1) 当 $k=2$ 时，结合题意可知 $x_{M}x_{N}=-\dfrac{b^{2}+t^{2}}{b^{2}-4}<0$，即 $b^{2}-4>0$，解得 $b>2$ 或 $b<-2$，又 $b>0$，故 $b$ 的取值范围是 $(2,+\infty)$．",
            r"(2) 直线 $AM$ 的方程为 $y=\dfrac{y_{M}}{x_{M}-1}(x-1)$，令 $x=0$，则 $y=-\dfrac{y_{M}}{x_{M}-1}$，即 $y_{P}=-\dfrac{y_{M}}{x_{M}-1}$．同理，$y_{Q}=-\dfrac{y_{N}}{x_{N}-1}$．",
            r"因此，$|PT|\cdot|QT|=|-\dfrac{y_{M}}{x_{M}-1}-t|\cdot|-\dfrac{y_{N}}{x_{N}-1}-t|=|-\dfrac{kx_{M}+t}{x_{M}-1}-t|\cdot|-\dfrac{kx_{N}+t}{x_{N}-1}-t|$ $=(k+t)^{2}\cdot\left|\dfrac{x_{M}x_{N}}{(x_{M}-1)(x_{N}-1)}\right|=(k+t)^{2}\cdot\left|\dfrac{x_{M}x_{N}}{x_{M}x_{N}-(x_{M}+x_{N})+1}\right|=t^{2}+b^{2}$．而 $|AT|^{2}=t^{2}+1$，则 $t^{2}+1=t^{2}+b^{2}$，解得 $b=1$．故双曲线 $C$ 的方程为 $x^{2}-y^{2}=1$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 18, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"已知集合 $U$ 含有 $n$ 个元素，其中 $n\geqslant 2$，先后两次随机、独立地选取集合 $U$ 的两个子集，记为 $A$ 与 $B$．设 $X$ 为集合 $A\cup B$ 中元素的个数，",
            r"(1) 若 $U=\{1,2\}$，且 $X=1$，请列举所有满足条件的 $A$ 和 $B$；",
            r"(2) 求随机变量 $X$ 的数学期望 $E(X)$；",
            r"(3) 设 $P(X=k)$ 在 $k=m$ 处取得最大值，试建立 $m$ 与 $E(X)$ 的函数关系．",
        ),
        "选项": {},
        "答案": L(
            r"(1) 六组：$A=\varnothing,B=\{1\}$；$A=\{1\},B=\varnothing$；$A=\varnothing,B=\{2\}$；$A=\{2\},B=\varnothing$；$A=\{1\},B=\{1\}$；$A=\{2\},B=\{2\}$；",
            r"(2) $E(X)=\dfrac{3n}{4}$；",
            r"(3) $m$ 按 $n$ 模 $4$ 分类取 $E(X)$、$E(X)+\dfrac{1}{4}$、$E(X)+\dfrac{1}{2}$、$E(X)-\dfrac{1}{4}$ 或 $E(X)+\dfrac{3}{4}$（见解析末式）．",
        ),
        "解析": L(
            r"(1) $A=\varnothing$，$B=\{1\}$；$A=\{1\}$，$B=\varnothing$；$A=\varnothing$，$B=\{2\}$；$A=\{2\}$，$B=\varnothing$；$A=\{1\}$，$B=\{1\}$；$A=\{2\}$，$B=\{2\}$．",
            r"(2) 根据集合 $U$ 的子集个数，可知集合 $A$ 的可能情况有 $2^{n}$ 种；同理，集合 $B$ 也可能有 $2^{n}$ 种．因此，两集合的所有可能情况数为 $2^{n}\times 2^{n}=4^{n}$．",
            r"$X$ 的所有取值为 $0$，$1$，$\cdots$，$n$．当 $X=k(k=0,1,\cdots,n)$ 时，先从 $n$ 个元素中选出 $k$ 个元素，记为 $x_{i}(i=1,2,\cdots,k)$，有 $C_{n}^{k}$ 种可能情况；对于这 $k$ 个元素中的每个元素 $x_{i}(i=1,2,\cdots,k)$，满足 $x_{i}\in A\cup B$ 时，只可能满足 $x_{i}\in C_{A}B$，$x_{i}\in C_{B}A$，$x_{i}\in A\cap B$ 这三种情况之一，有 $3^{k}$ 种可能情况．",
            r"因此，事件「$X=k(k=0,1,\cdots,n)$」的所有可能情况数为 $C_{n}^{k}3^{k}$，则 $P(X=k)=\dfrac{C_{n}^{k}3^{k}}{4^{n}}$．",
            r"由 $P(X=k)=\dfrac{C_{n}^{k}3^{k}}{4^{n}}=C_{n}^{k}(\dfrac{3}{4})^{k}(\dfrac{1}{4})^{n-k}$，可知 $X\sim B(n,\dfrac{3}{4})$，则 $E(X)=\dfrac{3n}{4}$．",
            r"(3) 若 $m=0$，由 $P(X=0)=\dfrac{1}{4^{n}}$，$P(X=1)=\dfrac{3n}{4^{n}}$，$P(X=1)>P(X=0)$，矛盾．",
            r"若 $m=n$，由 $P(X=n-1)=\dfrac{n\cdot 3^{n-1}}{4^{n}}$，$P(X=n)=\dfrac{3^{n}}{4^{n}}$，可知：当 $n=2$ 时，满足 $P(X=n-1)<P(X=n)$；当 $n\geqslant 3$ 时，满足 $P(X=n-1)\geqslant P(X=n)$．",
            r"若 $1\leqslant m<n$，由 $\begin{cases}P(X=m)\geqslant P(X=m-1)\\ P(X=m)\geqslant P(X=m+1)\end{cases}$，即 $\begin{cases}\dfrac{C_{n}^{m}3^{m}}{4^{n}}\geqslant\dfrac{C_{n}^{m-1}3^{m-1}}{4^{n}}\\ \dfrac{C_{n}^{m}3^{m}}{4^{n}}\geqslant\dfrac{C_{n}^{m+1}3^{m+1}}{4^{n}}\end{cases}$，即 $\begin{cases}3C_{n}^{m}\geqslant C_{n}^{m-1}\\ C_{n}^{m}\geqslant 3C_{n}^{m+1}\end{cases}$，解得 $\dfrac{3n-1}{4}\leqslant m\leqslant\dfrac{3n+3}{4}$．",
            r"从而，$m=\begin{cases}E(X),n=4j;\\ E(X)+\dfrac{1}{4},n=4j+1;\\ E(X)+\dfrac{1}{2},n=4j+2;\\ E(X)-\dfrac{1}{4}\text{ 或 }E(X)+\dfrac{3}{4},n=4j+3.\end{cases}$ 其中 $j$ 为自然数．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
    {
        "题号": 19, "题型": "detailed_answer", "页码": [4],
        "题干": L(
            r"已知函数 $f(x)=|\ln x|+\dfrac{a}{x}(a\neq 0)$．",
            r"(1) 若 $a=1$，求 $f(x)$ 的最小值；",
            r"(2) 讨论 $f(x)$ 的单调性；",
            r"(3) 若 $f(x)$ 有且仅有三个不同零点为 $x_{1}$，$x_{2}$，$x_{3}$，证明：$x_{1}+x_{2}+x_{3}>\dfrac{2a^{2}-4a+1}{1-a}$．",
        ),
        "选项": {},
        "答案": L(
            r"(1) $f(x)$ 的最小值为 $1$；",
            r"(2) 当 $a\leqslant -1$ 时在 $(0,+\infty)$ 上递增；当 $-1<a<0$ 时在 $(0,-a)$、$(1,+\infty)$ 上递增，在 $(-a,1)$ 上递减；当 $0<a\leqslant 1$ 时在 $(0,1)$ 上递减、在 $(1,+\infty)$ 上递增；当 $a>1$ 时在 $(0,a)$ 上递减、在 $(a,+\infty)$ 上递增；",
            r"(3) 证得 $x_{1}+x_{2}+x_{3}>-2a+\dfrac{1-2a}{1-a}=\dfrac{2a^{2}-4a+1}{1-a}$．",
        ),
        "解析": L(
            r"函数 $f(x)$ 的定义域为 $(0,+\infty)$．当 $0<x<1$ 时，$f^{\prime}(x)=-\dfrac{1}{x}-\dfrac{a}{x^{2}}=-\dfrac{x+a}{x^{2}}$；当 $x\geqslant 1$ 时，$f^{\prime}(x)=\dfrac{1}{x}-\dfrac{a}{x^{2}}=\dfrac{x-a}{x^{2}}$．",
            r"(1) 若 $a=1$，当 $x\in(0,1]$ 时，$f(x)=-\ln x+\dfrac{1}{x}$，可得 $f(x)$ 单调递减；当 $x\in(1,+\infty)$ 时，$f^{\prime}(x)=\dfrac{x-1}{x^{2}}>0$，可得 $f(x)$ 单调递增．故 $f(x)$ 的最小值为 $1$．",
            r"(2) 当 $x\in(0,1)$ 时，若 $a\leqslant -1$，$f^{\prime}(x)>0$，则 $f(x)$ 单调递增．若 $-1<a<0$，当 $x\in(0,-a)$ 时，$x+a<0$，即 $f^{\prime}(x)>0$，则 $f(x)$ 单调递增；当 $x\in(-a,1)$ 时，$x+a>0$，即 $f^{\prime}(x)<0$，则 $f(x)$ 单调递减．若 $a>0$，$f^{\prime}(x)<0$，则 $f(x)$ 单调递减．",
            r"当 $x\in[1,+\infty)$ 时，若 $a<0$，$f^{\prime}(x)>0$，则 $f(x)$ 单调递增．若 $0<a\leqslant 1$，$f^{\prime}(x)>0$，则 $f(x)$ 单调递增．若 $a>1$，当 $x\in(1,a)$ 时，$f^{\prime}(x)<0$，则 $f(x)$ 单调递减；当 $x\in(a,+\infty)$ 时，$f^{\prime}(x)>0$，则 $f(x)$ 单调递增．",
            r"综上所述，当 $a\leqslant -1$ 时，$f(x)$ 在 $(0,+\infty)$ 上递增；当 $-1<a<0$ 时，$f(x)$ 在 $(0,-a)$ 上递增，在 $(-a,1)$ 上递减，在 $(1,+\infty)$ 上递增；当 $0<a\leqslant 1$ 时，$f(x)$ 在 $(0,1)$ 上递减，在 $(1,+\infty)$ 上递增；当 $a>1$ 时，$f(x)$ 在 $(0,a)$ 上递减，在 $(a,+\infty)$ 上递增．",
            r"(3) 若 $f(x)$ 有且仅有三个不同零点为 $x_{1}$，$x_{2}$，$x_{3}$．由 (2) 可知，必有 $-1<a<0$，假设 $x_{1}<x_{2}<x_{3}$，且 $0<x_{1}<-a<x_{2}<1<x_{3}$．",
            r"当 $x\to 0$ 时，$f(x)=\dfrac{-x\ln x+a}{x}\to-\infty$；当 $x\to+\infty$ 时，$f(x)=\ln x+\dfrac{a}{x}\to+\infty$．由 $f(x)_{\text{极小值}}=f(1)=a<0$，$f(x)_{\text{极大值}}=f(-a)=-\ln(-a)-1>0$，解得 $-\dfrac{1}{\mathrm{e}}<a<0$．",
            r"先证不等式：$x_{1}+x_{2}>-2a$．",
            r"由 $-\ln x_{1}+\dfrac{a}{x_{1}}=-\ln x_{2}+\dfrac{a}{x_{2}}$，可得 $a=\dfrac{x_{1}x_{2}}{x_{2}-x_{1}}\ln\dfrac{x_{1}}{x_{2}}$，则只需证：$\dfrac{x_{1}+x_{2}}{2}>-\dfrac{x_{1}x_{2}}{x_{2}-x_{1}}\ln\dfrac{x_{1}}{x_{2}}$，即证：$\ln\dfrac{x_{1}}{x_{2}}>\dfrac{1}{2}(\dfrac{x_{1}}{x_{2}}-\dfrac{x_{2}}{x_{1}})$．",
            r"令 $t=\dfrac{x_{1}}{x_{2}}$，则 $0<t<1$，不等式转化为证明 $\ln t>\dfrac{1}{2}(t-\dfrac{1}{t})$．",
            r"令 $g(t)=\ln t-\dfrac{1}{2}(t-\dfrac{1}{t})(0<t<1)$，则 $g^{\prime}(t)=\dfrac{1}{t}-\dfrac{1}{2}-\dfrac{1}{2t^{2}}=\dfrac{-(t-1)^{2}}{2t^{2}}<0$，可得 $g(t)$ 在 $(0,1)$ 上单调递减，有 $g(t)>g(1)=0$，即 $\ln t>\dfrac{1}{2}(t-\dfrac{1}{t})$ 成立．",
            r"再证明不等式：$x_{3}>\dfrac{1-2a}{1-a}$．",
            r"由于 $x_{3}>\dfrac{1-2a}{1-a}=1-\dfrac{a}{1-a}>1$，且 $f(x)$ 在 $(1,+\infty)$ 上单调递增，则只需证：$f(\dfrac{1-2a}{1-a})<0$．",
            r"令 $\varphi(x)=\ln x-x+1(x>1)$，则 $\varphi^{\prime}(x)=\dfrac{1}{x}-1=\dfrac{1-x}{x}<0$，可得 $\varphi(x)<\varphi(1)=0$，即 $\ln x<x-1$．而 $f(\dfrac{1-2a}{1-a})=\ln\dfrac{1-2a}{1-a}+\dfrac{(1-a)a}{1-2a}<\dfrac{1-2a}{1-a}-1+\dfrac{(1-a)a}{1-2a}=\dfrac{a^{3}}{(1-a)(1-2a)}<0$，则 $x_{3}>\dfrac{1-2a}{1-a}$．",
            r"综上，可得 $x_{1}+x_{2}+x_{3}>-2a+\dfrac{1-2a}{1-a}=\dfrac{2a^{2}-4a+1}{1-a}$．",
        ),
        "粗筛图": False, "粗筛表": False,
    },
]

pending = [
    {
        "题号": 8, "题型": "single_choice", "页码": [2], "类型": "figure-in-solution",
        "原文": r"设 $f(x)=\sqrt{2}\sin\dfrac{\pi}{8}x+5.5(x\in[4,12])$，则 $f^{\prime}(x)=\dfrac{\sqrt{2}\pi}{8}\cos\dfrac{\pi}{8}x$．当方程（*）对应的直线与曲线 $y=f(x)$ 相切时，$d$ 达到最大值．",
        "说明": L(
            r"题干纯文字（函数型应用题），已进成品，解析也整段录入。这里登记的是解析内部的图：参考答案 PDF 第 1 页（卷面答案第 1 页）#8 解析在写完「$y=d+1.5-\dfrac{\pi}{8}(x-4)(x\geqslant 4)$（*）」之后，随文配一张无图号示意图：平面直角坐标系，$y$ 轴标 $5.5$，$x$ 轴标 $0$、$4$、$10$、$12$；一条正弦曲线标注 $y=\sqrt{2}\sin(\dfrac{\pi}{8}x)+5.5$，另一条自左上向右下倾斜的直线标注 $y=-\dfrac{\pi}{8}(x-4)+1.5+d$，直线与曲线在 $x=10$ 附近相切，$x=4$、$10$、$12$ 处各画一条竖直细线连到曲线上。解析「当方程（*）对应的直线与曲线 $y=f(x)$ 相切时，$d$ 达到最大值」这一步依赖该图。答案 C，$5.35\ \mathrm{m}$。交人工把图补进解析。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 11, "题型": "multi_choice", "页码": [2], "类型": "figure-in-solution",
        "原文": r"如下两图所示，过点 $M$，作直线 $x=4$ 的垂线，垂足为 $H_{1}$，作准线 $x=-\dfrac{1}{2}$ 的垂线，垂足为 $H_{2}$；过点 $N$，作直线 $x=4$ 的垂线，垂足为 $H_{3}$，作准线 $x=-\dfrac{1}{2}$ 的垂线，垂足为 $H_{4}$．",
        "说明": L(
            r"题干纯文字，已进成品，解析整段录入。这里登记解析内部的两张图：参考答案 PDF 第 2 页（卷面答案第 2 页）#11 解析中段并排印着左右两张无图号配图，两张都是同一套元素——平面直角坐标系中开口向右的抛物线 $E:y^{2}=2x$、圆心在 $x$ 轴正半轴的圆 $C$、切线 $l$ 与交点 $M$（上半支）、$N$（下半支）、切点 $P$、焦点 $F$、原点 $O$，以及两条竖直虚线分别标注 $x=4$（左图把标签印在虚线下端，右图印在下端）与准线 $x=-\dfrac{1}{2}$；水平虚线从 $M$、$N$ 引到两条竖直线上，垂足依次标 $H_{1}$、$H_{2}$、$H_{3}$、$H_{4}$。左图点 $P$ 在直线 $x=4$ 左侧（对应选项 C），右图点 $P$ 在其右侧（对应选项 D）。解析 B、C、D 三项的判断全部靠这两张图（「根据左图……」「如右图……」）。答案 AC。交人工把两图补进解析。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 14, "题型": "fill_in_blank", "页码": [3], "类型": "figure-in-solution",
        "原文": r"如图所示，由题意可知，点 $A$ 在以 $BC$ 为直径的截面圆 $O^{\prime}$ 上运动，则 $AB^{2}+AC^{2}=4$，可得 $S_{\triangle ABC}=\dfrac{1}{2}AB\cdot AC\leqslant\dfrac{1}{4}(AB^{2}+AC^{2})=1$，当且仅当 $AB=AC=\sqrt{2}$ 时取等号．",
        "说明": L(
            r"题干纯文字，已进成品，解析整段录入。这里登记解析内部的图：参考答案 PDF 第 3 页（卷面答案第 3 页）#14 解析在「如图所示」之后配一张无图号立体图：一个球（外轮廓圆 + 一条水平椭圆表示球内截面），球心标 $O$；球面上四点 $A$（左）、$B$（下）、$C$（右下靠前）、$D$（顶部），$BC$ 所在的小圆上标 $O^{\prime}$，$A$ 处画直角符号，$AB$、$AC$、$BC$ 与 $DA$、$DB$、$DC$ 连成四面体，$DH\perp$ 平面 $ABC$ 的垂足标 $H$（$H$ 在 $AO^{\prime}$ 上），另用绿色虚线画出点 $D$ 的轨迹圆并标出 $E$。解析「点 $D$ 的轨迹是以直线 $OA$ 为中心轴的圆锥与该球面的截面圆 $E$」「垂足 $H$ 必在 $AO^{\prime}$ 上」这两步依赖该图。答案 $\dfrac{3+\sqrt{3}}{6}$。交人工把图补进解析。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3], "类型": "figure",
        "原文": L(
            r"如图，在三棱锥 $P-ABC$ 中，平面 $PAC\perp$ 平面 $ABC$，$\triangle PAC$ 是边长为 $2$ 的等边三角形，$AB=2\sqrt{2}$，$\angle BAC=45^{\circ}$．",
            r"(1) 证明：$BC\perp PA$；",
            r"(2) 若线段 $PC$ 上的点 $Q$ 满足直线 $AP$ 与直线 $BQ$ 所成角的余弦值为 $\dfrac{\sqrt{5}}{10}$，求点 $Q$ 到直线 $AB$ 的距离．",
        ),
        "说明": L(
            r"题干以「如图」起头，试卷卷面第 3 页（PDF 第 5 页）#16 随题印着配图（无图号）：三棱锥 $P-ABC$，$P$ 在顶部、$C$ 在中、$B$ 在右、$A$ 在左下，$PA$、$PB$、$AB$、$BC$ 画实线，$PC$、$AC$ 画虚线（被遮挡）。按规矩不录正文，故本题未进成品。",
            r"参考答案给的全解析结果（PDF 第 4 页 / 卷面答案第 4 页）：(1) 在 $\triangle ABC$ 中由余弦定理得 $BC^{2}=AC^{2}+AB^{2}-2AB\cdot AC\cos 45^{\circ}=4$，即 $BC=2$，有 $BC^{2}+AC^{2}=AB^{2}$，故 $BC\perp AC$；又平面 $PAC\perp$ 平面 $ABC$、交线为 $AC$、$BC\subset$ 平面 $ABC$，得 $BC\perp$ 面 $PAC$，而 $PA\subset$ 平面 $PAC$，所以 $BC\perp PA$。(2) 取 $AC$、$AB$ 中点 $O$、$M$，连 $OP$、$OM$，以 $O$ 为原点、$\overrightarrow{OA}$、$\overrightarrow{OM}$、$\overrightarrow{OP}$ 为 $x$、$y$、$z$ 轴正方向建系（标答另配一张无图号建系图，图上标 $P$、$C$、$O$、$M$、$B$、$A$ 与 $x$、$y$、$z$ 三轴），得 $A(1,0,0)$、$C(-1,0,0)$、$B(-1,2,0)$、$P(0,0,\sqrt{3})$，设 $\overrightarrow{CQ}=\lambda\overrightarrow{CP}=(\lambda,0,\sqrt{3}\lambda)(0\leqslant\lambda\leqslant 1)$，解得 $\lambda=\dfrac{1}{2}$（另一根 $-\dfrac{1}{2}$ 舍），$Q(-\dfrac{1}{2},0,\dfrac{\sqrt{3}}{2})$，故点 $Q$ 到直线 $AB$ 的距离 $d=\sqrt{|\overrightarrow{AQ}|^{2}-(\dfrac{\overrightarrow{AQ}\cdot\overrightarrow{AB}}{|\overrightarrow{AB}|})^{2}}=\sqrt{3-\dfrac{9}{8}}=\dfrac{\sqrt{30}}{4}$。",
            r"标答 (2) 里那一步数量积与它自己给的坐标对不上，已另登 print-suspect（见下一条）。交人工把两张图补进成品。—— 不是缺题，切勿据此删题。",
        ),
    },
    {
        "题号": 16, "题型": "detailed_answer", "页码": [3], "类型": "print-suspect",
        "原文": r"$\cos<\overrightarrow{AP},\overrightarrow{BQ}>=\dfrac{\overrightarrow{AP}\cdot\overrightarrow{BQ}}{|\overrightarrow{AP}|\cdot|\overrightarrow{BQ}|}=\dfrac{2\lambda}{2\times\sqrt{4\lambda^{2}+4}}$．由 $|\cos<\overrightarrow{AP},\overrightarrow{BQ}>|=\dfrac{\sqrt{5}}{10}$，解得 $\lambda=\dfrac{1}{2}$ 或 $\lambda=-\dfrac{1}{2}$（舍）",
        "说明": L(
            r"参考答案 PDF 第 4 页（卷面答案第 4 页）#16 (2) 这一行的分子印作 $2\lambda$，但与它自己上一行给的坐标不自洽：按 $A(1,0,0)$、$P(0,0,\sqrt{3})$ 得 $\overrightarrow{AP}=(-1,0,\sqrt{3})$，按 $B(-1,2,0)$、$Q(\lambda-1,0,\sqrt{3}\lambda)$ 得 $\overrightarrow{BQ}=(\lambda,-2,\sqrt{3}\lambda)$，两者数量积应为 $-\lambda+3\lambda^{2}=3\lambda^{2}-\lambda$，不是 $2\lambda$。",
            r"后果：把 $\lambda=\dfrac{1}{2}$ 代回 $3\lambda^{2}-\lambda$ 得 $\dfrac{1}{4}$，此时夹角余弦为 $\dfrac{1/4}{2\times\sqrt{5}}=\dfrac{\sqrt{5}}{40}$，与题设 $\dfrac{\sqrt{5}}{10}$ 不符；也就是说 $\lambda=\dfrac{1}{2}$ 只有按分子 $2\lambda$ 才成立。反过来，若按 $3\lambda^{2}-\lambda$ 解 $|\cos|=\dfrac{\sqrt{5}}{10}$，得 $45\lambda^{4}-30\lambda^{3}+\lambda^{2}-4=0$，在 $[0,1]$ 上的根约为 $0.807$，不是有理数，后续 $Q$ 点坐标、$\overrightarrow{AQ}=(-\dfrac{3}{2},0,\dfrac{\sqrt{3}}{2})$ 与末答 $d=\dfrac{\sqrt{30}}{4}$ 都不成立。",
            r"末答 $d=\dfrac{\sqrt{30}}{4}$ 本身按 $\lambda=\dfrac{1}{2}$ 那组数据是自洽的（$|\overrightarrow{AQ}|^{2}=3$、$\dfrac{(\overrightarrow{AQ}\cdot\overrightarrow{AB})^{2}}{|\overrightarrow{AB}|^{2}}=\dfrac{9}{8}$、$\sqrt{3-\dfrac{9}{8}}=\dfrac{\sqrt{30}}{4}$），所以疑点集中在「$2\lambda$ 这一处数量积算错（或 $\overrightarrow{BQ}$、$\overrightarrow{AP}$ 中某个坐标印错）」，而不是整题作废。按「内容一个字都不许改」，此处照标答原样登记 $2\lambda$，没有替它改成 $3\lambda^{2}-\lambda$、也没有改坐标。本题因带图未进成品，登在此处供人工判断。",
        ),
    },
]

(OUT / (NAME + ".成品.json")).write_text(
    json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
(OUT / (NAME + ".待复核.json")).write_text(
    json.dumps(pending, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("成品", len(recs), "待复核", len(pending))
