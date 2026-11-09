"""把小初 content JSON 全量渲染、编译、转网页版，并刷新 manifest。

    python3 脚本/小初讲义编译.py --workers 4
    python3 脚本/小初讲义编译.py --ids x11.2 c71.2
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import lecture_tex  # noqa: E402

BASE = ROOT / "数据" / "专题" / "小初"
CONTENT = BASE / "content"
REPORT = BASE / "build_report.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-html", action="store_true")
    a = ap.parse_args()
    ids = a.ids or sorted(p.stem for p in CONTENT.glob("*.json"))
    rows, bad = [], 0
    with ThreadPoolExecutor(max_workers=max(1, min(6, a.workers))) as pool:
        futs = {pool.submit(lecture_tex.check_one, cid): cid for cid in ids}
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            if r.get("ok"):
                print("OK", r.get("id"), "%s 页 %s 字" % (r.get("pages"), r.get("chars")), flush=True)
            else:
                bad += 1
                print("ERR", r.get("id"), (r.get("error") or "").strip().splitlines()[0], flush=True)
    rows.sort(key=lambda x: str(x.get("id")))
    print("编译：%d 章，失败 %d" % (len(ids), bad), flush=True)
    m = lecture_tex.sync_manifest()
    print("manifest:", m, flush=True)
    if not a.no_html:
        ok_html, bad_html = 0, 0
        with ThreadPoolExecutor(max_workers=max(1, min(6, a.workers))) as pool:
            futs = {pool.submit(lecture_tex.build_html, cid): cid for cid in ids if
                    (BASE / f"{cid}.pdf").is_file()}
            for fut in as_completed(futs):
                cid = futs[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = {"ok": False, "error": str(e)}
                if r.get("ok"):
                    ok_html += 1
                else:
                    bad_html += 1
                    print("ERR html", cid, r.get("error"), flush=True)
        print("网页版：%d 成功，%d 失败" % (ok_html, bad_html), flush=True)
        bad += bad_html
    REPORT.write_text(json.dumps({"rows": rows, "failed": bad}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
