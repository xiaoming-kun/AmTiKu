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
import threading
import time
from pathlib import Path

from . import dedup, images as im, knowledge as kb, normalize as norm, store
from .latex_ir import BODY_ENV_RE, parse_question
from .schema import QTYPE_LABEL, Option, Question

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
    # 分隔符不能进 key：`/` 会被当成卷名/题号的分隔，`#` 会和 `#N` 混。
    # 换成全角字符，key 安全、meta 里的原出处不改。
    book = str(book or "").replace("/", "／").replace("#", "＃")
    label = str(label or "").replace("/", "／").replace("#", "＃")
    taken = taken or set()
    n = i
    key = f"{book}/{label}#{n}"
    while key in taken:
        n += 1
        key = f"{book}/{label}#{n}"
    return key


#: 手工录入的唯一策略口径。界面/接口/干跑/提交都从这里取默认值，
#: 避免“这次改了 no-update，下次忘了 sync 到另一个入口”。
#: 补旧题模式是**显式例外**：只补空考点/难度，不新增、不改正文。
MANUAL_INGEST_POLICY = {
    "allow_upgrade": False,       # 默认不显示/不执行升级
    "skip_near": True,            # 整题相似超过阈值不录入
    "near_threshold": dedup.NEAR_DUP_SCORE,
    "update_existing": False,     # 默认已有题不更新
    "backfill_update_existing": True,  # 补旧题模式例外
}


_TITLE_RE = re.compile(r"\\title\s*\{")


def _read_braced(s: str, i: int) -> tuple[str | None, int]:
    r"""读 `s[i] == '{'` 起的配对花括号内容；认嵌套与 `\{`。

    返回 `(内容, 右括号之后的下标)`。配不平返回 `(None, i)`。
    比正则可靠：标题里常有 `\textbf{…}`、`\thanks{…}` 甚至数学公式。
    """
    if i >= len(s) or s[i] != "{":
        return None, i
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def _clean_title(raw: str) -> str:
    r"""标题去 LaTeX：保留字面字，去掉命令与分组。

    `\thanks{…}` / `\footnote{…}` 整条删掉——它们是致谢/脚注，不是出处。
    """
    t = re.sub(r"\\(?:thanks|footnote)\s*\{[^{}]*\}", "", raw or "")
    t = re.sub(r"\\[a-zA-Z]+\s*", "", t)
    t = t.replace("\\\\", " ").replace("~", " ")
    t = t.replace("\\&", "&").replace("\\%", "%").replace("\\_", "_")
    t = t.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip(" .。；;，,")


def extract_source_hint(text: str) -> dict:
    r"""从源材料**前几行**认出处：`\title{…}` 或第一行像标题的纯文本。

    返回 `{"title": str, "year": int | None}`。只做提示，**不决定元数据**——
    界面把它填进「出处/年份」输入框，人还可以改。
    """
    text = text or ""
    m0 = re.search(r"\\begin\{(?:question|problem)\}", text)
    head = text[:m0.start()] if m0 else text
    title = ""
    m = _TITLE_RE.search(head)
    if m:
        raw, _ = _read_braced(head, m.end() - 1)
        title = _clean_title(raw or "")
    if not title:
        # 没有 `\title`：前几行里第一条不以反斜杠/注释开头的短文本。
        for line in head.splitlines():
            line = line.strip()
            if not line or line.startswith("%") or line.startswith("\\"):
                continue
            if len(line) <= 120:
                title = _clean_title(line)
                break
    year = None
    if title:
        ys = [int(x) for x in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", title)]
        if ys:
            year = max(ys)       # 「2024-2025 学年」取考试年 2025
    return {"title": title, "year": year}


def extract_source_titles(text: str) -> list[dict]:
    r"""找出材料里**所有** `\title{…}`（不只看第一个），带回在原文里的位置。

    一份材料粘多张卷子时，每张卷子前面的 `\title` 就是这道题该用的出处；
    界面据此给每张卡预填「单题出处」，不用整批共用一个 label。
    返回 `[{"title", "year", "pos"}]`，按出现顺序。
    """
    out: list[dict] = []
    for m in _TITLE_RE.finditer(text or ""):
        raw, _ = _read_braced(text, m.end() - 1)
        title = _clean_title(raw or "")
        if not title:
            continue
        ys = [int(x) for x in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", title)]
        out.append({"title": title, "year": max(ys) if ys else None, "pos": m.start()})
    return out


def _override_by_block(items: list[dict] | None) -> dict[int, dict]:
    r"""把界面回传的逐题覆盖整理成 `{块下标: {…}}`。

    块下标是 `split_source` 切出来的**原始顺序**（0 起），来自干跑里的
    `items[].block`。这样即使中间有一块解析失败，后面的题也不会错位。
    没带 `block` 的按数组位置兜底。
    """
    out: dict[int, dict] = {}
    for pos, ov in enumerate(items or []):
        if not isinstance(ov, dict):
            continue
        try:
            b = int(ov.get("block", pos))
        except (TypeError, ValueError):
            b = pos
        out[b] = ov
    return out


def _points_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [x.strip() for x in v.split(",")]
    return [str(x).strip() for x in v if str(x).strip()]


def parse_source(text: str, *, book: str = "手工录入", label: str = "",
                 region: str = "", year: int | None = None,
                 source_no: str = "", points: list[str] | None = None,
                 difficulty: str = "", qtype: str = "",
                 items: list[dict] | None = None) -> dict:
    r"""解析源材料。返回 `{questions, errors, blocks}`。**不写任何东西。**

    `points` / `difficulty` / `qtype` 是**在界面上填的**。源材料的 meta JSON
    里也能写这几样，但界面上明明白白选了就该以界面为准（界面覆盖源材料）。
    自动打标那条路（LLM 读题干定考点）只在两者都没有时才跑。

    `items` 是**多题录入**的逐题覆盖（按 `block` 对到切出来的块）：
        {"block": 0, "pick": true, "source_no": "1",
         "points": ["8.5.1"], "difficulty": "简单题",
         "qtype": "single_choice", "point_source": "llm",
         "tag_model": "qwen3.5-9b-mlx", "tagged_at": "2026-..."}
    逐题值优先于全局值；`points: []` / `difficulty: ""` 是**明确清空**，
    不是「没填」。`pick=False` 由 `preview`/`commit` 在外面筛，解析照常进行
    ——这样才能在界面上把没勾的卡片也显示出来。

    `blocks` 与 `questions` 一一对应，记录每道题来自第几个题块（0 起）。
    """
    blocks = split_source(text)
    out: list[Question] = []
    used_blocks: list[int] = []
    used_texts: list[str] = []
    used_titles: list[dict] = []
    errors: list[dict] = []
    title_marks = extract_source_titles(text)
    cursor = 0
    ovs = _override_by_block(items)
    # 库里已有的 key。`_auto_key` 靠它避让，否则出处留空时
    # 每道新题都算出同一个 key，第二道起全被当成"重复"跳过。
    taken = {x.key for x in store.load_cached()}

    for i, blk in enumerate(blocks, 1):
        q = parse_question(blk)
        if q is None:
            errors.append({"seq": i, "block": i - 1,
                           "reason": "认不出题目环境", "snippet": blk[:80]})
            continue
        ov = ovs.get(i - 1, {})

        def val(key: str, default):
            """逐题覆盖：键在就用它的值（空串/空列表也算明确值）。"""
            return ov[key] if key in ov and ov[key] is not None else default

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
                errors.append({"seq": i, "block": i - 1,
                               "reason": "元数据行不是合法 JSON"})

        qtype_i = val("qtype", qtype)
        if q.type and meta.get("type"):
            q.type = meta["type"]
        if qtype_i:
            q.type = qtype_i

        book_i = str(val("book", book) or "手工录入").strip()

        def _inherit_str(key: str, default: str) -> str:
            """逐题覆盖为空 = 沿用全局；非空才覆盖。"""
            if key in ov:
                v = str(ov.get(key) or "").strip()
                if v:
                    return v
            return str(default or "").strip()

        label_i = _inherit_str("label", label)
        region_i = _inherit_str("region", region)
        year_i = val("year", year)
        if "year" in ov and not year_i:
            year_i = year
        source_no_i = val("source_no", source_no)

        # 全局参数保持老口径（源材料 meta 优先），逐题明确值覆盖。
        meta.setdefault("book", book_i)
        # **题号**：单题录入时记原卷的题号。试卷上标来源要用它，
        # 不能用 key 里的序号——那是新库自己的顺序，不是原卷题号。
        if source_no_i:
            meta["source_no"] = source_no_i
        elif "source_no" in ov:
            meta.pop("source_no", None)
        if label_i:
            if "label" in ov:
                meta["source_label"] = label_i
            else:
                meta.setdefault("source_label", label_i)
        # 逐题 label 空串 = **沿用全局出处**，不是“明确清空”。
        # 界面单卷时每张卡都带 label:''，早先这里 pop 掉了全局出处，
        # 导致“左栏明明写了出处，入库题却没有出处”。
        if region_i:
            if "region" in ov:
                meta["region"] = region_i
            else:
                meta.setdefault("region", region_i)
        elif "region" in ov:
            meta.pop("region", None)
        if year_i:
            meta["year"] = int(year_i)
        # 逐题 year 空串 = 沿用全局年份；同上，不能 pop。
        if "book" in ov:
            meta["book"] = book_i

        # 考点：逐题 > 全局 > 源材料 meta / 正文
        pts_i = points
        if "points" in ov:
            pts_i = _points_list(ov.get("points"))
        if pts_i is not None:
            pts_i = [p for p in dict.fromkeys(_points_list(pts_i)) if kb.get(p)]
            if pts_i:
                q.points = list(pts_i)
                meta["point_source"] = str(ov.get("point_source") or "manual")
                for f in ("tag_model", "tagged_at"):
                    if ov.get(f):
                        meta[f] = str(ov.get(f))
            elif "points" in ov:
                q.points = []
                meta.pop("point_source", None)

        # 难度：逐题 > 全局。逐题空串 = 明确清空（让难度回落到主考点派生）。
        diff_i = difficulty
        if "difficulty" in ov:
            diff_i = str(ov.get("difficulty") or "").strip()
        if diff_i:
            meta["difficulty"] = diff_i
            meta["stars"] = {"简单题": 1, "中档题": 2, "难题": 3}.get(diff_i, 0)
        elif "difficulty" in ov:
            meta.pop("difficulty", None)
            meta.pop("stars", None)

        q.meta = meta
        if ov.get("key"):
            q.key = str(ov["key"])
        if not q.key:
            q.key = _auto_key(book_i, label_i or "录入", i, meta, taken)
        taken.add(q.key)          # 同一批里也不许撞
        # 这块题前面最近的一个 `\title`（多卷材料分段用）
        pos = text.find(blk, cursor)
        if pos < 0:
            pos = cursor
        cursor = pos + len(blk)
        mark = None
        for t in title_marks:
            if t["pos"] < pos:
                mark = t
            else:
                break
        used_titles.append({
            "title": (mark or {}).get("title", ""),
            "year": (mark or {}).get("year"),
        })
        out.append(q)
        used_blocks.append(i - 1)
        used_texts.append(blk)

    # 块内题号重复会导致 key 撞车——这必须在写之前发现
    seen: dict[str, int] = {}
    for q in out:
        seen[q.key] = seen.get(q.key, 0) + 1
    for k, n in seen.items():
        if n > 1:
            errors.append({"seq": 0, "block": None,
                           "reason": f"key 重复 {k}（出现 {n} 次）"})

    return {"questions": out, "errors": errors, "blocks": used_blocks,
            "texts": used_texts, "block_titles": used_titles,
            "source_titles": title_marks}


def dup_fingerprint_of(item: dict) -> str:
    """`preview` 的 items 是 dict，用同样的口径算指纹。"""
    parts = [dedup.norm_stem(item.get("stem") or "")]
    for o in (item.get("options") or []):
        parts.append(dedup.norm_stem(o.get("text") or ""))
    return "\x00".join(parts)


def apply_merge_into(qs: list[Question], merge_into: dict | None,
                     *, blocks: list[int] | None = None,
                     merge_blocks: dict | None = None) -> list[dict]:
    r"""把新题**并到指定的库内题**上——「这其实就是同一道题，别新建了」。

    判重是算出来的，算不准（相似度 0.8 的两道题可能真是两道）。
    所以最终由人拍板：界面上点「并入这道」，就把新题的 key 改成那道题的
    key，后面走的是**升级**那条路（补解析、并考点、按需改答案），
    而不是新写一份。

    `merge_into` 形如 `{新题现在的 key: 库内那道题的 key}`。
    `merge_blocks` 形如 `{题块下标: 库内那道题的 key}`——多题录入界面用这个，
    因为出处在解析后还能改，**key 会跟着变，块下标不会**。
    """
    done: list[dict] = []
    if not merge_into and not merge_blocks:
        return done
    merge_into = merge_into or {}
    merge_blocks = merge_blocks or {}
    for i, q in enumerate(qs):
        b = blocks[i] if blocks is not None and i < len(blocks) else None
        tgt = merge_into.get(q.key)
        if not tgt and b is not None:
            tgt = merge_blocks.get(b) or merge_blocks.get(str(b))
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
    | 难度 | 旧没有、新的有 → 用新的；**考点并集换了主考点 → 按新主考点重算**，
      但只动「本来就是从考点派生出来」的难度，人手填过的不覆盖 |

    `force=True` 时解析也以新为准（界面上的「覆盖已有解析」开关）。

    返回 `{}` 表示没有可升的——那就按重复跳过。
    """
    plan: dict = {}

    if new.has_solution and not old.has_solution:
        plan["solution"] = new.solution
        plan["solution_why"] = "库里没有解析"
    elif force and new.has_solution and new.solution.strip() != old.solution.strip():
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
    elif "points" in plan and old.points:
        # 考点换了主考点 ⇒ **派生**的难度得跟着换，否则库里会出现
        # 「考点已是数列、难度还写着三角」的题（2026-09-26 用户口径：
        # 重复题的考点、难度以更全的一方为准）。
        # 只有旧难度本来就是考点派生的才动它；人填过的是判断，不覆盖。
        hand = old.meta.get("difficulty")
        if not hand or hand == kb.difficulty_of(old.points[0]):
            d = kb.difficulty_of(plan["points"][0])
            if d and d != old.difficulty:
                plan["difficulty"] = d
                # 星级跟主考点走，不能留旧主考点那份
                plan["stars"] = kb.stars_of(plan["points"][0])

    return plan


def backfill_plan(old: Question, new: Question) -> dict:
    r"""补旧题计划：**只补旧题的空考点/空难度，不碰正文**。

    和 `merge_plan` 的区别：

    * 不返回 `solution`/`answer`/`stars`（难度除外）——补标签模式不能改正文；
    * 考点只在**旧题一个考点都没有**时才补；旧题已有考点不合并、不覆盖；
    * 难度只在旧题**没有考点、也没有人手填难度**时才补；
      旧题有考点时难度是从主考点派生的，不算“缺”。

    这样用户重录一份老卷子时，可以只把当年漏标的考点补上，
    而不会把库里已经审过的答案/解析/考点动掉。
    """
    plan: dict = {}
    if not old.points and new.points:
        plan["points"] = list(new.points)
    old_manual_diff = str(old.meta.get("difficulty") or "").strip()
    new_diff = str(new.meta.get("difficulty") or "").strip()
    if not old.points and not old_manual_diff and new_diff:
        plan["difficulty"] = new_diff
        plan["stars"] = {"简单题": 1, "中档题": 2, "难题": 3}.get(new_diff, 0)
    return plan


def apply_plan(old: Question, plan: dict, *, point_source: str = "") -> list[str]:
    r"""把 `merge_plan` 的结果落到**库里那一道**上，返回动了哪些字段。

    `commit` 和批次末的 `apply_labels` 共用这一份，两边不许各写一套落账姿势。
    """
    fields = [k for k in plan if k in ("solution", "answer", "points", "difficulty")]
    if plan.get("answer_prev"):
        old.meta["answer_prev"] = plan["answer_prev"]
    if "solution" in plan:
        old.solution = plan["solution"]
    if "answer" in plan:
        old.answer = plan["answer"]
    if "points" in plan:
        old.points = plan["points"]
        # 谁的考点写谁的路数：录入线带的是 llm，界面上手填才是 manual
        old.meta["point_source"] = point_source or "manual"
    if "difficulty" in plan:
        old.meta["difficulty"] = plan["difficulty"]
        old.meta["stars"] = plan.get("stars", {
            "简单题": 1, "中档题": 2, "难题": 3}.get(plan["difficulty"], 0))
    if "solution" in plan or "answer" in plan:
        # 答案/解析变了，作答括号得跟着重排。**只改标签时不重排**——
        # 那会把一道没动的存量题的正文也改了，等于绕过"存量不变"那条承诺。
        norm.normalize(old, norm.ENTRY)
    # **盖时间戳**。这样 `store.diff()` 能把"有意升级"和
    # "规则偷偷动了存量"分开报——否则每次升级验收都会红。
    old.meta["upgraded_at"] = time.strftime("%Y-%m-%d %H:%M")
    old.meta["upgraded_fields"] = fields
    return fields


def apply_labels(entries: list[dict], *, dry_run: bool = False) -> dict:
    r"""**一批一次**整库重写：把逐场录入攒下的「考点/难度该刷给库里哪道」一次落账。

    为什么要有这条路：`commit` 只要产出一项升级就得 `rewrite_all` 全库
    （51MB 重写＋52MB 备份），而实测一批 20 场里 18 场都带升级 ⇒
    逐场重写等于把全库重抄二十遍，每场白搭三十秒。
    所以录入线的姿势改成：**逐场只追加**（`update_existing=False`），
    该刷的标签记进 journal，一批跑完再走这里。

    幂等：内部对每条重跑 `merge_plan`（只升不降），刷过的第二遍不会再改，
    所以 journal 重复、程序中断都可以直接重跑。
    `entries` 每条要 `dup_key`（库里那道）和 `points`（手里这道标了什么）。
    """
    all_qs, _sig = store.load_for_update()
    by_key = {x.key: x for x in all_qs}
    done, missing = [], []
    for e in entries:
        old = by_key.get(e.get("dup_key") or "")
        if old is None:
            missing.append(e)
            continue
        new = Question(key=old.key, type=old.type, stem=old.stem,
                       points=list(e.get("points") or []))
        plan = {k: v for k, v in merge_plan(old, new).items()
                if k in ("points", "difficulty", "stars")}
        if not plan:
            continue                       # 库里那道已经不差了（多半上一批刷过）
        fields = apply_plan(old, plan, point_source=e.get("point_source") or "")
        done.append({"key": old.key, "fields": fields})
    rep = {"刷了": len(done), "查无此key": len(missing), "dry_run": dry_run,
           "明细": done[:20]}
    if done and not dry_run:
        store.rewrite_all(all_qs, based_on=_sig)
    return rep


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


# 整栏只剩「【缺：…】」占位（外加标点与空白）＝**等于没有解析**。
# 扫描端按 `设计/试卷扫描标准化规范-交给大模型.md` 的铁律，用 `【缺：…】` 标原件就没有的内容；
# 而本闸原来只看「非空」，于是 2026-11-02 实测：南京一中卷 11 道选择题的解析栏
# 全是 `【缺：原答案册未提供本题解析】`，闸门全绿放进来。
# ⚠️ **只判「整栏都是占位」**：解析里夹一处 `【缺：…】`（个别符号读不清、推导仍完整）
# 的题照收，别把能用的解析当垃圾拦掉。
_GAP_ONLY_RE = re.compile(r"^(?:\s|　|[。．.，,、；;：:！!？?]|【缺[^】]*】)+$")


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
        sol = (q.solution or "").strip()
        if not sol:
            miss.append("解析")
        elif _GAP_ONLY_RE.match(sol):
            out.append({"seq": 0, "key": q.key,
                        "reason": "解析整栏只有「【缺：…】」占位（原件就没有）——"
                                  "按没有解析处理，不许入库；要走求解那条线补完再录"})
        if not (q.answer or "").strip():
            miss.append("答案")
        if miss:
            out.append({"seq": 0, "key": q.key,
                        "reason": "缺%s——本库规矩：没有答案或没有解析的题目不许入库"
                                  % "与".join(miss)})
    return out

# 「答案栏里混进解析」的标记：出现就不是一个答案值。
_ANSWER_MIX = re.compile(
    r"【解答】|【解析】|【锤子|数学解析"
    r"|(?:^|[\n；;])\s*(?:解析|答案)\s*[:：]")
# 卷首说明 / 节标题：不该出现在题干或解析里。
_FRONT_MATTER = re.compile(r"考试结束后|答题卡.{0,8}一并交回|本试卷共")
_SECTION_HEAD = re.compile(
    r"^[一二三四五六七八九十]\s*[、.．]\s*"
    r"(?:单项选择题|多选题|选择题|填空题|解答题|单选题)")


def _flat(s: str) -> str:
    """比对答案/作答位用：去掉排版噪音，但保留内容。"""
    # `；`/`;` 只是多空答案的分隔符：作答位是逐个 `\fillin`，答案栏是拼起来的。
    return re.sub(r"[\s${}\\;；]", "", s or "")


def _structure_errors(qs) -> list[dict]:
    r"""**结构自洽闸**：字段之间对不上，比"缺字段"更危险。

    这些错进了库不会报错、也能渲染，但卷面/答案是错的（实测：44 道
    逐题订正里绝大多数都属这一类）：

      · `q.problems()` 的结构错（单选多答案、选项数不对、图没登记…）；
      · 答案栏与题干里的 `\paren[…]` / `\fillin[…]` **对不上**；
      · 答案栏抄了整条题干、或混进了解析/`答案：`标签；
      · 解析栏抄了整条题干；
      · 题干/解析里混进卷首说明或下一节的标题；
      · 两个选项文字完全相同（OCR 串行）。

    **宁可整批拒收，也不要让错答案进库。**
    """
    out: list[dict] = []
    for q in qs:
        why: list[str] = []
        # 「选项内容为空」单独判：整组全空＝选项是图（`images` 之后会写
        # `figure_missing`）；只空一两个才是 OCR 丢字。这里不提前拦整组图片题。
        probs = [p for p in q.problems() if "内容为空" not in p]
        why.extend("结构不合法：%s" % p for p in probs)

        ans = (q.answer or "").strip()
        sol = (q.solution or "").strip()
        stem = (q.stem or "").strip()

        if ans and _flat(ans) == _flat(stem):
            why.append("答案栏抄了整条题干")
        if sol and _flat(sol) == _flat(stem):
            why.append("解析栏抄了整条题干")
        if ans and _ANSWER_MIX.search(ans):
            why.append("答案栏里混进了解析/「答案：」标签")

        for line in (stem + "\n" + sol).splitlines():
            line = line.strip()
            if _SECTION_HEAD.match(line) or _FRONT_MATTER.search(line):
                why.append("题干/解析里混进了卷首说明或节标题：%s" % line[:32])
                break

        texts = [o.text.strip() for o in q.options if o.text.strip()]
        if len(texts) != len(set(texts)):
            dup = next(t for t in texts if texts.count(t) > 1)
            why.append("有两个选项文字完全相同：%s" % dup[:32])
        empties = [o.label for o in q.options if not o.text.strip()]
        if empties and len(empties) != len(q.options):
            why.append("选项 %s 内容为空（不是整组图片选项）" % "、".join(empties))

        # 答案栏 ↔ 作答位：这是"答案被挂到别的题上"最常见的形态。
        from .latex_ir import fillin_answers, paren_answers
        pa = paren_answers(q.stem)
        fa = fillin_answers(q.stem)
        if q.type in ("single_choice", "multi_choice") and pa:
            if _flat(pa[-1]) != _flat(ans):
                why.append("答案栏 %r 与作答位 \\paren[%s] 不一致"
                           % (ans[:24], pa[-1][:24]))
        elif q.type == "fill_in_blank" and fa:
            if _flat("".join(fa)) != _flat(ans):
                why.append("答案栏 %r 与作答位 \\fillin[…] 不一致" % ans[:24])
        elif q.type == "detailed_answer" and pa:
            why.append("解答题的题干里不该有 \\paren[…] 作答位")

        if why:
            out.append({"seq": 0, "key": q.key, "reason": "；".join(why)})
    return out


#: 查重索引缓存（按卷文件签名）。30k 道的整题指纹索引构建要几秒，
#: 多题录入每次解析都重建就是白等；库一改签名就整体失效。
_INDEX_CACHE: dict = {}
_INDEX_LOCK = threading.Lock()


def _dedup_index(sig, all_qs, *, full: bool = False):
    r"""取（或构建）查重索引。`full=True` 索引整题指纹，用于 95% 规则。"""
    key = "full" if full else "stem"
    with _INDEX_LOCK:
        c = _INDEX_CACHE
        if c.get("sig") != sig:
            c.clear()
            c["sig"] = sig
        if key not in c:
            c[key] = (dedup.DedupIndex(
                all_qs, text_of=dup_fingerprint, normalize=lambda x: x)
                if full else dedup.DedupIndex(all_qs))
        return c[key]


def preview(text: str, *, src_dirs=None, book: str = "手工录入", label: str = "",
            region: str = "", year: int | None = None, source_no: str = "",
            points: list[str] | None = None, difficulty: str = "",
            qtype: str = "",
            update_force: bool = False, merge_into: dict | None = None,
            merge_blocks: dict | None = None,
            items: list[dict] | None = None,
            allow_upgrade: bool = True,
            skip_near: bool = False,
            near_threshold: float = dedup.NEAR_DUP_SCORE,
            dup_threshold: float = 0.80,
            backfill: bool = False) -> dict:
    r"""干跑：解析 + 图片预检 + 查重 + 校验 + 影响面。**什么都不写。**

    `src_dirs` 是图片搜索目录（不传则用默认来源目录）。
    """
    parsed = parse_source(text, book=book, label=label, region=region, year=year,
                          source_no=source_no, points=points, difficulty=difficulty,
                          qtype=qtype, items=items)
    qs: list[Question] = parsed["questions"]
    q_blocks: list[int] = parsed.get("blocks") or list(range(len(qs)))
    q_texts: list[str] = parsed.get("texts") or [""] * len(qs)
    q_titles: list[dict] = parsed.get("block_titles") or [{}] * len(qs)
    errors = list(parsed["errors"])
    # 「并入这道」：先把 key 改过去，后面的查重/升级才认得出是同一道题
    merged = apply_merge_into(qs, merge_into, blocks=q_blocks,
                              merge_blocks=merge_blocks)

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
    errors.extend(_structure_errors(qs))      # 字段自洽 → 硬错误（P0 闸）

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
    for q, b, blk, bt in zip(qs, q_blocks, q_texts, q_titles):
        items.append({
            "key": q.key,
            # 原始题块：卡片上的「改源码」用。**保留原样**，不要拿渲染器重排，
            # 否则用户改一个字会把整段格式/公式都重写一遍。
            "tex": blk,
            # 多题录入：界面用 `block` 把卡片对回源材料里的题块。
            # 出处在解析后还能改（key 会变），块下标不会变。
            "block": b,
            "block_title": bt.get("title") or "",
            "block_year": bt.get("year"),
            "source_no": q.meta.get("source_no") or "",
            "label": q.meta.get("source_label") or "",
            "book": q.meta.get("book") or "",
            "year": q.meta.get("year") or None,
            "point_source": q.meta.get("point_source") or "",
            "tag_model": q.meta.get("tag_model") or "",
            "tagged_at": q.meta.get("tagged_at") or "",
            # 只有**明确写在 meta 里**的难度才算人手定的；`q.difficulty`
            # 可能是主考点派生的——界面要能分清，否则改考点后难度不跟着变。
            "manual_difficulty": q.meta.get("difficulty") or "",
            "type": q.type,
            "type_label": QTYPE_LABEL.get(q.type, q.type),
            "stem": q.stem,
            # 判重指纹 = 题干 + **选项正文**（见 `dup_fingerprint`）。items 里不带选项，
            # `dup_fingerprint_of(it)` 就只能算题干那一段 ⇒ 干跑对选择题的 merge 永远报 0，
            # 而 commit 却照样跳过它们。干跑和落盘必须是一个口径，所以这里带上选项。
            "options": [{"label": o.label, "text": o.text} for o in q.options],
            "answer": q.answer,
            "solution": q.solution,
            "points": q.points,
            # 考点**名称**、难度、星级——录入界面要显示，不然看不出
            # 这批题考什么、有多难。难度是主考点派生的，和库里同一套口径。
            "point_titles": q.point_titles,
            "difficulty": q.difficulty,
            "stars": q.stars,
            "figures": [f.id for f in q.figures],
            # 干跑还没复制到 `图片/`，但原图在来源目录里；给卡片一个预览入口。
            "figure_previews": {
                f.id: fig_report.get(f.id, {}).get("from", "")
                for f in q.figures
                if fig_report.get(f.id, {}).get("status") == "found"
                and fig_report.get(f.id, {}).get("from")
            },
            "flags": {
                "答案": bool(q.answer.strip()),
                "解析": q.has_solution,
                "图": q.figure_ok,
                "标签": bool(q.points),
                "小问": "\\begin{enumerate}" in q.stem,
            },
            "problems": q.problems(),
            # 逐题诊断：界面上把**不能入库的原因**直接挂在卡上，而不是
            # 只在右栏底部汇总一句"3 道有问题"（人还得自己找是哪三道）。
            "errors": [],
            "spec_before": [],
            "spec_after": [],
            "missing_images": [],
            "blocking": [],
        })

    # ── 图片缺失清单（③ 的结果）──
    missing = sorted({n for _k, n in img_rep["missing"]})

    # ── ③ 查重 ──
    #
    # 口径和 `commit` 一致：**只有 key 相同才算"已在库"**。
    # 内容雷同只是提示——高考题按卷组织，文理卷出同一道题是常态，
    # 按内容判重会把理卷那道丢掉（实测 1992 全国卷（理）少入库 13 道）。
    # 库里那份的三个索引，**一趟扫完**。以前这儿是四次 `iter_questions()`
    # 各扫一遍全库（21,063 道 × 4），而 preview 是逐场调的 —— 体检 571 场
    # 光重复扫库就多花十几分钟。
    existing: set[str] = set()
    existing_keys: set[str] = set()
    by_key: dict[str, Question] = {}
    # 指纹 → 库里那道。**另一份卷子上的同一道题，key 必然不同**，
    # 只按 key 找「库里那份」，重复题的考点/难度就永远对不上账。
    by_fp: dict[str, Question] = {}
    # **一趟扫完**：这里原先是 `iter_questions()` + `load_all()` 两趟，
    # 每趟都把 29k 道重新解析一遍；多题录入每粘一份卷子都跑一次 preview，
    # 两趟就是十秒级的白等。`load_cached()` 按卷文件签名缓存，写库后自动失效，
    # 读的仍是同一份真相。
    all_qs = store.load_cached()
    sig = store.volume_signature()
    idx = _dedup_index(sig, all_qs)
    for q in all_qs:
        fp = dup_fingerprint(q)
        existing.add(fp)
        by_fp.setdefault(fp, q)
        existing_keys.add(q.key)
        by_key[q.key] = q
    # 先判精确重复；**全是指纹完全相同的批次不需要整题索引**（省几秒）。
    for it in items:
        # ⚠️ **判据必须和 `commit` 一致**：key 相同 **或** 指纹相同。
        # 只看指纹会漏掉「同一个 key 但内容改了」——干跑说"新题"、
        # 入库却判"已在库"，两边说的不是一回事。
        it["same_key"] = (it["key"] in existing_keys
                          or dup_fingerprint_of(it) in existing)
    need_full = skip_near and any(not it["same_key"] for it in items)
    idx_full = _dedup_index(sig, all_qs, full=True) if need_full else None
    for it in items:
        # ⚠️ **排除它自己**。库里已经有这个 key 时（重录 / 升级），不排除就会
        # 看到"这道题和它自己重复"——纯粹是噪音，还会让人以为库里另有一道。
        hits = idx.find(it["stem"], threshold=dup_threshold, top=3,
                        exclude={it["key"]})
        for h in hits:
            h["verdict"] = dedup.verdict_of(h)
            # **把库内那道题的正文带上**。只给题号和 0.87 这样的分数，
            # 人没法判断到底是不是同一道——判断不了就等于没提示。
            src = by_key.get(h["key"])
            if src is not None:
                h["stem"] = src.stem
                h["type_label"] = QTYPE_LABEL.get(src.type, src.type)
                h["has_answer"] = bool(src.answer.strip())
                h["has_solution"] = src.has_solution
                h["point_titles"] = src.point_titles
                h["difficulty"] = src.difficulty
                # 给人工对比用：库内答案/解析截断即可，避免整份卷子 payload 过大。
                h["answer_preview"] = (src.answer or "")[:300]
                h["solution_preview"] = (src.solution or "")[:600]
                # 题干相似度是**粗筛**；这里再算一遍整题（题干+选项）相似度，
                # 95% 阈值按这个口径判，避免"题干一样、选项不同"被误杀。
                h["score_full"] = round(dedup.similarity(
                    dup_fingerprint_of(it), dup_fingerprint(src)), 3)
        hits.sort(key=lambda h: (-(h.get("score_full") or 0),
                                 -(h.get("score") or 0)))
        it["dups"] = hits
        it["near_dup"] = False
        it["near_score"] = 0.0
        it["near_key"] = ""
        if skip_near and not it["same_key"] and idx_full is not None:
            # 按用户 2026-11-03 口径：整题相似 >95% 就跳过，**不区分变式**。
            nh, _ncomplete = idx_full.find_norm(
                dup_fingerprint_of(it), threshold=near_threshold,
                top=1, exclude={it["key"]})
            if nh and nh[0]["score"] > near_threshold:
                best = nh[0]
                full = float(best["score"])
                it["near_dup"] = True
                it["near_score"] = round(full, 3)
                it["near_key"] = best["key"]
                src = by_key.get(best["key"])
                if src is not None:
                    disp = dict(best)
                    disp.update({
                        "score_full": round(full, 3), "stem": src.stem,
                        "type_label": QTYPE_LABEL.get(src.type, src.type),
                        "has_answer": bool(src.answer.strip()),
                        "has_solution": src.has_solution,
                        "point_titles": src.point_titles,
                        "difficulty": src.difficulty,
                        "answer_preview": (src.answer or "")[:300],
                        "solution_preview": (src.solution or "")[:600],
                        "verdict": "高度相似",
                    })
                    it["dups"] = [disp] + [x for x in it["dups"]
                                           if x["key"] != best["key"]]
        # **升级判定**：这道题库里已经有了，但手里这份更全？
        # 干跑就要说清楚"会升级还是会被跳过"，否则点下确认才发现白录了。
        old = by_key.get(it["key"])
        if old is None:
            old = by_fp.get(dup_fingerprint_of(it))
        it["dup_key"] = old.key if old is not None else ""
        it["old_points"] = list(old.points) if old is not None else []
        it["old_difficulty"] = str(old.meta.get("difficulty") or "") if old is not None else ""
        if old is not None:
            if backfill:
                # 补旧题：**只补空考点/空难度**，不碰答案/解析，不合并已有考点。
                plan = backfill_plan(old, _as_question(it))
            else:
                plan = merge_plan(old, _as_question(it), force=update_force)
                if old.key != it["key"]:
                    # 别处的同一道题（key 不同）：正文一个字都不动，只对考点/难度
                    plan = {k: v for k, v in plan.items()
                            if k in ("points", "difficulty", "stars")}
            it["update"] = {k: v for k, v in plan.items()
                            if k not in ("solution",)}   # 正文太long，只报字段名
            it["update_fields"] = [k for k in plan
                                   if k in ("solution", "answer", "points", "difficulty")]
        else:
            it["update"] = {}
            it["update_fields"] = []

    # 手工录入规则：库里已有同题一律**跳过，不新增也不更新**。
    # 预览也不该显示"将升级"（否则人以为提交会补字段）。
    if not allow_upgrade:
        for it in items:
            it["update"] = {}
            it["update_fields"] = []
    # 高度相似（>95%）的也不显示升级：它同样要整题跳过。
    for it in items:
        if it.get("near_dup"):
            it["update"] = {}
            it["update_fields"] = []

    # `merge` = **题目完全相同（含选项）**；`near` = 整题相似 >95%（非变式），
    # 两者在手工录入里都**不入库、不更新**。`suspect` 只是提示。
    n_upgrade = sum(1 for it in items if it["update_fields"])
    if backfill:
        # 补旧题模式：精确重复可更新；新题/近似重复都不新增。
        n_merge = 0
        n_near = 0
        n_new = 0
        n_skip = len(items) - n_upgrade
    else:
        n_merge = sum(1 for it in items if it["same_key"])
        n_near = sum(1 for it in items if it.get("near_dup"))
        n_new = len(items) - n_merge - n_near
        n_skip = n_merge + n_near
    n_suspect = sum(1 for it in items
                    if it["dups"] and it["dups"][0]["verdict"] == "疑似")

    # ── 逐题诊断：把错误/规范/缺图挂到对应卡片上 ──
    #
    # 汇总一句"3 道有问题"没用——人还得自己逐张卡找是哪三道。
    # 这里一次挂好，界面直接显示"这道为什么不能入库"。
    item_by_key = {it["key"]: it for it in items}
    item_by_block = {it["block"]: it for it in items}
    for e in errors:
        it = item_by_key.get(e.get("key") or "")
        if it is None and e.get("block") is not None:
            it = item_by_block.get(e["block"])
        if it is not None:
            it["errors"].append(e)
    for b in before:
        it = item_by_key.get(b.get("key") or "")
        if it is not None:
            it["spec_before"].append(b)
    for b in after:
        it = item_by_key.get(b.get("key") or "")
        if it is not None:
            it["spec_after"].append(b)
    for k, name in img_rep["missing"]:
        it = item_by_key.get(k)
        if it is not None:
            it["missing_images"].append(name)

    for it in items:
        why: list[str] = []
        if not it["flags"]["答案"]:
            why.append("缺答案")
        if not it["flags"]["解析"]:
            why.append("缺解析")
        # commit 会因为这些整批拒绝：只把**带 key 的硬错误**算进来。
        # 坏元数据行（block 有、key 没有）只提示，不拦——正文本身还能录。
        for e in it["errors"]:
            if e.get("key") and e.get("reason"):
                why.append(str(e["reason"]))
        for v in it["spec_after"]:
            why.append("规范复核：%s" % v.get("why", ""))
        for name in it["missing_images"]:
            why.append("缺图：%s" % name)
        it["blocking"] = list(dict.fromkeys(why))

    # ── ④ 类型与字段校验 ──
    from collections import Counter
    types = Counter(q.type for q in qs)
    bad = [it for it in items if it["problems"] and "必须" in " ".join(it["problems"])]

    return {
        "ok": not missing and not errors and not bad,
        "count": len(qs),
        "items": items,
        "errors": errors,
        # 前几行里的标题/年份：界面用来预填「出处/年份」，**可改**。
        "source_hint": extract_source_hint(text),
        # 多卷材料里所有 \title 及原文位置；界面用来给每张卡预填单题出处。
        "source_titles": parsed.get("source_titles") or [],
        "images": fig_report,
        "missing_images": missing,
        "dup": {"new": n_new, "merge": n_merge, "near": n_near,
                "skip": n_skip, "suspect": n_suspect,
                "upgrade": n_upgrade, "update": n_upgrade,
                "backfill": bool(backfill)},
        "backfill": bool(backfill),
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


def select_by_pick(qs: list[Question], blocks: list[int],
                   items: list[dict] | None) -> tuple[list[Question], list[int]]:
    r"""多题录入：按界面回传的 `pick` 只留下勾选的题。

    `blocks` 与 `qs` 一一对应（来自 `parse_source`）。没勾的题仍然解析、
    仍然显示，但不写库；`items` 为空（CLI/老界面）时原样全留，行为不变。
    """
    if not items:
        return list(qs), list(blocks)
    ovs = _override_by_block(items)
    keep = [(q, b) for q, b in zip(qs, blocks)
            if ovs.get(b, {}).get("pick", True)]
    return [q for q, _b in keep], [b for _q, b in keep]


def commit(text: str, *, src_dirs=None, book: str = "手工录入", label: str = "",
           region: str = "", year: int | None = None, source_no: str = "",
           points: list[str] | None = None, difficulty: str = "",
           qtype: str = "",
           update_existing: bool = True, update_force: bool = False,
           merge_into: dict | None = None, merge_blocks: dict | None = None,
           items: list[dict] | None = None,
           skip_dup: bool = True, skip_missing_figures: bool = True,
           skip_near: bool = False,
           near_threshold: float = dedup.NEAR_DUP_SCORE,
           backfill: bool = False) -> dict:
    r"""正式导入：图片入库 → 追加主文件。返回变更报告。

    `skip_dup=True` 时跳过 key 或指纹（题干+选项）完全相同的题；
    `skip_near=True` 时再跳过**整题相似度 > `near_threshold`（默认 95%）**
    的题；`skip_missing_figures=True` 时跳过缺图的题。
    `backfill=True` 是**补旧题模式**：只给库里已有题补空考点/空难度，
    不新增、不改答案/解析/已有考点。
    """
    parsed = parse_source(text, book=book, label=label, region=region, year=year,
                          source_no=source_no, points=points, difficulty=difficulty,
                          qtype=qtype, items=items)
    qs: list[Question] = parsed["questions"]
    q_blocks: list[int] = parsed.get("blocks") or list(range(len(qs)))
    if not qs:
        return {"ok": False, "error": "没有解析出任何题目", "added": []}
    # 多题录入：只落**勾选**的题。没勾的题仍然解析/展示，但不进库。
    qs, q_blocks = select_by_pick(qs, q_blocks, items)
    if not qs:
        return {"ok": False, "error": "没有勾选任何题目", "added": []}
    # 「并入这道」：key 先改过去。块下标优先，出处在解析后改了也不会错位。
    apply_merge_into(qs, merge_into, blocks=q_blocks,
                     merge_blocks=merge_blocks)

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
    bad_qs = _incomplete_errors(qs) + _structure_errors(qs)  # 缺字段 + 字段自洽
    if bad_qs:
        head = "；".join("%s（%s）" % (b["key"], b["reason"].split("——")[0]) for b in bad_qs[:3])
        return {"ok": False, "added": [], "rules_applied": {},
                "error": "有 %d 道不合入库要求，整批未入库：%s" % (len(bad_qs), head)}

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
    # 库内索引**一次装载、一趟扫完**：这里原先是 `iter_questions()` 两趟
    # ＋`load_all()` 两趟（每趟把 21,063 道重新解析一遍），
    # 而 commit 是逐场调的 —— 体检 571 场光重复读库就要多花十几分钟。
    all_qs, _sig = store.load_for_update()
    idx = _dedup_index(_sig, all_qs)
    idx_full = None
    skipped: list[dict] = []
    keep: list[Question] = []
    # 查重被截断了几道（见下面 `find_checked` 的说明）。>0 时报告里要明说
    # "本次查重结果可能不完整"，而不是让人以为"查过了，没重复"。
    dup_incomplete = 0
    # **升级**：库里已有这道题，但手里这份更全（带解析／考点更多）。
    # 不新写一份（那会撞 key 或写重复），而是**改库里那一份**。
    upgrades: list[dict] = []
    existing_fp: set[str] = set()
    existing_keys: set[str] = set()
    by_key: dict[str, Question] = {}
    # 指纹 → 库里那道：**另一份卷子上的同一道题，key 必然不同**。
    # 只按 key 找"库里那份"，这种重复题的考点/难度就永远对不上账
    # （手里这份标了考点、库里那道空着或标得更少，白白浪费一次录入）。
    by_fp: dict[str, Question] = {}
    for x in all_qs:
        fp = dup_fingerprint(x)
        existing_fp.add(fp)
        by_fp.setdefault(fp, x)
        existing_keys.add(x.key)
        by_key[x.key] = x
    for q in qs:
        fp = dup_fingerprint(q)
        if skip_dup and (q.key in existing_keys or fp in existing_fp):
            old = by_key.get(q.key) or by_fp.get(fp)
            if backfill:
                if old is None:
                    skipped.append({"key": q.key,
                                    "reason": "补旧题模式只更新已有题，不新增"})
                    continue
                plan = backfill_plan(old, q)
                if not plan:
                    skipped.append({"key": q.key,
                                    "reason": "库里这道已有考点/难度，没有可补的空字段"})
                    continue
                fields = apply_plan(old, plan,
                                    point_source=q.meta.get("point_source") or "manual")
                upgrades.append({"key": q.key, "dup_key": old.key,
                                 "fields": fields, "why": "补旧题空字段",
                                 "answer_prev": ""})
                continue
            plan = merge_plan(old, q, force=update_force) if old is not None else {}
            if old is not None and old.key != q.key:
                # 别处的同一道题：正文一个字都不动，只对考点/难度
                plan = {k: v for k, v in plan.items()
                        if k in ("points", "difficulty", "stars")}
            if update_existing and plan:
                fields = apply_plan(old, plan, point_source=q.meta.get("point_source") or "")
                upgrades.append({"key": q.key, "dup_key": old.key,
                                 "fields": fields,
                                 "why": plan.get("solution_why", ""),
                                 "answer_prev": plan.get("answer_prev", "")})
            else:
                reason = ("这个 key 已在库" if q.key in existing_keys
                          else "题目与库内完全相同（含选项）")
                if update_existing:
                    reason += "，且手里这份并不更全"
                skipped.append({"key": q.key, "reason": reason})
            continue
        if backfill:
            # 补旧题模式：不是精确重复的题一律不新增（近似重复也不更新，
            # 因为不知道应该改库里哪一道）。
            skipped.append({"key": q.key,
                            "reason": "补旧题模式只更新已有题，不新增"})
            continue
        if skip_near:
            if idx_full is None:      # 有非精确重复的题才建整题索引
                idx_full = _dedup_index(_sig, all_qs, full=True)
            nh, _ncomplete = idx_full.find_norm(
                fp, threshold=near_threshold, top=1, exclude={q.key})
            if nh and nh[0]["score"] > near_threshold:
                skipped.append({
                    "key": q.key,
                    "reason": "与库内 %s 整题相似 %.1f%%（>%.0f%%），"
                              "按规则不导入、不更新"
                              % (nh[0]["key"], nh[0]["score"] * 100,
                                 near_threshold * 100)})
                continue
        if skip_missing_figures and (set(q.meta.get("figure_missing") or []) & missing_names):
            skipped.append({"key": q.key, "reason": "缺图，不予导入"})
            continue
        # ⚠️ 用 `find_checked` 而不是 `find`：粗筛的候选数有上限，
        # 被截断时"没找到重复"是**不可信**的。这个信号要一路带到报告里，
        # 不能让它烂在索引内部 —— 否则用户看到的是"查过了，没重复"。
        hits, dup_complete = idx.find_checked(
            q.stem, threshold=dedup.SUSPECT_SCORE, top=1)
        if not dup_complete:
            dup_incomplete += 1
        if hits:
            q.meta["dup_of"] = hits[0]["key"]          # 和谁雷同，记录下来
            q.meta["dup_score"] = hits[0]["score"]
            # 反方向的对账：手里这道**没标考点**，而库里那道雷同的标了 ⇒ 拿它当参考
            # （用户 2026-09-26 口径）。只在 `并入` 档（≥ MERGE_SCORE）抄：
            # 0.80 那一档只是"像"，照抄会把考点挂到别的题上。
            if not q.points and dedup.verdict_of(hits[0]) == "并入":
                src = by_key.get(hits[0]["key"])
                if src is not None and src.points:
                    q.points = list(src.points)
                    q.meta["point_source"] = "库里同题"
        existing_fp.add(fp)          # 同一批里也不许重复
        keep.append(q)

    before_keys = {q.key for _f, q in store.iter_questions()}
    log = store.append(keep)
    if upgrades:
        # 升级动的是**库里已有的题**，`append` 只追加、改不了旧题，
        # 所以走整库重写（`rewrite_all` 会按 PER_VOLUME 重新分卷）。
        # ⚠️ 必须把本批新增**一起**写回去：`all_qs` 是 `append` 之前抓的快照，
        # 只传 `all_qs` 等于按"追加前"的样子整库重写 —— 本次新增会被整批抹掉，
        # 而 commit 照样返回 ok、`added_count` 变成 0。
        # （worker C 2026-09-23 沙盒实证：8 道全新 key 的题 0 道幸存。）
        # 用 `update()` 做**合并**，不要 `rewrite_all(all_qs + keep)`。
        #
        # 旧写法有两个问题，都在"快照之后库又变了"这一个根上：
        #  · `all_qs` 是 `append` 之前抓的，直接整库写回会抹掉本批新增
        #    （下面那段 worker C 的实证就是它）；
        #  · 就算把 `keep` 拼回去，快照之后**别人**写进来的题照样会被覆盖。
        # 合并式写回把两个都解决了：锁内重读全库，按 key 把本次升级套上去，
        # 库里多出来的（并发的写入）原样保留，库里少掉的（别人删了）也不复活。
        #
        # ⚠️ **只能拿「本次真正升级的那几道」**。`all_qs` 是 append 之前的
        # **全库快照**；用整份快照覆盖，等于把快照之后别人（后台求解器 /
        # 另一场录入）写进**任意已有题**的答案/解析静默回滚，接口还返回 ok。
        # 旧写法就是全量，worker 复核时发现了这个窗口。
        upgraded_keys = {u["dup_key"] for u in upgrades}
        upgraded = {q.key: q for q in all_qs if q.key in upgraded_keys}
        keep_by_key = {q.key: q for q in keep}

        def _merge(qs):
            have = {q.key for q in qs}
            out = [upgraded.get(q.key, q) for q in qs]  # 升级覆盖同 key，其余不动
            out += [q for k, q in keep_by_key.items() if k not in have]
            return out

        store.update(_merge)
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
        # 查重索引的覆盖率与本次是否被截断 —— 让"没发现重复"这件事**可信**
        "dedup_index": dedup.index_status(idx),
        "dedup_incomplete": dup_incomplete,
        "dedup_warning": (
            "本次有 %d 道题的查重候选被截断（上限 %d），**结果可能不完整**，"
            "请对这几道再人工扫一眼" % (dup_incomplete, dedup.DedupIndex.MAX_CANDIDATES)
            if dup_incomplete else ""),
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

    # 界面上明确选的题型**覆盖**从正文推断出来的（`qtype=`）：
    # 录一道还没写答案的多选题时，正文推断会判成单选，得能手动改过来。
    _ov = parse_source(src, book="测试录入", label="第1套",
                       qtype="multi_choice")["questions"]
    check("界面选的题型覆盖推断结果",
          [_q.type for _q in _ov] == ["multi_choice", "multi_choice"],
          str([_q.type for _q in _ov]))
    _ov2 = parse_source(src, book="测试录入", label="第1套",
                        qtype="detailed_answer")["questions"]
    check("覆盖对每一道都生效", _ov2[0].type == "detailed_answer", _ov2[0].type)
    check("不传 qtype 时行为不变",
          parse_source(src, book="测试录入", label="第1套")["questions"][0].type
          == "single_choice")
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

    # ── 多题录入：标题识别 + 逐题覆盖 ────────────────────────────────
    _hint = extract_source_hint(
        "\\title{2025年长沙市高三调研}\n\n" + src)
    check("从 \\title 认出出处", _hint["title"] == "2025年长沙市高三调研", _hint)
    check("从标题认出年份", _hint["year"] == 2025, _hint)
    _hint2 = extract_source_hint("2024-2025学年 某市高三一模\n" + src)
    check("没写 \\title 时看前几行纯文本",
          _hint2["title"].startswith("2024-2025学年"), _hint2)
    check("学年区间取考试年（后一个）", _hint2["year"] == 2025, _hint2)

    _ovs = parse_source(src, book="测试录入", label="第1套", items=[
        {"block": 0, "source_no": "7", "points": ["1.1.1"],
         "difficulty": "难题", "qtype": "multi_choice", "point_source": "llm"},
        {"block": 1, "source_no": "8", "points": [], "difficulty": "简单题"},
    ])
    _a, _b = _ovs["questions"]
    check("逐题覆盖：题号", (_a.meta.get("source_no"), _b.meta.get("source_no"))
          == ("7", "8"), str((_a.meta, _b.meta)))
    check("逐题覆盖：考点与来源", _a.points == ["1.1.1"]
          and _a.meta.get("point_source") == "llm", str(_a.meta))
    check("逐题覆盖：难度", _a.difficulty == "难题" and _b.difficulty == "简单题",
          str((_a.meta, _b.meta)))
    check("逐题覆盖：题型", _a.type == "multi_choice", _a.type)
    check("逐题明确清空考点", _b.points == [] and not _b.meta.get("point_source"),
          str(_b.meta))
    # 逐题空 label/year 必须沿用全局——多题界面单卷时每张卡都会带空串。
    _ov_global = parse_source(
        src, book="测试录入", label="江苏南京中华中学10月质量检测",
        region="江苏", year=2026,
        items=[{"block": 0, "label": "", "year": ""},
               {"block": 1, "label": "", "year": ""}])
    _g0, _g1 = _ov_global["questions"]
    check("逐题空 label 沿用全局出处",
          _g0.meta.get("source_label") == "江苏南京中华中学10月质量检测"
          and _g1.meta.get("source_label") == "江苏南京中华中学10月质量检测",
          str([_g0.meta.get("source_label"), _g1.meta.get("source_label")]))
    check("逐题空 year 沿用全局年份",
          _g0.meta.get("year") == 2026 and _g1.meta.get("year") == 2026,
          str([_g0.meta.get("year"), _g1.meta.get("year")]))
    check("逐题空 label 不破坏 key",
          "江苏南京中华中学10月质量检测" in _g0.key, _g0.key)

    check("blocks 与题目一一对应", _ovs["blocks"] == [0, 1], str(_ovs["blocks"]))

    # ── 补旧题：只补空考点/空难度，不碰正文 ──────────────────────
    _old = Question(key="补/旧#1", type="single_choice", stem="题干",
                    answer="A", solution="解析")
    _new = Question(key="补/新#1", type="single_choice", stem="题干",
                    answer="A", solution="解析", points=["8.1.2"],
                    meta={"difficulty": "简单题"})
    _bp = backfill_plan(_old, _new)
    check("补旧题补空考点", _bp.get("points") == ["8.1.2"], str(_bp))
    check("补旧题补空难度", _bp.get("difficulty") == "简单题", str(_bp))
    check("补旧题不动正文", "answer" not in _bp and "solution" not in _bp, str(_bp))
    _old2 = Question(key="补/旧#2", type="single_choice", stem="题干",
                     answer="A", solution="解析", points=["1.1.1"],
                     meta={"difficulty": "中档题"})
    check("旧题已有考点/难度时不补", backfill_plan(_old2, _new) == {},
          str(backfill_plan(_old2, _new)))

    # ── 多卷：每个题块归到前面最近的 \title ──────────────────────
    _multi = "\\title{2024年甲卷}\n" + src + "\\title{2025年乙卷}\n" + src
    _mt = extract_source_titles(_multi)
    check("多卷识别两个标题", [x["title"] for x in _mt] == ["2024年甲卷", "2025年乙卷"],
          str(_mt))
    _ms = parse_source(_multi, book="多卷测试", label="精选模拟题")
    check("多卷题块带回各自标题",
          [x.get("title") for x in _ms.get("block_titles", [])]
          == ["2024年甲卷", "2024年甲卷", "2025年乙卷", "2025年乙卷"],
          str(_ms.get("block_titles")))

    _pv5 = preview(src, book="测试录入", label="第1套", items=[
        {"block": 0, "source_no": "7", "points": ["1.1.1"],
         "difficulty": "难题", "qtype": "multi_choice"},
        {"block": 1, "source_no": "8", "points": [], "difficulty": "简单题"},
    ])
    check("干跑把 block 带回给界面",
          [it["block"] for it in _pv5["items"]] == [0, 1],
          str([it["block"] for it in _pv5["items"]]))
    check("干跑带逐题题号/考点/难度",
          _pv5["items"][0]["source_no"] == "7"
          and _pv5["items"][0]["points"] == ["1.1.1"]
          and _pv5["items"][0]["manual_difficulty"] == "难题",
          str(_pv5["items"][0]))
    check("干跑带标题提示", _pv5["source_hint"]["title"] == "", _pv5["source_hint"])

    _pv6 = preview("\\begin{problem}\n甲\n\\end{problem}", book="测试录入")
    check("缺解析的题被逐题标成 blocking",
          any("解析" in x for x in _pv6["items"][0]["blocking"]),
          str(_pv6["items"][0]["blocking"]))

    # 并入按**块下标**：出处在干跑后还能改，key 会变，块不会。
    _m1 = Question(key="a/b#1", type="single_choice")
    _m2 = Question(key="a/b#2", type="single_choice")
    _done = apply_merge_into([_m1, _m2], None, blocks=[3, 4],
                             merge_blocks={"4": "lib/x"})
    check("merge_blocks 按块下标并入",
          _m1.key == "a/b#1" and _m2.key == "lib/x" and len(_done) == 1,
          str([_m1.key, _m2.key, _done]))

    # 勾选：只落勾了的题；blocks 有空洞（前面某块解析失败）也不许错位。
    _s1 = Question(key="a#1", type="single_choice")
    _s2 = Question(key="a#2", type="single_choice")
    _picked, _pb = select_by_pick([_s1, _s2], [0, 2], [
        {"block": 0, "pick": True}, {"block": 2, "pick": False}])
    check("勾选：没勾的题不写库", [q.key for q in _picked] == ["a#1"]
          and _pb == [0], str(([q.key for q in _picked], _pb)))
    _picked2, _ = select_by_pick([_s1, _s2], [0, 2], None)
    check("勾选：没传 items 时保持全留（CLI/老界面不变）",
          len(_picked2) == 2, str(len(_picked2)))

    # ── 升级（merge_plan）────────────────────────────────────────────
    #
    # 铁律是**只升不降**：重录一遍不许把已有的解析/答案/考点抹掉。
    # 每一条都配一个反例，免得规则写反了还一路绿灯。
    def _q(sol="", ans="", pts=(), diff="", stem="题"):
        return Question(key="t/x", type="single_choice", stem=stem,
                        answer=ans, solution=sol, points=list(pts),
                        meta={"difficulty": diff} if diff else {})

    # ── 半成品闸：整栏只有「【缺：…】」占位 ＝ 没有解析 ────────────────
    #
    # 2026-11-02 实测：扫描端按规范用 `【缺：…】` 标原件就没有的内容，
    # 而闸门原来只看「非空」，南京一中卷 11 道选择题的占位符全绿进了库。
    # 反例也要守住：**个别符号**读不清、推导完整的题不许被误杀。
    check("整栏只有占位 → 判缺解析",
          any("只有「【缺" in e["reason"]
              for e in _incomplete_errors([_q(sol="【缺：原答案册未提供本题解析】", ans="B")])))
    check("两行占位叠在一起 → 仍判缺解析",
          bool(_incomplete_errors([_q(sol="【缺：解析】\n【缺：答案】", ans="B")])))
    check("推导完整、只缺一处符号 → 照收不误",
          not _incomplete_errors([_q(sol="又 $NC$【缺：符号不清】平面 $\\alpha$，故得证。", ans="B")]))
    check("解析为空 → 判缺解析", bool(_incomplete_errors([_q(sol="", ans="B")])))

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

    # 正例四：并集换了**主考点** ⇒ 派生难度得跟着走，
    #         否则库里留下「考点是根的分布、难度还写着集合」的错配
    pl = merge_plan(_q(pts=["1.1.1"]), _q(pts=["2.2.2"]))
    check("换主考点 → 难度按新主考点重算",
          pl.get("difficulty") == kb.difficulty_of("2.2.2")
          and pl.get("stars") == kb.stars_of("2.2.2"), str(pl))

    # 反例五：难度是人手填的（和它自己主考点对不上就是填的）→ 那是判断，不覆盖
    pl = merge_plan(_q(pts=["1.1.1"], diff="难题"), _q(pts=["2.2.2"]))
    check("人填的难度不覆盖", "difficulty" not in pl, str(pl))

    # 答案不同：以新的为准，但旧值要留痕
    pl = merge_plan(_q(ans="A"), _q(ans="B"))
    check("答案不同 → 用新的", pl.get("answer") == "B", str(pl))
    check("答案旧值留痕", pl.get("answer_prev") == "A", str(pl))

    # 完全一样 → 没有可升的，按重复跳过
    check("完全一样 → 空计划", merge_plan(_q(ans="A", pts=["1.1.1"]),
                                          _q(ans="A", pts=["1.1.1"])) == {})
    check("旧的更全 → 空计划", merge_plan(_q(sol="有", ans="A", pts=["1", "2"]),
                                          _q(sol="", ans="", pts=[])) == {})

    # ── 结构自洽闸（P0）：字段之间对不上，整批拒收 ──
    print("  ── 结构闸 ──")

    def _mk(**kw):
        base = dict(key="t/gate", type="single_choice",
                    stem=r"$1+1=$\paren[B]",
                    options=[Option("A", "$1$"), Option("B", "$2$")],
                    answer="B", solution="由 $1+1=2$ 得。", points=["1.1.1"])
        base.update(kw)
        return Question(**base)

    check("干净题放行", not _structure_errors([_mk()]))
    check("答案与作答位不一致 → 拦", bool(_structure_errors([_mk(answer="A")])))
    check("答案抄整条题干 → 拦", bool(_structure_errors([_mk(answer=_mk().stem)])))
    check("答案混进「答案：」标签 → 拦", bool(_structure_errors([_mk(answer="答案：B")])))
    check("解析抄整条题干 → 拦", bool(_structure_errors([_mk(solution=_mk().stem)])))
    check("题干混进卷首说明 → 拦",
          bool(_structure_errors([_mk(
              stem=r"$1+1=$\paren[B]" "\n"
                   "四、解答题：本题共 5 小题，共 77 分。")])))
    check("两个选项文字相同 → 拦",
          bool(_structure_errors([_mk(options=[Option("A", "$1$"),
                                                Option("B", "$1$")])])))
    check("填空答案与槽不一致 → 拦",
          bool(_structure_errors([_mk(type="fill_in_blank", options=[],
                                      stem=r"$1+1=$\fillin[2]。", answer="3")])))
    check("单选三个答案（problems）→ 拦",
          bool(_structure_errors([_mk(answer="AB")])))
    check("整组图片选项（文字全空）放行",
          not _structure_errors([_mk(options=[Option("A", ""), Option("B", "")])]))
    check("只有一个选项空 → 拦",
          bool(_structure_errors([_mk(options=[Option("A", ""),
                                                Option("B", "$2$")])])))

    print("ingest 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
