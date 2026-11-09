"""AmTiKu · 审阅工作台（P0）

## 为什么单独一层

「改过」不等于「审过」。旧实现把 `reviewed_at` 同时当两种信号用：
人工点「标记复核」会写它，**改答案/解析也会写它**。于是体检页的
「已复核 212」里 210 道只是改过一个错字，真正的复核率接近 0。

这里把语义拆开：

    review_status  pending / approved / needs_fix / flagged
    reviewed_hash  复核时的 content_hash
    reviewed_at    复核时间
    reviewed_by    复核人（本机名字，可空）
    review_note    复核备注
    review_batch   抽样批次号（手动审阅为空）

`stale` **不落盘**：正文一变，`content_hash` 与 `reviewed_hash` 对不上，
就现算成 stale。这样任何写正文的路径（改答案、改解析、改源码）都不需要
记得清复核标记——状态自己会失效。

旧数据没有 `review_status`：有 `reviewed_at` 时按历史复核看待；
若 `reviewed_at == edited_at`（旧代码改答案时同时写两个字段），视为
**编辑自动标记**，算 stale，不再冒充人工复核。

## 风险队列

风险分不是「题目对不对」的判据，只是**排序线索**：来源越不可追溯、
图/解析越可能缺、内容越改过，越该先看。规则全部公开在 `risk()` 里，
每条命中都带一句原因，界面上原样显示，不做黑箱评分。

## 分层抽样

按 `book × 题型` 分层，按各层题量比例分配，最少给非空层 1 道；
固定 seed 可复现。每条结果带 `review_batch`，复核后可以按批次算
错误率与 Wilson 95% 置信区间。
"""
from __future__ import annotations

import math
import random
import re
import time
from collections import Counter, defaultdict

from .schema import QTYPE_LABEL, Question

# ── 状态 ──────────────────────────────────────────────────────────────

STATUSES = ("pending", "approved", "needs_fix", "flagged")
EFFECTIVE = STATUSES + ("stale",)
REVIEWED = frozenset(("approved", "needs_fix", "flagged"))
STATUS_LABEL = {
    "pending": "待审",
    "approved": "已通过",
    "needs_fix": "需修改",
    "flagged": "存疑",
    "stale": "内容已改，原复核失效",
}
STATUS_SHORT = {
    "pending": "待审", "approved": "通过",
    "needs_fix": "需改", "flagged": "存疑", "stale": "失效",
}
TIER_LABEL = {"high": "高", "medium": "中", "low": "低"}

_FIG_REF = re.compile(r"如图|如下图|上图|下图|左图|右图|图中|图\s*[12]")
_IMG = re.compile(r"\\includegraphics|tikzpicture")


def _has_any_figure(q: Question) -> bool:
    if q.figures:
        return True
    texts = [q.stem or "", q.solution or ""] + [o.text or "" for o in q.options]
    return any(_IMG.search(t) for t in texts)


def _dangling_solution_figure(q: Question) -> bool:
    """解析里指了一张图，但整题一张图都没有。"""
    if not _FIG_REF.search(q.solution or ""):
        return False
    return not _has_any_figure(q)


def legacy_status(q: Question) -> str:
    """没有 review_status 时的历史口径（不写盘）。"""
    m = q.meta or {}
    st = str(m.get("review_status") or "").strip()
    if st in STATUSES:
        return st
    if m.get("reviewed_at"):
        # 旧代码改答案/解析时会同时写 reviewed_at 和 edited_at（同一分钟）。
        # 这种“顺手打上的戳”不能算人工复核。
        if m.get("edited_at") and str(m.get("edited_at")) == str(m.get("reviewed_at")):
            return "stale"
        return "approved"
    return "pending"


def effective_status(q: Question) -> str:
    st = legacy_status(q)
    if st in REVIEWED:
        h = str((q.meta or {}).get("reviewed_hash") or "")
        # 有指纹才谈失效；旧数据只有 reviewed_at，没法判断，按已复核保留
        if h and h != q.content_hash():
            return "stale"
    return st


def _tier(score: int) -> str:
    if score >= 35:
        return "high"
    if score >= 18:
        return "medium"
    return "low"


def risk(q: Question, status: str | None = None) -> tuple[int, list[str], str]:
    """返回 (0–100 风险分, 原因列表, high/medium/low)。

    只读元数据与正文里的「可疑信号」，不改任何东西。分数是排序用的，
    不是对题目正确性的断言。
    """
    m = q.meta or {}
    score = 0
    reasons: list[str] = []

    def add(n: int, why: str) -> None:
        nonlocal score
        score += n
        reasons.append(why)

    ans = str(m.get("answer_source") or "无")
    if ans in ("", "无"):
        add(16, "答案来源未登记")
    elif ans == "workbuddy":
        add(12, "答案是模型生成")
    elif ans == "legacy":
        add(6, "答案来源是历史存量")

    sol = str(m.get("solution_source") or "无")
    if sol in ("", "无"):
        add(14, "解析来源未登记")
    elif sol == "workbuddy" or sol.startswith("workbuddy+"):
        add(10, "解析是模型生成")
    elif sol == "legacy":
        add(5, "解析来源是历史存量")

    if not (q.answer or "").strip():
        add(25, "没有答案")
    if not q.has_solution:
        add(25, "没有可用的解析")
    if not q.figure_ok:
        add(20, "题干说如图，但图没进来")
    if m.get("figure_missing"):
        add(18, "录入时标记了缺图")
    if _dangling_solution_figure(q):
        add(18, "解析引用了不存在的图")
    if m.get("figure_low_res"):
        add(8, "配图分辨率低")

    ps = str(m.get("point_source") or "")
    if not ps:
        add(7, "考点来源未登记")
    elif ps == "llm":
        add(3, "考点由模型标注")

    if str(m.get("difficulty_source") or "") == "model":
        try:
            conf = float(m.get("difficulty_conf") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf and conf < 0.7:
            add(4, "难度模型置信度低")

    if m.get("solve_warn"):
        add(12, "求解时标记了存疑")
    if m.get("dup_of"):
        add(4, "有同型题可对照")

    st = status or effective_status(q)
    if st == "stale":
        add(8, "内容改过，原复核已失效")

    score = max(0, min(100, score))
    return score, reasons, _tier(score)


def info(q: Question) -> dict:
    st = effective_status(q)
    score, reasons, tier = risk(q, st)
    m = q.meta or {}
    return {
        "status": st,
        "label": STATUS_LABEL.get(st, st),
        "short": STATUS_SHORT.get(st, st),
        "reviewed_at": str(m.get("reviewed_at") or ""),
        "reviewed_by": str(m.get("reviewed_by") or ""),
        "note": str(m.get("review_note") or ""),
        "batch": str(m.get("review_batch") or ""),
        "reviewed_hash": str(m.get("reviewed_hash") or ""),
        "stale": st == "stale",
        "risk": score,
        "tier": tier,
        "reasons": reasons,
    }


def apply_decision(q: Question, status: str, *, note: str = "",
                   reviewer: str = "", batch: str = "") -> None:
    """把一次审阅决定写进 meta。**调用方负责落盘。**

    `pending` = 撤销/收回；approved/needs_fix/flagged = 记复核指纹。
    `stale` 不接受写入，它是正文变化后的派生状态。
    """
    status = (status or "").strip()
    if status not in STATUSES:
        raise ValueError("审阅状态只能是 %s" % " / ".join(STATUSES))
    m = q.meta
    if status == "pending":
        for k in ("review_status", "reviewed_at", "reviewed_by",
                  "reviewed_hash", "review_note", "review_batch"):
            m.pop(k, None)
        return
    stamp = time.strftime("%Y-%m-%d %H:%M")
    m["review_status"] = status
    m["reviewed_at"] = stamp
    m["reviewed_hash"] = q.content_hash()
    if reviewer.strip():
        m["reviewed_by"] = reviewer.strip()[:40]
    else:
        m.pop("reviewed_by", None)
    note = (note or "").strip()
    if note:
        m["review_note"] = note[:2000]
    else:
        m.pop("review_note", None)
    if batch.strip():
        m["review_batch"] = batch.strip()[:80]
    else:
        m.pop("review_batch", None)


# ── 统计 ──────────────────────────────────────────────────────────────

def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def stats(qs: list[Question]) -> dict:
    counts = Counter()
    risk_counts = Counter()
    by_book: dict[str, dict] = {}
    batches: dict[str, Counter] = defaultdict(Counter)
    last = ""
    for q in qs:
        it = info(q)
        st = it["status"]
        counts[st] += 1
        risk_counts[it["tier"]] += 1
        book = str((q.meta or {}).get("book") or "未标")
        b = by_book.setdefault(book, {"book": book, "total": 0, "pending": 0,
                                      "approved": 0, "needs_fix": 0,
                                      "flagged": 0, "stale": 0, "high": 0})
        b["total"] += 1
        b["high"] += 1 if it["tier"] == "high" else 0
        if st == "pending":
            b["pending"] += 1
        elif st == "stale":
            b["stale"] += 1
            b["pending"] += 1
        elif st in REVIEWED:
            b[st] += 1
        if it["reviewed_at"] > last:
            last = it["reviewed_at"]
        batch = it["batch"]
        if batch and st in REVIEWED:
            batches[batch][st] += 1
            batches[batch]["n"] += 1

    reviewed = sum(counts[s] for s in REVIEWED)
    pending = counts["pending"] + counts["stale"]
    total = len(qs)
    batch_rows = []
    for batch, c in sorted(batches.items(), reverse=True):
        n = c["n"]
        bad = c["needs_fix"] + c["flagged"]
        lo, hi = wilson_ci(bad, n)
        batch_rows.append({
            "batch": batch, "n": n, "approved": c["approved"],
            "needs_fix": c["needs_fix"], "flagged": c["flagged"],
            "error_rate": (bad / n) if n else 0.0,
            "ci_low": lo, "ci_high": hi,
        })
    return {
        "total": total,
        "reviewed": reviewed,
        "pending": pending,
        "approved": counts["approved"],
        "needs_fix": counts["needs_fix"],
        "flagged": counts["flagged"],
        "stale": counts["stale"],
        "review_rate": (reviewed / total) if total else 0.0,
        "risk": {k: risk_counts[k] for k in ("high", "medium", "low")},
        "by_book": sorted(by_book.values(), key=lambda x: (-x["total"], x["book"])),
        "batches": batch_rows[:30],
        "last_reviewed_at": last,
    }


# ── 队列 / 抽样 ───────────────────────────────────────────────────────

def _kw_hit(q: Question, kw: str) -> bool:
    if not kw:
        return True
    k = kw.lower()
    m = q.meta or {}
    hay = " ".join([
        q.key, q.stem or "", q.answer or "", q.solution or "",
        str(m.get("book") or ""), str(m.get("source_label") or ""),
        str(m.get("region") or ""), " ".join(q.point_titles or []),
    ]).lower()
    return k in hay


def _status_ok(st: str, want: str) -> bool:
    want = (want or "pending").strip()
    if want in ("", "all"):
        return True
    if want == "pending":
        return st in ("pending", "stale")
    return st == want


def queue(qs: list[Question], *, status: str = "pending", risk_tier: str = "",
          book: str = "", type: str = "", year_from: int = 0,
          kw: str = "", sort: str = "risk",
          limit: int = 50, offset: int = 0) -> tuple[int, list[tuple[Question, dict]]]:
    out = []
    for q in qs:
        it = info(q)
        if not _status_ok(it["status"], status):
            continue
        if risk_tier and it["tier"] != risk_tier:
            continue
        m = q.meta or {}
        if book and str(m.get("book") or "") != book:
            continue
        if type and q.type != type:
            continue
        if year_from:
            try:
                y = int(m.get("year") or 0)
            except (TypeError, ValueError):
                y = 0
            if y < year_from:
                continue
        if not _kw_hit(q, kw):
            continue
        out.append((q, it))
    if sort == "risk":
        out.sort(key=lambda x: (-x[1]["risk"], x[0].key))
    elif sort == "old":
        out.sort(key=lambda x: x[0].key)
    elif sort == "seq":
        pass                     # 保持题库原序（load_all 的追加顺序）
    else:
        out.sort(key=lambda x: (-int((x[0].meta or {}).get("year") or 0), x[0].key))
    total = len(out)
    return total, out[offset:offset + limit]


def _allocate(pops: dict[str, int], n: int) -> dict[str, int]:
    """按层题量比例分配 n，非空层至少 1 道（n 不够时给题量大的层）。"""
    keys = sorted(pops)
    if n <= 0 or not keys:
        return {k: 0 for k in keys}
    if n >= sum(pops.values()):
        return dict(pops)
    quotas = {k: 0 for k in keys}
    for k in sorted(keys, key=lambda x: (-pops[x], x))[:min(n, len(keys))]:
        quotas[k] = 1
    total_pop = sum(pops.values())
    for _ in range(n - sum(quotas.values())):
        # 只在还有容量的层里挑：目标配额 - 已分配，取缺口最大的；
        # 同缺口取容量大的，最后用 key 保证确定性。
        cand = [k for k in keys if quotas[k] < pops[k]]
        if not cand:
            break
        best = max(cand, key=lambda k: (
            (n * pops[k] / total_pop) - quotas[k],
            pops[k] - quotas[k], k))
        quotas[best] += 1
    return quotas


def sample(qs: list[Question], n: int = 100, seed: int | None = None,
           *, book: str = "", type: str = "", year_from: int = 0,
           risk_tier: str = "") -> dict:
    """按 `book × 题型` 分层随机抽样；只抽待审/失效的题。"""
    n = max(1, min(int(n), 500))
    seed = int(seed if seed is not None else time.time())
    rng = random.Random(seed)
    groups: dict[str, list[tuple[Question, dict]]] = defaultdict(list)
    for q in qs:
        it = info(q)
        if it["status"] not in ("pending", "stale"):
            continue
        if risk_tier and it["tier"] != risk_tier:
            continue
        m = q.meta or {}
        if book and str(m.get("book") or "") != book:
            continue
        if type and q.type != type:
            continue
        if year_from:
            try:
                y = int(m.get("year") or 0)
            except (TypeError, ValueError):
                y = 0
            if y < year_from:
                continue
        key = "%s|%s" % (str(m.get("book") or "未标"), q.type)
        groups[key].append((q, it))
    pops = {k: len(v) for k, v in groups.items()}
    quotas = _allocate(pops, n)
    picked: list[tuple[Question, dict, str, int, int]] = []
    strata = []
    for key in sorted(groups):
        pool = groups[key]
        take = min(quotas.get(key, 0), len(pool))
        if take:
            for q, it in rng.sample(pool, take):
                picked.append((q, it, key, len(pool), take))
        strata.append({
            "key": key,
            "book": key.rsplit("|", 1)[0],
            "type": key.rsplit("|", 1)[-1],
            "type_label": QTYPE_LABEL.get(key.rsplit("|", 1)[-1], key.rsplit("|", 1)[-1]),
            "population": len(pool),
            "sample": take,
        })
    rng.shuffle(picked)
    batch_id = "R%s-%s" % (time.strftime("%Y%m%d%H%M"), seed % 1000000)
    return {
        "batch_id": batch_id,
        "seed": seed,
        "requested": n,
        "population": sum(pops.values()),
        "items": picked,
        "strata": strata,
    }


def selftest() -> int:
    ok = 0
    total = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal ok, total
        total += 1
        ok += 1 if cond else 0
        print("  %s %s%s" % ("✓" if cond else "✗", name,
                             ("  " + extra) if extra and not cond else ""))

    def mk(key: str, **kw) -> Question:
        return Question(key=key, type=kw.pop("type", "single_choice"),
                        stem=kw.pop("stem", "已知 $x=1$，则 $x+1=$\\paren[B]"),
                        options=kw.pop("options", []),
                        answer=kw.pop("answer", "B"),
                        solution=kw.pop("solution", "因为 $1+1=2$，故选 B。"),
                        meta=kw.pop("meta", {}), **kw)

    q = mk("t/1")
    check("默认待审", effective_status(q) == "pending", effective_status(q))
    apply_decision(q, "approved", note="看过", reviewer="张三", batch="R1")
    check("通过后状态", effective_status(q) == "approved", effective_status(q))
    check("通过后写指纹", bool(q.meta.get("reviewed_hash")))
    check("备注/复核人落盘", q.meta.get("review_note") == "看过"
          and q.meta.get("reviewed_by") == "张三")
    q.answer = "C"
    check("改答案后自动 stale", effective_status(q) == "stale", effective_status(q))

    q2 = mk("t/2", meta={"reviewed_at": "2026-01-01 10:00",
                         "edited_at": "2026-01-01 10:00"})
    check("旧的编辑自动戳算 stale", effective_status(q2) == "stale", effective_status(q2))
    q3 = mk("t/3", meta={"reviewed_at": "2026-01-01 10:00",
                         "edited_at": "2026-01-01 09:00"})
    check("旧的人工复核保留", effective_status(q3) == "approved", effective_status(q3))

    q4 = mk("t/4", meta={"answer_source": "无", "solution_source": "无",
                         "point_source": ""})
    score, reasons, tier = risk(q4, "pending")
    check("来源未知进入高风险", tier == "high", "%s %s" % (score, reasons))
    check("风险原因有文字", any("来源" in r for r in reasons), str(reasons))

    q5 = mk("t/5", solution="如图，作辅助线……", meta={
        "answer_source": "workbuddy", "solution_source": "workbuddy",
        "point_source": "llm"})
    score5, reasons5, _ = risk(q5, "pending")
    check("解析悬空图被扣分", any("不存在的图" in r for r in reasons5), str(reasons5))

    lo, hi = wilson_ci(1, 50)
    check("Wilson 区间包住点估计", lo <= 0.02 <= hi, "%.3f-%.3f" % (lo, hi))
    check("Wilson 空样本", wilson_ci(0, 0) == (0.0, 0.0))

    qs = [mk("s/%d" % i, type=("single_choice" if i % 2 else "fill_in_blank"),
             meta={"book": "A" if i % 3 else "B"}) for i in range(60)]
    a = sample(qs, 20, seed=42)
    b = sample(qs, 20, seed=42)
    check("抽样可复现", [x[0].key for x in a["items"]] == [x[0].key for x in b["items"]])
    check("抽样数不超过请求", len(a["items"]) == 20, len(a["items"]))
    check("抽样覆盖两层", len(a["strata"]) >= 2, len(a["strata"]))
    check("抽样不重复", len({x[0].key for x in a["items"]}) == len(a["items"]))
    check("批次号非空", bool(a["batch_id"]))

    st = stats(qs)
    check("统计待审数", st["pending"] == 60, st["pending"])
    print("\n%d/%d 通过" % (ok, total))
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
