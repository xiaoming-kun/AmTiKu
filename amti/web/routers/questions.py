"""题目列表 / 详情 / 改标签 / 批量 / 补解析 / 改源码路由。

题目编辑是写路径最集中的一组：单题热路径只碰目标卷，批量改标签碰命中卷，
改出处/key 才退回整库。列表读模型/缓存 helper 在 `amti.web.core`。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from amti import content_store
from amti import fts as fulltext
from amti import knowledge
from amti import latex_blocks as lb
from amti import readmodel
from amti.query_syntax import parse as parse_query
from amti.recall import recall as _recall
from amti import review as review_mod
from amti import store
from amti.logutil import get_logger
from amti.paths import ROOT
from amti.render_tex import question_to_tex
from amti.schema import QTYPE_LABEL
from amti.web.core import (
    USAGE_PATH, _READMODEL_FLAGS, _brief_cached, _brief_cached_lite,
    _ensure_readmodel, _point_stage, _readmodel_page, _rm_apply, _seq_of,
    _stage_set, _usage, _usage_lock,
)
from amti.web.present import brief as _brief
from amti.web.present import stage_of as _stage_of
from amti.web.query import QuestionFilter
from amti.web.query import csv_set as _csv_set
from amti.web.query import source_of as _source_of
from amti.web.query import tag_ids_matching as _tag_ids_matching
from amti.web.retry import retry_on_concurrent

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["questions"])


def _load_question(key: str):
    r"""详情 / 改源码读一道题：**先查内容库**，没建好或没命中再回退 `store.find()`。

    内容库是派生数据（见 `amti/content_store.py`）：命中时约 1–3ms；
    回退路径也已经从整库解析改成“定位卷 + 只解析那一卷”，约 90ms。
    两条路都返回新解析的 Question，调用方可以放心改。
    """
    return content_store.get(key) or store.find(key)


class QuestionBrief(BaseModel):
    """列表/详情的精简题目契约。

    只钉住前端真正依赖的字段；`blocks`/`meta`/`flags` 仍是动态 dict
    （块级 IR 结构由 `present.brief` 定义，不在这里复制一份）。
    `extra="allow"` 让后续新增字段不被 response_model 静默裁掉。
    """
    model_config = {"extra": "allow"}
    key: str
    type: str = ""
    type_label: str = ""
    stem: str = ""
    options: list[dict] = []
    answer: str = ""
    solution: str = ""
    blocks: dict = {}
    points: list[str] = []
    difficulty: str = ""
    stars: int = 0
    point_titles: list[str] = []
    meta: dict = {}
    kind: str = ""
    hash: str = ""
    missing: list[str] = []
    problems: list[str] = []
    figures: list[str] = []
    flags: dict = {}
    review: dict | None = None
    seq: int = 0
    used: int = 0
    lite: bool = False


class QuestionListResponse(BaseModel):
    total: int
    items: list[QuestionBrief]
    #: 检索召回模式："" / fts / math。前端可据此显示“公式检索”提示。
    search_mode: str = ""
    #: 公式查询归一化后的样子（如 `cosb=3/4`），用于界面提示。
    search_normalized: str = ""


class QuestionDetailResponse(QuestionBrief):
    tex: str = ""




@router.get("/questions", response_model=QuestionListResponse)
def list_questions(
    q: str = "", type: str = "", kind: str = "",
    stage: str = "",          # 学段：primary/junior/senior，逗号分隔
    point: str = "",          # 考点 id，逗号分隔，命中任一即可
    difficulty: str = "",     # 难度，逗号分隔
    year: str = "",           # 年份，逗号分隔
    source: str = "",         # 卷别，逗号分隔
    region: str = "",         # 地区（meta.region），逗号分隔
    region_scope: str = "",   # single/multi/unknown/book
    paper_state: str = "",    # complete/partial
    star_state: str = "",     # rated/unrated
    quality: str = "",        # dup/lowres
    # 考点标注来源：`无` = 没记来源（早期批量录入），其余按 meta.point_source
    # 精确匹配（llm/human/manual/agent…）。题库体检的「无标签来源」点进来用它。
    point_source: str = "",
    # 答案来源：human / workbuddy / legacy（2026-11-03 回填后每道都有）
    answer_source: str = "",
    # 复核：yes/no — **有效审阅状态**（pending/stale 算 no）
    reviewed: str = "",
    # 审阅状态：pending / approved / needs_fix / flagged / stale，逗号分隔
    review_status: str = "",
    has: str = "",            # 逗号分隔：答案,解析,图,标签 → 只列**有**的
    missing: str = "",        # 逗号分隔：只列**缺**的
    sort: str = "",           # "" 默认（无关键词时原序；有关键词时相关度）
                              # / raw 强制原序 / new 新录入 / old 旧录入
                              # / solved 刚解出的 / year 年份新→旧 / year2 年份旧→新
    keys: str = "",           # 逗号分隔的题号 → 只要这些，且**按给定顺序**返回
    # 后端审查报告 Important #1：原本没有上界，而前端就在传 limit=5000。
    # limit=999999 会让服务端构造 17k 条 _brief（每条都要把 LaTeX 解析成
    # 块 IR，纯 CPU），足以让服务卡住几十秒。
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    # 默认**瘦身**：列表只带题干块 IR（答案/解析留给详情页）。
    # 全量校验脚本（`web/check.mjs`）需要答案/解析的块 IR —— 它显式传 lite=0，
    # 并且**分页**取，所以既拿到全量又不会一次压垮服务。
    lite: bool = True,
    # 内部开关：0 = 强制旧路径（测试/读模型回退用）
    rm: bool = True,
) -> dict:
    # 列表是打开应用的第一个请求：顺手让内容库在后台建起来（非阻塞）。
    # 这样用户点开第一道题时，详情多半已经命中 1–3ms 的主键查询。
    content_store.ensure()
    # 搜索框语法（考点:三角 年份:2024 ... -导数）在**列表与组卷共用**；
    # 显式筛选参数优先于语法字段，避免两个入口互相覆盖。
    pq = parse_query(q)
    kw = pq.keyword
    rec = _recall(kw) if kw else None
    cands = frozenset(rec["keys"]) if rec and rec["keys"] else None
    qtype = type or pq.type
    difficulty_v = difficulty or pq.difficulty
    year_v = year or pq.year
    source_v = source or pq.source
    region_v = region or pq.region
    point_ids = set(_csv_set(point))
    if pq.point and not point:
        for part in _csv_set(pq.point):
            got = _tag_ids_matching(part)
            if got:
                point_ids |= got
            else:
                # 语法写了考点但解析不到：必须是 0 结果，不能退化成“不筛”。
                point_ids.add("__none__")
    stage_set = _stage_set(stage)
    # 筛选口径**只此一份**，见 amti/web/query.py。列表与组卷共用它。
    flt = QuestionFilter(
        qtype=qtype, kind=kind,
        points=frozenset(point_ids),
        difficulties=_csv_set(difficulty_v),
        years=_csv_set(year_v),
        sources=_csv_set(source_v),
        scopes=_csv_set(region_scope),
        regions=_csv_set(region_v),
        paper_states=_csv_set(paper_state),
        star_states=_csv_set(star_state),
        qualities=_csv_set(quality),
        point_source=point_source.strip(),
        answer_sources=_csv_set(answer_source),
        reviewed=reviewed.strip(),
        review_status=_csv_set(review_status),
        has=_csv_set(has),
        missing=_csv_set(missing),
        keyword=kw,
        tag_ids=frozenset(_tag_ids_matching(kw) if kw else ()),
        deep_keyword=True,
        candidates=cands,
        candidate_only=bool(rec and rec["mode"] in ("math", "mixed") and cands),
        exclude_terms=pq.exclude,
    )

    key_list = [x.strip() for x in keys.split(",") if x.strip()]
    # 无关键词、无指定题号 → 元数据读模型直接 SQL 筛选/排序/分页。
    # 没有就绪时回退到下面的 Python 路径，并在后台重建。
    # `has/missing` 含读模型不认识的 flag（小问/存疑）时也必须回退：
    # 否则 SQL 里没有这个条件，筛选会被静默忽略，和组卷的池子对不上。
    use_readmodel = (
        rm and not kw and not key_list and not pq.exclude and not region_v
        and flt.has <= _READMODEL_FLAGS and flt.missing <= _READMODEL_FLAGS
    )
    if use_readmodel:
        rm_page = _readmodel_page(
            limit=limit, offset=offset, sort=sort, lite=lite,
            stage=stage_set,
            types=[flt.qtype] if flt.qtype else [],
            kinds=[flt.kind] if flt.kind else [],
            points=set(flt.points), diffs=set(flt.difficulties),
            years=set(flt.years), sources=set(flt.sources),
            scopes=set(flt.scopes), paper_states=set(flt.paper_states),
            star_states=set(flt.star_states), qualities=set(flt.qualities),
            point_source=flt.point_source,
            answer_sources=set(flt.answer_sources),
            reviewed=flt.reviewed, review_status=set(flt.review_status),
            has=set(flt.has), missing=set(flt.missing),
        )
        if rm_page is not None:
            return rm_page

    # **录入顺序 = 文件里的追加顺序。**
    # `store.append` 只追加，所以遍历顺序天然就是「先录的在前」。
    # 不需要额外的入库时间戳，也不需要改数据。
    rows = list(store.load_cached())

    # 召回（中文 FTS / 公式内容库）只负责缩候选；命中口径仍由
    # `QuestionFilter` 统一判断。公式查询没有原文子串可验，所以
    # `candidate_only=True`：候选集就是命中集。
    fts_rank: dict[str, int] = {}
    if rec and rec["keys"]:
        fts_rank = rec["ranks"]
        rows = [q for q in rows if q.key in rec["keys"]]

    # **按题号取题**：`keys` 一旦给了就只看这些题，并且**保持给定顺序**。
    # 存档的卷子/合集只存题号（`amti/papers.py`），前端要把它重新摊成
    # 可编辑的题目列表，就得有这么一条"按题号还原"的路。
    # 顺序用给定顺序是**有意的**——卷子里的题目次序是内容的一部分。
    if key_list:
        _by_key = {it.key: it for it in rows}
        rows = [_by_key[k] for k in key_list if k in _by_key]

    # ⚠️ **先筛、先排、先切片，最后才渲染。**
    #
    # 老写法对**全部 17,554 道题**都跑一遍 `_brief`（块级 IR 解析，
    # 一道几毫秒），再切片返回 200 条——只要 1 道题也要 3 秒。
    # 现在筛选阶段只碰字符串和布尔值，`_brief` 只对**真正要返回的那一页**跑。
    keep: list = []
    # 回退路径也要把学段表算一次：`_stage_of(item)` 每题都会进
    # knowledge_map.tree()，3 万道就是几十秒。
    stage_map = _point_stage()
    for item in rows:
        if stage_set and _stage_of(item, stage_map) not in stage_set:
            continue
        if not flt.matches(item):
            continue
        keep.append(item)

    # 有关键词时默认按**相关度**排（仍保留使用频次做同分次序）；
    # 用户明确选了别的排序（年份/难度/录入顺序）就尊重他。
    #
    # 排序分两层：
    #   ① SQLite FTS5 给候选召回的 bm25 名次（中文 2 字也能命中，见 amti/fts.py）；
    #   ② 同一个名次里再用 `search.score` 按“题干 > 考点 > 答案 > 解析”细排。
    # 索引没建好/查询里有 FTS 不认的符号时，`fts_rank` 为空，自动退回纯打分。
    if kw and sort in ("", "used"):
        from amti import search as _se
        u = _usage()
        keep.sort(key=lambda q: (fts_rank.get(q.key, 10 ** 9),
                                 -_se.score(q, kw, _source_of(q)),
                                 -u.get(q.key, 0), q.key))
    elif sort == "risk":
        keep.sort(key=lambda q: (-review_mod.info(q)["risk"], q.key))
    elif sort == "new":
        keep.reverse()
    elif sort in ("diff", "diff2"):
        # 按难度排。`diff` 是**从易到难**（最常见的诉求：
        # 「我要某个知识点的题，从简单到难排一遍」），`diff2` 反过来。
        from amti.generate import DIFF_ORDER as _D
        keep.sort(key=lambda q: _D.get(q.difficulty, 9),
                  reverse=(sort == "diff2"))
    elif sort == "used":
        # **按使用频次倒序**——老师导出过多次的题（高频题/经典题）
        # 排前面，打开题库默认就能看到。没用过的按原序跟在后面。
        u = _usage()
        keep.sort(key=lambda q: u.get(q.key, 0), reverse=True)
    elif sort == "solved":
        # **按求解时间倒序**——求解任务的产出顺序和录入顺序不一样，
        # 想看"刚解出来的几道"就得按 `solved_at` 排。
        # 没解过的排在最后（空字符串倒序时天然靠后）。
        keep.sort(key=lambda q: (q.meta or {}).get("solved_at") or "", reverse=True)
    elif sort in ("year", "year2"):
        # **按年份排**。`year` = 新→旧，`year2` = 旧→新。
        # 没写年份的题**两档都排在最后**（不能因为 0 最小就在"旧→新"里
        # 跑到最前面，那会让一批无年份的题把开头占满）。
        def _y(q) -> int:
            v = (q.meta or {}).get("year")
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0
        keep.sort(key=lambda q: (_y(q) == 0, -_y(q) if sort == "year" else _y(q)))

    total = len(keep)
    page = keep[offset:offset + limit]
    out = []
    usage = _usage()
    for item in page:
        b = _brief_cached_lite(item) if lite else _brief_cached(item)
        b["seq"] = _seq_of(item.key)
        b["used"] = usage.get(item.key, 0)
        out.append(b)
    return {"total": total, "items": out,
            "search_mode": rec["mode"] if rec else "",
            "search_normalized": (rec["normalized"] if rec else "")}


@router.get("/questions/{key:path}/duplicates")
def duplicate_questions(key: str) -> dict:
    r"""重复题：同指纹 / 同 duplicate_group / dup_of 的题。

    **只提示，不合并**；没有发现时 `n=0, items=[]`，不编造。
    """
    from amti import duplicates as _dups
    k = urllib.parse.unquote(key)
    q = _load_question(k)
    if q is None:
        raise HTTPException(404, f"没有这道题：{key}")
    rec = _dups.info(q.key)
    if not rec:
        return {"key": q.key, "group": "", "n": 0, "items": []}
    items = [_brief(it) for it in _dups.members(q.key) if it.key != q.key]
    return {"key": q.key, "group": rec["group"], "n": rec["n"],
            "items": items}


@router.get("/questions/{key:path}/similar")
def similar_questions(key: str,
                      limit: Annotated[int, Query(ge=1, le=30)] = 8) -> dict:
    r"""相似题：同考点 / 同公式结构 / 同题型。

    索引是派生的（`amti/similar.py`）；内容库没建好时返回 `ready=false`，
    不拿空结果冒充“没有相似题”。
    """
    from amti import similar as _similar
    k = urllib.parse.unquote(key)
    q = _load_question(k)
    if q is None:
        raise HTTPException(404, f"没有这道题：{key}")
    hits, ready = _similar.find(q, limit=limit)
    items = []
    for hit_key, score in hits:
        it = _load_question(hit_key)
        if it is None:
            continue
        b = _brief(it)
        b["similarity"] = round(score, 4)
        items.append(b)
    return {"key": q.key, "items": items, "ready": ready}


@router.get("/questions/{key:path}/answer")
def get_question_answer(key: str) -> dict:
    r"""只取答案的块 IR（列表「显示答案」用）。

    列表接口为了性能不带答案/解析块；公式答案不能在前端解析 LaTeX，
    所以单独给一个轻量入口。只解析目标卷，不读全库。
    """
    q = _load_question(urllib.parse.unquote(key))
    if q is None:
        raise HTTPException(404, f"没有这道题：{key}")
    return {"key": q.key, "answer": q.answer,
            "blocks": lb.parse_blocks(q.answer)}


@router.get("/questions/{key:path}", response_model=QuestionDetailResponse)
def get_question(key: str) -> dict:
    k = urllib.parse.unquote(key)
    q = _load_question(k)
    if not q:
        raise HTTPException(404, f"没有这道题：{key}")
    d = _brief(q)
    d["tex"] = question_to_tex(q)
    d["used"] = _usage().get(q.key, 0)
    return d


# ── 改答案时的格式处理 ────────────────────────────────────────────────
#
# 用户要的是「看到解析但没答案，随手补进去」。随手写的输入五花八门：
# 全角字母、小写、带括号、多打了顿号……所以**统一在这一层规整**，
# 规整不了就明确报错，绝不把半成品写进库。

# 题干里的**作答位置**。有两种写法，比对时都要抹平：
#   · 规范化之后的 `\paren[B]` / `\fillin[$x$]`
#   · 规范化之前的裸括号 `（ ）` / `（\quad）` / `(\qquad)`
#
# 只认前者的话，一道题干写 `（ ）` 的题在补答案时会被护栏判成
# "题干被改了"而拒绝——可那本来就是同一个位置，只是换了写法。
_SLOT = re.compile(
    # `\fillin` 有三种形态，**都要吃掉**：
    #   `\fillin{}`        空的（规范化前）
    #   `\fillin[$18$]`    填好的（规范化后）
    #   `\fillin`          光杆的
    # 早先只认中间那种，于是 `\fillin{}` 被替成占位符后**还剩一个 `{}`**，
    # 而填好的那个替完就没了 `{}`——两边一比就"不一样"，
    # 改答案时被误判成"动了题干"而拒绝。实测踩过。
    r"\\(paren|fillin)\s*(\[[^\]]*\])?\s*(\{[^{}]*\})?"
    r"|[（(]\s*(?:\\quad|\\qquad)?\s*[）)]")


def _content_outside_answer(q) -> tuple:
    r"""**除答案与作答括号之外**的内容快照。

    改答案会正当地改到两处：`answer` 字段，和题干里的 `\paren[…]`／`fillin[…]`。
    除此之外——题干正文、选项、解析、配图——**一个字节都不许变**。
    改完拿这个快照比对，对不上就说明改答案的路上动了别的东西。
    """
    # 两种写法都替换成同一个占位符，并**去掉所有空白**——
    # 我们关心的是"正文有没有被动过"，不是排版空白或作答位置用哪种写法。
    stem = re.sub(r"\s+", "", _SLOT.sub("§", q.stem or ""))
    return (stem, q.solution or "",
            tuple((o.label, o.text) for o in q.options),
            tuple(f.id for f in (q.figures or [])))


def _clean_answer_input(q, raw) -> str:
    r"""把界面上随手写的答案**规整成规范形态**；规整不了就报 400。

    按题型分别处理（这是"注意格式问题"的核心）：

    | 题型 | 收什么 | 规整成 |
    |---|---|---|
    | 单选 | `b` / `Ｂ` / `B、` / `选B` | `B`，**只能一个** |
    | 多选 | `abd` / `A,B,D` / `ABD` | `ABD`，排序去重，2–4 个 |
    | 填空 | 任意结果，如 `$\frac{1}{2}$`、`②③` | 去空白，检查 `$` 配平 |
    | 解答 | 结论文字（一般留空，结论写解析里） | 原样，同样检查 `$` 配平 |

    **不猜**：字母超范围（比如 `E`）、单选题给了两个字母、`$` 不配平——
    一律报错说清楚，而不是硬塞一个进去。
    """
    txt = str(raw or "").strip()
    if not txt:
        return ""                      # 允许清空（等于"这题确实没答案"）

    if q.type in ("single_choice", "multi_choice"):
        # 全角字母先转半角，再去掉所有非 A–D 的字符
        t = "".join(chr(ord(c) - 0xFEE0) if "Ａ" <= c <= "Ｚ" else c for c in txt)
        letters = sorted(set(re.findall(r"[A-Da-d]", t.upper())))
        if not letters:
            raise HTTPException(400, "选择题的答案要写选项字母，比如 B 或 ABD；收到 %r" % txt)
        # 有 E 之后的字母说明写错了（本库选项只有 A–D）
        stray = sorted(set(re.findall(r"[E-Za-z]", t.upper())))
        if stray:
            raise HTTPException(400, "选项只有 A–D，收到 %s" % "、".join(stray))
        if q.type == "single_choice" and len(letters) != 1:
            raise HTTPException(
                400, "这是**单选题**，只能填一个字母；收到 %s。"
                     "如果这题本来就该多选，请先把题型改成多选。" % "".join(letters))
        if q.type == "multi_choice" and len(letters) < 2:
            raise HTTPException(400, "这是**多选题**，至少要两个字母；收到 %s" % "".join(letters))
        return "".join(letters)

    # 填空/解答：结果本身可以是任意 LaTeX，但有两个硬要求
    if txt.count("$") % 2:
        raise HTTPException(400, "答案里的 `$` 个数是奇数（%d 个），数学模式没闭合" % txt.count("$"))
    if _SLOT.search(txt):
        raise HTTPException(400, "答案里不能写 `\\paren`／`\\fillin`——那是题干里的作答位置")
    return txt


# ── 改题型 ────────────────────────────────────────────────────────────
#
# 用户会遇到：**题目其实是多选，却被标成了单选**（选项 B、C、D 都对）。
# 题面里那句「则下列说法正确的是」根本看不出单选还是多选，判错很正常。
#
# 但改题型会**牵动答案的合法性**：
#   单选 → 恰好 1 个字母      多选 → 至少 2 个字母
# 所以这里不许"只改题型"了事——要么现有的答案对新题型也合法，
# 要么在**同一次请求**里把答案一起改好。**绝不悄悄把答案清掉。**
#
# 目前只放开**单选 ↔ 多选**：两者用同一个作答位置 `\paren[…]`，
# 换过去不影响题干。换成填空/解答要动选项和作答位置，那是另一回事，
# 会把题目改残，所以明确拒绝并说明原因。

_CHOICE_TYPES = ("single_choice", "multi_choice")


def _convert_type(q, new_type: str) -> str:
    r"""改题型。返回一句说明；不合法就抛 400。"""
    from amti.schema import QTYPE_LABEL
    if new_type not in QTYPE_LABEL:
        raise HTTPException(400, "没有这个题型：%s（可选：%s）"
                            % (new_type, "、".join(QTYPE_LABEL)))
    old = q.type
    if new_type == old:
        return ""
    if old not in _CHOICE_TYPES or new_type not in _CHOICE_TYPES:
        raise HTTPException(400, (
            "目前只支持**单选 ↔ 多选**互改。%s → %s 要动选项和作答位置，"
            "改下去容易把题目改残——请改题目源文件后重新录入。"
            % (QTYPE_LABEL.get(old, old), QTYPE_LABEL[new_type])))
    # 选择题得有选项，否则改完就是一道空壳
    if len(q.options) < 2:
        raise HTTPException(400, "这道题只有 %d 个选项，不能算选择题" % len(q.options))
    q.type = new_type
    return "%s → %s" % (QTYPE_LABEL[old], QTYPE_LABEL[new_type])


def _audit_tag_change(q, *, before: str, fields) -> None:
    r"""把「界面改标签」记一份档。

    只记标签变化，不记正文 —— 正文根本走不到这里（指纹校验会拦住）。
    记档失败**不阻断**修改，但必须留下日志：审查报告 Important #3 指出，
    原本全项目 0 处 logging，"改了但没记录"这种事没人知道。
    """
    from amti.audit import CHANGE_DIR
    try:
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面改标签.md" % time.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面改标签\n\n"
            "- 时间：%s\n- 题目：`%s`\n- 改动：%s\n"
            "- 内容指纹：%s → %s（**没变**，改的只是标签）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), q.key,
               "、".join(sorted(fields)), before, q.content_hash()),
            encoding="utf-8")
    except Exception:
        log.warning("标签变更记档失败（修改已生效）：%s", q.key, exc_info=True)


#: 存档里存的是**题目 key 字符串**（`试卷/存档.json` 的 `keys`、讲义存档的 blocks）。
#: 改 key 不跟着改，那几份卷子/讲义里这一题就**静默消失**——打开只看出来"少一道"，
#: 不报错，也没人知道为什么。
#:
#: `数据/订正台账.json` 也存 key（`patches[].key`、`retired[]`）。不迁的话，
#: 台账里多出一批死账，而 `fixups.run` 是「一条对不上就整批不执行」——
#: 1252 条待办全被卡住（`脚本/批量改出处.py` 把这一条列为必迁落点）。
_KEY_REF_FILES = ("试卷/存档.json", "讲义/讲义存档.json", "数据/订正台账.json",
                  "数据/专题/manifest.json")

#: 改名台账：`store.diff()` 读它，把「改了个名字」和「删一道 + 加一道」分开。
#: 不记的话，每改一次出处，顶栏的「删除」就红一次——那样的红灯很快就没人看了。
#: 路径**只有一处**（`store.RENAME_LEDGER`），这里只引用，别写第二份。


def _migrate_key_refs(old: str, new: str) -> list[str]:
    r"""把存档里引用的 `old` 换成 `new`。返回改到的文件（相对路径）。

    只做**整串替换**（连引号一起比），不解析结构：
    存档是给人看的 JSON，重排一遍会把 diff 弄得面目全非。
    改完**必须仍能 `json.loads`**，否则宁可不动——那说明替换改坏了文件。
    """
    a = json.dumps(old, ensure_ascii=False)
    b = json.dumps(new, ensure_ascii=False)
    hit: list[str] = []
    # `数据/专题/选题/*.json` 里存的是 add/remove/place 三类 key；
    # 不迁的话，改一次出处，高中讲义里那道题就悄悄消失。
    sel = ROOT / "数据" / "专题" / "选题"
    paths = [ROOT / rel for rel in _KEY_REF_FILES]
    if sel.is_dir():
        paths += sorted(sel.glob("*.json"))
    for p in paths:
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(ROOT))
        except ValueError:
            rel = str(p)
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if a not in t:
            continue
        t2 = t.replace(a, b)
        try:
            json.loads(t2)
        except ValueError:
            log.warning("改出处：%s 里替换后不是合法 JSON，跳过（引用会留在旧 key 上）", rel)
            continue
        try:
            p.write_text(t2, encoding="utf-8")
            hit.append(rel)
        except OSError:
            log.warning("改出处：写 %s 失败", rel, exc_info=True)
    return hit


def _migrate_usage(old: str, new: str) -> None:
    r"""改出处 = 改 key：把「被组过几次」也跟着迁到新 key。

    `数据/使用频次.json` 按 key 记次数。不迁的话，改一次出处这道题的
    「用过 N 次」就归零——默认排序按使用频次，用户会发现「我常用的题不见了」。

    **内存缓存必须一起改**：`_usage()` 只读一次盘，缓存里还是旧 key 的话，
    下次 `_usage_bump` 会把旧 key 写回文件，等于把迁移覆盖掉。
    """
    with _usage_lock:
        d = _usage()
        if old not in d:
            return
        n = d.pop(old)
        d[new] = d.get(new, 0) + n
        try:
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            USAGE_PATH.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True),
                                  encoding="utf-8")
        except OSError:
            log.warning("改出处：使用频次迁移写盘失败（改名已生效）", exc_info=True)
        else:
            readmodel.set_used({new: d.get(new, 0)})


def _migrate_meta_refs(qs, old: str, new: str) -> int:
    r"""把**别的题 meta 里指向旧 key 的引用**换成新 key。

    `dup_of`（和谁雷同）、`also_in`（还出现在哪）、`merged_keys`（合并过谁）
    存的是题目 key。改出处换了 key 而这里不换，查重提示/孪生题对账就会
    指向一道不存在的题（`semantic.py` 会报 `dup_of_dangling`）。
    返回改了几处。
    """
    n = 0
    for x in qs:
        m = x.meta if isinstance(getattr(x, "meta", None), dict) else {}
        if m.get("dup_of") == old:
            m["dup_of"] = new
            n += 1
        if m.get("merged_from") == old:
            m["merged_from"] = new
            n += 1
        for f in ("also_in", "merged_keys"):
            v = m.get(f)
            if isinstance(v, list) and old in v:
                m[f] = [new if z == old else z for z in v]
                n += 1
    return n


def _audit_key_rename(old: str, new: str) -> None:
    r"""记两笔：给程序读的台账 + 给人读的报告。**失败不阻断**。"""
    try:
        led = ROOT / store.RENAME_LEDGER
        led.parent.mkdir(parents=True, exist_ok=True)
        with led.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "from": old, "to": new}, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("改出处台账写入失败（改名已生效）：%s", old, exc_info=True)
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f2 = CHANGE_DIR / ("%s_界面改出处.md" % time.strftime("%Y%m%d_%H%M%S"))
        f2.write_text(
            "# 界面改出处\n\n- 时间：%s\n- 原 key：`%s`\n- 新 key：`%s`\n"
            "- 内容指纹：**没变**（改的只是出处）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), old, new), encoding="utf-8")
    except Exception:
        log.warning("改出处记档失败（改名已生效）：%s", old, exc_info=True)


def _apply_question_patch(q, body: dict, *, before: str,
                          content_before: tuple) -> None:
    r"""把白名单里的**非出处**字段应用到 q，并做正文/规范校验。

    单题 `patch_question` 有两条落盘路径：
      · 不带 `source`：`store.read_one()` + `store.write_one()` 只动一卷（热路径）；
      · 带 `source`：可能要改 key/跨卷引用，仍走整库 `load_for_update()`。
    两条路必须用**同一份**字段应用与校验逻辑，否则就会分叉；这个函数是那份逻辑。
    """
    if "points" in body:
        pts = [str(p).strip() for p in (body.get("points") or []) if str(p).strip()]
        bad = [p for p in pts if not knowledge.get(p)]
        if bad:
            raise HTTPException(400, "考点不存在：%s" % "、".join(bad))
        q.points = pts
        # 人工改过的标签，来源标成 human —— 以后一眼能看出哪些不是模型打的
        q.meta["point_source"] = "human"
    if "difficulty" in body:
        d = (body.get("difficulty") or "").strip()
        if d:
            q.meta["difficulty"] = d
        else:
            q.meta.pop("difficulty", None)      # 恢复成按主考点派生
    if "stars" in body:
        try:
            n = int(body["stars"])
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            q.meta["stars"] = n
        else:
            q.meta.pop("stars", None)


    type_note = ""
    if "type" in body:
        type_note = _convert_type(q, str(body.get("type") or "").strip())
        if type_note:
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    if "answer" in body:
        new_ans = _clean_answer_input(q, body.get("answer"))
        q.answer = new_ans
        q.meta["answer_source"] = "human"       # 人补的，和求解器写的分开记
        # **不要在这里写 reviewed_at**：改答案≠审过整道题。
        # 复核状态由 `/api/review/decision` 或详情页的“快速通过”单独写；
        # 正文一变，`reviewed_hash` 对不上，已有复核会自动失效（stale）。
        # **盖时间戳**：`store.diff()` 靠它把"界面补录"和"规则偷偷动数据"分开。
        # 不盖的话，你在界面上改一道答案，顶栏就报一次"⚠ 内容变化"——
        # 自己改的东西被当成异常，那这个报警很快就没人看了。
        q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
        # **格式问题就出在这一步**：答案要写进题干的 `\paren[…]`／`\fillin[…]`，
        # 否则卷面上不出现作答括号、答案也没地方显示。
        from amti import normalize as _norm
        _norm.normalize(q, _norm.ENTRY)

    # 改了题型但**没同时给答案**时，现有的答案必须对新题型也合法。
    # 否则会出现"单选题只剩一个字母却标成多选"这种自相矛盾的状态。
    if type_note and "answer" not in body and q.answer.strip():
        try:
            _clean_answer_input(q, q.answer)
        except HTTPException:
            q.type = "multi_choice" if q.type == "single_choice" else "single_choice"
            raise HTTPException(400, (
                "现在这个答案是 %r，改成%s后不合法。"
                "改题型时要**同时**把答案改好（比如把 B 改成 BD）。"
                % (q.answer, "多选题" if q.type == "single_choice" else "单选题")))

    if "reviewed" in body:
        # 详情页的快速通过/收回。语义是**一次审阅决定**，不是“改过”的副作用。
        review_mod.apply_decision(
            q, "approved" if body["reviewed"] else "pending",
            note="详情页快速通过" if body["reviewed"] else "",
            reviewer="界面")

    # 没改答案/题型时，指纹必须**一个字节都没变**（改标签不该动正文）
    if "answer" not in body and "type" not in body and q.content_hash() != before:
        raise HTTPException(500, "内容指纹变了——说明动到了正文，已拒绝")
    # 改答案时：除答案与作答括号之外，正文必须一个字节都没变
    if ("answer" in body or "type" in body) and _content_outside_answer(q) != content_before:
        raise HTTPException(500, "改答案时动到了题干正文/选项/解析，已拒绝")

    # **规范审查**：改完必须仍然合规，否则不存。
    # 答案写错格式（`$` 不配平、把 `\paren` 塞进答案里…）在这里被挡住。
    from amti import conform as _cf
    viol = _cf.run([q])
    if viol:
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (viol[0]["why"], viol[0]["check"], viol[0]["field"]))



@router.patch("/questions/{key:path}")
@retry_on_concurrent
def patch_question(key: str, body: dict) -> dict:
    r"""改标签：**考点**和**难度**。

    权威入口是 `store.rewrite_volume`（MIGRATE 级的那个），
    因为改标签必须落到主文件里才算数。安全性由指纹保证：

        内容指纹只覆盖 题干/选项/答案/解析/配图，
        **标签与元数据不在其中**（`schema.HASH_FIELDS`）。

    所以这个接口**改不动一道题的正文**——就算传了别的字段也白传。
    改完把新指纹回给前端，对不上就说明碰了不该碰的。

    请求体（字段都可选）：
        {"points": ["3.2.2","3.2.1"],   # 考点 id，第一条是主考点
         "difficulty": "难题",           # 空字符串 = 恢复成按主考点派生
         "stars": 3,
         "answer": "B",                  # **补答案**
         "type": "multi_choice",         # **改题型**（目前只放开 单选↔多选）
         "source": {"book": "…", "label": "…", "year": 2027,
                    "region": "…", "no": 22}}
                                         # **改出处**：改完 key 跟着改；
                                         # `no` 是题号（key 里 `#` 后面那截）
    """
    # ⚠️ **白名单：只有这几个字段能改，其余一律拒绝。**
    #
    # 界面上「考点」「难度」「出处」是标签，改它们是日常操作；
    # **题目正文（题干/选项/答案/解析/配图）一个字都不许从界面改**——
    # 那是数据，改它要走「改题目 → 重新录入」的正规路径，
    # 而且要过规范验证、查重、影响面这几关。
    #
    # 老写法是「只读认识的字段、其余静默忽略」——安全，但**不响**：
    # 有人想改题干，接口回 200，他会以为改成功了。
    # 现在直接 400 说清楚。
    ALLOWED = {"points", "difficulty", "stars", "answer", "type", "source",
               "reviewed"}
    unknown = set(body) - ALLOWED
    if unknown:
        raise HTTPException(400, (
            "只允许改 %s；收到 %s。"
            "题目正文（题干/选项/解析/配图）**不能从界面改**——"
            "要改请改题目源文件后重新录入。"
            "（**答案**可以改，见 `answer`。）"
            % ("、".join(sorted(ALLOWED)), "、".join(sorted(unknown)))))

    k = urllib.parse.unquote(key)
    # **热路径**：不改出处就不会改 key，不需要把 3 万道题全读进内存。
    # read_one 只解析目标卷；write_one 在写锁内核对全库签名/内容指纹，
    # 只重写那一卷。改答案/题型也走这里（正文变了但 key 不变）。
    if "source" not in body:
        one = store.read_one(k)
        if one is None:
            raise HTTPException(404, f"没有这道题：{k}")
        q, vol, sig, chunk = one
        before = q.content_hash()
        content_before = _content_outside_answer(q)
        _apply_question_patch(q, body, before=before, content_before=content_before)
        store.write_one(q, volume=vol, expect_hash=before, expect_sig=sig,
                        chunk=chunk)
        fulltext.apply([k], {q.key: q})
        _rm_apply([k], sig, {q.key: q})
        _audit_tag_change(q, before=before, fields=body)
        d = _brief(q)
        d["tex"] = question_to_tex(q)
        return d

    qs, _sig = store.load_for_update()
    q = next((x for x in qs if x.key == k), None)
    if q is None:
        raise HTTPException(404, f"没有这道题：{k}")

    before = q.content_hash()
    # 改答案会**有意**改到正文（答案在指纹里，题干里的作答括号也要跟着变），
    # 所以单独记一份"**除答案和作答括号之外**"的内容快照。
    # 改完拿它比对：只要题干正文、选项、解析、配图有一个字节变了，就拒绝。
    content_before = _content_outside_answer(q)
    # ── 出处（书 / 卷名 / 年份 / 地区）──────────────────────────────
    #
    # 用户的要求：「录入时填错了出处，录完就改不回来了」。
    # 难点不在改 meta —— 在 **key**：`书/卷名#序号` 是自然键，改出处就得改名。
    # 改名要连带三件事，缺一件就是静默损坏：
    #   ① 查重（新 key 不能已存在）
    #   ② 迁引用（`试卷/存档.json`、`讲义/讲义存档.json` 里存的是 key 字符串）
    #   ③ 记账（`数据/改出处.jsonl`）——`store.diff()` 靠它把"改名"和
    #      "一道题被删、另一道题被加"区分开；不记的话顶栏每改一次出处就红一次
    renamed_from = ""
    if "source" in body:
        src = body.get("source")
        if not isinstance(src, dict):
            raise HTTPException(400, "source 要给对象：{book, label, year, region, no}")
        unknown = set(src) - {"book", "label", "year", "region", "no"}
        if unknown:
            raise HTTPException(400, "source 里不认识的字段：%s"
                                % "、".join(sorted(unknown)))
        book = str(src.get("book", (q.meta or {}).get("book", "")) or "").strip()
        label = str(src.get("label", (q.meta or {}).get("source_label", "")) or "").strip()
        if not book or not label:
            raise HTTPException(400, "来源（书）和出处（卷名）都不能空")
        # key 是 `书/卷名#序号`，这三样里出现分隔符会把 key 结构弄坏
        for bad in ("/", "#"):
            if bad in book or bad in label:
                raise HTTPException(400, "来源/出处里不能有 `%s`（key 的分隔符）" % bad)
        # **题号**（key 里 `#` 后面那截）也能和出处一起改：出处录错时，
        # 「第几题」往往跟着错。统一成不带前导零的正整数——库里的 key
        # 尾串统一成不带前导零的正整数，排序与比较才可靠。
        tail = key.rsplit("#", 1)[-1] if "#" in key else "1"
        head = key.rsplit("#", 1)[0] if "#" in key else key
        new_tail = tail
        if "no" in src:
            raw_no = src.get("no")
            new_tail = str(raw_no).strip()
            if not new_tail.isdigit() or int(new_tail) < 1:
                raise HTTPException(400, "题号要是正整数，收到 %r" % (raw_no,))
            new_tail = str(int(new_tail))
        # ⚠️ **改名判据要拿改名前的书/卷名**：下面 q.meta 会被覆盖，
        # 覆盖之后再取等于拿新值跟旧 key 比——那永远不会同构，改名就静默失效。
        old_book = str((q.meta or {}).get("book", "") or "")
        old_label = str((q.meta or {}).get("source_label", "") or "")
        q.meta["book"] = book
        q.meta["source_label"] = label
        year = src.get("year", (q.meta or {}).get("year", ""))
        if str(year).strip():
            try:
                q.meta["year"] = int(str(year).strip())
            except ValueError:
                raise HTTPException(400, "年份要是整数，收到 %r" % (year,))
        else:
            q.meta.pop("year", None)
        region = str(src.get("region", (q.meta or {}).get("region", "")) or "").strip()
        if region:
            q.meta["region"] = region
        else:
            q.meta.pop("region", None)

        # **只有 key 本来就是 `书/卷名#号` 拼出来的，才跟着改名。**
        # 反例（真踩过）：`高考真题汇编/2024/新高考I卷#1` 的出处是
        # `2024年新高考I卷`——key 里多一层年份目录，和出处**不同构**。
        # 按 meta 重拼 key 会把它改成 `书/2024年新高考I卷#1`，等于
        # 悄悄给这道题换了身份：基线上的旧 key 变成"被删了"，
        # 组进卷子里的引用也跟着断。宁可只改标签，把 key 留着。
        #
        # 但**题号是用户明确改的**：不同构的 key 也要换掉 `#` 后面那截，
        # 否则界面上改了题号、卷子里还印旧号。目录（head）一个字不动。
        if head == "%s/%s" % (old_book, old_label):
            new_key = "%s/%s#%s" % (book, label, new_tail)
        else:
            new_key = key if new_tail == tail else "%s#%s" % (head, new_tail)
        if new_tail != tail:
            # 卷面/讲义印的「第 N 题」优先读 `meta.source_no`
            # （见 `render_tex.source_tag`）——只改 key 不改它，印出来还是旧题号。
            q.meta["source_no"] = new_tail
        if new_key != q.key:
            if any(x is not q and x.key == new_key for x in qs):
                raise HTTPException(409, "已经有这道题了：%s（出处不能重名，"
                                         "同一卷的多道题请用不同题号）" % new_key)
            renamed_from = q.key
            q.key = new_key
            # 改名是**有意动数据**：和别的"界面补录"一样盖时间戳，
            # 免得 `store.diff()` 把它报成"内容变化"
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    # 出处已处理完（可能改了 key/meta）；非出处字段与校验走同一份 helper。
    _apply_question_patch(q, body, before=before, content_before=content_before)

    # 改名的**跨题引用**也一起迁（`dup_of`/`also_in`/`merged_keys` 存的是
    # 别的题的 key）；必须在整库重写之前改，才会跟着落盘。
    if renamed_from:
        _migrate_meta_refs(qs, renamed_from, q.key)

    # ⚠️ 用 rewrite_all（**按 PER_VOLUME 重新分卷**），不要用 rewrite_volume(1,…)：
    # 后者会把所有卷的题都写进第 1 卷，而其它卷还在 → 整库重复。
    #
    # `based_on` 是乐观并发校验：读全库之后、写回之前若求解器/别的进程写了库，
    # 这次保存会被**拒绝**而不是把人家的写入覆盖掉。
    # ⚠️ **不要在这里 catch**：`@retry_on_concurrent` 靠捕获 `ConcurrentWrite`
    # 自动重跑一遍。在这里转成 HTTPException 的话装饰器永远接不到，
    # 「自动重试」形同虚设（复核时发现的）。
    _changed = [key, q.key] + ([renamed_from] if renamed_from else [])
    # 改名会改**别的题** meta 里的 dup_of/also_in/merged_keys；那些题可能在
    # 别的卷里。只写旧/新 key 会漏掉这些 meta 改动，必须整库写回。
    store.rewrite_all(qs, based_on=_sig,
                      changed_keys=(None if renamed_from
                                    else list(dict.fromkeys(_changed))))
    fulltext.apply(_changed, {q.key: q})
    _rm_apply(_changed, _sig, {q.key: q})

    # **记档**：标签是人工改的，要留痕（只记标签，不记正文）
    _audit_tag_change(q, before=before, fields=body)

    # 改名才有的三件事：存档里的引用跟着改、使用频次跟着迁、台账记一笔
    if renamed_from:
        moved = _migrate_key_refs(renamed_from, q.key)
        _migrate_usage(renamed_from, q.key)
        _audit_key_rename(renamed_from, q.key)
        log.info("改出处：%s → %s（引用已迁：%s）", renamed_from, q.key,
                 "、".join(moved) or "无")

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    if renamed_from:
        # 前端拿它把选中项/列表里那条旧 key 换掉（否则右栏会停在旧 key 上）
        d["renamed_from"] = renamed_from
    return d


class BatchTagBody(BaseModel):
    r"""批量改标签：列表里勾 N 道，一次改完、**一次写盘**。

    以前只能一道一道开详情改，16 道就是 16 次“读全库 + 写 6 卷”。
    这里只放开标签字段（考点/难度/星级/年份/地区/书/卷名），
    正文（题干/选项/解析/答案）仍然只能走单题详情或重新录入——
    批量接口不该成为绕过规范审查的后门。
    """
    model_config = {"extra": "forbid"}     # 传 stem/solution 进来直接 422，不静默忽略
    keys: list[str]
    points: list[str] | None = None        # 按 point_mode 替换/追加/移除
    # replace = 整组替换（默认，兼容旧客户端）；add = 追加；remove = 移除
    point_mode: str = "replace"
    difficulty: str | None = None          # '' = 恢复按主考点派生
    stars: int | None = None               # 0 = 恢复按主考点派生
    year: int | str | None = None          # '' / 0 = 清空
    region: str | None = None              # '' = 清空
    book: str | None = None                # 改书名（和 label 一起给）
    label: str | None = None               # 改卷名
    reviewed: bool | None = None           # 标记/取消“已复核”


@router.post("/questions/batch")
@retry_on_concurrent
def batch_patch(body: BatchTagBody) -> dict:
    r"""批量改标签（**一次写回**）。语义与 `patch_question` 的单题标签一致。

    · 只改标签，不碰正文；改完仍要过 `conform`，不过就整批不写。
    · 考点默认整体替换；`point_mode=add/remove` 时按题追加/移除（保留原顺序）。
    · 改书名/卷名时按单题同一条规则重拼 key：只有 key 本来就是
      `书/卷名#号` 拼出来的才改，`高考真题汇编/2024/新高考I卷#1` 这种
      “多一层目录”的保持原 key，只改 meta（和单题一致）。
    · 改名撞车 → 整批 409，不写一半。
    """
    from amti import conform as _cf
    if not body.keys:
        raise HTTPException(400, "keys 不能为空")
    keys = list(dict.fromkeys(body.keys))
    if len(keys) > 500:
        raise HTTPException(400, "一次最多改 500 道（再多就分批）")
    fields = {k for k in ("points", "difficulty", "stars", "year", "region",
                          "book", "label", "reviewed")
              if getattr(body, k) is not None}
    if not fields:
        raise HTTPException(400, "没有给任何要改的字段")
    if body.point_mode not in ("replace", "add", "remove"):
        raise HTTPException(400, "point_mode 只能是 replace / add / remove")
    if body.point_mode != "replace" and body.points is None:
        raise HTTPException(400, "point_mode 需要和 points 一起给")

    if body.points is not None:
        unknown = [p for p in body.points if not knowledge.get(p)]
        if unknown:
            raise HTTPException(400, "不认识的考点：%s" % "、".join(unknown[:5]))
    if body.difficulty not in (None, "", "简单题", "中档题", "难题"):
        raise HTTPException(400, "难度只能是 简单题/中档题/难题/空")
    if body.stars is not None and not (0 <= body.stars <= 4):
        raise HTTPException(400, "星级只能是 0–4（0 = 按考点派生）")

    # 批量只改标签（不动 book/label）时 key 不变，可以只读/只写命中的卷。
    fast = body.book is None and body.label is None
    if fast:
        by, vols, chunks, sig = store.read_many_map(keys)
        qs = None
    else:
        qs, sig = store.load_for_update()
        by = {q.key: q for q in qs}
    missing = [k for k in keys if k not in by]
    if missing:
        raise HTTPException(404, "有 %d 道题找不到：%s"
                            % (len(missing), "、".join(missing[:3])))
    before_hashes = {k: by[k].content_hash() for k in keys}

    stamp = time.strftime("%Y-%m-%d %H:%M")
    touched = []
    renamed: list[tuple[str, str]] = []
    taken = set(by)                     # 本批改名后的 key 也要占位，避免批内撞车
    for k in keys:
        q = by[k]
        if body.points is not None:
            pts = list(dict.fromkeys(body.points))
            if body.point_mode == "add":
                q.points = list(dict.fromkeys([*(q.points or []), *pts]))
            elif body.point_mode == "remove":
                drop = set(pts)
                q.points = [p for p in (q.points or []) if p not in drop]
            else:
                q.points = pts
            # 和单题 `patch_question` 同一口径：人工批量改过考点，来源就记 human。
            # 不记的话详情仍显示「AI标注」，体检页的“考点来源”统计也会失真。
            q.meta["point_source"] = "human"
        if body.difficulty is not None:
            if body.difficulty:
                q.meta["difficulty"] = body.difficulty
            else:
                q.meta.pop("difficulty", None)
        if body.stars is not None:
            if body.stars:
                q.meta["stars"] = body.stars
            else:
                q.meta.pop("stars", None)
        if body.year is not None:
            ys = str(body.year).strip()
            if ys in ("", "0"):
                q.meta.pop("year", None)
            else:
                try:
                    q.meta["year"] = int(ys)
                except ValueError:
                    raise HTTPException(400, "年份要是整数：%r" % (body.year,))
        if body.region is not None:
            if body.region.strip():
                q.meta["region"] = body.region.strip()
            else:
                q.meta.pop("region", None)
        if body.reviewed is not None:
            review_mod.apply_decision(
                q, "approved" if body.reviewed else "pending",
                note="批量快速通过（未逐题审阅）" if body.reviewed else "",
                reviewer="批量")

        if body.book is not None or body.label is not None:
            old_book = str(q.meta.get("book") or "")
            old_label = str(q.meta.get("source_label") or "")
            new_book = (body.book if body.book is not None else old_book).strip()
            new_label = (body.label if body.label is not None else old_label).strip()
            if not new_book or not new_label:
                raise HTTPException(400, "书 / 卷名不能为空：%s" % k)
            q.meta["book"] = new_book
            q.meta["source_label"] = new_label
            head, _, tail = k.rpartition("#")
            # 和 patch_question 同一条判据：拿**改名前的**书/卷名比
            if head and head == "%s/%s" % (old_book, old_label):
                new_key = "%s/%s#%s" % (new_book, new_label, tail)
            else:
                new_key = k
            if new_key != q.key:
                if new_key in taken and new_key != k:
                    raise HTTPException(409, "改名撞车：%s" % new_key)
                _migrate_meta_refs(qs, k, new_key)
                taken.discard(k)
                taken.add(new_key)
                q.key = new_key
                renamed.append((k, new_key))

        q.meta["edited_at"] = stamp
        touched.append(q)

    viol = _cf.run(touched)
    if viol:
        v = viol[0]
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (v["why"], v["check"], v["field"]))

    all_changed = list(dict.fromkeys(
        [k for k in keys] + [q.key for q in touched]))
    # 批量改名会改别的题 meta；跨卷引用必须整库写回。
    if fast:
        rep = store.write_many(touched, volumes=vols, chunks=chunks,
                               expect_hashes=before_hashes, expect_sig=sig)
    else:
        rep = store.rewrite_all(qs, based_on=sig,
                                changed_keys=(None if renamed else all_changed))
    fulltext.apply(all_changed, {x.key: x for x in touched})
    _rm_apply(all_changed, sig, {x.key: x for x in touched})

    # 改名后的跨文件引用迁移（存档/讲义/台账）+ 使用频次；写成功之后才做
    for old, new in renamed:
        _migrate_key_refs(old, new)
        _migrate_usage(old, new)
        _audit_key_rename(old, new)

    from amti.audit import CHANGE_DIR
    try:
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_批量改标签.md" % time.strftime("%Y%m%d_%H%M%S"))
        rmap = dict(renamed)
        lines = ["- `%s`%s" % (k, (" → `%s`" % rmap[k]) if k in rmap else "")
                 for k in keys]
        f.write_text(
            "# 批量改标签\n\n- 时间：%s\n- 题目：%d 道\n- 字段：%s\n"
            "- 改名：%d 道\n\n%s\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), len(touched),
               "、".join(sorted(fields)), len(renamed), "\n".join(lines)),
            encoding="utf-8")
    except Exception:
        log.warning("批量改标签记档失败（修改已生效）", exc_info=True)

    # **改名映射必须回给界面**：批量改书名/卷名会换 key，而界面里
    # 「当前卷子」只存题对象、不跟库自动同步（`App.paperMap`）。
    # 只回一个 `renamed` 数量的话，卷子里那些题仍拿着旧 key，导出时才
    # 报“找不到题”——单题改名有 `remapKey`，批量这里不能漏。
    # 附上新的出处字段，前端不用再逐题 `GET` 就能把卷子里的显示改对。
    renames = [{
        "old": old,
        "new": new,
        "book": str(by[old].meta.get("book") or ""),
        "label": str(by[old].meta.get("source_label") or ""),
        "year": by[old].meta.get("year") or "",
    } for old, new in renamed]

    return {"ok": True, "changed": len(touched), "renamed": len(renamed),
            "renames": renames,
            "volumes": rep.get("volumes"), "partial": rep.get("partial", False)}


# ── 补解析／补答案 ────────────────────────────────────────────────────
#
# 用户的原话：「没有解析也没有答案，我可以在题目界面直接录入 latex 代码，
# 经规范审查后，可以把解析写入，答案我也可以录进去了」。
#
# 这是**从界面改正文**，比改答案重，所以按录入那条路的规矩来，一步不少：
#
#     ① 规范化   过一遍 `normalize`（答案进作答括号、行间公式去壳…）
#     ② 规范审查 `conform` 必须 0 违规
#     ③ 落盘     写库 + 记 `变更记录/`
#
# **仍然改不了题干和选项**——那两个字段不在这个接口的射程里。
# 题干是题目的本体，改它等于换了一道题，必须走重新录入。

# ── 从整份文档里取出解析 ──────────────────────────────────────────────
#
# 用户是**直接粘整份 `.tex`** 的：`\documentclass`、`\usepackage`、
# `\begin{document}`、题目环境、解析环境全在里面。原样塞进 `solution`
# 会被规范检查拦住（`\documentclass` 会当正文渲染成一堆反斜杠）——
# 拦得对，但对用户没用：他要的是"贴进去就能用"。
#
# 所以这里把**解析那一段**取出来，其余部分丢掉。

_SOL_ENV = re.compile(r"\\begin\{solution\}(.*?)\\end\{solution\}", re.S)
_DOC_ENV = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.S)
_PREAMBLE = re.compile(
    r"\\(documentclass|usepackage|RequirePackage|geometry|examsetup)"
    r"\s*(\[[^\]]*\])?\s*\{[^}]*\}")
_Q_ENV = re.compile(r"\\begin\{question\}(.*?)\\end\{question\}", re.S)
# 解里若混进选题的 `choices`，说明取错了范围
_CHOICES = re.compile(r"\\begin\{choices\}")


def _extract_solution(raw: str) -> tuple[str, list[str]]:
    r"""把用户贴进来的东西**规整成纯解析正文**。返回 (正文, 做了什么)。

    处理顺序（每一步都记进 `notes`，干跑时给人看）：

      ① 有 `\begin{solution}…\end{solution}` → 只取里面
      ② 有 `\begin{document}…\end{document}`   → 只取里面
      ③ 去掉导言区命令（`\documentclass`／`\usepackage`…）
      ④ 若还剩 `\begin{question}…\end{question}` → 整段丢掉
         （那是题面，不是解析；**解析里不该有题面**）

    只认这几种，别的**不猜**：剩下的内容照原样交给规范器去审。
    """
    notes: list[str] = []
    t = raw or ""

    m = _SOL_ENV.search(t)
    if m:
        t = m.group(1)
        notes.append("从 `\\begin{solution}…\\end{solution}` 里取出解析")
    else:
        m2 = _DOC_ENV.search(t)
        if m2:
            t = m2.group(1)
            notes.append("从 `\\begin{document}…\\end{document}` 里取出正文")

    t2, n = _PREAMBLE.subn("", t)
    if n:
        t = t2
        notes.append("去掉了 %d 条导言区命令" % n)

    t2, n = _Q_ENV.subn("", t)
    if n:
        t = t2
        notes.append("去掉了 %d 个题目环境（那是题面，不该进解析）" % n)

    if _CHOICES.search(t):
        notes.append("⚠ 解析里还留着 `choices` 环境——请确认取的范围对不对")

    return t.strip(), notes


# 从解析里**读**答案（不是解题）。只认明说的写法，读不到就留空。
_ANS_BOXED = re.compile(r"\\boxed\{\\text\{([^}]*)\}\}|\\boxed\{([^}]*)\}")
_ANS_SAID = re.compile(r"(?:故选|答案为|答案[：:])\s*([A-D](?:\s*[、,，]?\s*[A-D])*)")


def _answer_from_solution(sol: str, q) -> str:
    r"""解析里明写了答案就顺手读出来。**读不到就返回空**，不猜。

    用户的原文以 `\boxed{\text{A、B、C}}` 收尾——这种一眼能看出来的，
    没必要让人再手填一遍。
    """
    if not sol:
        return ""
    m = _ANS_BOXED.search(sol)
    if m:
        txt = m.group(1) or m.group(2) or ""
        letters = "".join(sorted(set(re.findall(r"[A-D]", txt.upper()))))
        if letters:
            return letters
    m = _ANS_SAID.search(sol)
    if m:
        letters = "".join(sorted(set(re.findall(r"[A-D]", m.group(1).upper()))))
        if letters:
            return letters
    return ""


class SolutionBody(BaseModel):
    solution: str = ""
    answer: str = ""
    dry_run: bool = True                # 默认只审不写


@router.post("/questions/{key:path}/solution")
@retry_on_concurrent
def question_solution(key: str, body: SolutionBody) -> dict:
    r"""补/改**解析与答案**。默认干跑，`dry_run=false` 才落盘。"""
    from amti import conform as _cf
    from amti import normalize as _norm

    k = urllib.parse.unquote(key)
    # 解析/答案不改 key：只读/只写目标卷，别把全库拉进来。
    one = store.read_one(k)
    if one is None:
        raise HTTPException(404, "没有这道题：%s" % k)
    q, vol, sig, chunk = one
    before = q.content_hash()

    # 在一份**副本**上试，干跑和落盘走的是同一条路——
    # 不然"预览看到的"和"真写进去的"就不是一个东西了。
    from copy import deepcopy
    t = deepcopy(q)

    before_viol = [{"check": v["check"], "why": v["why"], "field": v["field"]}
                   for v in _cf.run([t])]

    notes: list[str] = []
    if body.solution.strip():
        # **贴整份文档也认**：把解析那一段取出来，导言区和题面丢掉
        sol, notes = _extract_solution(body.solution)
        if not sol.strip():
            return {"ok": False, "saved": False, "error":
                    "没找到解析内容。可以贴整份文档（含 \begin{solution}…），"
                    "也可以只贴解析正文。", "notes": notes}
        t.solution = sol
    # 答案：手填的优先；没填就从解析里读（只认明写的写法）
    if body.answer.strip():
        t.answer = _clean_answer_input(t, body.answer)
    elif t.solution:
        got = _answer_from_solution(t.solution, t)
        if got:
            t.answer = _clean_answer_input(t, got)
            notes.append("从解析里读出了答案：%s" % got)

    fixed = _norm.normalize(t, _norm.ENTRY)         # ① 规范化
    after_viol = [{"check": v["check"], "why": v["why"], "field": v["field"]}
                  for v in _cf.run([t])]            # ② 规范审查
    if after_viol:
        return {"ok": False, "saved": False,
                "before": before_viol, "fixed": fixed, "after": after_viol,
                "error": "规范审查没通过：%s（%s）"
                         % (after_viol[0]["why"], after_viol[0]["check"])}

    if body.dry_run:
        return {"ok": True, "saved": False, "before": before_viol,
                "fixed": fixed, "after": [], "solution": t.solution,
                "answer": t.answer, "stem": t.stem, "notes": notes}

    # ③ 落盘。**改的只能是解析和答案**，别的字段一个字都不许动。
    #
    # ⚠️ 题干要**先抹掉作答括号再比**：规范化本来就会把答案写进
    # `\paren[…]`／`\fillin[…]`（这正是「答案进作答括号」那条规则干的事），
    # 拿原样题干去比必然误报。除掉这个位置之后，正文才是一个字节都不许变。
    def _guard_of(x):
        return (_content_outside_answer(x)[0],
                [(o.label, o.text) for o in x.options],
                [f.id for f in (x.figures or [])],
                list(x.points))

    guard = _guard_of(q)
    old_sol, old_ans, old_stem = q.solution, q.answer, q.stem
    q.solution, q.answer = t.solution, t.answer
    # ⚠️ **题干也要跟着规范化后的走**。
    # 「答案进作答括号」改的正是题干（往里插 `\paren[B]`）——只拷答案不拷题干的话，
    # 这条规则白做，卷面上不出现作答括号、答案也没地方显示。
    # 安全性由上面那道 `_guard_of` 保证：除作答位置外，题干正文一个字节都没变。
    q.stem = t.stem
    if _guard_of(q) != guard:
        q.solution, q.answer, q.stem = old_sol, old_ans, old_stem   # 回滚
        raise HTTPException(500, "改解析时动到了题干正文/选项/配图/考点，已拒绝")
    q.meta["solution_source"] = "human"
    # 同样：改解析≠审过整题。已有复核会因 content_hash 变化自动 stale。
    if body.answer.strip():
        q.meta["answer_source"] = "human"
    q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    # 同 patch_question：**交给 @retry_on_concurrent 处理**，别在这里转 409，
    # 否则装饰器永远接不到 ConcurrentWrite、自动重试失效。
    store.write_one(q, volume=vol, expect_hash=before, expect_sig=sig,
                    chunk=chunk)
    fulltext.apply([q.key], {q.key: q})
    _rm_apply([q.key], sig, {q.key: q})

    try:
        from amti.audit import CHANGE_DIR
        import time as _t
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面补解析.md" % _t.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面补解析\n\n- 时间：%s\n- 题目：`%s`\n"
            "- 解析：%d → %d 字\n- 答案：%r → %r\n"
            "- 规范化改动：%s\n- 规范审查：通过（0 违规）\n"
            % (_t.strftime("%Y-%m-%d %H:%M:%S"), q.key,
               len(old_sol or ""), len(q.solution or ""), old_ans, q.answer,
               "、".join(fixed) if fixed else "无"),
            encoding="utf-8")
    except Exception:
        log.warning("解析变更记档失败（修改已生效）：%s", "", exc_info=True)
        pass

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    d.update({"ok": True, "saved": True, "before": before_viol,
              "fixed": fixed, "after": [], "notes": notes})
    return d


# ── 改源码 ────────────────────────────────────────────────────────────
#
# 详情页的「改源码」：把整道题的 LaTeX 正文（`\begin{question}…\end{question}`）
# 拿来直接改。**不设口令**（用户明确说没必要）：打开就是编辑器；
# 安全性由下面几道校验兜住，而不是靠多输一次密码——
#   · 只改正文，`%% @q` 元数据行不进来（key/出处/考点不会被手改坏）；
#   · 解析 → 规范化 → 规范审查，结构/格式不过一律不写；
#   · `expect_hash` 防并发覆盖；`store.update` 的写锁 + 临时文件 + rename
#     保证不会写半截。
#
# 保存走 `store.update`：读全库、改这一道、整库写回都在同一把锁里，
# 不会覆盖别人同时写进来的题。`expect_hash` 再挡一层「这道题本身被改过」。

class SourceBody(BaseModel):
    tex: str | None = None             # 不给 = 把当前源码发回来
    dry_run: bool = True               # 默认只检查不写盘
    expect_hash: str = ""              # 打开编辑器时那道题的内容指纹


def _source_candidate(old, tex: str):
    r"""界面上的源码 → 一道题。**只碰正文，元数据一律沿用库里的。**

    返回 `(候选题, 改之前的问题, 规范化改动, 复核后的问题, 结构问题)`。
    解析不出来直接 400 —— 这种情况没有"部分成功"可言。
    """
    from amti import conform as _cf
    from amti import normalize as _norm
    from amti.latex_ir import parse_question

    text = (tex or "").strip()
    # 用户可能把 `%% @q` 那行一起贴回来；元数据不在编辑范围内，直接丢掉。
    text = re.sub(r"(?m)^[ \t]*%%[ \t]*@q[^\n]*\n?", "", text).strip()
    if not text:
        raise HTTPException(400, "源码是空的")

    # **只允许一道题。** 多贴一道时 `parse_question` 会静默只取第一道，
    # 后面的内容看起来"保存成功"其实丢了——宁可当场拒绝。
    if len(re.findall(r"\\begin\{(?:question|problem)\}", text)) != 1:
        raise HTTPException(
            400, r"这里只改一道题：源码里要恰好有一个 \begin{question} 或 \begin{problem}")
    if not re.search(r"\\end\{(?:question|problem)\}\s*$", text):
        raise HTTPException(
            400, r"源码要在 \end{question}（或 \end{problem}）结束，后面不要带别的题")

    cand = parse_question(text)
    if cand is None:
        raise HTTPException(
            400, r"没认出题目环境：源码里要有 \begin{question} … \end{question}")

    # key / 考点不能从源码里改（源码里也没有它们）。
    cand.key = old.key
    cand.points = list(old.points)
    # 分值由正文的 `[points=…]` 表达；其余元数据（出处/年份/难度/来源）
    # 沿用库里的。旧分值先删掉，否则把 `[points=…]` 删了也改不回去。
    meta = dict(old.meta or {})
    meta.pop("points", None)
    meta.update(cand.meta or {})
    cand.meta = meta

    # **改之前**：用户这份源码本身合不合规。必须跑在规范化**之前**——
    # 跑在后面的话"改之前"和"复核后"是同一份，报告就成了摆设。
    before = [{"check": v["check"], "why": v["why"], "field": v["field"]}
              for v in _cf.run([cand])]

    fixed = _norm.normalize(cand, _norm.ENTRY)
    after = [{"check": v["check"], "why": v["why"], "field": v["field"]}
             for v in _cf.run([cand])]
    problems = cand.problems()

    # **防手滑删光。** 源码编辑是整段替换：少写一行 `\paren[A]`、把
    # `\begin{solution}` 连同内容一起删掉，格式上都是合法的，`conform`
    # 也看不出来——但题目会悄悄变成"没答案/没解析"。
    # 库的规矩是「没答案或没解析一律不许入库」，所以这里必须拦；
    # 真想清空就走「改答案」那条路（那里本来就有明确的提示）。
    if (old.answer or "").strip() and not (cand.answer or "").strip():
        problems.insert(0, "答案被清空了——如果是有意换答案，请在同一份源码里把新答案写进去")
    if old.has_solution and not cand.has_solution:
        problems.insert(0, "解析被删空了——可以改写，但不能把整段解析删掉")
    return cand, before, fixed, after, problems


def _source_images(q) -> dict:
    r"""这道题引用了哪些图、在不在库里。

    `改源码` 不能上传图片（那是录入那条路的事），所以这里只**如实报**：
    缺的图保存后会露在卷面上，必须在按保存之前看见。
    """
    from amti import images as _im
    out: dict[str, dict] = {}
    for text in [q.stem, q.solution] + [o.text for o in q.options]:
        for name in _im.collect(text or ""):
            if name in out:
                continue
            out[name] = ({"status": "ok", "note": "已在库"}
                         if (IMG_DIR / name).is_file()
                         else {"status": "missing", "note": "库里没有这张图"})
    return out


def _source_report(cand, before, fixed, after, problems) -> dict:
    r"""检查结果 + 渲染预览。**检查与保存走同一个构造函数**，
    所以"预览看到的"就是"真写进去的"（和补解析接口同一个原则）。

    报告的**分块与录入页那套一致**（`spec` / `images` / `impact`）：
    改源码和录新题是同一件事的两半，界面不该有两套说法。
    """
    try:
        d = _brief(cand)
    except Exception:
        # 源码坏到连预览都解析不了时，仍然把审查报告交回去；
        # 不能因为预览失败就让整个接口 500（那样用户什么也看不到）。
        log.warning("源码预览解析失败：%s", cand.key, exc_info=True)
        d = {
            "key": cand.key, "type": cand.type,
            "type_label": QTYPE_LABEL.get(cand.type, cand.type),
            "stem": cand.stem,
            "options": [{"label": o.label, "text": o.text} for o in cand.options],
            "answer": cand.answer, "solution": cand.solution,
            "blocks": {"stem": [], "answer": [], "solution": [], "options": []},
            "points": cand.points, "difficulty": cand.difficulty, "stars": cand.stars,
            "point_titles": cand.point_titles, "meta": cand.meta, "kind": cand.kind,
            "hash": cand.content_hash(), "missing": cand.missing(),
            "problems": problems, "figures": [f.id for f in cand.figures],
            "flags": {},
        }
    d.update({
        "ok": not after and not problems,
        "saved": False,
        "tex": question_to_tex(cand),
        "fixed": fixed,
        "after": after,
        "problems": problems,
        # ── 与录入页同一套报告字段 ──
        "spec": {"before": before, "fixed": fixed, "after": after,
                 "ok": not after and not problems},
        "images": _source_images(cand),
        "impact": {
            "existing_questions": 0,
            "note": "只改这一道；其余题目内容一个字节不动"
                    "（保存时整卷重写，但别的题逐字不变）。",
        },
    })
    return d


def _source_audit(q, before: str, after: str, fixed) -> None:
    r"""改源码的记档。失败**不阻断**保存，但必须留日志——
    「改了但没记录」正是审查报告 Important #3 要防的事。"""
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面改源码.md" % time.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面改源码\n\n- 时间：%s\n- 题目：`%s`\n"
            "- 内容指纹：%s → %s\n- 规范化改动：%s\n"
            "- 规范审查：通过（0 违规）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), q.key, before, after,
               "、".join(fixed) if fixed else "无"),
            encoding="utf-8")
    except Exception:
        log.warning("改源码记档失败（修改已生效）：%s", q.key, exc_info=True)


@router.post("/questions/{key:path}/source")
def question_source(key: str, body: SourceBody) -> dict:
    r"""改一道题的 LaTeX 源码。

    三种用法（同一个接口，只差参数）：

        {}                                              → 返回当前源码
        {"tex": "…"}                                    → 只检查（dry_run 默认 true）
        {"tex": "…", "dry_run": false}                  → 检查 → 写盘

    不设口令（用户明确说没必要）；安全性靠解析/规范化/规范审查、
    `expect_hash` 并发校验和原子写盘。
    """
    k = urllib.parse.unquote(key)

    # ── 取源码 ──
    if body.tex is None:
        q = _load_question(k)
        if q is None:
            raise HTTPException(404, f"没有这道题：{k}")
        return {"ok": True, "key": q.key, "tex": question_to_tex(q),
                "hash": q.content_hash()}

    # ── 干跑：只看不写 ──
    if body.dry_run:
        q = _load_question(k)
        if q is None:
            raise HTTPException(404, f"没有这道题：{k}")
        if body.expect_hash and q.content_hash() != body.expect_hash:
            raise HTTPException(
                409, "这道题刚被别的进程改过（内容指纹变了），"
                     "为免覆盖别人的改动，请关掉重开再改。")
        cand, before, fixed, after, problems = _source_candidate(q, body.tex)
        return _source_report(cand, before, fixed, after, problems)

    # ── 快速档：没改动 / 改坏了 → 根本不进写锁 ──
    #
    # 真写要「读全库 → 改一道 → 整库重写」，实测约 8 秒。可用户点保存时
    # 经常一个字都没改（先点检查再保存），或者源码明显不合规——这两种情况
    # 都**不需要写盘**。下面先拿当前快照算一遍：
    #   · 内容指纹一样 → 直接回「没有改动」；
    #   · 结构/规范不过 → 直接把报告交回去（写进去也会被同一套检查拒绝）。
    # 真正要写时，`store.update` 里还会**再算一遍**，所以这里只省时间，
    # 不放松「保存前必须过检查」这条。
    q0 = _load_question(k)
    if q0 is None:
        raise HTTPException(404, f"没有这道题：{k}")
    if body.expect_hash and q0.content_hash() != body.expect_hash:
        raise HTTPException(
            409, "这道题刚被别的进程改过（内容指纹变了），"
                 "为免覆盖别人的改动，请关掉重开再改。")
    cand0, before0, fixed0, after0, problems0 = _source_candidate(q0, body.tex)
    if after0 or problems0:
        return _source_report(cand0, before0, fixed0, after0, problems0)
    if cand0.content_hash() == q0.content_hash():
        rep = _source_report(cand0, before0, fixed0, after0, problems0)
        rep.update({"ok": True, "saved": False, "unchanged": True})
        return rep

    same_key = bool(cand0.key == q0.key)
    # ── 热路径：源码没改出处（key 不变）→ 只读/只写目标卷 ──
    if same_key:
        one = store.read_one(k)
        if one is None:
            raise HTTPException(404, f"没有这道题：{k}")
        q, vol, sig, chunk = one
        if body.expect_hash and q.content_hash() != body.expect_hash:
            raise HTTPException(
                409, "这道题刚被别的进程改过（内容指纹变了），"
                     "为免覆盖别人的改动，请关掉重开再改。")
        cand, before, fixed, after, problems = _source_candidate(q, body.tex)
        rep = _source_report(cand, before, fixed, after, problems)
        if after or problems:
            return rep
        after_hash = cand.content_hash()
        if after_hash == before:
            rep.update({"ok": True, "saved": False, "unchanged": True})
            return rep
        cand.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
        try:
            store.write_one(cand, volume=vol, expect_hash=before,
                            expect_sig=sig, chunk=chunk)
        except store.ConcurrentWrite:
            raise HTTPException(
                409, "这道题在你改的时候被别的进程改过了，"
                     "为免覆盖别人的改动，**没有保存**。请关掉重开再改。")
        fulltext.apply([k], {k: cand})
        _rm_apply([k], sig, {k: cand})
        _source_audit(cand, before, after_hash, fixed)
        rep.update({"ok": True, "saved": True, "unchanged": False,
                    "hash": after_hash})
        return rep

    # ── 真写：改出处可能换 key，需要整库处理跨题引用 ──
    out: dict = {}

    def _do(qs):
        for i, q in enumerate(qs):
            if q.key != k:
                continue
            before = q.content_hash()
            if body.expect_hash and before != body.expect_hash:
                out["conflict"] = True
                return store.NO_WRITE

            cand, before, fixed, after, problems = _source_candidate(q, body.tex)
            out["report"] = _source_report(cand, before, fixed, after, problems)
            if problems or after:
                out["invalid"] = True
                return store.NO_WRITE

            after_hash = cand.content_hash()
            if after_hash == before:
                # 一个字没改：**不写盘**。否则整库重写会把所有卷的 mtime
                # 都改掉，别的进程的 `based_on` 校验会白失败一次。
                out["unchanged"] = True
                return store.NO_WRITE

            cand.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
            # 源码里改了 `\source{}` 也可能换 key。和「改出处」一样，
            # 跨题 meta 引用要在整库写回之前跟着换；存档/台账在写回后迁。
            if cand.key != q.key:
                out["renamed_from"] = q.key
                _migrate_meta_refs(qs, q.key, cand.key)
            qs[i] = cand
            out.update({"before": before, "after_hash": after_hash,
                        "fixed": fixed, "cand": cand})
            return qs
        out["missing"] = True
        return store.NO_WRITE

    # 走到这里说明源码改了出处/key：别的题 meta 里的 dup_of/also_in
    # 等引用要一起改，必须整库写回。
    old_sig = store.volume_signature()
    store.update(_do)

    if out.get("missing"):
        raise HTTPException(404, f"没有这道题：{k}")
    if out.get("conflict"):
        raise HTTPException(
            409, "这道题在你改的时候被别的进程改过了，"
                 "为免覆盖别人的改动，**没有保存**。请关掉重开再改。")
    rep = out["report"]
    if out.get("invalid"):
        return rep
    if out.get("unchanged"):
        rep.update({"ok": True, "saved": False, "unchanged": True})
        return rep

    fulltext.apply([k, out["cand"].key], {out["cand"].key: out["cand"]})
    _rm_apply([k, out["cand"].key], old_sig,
              {out["cand"].key: out["cand"]})

    # 源码改出处 → 换 key：存档/使用频次/改名台账在写回之后迁
    # （和 `patch_question` 同一套；不然改一次 `\source{}` 引用就全断了）
    renamed_from = out.get("renamed_from") or ""
    if renamed_from:
        moved = _migrate_key_refs(renamed_from, out["cand"].key)
        _migrate_usage(renamed_from, out["cand"].key)
        _audit_key_rename(renamed_from, out["cand"].key)
        rep["renamed_from"] = renamed_from
        log.info("源码改出处：%s → %s（引用已迁：%s）", renamed_from,
                 out["cand"].key, "、".join(moved) or "无")

    _source_audit(out["cand"], out["before"], out["after_hash"], out["fixed"])
    rep.update({"ok": True, "saved": True, "unchanged": False,
                "hash": out["after_hash"]})
    return rep
