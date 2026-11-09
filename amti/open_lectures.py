"""AmTiKu · 开源小初**素材**（来源/许可追溯）

`数据/开源讲义/` 里放**可合法复用**的小初数学原文（MIT / LPPL 等），
本模块负责：读清单、把 Markdown 转成 HTML、把图片路径改写成 API 地址、
把 PDF 原样发出去。**不改写原文、不复制到题库、不混进正式专题。**

2026-11 起，小学/初中的**讲义正文**改由 `amti.lecture_tex.py` 从
`数据/专题/小初/content/*.json` 生成，与高中同一套 elegantbook 模板；
本模块保留为来源与许可追溯，不再直接出现在讲义阅读器里。

唯一入口：
    manifest.json   系列 → 讲义 → md/pdf/封面/字数/知识点
    README.md       来源、作者、许可与更新规则
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote, unquote

from .paths import ROOT
from . import knowledge_map

BASE = ROOT / "数据" / "开源讲义"
MANIFEST = BASE / "manifest.json"

_CACHE: dict = {"key": None, "v": None}
_HTML: dict = {}


def _sig() -> tuple:
    try:
        st = MANIFEST.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return (0, 0)


def load() -> dict:
    key = _sig()
    if _CACHE["key"] == key and _CACHE["v"] is not None:
        return _CACHE["v"]
    if not MANIFEST.exists():
        v = {"version": 0, "series": []}
    else:
        try:
            v = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            v = {"version": 0, "series": [], "error": "manifest.json 读不出来"}
    _CACHE["key"], _CACHE["v"] = key, v
    return v


def _series_for(stage: str = "") -> list[dict]:
    out = []
    for s in load().get("series", []):
        if stage and s.get("stage") != stage:
            continue
        out.append(s)
    return out


def _lectures(stage: str = "") -> dict[str, tuple[dict, dict]]:
    out = {}
    for s in _series_for(stage):
        for lec in s.get("lectures", []):
            out[lec["id"]] = (s, lec)
    return out


def _cover_url(s: dict, lec: dict) -> str:
    cover = lec.get("cover") or ""
    if not cover:
        return ""
    # asset 是相对 Markdown 所在目录解析的；cover 在 manifest 里是相对 BASE 的。
    md = _md_path(lec)
    rel = cover
    if md:
        try:
            rel = str((BASE / cover).resolve().relative_to(md.parent.resolve()))
        except ValueError:
            pass
    return f"/api/open-lectures/{lec['id']}/asset/{quote(rel)}"


def _stage_tree(stage: str) -> dict:
    tree = knowledge_map.tree()
    return next((s for s in tree.get("stages", []) if s.get("key") == stage), {})


def _public(s: dict, lec: dict) -> dict:
    return {
        "id": lec.get("id"), "title": lec.get("title"),
        "chars": lec.get("chars"), "summary": lec.get("summary"),
        "source": s.get("source"), "license": s.get("license"),
        "author": s.get("author"), "cover_url": _cover_url(s, lec),
    }


def list_for_stage(stage: str = "") -> dict:
    """按知识图谱的「册 → 章」返回讲义。

    外部讲义只在**匹配到某一章**时出现；不再按来源另起系列。
    `unmapped` 是 manifest 里对不上地图的条目，正常应为 0。
    """
    series = _series_for(stage)
    by: dict[tuple, tuple] = {}
    for s in series:
        for lec in s.get("lectures", []):
            by[(lec.get("book"), lec.get("chapter"))] = (s, lec)

    books = []
    used: set[tuple] = set()
    total_chapters = 0
    for b in _stage_tree(stage).get("books", []):
        chapters = []
        for c in b.get("chapters", []):
            total_chapters += 1
            key = (b.get("name"), c.get("title"))
            hit = by.get(key)
            if not hit:
                continue
            used.add(key)
            s, lec = hit
            chapters.append({
                "book": b.get("name"), "chapter": c.get("title"),
                "points": len(c.get("points", [])),
                "point_ids": [p.get("id") for p in c.get("points", []) if p.get("id")],
                "lecture": _public(s, lec),
            })
        if chapters:
            books.append({"name": b.get("name"), "chapters": chapters})

    unmapped = [k for k in by if k not in used]
    return {
        "stage": stage,
        "books": books,
        "total": sum(len(b["chapters"]) for b in books),
        "missing_chapters": max(0, total_chapters - len(used)),
        "unmapped": len(unmapped),
    }


def _map_info(lec: dict) -> dict:
    """给出这条讲义对应的教材位置与知识点数（以地图为准）。"""
    st = ""
    for s in load().get("series", []):
        if any(x is lec for x in s.get("lectures", [])):
            st = s.get("stage", "")
            break
    book, chapter = lec.get("book"), lec.get("chapter")
    pts = 0
    point_ids: list[str] = []
    for b in _stage_tree(st).get("books", []):
        if b.get("name") != book:
            continue
        for c in b.get("chapters", []):
            if c.get("title") == chapter:
                pts = len(c.get("points", []))
                point_ids = [p.get("id") for p in c.get("points", []) if p.get("id")]
                break
    return {"book": book, "chapter": chapter, "points": pts, "point_ids": point_ids}


def _find(lid: str) -> tuple[dict, dict] | tuple[None, None]:
    for s in load().get("series", []):
        for lec in s.get("lectures", []):
            if lec.get("id") == lid:
                return s, lec
    return None, None


def _md_path(lec: dict) -> Path | None:
    rel = lec.get("md") or ""
    if not rel:
        return None
    p = (BASE / rel).resolve()
    if BASE.resolve() not in p.parents or not p.is_file():
        return None
    return p


def _render_md(lec: dict) -> str:
    p = _md_path(lec)
    if not p:
        return "<p>讲义文件不见了。</p>"
    key = (str(p), p.stat().st_mtime_ns)
    if key in _HTML:
        return _HTML[key]
    text = p.read_text(encoding="utf-8")
    try:
        import mistune
        md = mistune.create_markdown(escape=False,
                                     plugins=["table", "strikethrough", "task_lists"])
        html = md(text)
    except Exception:                    # mistune 不在：先试 pandoc，再退回 <pre>
        import html as _h
        try:
            import subprocess
            r = subprocess.run(
                ["pandoc", "-f", "markdown", "-t", "html", "--wrap=none"],
                input=text, capture_output=True, text=True, timeout=20,
                encoding="utf-8", errors="replace")
            html = r.stdout if r.returncode == 0 and r.stdout else                 "<pre>" + _h.escape(text) + "</pre>"
        except Exception:
            html = "<pre>" + _h.escape(text) + "</pre>"

    # 行内数学：$...$ 或 pandoc 的 \(...\) → .math.inline（前端 KaTeX 渲染）
    html = re.sub(r"\$([^$\n]+?)\$", r'<span class="math inline">$\1$</span>', html)
    html = re.sub(r"\\\((.+?)\\\)", r'<span class="math inline">\(\1\)</span>', html)

    # 图片：相对路径 → API 资源地址；绝对 URL 保持原样
    def _src(m: re.Match) -> str:
        src = unquote(m.group(1).strip())
        if not src or src.startswith(("http://", "https://", "data:", "/")):
            return m.group(0)
        return f'src="/api/open-lectures/{lec["id"]}/asset/{quote(src.lstrip("./"))}"'
    html = re.sub(r'src="([^"]*)"', _src, html)

    # 外链新窗口
    html = re.sub(r'<a href="(https?://[^"]+)"',
                  r'<a href="\1" target="_blank" rel="noreferrer"', html)
    _HTML[key] = html
    if len(_HTML) > 24:
        _HTML.pop(next(iter(_HTML)))
    return html


def detail(lid: str) -> dict:
    s, lec = _find(lid)
    if not s or not lec:
        return {}
    base = {k: lec.get(k) for k in
            ("id", "title", "grade", "chapter", "summary", "chars",
             "images", "points", "pages")}
    base.update({
        "source": s.get("source"), "license": s.get("license"),
        "author": s.get("author"), "cover_url": _cover_url(s, lec),
    })
    html = _render_md(lec) if lec.get("md") else ""
    article_title = ""
    m = re.search(r"<h1>(.*?)</h1>", html, flags=re.S)
    if m:
        article_title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        html = html[:m.start()] + html[m.end():]
    return {
        "lecture": base,
        "series": {k: s.get(k) for k in
                   ("id", "title", "stage", "author", "source", "license", "description")},
        "map": _map_info(lec),
        "article_title": article_title,
        "html": html,
    }


def asset_path(lid: str, rel: str) -> Path | None:
    _, lec = _find(lid)
    md = _md_path(lec) if lec else None
    if not md:
        return None
    base = md.parent.resolve()
    p = (base / rel).resolve()
    if (base not in p.parents and p != base) or not p.is_file():
        return None
    return p


def pdf_path(lid: str) -> Path | None:
    _, lec = _find(lid)
    if not lec or not lec.get("pdf"):
        return None
    p = (BASE / lec["pdf"]).resolve()
    if BASE.resolve() not in p.parents or not p.is_file():
        return None
    return p


if __name__ == "__main__":
    d = list_for_stage("")
    print("系列", len(d["series"]), "讲义", d["total"])
    for s in d["series"]:
        print(" -", s["id"], s["title"], len(s["lectures"]))
        for lec in s["lectures"][:3]:
            print("   ", lec["id"], lec["title"], lec.get("chars"), lec.get("has_pdf"))
