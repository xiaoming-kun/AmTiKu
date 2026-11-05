r"""AmTiKu · 关键词相关度

为什么不用 SQLite FTS5：题库里大量是 **2 个汉字** 的查询（函数、导数、椭圆），
FTS5 的 trigram 分词器至少要吃 3 个字符，2 字查询直接 0 结果；unicode61
又会把整段中文当一个 token。29k 道的量级，直接在内存里扫 + 打分更简单，
而且能精确控制“题干命中 > 考点命中 > 解析命中”的权重。

这里只做**排序**，不做过滤——过滤仍走 `server._kw_hit`，保证“哪些题算命中”
只有一份口径。`score()` 只负责把命中结果按“像不像你要找的”排个序。

## 权重

    +6  题干里出现一次
    +3  答案里出现
    +2  解析里出现
    +4  考点名里出现
    +3  出处/卷名里出现
    +8  出现在题干开头（标题式命中）
    +20 所有词都命中（多词查询时）

数字是拍的，但**顺序**是有意的：题干 > 考点 > 答案/出处 > 解析。
"""
from __future__ import annotations

import re

from .schema import Question

_SPLIT = re.compile(r"[\s,，、;；]+")


def terms(kw: str) -> list[str]:
    """把查询切成词。中文不切字——「函数」就是一个词，整词匹配更准。"""
    return [t for t in _SPLIT.split((kw or "").strip()) if t]


def _source(q: Question, extra: str = "") -> str:
    m = q.meta or {}
    return " ".join(str(x) for x in (
        extra, m.get("book"), m.get("source_label"), m.get("region")) if x)


def score(q: Question, kw: str, extra: str = "") -> int:
    """一道题对 `kw` 的相关度。命中与否由调用方先保证，这里只排序。"""
    ts = terms(kw)
    if not ts:
        return 0
    stem = q.stem or ""
    answer = q.answer or ""
    sol = q.solution or ""
    titles = " ".join(q.point_titles or [])
    src = _source(q, extra)
    # **按字段给固定分，再给一点点次数加成**——不能用“出现次数 × 权重”：
    # 解析里反复提 10 次“函数”，会盖过题干里正儿八经问函数的那道题。
    s = 0
    for t in ts:
        if t in stem:
            s += 40 + 3 * min(stem.count(t), 3)
            if stem[:20].find(t) >= 0:
                s += 10
        if t in answer:
            s += 15 + min(answer.count(t), 2)
        if t in titles:
            s += 12
        if t in src:
            s += 10
        if t in sol:
            s += 6 + min(sol.count(t), 2)
    if all(any(t in x for x in (stem, answer, sol, titles, src)) for t in ts):
        s += 20
    return s


def _selftest() -> int:
    from .schema import Option

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    def mk(key, stem, sol="", points=None):
        return Question(key=key, type="single_choice", stem=stem, solution=sol,
                        options=[Option("A", "1"), Option("B", "2")],
                        points=points or [])

    a = mk("a", "已知函数 $f(x)=x^2$，求单调区间。", "求导得 $f'(x)=2x$。", ["3.1.1"])
    b = mk("b", "已知椭圆 $x^2/4+y^2=1$。", "这里要用到函数的单调性。", ["5.2.1"])
    check("题干命中 > 解析命中",
          score(a, "函数") > score(b, "函数"),
          str((score(a, "函数"), score(b, "函数"))))
    check("空查询得 0", score(a, " ") == 0)
    check("多词切分", terms("函数 单调") == ["函数", "单调"], str(terms("函数 单调")))
    check("题干开头加权",
          score(mk("c", "函数 $f(x)$…"), "函数") >
          score(mk("d", "在平面直角坐标系中，已知一个关于 $x$ 的函数…"), "函数"))
    print("search 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
