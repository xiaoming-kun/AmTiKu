r"""把 2026-10-28 全库格式体检里**一道一个样**的坏形，写成 `数据/订正台账.json` 的条目。

每条的 `expect`（改前现状）和 `set`（改成什么）都**从现库真值算出来**，不手抄，
抄了就会错（规范审查里那些「逐字比对被脏尾巴污染」的坑都是手抄出来的）。

    python3 脚本/格式订正入账.py            # 只打印将要入账的条目
    python3 脚本/格式订正入账.py --写        # 追加进台账（不改题库）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amti import store
from amti.schema import Option

LEDGER = Path("数据/订正台账.json")

# ── 订正表：(题号, 为什么改, 凭据, [(字段, 旧子串, 新子串), …]) ─────────
# 字段为 `options` 时，旧/新子串是给四个选项的**整表**（列表）。
SUBS = [
    ("模拟题/江浙皖高中（县中）发展共同体2026届高三上学期10月联考#8",
     "选项 B/C/D 被 OCR 弄成 `\\sqrt[3]{2}`（立方根），B 与 D 完全相同、无法作答",
     "同一场的解析里留着录入原文的四个选项（两处）：B 为 $-5\\sqrt2\\le m\\le 3\\sqrt2$、"
     "C 为 $-3\\sqrt2\\le m\\le 5\\sqrt2$、D 为 $-3\\sqrt2\\le m\\le 3\\sqrt2$；"
     "题面自洽性复核：$|AB|=\\sqrt2$ 且 $\\overrightarrow{PA}=\\tfrac34\\overrightarrow{PB}$ "
     "$\\Rightarrow |PA|=3\\sqrt2,|PB|=4\\sqrt2$，幂 $=|PC|^2-1=24\\Rightarrow |PC|=5$，"
     "故 $\\frac{|2-2+m|}{\\sqrt2}\\le5\\Rightarrow |m|\\le5\\sqrt2$，与库里答案 A 吻合",
     [("options", None, [
         ("A", r"$-5\sqrt{2}\leq m\leq5\sqrt{2}$"),
         ("B", r"$-5\sqrt{2}\leq m\leq3\sqrt{2}$"),
         ("C", r"$-3\sqrt{2}\leq m\leq5\sqrt{2}$"),
         ("D", r"$-3\sqrt{2}\leq m\leq3\sqrt{2}$")])]),

    ("模拟题/江浙皖高中（县中）发展共同体2026届高三上学期10月联考#5",
     "选项 C 是裸 Unicode 字符 `π`，不在数学模式里；其余三项都写成 `$…$`",
     "同一题其余选项的写法（A $\\frac{\\pi}{4}$、B $\\frac{\\pi}{2}$、D $2\\pi$）；"
     "规范 §3「行内公式用 $…$」",
     [("optC", "π", r"$\pi$")]),

    ("模拟题/重庆南开中学校2026届高三12月月考#3",
     "解析里的向量被 OCR 成了分式：`$ \\frac{2}{a} - \\frac{1}{b^2} $`、`|\\over a|`"
     "（`\\over` 老式写法，KaTeX 里分子会抓走前面整段）",
     "题干写的是 $\\overrightarrow{a}=(1,m)$、$\\overrightarrow{b}=(-1,3)$；"
     "解析结论 $m=2$、模 $\\sqrt{1+2^2}=\\sqrt5$ 与题干自洽",
     [("solution", r"$ \frac{2}{a} - \frac{1}{b^2} = (3, 2m - 3) $",
       r"$2\overrightarrow{a}-\overrightarrow{b}=(3,\ 2m-3)$"),
      ("solution", r"$\therefore |\over a| = \sqrt{1 + 2^2} = \sqrt{5}$",
       r"$\therefore|\overrightarrow{a}|=\sqrt{1+2^{2}}=\sqrt{5}$")]),

    ("模拟题/2026年重庆市普通高中学业水平选择性考试高考模拟调研卷（一）#6",
     "解析里 `\\frac15+\\frac35\\over 2` 用 `\\over` 造分数：分子会吃掉同一段前面的全部内容，"
     "换个渲染器就变成另一种结果",
     "该行讲的就是 $\\sin\\alpha\\sin\\beta=\\dfrac{\\cos(\\alpha-\\beta)-\\cos(\\alpha+\\beta)}{2}$，"
     "代值后分子是 $\\tfrac15+\\tfrac35$、分母是 $2$（等号右边 $=\\tfrac25$ 自洽）",
     [("solution", r"$\sin\alpha\sin\beta=\frac15+\frac35\over 2=\frac25$",
       r"$\sin\alpha\sin\beta=\dfrac{\frac15+\frac35}{2}=\dfrac25$")]),

    ("模拟题/天域全国名校协作体2026届高三上学期10月联考#18",
     "题干丢了三个符号：`□MNP`（应为 $\\triangle MNP$）、`m^2=□[…]`（应为 `\\in`）、"
     "`$\\overrightarrow{CA}=\\overrightarrow{CB}=-4$`（数量积的 `\\cdot` 丢了）",
     "解析第 (1) 问算的是 $\\overrightarrow{CA}\\cdot\\overrightarrow{CB}=-a^2+b^2=-c^2=-4$，"
     "说明题面给的是数量积；第 (3) 问讨论的是 $m^2$ **落在** $[\\tfrac15,\\tfrac12]$ 内；"
     "$\\triangle MNP$ 是三角形，□ 是 OCR 把 △ 丢了",
     [("stem", r"$\overrightarrow{CA}=\overrightarrow{CB}=-4$",
       r"$\overrightarrow{CA}\cdot\overrightarrow{CB}=-4$"),
      ("stem", r"$m^2=\square\left[\frac{1}{5},\frac{1}{2}\right]$",
       r"$m^2\in\left[\frac{1}{5},\frac{1}{2}\right]$"),
      ("stem", "□MNP为锐角三角形", "△MNP为锐角三角形")]),

    ("模拟题/浙江丽水、湖州、衢州三地市2026届高三上学期11月教学质量检测#14",
     "解析末尾挂着下一大题的栏头残片，且残片里的字被 OCR 吃掉成 □："
     "「四、解答□：本□共 5 小题，共 77 分。解答应写出…□明□程或演算步□。」",
     "同一场的 #15—#19 都是这道大题的小题；该行是卷面栏目，不是解析内容"
     "（规范 §3 不带分值、页眉页脚）",
     [("solution_drop", "四、解答□", None)]),

    ("模拟题/云师大附中2026届高三上学期适应性月考五+ - 副本#18",
     "解析中间夹着一行 OCR 噪声「■ ■ ■ ■ ■ □ ■ □ □」",
     "该行无任何数学内容，前后两句推导直接相接",
     [("solution_drop", "■ ■ ■", None)]),

    ("模拟题/2026届广东省六校联盟2026届高三上学期第二次联考#17",
     "解析里「□ 5个零件中恰有3个不合格品的概率…」的 □ 是答案册的列表符号，不是内容",
     "同句在孪生场「广东省六校联盟2026届高三12月第二次联考#17」里也在，形状一致"
     "（该场一并改）",
     [("solution_drop_prefix", "□ ", None)]),

    ("模拟题/广东省六校联盟2026届高三12月第二次联考#17",
     "同上：解析里的「□ 」列表符号",
     "孪生场「2026届广东省六校联盟2026届高三上学期第二次联考#17」同形",
     [("solution_drop_prefix", "□ ", None)]),

    ("模拟题/东北师大附中2026届高三上学期第一次摸底考试#17",
     "本题解析尾巴上串进了**下一题（第 18 题）的整段解析**（「】18. 解：(1) 由 $2a_n+T_n=…」），"
     "同一份内容在第 18 题里已经有一份",
     "第 18 题 `模拟题/东北师大附中2026届高三上学期第一次摸底考试#18` 的解析以同样的"
     "「(1) 由 $2a_n+T_n=$」开头，删掉这一段不丢任何内容",
     [("solution_cut_at", "18. 解", None)]),
]

# 竖线开闭不一致（conform 已列为风格提示）：`\left\| … \right|` 会印成 ‖…|
BAR_KEYS = [
    "模拟题/宁夏回族自治区银川一中2026-2027学年高三上学期第一次月考#8",
    "模拟题/厦门外国语学校2026届高三上学期十月月考#11",
    "模拟题/广东中山一中2026届高考数学仿真模拟测试#18",
    "模拟题/江西重点中学盟校2026届高三第一次质检#11",
]
BAR = re.compile(r"\\left\\\|((?:(?!\\right).){1,60}?)\\right\|")
BAR2 = re.compile(r"\\left\|((?:(?!\\right).){1,60}?)\\right\\\|")


def build() -> list[dict]:
    """按现库真值算出每条订正的 `expect`（改前子串）与 `set`（改后全文）。"""
    out: list[dict] = []
    for key, why, src, edits in SUBS:
        q = store.find(key)
        if q is None:
            print("!! 库里没有这道题：%s" % key)
            continue
        cur = {"stem": q.stem or "", "answer": q.answer or "", "solution": q.solution or ""}
        expect: dict = {}
        st: dict = {}
        skip = ""
        for fld, old, new in edits:
            if fld == "options":
                expect["options"] = [o.text for o in q.options]      # 原文照抄，读得懂
                st["options"] = [[lab, txt] for lab, txt in new]
                continue
            if fld == "solution_drop":
                keep = [ln for ln in cur["solution"].split("\n") if old not in ln]
                if len(keep) == len(cur["solution"].split("\n")):
                    skip = "找不到要删的行「%s」" % old
                    break
                expect["solution"] = old
                st["solution"] = "\n".join(keep).strip()
                cur["solution"] = st["solution"]
                continue
            if fld == "solution_drop_prefix":
                t = cur["solution"]
                n = t.replace("\n" + old, "\n").replace(old, "")
                if n == t:
                    skip = "找不到「%s」" % old.strip()
                    break
                expect["solution"] = old.strip() + "5个零件"
                st["solution"] = re.sub(r"\n{3,}", "\n\n", n).strip()
                cur["solution"] = st["solution"]
                continue
            if fld == "solution_cut_at":
                t = cur["solution"]
                i = t.find(old)
                if i < 0:
                    skip = "找不到切断点「%s」" % old
                    break
                cut = t[:i].rstrip()
                if cut.endswith("】"):                     # 「…说明】18. 解：」→ 括号要留下
                    cut = cut[:-1].rstrip()
                expect["solution"] = old
                st["solution"] = cut
                cur["solution"] = cut
                continue
            if fld.startswith("opt") and len(fld) == 4:
                lab = fld[3:]
                o = next((x for x in q.options if x.label == lab), None)
                if o is None or old not in (o.text or ""):
                    skip = "选项 %s 里没有「%s」" % (lab, old)
                    break
                expect["options"] = [old]
                st["options"] = [[x.label, (o.text or "").replace(old, new) if x is o else x.text]
                                 for x in q.options]
                continue
            if old not in cur[fld]:
                skip = "%s 里没有「%s」——题面已被别的改动动过，先不入账" % (fld, old[:44])
                break
            # expect 只记**第一个**旧子串（最有辨识度），后面的改动靠"替换必须命中"来保证
            expect.setdefault(fld, old)
            cur[fld] = cur[fld].replace(old, new)
            st[fld] = cur[fld]
        if skip:
            print("!! 跳过 %s：%s" % (key, skip))
            continue
        out.append({"key": key, "why": why, "src": src, "expect": expect, "set": st})

    # 竖线开闭不配对（conform 风格提示）：统一成单竖线
    for key in BAR_KEYS:
        q = store.find(key)
        if q is None:
            continue
        for fld in ("stem", "solution", "answer"):
            t = getattr(q, fld) or ""
            n = BAR.sub(lambda m: "\\left|" + m.group(1) + "\\right|", t)
            n = BAR2.sub(lambda m: "\\left|" + m.group(1) + "\\right|", n)
            if n == t:
                continue
            out.append({"key": key,
                        "why": "conform 风格提示：`\\left\\|…\\right|` 竖线开闭不配对，"
                               "卷面会印成 `‖…|`（同一式子里两种竖线）",
                        "src": "同一式子前后都是绝对值记号；规范 §3"
                               "「`\\left`/`\\right` 括号类型要一致」",
                        "expect": {fld: "\\left\\|"}, "set": {fld: n}})
            break
    return out


def main() -> int:
    patches = build()
    write = "--写" in sys.argv
    print("\n准备入账 %d 条：\n" % len(patches))
    for p in patches:
        print("─" * 92)
        print("%s\n  why  : %s\n  src  : %s" % (p["key"], p["why"], p["src"][:150]))
        print("  expect: %s" % json.dumps(p["expect"], ensure_ascii=False)[:150])
        print("  set  : %s" % json.dumps(p["set"], ensure_ascii=False)[:220])
    if not write:
        print("\n（没写台账。确认后加 --写）")
        return 0
    d = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    have = {p["key"] for p in d.get("patches") or []}
    dup = [p["key"] for p in patches if p["key"] in have]
    if dup:
        print("台账里已有这些题，跳过：%s" % dup)
        patches = [p for p in patches if p["key"] not in have]
    d.setdefault("patches", []).extend(patches)
    LEDGER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写 %d 条 → %s" % (len(patches), LEDGER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
