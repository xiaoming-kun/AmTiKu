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


def page_count(pdf_path: str | Path) -> int | None:
    """PDF 页数（读不出来给 None）。讲义"一题一页"靠它判断有没有题超页。"""
    try:
        import fitz
    except Exception:                                            # noqa: BLE001
        return None
    try:
        doc = fitz.open(str(pdf_path))
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:                                            # noqa: BLE001
        return None


def question_spans(tex_path: str | Path) -> dict[int, tuple[str, str]]:
    """每题（卷面序号）跨了哪几页：`{1: ("2","2"), 2: ("3","5")}`。

    数据来自 `.aux` 里的 `amtiq{N}` / `amtiqend{N}`（`qid_marks` 时才有）。
    `start != end` 就是**这道题被分页拆开了**——跨页修复循环靠它。
    """
    return _aux_pages(Path(tex_path).with_suffix(".aux"))


def split_questions(tex_path: str | Path) -> list[int]:
    """被拆到两页以上的题号（1 起）。"""
    return sorted(i for i, (a, b) in question_spans(tex_path).items() if a != b)


# Overfull 有三种报法，行号都在里面：
#   in paragraph at lines 812--815
#   in alignment at lines 96--96
#   **detected at line 146**（行间公式溢出走这条——以前只认前两种，公式溢出全漏了）
_OVERFULL_RE = re.compile(
    r"Overfull \\hbox \(([\d.]+)pt too wide\)[^\n]*?"
    r"(?:at lines? (\d+)(?:--(\d+))?)")


def _line_owner(tex_path: Path | None) -> list[tuple[int, str]]:
    """`[(行号, 题 key)]`：每道题的第一行是 `% AMTIKU-Q: <key>` 注释。"""
    if not tex_path or not tex_path.exists():
        return []
    out: list[tuple[int, str]] = []
    try:
        for i, line in enumerate(tex_path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("% AMTIKU-Q: "):
                out.append((i, line[len("% AMTIKU-Q: "):].strip()))
    except OSError:
        return []
    return out


def _owner_of(line: int, owners: list[tuple[int, str]]) -> str:
    key = ""
    for ln, k in owners:
        if ln <= line:
            key = k
        else:
            break
    return key


def overfull(log_path: str | Path, tex_path: str | Path | None = None) -> list[dict]:
    r"""`.log` 里的**排版溢出**：`[{line, pt, key}]`（按宽度降序）。

    "Overfull \hbox" 是 LaTeX 唯一会明说的版面错误——一行/一张表冲出纸面。
    以前只在编译失败时翻译它；现在**编成功了也报**：卷子能出，但某一行出血了。
    """
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    tex = Path(tex_path) if tex_path else None
    owners = _line_owner(tex)
    out: list[dict] = []
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for m in _OVERFULL_RE.finditer(text):
        pt = float(m.group(1))
        line = int(m.group(2))
        out.append({"pt": pt, "line": line, "key": _owner_of(line, owners)})
    out.sort(key=lambda x: -x["pt"])
    return out


def inspect(pdf_path: str | Path, *, tex_path: str | Path | None = None,
            aux_path: str | Path | None = None) -> dict:
    r"""返回 `{pages, page_stats, warnings, question_pages}`。"""
    pdf_path = Path(pdf_path)
    tex_path = Path(tex_path) if tex_path else None
    aux_path = Path(aux_path) if aux_path else pdf_path.with_suffix(".aux")
    out: dict = {"pages": None, "page_stats": [], "warnings": [],
                 "question_pages": {}, "overfull": []}
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

        # **排版溢出**：编成功了也要报（某一行/某张表冲出纸面）。
        over = overfull(pdf_path.with_suffix(".log"), tex_path)
        out["overfull"] = over[:20]
        # 0.1cm 以下的溢出在纸上不可见，不当问题报（否则每份卷子都挂一条噪声）
        from . import layout as _L
        over = [o for o in over if o["pt"] >= _L.OVERFULL_PT]
        if over:
            worst = over[0]
            who = ("「%s」" % worst["key"]) if worst["key"] else ""
            out["warnings"].append(
                "有 %d 处排版溢出（最宽 %.1fpt%s），标点/长公式可能顶出纸边"
                % (len(over), worst["pt"], "，最近的是 " + who if who else ""))
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
