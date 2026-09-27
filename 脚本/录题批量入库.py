#!/usr/bin/env python3
r"""**顺序**驱动器：一场一场调 `脚本/录题入库.py`，它自己不做任何入库动作。

    python3 脚本/录题批量入库.py 101 102 103            # 只看账（干跑，不写库）
    python3 脚本/录题批量入库.py --next 20              # 按队列顺序看接下来 20 场
    python3 脚本/录题批量入库.py --next 20 --commit      # 真入库，一场一次 commit

为什么要这么一层，而不是在 shell 里 for 循环：

* **一场一次 commit** 是 §6 红线：混批会让同 label 的两场撞 key
  （实测雄安 #219×#223 一次 commit 双写 7 道）
* 「疑似整场重复卷」那道闸由 `录题入库.py` 自己拦（判重≥半数），拦下来的场
  **只记日志不改队列状态** —— 改状态说"这场没了"是人的事
* 写法缺陷（preview 不干净：花括号配不平、印漏式子……）同样**只记日志、跳过这场**，
  剩下三百多场不该为一道的转录缺陷排队；名单在收工小结里一次性交出来
* 入库题数、跳过几道、升级几道要逐场落账，`录题收尾.py` 才有东西可写
* zsh 会把备注里的反引号当命令替换、静默吃掉还退 0 —— 全程 subprocess 传参数列表绕开

**标签为什么延后刷**：commit 每产出一项升级就要 `rewrite_all` 整库重写
（51MB 重写＋52MB 备份），实测一批 20 场有 18 场带升级 ⇒ 每场白搭三十秒。
所以逐场走 `--defer-upgrades`（只追加、该刷的记进 `待刷标签.jsonl`），
一批跑完 `脚本/刷标签.py` 一次落账。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
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


def blocked_scenes() -> set[int]:
    """日志里已经判过「疑似整场重复卷」的序号。

    `--next` 要绕开它们：这种场不改队列状态就会一直排在队首，
    每次跑批都在同一场上撞停，等于后面全堵死。
    """
    out = set()
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("结论") in ("被拦-疑似整场重复", "被拦-preview不干净"):
                out.add(r.get("序号"))
    return out


def ambiguous_scenes() -> set[int]:
    """一个序号挂两份成品的（实测 #53、#215）—— 挑哪份入库是人定的事。"""
    n: dict[int, int] = {}
    for f in glob.glob(str(V2 / "*.成品.json")):
        k = Path(f).name.split("_")[0]
        if k.isdigit():
            n[int(k)] = n.get(int(k), 0) + 1
    return {k for k, v in n.items() if v > 1}


def next_scenes(n: int) -> list[str]:
    q = json.loads(QFILE.read_text(encoding="utf-8"))
    have = {Path(f).name.split("_")[0] for f in glob.glob(str(V2 / "*.成品.json"))}
    # 绕开两类：判过「疑似整场重复卷」的（不改状态就会每批在同一场撞停）、
    # 一个序号两份成品的（`scene_file` 会直接退出，把整批带走）。
    skip = blocked_scenes() | ambiguous_scenes()
    out = [str(r["序号"]) for r in q["队列"]
           if r.get("状态") == "已解析-待入库" and str(r["序号"]) in have
           and r["序号"] not in skip]
    return out[:n]


def call(path: Path, commit: bool, defer: bool = False, allow_dup: bool = False) -> tuple[int, str]:
    cmd = [sys.executable, str(ROOT / "脚本/录题入库.py"), str(path)]
    if commit:
        cmd.append("--commit")
        if defer:
            cmd.append("--defer-upgrades")
        if allow_dup:
            cmd.append("--allow-mostly-dup")
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
    # `AMTIKU_SIMLIST=0`：逐场不做「读全库重刷库内模拟卷清单」，批末统一刷一次
    subprocess.run([sys.executable, str(ROOT / "脚本/录题收尾.py"),
                    str(no), str(added), str(pending), note],
                   cwd=ROOT, check=True, capture_output=True, text=True,
                   env={**os.environ, "AMTIKU_SIMLIST": "0"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenes", nargs="*", help="队列里的序号")
    ap.add_argument("--next", type=int, default=0)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--no-defer", action="store_true",
                    help="升级不延后，逐场内联刷（每产出一项升级就整库重写一次，慢三十秒/场）")
    ap.add_argument("--no-flush", action="store_true",
                    help="批末不把待刷标签落账（留着自己跑 脚本/刷标签.py）")
    ap.add_argument("--allow-mostly-dup", action="store_true",
                    help="放开「判重≥半数＝疑似整场重复卷」这道闸：整场里**库里没有的那几道**"
                         "值得留下（逐字重复的那批照样被指纹闸吞掉、不会写第二份）")
    a = ap.parse_args()
    nos = [str(x) for x in a.scenes] + (next_scenes(a.next) if a.next else [])
    if not nos:
        sys.exit("既没点名序号也没给 --next")
    defer = a.commit and not a.no_defer
    done, blocked, defect, secs = [], [], [], []
    print("%s%s：%d 场" % ("入库" if a.commit else "干跑（不写库）",
                          "，升级延后到批末" if defer else "", len(nos)), flush=True)
    for i, no in enumerate(nos, 1):
        path = scene_file(no)
        print("\n[%d/%d] %s" % (i, len(nos), path.name[:64]), flush=True)
        t0 = time.time()
        rec: dict = {"序号": int(no), "场": path.name,
                     "模式": "commit" if a.commit else "dry", "defer": defer}
        rc, out = call(path, a.commit, defer, a.allow_mostly_dup)
        rec.update(parse(out))
        rec["秒"] = round(time.time() - t0, 1)
        secs.append(rec["秒"])
        if rec["秒"] > 120:
            # 实测有两场各卡了 596 / 947 秒，而同一场单独干跑只要 4 秒
            # —— 卡的是落盘那一下（备份 52MB＋整库重写的磁盘突发，怀疑撞上 Time Machine），
            # 不是脚本逻辑。这种场必须看得见，不然整批的账会被平均数藏掉。
            print("⚠️ 这场用了 %.0f 秒（中位数才 %.0f 秒）—— 单独重跑一遍确认是不是盘的问题"
                  % (rec["秒"], sorted(secs)[len(secs) // 2]), flush=True)
        if rc:
            if "疑似整场重复卷" in out:
                rec["结论"] = "被拦-疑似整场重复"
                _log(rec)
                blocked.append(no)
                print("⛔ %s 疑似整场重复卷，**没入库**，继续下一场（改队列状态要人来裁）"
                      % path.name[:40])
                continue
            if "preview 不干净" in out:
                # 写法缺陷（花括号配不平、印漏式子…）：这一场不入库，但**不把整批停掉**。
                # 停下来的代价是剩下三百场都排队；跳过的前提是名单必须交到人手里。
                rec["结论"] = "被拦-preview不干净"
                rec["原因"] = (out.split("problems: ")[1][:300] if "problems: " in out
                               else out.split("⛔")[0][-300:])
                _log(rec)
                defect.append(no)
                print("⛔ %s 写法有缺陷，没入库（已记进缺陷名单，继续下一场）" % path.name[:40])
                continue
            rec["结论"] = "被拦"
            _log(rec)
            sys.exit("⛔ %s 被拦且不是上面两类（见上一段输出），停下来人工看" % path.name[:50])
        if a.commit:
            if rec["added"] is None:
                rec["结论"] = "commit 没报账"
                _log(rec)
                sys.exit("⛔ %s commit 退 0 却没报出 added，收尾不写账，先人来核" % path.name[:50])
            note = "入库 %d 题；判重跳过 %d；升级 %d；相似 %d" % (
                rec["added"], rec["skipped"], rec["upgraded"], rec["suspect"])
            finish(no, rec["added"], pending_registry(path), note)
            rec["结论"] = "done"
            done.append(no)
            print("✓ %s（%.0f 秒）" % (note, rec["秒"]))
        else:
            rec["结论"] = "干跑通过"
        _log(rec)
    print("\n小结：%s" % ("入库 %d 场" % len(done) if a.commit
                          else "干跑通过 %d 场" % len(nos)))
    if secs:
        print("每场中位 %.0f 秒（最快 %.0f / 最慢 %.0f）"
              % (sorted(secs)[len(secs) // 2], min(secs), max(secs)))
    if blocked:
        print("⛔ 判重过半（疑似整场重复卷）、没入库的序号：%s" % " ".join(blocked))
    if defect:
        print("⛔ 写法缺陷、没入库的序号：%s（逐条原因见 批量入库.jsonl 的「原因」列）"
              % " ".join(defect))
    amb = sorted(ambiguous_scenes())
    if amb:
        print("⚠️ 一个序号挂两份成品、`--next` 绕过的序号：%s" % " ".join(str(x) for x in amb))
    if a.commit and not a.no_flush:
        if defer:
            print("\n—— 批末落账：待刷标签 ——", flush=True)
            subprocess.run([sys.executable, str(ROOT / "脚本/刷标签.py")], cwd=ROOT)
        # 逐场省掉的「库内模拟卷清单」在这儿补刷一次（下一批的撞车预检才准）
        subprocess.run([sys.executable, str(ROOT / "脚本/录题收尾.py"), "--simlist"],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        print("\n—— 批末刷库内模拟卷清单（逐场省下的那三四秒在这里补上）——", flush=True)
        subprocess.run([sys.executable, str(ROOT / "脚本/录题收尾.py"), "--simlist"],
                       cwd=ROOT)


def _log(rec: dict) -> None:
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
