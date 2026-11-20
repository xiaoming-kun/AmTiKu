#!/usr/bin/env python3
"""把整库按顺序切成每 200 题一份，导出「测试卷」与「讲义」两套 PDF。

用途：**题目排版抽查**——一沓 PDF 从头翻，看到不对的记下题号去改。

    python3 脚本/批量导题目检查.py                # 默认输出到 ~/Desktop/题目检查
    python3 脚本/批量导题目检查.py --out 某目录
    python3 脚本/批量导题目检查.py --workers 4    # 并行编译数（默认 4）
    python3 脚本/批量导题目检查.py --from 1 --to 5   # 只导第 1~5 份（试跑）

特点：

  * **按题库顺序**（`store.load_all()` 的卷序），每 200 题一份，文件名标范围；
  * **两套**：`测试卷/`（A4 竖版试卷）与 `讲义/`（一题一页 A4 横版）；
  * **可断点续跑**：目标 PDF 已存在就跳过，中断后重跑只补缺的；
  * **失败不拖垮全局**：某一份编译失败只记进 `_失败.log`，继续下一份；
  * 编译在临时目录里做（`export.compile_tex` 自带 ASCII 绕行），不污染 `数据/预览`。

输出示例：

    ~/Desktop/题目检查/
      测试卷/0001-0200_测试卷.pdf        （约 48 页）
      讲义/0001-0200_讲义.pdf            （200 页，一题一页）
      _进度.log  _失败.log
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amti import export, store                     # noqa: E402

CHUNK = 200
DEFAULT_OUT = Path.home() / "Desktop" / "题目检查"


def _compile_ok(qs, mode: str) -> tuple[bool, str]:
    """试编一小批，返回 (是否成功, 日志尾巴)。"""
    tmp = Path(tempfile.mkdtemp(prefix="amti_probe_"))
    try:
        tex = export.render_paper(qs, mode=mode, title="probe", qid_marks=True,
                                  show_answers=(mode == "test"),
                                  answers_at_end=False, show_points=False)
        p = tmp / "probe.tex"
        p.write_text(tex, encoding="utf-8")
        ok, log = export.compile_tex(p)
        return ok, (log or "")[-400:]
    except Exception as e:                       # noqa: BLE001
        return False, "%s: %s" % (type(e).__name__, e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _find_bad(qs, mode: str, depth: int = 0) -> list[str]:
    r"""二分找出**编译不过**的题（通常是数据里 LaTeX 写坏了：缺 `\item`、括号不配对）。

    只在这个 batch 已经整体失败后调用；每次探针都是一次真编译（10 秒级），
    二分能把 200 题的排查压到 ~8 次。
    """
    if not qs:
        return []
    ok, _log_ = _compile_ok(qs, mode)
    if ok:
        return []
    if len(qs) == 1:
        return [qs[0].key]
    mid = len(qs) // 2
    return _find_bad(qs[:mid], mode, depth + 1) + _find_bad(qs[mid:], mode, depth + 1)


def _log(path: Path, msg: str) -> None:
    line = "%s  %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


VARIANTS = {
    "student": ("学生版", False, False),   # (目录名, 题目下带答案, 答案放卷末)
    "teacher": ("教师版", True, False),
    "booklet": ("答案册", False, True),
}

# 三种卷型：讲义 / 测试卷 / 高考卷（目录名, 渲染 mode, 题下带答案解析)
PAPERS = {
    "handout": ("讲义", "handout", False),
    "test": ("测试卷", "test", True),
    "gaokao": ("高考卷", "gaokao", True),
}


def _job(qs, mode: str, out_dir: Path, first: int, last: int,
         log_path: Path, fail_path: Path, force: bool = False) -> tuple[int, str]:
    """导出一份。返回 (份号, 错误信息或空串)。"""
    name = "%04d-%04d" % (first, last)
    if mode in VARIANTS:
        vdir, show_ans, at_end = VARIANTS[mode]
        out_dir = out_dir / vdir
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / ("%s_%s.pdf" % (name, vdir))
    elif mode in PAPERS:
        label = PAPERS[mode][0]
        out_dir = out_dir / label
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / ("%s_%s.pdf" % (name, label))
    else:
        dest = out_dir / ("%s_%s.pdf" % (name, "测试卷" if mode == "test" else "讲义"))
    if dest.exists() and dest.stat().st_size > 10_000 and not force:
        return first, ""                        # 已经有了，跳过
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="amti_bulk_"))
    try:
        label = (VARIANTS[mode][0] if mode in VARIANTS
                 else PAPERS[mode][0] if mode in PAPERS
                 else ("测试卷" if mode == "test" else "讲义"))
        title = "题目检查 %s %s" % (name, label)
        # 三变体：学生版（只出题）/ 教师版（题下带答案解析）/ 答案册（卷末）；
        # 两套固定卷型仍按原样。都不印「本次覆盖考点」（200 题会列上百条）。
        if mode in VARIANTS:
            _vd, show_ans, at_end = VARIANTS[mode]
            pmode = "test"
        elif mode in PAPERS:
            _label, pmode, show_ans = PAPERS[mode]
            at_end = False
        else:
            show_ans, at_end = (mode == "test"), False
            pmode = mode
        tex = export.render_paper(qs, mode=pmode, title=title, qid_marks=True,
                                  show_answers=show_ans,
                                  answers_at_end=at_end,
                                  show_points=False)
        p = tmp / "check.tex"
        p.write_text(tex, encoding="utf-8")
        ok, log = export.compile_tex(p)
        pdf = p.with_suffix(".pdf")
        if not ok or not pdf.exists():
            # **整批编不出来 → 逐道剔除再导**。
            # 先按日志行号定位（一次编译就知道是哪道）；同一批可能有好几道，
            # 所以循环剔除，直到编出来或剔到只剩一点为止。
            from amti import texdiag as _td
            bad: list[str] = []
            good = list(qs)
            for _ in range(30):
                if not good:
                    break
                try:
                    tex2 = export.render_paper(good, mode=mode, title=title,
                                               qid_marks=True,
                                               show_answers=(mode == "test"),
                                               answers_at_end=False,
                                               show_points=False)
                except Exception:                # noqa: BLE001
                    break
                p2 = tmp / "good.tex"
                p2.write_text(tex2, encoding="utf-8")
                ok2, log2 = export.compile_tex(p2)
                pdf2 = p2.with_suffix(".pdf")
                if ok2 and pdf2.exists():
                    shutil.move(str(pdf2), str(dest.with_name(
                        dest.stem + "_剔除坏题.pdf")))
                    note = out_dir / "_坏题.md"
                    with note.open("a", encoding="utf-8") as f:
                        for k in bad:
                            f.write("- `%s`（%s）\n"
                                    % (k, "测试卷" if mode == "test" else "讲义"))
                    msg = ("第 %s 份（%s）剔除 %d 道编不过的题后另存：%s"
                           % (name, mode, len(bad), "、".join(bad[:3])))
                    _log(fail_path, msg)
                    return first, msg
                try:
                    info2 = _td.locate(log2 or "", tex2)
                    k = info2.get("key") or ""
                except Exception:                # noqa: BLE001
                    k = ""
                if not k or k in bad or all(q.key != k for q in good):
                    bad2 = _find_bad(good, mode)
                    k = bad2[0] if bad2 else ""
                if not k:
                    break
                bad.append(k)
                good = [q for q in good if q.key != k]
            tail = (log or "").strip().splitlines()[-3:]
            msg = "第 %s 份（%s）编译失败：%s" % (name, mode, " / ".join(tail)[-300:])
            _log(fail_path, msg)
            return first, msg
        shutil.move(str(pdf), str(dest))
        _log(log_path, "✓ %s_%s  %d 题  %.1fs" % (name, label, len(qs), time.time() - t0))
        return first, ""
    except Exception as e:                       # noqa: BLE001
        msg = "第 %s 份（%s）异常：%s: %s" % (name, mode, type(e).__name__, e)
        _log(fail_path, msg)
        return first, msg
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="整库按 200 题一份导出检查用 PDF")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--from", dest="start", type=int, default=1, help="从第几份开始")
    ap.add_argument("--to", dest="end", type=int, default=0, help="到第几份（0=全部）")
    ap.add_argument("--modes", default="both",
                    choices=("both", "test", "handout", "variants", "trio"),
                    help="both=测试卷+讲义；variants=学生版/教师版/答案册")
    ap.add_argument("--force", action="store_true", help="已存在也重导（覆盖）")
    a = ap.parse_args()

    out = Path(a.out).expanduser()
    test_dir, hand_dir = out / "测试卷", out / "讲义"
    for d in (test_dir, hand_dir):
        d.mkdir(parents=True, exist_ok=True)
    log_path, fail_path = out / "_进度.log", out / "_失败.log"

    qs_all = store.load_all()
    total = len(qs_all)
    chunks = [qs_all[i:i + CHUNK] for i in range(0, total, CHUNK)]
    n = len(chunks)
    lo = max(1, a.start)
    hi = n if not a.end else min(n, a.end)

    _log(log_path, "共 %d 题 / %d 份 × 2 套；本次导第 %d–%d 份 → %s"
                    % (total, n, lo, hi, out))
    jobs = []
    for k in range(lo, hi + 1):
        qs = chunks[k - 1]
        first = (k - 1) * CHUNK + 1
        last = first + len(qs) - 1
        if a.modes == "both":
            modes = ("test", "handout")
        elif a.modes == "variants":
            modes = ("student", "teacher", "booklet")
        elif a.modes == "trio":
            modes = ("handout", "test", "gaokao")
        else:
            modes = (a.modes,)
        for mode in modes:
            if mode in VARIANTS or mode in PAPERS:
                d = out                     # 三版/三卷型直接放 <输出>/<子目录>/
            else:
                d = test_dir if mode == "test" else hand_dir
            jobs.append((qs, mode, d, first, last))

    bad = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        futs = [pool.submit(_job, qs, mode, d, first, last, log_path, fail_path,
                            a.force)
                for (qs, mode, d, first, last) in jobs]
        for f in as_completed(futs):
            _k, err = f.result()
            if err:
                bad += 1
    _log(log_path, "完成：%d 个任务，失败 %d，用时 %.1f 分钟"
                    % (len(jobs), bad, (time.time() - t0) / 60))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
