#!/usr/bin/env python3
r"""生成录题进度看板：数据/录题/Qoder录题进度看板.md

给谁看：用户随时打开这个文件就知道「跑到哪了、还要多久、有什么卡住」，
不用去翻 jsonl 和队列 JSON。自动任务每小时刷一次。

用法：python3 脚本/录题进度看板.py
只读不写题库；写出来的 md 也在 数据/录题/ 下，不碰 题目/。
`数据/` 自 2026-09-21 起进了 .gitignore ⇒ 本文件不再由 commit 保护，别 `git add -f`。
"""
import json, subprocess, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "数据/录题"
OUT = SRC / "Qoder录题进度看板.md"

# 客观题：答案栏本就该有值。解答题按口径留空（入库时 normalize 补「见解析」），不算缺口。
OBJ_TYPES = {"single_choice", "multi_choice", "fill_in_blank"}
EMPTY_EXPS = {"", "解析无", "解析无。", "无"}


def read_json(p):
    return json.loads((SRC / p).read_text(encoding="utf-8"))


def completed_rows(prog):
    """每场只留最后一次记账。一场会被记多行（首解析＋补解析／订正各一行），
    按行计数的话同一场会被数成好几场；锚点按规范用卷名。"""
    by_book = {}
    for p in prog:
        if p.get("状态") in ("已解析-待入库", "done"):
            by_book[p["卷名"]] = p
    return list(by_book.values())


def stamp_min(s):
    """进度行的「时间」人手补记时也直接写，格式没有约束（现读已有 3 行写成「20:4x」）。
    解不出来就当「不知道」，别让一行脏数据把整个看板停更。"""
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%d %H:%M"))
    except (TypeError, ValueError):
        return None


def rate_hours(n_todo, span_min):
    """按最近 span_min 分钟内做了多少场，估还剩多少小时。"""
    prog = [json.loads(l) for l in (SRC / "Qoder录题进度.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cut = time.time() - span_min * 60
    done_recent = [p for p in completed_rows(prog)
                   if (stamp_min(p.get("时间")) or 0) > cut]
    if not done_recent:
        return None, 0
    per_hour = len(done_recent) / (span_min / 60.0)
    return (n_todo / per_hour if per_hour else None), len(done_recent)


def eta_text(n_todo, est):
    # 「做了 0 场」与「做了 N 场但剩余 0」是两回事，别拿估时的真假去判有没有活
    if not n_todo:
        return "（剩余待解析 0 场 ⇒ 不必再估时）"
    return " → 照这个速度约 **%.0f 小时**（%.1f 天）跑完" % (est, est / 24)


def commit_board(msg):
    """只提交看板这一个文件。抢不到 index.lock（解析任务正在提交）就不提交、不重试，
    改动留在工作区，下一场自动任务会顺手带上。"""
    rel = str(OUT.relative_to(ROOT))

    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    def err(out):
        return (out.stderr or out.stdout).strip().splitlines()[-1:] or ["无输出"]

    # 2026-09-21 20:56 起 数据/ 整个进了 .gitignore（git 只管代码/配置/文档）。
    # 这段自提交是那天凌晨写的，比规矩改动早，现在每次都会失败 —— 别报错，安静跳过。
    if git("check-ignore", "-q", "--", rel).returncode == 0:
        print("看板不提交：%s 已被 .gitignore 排除（数据/ 不进 git，成品防丢靠磁盘与 backup）"
              % rel)
        return
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
    # 这一列只有 done 档能当入库账：非 done 的那批把成品题数误填了进来（A97 实测其卷名在库里 0 命中）
    ingested_q = sum(int(x.get("入库题数") or 0) for x in q if x["状态"] == "done")
    skipped = st.get("跳过-已在库", 0)
    dupfile = sum(v for k, v in st.items() if k.startswith("跳过-与"))
    left = todo + again

    files = sorted((SRC / "输出_v2").glob("*.成品.json"))
    nq = 0
    no_ans = no_exp = fld_ans = fld_exp = 0
    # 按成品实测的两本账：答案栏填了多少、闸（`ingest._incomplete_errors`，只认字面空串）
    # 会拦多少。队列 `答案[]` 是快照，登记不全 ≠ 磁盘上没有答案件（见下面「答案卷」那条）。
    filled_by = {}
    total_by = {}
    blocked_by = {}
    for f in files:
        recs = json.loads(f.read_text(encoding="utf-8"))
        nq += len(recs)
        a = [r for r in recs if r.get("题型") in OBJ_TYPES and not (r.get("答案") or "").strip()]
        e = [r for r in recs if (r.get("解析") or "").strip().replace(" ", "") in EMPTY_EXPS]
        no_ans += len(a); no_exp += len(e)
        fld_ans += bool(a); fld_exp += bool(e)
        seq = f.name.split("_", 1)[0]
        g = [r for r in recs if not (r.get("解析") or "").strip()
             or (r.get("题型") in OBJ_TYPES and not (r.get("答案") or "").strip())]
        total_by[seq] = total_by.get(seq, 0) + len(recs)
        filled_by[seq] = filled_by.get(seq, 0) + sum(1 for r in recs if (r.get("答案") or "").strip())
        blocked_by[seq] = blocked_by.get(seq, 0) + len(g)
    n_side = sum(len(json.loads(f.read_text(encoding="utf-8")))
                 for f in (SRC / "输出_v2").glob("*.解答.json"))
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
    recent = sorted(completed_rows(prog), key=lambda p: p["时间"])[-12:]

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
    if not (cnt_a or cnt_b):
        L.append("- 最近 10 小时没有新完成的场次，速度暂时算不出来（看下面「并发锁」）")
    else:
        if cnt_a:
            L.append("- 最近 1 小时做了 %d 场%s" % (cnt_a, eta_text(left, est_a)))
        if cnt_b:
            L.append("- 最近 10 小时做了 %d 场%s" % (cnt_b, eta_text(left, est_b)))
    bad_time = [p for p in completed_rows(prog) if stamp_min(p.get("时间")) is None]
    if bad_time:
        L.append("- ⚠️ %d 场的记账 `时间` 不是 `%Y-%m-%d %H:%M`（如 `%s`），已排除在上面的计数之外"
                 % (len(bad_time), bad_time[0]["时间"]))
    L.append("")

    L.append("## 待复核都登记了什么\n")
    名 = {"figure": "带图题（不录正文）", "table": "带表题（不录正文）",
          "figure-in-solution": "题干已录、解析里印着图", "print-suspect": "原卷印刷疑点（照录未改）",
          "missing-option": "原卷缺整条选项（照录未补）"}
    for k in ("figure", "table", "figure-in-solution", "print-suspect", "missing-option"):
        if pend.get(k):
            L.append("- %s：%d 条" % (名.get(k, k), pend[k]))
    for k in pend:
        if k not in 名:
            L.append("- %s：%d 条" % (k, pend[k]))
    L.append("")

    L.append("## 最近完成的 %d 场（一场多行的只留最后一次记账）\n" % len(recent))
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
        rows = [x for x in sorted(q, key=lambda x: x["序号"])
                if x["状态"] == "待重解析-曾判撞车"][:5]
        if rows:
            L.append("- todo 已清空，接下来轮到 `待重解析-曾判撞车` 那批 %d 场（从 #%s 起）"
                     % (again, rows[0]["序号"]))
        else:
            L.append("- todo 与 `待重解析-曾判撞车` 均已清空 ⇒ **解析线没有可认领的场**，"
                     "剩下的是入库与人工裁决，等用户批准")
    L.append("")

    L.append("## 并发锁\n")
    L.append("- %s\n" % lock)

    L.append("## 挂起、需要人决定的\n")
    L.append("- **入库通道开过 %d 场 / %d 题**（队列里 `done` 那批的 `入库题数` 合计）："
             "其余 %d 场成品只落在 `数据/录题/输出_v2/`，一道都没进题库。"
             "规范要求同一时刻只允许一条链路写库，且用户口径是「全部解析完再一次性入库」；"
             "入库要等用户批准，批前先 `preview`，再 `accept` 四层验收。"
             % (ingested, ingested_q, parsed))
    noans_all = [x for x in q if not x["答案"]]
    noans_parsed = sum(1 for x in noans_all if x["状态"] == "已解析-待入库")
    noans_left = sum(1 for x in noans_all if x["状态"] in ("todo", "待重解析-曾判撞车"))
    noans_other = "%s %d 场" % ("/".join(sorted({x["状态"] for x in noans_all
                                                 if x["状态"] not in ("已解析-待入库", "todo", "待重解析-曾判撞车")})),
                                len(noans_all) - noans_parsed - noans_left) \
        if len(noans_all) - noans_parsed - noans_left else "无"
    # 队列 `答案[]` 是**录入时的快照**，答案件常没登记进去（另存一个文件、或与卷面合在
    # 同一个 PDF 里）⇒ 判「有没有答案」只能读成品答案栏，不能读这个字段。
    def filled_of(x):
        fs = [f for f in files if f.name.startswith("%d_" % x["序号"])]
        return sum(filled_by.get(f.name.split("_", 1)[0], 0) for f in fs), len(fs)
    dry = [x for x in noans_all if not filled_of(x)[0]]
    dry_txt = "、".join("#%s %s%s" % (x["序号"], x["卷名"],
                                      "" if filled_of(x)[1] else "（无成品）") for x in dry) or "无"
    blk_n = sum(blocked_by.values())
    blk_f = sum(1 for v in blocked_by.values() if v)
    blk_all = sum(1 for k, v in blocked_by.items() if v and v == total_by.get(k))
    L.append("- **答案卷**：队列 `答案[]` 为空的 **%d 场**（%d 场已解析、%d 场还没做、%s）是**快照口径**，"
             "不等于磁盘上没有答案件——按成品答案栏实测，其中 **%d 场是取到答案的**；"
             "**真的一道答案没取到的 %d 场**：%s。\n"
             % (len(noans_all), noans_parsed, noans_left, noans_other,
                len(noans_all) - len(dry), len(dry), dry_txt))
    L.append("  入库闸 `_incomplete_errors()` 只认**字面空串**（写「解析无」的它放行），现读会拦 "
             "**%d 道 / %d 场**（整场级 %d 场，其余 %d 场是零头题）；"
             "闸按整批拒，所以怎么定仍要用户拍板（另寻答案卷 / 允许模型作答 / 开豁免口子）。"
             % (blk_n, blk_f, blk_all, blk_f - blk_all))
    L.append("- **内容级实测**（只读扫 %d 份成品）：客观题答案栏为空 **%d 道 / %d 场**；"
             "解析为空或写「解析无」**%d 道 / %d 场**，其中 `*.解答.json` 已备好待转录的 **%d 道**"
             "（那份是 sidecar，入库只读 `.成品.json`，不转录就不进库）。"
             % (len(files), no_ans, fld_ans, no_exp, fld_exp, n_side))
    if again:
        L.append("- **%d 场早期只按文件名判的撞车**已退回 `待重解析-曾判撞车`，排在 todo 之后；"
                 "另有 14 场已确认误判并恢复。" % again)
    else:
        L.append("- 早期「只按文件名判撞车」那批已全部处理完（`待重解析-曾判撞车` 现 0 场）。")
    L.append("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(OUT.relative_to(ROOT))
    commit_board("录题看板：剩 %d 场待解析，累计成品 %d 份 / %d 题，待复核 %d 条"
                 % (left, len(files), nq, np_))


if __name__ == "__main__":
    main()
