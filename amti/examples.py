#!/usr/bin/env python3
r"""讲义 PDF → **例题**（题干 + 解析，有就抽、没有就空着）。

## 为什么不走 `record2`（录题）那条路

那条路的每条假设都是"试卷"的：

* 题号 1–19 决定题型（`BY_NO`）；讲义是「例2-1」「变式3」；
* 解析在另一个文件 / 另一个区，靠题号配对；讲义的解析**紧跟在题干后面**；
* 选择题必须有 3–4 个选项、客观题必须有答案；纲举目张的讲义里，"例题"
  很多只有题干和讲解。

硬塞进去的结果是：题号全落在 1–19 之外，一道都不剩。

## 这里只做一件事

**把「例 X」这一块整块抠出来**，题目归属用出现顺序（1..N），不是讲义上的
编号。其余全部复用：OCR（`record2.scan_pdf`）、闸门（`record2.gate`）、
规范化（`rec_to_question`）、质检（`quality`）。

## 分块

讲义动辄几百页，一次塞不进上下文。例题是**局部**结构（不需要"整本"才能
认出来），所以可以按行窗口切、带重叠、按起始行去重——这跟试卷不一样
（试卷按题号配对，切开就会串，见 `bundle.py`）。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import record2 as R2
from . import quality as QLT
from . import store
from .schema import Question

SYS_EX = """你在从一份**高中数学讲义**里抽「例题」。输入是整页 OCR 文本，每行前面有行号。

输出 JSON：
{"items":[
 {"n":1,"type":"single_choice|multi_choice|fill_in_blank|detailed_answer",
  "stem_start":12,"stem_end":20,"sol_start":21,"sol_end":28,"quote":"逐字 10-25 字"}
]}

规矩：
* 只抽带「例」「例题」「变式」标号的小题。「方法技巧」「易错分析」「题型X」
  「真题训练」「课后练习」这些标题和它们的题目**不要**。
* 题干从「例X」那一行开始，到解析开始前一行结束；选项 A．B．C．D．算题干。
* 讲义里有「解」「解析」「【答案】」「【详解】」的，把这段的起止行也标出来；
  **没有就 sol_start / sol_end 给 null**，不要拿下一题的内容凑。
* n 按**出现顺序**从 1 编。讲义的「例2-1」不是题号，别照抄。
* quote：从题干里逐字摘 10-25 字，改一个字就算错。
* 有一行并排的四个选项 → single_choice；多个正确选项（多选）→ multi_choice；
  题干有空位 → fill_in_blank；其余 → detailed_answer。
"""

#: 「【答案】B」「【答案】−3」这类标签
ANS_TAG = re.compile(r"【答\s*案】\s*([^\n【]{1,40})")
#: 题干开头的「例 1.3」「变式1-2」「【例】」——是标号，不是题干
EX_HEAD = re.compile(r"^\s*(?:【\s*例\s*】|例题?|变式(?:训练)?)\s*[\d.．\-]*\s*")
#: 解析开头的「解析：」「解：」——是标签，不是内容
SOL_HEAD = re.compile(r"^\s*[^\w\u4e00-\u9fa5]{0,3}\s*(?:解析|详解|解)\s*[：:]\s*")


def _win_text(lines: list[tuple[int, str, int]]) -> str:
    out, prev = [], None
    for n, t, p in lines:
        if p != prev:
            out.append("=== 第%d页 ===" % p)
            prev = p
        out.append("%3d| %s" % (n, t))
    return "\n".join(out)


def structure_ex(rows: list[dict], *, size: int = 240, overlap: int = 20,
                 on_event=None) -> tuple[list[dict], list[tuple]]:
    r"""讲义逐页文本 → 例题块（**带全局行号**）；分块跑，按起始行去重。

    返回 `(items, lines)`。`items` 按 `stem_start` 升序，同一块在重叠区被
    两次抽到时只留第一次。
    """
    from . import lms as L
    _doc, lines = R2.build_doc(rows)
    if not lines:
        return [], []
    chunks, i = [], 0
    while i < len(lines):
        chunks.append(lines[i:i + size])
        if i + size >= len(lines):
            break
        i += max(1, size - overlap)
    got: dict[int, dict] = {}
    for k, ch in enumerate(chunks, 1):
        if on_event:
            on_event({"type": "stage",
                      "text": "抽例题（%d/%d 段，第 %d–%d 行）"
                              % (k, len(chunks), ch[0][0], ch[-1][0])})
        doc = _win_text(ch)
        need = R2.est_tokens(doc) + R2.est_tokens(SYS_EX) + 8000
        ok, ident, why = L.ensure_ctx(R2.R.MODEL, need_tokens=need)
        if not ok:
            raise RuntimeError(why)
        d = R2._post(R2.R.API, ident,
                     [{"role": "system", "content": SYS_EX},
                      {"role": "user", "content": doc}],
                     maxtok=8000, extra={"reasoning_effort": "none"})
        raw = d["choices"][0]["message"].get("content") or ""
        for it in (R2.grab_json(raw) or {}).get("items") or []:
            s = it.get("stem_start")
            if not isinstance(s, int) or not (ch[0][0] <= s <= ch[-1][0]):
                continue
            got.setdefault(s, it)
    items = [got[k] for k in sorted(got)]
    for i, it in enumerate(items, 1):
        it["n"] = i
    return items, lines


def _raw_answer(sol: str) -> str:
    r"""解析里抠答案原文：`【答案】B` 优先，其次「故选 B」；抠不到就是空。"""
    m = ANS_TAG.search(sol or "")
    if m:
        return m.group(1).strip()
    m2 = R2.ANSWER_IN_SOL.search(sol or "")
    return m2.group(1) if m2 else ""


def _answer_for(qtype: str, raw: str) -> str:
    r"""按题型把答案规整成该有的样子（客观题只留字母，解答题写「见解析」）。"""
    if qtype in ("single_choice", "multi_choice"):
        return raw if re.fullmatch(r"[A-D]{1,4}", raw or "") else ""
    if qtype == "detailed_answer":
        return "见解析"
    return (raw or "")[:40]


def assemble_ex(items: list[dict], lines: list[tuple], label: str) -> dict:
    r"""例题块 → 成品记录（与 `record2.assemble` 同构，供审阅界面直接审）。"""
    idx = {n: t for n, t, _p in lines}
    book, reject = [], []
    for it in items:
        s, e = it.get("stem_start"), it.get("stem_end")
        if not (isinstance(s, int) and isinstance(e, int) and s <= e):
            continue
        stem_raw = "\n".join(idx[i] for i in range(s, e + 1) if i in idx)
        ss, se = it.get("sol_start"), it.get("sol_end")
        sol_raw = ""
        if isinstance(ss, int) and isinstance(se, int) and ss <= se:
            sol_raw = "\n".join(idx[i] for i in range(ss, se + 1) if i in idx)
        stem3, opts = R2.split_stem_options(stem_raw.splitlines())
        stem3 = EX_HEAD.sub("", stem3, count=1)
        sol_raw = SOL_HEAD.sub("", sol_raw, count=1)
        # **题型由文本定**：有选项→选择（答案多字母=多选），有空位→填空，
        # 否则→解答。模型给的 type 只在"有选项但没答案"时当提示。
        raw = _raw_answer(sol_raw)
        qtype, basis = R2.classify_type(stem3, opts, raw, hint=it.get("type") or "")
        answer = _answer_for(qtype, raw)
        stem, sol, opts, notes = R2.clean_fields(
            stem3, sol_raw, qtype=qtype, opts=opts, quote=it.get("quote") or "")
        if qtype in ("single_choice", "multi_choice"):
            stem, opts = R2._recover_inline_options(stem, opts)
        stem = QLT.repair_math(stem)
        sol = QLT.repair_math(sol)
        why = R2.gate(qtype, stem, opts, answer, sol)
        rec = {"题号": it["n"], "题型": qtype, "题干": stem, "选项": opts,
               "答案": answer, "解析": sol, "清洗": notes,
               "页码": R2.covered_pages(lines, (s, e)),
               "行": [s, e], "配对": "相邻" if sol_raw else "",
               "题型依据": basis,
               "速查表": "", "粗筛图": False, "粗筛表": False,
               "引用对": True}
        if why:
            rec["原因"] = why
            reject.append(rec)
        else:
            book.append(rec)
    return {"label": label, "book": book, "reject": reject,
            "pending": [], "orphans": [], "lines": lines}


def run(pdf, *, label: str = "", book_name: str = "讲义", year=None,
        force: bool = False, on_event=None) -> dict:
    r"""一份讲义 PDF → 与 `record2.run_v2` 同构的结果（审阅界面直接能审）。"""
    pdf = Path(pdf)
    label = label or pdf.stem

    def ev(text):
        if on_event:
            on_event({"type": "stage", "text": text})

    ev("识别讲义（PaddleOCR-VL）")
    rows = R2.scan_pdf(pdf, force=force)
    if on_event:
        on_event({"type": "page", "page": len(rows), "total": len(rows),
                  "cached": force is False})
    ev("抽例题（%d 页）" % len(rows))
    items, lines = structure_ex(rows, on_event=on_event)
    if not items:
        raise RuntimeError("这份讲义里没找到「例/变式」—— 是不是试卷？"
                           "试卷请走录题（试卷模式）")
    res = assemble_ex(items, lines, label)

    tex, kept = [], []
    for rec in res["book"]:
        # 书名要一路带进入库 key：只改 `q.meta["book"]` 会让 key 仍落在
        # `模拟题/` 下，界面按书筛不到、`kind` 也永远是「模拟」。
        q = R2.rec_to_question(rec, label, book_name)
        single = store.render_question(q)
        tex.append((rec["题号"], single))
        kept.append({
            "n": rec["题号"], "type": R2.EN2TYPE.get(rec["题型"], rec["题型"]),
            "figure": False, "stem": rec["题干"], "pages": rec["页码"],
            "figs": [], "yrange": [], "opt_figs": {}, "fig_fallback": False,
            "point": "", "point_title": "", "points": [],
            "quality": QLT.check(rec["题干"], rec["解析"], rec["答案"],
                                 R2.EN2TYPE.get(rec["题型"], rec["题型"]),
                                 rec["选项"] or {}),
            "ans": rec["答案"], "sol": rec["解析"],
            "options": [[k, v] for k, v in sorted((rec["选项"] or {}).items())],
            "pair": rec.get("配对") or "", "table": "",
            "type_basis": rec.get("题型依据") or "", "tex": single})
    tex.sort(key=lambda kv: kv[0])
    body = "\n\n".join(t for _n, t in tex)
    stats = {
        "卷": label, "出处": "%s%s" % (year or "", label), "标题": label,
        "页数": len(rows), "识别到": len(items), "录入": len(kept),
        "带图丢弃": 0, "带图登记位置": 0, "未录入": len(res["reject"]),
        "无解析": sum(1 for q in kept if not (q["sol"] or "").strip()),
        "已打考点": 0, "失败页": [],
        "模式": "讲义抽例题",
        "题型": {t: sum(1 for q in kept if q["type"] == t)
                 for t in ("单选", "多选", "填空", "解答")},
    }
    return {"tex": body, "kept": kept, "dropped": [], "register": [],
            "lost": res["reject"], "stats": stats, "scans": rows,
            "label": label, "year": year or 0, "title": label}


# ── 自检（不碰模型）────────────────────────────────────────────────
def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ %s" if cond else "  ✗ %s  " + str(extra)) % name)
        if not cond:
            fails += 1

    print("examples 自检")

    # 讲义的「例1」带解析、「例2」没有解析（学生版）——两种都要能出来
    body = [
        (1, "集合的表示", 1),
        (2, "例1-1 已知集合 $A=\\{1,2,3\\}$，则下列正确的是（ ）", 1),
        (3, "A. $1\\in A$ B. $4\\in A$ C. $0\\in A$ D. $5\\in A$", 1),
        (4, "【答案】A", 2),
        (5, "【详解】由元素与集合的关系可得 $1\\in A$。故选 A。", 2),
        (6, "变式1-1 已知集合 $B=\\{x\\mid x>0\\}$，则 $0$ 属于 $B$ 吗？", 2),
        (7, "方法技巧：判断元素与集合的关系。", 2),
        (8, "例2-1 已知集合 $M=\\{1,2\\}$，求 $M$ 的子集个数。", 2),
    ]
    lines = [(n, t, p) for n, t, p in body]
    items = [
        {"n": 1, "type": "single_choice", "stem_start": 2, "stem_end": 3,
         "sol_start": 4, "sol_end": 5, "quote": "已知集合"},
        {"n": 2, "type": "detailed_answer", "stem_start": 6, "stem_end": 6,
         "sol_start": None, "sol_end": None, "quote": "已知集合"},
        {"n": 3, "type": "detailed_answer", "stem_start": 8, "stem_end": 8,
         "sol_start": None, "sol_end": None, "quote": "求 $M$ 的子集个数"},
    ]
    res = assemble_ex(items, lines, "讲义自检")
    book = res["book"]
    check("三道例题都抽出来", len(book) == 3, str(len(book)))
    check("带解析的：答案从【答案】抠出来", book and book[0]["答案"] == "A",
          str(book[0]["答案"] if book else ""))
    check("带解析的：解析有内容", book and "元素与集合" in book[0]["解析"])
    check("学生版没解析的：题干在、解析空、不进 reject",
          len(book) == 3 and not book[1]["解析"], str(len(res["reject"])))
    check("选择题选项拆出来了", book and set(book[0]["选项"]) == {"A", "B", "C", "D"},
          str(book[0]["选项"] if book else ""))
    check("编号按出现顺序 1..3", [b["题号"] for b in book] == [1, 2, 3],
          str([b["题号"] for b in book]))
    check("页码从题干行号推得", book and book[0]["页码"] == [1], str(book[0]["页码"]))

    print("examples 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(__doc__)
