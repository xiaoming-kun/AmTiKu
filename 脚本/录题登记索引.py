#!/usr/bin/env python3
r"""全库检索「待复核」登记（`.待复核.json`）——按关键词查，不按题号查。

为什么要有这把尺：铁律要求每个疑点都登记，但**登记常挂在相邻题号或整场级条目下**。
实测 #514#3 的解析断口登记在 **相邻题号 4** 名下，按「题号==3」筛该场待复核会判成
「没登记过」⇒ 报出假的净新增。所以查登记只能按**关键词搜整场全文**。

只读：不写 题目/、不写 输出_v2/、不动 队列.json / 进度.jsonl。索引默认打 stdout，
要留档自己重定向（`--out` 只允许写到 数据/录题/ 下面）。

用法：
  python3 脚本/录题登记索引.py find 断 半句 ...        # 关键词（全部命中才算，子串匹配）
  python3 脚本/录题登记索引.py find --type print-suspect 印坏
  python3 脚本/录题登记索引.py find --book 514 --context 整场
  python3 脚本/录题登记索引.py find --where 说明 缺页
  python3 脚本/录题登记索引.py stats
  python3 脚本/录题登记索引.py refs 514               # 这一场里「说明引用的题号≠自己那格」的条
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V2 = os.path.join(ROOT, "数据/录题/输出_v2")
FIELDS = ("原文", "说明")          # 默认检索范围：登记正文两个字段
TYPES = ("figure", "table", "figure-in-solution", "print-suspect", "missing-option")

# 说明里指代「题」的写法。数字必须落在 1—19 才算题号（本批每卷 19 题以内）。
REF_PATTERNS = (
    re.compile(r"#\s*(\d{1,2})(?:\s*[—–\-]\s*#?\s*(\d{1,2}))?"),
    re.compile(r"第\s*(\d{1,2})\s*题(?:\s*[—–\-]\s*第?\s*(\d{1,2})\s*题)?"),
    re.compile(r"(?<![0-9.$\\])(\d{1,2})\s*[—–\-]\s*(\d{1,2})\s*题"),
)
def _norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def load(books=None):
    """返回登记条目列表。每条补三个派生键：_文件 / _序号 / _卷名。

    books: 序号集合（str），只取这些场的登记。
    """
    out = []
    for fn in sorted(os.listdir(V2)):
        if not fn.endswith(".待复核.json"):
            continue
        num = fn.split("_", 1)[0]
        if books and num not in books:
            continue
        try:
            recs = json.load(open(os.path.join(V2, fn), encoding="utf-8"))
        except Exception as e:                                  # 坏 JSON 也要报出来而不是静默跳过
            print(f"!! 读不了 {fn}: {e}", file=sys.stderr)
            continue
        for i, r in enumerate(recs if isinstance(recs, list) else []):
            r = dict(r)
            r["_文件"] = fn
            r["_序号"] = num
            r["_卷名"] = fn[len(num) + 1:-len(".待复核.json")]
            r["_条号"] = i
            out.append(r)
    return out


def qnums(num):
    """某场成品里真实存在的题号集合；成品缺失或读不动时返回 None（不可判）。"""
    for fn in os.listdir(V2):
        if fn.startswith(num + "_") and fn.endswith(".成品.json"):
            try:
                book = json.load(open(os.path.join(V2, fn), encoding="utf-8"))
            except Exception:
                return None
            qs = book if isinstance(book, list) else (book.get("questions") or book.get("题目") or [])
            got = {q["题号"] for q in qs
                   if isinstance(q, dict) and isinstance(q.get("题号"), int)}
            return got or None
    return None


def refs_in(text):
    """抽出说明里引用的题号，返回 (题号集合, 是否可疑)。区间端点一起收。"""
    hits = set()
    for pat in REF_PATTERNS:
        for m in pat.finditer(text or ""):
            pre = text[max(0, m.start() - 3):m.start()]
            if re.search(r"(页|第)\s*$", pre):                   # 「第 2 页 3」这种不是题号
                continue
            for g in m.groups():
                if g and 1 <= int(g) <= 19:
                    hits.add(int(g))
    return hits


def cmd_find(args):
    recs = load(set(args.book) if args.book else None)
    kw = [_norm(k) for k in args.keywords]
    fields = args.where or list(FIELDS)
    rows = []
    for r in recs:
        if args.type and r.get("类型") != args.type:
            continue
        if args.book and r["_序号"] not in set(args.book):
            continue
        hay = _norm("".join(str(r.get(f) or "") for f in fields))
        if not hay:
            continue
        if all(k in hay for k in kw):
            rows.append(r)
    print(f"命中 {len(rows)} 条 / 全库 {len(recs)} 条")
    for r in rows:
        print(f"\n【{r['_序号']}·{r['_卷名']}】#{r.get('题号')} {r.get('题型')} "
              f"页{r.get('页码')} 类型={r.get('类型')}")
        for f in fields:
            v = str(r.get(f) or "").strip()
            if v:
                print(f"  {f}: {v[:600]}")
    if args.context == "整场":
        seen = {(r["_序号"], r["_条号"]) for r in rows}
        rest = [r for r in recs if (r["_序号"], r["_条号"]) not in seen]
        if rest:
            print(f"\n—— 命中所在场次另有 {len(rest)} 条未命中登记"
                  f"（整场上下文，勿据此判定「没登记」）——")
            for r in rest:
                print(f"  {r['_序号']}#{r.get('题号')} [{r.get('类型')}] "
                      f"{str(r.get('说明') or '')[:60]}")
    return 0


def cmd_stats(args):
    recs = load()
    print(f"登记总条数 {len(recs)}")
    print("按类型", dict(Counter(str(r.get("类型")) for r in recs).most_common()))
    print("按场数 ", len({r["_序号"] for r in recs}))
    print("键集合 ", dict(Counter(tuple(sorted(k for k in r if not k.startswith("_")))
                               for r in recs).most_common(6)))
    return 0


def cmd_refs(args):
    """某一场里「说明引用的题号 ≠ 自己那格题号」的登记条 ⇒ 题号筛的盲区清单。"""
    num = str(args.book)
    recs = load({num})
    valid = qnums(num)
    print(f"场 {num}：登记 {len(recs)} 条，成品题号 {sorted(valid) if valid else '不可判'}")
    n = 0
    for r in recs:
        own = r.get("题号")
        quoted = refs_in(str(r.get("说明") or "") + str(r.get("原文") or ""))
        foreign = {q for q in quoted if q != own}
        if foreign:
            n += 1
            print(f"  #{own} [{r.get('类型')}] 引用了 {sorted(foreign)}")
            print(f"      说明: {str(r.get('说明') or '')[:220]}")
    print(f"合计 {n} 条把说明写在别的题号名下")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="全库检索待复核登记")
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("find", help="按关键词搜（多个词=且）")
    f.add_argument("keywords", nargs="*")
    f.add_argument("--type", choices=TYPES)
    f.add_argument("--book", action="append", help="限定序号，可重复")
    f.add_argument("--where", action="append", choices=list(FIELDS) + ["题号", "题型"])
    f.add_argument("--context", choices=("无", "整场"), default="无")
    f.set_defaults(func=cmd_find)
    s = sp.add_parser("stats")
    s.set_defaults(func=cmd_stats)
    r = sp.add_parser("refs", help="列出说明引用了别的题号的登记条")
    r.add_argument("book")
    r.set_defaults(func=cmd_refs)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
