"""题目**读取**路由：列表 / 详情 / 答案 / 相似题 / 查重。

写路径拆在 `questions_edit.py`（改标签、改答案、改题型、改出处）与
`questions_source.py`（补解析、改源码、插 TikZ、批量改出处）——
拆开是因为这三类操作的前置校验、写入方式、要同步的派生索引各不相同，
放在一个 2000 行的文件里，改一处要通读三处（问题②）。
"""
from __future__ import annotations

import urllib.parse
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from amti import content_store
from amti import latex_blocks as lb
from amti.query_syntax import parse as parse_query
from amti.recall import recall as _recall
from amti import review as review_mod
from amti import store
from amti.logutil import get_logger
from amti.render_tex import question_to_tex
from amti.web.core import (
    _READMODEL_FLAGS, _brief_cached, _brief_cached_lite,
    _paper_usage, _point_stage, _readmodel_page, _seq_of, _stage_set, _usage,
)
from amti.web.present import brief as _brief
from amti.web.present import stage_of as _stage_of
from amti.web.query import QuestionFilter
from amti.web.query import csv_set as _csv_set
from amti.web.query import point_groups_of as _point_groups_of
from amti.web.query import point_mode_of as _point_mode_of
from amti.web.query import source_of as _source_of
from amti.web.query import tag_ids_matching as _tag_ids_matching

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
    #: 解析正文不进列表契约（列表走 `_slim_list_item`，详情才有）。
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
    solution: str = ""
    tex: str = ""




@router.get("/questions", response_model=QuestionListResponse)
def list_questions(
    q: str = "", type: str = "", kind: str = "",
    stage: str = "",          # 学段：primary/junior/senior，逗号分隔
    point: str = "",          # 考点 id，逗号分隔
    # 考点命中方式：any（默认，命中任一）/ all（交集，选的都要挂上）。
    # 界面「知识点」面板右上角的并集/交集开关、搜索框 `考点:A&B` 都落到这里。
    point_mode: str = "",
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
    missing: str = "",        # 逗号分隔：只列**缺**的（**全都缺**才算）
    # 「待补」：缺答案**或**缺解析，任一不全就列出来。导出前自查用；
    # 和 `missing=答案,解析`（两样都缺）不是一回事。
    incomplete: bool = False,
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
    # 考点：显式 `point=` 优先，搜索框的 `考点:` 兜底。摊成「必须同时命中
    # 的组」——交集模式下每组都要在题目的考点里露出一个。
    p_mode = _point_mode_of(point_mode, pq.point_mode)
    p_groups, point_ids = _point_groups_of(point, pq.point,
                                           resolve=_tag_ids_matching)
    stage_set = _stage_set(stage)
    # 筛选口径**只此一份**，见 amti/web/query.py。列表与组卷共用它。
    flt = QuestionFilter(
        qtype=qtype, kind=kind,
        points=point_ids,
        point_mode=p_mode,
        point_groups=p_groups,
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
        incomplete=incomplete,
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
    # 交集只在 Python 路径实现：读模型表里 `question_points` 是「题 → 考点」
    # 的明细，用 SQL 算“每组都露头”要么写子查询拼串、要么先 group by，
    # 两条路都比直接扫一遍字符串集合慢，还多一份口径。题库 3 万道，
    # 交集查询本来就不该出现在翻页热路径上。
    use_readmodel = (
        rm and not kw and not key_list and not pq.exclude and not region_v
        and p_mode != "all"
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
            incomplete=flt.incomplete,
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
    papers = _paper_usage()
    for item in page:
        b = _brief_cached_lite(item) if lite else _brief_cached(item)
        b["seq"] = _seq_of(item.key)
        b["used"] = usage.get(item.key, 0)
        hit = papers.get(item.key)
        if hit:
            b["papers"] = hit
        out.append(b)
    return {"total": total, "items": out,
            "search_mode": rec["mode"] if rec else "",
            "search_normalized": (rec["normalized"] if rec else "")}


@router.get("/questions/{key:path}/duplicates")
def duplicate_questions(key: str) -> dict:
    r"""查重：`items` 是**逐字重复**（同指纹 / 同 duplicate_group），
    `similar` 是**相似**（dup_of / similar_of，0.80–0.99）。

    两个口径必须分开：逐字重复才叫“重复题”，相似的只提示“同型/疑似”。
    **只提示，不合并**；没有发现时 `n=0, items=[]`，不编造。
    """
    from amti import duplicates as _dups
    k = urllib.parse.unquote(key)
    q = _load_question(k)
    if q is None:
        raise HTTPException(404, f"没有这道题：{key}")
    rec = _dups.info(q.key)
    items = ([_brief(it) for it in _dups.members(q.key) if it.key != q.key]
             if rec else [])
    similar = [_brief(it) for it in _dups.similar(q.key) if it.key != q.key]
    return {"key": q.key, "group": (rec or {}).get("group", ""),
            "n": (rec or {}).get("n", 0), "items": items,
            "similar": similar, "similar_n": len(similar)}


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
    hit = _paper_usage().get(q.key)
    if hit:
        d["papers"] = hit
    return d
