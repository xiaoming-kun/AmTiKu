#!/usr/bin/env python3
r"""**批量换书**：把若干本来源书的题并进一个书名，key 跟着改、引用跟着迁。

界面那道「改出处」只能改**单题**，而且有一条守卫：**key 与出处同构
（`书/卷名#题号`）时才改名**。教辅书那几本的 key 是 `书/扫描页号#题号`（有的
甚至是 `书/卷名#题号` 里带着书名），与出处不同构 —— 走界面改只会换掉
`meta.book`、把带旧书名的 key 留下。整本书要挪，得走这里。

    命中判据是 **key 的书名段**，不是 `meta.book`——半改完的题也能一次扫进来。

## key 的两种给法（`--key-mode`）

| 模式 | 结果 | 用在哪 |
|---|---|---|
| `keep-tail` | 只换书名段，`页号#题号` 一个字不动 | 一本书单独挪，不会和别家撞号 |
| `pnum` | 中间段换成组级流水号 `P0001`，题号不动 | **多本并成一个书名**。同页同号会撞（实测 8 本并一本撞 173 组 / 354 道）；而且题号在书内本来就不唯一（千题册 556 道只有 111 个不同题号，因为一本里装了几十套原卷，每套都从 1 编号），所以中间段必须承担原来页号的区分作用 |

`pnum` 的组 = 不同的「旧书名 + 旧中间段」，按字典序编号，因此
`(组, 题号)` 与原 `(书, 中间段, 题号)` 一一对应，**不会撞、不会并错**。

## 一次改动的全部落点（少一处就是静默损坏）

| 落点 | 不迁的后果 |
|---|---|
| `题目/*.tex` 的 key 与 `meta`（book / source_label / year / paper_group） | 本体 |
| `数据/改出处.jsonl` 改名台账 | `store.diff()` 把「改名」报成「删一道＋加一道」，一红就是几千条 |
| 别的题 `meta` 里指向旧 key 的字段（`dup_of`／`also_in`／`merged_keys`…） | 查重提示、孪生题对账全部指空 |
| `数据/使用频次.json` 的键 | 这道题被组过几次归零 |
| `数据/订正台账.json` 的 `patches[].key` 与 `retired[]` | 逐题订正台账多出一批死账，而这张账**一条对不上整批不执行** |
| `试卷/存档.json`、`讲义/讲义存档.json` 里的 key 字符串 | 存档的卷子/讲义里这一题**静默消失**，打开只看出"少一道" |

## 用法

    python3 脚本/批量改出处.py --from "旧书A" --from "旧书B" --to "新书名" \
            --key-mode pnum --label-if-leaky --year-map 2027=2026      # 干跑，只报数
    … 同上加 --yes                                                     # 落盘

`--label-if-leaky`：出处标签里**含旧书名**的才换成 `--label`（默认＝新书名），
不含书名的原卷名（「第14套 武汉三调」「2021 南昌三模」）保留。
干跑会把「命中几道、分几组、撞不撞库、各类引用各几处」全数出来——**数不对就别加 --yes**。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from amti import store                                           # noqa: E402

#: 别的题 meta 里可能存着**题目 key** 的字段（值是字符串或字符串列表）
KEY_FIELDS = ("dup_of", "dup_of_dropped", "also_in", "merged_keys", "renamed_from")
#: 存 key 字符串的存档（与 `amti.web.server._KEY_REF_FILES` 同一批，别漏）
ARCHIVE_FILES = ("试卷/存档.json", "讲义/讲义存档.json")
USAGE = "数据/使用频次.json"
LEDGER = "数据/订正台账.json"


def parts(key: str) -> tuple[str, str, str]:
    """`书/中段#题号` → (书, 中段, 题号)。"""
    book, rest = key.split("/", 1) if "/" in key else ("", key)
    mid, _, no = rest.rpartition("#")
    return book, mid, (no or rest)


def build_plan(qs: list, a: argparse.Namespace) -> dict:
    r"""算出这次要动什么，**一个字节都不写**。"""
    hit = [q for q in qs if parts(q.key)[0] in a.froms]
    # 组号：按（旧书, 旧中段）字典序分配，保证 (组, 题号) 与原 key 一一对应
    groups: dict[tuple[str, str], str] = {}
    for i, g in enumerate(sorted({parts(q.key)[0:2] for q in hit}), 1):
        groups[g] = "P%04d" % i
    book_idx = {b: i for i, b in enumerate(sorted(a.froms), 1)}

    def new_key(q) -> str:
        _b, mid, no = parts(q.key)
        if a.key_mode == "pnum":
            return "%s/%s#%s" % (a.to, groups[(parts(q.key)[0], mid)], no)
        return "%s/%s#%s" % (a.to, mid, no)          # keep-tail：中段与题号都不动

    m = {q.key: new_key(q) for q in hit}
    keys_now = {q.key for q in qs}
    clash = sorted(k for k in m.values() if k in keys_now and k not in m)
    leaky = sorted({b.replace("_images", "").strip() for b in a.froms} | set(a.froms),
                   key=len, reverse=True)

    def label_needs_swap(q) -> bool:
        if not a.label_if_leaky:
            return True
        lab = str(q.meta.get("source_label") or "")
        return any(t and t in lab for t in leaky)

    refs = {f: 0 for f in KEY_FIELDS}
    for q in qs:
        for f in KEY_FIELDS:
            v = q.meta.get(f)
            if v is None:
                continue
            vals = v if isinstance(v, list) else [v]
            refs[f] += sum(1 for x in vals if isinstance(x, str) and x in m)
    return {"hit": hit, "map": m, "clash": clash, "meta_refs": refs,
            "groups": groups, "book_idx": book_idx,
            "swap_label": {q.key: label_needs_swap(q) for q in hit}}


def apply_bank(p: dict, a: argparse.Namespace, stat: dict) -> None:
    """在 `store.update` 的锁内改全库：key、meta、以及别的题指向旧 key 的字段。"""
    def _do(qs):
        m = p["map"]
        for q in qs:
            if q.key in m:
                before = q.content_hash()
                old_book, mid, _no = parts(q.key)
                q.meta["book"] = a.to
                if p["swap_label"][q.key]:
                    q.meta["source_label"] = a.label
                    stat["label_swapped"] += 1
                y = str(q.meta.get("year") or "")
                if y in a.year_map:
                    q.meta["year"] = a.year_map[y]
                    stat["year_swapped"] += 1
                pg = q.meta.get("paper_group")
                if isinstance(pg, str) and pg:
                    # 分组留着（组卷按组），但前缀换成不泄露书名的组码 G<书序>
                    tail = pg[len(old_book):].lstrip("/") if pg.startswith(old_book) else pg
                    q.meta["paper_group"] = "%s/G%d%s" % (
                        a.to, p["book_idx"][old_book], ("-" + tail) if tail else "")
                q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
                q.meta["renamed_from"] = q.key
                q.key = m[q.key]
                if q.content_hash() != before:
                    raise SystemExit("✗ 改名动到了正文（%s），整批拒绝" % q.key)
                stat["renamed"] += 1
            for f in KEY_FIELDS:            # 别的题里指向旧 key 的引用
                v = q.meta.get(f)
                if isinstance(v, str) and v in m:
                    q.meta[f] = m[v]
                    stat["meta_refs"] += 1
                elif isinstance(v, list):
                    q.meta[f] = [m.get(x, x) if isinstance(x, str) else x for x in v]
        return qs
    store.update(_do, dry_run=a.dry)


def count_and_migrate_files(p: dict, a: argparse.Namespace, write: bool) -> dict:
    """迁 `数据/使用频次.json`、`数据/订正台账.json` 与两份存档里的 key 字符串。"""
    m = p["map"]
    done: dict[str, int] = {}

    def _sub_text(t: str) -> tuple[str, int]:
        n = 0
        for old, new in m.items():
            a_, b_ = json.dumps(old, ensure_ascii=False), json.dumps(new, ensure_ascii=False)
            c = t.count(a_)
            if c:
                t = t.replace(a_, b_)
                n += c
        return t, n

    for rel in ARCHIVE_FILES:               # 存档里是 key 字符串，整串替换
        f = ROOT / rel
        if not f.is_file():
            continue
        t, n = _sub_text(f.read_text(encoding="utf-8"))
        if n:
            json.loads(t)                   # 先验能解析，坏就不写
            if write:
                f.write_text(t, encoding="utf-8")
            done[rel] = n

    def _usage(d):
        return ({m.get(k, k): v for k, v in d.items()},
                sum(1 for k in d if k in m))

    def _ledger(d):
        n = 0
        for x in d.get("patches") or []:
            if x.get("key") in m:
                x["key"] = m[x["key"]]
                n += 1
        r = d.get("retired") or []
        for i, k in enumerate(r):
            if k in m:
                r[i] = m[k]
                n += 1
        return d, n

    for rel, fn in ((USAGE, _usage), (LEDGER, _ledger)):
        f = ROOT / rel
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            print("  ⚠ %s 不是合法 JSON，跳过（引用会留在旧 key 上）" % rel)
            continue
        new, n = fn(data)
        if not n:
            continue
        if write:
            indent = 1 if rel == LEDGER else None
            out = json.dumps(new, ensure_ascii=False, indent=indent) if indent \
                else json.dumps(new, ensure_ascii=False)
            f.write_text(out, encoding="utf-8")
            json.loads(f.read_text(encoding="utf-8"))   # 写完读回来验一次
        done[rel] = n
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="批量换书（key 跟着改、引用跟着迁）")
    ap.add_argument("--from", dest="froms", action="append", required=True,
                    help="旧书名（=key 书名段），可重复给多本")
    ap.add_argument("--to", required=True, help="新书名")
    ap.add_argument("--label", default="", help="新的 source_label，默认等于 --to")
    ap.add_argument("--label-if-leaky", action="store_true",
                    help="只换**含旧书名**的出处标签，原卷名保留")
    ap.add_argument("--key-mode", choices=("keep-tail", "pnum"), default="keep-tail",
                    help="keep-tail=只换书名段；pnum=中间段换组级流水号")
    ap.add_argument("--year-map", action="append", default=[],
                    help="只改这些年份，形如 2027=2026（可重复）；不给=年份不动")
    ap.add_argument("--yes", action="store_true", help="真的落盘（默认干跑）")
    a = ap.parse_args()
    a.dry = not a.yes
    a.label = a.label or a.to
    want = a.year_map                       # 命令行给的是 ["2027=2026", …]，别就地覆盖
    a.year_map = {}
    for y in want:
        old, _, new = y.partition("=")
        a.year_map[old.strip()] = int(new or old)
    for bad in ("/", "#"):
        if bad in a.to or bad in a.label:
            print("✗ 新书名/出处标签里不能有 `%s`（key 的分隔符）" % bad)
            return 1

    qs = store.load_all()
    p = build_plan(qs, a)
    print("命中：key 书名段 ∈ %s 的题 %d 道" % (a.froms, len(p["hit"])))
    if not p["hit"]:
        print("✗ 一道都没命中，什么都不做")
        return 1
    print("key 模式：%s ｜ %s" % (a.key_mode,
          "中间段换组级流水号（题号不动）" if a.key_mode == "pnum" else "只换书名段"))
    print("分组：%d 个（旧书,旧中段）组合 → P0001..P%04d" % (len(p["groups"]), len(p["groups"])))
    sample = p["hit"][0]
    print("     例：%s → %s" % (sample.key, p["map"][sample.key]))
    if p["clash"]:
        print("✗ 新 key 与库里别的题撞 %d 个，先停下：%s" % (len(p["clash"]), p["clash"][:3]))
        return 1
    print("     撞库：0 ✓")
    n_leak = sum(1 for k, v in p["swap_label"].items() if v)
    print("出处标签：%s" % ("含旧书名的 %d 道换成「%s」，其余保留原卷名"
                            % (n_leak, a.label) if a.label_if_leaky
                            else "全部换成「%s」(%d 道)" % (a.label, len(p["hit"]))))
    print("年份：%s" % (", ".join("%s→%s" % (k, v) for k, v in a.year_map.items())
                        or "不动"))
    print("paper_group：前缀换成 %s/G<书序>，尾段（第N卷）保留" % a.to)
    refs = {k: v for k, v in p["meta_refs"].items() if v}
    print("别的题 meta 里指向旧 key：", refs or "无")
    print("文件侧引用：", count_and_migrate_files(p, a, write=False) or "无")
    print("改名台账将追加 %d 行 → %s" % (len(p["map"]), store.RENAME_LEDGER))
    if a.dry:
        print("\n[干跑] 什么都没写。数对了再加 --yes")
        return 0

    stat = {"renamed": 0, "label_swapped": 0, "year_swapped": 0, "meta_refs": 0}
    apply_bank(p, a, stat)
    done = count_and_migrate_files(p, a, write=True)
    led = ROOT / store.RENAME_LEDGER
    with led.open("a", encoding="utf-8") as f:
        for old, new in sorted(p["map"].items()):
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "from": old, "to": new}, ensure_ascii=False) + "\n")
    rep = ROOT / "变更记录" / ("%s_批量改出处.md" % time.strftime("%Y%m%d_%H%M%S"))
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(
        "# 批量改出处\n\n- 时间：%s\n- 旧书名：%s\n- 新书名：`%s`\n"
        "- key 模式 `%s`：分 %d 组给流水号，**题号一个字没动**\n"
        "- 出处标签%s；年份%s\n- paper_group 前缀换成 `%s/G<书序>`（尾段保留，分组不丢）\n"
        "- 改名 %d 道；内容指纹逐题比对：全部未变\n"
        "- 连带迁移：meta 引用 %d 处、文件 %s\n- 台账：`%s` 追加 %d 行\n"
        % (time.strftime("%Y-%m-%d %H:%M:%S"), "、".join(a.froms), a.to, a.key_mode,
           len(p["groups"]),
           "只换含旧书名的 %d 道" % stat["label_swapped"] if a.label_if_leaky
           else "全部换成「%s」" % a.label,
           "、".join("%s→%s" % (k, v) for k, v in a.year_map.items()) + "（%d 道）"
           % stat["year_swapped"] if a.year_map else "未动",
           a.to, stat["renamed"], stat["meta_refs"],
           "、".join("%s %d 处" % (k, v) for k, v in done.items()) or "无",
           store.RENAME_LEDGER, len(p["map"])), encoding="utf-8")
    print("\n落盘完成：%s" % stat)
    print("引用迁移：%s ｜ 报告：%s" % (done or "无", rep.relative_to(ROOT)))
    print("下一步：python3 amti.py diff（内容变化必须是 0，删除不该出现这批）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
