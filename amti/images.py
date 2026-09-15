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

import hashlib
import json
import re
import shutil
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
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

    print("images 自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
