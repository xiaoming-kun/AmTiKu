#!/usr/bin/env python3
r"""L0：文件角色 与 页面几何。

**这是 v2 录题架构的第一层**（见 `设计/录题顶层设计-v2.md`）。
它只回答两个问题，两个都是**几何/命名问题，不该问模型**：

1. 这份 PDF 是**什么角色**——试卷 / 答案 / 答题卡 / 其他。
   旧代码（`record.pick_main`）只看文件名，于是 `数学答题卡.pdf`
   被当成答案卷喂进了管线，答题卡上的「15.（本小题满分13分）」被当成了
   答案块（台账 D06）。

2. 这一页是不是**两页拼扫**（横版），是的话从哪切开。
   旧代码整页丢给 OCR，横版页的阅读顺序会错乱、成块的选项会丢
   （台账 D05：整页 OCR 2019 字、`A.` 只 2 个；同一页单条带 OCR 有 5 个）。

**为什么单独一个模块**：页面几何是纯函数，不该和"跟模型打交道"混在
`record.py`（已 2500 行）里。这里不导入 record，也不碰网络和模型。
"""
from __future__ import annotations

import re
from pathlib import Path

# ── ① 文件角色 ──────────────────────────────────────────────────────
#
# **答题卡是空白卡，本来就没有答案。** 它不是"低优先级的答案卷"，
# 而是"绝不该进管线的东西"——上面的文字全是作答说明和题号分值。
_SHEET = re.compile(r"答题卡|答题纸|作卡|answer[\s_-]*sheet", re.I)
_ANSWER = re.compile(r"答案|解析|详解|评分标准|评分细则|参考答案|DA\b|教师版|教师用"
                     r"|答案与解析|试题答案|数学答案|全解全析", re.I)
# 卷面上出现这些词，几乎可以断定是答题卡（哪怕文件名没写）
_SHEET_TEXT = re.compile(r"贴条形码区|准考证号|填涂样例|超出黑色矩形边框|"
                         r"请在各题目的答题区域内作答|2B\s*铅笔")

# 角色
PAPER, ANSWER, SHEET, OTHER = "试卷", "答案", "答题卡", "其他"


def role_of(name: str, first_page_text: str = "") -> str:
    r"""文件名（+ 可选的首屏文字）→ 角色。

    判据顺序**不能颠倒**：

    1. 先认答题卡。它同时可能命中「答案」吗？不会——但文件名里
       「数学答题卡」和「数学答案」长得像，而**答题卡的危害最大**
       （整页文字进正文），所以先判它。
    2. 再认答案卷。
    3. 首屏文字是**兜底**：文件名干净但内容是答题卡的情况（实测有）。
    4. 都不像 → 试卷。
    """
    stem = Path(name or "").stem
    if _SHEET.search(stem):
        return SHEET
    if first_page_text and _SHEET_TEXT.search(first_page_text):
        return SHEET
    if _ANSWER.search(stem):
        return ANSWER
    return PAPER


def pick_pdfs(pdfs: list[Path]) -> tuple[Path | None, list[Path], list[Path]]:
    r"""一场考试的 PDF 目录 → `(试题, [答案…], [答题卡…])`。

    比旧 `pick_main` 多两件事：

    * **答题卡单独拎出来**，调用方直接无视（不喂模型、不进管线）。
    * **试题找不到时返回 None**，而不是"拿第一份凑数"——旧代码那句
      `main = pdfs[0]` 正是把答题卡/答案卷当试题的入口。
    """
    papers, answers, sheets = [], [], []
    for p in sorted(pdfs):
        r = role_of(p.name)
        (sheets if r == SHEET else answers if r == ANSWER else papers).append(p)
    return (papers[0] if papers else None), answers, sheets


# ── ② 横版双页对切 ──────────────────────────────────────────────────
#
# 判据：宽 > 高 × 1.15。扫描件里「一页」的正常比例约 1:1.41（A4 竖版），
# 两张 A4 并排是 ≈1.41:1，所以 1.15 这条线两边差得很开，不会误判。
SPREAD_RATIO = 1.15


def is_spread(size: tuple[int, int]) -> bool:
    """(宽, 高) 是不是两页拼扫。"""
    w, h = size
    return bool(h) and w > h * SPREAD_RATIO


def gutter_x(gray, x0: int = 0, x1: int | None = None, *, win: float = 0.30,
             dark: int = 200) -> int | None:
    r"""在中间找那条**竖向空白缝**，返回切分位置；找不到返回 None。

    `gray` 是 `numpy` 二维数组（0=黑，255=白）；只依赖 numpy，不引 OpenCV。

    做法：取中间 `win` 比例（默认 ±15%）的列，算每列的"暗像素"个数，
    取最小的一列；**该列必须几乎没有字**才算缝——判据是"这一列的暗像素
    ≤ 全页最密一列的 3%"。最后再要求缝**够宽**（≥ 页宽的 0.5%），
    免得切在一个字的笔画之间。

    ⚠️ 阈值必须拿**同一量纲**比：一开始写成"该列暗像素 < 全页暗像素总数的
    0.5%"，而总数是所有行累加的结果，比单列大三个数量级——于是**满页是字的
    图也能通过**（实测直接切在正文中间）。现在拿"最密的一列"当基准。
    """
    import numpy as np

    h, w = gray.shape
    full = (gray < dark).sum(axis=0)             # 整页每列的暗像素
    ref = float(full.max())
    if ref <= 0:
        return None                              # 全白：没有内容，谈不上缝
    thr = max(2.0, ref * 0.03)
    lo = x0 + int(w * (0.5 - win / 2))
    hi = x0 + int(w * (0.5 + win / 2))
    lo, hi = max(x0, lo), min(w, hi)
    if hi - lo < 4:
        return None
    col = full[lo:hi]
    # 取窗口里**最宽的一条空白带**。
    # ⚠️ 不能用 `argmin` 挑"最空的那一列"：最空的列往往是正文里的一条
    # 5 像素小缝（实测衡水金卷那张：旁边 x1107-1111 宽 5，真缝在 x1132-1248
    # 宽 117），argmin 取到小的那条就把整页判成"切不开"。
    runs: list[tuple[int, int]] = []
    start = None
    for k in range(len(col)):
        if col[k] <= thr:
            start = k if start is None else start
        elif start is not None:
            runs.append((start, k - 1))
            start = None
    if start is not None:
        runs.append((start, len(col) - 1))
    if not runs:
        return None
    a, b = max(runs, key=lambda r: r[1] - r[0])
    if b - a + 1 < max(2, w // 200):
        return None                              # 缝太窄，切下去会伤到字
    return lo + (a + b) // 2


def split_spread(img: Path, out_dir: Path) -> list[Path]:
    r"""横版页 → 左右两张图；竖版页原样返回 `[img]`。

    输出命名在原名后加 `_L` / `_R`（`p001.png` → `p001_L.png`、`p001_R.png`），
    调用方按 `_L` 在前、`_R` 在后拼页面顺序。

    **切不开就不切**（返回 `[img]`）：宁可让这一页继续走"整页 OCR"，
    也不能把一个字切成两半——切开的一半会变成两道残题。
    """
    from PIL import Image
    import numpy as np

    im = Image.open(img)
    if not is_spread(im.size):
        return [img]
    gray = np.asarray(im.convert("L"))
    x = gutter_x(gray)
    if x is None:
        return [img]
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for tag, box in (("_L", (0, 0, x, im.height)),
                     ("_R", (x, 0, im.width, im.height))):
        dst = out_dir / (img.stem + tag + img.suffix)
        im.crop(box).save(dst)
        out.append(dst)
    return out


def _selftest() -> int:
    """回归用例。**只测纯函数**，不碰文件、不碰模型。"""
    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("pagegeom 自检")

    # 角色：**答题卡必须优先于答案**（文件名「数学答题卡」也含"答案"吗？不含，
    # 但「答题卡答案」这种会同时像两者——先判卡）
    check("答题卡：数学答题卡.pdf", role_of("数学答题卡.pdf") == SHEET)
    check("答题卡：答题纸", role_of("高三数学答题纸.pdf") == SHEET)
    check("答题卡：Answer Sheet", role_of("Math-Answer-Sheet.pdf") == SHEET)
    check("答题卡：文件名叫「答题卡答案」也先判卡",
          role_of("答题卡答案.pdf") == SHEET, role_of("答题卡答案.pdf"))
    check("答案：十一校数学答案.pdf", role_of("十一校数学答案.pdf") == ANSWER)
    check("答案：评分标准", role_of("数学参考答案及评分标准.pdf") == ANSWER)
    check("答案：教师版", role_of("（教师版）雅礼月考四数学.pdf") == ANSWER)
    check("答案：全解全析", role_of("2026某市一模全解全析.pdf") == ANSWER)
    check("试卷：数学试题.pdf", role_of("数学试题.pdf") == PAPER)
    check("试卷：没线索的名字", role_of("scan_001.pdf") == PAPER)
    check("首屏文字兜底：文件名干净但内容是答题卡",
          role_of("2026届高三数学.pdf", "贴条形码区\n准考证号\n请在各题目的答题区域内作答")
          == SHEET)
    check("首屏文字不误伤：题干里出现'答题'不算答题卡",
          role_of("数学试题.pdf", "一、选择题：本题共8小题") == PAPER)

    # pick_pdfs：答题卡不进答案侧；没有试题就返回 None
    from pathlib import Path as _P
    m, a, s = pick_pdfs([_P("十一校数学答案.pdf"), _P("十一校数学试卷.pdf"),
                         _P("数学答题卡.pdf")])
    check("pick_pdfs：试题在前、答题卡单独拎出",
          m.name == "十一校数学试卷.pdf" and [x.name for x in a] == ["十一校数学答案.pdf"]
          and [x.name for x in s] == ["数学答题卡.pdf"], "%s %s %s" % (m, a, s))
    m2, _a2, _s2 = pick_pdfs([_P("数学答题卡.pdf"), _P("数学答案.pdf")])
    check("pick_pdfs：全是答案/答题卡时返回 None（不许拿第一份凑数）", m2 is None,
          str(m2))

    # 横版判定：A4 竖版 1:1.41 不算，两张并排 ≈1.41:1 算
    check("竖版 A4 不是拼扫", not is_spread((1240, 1754)))
    check("横版双页是拼扫", is_spread((2193, 1419)))
    check("接近正方（扫描裁边）不算拼扫", not is_spread((1500, 1400)))

    # 切缝：造两张"有字的纸"并排，中间留白
    try:
        import numpy as np
        page = np.full((600, 1200), 255, dtype=np.uint8)
        page[50:550, 60:520] = 0          # 左页有内容
        page[50:550, 680:1140] = 0        # 右页有内容 → 缝在 600 附近
        x = gutter_x(page)
        check("找到中间的竖向空白缝", x is not None and 520 <= x <= 680, str(x))
        solid = np.zeros((600, 1200), dtype=np.uint8)   # 满页是字 → 没有缝
        check("满页是字时不硬切", gutter_x(solid) is None, str(gutter_x(solid)))
    except ImportError:                    # pragma: no cover
        print("  ⚠ 没装 numpy，跳过切缝用例")

    print("pagegeom 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
