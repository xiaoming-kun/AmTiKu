#!/usr/bin/env python3
r"""标准化 exam-zh 整卷 `.tex` → 题库可录入的源材料。

上游规范：**`设计/试卷扫描标准化规范-交给大模型.md`**。
按那份规范交付的文件，这个脚本几乎不用动手；已经交来的旧文件
（`~/Desktop/27年试卷/tex/document*.tex`）方言很重，这里把差异一档一档抹平。

    一份 .tex ──拆卷──▶ 每卷的题目块 ──逐块转换──▶ 源材料 .tex + 转换报告

**切块不自己写**：复用录入端 `amti.ingest.split_source`（全项目唯一的题目切块入口）。
`\( \)`→`$ $`、`[label=…]`、「（本小题N分）」、方括号保护这些**也不自己做**：
留给 `amti.normalize` 的 ENTRY 规则（`ingest` 当场会跑）。

本脚本只干规范器兜不住的六件事：

1. **答案搬进作答位**。源文件把答案写成解析开头的「答案：B。」，那不是题库的载体
   （`latex_ir.ANSWER_CMD_RE` 只认 `\textbf{答案：}`）。读不出来就是「缺答案」→ 整批被拒。
2. **`\underline{\hspace{3cm}}` 换成 `\fillin[…]`**。`normalize._BLANK_ANY` 的
   `\underline\{[^{}]*\}` 不吃套花括号的写法，留着它程序只会**再补一个空位**，
   把整串答案塞进一个槽，多空题直接坏。
3. **`tabular` 排的四个图象选项拆回 `choices`**。`tabular` 里的 `A. B. C. D.` 不认作选项，
   题型会判成解答题、答案无处安放。
4. **解析里的 `enumerate` 摊平成 `(1)(2)` 行首文字**。规范只管题干用 `enumerate`；
   解析栏是分段叙述，前端的 `convertEnumerate` 走的是题干那条路，留着环境就是渲染盲区。
5. **摘掉解析开头的栏目标记**（`【解析】`/`【详解】`）。去掉它是 **MIGRATE** 级规则，
   录入当场的 ENTRY **不跑**，不清就跟着印进讲义。
6. **逐题内容订正（FIXES 表）**：凭据写在表里，报告里逐条列出；`find` 命不中就报警**不硬改**。

## 用法

    python3 脚本/标准化卷录入.py build <文件.tex> \
            --labels 江苏南通2027届高三10月,江苏百校大联考2027届高三10月 \
            --year 2027 --region 江苏 [--book 模拟题] [--tag] [--drop 南通:17,18,19]

    --tag   用本机 27B 给每道题打考点（`amti.record.tag_point`；认不出就不打）
    --drop  按「卷名关键词:题号,题号」排除，不写进源材料

产物落 `数据/录题/标准化卷_<文件名>/`：每卷一个 `.tex`（直接喂 `amti.py ingest --file`）
加一份 `转换报告_<卷名>.md`。**本脚本不写库**——入库仍走 `amti/ingest.py` 唯一入口。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import ingest as ig                                    # noqa: E402
from amti import normalize as N                                  # noqa: E402
from amti.latex_ir import fillin_answers, paren_answers          # noqa: E402

ENV_RE = re.compile(r"\\begin\{(question|problem)\}")
SOL_BEG, SOL_END = r"\begin{solution}", r"\end{solution}"
SOL_RE = re.compile(r"\\begin\{solution\}(.*?)\\end\{solution\}", re.S)
CHOICES_RE = re.compile(r"\\begin\{choices\}(?:\[[^\]]*\])?(.*?)\\end\{choices\}", re.S)
CENTER_TABULAR_RE = re.compile(
    r"\\begin\{center\}\s*\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}\s*\\end\{center\}",
    re.S)
ANSWER_LINE_RE = re.compile(r"^[\t ]*答案[：:][\t ]*(.+?)[\t ]*$", re.M)
COLUMN_TAG_RE = re.compile(r"^\s*【\s*(?:解析|详解|答案|解答|试题解析)\s*】\s*")
BLANK_RE = re.compile(r"\\underline\s*\{\\hspace\{[^{}]*\}\}|\\underline\s*\{\\phantom\{[^{}]*\}\}|_{2,}")
EMPTY_PAREN_RE = re.compile(r"[（(]\s*(?:\\(?:quad|qquad))?\s*[）)]")
SECTION_RE = re.compile(
    r"\\noindent\s*\{\\bfseries\s*([一二三四五六七八九十])[、.]?\s*"
    r"(单项选择题|单选题|多项选择题|多选题|选择题|填空题|解答题)")
META_TALK_RE = re.compile(r"解答略|见原解析|根据标准答案|OCR\s*识别|（原卷|原卷OCR")
ENUM_SOL_RE = re.compile(r"\\begin\{enumerate\}(?:\[[^\]]*\])?\s*(.*?)\\end\{enumerate\}", re.S)
ITEM_SPLIT_RE = re.compile(r"\\item\b")

# 节标题里的题型 → 题库 type
SEC_TYPE = {"单项选择题": "single_choice", "单选题": "single_choice",
            "多项选择题": "multi_choice", "多选题": "multi_choice",
            "选择题": "", "填空题": "fill_in_blank", "解答题": "detailed_answer"}


# ── 1. 拆卷 ───────────────────────────────────────────────────────────

def doc_body(text: str) -> str:
    m = re.search(r"\\begin\{document\}(.*)\\end\{document\}", text, re.S)
    return m.group(1) if m else text


def title_name(seg: str) -> str:
    """从标题块聚出卷名；不是卷名（插图、公式排版）返回空串。"""
    parts = []
    for g in re.findall(r"\{([^{}]*?)\}", seg):
        t = re.sub(r"\\[a-zA-Z]+", " ", g)
        t = re.sub(r"\s+", "", t).strip("，,、　 ")
        if t and re.search(r"届|试|考|卷|联考|调研|测评|数学", t):
            parts.append(t)
    return " ".join(parts)


def split_papers(body: str) -> list[tuple[str, str]]:
    r"""按**顶层卷名标题块**切卷。题目块内部的 `center`（插图、四选一图象）不算分卷点。"""
    marks: list[tuple[int, int, str]] = []
    i, n = 0, len(body)
    while i < n:
        m_env = ENV_RE.search(body, i)
        ce = body.find(r"\begin{center}", i)
        if ce >= 0 and (m_env is None or ce < m_env.start()):
            e = body.find(r"\end{center}", ce)
            if e < 0:
                break
            seg = body[ce:e]
            if r"\bfseries" in seg or r"\Large" in seg:
                name = title_name(seg)
                if name:
                    marks.append((ce, e + len(r"\end{center}"), name))
            i = e + len(r"\end{center}")
            continue
        if m_env is None:
            break
        end = ig._find_env_end(body, m_env.end(), m_env.group(1))
        if end < 0:
            break
        i = end
    if not marks:
        return [("未识别卷名", body)]
    out = []
    for k, (s, _e, name) in enumerate(marks):
        stop = marks[k + 1][0] if k + 1 < len(marks) else len(body)
        out.append((name, body[s:stop]))
    return out


def dedent(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"(?m)^[ \t]+", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


# ── 2. 逐块转换 ───────────────────────────────────────────────────────

def block_env(block: str) -> tuple[str, str]:
    """返回 (环境名, 环境内部正文)。"""
    b = block.strip()
    m = ENV_RE.match(b)
    if not m:
        return "", ""
    env = m.group(1)
    tail = r"\end{%s}" % env
    inner = b[m.end():]
    if inner.rstrip().endswith(tail):
        inner = inner.rstrip()[: -len(tail)]
    return env, inner


def flatten_solution_enumerate(sol: str) -> tuple[str, int]:
    r"""解析栏里的 `enumerate` 摊平成 `(1)`、`(2)` 行首文字。

    编号跟 `label=` 走：`arabic` → （1）用半角 `(1)`（与库里存量叙述体一致），
    `roman` → `(i)`。没有 `label=` 时按 arabic。
    """
    n = 0
    while True:
        m = ENUM_SOL_RE.search(sol)
        if not m:
            return sol, n
        opt = re.search(r"\\begin\{enumerate\}\s*\[([^\]]*)\]", m.group(0))
        roman = bool(opt and "roman" in opt.group(1))
        items = [dedent(p) for p in ITEM_SPLIT_RE.split(m.group(1))[1:] if p.strip()]
        if not items:
            return sol, n
        lines = []
        for k, t in enumerate(items, 1):
            tag = "(%s)" % to_roman(k).lower() if roman else "(%d)" % k
            lines.append("%s %s" % (tag, t))
        sol = sol[:m.start()] + "\n\n".join(lines) + sol[m.end():]
        n += 1


def to_roman(k: int) -> str:
    tbl = {1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii", 8: "viii"}
    return tbl.get(k, str(k))


def tabular_to_choices(inner: str) -> tuple[str, bool]:
    m = CENTER_TABULAR_RE.search(inner)
    if not m:
        return inner, False
    row = m.group(1).strip()
    row = re.sub(r"\\\\\s*$", "", row)
    cells = [dedent(c) for c in re.split(r"(?<!\\)&", row) if dedent(c)]
    if len(cells) < 2:
        return inner, False
    items = [re.sub(r"^[A-D]\s*[.、]\s*", "", c) for c in cells]
    new = "\n\\begin{choices}\n" + "\n".join("\\item " + it for it in items) + "\n\\end{choices}\n"
    return inner[:m.start()] + new + inner[m.end():], True


def put_paren(stem: str, answer: str) -> tuple[str, str]:
    r"""把答案放进**作答括号所在的位置**，返回 (新题干, 备注)。

    * 括号在句末（绝大多数题）：换掉它即可。
    * 括号在中间、后面还跟着插图（百校卷第 10 题就是这样）：**原地换**。
      早先无条件追加到题干末尾，`\paren[ACD]` 落到了 `\end{center}` 后面，
      卷面上作答位跑到图下头，而 ENTRY 的「去掉残留的空作答括号」还会把
      原位置那个空括号删掉——作答位就两头都没有了。
    * 压根没有作答括号：缀在末尾，并告警。
    """
    hits = list(EMPTY_PAREN_RE.finditer(stem))
    if hits:
        m = hits[-1]
        note = "" if m.end() >= len(stem.rstrip()) else "作答括号不在句末（后面有插图），已原地替换"
        return stem[:m.start()] + "\\paren[%s]" % answer + stem[m.end():], note
    return stem.rstrip() + "\\paren[%s]" % answer, "题干里没有作答括号，已缀在末尾"


def split_answers(raw: str, holes: int) -> list[str]:
    for sep in ("；", ";", "，"):
        parts = [p.strip() for p in raw.split(sep) if p.strip()]
        if len(parts) == holes:
            return parts
    return []


def verdict_mismatch(sol: str, answer: str) -> str:
    r"""解析里「X 正确／Y 错误」的判定集合与答案对不对得上。**只提示，不拦**。

    形态太杂（「排除 B、C」「选项 B 错」「B 不对」），认错了不该挡录入；
    认对了能抓出真事故——南通卷第 9 题就是这么露出来的。
    """
    if not answer:
        return ""
    yes = {m.group(1) for m in re.finditer(r"([A-D])\s*(?:正确|成立|对)[，,。]?\s*$", sol, re.M)}
    yes |= {m.group(1) for m in re.finditer(r"([A-D])\s*正确", sol)}
    no_ = {m.group(1) for m in re.finditer(r"([A-D])\s*(?:错误|不成立|不对|不正确)", sol)}
    yes -= no_
    got = set(re.sub(r"[^A-D]", "", answer))
    if not yes and not no_:
        return ""
    if yes and yes != got:
        return "解析判「正确」的是 %s，答案栏是 %s" % ("".join(sorted(yes)), "".join(sorted(got)))
    if no_ & got:
        return "解析判「错误」的 %s 却进了答案 %s" % ("".join(sorted(no_ & got)), answer)
    return ""


def content_warnings(it: dict) -> list[str]:
    """内容级告警。**订正之后要重跑一遍**，否则改好了还挂着旧告警。"""
    out: list[str] = []
    sol = it["solution"]
    if not sol.strip():
        out.append("解析为空——半成品，入库闸门会拒收")
    gaps = re.findall(r"【缺：[^】]*】", sol)
    if gaps:
        out.append("解析里有 %d 处【缺：…】占位（原卷就没有，不许编）：%s"
                   % (len(gaps), "；".join(g[:26] for g in gaps)))
    if it["type"] in ("single_choice", "multi_choice", "fill_in_blank") and not it["answer"]:
        out.append("★ 答案读不出来——这道题不能入库")
    dup = [o for o in it["options"] if it["options"].count(o) > 1]
    if dup:
        out.append("有两个选项文字完全相同：%s" % dup[0][:28])
    if META_TALK_RE.search(sol):
        out.append("解析里夹着工作备注：%s" % sorted(set(META_TALK_RE.findall(sol))))
    bad = verdict_mismatch(sol, it["answer"])
    if bad:
        out.append(bad)
    return out


def convert_block(block: str) -> tuple[dict | None, list[str]]:
    """一块题 → item（字段齐、还没拼 LaTeX）。第二个返回值是这一块的告警。"""
    warn: list[str] = []
    env, inner = block_env(block)
    if not env:
        return None, ["认不出题目环境"]

    sol_m = SOL_RE.search(inner)
    sol = dedent(sol_m.group(1)) if sol_m else ""
    if sol_m:
        inner = inner[:sol_m.start()] + inner[sol_m.end():]

    # 答案从解析里搬出来（旧方言）；新方言直接写在作答位里，没有这一行也正常
    a_raw = ""
    am = ANSWER_LINE_RE.search(sol)
    if am:
        a_raw = am.group(1).strip().rstrip("。．.").strip()
        sol = (sol[:am.start()] + sol[am.end():]).strip()
    sol = COLUMN_TAG_RE.sub("", sol)
    sol, n_flat = flatten_solution_enumerate(sol)
    if n_flat:
        warn.append("解析里的 enumerate 已摊平成 (1)(2)（%d 处）" % n_flat)

    inner, swapped = tabular_to_choices(inner)
    if swapped:
        warn.append("四个图象选项原为 tabular，已拆成 choices")

    cm = CHOICES_RE.search(inner)
    opts: list[str] = []
    if cm:
        raw = cm.group(1)
        opts = [dedent(p) for p in ITEM_SPLIT_RE.split(raw)[1:] if p.strip()]
        inner = inner[:cm.start()] + inner[cm.end():]

    stem = dedent(inner)
    n_blank = len(BLANK_RE.findall(stem))
    # **作答位已经有答案**＝这份材料本来就按规范交付，照抄，别再搬一次
    have_paren = [a for a in paren_answers(stem) if a.strip()]
    have_fillin = [a for a in fillin_answers(stem) if a.strip()]

    kind = ("detailed_answer" if env == "problem" else
            "choice" if opts else "fill" if (n_blank or have_fillin) else "")
    if not kind:
        return None, warn + ["无选项、无空位、非 problem——题型判不出"]

    answer = ""
    if kind == "choice":
        letters = re.sub(r"[^A-Da-d]", "", a_raw).upper()
        if have_paren:
            if letters and letters != have_paren[-1].strip():
                return None, warn + ["作答位 \\paren[%s] 与解析里的「答案：%s」不一致——不敢猜"
                                     % (have_paren[-1].strip(), letters)]
            answer = re.sub(r"[^A-Da-d]", "", have_paren[-1]).upper()
        elif letters:
            answer = letters
            stem, note = put_paren(stem, answer)
            if note:
                warn.append(note)
        else:
            warn.append("作答位是空的、解析里也没有「答案：」——答案读不出来")
        if answer:
            kind = "multi_choice" if len(answer) > 1 else "single_choice"
    elif kind == "fill":
        if have_fillin:
            parts = have_fillin
            answer = "；".join(p.strip() for p in parts)
            if n_blank:
                warn.append("题干里既有填好的 `\\fillin` 又有没填的空位——没填的那个不动，等人工")
        else:
            parts = [re.sub(r"\\\((.+?)\\\)", r"$\1$", p, flags=re.S)
                     for p in split_answers(a_raw, n_blank)]
            if not parts:
                return None, warn + ["答案段数与空位数 %d 对不上（原文 %r）" % (n_blank, a_raw[:24])]
            out, pos = [], 0
            for m_b, p in zip(BLANK_RE.finditer(stem), parts):
                out.append(stem[pos:m_b.start()])
                out.append("\\fillin[%s]" % N.protect(p))
                pos = m_b.end()
            out.append(stem[pos:])
            stem = "".join(out)
            answer = "；".join(parts)
        kind = "fill_in_blank"
    else:
        kind = "detailed_answer"
        answer = ""                       # 解答题答案栏由 ENTRY 规则补「见解析」

    item = {"env": env, "type": kind, "stem": stem, "options": opts,
            "answer": answer, "solution": sol, "n_blank": n_blank,
            "points": [], "warn": warn}
    return item, warn


# ── 3. 拼 LaTeX ───────────────────────────────────────────────────────

def render(item: dict) -> str:
    tex = "\\begin{%s}\n%s\n" % (item["env"], item["stem"])
    if item["options"]:
        tex += "\\begin{choices}\n" + "\n".join("  \\item " + o for o in item["options"]) + "\n\\end{choices}\n"
    if item["solution"].strip():
        tex += SOL_BEG + "\n" + item["solution"] + "\n" + SOL_END + "\n"
    return tex + "\\end{%s}" % item["env"]


def render_meta(item: dict, no: int, name: str, args) -> str:
    meta = {"source_no": no, "source_label": name}
    if args.book:
        meta["book"] = args.book
    if args.year:
        meta["year"] = args.year
    if args.region:
        meta["region"] = args.region
    head = "%% @q " + json.dumps({"points": item["points"], "meta": meta},
                                 ensure_ascii=False)
    return head + "\n" + render(item)


# ── 4. 逐题内容订正 ────────────────────────────────────────────────────
#
# 与 `amti/fixups.py` 同一套规矩：**凭据必填、先核对现状再改、命不中就报警不硬改**。
# field 取 stem / options / solution / answer；find 是**逐字子串**。
FIXES: list[dict] = [
    # ── 南通卷第 11 题（锐角三角形多选）：答案 ABD 与解析判「C 正确」互相打脸 ──
    {
        "paper": "南通", "no": 11, "field": "options",
        "find": r"\(\left(2,\dfrac{4\sqrt{3}}{3}\right)\)",
        "repl": r"\(\left[2,\dfrac{4\sqrt{3}}{3}\right]\)",
        "why": "把选项 C 恢复成**原卷印的闭区间**。锐角条件给出 $A\\in(\\pi/3,\\pi/2)$，"
               "$b=2/\\sin A$ 的真范围是**开区间** $(2,4\\sqrt3/3)$，所以原卷印闭区间时 C 是假命题、"
               "答案 ABD 才自洽。解析原话「（原卷OCR识别为闭区间，实际应为开区间）」就是这次「改正」的自供。"
               "扫描端本不该改题面（见规范 §7 铁律 2）。",
    },
    {
        "paper": "南通", "no": 11, "field": "solution",
        "find": "所以 \\(b\\in(2,\\frac{4\\sqrt{3}}{3})\\)，C正确（原卷OCR识别为闭区间，实际应为开区间）。",
        "repl": "所以 \\(b\\in(2,\\frac{4\\sqrt{3}}{3})\\)，而选项 C 写的是闭区间 "
                "\\(\\left[2,\\frac{4\\sqrt{3}}{3}\\right]\\)，两端都取不到，故 C 错误。",
        "why": "判定要跟答案 ABD 对齐；同时删掉那句转录自述（元话不许进正文）。",
    },
    {
        "paper": "南通", "no": 11, "field": "solution",
        "find": "\\(b+c=4\\sin A+4\\sin C = 4\\sin A+4\\sin(\\frac{5\\pi}{6}-A) = "
                "4\\sqrt{3}\\sin(A+\\frac{\\pi}{6})\\)，因为 \\(A+\\frac{\\pi}{6}\\in(\\frac{\\pi}{2},\\frac{2\\pi}{3})\\)，"
                "所以 \\(\\sin(A+\\frac{\\pi}{6})\\in(\\frac{\\sqrt{3}}{2},1)\\)，故 \\(b+c\\in(2+2\\sqrt{3},4\\sqrt{3})\\)，D正确。",
        "repl": "由正弦定理 \\(2R=\\frac{a}{\\sin A}=\\frac{4}{\\sin A}\\)，故 "
                "\\(b+c=2R(\\sin B+\\sin C)=\\frac{4}{\\sin A}\\left(\\frac{1}{2}+\\sin(\\frac{5\\pi}{6}-A)\\right)\\)\n"
                "\\(=\\frac{4}{\\sin A}\\left(\\frac{1}{2}+\\frac{1}{2}\\cos A+\\frac{\\sqrt{3}}{2}\\sin A\\right)"
                "=2\\sqrt{3}+\\frac{2(1+\\cos A)}{\\sin A}=2\\sqrt{3}+2\\cot\\frac{A}{2}\\)。"
                "因为 \\(A\\in(\\frac{\\pi}{3},\\frac{\\pi}{2})\\)，所以 \\(\\frac{A}{2}\\in(\\frac{\\pi}{6},\\frac{\\pi}{4})\\)，"
                "\\(\\cot\\frac{A}{2}\\in(1,\\sqrt{3})\\)，故 \\(b+c\\in(2+2\\sqrt{3},4\\sqrt{3})\\)，D正确。",
        "why": "原句把 $b+c$ 写成 $4\\sin A+4\\sin C$：正弦定理里 $b=2R\\sin B$、$c=2R\\sin C$，"
               "既不该出现 $\\sin A$，$2R$ 也不等于 $4$（$2R=4/\\sin A$），且它自己写的 "
               "$4\\sqrt3\\sin(A+\\pi/6)$ 与前一步根本不等价。区间端点独立复算（$A\\to\\pi/2$ 得 $2+2\\sqrt3$、"
               "$A\\to\\pi/3$ 得 $4\\sqrt3$）与选项 D 一致 ⇒ **结论对、过程错**，换成能站住的推导，结论不动。",
    },
    # ── 南通卷第 10 题：D 项的论证用了错的切线 ──
    {
        "paper": "南通", "no": 10, "field": "solution",
        "find": "\\(f(x)\\) 在 \\(x=1\\) 处的切线为 \\(y=x\\)，由于 \\(f(x)\\) 的图象在切线下方，"
                "当 \\(x>1\\) 时，\\(f(x)<x\\)；当 \\(0<x<1\\) 时，\\(f(x)<x\\)。\\(f(x_1)=f(x_2)<x_2\\)，"
                "而 \\(f(x_1)<x_1\\) 无法直接推出 D。事实上，由 \\(f(x_1)=f(x_2)\\) 得 \\(x_1 x_2>1\\)（可证），"
                "则 \\(\\frac{1}{x_1}+\\frac{1}{x_2}\\) 不一定小于 2，D错误。",
        "repl": "D 项：取 \\(t=\\dfrac{1}{2}\\)（在 A 所给的范围 \\((0,1)\\) 内），由 \\(f(x)=\\dfrac{1}{2}\\) 得 "
                "\\(2\\ln x=x-2\\)。令 \\(\\varphi(x)=x-2-2\\ln x\\)："
                "\\(\\varphi(0.45)>0\\)、\\(\\varphi(0.47)<0\\) 得小根 \\(x_1\\in(0.45,0.47)\\)；"
                "\\(\\varphi(5.3)<0\\)、\\(\\varphi(5.4)>0\\) 得大根 \\(x_2\\in(5.3,5.4)\\)。"
                "于是 \\(\\dfrac{1}{x_1}+\\dfrac{1}{x_2}>\\dfrac{1}{0.47}+\\dfrac{1}{5.4}>2.3>2\\)，"
                "与 D 所说的「小于 2」相反，故 D 错误。",
        "why": "两处硬伤：\\(f'(x)=-\\dfrac{\\ln x}{x^2}\\) 在 \\(x=1\\) 处为 \\(0\\)、\\(f(1)=1\\)，"
               "切线是 \\(y=1\\) 不是 \\(y=x\\)；而「得 \\(x_1x_2>1\\)（可证）」推不出 D 的真假。"
               "D 判「错误」本身对，换成可复核的反例："
               "$\\varphi(0.45)=0.047>0$、$\\varphi(0.47)=-0.020<0$、$\\varphi(5.3)=-0.035<0$、"
               "$\\varphi(5.4)=0.027>0$ 逐个代过；$1/0.47+1/5.4=2.31>2$。",
    },
    # ── 百校卷第 8 题：解的编号与条件写串，最终区间却对 ──
    {
        "paper": "百校", "no": 8, "field": "solution",
        "find": "若 \\(k<\\dfrac{\\ln x}{x(x+1)}\\) 有且只有3个整数解，结合单调性，这3个解只能是 \\(1, 2, 3\\)。",
        "repl": "又 \\(g(1)=0\\)，而此处 \\(k>0\\)，\\(x=1\\) 不满足 \\(k<g(x)\\)，"
                "故结合单调性，这 3 个整数解只能是 \\(2, 3, 4\\)。",
        "why": "$x=1$ 时 $g(1)=\\ln 1/(1\\cdot 2)=0$，$k>0$ 不可能小于 $0$ ⇒ $x=1$ 不是解。"
               "把它算进解里与它自己给出的最终区间 $[g(5),g(4))$（解为 2、3、4）矛盾。",
    },
    {
        "paper": "百校", "no": 8, "field": "solution",
        "find": "则需满足 \\(g(3)>k \\geqslant g(4)\\)（注意 \\(g(3) \\approx 0.091 > g(4) \\approx 0.069\\)）。",
        "repl": "则需满足 \\(g(4)>k \\geqslant g(5)\\)（\\(g(4)=\\dfrac{\\ln 2}{10}\\approx 0.069\\)、"
                "\\(g(5)=\\dfrac{\\ln 5}{30}\\approx 0.054\\)：\\(k=g(5)\\) 时 \\(x=5\\) 不满足严格不等式，"
                "解集仍是 \\(\\{2,3,4\\}\\)，故左端闭；\\(k=g(4)\\) 时 \\(x=4\\) 出局只剩 \\(\\{2,3\\}\\)，故右端开）。",
        "why": "解为 $2,3,4$ 的条件是 $k$ **低于** $g(4)$ 且**不低于** $g(5)$；原句写 $g(3)>k\\geqslant g(4)$，"
               "与它自己下一步给出的 $\\left[\\dfrac{\\ln 5}{30},\\dfrac{\\ln 2}{10}\\right)$ 打脸。"
               "最终区间与选项 D 都对，逐点验过开闭。",
    },
    # ── 南京一中高二卷：两处 `【缺：…】` 原卷其实有，按原卷抄回 ──
    {
        "paper": "南京一中", "no": 17, "field": "solution",
        "find": "=\\dfrac{\\sin(120^\\circ-C)-2\\sin C}{\\sqrt{3}\\left(\\dfrac{1}{2}\\cos C-"
                "\\dfrac{\\sqrt{3}}{2}\\sin C\\right)}.\n\\]\n【缺：原答案此处最后分式 OCR 不清，原文结论为 $2$。】",
        "repl": "=\\dfrac{\\sin(120^\\circ-C)-2\\sin C}"
                "{\\dfrac{\\sqrt{3}}{2}\\left(\\dfrac{1}{2}\\cos C-\\dfrac{\\sqrt{3}}{2}\\sin C\\right)}\n"
                "=\\dfrac{\\dfrac{\\sqrt{3}}{2}\\cos C-\\dfrac{3}{2}\\sin C}"
                "{\\dfrac{1}{2}\\left(\\dfrac{\\sqrt{3}}{2}\\cos C-\\dfrac{3}{2}\\sin C\\right)}=2 .\n\\]",
        "why": "凭据：答案册 PDF 第 3 页【小问2 详解】末两行（文字层把分式打散了，"
               "按 240dpi 渲染成图逐字看过）：分母是 $\\dfrac{\\sqrt{3}}{2}\\left(\\dfrac12\\cos C-"
               "\\dfrac{\\sqrt{3}}{2}\\sin C\\right)$（交付稿漏了那个 $/2$），"
               "再化成 $\\dfrac{\\frac{\\sqrt3}{2}\\cos C-\\frac32\\sin C}"
               "{$\\frac12\\left(\\frac{\\sqrt3}{2}\\cos C-\\frac32\\sin C\\right)}=2$ ……15 分。"
               "原答案的分值（12 分／15 分）不入正文。",
    },
    {
        "paper": "南京一中", "no": 17, "field": "stem",
        "find": r"已知函数 $f(x)=\bar{a}\cdot\bar{b}$，其中 $\bar{a}=(2\cos x,\sqrt{3}\sin x)$，"
                r"$\bar{b}=(\cos x,-2\cos x)$。",
        "repl": r"已知函数 $f(x)=\vec{a}\cdot\vec{b}$，其中 $\vec{a}=(2\cos x,\sqrt{3}\sin x)$，"
                r"$\vec{b}=(\cos x,-2\cos x)$。",
        "why": "凭据：试题 PDF 第 4 页 17 题题干按 400dpi 放大逐字看过，$a$、$b$ 顶上印的是**向量箭头**"
               "不是上划线；且**同一道题的解析自己写的就是** $f(x)=\\vec{a}\\cdot\\vec{b}$"
               "（答案册第 3 页【小问1 详解】首行），交付稿题干与解析记号自相矛盾。"
               "带坐标的分量 $\\vec a=(2\\cos x,\\sqrt3\\sin x)$ 也只有向量讲得通。"
               "题库统一写法见 `设计/题目规范.md` §2.6。",
    },
    {
        "paper": "南京一中", "no": 18, "field": "solution",
        "find": r"又 $NC$【缺：原答案此处符号不清】平面",
        "repl": r"又 $NC\not\subset$ 平面",
        "why": "凭据：答案册 PDF 第 4 页首行「此时 $QM\\parallel NC$，又 $NC\\not\\subset B'AM$，"
               "$QM\\subset B'AM$，故 $CN\\parallel$ 平面 $B'AM$。……4 分」"
               "（文字层把 `⊄` 丢了，渲染成图核对过）。线面平行的判定本来就要「线在面外＋线在面内」两条，"
               "缺这个符号推导就断，且与本文件其它处 `$QM\\subset$ 平面' 的写法统一。",
    },
]


def apply_fixes(items: list[dict], name: str, log: list) -> None:
    for fx in FIXES:
        if fx["paper"] not in name:
            continue
        hit = next((it for it in items if it["no"] == fx["no"]), None)
        if hit is None:
            log.append((name, fx["no"], "订正未命中", "这道题不在产物里"))
            continue
        if not fx.get("why"):
            raise ValueError("订正条目必须写凭据 why：%s 第%s题" % (name, fx["no"]))
        field = fx["field"]
        if field == "options":
            idx = [k for k, o in enumerate(hit["options"]) if fx["find"] in o]
            if not idx:
                log.append((name, fx["no"], "订正未命中", "选项里找不到 %r" % fx["find"][:44]))
                continue
            k = idx[0]
            hit["options"][k] = hit["options"][k].replace(fx["find"], fx["repl"])
            log.append((name, fx["no"], "内容订正", "选项 %s：%s" % (chr(65 + k), fx["why"])))
            continue
        cur = hit.get(field, "")
        if fx["find"] not in cur:
            log.append((name, fx["no"], "订正未命中", "%s 里找不到 %r" % (field, fx["find"][:44])))
            continue
        hit[field] = cur.replace(fx["find"], fx["repl"], 1)
        log.append((name, fx["no"], "内容订正", "%s：%s" % (field, fx["why"])))


# ── 5. 打考点 ─────────────────────────────────────────────────────────

def tag_points(items: list[dict]) -> None:
    from amti import record as RC
    for it in items:
        q = {"stem": it["stem"], "type": it["type"],
             "options": [(chr(65 + k), o) for k, o in enumerate(it["options"])]}
        pid = RC.tag_point(q)
        if pid:
            it["points"] = [pid]


# ── 6. 主流程 ─────────────────────────────────────────────────────────

def parse_drop(specs: list[str]) -> dict[str, set[int]]:
    out: dict[str, set[int]] = {}
    for d in specs:
        key, nums = d.split(":")
        out.setdefault(key, set()).update(int(x) for x in nums.split(",") if x.strip())
    return out


def dropped(drops: dict, name: str) -> set[int]:
    for k, v in drops.items():
        if k in name:
            return v
    return set()


def build(name: str, text: str, args, log: list) -> tuple[str, list[dict]]:
    items: list[dict] = []
    cursor = 0
    marks = [(m.start(), m.group(1)) for m in SECTION_RE.finditer(text)]
    sec_now = ""
    for i, blk in enumerate(ig.split_source(text), 1):
        p = text.find(blk[:40], cursor)
        if p >= 0:
            cursor = p
            for st, r in marks:
                if p >= st:
                    sec_now = r
        it, warn = convert_block(blk)
        if it is None:
            log.append((name, i, "未落源材料", warn))
            continue
        it["no"] = i
        it["section"] = sec_now
        it["warn"] = warn
        want = SEC_TYPE.get(sec_now, "")
        if want and want != it["type"]:
            warn.append("节标题「%s」说这是 %s，实测判成 %s" % (sec_now, want, it["type"]))
        items.append(it)
    apply_fixes(items, name, log)
    for it in items:                      # 订正之后重算内容级告警，改好了就不该再报
        it["warn"] = it["warn"] + content_warnings(it)
    keep = [it for it in items if it["no"] not in dropped(args.drop, name)]
    for it in items:
        if it["no"] not in dropped(args.drop, name):
            continue
        log.append((name, it["no"], "未入库（--drop）", ["按裁决排除"]))
    if args.tag:
        print("   打考点：%d 道…" % len(keep))
        tag_points(keep)
    blocks = [render_meta(it, it["no"], name, args) for it in keep]
    return "\n\n".join(blocks) + "\n", items


def report(path: Path, name: str, detected: str, src: Path, args, items: list[dict]) -> None:
    L = ["# 转换报告 · %s\n" % name,
         "源文件：`%s`" % src,
         "文件里检测到的卷名：%s" % detected,
         "录入参数：`--book %s --label %s --year %s --region %s`\n"
         % (args.book, name, args.year, args.region or "（空）"),
         "## 逐题\n",
         "| 原卷题号 | 节 | 题型 | 答案 | 选项 | 空位 | 考点 | 告警 |",
         "|---|---|---|---|---|---|---|---|"]
    for it in items:
        L.append("| %d | %s | %s | %s | %d | %d | %s | %s |" % (
            it["no"], it["section"] or "—", it["type"],
            (it["answer"] or "见解析").replace("|", "\\|"),
            len(it["options"]), it["n_blank"],
            "、".join(it["points"]) or "未打",
            "；".join(it["warn"]).replace("\n", " ") or "—"))
    L.append("\n## 逐题内容订正（凭据）\n")
    any_fix = False
    for fx in FIXES:
        if fx["paper"] in name:
            any_fix = True
            L.append("- 第 %s 题 · %s\n  - 原文：`%s`\n  - 改为：`%s`\n  - 凭据：%s"
                     % (fx["no"], fx["field"], fx["find"], fx.get("repl", "（整项替换）"), fx["why"]))
    if not any_fix:
        L.append("（本题卷无内容订正）")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--labels", default="")
    ap.add_argument("--book", default="模拟题")
    ap.add_argument("--year", type=int, default=2027)
    ap.add_argument("--region", default="")
    ap.add_argument("--tag", action="store_true")
    ap.add_argument("--drop", action="append", default=[])
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    args.drop = parse_drop(args.drop)

    src = Path(args.src)
    body = doc_body(src.read_text(encoding="utf-8"))
    papers = split_papers(body)
    labels = [x.strip() for x in args.labels.split(",") if x.strip()]
    print("识别出 %d 卷" % len(papers))
    for n, _t in papers:
        print("   ·", n[:70])
    if labels and len(labels) != len(papers):
        print("× 卷数不匹配：--labels 给了 %d 个" % len(labels))
        return 1

    out = Path(args.out) if args.out else ROOT / "数据" / "录题" / ("标准化卷_%s" % src.stem)
    if not out.is_absolute():
        out = ROOT / out                    # `--out` 给相对路径时也要能算 relative_to
    out.mkdir(parents=True, exist_ok=True)
    log: list = []
    for k, (detected, text) in enumerate(papers):
        name = labels[k] if labels else detected.replace(" ", "")[:40]
        print("\n══ %s" % name)
        tex, items = build(name, text, args, log)
        p = out / ("%s.tex" % name)
        p.write_text(tex, encoding="utf-8")
        report(out / ("转换报告_%s.md" % name), name, detected, src, args, items)
        print("   源材料：%s（%d 块）" % (p.relative_to(ROOT), tex.count("%% @q ")))
        for it in items:
            print("   %2d. [%-14s] 答:%-9s 选项%d 空%d%s" % (
                it["no"], it["type"], (it["answer"] or "—")[:9], len(it["options"]),
                it["n_blank"], ("　⚠ " + "; ".join(it["warn"])) if it["warn"] else ""))

    print("\n══ 订正与排除")
    for e in log:
        print("  %-24s 第%s题  %-10s %s" % (e[0][:12], e[1], e[2], str(e[3])[:180]))
    print("\n下一步先干跑：")
    print("  python3 amti.py ingest --file '%s/<卷名>.tex' --book %s --year %s%s"
          % (out.relative_to(ROOT), args.book, args.year,
             " --region " + args.region if args.region else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
