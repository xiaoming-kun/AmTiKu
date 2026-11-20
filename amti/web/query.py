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


def point_mode_of(explicit: str, parsed: str = "") -> str:
    """考点命中方式：`any`（默认，命中任一） / `all`（交集，全部都要挂）。

    显式参数优先于搜索框语法，和其余筛选字段同一套规矩。
    """
    for v in (explicit or "", parsed or ""):
        if v.strip().lower() in ("all", "and", "交集", "全部"):
            return "all"
    return "any"


def point_groups_of(explicit: str, parsed: str, *,
                    resolve) -> tuple[tuple[frozenset[str], ...], frozenset[str]]:
    """把「显式 `point=`」和「语法 `考点:`」摊成**必须同时命中的组**。

    一组 = 命中组里任意一个考点 id 就算满足这一组。界面多选考点时每个
    考点单独一组；语法里一个名字解析出多个 id（如「函数」）时，它们属于
    **同一组**——要求的是一道题挂着「函数」这件事，不是挂齐那几个 id。

    解析不到任何 id 时给 `__none__`：语法写了考点就**必须是 0 结果**，
    不能退化成“不筛”（列表与组卷共用这条口径）。

    返回 `(groups, 扁平 id 集合)`；`any` 模式只用得到后一半。
    """
    if (explicit or "").strip():
        return tuple(frozenset({x}) for x in csv_set(explicit)), csv_set(explicit)
    groups: list[frozenset[str]] = []
    for part in sorted(csv_set(parsed)):
        got = set(resolve(part))
        groups.append(frozenset(got) if got else frozenset({"__none__"}))
    flat = frozenset().union(*groups) if groups else frozenset()
    return tuple(groups), flat


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
    #: 考点命中方式：`any` = 命中任一（默认）；`all` = 交集，每组都要命中。
    point_mode: str = "any"
    #: 交集模式下「必须同时命中」的组。空 = 退回 `points` 的任一语义。
    point_groups: tuple[frozenset[str], ...] = ()
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
    #: 「待补」：**缺答案或缺解析**（任一就够）。`missing` 是“全都缺”的语义，
    #: 导出前的自查要的恰恰是“任一不全”，两个不能互相顶替。
    incomplete: bool = False
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
        if self.point_mode == "all" and self.point_groups:
            # 交集：每一组都要在题目的考点里露出一个。组内是 OR（一个名字
            # 可能解析成几个 id），组间是 AND——「函数 ∧ 导数」的题很少，
            # 这正是老师做专题卷时要的那批。
            pts = set(item.points or ())
            if not all(g & pts for g in self.point_groups):
                return False
        elif self.points and not (self.points & set(item.points or ())):
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
        if self.incomplete:
            f = flags_of(item)
            if f.get("答案") and f.get("解析"):
                return False
        if self.has or self.missing:
            f = flags_of(item)
            if self.has and not all(f.get(k) for k in self.has):
                return False
            if self.missing and not all(not f.get(k) for k in self.missing):
                return False
        return True
