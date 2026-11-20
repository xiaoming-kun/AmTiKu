r"""把已有题的解析重写成规范 LaTeX：**只改格式，不改题目/答案/步骤内容**。

校对页只给建议；这个模块给“真正重写解析”用。返回后前端仍走
`POST /questions/{key}/solution`，由现有规范闸门和并发保护决定是否保存。
"""
from __future__ import annotations

import re

from . import aispec, deepseek, latex_blocks as lb, latex_ir


def rewrite_solution(*, stem: str, answer: str, solution: str,
                     qtype: str = "") -> dict:
    if not str(solution or "").strip():
        raise ValueError("这道题还没有解析，不能重写；先补解析")
    prompt = (
        "下面是一道已有题的题干、答案和解析。请只把**解析**改写为规范 LaTeX，"
        "不改题意、不改答案、不增删推导步骤和结论。\n"
        "返回 JSON：{\"solution\":\"重写后的解析正文\",\"note\":\"改了什么\"}。\n"
        "要求：\n"
        "1. 所有数学用 $...$ 或 \\[...\\]；禁止 $$、\\(...\\)、裸 Unicode 数学；\n"
        "2. Unicode 符号换成 LaTeX：∈→\\in，≤→\\leqslant，≥→\\geqslant，"
        "∪→\\cup，∩→\\cap，√→\\sqrt{}，²→^{2}，logₚ→\\log_{p}；\n"
        "3. 不写 Markdown、不写思考过程、不写“答案：见解析”这类答案栏内容；\n"
        "4. 只输出解析正文；如果无法在不改变内容的前提下规范化，就原样返回并说明；\n"
        "5. 如果原解析里有 \\includegraphics 或 tikzpicture，必须原样保留，"
        "位置尽量不变；配图是正文的一部分，不能删。\n\n"
        "题型：%s\n题干：%s\n答案：%s\n现有解析：\n%s"
        % (qtype or "未标注", str(stem or "")[:5000], str(answer or "见解析")[:300],
           str(solution or "")[:10000])
    )
    raw = deepseek.chat(prompt, system=aispec.system_prompt(),
                        timeout=300, max_tokens=8192, json_mode=True)
    d = deepseek.json_obj(raw)
    out = str(d.get("solution") or "").strip()
    out = re.sub(r"^```(?:latex|tex|markdown)?\s*", "", out, flags=re.I)
    out = re.sub(r"\s*```$", "", out).strip()
    if not out:
        raise ValueError("模型没有返回重写后的解析")
    out, kept = latex_ir.preserve_figures(solution, out)
    note = str(d.get("note") or "已重写为规范 LaTeX")[:300]
    if kept:
        note = (note + "；原解析配图已保留在末尾").strip("；")
    return {"ok": True, "solution": out,
            "blocks": lb.parse_blocks(out),
            "note": note}
