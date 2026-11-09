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
from functools import lru_cache

from . import latex_ir
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


# ── 公式查询：识别 + 归一化 + 有界代数等价 ──────────────────────

_MATH_WORD_RE = re.compile(
    r"(?i)(sin|cos|tan|cot|sec|csc|arcsin|arccos|arctan|log|ln|lg|"
    r"sqrt|frac|pi|alpha|beta|gamma|theta|triangle|angle|"
    r"cdot|times|div|leq|geq|neq|sum|int|lim|root|infty)")
_CAMEL_RE = re.compile(r"[a-z][A-Z]")
_SHORT_MATH_RE = re.compile(r"(?i)^[a-z]\d+$")


@lru_cache(maxsize=512)
def looks_math(q: str) -> bool:
    """查询是否像公式。中文词（函数/导数）不算；`6.4.2` 也不算。"""
    q = (q or "").strip()
    if not q:
        return False
    if re.search(r"[\\^_{}=/]", q):
        return True
    if _MATH_WORD_RE.search(q):
        return True
    if _CAMEL_RE.search(q):          # cosB
        return True
    if _SHORT_MATH_RE.match(q):      # x2
        return True
    if re.fullmatch(r"\d+\.\d+", q):  # 0.5
        return True
    return False


def _parse_expr(text: str):
    """归一化后的表达式 → SymPy；解析不了返回 None。"""
    try:
        from sympy.parsing.sympy_parser import (
            convert_xor, implicit_multiplication_application, parse_expr,
            rationalize, standard_transformations)
    except Exception:
        return None
    try:
        return parse_expr(
            text, transformations=standard_transformations + (
                implicit_multiplication_application, convert_xor, rationalize),
            evaluate=True)
    except Exception:
        return None


def _sympy_variants(strict: str) -> list[str]:
    r"""用 SymPy 生成**有限几种**等价写法；不追求定理证明。

    只处理单个表达式（带 `=` 的等式交给文本归一化），并且只做
    expand / factor / together / cancel + 数值的分数/小数互转。
    解析不了、项数过多、异常都安静放弃。
    """
    if not strict or "=" in strict or "<" in strict or ">" in strict:
        return []
    # 没有空格/运算符/括号的单个词（x2、sqrt3、cosb）歧义太大：
    # `x2` 可能是 x^2 也可能是 x*2，交给文本归一化，不猜。
    # 纯数字/小数是例外：`0.5` 要能生成 `1/2`。
    if (" " not in strict
            and not re.search(r"[+\-*/^()]", strict)
            and not re.fullmatch(r"\d+(?:\.\d+)?", strict)):
        return []
    s = strict
    # `sin^2 a` / `sin^2(a)` → `sin(a)**2`
    s = re.sub(
        r"\b(sin|cos|tan|cot|sec|csc|log|ln|arcsin|arccos|arctan)"
        r"\^2\s*([a-z0-9]+)", r"\1(\2)**2", s)
    # `sin a` → `sin(a)`；只认后面跟单个变量的写法
    s = re.sub(
        r"\b(sin|cos|tan|cot|sec|csc|log|ln|arcsin|arccos|arctan)"
        r"\s+([a-z0-9]+)", r"\1(\2)", s)
    s = s.replace("^", "**")
    e = _parse_expr(s)
    if e is None:
        return []
    try:
        from sympy import cancel, expand, factor, nsimplify, together
    except Exception:
        return []
    out: list[str] = []
    for fn in (lambda x: x, expand, factor, together, cancel):
        try:
            v = fn(e)
            if getattr(v, "count_ops", lambda: 0)() > 80:
                continue
            out.append(str(v))
        except Exception:
            continue
    if getattr(e, "is_number", False):
        try:
            r = nsimplify(e)
            if getattr(r, "is_Rational", False):
                out.append(str(r))
                out.append("%d/%d" % (r.p, r.q))
                out.append(str(float(r)))
            elif getattr(r, "is_Integer", False):
                out.append(str(int(r)))
        except Exception:
            pass
    return out


@lru_cache(maxsize=512)
def math_base(q: str) -> tuple[str, ...]:
    """查询本身的严格/宽松写法（不算代数等价）。"""
    strict, loose = latex_ir.math_text(q)
    out: list[str] = []
    for f in (strict, loose):
        if f and len(f) >= 2 and f not in out:
            out.append(f)
    return tuple(out)


@lru_cache(maxsize=512)
def math_forms(q: str) -> tuple[str, ...]:
    r"""查询 → 一组可去内容库匹配的公式文本（严格/宽松 + 等价写法）。

    例：
        `\frac{1}{2}` → `1/2`、`0.5`
        `(x+1)^2`     → `(x+1)^2`、`x^2+2x+1`、`x2+2x+1` …
        `\cos B`      → `cos b`、`cosb`
    """
    strict, loose = latex_ir.math_text(q)
    forms: list[str] = []

    def add(s: str) -> None:
        if s and len(s) >= 2 and s not in forms:
            forms.append(s)

    for f in math_base(q):
        add(f)
    if strict:
        for v in _sympy_variants(strict):
            s2, l2 = latex_ir.math_text(v)
            add(s2)
            add(l2)
    return tuple(forms[:12])


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

    # 公式识别与写法归一
    check("公式识别 cosB", looks_math("cosB"))
    check("公式识别 3/4", looks_math("3/4"))
    check("中文不误判", not looks_math("三角形"))
    check("题号不误判", not looks_math("6.4.2"))
    f_cos = math_forms(r"\cos B")
    check("cosB 归一命中", "cosb" in f_cos, str(f_cos))
    f_half = math_forms(r"\frac{1}{2}")
    check("1/2 与 0.5 等价", "0.5" in f_half and "1/2" in f_half, str(f_half))
    f_sq = math_forms("(x+1)^2")
    check("(x+1)^2 展开写法", any("x2+2x+1" == x or "x^2+2x+1" == x for x in f_sq),
          str(f_sq))
    print("search 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
