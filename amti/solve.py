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

from .paths import ROOT
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


def call_model(prompt: str, *, timeout: int = 600,
               system: str = SYSTEM, reasoning_effort: str = "",
               max_tokens: int = MAX_TOKENS) -> str:
    r"""问模型一次，返回正文。

    ⚠️ **`max_tokens` 必须给足。** 这是推理模型：它先在 `reasoning_content`
    里想，想完才写正文，而 `max_tokens` **把两者算在一起**。
    实测 3000 时，难题上模型要想 200 多秒，额度在思考阶段就烧光了，
    正文返回**空字符串**——白等一趟，还查不出原因。
    所以这里给 8000，并在失败信息里带上 `finish_reason`：
    被截断（`length`）和没按格式（`stop`）是两回事，得能分开看。

    `reasoning_effort="none"` 能**关掉思考**（LM Studio 认这个字段）——实测同一道题
    从 361 秒 / 思考 5934 字 / 正文被截断，变成 **8 秒 / 思考 0 字 / 正文正常**。
    ⚠️ 注意 `/no_think`（提示词软开关）和 `chat_template_kwargs.enable_thinking=false`
    **在这个模型上都无效**（照样想 7000 字），别用那两个。
    只给"纯读取"的任务关（如从现成解析里取答案）；**写解析必须留着思考**。
    """
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    body = json.dumps(payload).encode("utf-8")
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
    ap.add_argument("--audit", action="store_true",
                    help="逐题审题模式：从后往前，一道一道交本地模型"
                         "（补答案/补解析/修题干）")
    ap.add_argument("--fill-answer", action="store_true",
                    help="补缺②：有解析、没答案的客观题——读现成解析把答案补上")
    ap.add_argument("--fill-solution", action="store_true",
                    help="补缺①：有答案、没解析的题——本地模型写解析")
    ap.add_argument("--reset-fill", action="store_true",
                    help="补缺：清掉该任务的进度，从头跑")
    ap.add_argument("--only-missing", action="store_true",
                    help="审题时只挑「缺答案或缺解析」的题")
    ap.add_argument("--reset", action="store_true",
                    help="审题：清掉进度，从最后一道重新开始")
    a = ap.parse_args()

    if a.audit:
        return run_audit(limit=a.limit, only_missing=a.only_missing,
                         reset=a.reset, check=a.check)
    if a.fill_answer or a.fill_solution:
        return run_fill("ans" if a.fill_answer else "sol", limit=a.limit,
                        reset=a.reset_fill, check=a.check)

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


# ══════════════════════════════════════════════════════════════
#  逐题审题：**从后往前**，一题一问、一题一写（本地大模型）
# ══════════════════════════════════════════════════════════════
#
# 用户的要求：把题库里的题**一道一道**交给本地模型审——
#   · 没有解析就补解析、没有答案就补答案；
#   · 题干有问题就按模型给的修正稿修（修稿要过规范才写）；
#   · 一题一次、从后往前、不怕慢（这是个长期活）。
#
# 两条安全线（都**不是**"替模型判断"，只是防止把库写坏）：
#   1. **已有的答案/解析不覆盖**——用户说的是"没有就补上"；
#      模型若与库里的答案冲突，只记进备注，交给人看。
#   2. 题干修正稿必须过 `normalize` + `conform`，且模型要同时在 `<备注>`
#      里说明题干确实有问题——两道门都过才动题干。
# 模型回了什么、改了什么，逐条落到 `数据/录题/大模型审题.jsonl`，便于复核。

AUDIT_SYSTEM = (
    "你是高中数学老师，正在**一道一道审题**。给你一道题和它现在的状态，你要：\n"
    "1. 判断题干本身有没有问题（条件矛盾、缺条件、缺图、抄错符号、设问不完整…）；\n"
    "2. 给出答案；\n"
    "3. 给出完整、简洁的解析。\n\n"
    "严格按下面四个标签回答，不要有别的内容：\n\n"
    "<题干>\n"
    "题干**确实有问题**时，这里写修正后的**完整题干**（保留原有的 LaTeX 写法与配图引用）；"
    "题干没问题就写：无\n"
    "</题干>\n"
    "<答案>\n"
    "（选择题只写字母，如 A 或 ACD；填空题只写结果；解答题写最终结论）\n"
    "</答案>\n"
    "<解析>\n"
    "（可以含 LaTeX 公式，行内用 $…$，行间用 \\[ … \\]）\n"
    "</解析>\n"
    "<备注>\n"
    "（一句话：题干有什么问题；没问题就写：无）\n"
    "</备注>\n\n"
    "注意：\n"
    "- 库里已经有的答案/解析**不要改写**；若与你的结论明显冲突，写在备注里。\n"
    "- LaTeX 里不要写中文，中文放公式外面或用 \\text{} 包起来。\n"
    "- 不要用 \\begin{enumerate}，小问直接写「(1)」「(2)」。\n"
    "- 解析要能让人看懂，但别啰嗦。"
)

AUDIT_DIR = ROOT / "数据" / "录题"
AUDIT_CURSOR = AUDIT_DIR / "大模型审题进度.json"
AUDIT_JSONL = AUDIT_DIR / "大模型审题.jsonl"
_NONE_WORDS = {"无", "无。", "なし", "-", "—", "none", "None", "（无）", "(无)"}


def build_audit_prompt(q: Question) -> str:
    r"""把一道题（连同它现在的状态）交给模型。"""
    parts = ["题型：%s" % q.type, "题干：%s" % q.stem]
    if q.options:
        parts.append("选项：")
        for o in q.options:
            parts.append("  %s. %s" % (o.label, o.text or "（图片选项）"))
    parts.append("现在的状态：答案%s；解析%s" % (
        ("已有：%s（不要改写）" % q.answer) if q.answer.strip() else "缺失（请补）",
        "已有（不要重写）" if q.solution.strip() else "缺失（请补）"))
    return "\n".join(parts)


def parse_audit_reply(text: str) -> tuple[str, str, str, str]:
    r"""(修正后的题干, 答案, 解析, 备注)。取不到就是空串，**不猜**。"""
    stem = _block(text, "题干")
    if stem.strip() in _NONE_WORDS:
        stem = ""
    note = _block(text, "备注")
    if note.strip() in _NONE_WORDS:
        note = ""
    return stem, _block(text, "答案"), _block(text, "解析"), note


def _stem_fix_ok(q: Question, new_stem: str) -> tuple[bool, str]:
    r"""题干修正稿能不能用：先过规范，再要求它"看得出是同一道题"。

    只做**防写坏**的检查，不代替模型判断：
      · 太短（<8 字）直接不要；
      · 过 `normalize` + `conform`，有一条不合规就不换；
      · 原来的配图引用必须还在（模型重写题干时很容易把图弄丢）。
    """
    import copy
    from . import conform
    if len(new_stem.strip()) < 8:
        return False, "修正稿太短"
    old_imgs = set(re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}",
                              q.stem or ""))
    new_imgs = set(re.findall(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}",
                              new_stem))
    lost = old_imgs - new_imgs
    if lost:
        return False, "修正稿把配图弄丢了：%s" % "、".join(sorted(lost)[:2])
    probe = copy.deepcopy(q)
    probe.stem = new_stem
    try:
        norm.normalize(probe, norm.ENTRY)
        viol = conform.run([probe])
    except Exception as e:                       # 规范化炸了也不换
        return False, "过不了规范：%s" % e
    if viol:
        return False, "过不了规范：%s（%s）" % (viol[0]["why"], viol[0]["check"])
    return True, ""


def audit_one(q: Question, vmap: dict[str, int]) -> tuple[bool, str, dict]:
    r"""审一道题并**立刻写盘**。返回 (是否成功, 说明, 记录)。

    写库规则（严格按用户要求）：
      · 答案栏是空的 → 填模型给的答案；
      · 解析栏是空的 → 填模型给的解析；
      · 题干：模型说有问题、且给了修正稿、且修正稿过规范 → 换；
      · 库里已有的答案/解析**一个字都不动**（冲突只记备注）。
    """
    t0 = time.time()
    try:
        raw = call_model(build_audit_prompt(q), system=AUDIT_SYSTEM)
    except urllib.error.URLError as e:
        return False, "模型连不上：%s" % e, {}
    except Exception as e:
        _bump_attempts(q)
        return False, "调用失败：%s: %s" % (type(e).__name__, e), {}

    stem_fix, ans_raw, sol, note = parse_audit_reply(raw)
    ans = clean_answer(q, ans_raw)

    qs = store.load_all()
    tgt = next((x for x in qs if x.key == q.key), None)
    if tgt is None:
        return False, "题不在库里了", {}

    actions: list[str] = []
    conflict = ""
    if ans and not tgt.answer.strip():
        tgt.answer = ans
        actions.append("补答案=%s" % ans)
    elif ans and tgt.answer.strip() and ans != tgt.answer.strip():
        conflict = "库里答案 %s / 模型答案 %s" % (tgt.answer.strip(), ans)
    if sol and not tgt.solution.strip():
        tgt.solution = sol
        actions.append("补解析(%d字)" % len(sol))

    stem_note = ""
    if stem_fix and note:
        ok, why = _stem_fix_ok(tgt, stem_fix)
        if ok:
            tgt.stem = stem_fix
            actions.append("修题干")
        else:
            stem_note = "题干修正稿没用上：%s" % why

    if actions or conflict or note or stem_note:
        tgt.meta["audit_at"] = time.strftime("%Y-%m-%d %H:%M")
        tgt.meta["audit_model"] = MODEL
        # 补答案/补解析也算"本地模型解出来的"——这样 `amti.py diff` 会把它
        # 归到「求解写入」那一栏（本来就该如此），不会误报成"存量被偷改"。
        if any(("补答案" in a) or ("补解析" in a) for a in actions):
            tgt.meta["solved_by"] = MODEL
            tgt.meta["solved_at"] = time.strftime("%Y-%m-%d %H:%M")
        if note:
            tgt.meta["audit_note"] = note
        if conflict:
            tgt.meta["audit_conflict"] = conflict          # 界面标黄，人工复核
        if stem_note:
            tgt.meta["audit_warn"] = stem_note
        if not (tgt.answer or "").strip() or not (tgt.solution or "").strip():
            tgt.meta["audit_incomplete"] = True            # 还是缺东西，下次再说
        else:
            tgt.meta.pop("audit_incomplete", None)
    else:
        tgt.meta["audit_at"] = time.strftime("%Y-%m-%d %H:%M")
        tgt.meta["audit_model"] = MODEL
        tgt.meta.pop("audit_note", None)
        tgt.meta.pop("audit_conflict", None)
        tgt.meta.pop("audit_warn", None)
        tgt.meta.pop("audit_incomplete", None)

    norm.normalize(tgt, norm.ENTRY)
    vol = vmap.get(q.key, 1)
    store.rewrite_volume(vol, [x for x in qs if vmap.get(x.key, 1) == vol])

    rec = {"key": q.key, "用时秒": round(time.time() - t0),
           "动作": actions, "备注": note, "冲突": conflict, "题干提醒": stem_note,
           "模型": MODEL}
    if note or stem_note or conflict or actions:
        rec["原始回复"] = raw[-4000:]
    msg = ("；".join(actions) if actions else "无需改动") + \
        ("  ⚠ " + conflict if conflict else "") + \
        ("  ✎ " + note if note else "")
    return True, msg, rec


def _load_cursor(path: Path = AUDIT_CURSOR, key: str = "") -> dict:
    r"""读进度。`key` 给了就从那份进度文件里取子字典（补缺任务一个文件放两条任务）。"""
    if path.exists():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return (d.get(key) or {}) if key else d
        except Exception:
            log.warning("进度文件坏了，从头开始", exc_info=True)
    return {}


def _save_cursor(d: dict, path: Path = AUDIT_CURSOR, key: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if key:                                  # 子字典：先读回整份，再替换这一条
        all_: dict = {}
        if path.exists():
            try:
                all_ = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                all_ = {}
        all_[key] = d
        path.write_text(json.dumps(all_, ensure_ascii=False, indent=1), encoding="utf-8")
        return
    path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def audit_queue(cursor: dict, *, only_missing: bool = False) -> list[Question]:
    r"""**从后往前**排好的审题队列。

    起点用 key 锚定（不用下标）——库在跑的过程中会变，下标会漂。
    """
    qs = list(reversed(store.load_all()))
    if only_missing:
        qs = [q for q in qs if not (q.answer or "").strip()
              or not (q.solution or "").strip()]
    start = (cursor or {}).get("下一个key") or ""
    if start:
        idx = next((i for i, q in enumerate(qs) if q.key == start), None)
        if idx is not None:
            qs = qs[idx:]
    return qs


def run_audit(*, limit: int = 0, only_missing: bool = False,
              reset: bool = False, check: bool = False) -> int:
    r"""审题主循环：一题一问、一题一写、随时可停可续。"""
    if reset and AUDIT_CURSOR.exists():
        AUDIT_CURSOR.unlink()
    cursor = _load_cursor()
    todo = audit_queue(cursor, only_missing=only_missing)
    print("审题队列：%d 道（从后往前%s）；上次停在 %s"
          % (len(todo), "，只审缺答案/解析的" if only_missing else "",
             cursor.get("下一个key") or "（还没开始）"))
    if check:
        try:
            call_model("回一个字：好", timeout=120, system=AUDIT_SYSTEM)
            print("模型连通 ✓  %s" % MODEL)
        except Exception as e:
            print("模型不通 ✗  %s" % e)
        return 0
    if not todo:
        print("审完了")
        return 0
    if limit:
        todo = todo[:limit]

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    vmap = volume_map()
    n_ans = n_sol = n_stem = n_note = n_bad = 0
    t0 = time.time()
    for i, q in enumerate(todo, 1):
        try:
            good, msg, rec = audit_one(q, vmap)
        except KeyboardInterrupt:
            print("\n被中断，进度已存", flush=True)
            raise
        el = time.time() - t0
        if good:
            acts = rec.get("动作", [])
            n_ans += any("补答案" in a for a in acts)
            n_sol += any("补解析" in a for a in acts)
            n_stem += any(a == "修题干" for a in acts)
            n_note += bool(rec.get("备注"))
        else:
            n_bad += 1
        line = "[%d/%d] %s  %s" % (i, len(todo), q.key, msg)
        print(line, flush=True)
        with (AUDIT_JSONL).open("a", encoding="utf-8") as f:
            f.write(json.dumps({**rec, "说明": msg, "成功": good},
                               ensure_ascii=False) + "\n")
        # 进度锚点：**记下一道的 key**，这样停了也能从断点接上
        nxt = todo[i].key if i < len(todo) else ""
        _save_cursor({"下一个key": nxt, "已审": cursor.get("已审", 0) + i,
                      "补答案": n_ans, "补解析": n_sol, "修题干": n_stem,
                      "有备注": n_note, "失败": n_bad,
                      "最后更新": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "最后一道": q.key})
        if i % 5 == 0:
            print("   —— 已审 %d：补答案 %d、补解析 %d、修题干 %d、有备注 %d、失败 %d"
                  "，用时 %.1f 分钟 ——"
                  % (i, n_ans, n_sol, n_stem, n_note, n_bad, el / 60), flush=True)
    print("\n本轮完成：%d 道，用时 %.1f 分钟" % (len(todo), (time.time() - t0) / 60))
    return 0


# ══════════════════════════════════════════════════════════════
#  补缺：只补"少了的那一样"（本地大模型，一题一问、一题一写）
# ══════════════════════════════════════════════════════════════
#
# 用户的要求：
#   ② `ans` 有解析、没答案的**客观题** → **读现成解析，把答案补上**（不重写解析）；
#   ① `sol` 有答案、没解析的题 → 写解析（"先慢慢做着"）。
#
# 一题一问、写完立刻落盘、可断点续跑（进度按 key 锚定）；**只动缺的那一栏**，
# 另一栏一个字不改——这是这两条任务的安全边界。

FILL_CURSOR = AUDIT_DIR / "补缺进度.json"
FILL_JSONL = AUDIT_DIR / "补缺.jsonl"

FILL_ANS_SYSTEM = (
    "你是高中数学老师。给你一道题**和它已有的解析**，你只做一件事："
    "从解析里读出这道题的答案。\n\n"
    "严格按格式回答，不要有别的内容：\n"
    "<答案>\n"
    "（选择题只写字母，如 A 或 ACD；填空题只写最终结果，数学式子用 $…$ 括起来）\n"
    "</答案>\n\n"
    "注意：\n"
    "- **不要重写解析**，不要解释过程，不要输出别的标签；\n"
    "- 解析里如果出现多个结论，答案栏只放**这道题最后要的那个结果**。"
)

FILL_SOL_SYSTEM = (
    "你是高中数学老师。给你一道题（**答案已经给出**），你要写出**完整、简洁**的解析，"
    "讲清怎么想、每步为什么。\n\n"
    "严格按格式回答，不要有别的内容：\n"
    "<解析>\n"
    "（可以含 LaTeX 公式，行内用 $…$，行间用 \\[ … \\]）\n"
    "</解析>\n\n"
    "注意：\n"
    "- LaTeX 里不要写中文，中文放公式外面或用 \\text{} 包起来。\n"
    "- 不要用 \\begin{enumerate}，小问直接写「(1)」「(2)」。\n"
    "- 解析要能让人看懂，但别啰嗦。"
)


def fill_todo(kind: str) -> list[Question]:
    r"""待补的题：`ans` = 有解析缺答案（**只取客观题**）；`sol` = 有答案缺解析。

    连败 `MAX_ATTEMPTS` 次的跳过，免得反复卡在同一道。顺序按 key，便于断点续跑。
    """
    out: list[Question] = []
    for q in store.load_all():
        if int(q.meta.get("fill_attempts") or 0) >= MAX_ATTEMPTS:
            continue
        have_a = bool((q.answer or "").strip())
        have_s = bool((q.solution or "").strip())
        if kind == "ans":
            if have_s and not have_a and q.type in ("single_choice", "multi_choice",
                                                    "fill_in_blank"):
                out.append(q)
        elif kind == "sol":
            if have_a and not have_s:
                out.append(q)
    out.sort(key=lambda q: q.key)
    return out


def _fill_prompt(q: Question, kind: str) -> str:
    parts = ["题型：%s" % q.type, "题干：%s" % q.stem]
    if q.options:
        parts.append("选项：")
        for o in q.options:
            parts.append("  %s. %s" % (o.label, o.text or "（图片选项）"))
    if kind == "ans":
        parts.append("已有解析：\n%s" % (q.solution or "").strip())
    else:
        parts.append("已有答案：%s" % (q.answer or "").strip())
    return "\n".join(parts)


def _bump_fill(q: Question, raw: str = "") -> None:
    r"""补缺失败留痕：把 `fill_attempts` 加一。

    ⚠️ **不能复用 `_bump_attempts`**（那记的是 `solve_attempts`）：
    `fill_todo` 的"连败 3 次就跳过"看的是 `fill_attempts`，而失败时却去加
    `solve_attempts` → 这个上限**永远触发不了**，同一道难题每次重跑都白试一遍。
    """
    qs = store.load_all()
    t = next((x for x in qs if x.key == q.key), None)
    if t is None:
        return
    t.meta["fill_attempts"] = int(t.meta.get("fill_attempts") or 0) + 1
    t.meta["fill_error"] = time.strftime("%Y-%m-%d %H:%M")
    if raw:
        t.meta["fill_raw_tail"] = raw[-2000:]
    try:
        store.rewrite_all(qs)
    except Exception:
        log.error("补缺失败留痕写库失败", exc_info=True)


def fill_one(q: Question, vmap: dict[str, int], kind: str) -> tuple[bool, str]:
    r"""补一道题的那一栏并**立刻写盘**。"""
    system = FILL_ANS_SYSTEM if kind == "ans" else FILL_SOL_SYSTEM
    try:
        # 补答案 = 纯读取任务 → 关思考（8 秒 vs 361 秒）；写解析保留思考
        raw = call_model(
            _fill_prompt(q, kind), system=system,
            # 写解析：思考很长，**一道要 400–600 秒**，600 秒超时会被打断（实测）
            timeout=(600 if kind == "ans" else 1800),
            reasoning_effort="none" if kind == "ans" else "",
            # 写解析：**思考动辄 7000+ tokens**，8000 会被思考吃光、正文空着回来
            # （实测 24/35 失败）。16k 上下文下给 12000，装得下思考+正文。
            max_tokens=(MAX_TOKENS if kind == "ans" else 12000))
    except urllib.error.URLError as e:
        return False, "模型连不上：%s" % e
    except Exception as e:
        _bump_fill(q)
        return False, "调用失败：%s: %s" % (type(e).__name__, e)

    # **重新读一遍库**：别覆盖别的进程刚写的内容
    qs = store.load_all()
    tgt = next((x for x in qs if x.key == q.key), None)
    if tgt is None:
        return False, "题不在库里了"

    if kind == "ans":
        ans = clean_answer(tgt, _block(raw, "答案"))
        if not ans:
            _bump_fill(tgt, raw=raw)
            return False, "没读到答案（正文 %d 字，finish=%s）" % (
                len(raw), LAST_CALL.get("finish_reason") or "?")
        if (tgt.answer or "").strip():
            return False, "库里有答案了（%s），不动" % tgt.answer
        tgt.answer = ans
        tgt.meta["filled_answer_by"] = MODEL
        tgt.meta["filled_answer_at"] = time.strftime("%Y-%m-%d %H:%M")
        msg = "补答案=%s" % ans
    else:
        sol = _block(raw, "解析")
        if not sol:
            _bump_fill(tgt, raw=raw)
            return False, "没取到解析（正文 %d 字，finish=%s）" % (
                len(raw), LAST_CALL.get("finish_reason") or "?")
        if (tgt.solution or "").strip():
            return False, "库里有解析了，不动"
        tgt.solution = sol
        tgt.meta["filled_solution_by"] = MODEL
        tgt.meta["filled_solution_at"] = time.strftime("%Y-%m-%d %H:%M")
        msg = "补解析(%d字)" % len(sol)

    tgt.meta["fill_attempts"] = int(tgt.meta.get("fill_attempts") or 0) + 1
    # 答案要写进 `\paren[…]` / `\fillin[…]`（与求解路径同一道规范）
    norm.normalize(tgt, norm.ENTRY)
    vol = vmap.get(q.key, 1)
    store.rewrite_volume(vol, [x for x in qs if vmap.get(x.key, 1) == vol])
    return True, msg


def run_fill(kind: str, *, limit: int = 0, reset: bool = False,
             check: bool = False) -> int:
    r"""补缺主循环：一题一问、一题一写、随时可停可续。"""
    if kind not in ("ans", "sol"):
        print("kind 只能是 ans / sol")
        return 2
    cur = _load_cursor(FILL_CURSOR, kind) if reset is False else {}
    if reset and FILL_CURSOR.exists():
        d = json.loads(FILL_CURSOR.read_text(encoding="utf-8"))
        d.pop(kind, None)
        FILL_CURSOR.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        cur = {}
    todo = fill_todo(kind)
    start = (cur or {}).get("下一个key") or ""
    if start:
        i = next((n for n, q in enumerate(todo) if q.key == start), None)
        if i is not None:
            todo = todo[i:]
    label = "补答案（读现成解析）" if kind == "ans" else "补解析"
    print("任务：%s；待补 %d 道；上次停在 %s" % (label, len(todo), start or "（还没开始）"))
    if check:
        try:
            call_model("回一个字：好", timeout=120,
                       system=FILL_ANS_SYSTEM if kind == "ans" else FILL_SOL_SYSTEM)
            print("模型连通 ✓  %s" % MODEL)
        except Exception as e:
            print("模型不通 ✗  %s" % e)
        return 0
    if not todo:
        print("补完了")
        return 0
    if limit:
        todo = todo[:limit]

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    vmap = volume_map()
    ok = bad = 0
    t0 = time.time()
    for i, q in enumerate(todo, 1):
        t = time.time()
        good, msg = fill_one(q, vmap, kind)
        ok += good
        bad += not good
        # **模型掉线就停**：连不上时继续跑只会一路刷失败（虽然不计入连败次数，
        # 但会把 885 道白跑一遍）。停下来等人把模型起回来，进度还在。
        if not good and msg.startswith("模型连不上"):
            print("✗ %s —— 停下（进度已存，模型起来后重跑本命令即可续上）" % msg,
                  flush=True)
            break
        line = "[%d/%d] %s  %.0fs  %s" % (i, len(todo), q.key, time.time() - t, msg)
        print(line, flush=True)
        with FILL_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"kind": kind, "key": q.key, "ok": good, "说明": msg,
                                "用时秒": round(time.time() - t), "模型": MODEL},
                               ensure_ascii=False) + "\n")
        nxt = todo[i].key if i < len(todo) else ""
        _save_cursor({"下一个key": nxt, "已补": (cur or {}).get("已补", 0) + i,
                      "最后一道": q.key, "成功": ok, "失败": bad,
                      "最后更新": time.strftime("%Y-%m-%d %H:%M:%S")}, FILL_CURSOR, kind)
        if i % 5 == 0:
            print("   —— 已补 %d：成功 %d、失败 %d，用时 %.1f 分钟 ——"
                  % (i, ok, bad, (time.time() - t0) / 60), flush=True)
    print("\n本轮完成：%d 道（成功 %d、失败 %d），用时 %.1f 分钟"
          % (len(todo), ok, bad, (time.time() - t0) / 60))
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

    # ── 审题模式：题干/答案/解析/备注 四段 ──────────────────────────
    # 实测坑：模型大多数时候在 <题干> 里写「无」，那一栏必须当"不动题干"，
    # 不然每道题都会拿「无」去覆盖题干（灾难）。
    check("题干写「无」= 不动题干",
          parse_audit_reply("<题干>无</题干><答案>B</答案><解析>x</解析>"
                            "<备注>无</备注>") == ("", "B", "x", ""))
    check("题干给修正稿时才取",
          parse_audit_reply("<题干>已知 $x>0$，求…</题干><答案>B</答案>"
                            "<解析>x</解析><备注>题干漏了 $x>0$</备注>")
          == ("已知 $x>0$，求…", "B", "x", "题干漏了 $x>0$"))
    check("备注「无」当空", parse_audit_reply("<备注>无</备注>")[3] == "")
    check("审题缺标签不炸", parse_audit_reply("") == ("", "", "", ""))

    # 题干修正稿的防写坏检查
    q3 = Question(key="t/3", type="fill_in_blank", stem="已知 $x$ 的方程为\\fillin[]。")
    check("修正稿太短 → 不换", not _stem_fix_ok(q3, "无")[0])
    q4 = Question(key="t/4", type="single_choice",
                  stem="如图，" + r"\includegraphics[width=0.4\linewidth]{b7124aa7bf01623d.png}" + r" 则 $x=$\paren[A]")
    ok, why = _stem_fix_ok(q4, "换个说法，但没有图")
    check("修正稿丢配图 → 不换", not ok and "配图" in why, why)
    ok2, why2 = _stem_fix_ok(
        q4, r"如图，$\triangle ABC$ 中 $AB=2$，" + "\n\n" +
        r"\includegraphics[width=0.4\linewidth]{b7124aa7bf01623d.png}" + "\n\n" +
        r"则 $x=$\paren[A]")
    check("修正稿保留配图且合规 → 换", ok2, why2)

    # ── 队列：从后往前，且用 key 锚定续跑 ────────────────────────
    qs = store.load_all()
    tail = audit_queue({})
    check("审题队列是倒序", bool(tail) and tail[0].key == qs[-1].key,
          "%s vs %s" % (tail[0].key if tail else "-", qs[-1].key if qs else "-"))
    if len(tail) > 3:
        anchor = {"下一个key": tail[3].key}
        check("按 key 续跑从锚点开始",
              audit_queue(anchor)[0].key == tail[3].key)
    check("锚点不存在时从头来（不报错）",
          audit_queue({"下一个key": "不存在的/钥匙#1"})[0].key == qs[-1].key)

    # ── 补缺：两条任务的取题口径 ────────────────────────────────
    # ② 补答案：**只取客观题**（解答题的答案栏本来就该空着，不能乱补）
    a_todo = fill_todo("ans")
    check("补答案只取客观题",
          all(q.type in ("single_choice", "multi_choice", "fill_in_blank") for q in a_todo))
    check("补答案的题都有解析、没答案",
          all((q.solution or "").strip() and not (q.answer or "").strip() for q in a_todo),
          "%d 道" % len(a_todo))
    # ① 补解析：有答案、没解析
    s_todo = fill_todo("sol")
    check("补解析的题都有答案、没解析",
          all((q.answer or "").strip() and not (q.solution or "").strip() for q in s_todo),
          "%d 道" % len(s_todo))
    check("两条任务不重叠", not ({q.key for q in a_todo} & {q.key for q in s_todo}))

    # 补答案的提示词里必须带上现成解析（否则模型只能重做一遍）
    if a_todo:
        p = _fill_prompt(a_todo[0], "ans")
        check("补答案的提示里有现成解析", "已有解析" in p and a_todo[0].solution[:20] in p)
    if s_todo:
        p2 = _fill_prompt(s_todo[0], "sol")
        check("补解析的提示里有答案", "已有答案" in p2)
    check("kind 只认 ans/sol", run_fill("xx", check=True) == 2)

    print("solve 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
