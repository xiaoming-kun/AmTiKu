r"""单题修复 agent：模型可以调用本地工具，看到失败原因后再改。

不是一次 prompt 定生死，而是一个有界的工具循环：
  模型 → 调 check_source/compile_tikz → 本地返回真实错误 → 模型再改
最多 4 轮；最终必须通过单题 preview 才算修复。只返回源码，不写库。
"""
from __future__ import annotations

import json

from . import ai_cases, ai_format, deepseek

_SYSTEM = r"""你是 AmMath 的单题 LaTeX 修复 agent。你只修**一道题**，不改题意/答案/选项。
你可以使用工具，但不要猜结果：

工具：
1. check_source(tex) —— 本地解析 + 规范检查；返回 errors（为空表示通过）和 block_count。
2. compile_tikz(code) —— 本地编译一段 TikZ；返回 ok/error。
3. final(tex, note) —— 提交最终题块。

每轮只返回一个 JSON：
{"action":"tool","tool":"check_source","args":{"tex":"..."}}
或
{"action":"tool","tool":"compile_tikz","args":{"code":"..."}}
或
{"action":"final","tex":"完整题块","note":"改了什么"}

规则：
- 题块必须恰好一道 question 或 problem；不要增删题；
- 数学用 $...$ / \[...\]；禁止裸 Unicode 数学、$$、\(...\)；
- 数学模式里不能有裸中文；
- 原卷本身矛盾（两个选项完全相同、答案与解析矛盾、缺答案/解析）不要改题意，final 原样并说明；
- 提交 final 前必须先调用 check_source；如果还有错误，继续修，不要假装通过。
"""


def _check(tex: str, src_dir: str = "") -> dict:
    from . import ingest
    pv = ingest.preview(
        tex, src_dirs=[src_dir] if src_dir else None,
        book="修复校验", label="修复校验")
    items = pv.get("items") or []
    errors: list[str] = []
    if len(items) != 1:
        errors.append("必须恰好解析成 1 道题（现在 %d 道）" % len(items))
    else:
        it = items[0]
        errors += [str(x) for x in (it.get("blocking") or [])]
        for x in ((pv.get("spec") or {}).get("after") or []):
            if x.get("key") == it.get("key"):
                errors.append("%s：%s" % (x.get("check") or "规范", x.get("why") or ""))
    if pv.get("errors"):
        errors += [str(x) for x in pv["errors"][:3]]
    return {"ok": not errors, "errors": list(dict.fromkeys(errors)), "block_count": len(items)}


def _compile(code: str) -> dict:
    try:
        from . import tikzfig
        p, why = tikzfig.render(code)
        return {"ok": p is not None, "error": "" if p is not None else str(why or "编译失败")[:300]}
    except Exception as e:                    # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


def repair_agent(tex: str, problems: list[str], *, source_no: str = "",
                 src_dir: str = "", max_rounds: int = 4,
                 on_step=None) -> dict:
    current = str(tex or "").strip()
    if not current:
        raise ValueError("源码为空")
    history: list[str] = []
    original = current
    current, fmt_changes = ai_format.clean(current)
    if fmt_changes:
        history.append("本地格式清洗：" + "；".join(fmt_changes))
    best = current
    best_errors = list(problems or [])
    related = ai_cases.search(current, problems, limit=2)
    case_hint = ""
    if related:
        case_hint = "\n\n历史类似失败案例（只作参考，不要照抄）：\n" + "\n".join(
            "- 错版：%s\n  修法：%s" % (str(c.get("wrong") or "")[:700],
                                       str(c.get("fixed") or "")[:700])
            for c in related)
    initial = (
        "原始报错：\n%s\n\n当前源码：\n%s\n\n"
        "请选择下一步（可先 check_source）。"
        % ("\n".join("- " + str(x) for x in (problems or [])[:20]) or "- 按规范检查",
           current[:14000]) + case_hint
    )
    messages: list[dict] = [{"role": "user", "content": initial}]
    for round_no in range(1, max_rounds + 1):
        # 多轮必须走同一段对话：模型要能看到自己上一轮的 tex 和工具返回，
        # 否则第 2 轮起只剩一句「继续修复」，等于每轮重新开题。
        raw = deepseek.chat_messages(messages, system=_SYSTEM, timeout=300,
                                     max_tokens=8192, json_mode=True)
        messages.append({"role": "assistant", "content": str(raw or "")})
        d = deepseek.json_obj(raw)
        action = str(d.get("action") or "").strip()
        tool = str(d.get("tool") or "")
        if action == "tool" or action in ("check_source", "compile_tikz"):
            tool = tool or action
            args = d.get("args") if isinstance(d.get("args"), dict) else {}
            if tool == "check_source":
                cand = str(args.get("tex") or current).strip()
                if cand:
                    current, _fc = ai_format.clean(cand)
                res = _check(current, src_dir)
                if on_step:
                    on_step(round_no, "check_source", res)
                history.append("check_source → " + json.dumps(res, ensure_ascii=False)[:1200])
                if res["ok"]:
                    try:
                        ai_cases.record(kind="repair", errors=problems, wrong=original,
                                        fixed=current, resolved=True, source_no=source_no,
                                        note="check_source 通过")
                    except Exception:            # noqa: BLE001
                        pass
                    return {"ok": True, "passed": True, "tex": current,
                            "note": "第 %d 轮 check_source 通过" % round_no,
                            "steps": history, "errors": []}
                best, best_errors = current, res["errors"]
                messages.append({"role": "user", "content":
                                 "check_source 结果：\n"
                                 + json.dumps(res, ensure_ascii=False)[:2000]})
                continue
            if tool == "compile_tikz":
                code = str(args.get("code") or "")
                res = _compile(code)
                if on_step:
                    on_step(round_no, "compile_tikz", res)
                history.append("compile_tikz → " + json.dumps(res, ensure_ascii=False)[:1200])
                messages.append({"role": "user", "content":
                                 "compile_tikz 结果：\n"
                                 + json.dumps(res, ensure_ascii=False)[:2000]})
                continue
            history.append("未知工具：" + tool)
            messages.append({"role": "user", "content":
                             "未知工具 %s；可用工具只有 check_source / compile_tikz / final。" % tool})
            continue
        cand = str(d.get("tex") or "").strip()
        if not cand:
            history.append("模型没有给出 tex")
            messages.append({"role": "user", "content":
                             "返回里没有 tex。请给 final.tex（完整题块），或改调 check_source。"})
            continue
        current, _fc = ai_format.clean(cand)
        res = _check(current, src_dir)
        if on_step:
            on_step(round_no, "final", res)
        history.append("final → " + json.dumps(res, ensure_ascii=False)[:1200])
        if res["ok"]:
            try:
                ai_cases.record(kind="repair", errors=problems, wrong=original,
                                fixed=current, resolved=True, source_no=source_no,
                                note=str(d.get("note") or "final 通过"))
            except Exception:                    # noqa: BLE001
                pass
            return {"ok": True, "passed": True, "tex": current,
                    "note": str(d.get("note") or "修复并通过单题检查")[:300],
                    "steps": history, "errors": []}
        best, best_errors = current, res["errors"]
        messages.append({"role": "user", "content":
                         "final 未通过单题检查：\n"
                         + json.dumps(res, ensure_ascii=False)[:2000]
                         + "\n请继续修改，仍然只返回一个 JSON。"})
    try:
        ai_cases.record(kind="repair", errors=best_errors or problems, wrong=original,
                        fixed=best, resolved=False, source_no=source_no,
                        note="达到最大轮次仍未通过")
    except Exception:                            # noqa: BLE001
        pass
    return {"ok": True, "passed": False, "tex": best,
            "note": "达到最大轮次仍未通过", "steps": history, "errors": best_errors}


if __name__ == "__main__":
    import json as _json

    _calls: list[int] = []
    _good = "FIXED"

    def _fake_chat(messages, **kw):
        _calls.append(len(messages))
        if len(_calls) == 1:
            return _json.dumps({"action": "tool", "tool": "check_source",
                                "args": {"tex": "BAD"}})
        # 第 2 轮必须能看到第 1 轮的 assistant 输出和工具结果；
        # 做不到就是每轮重新开题（旧实现的问题）。
        assert any(m["role"] == "assistant" and "check_source" in m["content"]
                   for m in messages), messages
        assert any(m["role"] == "user" and "check_source 结果" in m["content"]
                   for m in messages), messages
        return _json.dumps({"action": "final", "tex": _good, "note": "done"})

    _chat, _check_fn = deepseek.chat_messages, _check
    _search, _record = ai_cases.search, ai_cases.record
    try:
        deepseek.chat_messages = _fake_chat
        _check = lambda tex, src_dir="": {          # noqa: E731
            "ok": tex == _good, "errors": [] if tex == _good else ["坏"],
            "block_count": 1}
        ai_cases.search = lambda *a, **k: []
        ai_cases.record = lambda **k: None
        r = repair_agent("ORIG", ["报错"])
        assert r["passed"] and r["tex"] == _good, r
        assert _calls == [1, 3], _calls
    finally:
        deepseek.chat_messages, _check = _chat, _check_fn
        ai_cases.search, ai_cases.record = _search, _record
    print("ai_agent 自检通过：第 2 轮能看到工具结果并 final 通过")
