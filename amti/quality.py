r"""入库前的**本地体检**：置信度、答案↔解析一致性、公式能不能渲染。

不调模型、不写库，纯函数，几毫秒一道题。目的是把"看起来没问题的坏题"
在入库前标出来——这些错一旦进库，后面组卷印出去就是事故。

三条判断都刻意保守：**只标"可疑"，不自动改**。改不改由人定。
"""
from __future__ import annotations

import re

_OCR_NOISE = re.compile(r"[□�]|\\\\[a-zA-Z]{6,}")
_TRUNC_TAIL = ("，", ",", "、", "；", ";", "和", "与", "及", "则", "若", "设")
_ANSWER_LETTERS = re.compile(r"^[A-D]{1,4}$")
_SOL_ANSWER = re.compile(r"(?:故选|所以选|答案为|故选[:：])\s*[:：]?\s*([A-D]{1,4})")
#: 行间公式定界符 `\[` / `\]`；**排除 `\\[`**（换行 + 可选行距，见 `display_in_inline`）
_DISPLAY_DELIM = re.compile(r"(?<!\\)\\[\[\]]")


def display_in_inline(s: str) -> bool:
    r"""`$…$` 里夹着行间公式定界符 `\[` / `\]` —— 行内公式漏了收尾 `$`。

    ⚠️ 两条都不能省：
      · **按 `$` 切段再判**，不能写成 `\$[^$]*\\\[[^$]*\$`——那样会把
        「`$x$ ，\[\n…\n\] $y$`」这种**完全合法**的写法也匹配上：
        起点是上一段的收尾 `$`、终点是下一段的开头 `$`，中间夹的正是行间公式。
      · **排除 `\\[`**（换行 + 可选行距）。`cases` 里的 `\\[0.5ex]`、`\\[4pt]`
        到处都是，按子串找 `\[` 会把它们全判成缺陷（实测误报 14 道）。
    """
    segs = (s or "").split("$")
    return any(_DISPLAY_DELIM.search(seg) for i, seg in enumerate(segs) if i % 2)


def _brace_ok(s: str) -> bool:
    depth = 0
    for ch in s.replace(r"\{", "").replace(r"\}", ""):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _pair_ok(s: str, a: str, b: str) -> bool:
    return s.count(a) == s.count(b)


def check(stem: str, sol: str, answer: str, qtype: str,
          options: dict | None = None) -> dict:
    r"""一道题 → `{"conf": {...}, "issues": [...], "level": "高|中|低"}`。"""
    stem, sol, answer = (stem or "").strip(), (sol or "").strip(), (answer or "").strip()
    conf = {"stem": 1.0, "answer": 1.0, "solution": 1.0}
    issues: list[str] = []

    # ── 题干 ────────────────────────────────────────────────
    if not stem:
        conf["stem"] = 0.0
        issues.append("题干为空")
    else:
        if stem.endswith(_TRUNC_TAIL):
            conf["stem"] -= 0.35
            issues.append("题干疑似被截断")
        if _OCR_NOISE.search(stem):
            conf["stem"] -= 0.35
            issues.append("题干含乱码字符")
        if not _brace_ok(stem):
            conf["stem"] -= 0.25
            issues.append("题干花括号不配平")
        if stem.count("$") % 2:
            conf["stem"] -= 0.25
            issues.append("题干 `$` 不成对")
        if display_in_inline(stem):
            conf["stem"] -= 0.4
            issues.append("题干 `\\[…\\]` 夹在 `$…$` 里（行内公式没闭合）")

    # ── 答案 ────────────────────────────────────────────────
    if qtype in ("single_choice", "multi_choice"):
        if not answer:
            conf["answer"] = 0.0
            issues.append("选择题没有答案")
        elif not _ANSWER_LETTERS.match(answer):
            conf["answer"] -= 0.4
            issues.append("选择题答案不是 A–D")
        elif options and any(answer_letter not in options for answer_letter in answer):
            conf["answer"] -= 0.3
            issues.append("答案字母不在选项里")
    elif options is not None and qtype in ("single_choice", "multi_choice") \
            and len(options) < 4:
        conf["answer"] = min(conf["answer"], 0.6)
        issues.append("选项只有 %d 个（应为 4）" % len(options))
    elif qtype == "fill_in_blank":
        if not answer:
            conf["answer"] = 0.0
            issues.append("填空题没有答案")

    # ── 解析 ────────────────────────────────────────────────
    if not sol:
        conf["solution"] = 0.0
        issues.append("没有解析")
    else:
        if len(sol) < 24:
            conf["solution"] -= 0.4
            issues.append("解析过短")
        if sol.endswith(("，", ",", "、", "；", ";", "所以", "因此", "=")):
            conf["solution"] -= 0.35
            issues.append("解析疑似被截断")
        if not _brace_ok(sol):
            conf["solution"] -= 0.4
            issues.append("解析花括号不配平")
        if sol.count("$") % 2:
            conf["solution"] -= 0.3
            issues.append("解析 `$` 不成对")
        if display_in_inline(sol):
            conf["solution"] -= 0.4
            issues.append("解析 `\\[…\\]` 夹在 `$…$` 里（行内公式没闭合）")
        if not _pair_ok(sol, r"\left", r"\right"):
            conf["solution"] -= 0.2
            issues.append(r"解析 `\left`/`\right` 不成对")
        m = _SOL_ANSWER.search(sol)
        if m and answer and m.group(1) != answer:
            conf["solution"] -= 0.3
            issues.append("答案与解析结论不一致（解析说 %s）" % m.group(1))

    # ── 版面噪声（黑名单之外的新写法，靠这一条兜住）──────────
    for tag, txt in (("题干", stem), ("解析", sol)):
        if _NOISE.search(txt or ""):
            conf["stem" if tag == "题干" else "solution"] -= 0.3
            issues.append("%s 含版面噪声（HTML/图注）" % tag)

    for k in conf:
        conf[k] = round(max(0.0, min(1.0, conf[k])), 2)
    overall = min(conf.values())
    level = "高" if overall >= 0.85 else ("中" if overall >= 0.55 else "低")
    return {"conf": conf, "issues": issues, "level": level, "overall": overall}


_MATH_SPAN = re.compile(r"(\$[^$]*\$)|(\\\[[\s\S]*?\\\])")


def repair_math(s: str) -> str:
    r"""把**能确定修好**的 LaTeX 硬伤就地修掉。

    目前只做一件事：一段公式里 `\left` 与 `\right` 数量不等时，把这几个
    `\left`/`\right` 全部去掉。括号字符还在，KaTeX 照样能排，只是不再自动
    缩放——比整段渲染失败（界面上直接变成一串红字）好得多。

    ⚠️ 只修**数量不等**这一种，且只在公式段内动手；不猜语义、不动括号本身。
    实测：27B「修」过一次之后仍然 2 个 `\left` 对 1 个 `\right`——它并不
    真的校验平衡，所以这一层必须由代码兜底。
    """
    def one(m):
        seg = m.group(0)
        if seg.count(r"\left") != seg.count(r"\right"):
            seg = seg.replace(r"\left", "").replace(r"\right", "")
        return seg
    return _MATH_SPAN.sub(one, s or "")


#: 各种"填空位"的写法（27B 常写 `\_\_\_\_`，也有 `____`、`\underline{\hspace{2em}}`）
_BLANK_RUN = re.compile(
    r"(?:\\_){2,}|_{3,}|\\underline\{\\hspace\{[^}]*\}\}|\\rule\{[^}]*\}\{[^}]*\}")


def fix_blanks(stem: str, answer: str, qtype: str) -> str:
    r"""填空题的卷面空位统一成 `\fillin[答案]`。

    规范要求空位用 `\fillin[…]` 写（答案就在参数里）。27B 经常只画一串
    `\_\_\_\_`——渲染出来是一堆反斜杠，看着像坏了，而且**答案与卷面对不上**。
    这里只处理**第一个**空位（多空题保持原样，避免把答案塞错位置）。
    """
    if qtype != "fill_in_blank" or not (answer or "").strip():
        return stem
    if "fillin" in (stem or ""):
        return stem
    return _BLANK_RUN.sub(lambda _m: "\\fillin[%s]" % answer.strip(), stem or "", count=1)


_HTML_BLOCK = re.compile(r"<details\b[\s\S]*?</details>", re.I)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


#: 连续 ≥3 行、每行只有一两个字母/数字 —— 这是图里的顶点标注（A B C1 P …），
#: `<details>` 被清掉后它们会剩下来，混在题干末尾。
_LABEL_RUN = re.compile(r"(?m)(?:^[A-Za-z][0-9]?\s*$\n){3,}")


def strip_html(s: str) -> str:
    r"""去掉识别结果里混进正文的 HTML 与图注残留。

    它对"带文字的图"会输出

        <details><summary>text_image</summary>A1 C1 B1 …</details>

    这不是 markdown 图片语法，`sanitize()` 里那条 `![]()` 规则抓不到，
    于是整段标签就进了题干/解析（界面上原样显示 `<details>`）。
    """
    s = _HTML_BLOCK.sub("（图）", s or "")
    s = _HTML_TAG.sub("", s)
    s = _LABEL_RUN.sub("", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


#: 版面噪声的特征：HTML 标签、图注关键字（text_image/details）、连续短行字母串
_NOISE = re.compile(r"</?[a-z]+[\s>]|text_image|\bdetails\b", re.I)


# ── P0：串题 / 串行 / 选项异常 ───────────────────────────────

_LEAD_NO = re.compile(r"^\s*(\d{1,2})\s*[.、．]")
_Q_LINE = re.compile(r"(?m)^\s*(\d{1,2})\s*[.、．]\s*\S")
_DUP_PREFIX = 24


def _norm(s: str) -> str:
    return re.sub(r"[\s$\\{}^_]", "", s or "")


def check_ownership(sol: str, n: int, prev_sol: str = "") -> list[str]:
    r"""解析是不是这道题的。

    两种串法都实测见过：
      * 解析开头写着**别的题号**（`5.` 出现在第 6 题里）；
      * 解析开头**原样重复上一题**（第 6 题开头是第 5 题的尾巴，末尾才是自己的）。
    """
    issues: list[str] = []
    m = _LEAD_NO.match(sol or "")
    if m and int(m.group(1)) != int(n):
        issues.append("解析开头是第 %s 题" % m.group(1))
    if prev_sol:
        a, b = _norm(sol)[:_DUP_PREFIX], _norm(prev_sol)[:_DUP_PREFIX]
        if a and a == b:
            issues.append("解析开头与上一题重复")
        # **开头撞上一题的结尾**：切范围时把上一题尾巴带进来了
        # （实测第 6 题以第 5 题结尾那段 `{aligned…}` 开头）。
        head = _norm(sol)[:20]
        if head and len(head) >= 12 and head in _norm(prev_sol):
            issues.append("解析开头接了上一题的结尾")
    return issues


def check_stem_leak(stem: str, n: int) -> list[str]:
    r"""题干里是不是混进了**别的题**（两题被并成一题）。

    判据：题干里出现一行以别的题号开头的 `12.`。同一题号出现不算。
    """
    nums = {int(x) for x in _Q_LINE.findall(stem or "")}
    others = sorted(x for x in nums if x != int(n))
    return ["题干里混入了第 %s 题" % "、".join(map(str, others[:3]))] if others else []


def check_options_sane(opts: dict) -> list[str]:
    r"""选项看着对不对：重复、空、过长（把解析并进来了）。"""
    if not opts:
        return []
    issues: list[str] = []
    vals = [str(v or "").strip() for v in opts.values()]
    if any(not v for v in vals):
        issues.append("有选项是空的")
    seen = {}
    for k, v in zip(opts.keys(), vals):
        if v and v in seen:
            issues.append("选项 %s 与 %s 内容相同" % (seen[v], k))
            break
        seen[v] = k
    if vals and max(len(v) for v in vals) > 120 and min(len(v) for v in vals) < 20:
        issues.append("有选项过长（可能并进了别的内容）")
    return issues
