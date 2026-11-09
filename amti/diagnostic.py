"""AmTiKu · 小初诊断卷

诊断题不在正式题库里（`题目/*.tex`），所以不能走 `export.export(keys=…)`。
这里把它们临时组装成 `Question`，复用同一条 LaTeX 渲染与编译管线，
输出一份「测试卷」分类下的 PDF。

**只读**：不写存档、不改诊断题源文件。产物落 `导出位置/测试卷/`。
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from .schema import Option, Question
from . import export as _export
from . import paper as _paper
from .paths import out_kind_dir


def _q_of(it: dict) -> Question:
    """一条诊断题 → Question。题干里补上作答括号/空位，答案由卷面开关控制。"""
    prompt = _paper.esc_text((it.get("prompt") or "").strip())
    ans = (it.get("answer") or "").strip()
    choices = it.get("choices") or []
    if choices:
        qtype = "single_choice"
        stem = f"{prompt}\\paren[{ans}]"
        options = [Option(str(k), _paper.esc_text(str(t))) for k, t in choices]
    else:
        qtype = "fill_in_blank"
        stem = f"{prompt}\\fillin[{_paper.esc_text(ans)}]"
        options = []
    sol = _paper.esc_text((it.get("explanation") or "").strip()) or "见解析"
    return Question(
        key=f"diag:{it.get('point', '')}#{it.get('key', '').rsplit('#', 1)[-1]}",
        type=qtype,
        stem=stem,
        options=options,
        answer=ans,
        solution=sol,
        meta={"book": it.get("book") or "", "source_label": it.get("book") or "",
              "diagnostic": True},
        points=[it["point"]] if it.get("point") else [],
    )


def export(items: list[dict], *, title: str = "", answers: bool = False,
           out: str = "") -> dict:
    if not items:
        return {"ok": False, "error": "没有诊断题", "questions": 0}
    qs = [_q_of(x) for x in items]
    stage = items[0].get("stage_name") or "小初"
    title = (title or f"{stage}数学诊断卷").strip()
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    name = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", out or f"诊断卷_{stage}_{stamp}").strip("_") or "诊断卷"
    dest = out_kind_dir("测试卷")
    dest.mkdir(parents=True, exist_ok=True)
    tex_path = dest / f"{name}.tex"
    tex_path.write_text(_export.render_paper(
        qs, title=_paper.esc_text(title), show_answers=answers,
        answers_at_end=False, show_source=False, mode="test",
        score_box=False, seal_line=False, bottom_sep="2.2em",
    ), encoding="utf-8")
    ok, log = _export.compile_tex(tex_path)
    res = {
        "ok": ok, "name": name, "questions": len(qs), "kind": "测试卷",
        "tex_abs": str(tex_path), "pdf_abs": str(tex_path.with_suffix(".pdf")) if ok else None,
        "pdf_rel": f"测试卷/{name}.pdf" if ok else None,
        "dir_abs": str(dest), "log": log,
        "error": None if ok else "PDF 编译失败（检查 LaTeX 日志）",
    }
    return res
