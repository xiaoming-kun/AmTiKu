r"""AmTiKu · **全库编译体检**

## 为什么需要它

卷子编译失败是"抽到才炸"的：库里 17,000 多道题，平时出的卷子都好好的，
直到某一次组卷恰好抽中那道有问题的题，**整份卷子出不来**，而且报错信息
（`Unknown arrow tip kind 'Stealth'`）跟题目内容八竿子打不着，很难倒查。

实测踩过两次，都是"原卷预导言区里定义的东西没跟着搬过来"：
  · 自定义 pgfplots 样式 `exam statistical histogram`（30 处用）
  · `arrows.meta` 库没装（`-Stealth` 箭头，11 处用）

这类问题的共性是：**题目本身合法，是"渲染环境"缺东西**。
所以要么在导言里一次补齐（已做），要么得有办法**批量查出来**。
这个模块就是后者——不等到抽中，主动把全库过一遍。

## 怎么查（不然 17000 道要跑一天）

只查**有 TikZ／配图的题**（其余是纯文本 + 数学公式，不可能编译不过）。
然后**分批编译**：一批若干道放进一个文档编译一次；
- 过了 → 这一批全没问题
- 没过 → **二分**，一直缩到具体哪几道

这样几十分钟能覆盖全库，而不是几小时。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import store
from .export import IMG_DIR
from .paper import render_paper

# 一批放多少道。太大 → 一次失败要二分的层数多；
# 太小 → 编译次数上去了（每次 xelatex 要 2~3 秒）。
BATCH = 24


def risky(q) -> bool:
    r"""这道题**有没有可能**编译不过。

    判据：带 TikZ／配图。纯文本 + 数学公式的题不可能因为环境缺东西而失败
    （它们早在 `conform` 的渲染检查里就过了一遍）。
    """
    if q.figures:
        return True
    stem = q.stem or ""
    return "tikzpicture" in stem or "\\begin{axis}" in stem


def _compile(questions: list, workdir: Path, *, timeout: int = 240) -> tuple[bool, str]:
    r"""编译一批。返回 (成功?, 日志尾部)。"""
    tex = render_paper(questions, mode="test", title="编译体检", show_answers=False,
                       problem_blank_cm=0, graphicspath=str(IMG_DIR))
    src = workdir / "t.tex"
    src.write_text(tex, encoding="utf-8")
    try:
        p = subprocess.run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
            cwd=workdir, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "编译超时（%d 秒）" % timeout
    log = (p.stdout or b"").decode("utf-8", "ignore")
    if p.returncode == 0 and (workdir / "t.pdf").exists():
        return True, ""
    # 只留真正的那条错误，别把几百行日志全甩出来
    errs = [l for l in log.split("\n") if l.startswith("!")]
    return False, (errs[0][:200] if errs else log[-200:])


def check(keys: list[str] | None = None, *, batch: int = BATCH,
          verbose: bool = True) -> dict:
    r"""跑一遍体检。返回 `{检查了几道, 失败的: [{key, why}], 用了几次编译}`。

    `keys` 给定时只查这些题；不给就查全库里所有"有风险"的题。
    """
    if keys:
        qs = [q for k in keys if (q := store.find(k)) is not None]
    else:
        qs = [q for _f, q in store.iter_questions() if risky(q)]

    work = Path(tempfile.mkdtemp(prefix="amti-cc-"))
    fails: list[dict] = []
    runs = 0

    def probe(batch_qs: list) -> None:
        r"""编译一批；失败就二分，直到定位到具体哪几道。"""
        nonlocal runs
        if not batch_qs:
            return
        runs += 1
        ok, why = _compile(batch_qs, work)
        if ok:
            return
        if len(batch_qs) == 1:
            fails.append({"key": batch_qs[0].key, "why": why})
            return
        # 二分：先左后右。**两边都要试**——一批里可能不止一道坏题。
        mid = len(batch_qs) // 2
        probe(batch_qs[:mid])
        probe(batch_qs[mid:])

    try:
        for i in range(0, len(qs), batch):
            chunk = qs[i:i + batch]
            if verbose:
                print("  第 %d/%d 批（%d 道）…" % (i // batch + 1,
                      (len(qs) + batch - 1) // batch, len(chunk)), flush=True)
            probe(chunk)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {"checked": len(qs), "fails": fails, "runs": runs}
