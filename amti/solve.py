r"""AmTiKu · 模拟题求解（本地大模型）

**规矩（用户明确要求）**：一道题求解、一道题写入，**完成一个写一个**。
不做批量——批量意味着中途崩了就全丢，而且出错时无法回滚到某一道。

模型走 LM Studio 的 OpenAI 兼容接口（`http://127.0.0.1:1234/v1`）。

用法：
    python3 -m amti.solve --check              # 看还有多少要解、模型通不通
    python3 -m amti.solve --limit 20           # 解 20 道
    python3 -m amti.solve                      # 一直解到没有为止
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import normalize as norm, store
from .schema import Question

from amti.logutil import get_logger

log = get_logger(__name__)

API = "http://127.0.0.1:1234/v1/chat/completions"
MODEL = "qwen/qwen3.8-27b"
# 推理模型的额度**思考 + 正文一起算**，给少了正文就是空的。
# 见 `call_model` 的说明。
MAX_TOKENS = 8000
LOG = Path("/tmp/ruku/solve.log")

SYSTEM = (
    "你是高中数学老师。给你一道题，你要：\n"
    "1. 给出答案；\n"
    "2. 给出**完整、简洁**的解析（讲清怎么想、每步为什么）。\n\n"
    "严格按下面的格式回答，不要有别的内容：\n\n"
    "<答案>\n"
    "（选择题只写字母，如 A 或 ACD；填空题只写结果；解答题写最终结论）\n"
    "</答案>\n"
    "<解析>\n"
    "（可以含 LaTeX 公式，行内用 $…$，行间用 \\[ … \\]）\n"
    "</解析>\n\n"
    "注意：\n"
    "- LaTeX 里不要写中文，中文放公式外面或用 \\text{} 包起来。\n"
    "- 不要用 \\begin{enumerate}，小问直接写「(1)」「(2)」。\n"
    "- 解析要能让人看懂，但别啰嗦。"
)


def build_prompt(q: Question) -> str:
    parts = ["题型：%s" % q.type, "题干：%s" % q.stem]
    if q.options:
        parts.append("选项：")
        for o in q.options:
            parts.append("  %s. %s" % (o.label, o.text or "（图片选项）"))
    return "\n".join(parts)


def call_model(prompt: str, *, timeout: int = 600) -> str:
    r"""问模型一次，返回正文。

    ⚠️ **`max_tokens` 必须给足。** 这是推理模型：它先在 `reasoning_content`
    里想，想完才写正文，而 `max_tokens` **把两者算在一起**。
    实测 3000 时，难题上模型要想 200 多秒，额度在思考阶段就烧光了，
    正文返回**空字符串**——白等一趟，还查不出原因。
    所以这里给 8000，并在失败信息里带上 `finish_reason`：
    被截断（`length`）和没按格式（`stop`）是两回事，得能分开看。
    """
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    ch = d["choices"][0]
    LAST_CALL.clear()
    LAST_CALL.update({
        "finish_reason": ch.get("finish_reason") or "",
        "usage": d.get("usage") or {},
        "reasoning": len(ch["message"].get("reasoning_content") or ""),
    })
    return ch["message"]["content"] or ""


# 上一次调用的元信息（截断/用量）。**只为把失败原因说清楚**，不参与判断。
LAST_CALL: dict = {}


_TAG = re.compile(r"</?(?:答案|解析)>")


def _block(text: str, tag: str) -> str:
    r"""取 `<tag> … </tag>` 之间的内容。

    **闭合标签可以缺。** 实测模型经常开了 `<解析>` 就一路写到底、
    忘了收尾（`finish_reason=stop`，说明不是被截断，就是没写）。
    开标签本身已经把左边界划清楚了，右边界退化成"下一个标签或结尾"
    完全够用——原来苛求闭合标签，代价是**整段解析连同答案一起被丢掉**，
    一道题白算 200 多秒。
    """
    m = re.search(r"<%s>\s*" % tag, text)
    if not m:
        return ""
    rest = text[m.end():]
    end = rest.find("</%s>" % tag)
    if end >= 0:                       # 有闭合标签：用它
        return rest[:end].strip()
    nxt = _TAG.search(rest)            # 没有：用下一个标签当边界
    return (rest[:nxt.start()] if nxt else rest).strip()


def parse_reply(text: str) -> tuple[str, str]:
    r"""从模型回复里取 (答案, 解析)。取不到就返回空，**不猜**。

    两段**各自**判定：答案取到了、解析没取到，也把答案留下来——
    答案本身就有用（还能反过来验证题型标得对不对），没必要一起扔。
    """
    return _block(text, "答案"), _block(text, "解析")


def clean_answer(q: Question, ans: str) -> str:
    r"""把答案规整成项目要的形态；规整不了就返回空。"""
    ans = ans.strip().strip("。.").strip()
    if not ans:
        return ""
    if q.type in ("single_choice", "multi_choice"):
        letters = "".join(sorted(set(re.findall(r"[A-Da-d]", ans))))
        return letters.upper()
    return ans


def answer_hint(q: Question, ans: str) -> str:
    r"""答案形态和题型**对不上**时给的提示——只提示，不拦。

    用户的规矩：**求解不受题型约束**。模型答了 `ACD` 而题目标着单选，
    那多半是**题型标错了**（题干写着「（多选）」却被判成单选，库里
    真出过 347 道）。这时候正确的做法是**先把答案存下来**，题型之后
    按答案反推着改——而不是把答案丢掉、让这道题永远解不出来。

    返回空串表示形态正常。
    """
    if not ans:
        return "模型没给出可用的答案"
    letters = "".join(sorted(set(re.findall(r"[A-D]", ans))))
    if q.type == "single_choice" and len(letters) > 1:
        return "模型给了 %d 个选项（%s），题型可能要改成多选" % (len(letters), letters)
    if q.type == "multi_choice" and len(letters) == 1:
        return "模型只给了 1 个选项（%s），题型可能要改成单选" % letters
    if q.type in ("single_choice", "multi_choice") and not letters:
        return "模型没给出选项字母"
    return ""


_PICKED = re.compile(r"故选\s*([A-D](?:\s*[、,，]?\s*[A-D])*)")


def consistency_warn(q: Question, ans: str, sol: str) -> str:
    r"""轻量一致性检查——**挡不住答错，但能挡住"自相矛盾"**。

    选择题的解析通常以「故选 D」收尾。如果这里的字母和 `<答案>` 里的对不上，
    那至少有一处是错的，值得标出来人工看一眼。

    实测价值：模型偶尔会在解析里推对了、答案栏写错（或反过来）。
    这类矛盾是**免费的信号**——不用再跑一遍模型就能发现。
    """
    if q.type not in ("single_choice", "multi_choice"):
        return ""
    hits = _PICKED.findall(sol)
    if not hits:
        return ""
    last = "".join(sorted(set(re.findall(r"[A-D]", hits[-1]))))
    if last and ans and last != "".join(sorted(ans)):
        return "解析说「故选 %s」，答案栏是 %s" % (last, ans)
    return ""


MAX_ATTEMPTS = 3


def _bump_attempts(q: Question, raw: str = "") -> None:
    """失败留痕：同一道题连败 3 次就跳过，免得永远卡在它身上。

    `raw` 是模型这次的原始回复。留最后 2000 字下来——**"取不到 <解析>"
    到底是输出被截断，还是模型压根没按格式写**，不看原文就只能猜。
    """
    qs = store.load_all()
    t = next((x for x in qs if x.key == q.key), None)
    if t is None:
        return
    t.meta["solve_attempts"] = int(t.meta.get("solve_attempts") or 0) + 1
    t.meta["solve_error"] = time.strftime("%Y-%m-%d %H:%M")
    if raw:
        t.meta["solve_raw_tail"] = raw[-2000:]
    try:
        store.rewrite_all(qs)
    except Exception:
        log.error("求解结果写库失败（这批结果会丢）", exc_info=True)
        pass


# 求解顺序：**先易后难**。
# 用户的要求：简单题全部做完，再做中档，最后难题。
# 好处不只是"看着舒服"——简单题错得少，能先把量堆起来；
# 难题耗时最长（模型要想很久），放最后不阻塞前面的产出。
DIFF_ORDER = {"简单题": 0, "中档题": 1, "难题": 2}


def pending(difficulty: str = "") -> list[Question]:
    r"""还没解析、且**失败次数未超上限**的模拟题，**按难度从易到难排**。

    难度取主考点派生（`schema.Question.difficulty`）——和界面上显示的
    是同一套口径，不会出现"界面说简单、求解当难题"这种不一致。

    同一档内按录入顺序（书 → 页 → 题号），保证结果可复现。

    `difficulty` 给了就只要这一档（比如先只做「简单题」，难题留后面）。
    """
    qs = [q for q in store.load_all()
          if q.kind == "模拟" and not q.solution.strip()
          and int(q.meta.get("solve_attempts") or 0) < MAX_ATTEMPTS]
    if difficulty:
        want = {x.strip() for x in difficulty.split(",") if x.strip()}
        qs = [q for q in qs if q.difficulty in want]
    qs.sort(key=lambda q: (DIFF_ORDER.get(q.difficulty, 9), q.key))
    return qs


def volume_map() -> dict[str, int]:
    r"""一次扫出 `key → 卷号` 的映射。

    不要每道题都去读卷文件找 key——那是 O(全库) 的开销，
    「一道题写一次盘」会因此变成几秒一道。
    """
    m: dict[str, int] = {}
    for i, p in enumerate(store.existing_volumes(), start=1):
        for k in re.findall(r'"key":\s*"([^"]+)"', p.read_text(encoding="utf-8")):
            m[k] = i
    return m


def solve_one(q: Question, vmap: dict[str, int]) -> tuple[bool, str]:
    r"""解一道题并**立刻写盘**。返回 (是否成功, 说明)。

    用户的要求是「完成一个写一个」：每解完一道就落盘，
    中途断电或崩了也不会丢掉已经解出来的。
    """
    try:
        raw = call_model(build_prompt(q))
    except urllib.error.URLError as e:
        return False, "模型连不上：%s" % e
    except Exception as e:
        _bump_attempts(q)
        return False, "调用失败：%s: %s" % (type(e).__name__, e)

    ans, sol = parse_reply(raw)
    ans = clean_answer(q, ans)
    if not sol:
        # 连解析都没吐出来。**被截断**（`finish_reason=length`，思考把额度烧光）
        # 和**没按格式**（`stop`）是两回事，所以把两者都写进说明里。
        info = LAST_CALL
        _bump_attempts(q, raw=raw)
        return False, ("模型没按格式回（取不到 <解析>；正文 %d 字，思考 %d 字，"
                       "finish=%s，completion=%s tokens）"
                       % (len(raw), info.get("reasoning", 0),
                          info.get("finish_reason") or "?",
                          (info.get("usage") or {}).get("completion_tokens", "?")))

    # **题型不再拦路。** 答案形态和题型对不上时只记提示，照样入库——
    # 「先求解，题型之后按答案反推着改」（用户明确要求）。
    hint = answer_hint(q, ans)

    # **重新读一遍当前库**——保证不覆盖别的进程刚写的内容
    qs = store.load_all()
    tgt = next((x for x in qs if x.key == q.key), None)
    if tgt is None:
        return False, "题不在库里了"
    # 失败会留痕。**同一道题连续失败 3 次就不再试**——
    # 否则每次重启都从它开始，永远卡在第一道。
    tgt.meta["solve_attempts"] = int(tgt.meta.get("solve_attempts") or 0) + 1
    tgt.answer = ans
    tgt.solution = sol
    tgt.meta["solved_by"] = MODEL
    tgt.meta["solved_at"] = time.strftime("%Y-%m-%d %H:%M")
    if hint:
        tgt.meta["solve_hint"] = hint          # 界面会标出来，人工复核
    else:
        tgt.meta.pop("solve_hint", None)
    warn = consistency_warn(q, ans, sol)
    if warn:
        tgt.meta["solve_warn"] = warn        # 界面会标黄，人工复核
    else:
        tgt.meta.pop("solve_warn", None)

    # ⚠️ **必须过一遍 ENTRY 规范**：答案要写进 `\paren[…]` / `\fillin[…]`，
    # 否则卷面上不出现作答括号、答案也没地方显示。
    # 求解这条路径绕过了 `ingest`，规则不会自动跑——实测漏了 4 道。
    norm.normalize(tgt, norm.ENTRY)

    # **只重写它所在的那一卷**：一道一写，但不为一道题重写整库
    vol = vmap.get(q.key, 1)
    store.rewrite_volume(vol, [x for x in qs if vmap.get(x.key, 1) == vol])
    return True, "答案=%s  解析 %d 字%s%s" % (
        ans or "（空）", len(sol),
        "  ⚠ " + warn if warn else "",
        "  ? " + hint if hint else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="模拟题逐题求解（本地大模型）")
    ap.add_argument("--limit", type=int, default=0, help="最多解几道，0=不限")
    ap.add_argument("--difficulty", default="",
                    help="只要这一档，如「简单题」。留空=易→难全做。"
                         "本地模型只能串行，一次做一档更可控")
    ap.add_argument("--check", action="store_true", help="只报状态，不解")
    a = ap.parse_args()

    todo = pending(a.difficulty)
    from collections import Counter as _C
    cnt = _C(q.difficulty or "未标" for q in todo)
    print("待求解的模拟题：%d 道   %s" % (
        len(todo), "  ".join("%s %d" % (k, cnt[k])
                             for k in ("简单题", "中档题", "难题", "未标") if cnt[k])))
    if a.check:
        try:
            call_model("回一个字：好", timeout=120)
            print("模型连通 ✓  %s" % MODEL)
        except Exception as e:
            print("模型不通 ✗  %s" % e)
        return 0
    if not todo:
        print("没有要解的题了")
        return 0

    if a.limit:
        todo = todo[:a.limit]

    vmap = volume_map()
    print("卷映射：%d 个 key" % len(vmap))
    ok = fail = 0
    t0 = time.time()
    for i, q in enumerate(todo, 1):
        t = time.time()
        good, msg = solve_one(q, vmap)
        el = time.time() - t
        line = "[%d/%d] %s  %.0fs  %s" % (i, len(todo), q.key.split("/", 1)[-1], el, msg)
        print(line, flush=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        ok += good
        fail += not good
        if i % 10 == 0:
            print("   —— 已解 %d，失败 %d，累计 %.0f 分钟 ——"
                  % (ok, fail, (time.time() - t0) / 60), flush=True)

    print("\n完成：成功 %d，失败 %d，用时 %.1f 分钟" % (ok, fail, (time.time()-t0)/60))
    return 0


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    r"""解析器自检。

    这里的样本**全是实测踩过的坑**，不是编出来的：
    模型忘写 `</解析>` 那一条曾让每道题白算 200 多秒。
    """
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("solve 自检")

    check("完整标签",
          parse_reply("<答案>B</答案>\n<解析>过程</解析>") == ("B", "过程"))
    # 实测：模型开了 <解析> 就一路写到底，忘了收尾（finish_reason=stop）
    check("缺 </解析> 也能取到",
          parse_reply("<答案>B</答案>\n<解析>过程") == ("B", "过程"),
          parse_reply("<答案>B</答案>\n<解析>过程"))
    check("缺 </答案> 时不被 <解析> 吞掉",
          parse_reply("<答案>B\n<解析>过程</解析>") == ("B", "过程"),
          parse_reply("<答案>B\n<解析>过程</解析>"))
    check("两个闭合标签都缺",
          parse_reply("<答案>B\n<解析>过程") == ("B", "过程"))
    check("前后有多余的话不影响",
          parse_reply("前言<答案>ACD</答案>中间<解析>过程</解析>后记") == ("ACD", "过程"))
    check("答案里带换行与数学",
          parse_reply("<答案>\n$\\frac{1}{2}$\n</答案>\n<解析>x</解析>")
          == ("$\\frac{1}{2}$", "x"))
    # 只有答案没有解析：答案要留下来，解析留空（题目仍算没解完，会再试）
    check("只有答案时答案不丢", parse_reply("<答案>B</答案>") == ("B", ""))
    check("什么都没有就都返回空", parse_reply("我觉得选 B") == ("", ""))
    check("空串不炸", parse_reply("") == ("", ""))

    # 答案形态与题型对不上 → 只提示，不拦（用户要求「求解不受题型约束」）
    q1 = Question(key="t/1", type="single_choice", stem="x")
    check("单选答出多字母仍保留", clean_answer(q1, "ACD") == "ACD")
    check("单选多字母给提示", bool(answer_hint(q1, "ACD")))
    check("单选单字母无提示", not answer_hint(q1, "B"))
    q2 = Question(key="t/2", type="multi_choice", stem="x")
    check("多选答出单字母给提示", bool(answer_hint(q2, "B")))
    check("多选多字母无提示", not answer_hint(q2, "ABD"))
    check("没给出答案要给提示", bool(answer_hint(q1, "")))

    print("solve 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
