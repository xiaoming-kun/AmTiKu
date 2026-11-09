"""统计 / 体检数据路由。

`/api/stats` 给顶栏和总览用；`/api/stats/detail` 给体检页用。两者都只读
`store.load_cached()`，不写库。响应模型只钉顶层字段，`all_points` 这类
大列表保持 dict，避免复制一份考点结构。
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from pydantic import BaseModel

from amti import images as images_mod
from amti import knowledge as kb
from amti import review as review_mod
from amti import store
from amti.schema import QTYPE_LABEL
from amti.web.query import source_of

router = APIRouter(prefix="/api/stats", tags=["stats"])

DIFF_ORDER = {"简单题": 1, "中档题": 2, "难题": 3}


class StatType(BaseModel):
    key: str
    label: str
    n: int


class StatVolume(BaseModel):
    name: str
    n: int


class StatsResponse(BaseModel):
    total: int
    by_type: list[StatType]
    by_book: list[tuple[str, int]]
    missing: dict[str, int]
    volumes: list[StatVolume]
    baseline: int


def _im_mod_stats() -> dict:
    st = images_mod.stats()
    return {"files": st["files"], "bytes": st["bytes"]}


@router.get("", response_model=StatsResponse)
def stats() -> dict:
    by_type, by_book, miss = Counter(), Counter(), Counter()
    total = 0
    for q in store.load_cached():
        total += 1
        by_type[q.type] += 1
        by_book[q.kind] += 1
        for m in q.missing():
            miss[m] += 1
    return {
        "total": total,
        "by_type": [{"key": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                    for k, v in by_type.most_common()],
        "by_book": by_book.most_common(10),
        "missing": dict(miss),
        "volumes": [{"name": p.name, "n": store.vol_count(p)}
                    for p in store.existing_volumes()],
        "baseline": len(store.load_snapshot()),
    }


@router.get("/detail")
def stats_detail() -> dict:
    """统计页：考点覆盖、难度分布、完整性缺口、标签来源。"""
    qs = store.load_cached()
    # 体检页的考点全集：高中 + 初中（小学题库还没建，暂不列）。
    allp = kb.all_points("senior") + kb.all_points("junior")
    pts: Counter = Counter()
    pd: dict[str, Counter] = {}
    for q in qs:
        for p in q.points:
            pts[p] += 1
            pd.setdefault(p, Counter())[q.difficulty] += 1
    src = Counter(q.meta.get("point_source") or "无" for q in qs)
    src_all = Counter(source_of(q) for q in qs)
    # 章节题量按**题**去重：一道题挂 3 个本章考点只算 1 道。
    topic_n: Counter = Counter()
    for q in qs:
        for t in {kb.get(p).get("topic", "") for p in q.points}:
            if t:
                topic_n[t] += 1
    miss: Counter = Counter()
    for q in qs:
        for m in q.missing():
            miss[m] += 1
    rstat = review_mod.stats(qs)
    reviewed = rstat["reviewed"]
    return {
        "total": len(qs),
        "by_type": [{"value": k, "label": QTYPE_LABEL.get(k, k), "n": v}
                    for k, v in Counter(q.type for q in qs).most_common()],
        "by_kind": [{"value": k, "n": v}
                    for k, v in Counter(q.kind for q in qs).most_common()],
        "by_difficulty": [{"value": k, "n": v} for k, v in sorted(
            Counter(q.difficulty for q in qs if q.difficulty).items(),
            key=lambda x: DIFF_ORDER.get(x[0], 9))],
        "by_year": [{"value": k, "n": v} for k, v in sorted(
            Counter(str(q.meta.get("year")) for q in qs if q.meta.get("year")).items())],
        "by_point_source": [{"value": k, "n": v} for k, v in src.most_common()],
        "reviewed": reviewed,
        "unreviewed": len(qs) - reviewed,
        "review": rstat,
        "points_covered": len(pts),
        "points_total": len(allp),
        "untagged": sum(1 for q in qs if not q.points),
        "by_source": [{"value": k or "未标来源", "n": n}
                      for k, n in src_all.most_common(12)],
        # 全部考点，含 0 题目的——空考点本身就是要看的信息。
        "all_points": [{"value": p["id"], "title": kb.title_of(p["id"]),
                        "n": pts.get(p["id"], 0), "topic": p["topic"],
                        "section": p["section"],
                        "stars": p["stars"], "difficulty": p["difficulty"],
                        "by_diff": {d: pd.get(p["id"], Counter()).get(d, 0)
                                    for d in ("简单题", "中档题", "难题")}}
                       for p in sorted(allp,
                                       key=lambda x: (x["id"][:1].isalpha(),
                                                      [int(y) if y.isdigit() else 0
                                                       for y in x["id"].split(".")]))],
        "by_topic": [{"value": t, "n": topic_n.get(t, 0),
                      "total": sum(1 for p in allp if p["topic"] == t),
                      "covered": sum(1 for p in allp
                                     if p["topic"] == t and pts.get(p["id"], 0))}
                     for t in dict.fromkeys(p["topic"] for p in allp)],
        "top_points": [{"value": k, "title": kb.title_of(k), "n": v}
                       for k, v in pts.most_common(15)],
        "missing": [{"value": k, "n": v} for k, v in miss.most_common()],
        "figures": _im_mod_stats(),
    }
