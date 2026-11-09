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
        out.update({"kind": "pdf", "pdf_b64": base64.b64encode(data).decode("ascii")})
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
        out.update({"kind": "pdf", "pdf_b64": base64.b64encode(pdf.read_bytes()).decode("ascii")})
    else:
        man["kind"] = "image"
        out.update({"kind": "image"})

    _write_manifest(jd, man)
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
    print("source_import 自检 %s（%d 项失败）"
          % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
