"""AmTiKu · 查重

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


def _trigrams(s: str) -> set[str]:
    return {s[i:i + 3] for i in range(max(0, len(s) - 2))} or {s}


class DedupIndex:
    r"""库内查重索引。

    两段式：先用**字符三元组**倒排粗筛候选（快），再算精确相似度（准）。
    全量库 2 万道时，逐对算 difflib 是 2 万次长字符串比对，太慢；
    粗筛把候选压到个位数。
    """

    def __init__(self, questions):
        self.items: list[tuple[str, str, str]] = []      # (key, norm, title)
        self._inv: dict[str, list[int]] = {}
        for q in questions:
            n = norm_stem(q.stem)
            if not n:
                continue
            i = len(self.items)
            self.items.append((q.key, n, (q.point_titles[0] if q.point_titles else "")))
            for g in _trigrams(n):
                self._inv.setdefault(g, []).append(i)

    def find(self, stem: str, *, threshold: float = 0.80, top: int = 3,
             exclude: set[str] | None = None) -> list[dict]:
        """找出与 `stem` 相似度 ≥ threshold 的库内题目，按相似度降序。"""
        n = norm_stem(stem)
        if not n:
            return []
        # 粗筛：三元组命中数排序，取前若干；三元组全落空的题不可能相似
        votes: dict[int, int] = {}
        for g in _trigrams(n):
            for i in self._inv.get(g, ()):
                votes[i] = votes.get(i, 0) + 1
        if not votes:
            return []
        cand = sorted(votes, key=lambda i: -votes[i])[:60]

        ln = len(n)
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
            if r >= threshold:
                out.append({"key": key, "score": round(r, 3), "title": title})
        out.sort(key=lambda x: -x["score"])
        return out[:top]


# 「同一道题」的判据：归一化后**完全相同**。
# 不用相似度阈值——见文件头「为什么并入要求完全相同」。
MERGE_SCORE = 1.0
SUSPECT_SCORE = 0.80


def classify(score: float) -> str:
    """相似度 → 处理建议。"""
    if score >= MERGE_SCORE:
        return "并入"
    if score >= SUSPECT_SCORE:
        return "疑似"
    return "新建"


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
    check("回归：只差一个符号时必须落到「疑似」",
          r2 and 0.80 <= r2[0]["score"] < 1.0 and classify(r2[0]["score"]) == "疑似",
          str(r2))

    print("dedup 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
