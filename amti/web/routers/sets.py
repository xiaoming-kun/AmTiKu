r"""套卷（原卷）接口。

两个只读接口：

    GET /api/sets                → 套卷列表（按年份新→旧）
    GET /api/sets/{id}           → 一份套卷的题号顺序 + 带块 IR 的题目

题目正文走 `_brief_cached_lite`，和列表页同一份序列化口径；
**不新写解析**，前端拿到的仍然是块 IR。
"""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, HTTPException

from amti import papersets
from amti import store
from amti.logutil import get_logger
from amti.web.core import _brief_cached_lite, _paper_usage, _usage

router = APIRouter(prefix="/api", tags=["sets"])
log = get_logger(__name__)


@router.get("/sets")
def list_sets(q: str = "", stage: str = "", year: str = "",
              limit: int = 0, offset: int = 0) -> dict:
    """套卷列表。`limit=0` 保持旧行为（全量），套卷页传 `limit=50&offset=...`。

    **筛选在后端做**（学段/年份/卷名），分页才有意义：前端若先拿一页再
    按年份筛，会漏掉别的页里的同一年份。
    """
    items = papersets.index(q=q, stage=stage, year=year)
    total = len(items)
    offset = max(offset, 0)
    if limit > 0:
        items = items[offset: offset + limit]
    return {"total": total, "items": items, "years": papersets.years(),
            "limit": limit, "offset": offset}


@router.get("/sets/{sid:path}")
def get_set(sid: str) -> dict:
    name = urllib.parse.unquote(sid)
    it = papersets.get(name)
    if it is None:
        raise HTTPException(404, f"没有这份套卷：{name}")
    keys = it["keys"]
    # 按题号顺序取题：`read_many` 只读这几道，不扫全库。
    by = store.read_many(keys)
    usage, papers = _usage(), _paper_usage()
    items = []
    for k in keys:
        q = by.get(k)
        if q is None:
            continue          # 题被删了/改名了：跳过，不拿空壳占位
        b = _brief_cached_lite(q)
        b["used"] = usage.get(q.key, 0)
        hit = papers.get(q.key)
        if hit:
            b["papers"] = hit
        # 原卷题号：套卷里显示「第 7 题」用它，而不是列表序号
        b["source_no"] = (q.meta or {}).get("source_no") or ""
        items.append(b)
    return {**{k: v for k, v in it.items() if k != "keys"},
            "keys": keys, "items": items}
