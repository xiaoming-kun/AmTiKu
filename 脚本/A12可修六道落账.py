"""A12 里能修回来的 6 道：把「托词」换成真正的答案。

每道都满足：我自己重算过 + （能回源的）回过原卷或外部来源，
并且新题干要过 `$` 成对、槽位往返、XeLaTeX 编译三道检查才写台账。
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/Users/ximing/Documents/AmTiKu")
from amti import latex_ir, store

LEDGER = Path("/Users/ximing/Documents/AmTiKu/数据/订正台账.json")
import json

SRC = "大模型逐题重算 + 回原卷/权威来源核对"

# key -> (新答案, 新题干 or None, 新解析 or None, 依据)
FIX = {
    "高考真题汇编/2002/北京卷（秋理）#13": (
        r"$\arccos\left(-\frac{3}{4}\right)>\arcsin\left(-\frac{2}{5}\right)"
        r">\arctan\left(-\frac{5}{4}\right)$", None,
        r"三个数都在各自主值区间内，可直接定序。"
        r"$\arccos\left(-\frac{3}{4}\right)\in\left(\frac{\pi}{2},\pi\right)$ 为正；"
        r"另两个为负。设 $\alpha=\arcsin\frac{2}{5}$，$\beta=\arctan\frac{5}{4}$，"
        r"则 $\tan\alpha=\frac{2}{\sqrt{21}}<\frac{5}{4}=\tan\beta$，故 $\alpha<\beta$，"
        r"从而 $-\beta<-\alpha$，即 $\arctan\left(-\frac{5}{4}\right)<\arcsin\left(-\frac{2}{5}\right)$。"
        r"所以从小到大为 $\arctan\left(-\frac{5}{4}\right)<\arcsin\left(-\frac{2}{5}\right)"
        r"<\arccos\left(-\frac{3}{4}\right)$。",
        "题面三式全部有定义（|-2/5|≤1、|-3/4|≤1、arctan 定义域为 R），"
        "原「题面不成立」是误判；库内解析本身已推出正确排序"),

    "高考真题汇编/2002/北京卷（秋理）#16": (
        r"$2\sqrt{2}$",
        r"已知 $P$ 是直线 $3x+4y+8=0$ 上的动点，$PA$，$PB$ 是圆 $x^{2}+y^{2}-2x-2y+1=0$ "
        r"的两条切线，$A$，$B$ 是切点，$C$ 是圆心，那么四边形 $PACB$ 面积的最小值为"
        r"\fillin[$2\sqrt{2}$]。",
        r"配方得 $(x-1)^{2}+(y-1)^{2}=1$，圆心 $C(1,1)$、半径 $r=1$。"
        r"$C$ 到直线 $3x+4y+8=0$ 的距离 $d=\frac{|3+4+8|}{5}=3>r$，故 $C$ 在直线外。"
        r"切线长 $|PA|=\sqrt{|PC|^{2}-r^{2}}$，四边形 $PACB$ 由两个全等的直角三角形拼成，"
        r"面积 $S=r\cdot|PA|=\sqrt{|PC|^{2}-1}$。$|PC|$ 的最小值即 $d=3$，"
        r"所以 $S_{\min}=\sqrt{9-1}=2\sqrt{2}$。",
        "库内圆方程常数印成 8，配方得 $(x-1)^2+(y-1)^2=-6$ 不表示实圆，题面必错；"
        "据权威题库同一条目（直线 3x+4y+8=0 与切线四边形面积）圆为 x²+y²-2x-2y+1=0，答案 2√2"),

    "2027千题册创新拔高册（下）_images/164#26": (
        r"$\frac{27}{70}$", None,
        r"闭合开关的先后顺序等可能，即 $S_1,\dots,S_7$ 的一个随机排列。"
        r"三条支路分别需 $\{S_1,S_2\}$、$\{S_3,S_4,S_5\}$、$\{S_6,S_7\}$ 全部闭合才亮，"
        r"记三者闭合完成的时刻为 $T_1,T_2,T_3$。求 $P(T_1<T_2$ 且 $T_1<T_3)$。"
        r"按「三组开关各占哪几个时刻」计数，共 $\binom{7}{2}\binom{5}{3}=210$ 种等可能分法，"
        r"其中满足条件的 $81$ 种，故概率 $\frac{81}{210}=\frac{27}{70}$。"
        r"（对 $7!=5040$ 个排列直接穷举，同样得 $1944$ 个有利排列，$\frac{1944}{5040}=\frac{27}{70}$。）",
        "配图 960402d5c7768afb.png 实际存在（原「图片未提供」为误判）；"
        "两种独立枚举（210 位置组合 / 5040 全排列）一致"),

    "2027千题册创新拔高册（下）_images/168#34": (
        r"$\frac{5}{11}$", None,
        r"把网格点取为坐标，$A(0,0)$、$B(5,5)$、$C(4,2)$。"
        r"第三横行带（$y=2$ 到 $y=3$）中间的竖线没画，只能沿 $x=0,1,4,5$ 四条竖线下来。"
        r"最短走法即每次向右或向下：$\sum_{x\in\{0,1,4,5\}}\binom{x+2}{2}\binom{7-x}{2}"
        r"=21+45+45+21=132$ 种。"
        r"经过 $C(4,2)$ 的：$A\to C$ 为 $\binom{6}{2}=15$ 种，$C\to B$ 只能在 $x=4$ 或 $x=5$ 下行，"
        r"为 $4$ 种，共 $60$ 种。故概率 $\frac{60}{132}=\frac{5}{11}$。",
        "配图 a4b5e51a7adee42a.png 实际存在；竖线缺哪两条由像素覆盖率实测（带2: 1.00 1.00 0.00 0.00 1.00 1.00），"
        "132 与 60 各用递归计数和闭式两法对上账"),

    "模拟题/2026届辽宁名校联盟高三10月份联合考试-（含）#13": (
        r"$\sqrt{2}$",
        r"已知向量 $\boldsymbol{a}, \boldsymbol{b}$ 的夹角为 $\frac{\pi}{4}$，若 $|\boldsymbol{a}|=2$，"
        r"且 $\boldsymbol{a}-\boldsymbol{b}$ 在 $\boldsymbol{a}$ 上的投影向量为 "
        r"$\frac{1}{2}\boldsymbol{a}$，则 $|\boldsymbol{b}|=$ \fillin[$\sqrt{2}$]。",
        r"投影向量的定义给出 $\frac{(\boldsymbol{a}-\boldsymbol{b})\cdot"
        r"\boldsymbol{a}}{|\boldsymbol{a}|^{2}}\boldsymbol{a}=\frac{1}{2}\boldsymbol{a}$，"
        r"故 $(\boldsymbol{a}-\boldsymbol{b})\cdot\boldsymbol{a}=\frac{1}{2}|\boldsymbol{a}|^{2}=2$。"
        r"于是 $|\boldsymbol{a}|^{2}-\boldsymbol{a}\cdot\boldsymbol{b}=2$，得 "
        r"$\boldsymbol{a}\cdot\boldsymbol{b}=4-2=2$。"
        r"再由 $\boldsymbol{a}\cdot\boldsymbol{b}=|\boldsymbol{a}||\boldsymbol{b}|\cos\frac{\pi}{4}"
        r"=2|\boldsymbol{b}|\cdot\frac{\sqrt{2}}{2}=\sqrt{2}|\boldsymbol{b}|=2$，"
        r"所以 $|\boldsymbol{b}|=\sqrt{2}$。",
        "原答案栏是页眉「· 数学 ·/参考答案及解析」、解析栏整条是别题的（$f(x)=x^2+2x+1$）；"
        "「在 $\\mathbb{R}$ 上的投影向量」不成话（投影要相对一个向量），按 $\\boldsymbol{a}$ 解得唯一 |b|=√2，"
        "数值扫 1.2/1.414214/1.6/2.0 只有 √2 使投影恰为 a/2"),

    "模拟题/深圳中学2025年12月高三第二次阶段测试#14": (
        r"$\left(0,\frac{3}{2e^{2}}\right)$",
        r"函数 $f(x)=x(\ln x-ax)-\frac{e^2}{2}$ 有两个零点，则实数 $a$ 的取值范围为 "
        r"\fillin[$\left(0,\frac{3}{2e^{2}}\right)$]。",
        r"$f(x)=0$（$x>0$）等价于 $a=\frac{\ln x}{x}-\frac{e^{2}}{2x^{2}}\triangleq g(x)$。"
        r"$g'(x)=\frac{x(1-\ln x)+e^{2}}{x^{3}}$，令 $h(x)=x-x\ln x+e^{2}$，"
        r"$h'(x)=-\ln x$，故 $h$ 在 $(0,1)$ 增、$(1,+\infty)$ 减，且 $h(e^{2})=e^{2}-2e^{2}+e^{2}=0$，"
        r"于是 $g$ 在 $(0,e^{2})$ 单调递增、$(e^{2},+\infty)$ 单调递减，"
        r"最大值 $g(e^{2})=\frac{2}{e^{2}}-\frac{1}{2e^{2}}=\frac{3}{2e^{2}}$。"
        r"又 $x\to0^{+}$ 时 $g(x)\to-\infty$，$x\to+\infty$ 时 $g(x)\to0^{+}$。"
        r"所以水平线 $y=a$ 与 $y=g(x)$ 有两个交点当且仅当 $0<a<\frac{3}{2e^{2}}$；"
        r"$a=\frac{3}{2e^{2}}$ 时相切只有一个零点，$a\leqslant0$ 时也只有一个。",
        "原答案栏是下一大题的标题「[解答题详解及评分标准]」；解析推导本身是对的，"
        "数值扫零点数：a=0.02→2 个、a=3/(2e²)→重根 1 个、a=0.21→0 个、a=0→1 个，两端都取不到"),
}


def compile_ok(stem: str) -> bool:
    # ⚠️ 必须给 graphicspath：带配图的题在临时目录里编译会报
    #    「Unable to load picture」——那是**检查方法**缺图，不是题干坏了。
    #    第一版就是这么把两道好题误判成编译失败的。
    doc = ("\\documentclass{article}\\usepackage{amsmath,amssymb,graphicx,bm}\n"
           "\\graphicspath{{/Users/ximing/Documents/AmTiKu/图片/}}\n"
           "\\newcommand{\\fillin}[1]{\\underline{#1}}\\newcommand{\\paren}[1]{\\underline{#1}}\n"
           "\\begin{document}\n" + stem + "\n\\end{document}")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "t.tex").write_text(doc, encoding="utf-8")
        p = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
                           cwd=td, capture_output=True, text=True)
        if p.returncode != 0:
            tail = [l for l in p.stdout.splitlines() if l.startswith("!")]
            print("     编译报错:", tail[:3])
        return p.returncode == 0


led = json.loads(LEDGER.read_text(encoding="utf-8"))
idx = {p["key"]: i for i, p in enumerate(led["patches"])}
by_key = {q.key: q for q in store.load_all()}
added = upd = 0
for key, (ans, stem, sol, why) in FIX.items():
    q = by_key.get(key)
    if q is None:
        print("!! 题库里没有", key)
        continue
    new_stem = stem if stem else q.stem
    # 槽位与答案同源
    if not stem:
        hits = list(re.finditer(r"\\(?:paren|fillin)(?![a-zA-Z])\s*(?=\[)", new_stem))
        m = hits[-1]
        j = m.end()
        val, end = latex_ir.bracket_arg(new_stem, j)
        new_stem = new_stem[:j] + "[" + ans + "]" + new_stem[end:]
    assert new_stem.count("$") % 2 == 0, (key, "美元符不成对")
    got = latex_ir.fillin_answers(new_stem)
    if not got or got[-1] != ans:
        print("!! 槽位往返失败", key, got, "期望", ans)
        continue
    if not compile_ok(new_stem):
        print("!! 编译失败", key)
        continue
    ent = {"key": key, "why": why, "src": SRC,
           "expect": {"answer": q.answer, "stem": q.stem},
           "set": {"answer": ans, "stem": new_stem}}
    if sol:
        ent["expect"]["solution"] = q.solution
        ent["set"]["solution"] = sol
    if key in idx:
        led["patches"][idx[key]] = ent
        upd += 1
    else:
        led["patches"].append(ent)
        added += 1
    print(f"  ✓ {key}  →  {ans[:34]}")

print(f"台账：新增 {added}、覆盖 {upd}（现共 {len(led['patches'])} 条）")
LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")
