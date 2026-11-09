"""AmTiKu · 源文件适配（识题前段）

把用户丢进来的源文件变成现有录入链路认的东西：

    .docx  → pandoc → PDF     → 现有 VLM / AI 读题
    .pdf   → 原样             → 现有 VLM / AI 读题
    .tex/.txt/.md → 文本      → 现有 ingest.preview 编辑器
    图片   → 原样             → 现有 VLM

每次准备都在 `数据/录题/任务/<id>/` 留一份 **manifest**（源文件名、sha256、
类型、派生 PDF、时间、状态），方便回查“这份卷子是从哪来的”。

**这里不解析题目、不写题库**：真正的解析/查重/复核/入库仍只走
`ingest.preview()` → `ingest.commit()`。本模块只做“源 → 可读材料”。
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from .paths import ROOT

TASK_DIR = ROOT / "数据" / "录题" / "任务"
MAX_BYTES = 120 * 1024 * 1024
MAX_PAGES = 80
PAGE_DPI = 110
MAX_OCR_CHARS = 4 * 1024 * 1024
TEXT_EXT = {".tex", ".txt", ".md", ".markdown"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ext(name: str) -> str:
    return Path(str(name or "")).suffix.lower()


def _safe_label(name: str) -> str:
    n = Path(str(name or "资料")).name
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", n).strip(" ._")
    return n[:120] or "资料"


def _decode(data: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8(replace)"


def _job_dir(job_id: str, base_dir: Path | None = None) -> Path:
    root = (base_dir or TASK_DIR).resolve()
    p = (root / job_id).resolve()
    if root not in p.parents and p != root:
        raise ValueError("非法任务目录")
    return p


def _render_pages(pdf: Path, jd: Path) -> tuple[list[str], str]:
    """把 PDF 渲成源页 PNG；返回 `(names, warning)`。失败不阻断准备。"""
    try:
        try:
            import pymupdf as fitz
        except ImportError:                       # 旧依赖名
            import fitz
        page_dir = jd / "pages"
        page_dir.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        with fitz.open(str(pdf)) as doc:
            for i, page in enumerate(doc):
                if i >= MAX_PAGES:
                    return names, "源文件超过 %d 页，只渲了前 %d 页" % (len(doc), MAX_PAGES)
                name = "p-%03d.png" % (i + 1)
                page.get_pixmap(dpi=PAGE_DPI).save(str(page_dir / name))
                names.append(name)
        return names, ""
    except Exception as e:
        return [], "源页预览生成失败：%s" % e


def list_jobs(limit: int = 20, *, base_dir: Path | None = None) -> list[dict]:
    """最近准备过的源文件（manifest）；按修改时间倒序。"""
    root = (base_dir or TASK_DIR)
    out: list[dict] = []
    if not root.is_dir():
        return out
    for p in root.glob("*/manifest.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            m["_mtime"] = p.stat().st_mtime
            out.append(m)
        except Exception:
            continue
    out.sort(key=lambda x: x.get("_mtime", 0), reverse=True)
    return out[:max(1, min(100, int(limit or 20)))]


def load_job_payload(job_id: str, *, base_dir: Path | None = None) -> dict:
    """取任务的可继续材料：文本或 PDF；不重新转换，不写题库。"""
    m = load_job(job_id, base_dir=base_dir)
    if not m:
        raise ValueError("任务不存在")
    jd = _job_dir(job_id, base_dir)
    out: dict = {"ok": True, "job": m, "kind": m.get("kind") or "",
                 "pages": m.get("pages") or [],
                 "page_dir": str((jd / "pages").resolve())}
    ocr = _ocr_of(job_id, base_dir)
    if ocr:
        out["ocr_text"] = ocr.get("latex") or ""
        out["ocr"] = {k: ocr.get(k) for k in ("model", "pages", "seconds", "saved_at")}
    ext = str(m.get("source_ext") or "")
    src = jd / ("source" + ext)
    if m.get("kind") == "text" and src.is_file():
        text, enc = _decode(src.read_bytes())
        out.update({"text": text, "chars": len(text), "encoding": enc})
    elif m.get("kind") == "pdf":
        pdf = pdf_path(job_id, base_dir=base_dir)
        if not pdf or not pdf.is_file():
            raise ValueError("任务没有 PDF")
        out["pdf_b64"] = base64.b64encode(pdf.read_bytes()).decode("ascii")
    return out


def load_job(job_id: str, *, base_dir: Path | None = None) -> dict | None:
    try:
        p = _job_dir(job_id, base_dir) / "manifest.json"
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def prepare(name: str, data: bytes, *, base_dir: Path | None = None) -> dict:
    """保存源文件并做最小转换；返回 `{ok, job_id, kind, text?/pdf_b64?}`。"""
    if not data:
        raise ValueError("文件是空的")
    if len(data) > MAX_BYTES:
        raise ValueError("文件超过 %d MB" % (MAX_BYTES // 1024 // 1024))
    ext = _ext(name)
    if ext not in TEXT_EXT | IMAGE_EXT | {".pdf", ".docx"}:
        raise ValueError("暂不支持 %s；支持 PDF / DOCX / LaTeX / TXT / Markdown / 图片" % (ext or "该类型"))

    digest = _sha(data)
    job_id = time.strftime("%Y%m%d_%H%M%S") + "-" + digest[:8]
    jd = _job_dir(job_id, base_dir)
    jd.mkdir(parents=True, exist_ok=True)
    src = jd / ("source" + ext)
    src.write_bytes(data)
    man = {
        "id": job_id,
        "source_name": _safe_label(name),
        "source_ext": ext,
        "sha256": digest,
        "bytes": len(data),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "prepared",
        "kind": "",
        "warnings": [],
    }

    out: dict = {"ok": True, "job_id": job_id, "name": man["source_name"],
                 "kind": "", "warnings": []}

    if ext in TEXT_EXT:
        text, enc = _decode(data)
        man["kind"] = "text"
        man["encoding"] = enc
        if enc.startswith("utf-8(replace)"):
            man["warnings"].append("文件不是 UTF-8/GB18030，已按替换字符读取")
        out.update({"kind": "text", "text": text,
                    "chars": len(text), "encoding": enc})
        if ext == ".md":
            man["warnings"].append("Markdown 只作为原文载入；题目结构仍由现有解析/AI 处理")
    elif ext == ".pdf":
        man["kind"] = "pdf"
        pages, warn = _render_pages(src, jd)
        man["pages"] = pages
        man["page_count"] = len(pages)
        if warn:
            man["warnings"].append(warn)
        out.update({"kind": "pdf", "pdf_b64": base64.b64encode(data).decode("ascii"),
                    "pages": pages, "page_dir": str((jd / "pages").resolve())})
    elif ext == ".docx":
        pandoc = shutil.which("pandoc")
        if not pandoc:
            man["status"] = "error"
            man["error"] = "没有 pandoc"
            _write_manifest(jd, man)
            raise ValueError("Word 需要 Pandoc（brew install pandoc / choco install pandoc）")
        pdf = jd / "converted.pdf"
        t0 = time.perf_counter()
        r = subprocess.run(
            [pandoc, str(src), "-o", str(pdf), "--pdf-engine=xelatex",
             "-V", "documentclass=ctexart", "--resource-path", str(jd)],
            capture_output=True, text=True, timeout=240)
        man["seconds"] = round(time.perf_counter() - t0, 2)
        if r.returncode != 0 or not pdf.is_file() or pdf.stat().st_size == 0:
            man["status"] = "error"
            man["error"] = (r.stderr or r.stdout or "pandoc 没有产出 PDF")[:800]
            _write_manifest(jd, man)
            raise ValueError("Word 转 PDF 失败：%s" % man["error"][:300])
        man["kind"] = "pdf"
        man["derived_pdf"] = pdf.name
        pages, warn = _render_pages(pdf, jd)
        man["pages"] = pages
        man["page_count"] = len(pages)
        if warn:
            man["warnings"].append(warn)
        out.update({"kind": "pdf", "pdf_b64": base64.b64encode(pdf.read_bytes()).decode("ascii"),
                    "pages": pages, "page_dir": str((jd / "pages").resolve())})
    else:
        man["kind"] = "image"
        out.update({"kind": "image"})

    _write_manifest(jd, man)
    try:
        pr = prune_jobs(_keep_default(), base_dir=base_dir)
        out["pruned"] = len(pr.get("removed") or [])
    except Exception:
        out["pruned"] = 0
    out["warnings"] = man["warnings"]
    return out


def _write_manifest(jd: Path, man: dict) -> None:
    (jd / "manifest.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


def pdf_path(job_id: str, *, base_dir: Path | None = None) -> Path | None:
    jd = _job_dir(job_id, base_dir)
    for n in ("converted.pdf", "source.pdf"):
        p = jd / n
        if p.is_file():
            return p
    return None


def save_ocr(job_id: str, payload: dict, *, base_dir: Path | None = None) -> dict:
    """把一次本地读图/OCR 的结果缓存进任务，继续任务时不再重跑模型。"""
    m = load_job(job_id, base_dir=base_dir)
    if not m:
        raise ValueError("任务不存在")
    jd = _job_dir(job_id, base_dir)
    latex = str((payload or {}).get("latex") or "")
    if not latex.strip():
        raise ValueError("OCR 结果是空的")
    if len(latex) > MAX_OCR_CHARS:
        raise ValueError("OCR 结果过大")
    rec = {
        "latex": latex,
        "model": str((payload or {}).get("model") or "")[:120],
        "pages": int((payload or {}).get("pages") or 0),
        "seconds": float((payload or {}).get("seconds") or 0),
        "warnings": [str(x)[:300] for x in ((payload or {}).get("warnings") or [])][:20],
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (jd / "ocr.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    m["ocr"] = {k: rec[k] for k in ("model", "pages", "seconds", "saved_at")}
    m["ocr"]["chars"] = len(latex)
    m["status"] = "ocr"
    _write_manifest(jd, m)
    return {"ok": True, "job_id": job_id, "chars": len(latex),
            "model": rec["model"], "pages": rec["pages"]}


def _ocr_of(job_id: str, base_dir: Path | None = None) -> dict | None:
    try:
        p = _job_dir(job_id, base_dir) / "ocr.json"
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _all_jobs(base_dir: Path | None = None) -> list[tuple[float, dict]]:
    root = (base_dir or TASK_DIR)
    out: list[tuple[float, dict]] = []
    if not root.is_dir():
        return out
    for p in root.glob("*/manifest.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            out.append((p.stat().st_mtime, m))
        except Exception:
            continue
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def prune_jobs(keep: int = 50, *, base_dir: Path | None = None) -> dict:
    """只保留最近 `keep` 个任务；更老的整个任务目录删掉。"""
    keep = max(1, min(500, int(keep or 50)))
    jobs = _all_jobs(base_dir)
    removed: list[str] = []
    for _mtime, m in jobs[keep:]:
        jid = str(m.get("id") or "")
        if not jid:
            continue
        try:
            jd = _job_dir(jid, base_dir)
            if jd.is_dir():
                shutil.rmtree(jd)
                removed.append(jid)
        except Exception:
            continue
    return {"ok": True, "removed": removed, "kept": min(len(jobs), keep)}


def delete_job(job_id: str, *, base_dir: Path | None = None) -> dict:
    jd = _job_dir(job_id, base_dir)
    if not (jd / "manifest.json").is_file():
        raise ValueError("任务不存在")
    shutil.rmtree(jd)
    return {"ok": True, "removed": job_id}


def _keep_default() -> int:
    try:
        import os
        return max(5, min(500, int(os.environ.get("AMTIKU_INGEST_KEEP", "50"))))
    except Exception:
        return 50


def _selftest() -> int:
    import tempfile
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print(("  ✓ " if cond else "  ✗ ") + name + (("  " + extra) if extra else ""))
        if not cond:
            fails += 1

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        r = prepare("例题.tex", r"\title{测试}" "\n" r"\begin{question}题干\end{question}".encode(),
                    base_dir=base)
        check("text 类型", r["kind"] == "text" and "题干" in r["text"])
        man = load_job(r["job_id"], base_dir=base)
        check("manifest 落盘", man and man["sha256"] and man["status"] == "prepared")
        check("源文件保留", (_job_dir(r["job_id"], base) / "source.tex").is_file())
        try:
            prepare("x.exe", b"x", base_dir=base)
            ok = False
        except ValueError:
            ok = True
        check("拒绝未知扩展", ok)
        try:
            prepare("x.docx", b"not a docx", base_dir=base)
            ok = False
        except (ValueError, subprocess.SubprocessError):
            ok = True
        check("坏 DOCX 明确报错", ok)
        r2 = prepare("第二份.md", b"# test", base_dir=base)
        r3 = prepare("第三份.md", b"# test3", base_dir=base)
        save_ocr(r2["job_id"], {"latex": r"\begin{question}缓存\end{question}",
                                "model": "test", "pages": 1}, base_dir=base)
        pl = load_job_payload(r2["job_id"], base_dir=base)
        check("OCR 缓存可读", "缓存" in (pl.get("ocr_text") or ""))
        pr = prune_jobs(2, base_dir=base)
        check("任务保留策略", len(pr["removed"]) >= 1 and len(list_jobs(10, base_dir=base)) == 2)
    print("source_import 自检 %s（%d 项失败）"
          % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
