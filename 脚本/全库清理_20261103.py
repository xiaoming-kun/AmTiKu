#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-11-03 全库清理：3 道 P0 + 8 个悬空 dup_of。

为什么不用 `amti/fixups.py` 的台账：那张账里 1,288 条历史订正有几十条
`expect` 已经和现状对不上（题后来又被别的规则改过），而 `fixups.run()`
是「一条对不上就整批不执行」——新订正会被旧账一起卡死。这里用同一套
安全边界（先核对、改完 conform、整库一次写回、留变更记录），只是不走那张账。

只改 11 道题：
  · `2026精选模拟题/P1108#73`  解析末尾的「答案应为 C」裁决话术
  · `2026精选模拟题/深圳中学10月质量检测#7`  解析结论 A 与答案 B 冲突
  · `高考真题汇编/2012/广东卷（文）#17`  表格后多一个 `}`
  · 8 道 `dup_of` 指向已删除题的悬空引用（清掉绑定，不猜新目标）

用法：
    python3 脚本/全库清理_20261103.py          # 干跑
    python3 脚本/全库清理_20261103.py --apply  # 落盘
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import conform, store  # noqa: E402

# ── 三条 P0 ────────────────────────────────────────────────────────────

P1108 = "2026精选模拟题/P1108#73"
P1108_NOTE = ("（若允许两个相等的实数根，则 $m=-2$ 时两根同为 $1$，"
              "也落在 $(0,2)$ 内，答案应为 C；本题按「不相等」读，"
              "故判别式取 $\\Delta>0$。）")

SHENZHEN = "2026精选模拟题/深圳中学10月质量检测#7"
SHENZHEN_SOL = r"""当 $x \leqslant a$ 时，$f(x)=-(x+1)^2+1$；当 $x>a$ 时，$f(x)=1-2x$ 单调递减，其函数值可无限接近 $1-2a$，但取不到 $1-2a$。

若 $a<-1$，左侧在 $x=a$ 处取得最大值 $-a^2-2a$，而
\[
(1-2a)-(-a^2-2a)=a^2+1>0,
\]
右侧的函数值可以超过左侧的最大值，且 $1-2a$ 取不到，所以整个函数没有最大值。

若 $a\geqslant -1$，左侧在 $x=-1$ 处取得最大值 $1$。要使整个函数存在最大值，只需右侧的函数值不超过 $1$，即
\[
1-2x<1\quad(x>a)
\]
恒成立，等价于 $a\geqslant 0$。

所以 $f(x)$ 存在最大值当且仅当 $a\geqslant 0$，故 $a$ 的最小值为 $0$。故选 B。"""

GUANGDONG = "高考真题汇编/2012/广东卷（文）#17"

# ── 八个悬空 dup_of：目标 key → 现在只剩「源题」 ──────────────────────
# 这些目标题已经被删（多是清理重复题时删掉了原题），留着 dup_of 只会让
# `semantic.dup_of_dangling` 一直报，组卷/界面也拿不到可跳转的目标。
DANGLING = {
    "高考真题汇编/2014/山东卷（理）#5": "高考真题汇编/2014/山东卷（文）#5",
    "高考真题汇编/2014/福建卷（文）#15": "高考真题汇编/2010/福建卷（文）#7",
    "2026精选模拟题/P0675#9": "高考真题汇编/2017/全国III卷（文）#16",
    "高考真题汇编/2000/大纲卷（理）#21": "高考真题汇编/2000/大纲卷（文）#21",
    "模拟题/191.山东齐鲁名校大联考2026届高三上学期12月联考#13": "手工录入/001#1",
    "模拟题/2026届内蒙古赤峰市高三3·20模拟测试#5": "高考真题汇编/2010/福建卷（文）#7",
    "模拟题/西南名校联考2026届3+3+3名校联盟高三下学期4月联考#3": "高考真题汇编/2007/陕西卷（文）#4",
    "模拟题/江西萍乡市2026届高三二模#5": "手工录入/001#1",
}


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def fix(qs):
    """在内存里改。返回 (说明列表, 改过的题)。"""
    by = {q.key: q for q in qs}
    notes: list[str] = []
    touched = []
    stamp = _now()

    # 1) P1108#73：解析正文本身是对的，删掉末尾那段「若允许相等根…答案 C」
    q = by.get(P1108)
    if q is None:
        raise SystemExit(f"找不到 {P1108}")
    if P1108_NOTE not in (q.solution or ""):
        raise SystemExit(f"{P1108} 的解析里没有预期的裁决话术，可能已经改过；中止")
    q.solution = (q.solution or "").replace(P1108_NOTE, "").rstrip()
    q.meta["fixed_at"] = stamp
    notes.append(f"{P1108}：删掉与答案 D 冲突的「答案应为 C」裁决话术")
    touched.append(q)

    # 2) 深圳#7：答案 B 是对的，解析最后一段把「a≥-1」当成了充要条件；
    #    正确的是 a≥0（-1≤a<0 时右支上确界 1-2a>1，整体无最大值）。
    q = by.get(SHENZHEN)
    if q is None:
        raise SystemExit(f"找不到 {SHENZHEN}")
    if q.answer.strip() != "B":
        raise SystemExit(f"{SHENZHEN} 的答案不是 B（现在是 {q.answer!r}），中止")
    if "故选 A" not in (q.solution or ""):
        raise SystemExit(f"{SHENZHEN} 的解析里没有预期的「故选 A」，可能已经改过；中止")
    q.solution = SHENZHEN_SOL
    q.meta["fixed_at"] = stamp
    notes.append(f"{SHENZHEN}：解析结论 A→B，改为按「右支上确界 1-2a」判定，a≥0")
    touched.append(q)

    # 3) 2012 广东文#17：tabular 后多了一个 `}`，会把后面的 tikz 环境吞掉
    q = by.get(GUANGDONG)
    if q is None:
        raise SystemExit(f"找不到 {GUANGDONG}")
    stem = q.stem or ""
    if "\\end{tabular}\n}\n\\end{center}" not in stem:
        raise SystemExit(f"{GUANGDONG} 的题干里没有预期的多余花括号，可能已经改过；中止")
    q.stem = stem.replace("\\end{tabular}\n}\n\\end{center}",
                          "\\end{tabular}\n\\end{center}", 1)
    q.meta["fixed_at"] = stamp
    notes.append(f"{GUANGDONG}：去掉表格后多余的 `}}`（原为 `\\end{{tabular}}}}`）")
    touched.append(q)

    # 4) 八个悬空 dup_of：清掉绑定。不猜新目标——猜错比悬空更糟。
    for key, target in DANGLING.items():
        q = by.get(key)
        if q is None:
            raise SystemExit(f"找不到 {key}")
        if q.meta.get("dup_of") != target:
            raise SystemExit(
                "%s 的 dup_of 现在是 %r，不是预期的 %r；中止"
                % (key, q.meta.get("dup_of"), target))
        q.meta.pop("dup_of", None)
        q.meta.pop("dup_score", None)
        notes.append(f"{key}：清掉悬空 dup_of（原指向已删除的 {target}）")
        touched.append(q)

    return notes, touched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的写回；默认干跑")
    a = ap.parse_args()

    qs, sig = store.load_for_update()
    notes, touched = fix(qs)

    # 改完必须仍然合规：结构 + 规范两层，任何一条不过都不写
    bad = [(q.key, p) for q in touched for p in q.problems()]
    if bad:
        for k, p in bad:
            print("✗", k, p)
        raise SystemExit("结构校验不过，未写回")
    viol = conform.run(touched)
    if viol:
        for v in viol:
            print("✗", v)
        raise SystemExit("规范审查不过，未写回")

    print("将改动 %d 道：" % len(touched))
    for n in notes:
        print("  · " + n)
    if not a.apply:
        print("\n干跑结束；加 --apply 落盘。")
        return 0

    rep = store.rewrite_all(qs, based_on=sig)
    print("\n已写回：%d 道，%d 卷" % (rep["count"], rep["volumes"]))

    # 留痕（和 fixups 一样的格式，方便以后搜）
    out = ROOT / "变更记录" / ("%s_全库清理.md" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.write_text(
        "# 全库清理（P0 + 悬空 dup_of）\n\n"
        "- 时间：%s\n- 改动：%d 道\n- 写回：%d 卷 / %d 道\n\n%s\n"
        % (_now(), len(touched), rep["volumes"], rep["count"],
           "\n".join("- " + n for n in notes)),
        encoding="utf-8")
    print("变更记录：" + str(out.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
