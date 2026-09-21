r"""AmTiKu · 录入

`设计/录入流程.md` 的代码实现。核心承诺：**存量题目一个字都不会变。**

    干跑（preview） → 你确认 → 正式导入（commit） → 变更报告

干跑**什么都不写**——图片不复制、主文件不追加。它只回答五个问题：

    ① 解析出什么    ② 图全不全    ③ 有没有重复
    ④ 字段合不合规  ⑤ 存量题受不受影响

第 ⑤ 条是结构保证的：录入走 `store.append`，它**只追加**，程序里没有任何
改写已有行的路径。所以干跑永远报「存量影响 0 道」——这不是运气，是设计。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import dedup, images as im, normalize as norm, store
from .latex_ir import BODY_ENV_RE, parse_question
from .schema import QTYPE_LABEL, Question

# 一个题块 = 题目环境 + 紧跟着的 solution 环境（如果有）
_BLOCK_RE = re.compile(
    r"\\begin\{(?:question|problem)\}(?:\[[^\]]*\])?.*?\\end\{(?:question|problem)\}"
    r"(?:\s*\\begin\{solution\}.*?\\end\{solution\})?",
    re.S)
_ENV_HEAD_RE = re.compile(r"\\begin\{(question|problem)\}(?:\[([^\]]*)\])?")
_META_RE = re.compile(r"^%% @q (\{.*\})\s*$", re.M)


def split_source(text: str) -> list[str]:
    r"""把源材料切成题目块。

    两种输入都吃，**而且可以混着来**：
      1. **主文件形态**——块前带 `%% @q {...}` 元数据行
      2. **干净环境序列**——`\begin{question}…\end{question}` 一个接一个

    ⚠️ 老写法是「只要文里出现 `%% @q`，就整体按 `%% @q` 切」——
    于是**没有元数据的题会被吞进上一块**。
    实测：粘两道题、只有第一道带元数据时，第二道直接消失。
    做主文件迁移时这没问题（每块都有元数据），但录入界面是随手粘的，
    不能假设每道题都有元数据。

    现在改成**以题目环境为单位**切，元数据行（如果有）归给它下面那块。
    """
    text = text or ""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        m = _BLOCK_BEGIN_RE.search(text, i)
        if not m:
            break
        env = m.group(1)
        end = _find_env_end(text, m.end(), env)
        if end < 0:
            break
        start = m.start()
        # 往上找紧跟的 `%% @q` 行（中间只允许空行）
        head = text.rfind("\n", 0, start)
        j = head
        while j > 0:
            k = text.rfind("\n", 0, j)
            line = text[k + 1:j].strip()
            if line.startswith("%% @q "):
                start = k + 1
                break
            if line:
                break
            j = k
        # **题目后面紧跟的 `solution` 也算这一块**。
        # 规范写法是把解析放环境**里面**（`\begin{solution}` 在 question 内），
        # 但粘进来的材料常常写在外面。不收的话解析会整段丢掉——
        # 自检里专门有一条盯这个。
        tail = end
        while True:
            m2 = re.compile(r"\s*\\begin\{solution\}").match(text, tail)
            if not m2:
                break
            e2 = _find_env_end(text, m2.end(), "solution")
            if e2 < 0:
                break
            tail = e2
        out.append(text[start:tail].strip())
        i = tail
    if out:
        return out
    # 兜底：一个环境都没认出来时，退回老办法（至少不丢主文件形态）
    return store.split_questions(text)


_BLOCK_BEGIN_RE = re.compile(r"\\begin\{(question|problem)\}")


def _find_env_end(s: str, i: int, env: str) -> int:
    r"""找 `\end{env}`，认嵌套同类环境。找不到返回 -1。"""
    beg, end = "\\begin{%s}" % env, "\\end{%s}" % env
    depth, n = 1, len(s)
    while i < n:
        if s.startswith(beg, i):
            depth += 1
            i += len(beg)
            continue
        if s.startswith(end, i):
            depth -= 1
            if depth == 0:
                return i + len(end)
            i += len(end)
            continue
        i += 1
    return -1


def _auto_key(book: str, label: str, i: int, meta: dict,
              taken: set[str] | None = None) -> str:
    r"""自然键：`书/出处#序号`。与旧库的 `书/页#题号` 同构。

    ⚠️ **必须避开库里已有的 key。** 原样返回 `书/出处#序号` 有个致命后果：
    出处留空时大家都算 `书/录入#1`，于是**整个库只能录进一道题**——
    第二道生成同一个 key，被判"已在库"直接跳过，用户看到的却是
    "重复"，根本想不到是 key 撞了。实测踩过。

    撞了就往后顺延（`#1` → `#2` → …），保证新题一定落得下。
    """
    taken = taken or set()
    n = i
    key = f"{book}/{label}#{n}"
    while key in taken:
        n += 1
        key = f"{book}/{label}#{n}"
    return key


def parse_source(text: str, *, book: str = "手工录入", label: str = "",
                 region: str = "", year: int | None = None,
                 source_no: str = "", points: list[str] | None = None,
                 difficulty: str = "") -> dict:
    r"""解析源材料。返回 `{questions, errors}`。**不写任何东西。**

    `points` / `difficulty` 是**在界面上填的**。源材料的 meta JSON 里也能写
    这两样，但界面上明明白白选了就该以界面为准（界面覆盖源材料）。
    自动打标那条路（LLM 读题干定考点）只在两者都没有时才跑。
    """
    blocks = split_source(text)
    out: list[Question] = []
    errors: list[dict] = []
    # 库里已有的 key。`_auto_key` 靠它避让，否则出处留空时
    # 每道新题都算出同一个 key，第二道起全被当成"重复"跳过。
    taken = {x.key for _f, x in store.iter_questions()}

    for i, blk in enumerate(blocks, 1):
        q = parse_question(blk)
        if q is None:
            errors.append({"seq": i, "reason": "认不出题目环境",
                           "snippet": blk[:80]})
            continue

        meta: dict = {}
        m = _META_RE.search(blk)
        if m:
            try:
                d = json.loads(m.group(1))
                meta = dict(d.get("meta") or {})
                q.points = d.get("points") or []
                if d.get("key"):
                    q.key = d["key"]
            except ValueError:
                errors.append({"seq": i, "reason": "元数据行不是合法 JSON"})
        if q.type and meta.get("type"):
            q.type = meta["type"]

        meta.setdefault("book", book)
        # **题号**：单题录入时记原卷的题号。试卷上标来源要用它，
        # 不能用 key 里的序号——那是新库自己的顺序，不是原卷题号。
        if source_no:
            meta.setdefault("source_no", source_no)
        if label:
            meta.setdefault("source_label", label)
        if region:
            meta.setdefault("region", region)
        if year:
            meta.setdefault("year", year)
        # 界面上选的难度／考点**覆盖**源材料里的（用户明确选了就该算数）
        if difficulty:
            meta["difficulty"] = difficulty
            meta["stars"] = {"简单题": 1, "中档题": 2, "难题": 3}.get(difficulty, 0)
        if points:
            q.points = list(points)
            meta["point_source"] = "manual"
        q.meta = meta
        if not q.key:
            q.key = _auto_key(book, label or "录入", i, meta, taken)
        taken.add(q.key)          # 同一批里也不许撞
        out.append(q)

    # 块内题号重复会导致 key 撞车——这必须在写之前发现
    seen: dict[str, int] = {}
    for q in out:
        seen[q.key] = seen.get(q.key, 0) + 1
    for k, n in seen.items():
        if n > 1:
            errors.append({"seq": 0, "reason": f"key 重复 {k}（出现 {n} 次）"})

    return {"questions": out, "errors": errors}


def dup_fingerprint_of(item: dict) -> str:
    """`preview` 的 items 是 dict，用同样的口径算指纹。"""
    parts = [dedup.norm_stem(item.get("stem") or "")]
    for o in (item.get("options") or []):
        parts.append(dedup.norm_stem(o.get("text") or ""))
    return "\x00".join(parts)


def apply_merge_into(qs: list[Question], merge_into: dict | None) -> list[dict]:
    r"""把新题**并到指定的库内题**上——「这其实就是同一道题，别新建了」。

    判重是算出来的，算不准（相似度 0.8 的两道题可能真是两道）。
    所以最终由人拍板：界面上点「并入这道」，就把新题的 key 改成那道题的
    key，后面走的是**升级**那条路（补解析、并考点、按需改答案），
    而不是新写一份。

    `merge_into` 形如 `{新题现在的 key: 库内那道题的 key}`。
    """
    done: list[dict] = []
    if not merge_into:
        return done
    for q in qs:
        tgt = merge_into.get(q.key)
        if not tgt or tgt == q.key:
            continue
        # 原 key 记进 meta：将来能查"这道题是从哪条录入并过来的"
        q.meta["merged_from"] = q.key
        q.key = tgt
        done.append({"from": q.meta["merged_from"], "to": tgt})
    return done


def _as_question(d: dict) -> Question:
    """干跑里的 `items` 是 dict，`merge_plan` 要 Question——转一下。

    只取合并用得着的字段，不追求完整还原。
    """
    return Question(
        key=d.get("key") or "",
        type=d.get("type") or "",
        stem=d.get("stem") or "",
        answer=d.get("answer") or "",
        solution=d.get("solution") or "",
        options=[Option(o.get("label", ""), o.get("text", ""))
                 for o in (d.get("options") or [])],
        points=list(d.get("points") or []),
        meta={"difficulty": d.get("difficulty") or ""},
    )


def merge_plan(old: Question, new: Question, *, force: bool = False) -> dict:
    r"""**升级计划**：手里这份比库里那份全的时候，该改哪些字段。

    场景：库里那道是从 PDF 扫来的，没解析、考点也没标全；你手工录一份
    带解析、标好考点的同一道题——这时候不该当"重复"丢掉，该让它**升级**。

    ## 一条铁律：只升不降

    任何一个字段，**新的比旧的空就不动**。重录一遍不会把已有的解析、
    答案、考点抹掉——这是最要命的一种事故（手工录一次，库里的解析没了）。

    逐字段规则：

    | 字段 | 规则 |
    |---|---|
    | 解析 | 旧空、新不空 → 用新的；两个都不空 → **保留旧的**（除非 `force`）|
    | 答案 | 旧空、新不空 → 用新的；两个都非空且不同 → 用新的，旧值记入 `answer_prev` |
    | 考点 | **取并集**，新的排在前面（新的主考点优先）|
    | 难度 | 旧没有、新的有 → 用新的 |

    `force=True` 时解析也以新为准（界面上的「覆盖已有解析」开关）。

    返回 `{}` 表示没有可升的——那就按重复跳过。
    """
    plan: dict = {}

    if new.solution.strip() and not old.solution.strip():
        plan["solution"] = new.solution
        plan["solution_why"] = "库里没有解析"
    elif force and new.solution.strip() and new.solution.strip() != old.solution.strip():
        plan["solution"] = new.solution
        plan["solution_why"] = "覆盖已有解析"

    na, oa = new.answer.strip(), old.answer.strip()
    if na and not oa:
        plan["answer"] = new.answer
    elif na and oa and na != oa:
        plan["answer"] = new.answer
        plan["answer_prev"] = old.answer

    # 考点取并集：新的在前（它带着新的主考点），旧的补在后面。
    # 只多不少，所以不会把标好的考点弄丢。
    merged = list(dict.fromkeys(list(new.points) + list(old.points)))
    if len(merged) > len(old.points):
        plan["points"] = merged

    if new.difficulty and not old.difficulty:
        plan["difficulty"] = new.difficulty

    return plan


def dup_fingerprint(q: Question) -> str:
    r"""判重指纹：题干 + 选项**（归一化后）。

    用户的判据：*题目完全相同、包括选项都一样，就不再入库*；
    **不分文理科**——1992 全国卷（理）#1 和（文）#1 是同一道题，
    只留一条。

    为什么不把答案、解析算进来：同一道题在不同卷子里，
    解析的写法可能不同（有的详有的略），但**题目本身是一样的**。
    判重看的是"是不是同一道题"，不是"是不是同一份解析"。

    为什么用"归一化后完全相同"而不是相似度阈值：
    见 `amti/dedup.py` 文件头——0.96 的阈值会把"求并集"和"求交集"
    判成同一道题（实测 0.980）。
    """
    parts = [dedup.norm_stem(q.stem)]
    for o in q.options:
        parts.append(dedup.norm_stem(o.text))
    return "\x00".join(parts)


def _incomplete_errors(qs) -> list[dict]:
    r"""**规矩（用户 2026-09-21 定）：没有答案或没有解析的题，一律不许入库。**

    缺了就是半成品——进了库，统计、界面、导出全都不完整（库里曾因此攒出
    4,598 道解答题答案栏空着、15 道没有解析）。列进 `errors`（硬错误），
    `preview` 与 `commit` 都会因此**拒绝整批**。

    ⚠️ 必须在**规范化之后**调用：解答题答案栏由 ENTRY 规则补成「见解析」，
    先判会把本该能入库的题误拦下。
    """
    out: list[dict] = []
    for q in qs:
        miss = []
        if not (q.answer or "").strip():
            miss.append("答案")
        if not (q.solution or "").strip():
            miss.append("解析")
        if miss:
            out.append({"seq": 0, "key": q.key,
                        "reason": "缺%s——本库规矩：没有答案或没有解析的题目不许入库"
                                  % "与".join(miss)})
    return out

def preview(text: str, *, src_dirs=None, book: str = "手工录入", label: str = "",
            region: str = "", year: int | None = None, source_no: str = "",
            points: list[str] | None = None, difficulty: str = "",
            update_force: bool = False, merge_into: dict | None = None,
            dup_threshold: float = 0.80) -> dict:
    r"""干跑：解析 + 图片预检 + 查重 + 校验 + 影响面。**什么都不写。**

    `src_dirs` 是图片搜索目录（不传则用默认来源目录）。
    """
    parsed = parse_source(text, book=book, label=label, region=region, year=year,
                          source_no=source_no, points=points, difficulty=difficulty)
    qs: list[Question] = parsed["questions"]
    errors = list(parsed["errors"])
    # 「并入这道」：先把 key 改过去，后面的查重/升级才认得出是同一道题
    merged = apply_merge_into(qs, merge_into)

    # ══ 处理顺序：**验证 → 修改 → 复核**（顶层设计 §七点六，优先级最高）══
    #
    # 顺序不许颠倒，也不许跳过：
    #   1. 验证   先看原始材料哪里不合规范（`amti/conform.py` 的 9 项检查）
    #   2. 修改   用规范器逐条改（`amti/normalize.py`）
    #   3. 复核   改完再验一遍，**必须 0 处不规范**才允许录入
    #
    # 为什么必须"先验后改"：不改就录，不合规的数据就进库了；
    # 只改不验，改错了也不知道。中间跳过任何一步，问题都会往后滚。

    # ── ① 验证（改之前）──
    # 图片这时候还在源目录，所以解析器要「目标目录 or 源目录」都认
    from . import conform
    _resolver = im.Resolver(list(src_dirs) if src_dirs else [im.OLD_IMG])

    def _can_find(name):
        return (im.IMG_DIR / name).is_file() or _resolver.find(name) is not None

    before = conform.run(qs, image_resolver=_can_find)

    # ── ② 修改 ──
    rule_log: dict[str, list[str]] = {}
    for q in qs:
        for name in norm.normalize(q, norm.ENTRY):
            rule_log.setdefault(name, []).append(q.key)
    errors.extend(_incomplete_errors(qs))     # 缺答案/解析 → 硬错误（新规矩）

    # ── ③ 图片入库（复制到 图片/ + 引用改成内容寻址名）──
    # **这一步必须在复核之前**：复核要检查最终的引用形态。
    # 干跑时只算映射、不改文件，但**内存里的题照样改**——
    # 不然复核看到的是旧文件名，会误报「不是内容寻址名」。
    _resolver = im.Resolver(list(src_dirs) if src_dirs else [im.OLD_IMG])
    fig_report: dict[str, dict] = {}
    img_rep = {"copied": 0, "reused": 0, "already": 0, "missing": []}
    for q in qs:
        rep = im.ingest_question(q, _resolver, dry_run=True, manifest=None)
        for orig, new, nbytes, _src in rep["copied"]:
            fig_report[new] = {"status": "found", "note": "找到，将复制",
                               "bytes": nbytes, "from": orig}
            img_rep["copied"] += 1
        for orig, new in rep["reused"]:
            fig_report[new] = {"status": "reused",
                               "note": "已在库（内容相同，复用）", "from": orig}
            img_rep["reused"] += 1
        for name in rep["already"]:
            fig_report[name] = {"status": "reused", "note": "已入库"}
            img_rep["already"] += 1
        for name in rep["missing"]:
            fig_report[name] = {"status": "missing", "note": "⚠ 缺失"}
            img_rep["missing"].append((q.key, name))

    # ── ④ 复核（改之后）──
    # 图片这时已经改名成内容寻址名了，但**干跑没落盘**，新名字哪儿都不存在。
    # 所以复核的解析器要认「③ 已经确认过、会复制过去」的那批名字。
    _will_exist = {n for n, v in fig_report.items() if v["status"] != "missing"}

    def _can_find_after(name):
        return name in _will_exist or (im.IMG_DIR / name).is_file()

    after = conform.run(qs, image_resolver=_can_find_after)

    # ── ① 解析结果 ──
    items = []
    for q in qs:
        items.append({
            "key": q.key,
            "type": q.type,
            "type_label": QTYPE_LABEL.get(q.type, q.type),
            "stem": q.stem,
            "answer": q.answer,
            "solution": q.solution,
            "points": q.points,
            # 考点**名称**、难度、星级——录入界面要显示，不然看不出
            # 这批题考什么、有多难。难度是主考点派生的，和库里同一套口径。
            "point_titles": q.point_titles,
            "difficulty": q.difficulty,
            "stars": q.stars,
            "figures": [f.id for f in q.figures],
            "flags": {
                "答案": bool(q.answer.strip()),
                "解析": bool(q.solution.strip()),
                "图": any(f.kind == "bitmap" for f in q.figures),
                "标签": bool(q.points),
                "小问": "\\begin{enumerate}" in q.stem,
            },
            "problems": q.problems(),
        })

    # ── 图片缺失清单（③ 的结果）──
    missing = sorted({n for _k, n in img_rep["missing"]})

    # ── ③ 查重 ──
    #
    # 口径和 `commit` 一致：**只有 key 相同才算"已在库"**。
    # 内容雷同只是提示——高考题按卷组织，文理卷出同一道题是常态，
    # 按内容判重会把理卷那道丢掉（实测 1992 全国卷（理）少入库 13 道）。
    existing = {dup_fingerprint(q) for _f, q in store.iter_questions()}
    existing_keys = {q.key for _f, q in store.iter_questions()}
    idx = dedup.DedupIndex(store.load_all())
    by_key = {q.key: q for _f, q in store.iter_questions()}
    for it in items:
        # ⚠️ **判据必须和 `commit` 一致**：key 相同 **或** 指纹相同。
        # 只看指纹会漏掉「同一个 key 但内容改了」——干跑说"新题"、
        # 入库却判"已在库"，两边说的不是一回事。
        it["same_key"] = (it["key"] in existing_keys
                          or dup_fingerprint_of(it) in existing)
        # ⚠️ **排除它自己**。库里已经有这个 key 时（重录 / 升级），不排除就会
        # 看到"这道题和它自己重复"——纯粹是噪音，还会让人以为库里另有一道。
        hits = idx.find(it["stem"], threshold=dup_threshold, top=3,
                        exclude={it["key"]})
        for h in hits:
            h["verdict"] = dedup.classify(h["score"])
            # **把库内那道题的正文带上**。只给题号和 0.87 这样的分数，
            # 人没法判断到底是不是同一道——判断不了就等于没提示。
            src = by_key.get(h["key"])
            if src is not None:
                h["stem"] = src.stem
                h["type_label"] = QTYPE_LABEL.get(src.type, src.type)
                h["has_answer"] = bool(src.answer.strip())
                h["has_solution"] = bool(src.solution.strip())
                h["point_titles"] = src.point_titles
                h["difficulty"] = src.difficulty
        it["dups"] = hits
        # **升级判定**：这道题库里已经有了，但手里这份更全？
        # 干跑就要说清楚"会升级还是会被跳过"，否则点下确认才发现白录了。
        old = by_key.get(it["key"])
        if old is not None:
            plan = merge_plan(old, _as_question(it), force=update_force)
            it["update"] = {k: v for k, v in plan.items()
                            if k not in ("solution",)}   # 正文太long，只报字段名
            it["update_fields"] = [k for k in plan
                                   if k in ("solution", "answer", "points", "difficulty")]
        else:
            it["update"] = {}
            it["update_fields"] = []

    # `merge` = **题目完全相同（含选项）所以不会入库**；
    # 这正是 `commit` 的跳过判据，口径必须一致。
    # 内容相似（但不完全相同）的算 `suspect`，只是提示，照样入库。
    n_merge = sum(1 for it in items if it["same_key"])
    n_upgrade = sum(1 for it in items if it["update_fields"])
    n_new = len(items) - n_merge
    n_suspect = sum(1 for it in items
                    if it["dups"] and it["dups"][0]["verdict"] == "疑似")

    # ── ④ 类型与字段校验 ──
    from collections import Counter
    types = Counter(q.type for q in qs)
    bad = [it for it in items if it["problems"] and "必须" in " ".join(it["problems"])]

    return {
        "ok": not missing and not errors and not bad,
        "count": len(qs),
        "items": items,
        "errors": errors,
        "images": fig_report,
        "missing_images": missing,
        "dup": {"new": n_new, "merge": n_merge, "suspect": n_suspect,
                "upgrade": n_upgrade},
        "types": [{"value": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                  for k, v in types.most_common()],
        "problems": [{"key": it["key"], "problems": it["problems"]}
                     for it in items if it["problems"]],
        # ── 规范三步：验证 → 修改 → 复核 ──
        "spec": {
            "before": before,                    # 改之前的违规
            "fixed": [{"name": n, "hits": len(ks)} for n, ks in rule_log.items()],
            "after": after,                      # 改之后的违规，必须为空
            "ok": not after,
        },
        # ── ⑤ 影响面：报**真实跑过的规则**，不是写死的一句话 ──
        "rules": {
            "applied": [{"name": n, "scope": norm.ENTRY, "hits": len(ks),
                         "why": (norm.get(n).why if norm.get(n) else "")}
                        for n, ks in rule_log.items()],
            "migrate": [{"name": r.name, "why": r.why} for r in norm.rules_of(norm.MIGRATE)],
        },
        "impact": {
            "existing_questions": 0,
            "note": "录入走 store.append（只追加），程序里没有改写已有行的路径；"
                    "上面列出的是本次实际生效的 ENTRY 级规则",
        },
    }


def commit(text: str, *, src_dirs=None, book: str = "手工录入", label: str = "",
           region: str = "", year: int | None = None, source_no: str = "",
           points: list[str] | None = None, difficulty: str = "",
           update_existing: bool = True, update_force: bool = False,
           merge_into: dict | None = None,
           skip_dup: bool = True, skip_missing_figures: bool = True) -> dict:
    r"""正式导入：图片入库 → 追加主文件。返回变更报告。

    `skip_dup=True` 时跳过与库内已高度重复（≥0.96）的题；
    `skip_missing_figures=True` 时跳过缺图的题——**不导入半成品**。
    """
    parsed = parse_source(text, book=book, label=label, region=region, year=year,
                          source_no=source_no, points=points, difficulty=difficulty)
    qs: list[Question] = parsed["questions"]
    if not qs:
        return {"ok": False, "error": "没有解析出任何题目", "added": []}
    apply_merge_into(qs, merge_into)      # 「并入这道」：key 先改过去

    # ══ 与 `preview` **完全相同**的五步（顶层设计 §七点六）══
    # 少一步或者换顺序，干跑看到的和落盘的就不是一个东西。
    from . import conform
    _resolver = im.Resolver(list(src_dirs) if src_dirs else [im.OLD_IMG])

    def _can_find(name):
        return (im.IMG_DIR / name).is_file() or _resolver.find(name) is not None

    # ① 验证
    before = conform.run(qs, image_resolver=_can_find)

    # ② 规范化
    rule_log: dict[str, int] = {}
    for q in qs:
        for name in norm.normalize(q, norm.ENTRY):
            rule_log[name] = rule_log.get(name, 0) + 1
    bad_qs = _incomplete_errors(qs)          # 缺答案/解析 → 整批不入库（新规矩）
    if bad_qs:
        head = "；".join("%s（%s）" % (b["key"], b["reason"].split("——")[0]) for b in bad_qs[:3])
        return {"ok": False, "added": [], "rules_applied": {},
                "error": "有 %d 道缺答案或解析，整批未入库：%s" % (len(bad_qs), head)}

    # ③ 图片入库（**真的复制**到 图片/ + 改写引用）
    img_rep = im.ingest_all(qs, src_dirs=src_dirs, dry_run=False,
                            write_manifest=True)
    missing_names = {n for _k, n in img_rep["missing"]}

    # ④ 复核——图片这时已经落盘、引用已是内容寻址名，可以严格查
    after_viol = conform.run(qs)
    if after_viol:
        # **复核不过就不录**。宁可持续停下来问人，也不把不合规的数据写进库。
        return {"ok": False, "error": "规范复核未通过，拒绝录入",
                "spec": {"before": before, "after": after_viol}}
    spec_report = {"before": before, "fixed": rule_log, "after": after_viol}

    # ⑤ 筛掉**同一个 key** 与缺图的，再追加
    #
    # ⚠️ 判据是 **key 相同**，不是**内容相同**。
    #
    # 高考题**按卷组织**：同一道题常常同时出现在文卷和理卷（还有春秋卷、
    # 甲乙卷）。按内容判重会把理卷那道丢掉，库里只剩文卷的 key——
    # 实测踩过：1992 全国卷（理）28 道全被判「并入」，实际只入库 15 道。
    #
    # 内容雷同仍然记下来（`meta.dup_of`），但**照样入库**，
    # 因为它是另一份卷子上的另一道题。
    # ⚠️ **两个判据都要**：
    #   * key 已在库         → 同一道题重录，跳过（否则 append 写第二份 → 重复 key）
    #   * 指纹（题干+选项）已存在 → 别处的同一道题（文理卷），跳过
    # 只用指纹会漏掉第一种：内容变了（比如补了图）但 key 没变，
    # 指纹判「新」→ append 又写一份 → **重复 key**。实测踩过（92 个重复）。
    existing_fp = {dup_fingerprint(x) for _f, x in store.iter_questions()}
    existing_keys = {x.key for _f, x in store.iter_questions()}
    idx = dedup.DedupIndex(store.load_all())
    skipped: list[dict] = []
    keep: list[Question] = []
    # **升级**：库里已有这道题，但手里这份更全（带解析／考点更多）。
    # 不新写一份（那会撞 key 或写重复），而是**改库里那一份**。
    upgrades: list[dict] = []
    all_qs = store.load_all()
    by_key = {x.key: x for x in all_qs}
    for q in qs:
        fp = dup_fingerprint(q)
        if skip_dup and (q.key in existing_keys or fp in existing_fp):
            old = by_key.get(q.key)
            plan = merge_plan(old, q, force=update_force) if old is not None else {}
            if update_existing and plan:
                fields = [k for k in plan
                          if k in ("solution", "answer", "points", "difficulty")]
                if plan.get("answer_prev"):
                    old.meta["answer_prev"] = plan["answer_prev"]
                if "solution" in plan:
                    old.solution = plan["solution"]
                if "answer" in plan:
                    old.answer = plan["answer"]
                if "points" in plan:
                    old.points = plan["points"]
                    old.meta["point_source"] = "manual"
                if "difficulty" in plan:
                    old.meta["difficulty"] = plan["difficulty"]
                    old.meta["stars"] = {"简单题": 1, "中档题": 2,
                                         "难题": 3}.get(plan["difficulty"], 0)
                # 答案/解析变了，作答括号得跟着重排
                norm.normalize(old, norm.ENTRY)
                # **盖时间戳**。这样 `store.diff()` 能把"有意升级"和
                # "规则偷偷动了存量"分开报——否则每次升级验收都会红。
                old.meta["upgraded_at"] = time.strftime("%Y-%m-%d %H:%M")
                old.meta["upgraded_fields"] = fields
                upgrades.append({"key": q.key, "fields": fields,
                                 "why": plan.get("solution_why", ""),
                                 "answer_prev": plan.get("answer_prev", "")})
            else:
                reason = ("这个 key 已在库" if q.key in existing_keys
                          else "题目与库内完全相同（含选项）")
                if update_existing:
                    reason += "，且手里这份并不更全"
                skipped.append({"key": q.key, "reason": reason})
            continue
        if skip_missing_figures and (set(q.meta.get("figure_missing") or []) & missing_names):
            skipped.append({"key": q.key, "reason": "缺图，不予导入"})
            continue
        hits = idx.find(q.stem, threshold=dedup.SUSPECT_SCORE, top=1)
        if hits:
            q.meta["dup_of"] = hits[0]["key"]          # 和谁雷同，记录下来
            q.meta["dup_score"] = hits[0]["score"]
        existing_fp.add(fp)          # 同一批里也不许重复
        keep.append(q)

    before_keys = {q.key for _f, q in store.iter_questions()}
    log = store.append(keep)
    if upgrades:
        # 升级动的是**库里已有的题**，`append` 只追加、改不了旧题，
        # 所以走整库重写（`rewrite_all` 会按 PER_VOLUME 重新分卷）。
        store.rewrite_all(all_qs)
    after_keys = {q.key for _f, q in store.iter_questions()}

    return {
        "ok": True,
        "rules_applied": rule_log,
        "spec": spec_report,
        "images": {"copied": img_rep["copied"], "reused": img_rep["reused"],
                   "missing": img_rep["missing"]},
        "added": sorted(after_keys - before_keys),
        "added_count": len(after_keys - before_keys),
        "upgraded": upgrades,
        "skipped": skipped,
        "log": log,
    }


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("ingest 自检")

    src = r"""
\begin{question}
设集合 $A=\{1,2,3\}$，$B=\{2,3,4\}$，则 $A\cup B=$（\quad）
\begin{choices}
  \item* $\{1,2,3,4\}$
  \item $\{2,3\}$
\end{choices}
\end{question}
\begin{solution}
由并集定义得 $\{1,2,3,4\}$.
\end{solution}

\begin{problem}
已知函数 $f(x)=x^2-2x$.
\begin{enumerate}
  \item 求 $f(x)$ 的最小值；
  \item 求 $f(x)$ 在 $[0,3]$ 上的值域.
\end{enumerate}
\end{problem}
\begin{solution}
（1）配方得 $f(x)=(x-1)^2-1$，最小值 $-1$.
\end{solution}
"""
    blocks = split_source(src)
    check("按环境切出 2 块", len(blocks) == 2, str(len(blocks)))
    check("块里带上了 solution", "solution" in blocks[0])

    parsed = parse_source(src, book="测试录入", label="第1套")
    qs = parsed["questions"]
    check("解析出 2 道", len(qs) == 2, str(len(qs)))
    check("第 1 道是单选", qs[0].type == "single_choice", qs[0].type)
    check("单选题答案从 \\item* 得出", qs[0].answer == "A", qs[0].answer)
    check("第 2 道是解答", qs[1].type == "detailed_answer", qs[1].type)
    check("key 自动生成", qs[0].key == "测试录入/第1套#1", qs[0].key)
    check("book 写进 meta", qs[0].meta.get("book") == "测试录入", str(qs[0].meta))

    _n0 = len(store.load_all())
    pv = preview(src, book="测试录入", label="第1套")
    check("干跑报数量", pv["count"] == 2, str(pv["count"]))
    check("干跑报题型分布", sum(t["n"] for t in pv["types"]) == 2, str(pv["types"]))
    check("干跑报出实际生效的 ENTRY 规则",
          any(r["scope"] == "ENTRY" for r in pv["rules"]["applied"]),
          str(pv["rules"]["applied"]))
    check("存量影响是 0", pv["impact"]["existing_questions"] == 0, str(pv["impact"]))
    check("无错误", not pv["errors"], str(pv["errors"]))
    check("干跑不写主文件",
          len(store.load_all()) == _n0, "%d → %d" % (_n0, len(store.load_all())))

    # 解析不出东西时要报错，不能静默成功
    pv2 = preview("这里没有任何题目环境", book="x")
    check("空材料 → 0 道", pv2["count"] == 0, str(pv2["count"]))

    # **key 避让**：出处留空时，不避让的话每道新题都算 `书/录入#1`，
    # 第二道起全被判"已在库"跳过——用户看到的是"重复"，其实是 key 撞了。
    # 实测踩过：demo 录不进去就是这个原因。
    _keys = {x.key for _f, x in store.iter_questions()}
    pv3 = preview("\\begin{problem}\n甲\n\\end{problem}", book="手工录入")
    k_first = pv3["items"][0]["key"]
    check("出处留空时新题顺延，不撞已有的 key", k_first not in _keys, k_first)

    # 同一批里两道无出处的题也不能撞
    pv4 = preview("\\begin{problem}\n甲\n\\end{problem}\n"
                  "\\begin{problem}\n乙\n\\end{problem}", book="手工录入")
    ks = [it["key"] for it in pv4["items"]]
    check("同一批两道题 key 不重复", len(set(ks)) == 2, str(ks))

    # ── 升级（merge_plan）────────────────────────────────────────────
    #
    # 铁律是**只升不降**：重录一遍不许把已有的解析/答案/考点抹掉。
    # 每一条都配一个反例，免得规则写反了还一路绿灯。
    def _q(sol="", ans="", pts=(), diff="", stem="题"):
        return Question(key="t/x", type="single_choice", stem=stem,
                        answer=ans, solution=sol, points=list(pts),
                        meta={"difficulty": diff} if diff else {})

    old = _q(sol="", ans="", pts=["1.1.1"])
    new = _q(sol="我写的解析", ans="B", pts=["1.1.1", "1.1.2"])
    pl = merge_plan(old, new)
    check("旧无解析、新有 → 补解析", pl.get("solution") == "我写的解析", str(pl))
    check("旧无答案、新有 → 补答案", pl.get("answer") == "B")
    check("考点取并集", pl.get("points") == ["1.1.1", "1.1.2"], str(pl.get("points")))

    # 反例一：**旧有解析，新没有 → 一个字都不许动**
    pl = merge_plan(_q(sol="库里已有的解析"), _q(sol="", pts=["1.1.1"]))
    check("旧有解析、新无 → 不动解析", "solution" not in pl, str(pl))

    # 反例二：旧的解析更好，新的也带解析 → 默认保留旧的
    pl = merge_plan(_q(sol="旧的"), _q(sol="新的"))
    check("两个都有解析 → 默认保留旧的", "solution" not in pl, str(pl))
    pl = merge_plan(_q(sol="旧的"), _q(sol="新的"), force=True)
    check("force=True 才覆盖解析", pl.get("solution") == "新的", str(pl))

    # 反例三：考点不能变少（并集只会多不会少）
    pl = merge_plan(_q(pts=["1.1.1", "1.1.2"]), _q(pts=["1.1.1"]))
    check("新考点更少 → 不动考点", "points" not in pl, str(pl))

    # 答案不同：以新的为准，但旧值要留痕
    pl = merge_plan(_q(ans="A"), _q(ans="B"))
    check("答案不同 → 用新的", pl.get("answer") == "B", str(pl))
    check("答案旧值留痕", pl.get("answer_prev") == "A", str(pl))

    # 完全一样 → 没有可升的，按重复跳过
    check("完全一样 → 空计划", merge_plan(_q(ans="A", pts=["1.1.1"]),
                                          _q(ans="A", pts=["1.1.1"])) == {})
    check("旧的更全 → 空计划", merge_plan(_q(sol="有", ans="A", pts=["1", "2"]),
                                          _q(sol="", ans="", pts=[])) == {})

    print("ingest 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
