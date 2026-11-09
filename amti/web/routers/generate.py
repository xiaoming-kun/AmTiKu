"""组卷 / 单题换题路由。

筛选口径与 `/api/questions` 共用 `QuestionFilter`；组卷本身走
`amti.generate`，这里只负责把请求参数翻译成筛选器并渲染入卷 brief。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from amti import store
from amti.query_syntax import parse as parse_query
from amti.recall import recall as _recall
from amti.web.core import _usage
from amti.web.present import brief as _brief
from amti.web.core import _brief_cached_lite
from amti.web.query import QuestionFilter
from amti.web.query import csv_set as _csv_set
from amti.web.query import tag_ids_matching as _tag_ids_matching

router = APIRouter(prefix="/api", tags=["generate"])


class ReplaceBody(BaseModel):
    """单题换题：给当前题找同题型/同板块/同难度的替补。"""
    key: str
    type: str = ""
    section: str = ""          # 解答题的板块（三角/数列、概率统计…）
    want_diff: str = ""        # 目标难度；空 = 用当前题的难度
    exclude: list[str] = Field(default_factory=list)
    limit: int = 8


class GenerateBody(BaseModel):
    """组卷。`pool` 是筛选条件，和 `/api/questions` 一致。

    `mode`：
      * `gaokao`    按高考卷面结构（8+3+3+5，填补位置）
      * `test`      不约束，按传入顺序
      * `coverage`  **按考点覆盖率组卷**（易→难排序）
    """
    mode: str = "gaokao"
    coverage: float = 0.9               # coverage 模式的目标覆盖率
    want: int = 19                      # coverage 模式要几道题
    # coverage 模式：**要不要保住高考卷面的题型比例**（8 单选 3 多选 3 填空 5 解答，
    # 按 want 等比缩放）。默认保——不保的话贪心只认考点个数，
    # 46 道题能挑出 23 道解答题（解答题考点密度最高），那卷子没法用。
    # 代价是覆盖率约掉 2.6 个百分点（85.5% → 82.9%），说明里会报出来。
    keep_structure: bool = True
    seed: int | None = None             # 同 seed 出同一套
    q: str = ""
    type: str = ""
    kind: str = ""
    point: str = ""
    difficulty: str = ""
    year: str = ""
    source: str = ""
    has: str = ""
    missing: str = ""
    # **和 `/api/questions` 同一套筛选**。以前这里只有 7 个，
    # 列表那边新增的「地区/完整度/星级/质检」四个维度压根传不进来——
    # 用户在列表里筛到 300 道，组卷却按"没筛"的池子挑，出题完全不是他要的。
    region_scope: str = ""
    paper_state: str = ""
    star_state: str = ""
    quality: str = ""
    point_source: str = ""       # 与 /api/questions 同义（「无」= 没记来源）
    # 组卷硬约束：缺图/短解析不上卷；year_from>0 只要近年；同一考点上限
    exclude_missing_figure: bool = True
    min_solution_len: int = 20
    year_from: int = 0
    point_quota: int = 2
    # 目标时长（分钟）：0 = 不检查；组完只提示“超了/少了”，不自动改题
    target_minutes: int = 120
    # 按地区/卷别选题（精确匹配 meta.region；逗号分隔取并集）
    region: str = ""
    # 非 `gaokao` 模式是"照单全收"语义（`generate()` 直接把整个池子摊成卷子）。
    # 不加这道闸门，筛完 2.8 万道再点「取筛选结果」，前端会拿到 2.8 万道题的
    # 完整 brief——浏览器直接卡死。超出就截断，并在报告里**明说**截了。
    max_items: int = 500


@router.post("/generate")
def api_generate(body: GenerateBody) -> dict:
    r"""按高考的结构与排布惯例随机组一套卷。

    规则见 `amti/generate.py`：分值结构、解答题板块顺序、小题章节上限。
    """
    from amti import generate as _gen
    # 与列表共用搜索框语法；显式参数优先。
    pq = parse_query(body.q)
    kw = pq.keyword
    rec = _recall(kw) if kw else None
    cands = frozenset(rec["keys"]) if rec and rec["keys"] else None
    qtype = body.type or pq.type
    difficulty_v = body.difficulty or pq.difficulty
    year_v = body.year or pq.year
    source_v = body.source or pq.source
    region_v = body.region or pq.region
    point_ids = set(_csv_set(body.point))
    if pq.point and not body.point:
        for part in _csv_set(pq.point):
            got = _tag_ids_matching(part)
            if got:
                point_ids |= got
            else:
                point_ids.add("__none__")
    # **同一个 QuestionFilter**：列表筛到什么，组卷就从什么里挑。
    # `regions` 以前只解析没使用（region 选择器形同虚设），一并接上。
    flt = QuestionFilter(
        qtype=qtype, kind=body.kind,
        points=frozenset(point_ids),
        difficulties=_csv_set(difficulty_v),
        years=_csv_set(year_v),
        sources=_csv_set(source_v),
        scopes=_csv_set(body.region_scope),
        paper_states=_csv_set(body.paper_state),
        star_states=_csv_set(body.star_state),
        qualities=_csv_set(body.quality),
        point_source=body.point_source.strip(),
        has=_csv_set(body.has),
        missing=_csv_set(body.missing),
        keyword=kw,
        tag_ids=frozenset(_tag_ids_matching(kw) if kw else ()),
        # 组卷选池**不搜解析**：题干没提导数、解析里提一句的题不该进导数卷。
        deep_keyword=False,
        regions=_csv_set(region_v),
        candidates=cands,
        candidate_only=bool(rec and rec["mode"] in ("math", "mixed") and cands),
        exclude_terms=pq.exclude,
    )
    pool = [item for item in store.load_cached() if flt.matches(item)]

    # 硬约束先过一遍：**列表里还在、但印出来做不了的题**不该进卷。
    # `test` 模式是“老师明确选的”，不过滤。
    if body.mode != "test":
        pool = _gen.filter_pool(
            pool,
            exclude_missing_figure=body.exclude_missing_figure,
            min_solution_len=body.min_solution_len,
            year_from=body.year_from)

    if body.mode == "coverage":
        # **按考点覆盖率组卷**：以「尽量多覆盖考点」为目标挑题，
        # 挑完**按易→难排好**。跟 `gaokao` 那种"填卷面位置"是两回事。
        mix = _gen.gaokao_mix(body.want) if body.keep_structure else None
        r = _gen.generate_by_coverage(pool, want=body.want, coverage=body.coverage,
                                      seed=body.seed, type_mix=mix,
                                      report_cost=bool(mix))
        r["slots"] = []
    else:
        # 非 `gaokao` 模式是"照单全收"：`generate()` 会把整个池子摊成卷子。
        # 筛完 2.8 万道再点「取筛选结果」，前端会拿到 2.8 万条 brief——卡死。
        cap = max(1, int(body.max_items or 500))
        r = _gen.generate(pool[:cap], mode=body.mode, seed=body.seed,
                          exclude_missing_figure=body.exclude_missing_figure,
                          min_solution_len=body.min_solution_len,
                          year_from=body.year_from,
                          point_quota=body.point_quota)
        if len(pool) > cap:
            r["report"]["note"] = (
                f"筛选到 {len(pool):,} 道，按当前顺序取前 {cap:,} 道入卷")

    # 顺带把每道题的显示信息带上，前端要列卷子。
    # **只给真正入卷的那几道渲染 brief**：`pool` 可能是筛选后的 2.8 万道，
    # 全量渲染块级 IR 会把这个服务卡住几十秒（列表接口早就为此改成
    # "先筛、先切，最后才渲染"），这里以前是漏的。
    # 时长预算：只提示，不偷偷换题——换题会破坏细目表和已排好的顺序
    _target = max(0, int(body.target_minutes or 0))
    _mins = r.get("minutes") or (r.get("report") or {}).get("minutes")
    if _target and _mins:
        _gap = int(_mins) - _target
        if _gap > 10:
            r["report"].setdefault("notes", []).append(
                "预计 %d 分钟，比目标 %d 分钟多 %d 分钟；可减少题量或换简单题"
                % (_mins, _target, _gap))
        elif _gap < -15:
            r["report"].setdefault("notes", []).append(
                "预计 %d 分钟，比目标 %d 分钟少 %d 分钟；题量还可以再加"
                % (_mins, _target, -_gap))

    picked = set(r["keys"])
    chosen = {q.key: q for q in pool if q.key in picked}
    r["items"] = [_brief(chosen[k]) for k in r["keys"] if k in chosen]
    return r




@router.post("/generate/replace")
def api_generate_replace(body: ReplaceBody) -> dict:
    r"""单题换题：返回可替换当前题的候选。

    排序不是随机的，按教师的实际偏好加权：
      ① 同主考点（+6）/ 同解答题板块（+5）
      ② 同目标难度（+4）
      ③ 与当前题有共同考点标签（+2）
      ④ 有解析（+1）、同类别（+0.5）
      ⑤ 用得少的题略微优先（-0.02/次，最多 -0.4）

    只返回 `limit` 条列表用 brief；答案/解析块 IR 不带（详情再取）。
    """
    from amti import generate as gen

    qs = list(store.load_cached())
    by_key = {q.key: q for q in qs}
    cur = by_key.get(body.key)
    if cur is None:
        raise HTTPException(404, "题不在库里")

    typ = body.type or cur.type
    want_diff = body.want_diff or cur.difficulty or ""
    section = body.section or ""
    topic = gen.topic_of(cur)
    section_topics = gen.SECTION_TOPICS.get(section, set())
    exclude = set(body.exclude) | {cur.key}
    usage = _usage()

    scored: list[tuple[float, object]] = []
    for q in qs:
        if q.key in exclude or q.type != typ:
            continue
        qt = gen.topic_of(q)
        s = 0.0
        if topic and qt == topic:
            s += 6
        if section_topics and qt in section_topics:
            s += 5
        if want_diff and q.difficulty == want_diff:
            s += 4
        if set(q.points) & set(cur.points):
            s += 2
        if q.has_solution:
            s += 1
        if q.kind == cur.kind:
            s += 0.5
        s -= min(usage.get(q.key, 0), 20) * 0.02
        scored.append((s, q))

    scored.sort(key=lambda x: (-x[0], getattr(x[1], "seq", 0) or 0))
    limit = max(1, min(int(body.limit or 8), 12))
    out = []
    for s, q in scored[:limit]:
        d = _brief_cached_lite(q)
        d["match"] = {
            "topic": bool(topic and gen.topic_of(q) == topic),
            "section": bool(section_topics and gen.topic_of(q) in section_topics),
            "difficulty": bool(want_diff and q.difficulty == want_diff),
        }
        d["score"] = round(s, 2)
        out.append(d)
    return {"items": out, "want_diff": want_diff, "topic": topic}
