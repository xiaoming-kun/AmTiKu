"""AI 录题 / 读图 / 本地模型 / 录入 / 预标注路由。

这些端点大多只读或写独立配置文件；真正写题库仍然只走 `amti.ingest`。
AI 任务的进程级状态（job 表 / 取消信号）放在本模块，server 只重导出给
旧测试用，不再自己维护一份。
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from amti import fts as fulltext
from amti import latex_blocks as lb
from amti import store
from amti.logutil import get_logger
from amti.web.core import _rm_apply
from amti.web.runtime import INFLIGHT as _INFLIGHT

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["ai"])


class IngestBody(BaseModel):
    text: str = ""                      # 源材料（LaTeX）
    book: str = "手工录入"
    label: str = ""                     # 出处，如 "第14套武汉三调"
    region: str = ""
    year: int | None = None
    source_no: str = ""
    src_dir: str = ""                   # 图片来源目录，留空用默认
    points: str = ""                    # 考点 id，逗号分隔（界面上选的）
    difficulty: str = ""                # 简单题/中档题/难题（界面上选的）
    qtype: str = ""                     # 题型（界面上选的）；留空=按正文推断
    # 手工录入规则：库里已有同题 → 整题跳过，不新增、不更新。
    # 这两个字段保留只为兼容旧客户端；`/api/ingest/commit` 会固定按 False 执行。
    update_existing: bool = False
    update_force: bool = False
    merge_into: dict = {}               # {新题key: 库内key} —— 旧界面/脚本用
    merge_blocks: dict = {}             # {题块下标: 库内key} —— 多题界面用（key 会随出处变）
    items: list[dict] = Field(default_factory=list)  # 逐题覆盖（勾选/考点/难度/题号）
    dup_threshold: float = 0.80
    near_threshold: float = 0.95      # 整题相似 > 这个值 → 不录入；默认 95%
    # 补旧题模式：只给库里已有题补空考点/空难度，不新增、不改正文。
    # 和默认录入规则分开，避免把「已有不更新」的承诺悄悄放开。
    backfill: bool = False


class VlmBody(BaseModel):
    data: str = ""                      # 文件内容的 base64（不带 data: 前缀）
    name: str = "upload.png"            # 只为报错和显示用
    dpi: int = 200                      # PDF 栅格化 dpi



@router.get("/vlm/status")
def vlm_status() -> dict:
    """**读图**服务的现状。**只查，不启动**——启动由 `/api/vlm/extract` 负责。

    ⚠️ 现在的识别链是 **PaddleOCR-VL 认字 → 27B 改格式**（2026-10-27 起
    MinerU 已移除）。这里原来只报 llama.cpp（:1235）那套的"就绪"，
    但这条后备只在没装 Paddle 时才走；装了 Paddle 的机器上界面永远是灰点，
    看起来像"读图不可用"，其实点下去照样能识别。
    """
    from amti import lms as _lms
    from amti import paddle as _paddle
    from amti import vlm as _vlm
    ok_p, why_p = _paddle.available()
    return {
        # 真正决定"按下有没有用"的是：Paddle 装好（走主链），
        # 或者 llama.cpp 读图服务在跑，或者 LM Studio 在跑（27B 顶班）
        "ready": bool(ok_p or _lms.up_vision() or _lms.up()),
        "engine": "paddle+27b" if ok_p else "llama.cpp",
        "paddle": {"installed": ok_p, "why": why_p, "service": _paddle.up()},
        "solve": {"up": _lms.up(), "model": _vlm.SOLVE_MODEL},
        "api": _lms.VISION_API,
        "model": _vlm.MODEL,
        "runtime": "llama.cpp",
        "engine_installed": _lms.LLAMA_SERVER.is_file(),
        "model_files": {
            "model": (_lms.VISION_MODEL.is_file(), str(_lms.VISION_MODEL)),
            "mmproj": (_lms.VISION_MMPROJ.is_file(), str(_lms.VISION_MMPROJ)),
        },
    }


@router.post("/vlm/extract")
def vlm_extract(body: VlmBody) -> dict:
    """图片 / PDF → LaTeX 文本。**只识别，不写库。**

    产物由前端填进录入框，再走 `/api/ingest/preview` → 人工审阅 →
    `/api/ingest/commit`。这样"审阅后才入库"和"存量一个字不变"
    都由 `ingest` 那一条现成管线保证，这里不重复实现。
    """
    import base64 as _b64
    from amti import vlm as _vlm
    if not body.data.strip():
        raise HTTPException(400, "没有收到文件内容")
    try:
        raw = _b64.b64decode(body.data, validate=True)
    except Exception:
        raise HTTPException(400, "文件内容不是合法的 base64")
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(413, "文件太大（>80MB）")
    try:
        return _vlm.extract(raw, body.name, dpi=max(72, min(body.dpi, 400)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        # 模型没配好 / 读不了图 —— 这是**用户要动手修**的事，
        # 所以原文带出去，别吞成"服务器错误"。
        raise HTTPException(503, str(e))


# ══ AI 录题（DeepSeek 读整份资料）═════════════════════════════════════
#
# 四个接口：状态 / 存配置 / 连通性测试 / 跑一次（异步 + 进度轮询）。
#
# **为什么要异步**：一份 100 页的资料要读几分钟到十几分钟。同步接口会让
# 浏览器一直挂着、还可能被看门狗当成"没活干"。所以开线程跑，前端每秒
# 拉一次 `/api/ai/job/{id}`，进度是"已读 N / M 页"。
#
# **为什么不用 multipart**：`/api/vlm/extract` 已经是 base64 JSON，
# 前端那条 `send()` 直接能复用；FastAPI 收文件还要 `python-multipart`
# 这个不在 requirements 里的依赖，为一个接口加一条安装负担不值。

#: 任务表：id → {state, done, total, msg, result, error, at}
_AI_JOBS: dict[str, dict] = {}
#: 取消信号：id → threading.Event。**不放进 _AI_JOBS**，否则轮询接口
#: 会把 Event 一起 JSON 序列化（直接 500）。
_AI_CANCELS: dict[str, threading.Event] = {}
_AI_LOCK = threading.Lock()


class AIBody(BaseModel):
    name: str = "资料.pdf"
    data: str = ""                       # 试题：PDF / 图片的 base64（不带 data: 前缀）
    #: 答案 / 解析——**另一份文件**。一份试题一份答案是最常见的形态，
    #: 不传也能跑（只是缺答案的题会被拦下）。
    answer_name: str = ""
    answer_data: str = ""
    pages_per_call: int = 0              # 0 = 用配置里的


class AIConfigBody(BaseModel):
    api_key: str | None = None           # 不传 = 不动；传空串 = 清空
    base_url: str = ""
    model: str = ""
    pages_per_call: int = 0
    workers: int = 0


@router.get("/ai/status")
def ai_status() -> dict:
    """配没配、什么模型、key 末四位。**永远不回明文 key。**"""
    from amti import deepseek as _ds
    try:
        return {"ok": True, **_ds.status()}
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "configured": False, "detail": str(e)}


@router.post("/ai/config")
def ai_config(body: AIConfigBody) -> dict:
    from amti import deepseek as _ds
    patch: dict = {}
    if body.api_key is not None:
        patch["api_key"] = body.api_key
    for k in ("base_url", "model"):
        v = str(getattr(body, k) or "").strip()
        if v:
            patch[k] = v
    for k in ("pages_per_call", "workers"):
        v = int(getattr(body, k) or 0)
        if v:
            patch[k] = v
    try:
        _ds.save(patch)
    except _ds.AIError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **_ds.status()}


@router.post("/ai/test")
def ai_test() -> dict:
    """连通性测试：一句话、零图片。key 错/余额不足/模型名不对，这里就炸。"""
    from amti import deepseek as _ds
    try:
        return _ds.check()
    except _ds.AIError as e:
        raise HTTPException(400, str(e))


@router.post("/ai/run")
def ai_run(body: AIBody) -> dict:
    """开一个后台任务。**只读不写库**：结果是一段源材料文本。"""
    import base64 as _b64
    from amti import deepseek as _ds
    if not body.data.strip():
        raise HTTPException(400, "没有收到文件内容")
    try:
        raw = _b64.b64decode(body.data, validate=True)
    except Exception:                            # noqa: BLE001
        raise HTTPException(400, "文件内容不是合法的 base64")
    if len(raw) > 200 * 1024 * 1024:
        raise HTTPException(413, "文件太大（>200MB）")
    if not _ds.load()["api_key"]:
        raise HTTPException(400, "还没填 DeepSeek API Key")
    answer_raw = b""
    if body.answer_data.strip():
        try:
            answer_raw = _b64.b64decode(body.answer_data, validate=True)
        except Exception:                        # noqa: BLE001
            raise HTTPException(400, "答案文件的 base64 不合法")
        if len(answer_raw) > 200 * 1024 * 1024:
            raise HTTPException(413, "答案文件太大（>200MB）")

    job_id = "ai-%s" % (time.strftime("%H%M%S") + "-%d" % int(time.time() * 1000 % 1000))
    cancel = threading.Event()
    with _AI_LOCK:
        # 只清**已经结束**的任务；正在跑/正在取消的不能被挤掉——
        # 挤掉后 work() 回来更新 job 会 KeyError，而且用户再也看不到进度。
        finished = [k for k in sorted(_AI_JOBS)
                    if _AI_JOBS[k].get("state") in ("done", "error", "cancelled")]
        for old in finished[:-4]:
            _AI_JOBS.pop(old, None)
            _AI_CANCELS.pop(old, None)
        _AI_JOBS[job_id] = {"state": "queued", "done": 0, "total": 0,
                            "msg": "排队中…", "at": time.time(),
                            "result": None, "error": ""}
        _AI_CANCELS[job_id] = cancel

    def progress(done_pages: int, total_pages: int, msg: str) -> None:
        with _AI_LOCK:
            j = _AI_JOBS.get(job_id)
            # **取消后不能再被 progress 改回 running**——否则界面上的
            # 「正在取消…」会被下一句进度覆盖，用户以为没点上。
            if j is not None and j.get("state") not in ("cancelling", "cancelled"):
                j.update({"state": "running", "done": done_pages,
                          "total": total_pages, "msg": msg})

    def work() -> None:
        from amti import aiingest as _ai
        # 计入"在跑"，看门狗这期间不会把服务退掉（读 100 页要好几分钟）
        _INFLIGHT[0] += 1
        try:
            res = _ai.run(raw, name=body.name,
                          answer_data=answer_raw or None,
                          answer_name=body.answer_name,
                          pages_per_call=body.pages_per_call or None,
                          on_progress=progress,
                          should_stop=cancel.is_set)
            state = "cancelled" if res.get("cancelled") else "done"
            msg = ("已取消：保留已核对 %d 道题" % res["stats"].get("ok", 0)
                   if state == "cancelled" else
                   "读完了：%d 道题通过第二遍核对" % res["stats"]["ok"])
            with _AI_LOCK:
                j = _AI_JOBS.get(job_id)
                if j is not None:
                    j.update({"state": state, "result": res, "msg": msg,
                              "total": res["stats"].get("pages", j.get("total", 0))})
        except _ai.Cancelled as e:
            with _AI_LOCK:
                j = _AI_JOBS.get(job_id)
                if j is not None:
                    j.update({"state": "cancelled", "result": None,
                              "error": str(e) or "已取消", "msg": "已取消"})
        except Exception as e:                   # noqa: BLE001
            with _AI_LOCK:
                j = _AI_JOBS.get(job_id)
                if j is not None:
                    j.update({"state": "error",
                              "error": str(e) or "读不出来",
                              "msg": "失败了"})
        finally:
            _INFLIGHT[0] -= 1
            with _AI_LOCK:
                _AI_CANCELS.pop(job_id, None)

    threading.Thread(target=work, name="ai-ingest", daemon=True).start()
    return {"ok": True, "job": job_id}


@router.get("/ai/job/{job_id}")
def ai_job(job_id: str) -> dict:
    """轮询进度。`state`：queued / running / cancelling / cancelled / done / error。"""
    with _AI_LOCK:
        j = _AI_JOBS.get(job_id)
        if j is None:
            raise HTTPException(404, "任务不存在或已过期，重新点一次")
        out = dict(j)
    out["elapsed"] = int(time.time() - float(out.pop("at", time.time())))
    return out


@router.post("/ai/job/{job_id}/cancel")
def ai_cancel(job_id: str) -> dict:
    """请求取消：**不再发新请求**，已读到的批次保留。

    已经发出去的 HTTP 请求收不回来（仍会计费），所以状态先变
    `cancelling`，线程跑完当前在飞的批次后再变 `cancelled`。
    """
    with _AI_LOCK:
        j = _AI_JOBS.get(job_id)
        if j is None:
            raise HTTPException(404, "任务不存在或已过期，重新点一次")
        if j.get("state") in ("done", "error", "cancelled"):
            return {"ok": True, "state": j["state"]}
        ev = _AI_CANCELS.get(job_id)
        if ev is not None:
            ev.set()
        j.update({"state": "cancelling", "msg": "正在取消…（已发出的请求仍会计费）"})
        return {"ok": True, "state": "cancelling"}


@router.post("/ingest/preview")
def ingest_preview(body: IngestBody) -> dict:
    """**干跑**：解析 + 图片预检 + 查重 + 校验 + 影响面。什么都不写。"""
    from amti import dedup as _dd
    from amti import ingest as _ig
    src = [body.src_dir] if body.src_dir.strip() else None
    pts = [x.strip() for x in body.points.split(",") if x.strip()]
    pv = _ig.preview(body.text, src_dirs=src, book=body.book, label=body.label,
                     region=body.region, year=body.year,
                     source_no=body.source_no, points=pts or None,
                     difficulty=body.difficulty.strip(),
                     qtype=body.qtype.strip(),
                     update_force=body.update_force,
                     merge_into=body.merge_into or None,
                     merge_blocks=body.merge_blocks or None,
                     items=body.items or None,
                     allow_upgrade=(body.backfill
                                    or _ig.MANUAL_INGEST_POLICY["allow_upgrade"]),
                     skip_near=((not body.backfill)
                                and _ig.MANUAL_INGEST_POLICY["skip_near"]),
                     near_threshold=max(0.80, min(1.0, body.near_threshold)),
                     dup_threshold=body.dup_threshold,
                     backfill=body.backfill)
    # 顺带把渲染用的块级 IR 也带上，前端要实时预览
    for it, q in zip(pv["items"], _ig.parse_source(
            body.text, book=body.book, label=body.label,
            region=body.region, year=body.year,
            source_no=body.source_no, points=pts or None,
            difficulty=body.difficulty.strip(),
            qtype=body.qtype.strip(), items=body.items or None)["questions"]):
        it["blocks"] = {
            "stem": lb.parse_blocks(q.stem, parts=True),
            "answer": lb.parse_blocks(q.answer),
            "solution": lb.parse_blocks(q.solution),
            "options": [lb.parse_blocks(o.text) for o in q.options],
        }
    return pv


@router.post("/ingest/commit")
def ingest_commit(body: IngestBody) -> dict:
    """正式导入：图片入库 → 追加主文件。返回变更报告。"""
    from amti import dedup as _dd
    from amti import ingest as _ig
    src = [body.src_dir] if body.src_dir.strip() else None
    pts = [x.strip() for x in body.points.split(",") if x.strip()]
    old_sig = store.volume_signature()
    out = _ig.commit(body.text, src_dirs=src, book=body.book, label=body.label,
                     region=body.region, year=body.year,
                     source_no=body.source_no, points=pts or None,
                     difficulty=body.difficulty.strip(),
                     qtype=body.qtype.strip(),
                     # 默认手工录入的硬规则：库里已有同题 → 跳过，不新增也不更新。
                     # 只有显式 `backfill=True` 才放开「只补空考点/难度」。
                     # LLM 录题走 `ig.commit` 的默认值，不受这个端点影响。
                     update_existing=(body.backfill
                                      or _ig.MANUAL_INGEST_POLICY["update_existing"]),
                     update_force=False,
                     skip_near=((not body.backfill)
                                and _ig.MANUAL_INGEST_POLICY["skip_near"]),
                     near_threshold=max(0.80, min(1.0, body.near_threshold)),
                     backfill=body.backfill,
                     merge_into=body.merge_into or None,
                     merge_blocks=body.merge_blocks or None,
                     items=body.items or None)
    # 录入也是写库：读模型/FTS 能增量就跟上，别让下一屏又回退全量/重建。
    if out.get("ok"):
        touched = list(out.get("added") or [])
        touched += [u.get("dup_key") for u in (out.get("upgraded") or [])
                    if u.get("dup_key")]
        if touched:
            fulltext.apply(touched)
            _rm_apply(touched, old_sig)
    return out


class IngestSourceBody(BaseModel):
    text: str = ""


@router.post("/ingest/source")
def ingest_source(body: IngestSourceBody) -> dict:
    r"""只从源材料**前几行**认标题/年份（`\title{…}` 或第一行纯文本）。

    单独一个轻量接口：不用为了填「出处」先跑一遍整库查重。
    多题录入界面在干跑前先调它，把出处填好，干跑就只跑一次。
    """
    from amti.ingest import extract_source_hint
    return extract_source_hint(body.text)


class IngestTagItem(BaseModel):
    stem: str = ""
    options: list[dict] = Field(default_factory=list)
    type: str = ""


class IngestTagBody(BaseModel):
    items: list[IngestTagItem] = Field(default_factory=list)
    model: str = ""                 # 留空用 qwen3.5-9b-mlx；失败自动回落 27B
    workers: int = 4


class LlmUnloadBody(BaseModel):
    model: str = ""


@router.get("/llm/status")
def llm_status() -> dict:
    r"""标注模型/27B 现在有没有在内存里；只读，不加载。

    用户对 9B 常驻有明确顾虑（默认自动标已关、TTL 30 分钟）；
    界面要能看见“现在到底加载了什么”，并给一个卸载按钮。
    """
    from amti import lms as _lms
    from amti import record2
    rows = _lms.ps_json()
    loaded = [{
        "identifier": r.get("identifier") or r.get("modelKey") or "",
        "model_key": r.get("modelKey") or "",
        "display_name": r.get("displayName") or "",
        "context_length": r.get("contextLength"),
        "ttl_ms": r.get("ttlMs"),
        "status": r.get("status") or "",
        "size_bytes": r.get("sizeBytes"),
    } for r in rows if r.get("type") == "llm"]
    return {
        "ok": True,
        "tag_model": record2.TAG_MODEL,
        "tag_ttl": record2.TAG_TTL,
        "loaded": loaded,
    }


@router.post("/llm/unload")
def llm_unload(body: LlmUnloadBody) -> dict:
    """卸载一个已加载模型（9B/27B）。只释放内存，不碰题库。"""
    from amti import lms as _lms
    ok, why = _lms.unload(body.model.strip())
    if not ok:
        raise HTTPException(400, why)
    return {"ok": True, "model": body.model.strip(), "message": why}


@router.post("/ingest/tag")
def ingest_tag(body: IngestTagBody) -> dict:
    r"""给多题录入的卡片**预标考点/难度**（只读，不写库）。

    模型默认 `qwen3.5-9b-mlx`（用户点名要 qwen3.5；9B 够快）。它只负责
    "粗标"——编号必须来自考点清单，非法编号会被丢掉。人可以在卡片上改，
    确认后才走 `/api/ingest/commit`。

    **不碰题库**：这里只返回标签，写库仍然只走 ingest 那一条线。
    """
    from amti import knowledge as kb
    from amti import record2

    if not body.items:
        return {"ok": False, "error": "没有题目", "items": [], "model": "", "failed": 0}
    if len(body.items) > 60:
        raise HTTPException(413, "一次最多标注 60 道（整卷请分批）")

    # 空题干的题跳过；下标要记住，返回的数组必须和请求**一一对应**，
    # 否则前端会把 A 题的标签贴到 B 题上。
    idx: list[int] = []
    recs: list[dict] = []
    for i, it in enumerate(body.items):
        if not (it.stem or "").strip():
            continue
        opts: dict[str, str] = {}
        for o in it.options or []:
            if not isinstance(o, dict):
                continue
            label = str(o.get("label") or "").strip()
            text = str(o.get("text") or "")
            if label:
                opts[label] = text
        idx.append(i)
        recs.append({"题干": it.stem, "选项": opts, "题型": it.type or ""})

    out: list[dict] = [{"points": [], "point_titles": [], "difficulty": "",
                        "stars": 0, "point_source": ""}
                       for _ in body.items]
    if not recs:
        return {"ok": False, "error": "没有可标注的题干", "items": out,
                "model": "", "failed": 0}

    model = (body.model or "").strip() or record2.TAG_MODEL
    workers = max(1, min(int(body.workers or 4), 8))
    res = record2.tag_points_detailed(recs, model=model, workers=workers,
                                      with_difficulty=True, retry_empty=True)
    used = res.get("model") or model
    # qwen3.5 没装/没起来 → 回落 27B（它可能已经在内存里）。只在**一条都没标上**
    # 时回落；部分失败是模型抽风，重跑比换模型更稳。
    if not res.get("n") and not res.get("n_diff") and res.get("error"):
        alt = record2.tag_points_detailed(recs, model="", workers=workers,
                                          with_difficulty=True, retry_empty=True)
        if alt.get("n") or alt.get("n_diff"):
            res, used = alt, alt.get("model") or "qwen/qwen3.8-27b"

    for j, r in zip(idx, recs):
        pts = [p for p in (r.get("points") or []) if kb.get(p)][:2]
        diff = str(r.get("difficulty") or "").strip()
        if diff not in ("简单题", "中档题", "难题"):
            diff = kb.difficulty_of(pts[0]) if pts else ""
        out[j] = {
            "points": pts,
            "point_titles": [kb.title_of(p) for p in pts],
            "difficulty": diff,
            "stars": kb.stars_of(pts[0]) if pts else 0,
            "point_source": "llm" if (pts or diff) else "",
        }
    ok = bool(res.get("n") or res.get("n_diff"))
    return {"ok": ok, "error": res.get("error") or "",
            "model": used, "items": out,
            "failed": int(res.get("failed") or 0),
            "retried": int(res.get("retried") or 0),
            "filled": int(res.get("filled") or 0)}
