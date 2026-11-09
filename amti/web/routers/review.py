"""审阅工作台路由。

审阅状态与“编辑过”分开：`review_status + reviewed_hash`。队列/抽样/统计都走
`amti.review`，这里只负责把题目序列化成前端要的形状。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from amti import review as review_mod
from amti import store
from amti.web.core import _rm_apply
from amti.web.present import brief, stage_of
from amti.web.retry import retry_on_concurrent

router = APIRouter(prefix="/api/review", tags=["review"])


class ReviewDecisionItem(BaseModel):
    model_config = {"extra": "forbid"}
    key: str
    status: str
    note: str = ""


class ReviewDecisionBody(BaseModel):
    model_config = {"extra": "forbid"}
    items: list[ReviewDecisionItem]
    reviewer: str = ""
    batch_id: str = ""


class ReviewSampleBody(BaseModel):
    model_config = {"extra": "forbid"}
    n: int = 100
    seed: int | None = None
    book: str = ""
    type: str = ""
    year_from: int = 0
    risk: str = ""


def _review_item(q, it: dict | None = None, **extra) -> dict:
    b = brief(q)
    b["review"] = review_mod.info(q) if it is None else it
    b["stage"] = stage_of(q)
    b.update(extra)
    return b


@router.get("/stats")
def review_stats() -> dict:
    """审阅进度与抽样批次错误率（Wilson 95% CI）。"""
    return review_mod.stats(store.load_cached())


@router.get("/queue")
def review_queue(
    status: str = "pending",       # pending（含 stale）/ approved / needs_fix / flagged / all
    risk: str = "",                # high / medium / low
    book: str = "",
    type: str = "",
    year_from: int = 0,
    kw: str = "",
    sort: str = "risk",            # risk / old / year
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """风险优先的待审队列。返回**完整题面**（审阅要看答案/解析）。"""
    total, rows = review_mod.queue(
        store.load_cached(), status=status, risk_tier=risk, book=book,
        type=type, year_from=year_from, kw=kw, sort=sort,
        limit=limit, offset=offset)
    return {"total": total, "items": [_review_item(q, it) for q, it in rows]}


@router.post("/sample")
def review_sample(body: ReviewSampleBody) -> dict:
    """分层抽样：按 book × 题型比例抽，固定 seed 可复现。只读，不写库。"""
    res = review_mod.sample(
        store.load_cached(), body.n, body.seed, book=body.book,
        type=body.type, year_from=body.year_from, risk_tier=body.risk)
    items = [
        _review_item(q, it, stratum=stratum, stratum_n=stratum_n,
                     sample_n=sample_n)
        for q, it, stratum, stratum_n, sample_n in res["items"]
    ]
    return {
        "batch_id": res["batch_id"],
        "seed": res["seed"],
        "requested": res["requested"],
        "population": res["population"],
        "strata": res["strata"],
        "items": items,
    }


@router.post("/decision")
@retry_on_concurrent
def review_decision(body: ReviewDecisionBody) -> dict:
    r"""保存一批审阅决定。**一次写回**，可跨多卷。

    `pending` = 撤销/收回；approved / needs_fix / flagged = 记复核。
    写入同时记录 `reviewed_hash`，正文一变就自动 stale。
    """
    if not body.items:
        raise HTTPException(400, "items 不能为空")
    if len(body.items) > 200:
        raise HTTPException(400, "一次最多保存 200 道（再多就分批）")
    seen = set()
    for it in body.items:
        if it.status not in review_mod.STATUSES:
            raise HTTPException(400, "审阅状态只能是 %s，收到 %r"
                                % (" / ".join(review_mod.STATUSES), it.status))
        if it.key in seen:
            raise HTTPException(400, "同一批里重复的题：%s" % it.key)
        seen.add(it.key)

    keys = [it.key for it in body.items]
    # 审阅决定不改 key/正文：只读/只写命中的卷，不必把全库拉进来。
    by, vols, chunks, sig = store.read_many_map(keys)
    missing = [k for k in keys if k not in by]
    if missing:
        raise HTTPException(404, "有 %d 道题找不到：%s"
                            % (len(missing), "、".join(missing[:3])))
    before = {k: by[k].content_hash() for k in keys}
    changed = []
    for it in body.items:
        q = by[it.key]
        review_mod.apply_decision(q, it.status, note=it.note,
                                  reviewer=body.reviewer,
                                  batch=body.batch_id)
        changed.append(q)

    store.write_many(changed, volumes=vols, chunks=chunks,
                     expect_hashes=before, expect_sig=sig)
    _rm_apply(keys, sig, {q.key: q for q in changed})
    return {
        "ok": True, "saved": len(keys),
        "items": [{"key": q.key, "review": review_mod.info(q)}
                  for q in changed],
    }
