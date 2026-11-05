r"""删掉求解复核后剩下的 12 道（题干坏的 7 道 + 没把握的 5 道），走回收站。

来源：

* `数据/题库审阅/复核191_判定.json` 里 `v != "change"` 的 7 道（题干本身坏了）；
* `数据/题库审阅/求解结果/结果_*.txt` 里 `<状态>unsure</状态>` 的 5 道。

用户口径（2026-10-18）：这 12 道**全部删掉**，不再回原卷重录。
删前核对：数量必须是 12、都在库里、都还没有解析；删后逐题比对指纹，
除这 12 道外一个字节都不许变。

用法：

    python3 脚本/删求解剩余十二道.py --dry-run
    python3 脚本/删求解剩余十二道.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store, trash  # noqa: E402

REVIEW = ROOT / "数据" / "题库审阅" / "复核191_判定.json"
OUT_DIR = ROOT / "数据" / "题库审阅" / "求解结果"
RECORD = ROOT / "数据" / "题库审阅" / "删求解剩余十二道_20261018.json"
REASON = "结构性坏题（缺图/缺条件，无法作答）"

_TAG = re.compile(r"<(状态|核对|答案|解析|备注)>\s*(.*?)(?:</\1>|\Z)", re.S)


def blocks(text: str):
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("@@Q "):
            if cur is not None:
                yield cur, "\n".join(buf)
            cur, buf = line[4:].strip(), []
        elif line.strip() == "@@END":
            if cur is not None:
                yield cur, "\n".join(buf)
            cur, buf = None, []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        yield cur, "\n".join(buf)


def collect() -> tuple[list[str], list[str]]:
    broken = [k for k, v in json.loads(
        REVIEW.read_text(encoding="utf-8")).items() if v["v"] != "change"]
    unsure: list[str] = []
    for f in sorted(OUT_DIR.glob("结果_*.txt")):
        for key, body in blocks(f.read_text(encoding="utf-8")):
            t = {m.group(1): m.group(2).strip() for m in _TAG.finditer(body)}
            if t.get("状态") == "unsure":
                unsure.append(key)
    return broken, unsure


def fingerprint(qs) -> dict:
    return {q.key: hashlib.md5(json.dumps(
        [q.type, q.stem, q.answer, q.solution,
         [[o.label, o.text] for o in q.options],
         [f.id for f in (q.figures or [])]], ensure_ascii=False).encode()
    ).hexdigest() for q in qs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    broken, unsure = collect()
    todo = list(dict.fromkeys(broken + unsure))
    print(f"题干坏 {len(broken)} 道、unsure {len(unsure)} 道，合计 {len(todo)} 道")
    if (len(broken), len(unsure), len(todo)) != (7, 5, 12):
        print("✗ 数量与预期（7 + 5 = 12）不符，整批不删")
        return 1

    bank = {q.key: q for q in store.load_all()}
    missing = [k for k in todo if k not in bank]
    if missing:
        print("✗ 这些题号不在库里，整批不删：", missing)
        return 1
    solved = [k for k in todo if bank[k].has_solution]
    if solved:
        print("✗ 这些题已经有解析，不该按「没法做」删：", solved)
        return 1

    before = fingerprint(bank.values())
    before_n = len(bank)
    print(f"库里共 {before_n} 道；回收站现有 {trash.count()} 道")
    for k in todo:
        print(f"  · {k[:70]}  {bank[k].type}")
    if a.dry_run:
        print("[dry-run] 未动库")
        return 0

    pw = (ROOT / "数据" / "删题口令.txt").read_text(encoding="utf-8").strip()
    r = trash.delete(todo, reason=REASON, password=pw)
    if not r.get("ok"):
        print("✗ 没删：", r.get("error"))
        return 1
    print(f"\ndeleted={len(r['deleted'])}  not_found={r.get('not_found')}")

    after = {q.key: q for q in store.load_all()}
    print(f"记录数：{before_n} → {len(after)}（应少 12）")
    if len(after) != before_n - 12 or set(after) != set(before) - set(todo):
        print("✗ 数量或集合对不上")
        return 1
    after_fp = fingerprint(after.values())
    changed = [k for k in after_fp if after_fp[k] != before[k]]
    print("其余题目原文未变：", not changed)
    if changed:
        print("✗ 这些题被顺带改动了：", changed[:10])
        return 1

    box = {x.get("key"): x for x in trash.all_items()}
    bad = [k for k in todo if box.get(k, {}).get("reason") != REASON]
    print(f"回收站现有 {trash.count()} 道；12 道全部落箱：{not bad}")
    if bad:
        return 1

    RECORD.write_text(json.dumps({
        "date": "2026-10-18",
        "reason": REASON,
        "count": len(todo),
        "broken": broken,
        "unsure": unsure,
        "note": "已进回收站，可原样恢复；本文件只留题号名册。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("名册写到：", RECORD.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
