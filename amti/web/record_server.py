r"""AmTiKu · 录题台（独立界面）

单独一个端口（默认 8901），跟题库主服务（8899）互不干扰：

    python3 -m amti.web.record_server --port 8901

把试卷 PDF 拖进来 → 后台用本地大模型逐页识别 → 看结果 → 一键入库。

**这里没有识别逻辑，也没有落盘逻辑。** 识别全在 `amti/record.py`，
入库全在 `amti/ingest.py`。本模块只做三件事：排队、调它们、把状态交给界面。
多写一行识别代码，就会多出一份和 CLI 不一样的实现。
"""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))

from amti import ingest as ig                             # noqa: E402
from amti import record as rec                            # noqa: E402

JOBS = PKG / "数据" / "录题" / "任务"
UPLOADS = PKG / "数据" / "录题" / "上传"
HTML = Path(__file__).resolve().parent / "record.html"

app = FastAPI(title="AmTiKu 录题台")
_q: "queue.Queue[str]" = queue.Queue()
_lock = threading.Lock()


# ── 任务存取 ──────────────────────────────────────────────────────


def _path(jid: str) -> Path:
    return JOBS / ("%s.json" % jid)


def load(jid: str) -> dict:
    p = _path(jid)
    if not p.exists():
        raise HTTPException(404, "没有这个任务")
    return json.loads(p.read_text(encoding="utf-8"))


def save(j: dict) -> None:
    r"""任务写盘。**必须先写临时文件再 `os.replace`。**

    直接 `write_text` 不是原子的：worker 线程正在写、请求线程同时在读，
    读到的就是**半截 JSON**——实测报 `JSONDecodeError: Expecting value:
    line 1 column 1`，界面上表现为"任务莫名其妙出错了"。
    `os.replace` 在同一文件系统内是原子的，读到的要么是旧的全份、要么是新的全份。

    临时文件名**带线程号**：同一个任务会被 worker 线程和请求线程同时写，
    共用一个 `.tmp` 名字的话，先写完的那个 `os.replace` 已经把它搬走了，
    后一个就撞上 `FileNotFoundError`。
    """
    JOBS.mkdir(parents=True, exist_ok=True)
    j["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    p = _path(j["id"])
    tmp = p.with_name("%s.%d.tmp" % (p.name, threading.get_ident()))
    tmp.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def brief(j: dict) -> dict:
    """列表用：**不带题目正文和整份 tex**，否则列表接口会越拖越慢。"""
    keep = {k: v for k, v in j.items()
            if k not in ("tex", "kept", "dropped", "report")}
    return keep


def all_jobs() -> list[dict]:
    JOBS.mkdir(parents=True, exist_ok=True)
    js = []
    for p in JOBS.glob("*.json"):
        try:
            js.append(brief(json.loads(p.read_text(encoding="utf-8"))))
        except ValueError:
            continue
    js.sort(key=lambda j: j.get("created", ""), reverse=True)
    return js


# ── 后台 worker ───────────────────────────────────────────────────


def _work(jid: str) -> None:
    j = load(jid)
    j.update(status="running", stage="启动", error="", log=[])
    save(j)

    def ev(e: dict) -> None:
        cur = load(jid)
        if e["type"] == "page":
            cur["done"] = e["page"]
            cur["total"] = e["total"]
            cur["stage"] = "识别第 %d/%d 页%s" % (
                e["page"], e["total"],
                "（缓存）" if e["cached"] else
                ("（%.0fs）" % e["secs"] if e.get("secs") else ""))
            if e.get("error"):
                cur["log"] = (cur.get("log") or []) + [
                    "第 %d 页失败：%s" % (e["page"], e["error"])]
        elif e["type"] == "stage":
            cur["stage"] = e["text"]
        save(cur)

    try:
        r = rec.run(
            Path(j["pdf"]),
            answers=Path(j["answers"]) if j.get("answers") else None,
            book=j["book"], label=j["label"], region=j.get("region", ""),
            year=j.get("year"), workers=int(j.get("workers", 1)),
            force=bool(j.get("force")), on_event=ev)
        j = load(jid)
        j.update(
            status="ready", stage="识别完成，等待入库",
            tex=r["tex"], stats=r["stats"], register=r["register"],
            kept=[{"n": q["n"], "type": q["type"], "figure": q["figure"],
                   "stem": q["stem"], "ans": q["ans"], "sol": q["sol"],
                   "options": q["options"]} for q in r["kept"]],
            dropped=[{"n": q["n"], "pages": q["pages"], "fig": q["fig"]}
                     for q in r["dropped"]],
            title=r["title"], label=r["label"], year=r["year"])
    except Exception as e:                                     # noqa: BLE001
        j = load(jid)
        j.update(status="error", stage="出错",
                 error="%s: %s" % (type(e).__name__, e),
                 trace=traceback.format_exc()[-2000:])
    save(j)


def _worker() -> None:
    r"""排队消费。

    **`_work` 抛异常不能把 worker 打死。** 打死之后进程还在、接口还能响应，
    但队列再也没人消费——界面上所有任务永远停在"排队中"，
    这是最难查的一类故障（服务"活着"却什么也不干）。
    """
    while True:
        jid = _q.get()
        try:
            _work(jid)
        except Exception as e:                                 # noqa: BLE001
            try:
                j = load(jid)
                j.update(status="error", stage="出错",
                         error="%s: %s" % (type(e).__name__, e),
                         trace=traceback.format_exc()[-2000:])
                save(j)
            except Exception:                                  # noqa: BLE001
                pass                    # 连兜底都写不进去，只能让日志说话
        finally:
            _q.task_done()


threading.Thread(target=_worker, daemon=True).start()


# ── 接口 ──────────────────────────────────────────────────────────


@app.get("/")
def index():
    return FileResponse(HTML)


class NewJob(BaseModel):
    pdf: str
    answers: str | None = None
    book: str = "模拟题"
    label: str = ""
    region: str = ""
    year: int | None = None
    workers: int = 1
    force: bool = False


def _mk(pdf: Path, answers: Path | None, **kw) -> dict:
    if not pdf.exists():
        raise HTTPException(400, "文件不存在：%s" % pdf)
    jid = time.strftime("%y%m%d") + "-" + uuid.uuid4().hex[:6]
    j = {"id": jid, "pdf": str(pdf), "status": "queued", "stage": "排队中",
         "created": time.strftime("%Y-%m-%d %H:%M:%S"), "done": 0, "total": 0,
         "label": kw.get("label") or rec.guess_label(pdf),
         "year": kw.get("year") or rec.guess_year(pdf),
         "region": kw.get("region", ""), "book": kw.get("book", "模拟题"),
         "workers": max(1, min(8, int(kw.get("workers", 1)))),
         "force": kw.get("force", False)}
    auto = None if answers else rec.pair_answer(pdf)
    j["answers"] = str(answers or auto) if (answers or auto) else ""
    j["answers_auto"] = bool(auto and not answers)
    save(j)
    _q.put(jid)
    return j


@app.post("/api/jobs")
def new_job(b: NewJob):
    """按路径加一份卷子（本地已有的文件走这条）。"""
    return _mk(Path(b.pdf), Path(b.answers) if b.answers else None,
               book=b.book, label=b.label, region=b.region, year=b.year,
               workers=b.workers, force=b.force)


@app.post("/api/upload")
async def upload(request: Request):
    r"""拖进来的文件走这条：**请求体就是文件字节**，文件名放 query。

    不用 multipart 是有意的——那要给项目加一个 `python-multipart` 依赖，
    而这里只需要一个文件名。
    """
    name = request.query_params.get("name") or "上传.pdf"
    name = Path(name).name                      # 防目录穿越
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dst = UPLOADS / name
    dst.write_bytes(await request.body())
    q = request.query_params
    year = q.get("year")
    return _mk(dst, None, book=q.get("book") or "模拟题",
               label=q.get("label") or "", region=q.get("region") or "",
               year=int(year) if year else None)


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": all_jobs()}


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    j = load(jid)
    j["tex"] = j.get("tex", "")
    return j


@app.post("/api/jobs/{jid}/retry")
def retry(jid: str):
    """重跑：**已成功的页命中缓存**，所以实际只会重试失败/没跑的那几页。"""
    j = load(jid)
    j.update(status="queued", stage="排队中", error="")
    save(j)
    _q.put(jid)
    return j


class Patch(BaseModel):
    label: str | None = None
    region: str | None = None
    year: int | None = None
    book: str | None = None
    answers: str | None = None


@app.patch("/api/jobs/{jid}")
def patch(jid: str, b: Patch):
    j = load(jid)
    for k, v in b.model_dump(exclude_none=True).items():
        j[k] = v
    # 出处变了，题目 key 就得跟着变——否则 tex 里还是旧出处
    if j.get("tex") and any(k in (b.model_fields_set or ())
                            for k in ("label", "book", "region", "year")):
        j["tex"] = rec.to_tex(
            [{"n": q["n"], "type": q["type"], "stem": q["stem"],
              "options": [tuple(o) for o in q["options"]],
              "fig": "", "ans": q["ans"], "sol": q["sol"]}
             for q in j.get("kept", [])],
            book=j["book"], label=j["label"], region=j.get("region", ""),
            year=j.get("year"), title=j.get("title", ""))
    save(j)
    return brief(j)


class IngestBody(BaseModel):
    yes: bool = False


@app.post("/api/jobs/{jid}/ingest")
def do_ingest(jid: str, b: IngestBody):
    r"""入库。`yes=false` 只干跑——**先在界面上给用户看清楚再写**。"""
    j = load(jid)
    if not j.get("tex"):
        raise HTTPException(400, "还没识别完")
    kw = dict(book=j["book"], label=j["label"], region=j.get("region", ""),
              year=j.get("year"))
    with _lock:                       # 写库是全局串行的，两个任务同时落盘会打架
        if not b.yes:
            return ig.preview(j["tex"], **kw)
        rep = ig.commit(j["tex"], **kw)
    j = load(jid)
    j.update(status="ingested", stage="已入库", report=rep)
    save(j)
    return rep


@app.get("/api/jobs/{jid}/page/{n}")
def page_image(jid: str, n: int):
    j = load(jid)
    d = rec.WORK / Path(j["pdf"]).stem / "pages"
    hit = sorted(d.glob("p%03d.*" % n))
    if not hit:
        raise HTTPException(404, "没有这一页")
    return FileResponse(hit[0])


@app.get("/api/pdfs")
def list_pdfs(dir: str = ""):
    r"""列目录里的 PDF，方便不开拖拽也能加卷子。默认列桌面的 27年试卷。"""
    d = Path(dir).expanduser() if dir else Path.home() / "Desktop" / "27年试卷" / "试卷"
    if not d.is_dir():
        return {"dir": str(d), "files": [], "error": "目录不存在"}
    return {"dir": str(d),
            "files": [{"name": p.name, "path": str(p),
                       "label": rec.guess_label(p), "year": rec.guess_year(p),
                       "answer": (rec.pair_answer(p).name
                                  if rec.pair_answer(p) else "")}
                      for p in sorted(d.glob("*.pdf"))]}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(description="AmTiKu 录题台")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)
    print("录题台  http://%s:%d" % (a.host, a.port))
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
