"""按审校报告修正小初讲义 content JSON。

    python3 脚本/小初讲义修复.py --severity high medium --workers 4
    python3 脚本/小初讲义修复.py --ids c71.3 --dry

修正后先 validate，再试编译；编译不过就保留原文件，不把好文件改坏。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import deepseek  # noqa: E402
from amti import lecture_tex  # noqa: E402

BASE = ROOT / "数据" / "专题" / "小初"
CONTENT = BASE / "content"
DOSSIER = BASE / "dossiers"
REPORT = BASE / "review_report.json"
OUT = BASE / "repair_report.json"

SYSTEM = (
    "你是严谨的 K12 数学教研员。你根据审校意见修正讲义，"
    "只输出完整的合法 JSON 对象，不输出 Markdown 围栏、不解释。"
    "数学必须正确；不要改没问题的内容；不排习题；不写裸 ~。"
)


def _prompt(c: dict, d: dict, issues: list[dict]) -> str:
    return f"""请按审校意见修正下面这份小初数学讲义，输出**完整的修正后 JSON**。

【本章知识点】
{json.dumps(d.get('points') or [], ensure_ascii=False, indent=1)}

【审校意见】
{json.dumps(issues, ensure_ascii=False, indent=1)}

【原讲义 JSON】
{json.dumps(c, ensure_ascii=False, indent=1)}

修正要求：
1. 逐条处理审校意见；如果某条是误报，可以不改，但不要引入新错误。
2. 只改有问题的句子/公式/图/表，保留原来的结构、章节和大部分内容。
3. 修正后仍是同一章，字段齐全；不排习题，不写裸 ~，所有公式必须放在 $...$ 或 \\[...\\] 里；
   不用 \\documentclass/\\chapter/\\includegraphics。
4. **教材册次/章号以本章素材的 book/chapter 为准**；审校意见里说“人教版应为第 X 章/第 X 页”的，
   可能是旧版教材记忆，一律不要据此改 subtitle/source_note。
5. 每个改动过的公式、例题都要自己验算；图与表的数据必须和正文一致。
6. 只输出 JSON 对象。
"""


def _extract(s: str) -> dict:
    s = s.strip()
    if s.startswith("```"):
        s = s.replace("```json", "").replace("```", "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("回复里没有 JSON")
    return json.loads(s[i:j + 1])


def repair_one(cid: str, issues: list[dict], dry: bool = False) -> dict:
    cp = CONTENT / f"{cid}.json"
    dp = DOSSIER / f"{cid}.json"
    if not cp.is_file():
        return {"id": cid, "ok": False, "msg": "缺 content"}
    old_text = cp.read_text(encoding="utf-8")
    old = json.loads(old_text)
    d = json.loads(dp.read_text(encoding="utf-8")) if dp.is_file() else {}
    last = ""
    for attempt in range(1, 4):
        try:
            raw = deepseek.chat(_prompt(old, d, issues), system=SYSTEM,
                                json_mode=True, max_tokens=8192, timeout=300)
            c = _extract(raw)
            c["id"] = cid
            bad = lecture_tex.validate_content(c, cid)
            if bad:
                last = "；".join(bad)
                issues = issues + [{"severity": "high", "problem": "修正版校验失败：" + last,
                                    "fix": "修好这些结构问题"}]
                continue
            if dry:
                return {"id": cid, "ok": True, "msg": "dry-run 通过，未写盘"}
            cp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
            chk = lecture_tex.check_one(cid)
            if not chk.get("ok"):
                cp.write_text(old_text, encoding="utf-8")
                return {"id": cid, "ok": False,
                        "msg": "修正版编译失败，已回滚：" + (chk.get("error") or "")[:200]}
            return {"id": cid, "ok": True, "msg": "已修正并编译通过"}
        except Exception as e:
            last = str(e)
            time.sleep(2 * attempt)
    return {"id": cid, "ok": False, "msg": last[:300]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--severity", nargs="*", default=["high", "medium"])
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    rep = json.loads(pathlib.Path(a.report).read_text(encoding="utf-8"))
    rows = rep.get("rows") or []
    tasks = {}
    for r in rows:
        cid = r.get("id")
        if a.ids and cid not in a.ids:
            continue
        if not cid:
            continue
        issues = [x for x in (r.get("issues") or [])
                  if str(x.get("severity") or "").lower() in a.severity]
        if issues:
            tasks[cid] = issues
    if not tasks:
        print("没有需要修的条目")
        return 0
    out = []
    with ThreadPoolExecutor(max_workers=max(1, min(6, a.workers))) as pool:
        futs = {pool.submit(repair_one, cid, issues, a.dry): cid
                for cid, issues in tasks.items()}
        for fut in as_completed(futs):
            r = fut.result()
            out.append(r)
            print(("OK " if r.get("ok") else "ERR ") + str(r.get("id")) + " " + str(r.get("msg")),
                  flush=True)
    out.sort(key=lambda x: str(x.get("id")))
    OUT.write_text(json.dumps({"rows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = sum(1 for x in out if not x.get("ok"))
    print("修复 %d 份，失败 %d -> %s" % (len(out), bad, OUT))
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
