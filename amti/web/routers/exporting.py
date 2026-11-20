"""导出 / PDF / 图片 / TikZ / 在访达中显示路由。

导出串行化锁原来在 server.py 顶部；跟着导出端点一起搬，避免 router
反向依赖 server。图片透明缓存、题库图片和预览 PDF 都只读数据目录。
"""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from amti.logutil import get_logger
from amti.paths import OUT_DIR, PREVIEW_DIR
from amti.paths import ROOT as PKG
from amti.web.core import _usage_bump

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["export"])

IMG_DIR = PKG / "图片"
TRANSPARENT_CACHE = PKG / "数据" / "缓存" / "transparent"
_EXPORT_LOCK = threading.Lock()


def _serialized_export(fn):
    """导出端点装饰器：串行化执行，且无论如何都释放锁。"""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        lock = _export_guard()
        try:
            return fn(*a, **kw)
        finally:
            lock.release()
    return wrapper


def _export_guard() -> threading.Lock:
    if not _EXPORT_LOCK.acquire(blocking=False):
        raise HTTPException(429, "已有一个导出在进行，请稍候再试")
    return _EXPORT_LOCK


@router.get("/reveal")
def reveal(path: str):
    """在访达中显示。**只允许项目内或导出文件夹里的路径**，防止把任意路径交给 Finder。

    导出位置可以在 `数据/导出位置.txt` 里改到项目外（用户的资料夹），
    所以不能只认 PKG —— 否则导完点「在访达中显示」永远 403。
    """
    import subprocess
    p = Path(path).resolve()
    roots = (PKG.resolve(), OUT_DIR.resolve())
    if not any(r == p or r in p.parents for r in roots):
        raise HTTPException(403, "只能打开项目内或导出文件夹里的文件")
    if not p.exists():
        raise HTTPException(404, f"不存在：{p}")
    subprocess.Popen(["open", "-R", str(p)])
    return {"ok": True, "revealed": str(p)}


class TikzBody(BaseModel):
    tex: str = ""


@router.post("/tikz/render")
def tikz_render(body: TikzBody) -> dict:
    r"""把一段 TikZ 源码渲成 PNG，供录入卡片预览。

    只给**手工作台审题**用：源码来自用户粘贴的材料，先查缓存再编译；
    产物是内容寻址的 `图片/tikz-*.png`。**不写题目**。
    """
    from amti import tikzfig
    tex = (body.tex or "").strip()
    if not tex:
        raise HTTPException(400, "TikZ 源码为空")
    p = tikzfig.png_cached(tex)
    if p is None:
        _pdf, why = tikzfig.render(tex)
        p = tikzfig.png_cached(tex)
        if p is None:
            raise HTTPException(422, "TikZ 渲染失败：%s" % (why or "没有产出 PNG"))
    return {"ok": True, "path": p.name}


@router.get("/ingest/preview-image")
def ingest_preview_image(path: str, src_dir: str = ""):
    r"""干跑时的题图原图。**只读**，且只能读来源目录/默认待录入图片里的文件。

    卡片上的 `\includegraphics` 引用的是**将要复制过去**的内容寻址名，
    这时 `图片/` 里还没有它；没有这个入口，带图题在审阅时是破图。
    """
    from amti import images as im
    roots: list[Path] = []
    if src_dir.strip():
        roots.append(Path(src_dir).expanduser())
    roots.append(im.OLD_IMG)
    raw = Path(path).expanduser()
    candidates = [raw] if raw.is_absolute() else [r / raw for r in roots]
    for c in candidates:
        try:
            c = c.resolve()
            if c.is_file() and any(c.is_relative_to(r.expanduser().resolve()) for r in roots):
                return FileResponse(c)
        except (OSError, ValueError):
            continue
    raise HTTPException(404, "图片不在来源目录里")


@router.get("/figure")
def figure(path: str, raw: int = 0):
    r"""题库图片。

    默认做**白底转透明** —— 题库的图多是白底，贴在米色讲义上会显出一个
    白方块，很突兀。出卷/讲义时也做同样处理，保证预览与导出 PDF 一致。
    传 ?raw=1 拿原图。
    """
    p = (IMG_DIR / path).resolve()
    if not str(p).startswith(str(IMG_DIR.resolve())) or not p.exists():
        raise HTTPException(404, f"没有这张图：{path}")
    if raw:
        return FileResponse(p)

    # 处理结果缓存到 `数据/缓存/transparent`（见 TRANSPARENT_CACHE）
    cache_dir = TRANSPARENT_CACHE
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        dst = cache_dir / p.name
        if not dst.exists() or dst.stat().st_mtime < p.stat().st_mtime:
            from PIL import Image
            import numpy as np
            im = Image.open(p).convert("RGBA")
            a = np.array(im)
            r, g, b, alpha = a[:, :, 0], a[:, :, 1], a[:, :, 2], a[:, :, 3]
            near_white = (r > 242) & (g > 242) & (b > 242)
            a[:, :, 3] = np.where(near_white, 0, alpha)
            Image.fromarray(a).save(dst)
        return FileResponse(dst, media_type="image/png")
    except Exception:
        log.debug("图片透明处理失败，返回原图：%s", "", exc_info=True)
        return FileResponse(p)          # 处理失败就给原图，不阻断


# ── 导出 ──────────────────────────────────────────────────────────────

class ExportBody(BaseModel):
    title: str = ""
    out: str = ""                       # 文件名，留空用「标题_时间戳」
    keys: list[str] = []                # 选的题
    show_answers: bool = False
    show_source: bool = True            # 题干第一行印出处（年份/卷别，不含原卷题号）
    answers_at_end: bool = False        # 答案与解析统一放卷末（真高考卷的做法）
    handout_font: str = ""              # 讲义字号，见 paper.HANDOUT_SIZES
    bottom_sep: str = ""                # 题目间距，如 "0.6em"
    problem_blank_cm: float | None = None
    mode: str = "gaokao"                # gaokao 高考卷 / test 纯测试题 / handout 讲义
    # 分类子目录（试卷 / 测试卷 / 讲义，见 paths.OUT_KINDS）。留空按卷型推；
    # 界面总是显式传（落盘分类跟着界面上的卷型走），所以这里留了口子。
    kind: str = ""
    compile: bool = True
    # 「编译预览」：只编译给人看。产物进 数据/预览/，**不存档、不计使用频次**。
    # 以前预览和导出是同一个请求，点一次预览就在资料夹里留一份 PDF、
    # 还把题目的「用过 N 次」+1（默认排序都跟着变）。
    preview: bool = False
    # 目标时长（分钟）：0 = 不检查；组完只提示“超了/少了”，不自动改题
    target_minutes: int = 120


@router.post("/export")
@_serialized_export
def export(body: ExportBody) -> dict:
    r"""导出套卷。

    **必须回传落盘位置**（`tex_abs`/`pdf_abs`/`dir_abs`）——旧项目导出完
    只说一句"已生成"，用户还得自己去翻文件夹找。
    """
    from amti import export as _ex
    from amti import paper as _paper          # 这个函数里必须自己导入：
    # 原来只在 1580 行的另一个函数里 `from amti import paper as _paper`，
    # 这里用 _paper.HANDOUT_FONT_DEFAULT 却是未定义名。平时不炸是因为下一行
    # 用 `or` 短路（前端总会传 handout_font）；只有不传该字段的 API 调用才会
    # NameError（导出直接 500）。
    r = _ex.export(body.keys, title=body.title, out=body.out,
                   show_answers=body.show_answers, show_source=body.show_source,
                   answers_at_end=body.answers_at_end,
        handout_font=body.handout_font or _paper.HANDOUT_FONT_DEFAULT,
                   bottom_sep=body.bottom_sep or "0.6em",
                   problem_blank_cm=(body.problem_blank_cm
                                     if body.problem_blank_cm is not None else 4.0),
                   do_compile=body.compile, mode=body.mode, kind=body.kind,
                   preview=body.preview,
                   )
    if not r.get("ok") and r.get("error"):
        raise HTTPException(400, r["error"])
    # 预览**不计**使用频次：那是"看一眼排版"，不代表这套题被用出去了。
    if not body.preview:
        _usage_bump(body.keys)                  # ← 试卷导出计入频次
    # 前端预览 `<iframe>` 直接用这个地址（普通导出走导出位置，预览走预览目录）。
    if r.get("pdf_rel"):
        from urllib.parse import quote as _q
        r["pdf_url"] = ("/api/pdf?path=" + _q(r["pdf_rel"])
                        + ("&root=preview" if r.get("preview") else ""))
    return r


class DocxBody(BaseModel):
    keys: list[str] = []
    title: str = ""
    show_answers: bool = False
    answers_at_end: bool = False
    show_source: bool = True


@router.post("/export/docx")
@_serialized_export
def export_docx(body: DocxBody) -> dict:
    r"""导出可编辑 Word。走 Markdown → Pandoc，公式为 OMML。

    和 PDF 是两条渲染路径（PDF 仍走 exam-zh）；Word 里不保证 TikZ/复杂
    版式，但题干、选项、答案、解析和图片都有。Pandoc 没装就明确报错。
    """
    from amti import docx_export
    r = docx_export.export_docx(
        body.keys, title=body.title, show_answers=body.show_answers,
        answers_at_end=body.answers_at_end, show_source=body.show_source)
    if not r.get("ok"):
        raise HTTPException(400, r.get("error") or "Word 导出失败")
    _usage_bump(body.keys)
    from urllib.parse import quote as _q
    r["docx_url"] = "/api/docx?path=" + _q(r["docx_rel"])
    return r


@router.get("/docx")
def docx(path: str):
    """把导出的 DOCX 发出去；只允许导出目录内。"""
    base = OUT_DIR.resolve()
    p = (base / path).resolve()
    if (base not in p.parents and p != base) or not p.is_file():
        raise HTTPException(404, f"没有这个文件：{path}")
    return FileResponse(
        p, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/pdf")
def pdf(path: str, root: str = "out"):
    r"""预览用：把 PDF 发出去。

    `path` 相对 `root`：默认导出位置（可带分类子目录）；`root=preview`
    是「编译预览」的产物目录（`数据/预览/`，不落用户资料夹）。
    """
    base = (PREVIEW_DIR if root == "preview" else OUT_DIR).resolve()
    p = (base / path).resolve()
    if (base not in p.parents and p != base) or not p.exists():
        raise HTTPException(404, f"没有这个文件：{path}")
    return FileResponse(p, media_type="application/pdf")
