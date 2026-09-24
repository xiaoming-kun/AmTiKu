#!/usr/bin/env python3
r"""给**还没入库的成品**补考点标签（难度随之派生，不用单独做）。

## 为什么不能直接用 脚本/补考点入库.py

`补考点入库.py` 是给**库里已有的题**补标签的：它的输入 key 是库内 key，
写库走 `store.rewrite_all()`。而这 571 份成品还没入库，两件事都对不上：
key 还不存在，而且入库后再补要触发全库重写，风险高得多。

所以这里的做法是：**入库前就把考点算好，入库时随 `ingest` 一起带进去**，
一次落定、不需要 rewrite_all。

## 难度不用单独做

`schema.Question.difficulty` 是派生的：`meta["difficulty"]` 有值就用，
否则取 `knowledge.difficulty_of(points[0])`（`amti/knowledge.py`）。
考点库 152 个考点的难度是齐的 ⇒ **补了 points，难度自动来**。

## 三个子命令

    python3 脚本/补考点成品.py split      # 出题：成品 → batches/bNNN.json（每批 40 题）
    python3 脚本/补考点成品.py merge      # 收结果：r*.json → 成品标签.json（带校验）
    python3 脚本/补考点成品.py stat       # 覆盖率与缺口

分类由模型会话做：读 `batches/bNNN.json` + `考点表.txt`，
把结果写 `batches/rNNN.json`，格式 `[{"key":"…","points":["1.1.3"]}, …]`。

## 校验（merge 时硬拦，不合格的一律不进标签文件）

- 考点 id 必须在 `知识点.json` 里存在
- 每题 1–3 个，去重
- **一题多考点时，第一个必须是主考点**（难度按它派生）
- key 撞车要报出来：`label` 取自文件名，历史上 #32×#53、#219×#223 跨场撞过 37 个 key，
  静默覆盖会让两道不同的题共用一套标签
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from amti import knowledge, record2  # noqa: E402

V2 = ROOT / "数据/录题/输出_v2"
WORK = ROOT / ".tobias/分类/成品"
BATCH = WORK / "batches"
CATALOG = WORK / "考点表.txt"
LABELS = ROOT / ".tobias/分类/成品标签.json"
SIZE = 40


def _label_of(path: Path) -> str:
    """成品文件名 → 将来的库 source_label（与 录题入库.py 的 re_label 同一条规则）。"""
    n = path.name
    for suf in (".成品.json", ".解答.json", ".待复核.json"):
        if n.endswith(suf):
            return n[:-len(suf)]
    return n


def _key_of(label: str, no) -> str:
    return "%s#%s" % (label, no)


def _valid_ids() -> set:
    return {p["id"] for p in knowledge.all_points()}


def _empty_sol(s: str) -> bool:
    s = (s or "").strip()
    return (not s) or s == "解析无"


def split() -> None:
    """出分类输入。带选项和解析摘要——只看题干常常定不准考点。"""
    BATCH.mkdir(parents=True, exist_ok=True)
    if not CATALOG.exists():
        lines = []
        for p in sorted(knowledge.all_points(), key=lambda x: x["id"]):
            lines.append("%s\t%s\t%s" % (p["id"], knowledge.difficulty_of(p["id"]),
                                         knowledge.title_of(p["id"])))
        CATALOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("写了考点表 %s（%d 个考点）" % (CATALOG.relative_to(ROOT), len(lines)))

    items, seen = [], defaultdict(list)
    for p in sorted(V2.glob("*.成品.json")):
        label = _label_of(p)
        for r in json.loads(p.read_text(encoding="utf-8")):
            k = _key_of(label, r["题号"])
            seen[k].append(p.name)
            opts = "；".join((o.get("text") if isinstance(o, dict) else str(o)) or ""
                             for o in (r.get("选项") or {}).values())
            items.append({"i": len(items), "key": k, "type": r["题型"],
                          "stem": (r.get("题干") or "")[:600],
                          "opts": opts[:400],
                          # 解析能显著提高考点判定准确率，但只给摘要，省 token
                          "sol_hint": (r.get("解析") or "")[:200]})
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    n = 0
    for i in range(0, len(items), SIZE):
        n += 1
        (BATCH / ("b%03d.json" % n)).write_text(
            json.dumps(items[i:i + SIZE], ensure_ascii=False, indent=1), encoding="utf-8")
    print("成品 %d 题 → %d 批（每批 ≤%d）" % (len(items), n, SIZE))
    if dup:
        print("⚠️ 有 %d 个 key 被多份成品共用（label 取自文件名导致的跨场撞车），"
              "merge 时不能静默覆盖：%s" % (len(dup), list(dup)[:5]))
        (WORK / "撞车key.json").write_text(json.dumps(dup, ensure_ascii=False, indent=1),
                                           encoding="utf-8")


def _index_map() -> dict:
    r"""`i` → key。让 worker 只回填序号，卷名由这里对上——
    实测有 worker 手打卷名把 `213_2026年2月上虞区高三期末` 写成
    「213_2026届四川省内江市…」，35 条挂到成品里不存在的 key 上。
    """
    m = {}
    for f in sorted(BATCH.glob("b[0-9][0-9][0-9].json")):
        for it in json.loads(f.read_text(encoding="utf-8")):
            m[it["i"]] = it["key"]
    return m


def merge() -> None:
    ids = _valid_ids()
    idx = _index_map()
    by_key = {}
    bad = []
    by_i = 0
    fixed_pos = []
    files = (sorted(BATCH.glob("r*.json")) + sorted(WORK.glob("r*.json"))
             + sorted((BATCH / "27b").glob("r*.json")))
    if not files:
        sys.exit("还没有 r*.json 结果文件（先让模型跑 batches/）")
    for f in files:
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            bad.append((f.name, "读不了：%s" % e))
            continue
        # **只报不改**：结果里的 key 与批次文件对不上就记一笔，**不按位置覆盖回去**——
        # 万一某个 worker 把顺序打乱，按位置覆盖会把 A 题的标签静默挂到 B 题上，
        # 那比丢标签严重得多。丢了是响的：`未覆盖.json` 会列出来，重跑那一批就行。
        twin = (BATCH / ("b%s.json" % f.stem[1:]))
        if twin.exists() and rows:
            want = {it["key"] for it in json.loads(twin.read_text(encoding="utf-8"))}
            typed = sum(1 for r in rows if r.get("key") and r["key"] not in want)
            if typed:
                fixed_pos.append((f.name, typed))
        for r in rows:
            pts = list(dict.fromkeys(str(x) for x in (r.get("points") or [])))
            # key 一律以 `i` 为准；没有 `i` 才信它自己写的 key（旧格式）
            if r.get("i") is not None and r["i"] in idx:
                k = idx[r["i"]]
                by_i += 1
            else:
                k = r.get("key")
                if r.get("i") is not None:
                    bad.append((str(r.get("i")), "序号在批次里不存在，key 又不认：%s" % k))
                    continue
            if not k:
                bad.append((f.name, "既没 key 也没序号"))
                continue
            if not pts:
                bad.append((k, "没给考点"))
                continue
            if len(pts) > 3:
                bad.append((k, "考点多于 3 个：%s" % pts)); continue
            unk = [x for x in pts if x not in ids]
            if unk:
                bad.append((k, "考点 id 不存在：%s" % unk)); continue
            new = {"key": k, "points": pts, "source": r.get("source") or "llm"}
            old = by_key.get(k)
            if old and old["points"] != pts:
                # 两条来源给得不一样。**不许两边都丢**（原来这里是 continue，
                # 等于 agent 和 27B 撞车时两道题的标签一起蒸发）。
                # 谁给得多留谁（agent 给 1—3 个、27B 只给 1 个，不是同一件事的两种答案），
                # 数量相同且主考点也不同才算真分歧，留着报出来给人裁。
                if len(pts) > len(old["points"]):
                    by_key[k] = new
                elif len(pts) == len(old["points"]) and pts[0] != old["points"][0]:
                    bad.append((k, "同一 key 两份标签主考点不同，已留先到的：%s ≠ %s"
                                % (old["points"], pts)))
                continue
            by_key[k] = by_key.get(k) or new

    need = set()
    for p in sorted(V2.glob("*.成品.json")):
        label = _label_of(p)
        for r in json.loads(p.read_text(encoding="utf-8")):
            need.add(_key_of(label, r["题号"]))
    got = set(by_key)
    out = [{"key": k, "points": v["points"], "source": v["source"]} for k, v in sorted(by_key.items())]
    LABELS.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("结果文件 %d 份 → 合格标签 %d 条，写入 %s" % (len(files), len(out), LABELS.relative_to(ROOT)))
    if by_i:
        print("   其中 %d 条是按序号 `i` 对上的" % by_i)
    if fixed_pos:
        print("   ⚠️ %d 个结果文件写了批次里没有的 key，共 %d 条（没按位置硬覆盖，重跑那批）：%s"
              % (len(fixed_pos), sum(n for _, n in fixed_pos),
                 ", ".join("%s×%d" % (a, b) for a, b in fixed_pos[:6])))
    print("覆盖成品 %d / %d 题（%.1f%%）" % (len(got & need), len(need), 100 * len(got & need) / max(1, len(need))))
    miss = sorted(need - got)
    if miss:
        (WORK / "未覆盖.json").write_text(json.dumps(miss, ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8")
        print("未覆盖 %d 题 → %s" % (len(miss), (WORK / "未覆盖.json").relative_to(ROOT)))
    extra = sorted(got - need)
    if extra:
        print("⚠️ 标签里有 %d 个 key 在成品中找不到（多半是场名变了）：%s" % (len(extra), extra[:5]))
    if bad:
        (WORK / "不合格.json").write_text(json.dumps([{"key": a, "原因": b} for a, b in bad],
                                                     ensure_ascii=False, indent=1) + "\n",
                                          encoding="utf-8")
        print("⛔ 不合格 %d 条 → %s" % (len(bad), (WORK / "不合格.json").relative_to(ROOT)))
        for k, why in bad[:5]:
            print("   %s：%s" % (k, why))


def stat() -> None:
    need = set()
    for p in sorted(V2.glob("*.成品.json")):
        label = _label_of(p)
        for r in json.loads(p.read_text(encoding="utf-8")):
            need.add(_key_of(label, r["题号"]))
    got = {}
    if LABELS.exists():
        got = {x["key"]: x for x in json.loads(LABELS.read_text(encoding="utf-8"))}
    done = len(set(got) & need)
    print("成品题数 %d | 已有考点标签 %d | 缺 %d" % (len(need), done, len(need) - done))
    b = BATCH / "b001.json"
    if b.exists():
        n = len(list(BATCH.glob("b*.json")))
        r = len(list(BATCH.glob("r*.json"))) + len(list((BATCH / "27b").glob("r*.json")))
        print("批次：出 %d 批，回收 %d 批" % (n, r))
    if got:
        c = Counter(x["points"][0] for x in got.values())
        print("主考点分布 top8：", ", ".join("%s×%d" % (k, v) for k, v in c.most_common(8)))
        noq = [k for k, v in got.items() if not knowledge.difficulty_of(v["points"][0])]
        print("派生不出难度的：%d" % len(noq))


def todo() -> None:
    r"""还缺哪几批 —— 派活时按这个切区间，别靠记忆。"""
    missing = [int(f.stem[1:]) for f in BATCH.glob("b*.json")
               if not (BATCH / ("r%s.json" % f.stem[1:])).exists()
               and not (WORK / ("r%s.json" % f.stem[1:])).exists()
               and not (BATCH / "27b" / ("r%s.json" % f.stem[1:])).exists()]
    missing.sort()
    spans = []
    for n in missing:
        if spans and n == spans[-1][1] + 1:
            spans[-1][1] = n
        else:
            spans.append([n, n])
    print("缺 %d/%d 批（%d 题）" % (len(missing), len(list(BATCH.glob("b*.json"))),
                                    len(missing) * SIZE))
    print("连续区间：" + " ".join("%d" % a if a == b else "%d-%d" % (a, b) for a, b in spans))


def check() -> None:
    r"""标签账本本身的体检——**别拿「某个 r 文件第 N 行」当「第 N 题」**。

    起因：有复核用「i=4161 落在第 105 批 ⇒ 应该去看 r042 的第 N 行」这种位置算法
    去对账，得出「b001—b072 整段串题、要重跑 2880 题」。实测 i=4161 属于 `b105`
    （`336_…皖北协作区#16`，一道椭圆题），标签 `5.3.3/5.2.1/5.3.1` 对得上题干。
    批次的 `i` **不是连续的 40 个一组对齐文件号的**，跨场切分时一场会占两批、
    一批会含多场，所以只能按 `i` 的取值范围查，不能按行号推算。
    """
    idx = _index_map()
    in_batch = set(idx.values())
    if not LABELS.exists():
        sys.exit("还没有 %s" % LABELS.relative_to(ROOT))
    lab = json.loads(LABELS.read_text(encoding="utf-8"))
    ks = [x["key"] for x in lab]
    over = [x for x in lab if len(x["points"]) > 3]
    ghost = sorted(set(ks) - in_batch)
    dup = len(ks) - len(set(ks))
    print("标签 %d 条 | 考点多于 3 个 %d | 不属于任何批次的 key %d | 重复 key %d"
          % (len(ks), len(over), len(ghost), dup))
    for x in over[:3]:
        print("   超量：", x["key"], x["points"])
    for g in ghost[:3]:
        print("   幽灵：", g)
    print("结论：%s" % ("✅ 账本自洽" if not (over or ghost or dup) else "⛔ 账本有问题，先修再入库"))

    # **两种回填格式各自与批次对账**：早期 worker 只写 `key`（没有 `i`），
    # 后期只写 `i`（没有 `key`）。有复核拿「`i` 是批次内局部号」去推 b001—b072 串题，
    # 其实那 71 个文件**根本没有 `i` 字段**，无从错位。这里把两类的对账都固化下来：
    # 纯 key 的比 key 集合，纯 i 的逐位比 i 序列，混排的单独报出来。
    only_key = only_i = mixed = 0
    mismatch = []
    for f in sorted(BATCH.glob("r[0-9][0-9][0-9].json")):
        bf = BATCH / ("b%s.json" % f.stem[1:])
        if not bf.exists():
            mismatch.append((f.name, "没有对应的批次文件"))
            continue
        rows = json.loads(f.read_text(encoding="utf-8"))
        b = json.loads(bf.read_text(encoding="utf-8"))
        hk = sum(1 for r in rows if r.get("key"))
        hi = sum(1 for r in rows if r.get("i") is not None)
        if hk == len(rows) and not hi:
            only_key += 1
            if {r["key"] for r in rows} != {x["key"] for x in b}:
                mismatch.append((f.name, "key 集合与批次不符"))
        elif hi == len(rows) and not hk:
            only_i += 1
            if [r["i"] for r in rows] != [x["i"] for x in b]:
                mismatch.append((f.name, "i 序列与批次不符"))
        else:
            mixed += 1
            mismatch.append((f.name, "i/key 混排：有 i %d 行、有 key %d 行" % (hi, hk)))
    print("结果文件：纯 key %d 个・纯 i %d 个・混排 %d 个；与批次对不上 %d 个%s"
          % (only_key, only_i, mixed, len(mismatch),
             "" if not mismatch else " → " + "; ".join("%s %s" % m for m in mismatch[:4])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("act", choices=["split", "merge", "stat", "todo", "check"])
    a = ap.parse_args()
    {"split": split, "merge": merge, "stat": stat, "todo": todo, "check": check}[a.act]()
