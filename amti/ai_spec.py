r"""规范驱动的 AI 录题：PDF 页图 + 《试卷扫描标准化规范》→ 规范 .tex。

这是取代旧「两遍 JSON 转录 + _compose」的新主路径：
- 模型直接按规范输出题目 .tex，不再由本地拼题块；
- 图一律用 TikZ，本地不裁图；写不出关键信息的整题不交，进「未交付」表；
- 本地只做 preview/规范检查，不写库；
- 答案/解析是否允许模型补，由用户显式选项决定。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import fitz

from . import ai_format, aispec, deepseek
from .paths import ROOT

JOB_ROOT = ROOT / "数据" / "缓存" / "AI图"
# 单次请求最多读多少页。DeepSeek 视觉接口本身允许 600 张图/请求，图不是瓶颈；
# 卡住的是输出长度：模型一次要交整份 .tex（max_tokens=32000），实测每页约
# 1.3k 输出 token（4+6 页 ≈ 13k）。30 页 ≈ 39k，密集卷子会超过 32k 被截断，
# 那时报错而不是静默漏题。超过 30 页在入口整卷拒绝，不悄悄分批——半份试题 +
# 半份答案拼起来，题号和答案会错位。
MAX_PAGES = 30
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


class Cancelled(deepseek.AIError):
    """用户点了取消。router 靠这个类型把任务标成 cancelled 而不是 error。"""


def merge_parts(parts: list[tuple[bytes, str]], *, label: str = "文件") -> bytes:
    """多份 PDF / 图片按选择顺序合成一份；格式不对当场报错。"""
    if not parts:
        raise deepseek.AIError("%s是空的" % label)
    out = fitz.open()
    try:
        for raw, name in parts:
            low = (name or "").lower()
            if not raw:
                continue
            if low.endswith(".pdf"):
                src = fitz.open(stream=raw, filetype="pdf")
                try:
                    if not src.page_count:
                        raise deepseek.AIError("%s《%s》没有页面" % (label, name))
                    out.insert_pdf(src)
                finally:
                    src.close()
            elif low.endswith(_IMG_EXT):
                src = fitz.open(stream=raw)
                try:
                    pdf = src.convert_to_pdf()
                finally:
                    src.close()
                tmp = fitz.open("pdf", pdf)
                try:
                    out.insert_pdf(tmp)
                finally:
                    tmp.close()
            else:
                raise deepseek.AIError("%s只收 PDF / 图片；Word 请先另存为 PDF（%s）"
                                       % (label, name or "未命名"))
        if not out.page_count:
            raise deepseek.AIError("%s里没有可用页面" % label)
        return out.tobytes()
    finally:
        out.close()


def _pages(data: bytes, dpi: int) -> list[bytes]:
    d = fitz.open(stream=data, filetype="pdf")
    out: list[bytes] = []
    try:
        for i in range(d.page_count):
            pix = d[i].get_pixmap(dpi=dpi)
            out.append(pix.tobytes("png"))
    finally:
        d.close()
    return out


def _ascii_name(name: str, i: int) -> str:
    return "%s-%d.png" % (name, i)


def _save_pages(pngs: list[bytes], prefix: str, page_dir: Path) -> None:
    page_dir.mkdir(parents=True, exist_ok=True)
    for i, raw in enumerate(pngs, 1):
        (page_dir / _ascii_name(prefix, i)).write_bytes(raw)


def _strip_tex(raw: str) -> str:
    s = str(raw or "").strip()
    s = re.sub(r"^```(?:latex|tex|markdown)?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*```$", "", s).strip()
    m = re.search(r"\\(?:title\{[^}]*\}|begin\{(?:question|problem)\})", s)
    if not m:
        return ""
    s = s[m.start():]
    # Drop trailing report-ish prose after the last end environment.
    ends = list(re.finditer(r"\\end\{(?:question|problem)\}", s))
    if ends:
        s = s[:ends[-1].end()]
    return s.strip()


def _prompt(pages: list[int], total: int, ans_pages: int, fill: bool,
            source_name: str, title_hint: str) -> str:
    policy = ("用户明确要求：可以解题补答案。按文件附录的 B 口径执行，"
              "并在未交付表加来源列；解不出/与原卷冲突就留空标待补。"
              if fill else
              "默认 A 口径：只抄原卷，不自己解题；没有答案/解析就留空并写进未交付表。")
    return (
        "请严格按随附《PDF题目录入格式要求（给网页端大模型）》处理下面的页图。\n"
        "输出必须和网页端一致：先一个 ```latex 代码块，再「未交付 / 待补」表；"
        "多页再给「原题号 → 第几块」表。**不要 JSON、不要解释、不要 HTML。**\n"
        "PDF 文件名（\\title 用它，去掉 .pdf）：%s\n"
        "本批是试题第 %s 页（共 %d 页），答案册 %d 页；跨页题合并。\n"
        "答案/解析策略：%s\n"
        "整份这些页都读，不要只读第一页；有图一律用 TikZ，画不出关键信息就整题不交并写待补。"
        % (source_name or title_hint or "未命名.pdf",
           "、".join(str(x) for x in pages), total, ans_pages, policy)
    )


def _extract_web(raw: str, title_hint: str) -> tuple[str, str, list[dict], list[str]]:
    """从网页端三段输出里取 tex / title / 未交付表 / 警告。"""
    text = str(raw or "").strip()
    blocks = re.findall(r"```(?:latex|tex)?\s*\n(.*?)```", text, re.S)
    if blocks:
        tex = "\n\n".join(b.strip() for b in blocks if b.strip())
    else:
        tex = _strip_tex(text)
    m = re.search(r"\\title\{([^{}]*)\}", tex)
    title = (m.group(1).strip() if m else "") or title_hint
    # `\title` 里文件名转义了 LaTeX 特殊字符；界面显示用原始字符。
    title = (title.replace("\\_", "_").replace("\\&", "&")
             .replace("\\%", "%").replace("\\#", "#"))
    # 只读「未交付/待补」的第一张表，不能把后面的「原题号→第几块」表也吃进来。
    pending: list[dict] = []
    sec = re.split(r"未交付\s*/?\s*待补", text, maxsplit=1)
    if len(sec) > 1:
        body = sec[1]
        if re.match(r"\s*[：:]\s*无", body):
            body = ""
        lines = body.splitlines()
        start = -1
        for i, line in enumerate(lines):
            if "|" in line and "原因" in line:
                start = i + 1
                break
        if start >= 0:
            for line in lines[start:]:
                if not line.strip().startswith("|"):
                    if line.strip() == "" and pending:
                        break
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 3 or set(cells[0]) <= set("-: "):
                    continue
                no, page, reason = cells[0], cells[1], cells[2]
                if not no.isdigit():
                    continue
                pending.append({"no": no, "type": "", "reason": reason[:160],
                                "page": page, "tex": ""})
                if len(pending) >= 50:
                    break
    warnings: list[str] = []
    if not tex:
        warnings.append("模型没有返回 latex 代码块")
    return tex, title, pending, warnings


def run(data: bytes, *, name: str = "资料.pdf",
        answer_data: bytes | None = None, answer_name: str = "",
        dpi: int = deepseek.DEFAULT_DPI,
        fill_solutions: bool = False,
        on_progress=None, should_stop=None) -> dict:
    cfg = deepseek.load()
    if not cfg["api_key"]:
        raise deepseek.AIError("还没填 DeepSeek API Key")
    t0 = time.time()
    say = lambda d, t, m: on_progress and on_progress(d, t, m)  # noqa: E731
    stopped = lambda: bool(should_stop and should_stop())  # noqa: E731
    pngs = _pages(data, dpi)
    apngs = _pages(answer_data, dpi) if answer_data else []
    total = len(pngs)
    if not total:
        raise deepseek.AIError("这份 PDF 里没有页面")
    if total + len(apngs) > MAX_PAGES:
        raise deepseek.AIError(
            "这次共 %d 页（试题 %d + 答案 %d），超过单次上限 %d 页；请拆成多份"
            "（每份都带上对应的试题页和答案页）分别读取"
            % (total + len(apngs), total, len(apngs), MAX_PAGES))
    job = "spec-%s" % time.strftime("%Y%m%d-%H%M%S")
    job_dir = JOB_ROOT / job
    page_dir = job_dir / "pages"
    _save_pages(pngs, "q", page_dir)
    if apngs:
        _save_pages(apngs, "a", page_dir)
    if stopped():
        raise Cancelled("已取消")
    say(0, total, "正在按规范读取 %d 页…" % total)
    # 规范管线先按一次请求做；超过 MAX_PAGES 在入口已拒绝，避免悄悄分批漏题。
    images = pngs + apngs
    usage: dict = {}
    calls = 0

    def add_usage(u: dict) -> None:
        nonlocal calls
        calls += 1
        for k in ("prompt_tokens", "completion_tokens", "total_tokens",
                  "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
            try:
                usage[k] = int(usage.get(k) or 0) + int((u or {}).get(k) or 0)
            except (TypeError, ValueError):
                pass

    title_hint = Path(name).stem.replace("_试卷", "").replace("_答案", "")
    prompt = _prompt(list(range(1, total + 1)), total, len(apngs),
                     fill_solutions, name, title_hint)
    say(0, total, "正在按网页端同款规范生成 .tex…")
    raw = deepseek.chat(prompt, images, system=aispec.pdf_system_prompt(),
                        timeout=600, max_tokens=32000,
                        on_usage=add_usage)
    if stopped():
        raise Cancelled("已取消")
    tex, raw_title, pending, parse_warn = _extract_web(raw, title_hint)
    if not tex:
        raise deepseek.AIError("模型没有返回规范 latex 代码块")
    tex, fmt_changes = ai_format.clean(tex)
    # 网页端输出所有图都用 TikZ；不再 crop，也不接受 includegraphics。
    fig_problems: list[str] = []
    if "\\includegraphics" in tex:
        fig_problems.append("模型仍写了 includegraphics；网页要求图一律用 TikZ，请人工处理")
    # 标题/参数：网页端规定 title=文件名；本地再用文件名补 book/region。
    title = raw_title.strip() or title_hint
    ym = re.search(r"(?:19|20)\d{2}", title) or re.search(r"(?:19|20)\d{2}", title_hint)
    year = int(ym.group(0)) if ym else 0
    region = ""
    if "学" in title_hint or "卷" in title_hint:
        region = re.split(r"(?:19|20)\d{2}", title_hint)[0].strip(" _-")
    params = {"book": title, "label": title, "year": year, "region": region}
    # 先 preview，把规范复核结果交给界面；补考点由前端另调 `/api/ai/tag`。
    from . import ingest
    pv = ingest.preview(tex, src_dirs=[str(job_dir)], book=str(params["book"]),
                        label=title, year=year or None, region=region)
    items = pv.get("items") or []
    warnings = parse_warn + fig_problems
    if fmt_changes:
        warnings.append("本地格式清洗：" + "；".join(fmt_changes))
    if pv.get("errors"):
        warnings += [str(x)[:160] for x in pv.get("errors")[:3]]
    if pv.get("spec") and not pv["spec"].get("ok"):
        warnings.append("规范复核未通过：%d 条" % len(pv["spec"].get("after") or []))
    cost = deepseek.cost_cny(cfg["model"], usage)
    return {
        "ok": True, "latex": tex, "title": title,
        "params": params,
        "crop_dir": str(job_dir), "page_dir": str(page_dir),
        "items": items, "pending": pending,
        "coverage": {"expected": len(items) + len(pending),
                     "transcribed": len(items), "verified": len(items),
                     "missing": [], "flawed": [], "extra": [], "unverified": []},
        "problems": list(pv.get("errors") or []),
        "warnings": warnings,
        "stats": {"pages": total, "answer_pages": len(apngs),
                  "ok": len(items), "pending": len(pending), "verified": len(items),
                  "failed": 0, "calls": calls,
                  "generated_solutions": 0, "tagged_points": 0, "tag_failed": 0,
                  "format_fixes": len(fmt_changes),
                  "seconds": int(time.time() - t0), "model": cfg["model"],
                  "usage": usage, "cost_cny": cost},
    }


def _selftest() -> int:
    """不碰网络：假模型按网页端三段格式返回，验证 tex/标题/待补/preview。"""
    import tempfile
    from pathlib import Path as _Path
    import fitz as _fitz
    from . import deepseek as _ds

    tmp = _Path(tempfile.mkdtemp())
    pdf = tmp / "sample.pdf"
    d = _fitz.open()
    d.new_page(width=595, height=842).insert_text((72, 72), "sample")
    d.save(pdf)
    d.close()

    def fake_chat(prompt, images=None, *, system="", **kw):
        assert "PDF 题目录入格式要求" in system or "PDF 题目录入格式要求" in prompt
        return r"""```latex
\title{自检卷}
%% @q {"points":["1.1.1"],"difficulty":"简单题"}
\begin{question}
已知 $x=1$，则 $x+1=$ \paren[A]
\begin{choices}
\item $2$
\item $3$
\end{choices}
\end{question}
\begin{solution}
由 $x=1$，得 $x+1=2$，故选 A。
\end{solution}
```

未交付 / 待补：无

| 原题号 | 页码 | 第几块 | 状态 |
|---|---|---|---|
| 1 | 1 | 1 | 交付 |
"""

    old_load, old_chat = _ds.load, _ds.chat
    _ds.load = lambda: {"api_key": "selftest", "model": "mock", "pages_per_call": 6, "workers": 2}
    _ds.chat = fake_chat
    try:
        res = run(pdf.read_bytes(), name="selftest.pdf", fill_solutions=True)
        assert len(res["items"]) == 1, res
        assert res["items"][0]["points"] == ["1.1.1"], res["items"][0]
        assert "\\begin{question}" in res["latex"]
        assert res["title"] == "自检卷", res["title"]
        assert res["stats"]["ok"] == 1
        # 超限在入口就拒绝，报出真实页数，且不提交模型（fake_chat 没被调用）。
        big = tmp / "big.pdf"
        d = _fitz.open()
        for _ in range(MAX_PAGES + 1):
            d.new_page(width=595, height=842)
        d.save(big)
        d.close()
        try:
            run(big.read_bytes(), name="big.pdf")
            raise AssertionError("超限没有拒绝")
        except _ds.AIError as e:
            msg = str(e)
            assert "%d" % (MAX_PAGES + 1) in msg and "%d" % MAX_PAGES in msg, msg
    finally:
        _ds.load, _ds.chat = old_load, old_chat
    print("ai_spec 自检通过：网页格式 → tex → preview → 标签 1 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
