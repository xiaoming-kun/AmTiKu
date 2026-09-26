#!/usr/bin/env python3
r"""录题入库：成品 JSON → Question → preview → commit（走 ingest 唯一入口）。

用法：python3 脚本/录题入库.py <成品.json> [--commit] [--force] [--skip 3,7]
                       [--defer-upgrades] [--allow-mostly-dup]
不带 --commit 只干跑。preview 有 errors / problems / missing_images 时**拒绝入库**。
`--force` = 库里已有同 key 且解析非空时，以手里这份为准（补录解析用）。

`--defer-upgrades`：本批**只追加、不动存量**。该刷给库里重复题的考点/难度记进
`数据/录题/待刷标签.jsonl`，一批跑完由 `脚本/刷标签.py` 一次落账。
为什么要有这个开关：commit 只要产出一项升级就得整库重写（51MB 重写＋52MB 备份），
而实测一批 20 场里 18 场都带升级 ⇒ 每场白搭三十秒。

`--allow-mostly-dup`：放开「**判重≥半数＝疑似整场重复卷**」这道闸。
默认拦：这种场多半是同一场考试换了个卷名又录了一遍（实测 #7 武汉九调 11/17 题
指纹已在库里），该人来裁队列状态，不该由脚本顺手写进去。
"""
import datetime as _dt
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amti import record2 as R2, store, ingest

# 入库前就算好的考点标签（`脚本/补考点成品.py merge` 产出）。
# 为什么不在入库后再补：那要走 `store.rewrite_all()` 全库重写，
# 而 `points` 不参与 content_hash，入库时一次带进去是零风险的。
LABELS = Path(__file__).resolve().parent.parent / ".tobias/分类/成品标签.json"

# `--defer-upgrades` 攒下来的账单：一批场跑完后 `脚本/刷标签.py` 一次落账。
# 为什么攒着：commit 每产出一项升级就要 `rewrite_all` 整库重写（51MB）＋备份（52MB）。
LABEL_JOURNAL = Path(__file__).resolve().parent.parent / "数据/录题/待刷标签.jsonl"
_points_cache = None


def lab_key(path, no):
    r"""成品文件 + 题号 → 标签文件里的 key。

    **保留 `<序号>_` 前缀**：`re_label` 会把它剥掉，而队列里确实有重名卷
    （不同序号、同一卷名），剥掉前缀两道不同的题就共用一套标签了。
    """
    return "%s#%s" % (Path(path).name[: -len(".成品.json")], no)


def load_points():
    global _points_cache
    if _points_cache is None:
        _points_cache = {}
        if LABELS.exists():
            for r in json.loads(LABELS.read_text(encoding="utf-8")):
                _points_cache[r["key"]] = list(r.get("points") or [])
    return _points_cache


def attach_points(path, recs, qs):
    r"""把考点挂到 `Question` 上。**难度、星级随之派生**
    （`schema.Question.difficulty` 取 `knowledge.difficulty_of(points[0])`），
    所以不用单独补难度。
    """
    lab = load_points()
    n = 0
    for r, q in zip(recs, qs):
        pts = lab.get(lab_key(path, r["题号"]))
        if not pts:
            continue
        q.points = list(pts)
        q.meta["point_source"] = "llm"      # 与库里既有的 17679 道同一个口径
        n += 1
    return n


def derive_year(label):
    r"""卷名 → `meta.year`。**库内惯例是毕业届年份，不是卷面出现的第一个年份**。

    原先只认 `label[:4]`，而 570 份成品里有 233 份（4036 题）把年份写在卷名中间
    （「湖北荆门2026届高三…」）⇒ 入库后 `meta.year` 整个不写，这些题在年份筛选、
    统计页的 by_year 里全部隐身。存量模拟题逐条对过：卷名前四位与 `meta.year`
    一致 876／不一致 13，那 13 条全是「2025年11月…」按学年记成 2026，
    所以「2025-2026学年」这种区段取**后一个**才是同一个口径。
    """
    rng = re.search(r"(?<!\d)(20\d\d)\s*[-—–~至]\s*(20\d\d)(?!\d)", label)
    if rng:
        return int(rng.group(2))
    head = re.match(r"20\d\d(?!\d)", label)
    if head:
        return int(head.group())
    m = re.search(r"(?<!\d)20\d\d(?!\d)", label)
    return int(m.group()) if m else None


# 「缺答案/缺解析」是**入库**闸门（`ingest._incomplete_errors`，2026-09-21 新规矩）拦的，
# 不是解析阶段的失败。无答案卷的成品本来就该空着，把它算进失败会逼执行的人去凑答案
# ——那是伪造原卷内容。所以按「是不是这道闸拦的」分流，只有**其它**错误才算失败。
# 精确匹配 `ingest` 的固定句式，不用「缺」+「答案」这种宽松关键词——会误吞真正的错误。
INC_REASON = "本库规矩：没有答案或没有解析的题目不许入库"
_INC_REASON = INC_REASON          # 旧名沿用，免得别处已经引用


def incomplete(e) -> bool:
    return INC_REASON in json.dumps(e, ensure_ascii=False)


SOLVED_BY = "qoder/agent"      # 与本地求解线的 "qwen/qwen3.8-27b" 区分开

# 用户 2026-09-25 让补的那批答案：模型逐题解出来的，单独一个可审的文件。
# **不并进成品 JSON**——成品里印着的答案是原卷内容，混进去就分不清谁是谁的了。
GAP_ANSWERS = Path(__file__).resolve().parent.parent / "数据/录题/补答案_41题.json"
_answer_cache = None


def load_gap_answers():
    global _answer_cache
    if _answer_cache is None:
        _answer_cache = {}
        if GAP_ANSWERS.exists():
            for r in json.loads(GAP_ANSWERS.read_text(encoding="utf-8")):
                _answer_cache["%s#%s" % (r["场"], r["题号"])] = r
    return _answer_cache


def attach_answers(path, recs):
    r"""**只填本来就空的栏**（答案、解析各判各的），返回填了哪些题号。

    与 `merge_sidecar` 那条「不许取 sidecar 答案」的老规矩不冲突：
    这里读的是单独一份、逐条写明「agent/自解」的清单
    （`数据/录题/补答案_41题.json`），而且**原卷印了答案的一律不碰**——那是内容，不是缺口。
    必须在 `rec_to_question` **之前**调用：题的正文是从 recs 渲染的。
    不往 rec 里塞第 10 个键（成品固定 9 键，多出来的键会被 `tidy` 写回文件）。
    """
    lab = Path(path).name[: -len(".成品.json")]
    gap = load_gap_answers()
    filled, also_sol = [], []
    for r in recs:
        g = gap.get("%s#%s" % (lab, r["题号"]))
        if not g:
            continue
        cur_a = (r.get("答案") or "").strip()
        new_a = (g.get("答案") or "").strip()
        if not cur_a and new_a:
            r["答案"] = new_a
            filled.append((r["题号"], g.get("来源") or "agent/自解"))
        cur_s = (r.get("解析") or "").strip()
        new_s = (g.get("解析") or "").strip()
        if (not cur_s or cur_s == "解析无") and new_s:
            r["解析"] = new_s
            also_sol.append(r["题号"])
    return filled, also_sol



def merge_sidecar(path, recs):
    r"""把同名的 `.解答.json`（模型补写的解析）并进成品，**只填空、不覆盖原卷解析**。

    为什么需要：补解析那条线产出的是 sidecar（`输出_v2/<序号>_<卷名>.解答.json`），
    而本脚本原先只读 `.成品.json` ⇒ 3099 道补好的解析**一句都进不了库**，白躺在盘上。

    三条硬规矩：
    1. **只填 `解析` 为空或等于「解析无」的题**。原卷给了详解的一律不盖
       （sidecar 是模型写的，原卷是印刷的，可信度不对等）。
    2. **不取 sidecar 的 `答案`**。它是从成品抄过去的，拿它当判据是循环论证
       （实测「答案 100% 相同」就是这么来的，不代表答对率）。
    3. 题号对不上、或成品里根本没这道题的，**跳过并报告**，不猜。
    """
    sib = Path(str(path).replace(".成品.json", ".解答.json"))
    if not sib.exists():
        return 0, [], []
    try:
        sol = json.loads(sib.read_text(encoding="utf-8"))
    except Exception as e:
        return 0, [], ["sidecar 读不了：%s" % e]
    by_no = {}
    for r in sol:
        by_no.setdefault(r.get("题号"), r)
    have = {r.get("题号") for r in recs}
    filled, orphan = [], []
    for r in recs:
        cur = (r.get("解析") or "").strip()
        if cur and cur != "解析无":
            continue
        g = by_no.get(r.get("题号"))
        if not g:
            continue
        txt = (g.get("解析") or "").strip()
        if not txt:
            continue
        r["解析"] = txt          # 只写解析，不动 rec 的键集合（成品固定 9 键）
        filled.append(r["题号"])
    orphan = sorted(set(by_no) - have)
    return len(filled), filled, orphan


def drop_skipped(path, recs, skip):
    r"""按题号把个别题**从这一场的入库里摘掉**，用于「原卷自己印坏、四道闸都过不去」的题。

    为什么不放宽闸：`schema.problems()` 要求选项标号从 A 连续，这条不变量抓的正是
    **我们自己把选项抄丢**。为一道题去容忍非连续标号，等于把闸上开个能漏题的口子。
    也不补一个不存在的 C 选项——那是编造原卷没有的内容。
    所以摘出来单独挂着，但**必须在同场的 `.待复核.json` 里有登记**才让摘，
    免得「摘掉」变成悄悄丢题。
    """
    if not skip:
        return recs, []
    pf = Path(str(path).replace(".成品.json", ".待复核.json"))
    reg = set()
    if pf.exists():
        reg = {str(e.get("题号")) for e in json.loads(pf.read_text(encoding="utf-8"))}
    out, gone = [], []
    for r in recs:
        if str(r["题号"]) in skip:
            if str(r["题号"]) not in reg:
                sys.exit("⛔ 要摘掉第 %s 题，但 %s 里没有它的登记 —— 不许悄悄丢题"
                         % (r["题号"], pf.name))
            gone.append(r["题号"])
        else:
            out.append(r)
    return out, gone


def defer_labels(path, pv):
    r"""把「该刷给库里重复题的考点/难度」逐条追加进 journal，本场 commit 因此**不必整库重写**。

    journal 只记两件事：刷给库里哪道（`dup_key`）、用什么考点（`points`）。
    落账时 `ingest.apply_labels` 会**重跑一遍 `merge_plan`**，所以这里记的不是
    「结论」而是「线索」——重复记、隔几天再记都不会把库里已有的东西改坏。
    """
    lab = Path(path).name[: -len(".成品.json")]
    n = 0
    with LABEL_JOURNAL.open("a", encoding="utf-8") as fh:
        for it in pv["items"]:
            up = it.get("update") or {}
            tgt = it.get("dup_key") or ""
            if not tgt or not up.get("points"):
                continue
            fh.write(json.dumps({"场": lab, "key": it["key"], "dup_key": tgt,
                                 "points": up["points"], "point_source": "llm"},
                                ensure_ascii=False) + "\n")
            n += 1
    return n


def main(path, do_commit, force=False, skip=(), defer=False, allow_mostly_dup=False):
    recs = json.loads(Path(path).read_text(encoding="utf-8"))
    label = re_label(path)
    year = derive_year(label)
    recs, gone = drop_skipped(path, recs, skip)
    if gone:
        print(f"按 --skip 摘掉 {len(gone)} 题（已在待复核登记）：{gone}")
    fixed = tidy(recs)
    if fixed:
        Path(path).write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
        print("修掉相邻数学段拼成 `$$` 的写法 %d 处（会让 conform 的数学段配对错位）" % fixed)
    n_fill, filled, orphan = merge_sidecar(path, recs)
    if n_fill:
        print("并入 sidecar 模型解答 %d 道（题号 %s）" % (n_fill, filled))
    if orphan:
        print("⚠️ sidecar 里有 %d 个题号在成品中不存在，已跳过：%s" % (len(orphan), orphan))
    filled_ans, gap_sol = attach_answers(path, recs)
    if filled_ans:
        print("填模型自解答案 %d 道（题号 %s）" % (len(filled_ans), [t for t, _ in filled_ans]))
    if gap_sol:
        print("填模型自解解析 %d 道（题号 %s）" % (len(gap_sol), gap_sol))
    qs = [R2.rec_to_question(r, label) for r in recs]
    n_pt = attach_points(path, recs, qs)
    if n_pt != len(recs):
        print("⚠️ 考点标签只覆盖 %d/%d 道 —— 漏的那几道入库后考点为空，"
              "界面按考点筛会找不到它们" % (n_pt, len(recs)))
    # 模型补的解析要在库里可辨识：meta.solved_by 不参与指纹（不改 content_hash），
    # 界面 Detail.tsx 会据此挂「AI 求解」角标，供人工复核。
    filled_set = set(filled) | set(gap_sol)
    ans_by = dict(filled_ans)
    for r, q in zip(recs, qs):
        if r.get("题号") in filled_set:
            q.meta["solved_by"] = SOLVED_BY
            q.meta["solved_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        if r.get("题号") in ans_by:
            # 答案不是原卷印的，库里要能一眼看出来
            q.meta["answer_by"] = ans_by[r["题号"]]
    tex = "\n\n".join(store.render_question(q) for q in qs)
    pv = ingest.preview(tex, book="模拟题", label=label, update_force=force)
    print("count=%s dup=%s" % (pv["count"], pv["dup"]))
    # `merge` > 0 = 有题**指纹完全相同**已在库。整场录题里出现它，多半说明
    # **这一整场就是重复卷**，只是队列的卷名和库里的 source_label 写法不同，
    # 卷面标题预检没拦住（实测第 43 场：队列叫「2025年10月杭二高三月考」，
    # 库里已有同一场卷（卷名逐字相同），#17/#18 指纹 1.0）。
    # 这时先停下来核对，别把同一场录两遍。
    if pv["dup"]["merge"]:
        print("⚠️ 有 %d 题指纹已在库，先核对是不是整场撞车：" % pv["dup"]["merge"])
        for it in pv["items"]:
            if it["same_key"]:
                # `dup_key` 才是**指纹逐字相同**的那道（也就是会被刷标签的那道）；
                # `dups[0]` 只是最像的一道，0.80 也算，拿它当撞车证据会冤枉人。
                hits = it["dups"][:1]
                print("   %s ←→ %s" % (it["key"], it.get("dup_key")
                                       or ("同 key（最像的是 %s %s）" % (hits[0]["key"], hits[0]["score"])
                                           if hits else "同 key")))
    # ⚠️ `spec.after` 也要拦：commit 里还有一道「规范复核不过就不录」的闸门，
    # 只查 errors/problems 会白跑一次 commit 才被拒（实测第 29 场 #19）。
    spec_after = pv["spec"]["after"]
    inc = [e for e in pv["errors"] if incomplete(e)]
    hard = [e for e in pv["errors"] if not incomplete(e)]
    bad = hard or pv["problems"] or pv["missing_images"] or spec_after
    for k, arr in (("errors", hard), ("problems", pv["problems"]),
                   ("missing_images", pv["missing_images"])):
        if arr:
            print("%s: %s" % (k, json.dumps(arr, ensure_ascii=False)[:1200]))
    if spec_after:
        print("spec.after: %s" % json.dumps(spec_after, ensure_ascii=False)[:1200])
    if inc:
        print("ℹ️ 另有 %d 条「缺答案/缺解析」被入库完整性闸拦下 —— 无答案卷属正常，"
              "**不许为了清空它去编答案**，照常收尾即可" % len(inc))
    if bad:
        sys.exit("⛔ preview 不干净，不许入库")
    if not do_commit:
        print("干跑通过（未加 --commit，没有写库）")
        return
    # ── 两道入库前的闸 ──
    n_merge = pv["dup"]["merge"]
    if not allow_mostly_dup and n_merge * 2 >= len(recs):
        sys.exit("⛔ 判重 %d/%d 题指纹已在库 —— 疑似整场重复卷，没入库。"
                 "先核库里是不是已有这一场（看上面 ←→ 的那批 key），确认要录再加 --allow-mostly-dup"
                 % (n_merge, len(recs)))
    if defer:
        # defer 只搬得动**标签**（考点/难度）。哪道题的升级还牵扯正文，这一场就退回
        # 逐场内联升级——宁可慢，不许把该补的解析攒丢了。
        body = [it["key"] for it in pv["items"]
                if set(it.get("update") or {}) - {"points", "difficulty", "stars"}]
        if body:
            print("⚠️ 有 %d 道的升级牵扯正文（%s），本场**不 defer**，照常内联升级"
                  % (len(body), body[:3]))
            defer = False
        else:
            n = defer_labels(path, pv)
            if n:
                print("记待刷标签 %d 条（本场只追加，收尾跑 脚本/刷标签.py 一次落账）" % n)
    rep = ingest.commit(tex, book="模拟题", label=label, year=year,
                        update_force=force, update_existing=not defer)
    print("ok=%s added=%s upgraded=%s skipped=%s"
          % (rep.get("ok"), rep.get("added_count"), len(rep.get("upgraded") or []),
             len(rep.get("skipped") or [])))
    if not rep.get("ok"):
        print(json.dumps(rep, ensure_ascii=False, indent=1)[:1500])
        sys.exit("commit 失败")
    if rep.get("upgraded"):
        print("upgraded:", json.dumps(rep["upgraded"], ensure_ascii=False)[:600])
    if rep.get("skipped"):
        print("skipped:", json.dumps(rep["skipped"], ensure_ascii=False)[:600])


def tidy(recs):
    r"""两处固化下来的清洗（都是实测踩过、闸门会拒的写法）：

    1. 相邻两个数学段之间没有分隔会拼成 `$$`，让 conform 的 `$…$` 配对错位、
       把中文吞进数学模式（实测第 3 场 #7/#19 被闸门拒收）。补一个空格即可。
       本项目行间公式一律 `\\[ \\]`，所以 `$$` 不可能是合法写法。
    2. 生成脚本里用 Python **原始字符串** 写正文时，`\\n` 不会变成换行，
       落库就成了正文里的两个字符（实测第 28 场 8 道题被闸门拒收）。
       只认后面不接字母的那种，`\\neq`、`\\nu` 这类命令不受影响。
    3. 反过来，用**普通字符串**写 LaTeX 时 `\\v`、`\\f`、`\\b`、`\\a`、`\\e`
       会被 Python 吃掉成控制符，**而且命令的首字母一起没了**
       （实测：第 79、132 场的 `$\\varphi$` 落成 `$<0x0b>arphi$`）。
       所以必须还原成「反斜杠 + 那个字母」，只补反斜杠会得到 `\\arphi` 这种假命令。
       **不动 `\\t`(0x09) 和 `\\n`(0x0a)**——这两个在本项目正文里是合法的段落分隔。
       映射表以外的控制符（0x01-0x06 等）不动，留着让闸门报错，别猜。
    """
    import re
    fake_nl = re.compile(r"\\n(?![a-zA-Z])")
    CTRL2CMD = {"\x07": "\\a", "\x08": "\\b", "\x0b": "\\v",
                "\x0c": "\\f", "\x0d": "\\r", "\x1b": "\\e", "\x00": "\\0"}
    ctrl = re.compile("[" + "".join(CTRL2CMD) + "]")
    n = 0

    def fix(t):
        nonlocal n
        if "$$" in t:
            n += t.count("$$")
            t = t.replace("$$", "$ $")
        t, k = fake_nl.subn("\n", t)
        n += k
        t, k = ctrl.subn(lambda mo: CTRL2CMD[mo.group()], t)
        n += k
        return t

    for r in recs:
        for f in ("题干", "答案", "解析"):
            r[f] = fix(r.get(f) or "")
        opts = {}
        for k, v in list((r.get("选项") or {}).items()):
            opts[k] = fix(v)
        if r.get("选项"):
            r["选项"] = opts
    return n


def re_label(path):
    import re
    return re.sub(r"^\d+_", "", Path(path).stem).replace(".成品", "")


if __name__ == "__main__":
    argv = sys.argv[1:]
    skip = ()
    if "--skip" in argv:
        i = argv.index("--skip")
        skip = tuple(x for x in argv[i + 1].split(",") if x)
        del argv[i:i + 2]
    main(argv[0], "--commit" in argv, "--force" in argv, skip,
         "--defer-upgrades" in argv, "--allow-mostly-dup" in argv)
