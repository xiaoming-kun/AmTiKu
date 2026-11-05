r"""删掉外部求解判为「题面坏了 / 缺图」的题（error 91 + needs_figure 6），走回收站。

来源：`数据/题库审阅/求解结果/结果_*.txt` 里 `<状态>error</状态>` 与
`<状态>needs_figure</状态>` 的块。用户口径（2026-10-18）：这两类**直接删除**，
不再回原卷重录；其余 `ok` / `unsure` 不动。

安全闸（任一不过就整批不删）：

1. 结果文件里的 error / needs_figure 数量必须正好是 91 / 6；
2. 97 个 key 必须都在库里；
3. 库里题干必须与求解批次喂给模型的题干**逐字相同**（防 key 漂移删错题）；
4. 删前删后逐题比对，除这 97 道外**一个字节都不许变**；
5. 回收站里必须落下这 97 条、原因一致。

用法：

    python3 脚本/删求解判坏的九十七道.py --dry-run   # 只核对，不删
    python3 脚本/删求解判坏的九十七道.py             # 真删（要 数据/删题口令.txt）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import store, trash  # noqa: E402

OUT_DIR = ROOT / "数据" / "题库审阅" / "求解结果"
BATCH_DIR = ROOT / "数据" / "题库审阅" / "求解批次"
RECORD = ROOT / "数据" / "题库审阅" / "求解判坏删除_20261018.json"
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


def tags(body: str) -> dict:
    return {m.group(1): m.group(2).strip() for m in _TAG.finditer(body)}


def collect() -> tuple[list[str], list[str]]:
    status: dict[str, str] = {}
    for f in sorted(OUT_DIR.glob("结果_*.txt")):
        for key, body in blocks(f.read_text(encoding="utf-8")):
            status.setdefault(key, tags(body).get("状态", ""))
    err = [k for k, s in status.items() if s == "error"]
    fig = [k for k, s in status.items() if s == "needs_figure"]
    return err, fig


def fingerprint(qs) -> dict:
    return {q.key: hashlib.md5(
        json.dumps([q.type, q.stem, q.answer, q.solution,
                    [[o.label, o.text] for o in q.options],
                    [f.id for f in (q.figures or [])]], ensure_ascii=False).encode()
    ).hexdigest() for q in qs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    err, fig = collect()
    print(f"结果文件：error {len(err)} 道，needs_figure {len(fig)} 道")
    if (len(err), len(fig)) != (91, 6):
        print("✗ 数量与用户口径（91/6）不符，整批不删")
        return 1
    todo = err + fig
    if len(set(todo)) != 97:
        print("✗ error / needs_figure 有重号，整批不删")
        return 1

    bank = {q.key: q for q in store.load_all()}
    missing = [k for k in todo if k not in bank]
    if missing:
        print("✗ 这些题号不在库里，整批不删：", missing[:10])
        return 1

    fed: dict[str, str] = {}
    for f in sorted(BATCH_DIR.glob("批次_*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                fed[r["key"]] = r["stem"]
    drift = [k for k in todo if fed.get(k, "").strip() != bank[k].stem.strip()]
    if drift:
        print("✗ 这些题的库内题干与喂给模型的题干不一致（怕 key 漂移），整批不删：")
        for k in drift[:10]:
            print("   ", k)
        return 1

    print(f"待删 {len(todo)} 道（error {len(err)} + needs_figure {len(fig)}），"
          f"库里共 {len(bank)} 道")
    print("题型分布：", dict(Counter(bank[k].type for k in todo)))
    print("\n前 5 道：")
    for k in todo[:5]:
        print(f"  · {k[:64]:66s} {bank[k].type:14s} 答案={bank[k].answer[:14]!r}")

    before = fingerprint(bank.values())
    before_n = len(bank)

    if a.dry_run:
        print(f"\n[dry-run] 核对通过，未动库。回收站现有 {trash.count()} 道。")
        return 0

    pw = (ROOT / "数据" / "删题口令.txt").read_text(encoding="utf-8").strip()
    r = trash.delete(todo, reason=REASON, password=pw)
    if not r.get("ok"):
        print("✗ 没删：", r.get("error"))
        return 1
    print(f"\ndeleted={len(r['deleted'])}  not_found={r.get('not_found')}")

    after = {q.key: q for q in store.load_all()}
    print(f"记录数：{before_n} → {len(after)}（应少 97）")
    if len(after) != before_n - 97:
        print("✗ 数量对不上")
        return 1
    if set(after) != set(before) - set(todo):
        print("✗ 少掉的不是该删的那批")
        return 1
    after_fp = fingerprint(after.values())
    changed = [k for k in after_fp if after_fp[k] != before[k]]
    print("其余题目原文未变：", not changed)
    if changed:
        print("✗ 这些题被顺带改动了：", changed[:10])
        return 1

    box = {x.get("key"): x for x in trash.all_items()}
    not_in_bin = [k for k in todo if k not in box]
    bad_reason = [k for k in todo if box.get(k, {}).get("reason") != REASON]
    print(f"回收站现有 {trash.count()} 道；97 道全部落箱：{not not_in_bin}；原因一致：{not bad_reason}")
    if not_in_bin or bad_reason:
        return 1

    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps({
        "date": "2026-10-18",
        "reason": REASON,
        "source": "数据/题库审阅/求解结果（外部模型求解，状态 error / needs_figure）",
        "count": len(todo),
        "error": err,
        "needs_figure": fig,
        "note": "已进回收站，可原样恢复；本文件只留题号名册。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("名册写到：", RECORD.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
