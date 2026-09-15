r"""AmTiKu · 影响面审计

顶层设计 §4.3 定的 **MIGRATE 强制流程**，这个模块只做这一件事：

    1. dry-run  → 输出「将影响 N 道，其中 M 道是存量题」，并列出前 20 道
    2. 需要 --yes 才真正执行
    3. 执行后自动写一份 diff 报告到 变更记录/

§八 又补了一条：「不做**悄悄生效**的迁移」。所以这里没有"顺手就改了"的入口——
要么 `preview()` 只看不动，要么 `apply()` 带 `yes=True`。

`audit` 与 `conform` 的分工：
    conform  只**校验**（写法规不规范），从不修改
    audit    只**执行迁移**（规则要改哪些题），改完留报告
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from . import normalize as R
from . import store

PKG = Path(__file__).resolve().parent.parent
CHANGE_DIR = PKG / "变更记录"


def preview(rule_name: str | None = None, *, scope: str = R.MIGRATE) -> dict:
    r"""**只看不动**：这一级（或这一条）规则会改动哪些题。

    顶层设计要的就是这句话：「将影响 N 道，其中 M 道是存量题」。
    这里所有题都是存量题，所以两个数相等。
    """
    qs = store.load_all()
    if rule_name:
        r = R.get(rule_name)
        if r is None:
            return {"ok": False, "error": "没有这条规则：%s" % rule_name}
        targets = [(q, [r.name]) if r.fn(_copy(q)) else (q, []) for q in qs]
        hits = [(q.key, fired) for q, fired in targets if fired]
    else:
        hits = []
        for q in qs:
            fired = R.normalize(_copy(q), scope)
            if fired:
                hits.append((q.key, fired))
    return {
        "ok": True,
        "rule": rule_name or scope,
        "affected": len(hits),
        "existing": len(hits),          # 全库都是存量题
        "total": len(qs),
        "sample": hits[:20],
        "hits": hits,
    }


def _copy(q):
    from copy import deepcopy
    return deepcopy(q)


def apply(rule_name: str | None = None, *, scope: str = R.MIGRATE,
          yes: bool = False) -> dict:
    r"""执行迁移。**没有 `yes=True` 一律不动。**

    改完把 diff 报告写到 `变更记录/`，文件名带时间戳——顶层设计要求
    「执行后自动写一份 diff 报告」，目的就是事后能回答"这条规则什么时候
    改过哪些题"。
    """
    pv = preview(rule_name, scope=scope)
    if not pv.get("ok", True) is True:
        return pv
    if not yes:
        return {"ok": False, "error": "没有 --yes，什么都不写", "preview": pv}
    if not pv["affected"]:
        return {"ok": True, "affected": 0, "note": "没有题需要改", "report": None}

    qs = store.load_all()
    changed: list[dict] = []
    for q in qs:
        before = q.content_hash()
        fired = ([rule_name] if rule_name else []) or None
        if rule_name:
            r = R.get(rule_name)
            fired = [r.name] if r.fn(q) else []
        else:
            fired = R.normalize(q, scope)
        if not fired:
            continue
        after = q.content_hash()
        # **盖时间戳**：批量迁移是**有意改数据**，`store.diff()` 靠它把
        # "规则迁移"和"没登记过的改动"分开。不盖的话，每跑一次迁移
        # 验收的快照层就红一次——那样的红灯很快就没人看了。
        import time as _t
        q.meta["migrated_at"] = _t.strftime("%Y-%m-%d %H:%M")
        q.meta["migrated_by"] = (rule_name or scope)
        changed.append({"key": q.key, "rules": fired,
                        "hash": "%s → %s" % (before, after)})

    if not changed:
        return {"ok": True, "affected": 0, "note": "规则跑完没有实际改动"}

    # 落盘：整卷重写（这是 MIGRATE，本来就是一次性整体处理）
    # ⚠️ 用 rewrite_all（**按 PER_VOLUME 重新分卷**），不要用 rewrite_volume(1,…)：
    # 后者会把所有卷的题都写进第 1 卷，而其它卷还在 → 整库重复。
    r = store.rewrite_all(qs)

    CHANGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report = CHANGE_DIR / ("%s_%s.md" % (stamp, (rule_name or scope).replace("/", "_")))
    lines = [
        "# 迁移报告",
        "",
        "- 时间：%s" % _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "- 规则：%s（scope=%s）" % (rule_name or "全部", scope),
        "- 影响：%d 道（全库 %d 道）" % (len(changed), len(qs)),
        "- 内容指纹变化：%d 道" % len(r["changed"]),
        "",
        "## 逐条",
        "",
    ]
    for c in changed:
        lines.append("- `%s` ← %s" % (c["key"], "、".join(c["rules"])))
    lines += ["", "## 依据", ""]
    for name in sorted({n for c in changed for n in c["rules"]}):
        rr = R.get(name)
        lines.append("- **%s**：%s" % (name, (rr.why if rr else "（规则已不存在）")))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"ok": True, "affected": len(changed),
            "fingerprints_changed": len(r["changed"]),
            "report": str(report), "changed": changed}


def list_rules() -> list[dict]:
    """列出全部规则（`audit --rules`）。"""
    from . import normalize as R2
    return [{"name": r.name, "scope": r.scope, "why": r.why} for r in R2.RULES]


if __name__ == "__main__":
    print("规则清单：")
    for r in list_rules():
        print("  [%-7s] %-22s %s" % (r["scope"], r["name"], r["why"][:52]))
    print()
    pv = preview()
    print("MIGRATE 级影响面：%d 道 / 全库 %d 道" % (pv["affected"], pv["total"]))
    for k, fired in pv["sample"][:10]:
        print("  %-38s ← %s" % (k, "、".join(fired)))
