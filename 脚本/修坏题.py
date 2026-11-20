#!/usr/bin/env python3
"""把「编不过」的题**从源头**修好：改题目里的 LaTeX，不在渲染器里打补丁。

    python3 脚本/修坏题.py            # 干跑：逐道试修，只报结果
    python3 脚本/修坏题.py --yes      # 落盘（改完仍要能编过才写）

修的是数据里真写错的地方：

  · 题干里裸的 `____`（应在数学模式或 `\\underline`）→ `\\underline{\\hspace{2em}}`
  · `\\fillin[$…\\right]$]`：`]` 会被当成可选参数的结束符
    → `\\right\\rbrack`（LaTeX 自带，不再含裸 `]`）
  · `\\diaghead{甲}{乙}` → `甲/乙`（讲义没有这个宏）
  · `\\begin{enumerate}` 后面没有 `\\item` 的 → 按行补 `\\item`
  · 花括号多一个的 → 去掉多余的 `}`

每道题修完都要**真编两遍**（试卷模式 + 讲义模式），两边都过才落盘；
过不了的原样保留并报出来，交人工。
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import export, store                     # noqa: E402

BAD = """2026精选模拟题/P1623#39
中考模拟/2026年鼓楼区中考数学一模卷#20
模拟题/187.湖南长郡中学2026届高三上学期12月月考#13
模拟题/189.江西三新协作体2026届高三上学期12月联考#5
模拟题/2025年10月诊断性测试#4
模拟题/2025年10月诊断性测试#5
模拟题/2025年10月诊断性测试#6
模拟题/2025年10月诊断性测试#7
模拟题/2025年10月诊断性测试#8
模拟题/2025年12月2026届T8联考高三#11
模拟题/2025年9月浙江名校协作体高三联考#15
模拟题/2026届山东省潍坊市高三开学调研监测考试#14
模拟题/2026届广安一诊#14
模拟题/2026届泉州二检#19
模拟题/2026届湖南名校联考联合体(炎德英才)高三1月联考（含）#13
模拟题/2026届潮州高三1月期末考#7
模拟题/2026届高三上学期咸阳一模#13
模拟题/2026届高三上学期咸阳一模#2
模拟题/2026年山东东营二模#14
模拟题/2027届高三年级9月阶段练习#7
模拟题/2027届高三年级9月阶段练习#8
模拟题/华大新高考联盟2026届高三9月联考#10
模拟题/南京师大附中、海安中学、天一中学、海门中学2026届高三上学期12月联考#14
模拟题/安徽江南十校2027届高三第一次综合素质检测#8
模拟题/广东佛山S6高质量发展联盟2026届高三上学期10月联考#14
模拟题/江苏省无锡市2025-2026学年高三上学期期中教学质量调研测试数学#14
模拟题/河南省TOP二十名校2025-2026学年高三上学期调研考试二#15
模拟题/河南青桐鸣2026-2027学年高三上学期9月学情调研#14
模拟题/浙江A9协作体2027届高三上学期暑假返校学情诊断#13
模拟题/浙江A9协作体2027届高三上学期暑假返校学情诊断#14
模拟题/浙江省A9协作体2026届高三上学期暑假返校联考#12
模拟题/湖北楚天协作体2026届高三上学期11月期中考试#14
模拟题/湖北省“新八校 协作体2026届高三上学期10月月考#12
模拟题/湖北省“新八校 协作体2026届高三上学期10月月考#14
模拟题/湖南名校联考联合体2026届高三上学期10月月考#14
模拟题/湖南长郡中学2025-2026学年高三上学期月考一#18
模拟题/湘豫名校联考2026届高三上学期12月月考#1
模拟题/福建省厦门第一中学2025-2026学年高三上学期10月月考（含）#13
模拟题/福建省百校2026届高三上学期10月联合测评#1
模拟题/重庆十一中2026届高三上学期第五次质检#13
模拟题/高三正文（2026年湛江市普通高考调研测试）#7
模拟题/（附中高三3次）#1
模拟题/（附中高三3次）#5
模拟题/（附中高三3次）#6
高考真题汇编/2013/湖南卷（理）#16
高考真题汇编/2015/湖北卷（理）#14""".splitlines()


def split_math(t: str):
    """切成 [(是否数学, 片段)]：`$…$` 与 `\\[…\\]` 算数学（转义的 `\\$` 不算）。"""
    out, buf, i, n = [], [], 0, len(t)
    in_math = False
    while i < n:
        if in_math:
            if t[i] == "\\":
                buf.append(t[i:i + 2]); i += 2; continue
            if t[i] == "$":
                buf.append("$")
                out.append((True, "".join(buf))); buf = []
                in_math = False; i += 1; continue
            buf.append(t[i]); i += 1
        else:
            if t.startswith("\\[", i):
                if buf:
                    out.append((False, "".join(buf))); buf = []
                j = t.find("\\]", i + 2)
                j = n if j < 0 else j + 2
                out.append((True, t[i:j])); i = j; continue
            if t[i] == "$":
                if buf:
                    out.append((False, "".join(buf))); buf = []
                buf.append("$"); i += 1; in_math = True; continue
            if t[i] == "\\":
                buf.append(t[i:i + 2]); i += 2; continue
            buf.append(t[i]); i += 1
    if buf:
        out.append((in_math, "".join(buf)))
    return out


_BLANK = re.compile(r"_{2,}")
_IDENT = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]*(?:_(?:\{[^{}]*\}|[A-Za-z0-9]))+(?:\^\{[^{}]*\})?)")


_BARE_SCRIPT = re.compile(
    r"(?<![$\\A-Za-z0-9])([0-9A-Za-z]+(?:\^|_)"          # 45^2 / a^2
    r"(?:\{[0-9A-Za-z+-]*\}|[0-9A-Za-z]*)"
    r"(?:[+\-=][0-9A-Za-z]+(?:\^|_)(?:\{[0-9A-Za-z+-]*\}|[0-9A-Za-z]*))*)"
)


def _fix_text_only(seg: str) -> str:
    s = _BLANK.sub(lambda m: r"\underline{\hspace{2em}}", seg)
    # 正文里的裸上下标（`45^2`、`a^2+b^2-c^2=4`）→ 包进数学模式
    s = _BARE_SCRIPT.sub(lambda m: "$%s$" % m.group(1), s)
    # 裸标识符（A_1、a_{n+1}）在正文里 → 包进数学模式
    s = _IDENT.sub(lambda m: "$%s$" % m.group(1), s)
    return s


def fix_rules(text: str) -> str:
    """常见错法一把修：裸下划线、\\fillin 里的 `]`、\\diaghead。"""
    # `\fillin[$…\right]$]`：把 `\right]` 换成不含裸 `]` 的写法。
    # 用**配平扫描**找可选参数结尾（正则数不清 `\left( … \right]` 里的方括号）。
    from amti.paper import _blank_arg_end
    out, i = [], 0
    while True:
        j = text.find(r"\fillin[", i)
        if j < 0:
            out.append(text[i:]); break
        start = j + len(r"\fillin[")
        end = _blank_arg_end(text, start - 1)
        if end < 0:
            out.append(text[i:]); break
        body = text[start:end]
        body = body.replace(r"\right]", r"\right\rbrack")
        out.append(text[i:start]); out.append(body)
        i = end
    text = "".join(out)
    # \diaghead{A}{B} → A/B（讲义没有这个宏）
    text = re.sub(r"\\diaghead\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
                  lambda m: "%s/%s" % (m.group(1), m.group(2)), text)
    # 行首孤立 `[`：`\item [3, 4]` 会被 enumitem 当成可选 label（讲义里炸）
    text = re.sub(r"(?m)^(\s*)\[([^\[\]]+)\]\s*$", r"\1$[\2]$", text)
    # 页眉页脚/答题卡残留（整行只有"考号/姓名/班级/学号/第几页"）
    text = re.sub(r"(?m)^\s*(考号|姓名|班级|学号|座位号)\s*$\n?", "", text)
    # 正文里的裸下划线 / 裸标识符
    parts = split_math(text)
    parts = [(m, (seg if m else _fix_text_only(seg))) for m, seg in parts]
    text = "".join(seg for _m, seg in parts)
    return text


# 逐题补丁：自动规则覆盖不到的数据错（每条都写清改什么、为什么）
MANUAL: dict[str, tuple[str, str]] = {
    # 题干尾部重复粘了一句（"ABCD-A_1B_1C_1D_1 的内部…"，与前文重复）
    "模拟题/2025年12月2026届T8联考高三#11": (
        "。\nABCD-A_1B_1C_1D_1 的内部（包括表面），则下列结论正确的是\\paren[ACD]",
        "。\\paren[ACD]"),
}


def _make_enumerate_ok(text: str) -> str:
    r"""`\begin{enumerate}` 后面紧跟着不带 `\item` 的正文 → 逐行补 `\item`。"""
    def sub(m):
        body = m.group(1)
        if r"\item" in body:
            return m.group(0)
        lines = [ln for ln in body.splitlines() if ln.strip()]
        return (r"\begin{enumerate}" + "\n"
                + "\n".join(r"\item " + ln.strip() for ln in lines) + "\n"
                + r"\end{enumerate}")
    return re.sub(r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", sub, text, flags=re.S)


def compiles(q, mode: str) -> bool:
    tex = export.render_paper([q], mode=mode, title="probe", qid_marks=False,
                              show_answers=(mode == "test"),
                              answers_at_end=False, show_points=False)
    td = Path(tempfile.mkdtemp())
    try:
        p = td / "p.tex"
        p.write_text(tex, encoding="utf-8")
        ok, _log = export.compile_tex(p)
        return ok
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def _balance_braces(text: str) -> str:
    """去掉**多余的** `}`（只会删不配对的右括号，不碰内容）。"""
    depth = 0
    out = []
    for ch in text:
        if ch == "{" and (not out or out[-1] != "\\"):
            depth += 1; out.append(ch)
        elif ch == "}" and (not out or out[-1] != "\\"):
            if depth == 0:
                continue
            depth -= 1; out.append(ch)
        else:
            out.append(ch)
    return "".join(out)


def fix_one(q) -> tuple[str, str, list[str]]:
    """返回 (新 stem, 新 solution, 用了哪些修法)。"""
    used = []
    stem, sol = q.stem, q.solution
    if q.key in MANUAL:
        old, new = MANUAL[q.key]
        if old in stem:
            stem = stem.replace(old, new)
            used.append("manual")
    for o in (q.options or []):
        t = o.text or ""
        # 选项以 `[` 开头：`\item [2, 3)` 会被 enumitem 当成可选 label，
        # 没有配对的 `]` 就一路扫到段末（"Paragraph ended before \@item"）。
        # 区间本来就是数学，包进 `$…$`；顺手去掉粘进来的页脚"考号"。
        if t.strip().startswith("[") and not t.strip().startswith("$"):
            t = re.sub(r"\n\s*(考号|姓名|班级|学号|座位号)\s*", "\n", t).strip()
            o.text = "$%s$" % t
            used.append("options")
            continue
        n = fix_rules(t)
        if n != t:
            o.text = n
            used.append("options")
    s2, a2 = fix_rules(stem), fix_rules(sol)
    if s2 != stem or a2 != sol:
        used.append("common")
    stem, sol = s2, a2
    s3, a3 = _make_enumerate_ok(stem), _make_enumerate_ok(sol)
    if s3 != stem or a3 != sol:
        used.append("enumerate")
    stem, sol = s3, a3
    s4, a4 = _balance_braces(stem), _balance_braces(sol)
    if s4 != stem or a4 != sol:
        used.append("braces")
    return s4, a4, used


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="落盘（默认干跑）")
    ap.add_argument("keys", nargs="*", help="只修这几道（默认整张清单）")
    a = ap.parse_args()

    wanted = a.keys or BAD
    qs = [store.find(k) for k in wanted]
    qs = [q for q in qs if q]
    print("待修：%d 道" % len(qs))
    done, remain = [], []
    for q in qs:
        # 先看现在还坏不坏（渲染器修过的地方，数据可能不用动）
        if compiles(q, "test") and compiles(q, "handout"):
            print("  = %-40s 已能编，不用修" % q.key[-38:])
            done.append((q.key, [], q.stem, q.solution))
            continue
        stem, sol, used = fix_one(q)
        if not used:                      # 选项改了也要算"有修法"
            remain.append((q.key, "没有可自动修的规则"))
            continue
        probe = store.find(q.key)
        probe.stem, probe.solution = stem, sol
        ok = compiles(probe, "test") and compiles(probe, "handout")
        if ok:
            done.append((q.key, used, stem, sol))
            print("  ✓ %-40s %s" % (q.key[-38:], used))
        else:
            remain.append((q.key, "修完仍编不过"))
            print("  ✗ %-40s %s" % (q.key[-38:], used))
    print("可自动修好：%d，剩 %d 道" % (len(done), len(remain)))
    for k, why in remain:
        print("   剩:", k, "|", why)
    if not a.yes:
        print("（干跑，未落盘；加 --yes 落盘）")
        return 0
    # 能验证的都写；修不好的留着人工看，不阻塞其它题
    if remain:
        print("注意：%d 道自动修不好，先不写" % len(remain))
    for key, used, stem, sol in done:
        if not used:
            continue                      # 本来就编得过，不用写
        got = store.read_one(key)
        if not got:
            print("读不到，跳过：", key); continue
        q, vol, sig, chunk = got
        before = q.content_hash()
        q.stem, q.solution = stem, sol
        q.meta["edited_at"] = __import__("time").strftime("%Y-%m-%d %H:%M")
        store.write_one(q, volume=vol, expect_hash=before, expect_sig=sig, chunk=chunk)
    print("已落盘 %d 道" % len(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
