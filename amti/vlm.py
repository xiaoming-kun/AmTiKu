r"""本地视觉模型：图片 / PDF → LaTeX。

## 它只做一件事

**把图变成文本，什么都不写。** 产物交给 `amti/ingest.py` 的
`preview` → 人工审阅 → `commit` 那条现成管线。

这一点是刻意的：录入的规范校验、查重、图片入库、影响面审计
只在 `ingest` 里有，这里再写一条写库路径必然分叉（AGENTS.md 第三节）。
所以本模块**没有**任何 `store` / `rewrite` 调用。

## 流程

    图片 ──┐
           ├─→ 视觉模型 ─→ LaTeX 文本 ─→ 录入框 ─→ preview（干跑）
    PDF  ──┘                                          ↓
                                              人看一眼，点确认
                                                     ↓
                                                  commit

PDF 用 `fitz`（PyMuPDF）逐页转图再喂给模型——模型只认图片，
不能直接吞 PDF 字节。
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import lms

#: 请求里 `"model"` 字段。llama.cpp 只加载了一个模型，这个值它不看，
#: 但 OpenAI 协议要求有，所以给个能看懂的名字。
MODEL = "paddleocr-vl"

# ── 后备：PaddleOCR-VL 不在时，用已在跑的 27B（LM Studio :1234）读图 ──
#
# 2026-10-26 起读图模型（paddleocr-vl / dots.ocr）已从 LM Studio 删掉，
# 全卷识别走 PaddleOCR-VL（见 `amti/paddle.py`）。单题截图这条路还留着，
# 但模型没了就会报「找不到模型文件」——于是加一个后备：直接问 27B。
# 它是多模态的，且已经为「结构化」常驻，不必再拉一个服务。
SOLVE_API = lms.API + "/chat/completions"
SOLVE_MODEL = "qwen/qwen3.8-27b"
LATEX_PROMPT = (
    "把图片里的题目转成 exam-zh LaTeX，只输出 LaTeX，不要解释：\n"
    "题干用 \\begin{question}…\\end{question}，解析用 "
    "\\begin{solution}…\\end{solution}；选择题选项用 "
    "\\begin{choices}\\item … \\end{choices}；行内公式用 $…$。")

#: paddleocr-vl 的提示词。**实测有效**：图片 → `A.240 B.280`、
#: `\(y\uparrow\)`（公式以 LaTeX 出来）。
PROMPT = "OCR:"

#: PDF 渲染到多少 DPI。200 够看清公式上下标，再高只是白烧时间。
PDF_DPI = 200

#: 单次请求的超时。视觉模型首帧要预热，给宽一点。
TIMEOUT = 300

#: **一次只发一页。**
#:
#: ⚠️ 实测（2026-10-03）：`paddleocr-vl` 收到多张图时**只处理第一张，
#: 其余静默丢掉**。两页的 PDF 一起发，返回的只有第 1 页内容——
#: 不报错、不缺页提示，就是少了一半。这种"静默丢内容"最危险，
#: 所以宁可一页一个请求。
#:
#: 代价是慢一点（实测每页 1–3 秒），换来的是**不会静默丢页**。
#: 另一个好处：不用再猜模型的上下文能装几页。


def _data_url(data: bytes, mime: str) -> str:
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())


def _sniff(data: bytes) -> tuple[str, str]:
    r"""字节头 → `(扩展名, MIME)`。

    ⚠️ 原来一律当 PNG 发、临时文件也一律叫 `.png`——截图是 JPEG 时，
    `paddle.parse_file` 按扩展名解码会报错，模型那边也会收到错误的 MIME。
    按魔数认最省事，也不怕文件名骗人。
    """
    if data[:5] == b"%PDF-":
        return "pdf", "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if data[:2] in (b"II", b"MM"):
        return "tif", "image/tiff"
    # 认不出就当 PNG：让下游报"解不开"比在这里瞎猜强
    return "png", "image/png"


def pdf_pages(data: bytes, dpi: int = PDF_DPI) -> list[bytes]:
    r"""PDF 字节 → 每页一张 PNG。**只读，不落盘。**

    直接拿 PDF 字节喂模型是不行的——模型只认图片。所以必须先栅格化。
    """
    import fitz                                     # PyMuPDF
    out: list[bytes] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            out.append(pix.tobytes("png"))
    return out


def _chat(images: list[bytes], prompt: str, model: str,
          api: str | None = None) -> tuple[str, dict]:
    r"""把若干张图 + 一句话发给模型，返回 `(正文, 元信息)`。

    多张图**一次请求**发出去（PDF 的每一页）——逐页分开请求会
    丢掉"跨页同一道题"的上下文，而卷子里跨页是常态。

    ⚠️ 两条路要唤的不是同一个服务：
      · 默认（`api=None`）走 llama.cpp :1235（paddleocr-vl）→ `ensure_vision()`
      · 显式给 `api`（27B 顶班）走 LM Studio :1234 → `ensure_ctx()`
    原来不分青红皂白调 `ensure_ctx(model)`，等于去 LM Studio 等一个
    llama.cpp 上的模型；而且 `need_tokens=len(text)` 里的 `text` 根本不存在，
    一调用就 `NameError`——这条路此前从没跑通过。
    """
    mimes = [_sniff(im)[1] for im in images]
    content: list[dict] = [
        {"type": "image_url", "image_url": {"url": _data_url(im, mime)}}
        for im, mime in zip(images, mimes)]
    content.append({"type": "text", "text": prompt})

    ident = model
    if api:
        # 27B 顶班：图会占掉不少 token，按"每页约 1.5k + 提示词"估一个下限
        need = len(prompt) // 2 + 1500 * len(images) + 8192
        ok, ident, why = lms.ensure_ctx(model, need_tokens=need)
        if not ok:
            raise RuntimeError(why)
    else:
        ok, why = lms.ensure_vision()
        if not ok:
            raise RuntimeError(why)

    payload = {"model": ident, "messages": [{"role": "user", "content": content}],
               "temperature": 0.1, "max_tokens": 8000}
    req = urllib.request.Request(
        api or (lms.VISION_API + "/chat/completions"),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(_explain_http(e.code, body, model)) from None
    ch = d["choices"][0]
    usage = d.get("usage") or {}
    return (ch["message"]["content"] or ""), {
        "seconds": round(time.time() - t0, 1),
        "finish_reason": ch.get("finish_reason") or "",
        "prompt_tokens": usage.get("prompt_tokens"),
        "model": model,
    }


def _need_tokens(text: str) -> int:
    r"""粗估中文/公式混排要多少 token（1 token ≈ 2 字符，另留 8k 输出）。

    只用来决定"要不要按更大上下文重载"，估大一点没坏处（多占点内存），
    估小了就是 HTTP 400 + 整卷白跑。
    """
    return len(text) // 2 + 8192


def _chat_text(text: str, prompt: str, model: str) -> tuple[str, dict]:
    r"""纯文本请求（不带图）。PaddleOCR 已经把字认完，这里只让 27B 改格式。"""
    # **先按输入长度确保上下文**：整卷十几页文本直接塞给按 8192 起的模型，
    # 换来的是一句看不出原因的 `HTTP 400 Bad Request`（`ensure_ctx` 顶上写着）。
    ok, ident, why = lms.ensure_ctx(model, need_tokens=_need_tokens(text + prompt))
    if not ok:
        raise RuntimeError(why)
    payload = {"model": ident,
               "messages": [{"role": "user", "content": prompt + "\n\n" + text}],
               "temperature": 0.1, "max_tokens": 8000}
    req = urllib.request.Request(
        SOLVE_API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        raise RuntimeError(_explain_http(e.code, body, model)) from None
    ch = d["choices"][0]
    return (ch["message"]["content"] or ""), {
        "seconds": round(time.time() - t0, 1),
        "finish_reason": ch.get("finish_reason") or "",
        "prompt_tokens": (d.get("usage") or {}).get("prompt_tokens"),
        "model": model,
        "note": why,
    }


def _explain_http(code: int, body: str, model: str) -> str:
    r"""把 HTTP 错误翻成人话。

    ⚠️ 专门认 `does not support image inputs` 这句：这是**最可能踩的坑**
    ——模型文件下好了，但运行时没把视觉投影（mmproj）配上，
    于是它被当成纯文本模型。这时报错原文是英文的，
    不说清等于让人对着"400 Bad Request"猜半天。
    """
    if "does not support image inputs" in body:
        return ("模型 `%s` 不能读图 —— 运行时没给它配上视觉投影（mmproj）。\n"
                "**LM Studio 配不好这一步**（实测它把 mmproj 当成独立模型，"
                "调接口直接报这句）。\n"
                "读图走 llama.cpp：`llama-server -m <模型>.gguf "
                "--mmproj <视觉投影>.gguf`（详见 amti/lms.py 顶部注释）" % model)
    return "模型接口返回 %s：%s" % (code, body[:400])


def extract(data: bytes, name: str = "upload.png", *,
            model: str = MODEL, dpi: int = PDF_DPI,
            prompt: str = PROMPT) -> dict:
    r"""图片或 PDF 的字节 → LaTeX 文本。**不落盘、不写库。**

    返回 `{latex, pages, name, model, seconds, warnings}`。
    PDF 的每一页转成图后一起发给模型，页与页之间用注释标出边界，
    人审阅时能看出模型是在哪一页换的。
    """
    if not data:
        raise ValueError("空文件")
    ext, _mime = _sniff(data)
    is_pdf = ext == "pdf"
    warnings: list[str] = []

    # ── 首选：PaddleOCR-VL 认字 → 27B 改格式 ─────────────────────────
    # 识别只负责"把字读准"，格式改写交给 27B——两件事分开，出错好定位。
    # ⚠️ 这条路**失败要能退回去**：原来 `parse_file` 或 27B 一出错就整条
    # 请求 503，明明还有"27B 直接看图"这条后备。Paddle 没装好属于常态。
    from . import paddle
    ok_p, why_p = paddle.available()
    if ok_p:
        t0 = time.time()
        tmpdir = Path(tempfile.mkdtemp(prefix="vlm-"))
        try:
            src = tmpdir / ("in." + ext)
            src.write_bytes(data)
            md = paddle.parse_file(src)
            ok, why = lms.ensure(SOLVE_MODEL)
            if not ok:
                raise RuntimeError(why)
            latex, meta = _chat_text(md, LATEX_PROMPT, SOLVE_MODEL)
            if not (latex or "").strip():
                raise RuntimeError("27B 没有返回任何 LaTeX（识别到的原文 %d 字）" % len(md))
            pages = max(1, md.count("<!-- page "))
            notes = ["PaddleOCR-VL 识别 → 27B 转 exam-zh LaTeX"]
            if meta.get("note") and "已在内存" not in meta["note"]:
                notes.append(str(meta["note"]))
            if meta.get("finish_reason") == "length":
                notes.append("输出被 max_tokens 截断：成品末尾可能缺解析——"
                             "这一份请重点看最后一道题")
            return {"latex": latex.strip(), "pages": pages, "name": name,
                    "model": "paddleocr-vl+" + SOLVE_MODEL,
                    "seconds": round(time.time() - t0, 1),
                    "warnings": notes}
        except Exception as e:                              # noqa: BLE001
            # 落到后备之前先把原因留给人看，别让"为什么慢/为什么换了模型"成谜
            warnings.append("PaddleOCR-VL 这条路没走通（%s），改用 27B 直接读图"
                            % str(e)[:160])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    chat_api = None
    why = ""
    if lms.VISION_MODEL.is_file():
        ok, why = lms.ensure_vision()
        if not ok:
            # 视觉模型文件在、但运行时没配好 mmproj（LM Studio 的常见状态）。
            # 这时**不要**把请求整条打回——27B 本来就是常驻的、也能看图，
            # 换它顶一下，比让人对着 503 猜原因强。
            warnings.append("读图模型起不来（%s），改用 `%s` 直接读图"
                            % (str(why)[:160], SOLVE_MODEL))
            ok, why = lms.ensure(SOLVE_MODEL)
            if not ok:
                raise RuntimeError(why)
            chat_api, model, prompt = SOLVE_API, SOLVE_MODEL, LATEX_PROMPT
    else:
        # 读图模型不在了 → 用常驻的 27B 顶一下（提示词也换成"直接出 LaTeX"）
        ok, why = lms.ensure(SOLVE_MODEL)
        if not ok:
            raise RuntimeError(why)
        chat_api, model, prompt = SOLVE_API, SOLVE_MODEL, LATEX_PROMPT
        warnings.append("没装 PaddleOCR-VL，改用 `%s` 读图" % SOLVE_MODEL)
    if why and "已在内存" not in why:
        warnings.append(why)          # 记下"这次起了多久"，方便判断是不是冷启动慢

    if is_pdf:
        images = pdf_pages(data, dpi)
    else:
        images = [data]

    # **逐页请求**：一次发多张会静默丢页（见文件头 `PROMPT` 附近的说明）。
    # 多页时在页与页之间插一行注释，人审阅时看得见页码边界，
    # 模型自己认不出的"跨页同一道题"也能据此人工拼回。
    parts: list[str] = []
    meta: dict = {}
    for i, im in enumerate(images):
        if len(images) > 1:
            parts.append("%% ── 第 %d 页 ──" % (i + 1))
        t, meta = _chat([im], prompt, model, api=chat_api)
        parts.append(t)
    text = "\n\n".join(parts)

    if len(images) > 1:
        warnings.append("共 %d 页，已逐页识别，页之间用 `%%%% ── 第 N 页 ──` 标出；"
                        "跨页的同一道题请留意" % len(images))

    return {"latex": text.strip(), "pages": len(images), "name": name,
            "model": model, "seconds": meta.get("seconds"),
            "warnings": warnings}


def _selftest() -> int:
    r"""自检**不需要模型**：测的全是纯函数（PDF→图、data URL、报错翻译）。

    真正调模型的那段没法在这里测——它要么依赖 LM Studio，
    要么依赖一个假的 HTTP 服务。留一个手工验收入口更划算：
    `python -m amti.vlm 待录入图片/xxx.png`
    """
    import io
    import struct
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        print("  %s %s%s" % ("✓" if cond else "✗", name, "" if cond else "  ← " + str(extra)))
        if not cond:
            fails += 1

    def _png_bytes() -> bytes:
        """一张最小的真 PNG（用 PIL 造，别手写字节）。"""
        import io as _io
        import PIL.Image
        buf = _io.BytesIO()
        PIL.Image.new("RGB", (60, 30), (0, 0, 0)).save(buf, "PNG")
        return buf.getvalue()

    print("vlm 自检")

    check("data URL 形状正确",
          _data_url(b"abc", "image/png") == "data:image/png;base64,YWJj",
          _data_url(b"abc", "image/png"))

    # 真造一个一页 PDF，验证栅格化确实出图
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=200, height=120)
        page.insert_text((20, 60), "x^2 + 1 = 0")
        buf = doc.tobytes()
        doc.close()
        check("认得 PDF 魔数", buf[:5] == b"%PDF-", buf[:8])
        pages = pdf_pages(buf, dpi=100)
        check("PDF → 1 张图", len(pages) == 1, len(pages))
        check("产出的是 PNG", pages[0][:8] == b"\x89PNG\r\n\x1a\n", pages[0][:8])
        check("图有实际内容（不是 0 字节）", len(pages[0]) > 500, len(pages[0]))
        import PIL.Image
        with PIL.Image.open(io.BytesIO(pages[0])) as im:
            check("图像尺寸符合 dpi（200×120 @100dpi ≈ 278×167）",
                  250 < im.width < 300 and 150 < im.height < 190,
                  "%dx%d" % (im.width, im.height))
    except ImportError:
        print("  ⚠ 没装 PyMuPDF，跳过 PDF 栅格化检查")

    # 图像字节要按魔数认，不能一律当 PNG：截图多是 JPEG，
    # 临时文件叫 `.png` 会让 Paddle 按错格式解码、模型收到的 MIME 也是错的。
    check("JPEG 字节认得出（不是当 PNG）", _sniff(b"\xff\xd8\xff\xe0abc")[:2]
          == ("jpg", "image/jpeg"), _sniff(b"\xff\xd8\xff\xe0abc"))
    check("PNG 字节认得出", _sniff(_png_bytes())[0] == "png")
    check("PDF 字节认得出", _sniff(b"%PDF-1.7\n")[0] == "pdf")

    # 报错翻译：这句英文是**必须认出来**的，否则用户对着 400 猜
    msg = _explain_http(400, '{"error":{"message":"The provided messages contain '
                             'images, but ppocr does not support image inputs."}}',
                        "ppocr")
    check("认得出「模型不能读图」并给可执行建议",
          "mmproj" in msg and "llama-server" in msg and "LM Studio" in msg, msg[:90])
    other = _explain_http(500, "boom", "m")
    check("其他错误照原样带出", "500" in other and "boom" in other, other)

    # **一次只发一页**——这是正确性要求，不是性能取舍。
    # 要真调模型才测得到，所以把 `_chat` 换掉、数调用次数：
    # 两页的 PDF 必须产生**两次**请求，否则就是又在静默丢页。
    #
    # ⚠️ 这台机器上 PaddleOCR 是装好的，`extract()` 会走 Paddle→27B，
    # 自检就变成"必须开模型"（而且真烧几分钟）。所以这里把 Paddle 这条路
    # 明确关掉、把两个 `lms` 唤起函数换成假的，只测**逐页请求**的编排。
    from . import paddle as _paddle
    _old_avail, _old_parse = _paddle.available, _paddle.parse_file
    _old_ensure, _old_ev = lms.ensure, lms.ensure_vision
    _old_vm = lms.VISION_MODEL
    _paddle.available = lambda: (False, "自检强制走后备")
    lms.ensure = lambda *_a, **_k: (True, "自检")
    lms.ensure_vision = lambda *_a, **_k: (True, "自检")
    lms.VISION_MODEL = Path(__file__)          # 只要"文件存在"，让 _chat 走 :1235
    try:
        import fitz as _fitz
        d2 = _fitz.open()
        for txt in ("first page", "second page"):
            d2.new_page(width=300, height=200).insert_text((20, 60), txt)
        two_page = d2.tobytes()
        d2.close()

        def count_calls(pdf_bytes, name, **kw):
            seen: list[int] = []
            real = globals()["_chat"]

            def fake(images, prompt, model, api=None):
                seen.append(len(images))
                return "page-%d" % len(seen), {"prompt_tokens": 1}
            globals()["_chat"] = fake
            try:
                return extract(pdf_bytes, name, **kw), seen
            finally:
                globals()["_chat"] = real

        r2, calls = count_calls(two_page, "two.pdf", dpi=100)
        check("两页 PDF → 两次请求（不是一次塞两页）", calls == [1, 1], calls)
        check("两页的内容都在结果里",
              "page-1" in r2["latex"] and "page-2" in r2["latex"], r2["latex"][:80])
        check("页与页之间有页码注释",
              "第 1 页" in r2["latex"] and "第 2 页" in r2["latex"], r2["latex"][:80])

        # 单页图片：一次请求就够
        r1, calls1 = count_calls(_png_bytes(), "one.png", dpi=100)
        check("单页图片 → 一次请求", calls1 == [1], calls1)
        check("单页时不插页码注释（多余）", "第 1 页" not in r1["latex"], r1["latex"][:60])

        # Paddle 那条路**挂了要能退回去**，而不是把整条请求打死。
        _paddle.available = lambda: (True, "自检假装装了")
        def _boom(_p):
            raise RuntimeError("假装 Paddle 崩了")
        _paddle.parse_file = _boom
        r3, calls3 = count_calls(_png_bytes(), "one.png", dpi=100)
        check("Paddle 崩了 → 退回逐页读图，不 503",
              calls3 == [1] and "page-1" in r3["latex"], (calls3, r3["latex"][:40]))
        check("退回时把原因写进 warnings",
              any("PaddleOCR-VL" in w and "没走通" in w for w in r3["warnings"]),
              r3["warnings"])
    except ImportError:
        print("  ⚠ 没装 PyMuPDF，跳过逐页请求检查")
    finally:
        _paddle.available, _paddle.parse_file = _old_avail, _old_parse
        lms.ensure, lms.ensure_vision = _old_ensure, _old_ev
        lms.VISION_MODEL = _old_vm

    # 空文件必须拒，不能把空字节发出去
    try:
        extract(b"")
        check("空文件被拒", False, "没抛异常")
    except ValueError:
        check("空文件被拒", True)
    except RuntimeError as e:
        check("空文件被拒（在调模型前）", False, "走太远了：%s" % e)

    print("vlm 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    import sys as _s
    if "--selftest" in _s.argv:
        raise SystemExit(_selftest())
    if len(_s.argv) > 1:
        # 手工验收：真调一次模型
        import pathlib
        p = pathlib.Path(_s.argv[1])
        r = extract(p.read_bytes(), p.name)
        print("模型:", r["model"], "| 页数:", r["pages"], "| 用时:", r["seconds"], "秒")
        for w in r["warnings"]:
            print("⚠", w)
        print("─" * 60)
        print(r["latex"][:2000])
        raise SystemExit(0)
    print(__doc__)
    raise SystemExit(0)
