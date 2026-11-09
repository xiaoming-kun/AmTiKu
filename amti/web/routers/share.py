"""AmTiKu · 分享包路由

- `POST /api/share/export`：选中的 key → zip 字节（不落盘）
- `POST /api/share/import`：原始 zip body → 导入报告；同 key 跳过，不覆盖

导入用**原始 body**（`Content-Type: application/zip`），不引入
`python-multipart`；前端直接 `fetch(url, {body: file})`。
"""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from amti import sharepack

router = APIRouter(prefix="/api/share", tags=["share"])


class ShareExportBody(BaseModel):
    name: str = "分享包"
    keys: list[str] = []


@router.post("/export")
def share_export(body: ShareExportBody) -> Response:
    try:
        data, _rep = sharepack.build_pack(body.keys, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    fn = "amti-share.zip"
    disp = "attachment; filename=%s; filename*=UTF-8''%s" % (
        fn, urllib.parse.quote((body.name or "分享包") + ".amti-pack.zip"))
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": disp})


@router.post("/import")
async def share_import(request: Request, dry_run: bool = False) -> dict:
    data = await request.body()
    if not data:
        raise HTTPException(400, "分享包是空的")
    if len(data) > sharepack.MAX_PACK_BYTES:
        raise HTTPException(413, "分享包超过 200MB")
    try:
        return await run_in_threadpool(sharepack.import_pack, data, dry_run=dry_run)
    except ValueError as e:
        raise HTTPException(400, str(e))
