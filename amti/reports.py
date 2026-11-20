"""数据治理报告（只读）：审阅清单 / 考点分布 / 题型配额 / 占位与低清。

对应评估报告第四节的 #3–#5、#7 —— 这些建议的产物是「给人看的清单」，
不是改数据。所有统计都从真实库现算，口径写在每份报告开头。

    python3 amti.py report              # 四份都出
    python3 amti.py report --sample 50  # 抽样数改 50
"""
from __future__ import annotations

import random
import sqlite3
import time
from collections import Counter
from pathlib import Path

from amti import knowledge
from amti import review as rv
from amti.paths import ROOT

OUT_DIR = ROOT / "数据" / "报告"
READMODEL = ROOT / "数据" / "缓存" / "readmodel.sqlite"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join("---" for _ in head) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "\\|") for x in r) + " |")
    return out


def _write(name: str, lines: list[str]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ── #3 审阅清单 ──────────────────────────────────────────────
def review_plan(qs, *, sample: int = 100, seed: int = 20261120) -> dict:
    rows = []
    for q in qs:
        st = rv.effective_status(q)
        score, why, _tier = rv.risk(q, st)
        rows.append({"key": q.key, "status": st, "score": score,
                     "why": why, "type": q.type})
    pending = [r for r in rows if r["status"] in ("pending", "stale")]
    tiers = Counter(rv._tier(r["score"]) for r in rows)
    top = sorted((r for r in pending if r["score"] >= 70),
                 key=lambda r: -r["score"])
    mid = sorted((r for r in pending if 40 <= r["score"] < 70),
                 key=lambda r: -r["score"])
    low = sorted((r for r in pending if r["score"] < 40),
                 key=lambda r: -r["score"])
    rnd = random.Random(seed)
    picked = rnd.sample(pending, min(sample, len(pending))) if pending else []

    lines = ["# 审阅清单（风险优先 + 分层随机抽样）", "",
             "- 生成时间：%s" % _now(),
             "- 题库：%d 道；待审（pending + stale）：%d 道；已复核：%d 道"
             % (len(qs), len(pending), len(qs) - len(pending)),
             "- 风险分层（review._tier）：高 %d / 中 %d / 低 %d"
             % (tiers["high"], tiers["medium"], tiers["low"]),
             "- 其中 70 分以上 %d 道、40–69 分 %d 道；抽样本 %d 道（seed=%d）"
             % (len(top), len(mid), len(picked), seed),
             "",
             "打标方式：`POST /api/review/decision`（带 reviewer → 写 reviewed_by），",
             "或题库页逐题审阅。正文一改，reviewed_hash 失配、自动回到 stale。", "",
             "## 最高风险（≥70）", ""]
    lines += _table(["分数", "题目", "状态", "原因"],
                    [[r["score"], "`%s`" % r["key"], r["status"],
                      "；".join(r["why"])] for r in top])
    lines += ["", "## 高优先（40–69）", ""]
    lines += _table(["分数", "题目", "状态", "原因"],
                    [[r["score"], "`%s`" % r["key"], r["status"],
                      "；".join(r["why"])] for r in mid])
    lines += ["", "## 低风险待审（<40，按分数倒序，只列前 300）", ""]
    lines += _table(["分数", "题目", "状态", "原因"],
                    [[r["score"], "`%s`" % r["key"], r["status"],
                      "；".join(r["why"])] for r in low[:300]])
    lines += ["", "## 分层随机抽样（%d 道）" % len(picked), ""]
    lines += _table(["分数", "题目", "状态", "原因"],
                    [[r["score"], "`%s`" % r["key"], r["status"],
                      "；".join(r["why"])] for r in picked])
    p = _write("审阅清单.md", lines)
    return {"path": str(p), "pending": len(pending), "stale":
            sum(1 for r in rows if r["status"] == "stale"),
            "top": len(top), "mid": len(mid), "sampled": len(picked)}


# ── #4 考点分布 ─────────────────────────────────────────────
def point_report(qs) -> dict:
    cnt: Counter = Counter()
    for q in qs:
        for pid in (getattr(q, "points", None) or q.meta.get("points") or []):
            cnt[str(pid)] += 1
    use = cnt.most_common()
    total = sum(cnt.values()) or 1
    senior = {p["id"] for p in knowledge.all_points("senior")}
    junior = {p["id"] for p in knowledge.all_points("junior")}
    primary = {p["id"] for p in knowledge.all_points("primary")}
    cover = {"senior": sum(1 for k in cnt if k in senior),
             "junior": sum(1 for k in cnt if k in junior),
             "primary": sum(1 for k in cnt if k in primary)}
    zero_junior = sorted(junior - set(cnt))
    zero_primary = sorted(primary - set(cnt))
    top10 = int(len(use) * 0.10) or 1
    top25 = int(len(use) * 0.25) or 1
    top50 = int(len(use) * 0.50) or 1
    share = lambda n: 100.0 * sum(c for _k, c in use[:n]) / total
    rows = [[k, knowledge.title_of(k), c, "%.2f%%" % (100.0 * c / total)]
            for k, c in use[:30]]
    tail = [[k, knowledge.title_of(k), c] for k, c in use[-30:]]
    lines = ["# 考点分布校准", "",
             "- 生成时间：%s" % _now(),
             "- 题库：%d 道；有考点的题：%d 道；考点引用：%d 次；被引用考点：%d 个"
             % (len(qs), sum(1 for q in qs if (q.points or q.meta.get("points"))), total, len(cnt)),
             "- 考点库：高中 %d / 初中 %d / 小学 %d；已覆盖：高中 %d / 初中 %d / 小学 %d"
             % (len(senior), len(junior), len(primary),
                cover["senior"], cover["junior"], cover["primary"]),
             "- 集中度：被引用考点的前 10%% 占引用 %.1f%%，前 25%% 占 %.1f%%，前 50%% 占 %.1f%%"
             % (share(top10), share(top25), share(top50)),
             "- 缺口：初中零覆盖 %d 个、小学零覆盖 %d 个（题库没有小学题）"
             % (len(zero_junior), len(zero_primary)),
             "",
             "**「真卷占比」列暂空**：项目内还没有近 5 年新高考 I/II 卷的逐题考点表。",
             "建议新增 `数据/真卷考点频次.json`（{考点 id: 出现次数}）后，本报告会自动补上",
             "「题库占比 vs 真卷占比」和按缺口的补题清单。没有这份外部数据前不编造对照值。",
             "", "## 热点（前 30）", ""]
    lines += _table(["考点", "名称", "题数", "占引用"], rows)
    lines += ["", "## 尾部（最少 30 个，有引用的考点）", ""]
    lines += _table(["考点", "名称", "题数"], tail)
    lines += ["", "## 零覆盖", "",
              "初中（%d）：%s" % (len(zero_junior),
                                "、".join("%s %s" % (k, knowledge.title_of(k))
                                         for k in zero_junior[:40])),
              "", "小学（%d 个考点全部零覆盖，题库 0 道小学题）：%s"
              % (len(zero_primary),
                 "、".join(zero_primary[:20]) + ("…" if len(zero_primary) > 20 else ""))]
    p = _write("考点分布校准.md", lines)
    return {"path": str(p), "points_used": len(cnt), "refs": total,
            "zero_junior": len(zero_junior), "zero_primary": len(zero_primary)}


# ── #5 题型配额 ─────────────────────────────────────────────
TARGET = {"single_choice": 42.1, "multi_choice": 15.8,
          "fill_in_blank": 15.8, "detailed_answer": 26.3}
NAMES = {"single_choice": "单选", "multi_choice": "多选",
         "fill_in_blank": "填空", "detailed_answer": "解答"}


def type_quota_report(qs) -> dict:
    def dist(items):
        c = Counter(q.type for q in items)
        return {t: 100.0 * c.get(t, 0) / len(items) for t in TARGET} if items else {}

    def block(title, items):
        d = dist(items)
        rows = []
        for t in TARGET:
            cur = d.get(t, 0.0)
            target_n = TARGET[t] / 100.0 * len(items)
            cur_n = sum(1 for q in items if q.type == t)
            rows.append([NAMES[t], cur_n, "%.1f%%" % cur,
                         "%.1f%%" % TARGET[t], "%+.0f" % (cur_n - target_n)])
        return ["## " + title + "（%d 道）" % len(items), ""] + \
            _table(["题型", "现有", "现有占比", "目标占比", "缺口（目标-现有）"], rows) + [""]

    lines = ["# 题型配额缺口", "",
             "- 生成时间：%s" % _now(),
             "- 目标配额（报告口径）：单选 42.1% / 多选 15.8% / 填空 15.8% / 解答 26.3%",
             "- 说明：这是「库存是否撑得住标准卷」的检查，不替用户决定补哪些题；",
             "  组卷模板的按卷面配额参数尚未接入（generate.py 只有 topic_quota），待产品确认。", ""]
    stage = {}
    try:
        con = sqlite3.connect(str(READMODEL))
        stage = {k: v for k, v in con.execute("select key, stage from questions")}
        con.close()
    except Exception:
        stage = {}
    lines += block("全库", qs)
    lines += block("高中", [q for q in qs if stage.get(q.key, "senior") != "junior"])
    lines += block("初中", [q for q in qs if stage.get(q.key) == "junior"])
    p = _write("题型配额缺口.md", lines)
    return {"path": str(p)}


# ── #7 占位与低清 ───────────────────────────────────────────
def placeholder_report(qs) -> dict:
    marks = []
    for q in qs:
        for field, text in (("题干", q.stem), ("答案", q.answer), ("解析", q.solution)):
            if "【缺：" in (text or ""):
                i = text.find("【缺：")
                marks.append((q.key, field, text[i:i + 60].replace("\n", " ")))
    low = []
    try:
        con = sqlite3.connect(str(READMODEL))
        low = [r[0] for r in con.execute("select key from questions where lowres=1 order by key")]
        con.close()
    except Exception:
        low = []
    lines = ["# 占位与低清清单", "",
             "- 生成时间：%s" % _now(),
             "- `【缺：` 占位：%d 处（涉及 %d 道题）" % (len(marks), len({m[0] for m in marks})),
             "- 低清图：%d 道" % len(low),
             "",
             "占位不是格式错误，是**原卷就缺**（缺页/缺图/截断）。这类题不能靠库内信息补全，",
             "要么找到原卷补，要么下架——需要人判断，脚本不自动处理。", "",
             "## `【缺：` 占位", ""]
    seen = set()
    for key, field, text in marks:
        if (key, text) in seen:
            continue
        seen.add((key, text))
        lines.append("- `%s` · %s：%s" % (key, field, text))
    lines += ["", "## 低清图（%d 道）" % len(low), ""]
    lines += ["- `%s`" % k for k in low]
    p = _write("占位与低清清单.md", lines)
    return {"path": str(p), "marks": len(marks), "lowres": len(low)}


def write_all(qs, *, sample: int = 100) -> dict:
    return {
        "审阅清单": review_plan(qs, sample=sample),
        "考点分布": point_report(qs),
        "题型配额": type_quota_report(qs),
        "占位与低清": placeholder_report(qs),
    }
