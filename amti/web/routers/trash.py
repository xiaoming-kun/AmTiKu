"""回收站路由。

删除不是真删：移进 `回收站/回收站.json`（存整道题），随时能恢复；
只有 `purge` 不可逆。请求/响应模型和路由放在一起，接口契约跟着业务域走。
"""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from amti import trash as T
from amti.schema import NO_SOLUTION_MARKS

router = APIRouter(prefix="/api", tags=["trash"])


class TrashBody(BaseModel):
    keys: list[str] = Field(default_factory=list)
    reason: str = ""
    password: str = ""                  # 清空要口令；删除/恢复不要


class BatchDeleteBody(TrashBody):
    pass


class TrashItem(BaseModel):
    key: str
    deleted_at: str = ""
    reason: str = ""
    type: str = ""
    stem: str = ""
    has_solution: bool = False
    has_answer: bool = False
    points: list[str] = Field(default_factory=list)


class TrashList(BaseModel):
    items: list[TrashItem]
    count: int


class TrashReasons(BaseModel):
    items: list[str]


@router.post("/questions/{key:path}/trash")
def question_trash(key: str, body: TrashBody) -> dict:
    """把一道题移进回收站。**不需要口令**（删除可恢复）。"""
    r = T.delete([urllib.parse.unquote(key)], reason=body.reason.strip())
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


@router.post("/trash")
def trash_delete_batch(body: BatchDeleteBody) -> dict:
    r"""**批量删题**。一次移进回收站，和单题删除同一套规矩：原因必选 + 整批原子。"""
    r = T.delete(body.keys, reason=body.reason.strip())
    if not r["ok"]:
        raise HTTPException(400, r["error"])
    return r


@router.get("/trash/reasons", response_model=TrashReasons)
def trash_reasons() -> dict:
    """删题的**原因选项**。界面照着渲染，不在前端再抄一份。"""
    return {"items": T.DELETE_REASONS}


@router.get("/trash", response_model=TrashList)
def trash_list() -> dict:
    """回收站内容。带原题题干，好认。"""
    items = []
    for x in T.all_items():
        q = x.get("question") or {}
        _sol = (q.get("solution") or "").strip()
        items.append({
            "key": x["key"], "deleted_at": x.get("deleted_at", ""),
            "reason": x.get("reason", ""), "type": q.get("type", ""),
            "stem": (q.get("stem") or "")[:200],
            # 与 `Question.has_solution` 同一口径：占位符不算解析
            "has_solution": bool(_sol) and _sol not in NO_SOLUTION_MARKS,
            "has_answer": bool((q.get("answer") or "").strip()),
            "points": q.get("points") or [],
        })
    return {"items": items, "count": len(items)}


@router.post("/trash/restore")
def trash_restore(body: TrashBody) -> dict:
    """恢复。**整批原子**：有一条对不上就整批不动。"""
    r = T.restore(body.keys)
    if not r["ok"]:
        raise HTTPException(400, r["error"] + "：" + "、".join(
            r.get("not_found", []) + r.get("clash", [])))
    return r


@router.post("/trash/delete", deprecated=True)
def trash_delete_batch_legacy(body: BatchDeleteBody) -> dict:
    """旧路径 → 同 `POST /api/trash`。"""
    return trash_delete_batch(body)


@router.delete("/trash")
def trash_purge_rest(body: BatchDeleteBody) -> dict:
    """REST 版清空：旧路径 `/api/trash/purge` 保留。"""
    return trash_purge(body)


@router.post("/trash/purge", deprecated=True)
def trash_purge(body: TrashBody) -> dict:
    """**真删**，之后恢复不了。`keys` 为空 = 清空整个回收站。"""
    r = T.purge(body.keys or None, password=body.password, confirm_all=True)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or "清空失败")
    return r
