r"""AI 候选源码的本地格式清洗：只改格式，不改题意/答案/选项。

先本地做，不花 token；改不动的再交给 agent。
不写题库；调用方拿到结果后仍走 ingest.preview。
"""
from __future__ import annotations

import re

# 复用题库唯一的裸数学符号表，避免另建一份。
try:
    from .normalize import _BARE_MATH
except Exception:                                # pragma: no cover
    _BARE_MATH = {}

_MATH_SPAN = re.compile(r"(?<!\\)\\\[[\s\S]*?\\\]|(?<!\\)\\\([\s\S]*?\\\)"
                        r"|(?<!\\)\$(?!\$)[^$]*?(?<!\\)\$", re.S)


def _display_dollars(s: str) -> tuple[str, int]:
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        return "\n\\[\n%s\n\\]\n" % m.group(1).strip()

    return re.sub(r"\$\$([\s\S]+?)\$\$", repl, s), n


def _paren_delims(s: str) -> tuple[str, int]:
    n = s.count(r"\(") + s.count(r"\)")
    if n:
        s = s.replace(r"\(", "$").replace(r"\)", "$")
    return s, n


def _empty_slots(s: str) -> tuple[str, int]:
    n = 0
    # 先处理 `=($ \paren[A] )`：前面数学没闭合，要补 `$`，不能只删括号。
    pat_eq = re.compile(r"=\s*\(\s*\$?\s*(\\paren\s*\[[^\]]*\]|\\fillin\s*\[[^\]]*\])\s*[）)]")
    s2, k = pat_eq.subn(lambda m: "=$ " + m.group(1), s)
    if k:
        n += k
        s = s2
    # 作答位外层又抄了一个空括号：`($ \paren[A] )` / `（\fillin[]）`
    pat = re.compile(r"[（(]\s*\$?\s*(\\paren\s*\[[^\]]*\]|\\fillin\s*\[[^\]]*\])\s*[）)]")

    def repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        return m.group(1)

    s = pat.sub(repl, s)
    # 漏了数学收尾：`$A\cap B=\paren[A]` → `$A\cap B=$ \paren[A]`
    pat_close = re.compile(r"(\$[^$\n]*?)=\s*(\\paren\s*\[[^\]]*\]|\\fillin\s*\[[^\]]*\])")
    s3, k = pat_close.subn(lambda m: m.group(1) + "=$ " + m.group(2), s)
    if k:
        n += k
        s = s3
    return s, n


def _slot_braces(s: str) -> tuple[str, int]:
    n = 0
    pat = re.compile(r"(\\(?:paren|fillin)\s*\[)\{\{([^{}]*)\}\}(\])")

    def repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        return m.group(1) + "{" + m.group(2).strip() + "}" + m.group(3)

    return pat.sub(repl, s), n


def _bare_unicode(s: str) -> tuple[str, int]:
    if not _BARE_MATH:
        return s, 0
    n = 0
    out: list[str] = []
    pos = 0
    for m in _MATH_SPAN.finditer(s):
        seg = s[pos:m.start()]
        new = "".join("$%s$" % _BARE_MATH[ch] if ch in _BARE_MATH else ch for ch in seg)
        if new != seg:
            n += 1
            # 避免和相邻的 $...$ 拼成 $$
            if out and out[-1].endswith("$") and new.startswith("$"):
                new = " " + new
        out.append(new)
        out.append(m.group(0))
        pos = m.end()
    seg = s[pos:]
    new = "".join("$%s$" % _BARE_MATH[ch] if ch in _BARE_MATH else ch for ch in seg)
    if new != seg:
        n += 1
        out.append(new)
    else:
        out.append(seg)
    return "".join(out), n


def _relations(s: str) -> tuple[str, int]:
    n = 0
    for old, new in ((r"\ge", r"\geqslant"), (r"\le", r"\leqslant")):
        pat = re.compile(re.escape(old) + r"(?![a-zA-Z])")
        s, k = pat.subn(lambda m, _n=new: _n, s)
        n += k
    return s, n


def clean(text: str) -> tuple[str, list[str]]:
    """返回 (清洗后的文本, 做过的改动列表)。"""
    s = str(text or "")
    changes: list[str] = []
    s, n = _display_dollars(s)
    if n:
        changes.append("双美元改行间 %d 处" % n)
    s, n = _paren_delims(s)
    if n:
        changes.append("圆括号数学定界 %d 处" % n)
    s, n = _relations(s)
    if n:
        changes.append("\\ge/\\le 统一为 \\geqslant/\\leqslant %d 处" % n)
    s, n = _empty_slots(s)
    if n:
        changes.append("空作答括号 %d 处" % n)
    s, n = _slot_braces(s)
    if n:
        changes.append("作答位双花括号 %d 处" % n)
    s, n = _bare_unicode(s)
    if n:
        changes.append("裸 Unicode 数学 %d 处" % n)
    return s, changes
