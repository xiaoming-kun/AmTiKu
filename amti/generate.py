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
# 第 6 道起的分值。测试卷的题量是老师筛出来多少算多少，答案题可能 1 道、
# 也可能 20 道，超出的按 15 分一道。
ANSWER_EXTRA = 15
MINOR_SCORE = {"single_choice": 5, "multi_choice": 6, "fill_in_blank": 5}

# 题型的中文短名（说明文字里用）
SHORT_NAME = {"single_choice": "单选", "multi_choice": "多选",
              "fill_in_blank": "填空", "detailed_answer": "解答"}


def answer_scores(n: int) -> list[int]:
    r"""解答题分值表：**按高考卷面上的位置**取 —— 13/15/15/17/17，第 6 道起 15 分。

    以前这里把 77 分按题数**摊平**，保证"解答题板块恒为 77 分"——那是为了让
    标准高考卷正好 150 分。可测试卷的题量是老师筛出来多少算多少：

        1 道  → [77]        ← 一道解答题 77 分（用户：「解答题怎么能够是 77 分呢」）
        23 道 → 每道 3 分

    一道题值多少分，不该由卷上还有几道题决定。分值跟着**题在卷面上的位置**走。
    高考卷恒为 5 道 → [13,15,15,17,17] → 合计 77，全卷 150 分，一个字没变。
    """
    if n <= 0:
        return []
    return [ANSWER_SCORES[i] if i < len(ANSWER_SCORES) else ANSWER_EXTRA
            for i in range(n)]


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


# ── 双向细目表（命题蓝图）────────────────────────────────────────────
#
# 「双向」= **内容维度 × 难度维度**，这是教育测量学里命题的标准工具
# （「双向细目表」/ table of specifications）。一份好卷子不是"凑够 19 道题"，
# 而是**每个位置要什么难度、每个章节出几道**都事先定好，组完再拿实际值对账。
#
# 以前这里只有一条"章节别重复"的软规则，**难度完全不参与挑选**——
# 卷面的难度只是渲染时按位置标上去的一个标签，跟题目实际难度毫无关系。
# 于是所谓"难度适宜"全靠运气。

# 每个位置的**目标难度**。一行一个题型，第 i 个字就是该题型第 i 题的目标：
#     易 = 简单题，中 = 中档题，难 = 难题
#
# 这个形状是**算出来的**，不是拍的：在 8+3+3+5 的卷面上枚举所有
# 「易→难单调不减」的难度分配，加上真实卷面的形状约束
# （单选至少 3 易 2 中、最多 2 难；多选/填空各至少 1 中 1 难；
#   解答题不含简单题、至少 2 中 2 难），再取最接近标准「易:中:难 = 3:5:2」的那个。
#
# 结果落在 **易 36 分 : 中 69 分 : 难 45 分 = 24% : 46% : 30%**，
# 离 3:5:2 的 45/75/30 差 30 分——而且**这是结构性的**：
# 容易题最多只能来自「单选前 5 + 多选 1 + 填空 1」= 36 分，
# 解答题一道都不可能算容易（近五年真题里解答题只有 4.5% 标简单题）。
# 所以 45 分容易题在这个卷面上做不到，36 分就是天花板。
_DIFF_SHAPE: dict[str, str] = {
    "single_choice":   "易易易易易中中中",     # 1–5 易，6–8 中
    "multi_choice":    "易中难",               # 9 / 10 / 11
    "fill_in_blank":   "易中难",               # 12 / 13 / 14
    "detailed_answer": "中中中难难",           # 15–17 中，18–19 难
}
_DIFF_CHAR = {"易": "简单题", "中": "中档题", "难": "难题"}

# 小题（14 道）的**章节配额**，照**近五年高考真题实测**的占比缩放：
# 2021 年起的真题里，小题各章占比 解析几何 14.4% / 概率统计 13.9% /
# 函数 13.1% / 平面向量与复数 12.9% / 三角函数 11.0% / 立体几何 10.3% /
# 集合与逻辑 9.1% / 数列 6.5% / 不等式 5.1% / 导数 3.7%。
# 用最大余数法缩放到 14 道（和 `answer_scores`/`gaokao_mix` 同一套办法）。
#
# 表里没有的章节按 3% 算（约等于表里最小的那一档）——课标以后加章也不会
# 被完全排除在外；这份占比是**量出来的**，不是编的。
MINOR_TOPIC_WEIGHT: dict[str, float] = {
    "五、解析几何": 0.144, "九、概率统计": 0.139, "三、函数": 0.131,
    "八、平面向量与复数": 0.129, "六、三角函数与解三角形": 0.110,
    "十、立体几何与空间向量": 0.103, "一、集合与逻辑": 0.091,
    "七、数列": 0.065, "二、不等式": 0.051, "四、导数": 0.037,
}
UNKNOWN_TOPIC_WEIGHT = 0.03


def topic_quota(n_minor: int, topics: list[str]) -> dict[str, int]:
    """把实测占比缩放成"这 N 道小题里每章出几道"。最大余数法，合计正好 N。"""
    if n_minor <= 0:
        return {}
    exact = [(t, n_minor * MINOR_TOPIC_WEIGHT.get(t, UNKNOWN_TOPIC_WEIGHT))
             for t in topics]
    out = {t: int(v) for t, v in exact}
    rest = n_minor - sum(out.values())
    order = sorted(range(len(exact)), key=lambda i: -(exact[i][1] - int(exact[i][1])))
    for i in order[:rest]:
        out[exact[i][0]] += 1
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


def _blueprint_diff(slot: "Slot") -> str:
    """这个位置**要**什么难度（细目表说的）。"""
    shape = _DIFF_SHAPE.get(slot.type, "")
    return _DIFF_CHAR.get(shape[slot.index] if slot.index < len(shape) else "中", "中档题")


def _pick(cands: list[Question], used: set[str], counter: dict[str, int],
          *, want_diff: str, quota: dict[str, int] | None,
          rng: random.Random) -> tuple[Question | None, str]:
    r"""从候选里挑一道。返回 `(题目, 放宽到哪一级)`。

    **按细目表挑**，而不是"随便挑一道不重复的"：

    | 级别 | 条件 | 说明 |
    |---|---|---|
    | ①  | 难度对 + 章节还有配额 | 最理想，什么都不欠 |
    | ②  | 难度对（章节配额用完） | 记一笔"某章超配" |
    | ③  | 章节还有配额（难度不对） | 记一笔"这一档题不够" |
    | ④  | 都不满足 | 记一笔"只能退而求其次" |

    级内打分：**本章还没出现过**的优先（+3），同分随机——
    随机是为了同 seed 之外每次组出的卷子不完全一样。

    ⚠️ 为什么难度要参与挑选：`q.difficulty` 是**考点派生**的（内容难度），
    而位置难度是卷面设计。两者以前毫无联系，于是"第 1 题"有可能是道压轴难度的题，
    卷子的实际难度全凭运气。这一版把它们对上了。
    """
    def rank(q: Question) -> float:
        tp = topic_of(q)
        return (3.0 if counter.get(tp, 0) == 0 else 1.0) + rng.random()

    def pool_by(level: int) -> list[Question]:
        out = []
        for q in cands:
            if q.key in used:
                continue
            tp = topic_of(q)
            ok_diff = (q.difficulty == want_diff)
            ok_topic = (quota is None) or (counter.get(tp, 0) < quota.get(tp, 0))
            if level == 1 and not (ok_diff and ok_topic):
                continue
            if level == 2 and not ok_diff:
                continue
            if level == 3 and not ok_topic:
                continue
            out.append(q)
        return out

    for level, name in ((1, "ok"), (2, "章节超配"), (3, "难度不匹配"), (4, "只能退而求其次")):
        pool = pool_by(level)
        if pool:
            return max(pool, key=rank), name
    return None, "无题可用"


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

    # 细目表：小题的章节配额（照近五年真题量的占比缩放）
    n_minor = sum(1 for sl in slots if sl.type != "detailed_answer")
    topics_in_pool = sorted({topic_of(q) for q in pool if topic_of(q)})
    quota = topic_quota(n_minor, topics_in_pool)

    used: set[str] = set()
    # 小题与解答题**分开计数**（见 _pick 的说明）
    minor_topics: dict[str, int] = {}
    answer_topics: dict[str, int] = {}
    rep = PickReport()
    relaxed: dict[str, int] = {}
    out: list[dict] = []

    for slot in slots:
        cands = by_type.get(slot.type, [])
        want_diff = _blueprint_diff(slot)
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
            cands, counter, sl_quota = (fresh or same), answer_topics, None
        else:
            counter, sl_quota = minor_topics, quota

        q, level = _pick(cands, used, counter, want_diff=want_diff,
                         quota=sl_quota, rng=rng)
        if q is not None and level != "ok":
            relaxed[level] = relaxed.get(level, 0) + 1
        if q is None:
            rep.unfilled.append(
                f"{slot.type} 第 {slot.index + 1} 题"
                + (f"（{slot.section}）" if slot.section else ""))
            out.append({"key": "", "type": slot.type, "score": slot.score,
                        "section": slot.section, "index": slot.index,
                        "total": slot.total, "want_diff": want_diff, "got_diff": ""})
            continue
        used.add(q.key)
        tp = topic_of(q)
        counter[tp] = counter.get(tp, 0) + 1
        rep.filled.append(q.key)
        out.append({"key": q.key, "type": slot.type, "score": slot.score,
                    "section": slot.section, "index": slot.index,
                    "total": slot.total, "want_diff": want_diff,
                    "got_diff": q.difficulty, "topic": tp})

    score = sum(s["score"] for s in out if s["key"])
    if rep.unfilled:
        rep.notes.append(
            f"题库不足，有 {len(rep.unfilled)} 个位置空着。"
            "把更多题加进筛选结果，或先导入更多题目。")

    # ── 细目表达成度：目标 vs 实际 ──
    # 这是这份卷子"难不难、知识面均不均"的唯一凭据，直接给老师看。
    bp = _blueprint_report(out, quota)

    # 放宽了就要说清楚，别让用户以为卷子是完全按蓝图出的
    if relaxed.get("章节超配"):
        bp["notes"].append(
            f"有 {relaxed['章节超配']} 个位置的章节配额用完了，那一章多出了一两道")
    if relaxed.get("难度不匹配"):
        bp["notes"].append(
            f"有 {relaxed['难度不匹配']} 个位置**没能在目标难度上找到题**"
            f"（该档题不够），换成了别的难度")
    if relaxed.get("只能退而求其次"):
        bp["notes"].append(
            f"有 {relaxed['只能退而求其次']} 个位置难度和章节都没对上——题库这块太空了")
    d = rep.as_dict()
    d["blueprint"] = bp
    d["relaxed"] = relaxed
    return {"keys": [s["key"] for s in out if s["key"]],
            "slots": out, "report": d, "score": score}


def _blueprint_report(out: list[dict], quota: dict[str, int]) -> dict:
    """把实际组出来的卷子跟细目表对账。

    · **难度按分值**比（难度该看分，不是看题数），全部 19 个位置都算
    · **章节按题量**比，只算**小题**——解答题的章节是由「第几题考哪个板块」
      定死的（不是按占比挑的），拿它来跟"目标占比"对比是循环论证
    """
    tgt_d: dict[str, int] = {}
    act_d: dict[str, int] = {}
    act_t: dict[str, int] = {}
    for s in out:
        sc = s["score"] if s["key"] else 0
        tgt_d[s["want_diff"]] = tgt_d.get(s["want_diff"], 0) + sc
        if s["key"] and s.get("got_diff"):
            act_d[s["got_diff"]] = act_d.get(s["got_diff"], 0) + sc
        if s["type"] == "detailed_answer":
            continue                      # 见上面：解答题不参与章节对账
        tp = s.get("topic") or ""
        if s["key"] and tp:
            act_t[tp] = act_t.get(tp, 0) + 1
    return {"diff_target": tgt_d, "diff_actual": act_d,
            "topic_target": dict(quota), "topic_actual": act_t,
            "notes": []}


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


# 高考卷面的题型比例：8 单选 + 3 多选 + 3 填空 + 5 解答 = 19 题。
# 顺序就是卷面顺序，也是下面摊余数时的平手次序。
GAOKAO_MIX = (("single_choice", 8), ("multi_choice", 3),
              ("fill_in_blank", 3), ("detailed_answer", 5))


def gaokao_mix(want: int) -> dict[str, int]:
    r"""把高考卷面的题型比例**按比例缩放到 `want` 道**。

    和 `answer_scores()` 用同一套**最大余数法**：先按比例向下取整，
    余数大的依次加一，保证加起来**正好等于 `want`**（不然贪心会少挑几道）。

    为什么要这个：按覆盖率贪心只认"考点个数"，完全不管题型——
    实测 `want=46` 时它会挑出 **23 道解答题**（因为解答题平均挂 2.34 个考点，
    比单选题的 1.74 高，对目标函数而言是理性的）。但一半是解答题的卷子不能用。
    加上配额只掉约 2.6 个百分点的覆盖率（85.5% → 82.9%），换一份能用的卷面，值。
    """
    if want <= 0:
        return {}
    base_total = sum(n for _, n in GAOKAO_MIX)
    exact = [(t, want * n / base_total) for t, n in GAOKAO_MIX]
    out = {t: int(v) for t, v in exact}
    rest = want - sum(out.values())
    # 余数大的先加；余数一样就按卷面次序（和 answer_scores 的稳定排序同理）
    order = sorted(range(len(exact)), key=lambda i: -(exact[i][1] - int(exact[i][1])))
    for i in order[:rest]:
        out[exact[i][0]] += 1
    return out


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
            "short": short, "picked": picked}


def generate_by_coverage(pool: list[Question], *, want: int = 19,
                         coverage: float = 0.9, seed: int | None = None,
                         type_mix: dict[str, int] | None = None,
                         report_cost: bool = False) -> dict:
    r"""按**考点覆盖率**组一套卷。

    `coverage` 是目标覆盖率（0~1），对着**题库里能覆盖到的**考点算。
    `type_mix` 给题型配额（如 `gaokao_mix(46)`），不传就不限题型。
    `report_cost` 为真时**再跑一遍不限题型的**，好在说明里报出
    "为保卷面结构，覆盖率从 X% 降到 Y%"——多花一遍贪心的钱（实测约 1 秒），
    但这样用户才看得出这个开关值不值。

    返回 keys（已按易→难排好）和一份说明覆盖了多少。
    """
    rng = random.Random(seed)
    reachable = all_points_of(pool)
    if not reachable:
        return {"keys": [], "covered": [], "report": {"note": "这批题一个考点都没标"}}

    plan = cover_plan(pool, want=want, rng=rng, type_mix=dict(type_mix or {}))
    got, total = len(plan["covered"]), len(reachable)
    ratio = got / total if total else 0.0

    # 不限题型时的上限（只为了报"这个开关代价多大"）
    base_ratio = None
    if report_cost and type_mix:
        base = cover_plan(pool, want=want, rng=random.Random(seed))
        base_ratio = len(base["covered"]) / total if total else 0.0

    # 整卷总分。**必须和 `paper.py` 印在卷面上的一致**（界面上的"多少分"
    # 就是拿这个数报的）：解答题按位置取 `answer_scores()`，其余固定分。
    # 早先这里不返回 score，界面只好自己拿一张"解答题 15 分一道"的假表去算，
    # 一道 46 题的覆盖卷能报出 484 分，而卷面上只有 196 分。
    counts: dict[str, int] = {}
    for q in plan["picked"]:
        counts[q.type] = counts.get(q.type, 0) + 1
    score = total_score(counts)

    notes = ["目标覆盖 %.0f%%，实际覆盖 %.0f%%（%d/%d 个考点）"
             % (coverage * 100, ratio * 100, got, total)]
    if ratio < coverage:
        miss = sorted(reachable - set(plan["covered"]))
        notes.append("没覆盖到的考点还有 %d 个：%s%s"
                     % (len(miss), "、".join(miss[:8]),
                        "…" if len(miss) > 8 else ""))
        notes.append("**要么加题量，要么题库里这些考点的题太少**")
    if type_mix:
        mix_txt = " · ".join(
            "%s %d" % (SHORT_NAME.get(t, t), n) for t, n in
            ((t, type_mix.get(t, 0)) for t, _ in GAOKAO_MIX) if n)
        notes.insert(0, "题型按高考卷面比例分配：%s" % mix_txt)
        if base_ratio is not None and base_ratio > ratio + 0.005:
            notes.append("为保卷面结构，覆盖率从 %.0f%% 降到 %.0f%%（不限定题型时的最大覆盖是前者）"
                         % (base_ratio * 100, ratio * 100))
    if plan["short"]:
        notes.append("题型配额没满足：%s —— 这类题在筛选结果里不够" % plan["short"])

    return {"keys": plan["keys"], "covered": plan["covered"], "score": score,
            "report": {"covered": got, "reachable": total, "ratio": round(ratio, 3),
                       "target": coverage, "notes": notes,
                       **({"mix": {t: type_mix.get(t, 0) for t, _ in GAOKAO_MIX}}
                          if type_mix else {}),
                       **({"ratio_free": round(base_ratio, 3)}
                          if base_ratio is not None else {})}}


# ── 自检 ──────────────────────────────────────────────────────────────

_RANK = {"易": 0, "中": 1, "难": 2}


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

    # ── 计分口径：**界面上报的"多少分"和卷面上印的是同一个数** ──────────
    # 前端 `web/src/lib/paper.ts` 里有一份同样规则的 TS 实现（界面要实时算分，
    # 不能每加一道题就请求一次后端）。这两条断言就是那份拷贝的"锚"：
    # 改了这里的规则，这两条会红，提醒你回去改 TS。
    check("解答题按高考卷面位置给分：5 道 = 13/15/15/17/17 = 77 分",
          answer_scores(5) == ANSWER_SCORES and sum(answer_scores(5)) == 77,
          str(answer_scores(5)))
    # 分值跟着题走，不跟着卷走：题量变了，每道题的分数不能变。
    # 这条同时钉住「1 道解答题 ≠ 77 分」，以及前端 `paper.ts` 那份拷贝。
    check("解答题分值不随题量摊平（1 道=13、6 道=92、每道都在 13~17）",
          answer_scores(1) == [13] and answer_scores(6) == [13, 15, 15, 17, 17, 15]
          and all(13 <= s <= 17 for n in range(1, 31) for s in answer_scores(n)),
          str([(n, answer_scores(n)) for n in (1, 2, 6)]))
    check("标准高考卷 8+3+3+5 = 150 分",
          total_score({"single_choice": 8, "multi_choice": 3,
                       "fill_in_blank": 3, "detailed_answer": 5}) == 150,
          str(total_score({"single_choice": 8, "multi_choice": 3,
                           "fill_in_blank": 3, "detailed_answer": 5})))
    # ── 双向细目表的锚 ──────────────────────────────────────────
    # 这三个数（36/69/45）是"算出来的"，改动 _DIFF_SHAPE 就会变，所以钉住它：
    # 它是"容易题在 8+3+3+5 上最多只占 36 分"这个结论的具体体现。
    _shape_scores = {"易": 0, "中": 0, "难": 0}
    for _t, _scores in STRUCTURE:
        _sh = _DIFF_SHAPE.get(_t, "")
        for _i, _sc in enumerate(_scores):
            if _i < len(_sh):
                _shape_scores[_sh[_i]] += _sc
    check("细目表难度分值 = 易36/中69/难45（3:5:2 在本题型结构上到不了 45/75/30）",
          (_shape_scores["易"], _shape_scores["中"], _shape_scores["难"]) == (36, 69, 45),
          str(_shape_scores))
    check("难度形状在每个题型内单调不减（易→难）",
          all(all(_RANK[_sh[i]] <= _RANK[_sh[i + 1]] for i in range(len(_sh) - 1))
              for _sh in _DIFF_SHAPE.values()),
          str(_DIFF_SHAPE))
    _q14 = topic_quota(14, list(MINOR_TOPIC_WEIGHT))
    check("小题章节配额合计正好 14 道", sum(_q14.values()) == 14, str(_q14))

    check("覆盖卷 9+4+10+23 = 466 分（解答题 77 + 15×18，不摊成每道 3 分）",
          total_score({"single_choice": 9, "multi_choice": 4,
                       "fill_in_blank": 10, "detailed_answer": 23}) == 466,
          str(total_score({"single_choice": 9, "multi_choice": 4,
                           "fill_in_blank": 10, "detailed_answer": 23})))
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
