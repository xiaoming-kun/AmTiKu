r"""极简链：**OCR 全文 → 大模型 → 规范 LaTeX**。

跟 `record2` 那条链的区别只有一句话：**不做几何切分、不做行号引用、不做配对**，
整份文本一次性交给模型，让它一边读一边排版。

## 为什么这样也能用

题目是有特征的：`1.`～`19.`、`A.`～`D.`、`（1）（2）`、`【答案】`。
模型不需要"被切好"才能认出这些，它一次看全文，上下文反而更完整——
题号断档、选项缺失、解析对不上，它自己有数。

## 唯一的铁律：只准抄，不准补

实测（2026-10-28，唐山卷）：给它一页掉了两行题干的 OCR，它会**发现**缺行，
但默认动作是"根据选项推测补全题干"，然后在末尾老实承认。对题库来说这是
最坏的结果——看着完整，其实是编的。所以提示词的第一条就是禁止补全，
缺口必须原样留 `【缺：…】`。

## 怎么用

    python3 -m amti.simple <试卷.pdf> [答案.pdf] [-o 输出.tex]

产物是 tex 文本，**不写库**。要入库仍走 `ingest.preview` → 人工看一眼 → `commit`。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from . import lms as L
from . import record as R
from . import record2 as R2

SYS = """你在把一份高中数学试卷的 OCR 文本整理成规范 LaTeX。

## 铁律（违反即废）

1. **只准抄，不准补。** 原文没有的字、公式、条件、选项，一个都不许加。
2. 缺内容就留标记：`【缺：题干】` `【缺：选项】` `【缺：解析】`，
   然后把它记进末尾的清单。**宁可交一道残缺的题，也不许交一道编出来的题。**
3. 题号原样保留。发现断档（1、2、4）不要自己补第 3 题，写成 `【缺：第3题】`。
4. 水印、公众号、二维码、"资料来源于网络"这类行，直接丢掉。

## 格式

每道题：

    \\begin{question}
    题干……
    \\begin{choices}
      \\item 选项一
      \\item 选项二
    \\end{choices}
    \\end{question}

如果这份文本里带着答案或解析，紧跟在对应题目后面：

    \\begin{solution}
    ……
    \\end{solution}

公式用 `$…$`（行内）和 `\\[…\\]`（独立）。选择题干末尾的作答位写 `\\paren[A]` 这种。

## 收尾

最后单独输出一节：

    【问题】
    1. ……
    （没有就写"无"）

这一节只写你**真的没把握**的东西：缺了哪一行、哪个选项对不上、哪道题的
公式明显被截断。不要为了凑数编问题。
"""


def _number(lines: list[tuple[int, str, int]]) -> str:
    """整卷文本 → 连续行号的纯文本（页标记不占行号，跟 record2 一致）。"""
    out = []
    for page in sorted({p for _n, _t, p in lines}):
        out.append("=== 第%d页 ===" % page)
        for n, t, p in lines:
            if p == page:
                out.append("%3d| %s" % (n, t))
    return "\n".join(out)


def check(tex: str) -> list[str]:
    r"""最便宜的三条自检：题号断档 / 选项数不对 / `$` 不配平。

    **只报不拦**——这是给人看的清单，不是闸门。四条规则的闸门在 `conform` 里。
    """
    warns: list[str] = []
    nums = [int(m) for m in re.findall(r"^%%\s*@q\s*\{.*?\"no\"\s*:\s*(\d+)", tex, re.M)]
    if not nums:
        nums = [i for i, _ in enumerate(re.findall(r"\\begin\{question\}", tex), 1)]
    if nums:
        want = list(range(1, max(nums) + 1))
        missing = [n for n in want if n not in nums]
        if missing:
            warns.append("题号断档：缺第 %s 题" % "、".join(map(str, missing[:10])))

    for i, block in enumerate(re.split(r"\\begin\{question\}", tex)[1:], 1):
        body = block.split(r"\end{question}")[0]
        if r"\begin{choices}" in body:
            n_opt = body.count(r"\item")
            if n_opt not in (4,):
                warns.append("第 %d 题选项 %d 个（单选应为 4）" % (i, n_opt))
        if body.count("$") % 2:
            warns.append("第 %d 题 `$` 不成对" % i)
    return warns


def run(rows: list[dict], *, maxtok: int = 16000, label: str = "") -> dict:
    r"""OCR rows → `{tex, 问题, warn, seconds, usage}`。**不写库。**"""
    doc, lines = R2.build_doc(rows)
    text = _number(lines)
    t0 = time.time()
    need = R2.est_tokens(text) + R2.est_tokens(SYS) + maxtok
    ok, ident, why = L.ensure_ctx(R.MODEL, need_tokens=need)
    if not ok:
        raise RuntimeError(why)
    d = R2._post(R.API, ident,
                 [{"role": "system", "content": SYS},
                  {"role": "user", "content": text}],
                 maxtok=maxtok, extra={"reasoning_effort": "none"})
    R2._guard_thinking(d, "整卷", maxtok)
    raw = d["choices"][0]["message"].get("content") or ""
    finish = d["choices"][0].get("finish_reason")

    tex, problems = raw, ""
    m = re.search(r"【问题】", raw)
    if m:
        tex, problems = raw[:m.start()], raw[m.end():].strip()

    warn = check(tex)
    if finish == "length":
        warn.insert(0, "输出被截断（finish=length）——这份卷子太长，需要分段跑")
    return {"tex": tex.strip(), "问题": problems, "warn": warn,
            "seconds": round(time.time() - t0, 1), "usage": d.get("usage") or {},
            "label": label}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    pdf = Path(argv[1])
    out = None
    if "-o" in argv:
        out = Path(argv[argv.index("-o") + 1])
    work = R2.work_of(pdf)
    key = work / "v2" / "paddle.json"
    if key.is_file():
        rows = json.loads(key.read_text(encoding="utf-8"))["rows"]
        print("复用已识别的 %d 页" % len(rows))
    else:
        print("识别中……")
        rows = R2.scan_pdf(pdf)
    res = run(rows, label=pdf.stem)
    dst = out or pdf.with_suffix(".tex")
    dst.write_text(res["tex"] + "\n", encoding="utf-8")
    print("用时 %.0fs  →  %s" % (res["seconds"], dst))
    if res["问题"]:
        print("\n【模型报的问题】\n" + res["问题"])
    if res["warn"]:
        print("\n【自检】\n" + "\n".join("- " + w for w in res["warn"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
