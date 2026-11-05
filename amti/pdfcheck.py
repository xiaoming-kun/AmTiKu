r"""PDF 排版体检：页数、每页空白、解答题跨页。

导出后编译出的 PDF 再读一遍，回答三个问题：

  · 一共几页？
  · 每页内容占到哪儿、底部还剩多少空白（缩略条用）？
  · 有没有解答题跨到了下一页？

依赖 PyMuPDF（`fitz`）。没装就只返回空结果，不影响导出——这是体检，
不是导出的前置条件。
"""
from __future__ import annotations

import re
from pathlib import Path


def _detail_indices(tex_path: Path | None) -> list[int]:
    if not tex_path or not tex_path.exists():
        return []
    try:
        text = tex_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [int(x) for x in re.findall(r"% AMTIKU-DETAIL: (\d+)", text)]


def _aux_pages(aux_path: Path | None) -> dict[int, tuple[str, str]]:
    if not aux_path or not aux_path.exists():
        return {}
    try:
        text = aux_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    start = {int(m.group(1)): m.group(2) for m in
             re.finditer(r"\\newlabel\{amtiq(\d+)\}\{\{[^}]*\}\{([^}]*)\}", text)}
    end = {int(m.group(1)): m.group(2) for m in
           re.finditer(r"\\newlabel\{amtiqend(\d+)\}\{\{[^}]*\}\{([^}]*)\}", text)}
    return {i: (start[i], end[i]) for i in start if i in end}


def inspect(pdf_path: str | Path, *, tex_path: str | Path | None = None,
            aux_path: str | Path | None = None) -> dict:
    r"""返回 `{pages, page_stats, warnings, question_pages}`。"""
    pdf_path = Path(pdf_path)
    tex_path = Path(tex_path) if tex_path else None
    aux_path = Path(aux_path) if aux_path else pdf_path.with_suffix(".aux")
    out: dict = {"pages": None, "page_stats": [], "warnings": [],
                 "question_pages": {}}
    try:
        import fitz  # PyMuPDF；没装就走下面的 except
    except Exception:                                            # noqa: BLE001
        return out

    try:
        doc = fitz.open(pdf_path)
    except Exception:                                            # noqa: BLE001
        return out

    try:
        out["pages"] = len(doc)
        for i, page in enumerate(doc, start=1):
            rect = page.rect
            bottom = 0.0
            has_text = False
            for b in page.get_text("blocks"):
                text = (b[4] or "").strip()
                if not text:
                    continue
                y1 = float(b[3])
                # 页脚页码不算正文；页眉也忽略。
                # AmTiKu 页眉落在 ~54pt，旧阈值 35 会把页眉算成正文：
                # 一张本来空白的页只要印了页眉，就再也报不出“空白页”。
                if y1 > rect.height - 60 or float(b[1]) < 60:
                    continue
                has_text = True
                bottom = max(bottom, y1)
            for img in page.get_images(full=True):
                try:
                    for r in page.get_image_rects(img[0]):
                        if 60 <= r.y1 < rect.height - 60:
                            bottom = max(bottom, float(r.y1))
                            has_text = True
                except Exception:                                # noqa: BLE001
                    pass
            for d in page.get_drawings():
                r = d.get("rect")
                if r is None:
                    continue
                # 整页边框 / 密封线 / 背景不是“内容”：它们能一直画到页脚，
                # 会把空白算成 0。只认尺寸明显小于整页的图形（图、表格线）。
                if float(r.height) > rect.height * 0.6 or float(r.width) > rect.width * 0.9:
                    continue
                # 页眉那条 0.4pt 的细线也不算正文
                if 60 <= r.y1 < rect.height - 60:
                    bottom = max(bottom, float(r.y1))
                    has_text = True
            blank_cm = max(0.0, (rect.height - 60 - bottom) / 72 * 2.54)
            stat = {"page": i, "fill_pct": round(bottom / rect.height * 100, 1),
                    "blank_cm": round(blank_cm, 1), "empty": not has_text}
            out["page_stats"].append(stat)
            if not has_text:
                out["warnings"].append("第 %d 页是空白页" % i)
            elif blank_cm < 1.0:
                out["warnings"].append(
                    "第 %d 页底部只剩 %.1fcm，可能太挤/跨页" % (i, blank_cm))

        spans = _aux_pages(aux_path)
        out["question_pages"] = {str(k): list(v) for k, v in spans.items()}
        details = set(_detail_indices(tex_path))
        for idx in sorted(details):
            if idx not in spans:
                continue
            a, b = spans[idx]
            if a != b:
                out["warnings"].append(
                    "第 %d 个解答题跨页（第 %s–%s 页）" % (idx, a, b))
    finally:
        doc.close()
    return out


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("用法：python3 -m amti.pdfcheck <file.pdf> [file.tex]")
    print(json.dumps(inspect(sys.argv[1],
                             tex_path=sys.argv[2] if len(sys.argv) > 2 else None),
                     ensure_ascii=False, indent=2))
