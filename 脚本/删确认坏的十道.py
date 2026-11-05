"""删掉确认坏的 10 道（A11 的 2 + A12 的 8），走回收站（可 --restore 恢复）。

A11 另外 11 道**没删**：逐张开图核过，选项都在图条上、A./B./C./D. 标签齐全，
是探针判据错了，不是题坏了。
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/ximing/Documents/AmTiKu")
from amti import store, trash

KEYS = json.load(open("/tmp/del_keys2.json"))
todo = KEYS["A11"] + KEYS["A12"]
print(f"待删 {len(todo)} 道（A11 {len(KEYS['A11'])} + A12 {len(KEYS['A12'])}）")

by_key = {q.key: q for q in store.load_all()}
miss = [k for k in todo if k not in by_key]
if miss:
    print("!! 这些 key 在库里找不到，整批不删：", miss)
    sys.exit(1)
for k in todo:
    q = by_key[k]
    print(f"  · {k[:56]:58s} {q.type:14s} 答案={q.answer[:16]!r}")

before_n = len(by_key)
before_hash = hashlib.md5(json.dumps(
    {k: (v.stem, v.answer) for k, v in sorted(by_key.items())},
    ensure_ascii=False).encode()).hexdigest()

pw = Path("/Users/ximing/Documents/AmTiKu/数据/删题口令.txt").read_text(encoding="utf-8").strip()
r = trash.delete(todo, reason="结构性坏题（缺图/缺条件，无法作答）", password=pw)
if not r.get("ok"):
    print("✗ 没删：", r.get("error"))
    sys.exit(1)
print(f"\ndeleted={len(r['deleted'])}  not_found={r.get('not_found')}")

after = {q.key: q for q in store.load_all()}
print(f"记录数：{before_n} → {len(after)}（应少 {len(todo)}）")
assert len(after) == before_n - len(todo), "数量对不上"
assert set(after) == set(by_key) - set(todo), "少掉的不是该删的那批"
# 其余题一个字节都没动
same = all(after[k].stem == by_key[k].stem and after[k].answer == by_key[k].answer
           for k in after)
print("其余题目原文未变：", same)
assert same
print("回收站现共", trash.count(), "道")
Path("/tmp/deleted_keys.json").write_text(json.dumps(todo, ensure_ascii=False, indent=1))
