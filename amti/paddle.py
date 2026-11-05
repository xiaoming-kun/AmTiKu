r"""PaddleOCR-VL-1.6（MLX 4bit）识别引擎。

`record2` 只跟这几个函数打交道：`scan / figures / layout / available`，
外加 `parse_file()` 给「单张图 → markdown」的场景用。

为什么换：实测同一份卷子，MinerU 把一页四道题的选项标签整排丢掉、
还把解析范围串到上一题；PaddleOCR-VL 逐块识别、选项 A/B/C/D 齐全，
公式也是干净的 `$…$`。代价是每页 4–10 秒（比 MinerU 慢一点），换来的是对得上原卷。

依赖用户环境（已装好，见 `~/paddleocr-vl-tools/README.md`）：

    ~/paddleocr-vl/bin/python          # 带 paddleocr / mlx-vlm 的 venv
    ~/paddleocr-vl-tools/ocr_pdf.py    # 逐页 → md + json + 裁图
    ~/.local/bin/ocr                   # 起停 :8111 的 MLX 服务
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
VENV_PY = HOME / "paddleocr-vl" / "bin" / "python"
TOOL = HOME / "paddleocr-vl-tools" / "ocr_pdf.py"
OCR_BIN = HOME / ".local" / "bin" / "ocr"
SERVER = "http://127.0.0.1:8111/"
DPI = os.environ.get("AMTIKU_PADDLE_DPI", "200")
TIMEOUT = int(os.environ.get("AMTIKU_PADDLE_TIMEOUT", "3600"))


def up(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(SERVER, timeout=timeout):
            return True
    except Exception:                                         # noqa: BLE001
        # 根路径可能 404，但服务是活的：连得上就算 ok
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 8111), timeout=timeout):
                return True
        except OSError:
            return False


def available() -> tuple[bool, str]:
    if not VENV_PY.is_file():
        return False, "没装 PaddleOCR 环境：%s" % VENV_PY
    if not TOOL.is_file():
        return False, "没装解析脚本：%s" % TOOL
    return True, "就绪"


def ensure(*, wait: float = 120.0) -> tuple[bool, str]:
    r"""确保 :8111 的 MLX 服务在跑（不在就用 `ocr start` 拉起）。"""
    if up():
        return True, "服务在线"
    if not OCR_BIN.is_file():
        return False, "找不到 `ocr` 命令（%s）" % OCR_BIN
    try:
        subprocess.run([str(OCR_BIN), "start"], capture_output=True,
                       text=True, timeout=180)
    except Exception as e:                                    # noqa: BLE001
        return False, "启动失败：%s: %s" % (type(e).__name__, e)
    t0 = time.time()
    while time.time() - t0 < wait:
        if up():
            return True, "已拉起"
        time.sleep(1.0)
    return False, "起了 %.0f 秒还没就绪" % wait


def _run(pdf: Path, out: Path) -> str:
    """跑一遍 ocr_pdf.py，返回它最后几行输出（出错时贴进异常里）。"""
    ok, why = ensure()
    if not ok:
        raise RuntimeError(why)
    cmd = [str(VENV_PY), str(TOOL), str(pdf), "-p", "all",
           "--dpi", DPI, "-o", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    tail = ((r.stdout or "") + (r.stderr or ""))[-600:]
    if r.returncode != 0 or not out.exists():
        raise RuntimeError("PaddleOCR 解析失败（exit %s）：%s" % (r.returncode, tail))
    return tail


def scan(pdf: Path, work: Path, *, force: bool = False) -> list[dict]:
    r"""整卷 PDF → 每页文本，落在 `work/v2/txt/pNN.md`（和 MinerU 同一套约定）。"""
    from . import record as R                                 # 延迟导入，避开循环

    pdf, work = Path(pdf), Path(work)
    d = work / "v2"
    txt = d / "txt"
    txt.mkdir(parents=True, exist_ok=True)

    # 页图照常渲染：下游「原页」面板、裁图都指着 work/pages
    imgs = R.pages_of(pdf, work / "pages")

    key = d / "paddle.json"
    if key.exists() and not force:
        try:
            cached = json.loads(key.read_text(encoding="utf-8"))
            if cached.get("pdf") == str(pdf) and all(
                    Path(r["txt"]).exists() for r in cached.get("rows", [])):
                (d / "pages.json").write_text(
                    json.dumps(cached["rows"], ensure_ascii=False, indent=1),
                    encoding="utf-8")
                return cached["rows"]
        except Exception:                                     # noqa: BLE001
            pass

    out = work / "paddle"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    _run(pdf, out)

    rows: list[dict] = []
    for pd in sorted(out.glob("p*")):
        if not pd.is_dir():
            continue
        m = re.search(r"(\d+)", pd.name)
        if not m:
            continue
        n = int(m.group(1))
        md = next(iter(pd.glob("p*.md")), None)
        if md is None:
            continue
        body = _tidy(md.read_text(encoding="utf-8", errors="ignore"))
        dst = txt / ("p%02d.md" % n)
        dst.write_text(body, encoding="utf-8")
        img = imgs[n - 1] if n - 1 < len(imgs) else ""
        rows.append({"page": n, "img": str(img), "txt": str(dst), "chars": len(body)})

    if not rows:
        raise RuntimeError("PaddleOCR 没产出任何页（%s）" % out)
    (d / "pages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    key.write_text(json.dumps({"pdf": str(pdf), "rows": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


_MD_IMG = re.compile(r'<div[^>]*>\s*<img[^>]*src="imgs/([^"]+)"[^>]*>\s*</div>', re.I)
_IMG_ALT = re.compile(r'!\[[^\]]*\]\(imgs/([^)]+)\)')


def _tidy(md: str) -> str:
    r"""把 Paddle 的 markdown 收敛成"正文 + （图）占位"。

    它给的是 `<div style=...><img src="imgs/xxx.jpg"></div>`，图本身已单独裁好，
    正文里只留 `（图）` 占位即可（下游的图是单独挂的）。
    """
    md = _MD_IMG.sub("（图）", md)
    md = _IMG_ALT.sub("（图）", md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md + "\n"


def figures(pdf: Path, work: Path, *, force: bool = False) -> dict[int, list[str]]:
    r"""按块裁好的插图：`{页码: [文件名]}`，文件落在 `work/v2/figs/`。

    命名加页前缀（`p3_img_in_image_box_…jpg`），避免不同页同坐标撞名。
    """
    work = Path(work)
    d = work / "v2"
    out = d / "figcrops.json"
    if out.exists() and not force:
        try:
            return {int(k): v for k, v in json.loads(out.read_text(encoding="utf-8")).items()}
        except Exception:                                     # noqa: BLE001
            pass

    dest = d / "figs"
    dest.mkdir(parents=True, exist_ok=True)
    table: dict[int, list[str]] = {}
    for pd in sorted((work / "paddle").glob("p*")):
        m = re.search(r"(\d+)", pd.name)
        src = pd / "imgs"
        if not m or not src.is_dir():
            continue
        n = int(m.group(1))
        for f in sorted(src.iterdir()):
            if not f.is_file():
                continue
            name = "p%d_%s" % (n, f.name)
            shutil.copyfile(f, dest / name)
            table.setdefault(n, []).append(name)
    out.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    return table


_LABEL_IMAGE = {"image", "figure", "chart", "table", "seal"}


def layout(work: Path) -> dict[int, dict]:
    r"""`{页: {"texts": [(y0, y1, 文本, x0, x1)], "images": [((桶, x), 文件名)]}}`。

    坐标归一化到 0–1（左上原点），`assign_figs` 直接吃这个结构。
    """
    work = Path(work)
    out: dict[int, dict] = {}
    for pd in sorted((work / "paddle").glob("p*")):
        m = re.search(r"(\d+)", pd.name)
        res = next(iter(pd.glob("p*_res.json")), None)
        if not m or res is None:
            continue
        try:
            data = json.loads(res.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        W = float(data.get("width") or 1)
        H = float(data.get("height") or 1)
        n = int(m.group(1))
        texts, images = [], []
        for b in data.get("parsing_res_list") or []:
            bb = b.get("block_bbox") or []
            if len(bb) < 4:
                continue
            x0, y0, x1, y1 = (bb[0] / W, bb[1] / H, bb[2] / W, bb[3] / H)
            label = str(b.get("block_label") or "text")
            if label in _LABEL_IMAGE:
                name = "p%d_img_in_image_box_%d_%d_%d_%d.jpg" % (
                    n, bb[0], bb[1], bb[2], bb[3])
                images.append(((round(((y0 + y1) / 2) / 0.05), x0), name))
            else:
                t = str(b.get("block_content") or "").strip()
                if t:
                    texts.append((y0, y1, t, x0, x1))
        images.sort(key=lambda kn: kn[0])
        out[n] = {"texts": texts, "images": images}
    return out


def parse_file(path: Path) -> str:
    r"""单文件（PDF 或图片）→ markdown 全文，页间用 `<!-- page N -->` 分隔。"""
    import shutil
    import tempfile

    path = Path(path)
    out = Path(tempfile.mkdtemp(prefix="paddle-one-"))
    try:
        _run(path, out)
        parts: list[str] = []
        for i, pd in enumerate(sorted(out.glob("p*")), 1):
            md = next(iter(pd.glob("p*.md")), None)
            if md is None:
                continue
            parts.append("<!-- page %d -->\n%s"
                         % (i, _tidy(md.read_text(encoding="utf-8", errors="ignore"))))
        if not parts:
            raise RuntimeError("PaddleOCR 没认出任何内容：%s" % path)
        return "\n\n".join(parts)
    finally:
        # ⚠️ 原来这里不删：每次「大模型读图」都在 /tmp 留一份整卷裁图，
        # 反复用几天就把盘塞满——而且是静默的。
        shutil.rmtree(out, ignore_errors=True)
