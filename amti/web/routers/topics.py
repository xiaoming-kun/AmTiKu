"""专题 / 讲义 / 教材知识地图 / 开源讲义路由。

这组只读 `topics` / `knowledge_map` / `open_lectures`，写操作也只有专题
选题和讲义 tex 副本；不碰题目存储。`_brief_cached` 等列表 helper 已抽到
`amti.web.core`，所以 router 不需要 import server。
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from amti import knowledge
from amti import knowledge_map
from amti import lecture_html
from amti import open_lectures
from amti import topic_export as topic_export_mod
from amti import topics
from amti.logutil import get_logger
from amti import store
from amti.web.core import _STAGE_NAMES, _brief_cached, _point_stage, _stage_set

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["topics"])


class TopicQs(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)
    place_after: str = ""


class TopicTex(BaseModel):
    tex: str


class NewTopicBody(BaseModel):
    point: str = ""          # 可选：关联一个高中考点；不绑定也可以建
    title: str = ""
    topic: str = ""
    section: str = ""


_NEW_LOCK = threading.Lock()


def _tex_escape(s: str) -> str:
    return (s.replace("\\", r"\textbackslash{}")
             .replace("&", r"\&").replace("%", r"\%")
             .replace("#", r"\#").replace("_", r"\_")
             .replace("{", r"\{").replace("}", r"\}"))


@router.post("/topics/new")
def topic_new(body: NewTopicBody) -> dict:
    r"""从高中考点新建一份讲义骨架。

    TeX 仍是唯一真相：这里只生成一个合法的 elegantbook 骨架，正文/题目
    由用户在阅读器里继续补。不覆盖已有讲义，不碰小初章节（小初由
    `lecture_tex` 从章节目录生成）。
    """
    point = body.point.strip()
    if point and not re.fullmatch(r"\d+(?:\.\d+)*", point):
        raise HTTPException(400, "考点 id 不合法")
    k = knowledge.get(point) if point else None
    if point and not k:
        raise HTTPException(404, "没有这个高中考点")
    title = body.title.strip() or (knowledge.title_of(point) if point else "") or "新建讲义"
    if "/" in title or "#" in title:
        raise HTTPException(400, "标题里不能有 / 或 #")
    # 允许多份讲义关联同一个考点（例如“基础版/提高版”）；id 用时间戳，
    # 不和考点 id 抢唯一键。
    tid = "new-" + time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:4]
    tex_path = topics.TOPIC_DIR / f"{tid}.tex"
    # 复用现有讲义的导言区，保证版式/字体/图片路径一致。
    base = topics.TOPIC_DIR / "1.1.1.tex"
    if not base.is_file():
        cands = sorted(topics.TOPIC_DIR.glob("*.tex"))
        base = cands[0] if cands else None
    if not base:
        raise HTTPException(500, "没有可复用的讲义模板")
    raw = base.read_text(encoding="utf-8")
    if "\\begin{document}" not in raw:
        raise HTTPException(500, "讲义模板不合法")
    preamble = raw.split("\\begin{document}", 1)[0]
    t = _tex_escape(title)
    preamble = re.sub(r"\\title\{[^}]*\}", r"\\title{%s}" % t, preamble, count=1)
    preamble = re.sub(r"\\subtitle\{[^}]*\}",
                      r"\\subtitle{%s}" % _tex_escape((k or {}).get("topic", "") or body.topic.strip() or "自建讲义"), preamble, count=1)
    preface = ["\\begin{document}",
               "\\renewcommand{\\lecturenumber}{%s}" % (point or ""),
               "\\chapter{%s}" % t,
               "\\begin{introduction}"]
    for key in ("核心概念", "核心公式/记号", "常用方法", "常考题型", "易错点"):
        if ((k or {}).get("fields") or {}).get(key):
            preface.append("\t\\item %s" % _tex_escape(key))
    preface += ["\\end{introduction}", "", "\\section{%s}" % t,
                "本节内容待补充。可以在阅读器里点击段落直接编辑。",
                "", "\\section{本节小结}",
                "\\begin{proposition}[本节小结]",
                "在这里补三条最重要的结论。",
                "\\end{proposition}", "", "\\end{document}"]
    tex = preamble + "\n".join(preface) + "\n"
    with _NEW_LOCK:
        if tex_path.exists():
            raise HTTPException(409, "讲义源已存在")
        tmp = tex_path.with_suffix(".tex.tmp")
        tmp.write_text(tex, encoding="utf-8")
        tmp.replace(tex_path)
        mp = topics.MANIFEST
        data = json.loads(mp.read_text(encoding="utf-8")) if mp.is_file() else {"topics": []}
        entry = {
            "id": tid, "title": title,
            "topic": (k or {}).get("topic", "") or body.topic.strip() or "自建讲义",
            "section": (k or {}).get("section", "") or body.section.strip() or "未分类",
            "stage": "senior", "stars": (k or {}).get("stars", 0),
            "difficulty": (k or {}).get("difficulty", "") or "待定",
            "pdf": f"{tid}.pdf", "tex": f"{tid}.tex", "summary": [],
            "questions": [], "pre": [], "post": [],
            "points": [point] if point else [],
        }
        data.setdefault("topics", []).append(entry)
        data["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        mt = mp.with_suffix(".json.tmp")
        mt.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        mt.replace(mp)
    topics.reload()
    # 先出网页版；PDF 仍可在保存/导出时再编译。
    try:
        lecture_html.build(tid, force=True)
    except Exception:
        log.warning("新讲义网页版生成失败：%s", tid, exc_info=True)
    return {"ok": True, "id": tid, "title": title}


@router.get("/topics")
def topics_list(stage: str = "") -> dict:
    """考点专题/讲义列表（不含题目正文）。"""
    stage_set = _stage_set(stage)
    out = []
    pm = _point_stage()
    for t in topics.load():
        tid = str(t.get("id") or "")
        st = str(t.get("stage") or pm.get(tid, "senior"))
        if stage_set and st not in stage_set:
            continue
        d = {k: v for k, v in t.items() if k != "questions"}
        d["n"] = len(t.get("questions") or [])
        d["stage"] = st
        out.append(d)
    return {"topics": out}


@router.post("/topics/{tid}/questions")
def topic_questions(tid: str, body: TopicQs) -> dict:
    """在专题里添加/移出题目（写 数据/专题/选题/，不动 manifest）。"""
    t0 = topics.get(tid)
    if t0 is None:
        raise HTTPException(404, "没有这个专题")
    if t0.get("stage") in ("primary", "junior"):
        raise HTTPException(400, "小初章节讲义不接练习")
    by_key = {q.key for q in store.load_cached()}
    add = [k for k in body.add if k in by_key]
    bad = [k for k in body.add if k not in by_key]
    t = topics.update_questions(tid, add, body.remove, body.place_after)
    return {"ok": True, "n": len(t.get("questions") or []), "skipped": bad}


HISTORY_DIR = topics.TOPIC_DIR / "历史"


def _snapshot_tex(tid: str, tex: str) -> None:
    """保存前留一份源快照，最多 20 份；直接点段落改错时还能回退。"""
    if not tex:
        return
    d = HISTORY_DIR / tid
    d.mkdir(parents=True, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4] + ".tex"
    (d / name).write_text(tex, encoding="utf-8")
    old = sorted(d.glob("*.tex"), key=lambda p: p.stat().st_mtime)
    for p in old[:-20]:
        try: p.unlink()
        except OSError: pass


def _save_tex(tid: str, t: dict, tex: str) -> dict:
    p = topics.TOPIC_DIR / t["tex"]
    if p.is_file():
        _snapshot_tex(tid, p.read_text(encoding="utf-8"))
    p.write_text(tex, encoding="utf-8")
    out = lecture_html.build(tid, force=True)
    if not out:
        raise HTTPException(500, "已保存，但重新生成网页版失败（检查 LaTeX）")
    return {"ok": True, "html": out.read_text(encoding="utf-8")}


@router.get("/topics/{tid}/tex")
def topic_tex(tid: str) -> dict:
    """取讲义的 LaTeX 源（用于「改讲义」）。"""
    t = topics.get(tid)
    if not t or not t.get("tex"):
        raise HTTPException(404, "这个专题没有讲义源")
    p = topics.TOPIC_DIR / t["tex"]
    if not p.is_file():
        raise HTTPException(404, "讲义源不见了")
    return {"tex": p.read_text(encoding="utf-8")}


@router.post("/topics/{tid}/tex")
def topic_tex_save(tid: str, body: TopicTex) -> dict:
    """保存讲义源并重新生成网页版。只写 数据/专题/ 里的副本。"""
    t = topics.get(tid)
    if not t or not t.get("tex"):
        raise HTTPException(404, "这个专题没有讲义源")
    tex = body.tex or ""
    if len(tex) > 400_000:
        raise HTTPException(400, "讲义源太大")
    if "\\begin{document}" not in tex or "\\end{document}" not in tex:
        raise HTTPException(400, "讲义源缺 \\begin{document} / \\end{document}")
    return _save_tex(tid, t, tex)


@router.get("/topics/{tid}/history")
def topic_history(tid: str) -> dict:
    t = topics.get(tid)
    if not t or not t.get("tex"):
        raise HTTPException(404, "这个专题没有讲义源")
    d = HISTORY_DIR / tid
    out = []
    for p in sorted(d.glob("*.tex"), key=lambda x: x.stat().st_mtime, reverse=True) if d.is_dir() else []:
        try:
            out.append({"name": p.name, "mtime": int(p.stat().st_mtime), "size": p.stat().st_size})
        except OSError:
            continue
    return {"versions": out[:20]}


class RestoreTex(BaseModel):
    name: str


@router.post("/topics/{tid}/restore")
def topic_restore(tid: str, body: RestoreTex) -> dict:
    t = topics.get(tid)
    if not t or not t.get("tex"):
        raise HTTPException(404, "这个专题没有讲义源")
    name = body.name.strip()
    if not re.fullmatch(r"[0-9A-Za-z_.-]+\.tex", name):
        raise HTTPException(400, "版本名不合法")
    p = HISTORY_DIR / tid / name
    if not p.is_file():
        raise HTTPException(404, "这个版本不存在")
    try:
        tex = p.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(404, "这个版本读不出来")
    if len(tex) > 400_000 or "\\begin{document}" not in tex or "\\end{document}" not in tex:
        raise HTTPException(400, "这个版本不是合法讲义")
    return _save_tex(tid, t, tex)


@router.get("/topics/{tid}/lecture")
def topic_lecture(tid: str) -> dict:
    """网页版讲义（HTML 片段，公式交给前端 KaTeX）。"""
    p = lecture_html.build(tid)
    if not p:
        raise HTTPException(404, "这份讲义还没有网页版")
    return {"html": p.read_text(encoding="utf-8")}


@router.get("/topics/{tid}/lecture/{name}.png")
def topic_lecture_fig(tid: str, name: str):
    """网页版讲义里的 TikZ 图（单独编译成 PNG）。"""
    if not re.fullmatch(r"fig-\d+", name):
        raise HTTPException(404, "没有这张图")
    p = lecture_html.LECT_DIR / tid / f"{name}.png"
    if not p.is_file():
        raise HTTPException(404, "没有这张图")
    return FileResponse(p, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/topics/{tid}/page/{n}")
def topic_page(tid: str, n: int):
    """讲义第 n 页的 PNG。"""
    p = topics.page_png(tid, n)
    if not p:
        raise HTTPException(404, "没有这一页")
    return FileResponse(p, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/topics/{tid}/export")
def topic_export_pdf(tid: str, answers: int = 1):
    """导出「讲义 + 配套练习」PDF。"""
    t = topics.get(tid)
    if t and t.get("stage") in ("primary", "junior"):
        raise HTTPException(400, "小初章节讲义不接练习，没有讲练 PDF")
    try:
        p = topic_export_mod.build_pdf(tid, bool(answers))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    ver = "teacher" if answers else "student"
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{tid}-{ver}.pdf"'})


@router.get("/topics/{tid}/pdf")
def topic_pdf(tid: str):
    """讲义 PDF：浏览器内置阅读器打开。"""
    p = topics.pdf_path(tid)
    if not p:
        raise HTTPException(404, "这个专题还没有讲义")
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{tid}.pdf"'})


@router.get("/topics/{tid}")
def topic_detail(tid: str) -> dict:
    """一个专题：讲义元信息 + 五要素 + 精选题。"""
    t = topics.get(tid)
    if not t:
        raise HTTPException(404, "没有这个专题")
    by_key = {q.key: q for q in store.load_cached()}
    qs = []
    for k in t.get("questions") or []:
        q = by_key.get(k)
        if q is not None:
            qs.append(_brief_cached(q))
    out = {k: v for k, v in t.items() if k != "questions"}
    out["pages"] = topics.page_count(tid)
    out["stage"] = str(t.get("stage") or _point_stage().get(tid, "senior"))
    return {"topic": out, "questions": qs}


@router.get("/map/questions/{pid}")
def map_questions(pid: str) -> dict:
    """单个小学/初中知识点的诊断题。"""
    d = knowledge_map.questions(pid)
    if not d:
        raise HTTPException(404, "没有这个知识点")
    return d


@router.get("/map")
def knowledge_map_tree() -> dict:
    """教材知识地图：学段 → 年级/册 → 章 → 知识点。"""
    return knowledge_map.tree()


@router.get("/open-lectures")
def open_lectures_list(stage: str = "") -> dict:
    return open_lectures.list_for_stage(stage)


@router.get("/open-lectures/{lid}/asset/{path:path}")
def open_lecture_asset(lid: str, path: str):
    import mimetypes
    p = open_lectures.asset_path(lid, path)
    if not p:
        raise HTTPException(404, "没有这张图")
    mt = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=mt,
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/open-lectures/{lid}/pdf")
def open_lecture_pdf(lid: str):
    p = open_lectures.pdf_path(lid)
    if not p:
        raise HTTPException(404, "这份讲义没有 PDF")
    return FileResponse(p, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{lid}.pdf"'})


@router.get("/open-lectures/{lid}")
def open_lecture_detail(lid: str) -> dict:
    d = open_lectures.detail(lid)
    if not d:
        raise HTTPException(404, "没有这份开源讲义")
    return d
