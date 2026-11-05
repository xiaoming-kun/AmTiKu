r"""把解析里**用文字写出来的分布列**排成真的表格（探针/干跑用）。

判据严格到"认不出谁是谁就整条不动"：
  · 句子里要有「分布列」；
  · 变量行：`$X$ 依次取 a、b、c`（变量名 + 取 + 列表）；
  · 概率行：`对应的概率 $P$ 依次为 p、q、r`（「概率」二字必须在）；
  · 两行**等长**、每格都是数字或 `$…$`、列数 2—6；
  · 后面那个「（两行五列的表格，见待复核登记）」之类的注解一并删掉——表格已经在卷面上了。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amti import store

VAR_ROW = re.compile(
    r"(?:随机变量\s*)?(\$[A-Za-z\\][^$]{0,6}\$|[A-Za-z])\s*(?:的)?(?:值)?\s*(?:依次)?取\s*"
    r"((?:\$[^$]+\$|[\d.]+)(?:\s*[、，,]\s*(?:\$[^$]+\$|[\d.]+))+)\s*(?=，|,|（|\(|。|$)")
PROB_ROW = re.compile(
    r"(?:对应的)?概率\s*(?:\$P\$|[A-Za-z])?\s*(?:依次)?为\s*"
    r"((?:\$[^$]+\$|[\d.]+|\\d?frac[^，。]{1,28})(?:\s*[、，,]\s*(?:\$[^$]+\$|[\d.]+|\\d?frac[^，。]{1,28}))+)"
    r"\s*(?=（|\(|，|,|。|$)")
ANN = re.compile(r"[（(][^（）()]{0,70}?(?:两行[三四五六七]列|一张两行|列表见|见「待复核」|见待复核)"
                 r"[^（）()]{0,70}[）)]")


def cells(s: str) -> list[str]:
    # 朴素切分就够了：分布列的每一格都是「$…$」或纯数字，
    # 万一某个格子里真带逗号（如坐标），后面的 fullmatch 校验会把它判死、整条不动。
    return [c.strip() for c in re.split(r"[、，,]", s) if c.strip()]


def try_rebuild(sol: str) -> tuple[str, str] | None:
    """认得出来就返回 (新解析, 说明)，认不出来返回 None。"""
    if "分布列" not in sol:
        return None
    mv, mp = VAR_ROW.search(sol), PROB_ROW.search(sol)
    if not mv or not mp or mp.start() < mv.start():
        return None
    vs, ps = cells(mv.group(2)), cells(mp.group(1))
    if not (2 <= len(vs) <= 6) or len(vs) != len(ps):
        return None
    if any(not re.fullmatch(r"\$[^$]+\$|[\d.]+", c) for c in vs + ps):
        return None
    head = "\\begin{tabular}{|" + "c|" * (len(vs) + 1) + "}\n"
    row1 = " & ".join([mv.group(1).strip(), *vs]) + r" \\"
    row2 = " & ".join(["$P$", *ps]) + r" \\"
    tab = head + "\\hline\n" + row1 + "\n\\hline\n" + row2 + "\n\\hline\n\\end{tabular}"
    # 从「$X$ 依次取…」起到概率表末尾整段换成表格；再删掉那个表格注解
    a, b = mv.start(), mp.end()
    new = sol[:a] + tab + sol[b:]
    new = ANN.sub("", new)
    new = re.sub(r"[ \t]+\n", "\n", new)
    new = re.sub(r"\n{3,}", "\n\n", new).strip()
    if len(new) > len(sol) + 600:
        return None
    return new, "%d 列" % len(vs)


def main() -> int:
    hit = 0
    for q in store.load_all():
        r = try_rebuild(q.solution or "")
        if not r:
            continue
        hit += 1
        new, note = r
        print("=" * 90)
        print("%s  (%s)" % (q.key, note))
        print("  前：%s" % (q.solution or "")[:230].replace("\n", "⏎"))
        print("  后：%s" % new[:260].replace("\n", "⏎"))
    print("\n可安全重排：%d 道" % hit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
