r"""双 OCR 对拍 → 27B 规范化 → 产出 tex。

## 分工

    页图 ──┬─ PaddleOCR-VL（::8111，出 LaTeX）──┐
           └─ GLM-OCR（::1236，出纯文本）──────┤ 对拍：谁漏了、漏在哪
                                                ↓
                                     27B（只抄不补）→ exam-zh LaTeX
                                                ↓
                                        自检：题号/选项/$ 配平

## 为什么要两个

实测（2026-10-28）：PaddleOCR-VL 在一页上偶发把题干整行吞掉，而且**不报错**；
同一页重跑又好。单引擎没法知道自己漏了，两个引擎的差异就是"可疑处"。

## 两阶段，不并发

识别时**先把 27B 卸掉**——48 GB 的机器上，27B 占 23 GB 时 OCR 掉行概率明显上升
（`record2.py` 开头那句「内存不够两个模型同时驻留」说的就是这个）。

## 用法

    python3 -m amti.dual <pdf> --pages 1-30 -o 输出.tex
    python3 -m amti.dual <pdf> --pages 1-30 --ocr-only     # 只识别，缓存下来
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DPI = 200
GLM_API = "http://127.0.0.1:1236/v1/chat/completions"
WORK = Path.home() / ".amtiku" / "dual"

_NUM = re.compile(r"(?m)^\s*(?:#{1,6}\s*)?(\d{1,2})[.．、]")


# ── ① 渲染 ────────────────────────────────────────────────────────
def render(pdf: Path, first: int, last: int) -> list[Path]:
    r"""PDF 的第 first..last 页 → PNG（200 dpi）。已有就复用。"""
    import pymupdf
    out = WORK / pdf.stem / "pages"
    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    paths = []
    for i in range(first - 1, min(last, doc.page_count)):
        p = out / ("p%03d.png" % (i + 1))
        if not p.is_file():
            pix = doc[i].get_pixmap(dpi=DPI)
            pix.save(p)
        paths.append(p)
    return paths


# ── ② 两个引擎 ────────────────────────────────────────────────────
def ocr_paddle(img: Path) -> str:
    from . import paddle
    return paddle.parse_file(img)


def ocr_glm(img: Path, *, timeout: int = 300) -> str:
    import urllib.request
    b64 = base64.b64encode(img.read_bytes()).decode()
    body = {"model": "glm-ocr", "temperature": 0,
            "max_tokens": 8000,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                {"type": "text", "text": "OCR:"}]}]}
    req = urllib.request.Request(GLM_API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=timeout))
    return d["choices"][0]["message"].get("content") or ""


# ── ③ 对拍 ────────────────────────────────────────────────────────
def _nums(text: str) -> list[int]:
    out = []
    for m in _NUM.finditer(text):
        n = int(m.group(1))
        if not out or n > out[-1]:
            out.append(n)
    return out


def compare(a: str, b: str) -> dict:
    r"""两段文本的差异 → `{take, why}`。

    **不比字面**——一个出 LaTeX、一个出 unicode 数学，直接 diff 全是噪声。
    只比三件跟"漏没漏"有关的事：字数、题号覆盖、选项标签数。
    """
    na, nb = _nums(a), _nums(b)
    la, lb = len(a), len(b)
    why = []
    if set(nb) - set(na):
        why.append("GLM 多出题号 %s" % sorted(set(nb) - set(na))[:6])
    if set(na) - set(nb):
        why.append("Paddle 多出题号 %s" % sorted(set(na) - set(nb))[:6])
    if max(la, lb) and abs(la - lb) / max(la, lb) > 0.25:
        why.append("字数差 %.0f%%（%d vs %d）" % (100 * abs(la - lb) / max(la, lb), la, lb))
    # 默认用 Paddle：它出 LaTeX，下游直接能用
    return {"take": "paddle", "why": why, "chars": (la, lb),
            "nums": (na, nb)}


# ── ④ 27B 规范化 ──────────────────────────────────────────────────
SYS_EXAM = """你在把一份高中数学试卷的 OCR 文本整理成规范 LaTeX。

## 铁律

1. **只准抄，不准补。** 原文没有的字、公式、条件、选项，一个都不许加。
2. 缺内容留标记 `【缺：…】`。宁可交残缺的，不许交编的。
3. 题号原样保留；断档不要自己补，写 `【缺：第N题】`。
4. 水印、公众号、二维码这类行直接丢掉。

## 输入

会分两段给：`=== 试卷 ===` 和 `=== 答案 ===`。答案那段形如
`12.【答案】9` 换行 `【解析】……`。

**`=== 答案 ===` 之后的每一段，都是"某道题的答案与解析"，不是新题目。**
绝对不许在那里再开 `question` 环境——那是这份任务最容易犯的错
（实测 19 道题被写成 38 道，后 19 道是答案）。

## 输出

**题目在前、解析在后**：先把 `=== 试卷 ===` 里的题按题号整理成 question 环境
（选择题带 choices），再按题号把答案那段里的答案/解析接成 solution 环境。
配不上的题写 `【缺：解析】`，多出来的解析单独列在末尾 `【多出的解析】` 下。

行内公式 `$…$`，独立公式 `\\[…\\]`。
"""

SYS = """你在把一份高中数学讲义的 OCR 文本整理成规范 LaTeX。

## 铁律

1. **只准抄，不准补。** 原文没有的字、公式、条件，一个都不许加。
2. 缺内容留标记 `【缺：…】`。宁可交残缺的，不许交编的。
3. 水印、公众号、二维码、"资料来源于网络"这类行直接丢掉。

## 格式

每道题一个 `question` 环境，选择题用 `choices`；解析紧跟在题目后面：

    \\begin{question}
    ……题干……
    \\begin{choices}
      \\item ……
    \\end{choices}
    \\end{question}

    \\begin{solution}
    ……解析……
    \\end{solution}

行内公式 `$…$`，独立公式 `\\[…\\]`。
"""


def to_tex(text: str, *, maxtok: int = 12000, kind: str = "讲义") -> dict:
    from . import lms as L, record as R, record2 as R2
    sys_prompt = SYS_EXAM if kind == "试卷" else SYS
    need = R2.est_tokens(text) + R2.est_tokens(sys_prompt) + maxtok
    ok, ident, why = L.ensure_ctx(R.MODEL, need_tokens=need)
    if not ok:
        raise RuntimeError(why)
    d = R2._post(R.API, ident,
                 [{"role": "system", "content": sys_prompt},
                  {"role": "user", "content": text}],
                 maxtok=maxtok, extra={"reasoning_effort": "none"})
    R2._guard_thinking(d, "整卷", maxtok)
    raw = d["choices"][0]["message"].get("content") or ""
    return {"tex": raw, "finish": d["choices"][0].get("finish_reason"),
            "usage": d.get("usage") or {}}


# ── ⑤ 主流程 ──────────────────────────────────────────────────────
def run(pdf: Path, first: int, last: int, out: Path, *, ocr_only: bool = False) -> None:
    pdf = Path(pdf)
    out.mkdir(parents=True, exist_ok=True)
    imgs = render(pdf, first, last)
    print("渲染 %d 页 → %s" % (len(imgs), imgs[0].parent), flush=True)

    # 阶段一：双引擎识别（此时 27B 必须卸掉）
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, timeout=120)
    except Exception:                                          # noqa: BLE001
        pass
    cache = out / "ocr.json"
    pages = _ocr_pages(imgs, cache)
    if ocr_only:
        print("只识别，产物：%s" % cache)
        return

    # 阶段二：27B 规范化（按 6 页一组，控制输出长度）
    keys = [im.stem for im in imgs]
    step = 6
    texs = []
    for i in range(0, len(keys), step):
        part = keys[i:i + step]
        text = "\n\n".join("=== 第 %s 页 ===\n%s" % (k, pages[k]["paddle"]) for k in part)
        r = to_tex(text)
        texs.append(r["tex"])
        print("  第 %d-%d 页 → %d 字  finish=%s"
              % (i + 1, i + len(part), len(r["tex"]), r["finish"]), flush=True)
        (out / ("part%02d.tex" % (i // step + 1))).write_text(r["tex"], encoding="utf-8")
    (out / "all.tex").write_text("\n\n".join(texs), encoding="utf-8")
    print("完成：%s" % (out / "all.tex"))


def _ocr_pages(imgs: list[Path], cache: Path) -> dict:
    r"""逐页跑两个引擎，结果落 `ocr.json`（可续跑）。"""
    pages = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else {}
    for img in imgs:
        k = img.stem
        if k in pages and pages[k].get("paddle") and pages[k].get("glm"):
            continue
        t0 = time.time()
        a = ocr_paddle(img)
        b = ocr_glm(img)
        pages[k] = {"paddle": a, "glm": b, **compare(a, b)}
        cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
        print("  %s  paddle %d 字 / glm %d 字  %.0fs  %s"
              % (k, len(a), len(b), time.time() - t0,
                 "；".join(pages[k]["why"]) or "一致"), flush=True)
    return pages


def run_pair(paper: Path, answers: Path | None, out: Path, *, maxtok: int = 16000) -> dict:
    r"""一份试卷（+ 可选答案）→ tex。**先识别、再上模型**，两阶段不并发。"""
    paper, out = Path(paper), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, timeout=120)
    except Exception:                                          # noqa: BLE001
        pass

    q_imgs = render(paper, 1, 10 ** 6)
    pages = _ocr_pages(q_imgs, out / "ocr_paper.json")
    text = "\n\n".join("=== 试卷 第 %s 页 ===\n%s" % (i.stem, pages[i.stem]["paddle"])
                        for i in q_imgs)
    if answers:
        a_imgs = render(Path(answers), 1, 10 ** 6)
        ap = _ocr_pages(a_imgs, out / "ocr_answers.json")
        text += "\n\n" + "\n\n".join(
            "=== 答案 第 %s 页 ===\n%s" % (i.stem, ap[i.stem]["paddle"]) for i in a_imgs)
    r = to_tex(text, maxtok=maxtok, kind="试卷")
    (out / "all.tex").write_text(r["tex"], encoding="utf-8")
    print("完成：%s（%d 字，finish=%s）" % (out / "all.tex", len(r["tex"]), r["finish"]), flush=True)
    return r



# ── ⑥ 试卷 + 答案：**分两次调用**，按题号配 ────────────────────────
#
# 为什么不再把两段拼成一次调用：实测（湖北九师）19 道题被写成 38 道，
# 后 19 道是答案——模型把"答案段"当成了"又一批题"。两次调用各自只有
# 一种活，就没有"分不清段落"这回事。

SYS_Q = """你在把一份高中数学试卷的 OCR 文本整理成规范 LaTeX，**只出题目**。

铁律：只准抄，不准补；原文没有的不许加；缺了写【缺：…】。
水印、公众号、二维码那些行丢掉。

格式：每道题**前面单独一行**写 `%% [n]`（n 是题号），紧接着

    \\begin{question}
    ……题干……
    \\begin{choices}
      \\item ……
    \\end{choices}
    \\end{question}

**不要写任何 solution。**
"""

SYS_A = """你在整理一份答案卷的 OCR 文本，**只出答案与解析**。

铁律：只准抄，不准补；缺了写【缺：…】。

格式：每一条前面单独一行写 `%% [n]`（n 是题号），紧接着

    \\begin{solution}
    【答案】……
    【解析】……
    \\end{solution}

**不要写任何 question。**
"""


def _by_no(tex: str) -> dict[int, str]:
    """`%% [n]` 分块 → {题号: 正文}；没有标记就按出现顺序编号。"""
    import re as _re
    parts = _re.split(r"(?m)^\s*%%\s*\[(\d+)\]\s*$", tex)
    if len(parts) > 2:
        return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    blocks = _re.findall(r"\\begin\{question\}.*?\\end\{question\}", tex, _re.S)
    return {i: b for i, b in enumerate(blocks, 1)}


def _call(text: str, sys_prompt: str, *, maxtok: int, model: str = "") -> str:
    from . import lms as L, record as R, record2 as R2
    model = model or R.MODEL
    need = R2.est_tokens(text) + R2.est_tokens(sys_prompt) + maxtok
    ok, ident, why = L.ensure_ctx(model, need_tokens=need)
    if not ok:
        raise RuntimeError(why)
    d = R2._post(R.API, ident,
                 [{"role": "system", "content": sys_prompt},
                  {"role": "user", "content": text}],
                 maxtok=maxtok, extra={"reasoning_effort": "none"})
    R2._guard_thinking(d, "整卷", maxtok)
    return d["choices"][0]["message"].get("content") or ""


#: 抄答案用的模型。**这一步是机械活**（照抄 + 按题号配），9B 够用，
#: 而且实测比 27B 快 1.8 倍（324s/7937 字 vs 360s/4857 字），还省 10 GB 内存。
ANSWER_MODEL = "qwen3.5-9b-mlx"


def run_exam(paper: Path, answers: Path | None, out: Path, *,
             answer_model: str = ANSWER_MODEL) -> dict:
    r"""试卷 / 答案**分开调用**，再按题号拼成一份 tex。"""
    paper, out = Path(paper), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["lms", "unload", "--all"], capture_output=True, timeout=120)
    except Exception:                                          # noqa: BLE001
        pass

    q_imgs = render(paper, 1, 10 ** 6)
    qp = _ocr_pages(q_imgs, out / "ocr_paper.json")
    q_text = "\n\n".join(qp[i.stem]["paddle"] for i in q_imgs)
    qf = out / "questions.tex"
    if qf.is_file() and qf.stat().st_size > 500:      # 上一次已经出来的，别重跑
        q_tex = qf.read_text(encoding="utf-8")
        print("  复用已有的 questions.tex（%d 字）" % len(q_tex), flush=True)
    else:
        q_tex = _call(q_text, SYS_Q, maxtok=14000)
        qf.write_text(q_tex, encoding="utf-8")

    a_map: dict[int, str] = {}
    if answers:
        a_imgs = render(Path(answers), 1, 10 ** 6)
        ap = _ocr_pages(a_imgs, out / "ocr_answers.json")
        # **按 3 页一组**：整份答案 3 万字一次性喂，上下文要到 49k，
        # 48 GB 的机器上进程会被系统 SIGKILL 掉（无异常、无 traceback）。
        # 分组之后每次上下文 20k 上下，进程稳得住。
        parts, buf = [], ""
        for i in a_imgs:
            t = ap[i.stem]["paddle"]
            if buf and len(buf) + len(t) > 8000:
                parts.append(buf); buf = ""
            buf += "\n\n" + t
        if buf.strip():
            parts.append(buf)
        got = []
        for k, chunk in enumerate(parts, 1):
            t = _call(chunk, SYS_A, maxtok=5000, model=answer_model)
            got.append(t)
            print("  答案第 %d/%d 组 → %d 字" % (k, len(parts), len(t)), flush=True)
        a_tex = "\n\n".join(got)
        (out / "answers.tex").write_text(a_tex, encoding="utf-8")
        a_map = _by_no(a_tex)

    qs = _by_no(q_tex)
    merged, miss = [], 0
    for n in sorted(qs):
        merged.append(qs[n])
        sol = a_map.get(n)
        if sol and r"\begin{solution}" not in sol:
            sol = "\\begin{solution}\n" + sol + "\n\\end{solution}"
        if not sol:
            miss += 1
            sol = "\\begin{solution}\n【缺：解析】\n\\end{solution}"
        merged.append(sol)
    tex = "\n\n".join(merged)
    (out / "all.tex").write_text(tex, encoding="utf-8")
    print("题目 %d 条，配上解析 %d 条，缺 %d 条 → %s"
          % (len(qs), len(qs) - miss, miss, out / "all.tex"), flush=True)
    return {"tex": tex, "questions": len(qs), "missing": miss}



def audit_pages(work: Path, pdf: Path) -> dict:
    r"""对已识别的卷子做**第二引擎复核**，结果写 `v2/ocr_check.json`。

    只记账、不改正文：Paddle 已经出了 LaTeX，GLM 出的是纯文本，两者没法
    直接合并；能比的是"这页有没有明显少读"。差异页留给人看。
    """
    work = Path(work)
    key = work / "v2" / "paddle.json"
    if not key.is_file():
        return {"可疑": [], "error": "没有 paddle.json"}
    rows = json.loads(key.read_text(encoding="utf-8")).get("rows") or []
    res: dict[str, dict] = {}
    for r in rows:
        img = Path(r["img"])
        if not img.is_file():
            continue
        try:
            g = ocr_glm(img)
        except Exception as e:                                 # noqa: BLE001
            return {"可疑": [], "error": "GLM-OCR 不可用：%s" % type(e).__name__}
        p_txt = Path(r["txt"]).read_text(encoding="utf-8")
        c = compare(p_txt, g)
        res[img.stem] = {"paddle": len(p_txt), "glm": len(g), "why": c["why"]}
    (work / "v2" / "ocr_check.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [k for k, v in res.items() if v["why"]]
    return {"可疑": bad, "pages": res}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    pdf = Path(argv[1])
    rng = "1-30"
    if "--pages" in argv:
        rng = argv[argv.index("--pages") + 1]
    a, _, b = rng.partition("-")
    out = Path(argv[argv.index("-o") + 1]) if "-o" in argv else WORK / pdf.stem / "out"
    run(pdf, int(a), int(b or a), out, ocr_only="--ocr-only" in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
