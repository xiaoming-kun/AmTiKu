"""AmMath · **排版参数（唯一来源）**

这些数字原来散在 `paper.py` 里十几处：`0.5\\textheight` / `0.58\\textheight`
的 `\\needspace`、`0.16` / `0.20` / `0.32\\textheight` 的图高、`0.18` /
`0.24` / `0.30\\textwidth` 的图宽、`3/5/8cm` 的解答题留白……改一个忘一个，
而且过半年没人说得清"为什么是 0.5 不是 0.6"。

**凡是要调排版，只改这里。** `paper.py` 按名字取用，`测试/排版回归.py`
比对指标时也读这里的版本号——参数一改，金样回归就该重新确认。

分组：

  * `NEED_*`     —— 分页预留（`\\needspace`），"这块放不下就提前断页"
  * `FIG_*`      —— 图片尺寸上限（高按 `\\textheight`、宽按 `\\textwidth`）
  * `OPT_*`      —— 选项排版（列数、每张图的槽宽）
  * `BLANK_*`    —— 解答题留白
  * `HANDOUT_*`  —— 讲义（一题一页）专用

为什么宽高都按版心记而不是 `\\linewidth`：exam-zh 的 `choices` 是**按列**排的，
多列时 `\\linewidth` 就是那一列的宽度（四列只剩 ~100pt），
`0.21\\linewidth` 实际只有 20pt——2026-11-13 踩过一次，"横排"反而把图缩没了。
"""

from __future__ import annotations

# 参数一变（或"为什么这么定"变了）就 +1：排版档案缓存按它失效。
VERSION = 1

# ── 分页预留 ──────────────────────────────────────────────────────────
# 普通题：题干 2–3 行 + 选项 2 行，留 6 行就够。
NEED_NORMAL = r"6\baselineskip"
# 选项带图的题：**别一上来就按半页预留**。图选项现在压得更小、还排成一行，
# 预留 0.40 页就够；真被拆页了跨页修复循环（`export` 的第二遍）会把这题推到新页，
# 代价只是一次重编译——比"页底空出小半页"划算。
NEED_IMG_OPT = r"0.40\textheight"
# 分节标题：标题 + 首题开头，至少 12 行。
NEED_SECTION = r"12\baselineskip"
# 分节标题下首题就带图选项：跟题一起留 0.58 页。
NEED_SECTION_IMG = r"0.58\textheight"
# 跨页修复：已知会跨页的题，直接从新页开始（`\needspace{\textheight}` 等价于强制断页）。
NEED_HARD_BREAK = r"\textheight"

# ── 排版溢出 ──────────────────────────────────────────────────────────
# 小于这个宽度（pt）的 Overfull **不当问题**：0.1cm 以下在纸上根本看不出来，
# 但 TeX 照样报。全报会让"排版检查"每份卷子都挂一条噪声警告。
OVERFULL_PT = 3.0

# 行间公式超过这个溢出量就**不自动缩**了：A4 版心约 451pt，超 300pt 意味着
# 缩完只剩六成字号——字会糊成一条线，还不如让它出血 + 报出来让人拆行。
# （实测 879pt 那道题缩完只有 34% 大小，完全没法看。）
MATH_FIT_MAX_PT = 300.0


# ── 图片尺寸上限 ──────────────────────────────────────────────────────
# 题干里独立成行的图：不超过小半页高（讲义一题一页时放宽到 0.46）。
FIG_H_STEM = r"0.26\textheight"
FIG_H_HANDOUT = r"0.40\textheight"
# 图选项：一行多张时高度上限可以放宽（只占一层），2×2 网格时收紧。
FIG_H_OPT_ROW = r"0.20\textheight"
FIG_H_OPT_GRID = r"0.16\textheight"
# 独立图没有写宽度时补的上限（写了 width 的尊重作者）
FIG_W_STEM = r"0.85\textwidth"

# ── 选项排版 ──────────────────────────────────────────────────────────
# 每张选项图占的槽宽 = 版心 × SLOT_RATIO / 列数（4 列 → 0.18、3 列 → 0.24）
OPT_SLOT_RATIO = 0.72
# 卷面：几张图以上才按"一行多张"重排
OPT_ROW_MIN = 3
# 卷面 2×2 时不重排，仅把超宽图压到这个比例
OPT_GRID_CAP = 0.30
# 卷面一行多张选项图时，每张占版心的比例（4 张 → 0.86/4 ≈ 0.21，
# 留出标签与列间距的空隙，整行才不会越界）
OPT_ROW_SLOT_RATIO = 0.86
# 讲义（一题一页）：一行一个太占页，两张图起就并成一行
OPT_HANDOUT_MIN = 2
OPT_HANDOUT_CAP = 0.24
OPT_HANDOUT_H = r"0.15\textheight"
# 讲义"超页降级"时用的一套（一题一页实在放不下）
OPT_TIGHT_CAP = 0.18
OPT_TIGHT_H = r"0.10\textheight"
FIG_H_HANDOUT_TIGHT = r"0.30\textheight"

# ── 解答题留白（cm）──────────────────────────────────────────────────
# 按位置定难度，留白跟着难度走；界面可整套覆盖（`problem_blank_cm`）。
BLANK_CM = {"简单题": 3.0, "中档题": 5.0, "难题": 8.0}
# 跨页修复用：允许各题少收一点，把"题 + 留白"挤进一页
BLANK_SHRINK_CM = 0.8

# ── 讲义 ──────────────────────────────────────────────────────────────
# 一题一页：讲义字号档（见 `paper.HANDOUT_SIZES`），默认小四
HANDOUT_FONT = "-4"


def opt_slot(cols: int) -> float:
    """一行 `cols` 张图选项时，每张占版心的比例（4 列 0.18、3 列 0.24）。"""
    if cols <= 0:
        return OPT_GRID_CAP
    return min(OPT_GRID_CAP, OPT_SLOT_RATIO / cols)


def handcheck() -> int:
    """自检：参数互相不打架。`python3 -m amti.layout`"""
    fails = 0

    def check(name, cond, extra=""):
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("layout 自检")
    check("4 列槽宽 0.18", abs(opt_slot(4) - 0.18) < 1e-9, opt_slot(4))
    check("3 列槽宽 0.24", abs(opt_slot(3) - 0.24) < 1e-9, opt_slot(3))
    check("列数越多槽越窄", opt_slot(4) < opt_slot(3) < opt_slot(2) or opt_slot(2) <= OPT_GRID_CAP)
    check("留白 易<中<难", BLANK_CM["简单题"] < BLANK_CM["中档题"] < BLANK_CM["难题"])
    check("讲义降级后更小", OPT_TIGHT_CAP < OPT_HANDOUT_CAP)
    check("版本号是正整数", isinstance(VERSION, int) and VERSION >= 1)
    print("layout 自检 通过（0 项失败）" if not fails else "layout 自检 失败 %d 项" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(handcheck())
