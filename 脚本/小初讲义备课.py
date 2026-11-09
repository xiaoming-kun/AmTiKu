"""给小学/初中每一章备一份「讲义素材」：知识点、诊断题、现有开源讲义。

只读 `知识地图.json` / `小初诊断题.json` / `数据/开源讲义/manifest.json`，
写到 `数据/专题/小初/dossiers/<章id>.json`。生成讲义内容的代理只读这份素材。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "知识地图.json"
DIAG = ROOT / "小初诊断题.json"
OPEN = ROOT / "数据" / "开源讲义"
OUT = ROOT / "数据" / "专题" / "小初" / "dossiers"


def _chapter_id(points: list[dict]) -> str:
    for p in points:
        pid = str(p.get("id") or "")
        if re.match(r"^[xc]\d+\.\d+\.\d+$", pid):
            return pid.rsplit(".", 1)[0]
    return ""


def main() -> int:
    tree = json.loads(MAP.read_text(encoding="utf-8"))
    diag = json.loads(DIAG.read_text(encoding="utf-8")).get("points", {})
    open_manifest = json.loads((OPEN / "manifest.json").read_text(encoding="utf-8"))
    by_book_chapter = {}
    for s in open_manifest.get("series", []):
        for lec in s.get("lectures", []):
            key = (lec.get("book"), lec.get("chapter"))
            if key[0] and key[1] and key not in by_book_chapter:
                md = lec.get("md") or ""
                text = ""
                p = OPEN / md
                if p.is_file():
                    text = p.read_text(encoding="utf-8")
                by_book_chapter[key] = {
                    "title": lec.get("title"),
                    "md": md,
                    "text": text,
                    "source": {
                        "series": s.get("title"),
                        "author": s.get("author"),
                        "license": s.get("license"),
                        "url": s.get("source"),
                    },
                }
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for stage in tree.get("stages", []):
        skey = stage.get("key")
        if skey not in ("primary", "junior"):
            continue
        seq = 0
        for book in stage.get("books", []):
            for ch in book.get("chapters", []):
                seq += 1
                points = ch.get("points") or []
                cid = _chapter_id(points)
                if not cid:
                    continue
                ds = []
                seen = set()
                for p in points:
                    for q in diag.get(p["id"], []) or []:
                        key = (q.get("prompt"), q.get("answer"))
                        if key in seen:
                            continue
                        seen.add(key)
                        ds.append({
                            "point": p["id"],
                            "point_title": p.get("title"),
                            "prompt": q.get("prompt"),
                            "answer": q.get("answer"),
                            "explanation": q.get("explanation"),
                            "choices": q.get("choices") or [],
                            "level": q.get("level"),
                        })
                existing = by_book_chapter.get((book.get("name"), ch.get("title")))
                dossier = {
                    "id": cid,
                    "stage": skey,
                    "stage_name": stage.get("name"),
                    "grade": int(str(book.get("name", "1"))[0]) if str(book.get("name", ""))[:1].isdigit() else 0,
                    "book": book.get("name"),
                    "chapter": ch.get("title"),
                    "seq": seq,
                    "stars": 2 if skey == "junior" else 1,
                    "points": points,
                    "diagnostics": ds[:12],
                    "existing": existing or {},
                }
                (OUT / f"{cid}.json").write_text(
                    json.dumps(dossier, ensure_ascii=False, indent=1), encoding="utf-8")
                total += 1
    print("dossiers:", total, "->", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
