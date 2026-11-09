"""题目查询的唯一筛选口径。

为什么要单独一个模块：`/api/questions`（列表）和 `/api/generate`（组卷）
原来各写一遍**同一套 15 个筛选维度**。列表这边新增「地区/完整度/星级/质检」
之后，组卷那边没跟上——用户在列表筛到 300 道，组卷却从没筛的池子里挑，
两边都觉得自己是对的。现在筛选只此一份，列表和组卷拿同一个
`QuestionFilter` 走一遍。

这里只做**纯判定**：不读盘、不改数据、不渲染块 IR。调用方自己决定
遍历哪个快照、先不先用 FTS/读模型召回。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from amti import knowledge
from amti import review as review_mod
from amti.schema import Question

#: 搜索框的提示语写着「搜索题目、答案、考点、出处」——这四个字段都得真能搜。
_TAG_HAYSTACK_FIELDS = ("id", "title", "topic", "section")


def csv_set(raw: str | None) -> frozenset[str]:
    """把 `a,b,c` 解析成集合。空串/None → 空集；空白项丢掉。"""
    return frozenset(x.strip() for x in (raw or "").split(",") if x.strip())


def source_of(q: Question) -> str:
    """卷别（如「新课标I卷」）。试卷上标注来源用的就是它。"""
    return q.meta.get("region") or (q.meta.get("source_label") or "").split("年")[-1]


def _has_figure(q: Question) -> bool:
    """`图` 这一格：图**不缺**——有图，或者这题本来就不需要图。

    口径已经收到 `Question.figure_ok`（录入干跑/列表共用一套），
    这里只做兼容包装，别再写第二份正则。
    """
    return q.figure_ok


def _has_figure_real(q: Question) -> bool:
    r"""`有图`：**真的有插图**（位图或 TikZ），不管这题需不需要。

    为什么要和 `图` 分开：`图` 是完整度（不需要图也算"不缺"），全库 98% 都是真。
    用户点「只看有·图」要的是真的有图的题（三千道上下），拿 `图` 去筛，
    出来两万八——**条件看着对、结果全不对**，实测被这么报过一次。
    """
    if q.figures:
        return True
    for text in [q.stem, q.solution] + [o.text for o in q.options]:
        if text and ("\\includegraphics" in text or "tikzpicture" in text):
            return True
    return False


def flags_of(q: Question) -> dict:
    """一道题的 `flags`。**只此一份**——`_brief`/`_cheap_fields`/筛选
    三处都要它，各写一遍必然分叉（实测就是这么把 `有图` 漏了的）。"""
    return {
        "答案": bool(q.answer.strip()),
        "解析": q.has_solution,
        "图": _has_figure(q),          # 图不缺（完整度）
        "有图": _has_figure_real(q),    # 真的有图（「只看有」用这个）
        "标签": bool(q.points),
        "小问": "\\begin{enumerate}" in q.stem,
        "存疑": bool(q.meta.get("solve_warn")),
    }


def tag_ids_matching(kw: str) -> set[str]:
    r"""考点表里**编号／名称／章节／主题**含 `kw` 的考点 id。

    考点表只有 152 条，一次算完；逐题只做一次集合判断。
    别在两万八千道题上逐条拼标签串——筛选阶段刻意只碰字符串和布尔值。
    """
    k = kw.lower()
    out: set[str] = set()
    # **K12 全查**：初中题挂的是 `c` 前缀知识点，只查 知识点.json 的话，
    # 搜「二次函数」「圆周角」一个初中考点都出不来。
    for node in knowledge.all_points("k12"):
        hay = " ".join(str(node.get(f) or "") for f in _TAG_HAYSTACK_FIELDS).lower()
        if k in hay:
            out.add(str(node.get("id")))
    return out


def source_hit(item: Question, kw: str) -> bool:
    """出处（书名／卷名／卷别／key）含不含这个关键词。大小写不敏感。

    `key` 也要看：`模拟题/2026精选模拟题/004#1` 这类历史 key 里的目录，
    和 `meta.book`/`source_label` 不一定同构；只比 meta 会漏。
    搜索框写的是「出处」，用户会把整条卷名、甚至 `#22` 抄进来。
    """
    k = kw.lower()
    m = item.meta or {}
    if any(k in str(m.get(f) or "").lower()
           for f in ("source_label", "book", "region")):
        return True
    return k in str(getattr(item, "key", "") or "").lower()


def kw_hit(item: Question, kw: str,
           tag_ids: set[str] | frozenset[str], *, deep: bool = False) -> bool:
    r"""关键词命中 **题干／答案／考点标签／出处** 任意一处就算命中。

    搜索框的提示语是「搜索题目、答案、考点、出处」，可后端原来只比了
    `stem` 与 `answer` 两个字段——输「余弦定理」「6.4.2」「解析几何」
    「南通一模」一个都出不来，看上去像标签坏了，其实是检索没查这两类字段。

    **列表与组卷共用这一条**：两边的筛选链本来就是一份逻辑，
    各写一遍必然分叉（改了一处，另一处还是搜不到）。

    `deep=True` 时**连解析一起搜**——只在列表搜索里开；组卷选池不开，
    否则“题干里没提导数、解析里提了一句”的题会被搜进导数卷。
    多词查询按 **AND**：每个词都要在某一处命中（整串比会永远搜不到
    “函数 单调”这种带空格的输入）。
    """
    if not kw:
        return True
    parts = [t for t in re.split(r"[\s,，、;；]+", kw.strip()) if t]
    if len(parts) > 1:
        return all(kw_hit(item, t, tag_ids, deep=deep) for t in parts)
    if kw in item.stem or kw in item.answer:
        return True
    if deep and kw in (item.solution or ""):
        return True
    if tag_ids & set(item.points or ()):
        return True
    return source_hit(item, kw)


@dataclass(frozen=True, slots=True)
class QuestionFilter:
    """题目筛选条件。空字段 = 该维度不筛。

    只覆盖「题目自身 + meta」能判断的条件；`stage` 需要知识地图，
    由调用方（列表接口）在进循环前算一次，不塞进这里。
    """

    qtype: str = ""
    kind: str = ""
    points: frozenset[str] = frozenset()
    difficulties: frozenset[str] = frozenset()
    years: frozenset[str] = frozenset()
    sources: frozenset[str] = frozenset()
    scopes: frozenset[str] = frozenset()
    paper_states: frozenset[str] = frozenset()
    star_states: frozenset[str] = frozenset()
    qualities: frozenset[str] = frozenset()
    point_source: str = ""
    answer_sources: frozenset[str] = frozenset()
    reviewed: str = ""
    review_status: frozenset[str] = frozenset()
    has: frozenset[str] = frozenset()
    missing: frozenset[str] = frozenset()
    keyword: str = ""
    tag_ids: frozenset[str] = frozenset()
    deep_keyword: bool = True
    regions: frozenset[str] = frozenset()
    #: 召回候选（recall() 的结果）。None = 不做候选限制。
    candidates: frozenset[str] | None = None
    #: True = 命中由候选集负责，不再用原文 `kw_hit` 二次筛。
    #: 公式查询必须这样：`cosB` 在原文里是 `\cos B`，二次筛会全刷掉。
    candidate_only: bool = False
    #: 搜索语法里的 `-词`：命中任一排除词就丢掉。列表与组卷同用。
    exclude_terms: tuple[str, ...] = ()

    def matches(self, item: Question) -> bool:
        if self.candidates is not None and item.key not in self.candidates:
            return False
        if self.qtype and item.type != self.qtype:
            return False
        if self.kind and item.kind != self.kind:
            return False
        if self.points and not (self.points & set(item.points or ())):
            return False
        if self.difficulties and item.difficulty not in self.difficulties:
            return False
        if self.years and str(item.meta.get("year") or "") not in self.years:
            return False
        if self.sources and source_of(item) not in self.sources:
            return False
        if self.scopes:
            sc = item.meta.get("region_scope") or (
                "single" if item.meta.get("region") else "unknown")
            if sc not in self.scopes:
                return False
        if self.paper_states:
            partial = item.meta.get("paper_complete") is False
            if ("partial" if partial else "complete") not in self.paper_states:
                return False
        if self.star_states:
            rated = item.stars > 0
            if ("rated" if rated else "unrated") not in self.star_states:
                return False
        if self.qualities:
            ok = (("dup" in self.qualities
                   and (item.meta.get("duplicate_group") or item.meta.get("dup_of")))
                  or ("lowres" in self.qualities
                      and item.meta.get("figure_low_res")))
            if not ok:
                return False
        if self.point_source:
            got = str(item.meta.get("point_source") or "")
            # 「无」是 /api/stats/detail 里 `or "无"` 那个合成组的名字
            if (self.point_source == "无" and got) or (
                    self.point_source != "无" and got != self.point_source):
                return False
        if self.answer_sources:
            if str(item.meta.get("answer_source") or "无") not in self.answer_sources:
                return False
        if self.reviewed or self.review_status:
            est = review_mod.effective_status(item)
            if self.reviewed:
                if (self.reviewed == "yes") != (est in review_mod.REVIEWED):
                    return False
            if self.review_status and est not in self.review_status:
                return False
        if self.regions:
            if str(item.meta.get("region") or "") not in self.regions:
                return False
        if (self.keyword
                and not (self.candidate_only and self.candidates is not None)
                and not kw_hit(item, self.keyword, self.tag_ids,
                               deep=self.deep_keyword)):
            return False
        for term in self.exclude_terms:
            if kw_hit(item, term, frozenset(), deep=self.deep_keyword):
                return False
        if self.has or self.missing:
            f = flags_of(item)
            if self.has and not all(f.get(k) for k in self.has):
                return False
            if self.missing and not all(not f.get(k) for k in self.missing):
                return False
        return True
