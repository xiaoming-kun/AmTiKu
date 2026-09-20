#!/usr/bin/env python3
r"""生成录题进度看板：数据/录题/Qoder录题进度看板.md

给谁看：用户随时打开这个文件就知道「跑到哪了、还要多久、有什么卡住」，
不用去翻 jsonl 和队列 JSON。自动任务每小时刷一次。

用法：python3 脚本/录题进度看板.py
只读不写题库；写出来的 md 也在 数据/录题/ 下，不碰 题目/。
生成后单独 git 提交这一个文件（绝不 git add -A），每次都留痕。
"""
import json, subprocess, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "数据/录题"
OUT = SRC / "Qoder录题进度看板.md"


def read_json(p):
    return json.loads((SRC / p).read_text(encoding="utf-8"))


def rate_hours(n_todo, span_min):
    """按最近 span_min 分钟内做了多少场，估还剩多少小时。"""
    prog = [json.loads(l) for l in (SRC / "Qoder录题进度.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cut = time.time() - span_min * 60
    done_recent = [p for p in prog
                   if p.get("状态") in ("已解析-待入库", "done")
                   and time.mktime(time.strptime(p["时间"], "%Y-%m-%d %H:%M")) > cut]
    if not done_recent:
        return None, 0
    per_hour = len(done_recent) / (span_min / 60.0)
    return (n_todo / per_hour if per_hour else None), len(done_recent)


def commit_board(msg):
    """只提交看板这一个文件。抢不到 index.lock（解析任务正在提交）就不提交、不重试，
    改动留在工作区，下一场自动任务会顺手带上。"""
    rel = str(OUT.relative_to(ROOT))

    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    def err(out):
        return (out.stderr or out.stdout).strip().splitlines()[-1:] or ["无输出"]

    add = git("add", "--", rel)
    if add.returncode:
        print("看板未提交（git add 失败）：%s" % "；".join(err(add)), file=sys.stderr)
        return
    if not git("diff", "--cached", "--quiet", "--", rel).returncode:
        print("看板内容无变化，未提交")
        return
    c = git("commit", "-m", msg)
    if c.returncode:
        print("看板未提交（git commit 失败）：%s" % "；".join(err(c)), file=sys.stderr)
    else:
        print("已提交：" + msg)


def main():
    q = read_json("Qoder录题队列.json")["队列"]
    st = Counter(x["状态"] for x in q)
    todo = st.get("todo", 0)
    again = st.get("待重解析-曾判撞车", 0)
    parsed = st.get("已解析-待入库", 0)
    ingested = st.get("done", 0)
    skipped = st.get("跳过-已在库", 0)
    dupfile = sum(v for k, v in st.items() if k.startswith("跳过-与"))
    left = todo + again

    files = sorted((SRC / "输出_v2").glob("*.成品.json"))
    nq = sum(len(json.loads(f.read_text(encoding="utf-8"))) for f in files)
    pend = Counter()
    np_ = 0
    for f in (SRC / "输出_v2").glob("*.待复核.json"):
        for e in json.loads(f.read_text(encoding="utf-8")):
            pend[e.get("类型", "?")] += 1
            np_ += 1

    est_a, cnt_a = rate_hours(left, 60)
    est_b, cnt_b = rate_hours(left, 600)

    lock = subprocess.run([sys.executable, str(ROOT / "脚本/录题锁.py"), "status"],
                          capture_output=True, text=True).stdout.strip()

    prog = [json.loads(l) for l in (SRC / "Qoder录题进度.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    recent = [p for p in prog if p.get("状态") in ("已解析-待入库", "done")][-12:]

    L = []
    L.append("# 录题进度看板\n")
    L.append("生成时间：%s（本文件由 `脚本/录题进度看板.py` 覆盖写，自动任务每小时刷一次）\n"
             % time.strftime("%Y-%m-%d %H:%M"))
    L.append("## 一句话\n")
    L.append("队列 %d 场：**%d 场已入库**、**%d 场已解析成成品待入库**、**剩 %d 场待解析**"
             "（%d 场从没做过 + %d 场早期误判跳过要重做）。"
             "另有 %d 场经题干比对确认库里已有、%d 场是同一场的重复文件，都不必再做。\n"
             % (len(q), ingested, parsed, left, todo, again, skipped, dupfile))
    L.append("累计成品 **%d 份 / %d 题**；待复核登记 **%d 条**。\n" % (len(files), nq, np_))

    L.append("## 速度\n")
    if est_a:
        L.append("- 最近 1 小时做了 %d 场 → 照这个速度约 **%.0f 小时**（%.1f 天）跑完" % (cnt_a, est_a, est_a / 24))
    if est_b:
        L.append("- 最近 10 小时做了 %d 场 → 照这个速度约 **%.0f 小时**（%.1f 天）跑完" % (cnt_b, est_b, est_b / 24))
    if not (est_a or est_b):
        L.append("- 最近 10 小时没有新完成的场次，速度暂时算不出来（看下面「并发锁」）")
    L.append("")

    L.append("## 待复核都登记了什么\n")
    名 = {"figure": "带图题（不录正文）", "table": "带表题（不录正文）",
          "figure-in-solution": "题干已录、解析里印着图", "print-suspect": "原卷印刷疑点（照录未改）",
          "missing-option": "原卷缺整条选项（照录未补）"}
    for k in ("figure", "table", "figure-in-solution", "print-suspect"):
        if pend.get(k):
            L.append("- %s：%d 条" % (名.get(k, k), pend[k]))
    for k in pend:
        if k not in 名:
            L.append("- %s：%d 条" % (k, pend[k]))
    L.append("")

    L.append("## 最近完成的 12 场\n")
    L.append("| 时间 | 卷名 | 状态 | 待复核 |")
    L.append("|---|---|---|---|")
    for p in recent:
        L.append("| %s | %s | %s | %s |" % (p["时间"][5:], p["卷名"][:34], p["状态"], p.get("待复核", 0)))
    L.append("")

    L.append("## 下一场\n")
    nxt = [x for x in sorted(q, key=lambda x: x["序号"]) if x["状态"] == "todo"][:5]
    for x in nxt:
        L.append("- #%s %s（试卷 %d 个文件、答案 %d 个文件）"
                 % (x["序号"], x["卷名"], len(x["试卷"]), len(x["答案"])))
    if not nxt:
        L.append("- todo 已清空，接下来轮到 `待重解析-曾判撞车` 那批")
    L.append("")

    L.append("## 并发锁\n")
    L.append("- %s\n" % lock)

    L.append("## 挂起、需要人决定的\n")
    L.append("- **入库通道没开**：成品只落在 `数据/录题/输出_v2/`，一场都没进题库。"
             "本机 `amti.solve` 在写库，规范要求同一时刻只允许一条链路写库；"
             "等求解跑完再一次性 `preview → commit → accept 四层验收`。")
    noans = [x for x in q if x["状态"] in ("todo", "待重解析-曾判撞车") and not x["答案"]]
    L.append("- **无答案卷 %d 场**：按口径照录、答案/解析留空，入库后会成为待补题，"
             "需要接「补欠」那条线。" % len(noans))
    L.append("- **%d 场早期只按文件名判的撞车**已退回 `待重解析-曾判撞车`，排在 todo 之后；"
             "另有 14 场已确认误判并恢复。" % again)
    L.append("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(OUT.relative_to(ROOT))
    commit_board("录题看板：剩 %d 场待解析，累计成品 %d 份 / %d 题，待复核 %d 条"
                 % (left, len(files), nq, np_))


if __name__ == "__main__":
    main()
