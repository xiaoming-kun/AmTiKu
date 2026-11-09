"""系统状态 / 变更记录 / 基线 / 设置 / 检索状态路由。

这些端点原来夹在 server.py 的静态文件挂载之前，依赖心跳和基线两份进程级
状态；状态已抽到 `amti.web.runtime`，这里不再 import server。
"""
from __future__ import annotations

import time
import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from amti import fts
from amti import store
from amti.audit import CHANGE_DIR
from amti.paths import OUT_DIR, kind_of
from amti.version import __version__
from amti.web import runtime

router = APIRouter(prefix="/api", tags=["meta"])


class ChangeItem(BaseModel):
    name: str
    rule: str
    at: str
    bytes: int
    mtime: float


class ChangesResponse(BaseModel):
    items: list[ChangeItem]


class ChangeDetail(BaseModel):
    name: str
    text: str


class SettingsResponse(BaseModel):
    out_dir: str
    version: str
    out_name: str
    kinds: dict[str, str]


class SearchStatus(BaseModel):
    exists: bool
    n: int
    current: bool
    bytes: int


class SnapshotResponse(BaseModel):
    ok: bool
    questions: int
    at: str


@router.post("/alive")
def alive() -> dict:
    """页面每几秒 ping 一次。"""
    if not runtime.PING_SEEN[0]:
        print("浏览器已连接 —— 关掉页面服务会自动退出", flush=True)
    runtime.LAST_PING[0] = time.monotonic()
    runtime.PING_SEEN[0] = True
    return {"ok": True}


@router.post("/gone")
def gone() -> dict:
    r"""页面说它要走了（`navigator.sendBeacon`）。

    不能立刻退：`pagehide` 在刷新时也会触发，所以只把倒计时缩短到
    `GONE_GRACE_SEC` 秒——刷新来得及接上，真关掉也只是多等几秒。
    """
    runtime.LAST_PING[0] = time.monotonic() - (
        runtime.EXIT_IDLE_SEC - runtime.GONE_GRACE_SEC)
    print("页面说要走 —— %d 秒内没有新的心跳就退出"
          % runtime.GONE_GRACE_SEC, flush=True)
    return {"ok": True}


@router.post("/snapshot", response_model=SnapshotResponse)
def update_snapshot() -> dict:
    r"""把当前状态存成新基线。

    基线的用途是"我上次确认过的题，之后有没有被悄悄改动"。
    每次有意改完数据都该更新一次。这个动作**不改任何题目**，只记指纹。
    """
    d = store.snapshot()
    # 快照变了，「基线与现状的差」也就变了；`BASE` 只按卷签名失效，
    # 而存基线不动任何卷——不清缓存的话前端刷新后仍显示旧数。
    runtime.BASE["key"] = None
    runtime.BASE["v"] = None
    return {"ok": True, "questions": d["questions"],
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/changes", response_model=ChangesResponse)
def changes() -> dict:
    r"""变更记录列表（`变更记录/*.md`）。"""
    if not CHANGE_DIR.is_dir():
        return {"items": []}
    items = []
    for f in sorted(CHANGE_DIR.glob("*.md"), reverse=True):
        st = f.stat()
        parts = f.stem.split("_", 2)
        stamp = parts[0]
        if len(parts) >= 2:
            stamp = "%s-%s-%s %s:%s" % (
                parts[0][:4], parts[0][4:6], parts[0][6:8],
                parts[1][:2], parts[1][2:4])
        items.append({
            "name": f.name,
            "rule": parts[2] if len(parts) > 2 else f.stem,
            "at": stamp,
            "bytes": st.st_size,
            "mtime": st.st_mtime,
        })
    return {"items": items}


@router.get("/changes/{name:path}", response_model=ChangeDetail)
def change_detail(name: str) -> dict:
    """只允许读 变更记录/ 里的 .md，防目录穿越。"""
    f = (CHANGE_DIR / urllib.parse.unquote(name)).resolve()
    if CHANGE_DIR.resolve() not in f.parents or f.suffix != ".md" or not f.is_file():
        raise HTTPException(404, "没有这份记录")
    return {"name": f.name, "text": f.read_text(encoding="utf-8")}


@router.get("/baseline")
def baseline() -> dict:
    """冻结基线的状态——UI 顶部常驻显示「存量题有没有被改」。"""
    sig = store._vol_signature()
    if runtime.BASE["key"] == sig and runtime.BASE["v"] is not None:
        return runtime.BASE["v"]
    d = store.diff()
    v = {"基线": d["基线题数"], "当前": d["当前题数"],
         "新增": len(d["新增"]),
         "内容变化": len(d["内容变化"]),
         "删除": len(d["删除"]),
         "求解写入": len(d.get("求解写入", [])),
         "录入升级": len(d.get("录入升级", [])),
         "界面补录": len(d.get("界面补录", [])),
         "规则迁移": len(d.get("规则迁移", [])),
         "变动清单": d["内容变化"][:20]}
    runtime.BASE["key"] = sig
    runtime.BASE["v"] = v
    return v


@router.get("/settings", response_model=SettingsResponse)
def settings() -> dict:
    """界面要知道的只读设置：导出位置 + 分类子目录 + 版本。"""
    return {"out_dir": str(OUT_DIR),
            "version": __version__,
            "out_name": OUT_DIR.name or str(OUT_DIR),
            "kinds": {m: kind_of(m)
                      for m in ("gaokao", "test", "coverage", "handout")}}


@router.get("/search/status", response_model=SearchStatus)
def search_status() -> dict:
    """检索索引状态：在不在、多少条、是不是当前卷签名、占多少字节。"""
    return fts.status()
