r"""OCR 质量对账：**找"块内掉行"，并把缺口补回来**。

## 为什么需要这个

实测（2026-10-28，唐山卷 p002）：版面检测到了第 1 题那一块
（`text`，bbox 135,1552–1802,1820），解析出的文本却**从 `A.` 开始**——
题干那行在识别阶段被丢了。块数还完全对得上（layout 10 块 / parsed 10 块），
所以"数块数"抓不到：丢的是**块内首行**。

掉行不报错，下游只会看到一道"没有题干的题"。这里做两件事：

1. **对账**：`text` 块以 `A.`/`B.`/`C.`/`D.` 开头 → 这个块从中间开始的，
   题干大概率丢了；再叠一层题号断档（声明 8 小题，实际只有 2/3/5/6）。
2. **补洞**：把那一块的图裁出来，交给常驻的 27B **只抄不补**地重读。

## 用法

    python3 -m amti.ocrcheck <一场考试的工作目录>
    python3 -m amti.ocrcheck <工作目录> --fill      # 顺手把可疑块重读一遍

退出码：有可疑块 → 1，全干净 → 0（可以挂进 accept）。
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

#: 选项标签打头 = 这个块不是从题干开始的
_OPT_HEAD = re.compile(r"^\s*[A-D][.．、]")

#: 题号：行首 `12.` / `12、` / `### 12.`
_NUM = re.compile(r"^\s*(?:#{1,6}\s*)?(\d{1,2})[.．、]")


def pages(work: Path) -> list[dict]:
    r"""工作目录 → 每页的 `{page, width, height, blocks, img}`。"""
    out = []
    for d in sorted((Path(work) / "paddle").glob("p[0-9][0-9][0-9]")):
        j = d / (d.name + "_res.json")
        if not j.is_file():
            continue
        res = json.loads(j.read_text(encoding="utf-8"))
        img = Path(work) / "pages" / (d.name + ".png")
        out.append({"page": int(d.name[1:]), "width": res.get("width"),
                    "height": res.get("height"),
                    "blocks": res.get("parsing_res_list") or [],
                    "img": img if img.is_file() else None})
    return out


def audit(page: dict) -> dict:
    r"""一页 → `{题号, 缺号, 可疑块}`。**只报不判**，交给人或 `--fill` 复核。"""
    blocks = page["blocks"]
    whole = "\n".join((b.get("block_content") or "").strip() for b in blocks)

    nums = []
    for line in whole.splitlines():
        m = _NUM.match(line)
        if m:
            nums.append(int(m.group(1)))
    # 只保留单调递增的题号，避免把年份、页码当成题号
    seq = [n for i, n in enumerate(nums) if i == 0 or n > nums[i - 1]]
    missing = [n for n in range(1, (max(seq) if seq else 0) + 1) if n not in seq]

    suspect = []
    for b in blocks:
        if b.get("block_label") != "text":
            continue
        t = (b.get("block_content") or "").strip()
        if t and _OPT_HEAD.match(t):
            suspect.append({"bbox": [int(x) for x in b["block_bbox"]],
                            "text": t[:60], "why": "块从选项开始，题干可能丢了"})
    return {"page": page["page"], "n_block": len(blocks), "题号": seq,
            "缺号": missing, "可疑块": suspect}


def crop(page: dict, bbox: list[int], pad: int = 12) -> Path:
    r"""按 bbox 裁一块图（带一点边距），返回临时文件。

    ⚠️ **bbox 的坐标系是 OCR 那张图，不是页图**：实测同一页
    `p002_res.json` 说 2339×3309，`pages/p002.png` 却是 1404×1985。
    直接拿 bbox 去裁页图，会裁到下一题去（我第一次就裁错了，模型照着
    错图抄回了第 5 题）。所以按两边尺寸等比换算。
    """
    from PIL import Image
    im = Image.open(page["img"])
    sx = im.width / float(page["width"] or im.width)
    sy = im.height / float(page["height"] or im.height)
    x0, y0, x1, y1 = (bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy)
    box = (max(0, int(x0) - pad), max(0, int(y0) - pad),
           min(im.width, int(x1) + pad), min(im.height, int(y1) + pad))
    dst = Path("/tmp") / ("ocrcheck_p%d_%d.png" % (page["page"], bbox[1]))
    im.crop(box).save(dst)
    return dst


def fill(page: dict, bbox: list[int], *, timeout: int = 300) -> str:
    r"""把一块裁图发给常驻的 27B，**只抄不补**地重读。

    提示词里"看不清写 □"是刻意的：堵死它"猜一个像样的字"的路。
    """
    import urllib.request
    from . import lms as L

    ok, why = L.ensure()
    if not ok:
        raise RuntimeError(why)
    b64 = base64.b64encode(crop(page, bbox).read_bytes()).decode()
    body = {"model": "qwen/qwen3.8-27b",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                {"type": "text",
                 "text": "只把图里的字原样抄下来，行内公式用 $…$，不要解释、不要补全。"
                         "看不清的字写 □。"}]}],
            "max_tokens": 400, "temperature": 0}
    req = urllib.request.Request(L.API + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=timeout))
    return (d["choices"][0]["message"].get("content") or "").strip()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    work = Path(argv[1])
    do_fill = "--fill" in argv
    pages_ = pages(work)
    bad = 0
    # 题号断档只在**全卷**层面说：按页看，第 3 页从 7 开始会被当成"缺 1–6"。
    seq: list[int] = []
    for page in pages_:
        for n in audit(page)["题号"]:
            if not seq or n > seq[-1]:
                seq.append(n)
    gaps = [n for n in range(1, (max(seq) if seq else 0) + 1) if n not in seq]
    print("全卷题号：%s" % (",".join(map(str, seq)) or "-"))
    if gaps:
        print("题号断档：缺 %s" % ",".join(map(str, gaps)))
    for page in pages_:
        r = audit(page)
        if not r["可疑块"]:
            continue
        print("\n=== 第 %d 页 ===（%d 块）" % (r["page"], r["n_block"]))
        for s in r["可疑块"]:
            bad += 1
            print("  ⚠ bbox=%s  %s" % (s["bbox"], s["why"]))
            print("    现有开头：%r" % s["text"])
            if do_fill:
                try:
                    print("    重读结果：%r" % fill(page, s["bbox"])[:120])
                except Exception as e:                        # noqa: BLE001
                    print("    重读失败：%s: %s" % (type(e).__name__, e))
    print("\n合计可疑块：%d" % bad)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
