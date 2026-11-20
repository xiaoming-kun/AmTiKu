r"""DeepSeek 单题修复：只根据 conformance 报错修一道题的 LaTeX，不写库。

前端拿到修复后的题块后，仍然走 `ingest.preview`；预览通过才替换。
所以这里没有第二套写库路径。原卷内容矛盾（选项重复、答案/解析矛盾）不硬改。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import aispec, deepseek
from .paths import ROOT


def repair(tex: str, problems: list[str], source_no: str = "",
           instruction: str = "", src_dir: str = "") -> dict:
    src = str(tex or "").strip()
    if not src:
        raise ValueError("源码为空")
    meta_line = src.splitlines()[0] if src.startswith("%% @q") else ""
    # 原卷内容矛盾不是模型能擅自改的：直接拒绝，避免把题面改“顺”。
    if any(("选项文字完全相同" in str(x)) or ("答案与解析" in str(x) and "矛盾" in str(x))
           for x in (problems or [])):
        return {"ok": True, "tex": src, "unfixable": True,
                "note": "原卷内容本身矛盾，不能自动改；请人工确认选项/答案"}
    probs = "\n".join("- " + str(x) for x in (problems or [])[:24]) or "- 按规范检查"
    task = str(instruction or "").strip() or "只按校验报错修 LaTeX 格式；不要改题意、答案、选项、题号。"
    tikz = ("tikz" in task.lower()) or ("图" in task)
    if tikz and not instruction.strip():
        task = "把题中的位图图片改成可编译的 TikZ；保留题干/选项/答案/解析/题号，不要改题意。"
    prompt = (
        "你是 LaTeX 题库修理工。下面是一道题的源码和规范校验报错。\n"
        "任务：%s\n"
        "不改题意、答案、选项、题号、考点和 %% @q 元数据；不要新增/删除题目内容，"
        "不要编造答案或解析。\n"
        "必须返回 JSON：{\"tex\":\"处理后的完整题块\",\"unfixable\":false,\"note\":\"改了什么\"}。\n"
        "要求：\n"
        "1. 题干/选项/解析用 $...$ 或 \\[...\\]，禁止 $$、\\(...\\)、裸 Unicode 数学符号；\n"
        "2. 数学模式里不能有裸中文，必须用 \\text{...} 包起来或移到数学模式外；\n"
        "3. 不增删 \\begin{question}/\\end{question}、choices、solution；\n"
        "4. 如果任务是把图片改成 TikZ：只能使用导言区已加载的库，代码必须可编译；"
        "无法准确还原就 unfixable=true，不要乱画。保留原图的语义和标注。\n"
        "5. 如果是原卷本身矛盾（两个选项完全相同、答案与解析矛盾、缺答案/缺解析），"
        "不要改题意，tex 原样返回，unfixable=true，note 说明原因；\n"
        "6. 只输出 JSON，不要 Markdown 围栏。\n\n"
        "题号：%s\n校验报错：\n%s\n\n源码：\n%s"
        % (task, source_no or "（未知）", probs, src[:12000])
    )
    # 单题修复也可以带图：从当前 AI 任务的 crop_dir / 图片来源目录读取源码引用的图片。
    images: list[bytes] = []
    if tikz:
        bases = ([Path(src_dir).expanduser().resolve()] if src_dir
                 else [ROOT / "图片"])
        for name in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", src)[:2]:
            name = name.strip()
            for base in bases:
                try:
                    p = (base / name).resolve()
                    if base not in p.parents or not p.is_file():
                        continue
                    images.append(p.read_bytes())
                    break
                except Exception:                # noqa: BLE001
                    continue
    raw = deepseek.chat(prompt, images, system=aispec.system_prompt(),
                        timeout=300, max_tokens=8192, json_mode=True)
    d = deepseek.json_obj(raw)
    fixed = str(d.get("tex") or "").strip()
    fixed = re.sub(r"^```[a-zA-Z]*\s*", "", fixed)
    fixed = re.sub(r"\s*```$", "", fixed).strip()
    if d.get("unfixable"):
        return {"ok": True, "tex": src, "unfixable": True,
                "note": str(d.get("note") or "原卷内容矛盾，不能自动改")[:300]}
    if not fixed:
        raise ValueError("模型没有返回修复后的源码")
    env = "problem" if "\\begin{problem}" in src else "question"
    if (fixed.count("\\begin{%s}" % env) != 1
            or fixed.count("\\end{%s}" % env) != 1):
        raise ValueError("修复结果不是恰好一道 %s 题块，已拒绝" % env)
    if src.count("\\begin{solution}") != fixed.count("\\begin{solution}"):
        raise ValueError("修复结果增删了 solution，已拒绝")
    # 元数据行必须保留原样，不能被模型重写。
    if meta_line and not fixed.startswith("%% @q"):
        fixed = meta_line + "\n" + fixed
    return {"ok": True, "tex": fixed, "unfixable": False,
            "note": str(d.get("note") or "已按报错修复")[:300]}


if __name__ == "__main__":
    import json as _json

    _B = chr(92)

    def _block(env: str) -> str:
        return ("%% @q key=测试/卷#1 type=detailed_answer" + "\n"
                + _B + "begin{%s}" % env + "\n已知 $x=1$，求 $x+1$。\n"
                + _B + "end{%s}" % env + "\n"
                + _B + "begin{solution}" + "\n$2$。\n" + _B + "end{solution}")

    _problem, _question = _block("problem"), _block("question")
    _chat = deepseek.chat
    try:
        # 解答题是 problem 环境：曾只认 question，修解答题 100% 被拒。
        deepseek.chat = lambda prompt, images=None, **kw: _json.dumps(
            {"tex": _problem, "note": "ok"}, ensure_ascii=False)
        r = repair(_problem, ["编译失败"])
        assert r["tex"] == _problem and not r["unfixable"], r
        # 选择题仍是 question，不能被 problem 分支带坏。
        deepseek.chat = lambda prompt, images=None, **kw: _json.dumps(
            {"tex": _question, "note": "ok"}, ensure_ascii=False)
        r = repair(_question, ["编译失败"])
        assert r["tex"] == _question, r
        # 模型把一道题拆成两道 → 拒绝。
        deepseek.chat = lambda prompt, images=None, **kw: _json.dumps(
            {"tex": _problem + "\n" + _problem}, ensure_ascii=False)
        try:
            repair(_problem, ["编译失败"])
        except ValueError:
            pass
        else:
            raise AssertionError("重复题块应被拒绝")
        # 原卷本身矛盾 → 原样返回，不硬改。
        r = repair(_problem, ["答案与解析矛盾"])
        assert r["unfixable"] and r["tex"] == _problem, r
    finally:
        deepseek.chat = _chat
    print("airepair 自检通过：problem/question 题块、重复拒绝、矛盾原样返回")
