#!/usr/bin/env python3
r"""逐题审阅 · 落账（**只落终审放行的条目**）。

`题库审阅合并.py` 是「批次里所有判错的都放进来」，本脚本换成
「**只有 `终审.jsonl` 里我逐条重算过、结论为 pass 的**才落账」，并且：

* `终审.jsonl` 里同一题记多次时**以最后一次为准**（我改判过 #19，靠这条收口）；
* `终审.jsonl` 结论为 `reject` 的一律不落（agent 判错、题库本来就对）；
* `终审替换.jsonl` 里我重写的 `set` **覆盖** agent 的 `fix`
  （agent 有 4 条替换稿是纯文本，裸下划线/无 `$`，直接写进库会把 TeX 排坏）；
* 台账里已有账的题跳过，不重复落。

改答案时题干 `\paren[…]` / `\fillin[…]` 同步改（与 `合并.py` 同一口径：
ENTRY 期规则只在录入时同步过一次，只改字段的话卷面仍印旧答案）。

    python3 脚本/题库审阅落账.py            # 干跑
    python3 脚本/题库审阅落账.py --yes      # 落账 + 跑 fixups
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import latex_ir, store                           # noqa: E402
from amti.paths import ROOT as RROOT                     # noqa: E402

DIR = RROOT / "数据" / "题库审阅"
LEDGER = RROOT / "数据" / "订正台账.json"


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


_SLOT_CMD = re.compile(r"\\(?:paren|fillin)(?![a-zA-Z])\s*(?=\[)")


def set_blank(stem: str, ans: str) -> str:
    r"""把题干里**最后一个**作答位的空填成答案（\paren 与 \fillin 两种写法）。

    🔴 早先用 `\\(?:paren|fillin)\s*\[[^\]]*\]` 自己扫槽位，遇到**答案里带 `]`**
       就当场截断：`$[0,\frac{\pi}{4}]$` 被当成"槽在 `\frac{\pi}{4}` 处结束"，
       替换完剩一截 `$]` 挂在正文里 → `$` 变奇数、题干被写坏。
       槽位的真相只有 `latex_ir` 懂（AGENTS.md：LaTeX 解析只此一处），
       所以这里改用它认嵌套的 `bracket_arg`。
    """
    hits = list(_SLOT_CMD.finditer(stem))
    if not hits:
        return stem
    m = hits[-1]
    j = m.end()                                   # 指向 '['
    val, end = latex_ir.bracket_arg(stem, j)
    if val is None:                               # 配不平就不动（读不准别改）
        return stem
    return stem[:j] + "[" + ans + "]" + stem[end:]


# agent 改题干时，**删掉的东西**必须一眼看得出没丢正文。
# 强噪声标记：出现它才允许这一整段被删。
_JUNK_MARK = re.compile(
    r"第\s*\d+\s*页|共\s*\d+\s*页|参考答案|答案与?及?解析|解答题|选择题|填空题|单选题"
    r"|本题共|本大题共|小题|满分|每小题|解答应写出|文字说明|证明过程|演算步骤|评分标准"
    r"|考试时间|内装订线|不．要．答．题|[一二三四五六七八九十][、.．]\s*(?:单项选择|多选|选择|填空|解答)")
# 纯噪声片段允许出现的字符：噪声词表里的汉字 + 标点 + 英数。
# ⚠️ **`$` 不在表里**——所以任何含数学式的片段都会被判成"不像噪声"而挡下，
#    这一条是整个护栏的支点。
_JUNK_CHARS = set(
    "数学文科理科试题试卷卷解答选择填空单双项参考答案与解析第页共本题大小分满分每小题"
    "时间内装订线不要答题应写出文字说明证明过程或演算步骤评分标准考总钟长度组"
    "一二三四五六七八九十、.．：:；;，,。（）()【】[]{}~-–—_ *#\n\t "
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def _blank_slots(s: str) -> str:
    r"""把 `\fillin[…]`／`\paren[…]` 的**参数值抹掉**再比对。

    不加这一步，护栏会把「槽里的旧答案 C 换成新值 $10$」当成"删掉了正文 C"——
    而那正是本次要改的东西。槽位变化不该算内容损失。
    """
    return re.sub(r"\\(?:paren|fillin)(?![a-zA-Z])\s*\[[^\]]*\]", r"\\slot[<>]", s)


def _is_junk_frag(frag: str) -> bool:
    if not _JUNK_MARK.search(frag):
        return False
    return all(ch in _JUNK_CHARS for ch in frag)


def _stem_guard(old: str, new: str) -> str:
    r"""返回拒绝理由（空串 = 放行）。**改坏了比不改更糟**，所以宁可挡下来看。"""
    if new.count("$") % 2:
        return "`$` 不成对"
    g_ref = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}")
    lost = set(g_ref.findall(old)) - set(g_ref.findall(new))
    if lost:
        return "丢了配图引用 " + "、".join(sorted(lost))
    if re.search(r"\\(?:paren|fillin)(?![a-zA-Z])\s*\[", old) \
            and not re.search(r"\\(?:paren|fillin)(?![a-zA-Z])\s*\[", new):
        return "作答位槽被删掉了"
    sm = difflib.SequenceMatcher(None, _blank_slots(old), _blank_slots(new), autojunk=False)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag not in ("delete", "replace"):
            continue
        cut = _blank_slots(old)[i1:i2].strip()
        if len(cut) < 8:                   # 短片段：换词、改字母，不是丢正文
            continue
        if not _is_junk_frag(cut):
            return f"删掉了不像噪声的内容「{cut[:44]}」"
    return ""


# ⚠️ **人工背书**的题干改动：护栏按"含 `$` 就不像噪声"一律挡，但有一类恰恰是
#    **卷面上的汉字被 OCR 成了数学式**——删掉它才是还原正文。这种我逐条回原卷核过，
#    所以开一个显式名单绕过护栏，而不是去放宽护栏（放宽会连带放过真的丢正文）。
#    每条都要写清凭什么，落账时会打「⚠️ 人工背书」字样，便于事后追查。
MANUAL_STEM_OK = {
    "模拟题/江苏省扬州市2025-2026学年高三上学期11月期中考试（含） - 副本#13":
        "「写出$\\vec{a}$个同时具有…」不成句；回源 scan p003/p015 卷面作「写出一个」，"
        "$\\vec{a}$ 是「一」被 OCR 成向量字母。删它=还原正文",
}


def _guard_selftest() -> int:
    r"""护栏自己的账：**必须既能放行真订正、又能挡下真丢正文**。

    只测"该放的放"会把护栏写成一台橡皮图章——所以阳性对照（该挡的）比阴性更重要。
    """
    bad = 0

    def ck(name, cond, extra=""):
        nonlocal bad
        if not cond:
            bad += 1
            print("  ✗ %s  %s" % (name, extra))
        else:
            print("  ✓ %s" % name)

    # ── 该放行 ──
    ck("槽里旧答案换成新值不算丢内容",
       _stem_guard("系数为\\fillin[C]。", "系数为\\fillin[$10$]。") == "")
    ck("删整行「四、解答题…」说明放行",
       _stem_guard("求 $x$。\n\n四、解答题：本题共5小题，共77分。解答应写出文字说明、"
                   "证明过程或演算步骤。", "求 $x$。") == "")
    ck("删「数学试题第 2 页 (共 4 页)」放行",
       _stem_guard("求 $x$。\n数学试题第 2 页 (共 4 页)\nCS", "求 $x$。") == "")
    ck("短片段换词放行（α→a）",
       _stem_guard("$e^{\\frac{\\alpha}{x}}$", "$e^{\\frac{a}{x}}$") == "")

    # ── 该挡下（阳性对照）──
    ck("删掉真正文必须挡",
       _stem_guard("已知 $f(x)=x^2-2x+3$，求最小值。", "已知 求最小值。") != "",
       _stem_guard("已知 $f(x)=x^2-2x+3$，求最小值。", "已知 求最小值。"))
    ck("删掉配图引用必须挡",
       _stem_guard("如图\\includegraphics{abc.png}，求 $x$。", "如图，求 $x$。") != "")
    ck("把作答位槽整个删掉必须挡",
       _stem_guard("值为\\fillin[C]。", "值为多少。") != "")
    ck("`$` 改得不成对必须挡",
       _stem_guard("则 $x=1$ 成立\\fillin[C]", "则 $x=1 成立\\fillin[1]") != "")

    # ── set_blank：答案里带 `]` 时不能把题干写坏（真踩过：抚顺#14 的 $[0,\frac{\pi}{4}]$）
    #    ⚠️ 这些字面量一律用 r""：写成 "\\\\left" 会在运行时留下两个反斜杠，
    #       测的就不是题干里真实的 `\left[` 了（本条自检第一版就是这么假失败的）。
    for ans in [r"$[0,\frac{\pi}{4}]$", r"$(-2,1)$", r"$\sqrt{2}$", "25"]:
        s = r"则取值范围为 \fillin[B]。"
        r_ = set_blank(s, ans)
        ck(f"set_blank 填 {ans}",
           latex_ir.fillin_answers(r_) == [ans] and r_.count("$") % 2 == 0, repr(r_))
    _lb = r"$\left[700,4900\right)$"
    _rr = set_blank(r"范围为 \fillin[C]。", _lb)
    ck("set_blank 认嵌套：\\left[…\\right) 这种定界符写法",
       latex_ir.fillin_answers(_rr) == [_lb], repr(_rr))
    print("护栏自检 %s（%d 项失败）" % ("通过" if not bad else "未通过", bad))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--guard-selftest", action="store_true")
    a = ap.parse_args()
    if a.guard_selftest:
        return _guard_selftest()

    # 终审结论：同一 key 后记的覆盖先记的
    final: dict[str, dict] = {}
    for r in read_jsonl(DIR / "终审.jsonl"):
        final[r["key"]] = r
    override = {r["key"]: r["set"] for r in read_jsonl(DIR / "终审替换.jsonl")}

    claims: dict[str, dict] = {}
    for p in sorted((DIR / "批次").glob("*.jsonl")) + sorted((DIR / "批次").glob("*-待核.hold")):
        for r in read_jsonl(p):
            if r.get("verdict") == "错" and r.get("key"):
                claims.setdefault(r["key"], r)

    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    idx = {p["key"]: i for i, p in enumerate(led["patches"])}
    by_key = {q.key: q for q in store.load_cached()}

    new, skip, refused = [], [], []
    for key, j in final.items():
        if j["result"] != "pass":
            refused.append(key)
            continue
        c = claims.get(key)
        if c is None:
            skip.append(key + "（批次里找不到原始判定）")
            continue
        q = by_key.get(key)
        if q is None:
            skip.append(key + "（题库里没有）")
            continue
        # ⚠️ 我的替换稿是**逐字段覆盖**，不是整条顶掉 agent 的 fix。
        #    写成 `override or fix` 时，福州#4 的 `answer:"C"` 被只含 solution 的
        #    替换稿顶没了——答案栏留在 A、新解析却写「故选 C」，机检 A4 当场抓到。
        se = dict(c.get("fix") or {})
        se.update((override.get(key) or {}))
        se.pop("points", None)          # 考点不走 fixups
        se.pop("difficulty", None)      # 难度建议单独走，别混在内容订正里
        st, out = {}, {}
        # 题干：agent 除了填答案，常常还得**修题干本身**（青岛#14 丢了参数 a、
        # 抚顺#13 把 a 认成 α、厦门一中#14 丢了下标 x_1、还有几道题干尾巴上
        # 粘着「四、解答题…」）。早先这里只拿 `set_blank(现题干, 新答案)`，
        # 等于把 agent 改好的题干整条扔掉——只填了槽，正文还是坏的。
        base = q.stem or ""
        cand = (se.get("stem") or "").strip()
        if cand and cand != (q.stem or "").strip():
            bad = _stem_guard(q.stem or "", cand)
            if bad and key in MANUAL_STEM_OK:
                print(f"  ⚠️ 人工背书放行 {key}（护栏本挡：{bad}）依据：{MANUAL_STEM_OK[key]}")
                bad = ""
            if bad:
                skip.append(f"{key}（agent 题干被护栏挡下：{bad}）")
                continue
            base = cand
        if se.get("answer") and se["answer"].strip() != (q.answer or "").strip():
            out["answer"] = se["answer"].strip()
            st["answer"] = q.answer
            ns = set_blank(base, out["answer"])
            if ns != (q.stem or ""):
                out["stem"] = ns
                st["stem"] = q.stem
        elif base != (q.stem or ""):
            out["stem"] = base
            st["stem"] = q.stem
        if se.get("solution") and se["solution"].strip() != (q.solution or "").strip():
            out["solution"] = se["solution"]
            st["solution"] = q.solution
        # 选项也能补：山东#7 录入时把 D 整个丢了，只改答案栏会指向不存在的选项。
        # ⚠️ 两边形状不一样，别写错：`expect.options` 是**文字子串列表**
        #    （fixups 的漂移护栏按「每个子串能在某个选项里找到」判），
        #    `set.options` 才是 [[标签, 文字], …]。写成对会当场 AttributeError。
        if se.get("options"):
            now = [[o.label, o.text] for o in q.options]
            if [t for _l, t in now] != [t for _l, t in se["options"]]:
                out["options"] = se["options"]
                st["options"] = [t for _l, t in now]
        if not out:
            skip.append(key + "（现值已与订正值相同）")
            continue
        new.append({"key": key,
                    "why": (j.get("note") or c.get("problem") or "终审放行")[:200],
                    "src": c.get("proof") or "终审者独立复算",
                    "expect": st, "set": out})

    print(f"终审放行 {sum(1 for j in final.values() if j['result'] == 'pass')} 条："
          f"要落 {len(new)} 条、跳过 {len(skip)} 条、判否不落 {len(refused)} 条")
    for e in new:
        print(f"  · {e['key']}  →  {list(e['set'])}")
    for s in skip:
        print(f"  ⏭ 跳过 {s}")
    for s in refused:
        print(f"  ✋ 判否 {s}")
    if not a.yes:
        print("（干跑。加 --yes 落账）")
        return 0

    upd = [e for e in new if e["key"] in idx]
    fresh = [e for e in new if e["key"] not in idx]
    led["patches"].extend(fresh)
    for e in upd:                       # 台账里已有账的**就地补字段**，不留两条互相打架的账
        led["patches"][idx[e["key"]]] = e
    LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=1), encoding="utf-8")

    # 游标也要记：`合并.py` 只 glob `*.jsonl`，`*-待核.hold` 的判定进不去，
    # 而本脚本落完账不写游标的话，`题库审阅取题.py` 会把同一批题**再发一遍**。
    CURSOR = DIR / "逐题进度.json"
    cur = json.loads(CURSOR.read_text(encoding="utf-8")) if CURSOR.exists() else {"判定": {}}
    mark = {"pass": "错", "reject": "ok"}          # 游标沿用批次那套词：pass＝确实错、reject＝题库本来对
    for key, j in final.items():
        if j["result"] in mark:
            cur["判定"][key] = mark[j["result"]]
    cur["审到"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    cur["keys"] = list(cur["判定"])
    CURSOR.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已写台账：新增 {len(fresh)} 条、补写 {len(upd)} 条（现共 {len(led['patches'])} 条）；"
          f"游标 {len(cur['判定'])} 道。接下来：python3 -m amti.fixups --yes && python3 amti.py accept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
