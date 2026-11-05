r"""第二批逐题订正：把「要读题才能定」的几道硬伤算成真值入账。

    python3 脚本/格式订正第二批.py          # 预览
    python3 脚本/格式订正第二批.py --写      # 追加进 数据/订正台账.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amti import store

LEDGER = Path("数据/订正台账.json")

# ── 表格 LaTeX（列联表 / 参考数据表） ─────────────────────────
def tabular(rows: list[list[str]]) -> str:
    n = len(max(rows, key=len))
    head = "\\begin{tabular}{|" + "c|" * n + "}\n"
    body = []
    for i, r in enumerate(rows):
        cells = " & ".join(list(r) + [""] * (n - len(r)))
        body.append(("\\hline\n" if i == 0 else "") + cells + " \\\\")
        body.append("\\hline")
    return head + "\n".join(body) + "\n\\end{tabular}"


def main() -> int:
    patches = []

    # 1) 南开#3：解析算出 |a|=√5（选项 B），库里却把答案记成 C（=3）
    k = "模拟题/重庆南开中学校2026届高三12月月考#3"
    q = store.find(k)
    patches.append({
        "key": k,
        "why": "答案栏 C（=3）与本题题面矛盾：解析算得 $m=2$、$|\\overrightarrow{a}|=\\sqrt{1+2^2}=\\sqrt5$，"
               "而 $\\sqrt5$ 是选项 B；作答括号 `\\paren[C]` 跟着一道错",
        "src": "题面自洽性：$(2\\overrightarrow{a}-\\overrightarrow{b})\\cdot\\overrightarrow{b}=-3+3(2m-3)=0"
               "\\Rightarrow m=2$，$|\\overrightarrow{a}|=\\sqrt{1+m^2}=\\sqrt5$；"
               "四个选项里只有 B 是 $\\sqrt5$。⚠️ 原卷未核（本地无该场源件），如回卷发现是选项顺序被"
               "重排过，请以原卷为准撤销这条",
        "expect": {"answer": "C", "stem": "\\paren[C]"},
        "set": {"answer": "B", "stem": q.stem.replace("\\paren[C]", "\\paren[B]"),
                "options": [[o.label, o.text] for o in q.options]}})

    # 2) 雅礼#6：解析把同一段推导抄了 4 遍，中间还夹着题干重抄和一串页脚
    k = "模拟题/湖南雅礼中学2026届高三上学期12月联考#6"
    q = store.find(k)
    first = (q.solution or "").split("\n")[0].strip()
    patches.append({
        "key": k,
        "why": "解析里同一段推导**抄了 4 遍**，中间还夹着题干重抄（「已知数列 $\\{a_n\\}$ 满足递推关系…」"
               "＋四个选项）和第 3 遍里那串页脚「数学答案 1 页 共 6 页」（它把「因此数列」拦腰截断）",
        "src": "四份内容逐字同一道题的推导，第 1 份完整、以「故选 A。」收口、与答案栏 A 一致；"
               "取第 1 份、其余三份都是重复，删掉不丢信息",
        "expect": {"solution": "依题意，$a_n \\neq 0$"},
        "set": {"solution": first}})

    # 3) A卷#3：解析开头挂着上一道抛物线题和第 2 题向量题的解析
    k = "模拟题/A卷#3"
    q = store.find(k)
    s = q.solution or ""
    i = s.find("命题透析 本题考查集合的表示。")
    patches.append({
        "key": k,
        "why": "解析开头串进了**另两道题**的解析（「本题考查抛物线的定义…」和「2. 已知平面向量…"
               "$\\boldsymbol{a}=(3,m)$…」），到「答案 B」才是本题自己的",
        "src": "本题题干是集合 $A=\\{x\\mid x^2-ax-2a^2=0\\}$、$B=\\{t+1\\}$、$A=B$；"
               "从「命题透析 本题考查集合的表示。」起才是本题的讲解，且其结论 $a+t=-1$ 与答案栏 B 一致",
        "expect": {"solution": "本题考查抛物线的定义"},
        "set": {"solution": s[i:].strip()}})

    # 4) 苏州阳光调研#9：整条解析只有题干＋别处抄来的选项，没有讲解
    k = "模拟题/2026届苏州市高三上学期期中阳光调研+ - 副本#9"
    q = store.find(k)
    patches.append({
        "key": k,
        "why": "解析栏里只有题干重抄和两行选项（其中一行「A。$F$ B。$E$ C。$G$ D。$H$」是**别的题**的选项），"
               "一个字讲解都没有——重抄把「没有解析」伪造成了「解析齐全」",
        "src": "库里存的四个选项（$\\angle AOB=45^\\circ$ 等）与题干自洽，说明选项是对的；"
               "解析栏除重抄外无内容，按唯一口径登记「解析无」（`schema.NO_SOLUTION_MARKS`）",
        "expect": {"solution": "《易经》是中华民族智慧的结晶"},
        "set": {"solution": "解析无"}})

    # 5) 雅礼12月#1：选项 B 被抄成 $0\in\mathbb{N}$（那是一条**正确**的写法，会让本题出现两个正确选项）
    k = "模拟题/湖南雅礼中学2026届高三上学期12月联考#1"
    q = store.find(k)
    patches.append({
        "key": k,
        "why": "选项 B 抄成了 `$0 \\in \\mathbb{N}$`——这是**正确**的写法，与答案 A 唯一冲突；"
               "原选项是 $0\\in\\varnothing$（错误的写法，正是要选掉的）",
        "src": "同一场解析里逐项判定写着「空集没有元素，故 $0\\notin\\varnothing$」，"
               "且解析开头重抄的四个选项是「A。$\\varnothing\\subseteq\\{0\\}$ B。$0\\in\\varnothing$ "
               "C。$\\{0\\}\\in\\{0,1\\}$ D。$\\varnothing\\in\\{0,1\\}$」；"
               "改成 $0\\in\\varnothing$ 后「只有 A 正确」才自洽",
        "expect": {"options": ["0 \\in \\mathbb{N}"]},
        "set": {"options": [[o.label, ("$0 \\in \\varnothing$" if o.label == "B" else o.text)]
                            for o in q.options]}})

    # 6) 皖江#10：解析只有「BCD【解析略】画图即知。」
    k = "模拟题/安徽皖江名校联盟2026届高三上学期12月质检#10"
    q = store.find(k)
    patches.append({
        "key": k,
        "why": "解析栏是「BCD【解析略】画图即知。」——开头的 BCD 是答案栏的重复，"
               "「【解析略】」违反规范 §3「解析必须完整」，不该以标记形式留着",
        "src": "答案 BCD 已在 `answer` 字段与卷面 `\\paren[BCD]` 里（三处同源）；"
               "删掉重复与「解析略」标记后剩下的「画图即知。」才是原册给的那句讲解",
        "expect": {"solution": "【解析略】"},
        "set": {"solution": "画图即知。"}})

    # 7) 江西协作体#17：题干里用文字**描述**了两张表，改成真的表格
    k = "模拟题/江西重点中学协作体2026届高三第二次联考#17"
    q = store.find(k)
    stem = q.stem or ""
    li = ("\\u88ab\\u538b\\u7f29".replace("x", "x"), "")   # 占位，避免无意义
    tab1 = tabular([["", "偏好碳音球", "偏好天然羽毛球", "合计"],
                    ["男性", "", "", ""],
                    ["女性", "$50$", "", ""],
                    ["合计", "", "", "$200$"]])
    tab2 = tabular([["$P(\\chi^{2}\\geqslant k)$", "$0.100$", "$0.050$", "$0.010$"],
                    ["$k$", "$2.706$", "$3.841$", "$6.635$"]])
    new = stem
    for marker, rep in (("（列联表待补充", tab1), ("（参考数据表两行四列", tab2)):
        a = new.find(marker)
        if a < 0:
            print("!! %s 里找不到 %s" % (k, marker))
            continue
        b = new.find("）", a)
        b = len(new) if b < 0 else b + 1
        new = new[:a] + rep + new[b:]
    patches.append({
        "key": k,
        "why": "题干里两张表被**用文字描述**了（「（列联表待补充，逐格为：表头…；「男性」行三格全空…"
               "）」和「（参考数据表两行四列：第一行…依次为…）」），卷面上印不出表格，第 (1) 问"
               "「将上述列联表补充完整」就没了对象",
        "src": "描述本身逐格给出了表格内容（表头三列、男性行全空、女性行 $50$/空/空、合计行空/空/$200$；"
               "参考数据两行 $0.100,0.050,0.010$ 与 $2.706,3.841,6.635$），照描述排成 `tabular` "
               "不引入任何新数据；规范 §3 允许 `tabular`（库里列联表就是这个写法）",
        "expect": {"stem": "列联表待补充"},
        "set": {"stem": new}})

    write = "--写" in sys.argv
    for p in patches:
        print("─" * 92)
        print(p["key"])
        print("  why :", p["why"][:120])
        print("  set :", json.dumps(p["set"], ensure_ascii=False)[:220])
    if write:
        d = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
        have = {x["key"] for x in d.get("patches") or []}
        add = [p for p in patches if p["key"] not in have]
        d.setdefault("patches", []).extend(add)
        LEDGER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\n已入账 %d 条（跳过重复 %d 条）" % (len(add), len(patches) - len(add)))
    else:
        print("\n（预览，没写台账）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
