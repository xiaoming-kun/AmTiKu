r"""DeepSeek 单题校对：答案 / 解法 / 配图建议。**只读，不写库。**

写回仍然走现有的两个入口：`PATCH /questions/{key}`（答案/标签）和
`POST /questions/{key}/solution`（答案/解析）；TikZ 改动走 `/source`，
由用户在看源码后自己确认。这个模块不提供第二套写库路径。
"""
from __future__ import annotations

import re
import time
from copy import deepcopy

from . import aispec, deepseek, latex_blocks as lb, latex_ir, normalize, store


def _clean_sol(s: str) -> str:
    s = str(s or "").strip()
    s = re.sub(r"^```(?:latex|tex|markdown)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s).strip()
    return s[:12000]


def proofread(key: str) -> dict:
    one = store.read_one(str(key or "").strip())
    if one is None:
        raise ValueError("没有这道题：%s" % key)
    q = one[0]
    cfg = deepseek.load()
    if not cfg["api_key"]:
        raise deepseek.AIError("还没填 DeepSeek API Key")
    opts = "\n".join("%s. %s" % (o.label, o.text) for o in (q.options or []))
    pts = "、".join(q.point_titles or []) or "（未标考点）"
    figs = len(q.figures or [])
    prompt = (
        "你是 K12 数学教研员。请校对下面这道**已在题库里**的题，只返回一个 JSON 对象。\n"
        "要求：\n"
        "1. 先独立解题，再判断现有答案是否正确；不要因为现有答案而迁就它；\n"
        "2. 检查解析是否完整、有没有逻辑漏洞/算错/漏范围/漏情况；\n"
        "3. 判断题干是否需要配图；若需要而题中没有图，给出可编译的 TikZ 代码；\n"
        "4. 不确定就给 uncertain，不要硬改。\n"
        "JSON 字段：\n"
        '{"verdict":"pass|fix|uncertain","answer_ok":true|false|null,'
        '"answer":"若答案错/空，给正确最终答案；否则空串",'
        '"solution_issues":["..."],"solution":"需要改时才给完整解析正文",'
        '"figure_issues":["..."],"tikz":"需要补图时才给 tikzpicture 代码",'
        '"notes":["..."]}\n'
        "硬性要求：answer 只写最终答案；solution 只写解析正文（LaTeX，可含 $...$），"
        "不要 Markdown 围栏，不要重复题干；tikz 只写 figure 内容（不要导言区）。\n"
        "如果现有解析里有 \\includegraphics 或 tikzpicture，重写时必须原样保留，"
        "位置尽量不变；配图是正文的一部分，不能删。\n\n"
        "题目信息：\n题型：%s\n考点：%s\n现有配图数：%d\n题干：%s\n%s\n"
        "现有答案：%s\n现有解析：%s\n"
        % (q.type, pts, figs, q.stem.strip()[:4000],
           ("选项：\n" + opts + "\n") if opts else "",
           q.answer.strip() or "（空）", q.solution.strip()[:5000] or "（空）")
    )
    t0 = time.time()
    usage: dict = {}
    raw = deepseek.chat(prompt, system=aispec.system_prompt(),
                        timeout=300, max_tokens=4096, json_mode=True,
                        on_usage=lambda u: usage.update(u or {}))
    d = deepseek.json_obj(raw)
    if not d:
        raise deepseek.AIError("模型没有返回可解析的校对 JSON")
    verdict = str(d.get("verdict") or "").strip()
    if verdict not in ("pass", "fix", "uncertain"):
        verdict = "uncertain"
    ans_ok = d.get("answer_ok")
    if not isinstance(ans_ok, bool):
        ans_ok = None
    issues = d.get("solution_issues")
    fissues = d.get("figure_issues")
    notes = d.get("notes")
    ans = str(d.get("answer") or "").strip()[:200]
    sol = _clean_sol(d.get("solution"))
    # 模型只改文字时很容易把配图命令漏掉；正文是配图的唯一真相，
    # 先补回旧解析里的图，再规范化 / 出 blocks。
    preserved: list[str] = []
    ans, ans_kept = latex_ir.preserve_figures(q.answer, ans)
    sol, sol_kept = latex_ir.preserve_figures(q.solution, sol)
    preserved = list(dict.fromkeys(ans_kept + sol_kept))
    # 预览和写回走同一套规范化：右栏要看到的是**保存后的样子**，
    # 不是模型原样吐出的 LaTeX 串。规范化失败就退回原文，至少能读。
    if ans or sol:
        try:
            t = deepcopy(q)
            if ans:
                t.answer = ans
            if sol:
                t.solution = sol
            normalize.normalize(t, normalize.ENTRY)
            ans = t.answer
            sol = t.solution
        except Exception:                       # noqa: BLE001
            pass
    return {
        "ok": True, "key": q.key,
        "current": {
            "answer": q.answer, "solution": q.solution,
            "points": q.points, "point_titles": q.point_titles,
            "difficulty": q.difficulty, "figures": figs,
        },
        "proposal": {
            "verdict": verdict, "answer_ok": ans_ok,
            "answer": ans,
            "solution": sol,
            "answer_blocks": lb.parse_blocks(ans) if ans else [],
            "solution_blocks": lb.parse_blocks(sol) if sol else [],
            "solution_issues": [str(x)[:300] for x in issues]
                if isinstance(issues, list) else [],
            "figure_issues": [str(x)[:300] for x in fissues]
                if isinstance(fissues, list) else [],
            "tikz": str(d.get("tikz") or "").strip()[:12000],
            "notes": ([str(x)[:300] for x in notes]
                      if isinstance(notes, list) else [])
                     + (["原解析里的配图已保留在改写结果末尾。"]
                        if preserved else []),
        },
        "model": cfg["model"],
        "cost_cny": deepseek.cost_cny(cfg["model"], usage),
        "seconds": int(time.time() - t0),
    }


def suggest_tikz(key: str) -> dict:
    r"""只判断一道题缺不缺配图，并给出一段可直接插入的 TikZ。

    和 `proofread()` 分开：补图不需要重新做一遍整题，prompt 更小、更便宜。
    这个函数**只读**，不写库；插入仍由用户在界面上确认后走 `/source`。
    """
    one = store.read_one(str(key or "").strip())
    if one is None:
        raise ValueError("没有这道题：%s" % key)
    q = one[0]
    cfg = deepseek.load()
    if not cfg["api_key"]:
        raise deepseek.AIError("还没填 DeepSeek API Key")
    pts = "、".join(q.point_titles or []) or "（未标考点）"
    figs = len(q.figures or [])
    prompt = (
        "你是 K12 数学教研员。请只判断下面这道题**是否缺一幅必要的配图**"
        "（几何图 / 函数图象 / 统计图 / 示意图等），不要重新解题。\n"
        "只返回一个 JSON 对象：\n"
        '{"needed":true|false,"placement":"stem|solution",'
        '"tikz":"需要补时的完整 tikzpicture 环境，不需要时空串",'
        '"reason":"一句话说明"}\n'
        "要求：\n"
        "1. 纯代数/纯文字题、已有配图足够说明问题的，needed=false；\n"
        "2. 需要补时，tikz 必须是**完整可编译**的 `\\begin{tikzpicture}...\\end{tikzpicture}`，"
        "只用标准 TikZ，不要导言区、不要外部图片、不要 Markdown 围栏；\n"
        "3. 几何关系、比例、标注要合理，图能帮助学生理解即可，不求花哨；\n"
        "4. placement 只能是 stem（插到题干）或 solution（插到解析）。\n\n"
        "题目信息：\n题型：%s\n考点：%s\n已有配图数：%d\n题干：%s\n"
        "现有答案：%s\n现有解析：%s\n"
        % (q.type, pts, figs, q.stem.strip()[:5000],
           q.answer.strip()[:300] or "（空）", q.solution.strip()[:4000] or "（空）")
    )
    t0 = time.time()
    usage: dict = {}
    raw = deepseek.chat(prompt, system=aispec.system_prompt(),
                        timeout=300, max_tokens=4096, json_mode=True,
                        on_usage=lambda u: usage.update(u or {}))
    d = deepseek.json_obj(raw)
    if not d:
        raise deepseek.AIError("模型没有返回可解析的补图 JSON")
    needed = bool(d.get("needed"))
    tikz = str(d.get("tikz") or "").strip()
    tikz = re.sub(r"^```(?:latex|tex|tikz|markdown)?\s*", "", tikz, flags=re.I)
    tikz = re.sub(r"\s*```$", "", tikz).strip()
    if needed and tikz and "\\begin{tikzpicture}" not in tikz:
        tikz = "\\begin{tikzpicture}\n%s\n\\end{tikzpicture}" % tikz
    if needed and not tikz:
        needed = False
    placement = str(d.get("placement") or "stem").strip()
    if placement not in ("stem", "solution"):
        placement = "stem"
    return {
        "ok": True, "key": q.key, "needed": needed,
        "tikz": tikz if needed else "",
        "placement": placement if needed else "",
        "reason": str(d.get("reason") or "")[:300],
        "model": cfg["model"],
        "cost_cny": deepseek.cost_cny(cfg["model"], usage),
        "seconds": int(time.time() - t0),
    }
