"""改完 normalize 的干跑审计（第二版：逐字符 diff，不把「改了」误报成「删了」）。

第一版的尺是错的：它按整行比对，答案槽里少一个「。」会让整行"消失"，
于是把 142 行**改过**的正文报成"被删"。这一版用 difflib 逐字符取差异，
只统计真正**从文本里消失**的片段。
"""
import argparse
import copy
import difflib
import re
import sys
from collections import Counter

sys.path.insert(0, "/Users/ximing/Documents/AmTiKu")
from amti import normalize as N
from amti import store

AP = argparse.ArgumentParser()
AP.add_argument("--only", default="", help="只看规则名含此子串的")
A = AP.parse_args()

fired = Counter()
gone_frags = Counter()        # 真正消失的片段
changed_only = Counter()      # 只改不删的（例如槽里去掉句号）
examples = {}

for _v, q in store.iter_questions():
    q2 = copy.deepcopy(q)
    applied = N.normalize(q2, scope=N.MIGRATE)
    hit = [n for n in applied if (not A.only or A.only in n)]
    if not hit:
        continue
    for name in hit:
        fired[name] += 1
        examples.setdefault(name, [])
        if len(examples[name]) < 5:
            examples[name].append(q.key)
    for fld in ("stem", "answer", "solution"):
        old = getattr(q, fld) or ""
        new = getattr(q2, fld) or ""
        if old == new:
            continue
        sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
        dele = "".join(old[i1:i2] for tag, i1, i2, _j1, _j2 in sm.get_opcodes()
                       if tag in ("delete", "replace")).strip()
        ins = "".join(new[j1:j2] for tag, _i1, _i2, j1, j2 in sm.get_opcodes()
                      if tag in ("insert", "replace")).strip()
        if dele:
            gone_frags[dele[:80]] += 1
        elif ins:
            changed_only[ins[:60]] += 1

print("命中的 MIGRATE 规则：")
for name, n in fired.most_common():
    print(f"  {n:5d}  {name}   例：{examples[name]}")

print(f"\n【A】真正从文本里**消失**的片段，去重 {len(gone_frags)} 种：")
for frag, n in gone_frags.most_common(45):
    print(f"  {n:4d}  {frag!r}")

print("\n【B】只增改不删的片段（去重 %d 种）：" % len(changed_only))
for frag, n in changed_only.most_common(12):
    print(f"  {n:4d}  {frag!r}")

NOISE = re.compile(r"第\s*\d+\s*页|共\s*\d+\s*页|参考答案|解析|选择题|填空题|解答题|"
                   r"数学|试题|试卷|Page|页|^\s*$|^[\s:：。；;，,、.]+$")
bad = [(f, n) for f, n in gone_frags.items() if not NOISE.search(f)]
print(f"\n判定：消失片段里**不含任何噪声词**的 {len(bad)} 种 / 共 "
      f"{sum(n for _f, n in bad)} 处 —— 这些要逐条看：")
for f, n in bad[:25]:
    print(f"  {n:4d}  {f!r}")
