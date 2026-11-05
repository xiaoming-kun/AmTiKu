r"""合并重复题：**同一道题**只留一份，其余进回收站（可恢复）。

## 判定（宁缺勿错）

同时满足才合并：

1. 题干按去重归一化（空白/LaTeX 排版差异）后**完全相同**；
2. 题型相同；
3. 选项**集合**相同（顺序无关；`$`、括号、`\left/\right`、`\,` 等排版差异不算不同）；
4. 答案**指向的选项内容**相同（不是只看字母——题号顺序变了，字母就不可比）；
5. 配图集合相同（图不同 = 可能不是同一道题，留给人工）。

任何一条不满足 → **不动**，写进冲突清单。

## 保留哪一份（依次比较）

高考 > 有真解析 > 无结构问题 > 解析更长 > 被试卷存档引用 >
被订正台账引用 > 使用过 > 考点更多 > 录入更早。

## 合并后

- 保留题的 `meta` 增加 `also_in`（其它出处）、`merged_keys`（并掉的题号）；
- 考点取并集；保留题缺解析时，采用并掉题里**最长的那份真解析**；
- `试卷/存档.json`、`数据/使用频次.json`、`数据/订正台账.json` 里的旧题号改指保留题；
- 其余题走 `trash.delete`（原因「与库内已有题重复」，可恢复）。

## 用法

    python3 脚本/合并重复题.py            # 干跑：只打印会并掉多少、样例
    python3 脚本/合并重复题.py --yes      # 落盘，并写 变更记录/ 报告
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import dedup, papers, store, trash          # noqa: E402
from amti.paths import ROOT as PROJECT                 # noqa: E402

REASON = "与库内已有题重复"
REPORT_DIR = PROJECT / "变更记录"
CONFLICT_DIR = PROJECT / "数据" / "题库审阅"
USAGE = PROJECT / "数据" / "使用频次.json"
LEDGER = PROJECT / "数据" / "订正台账.json"
HANDOUT = PROJECT / "讲义" / "讲义存档.json"
PASSWORD_FILE = PROJECT / "数据" / "删题口令.txt"


def _write_json(path: Path, data) -> None:
    """原子写：中途失败不会留半个 JSON。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _raw(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _norm(s: str) -> str:
    """选项/答案的比对形态：只抹掉排版差异，不抹掉内容。"""
    t = dedup.norm_stem(s or "")
    # 先归一**定界符**：`\\lvert`/`\\vert` 和裸 `|` 是同一个东西，
    # 但**不能把 `|` 删掉**——`|x|` 和 `x` 是不同选项。
    for a, b in (("\\lvert", "|"), ("\\rvert", "|"), ("\\vert", "|"),
                 ("\\Vert", "‖"), ("\\|", "‖"),
                 # 同一符号的不同写法：不归一的话，"同一道题"会被判成两道。
                 ("\\overline", "bar"), ("\\bar", "bar"),
                 ("\\mid", "|"),
                 ("\\leqslant", "leq"), ("\\geqslant", "geq"),
                 ("\\le", "leq"), ("\\ge", "geq"),
                 ("\\overrightarrow", ""), ("\\overleftarrow", ""),
                 ("\\vec", ""), ("\\mathbf", ""), ("\\boldsymbol", ""),
                 ("\\symbfit", ""), ("\\symbf", ""),
                 ("\\mathbb", ""), ("\\mathcal", "")):
        t = t.replace(a, b)
    for c in ("\\left", "\\right",
              "\\dfrac", "\\tfrac", "\\big", "\\Big", "\\bigg", "\\Bigg",
              "\\displaystyle", "\\limits", "\\nolimits",
              "\\,", "\\;", "\\!", "\\ ", "\\quad", "\\qquad"):
        t = t.replace(c, "")
    return (t.replace("\\frac", "frac").replace("\\sqrt", "sqrt")
             .replace("\\mathrm", "").replace("\\text", ""))


def _sig(q) -> tuple:
    """同一道题的判据。选项顺序无关；答案比的是**选中的内容**。"""
    labels = [o.label for o in q.options]
    ans = re.sub(r"[^A-H]", "", q.answer or "")
    if q.options and ans and all(c in labels for c in ans):
        picked = tuple(sorted(_norm(q.options[labels.index(c)].text) for c in ans))
    else:
        picked = (_norm(q.answer),)
    return (q.type,
            tuple(sorted(Counter(_norm(o.text) for o in q.options).items())),
            picked,
            tuple(sorted(f.id for f in q.figures)))


JUNK_LABEL = re.compile(r"^(?:\d{1,4}|满分.*|.*考试时间.*|.*答题卡.*)$")


def _key_label(key: str) -> str:
    """题号 → 人能读的出处前缀。书册的 `_images/045` 写成 `·045`。"""
    prefix = key.rsplit("#", 1)[0] if "#" in key else key
    return prefix.replace("_images/", "·")


def _label(q) -> str:
    """人能读的出处。`source_label` 是「045」这种页码噪声时，退回题号前缀。"""
    lab = str((q.meta or {}).get("source_label") or "").strip()
    if lab and not JUNK_LABEL.fullmatch(lab):
        return lab
    return _key_label(q.key)


def _groups(rows):
    h: dict[str, list] = {}
    for q in rows:
        # 用 `dedup.norm_stem` 而不是 `_raw`：`_raw` 只抹空白，同一道题
        # 只要一边有 `\left`/`\,`/`$` 就会漏掉。归一化只抹排版，不抹数字/关系。
        h.setdefault(dedup.norm_stem(q.stem), []).append(q)
    return [g for g in h.values() if len(g) > 1]


def _plan(rows, *, paper_keys, ledger_keys, usage_keys, adopt_sources):
    groups = _groups(rows)
    index = {q.key: i for i, q in enumerate(rows)}
    plan, conflicts = [], []
    for g in groups:
        if len({_sig(q) for q in g}) != 1:
            conflicts.append(g)
            continue

        def score(q):
            return (
                1 if q.kind == "高考" else 0,
                1 if q.has_solution else 0,
                0 if q.problems() else 1,
                len(q.solution or ""),
                1 if q.key in paper_keys else 0,
                1 if q.key in ledger_keys else 0,
                1 if q.key in usage_keys else 0,
                1 if q.key in adopt_sources else 0,
                len(q.points or []),
                -index.get(q.key, 10 ** 9),
            )

        keep = max(g, key=score)
        others = [q for q in g if q.key != keep.key]
        plan.append((keep, others))
    return plan, conflicts


def _merge_into(keep, others, *, stamp):
    """把出处/考点/解析并进保留题。返回是否改到正文（需要 migrated_at）。"""
    labels = [_label(q) for q in others]
    old_labels = keep.meta.get("also_in") or []
    keep.meta["also_in"] = sorted({*old_labels, *labels} - {_label(keep)})
    keep.meta["merged_keys"] = sorted({*(keep.meta.get("merged_keys") or []),
                                       *(q.key for q in others)})
    keep.meta["merged_at"] = stamp
    keep.meta["merged_by"] = "合并重复题"

    merged_points = list(dict.fromkeys(
        list(keep.points or []) + [p for q in others for p in (q.points or [])]))
    if merged_points != list(keep.points or []):
        keep.points = merged_points

    changed = False
    if not keep.has_solution:
        cand = [q for q in others if q.has_solution]
        if cand:
            best = max(cand, key=lambda q: len(q.solution or ""))
            keep.solution = best.solution
            changed = True
    if changed:
        keep.meta["migrated_at"] = stamp
        keep.meta["migrated_by"] = "合并重复题（补解析）"
    return changed


def _write_conflicts(conflicts, stamp):
    if not conflicts:
        return None
    CONFLICT_DIR.mkdir(parents=True, exist_ok=True)
    p = CONFLICT_DIR / ("重复题冲突_%s.md" % stamp[:10].replace("-", ""))
    lines = ["# 题干相同、但内容不一致的题（**没有合并**）", "",
             "判定口径见 `脚本/合并重复题.py`：题干相同但选项/答案/配图对不上，",
             "可能是文理不同题、也可能是 OCR 串行——**必须回原卷核对**。", ""]
    for g in sorted(conflicts, key=lambda g: g[0].key):
        lines.append("## `%s`" % g[0].key)
        lines.append("")
        for q in g:
            lines.append("- `%s`｜题型 %s｜答案 `%s`｜选项 %s"
                         % (q.key, q.type, (q.answer or "")[:20],
                            " / ".join((o.text or "")[:24] for o in q.options)))
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _remap_handout(obj, mapping):
    """递归改讲义存档里的题号。画布块和普通块都用 `key`。"""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "key" and isinstance(v, str) and v in mapping:
                obj[k] = mapping[v]
            else:
                _remap_handout(v, mapping)
    elif isinstance(obj, list):
        for v in obj:
            _remap_handout(v, mapping)


def main() -> int:
    ap = argparse.ArgumentParser(description="合并重复题（默认干跑）")
    ap.add_argument("--yes", action="store_true", help="真的落盘")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 组（调试用）")
    a = ap.parse_args()

    rows = store.load_all()
    paper_keys = {k for it in papers._load() for k in (it.get("keys") or [])}
    usage = json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    ledger_keys = {x["key"] for x in ledger.get("patches", [])}
    adopt_sources = {x["set"].get("_adopt") for x in ledger.get("patches", [])
                     if x.get("set", {}).get("_adopt")}

    plan, conflicts = _plan(rows, paper_keys=paper_keys, ledger_keys=ledger_keys,
                            usage_keys=set(usage), adopt_sources=adopt_sources)
    if a.limit:
        plan = plan[:a.limit]
    removed = [q.key for _keep, others in plan for q in others]
    print("全库 %d 道；题干相同的组 %d 组；可合并 %d 组（并掉 %d 道）；冲突 %d 组"
          % (len(rows), len(plan) + len(conflicts), len(plan), len(removed), len(conflicts)))
    for keep, others in plan[:8]:
        print("  ✓ 保留 %s" % keep.key)
        for q in others:
            print("      并入 %s" % q.key)
    if conflicts:
        print("  ⚠ 冲突样例（不合并）：")
        for g in conflicts[:5]:
            print("      %s" % " / ".join(q.key for q in g))
    if not a.yes:
        print("\n[干跑] 什么都没写。确认后加 --yes")
        return 0

    if not removed:
        print("没有需要合并的题")
        return 0

    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    mapping = {q.key: keep.key for keep, others in plan for q in others}
    merged_meta = {keep.key: (keep, others) for keep, others in plan}
    changed: list[str] = []

    def _do(qs):
        by = {q.key: q for q in qs}
        for key, (keep, others) in merged_meta.items():
            q = by.get(key)
            if q is None:
                continue
            if _merge_into(q, others, stamp=stamp):
                changed.append(key)
        return qs

    store.update(_do)

    # 先改引用，再删题：删到一半失败也不会留下悬空题号。
    items = papers._load()
    n_paper = 0
    for it in items:
        old = it.get("keys") or []
        new = list(dict.fromkeys(mapping.get(k, k) for k in old))
        if new != old:
            it["keys"] = new
            it["n"] = len(new)
            n_paper += 1
    if n_paper:
        papers._save(items)

    n_usage = 0
    for old, new in mapping.items():
        if old in usage:
            usage[new] = int(usage.get(new, 0)) + int(usage.pop(old))
            n_usage += 1
    if n_usage:
        _write_json(USAGE, usage)

    n_handout = 0
    if HANDOUT.exists():
        try:
            hd = json.loads(HANDOUT.read_text(encoding="utf-8"))
            before = json.dumps(hd, ensure_ascii=False, sort_keys=True)
            _remap_handout(hd, mapping)
            if json.dumps(hd, ensure_ascii=False, sort_keys=True) != before:
                _write_json(HANDOUT, hd)
                n_handout = 1
        except Exception as e:
            print("✗ 改讲义存档失败：%s" % e)
            return 1

    n_retired = 0
    if ledger:
        retired = set(ledger.get("retired") or [])
        for old in removed:
            if old in ledger_keys and old not in retired:
                retired.add(old)
                n_retired += 1
        if n_retired:
            ledger["retired"] = sorted(retired)
            _write_json(LEDGER, ledger)

    password = (PASSWORD_FILE.read_text(encoding="utf-8").strip()
                if PASSWORD_FILE.exists() else "")
    res = trash.delete(removed, reason=REASON, password=password)
    if not res.get("ok"):
        print("✗ 进回收站失败：%s" % res.get("error"))
        return 1

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    p = REPORT_DIR / ("%s_合并重复题.md" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    lines = ["# 合并重复题", "",
             "- 时间：%s" % stamp,
             "- 合并：%d 组，进回收站 %d 道" % (len(plan), len(removed)),
             "- 补解析：%d 道；改试卷存档 %d 份；改使用频次 %d 条；注销订正账目 %d 条；改讲义存档 %d 份"
             % (len(changed), n_paper, n_usage, n_retired, n_handout), "",
             "## 逐组", ""]
    for keep, others in plan:
        lines.append("### 保留 `%s`" % keep.key)
        lines.append("")
        lines.append("- 并入：%s" % "、".join("`%s`" % q.key for q in others))
        lines.append("- 出处：%s" % "、".join(_label(q) for q in others))
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    cp = _write_conflicts(conflicts, stamp)
    print("✓ 合并 %d 组，进回收站 %d 道；报告：%s"
          % (len(plan), len(removed), p))
    if cp:
        print("  冲突清单（未合并）：%s" % cp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
