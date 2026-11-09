"""用 DeepSeek 审校小初讲义内容：数学错误、超纲、表述不清、模板问题。

    python3 脚本/小初讲义审校.py --all --workers 4
    python3 脚本/小初讲义审校.py --ids x11.3 c71.2

只读 content JSON，把问题写到 `数据/专题/小初/review_report.json`；不改文件。
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

BASE = ROOT / "数据" / "专题" / "小初"
CONTENT = BASE / "content"
DOSSIER = BASE / "dossiers"
REPORT = BASE / "review_report.json"

SYSTEM = (
    "你是严谨的 K12 数学教研员，负责审校讲义。"
    "你只输出一个合法 JSON 对象，不输出 Markdown 围栏、不解释。"
    "宁可多报一个可疑点，也不要把错误放过。"
)

CHECKLIST = """逐项检查：
1. 定义、公式、法则是否准确；有没有把条件写漏（如除数不为 0、二次根式非负、三角形三边关系）。
2. 每个例题、表格、图中的数字是否算对；答案与解析是否一致。
3. 有没有超纲：小学不要用方程/函数/负数（除非本章就是负数）；初中不要用导数、向量、圆锥曲线。
4. 有没有前后矛盾：同一份讲义里对同一个概念的说法是否一致。
5. 有没有把“几个”和“第几”、周长和面积、体积和容积、因数与倍数等混淆。
6. 有没有编造教材页码、作者、定理名。
7. 有没有习题化表述（练习/习题/选择题/填空题/下列各题）。
8. 图形/表格是否与文字一致；TikZ 坐标是否明显画错。
"""


def _prompt(c: dict, d: dict) -> str:
    return f"""请审校这份小初数学讲义 content JSON。

【本章知识点】
{json.dumps(d.get('points') or [], ensure_ascii=False, indent=1)}

【讲义 JSON】
{json.dumps(c, ensure_ascii=False, indent=1)}

{CHECKLIST}

只输出：
{{"ok": true/false, "issues": [{{"severity": "high/medium/low", "field": "章节/字段", "problem": "具体问题", "fix": "建议怎么改"}}]}}
没有问题就输出 {{"ok": true, "issues": []}}。
"""


def review_one(cid: str) -> dict:
    cp = CONTENT / f"{cid}.json"
    dp = DOSSIER / f"{cid}.json"
    if not cp.is_file():
        return {"id": cid, "ok": False, "issues": [{"severity": "high", "problem": "缺 content JSON"}]}
    c = json.loads(cp.read_text(encoding="utf-8"))
    d = json.loads(dp.read_text(encoding="utf-8")) if dp.is_file() else {}
    last = ""
    for attempt in range(1, 3):
        try:
            raw = deepseek.chat(_prompt(c, d), system=SYSTEM, json_mode=True,
                                max_tokens=4096, timeout=300)
            s = raw.strip()
            i, j = s.find("{"), s.rfind("}")
            r = json.loads(s[i:j + 1])
            r["id"] = cid
            r.setdefault("issues", [])
            return r
        except Exception as e:
            last = str(e)
            time.sleep(2 * attempt)
    return {"id": cid, "ok": False, "issues": [{"severity": "high", "problem": "审校失败：" + last[:300]}]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ids", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    ids = a.ids or sorted(p.stem for p in CONTENT.glob("*.json"))
    rows = []
    with ThreadPoolExecutor(max_workers=max(1, min(6, a.workers))) as pool:
        futs = {pool.submit(review_one, cid): cid for cid in ids}
        for fut in as_completed(futs):
            r = fut.result()
            rows.append(r)
            n = len(r.get("issues") or [])
            print(("OK " if r.get("ok") and not n else "!! ") + str(r.get("id")) +
                  " issues=%d" % n, flush=True)
            for x in (r.get("issues") or [])[:3]:
                print("   -", x.get("severity"), x.get("problem"), flush=True)
    rows.sort(key=lambda x: str(x.get("id")))
    REPORT.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in rows if not r.get("ok") or r.get("issues")]
    print("审校 %d 份，有问题 %d 份 -> %s" % (len(rows), len(bad), REPORT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
