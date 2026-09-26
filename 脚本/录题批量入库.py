#!/usr/bin/env python3
r"""**顺序**驱动器：一场一场调 `脚本/录题入库.py`，它自己不做任何入库动作。

    python3 脚本/录题批量入库.py 101 102 103            # 只看账（干跑，不写库）
    python3 脚本/录题批量入库.py --next 12              # 按队列顺序看接下来 12 场
    python3 脚本/录题批量入库.py --next 12 --commit      # 真入库，一场一次 commit

为什么要这么一层，而不是在 shell 里 for 循环：

* **一场一次 commit** 是 §6 红线：混批会让同 label 的两场撞 key
  （实测雄安 #219×#223 一次 commit 双写 7 道）
* 每场**先干跑再看账**，账不对就不按 `--commit`：中途一场不干净必须停下来，
  不把后面的场连着跑完
* `merge ≥ 半数` 说明这一整场多半就是库里已有的重复卷 —— 这种场**不自动入库**，
  只记进日志等人改队列状态（自动跳＝悄悄丢一整场）
* 入库题数、跳过几道、升级几道要逐场落账，`录题收尾.py` 才有东西可写

zsh 会把备注里的反引号当命令替换、静默吃掉还退 0 —— 所以全程 subprocess 传参数列表。
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "数据/录题/输出_v2"
QFILE = ROOT / "数据/录题/Qoder录题队列.json"
LOG = ROOT / "数据/录题/批量入库.jsonl"

DUP_RE = re.compile(r"dup=\{'new': (\d+), 'merge': (\d+), 'suspect': (\d+), 'upgrade': (\d+)\}")
CNT_RE = re.compile(r"count=(\d+)")
OK_RE = re.compile(r"ok=(\w+) added=(\d+) upgraded=(\d+) skipped=(\d+)")


def scene_file(no: str) -> Path:
    hits = sorted(glob.glob(str(V2 / ("%s_*.成品.json" % no))))
    if not hits:
        sys.exit("⛔ 序号 %s 没有成品文件（输出_v2/%s_*.成品.json）" % (no, no))
    if len(hits) > 1:
        # 一个序号两份成品（实测 #215 的 A 卷/B 卷）——挑哪份是人定的事
        sys.exit("⛔ 序号 %s 有 %d 份成品，得人来定：%s"
                 % (no, len(hits), [Path(h).name[:46] for h in hits]))
    return Path(hits[0])


def next_scenes(n: int) -> list[str]:
    q = json.loads(QFILE.read_text(encoding="utf-8"))
    have = {Path(f).name.split("_")[0] for f in glob.glob(str(V2 / "*.成品.json"))}
    out = [str(r["序号"]) for r in q["队列"]
           if r.get("状态") == "已解析-待入库" and str(r["序号"]) in have]
    return out[:n]


def call(path: Path, commit: bool) -> tuple[int, str]:
    cmd = [sys.executable, str(ROOT / "脚本/录题入库.py"), str(path)]
    if commit:
        cmd.append("--commit")
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = p.stdout + (("\n" + p.stderr) if p.stderr.strip() else "")
    print(out.rstrip(), flush=True)
    return p.returncode, out


def parse(out: str) -> dict:
    m = DUP_RE.search(out)
    c = CNT_RE.search(out)
    k = OK_RE.search(out)
    return {"new": int(m.group(1)) if m else None,
            "merge": int(m.group(2)) if m else None,
            "suspect": int(m.group(3)) if m else None,
            "upgrade": int(m.group(4)) if m else None,
            "count": int(c.group(1)) if c else None,
            "added": int(k.group(2)) if k else None,
            "upgraded": int(k.group(3)) if k else None,
            "skipped": int(k.group(4)) if k else None}


def pending_registry(path: Path) -> int:
    f = Path(str(path).replace(".成品.json", ".待复核.json"))
    if not f.exists():
        return 0
    try:
        return len(json.loads(f.read_text(encoding="utf-8")))
    except ValueError:
        return 0


def finish(no: str, added: int, pending: int, note: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "脚本/录题收尾.py"),
                    str(no), str(added), str(pending), note],
                   cwd=ROOT, check=True, capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*", help="队列里的序号")
    ap.add_argument("--next", type=int, default=0)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()
    nos = [str(x) for x in a.scenes] + (next_scenes(a.next) if a.next else [])
    if not nos:
        sys.exit("既没点名序号也没给 --next")
    done, blocked = [], []
    print("%s：%d 场" % ("入库" if a.commit else "干跑（不写库）", len(nos)))
    for i, no in enumerate(nos, 1):
        path = scene_file(no)
        print("\n[%d/%d] %s" % (i, len(nos), path.name[:64]), flush=True)
        t0 = time.time()
        rec: dict = {"序号": int(no), "场": path.name,
                     "模式": "commit" if a.commit else "dry"}
        rc, out = call(path, False)               # ① 先干跑
        rec.update({"干跑退出码": rc, **{"干跑_" + k: v for k, v in parse(out).items()}})
        if rc:
            rec["结论"] = "干跑不干净"
            _log(rec)
            sys.exit("⛔ %s 干跑就不干净，停下来人工看，不把后面的场连着跑" % path.name[:50])
        if (rec["干跑_merge"] or 0) * 2 >= (rec["干跑_count"] or 1):
            rec["结论"] = "疑似整场撞车，未入库"
            _log(rec)
            blocked.append(no)
            print("⛔ 判重 %s/%s 题已在库 —— 疑似整场重复卷，**没有入库**，等人工裁队列状态"
                  % (rec["干跑_merge"], rec["干跑_count"]))
            continue
        if a.commit:
            rc2, out2 = call(path, True)          # ② 账对了才真入库
            c = parse(out2)
            rec["入库_"] = c
            if rc2 or c["added"] is None:
                rec["结论"] = "commit 失败"
                _log(rec)
                sys.exit("⛔ %s 干跑过了但 commit 退回 %s，停" % (path.name[:50], rc2))
            note = "入库 %d 题；判重跳过 %d；升级 %d；相似 %d" % (
                c["added"], c["skipped"], c["upgraded"], rec["干跑_suspect"])
            finish(no, c["added"], pending_registry(path), note)
            rec["结论"] = "done"
            done.append(no)
            print("✓ " + note)
        else:
            rec["结论"] = "干跑通过"
        _log(rec)
    print("\n小结：%s" % ("入库 %d 场" % len(done) if a.commit else "干跑通过 %d 场" % len(nos)))
    if blocked:
        print("⚠️ 疑似整场撞车、没入库的序号：%s" % " ".join(blocked))


def _log(rec: dict) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
