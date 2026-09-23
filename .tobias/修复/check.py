#!/usr/bin/env python3
"""校验一批 fixups 台账条目（只验证，不含任何修复规则）。

用法：python3 .tobias/修复/check.py .tobias/修复/r01.json
对每个条目检查：
  1. expect 能对上当前题（漂移则报错）；
  2. 按 set 试改后 schema.problems() 为空；
  3. 按 set 试改后 conform 规范审查 0 违规；
  4. 答案与卷面一致：选择题 \\paren[…] 必须等于 answer，
     填空题 \\fillin[…] 的内容必须包含 answer。
exit 0 = 全部通过。
"""
import copy
import json
import sys

sys.path.insert(0, ".")
from amti import conform, store          # noqa: E402
from amti.fixups import _apply_one, _check_expect  # noqa: E402


def slot(stem: str) -> str:
    for cmd in ("\\paren[", "\\fillin["):
        i = stem.find(cmd)
        if i >= 0:
            return stem[i:stem.find("]", i) + 1]
    return ""


def main() -> int:
    path = sys.argv[1]
    patches = json.loads(open(path, encoding="utf-8").read())
    by = {q.key: q for q in store.load_all()}
    fails = 0
    for p in patches:
        key = p.get("key", "?")
        if p.get("skip"):
            print("SKIP  %s  — %s" % (key, (p.get("reason") or "")[:70]))
            continue
        q = by.get(key)
        if q is None:
            print("✗ %s：题不在库" % key)
            fails += 1
            continue
        for w in _check_expect(q, p.get("expect") or {}):
            print("✗ %s：expect 对不上（%s）" % (key, w))
            fails += 1
            break
        probe = copy.deepcopy(q)
        try:
            _apply_one(probe, p, by)
        except Exception as e:
            print("✗ %s：set 应用失败 %s" % (key, e))
            fails += 1
            continue
        probs = probe.problems()
        if probs:
            print("✗ %s：改后仍有结构问题 %s" % (key, probs))
            fails += 1
        viol = conform.run([probe])
        if viol:
            print("✗ %s：改后不规范 %s/%s %s"
                  % (key, viol[0]["check"], viol[0]["field"], viol[0]["why"]))
            fails += 1
        # 答案 ↔ 卷面
        if probe.type in ("single_choice", "multi_choice"):
            want = "\\paren[%s]" % probe.answer.strip()
            if want not in probe.stem:
                print("✗ %s：卷面作答括号与答案不一致（要 %s，卷面 %s）"
                      % (key, want, slot(probe.stem)))
                fails += 1
        elif probe.type == "fill_in_blank" and probe.answer.strip():
            s = slot(probe.stem)
            if probe.answer.strip() not in s:
                print("✗ %s：填空位 %s 与答案 %s 不一致"
                      % (key, s, probe.answer))
                fails += 1
    n_ok = len(patches) - fails
    print(("全部通过（%d 条）" % len(patches)) if not fails
          else ("有 %d 处失败 / 共 %d 条" % (fails, len(patches))))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
