"""试卷存档 / 合集的 HTTP 路由。

从 `server.py` 拆出来的第一组：只依赖 `amti.papers`，不碰题目存储和渲染，
是最低风险的一块。响应模型也在这里定义，接口契约跟着路由走。
"""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from amti import papers as P

router = APIRouter(prefix="/api/papers", tags=["papers"])


class PaperRecord(BaseModel):
    """一份存档。存档里只存题号，`keys` 是原样还原的依据。"""

    name: str
    title: str = ""
    kind: str = "试卷"
    mode: str = "gaokao"
    keys: list[str] = Field(default_factory=list)
    n: int = 0
    params: dict = Field(default_factory=dict)
    note: str = ""
    at: str = ""
    seq: int = 0
    updated: str | None = None


class PaperList(BaseModel):
    items: list[PaperRecord]


class PaperBody(BaseModel):
    name: str
    keys: list[str] = Field(default_factory=list)
    title: str = ""
    mode: str = "gaokao"
    kind: str = "试卷"          # 试卷 / 合集
    note: str = ""
    params: dict = Field(default_factory=dict)


@router.get("", response_model=PaperList)
def papers_list() -> dict:
    r"""出过的卷子 + 合集，按时间倒序。"""
    return {"items": P.all_items()}


@router.post("", response_model=PaperRecord)
def papers_save(b: PaperBody) -> dict:
    """存一份卷子，或把挑好的题存成**合集**。"""
    if not b.name.strip():
        raise HTTPException(400, "得给个名字")
    return P.add(b.name.strip(), b.keys, title=b.title or b.name, mode=b.mode,
                 kind=b.kind, note=b.note, params=b.params)


@router.get("/{name:path}", response_model=PaperRecord)
def papers_get(name: str) -> dict:
    d = P.get(urllib.parse.unquote(name))
    if not d:
        raise HTTPException(404, "没有这份存档")
    return d


@router.delete("/{name:path}")
def papers_delete(name: str) -> dict:
    return {"ok": P.remove(urllib.parse.unquote(name))}
