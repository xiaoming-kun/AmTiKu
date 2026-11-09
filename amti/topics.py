"""AmTiKu · 讲义清单

两份清单，统一成同一个列表：

    高中专题   `数据/专题/manifest.json`
               一个考点一份 elegantbook 讲义 + 五要素 + 3+3+2 道精选题
    小初章节   `数据/专题/小初/manifest.json`
               一个章节一份，与高中同款 elegantbook 模板；只讲不练

小初条目带 `stage` 字段（primary/junior），`id` 是章 id（x11.1 / c71.1），
没有精选题；高中条目仍是考点 id，带 `questions`。

只读，不改任何东西；文件缺失时返回空列表，界面显示「还没有讲义」，不报错。
"""
from __future__ import annotations

from .paths import ROOT
import json
from pathlib import Path

TOPIC_DIR = ROOT / "数据" / "专题"
MANIFEST = TOPIC_DIR / "manifest.json"
# 小初章节讲义：与高中专题同一套 elegantbook 模板，清单单独一份。
CHAPTER_MANIFEST = TOPIC_DIR / "小初" / "manifest.json"

_CACHE: dict = {"key": None, "v": None}


def _sig() -> tuple:
    out = []
    for p in (MANIFEST, CHAPTER_MANIFEST):
        try:
            st = p.stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((0, 0))
    return tuple(out)


def _read_manifest(p: Path) -> list[dict]:
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [x for x in (data.get("topics") or []) if isinstance(x, dict)]


def load() -> list[dict]:
    """高中考点专题 + 小初章节讲义，统一成一份列表。

    小学/初中的条目带 `stage` 字段，`id` 是章 id（如 x11.1 / c71.1），
    没有精选题；高中的条目仍是考点 id，带 `questions`。
    """
    key = _sig()
    if _CACHE["key"] == key and _CACHE["v"] is not None:
        return _CACHE["v"]
    v = _read_manifest(MANIFEST) + _read_manifest(CHAPTER_MANIFEST)
    _CACHE["key"], _CACHE["v"] = key, v
    return v


def reload() -> None:
    """改完 manifest 后清缓存（同一进程里生成网页版时要用）。"""
    _CACHE.update({"key": None, "v": None})


SEL_DIR = TOPIC_DIR / "选题"


def _overlay(tid: str) -> dict:
    """用户在界面上「添加/移出」的题目，单独存一层，不动生成的 manifest。"""
    p = SEL_DIR / f"{tid}.json"
    if not p.is_file():
        return {"add": [], "remove": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"add": list(d.get("add") or []), "remove": list(d.get("remove") or []),
                "place": dict(d.get("place") or {})}
    except Exception:
        return {"add": [], "remove": [], "place": {}}


def merged(t: dict) -> dict:
    # 小初章节讲义没有精选题，也不参与「选题」覆盖层。
    if t.get("stage") in ("primary", "junior"):
        return {**t, "questions": [], "placements": {}}
    ov = _overlay(t.get("id", ""))
    rm = set(ov["remove"])
    qs = [k for k in (t.get("questions") or []) if k not in rm]
    for k in ov["add"]:
        if k not in qs:
            qs.append(k)
    place = {k: v for k, v in (ov.get("place") or {}).items() if k in qs and v}
    return {**t, "questions": qs, "placements": place}


def update_questions(tid: str, add: list[str], remove: list[str],
                     place_after: str = "") -> dict:
    """增删题目（写 数据/专题/选题/<id>.json）。返回合并后的专题。

    小初章节讲义是「只讲不练」的，直接拒绝，免得写入一份没人读的选题文件。
    """
    t = get(tid)
    if t is None:
        raise KeyError(tid)
    if t.get("stage") in ("primary", "junior"):
        raise ValueError("小初章节讲义不接练习，不能增删题目")
    ov = _overlay(tid)
    for k in add:
        if k in ov["remove"]:
            ov["remove"].remove(k)
        if k not in ov["add"]:
            ov["add"].append(k)
    place = ov.get("place") or {}
    for k in add:
        if place_after:
            place[k] = place_after
    for k in remove:
        if k in ov["add"]:
            ov["add"].remove(k)
        if k not in ov["remove"]:
            ov["remove"].append(k)
        place.pop(k, None)
    ov["place"] = place
    SEL_DIR.mkdir(parents=True, exist_ok=True)
    dst = SEL_DIR / f"{tid}.json"
    tmp = dst.with_suffix(".tmp")
    tmp.write_text(json.dumps(ov, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(dst)
    return get(tid) or {}


def get(tid: str) -> dict | None:
    t = next((x for x in load() if x.get("id") == tid), None)
    return merged(t) if t else None


def pdf_path(tid: str) -> Path | None:
    t = get(tid)
    if not t or not t.get("pdf"):
        return None
    p = TOPIC_DIR / t["pdf"]
    return p if p.is_file() else None


# ── 讲义页图：专题页不再用浏览器 PDF 阅读器（工具栏/暗底很难看），
#    改成服务端把每页渲成 PNG，前端当"书页"排下来 ──
PAGE_CACHE = TOPIC_DIR / "缓存"


def page_count(tid: str) -> int:
    p = pdf_path(tid)
    if not p:
        return 0
    try:
        import pymupdf
    except ImportError:                       # 老版本叫 fitz
        import fitz as pymupdf
    with pymupdf.open(p) as d:
        return d.page_count


def page_png(tid: str, n: int) -> Path | None:
    """第 n 页（1 起）的 PNG，缓存按 PDF mtime 失效。"""
    p = pdf_path(tid)
    if not p or n < 1:
        return None
    out = PAGE_CACHE / tid / f"{n}.png"
    if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
        return out
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    with pymupdf.open(p) as d:
        if n > d.page_count:
            return None
        page = d[n - 1]
        pix = page.get_pixmap(dpi=144)
        out.parent.mkdir(parents=True, exist_ok=True)
        pix.save(out)
    return out


def _selftest() -> int:
    ts = load()
    bad = 0
    for t in ts:
        if not t.get("id") or not t.get("title"):
            print("✗ 缺 id/title：", t); bad += 1
            continue
        if not pdf_path(t["id"]):
            print("✗ 讲义 PDF 缺失：", t.get("id")); bad += 1
        if t.get("stage") in ("primary", "junior"):
            if not t.get("points"):
                print("✗ 小初讲义没有挂知识点：", t.get("id")); bad += 1
        elif not t.get("questions"):
            print("✗ 没有精选题：", t.get("id")); bad += 1
    print(f"专题 {len(ts)} 个，问题 {bad} 个")
    print("通过" if not bad else "失败")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
