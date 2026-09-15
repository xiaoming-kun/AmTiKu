r"""AmTiKu · 待解题目的**导出 / 回收**

用户的做法：把没做的题导成一个文档 → 贴到别的模型（WorkBuddy）里做 →
拿回来的文档**直接导回题库**。所以这里只有两头，不碰任何模型端点。

    python3 amti.py 导出待解 --limit 100        # 出题
    python3 amti.py 收回解答 解答.md            # 收题（默认干跑）

## 为什么做成明文文档而不是 JSON

贴进对话里、再贴回来——JSON 会被模型顺手"美化"（加注释、改缩进、
把 `\n` 转义掉），而 LaTeX 里的反斜杠本来就和 JSON 转义打架。
明文没有这个问题：**所见即所得，抄回来就行**。

## 格式为什么长这样

一条题一个块，块头是 `题号：`（**回卷时靠它对上号**，不靠顺序——
模型可能漏做、跳做、重排，靠序号对会全错位）。

    ════════════════════════════════════
    题号：2024全国优质模拟题精选/…/三月班（一）#20
    题型：填空题
    题干：已知函数 …，则最小值为\fillin{}.
    选项：（无）
    ────────────────────────────────────
    【答案】
    18
    【解析】
    由 … 得 …，故最小值为 18.

回收时只认两样东西：`题号：` 那一行，和 `【答案】`／`【解析】` 两个标记。
中间写成什么样都行——多空行、加序号、换标点，都不影响解析。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import normalize as norm, store


# 导出时写在文档最前面的**格式要求**。这段是给模型看的，
# 所以要像跟人说话一样写清楚，而不是写成一串 schema。
HEADER = r"""# 待解题目（@@N@@ 道）

请逐题给出**答案**和**完整解析**，直接在本文件上填写，**不要改动其它内容**。

## 怎么填

每一道题下面都有两个标记，各自单独占一行：先是 `【答案】`，后是 `【解析】`。
把内容写在**标记的下一行**。一道题填完长这样：

    〔题号行〕          ← 原样保留，**别改**
    题型：填空题
    题干：……
    ────────────────────────────────
    【答案】            ← 这行保留
    \frac{1}{2}         ← 你的答案写这儿
    【解析】            ← 这行保留
    由题意……             ← 你的解析写这儿

**题号那一行（形如 `题号：xxx/yyy#12`）一定要原样保留**——回收时靠它对上号。
上面的示例里写成「〔题号行〕」是为了不跟真题目混淆，**你填的时候不要把真题号改掉**。
你漏做几道、跳着做、换个顺序都没关系，但题号不能改。

## 写作要求

1. **答案**
   - 单选题：只写一个字母，如 `B`
   - 多选题：写 2–4 个字母，如 `ABD`（不加逗号）
   - 填空题：只写最终结果；数学式子用 `$…$` 括起来，如 `$x=1$`
   - 解答题：**答案栏一律写「见解析」**（答案就在解析里）

   ⚠️ **单选题、多选题、填空题的答案栏必须填**。
   只写解析不填答案的，回收时会**被退回**——那等于这道题还是没做。

2. **解析**
   - 讲清楚怎么想、每步为什么，但别啰嗦
   - **行内公式一律用 `$…$`，不要用 `\( … \)`**（规范这么定的，全库已统一；
     `\( \)` 虽然 LaTeX 也认，但回收时会被判不规范）
   - 行间公式用 `\[ … \]`
   - **LaTeX 里不要写中文**：中文放在公式外面，或用 `\text{中文}` 包起来
   - 不要用 `\begin{enumerate}`，小问直接写「(1)」「(2)」
   - 解析里可以写「故选 B」「答案为 …」，但**答案栏别漏填**

3. 如果这道题**题面本身有问题**（条件矛盾、选项都不对），
   就在答案栏写 `题面有误`，并在解析里说清哪里有问题——**不要硬凑一个答案**。

---
"""


def _fmt_question(q, i: int, *, stage: str = "both") -> str:
    r"""一道题 → 文档里的一个块。

    `stage="solution"` 时**把已有答案亮出来**，并说明"答案不用填，只写解析"——
    不然模型看到空答案栏，要么重新算一遍（浪费），要么按规矩填（可能和已有答案打架）。
    """
    lines = ["", "═" * 60, "题号：%s" % q.key, "题型：%s" % _type_label(q.type)]
    lines.append("题干：%s" % (q.stem or "").strip())
    if q.options:
        for o in q.options:
            lines.append("　%s. %s" % (o.label, (o.text or "").strip()))
    else:
        lines.append("选项：（无）")
    lines.append("─" * 60)
    if stage == "solution" and q.answer.strip():
        # ⚠️ 提示语必须写在**两个标记外面**。
        # 早先写在 `【答案】` 和 `【解析】` 之间，回收时它被当成了答案的一部分——
        # 「答案解析出 2 段」，整批被「填空位数」退回。实测踩过。
        lines += ["（这题**已有答案，不用改也不用重填**；只把解析写在下面）",
                  "【答案】", q.answer.strip(), "【解析】", "", ""]
    else:
        lines += ["【答案】", "", "【解析】", "", ""]
    return "\n".join(lines)


def _type_label(t: str) -> str:
    return {"single_choice": "单选题", "multi_choice": "多选题",
            "fill_in_blank": "填空题", "detailed_answer": "解答题"}.get(t, t or "未知")


def pending(*, kind: str = "", difficulty: str = "", book: str = "",
            limit: int = 0, offset: int = 0, stage: str = "both") -> list:
    r"""要导出的题。

    `stage` 两档：

    | stage | 取哪些 | 用途 |
    |---|---|---|
    | `both`（默认） | **答案和解析都没有** | 整道题从头做 |
    | `solution` | **有答案、但没解析** | 只补解析 |

    第二种是后加的。起因：`2022/上海卷（秋）#1–#11` 的解析被挂成了别的题的，
    清掉之后它们成了「有答案、没解析」——这种状态原来**进不了待解队列**，
    等于永远补不上。全库这类有 460 道。
    """
    out = []
    for _f, q in store.iter_questions():
        if stage == "solution":
            # 只补解析：必须有答案、且确实没解析
            if not q.answer.strip() or q.solution.strip():
                continue
        else:
            if q.solution.strip() or q.answer.strip():
                continue
        if kind and q.kind != kind:
            continue
        if difficulty and q.difficulty != difficulty:
            continue
        if book and (q.meta or {}).get("book") != book:
            continue
        out.append(q)
    # 易→难，和界面的默认排序一致
    from .solve import DIFF_ORDER
    out.sort(key=lambda q: (DIFF_ORDER.get(q.difficulty, 9), q.key))
    if offset:
        out = out[offset:]
    return out[:limit] if limit else out


def export(path: str | Path, *, limit: int = 100, offset: int = 0, kind: str = "",
           difficulty: str = "", book: str = "", stage: str = "both") -> dict:
    r"""把待解题目导成一份可粘贴的文档。`stage` 见 `pending`。"""
    qs = pending(kind=kind, difficulty=difficulty, book=book, offset=offset,
                 limit=limit, stage=stage)
    if not qs:
        return {"ok": False, "error": "没有符合条件的待解题目", "count": 0}
    p = Path(path)
    body = [HEADER.replace("@@N@@", str(len(qs)))]
    for i, q in enumerate(qs, 1):
        body.append(_fmt_question(q, i))
    p.write_text("\n".join(body), encoding="utf-8")
    from collections import Counter
    c = Counter(q.difficulty or "未定" for q in qs)
    return {"ok": True, "path": str(p.resolve()), "count": len(qs),
            "by_difficulty": {k: c[k] for k in ("简单题", "中档题", "难题", "未定") if c[k]}}


def export_split(outdir: str | Path, *, per: int = 100, kind: str = "",
                 difficulty: str = "", book: str = "", stage: str = "both") -> dict:
    r"""把符合条件**全部**导出来，按 `per` 道切成一批。

    为什么要分批：一份塞 4000 道，模型做不完也贴不动；一批 100 道左右
    是"一次对话能做完"的量。文件名带**难度和序号**，回收时一眼知道是哪批。

    另外写一份 `清单.md`——**哪批做了、哪批没做，得有个地方看**。
    """
    qs = pending(kind=kind, difficulty=difficulty, book=book, stage=stage)
    if not qs:
        return {"ok": False, "error": "没有符合条件的待解题目", "files": []}
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    label = (difficulty or kind or "全部") + ("_补解析" if stage == "solution" else "")
    files = []
    for i in range(0, len(qs), per):
        chunk = qs[i:i + per]
        n = i // per + 1
        f = d / ("第%02d批_%s_%d道.md" % (n, label, len(chunk)))
        body = [HEADER.replace("@@N@@", str(len(chunk)))]
        for j, q in enumerate(chunk, 1):
            body.append(_fmt_question(q, j, stage=stage))
        f.write_text("\n".join(body), encoding="utf-8")
        from collections import Counter
        c = Counter(x.difficulty or "未定" for x in chunk)
        files.append({"path": str(f.resolve()), "name": f.name, "count": len(chunk),
                      "difficulty": difficulty,
                      "by_difficulty": {k: c[k] for k in
                                        ("简单题", "中档题", "难题", "未定") if c[k]},
                      "first": chunk[0].key, "last": chunk[-1].key})

    lines = ["# 待解清单", "",
             "共 %d 道，切成 %d 批（每批 %d 道）。" % (len(qs), len(files), per), "",
             "做法：把某一批的内容贴给模型 → 拿回来跑",
             "`python3 amti.py collect 待解/<那一批>.md --yes`", "",
             "| 批次 | 道数 | 难度 | 首题 | 末题 |", "|---|---|---|---|---|"]
    for f in files:
        lines.append("| `%s` | %d | %s | `%s` | `%s` |"
                     % (f["name"], f["count"],
                        "、".join("%s %d" % (k, v) for k, v in f["by_difficulty"].items()),
                        f["first"].split("/")[-1], f["last"].split("/")[-1]))
    (d / "清单.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "total": len(qs), "files": files,
            "index": str((d / "清单.md").resolve())}


# ── 回收 ──────────────────────────────────────────────────────────────

# 只认这两样：`题号：xxx` 和 `【答案】`／`【解析】`。
# 别的写成什么样都不管——模型很容易在格式上跑偏，判据要少而硬。
_KEY_LINE = re.compile(r"^\s*题号[：:]\s*(.+?)\s*$", re.M)
_MARK = re.compile(r"^\s*【\s*(答案|解析)\s*】\s*$", re.M)
# 块与块之间的分隔线。段落是按 `题号：` 切的，所以**下一题的框线会落在
# 上一题解析的尾巴上**——不剥掉的话，每题解析最后都挂着一串 `════`。
_BORDER = re.compile(r"^\s*[─═\-=]{4,}\s*$")


def _trim(s: str) -> str:
    """剥掉首尾的空行和分隔线。"""
    lines = (s or "").split("\n")
    while lines and (not lines[-1].strip() or _BORDER.match(lines[-1])):
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines).strip()


def parse_back(text: str) -> tuple[dict[str, dict], list[str]]:
    r"""把回收的文档拆成 `{题号: {答案, 解析}}`。返回 (结果, 问题说明)。

    **按题号对齐，不按顺序**：模型可能漏做、跳做、重排。
    """
    out: dict[str, dict] = {}
    notes: list[str] = []
    keys = list(_KEY_LINE.finditer(text))
    if not keys:
        return {}, ["没找到任何 `题号：` 行——文档格式不对？"]

    for i, km in enumerate(keys):
        key = km.group(1).strip().strip("`")
        # 这一题的正文：从题号行到下一个题号行
        end = keys[i + 1].start() if i + 1 < len(keys) else len(text)
        seg = text[km.end():end]

        marks = list(_MARK.finditer(seg))
        if not marks:
            notes.append("%s：没找到【答案】/【解析】标记" % key)
            continue
        got: dict[str, str] = {}
        for j, mm in enumerate(marks):
            stop = marks[j + 1].start() if j + 1 < len(marks) else len(seg)
            got[mm.group(1)] = _trim(seg[mm.end():stop])
        ans = got.get("答案", "").strip()
        sol = got.get("解析", "").strip()
        # 模型常把「（这里写答案）」这类提示语留下，去掉
        ans = re.sub(r"^[（(]\s*这里写.*?[）)]\s*$", "", ans).strip()
        sol = re.sub(r"^[（(]\s*这里写.*?[）)]\s*$", "", sol).strip()
        if not ans and not sol:
            notes.append("%s：答案和解析都是空的（跳过）" % key)
            continue
        out[key] = {"answer": ans, "solution": sol}
    return out, notes


def collect(path: str | Path, *, dry_run: bool = True,
            skip_bad: bool = True) -> dict:
    r"""把回收的解答写进题库。

    写之前**每题都过一遍规范**（和录入、求解同一条路）：
    规范化 → 规范审查 → 通过了才写。写不进去的列出来，不硬塞。

    `skip_bad=True`：个别题不合规就跳过它，其余照写（批量场景下更实用）；
    `False`：有一道不合规整批不写。
    """
    text = Path(path).read_text(encoding="utf-8")
    parsed, notes = parse_back(text)
    if not parsed:
        return {"ok": False, "error": "没解析出任何解答", "notes": notes}

    qs = store.load_all()
    by_key = {q.key: q for q in qs}
    done: list[dict] = []
    bad: list[dict] = []
    missing: list[str] = []

    from .web import server as _srv          # 复用答案格式校验，绝不两处各写一遍
    for key, d in parsed.items():
        q = by_key.get(key)
        if q is None:
            missing.append(key)
            continue
        from copy import deepcopy
        t = deepcopy(q)
        ans = (d["answer"] or "").strip()
        sol = (d["solution"] or "").strip()

        # ── 两条硬规矩（用户明确要求，写死在这里，不靠提醒） ──
        #
        # ① **客观题必须有答案。** 「解析进去了、答案没有了」是踩过的坑：
        #    模型辛辛苦苦写了半页解析，答案栏空着——那这道题**还是没做**，
        #    卷面上作答括号里空空如也。所以宁可不写，也不能写成半成品。
        # ② **解答题的答案就是「见解析」。** 解答题的结论本来就在解析里，
        #    单独填一个答案既重复又没意义；统一写「见解析」，一眼知道去哪儿看。
        if t.type == "detailed_answer":
            if not sol:
                bad.append({"key": key, "why": "解答题没写解析"})
                if not skip_bad:
                    return {"ok": False, "error": "有题不合规，整批未写", "bad": bad}
                continue
            ans = "见解析"
        elif not ans and not t.answer.strip():
            # 空答案栏**只有在题目本来就有答案时才放过**（"只补解析"那一档）。
            # 否则照旧退回——客观题没答案等于还没做。
            bad.append({"key": key, "why": (
                "**有解析但没有答案**——客观题的答案栏必须填，"
                "否则卷面上作答括号是空的，这道题等于还没做")})
            if not skip_bad:
                return {"ok": False, "error": "有题不合规，整批未写", "bad": bad}
            continue

        try:
            t.answer = _srv._clean_answer_input(t, ans)
            if sol:
                t.solution = sol
        except Exception as e:
            bad.append({"key": key, "why": str(getattr(e, "detail", e))})
            if not skip_bad:
                return {"ok": False, "error": "有题不合规，整批未写", "bad": bad}
            continue
        fixed = norm.normalize(t, norm.ENTRY)
        from . import conform
        viol = conform.run([t])
        if viol:
            bad.append({"key": key,
                        "why": "%s（%s）" % (viol[0]["why"], viol[0]["check"])})
            if not skip_bad:
                return {"ok": False, "error": "有题不合规，整批未写", "bad": bad}
            continue
        done.append({"key": key, "obj": t, "fixed": fixed})

    if dry_run:
        return {"ok": True, "dry_run": True, "would_write": len(done),
                "bad": bad, "missing": missing, "notes": notes,
                "sample": [{"key": x["key"], "answer": x["obj"].answer,
                            "solution": x["obj"].solution[:80]} for x in done[:5]]}

    for x in done:
        q = by_key[x["key"]]
        q.answer, q.solution = x["obj"].answer, x["obj"].solution
        q.stem = x["obj"].stem                    # 规范化可能补了作答位置
        q.meta["solution_source"] = "workbuddy"
        if x["obj"].answer:
            q.meta["answer_source"] = "workbuddy"
        import time as _t
        q.meta["edited_at"] = _t.strftime("%Y-%m-%d %H:%M")
    store.rewrite_all(qs)

    return {"ok": True, "dry_run": False, "written": len(done),
            "bad": bad, "missing": missing, "notes": notes}
