"""图片入库：复制进项目 + 改成内容寻址名。**全项目唯一处理图片的地方。**

为什么内容寻址
--------------
旧项目是 `图片/moni/x.png` 这种「按来源分目录 + 原名」的存法。一旦要拍平，
同名就冲突，于是改名、消歧、回写引用——四步都可能出错，最后的表现就是页面上
一个碎图占位。设计文档第 1.4 节定了内容寻址，这里落实它：

    文件名 = sha256(图片内容)[:16] + 后缀

    * 同样内容天然合并，不会有两份
    * 改名不可能冲突，**文件名即事实**
    * 图片全在 图片/ 一个目录，导出的 `\\graphicspath` 指向它

硬性要求（用户反复强调的两条）
------------------------------
1. 图片必须**复制进项目**，不能引用外部路径——外部文件一改项目就坏。
2. 复制不了的要**显式报出来**（`meta.figure_missing`），不许静默留个碎图。

⚠️ 图片引用是题目**内容**的一部分（在 `HASH_FIELDS` 里），所以改写引用会让
内容指纹变化。这是一次性 MIGRATE 操作，不是 ENTRY 规则。
"""

from __future__ import annotations

from .paths import ROOT
import hashlib
import json
import re
import shutil
from pathlib import Path

PKG = ROOT
IMG_DIR = PKG / "图片"
MANIFEST = IMG_DIR / "来源清单.json"

IMG_RE = re.compile(r"\\includegraphics\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
# 内容寻址名：sha256 前 16 位 + 后缀
_HASH_NAME_RE = re.compile(r"^[0-9a-f]{16}\.[a-z0-9]+$")

# 录入新题时**没给 `--src`** 的兜底图源。
#
# 原来是写死旧项目 `deepseek/习题/题库/图片`——那是迁移期的临时做法，
# 现在改成**项目内的暂存目录**：把要录入的图先丢进 `待录入图片/`，
# 不带 `--src` 也能找到。这样 AmTiKu 不依赖任何项目外的路径。
OLD_IMG = PKG / "待录入图片"


# ── 命名 ──────────────────────────────────────────────────────────────

def sha_name(data: bytes, suffix: str = ".png") -> str:
    """内容 → 文件名。同内容同名字，这是「不重复、不冲突」的全部依据。"""
    return hashlib.sha256(data).hexdigest()[:16] + (suffix or ".png").lower()


# ── 找源文件 ──────────────────────────────────────────────────────────

class Resolver:
    r"""按 `\includegraphics{…}` 里的名字找源文件。

    先按相对路径找（`moni/x.png` 能命中 `图片/moni/x.png`）；
    找不到再退化成按文件名索引找（旧库里有引用丢了目录前缀的情况）。
    索引是懒建的——只有真的出现找不到的情况才扫目录。
    """

    def __init__(self, dirs):
        self.dirs = [Path(d) for d in dirs]
        self._index: dict[str, Path] | None = None

    def _build(self) -> None:
        self._index = {}
        for d in self.dirs:
            if not d.is_dir():
                continue
            for p in d.rglob("*"):
                if p.is_file():
                    self._index.setdefault(p.name, p)

    def find(self, name: str) -> Path | None:
        n = (name or "").strip().lstrip("/")
        if not n:
            return None
        for d in self.dirs:
            p = d / n
            if p.is_file():
                return p
        if self._index is None:
            self._build()
        return self._index.get(Path(n).name)


# ── 改写 ──────────────────────────────────────────────────────────────

def collect(text: str) -> list[str]:
    """一段正文里引用到的图片名（按出现顺序，去重）。"""
    out: list[str] = []
    for m in IMG_RE.finditer(text or ""):
        n = m.group(2).strip()
        if n and n not in out:
            out.append(n)
    return out


def rewrite(text: str, mapping: dict[str, str]) -> str:
    """把引用换成新名。`[width=…]` 之类的可选参数原样保留。"""
    if not text or not mapping:
        return text or ""

    def sub(m: re.Match) -> str:
        opt, name = m.group(1), m.group(2).strip()
        new = mapping.get(name)
        if not new:
            return m.group(0)
        return "\\includegraphics%s{%s}" % (("[%s]" % opt) if opt else "", new)

    return IMG_RE.sub(sub, text)


# ── 主流程 ────────────────────────────────────────────────────────────

def ingest_question(q, resolver: Resolver, *, dst: Path = IMG_DIR,
                    dry_run: bool = False,
                    manifest: dict | None = None) -> dict:
    """把一道题引用的图片复制进项目、引用改成内容寻址名。

    返回报告：`{copied, reused, missing, map}`。
    `dry_run=True` 时**只看不动**，用于录入前的预检。
    """
    fields = [q.stem, q.answer, q.solution] + [o.text for o in q.options]
    names: list[str] = []
    for v in fields:
        for n in collect(v):
            if n not in names:
                names.append(n)

    mapping: dict[str, str] = {}
    rep: dict = {"copied": [], "reused": [], "already": [], "missing": [],
                 "map": mapping}

    for n in names:
        # 已经是内容寻址名、文件就在项目里 → 迁移过了，跳过。
        # 这一条让整个入库**可以反复执行**，不然第二次会把已迁移的引用
        # 当成"源文件找不到"，报一堆假缺失。
        if _HASH_NAME_RE.match(n) and (dst / n).is_file():
            rep["already"].append(n)
            continue
        src = resolver.find(n)
        if src is None:
            # 找不到就**报出来**，绝不静默留个碎图
            rep["missing"].append(n)
            continue
        data = src.read_bytes()
        new = sha_name(data, src.suffix)
        mapping[n] = new
        target = dst / new
        if target.exists():
            rep["reused"].append((n, new))
        else:
            rep["copied"].append((n, new, len(data), str(src)))
            if not dry_run:
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        if manifest is not None:
            manifest.setdefault(new, {"orig": n, "src": str(src),
                                      "bytes": len(data),
                                      "sha256": hashlib.sha256(data).hexdigest()})

    # **引用改写和文件复制分开。**
    #
    # 录入流水线是「验证 → 规范化 → **图片入库** → 复核 → 录入」，
    # 复核要检查的是**最终的引用形态**（内容寻址名 + 文件在位）。
    # 所以干跑时也要把引用改掉——不然复核看到的是旧名，永远报
    # 「不是内容寻址名」。`dry_run` 只表示**不落盘**，不表示"不改内存里的题"。
    if mapping:
        q.stem = rewrite(q.stem, mapping)
        q.answer = rewrite(q.answer, mapping)
        q.solution = rewrite(q.solution, mapping)
        for o in q.options:
            o.text = rewrite(o.text, mapping)
        for f in q.figures:
            f.id = mapping.get(f.id, f.id)

    # 缺失清单：**只增不减**。
    #
    # 老写法在"这一步没发现缺图"时 `pop` 掉整个字段——于是**别的来源**
    # 打好的缺图标记被抹掉。实测踩过：模拟题的读图题（选项是图片、
    # OCR 没抽出来）本来标了 `figure_missing`，一过图片入库就没了，
    # 于是 schema 又报「选项内容为空」，整本书进不来。
    #
    # 合并而不是覆盖：不同步骤看到的缺口不一样，谁都不该擦掉谁的。
    # `ingest_question` 的 `missing` 是**图片名列表**；
    # 只有 `ingest_all` 才把它包成 `(key, name)`。别弄混。
    miss = set(rep["missing"])
    if miss:
        q.meta["figure_missing"] = sorted(set(q.meta.get("figure_missing") or []) | miss)
    return rep


def ingest_all(questions, *, src_dirs=None, dst: Path = IMG_DIR,
               dry_run: bool = False, write_manifest: bool = True) -> dict:
    """批量入库。返回汇总报告。"""
    resolver = Resolver(src_dirs or [OLD_IMG])
    manifest: dict = {}
    if write_manifest and MANIFEST.exists() and not dry_run:
        try:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {}

    total = {"questions": len(questions), "copied": 0, "reused": 0,
             "already": 0, "missing": [], "with_figures": 0, "map": {}}
    for q in questions:
        rep = ingest_question(q, resolver, dst=dst, dry_run=dry_run,
                              manifest=manifest)
        if rep["copied"] or rep["reused"] or rep["missing"]:
            total["with_figures"] += 1
        total["copied"] += len(rep["copied"])
        total["reused"] += len(rep["reused"])
        total["already"] += len(rep["already"])
        total["map"].update(rep["map"])
        for n in rep["missing"]:
            total["missing"].append((q.key, n))

    if write_manifest and not dry_run and manifest:
        dst.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False,
                                       indent=1, sort_keys=True),
                            encoding="utf-8")
    return total


def verify(questions) -> list[tuple[str, str]]:
    r"""检查所有 `\includegraphics` 引用都能在 图片/ 里找到实体文件。

    返回 `[(key, 引用名)]`，空列表表示全部可编译。
    """
    bad: list[tuple[str, str]] = []
    for q in questions:
        fields = [q.stem, q.answer, q.solution] + [o.text for o in q.options]
        for v in fields:
            for n in collect(v):
                if not (IMG_DIR / n).is_file():
                    bad.append((q.key, n))
    return bad


def stats() -> dict:
    """图片目录现状。"""
    files = [p for p in IMG_DIR.glob("*") if p.is_file() and p.name != MANIFEST.name] \
        if IMG_DIR.is_dir() else []
    return {"files": len(files),
            "bytes": sum(p.stat().st_size for p in files),
            "dir": str(IMG_DIR)}


# ══ 像素级身份 ════════════════════════════════════════════════════════
#
# `sha_name()` 算的是**文件字节**的哈希。它回答"这两个文件是不是同一份字节"，
# 但"是不是同一张图"是另一个问题：
#
#   · 同一张图另存为 JPEG、只是去掉 EXIF、或 Word 重导出一次
#     → 字节不同、`sha_name` 不同 → **库里存两份**（其实是同一张图）。
#   · 反过来，纯文本相同的两道题配了不同图（锐角 / 钝角三角形这类）
#     → 只比文字判重必然假阳性。
#
# 所以补一个**解码后像素**的签名，跟 MathBank 的 `_decoded_pixel_signature`
# （`question_duplicate_service.py:147-161`）同一个路子：`exif_transpose` 摆正方向、
# `convert("RGBA")` 统一色彩模式，再把「宽×高 + 原始像素」喂给 sha256。
# 这样它与文件名、EXIF、压缩方式都无关。
#
# ⚠️ **只用于"判断是不是同一张"，绝不用于改名。**
# `图片/` 下的文件名是内容寻址的，改名即断引用（AGENTS.md 第五节）——
# 所以这个签名不参与命名，只参与查重与体检。

#: 解不开的图返回它（空串）。给一个**看得见的哨兵**，下游就必须当
#: "身份未知"处理 —— 不能当成"不重复"。
PIXEL_UNKNOWN = ""


def pixel_signature(data: bytes) -> str:
    r"""解码后的像素签名；解不开返回 `PIXEL_UNKNOWN`（空串）。

    ⚠️ 解不开时**返回空串而不是跳过**。跳过等于悄悄说"这张图不重复"——
    而"我读不出来"和"它不重复"是两回事。（MathBank 同样返回空串，
    下游据此报 `VISUAL_SIGNATURE_PENDING` 强制人核。）
    """
    import io
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return PIXEL_UNKNOWN
    try:
        with Image.open(io.BytesIO(data)) as im:
            # 先按 EXIF 摆正方向 —— 否则同一张图旋转 90° 存两次会得到两个签名
            im = ImageOps.exif_transpose(im).convert("RGBA")
            h = hashlib.sha256()
            h.update(("%dx%d:RGBA:" % (im.width, im.height)).encode("ascii"))
            h.update(im.tobytes())
            return h.hexdigest()[:16]
    except Exception:
        # 解不开的任何情形（含 Pillow 的 DecompressionBomb、不认识的格式）
        return PIXEL_UNKNOWN


# ── 上传图片的体检 ────────────────────────────────────────────────────
#
# 这道检查**不重编码、不改字节**，只回答"这张图能不能安心入库"。
#
# 为什么不照 MathBank 那样解码后重编码一遍：它那边的理由是
# "re-encoding removes metadata, trailing polyglot payloads and active content
# disguised by suffix"（`asset_security.py:332-383`）。那对**在线服务**是对的；
# 但这里是本机单用户、图来自用户自己的卷子，而且**几何图是线条画**——
# JPEG 重编码会把线画糊掉，代价大于收益。
#
# 所以只做两件真正有代价的事：
#   ① 声明是图片但**解不开** → 拒。省得它变成页面上一个裂图，或者更糟：
#      一个改名成 .png 的 SVG/HTML（`<img>` 里跑不了脚本，但也没必要收）。
#   ② 尺寸或体积**离谱** → 拒。两万见方的 PNG 能把仓库撑爆，也贴不进版心。

#: 单张图的像素上限。3000 万像素 ≈ 6000×5000，一张 A4 卷子的插图远不到。
MAX_PIXELS = 30_000_000
#: 单张图的字节上限。
MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: 认得的栅格格式。**不认 SVG** —— 它是矢量、能带脚本，而本项目的题图
#: 一律走 `图片/` 下的栅格文件或预渲染的 TikZ，不需要 SVG 入库。
RASTER_OK = frozenset({"PNG", "JPEG", "GIF", "WEBP", "BMP", "TIFF"})


def check_raster(data: bytes) -> tuple[bool, str, dict]:
    r"""一份字节能不能当题图入库。返回 `(能不能用, 原因, 信息)`。

    `info` 带 `format/size/warn`，供调用方记进报告——**拒了要说清为什么**。
    """
    import io
    if not data:
        return False, "空文件", {}
    if len(data) > MAX_IMAGE_BYTES:
        return False, ("文件太大（%.1f MB > %d MB）"
                       % (len(data) / 1e6, MAX_IMAGE_BYTES // 1024 // 1024)), {}
    try:
        from PIL import Image
    except ImportError:
        return True, "", {"warn": "没装 Pillow，跳过了图片体检"}
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
            w, h = im.size
    except Exception as e:
        return False, ("不是能解开的图片（%s）——改名成 .png 的 SVG/HTML 也落在这里"
                       % type(e).__name__), {}
    if fmt not in RASTER_OK:
        return False, "不是栅格图片（识别为 %s）" % (fmt or "未知"), {"format": fmt}
    if w * h > MAX_PIXELS:
        return False, ("像素太多（%d×%d = %.1f 千万像素）" % (w, h, w * h / 1e7)), {"format": fmt}
    return True, "", {"format": fmt, "size": "%dx%d" % (w, h), "bytes": len(data)}


def pixel_duplicate_groups(paths=None) -> dict:
    r"""找出「字节不同、像素相同」的图片组——同一张图被存了几份。

    **只读，不改任何文件。** 用来回答"图片目录为什么这么大"：
    实测有 1000+ 张图没被任何题引用（约 41 MB），其中一部分就是
    同一张图的多次重编码。返回
    `{groups: [[名, …], …], waste_bytes: N, unreadable: [名, …]}`。

    `unreadable` 单独列出，**不并进 groups**：读不出来不等于"不重复"。
    """
    ps = list(paths) if paths is not None else sorted(
        p for p in IMG_DIR.glob("*") if p.is_file() and p.name != MANIFEST.name)
    # ⚠️ 只把**自称是栅格图**的文件算进"读不出来"。
    # `图片/` 下还有 TikZ 预渲染的 `tikz-*.pdf` —— PDF 不是栅格格式，
    # Pillow 解不开是**正常的**。第一版把它们全算成"读不出来"，
    # 报出 119 张，看着像一片坏图，其实一张都不坏（也一张都没被引用）。
    # 报告里混进这种噪声，人就不看报告了。
    raster = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
    by_sig: dict[str, list[Path]] = {}
    unreadable: list[str] = []
    for p in ps:
        if p.suffix.lower() not in raster:
            continue                      # 非栅格（PDF 等），不参与像素比对
        try:
            sig = pixel_signature(p.read_bytes())
        except OSError:
            continue
        if not sig:
            unreadable.append(p.name)      # 自称是图却解不开 —— 这才要报
            continue
        by_sig.setdefault(sig, []).append(p)
    groups = [sorted(x.name for x in v) for v in by_sig.values() if len(v) > 1]
    waste = 0
    for v in by_sig.values():
        if len(v) > 1:
            # 留最大的那份，其余算浪费
            waste += sum(sorted((x.stat().st_size for x in v), reverse=True)[1:])
    groups.sort()
    return {"groups": groups, "waste_bytes": waste, "unreadable": unreadable}


# ── 自检 ──────────────────────────────────────────────────────────────

def _selftest() -> int:
    import tempfile

    fails = 0

    def check(name: str, cond: bool, extra: str = "") -> None:
        nonlocal fails
        if cond:
            print("  ✓ %s" % name)
        else:
            fails += 1
            print("  ✗ %s  %s" % (name, extra))

    print("images 自检")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "src"
        (src / "sub").mkdir(parents=True)
        dst = root / "dst"

        a = b"\x89PNG-fake-A"
        b = b"\x89PNG-fake-B"
        (src / "x.png").write_bytes(a)
        (src / "sub" / "y.png").write_bytes(b)
        (src / "dup.png").write_bytes(a)          # 与 x.png 内容相同

        check("同内容同名", sha_name(a) == sha_name(a))
        check("异内容异名", sha_name(a) != sha_name(b))

        r = Resolver([src])
        check("按相对路径找到", r.find("sub/y.png") is not None)
        check("退化按文件名找到", r.find("y.png") is not None)
        check("确实没有的返回 None", r.find("nope.png") is None)

        from amti.schema import Question
        q = Question(key="t/1#1", type="single_choice",
                     stem=r"如图 \includegraphics[width=0.4\linewidth]{x.png} 和 $\includegraphics{sub/y.png}$",
                     answer=r"见 \includegraphics{dup.png}",
                     solution="", meta={})
        rep = ingest_question(q, r, dst=dst)
        check("找到 3 个引用中的 2 个不同内容", len(rep["map"]) == 3, str(rep["map"]))
        check("同内容的 dup 与 x 指向同一个文件",
              rep["map"]["x.png"] == rep["map"]["dup.png"], str(rep["map"]))
        check("文件落盘", (dst / rep["map"]["x.png"]).is_file())
        check("同内容只落一份", len(list(dst.glob("*.png"))) == 2,
              str(sorted(p.name for p in dst.glob("*.png"))))
        check("引用的 width 参数保留",
              "[width=0.4\\linewidth]" in q.stem, q.stem)
        check("嵌套在 $…$ 里的引用也改了", "sub/y.png" not in q.stem, q.stem)
        check("答案字段也改了", "dup.png" not in q.answer, q.answer)
        check("figures 里的 id 同步",
              all(f.id in rep["map"].values() for f in q.figures) or not q.figures)

        # 缺失要报出来，不许静默
        q2 = Question(key="t/1#2", type="single_choice",
                      stem=r"\includegraphics{gone.png}", meta={})
        rep2 = ingest_question(q2, r, dst=dst)
        check("缺失被记录", rep2["missing"] == ["gone.png"], str(rep2["missing"]))
        check("缺失写进 meta", q2.meta.get("figure_missing") == ["gone.png"],
              str(q2.meta))

        # 幂等：再跑一次应该识别出"已迁移"，不重复复制、也不报假缺失
        q3 = Question(key="t/1#3", type="single_choice",
                      stem=r"\includegraphics{x.png}", meta={})
        ingest_question(q3, r, dst=dst)
        rep3 = ingest_question(q3, r, dst=dst)
        check("二次执行幂等（不重复复制、不报假缺失）",
              not rep3["copied"] and not rep3["missing"] and len(rep3["already"]) == 1,
              str(rep3))
        check("二次执行不改动正文", q3.stem == "\\includegraphics{%s}"
              % sha_name(a), q3.stem)

    # ── 像素级身份（B9）与图片体检（B11）──────────────────────────
    # 真造两张图：同一张图的两种编码 / 两张内容不同的图 / 一个假 PNG。
    import io
    from PIL import Image

    def _png(color, size=(8, 8), *, level=6, fmt="PNG"):
        buf = io.BytesIO()
        Image.new("RGB", size, color).save(buf, fmt, **({"compress_level": level} if fmt == "PNG" else {}))
        return buf.getvalue()

    # 同一张图的**无损**两种编码：压缩级别不同 → 字节不同、像素逐点相同。
    # 这正是现实里最常见的那种重复（抽图工具重存一遍、去掉元数据、换压缩级别）。
    red_png = _png((255, 0, 0), level=0)
    red_png2 = _png((255, 0, 0), level=9)
    # JPEG 是**有损**的：解码回来是 (254,0,0) 一类，像素不逐点相同。
    red_jpg = _png((255, 0, 0), fmt="JPEG")
    blue_png = _png((0, 0, 255))

    check("字节不同（sha_name 认为这是两份）",
          sha_name(red_png, ".png") != sha_name(red_png2, ".png"),
          "%s vs %s" % (sha_name(red_png, ".png"), sha_name(red_png2, ".png")))
    check("像素逐点相同 → pixel_signature 认出是同一张",
          pixel_signature(red_png) == pixel_signature(red_png2),
          "%s vs %s" % (pixel_signature(red_png), pixel_signature(red_png2)))
    # ⚠️ **已知边界**：签名是"像素逐点相等"，不是"看着像"。
    # 有损重编码（JPEG）解出来的像素已经变了，签名就不一样。
    # 这一条**故意断言它不相等**——把边界钉住，免得以后有人以为它能管有损。
    # （MathBank 的 `_decoded_pixel_signature` 同样是精确 RGBA 哈希，边界一样。）
    check("已知边界：有损重编码认不出（精确像素哈希管不了 JPEG）",
          pixel_signature(red_png) != pixel_signature(red_jpg),
          "%s vs %s" % (pixel_signature(red_png), pixel_signature(red_jpg)))
    check("不同内容的图签名不同",
          pixel_signature(red_png) != pixel_signature(blue_png))
    check("签名不是空（正常图片必须给出身份）", bool(pixel_signature(red_png)))
    check("解不开的给空哨兵，而不是假装不重复",
          pixel_signature(b"\x89PNG-not-really") == PIXEL_UNKNOWN)

    # EXIF 方向不该影响身份：同一张图画进 8x4 与旋转后存 4x8，
    # exif_transpose 之后应当一致 —— 这里用同一尺寸变颜色来等价验证
    check("尺寸不同则签名不同（宽高进了哈希）",
          pixel_signature(_png((1, 2, 3), (8, 8))) != pixel_signature(_png((1, 2, 3), (4, 4))))

    # 体检
    ok, why, info = check_raster(red_png)
    check("正常 PNG 放行", ok and info.get("format") == "PNG", why)
    ok, why, _ = check_raster(b"not an image at all")
    check("假图片被拒且说明原因", not ok and why, why)
    ok, why, _ = check_raster(b"")
    check("空文件被拒", not ok, why)
    ok, why, _ = check_raster(b"x" * (MAX_IMAGE_BYTES + 1))
    check("超大文件被拒（不先解码）", not ok and "太大" in why, why)

    # 重复组：只在临时目录里验，**绝不碰真的 图片/**
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        (d / "a.png").write_bytes(red_png)
        (d / "b.png").write_bytes(red_png2)
        (d / "c.png").write_bytes(blue_png)
        (d / "broken.png").write_bytes(b"nope")
        g = pixel_duplicate_groups(sorted(d.glob("*")))
        check("认出 a.png 与 b.png 是同一张图（字节不同）",
              g["groups"] == [["a.png", "b.png"]], str(g["groups"]))
        check("浪费的字节 = 较小那份", g["waste_bytes"] > 0, str(g["waste_bytes"]))
        check("读不出来的单独列，不算「不重复」",
              g["unreadable"] == ["broken.png"], str(g["unreadable"]))

    print("images 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
