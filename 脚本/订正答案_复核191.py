r"""把 191 道 `mismatch` 的人工复核结论写进题库（答案 + 解析 + 必要的题型/解析订正）。

输入：`数据/题库审阅/复核191_判定.json`
      `{key: {"v": "change"|"broken", "ans": "…", "type": "…"(可选), "why": "…"}}`

口径（2026-10-18 逐题复核）：

* `change`：按**题库里印着的题干**独立重算，求解器给的答案是对的 → 改 `answer`，
  并把求解解析写进 `solution`（解析里若混了「题库/原卷/疑」这类元话，先剔掉）；
* `broken`：题干本身坏了（记号残缺、答案嵌进题面、选项与题面无交集），
  改了也只是把错固化成另一种样子 → **不动**，列出来等回原卷重录。

写库沿用界面改答案同一条路：`_clean_answer_input` → `norm.normalize(…, ENTRY)`
（把新答案写进 `\paren[…]`／`\fillin[…]`）→ 逐题规范审查。
写前写后都比对「去掉作答位之后的题干、选项、配图」：只许动作答位，正文一个字节不许动。

用法：

    python3 脚本/订正答案_复核191.py --dry-run
    python3 脚本/订正答案_复核191.py
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import conform, normalize, store  # noqa: E402
from amti.web.server import _clean_answer_input  # noqa: E402

VERDICTS = ROOT / "数据" / "题库审阅" / "复核191_判定.json"
RECORD = ROOT / "数据" / "题库审阅" / "复核191_落账_20261018.json"

_SLOT = re.compile(
    r"\\(paren|fillin)\s*(\[[^\]]*\])?\s*(\{[^{}]*\})?"
    r"|[（(]\s*(?:\\quad|\\qquad)?\s*[）)]")
_FILLIN = re.compile(r"\\fillin\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]")
_PAREN = re.compile(r"\\paren\s*\[([^\]]*)\]")
_META = re.compile(r"题库|原卷|原答案|参考答案|疑为|录入|抄错|串入|串题")

# 解析里的元话（只在 #15 一处），剔掉后才是学生能看的解析。
SOLUTION_PATCH = {
    "模拟题/2026届安徽高三上学期第三次教学质量检测#4": (
        "按选项应选 B，而题库标注 D（既不充分也不必要）与「异面必不相交」这一基本事实矛盾。故选 B。",
        "按选项应选 B。",
    ),
}


def outside_answer(q) -> tuple:
    r"""去掉作答位之后的内容快照（题干、选项、配图）。"""
    return (re.sub(r"\s+", "", _SLOT.sub("§", q.stem or "")),
            tuple((o.label, o.text) for o in q.options),
            tuple(f.id for f in (q.figures or [])))


def slots_ok(q) -> bool:
    r"""作答位里印的必须就是 `answer`。"""
    if q.type in ("single_choice", "multi_choice"):
        hits = [x.strip() for x in _PAREN.findall(q.stem)]
        return len(hits) == 1 and hits[0] == q.answer
    if q.type == "fill_in_blank":
        holes = _FILLIN.findall(q.stem)
        parts = normalize.split_answers(q.answer, len(holes))
        return bool(parts) and len(parts) == len(holes) and all(
            a.strip() == b.strip() for a, b in zip(holes, parts))
    return True


def fingerprint(q) -> str:
    return hashlib.md5(json.dumps(
        [q.type, q.stem, q.answer, q.solution,
         [[o.label, o.text] for o in q.options],
         [f.id for f in (q.figures or [])]], ensure_ascii=False).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    verdicts = json.loads(VERDICTS.read_text(encoding="utf-8"))
    bank = {q.key: q for q in store.load_all()}
    print(f"判定 {len(verdicts)} 道：change {sum(1 for v in verdicts.values() if v['v'] == 'change')}，"
          f"broken {sum(1 for v in verdicts.values() if v['v'] != 'change')}")

    # 解析正文从求解结果里取（与落账同一来源）
    sys.path.insert(0, str(ROOT / "脚本"))
    from importlib import import_module
    results = import_module("落账求解结果").collect()

    todo: dict[str, object] = {}
    skipped: dict[str, list[str]] = {}
    changes: dict[str, dict] = {}
    for key, v in verdicts.items():
        if v["v"] != "change":
            continue
        q0 = bank.get(key)
        if q0 is None:
            skipped[key] = ["不在库里"]
            continue
        sol = (results.get(key, {}).get("解析") or "").strip()
        if key in SOLUTION_PATCH:
            old, new = SOLUTION_PATCH[key]
            if old not in sol:
                skipped[key] = ["解析订正锚点没找到"]
                continue
            sol = sol.replace(old, new)
        if _META.search(sol):
            skipped[key] = ["解析里有元话：%s" % _META.search(sol).group(0)]
            continue
        q = copy.deepcopy(q0)
        before = outside_answer(q)
        try:
            if v.get("type"):
                q.type = v["type"]
            q.answer = _clean_answer_input(q, v["ans"])
            if sol:
                q.solution = sol
            normalize.normalize(q, normalize.ENTRY)
        except Exception as e:
            skipped[key] = ["规整失败：%s" % str(e)[:80]]
            continue
        if outside_answer(q) != before:
            skipped[key] = ["动了作答位以外的题干/选项"]
            continue
        if not slots_ok(q):
            skipped[key] = ["作答位没跟上答案"]
            continue
        viol = conform.run([q])
        if viol:
            skipped[key] = ["不规范：%s（%s）" % (viol[0]["why"], viol[0]["check"])]
            continue
        q.meta["answer_source"] = "human"
        q.meta["solution_source"] = "workbuddy"
        q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
        todo[key] = q
        changes[key] = {"before": q0.answer, "after": q.answer,
                        "type": [q0.type, q.type] if q0.type != q.type else None,
                        "why": v["why"]}

    print(f"可写 {len(todo)} 道；跳过 {len(skipped)} 道")
    for k, why in list(skipped.items())[:20]:
        print("  ✗", k, "｜", "；".join(why))
    if a.dry_run:
        print("[dry-run] 未写库")
        return 0

    before_fp = {q.key: fingerprint(q) for q in bank.values()}

    def _do(qs):
        n = 0
        for i, q in enumerate(qs):
            new = todo.get(q.key)
            if new is None:
                continue
            qs[i] = new
            n += 1
        print(f"  update() 内替换 {n} 道")
        return qs

    rep = store.update(_do)
    print(f"写回：changed={len(rep.get('changed', []))} volumes={rep.get('volumes')}")

    after = {q.key: q for q in store.load_all()}
    if len(after) != len(before_fp):
        print("✗ 题数变了"); return 1
    after_fp = {q.key: fingerprint(q) for q in after.values()}
    changed = [k for k in before_fp if before_fp[k] != after_fp[k]]
    if set(changed) != set(todo):
        print("✗ 改动集合不符：多 %s 少 %s"
              % (sorted(set(changed) - set(todo))[:5], sorted(set(todo) - set(changed))[:5]))
        return 1
    bad = [k for k in todo if after[k].answer != todo[k].answer or after[k].solution != todo[k].solution
           or after[k].type != todo[k].type]
    if bad:
        print("✗ 写入值不符：", bad[:5]); return 1
    print(f"题数不变：{len(after)}；改动 {len(changed)} 道，写回值全部核对一致")

    RECORD.write_text(json.dumps({
        "date": "2026-10-18",
        "source": "数据/题库审阅/求解结果（外部模型求解）+ 逐题人工复核",
        "rule": "以题库题干为准独立重算；答案改对、写入解析；题干坏的不动",
        "changed": len(todo),
        "skipped": skipped,
        "broken": {k: v["why"] for k, v in verdicts.items() if v["v"] != "change"},
        "detail": changes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("记录写到：", RECORD.relative_to(ROOT))
    print("题型：", dict(Counter(after[k].type for k in todo)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
