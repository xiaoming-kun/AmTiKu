r"""AmTiKu · 查重

录入前先问一句「库里是不是已经有这道题了」。旧项目在这上面栽过：
同一道高考题在不同汇编里出现两次，两次都进了库，组卷时一卷两题。

判据只用一个：**归一化题干的字符级相似度**。

    归一化  →  去掉一切「排版差异」，只留「内容」
    比相似  →  difflib 的字符级比值（标准库，无依赖）

阈值（**与 `设计/录入流程.md` 的原始约定不同，这里改严了，理由见下**）：

    归一化后**完全相同** → 同一道题   → 建议并入原题，不新建
    0.80–1.00           → 疑似        → 列出来交给人判断
    < 0.80              → 正常新建

⚠️ **为什么「并入」要求完全相同，而不是相似度 ≥ 0.96**

实测：把库里的 2024 新高考I卷#1（求 $A\cap B$）改成求 $A\cup B$ 再录一遍，
相似度是 **0.980**。设计文档原来写「≥0.96 并入」，于是这两道**不同的题**
会被自动合并成一道——`∪` 和 `∩` 只差一个字符，但它们是两道题。

归一化本来就已经抹掉了全部**排版**差异（空白、定界符、`\dfrac`/`\frac`、
`\fillin{}`/`（\quad）`）。所以归一化后还有差异，就是**内容**差异，
哪怕只差一个字符。**自动合并的代价远大于多问一句。**

⚠️ **而且无论如何都只提示，不自动合并。** 判断权留给人。
"""
from __future__ import annotations

import difflib
import re

# 归一化时抹掉的东西：都是「排版差异」，不是「内容差异」
_STRIP_CMDS = (
    r"\left", r"\right", r"\big", r"\Big", r"\bigg", r"\Bigg",
    r"\quad", r"\qquad", r"\,", r"\;", r"\!", r"\ ",
    r"\nolimits", r"\limits", r"\displaystyle", r"\textstyle",
)
_UNIFY = {
    r"\dfrac": r"\frac", r"\tfrac": r"\frac", r"\cfrac": r"\frac",
    r"\leqslant": r"\le", r"\geqslant": r"\ge",
    r"\cdot": "", r"\times": "", r"\div": "",
    r"\varnothing": r"\emptyset",
    r"\symbfit": "", r"\symbf": "", r"\boldsymbol": "", r"\mathbf": "",
    r"\mathrm": "", r"\text": "", r"\mbox": "",
}
# 空的占位形态：答案位 / 填空位。同一道题可能用不同写法，比之前先统一
_BLANK_PAT = re.compile(
    r"（\s*\\quad\s*）|\(\s*\\quad\s*\)|（\s*）|\(\s*\)|\\fillin\s*(?:\{\})?"
    r"|\\paren(?:\{\})?|_{2,}|\\underline\{\s*\}")
_PUNCT = re.compile(r"[，。、；：？！,.;:?!\"'“”‘’（）()\[\]【】\s]+")


def norm_stem(stem: str) -> str:
    r"""题干归一化。**只做无争议的归一**，不做语义改写。

    归一过头会把「$a>0$」和「$a<0$」判成同一道题——那比不查重更糟。
    """
    s = stem or ""
    s = re.sub(r"(?<!\\)%[^\n]*", "", s)          # 注释
    for c in _STRIP_CMDS:
        s = s.replace(c, "")
    for a, b in _UNIFY.items():
        s = s.replace(a, b)
    s = _BLANK_PAT.sub("_", s)                     # 空位统一成 _
    s = s.replace("$", "").replace("{", "").replace("}", "")
    s = s.replace("\\\\", "")
    s = _PUNCT.sub("", s)
    return s.lower()


def similarity(a: str, b: str) -> float:
    """两个**已归一化**字符串的相似度（0–1）。"""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ══ 语义关键词：**一个词就能把题变成另一道题** ══════════════════════════
#
# 光看字符相似度会漏掉中文数学里最要命的一类：
#
#     已知 $f(x)$ 在 $\mathbb{R}$ 上**单调递增**，求 $a$ 的取值范围。
#     已知 $f(x)$ 在 $\mathbb{R}$ 上**单调递减**，求 $a$ 的取值范围。
#
# 两句话只差一个字，字符相似度 **0.963** —— 按原来的阈值直接落进「疑似」。
# 实测这一对，加上 至少一个/至多一个、存在/任意、正数/负数、
# 不小于/不大于、恒成立/有解，**6 对里 6 对都被判成「疑似」**，
# 而老师会说这是六对不同的题。同类还有"并集 vs 交集"（0.93）——
# 那是出题人最爱设的对照题。
#
# 所以除了字符相似度，再抽一层**语义关键词**：一串"改了它就换题"的词与符号。
# 两份题的关键词集合只要对不上，无论字符多像都**不许当重复**。
#
# 这一招学自 MathBank 的 `_CRITICAL_TOKEN_RE`（`question_duplicates.py:65-88`）
# 加 `critical_matches` 闸门。它那边还把关键词按 数值/关系/量词/变量/运算符
# 分成五类以给出可读理由；这里先用朴素的一层——**集合是否一致**。
# 够用，而且没有阈值要标定（阈值是最容易标错的东西）。
#
# ⚠️ 只收"成对出现才有意义"的词。别把 `函数`/`取值范围`/`已知` 这类
# 每道题都有的词收进来——它们对判定毫无贡献，只会让关键词集合永远相等、
# 这道闸门等于没装。
_CRITICAL_WORDS = (
    # 单调性
    "单调递增", "单调递减", "单调不减", "单调不增", "递增", "递减", "增函数", "减函数",
    # 量词 / 存在性 —— 中文数学里最爱设的一组对照
    "至少一个", "至多一个", "有且仅有", "有且只有", "至少", "至多",
    "任意", "任一", "所有", "每个", "存在", "不存在", "唯一",
    # 数的范围
    "正数", "负数", "非正", "非负", "为正", "为负", "整数", "自然数", "有理数",
    # 不等关系
    "不小于", "不大于", "不超过", "不少于", "大于", "小于", "等于", "不等于",
    "大于等于", "小于等于", "恒成立", "有解", "无解", "充分", "必要", "充要",
    # 统计 / 概率
    "相互独立", "互斥", "对立", "放回", "不放回", "有放回", "无放回",
    # 几何关系
    "相切", "相交", "相离", "内切", "外切", "平行", "垂直", "异面",
    # 集合
    "并集", "交集", "补集", "子集", "真子集", "空集",
    # 数列
    "等差数列", "等比数列", "递增数列", "递减数列",
)
# 单个符号也要算：`A\cup B` 与 `A\cap B`、`\geqslant` 与 `\leqslant`
# 是同一类"一字之差换一道题"。这些宏在 `_UNIFY` 里**没有被合并**
# （`_UNIFY` 统一的是同义写法，不是近形宏），所以归一化后仍分得开。
_CRITICAL_SYMBOLS = (
    r"\cup", r"\cap", r"\subset", r"\subseteq", r"\supseteq", r"\supset",
    r"\varnothing", r"\emptyset", r"\parallel", r"\perp", r"\cong", r"\equiv",
    r"\geqslant", r"\leqslant", r"\ge", r"\le", r"\neq", r"\pm", r"\mp",
)
_CRITICAL_RE = re.compile(
    "|".join([re.escape(w) for w in _CRITICAL_WORDS]
             + [re.escape(s) for s in _CRITICAL_SYMBOLS]))


def critical_tokens(text: str) -> frozenset:
    r"""抽「语义关键词」集合。传**归一化后**的题干（`norm_stem` 的输出）。"""
    return frozenset(_CRITICAL_RE.findall(text or ""))


def critical_conflict(a: str, b: str) -> bool:
    r"""两份**已归一化**的题干，语义关键词是否对不上。

    对不上 = 至少有一边的某个"换词就换题"的词，另一边没有。
    返回 True 时**无论字符多像都不该判成重复**。
    """
    return critical_tokens(a) != critical_tokens(b)


def _trigrams(s: str) -> set[str]:
    return {s[i:i + 3] for i in range(max(0, len(s) - 2))} or {s}


class DedupIndex:
    r"""库内查重索引。

    两段式：先用**字符三元组**倒排粗筛候选（快），再算精确相似度（准）。
    全量库 2 万道时，逐对算 difflib 是 2 万次长字符串比对，太慢；
    粗筛把候选压到个位数。

    ⚠️ **粗筛会丢候选，所以它必须能被质询。**
    两处会造成"查过了，但没查全"：

      ① `norm_stem` 为空的题**不进索引** —— 它永远不会被当成重复找到，
         而且没有任何提示；
      ② 候选按三元组命中数排序后**只取前 `MAX_CANDIDATES` 个** ——
         真正的重复如果排在后面就被漏掉。

    这两条都不该静默。「没找到重复」和「查不动了」是两回事，
    调 `index_status()` 能看见覆盖率，`find()` 之后能看见这次有没有被截断。
    （MathBank 是同一个立场：LSH 分桶被截断时强制 `ready=false`，
    把"本次结果可能不完整"透传给前端，而不是假装完整。）
    """

    #: 粗筛后进入精确比对的候选上限。调大更全但更慢。
    MAX_CANDIDATES = 60

    def __init__(self, questions):
        self.items: list[tuple[str, str, str]] = []      # (key, norm, title)
        self._inv: dict[str, list[int]] = {}
        self.total = 0                # 传进来多少道
        self.skipped: list[str] = []  # 归一化后为空、**没进索引**的那些 key
        self.last_truncated = False   # 上一次 find 有没有被 MAX_CANDIDATES 截断
        for q in questions:
            self.total += 1
            n = norm_stem(q.stem)
            if not n:
                self.skipped.append(q.key)
                continue
            i = len(self.items)
            self.items.append((q.key, n, (q.point_titles[0] if q.point_titles else "")))
            for g in _trigrams(n):
                self._inv.setdefault(g, []).append(i)

    def find(self, stem: str, *, threshold: float = 0.80, top: int = 3,
             exclude: set[str] | None = None) -> list[dict]:
        """找出与 `stem` 相似度 ≥ threshold 的库内题目，按相似度降序。

        ⚠️ 返回空列表**不等于**"库里没有重复"——可能是这次粗筛被截断了。
        调用方要区分的话用 `find_checked()`，它会一并给出 `complete`。
        """
        hits, _ = self.find_checked(stem, threshold=threshold, top=top, exclude=exclude)
        return hits

    def find_checked(self, stem: str, *, threshold: float = 0.80, top: int = 3,
                     exclude: set[str] | None = None) -> tuple[list[dict], bool]:
        r"""同 `find()`，另外返回 `complete`：这次**查全了没有**。

        `complete=False` 的含义很明确：候选被 `MAX_CANDIDATES` 截断了，
        所以"没找到"可能是假的。调用方要么调大上限重查，要么在界面上
        明说"本次查重结果可能不完整"。
        """
        self.last_truncated = False
        n = norm_stem(stem)
        if not n:
            return [], True
        # 粗筛：三元组命中数排序，取前若干；三元组全落空的题不可能相似
        votes: dict[int, int] = {}
        for g in _trigrams(n):
            for i in self._inv.get(g, ()):
                votes[i] = votes.get(i, 0) + 1
        if not votes:
            return [], True
        ranked = sorted(votes, key=lambda i: -votes[i])
        # **截断要记账**：`complete=False` 时"没找到重复"是**不可信**的。
        self.last_truncated = len(ranked) > self.MAX_CANDIDATES
        cand = ranked[:self.MAX_CANDIDATES]

        ln = len(n)
        mine = critical_tokens(n)
        out: list[dict] = []
        for i in cand:
            key, other, title = self.items[i]
            if exclude and key in exclude:
                continue
            # 长度差一倍以上，字符相似度不可能高，省掉精确比对
            lo, hi = sorted((ln, len(other)))
            if lo * 2 < hi:
                continue
            r = similarity(n, other)
            if r < threshold:
                continue
            # **语义闸门**：关键词对不上就不是同一道题，字符再像也不行。
            # 但**不把分数压下去、也不静默丢弃** —— 分数是"看起来多像"的
            # 客观事实（0.963 就是 0.963），该改的是**结论**。
            # 所以照原样返回分数，另加 `variant` 标记与理由，
            # 由 `verdict_of()` 把它归到「变式」而不是「疑似」。
            # （MathBank 的做法：critical 不匹配 → `possible_variant`，
            #  永不 `probable`；且结果永远是**给老师看的证据**，不是判决。）
            theirs = critical_tokens(other)
            if mine != theirs:
                only_mine = sorted(mine - theirs)[:3]
                only_theirs = sorted(theirs - mine)[:3]
                out.append({
                    "key": key, "score": round(r, 3), "title": title,
                    "variant": True,
                    "critical": {"mine": only_mine, "theirs": only_theirs},
                    "why": "语义关键词不同（本侧：%s；库内：%s）——是两道不同的题"
                           % ("、".join(only_mine) or "无",
                              "、".join(only_theirs) or "无"),
                })
                continue
            out.append({"key": key, "score": round(r, 3), "title": title})
        out.sort(key=lambda x: -x["score"])
        return out[:top], not self.last_truncated


# 「同一道题」的判据：归一化后**完全相同**。
# 不用相似度阈值——见文件头「为什么并入要求完全相同」。
MERGE_SCORE = 1.0
SUSPECT_SCORE = 0.80


def classify(score: float) -> str:
    """相似度 → 处理建议。

    ⚠️ 只看分数。语义关键词对不上的那种走 `verdict_of(hit)`——
    它的**分数仍然很高**（0.96 就是 0.96），但结论不该是「疑似」。
    """
    if score >= MERGE_SCORE:
        return "并入"
    if score >= SUSPECT_SCORE:
        return "疑似"
    return "新建"


def index_status(idx: "DedupIndex") -> dict:
    r"""查重索引的覆盖率体检。**宁可说"查不动"，也不假装完整。**

    返回：
      · `total`     传进来多少道题
      · `indexed`   真正进了索引多少道
      · `skipped`   归一化后题干为空、**永远查不到**的那些 key（要报出来）
      · `coverage`  indexed / total
      · `ready`     coverage 是否 100%
      · `note`      给人看的一句话
    """
    total = getattr(idx, "total", len(idx.items))
    indexed = len(idx.items)
    skipped = list(getattr(idx, "skipped", []))
    cov = (indexed / total) if total else 1.0
    ready = not skipped
    if ready:
        note = "索引完整：%d 道全在索引里" % indexed
    else:
        note = ("索引**不完整**：%d 道没有题干（归一化后为空），"
                "这些题永远不会被查重找到 —— %s" % (len(skipped), "、".join(skipped[:3])))
    return {"total": total, "indexed": indexed, "skipped": skipped,
            "coverage": round(cov, 4), "ready": ready, "note": note}


#: 语义关键词对不上时的结论。既不是「并入」（不许合并）也不是「疑似」
#: （它不是重复），而是**变式**——两道长得几乎一样、但换了关键条件的题。
#: 单独一档而不是丢掉，是因为这种题恰恰值得人看一眼：
#: 往往其中一道是另一道的改编，或者反过来，有人把条件抄错了。
VARIANT = "变式"


def verdict_of(hit: dict) -> str:
    r"""`DedupIndex.find()` 的一条命中 → 处理建议。

    **调用方应该用这个，不要自己拿 `classify(hit["score"])`。**
    后者会把「差一个关键条件」的题报成「疑似重复」，而中文数学里
    「单调递增/递减」「至少一个/至多一个」「存在/任意」这种对照
    正是出题人故意设的——报成疑似就是成片的噪声。
    """
    return VARIANT if hit.get("variant") else classify(hit.get("score") or 0.0)


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    from .schema import Option, Question

    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("dedup 自检")

    # 1. 归一化抹掉排版差异
    a = r"已知集合 $A=\{1,2,3\}$，$B=\{2,3,4\}$，则 $A\cup B=$（\quad）"
    b = r"已知集合 $A = \left\{ 1, 2, 3 \right\}$ ， $B=\left\{2,3,4\right\}$，则 $A \cup B =$ （\quad）"
    check("排版差异被抹平", norm_stem(a) == norm_stem(b),
          "%r != %r" % (norm_stem(a), norm_stem(b)))
    check("同一道题相似度为 1", similarity(norm_stem(a), norm_stem(b)) == 1.0)

    # 2. 不同题目不能误判
    c = r"已知集合 $A=\{1,2,3\}$，$B=\{2,3,4\}$，则 $A\cap B=$（\quad）"
    check("并集 vs 交集 相似但不为 1",
          0.80 <= similarity(norm_stem(a), norm_stem(c)) < 1.0,
          str(similarity(norm_stem(a), norm_stem(c))))

    d = r"已知函数 $f(x)=\mathrm{e}^x-ax$，讨论其单调性."
    check("完全不同的题相似度低",
          similarity(norm_stem(a), norm_stem(d)) < 0.6,
          str(similarity(norm_stem(a), norm_stem(d))))

    # 3. 空位写法差异要归一
    e1 = r"若 $x+1=2$，则 $x=$\fillin{}."
    e2 = r"若 $x+1=2$，则 $x=$（\quad）."
    check("\\fillin 与（\\quad）视作同一种空位",
          norm_stem(e1) == norm_stem(e2),
          "%r != %r" % (norm_stem(e1), norm_stem(e2)))

    # 4. 索引能真的找出来
    lib = [
        Question(key="k/1", type="single_choice", stem=a),
        Question(key="k/2", type="single_choice", stem=d),
    ]
    idx = DedupIndex(lib)
    hit = idx.find(b, threshold=0.80)
    check("索引命中同一道题", hit and hit[0]["key"] == "k/1", str(hit))
    check("分数在阈值之上", hit and hit[0]["score"] >= 0.96, str(hit))
    check("无关题目不入选", all(h["key"] != "k/2" for h in hit), str(hit))
    check("exclude 生效", not idx.find(b, threshold=0.80, exclude={"k/1"}), "未排除")

    # 5. 分类阈值
    check("完全相同的空位写法 → 并入", classify(1.0) == "并入")
    check("0.98（只差 ∪/∩ 一个字符）→ 疑似，不并入", classify(0.98) == "疑似")
    check("0.50 → 新建", classify(0.50) == "新建")

    # 6. 回归：差一个符号的题**绝不能**被判成同一道
    #    （实测踩过：$A\cap B$ 与 $A\cup B$ 相似度 0.980）
    lib2 = [Question(key="m/1", type="single_choice", stem=a)]
    idx2 = DedupIndex(lib2)
    r = idx2.find(b, threshold=0.80)
    check("回归：排版不同但内容相同 → 相似度 1.0",
          r and r[0]["score"] == 1.0, str(r))
    r2 = idx2.find(c, threshold=0.80)      # c 是 A∩B，与库里的 A∪B 差一个符号
    # ⚠️ 这里原来断言的是「疑似」。加了语义闸门之后它应该落到**「变式」**：
    # 分数照样很高（0.98，那是"看起来多像"的客观事实），但 `\cup` 与 `\cap`
    # 是语义关键词，对不上 → 不是重复，是两道对照题。断言分数区间不变、
    # 只把结论换成 `verdict_of`，这样"分数诚实、结论可解释"两件事都被钉住。
    check("回归：只差一个语义符号 → 分数仍高，但结论是「变式」而非「疑似」",
          r2 and 0.80 <= r2[0]["score"] < 1.0
          and verdict_of(r2[0]) == VARIANT and r2[0].get("why"),
          str(r2))

    # 7. 语义关键词闸门：中文数学里"换一个词就是另一道题"的那些对照。
    #    实测（加闸门之前）：下面 6 对**全部**被判成「疑似」，
    #    而老师会说六对都是不同的题。
    opposite = [("单调递增", "单调递减"), ("至少一个", "至多一个"),
                ("存在", "任意"), ("正数", "负数"),
                ("不小于", "不大于"), ("恒成立", "有解")]
    for wa, wb in opposite:
        sa = norm_stem(r"已知函数 $f(x)$ 在 $\mathbb{R}$ 上" + wa + r"，求 $a$ 的取值范围。")
        sb = norm_stem(r"已知函数 $f(x)$ 在 $\mathbb{R}$ 上" + wb + r"，求 $a$ 的取值范围。")
        # 先证明这一对**确实**长得极像——否则这条闸门是白测的
        sc = similarity(sa, sb)
        hit = {"score": sc, "variant": critical_conflict(sa, sb)}
        check("%s vs %s：像（%.3f）但结论为「变式」" % (wa, wb, sc),
              sc >= 0.85 and verdict_of(hit) == VARIANT and verdict_of(hit) != "疑似",
              "相似度 %.3f 结论 %s" % (sc, verdict_of(hit)))

    # 8. 闸门的**误报**边界：同义改写不能被它拦下来。
    #    `\leqslant` 与 `\le` 在 `_UNIFY` 里已经统一，所以关键词集合相同；
    #    排版差异同理。这一条是"干净样本"，没有它闸门可能把对的题拆开。
    same = [
        (r"$a \leqslant 1$", r"$a \le 1$"),
        (r"已知 $x>0$", r"已知 $x > 0$"),
    ]
    for wa, wb in same:
        check("同义写法不触发语义闸门：%s" % wa,
              not critical_conflict(norm_stem(wa), norm_stem(wb)),
              "%r vs %r" % (critical_tokens(norm_stem(wa)), critical_tokens(norm_stem(wb))))

    # 9. 索引覆盖率（B10）：**别把"查不动"说成"没有重复"**
    from .schema import Question as _Q
    covered = [
        _Q(key="c/1", type="single_choice", stem=a),          # 有题干 → 进索引
        _Q(key="c/2", type="single_choice", stem=""),          # 空题干 → 永远查不到
        # ⚠️ 别拿 `（  ）` 当"空"——它归一化成 `_`（空位占位符），是**非空**的。
        # 真正归一化为空的是"整句都是被抹掉的标点"这种。
        _Q(key="c/3", type="single_choice", stem="，。"),        # 归一化后为空 → 同上
    ]
    idx3 = DedupIndex(covered)
    st = index_status(idx3)
    check("覆盖率不是 100% 时 ready=False",
          st["ready"] is False and st["indexed"] == 1 and st["total"] == 3, str(st))
    check("没进索引的 key 被点名报出来",
          set(st["skipped"]) == {"c/2", "c/3"}, str(st["skipped"]))
    # `index_status` 把 coverage 四舍五入到 4 位，所以断言那个约定值本身
    check("覆盖率算得对（1/3 四舍五入到 4 位）",
          st["coverage"] == round(1 / 3, 4), str(st["coverage"]))
    check("索引完整时 ready=True",
          index_status(DedupIndex([_Q(key="c/4", type="single_choice", stem=a)]))["ready"] is True)

    # 截断要记账：候选数超过上限时 complete=False
    many = [_Q(key="m/%d" % i, type="single_choice",
               stem=a + ("$x_{%d}$" % i)) for i in range(DedupIndex.MAX_CANDIDATES + 40)]
    idx4 = DedupIndex(many)
    hits, complete = idx4.find_checked(a, threshold=0.5)
    check("候选被截断时 complete=False（不假装查全了）",
          complete is False and idx4.last_truncated is True,
          "complete=%s truncated=%s" % (complete, idx4.last_truncated))
    small = DedupIndex(many[:5])
    _, complete2 = small.find_checked(a, threshold=0.5)
    check("候选没超上限时 complete=True", complete2 is True)

    print("dedup 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
