"""AmTiKu · 按学段出包（母库 → 可独立运行的数据目录）

为什么需要它：母库是一份（跨学段查重、统一备份都靠它），但**发给客户**要按
学段分开。这里不做“视图筛选”，而是把一个学段真正抽出来，写成一套完整的
数据目录：`题目/ 图片/ 知识点.json 知识地图.json 小初诊断题.json`。

    python3 -m amti.stagepack junior --out ~/Desktop/分发/初中

出包之后，把 `AmTiKu.app` 放在这个目录里，程序按“旁边有没有 `题目/`”认数据根
（见 `amti/paths.py` 便携模式），客户拿到的就是一套独立题库，和母库无关。

边界：
  * 题目块**原样拷贝**（含 `%% @q` 元数据），不重新序列化——避免出包时改写正文。
  * 只拷引用到的图片（内容寻址命名不变）。
  * 知识点/知识地图/诊断题按学段裁剪；别的学段的数据一个字都不带。
  * 不带 `使用频次/审阅/快照/索引/缓存/试卷/回收站`——客户拿到的是干净库，
    索引在客户机器上首次启动时自动重建。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

from .paths import ROOT
from . import store
from . import knowledge_map

STAGE_NAME = {"primary": "小学", "junior": "初中", "senior": "高中"}
STAGES = ("primary", "junior", "senior")
KB_PATH = ROOT / "知识点.json"
MAP_PATH = ROOT / "知识地图.json"
QS_PATH = ROOT / "小初诊断题.json"
IMG_DIR = ROOT / "图片"
PER_VOLUME = 5000


def _stage_map() -> dict[str, str]:
    """知识点 id → 学段 key（`知识地图.json` 是学段的唯一真相）。"""
    out: dict[str, str] = {}
    for st in knowledge_map.load().get("stages", []):
        k = str(st.get("key") or "")
        if k not in STAGE_NAME:
            continue
        for b in st.get("books", []):
            for c in b.get("chapters", []):
                for p in c.get("points", []):
                    pid = str(p.get("id") or "")
                    if pid:
                        out[pid] = k
    return out


def _block_stage(q, pm: dict[str, str]) -> str:
    r"""一道题属于哪个学段。

    以考点为准；考点必须同属一个学段（混挂说明录入时标错了，直接报错让人修，
    不能默默按第一个点分）。完全没有考点的题按书名兜底，并在报告里点名。
    """
    sts = {pm[p] for p in (q.points or []) if p in pm}
    if len(sts) > 1:
        raise ValueError("考点跨学段：%s %r" % (q.key, q.points))
    if sts:
        return sts.pop()
    book = str((q.meta or {}).get("book") or "")
    if "中考" in book:
        return "junior"
    if "小学" in book:
        return "primary"
    return "senior"


def _read_bank() -> list[tuple[str, object, str]]:
    r"""读母库：`[(key, Question, 原始题块)]`，顺序按卷序。"""
    out = []
    for path in store.existing_volumes():
        text = path.read_text(encoding="utf-8")
        from .latex_ir import split_questions
        for block in split_questions(text):
            if store.GRAVE_MARK in block:
                continue
            q = store.question_from_block(block)
            if q is None or not q.key:
                continue
            out.append((q.key, q, block))
    return out


def _write_volumes(out: Path, blocks: list[str]) -> None:
    d = out / "题目"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(0, len(blocks), PER_VOLUME):
        chunk = blocks[i:i + PER_VOLUME]
        (d / ("%03d.tex" % (i // PER_VOLUME + 1))).write_text(
            "\n\n".join(chunk) + "\n", encoding="utf-8")


def _write_zhishidian(out: Path, stage: str) -> None:
    if stage == "senior":
        if KB_PATH.is_file():
            shutil.copy2(KB_PATH, out / "知识点.json")
        return
    # 小初包里没有高中考点：留一个合法空壳，`knowledge._index()` 会返回空，
    # `_small_index()` 照常从知识地图读小初知识点。
    (out / "知识点.json").write_text(
        json.dumps({"topics": []}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")


def _write_map(out: Path, stage: str) -> dict:
    raw = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    stages = [s for s in raw.get("stages", []) if s.get("key") == stage]
    if not stages:
        raise ValueError("知识地图里没有学段 %s" % stage)
    ids = {str(p.get("id")) for s in stages
           for b in s.get("books", []) for c in b.get("chapters", [])
           for p in c.get("points", []) if p.get("id")}
    edges = [e for e in raw.get("edges", [])
             if str(e.get("from")) in ids and str(e.get("to")) in ids]
    n_pts = len(ids)
    n_books = sum(len(s.get("books", [])) for s in stages)
    hard = sum(1 for e in edges if e.get("kind") == "hard")
    soft = sum(1 for e in edges if e.get("kind") == "soft")
    prereq = sum(1 for e in edges if e.get("kind") == "prereq")
    order = sum(1 for e in edges if e.get("kind") == "order")
    data = {
        **raw,
        "stages": stages,
        "edges": edges,
        "stats": {
            "points": {stage: n_pts},
            "total": n_pts,
            "books": {stage: n_books},
            "edges": {"total": len(edges), "hard": hard, "soft": soft,
                      "prereq": prereq, "order": order, "covered": len(edges)},
        },
    }
    (out / "知识地图.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"points": n_pts, "books": n_books, "edges": len(edges), "ids": ids}


def _write_diagnostics(out: Path, stage: str, ids: set[str]) -> int:
    if stage == "senior" or not QS_PATH.is_file():
        return 0
    raw = json.loads(QS_PATH.read_text(encoding="utf-8"))
    pts = {k: v for k, v in (raw.get("points") or {}).items() if k in ids}
    data = {**raw, "points": pts}
    (out / "小初诊断题.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return sum(len(v) for v in pts.values() if isinstance(v, list))


def _write_publish(out: Path, stage: str, counts: dict) -> None:
    data = {
        "version": 1,
        "stage": stage,
        "stage_name": STAGE_NAME[stage],
        "product": "AmTiKu %s数学题库" % STAGE_NAME[stage],
        "built_at": time.strftime("%Y-%m-%d %H:%M"),
        "counts": counts,
        "content_hash": counts["content_hash"],
        "includes": ["题目", "图片", "知识点", "知识地图", "小初诊断题"],
        "note": "按学段从母库导出的独立题库；索引/使用频次等派生数据不随包。",
    }
    (out / "数据").mkdir(exist_ok=True)
    (out / "数据" / "发布.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _write_readme(out: Path, stage: str, counts: dict) -> None:
    name = STAGE_NAME[stage]
    text = f"""# AmTiKu · {name}数学题库（独立数据目录）

这是从母库按学段导出的一套{name}题库，**不含其他学段**。

- 题目：{counts['questions']} 道
- 知识点：{counts['points']} 个
- 配图：{counts['images']} 张
- 诊断题：{counts['diagnostics']} 道
- 内容指纹：`{counts['content_hash']}`

## 怎么用

把 `AmTiKu.app`（或 Windows 的 `AmTiKu.exe`）放进**本目录**，双击打开。
程序按“旁边有没有 `题目/`”认数据目录（`amti/paths.py` 便携模式），
不会读你电脑上别的题库。

也可以从源码跑：

    AMTIKU_ROOT="$(pwd)" python3 -m amti.web.server --port 8899

## 目录里有什么

    题目/          题库正文（按 {PER_VOLUME} 题分卷）
    图片/          题目配图（内容寻址命名，别改名）
    知识点.json    {'高中 152 个考点' if stage == 'senior' else '空壳（本学段没有高中考点）'}
    知识地图.json  本学段的教材位置与先修边
    小初诊断题.json {'本学段诊断题' if stage != 'senior' else '（本学段没有诊断题）'}
    数据/发布.json 交付清单（学段、题量、内容指纹）

`使用频次/审阅/索引/缓存/试卷` 都不随包；首次启动会自动重建索引。

## 备份

复制整个目录即可。不要只拷 `题目/`——图片和知识地图是配套的。
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def build(stage: str, out: Path, *, dry_run: bool = False) -> dict:
    if stage not in STAGES:
        raise ValueError("学段只能是 primary/junior/senior")
    out = out.expanduser().resolve()
    pm = _stage_map()
    bank = _read_bank()
    picked = []
    warn_untagged = []
    for key, q, block in bank:
        k = _block_stage(q, pm)
        if k == stage:
            picked.append((key, q, block))
            if not q.points:
                warn_untagged.append(key)

    blocks = [b for _k, _q, b in picked]
    keys = [k for k, _q, _b in picked]
    if dry_run:
        return {"stage": stage, "out": str(out), "questions": len(blocks),
                "keys": keys, "untagged": warn_untagged, "dry_run": True}

    if out.exists():
        # 只允许覆盖“上一次出包”的目录，防止 `--out ~/文档` 误删整个文件夹。
        if not (out / "数据" / "发布.json").exists():
            raise SystemExit("✗ 目标已存在且不是出包目录：%s" % out)
        shutil.rmtree(out)
    out.mkdir(parents=True)

    _write_volumes(out, blocks)

    figs: set[str] = set()
    for _k, q, _b in picked:
        for f in q.figures or ():
            if f.kind == "bitmap" and f.id:
                figs.add(f.id)
    (out / "图片").mkdir(exist_ok=True)
    missing = []
    for fid in sorted(figs):
        src = IMG_DIR / fid
        if src.is_file():
            shutil.copy2(src, out / "图片" / fid)
        else:
            missing.append(fid)

    _write_zhishidian(out, stage)
    mp = _write_map(out, stage)
    diag_n = _write_diagnostics(out, stage, mp["ids"])

    h = hashlib.sha256()
    for k in keys:
        h.update(k.encode("utf-8"))
        h.update(b"\0")
    counts = {
        "questions": len(blocks),
        "points": mp["points"],
        "books": mp["books"],
        "edges": mp["edges"],
        "images": len(figs) - len(missing),
        "diagnostics": diag_n,
        "content_hash": h.hexdigest(),
    }
    _write_publish(out, stage, counts)
    # 空的使用频次文件：没有它，第一屏会打一条“文件损坏”的日志（虽然不影响用）。
    (out / "数据" / "使用频次.json").write_text("{}\n", encoding="utf-8")
    _write_readme(out, stage, counts)

    return {"stage": stage, "out": str(out), "questions": len(blocks),
            "images": counts["images"], "missing_images": missing,
            "diagnostics": diag_n, "points": mp["points"], "edges": mp["edges"],
            "untagged": warn_untagged, "content_hash": counts["content_hash"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按学段把母库导出成独立数据目录")
    ap.add_argument("stage", choices=STAGES)
    ap.add_argument("--out", required=True, help="输出目录（必须是新目录或上次的出包目录）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = build(a.stage, Path(a.out), dry_run=a.dry_run)
    except (ValueError, SystemExit) as e:
        print("✗ %s" % e)
        return 1
    if r.get("dry_run"):
        print("%s：将导出 %d 道" % (STAGE_NAME[r["stage"]], r["questions"]))
        return 0
    print("✓ %s：%d 道 · %d 图 · %d 诊断题 · %d 知识点／%d 条先修边"
          % (STAGE_NAME[r["stage"]], r["questions"], r["images"],
             r["diagnostics"], r["points"], r["edges"]))
    if r["missing_images"]:
        print("  ⚠ 缺图 %d 张：%s" % (len(r["missing_images"]),
                                     ", ".join(r["missing_images"][:5])))
    if r["untagged"]:
        print("  ⚠ 无考点、按书名归入本学段的 %d 道：%s"
              % (len(r["untagged"]), ", ".join(r["untagged"][:3])))
    print("  输出：%s" % r["out"])
    return 0 if not r["missing_images"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
