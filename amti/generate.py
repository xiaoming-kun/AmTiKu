r"""AmTiKu · 随机组卷

按高考真题的**结构和排布惯例**，从题库里组一套卷。

## 分值结构（2024 新课标卷，总分 150）

    一、单选   8 题 × 5 分 = 40
    二、多选   3 题 × 6 分 = 18
    三、填空   3 题 × 5 分 = 15
    四、解答   5 题        = 77   （13 + 15 + 15 + 17 + 17）

解答题**分值不是均分的**——15 题 13 分，16/17 题各 15 分，18/19 题各 17 分。
早先按每题 15 分算，整卷会变成 152 分。

## 排布规则（从 2021–2026 新高考/全国卷统计出来的）

解答题的顺序**没有硬规定**，各年都在变。但有两条强不变量：

    * **导数**永远在最后两位（压轴）
    * **解析几何**在倒数第二位附近

据此定顺序：

    1. 三角 / 数列      ← 开门题，最易
    2. 概率统计
    3. 立体几何
    4. 解析几何
    5. 导数             ← 压轴

小题（选择 + 填空共 14 道）的规则：**尽量覆盖不同章节，同一章节最多 2 道**。
真实卷就是这么分布的（2024 新高考I卷的 14 道小题覆盖了 8 个章节）。

难度不在这里定——`paper.py` 的 `POSITION_RULE` 按位置算，那是高考的惯例。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import knowledge as kb
from .schema import Question

# ── 结构 ──────────────────────────────────────────────────────────────

# 分值结构（2024 新课标卷）。解答题分值不均分，这是真实卷的样子。
STRUCTURE: list[tuple[str, list[int]]] = [
    ("single_choice", [5] * 8),
    ("multi_choice", [6] * 3),
    ("fill_in_blank", [5] * 3),
    ("detailed_answer", [13, 15, 15, 17, 17]),
]

# 解答题板块顺序。前三条是可以互换的，后两条基本固定。
ANSWER_ORDER = ["三角/数列", "概率统计", "立体几何", "解析几何", "导数"]

# 板块 → 知识点库的「大类」。用大类而不是硬编码考点 id，
# 这样知识点库改了也不用动这里。
SECTION_TOPICS: dict[str, set[str]] = {
    "三角/数列": {"六、三角函数与解三角形", "七、数列"},
    "概率统计": {"九、概率统计"},
    "立体几何": {"十、立体几何与空间向量"},
    "解析几何": {"五、解析几何"},
    "导数": {"四、导数"},
}

# 小题同一章节最多几道（14 道小题，10 个大类，2 道是上限）
MINOR_MAX_PER_TOPIC = 2

# 解答题**按位置**的分值，不是均分。真实卷就是这样：
# 15 题 13 分，16/17 题各 15 分，18/19 题各 17 分，合计 77。
ANSWER_SCORES = [13, 15, 15, 17, 17]
MINOR_SCORE = {"single_choice": 5, "multi_choice": 6, "fill_in_blank": 5}


def answer_scores(n: int) -> list[int]:
    r"""解答题分值表。标准是 5 题；题数不是 5 时按 77 分同比例摊，
    并用**最大余数法**保证加起来仍是 77（不然整卷会不是 150 分）。
    """
    if n <= 0:
        return []
    if n == len(ANSWER_SCORES):
        return list(ANSWER_SCORES)
    total = sum(ANSWER_SCORES)
    exact = [total / n] * n
    base = [int(x) for x in exact]
    rest = total - sum(base)
    # 余数大的先加
    order = sorted(range(n), key=lambda i: -(exact[i] - base[i]))
    for i in order[:rest]:
        base[i] += 1
    return base


def score_of(qtype: str, index: int, total: int) -> int:
    """一道题在卷面上的分值。解答题按位置取，其余固定。"""
    if qtype == "detailed_answer":
        table = answer_scores(total)
        return table[index] if index < len(table) else 15
    return MINOR_SCORE.get(qtype, 5)


def total_score(counts: dict[str, int]) -> int:
    """整卷总分。"""
    return (counts.get("single_choice", 0) * 5 + counts.get("multi_choice", 0) * 6
            + counts.get("fill_in_blank", 0) * 5
            + sum(answer_scores(counts.get("detailed_answer", 0))))


@dataclass
class Slot:
    """卷面上的一个位置。"""
    type: str
    score: int
    section: str = ""           # 解答题的板块；小题为空
    index: int = 0              # 同题型内的序号
    total: int = 0              # 同题型的总数


def topic_of(q: Question) -> str:
    """题目所属大类（按主考点）。没标签的归入空串。"""
    if not q.points:
        return ""
    return kb.get(q.points[0]).get("topic", "")


def build_slots(mode: str = "gaokao") -> list[Slot]:
    r"""按结构生成槽位。

    `test` 模式**不用高考结构**——测试题是按考点专练，题量由你筛出来多少决定。
    """
    if mode != "gaokao":
        return []
    out: list[Slot] = []
    for t, scores in STRUCTURE:
        for i, sc in enumerate(scores):
            sec = ANSWER_ORDER[i] if t == "detailed_answer" else ""
            out.append(Slot(type=t, score=sc, section=sec,
                            index=i, total=len(scores)))
    return out


# ── 抽取 ──────────────────────────────────────────────────────────────

@dataclass
class PickReport:
    filled: list[str] = field(default_factory=list)
    unfilled: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"filled": len(self.filled), "unfilled": self.unfilled,
                "notes": self.notes}


def _pick_pass(cands: list[Question], used: set[str], counter: dict[str, int],
               max_per_topic: int, rng: random.Random, *, strict: bool):
    best, best_score = None, -1e9
    for q in cands:
        if q.key in used:
            continue
        tp = topic_of(q)
        n = counter.get(tp, 0)
        if strict and n >= max_per_topic:
            continue
        s = 3.0 if n == 0 else 1.0
        s += rng.random()                      # 同分随机，避免每次组出同一套
        if s > best_score:
            best, best_score = q, s
    return best


def _pick(cands: list[Question], used: set[str], counter: dict[str, int],
          *, max_per_topic: int, rng: random.Random) -> tuple[Question | None, bool]:
    """从候选里挑一道。返回 `(题目, 是否放宽了章节上限)`。

    打分（高分先选，同分随机）：
      +3  这一档里该章节还没出现过（鼓励覆盖不同章节）
      +1  出现过但没到上限

    ⚠️ `counter` 必须**分档独立**：小题的章节计数和解答题的分开。
    早先共用一个计数器，于是小题把某章节用满两次后，
    解答题里属于该章节的题全被挡掉——实测组出来的卷子只有 15 题。

    ⚠️ 严格按上限挑不到时**放宽上限**再挑一次：
    **题量是硬的，章节分布是软的**。题库小的时候，宁可某一章出现三次，
    也不能让卷面空一个位置——那看起来像程序坏了。放宽了会记进报告。
    """
    q = _pick_pass(cands, used, counter, max_per_topic, rng, strict=True)
    if q is not None:
        return q, False
    return _pick_pass(cands, used, counter, max_per_topic, rng, strict=False), True


def generate(pool: list[Question], *, mode: str = "gaokao",
             seed: int | None = None) -> dict:
    r"""从 `pool` 里组一套卷。返回 `{keys, slots, report, score}`。

    `mode="gaokao"` 按高考结构；`mode="test"` 不做结构约束，按传入顺序直接用。
    """
    rng = random.Random(seed)
    if mode != "gaokao":
        return {"keys": [q.key for q in pool],
                "slots": [{"type": q.type, "score": 0, "section": "", "index": i,
                           "total": len(pool)} for i, q in enumerate(pool)],
                "report": {"filled": len(pool), "unfilled": [],
                           "notes": ["测试题不做结构约束，用传入的题目顺序"]},
                "score": 0}

    slots = build_slots("gaokao")
    by_type: dict[str, list[Question]] = {}
    for q in pool:
        by_type.setdefault(q.type, []).append(q)

    used: set[str] = set()
    # 小题与解答题**分开计数**（见 _pick 的说明）
    minor_topics: dict[str, int] = {}
    answer_topics: dict[str, int] = {}
    rep = PickReport()
    out: list[dict] = []

    for slot in slots:
        cands = by_type.get(slot.type, [])
        if slot.type == "detailed_answer" and slot.section:
            want = SECTION_TOPICS.get(slot.section, set())
            same = [q for q in cands if topic_of(q) in want]
            if not same:
                rep.notes.append(
                    f"解答题第 {slot.index + 1} 题想要「{slot.section}」，"
                    f"题库里没有这个板块的题，改从全部解答题里挑")
                same = cands
            # 解答题**五个板块互不重复**：本板块已用过就换别的板块的题
            fresh = [q for q in same if answer_topics.get(topic_of(q), 0) == 0]
            cands, counter, max_per = (fresh or same), answer_topics, 1
        else:
            counter, max_per = minor_topics, MINOR_MAX_PER_TOPIC

        q, relaxed = _pick(cands, used, counter, max_per_topic=max_per, rng=rng)
        if relaxed and q is not None:
            rep.notes.append(
                f"{slot.type} 第 {slot.index + 1} 题：题库里够分的章节都用满了，"
                f"放宽了「同章节最多 {max_per} 道」的限制")
        if q is None:
            rep.unfilled.append(
                f"{slot.type} 第 {slot.index + 1} 题"
                + (f"（{slot.section}）" if slot.section else ""))
            out.append({"key": "", "type": slot.type, "score": slot.score,
                        "section": slot.section, "index": slot.index,
                        "total": slot.total})
            continue
        used.add(q.key)
        tp = topic_of(q)
        counter[tp] = counter.get(tp, 0) + 1
        rep.filled.append(q.key)
        out.append({"key": q.key, "type": slot.type, "score": slot.score,
                    "section": slot.section, "index": slot.index,
                    "total": slot.total})

    score = sum(s["score"] for s in out if s["key"])
    if rep.unfilled:
        rep.notes.append(
            f"题库不足，有 {len(rep.unfilled)} 个位置空着。"
            "把更多题加进筛选结果，或先导入更多题目。")
    return {"keys": [s["key"] for s in out if s["key"]],
            "slots": out, "report": rep.as_dict(), "score": score}


# ── 组卷方案：按**考点覆盖**组卷 ──────────────────────────────────────
#
# 用户要的：「出一套高考模拟题，几乎要覆盖 90% 的考点」。
#
# 这跟 `generate()` 不是一回事：那个是**按卷面结构**填位置
# （几个单选、几个解答），覆盖什么考点是顺带的。
# 这个是**以覆盖率为目标**去挑题。

# 难度从易到难的顺序。卷面本来就该这样排——
# 高考卷前面简单后面难，不是随机撒的。
DIFF_ORDER = {"简单题": 0, "中档题": 1, "难题": 2}


def all_points_of(pool: list[Question]) -> set[str]:
    """这批题**能覆盖到的**考点集合。

    是「题库里有的」而不是「知识点库全部 153 个」——
    拿题库里根本没有的考点去要求覆盖，那是缘木求鱼。
    """
    out: set[str] = set()
    for q in pool:
        out.update(q.points)
    return out


def cover_plan(pool: list[Question], *, want: int, rng,
               must_cover: set[str] | None = None,
               type_mix: dict[str, int] | None = None) -> dict:
    r"""挑 `want` 道题，**尽量多覆盖考点**，并按**易→难**排好。

    贪心：每轮挑「能带来最多新考点」的那道；打平时挑简单的。
    这是集合覆盖的经典近似（贪心能到最优解的 1-1/e），
    对组卷够用，而且**结果可解释**——每一步为什么挑它说得清。

    `type_mix` 给题型配额（如 `{"single_choice": 8}`），
    不传就不限。配额满足不了时**报出来**，不静默少题。
    """
    picked: list[Question] = []
    used: set[str] = set()
    covered: set[str] = set()
    remaining = list(pool)
    short: dict[str, int] = {}

    for _ in range(want):
        best, best_gain, best_diff = None, -1, 99
        for q in remaining:
            if q.key in used:
                continue
            if type_mix:
                quota = type_mix.get(q.type)
                if quota is not None and quota <= 0:
                    continue
            gain = len(set(q.points) - covered)
            # 优先覆盖「指定必覆盖」里还没覆盖的
            if must_cover:
                gain += 2 * len(set(q.points) & (must_cover - covered))
            d = DIFF_ORDER.get(q.difficulty, 9)
            # 新考点多者优先；一样多时**先挑简单的**（前面该是简单题）
            if gain > best_gain or (gain == best_gain and d < best_diff):
                best, best_gain, best_diff = q, gain, d
        if best is None:
            break
        picked.append(best)
        used.add(best.key)
        covered.update(best.points)
        remaining = [q for q in remaining if q.key != best.key]
        if type_mix and best.type in type_mix:
            type_mix[best.type] -= 1

    for t, n in (type_mix or {}).items():
        if n > 0:
            short[t] = n

    # **按难度从易到难排**（同难度保持挑选顺序）
    picked.sort(key=lambda q: DIFF_ORDER.get(q.difficulty, 9))
    return {"keys": [q.key for q in picked], "covered": sorted(covered),
            "short": short}


def generate_by_coverage(pool: list[Question], *, want: int = 19,
                         coverage: float = 0.9, seed: int | None = None,
                         type_mix: dict[str, int] | None = None) -> dict:
    r"""按**考点覆盖率**组一套卷。

    `coverage` 是目标覆盖率（0~1），对着**题库里能覆盖到的**考点算。
    返回 keys（已按易→难排好）和一份说明覆盖了多少。
    """
    rng = random.Random(seed)
    reachable = all_points_of(pool)
    if not reachable:
        return {"keys": [], "covered": [], "report": {"note": "这批题一个考点都没标"}}

    plan = cover_plan(pool, want=want, rng=rng, type_mix=dict(type_mix or {}))
    got, total = len(plan["covered"]), len(reachable)
    ratio = got / total if total else 0.0

    notes = ["目标覆盖 %.0f%%，实际覆盖 %.0f%%（%d/%d 个考点）"
             % (coverage * 100, ratio * 100, got, total)]
    if ratio < coverage:
        miss = sorted(reachable - set(plan["covered"]))
        notes.append("没覆盖到的考点还有 %d 个：%s%s"
                     % (len(miss), "、".join(miss[:8]),
                        "…" if len(miss) > 8 else ""))
        notes.append("**要么加题量，要么题库里这些考点的题太少**")
    if plan["short"]:
        notes.append("题型配额没满足：%s" % plan["short"])

    return {"keys": plan["keys"], "covered": plan["covered"],
            "report": {"covered": got, "reachable": total, "ratio": round(ratio, 3),
                       "target": coverage, "notes": notes}}


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    from .schema import Option

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("generate 自检")

    slots = build_slots("gaokao")
    check("共 19 个槽位", len(slots) == 19, str(len(slots)))
    check("总分 150", sum(s.score for s in slots) == 150,
          str(sum(s.score for s in slots)))
    check("解答题分值 13/15/15/17/17",
          [s.score for s in slots if s.type == "detailed_answer"] == [13, 15, 15, 17, 17],
          str([s.score for s in slots if s.type == "detailed_answer"]))
    check("解答题板块顺序正确",
          [s.section for s in slots if s.type == "detailed_answer"] == ANSWER_ORDER,
          str([s.section for s in slots if s.type == "detailed_answer"]))
    check("测试模式没有槽位", build_slots("test") == [])

    # 造一个够用的池子
    def mk(i, t, pid):
        return Question(key="k/%d" % i, type=t, stem="题 %d" % i, points=[pid])

    pool: list[Question] = []
    n = 0
    for i in range(12):
        n += 1; pool.append(mk(n, "single_choice", ["1.1.1", "3.3.3", "8.5.1", "6.1.1"][i % 4]))
    for i in range(6):
        n += 1; pool.append(mk(n, "multi_choice", ["4.4.1", "9.2.6"][i % 2]))
    for i in range(6):
        n += 1; pool.append(mk(n, "fill_in_blank", ["5.2.2", "10.1.3"][i % 2]))
    # 解答题：五个板块各给两道
    for sec in ANSWER_ORDER:
        tp = sorted(SECTION_TOPICS[sec])[0]
        pid = next(p["id"] for p in kb.all_points() if p["topic"] == tp)
        for _ in range(2):
            n += 1; pool.append(mk(n, "detailed_answer", pid))

    r = generate(pool, seed=42)
    check("组出 19 道", len(r["keys"]) == 19, str(len(r["keys"])))
    check("满分 150", r["score"] == 150, str(r["score"]))
    check("没有重复题", len(set(r["keys"])) == len(r["keys"]), "有重复")
    ans = [s for s in r["slots"] if s["type"] == "detailed_answer"]
    check("解答题板块按序填满",
          all(s["key"] for s in ans) and [s["section"] for s in ans] == ANSWER_ORDER,
          str([(s["section"], bool(s["key"])) for s in ans]))
    check("解答题五道分属五个不同板块",
          len({topic_of(next(q for q in pool if q.key == s["key"])) for s in ans}) == 5,
          "有板块重复")

    # 确定性：同一 seed 出同一套
    check("同 seed 结果一致", generate(pool, seed=7)["keys"] == generate(pool, seed=7)["keys"])
    check("不同 seed 结果不同", generate(pool, seed=1)["keys"] != generate(pool, seed=2)["keys"])

    # 章节配额挡死候选时要放宽，不能空位置
    r3 = generate(pool, seed=3)
    check("题库够时 19 个位置全填满", len(r3["keys"]) == 19, str(len(r3["keys"])))
    check("真填不满才报未填", not r3["report"]["unfilled"], str(r3["report"]["unfilled"]))

    # 池子不够时要报出来，不能静默少题
    r2 = generate(pool[:10], seed=1)
    check("题不够时报未填位置", r2["report"]["unfilled"], str(r2["report"]))
    check("题不够时不编造题", all(k for k in r2["keys"]), "出现空 key")

    print("generate 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
