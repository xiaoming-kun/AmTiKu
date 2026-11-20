r"""AI 录题历史：把上传的试题/答案和结果存在本地，避免每次重传。

布局：
    数据/AI录题历史/<job>/source.pdf
    数据/AI录题历史/<job>/answer.pdf
    数据/AI录题历史/<job>/manifest.json
    数据/AI录题历史/<job>/result.json
    数据/AI录题历史/<job>/cache/...   （裁图/原页副本）

历史只是缓存，不是题库；删除不影响题目。
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from amti.logutil import get_logger

from .paths import ROOT

log = get_logger(__name__)

HIST = ROOT / "数据" / "AI录题历史"
_ID = re.compile(r"^ai-[0-9-]+$")


def _dir(job: str) -> Path:
    if not _ID.fullmatch(str(job or "")):
        raise ValueError("历史任务号不合法")
    return HIST / job


def save_job(job: str, *, source: bytes, answer: bytes = b"",
             name: str = "", answer_name: str = "",
             source_files: list[str] | None = None,
             fill_solutions: bool = False) -> None:
    d = _dir(job)
    d.mkdir(parents=True, exist_ok=True)
    if source:
        (d / "source.pdf").write_bytes(source)
    if answer:
        (d / "answer.pdf").write_bytes(answer)
    m = {
        "id": job, "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "name": name, "answer_name": answer_name,
        "source_files": list(source_files or []),
        "fill_solutions": bool(fill_solutions),
        "state": "running", "title": "", "pages": 0, "answer_pages": 0,
        "cost_cny": 0, "questions": 0,
    }
    (d / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2),
                                     encoding="utf-8")


def save_result(job: str, res: dict) -> None:
    d = _dir(job)
    d.mkdir(parents=True, exist_ok=True)
    # 裁图/原页在临时缓存里，过期会清；复制进历史，保证重开时还能对照。
    cache = d / "cache"
    cache.mkdir(exist_ok=True)
    for key, sub in (("crop_dir", ""), ("page_dir", "pages")):
        raw = str(res.get(key) or "").strip()
        if not raw:
            continue
        src = Path(raw).expanduser()
        if not src.is_absolute():
            continue
        if not src.is_dir() or src == Path("/") or src == ROOT:
            continue
        dst = cache / (sub or "crop")
        dst.mkdir(parents=True, exist_ok=True)
        try:
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)
                elif f.is_dir():
                    shutil.copytree(f, dst / f.name, dirs_exist_ok=True)
        except OSError as e:                    # 复制缺一件不算错，重开会缺图
            log.warning("录题历史：复制 %s 失败，重开任务可能缺文件：%s", src, e)
    # 指向历史副本，重开不再依赖 AI图 缓存。
    res = dict(res)
    if (cache / "crop").is_dir():
        res["crop_dir"] = str(cache / "crop")
    if (cache / "pages").is_dir():
        res["page_dir"] = str(cache / "pages")
    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False),
                                   encoding="utf-8")
    mpath = d / "manifest.json"
    try:
        m = json.loads(mpath.read_text(encoding="utf-8"))
    except Exception:                           # noqa: BLE001
        m = {"id": job, "created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    st = res.get("stats") or {}
    m.update({
        "state": "done", "title": str(res.get("title") or ""),
        "pages": int(st.get("pages") or 0),
        "answer_pages": int(st.get("answer_pages") or 0),
        "cost_cny": float(st.get("cost_cny") or 0),
        "questions": len(res.get("items") or []),
    })
    mpath.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_error(job: str, error: str) -> None:
    try:
        d = _dir(job)
        mpath = d / "manifest.json"
        m = json.loads(mpath.read_text(encoding="utf-8")) if mpath.is_file() else {"id": job}
        m.update({"state": "error", "error": str(error)[:300]})
        mpath.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError) as e:          # 连失败原因都记不上，只能打日志
        log.warning("录题历史：任务 %s 的失败原因没写进 manifest：%s", job, e)


def list_jobs(limit: int = 20) -> list[dict]:
    out: list[dict] = []
    if not HIST.is_dir():
        return out
    for d in sorted((p for p in HIST.iterdir() if p.is_dir()), reverse=True):
        try:
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except Exception:                       # noqa: BLE001
            continue
        m["has_result"] = (d / "result.json").is_file()
        # 旧记录可能把文件名里的 _ 转义成 \_；列表显示还原。
        m["title"] = str(m.get("title") or "").replace("\\_", "_")
        out.append(m)
        if len(out) >= max(1, min(100, int(limit))):
            break
    return out


def get_job(job: str) -> dict:
    d = _dir(job)
    if not d.is_dir():
        raise FileNotFoundError("没有这个历史任务")
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    result = None
    if (d / "result.json").is_file():
        result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    return {"ok": True, "manifest": m, "result": result}


def delete_job(job: str) -> None:
    d = _dir(job)
    if d.is_dir():
        shutil.rmtree(d)
