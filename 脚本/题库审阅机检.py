#!/usr/bin/env python3
r"""题库逐题审阅 · 第 0 步：全库机检，把三轴的**可疑题**摊成一张队列。

用户定的三条重点：**答案与题目的匹配性、难度系数、知识点匹配**。
3 万道题不可能凭眼睛挨个看，所以先机检一遍：机器能确定的部分直接判，
机器只能「觉得不对」的部分进队列，交给人（或大模型）逐题裁。

    python3 脚本/题库审阅机检.py            # 全库跑一遍，写 数据/题库审阅/
    python3 脚本/题库审阅机检.py --sample 8 # 每类只打 8 条到终端，不落盘

产出（都不进 git，见 .gitignore 的 数据/）：

    数据/题库审阅/候选.jsonl   一行一条可疑题：{axis, code, key, 证据…}
    数据/题库审阅/机检报告.md   每个码多少条、样例、以及**这一条为什么可疑**

## 机检只判「自相矛盾」，不判「数学对不对」

能被机器咬死的，都是**同一道题内部对不上**：答案字母不在选项里、
解析说「故选 C」而答案是 B、选项重复、解答题答案栏没写「见解析」……
至于「这道题的解本身算错了」，机检只能给个**嫌疑**（比如填空的解析末尾
抽出来的数和答案不是一个量），最终要人算。这一步故意不越权。

## 为什么不与 `amti/conform.py` 合并

`conform` 是**规范审查**：写法不合规就红，它不关心答案对不对。
这里查的是**内容自洽**，判据完全不同（要读解析、要比数值），
混在一起会让 conform 的「全绿」变得含义模糊。两者都只读题库，不改数据。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import knowledge, store                    # noqa: E402
from amti.paths import ROOT as RROOT                 # noqa: E402

OUT = RROOT / "数据" / "题库审阅"

# 每道题都会走一遍这些检查；code 是稳定的，队列按 (code,key) 幂等
CODES = {
    "A1": "答案字母不在选项里",
    "A2": "选项标签不连续（缺 A/B/C/D 或多出）",
    "A3": "有重复选项",
    "A4": "解析结论与答案不一致",
    "A5": "客观题没有答案",
    "A6": "解答题答案栏不是「见解析」",
    "A7": "填空解析末尾的数与答案对不上",
    "A8": "题干/解析里混进卷面噪声（页眉、大题说明、元话）",
    "A9": "填空题答案栏写成选项字母（答案表串列）",
    "A10": "答案栏以分号收尾（答案表分列残留）",
    "A11": "选择题选项文字被清空（选项图/标签在录入时丢了）",
    "A12": "答案栏里不是答案（托词／卷面页眉串进来）",
    "B1": "题目自带难度与主考点星级派生的难度差两级",
    "B2": "同考点内自带难度与考点定性大面积相反",
    "C1": "考点 id 不存在于 152 表",
    "C2": "没有考点标签",
    "C3": "考点跨度过大（跨 3 个以上板块）",
    "C4": "题干关键词与主考点板块不符",
}

LETTERS = "ABCDEF"
# 「故选 C」「故答案选 B」「答案：A」「选 AD」——解析末尾的结论最容易和答案栏打架
_PICK = re.compile(r"(?:故选|故选|答案选|故答案选|因此选|所以选|应选|答案[:：为]\s*)\s*"
                   r"([A-F](?:\s*[、,，]\s*[A-F])*)\b")
_FILL_END = re.compile(r"(?:故填|所以填|应填|故答案|答案[:：为])\s*([^。\n]{1,40})")
# 卷面噪声：把整场考试的说明抄进了一道题里。
# ⚠️ 不收「选择题/填空题/解答题」这种光杆词——解析里「本题为选择题」是正常表述，
# 第一次试跑就是被它污染成假阳。要的是**页眉页脚与卷首说明**的形态。
_NOISE = re.compile(r"第\s*\d+\s*页\s*[（(]共\s*\d+\s*页[）)]|共\s*\d+\s*页|本题共\s*\d+\s*小题"
                    r"|满分\s*\d+\s*分|考试时间\s*\d+\s*分钟|QQ\s*[群号]|微信公众号"
                    r"|参考答案及?解析|^\s*[一二三四五六]\s*[、.]\s*(选择题|填空题|解答题)")
# 题干**问的就是代号/序号**的填空题：答案栏填字母是对的，别报 A9。
# 实例：2009 江西文/理#16「其中真命题的代号是＿＿＿（写出所有真命题的代号）」答 ABC / BC；
#      2014 新课标I文#14「乙去过的城市为＿＿」答 A（城市名本身就叫 A）。
_ASKS_LETTER = re.compile(r"代号|序号|编号|填写所有|真命题的|正确命题的|答案是填写序号")
# A12 的两路判据。第一路是**上一道工序的话**混进了答案栏；第二路是**卷面页眉**串位。
_HEDGE_ANS = re.compile(r"题面|无法确定|无法唯一确定|无法求解|无法作答|无法判断|无法计算"
                        r"|条件不足|缺少.{0,10}(条件|集合|个数|数据|数字)|不成立|答案不唯一")
_JUNK_HDR_ANS = re.compile(r"参考答案|解析$|详解|评分标准|第\s*\d+\s*页|^\s*[一二三四五六七八九十]、")
# 板块关键词：只放**误标代价大**的几组，宁可漏报不误伤
_TOPIC_KEY = {
    "9": ["概率", "分布列", "期望", "方差", "排列", "组合", "二项式", "统计", "抽样", "回归"],
    "7": ["等差", "等比", "前 n 项和", "数列"],
    "5": ["椭圆", "双曲线", "抛物线", "离心率", "渐近线", "直线", "圆"],
    "6": ["sin", "cos", "tan", "三角", "内角", "向量"],
    "4": ["导数", "f'(x)", "单调", "极值", "切线"],
    "10": ["平面", "棱柱", "棱锥", "二面角", "线面", "法向量"],
}


def norm_txt(s: str) -> str:
    """比选项文本、比结论用：去掉 LaTeX 包装与空白，只留可比内容。"""
    s = re.sub(r"\$+", "", s or "")
    s = re.sub(r"\\(?:left|right|,|;|!|quad|qquad|mathrm|text|displaystyle)", "", s)
    s = re.sub(r"\s+", "", s)
    return s.replace("（", "(").replace("）", ")").replace("，", ",")


def as_num(s: str):
    r"""把「$\frac{3}{4}$」「-0.5」「3/2」「\dfrac12」「2\times10^3」读成一个数。

    只认**纯数值**形态：化成算术式后还剩字母或汉字（区间、含参式子）一律 None，
    宁可不判也不猜。第一次试跑 A7 一条都没抓到，就是因为只写了
    `\dfrac{a}{b}` 的一种形态——分数写法有三种，都得认。
    """
    t = norm_txt(s)
    if not t:
        return None
    t = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"((\1)/(\2))", t)
    t = re.sub(r"\\[dt]?frac(\d)(\d)", r"((\1)/(\2))", t)
    t = re.sub(r"\\(?:cdot|times)", "*", t)
    t = t.replace("^", "**")
    if re.search(r"[a-zA-Z\u4e00-\u9fff{}\\]", t):
        return None
    if not re.fullmatch(r"[-+*/().0-9* \t]*", t):
        return None
    try:
        return float(eval(t, {"__builtins__": {}}, {}))     # noqa: S307 上面已限死字符集
    except Exception:                                       # noqa: BLE001
        return None


def check(q, point_of, ran: Counter) -> list[tuple[str, str]]:
    """一道题跑完所有检查，返回 [(code, 证据)]。

    `ran` 记的是**这条检查到底有没有跑到**——0 命中和「探针没生效」是两件
    完全不同的事，不分开记就会拿一片绿当安全（这仓库在这上面栽过）。
    """
    out: list[tuple[str, str]] = []
    labels = [norm_txt(o.label) for o in q.options]
    ans = (q.answer or "").strip()
    sol = q.solution or ""

    # ── 轴一：答案 ↔ 题目 ──
    if q.type in ("single_choice", "multi_choice"):
        got = [a for a in re.sub(r"[^A-F]", "", ans.upper())]
        ran["A1"] += 1
        ran["A2"] += 1
        ran["A3"] += 1
        ran["A4"] += 1
        if not got:
            out.append(("A5", f"答案栏是 {ans!r}，读不出选项字母"))
        elif set(got) - set(labels):
            out.append(("A1", f"答案 {ans} 里的 {sorted(set(got) - set(labels))} 不在选项 {labels} 里"))
        if labels and labels != list(LETTERS[:len(labels)]):
            out.append(("A2", f"选项标签是 {labels}"))
        dup = [t for t, n in Counter(norm_txt(o.text) for o in q.options).items() if t and n > 1]
        if dup:
            out.append(("A3", f"重复选项：{dup[:2]}"))
        concl = _concl(sol)
        if concl:
            ran["A4#匹配"] += 1
            if ans and set(concl) != set(re.sub(r"[^A-F]", "", ans.upper())):
                out.append(("A4", f"解析结论「{concl}」与答案栏 {ans} 不符"))
    elif q.type == "fill_in_blank":
        ran["A5"] += 1
        ran["A7"] += 1
        ran["A9"] += 1
        if not ans:
            out.append(("A5", "答案栏为空"))
        else:
            # A9：填空题答案栏写成**选项字母**——逐题审阅连着抓到 4 道
            # （学军#12 填「A」、嘉兴#12/#13 填「A」「ABC」、浙江强基#12 填「A」），
            # 都是答案表里选择题那一列串过来的。真值要重算，机检只负责把盘子端出来。
            # ⚠️ 但**填代号/序号的填空题答案本来就是字母**：2009 江西文理#16
            #    「其中真命题的代号是＿＿（写出所有真命题的代号）」答 ABC / BC，
            #    2014 新课标I文#14「乙去过的城市为＿＿」答 A（城市名就叫 A）。
            #    题干问了代号/序号/编号的一律不报——第一次不加这条，31 道里混进 3 道好题。
            if re.fullmatch(r"[A-F]{1,3}", ans.upper()) and not _ASKS_LETTER.search(q.stem or ""):
                out.append(("A9", f"填空题答案栏是选项字母 {ans!r}，不是数值"))
            tail = _FILL_END.findall(sol)
            if tail:
                a, b = as_num(ans), as_num(tail[-1])
                if a is not None and b is not None:
                    ran["A7#可比"] += 1
                    if abs(a - b) > max(1e-9, abs(a) * 1e-6):
                        out.append(("A7", f"答案 {ans} 与解析末尾 {tail[-1]!r} 数值不等"))
    elif q.type == "detailed_answer":
        ran["A6"] += 1
        if ans and norm_txt(ans) not in ("见解析", "略"):
            out.append(("A6", f"答案栏写的是 {ans[:28]!r}"))

    body = (q.stem or "") + "\n" + sol
    ran["A8"] += 1
    hit = _NOISE.search(body)
    if hit:
        out.append(("A8", f"命中卷面噪声「{hit.group(0)}」"))

    # A11：选择题**选项既没文字、也没图来承载**——界面上只剩「A. B. C. D.」四个光杆字母。
    # 🔴 判据改过一版，旧版是「空文字选项数 ≠ 配图数」，**这是错的**：
    #    `_images` 那批书（千题册等）的体例是**一张图条里排两个带 A./B./C./D. 印刷标签的选项**，
    #    所以 4 个选项只对应 2 张图，旧判据 100% 误报。
    #    实测逐张开图核过 9 道（千题册 026#19/027#20/020#32/034#69/023#39/151#41/037#75/044#61
    #    ＋ 2009 广东文#1），**四个选项全都在图上、标签齐全**，一道都不缺。
    #    它们登记的 `figure_missing`（"选项 A 的图（OCR 未提取）"）也是错的——
    #    但那个标记**不能清**：`schema.problems()` 靠它放行空选项，清掉这 11 道立刻变非法。
    # ⇒ 只报「空文字选项 + 零配图」：那才是真的没东西承载选项。
    if q.type in ("single_choice", "multi_choice"):
        blank = [o.label for o in q.options if not (o.text or "").strip()]
        ran["A11"] += 1
        if blank and not q.figures:
            out.append(("A11", f"{len(blank)} 个选项文字为空（{blank}）且**题级零配图**"
                               f"⇒ 选项没有任何载体"))
        elif blank and len(blank) != len(q.figures):
            ran["A11-图条"] += 1      # 只计数不报：`_images` 体例一张图条排两个选项
        elif blank and len(blank) == len(q.figures):
            out.append(("A11", f"{len(blank)} 个选项文字为空、配图 {len(q.figures)} 张（数量对得上，"
                               f"但选项标签没写「见图 A/B/C/D」）"))

    # A10：答案栏**以分号收尾**＝答案表分列的残留（青岛#12/#13、九五#12/#13、
    # 绵阳#12/#13、成都一诊#13、广东六校#13 抓到 8 处）。
    # 只认「最后一个字符是分号」：多空答案写成「$1$；$2$」的收尾是数值，不吃。
    ran["A10"] += 1
    if ans and ans[-1] in ";；":
        out.append(("A10", f"答案栏以分号收尾：{ans[-14:]!r}"))

    # A12：答案栏里写的**不是答案**，是上一道工序留下的话（「题面有误」「无法确定」…）
    #       或者串进来的卷面页眉（「· 数学 ·\n参考答案及解析」）。
    # 🔴 这一条为什么必须存在：入库闸只问「答案栏空不空」，**不问那是不是答案**。
    #    于是"没答案的题"只要塞一句托词就过关了，`missing()` 也报不出「缺答案」——
    #    这批 14 道在库里躺了不知多少轮，机检一个都没抓到。
    # ⚠️ 只扫**纯中文散文**的答案（不含数字、`$`、反斜杠），否则会误伤
    #    「侧棱相等」「分层抽样」「不存在」「乙；数学」这类**合法的文字答案**。
    ran["A12"] += 1
    # ⚠️ 排除表里**不许放 `·`**：卷面页眉就是「· 数学 ·」这种用间隔号包的，
    #    把它当数学符号排除掉，页眉串位那一路就永远抓不到（自检当场抓到过一次）。
    if ans and ans != "见解析" and not re.search(r"[0-9$\\{}=<>±√π⋅]", ans) \
            and re.search(r"[一-鿿]", ans):
        if _HEDGE_ANS.search(ans):
            out.append(("A12", f"答案栏写的是**托词**而不是答案：{ans[:34]!r}"))
        elif _JUNK_HDR_ANS.search(ans):
            out.append(("A12", f"答案栏串进了**卷面页眉/节标题**：{ans[:34]!r}"))

    # ── 轴二：难度 ──
    own = (q.meta.get("difficulty") or "").strip()
    p0 = (q.points or [""])[0]
    derived = knowledge.difficulty_of(p0)
    rank = {"简单题": 1, "中档题": 2, "难题": 3}
    if own:
        ran["B1"] += 1
        if derived and abs(rank.get(own, 0) - rank.get(derived, 0)) >= 2:
            out.append(("B1", f"题自带 {own}，考点 {p0} 星级派生 {derived}"))

    # ── 轴三：知识点 ──
    pts = [p.strip() for p in (q.points or []) if p.strip()]
    ran["C1"] += 1
    ran["C2"] += 1
    if not pts:
        out.append(("C2", "没有考点标签"))
    else:
        bad = [p for p in pts if not point_of.get(p)]
        if bad:
            out.append(("C1", f"考点不存在：{bad}"))
        tops = {p.split(".")[0] for p in pts if p.split(".")[0].isdigit()}
        if len(tops) >= 3:
            out.append(("C3", f"跨 {len(tops)} 个板块：{sorted(tops)}"))
    return out


def topic_gap(qs, point_of) -> list[dict]:
    r"""C4 改成**按考点聚合**的信号：某个考点下「板块关键词一个都不沾」的比例。

    逐题判「题干不含本板块词」误伤太重（考点叫「椭圆的简单几何性质」，
    题干写「已知曲线 C」是完全正常的说法），第一次试跑 2,500 道就报了 200 条。
    但**一个考点底下八成题都不沾边**，那就不是措辞问题，是这个考点被乱贴了。
    """
    stat: dict[str, list[int]] = defaultdict(lambda: [0, 0])      # 考点 → [无词, 总数]
    for q in qs:
        pts = [p.strip() for p in (q.points or []) if p.strip()]
        if not pts:
            continue
        pid = pts[0]
        top = pid.split(".")[0]
        keys = _TOPIC_KEY.get(top)
        if not keys:
            continue
        s = stat[pid]
        s[1] += 1
        if not any(k in (q.stem or "") + "\n" + (q.solution or "") for k in keys):
            s[0] += 1
    rows = []
    for pid, (miss, tot) in s_items(stat):
        if tot >= 20 and miss / tot >= 0.75:
            rows.append({"point": pid, "n": tot, "miss": miss,
                         "rate": round(miss / tot, 3),
                         "title": knowledge.title_of(pid)})
    return sorted(rows, key=lambda r: -r["rate"])


def s_items(stat):
    return sorted(stat.items(), key=lambda kv: kv[0])


def _selftest() -> int:
    r"""**灵敏度自证**：往库里造几道「一定错」的题，每条探针必须抓到。

    没有这一步，「0 命中」根本没法读——是真干净，还是正则压根没匹配上？
    每条都同时断言「探针跑到了」和「该报的报了」。
    """
    from amti.schema import Option, Question
    ok = True

    def chk(name, cond, note=""):
        nonlocal ok
        print("%-34s %s %s" % (name, "OK" if cond else "FAIL", note))
        ok = ok and bool(cond)

    def Q(**kw):
        base = dict(key="自检#1", type="single_choice", stem="1+1=?", answer="B",
                    options=[Option(label=l, text=t) for l, t in
                             zip("ABCD", ["1", "2", "3", "4"])],
                    solution="显然 1+1=2，故选 B。", points=["1.1.1"], meta={})
        base.update(kw)
        return Question(**base)

    cases = [
        ("A1", Q(answer="E"), "答案字母越界"),
        ("A2", Q(options=[Option(label=l, text=t) for l, t in
                          zip("ABD", ["1", "2", "3"])]), "选项标签缺 C"),
        ("A3", Q(options=[Option(label=l, text="2") for l in "ABCD"]), "四个选项同文"),
        ("A4", Q(solution="算完得 3，故选 C。"), "解析故选 C 而答案是 B"),
        ("A5", Q(answer=""), "答案栏空"),
        ("A7", Q(type="fill_in_blank", stem="1+1=____", answer=r"$\dfrac{1}{2}$",
                 solution=r"显然，故填 $\dfrac{1}{3}$。"), "填空答案与解析末尾不等"),
        ("A6", Q(type="detailed_answer", answer="2", solution="见解析。"),
         "解答题答案栏没写见解析"),
        ("A8", Q(solution="故选 B。\\n第 3 页（共 4 页）"), "卷尾页码混进解析"),
        ("A9", Q(type="fill_in_blank", stem=r"x= \fillin[A]。", answer="A",
                 solution=r"解得 x=2。"), "填空题答案栏写成选项字母"),
        ("A10", Q(type="fill_in_blank", stem=r"x= \fillin[$2$]。", answer=r"$2$;",
                  solution=r"解得 x=2。"), "答案栏以分号收尾"),
        ("A11", Q(answer="A", solution="如图，故选 A。", figures=[],
                  options=[Option(label=l, text="") for l in "ABCD"]),
         "四个选项全空、题级零配图"),        ("A12", Q(type="fill_in_blank", stem=r"则 $a=$ \fillin[题面有误]。",
                  answer="题面有误", solution="题图缺失，无法确定。"),
         "答案栏写成托词"),
        ("A12", Q(type="fill_in_blank", stem=r"解集为 \fillin[· 数学 · 参考答案及解析]。",
                  answer="· 数学 ·\n参考答案及解析", solution="略。"),
         "答案栏串进卷面页眉"),
        ("B1", Q(points=["1.1.1"], meta={"difficulty": "难题"}),
         "自带难度与星级差两级"),
        ("C1", Q(points=["99.9.9"]), "考点不存在"),
        ("C2", Q(points=[]), "没有考点"),
        ("C3", Q(points=["1.1.1", "5.2.1", "9.2.1"]), "跨三个板块"),
    ]
    point_of = {p["id"]: p for p in knowledge.all_points()}
    for code, q, note in cases:
        ran: Counter = Counter()
        got = {c for c, _w in check(q, point_of, ran)}
        chk(f"注入 {code}（{note}）", code in got, "" if code in got else f"探针没抓到，只抓到 {sorted(got)}")

    # 阴性对照：**合法的文字答案**不许被 A12 误伤。只测阳性会把探针写成一张大网，
    # 把「侧棱相等」「分层抽样」这类正常答案一起捞进来，人就再也不看这个数了。
    legit = ["侧棱相等", "分层抽样", "不存在", "乙；数学", "甲", "投资房地产",
             "三棱锥、三棱柱、圆锥", "图形的全等、图形的相似、非零向量的共线",
             "用代数的方法研究图形的几何性质", "见解析"]
    for a in legit:
        ran = Counter()
        q = Q(type="fill_in_blank", stem=r"则 ____", answer=a, solution="略。")
        got = {c for c, _w in check(q, point_of, ran)}
        chk(f"阴性：合法文字答案 {a[:12]!r} 不报 A12", "A12" not in got,
            "" if "A12" not in got else f"误伤，抓到 {sorted(got)}")

    # 阴性对照：`_images` 体例——4 个空文字选项由**两张图条**承载（一张排两个带标签的选项）。
    # 旧判据「空选项数 ≠ 配图数」在这里 100% 误报，实测误伤 11 道好题。
    from amti.schema import Figure
    ran = Counter()
    _strip = Q(answer="D", solution="读图可知选 D。",
               figures=[Figure(id="a.png", kind="bitmap", source="inline"),
                        Figure(id="b.png", kind="bitmap", source="inline")],
               options=[Option(label=l, text="") for l in "ABCD"])
    got = {c for c, _w in check(_strip, point_of, ran)}
    chk("阴性：四选项由两张图条承载 不报 A11", "A11" not in got,
        "" if "A11" not in got else f"误伤，抓到 {sorted(got)}")
    return 0 if ok else 1


def shift_scan(qs) -> list[dict]:
    r"""按卷子统计「解析结论 ↔ 答案栏」不符率，并试答：能不能用**错一位**解释。

    为什么按卷子而不是逐题：一份卷的答案是照答案表按题号抄的，抄错一行就是
    **连着几道一起错**。第一例（江苏镇江一中 10 月阶段测试）#1—#4 的答案栏
    整体后错一位（解析 #2/#3/#4 的结论正好等于答案栏 #1/#2/#3），而 #6—#8 是对的
    ——所以「整场平移」这个模型是错的，只能按段看，报出来交人判。

    阈值故意保守：至少 5 道可比、不符 ≥3 道且占四成以上才报。
    """
    by_paper: dict[str, list] = defaultdict(list)
    for q in qs:
        m = _KEY_NO.match(q.key or "")
        if not m:
            continue
        no = int(m.group("no"))
        src = str(q.meta.get("source_no") or "").strip()
        if src.isdigit():
            no = int(src)                       # 卷面题号优先，key 里的 #N 是入库序号
        if q.type in ("single_choice", "multi_choice"):
            by_paper[m.group("paper")].append((no, q))
    out = []
    for paper, items in sorted(by_paper.items()):
        pairs = []
        for no, q in sorted(items):
            concl, ans = _concl(q.solution or ""), re.sub(r"[^A-F]", "", (q.answer or "").upper())
            if concl and ans:
                pairs.append((no, set(concl), set(ans)))
        if len(pairs) < 5:
            continue
        diff = [(n, c, a) for n, c, a in pairs if c != a]
        if len(diff) < 3 or len(diff) / len(pairs) < 0.4:
            continue
        # 「错一位」能不能解释：不符的那几道里，解析结论等于前一题答案栏的有几个
        byno = {n: a for n, _c, a in pairs}
        off1 = sum(1 for n, c, _a in diff if byno.get(n - 1) == c)
        out.append({"paper": paper, "n": len(pairs), "diff": len(diff),
                    "off1": off1, "rate": round(len(diff) / len(pairs), 2),
                    "nums": [n for n, _c, _a in diff]})
    return sorted(out, key=lambda r: (-r["off1"], -r["diff"]))


_KEY_NO = re.compile(r"^(?P<paper>.+)#(?P<no>\d+)$")


def _concl(sol: str) -> str:
    """取解析**结尾**那句结论字母（中间逐选项分析的「故 A 正确」不算结论）。"""
    tail = re.sub(r"\s+", " ", sol or "")[-160:]
    # ⚠️ 字母要按**一整串**吃：多选常写「故选 BC」（中间没顿号）。
    # 早先写成 `[A-F](?:[、,，][A-F])*`，「BC」只吃到 B，一下造出 1,293 条假阳。
    m = re.findall(r"(?:故选|故答案选|答案选|因此选|所以选|应选)\s*[:：]?\s*"
                   r"([A-F]+(?:\s*[、,，]\s*[A-F]+)*)", tail)
    if not m:
        return ""
    last = m[-1].upper()
    # 「故选 A C D」（字母之间只有空格）上面那条只吃到 A —— 实测把一道答案正确的
    # 多选题报成 A4 假阳。但**不能无条件放开空格**：「故选 A 正确，B 错误」会被吃成 AB。
    # 折中：只有当结论字母串**正好落在句尾**（后面只剩标点）时，才按空格再吃一次。
    anchor = re.search(r"(?:故选|故答案选|答案选|因此选|所以选|应选)\s*[:：]?\s*"
                       r"([A-F](?:[ ]+[A-F]+)*)\s*[。.!！]?$", tail)
    if anchor and len(anchor.group(1).replace(" ", "")) > len(re.sub(r"[^A-F]", "", last)):
        last = anchor.group(1)
    return re.sub(r"[^A-F]", "", last)


def main() -> int:
    ap = argparse.ArgumentParser(description="题库三轴机检")
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "check", "shift"])
    ap.add_argument("--sample", type=int, default=4, help="终端里每类打印几条")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 道（调试用）")
    ap.add_argument("--write", action="store_true", help="落盘候选队列与报告")
    ap.add_argument("--shift", action="store_true", help="只跑整场答案错位探测")
    a = ap.parse_args()
    if a.cmd == "check":
        return _selftest()

    qs = store.load_cached()
    if a.limit:
        qs = qs[:a.limit]
    if a.cmd == "shift" or a.shift:
        rows = shift_scan(qs)
        print(f"解析结论与答案栏大面积不符的卷子：{len(rows)} 份")
        for r in rows[:a.sample * 6]:
            tag = "← 错一位可解释" if r["off1"] >= 2 else ""
            print(f"  不符 {r['diff']}/{r['n']}（{int(r['rate'] * 100)}%）"
                  f"错一位命中 {r['off1']} {tag}｜ {r['paper']}")
            print(f"      题号 {r['nums']}")
        return 0

    point_of = {p["id"]: p for p in knowledge.all_points()}
    rows: list[dict] = []
    by_code: Counter = Counter()
    ran: Counter = Counter()
    for q in qs:
        for code, why in check(q, point_of, ran):
            by_code[code] += 1
            rows.append({"axis": code[0], "code": code, "key": q.key,
                         "type": q.type, "point": (q.points or [""])[0], "why": why})
    print(f"扫了 {len(qs)} 道题，命中 {len(rows)} 条嫌疑")
    print(f"{'码':<4}{'命中':>7}{'跑到':>9}  说明 / 涉及题数")
    for code in sorted(CODES):
        keys = {r["key"] for r in rows if r["code"] == code}
        print(f"{code:<4}{by_code[code]:>7}{ran[code]:>9}  {CODES[code]}（{len(keys)} 道题）")
    print(f"  A4 里「解析中真出现故选X」的题：{ran['A4#匹配']}；"
          f"A7 里两边都能读成数的题：{ran['A7#可比']}")
    print(f"合计涉及 {len({r['key'] for r in rows})} 道题（一道可能中多条）")
    gaps = topic_gap(qs, point_of)
    print(f"C4（按考点聚合）：{len(gaps)} 个考点八成以上题目不沾本板块关键词")
    for g in gaps[:a.sample]:
        print(f"  {g['point']} {g['title'][:20]} ｜ {g['miss']}/{g['n']} 无关键词")

    if a.write:
        OUT.mkdir(parents=True, exist_ok=True)
        with (OUT / "候选.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        lines = ["# 题库三轴机检报告", "",
                 f"扫 {len(qs)} 道，命中 {len(rows)} 条嫌疑，涉及 {len({r['key'] for r in rows})} 道题。",
                 "", "机检只判「同一道题内部对不上」，最终是不是错要逐题裁。",
                 "「跑到」那一列是探针生效范围——0 命中且 0 跑到 ＝ 这条**没验到**，不是没问题。", "",
                 "| 码 | 说明 | 命中 | 跑到 | 涉及题 |", "|---|---|---|---|---|"]
        for code in sorted(CODES):
            keys = {r["key"] for r in rows if r["code"] == code}
            lines.append(f"| {code} | {CODES[code]} | {by_code[code]} | {ran[code]} | {len(keys)} |")
        lines += ["", "## 逐码明细（每类前若干条）", ""]
        for code in sorted(CODES):
            sub = [r for r in rows if r["code"] == code]
            if not sub:
                continue
            lines += [f"### {code} · {CODES[code]}（{len(sub)}）", ""]
            lines += [f"- `{r['key']}` ｜ {r['why']}" for r in sub[:a.sample * 3]]
            lines.append("")
        if gaps:
            lines += ["## C4 · 考点级：贴了标签但题干不沾边", ""]
            lines += [f"- {g['point']} {g['title']} ｜ 无关键词 {g['miss']}/{g['n']}"
                      f"（{int(g['rate'] * 100)}%）" for g in gaps]
            lines.append("")
        (OUT / "机检报告.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"写了 {OUT/'候选.jsonl'} 与 {OUT/'机检报告.md'}")
    else:
        for code in sorted(CODES):
            for r in [x for x in rows if x["code"] == code][:a.sample]:
                print(f"  {code} {r['key']} ｜ {r['why'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
