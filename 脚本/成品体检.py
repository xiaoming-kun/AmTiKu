#!/usr/bin/env python3
r"""批量体检 输出_v2/*.成品.json：把只有入库时才会炸的问题提前找出来。

不写题库、不碰 队列.json / 进度.jsonl（那是解析任务在锁内维护的），
只读成品 JSON + 只读题库，产出一份 md 报告。

查六类：
  A 结构      键齐不齐、题型和题号对不对、选择题有没有选项、客观题有没有答案
  B LaTeX     控制符残留、`$$`、`$` 个数奇偶、数学段里的裸中文
  C 归一化    过一遍 normalize，看会不会抛异常或改出空字段
  D 自我重复  同一份成品里题干撞车（跨题号复制粘贴）
  E 跨场重复  不同场之间整卷或单题撞车（解析任务可能把同一场做了两遍）
  F 覆盖率    19 题减去待复核登记的带图带表题，数量对不对得上
"""
import json, re, sys, hashlib
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amti import normalize as N, conform, record2

ROOT = Path(__file__).resolve().parent.parent
V2 = ROOT / "数据/录题/输出_v2"
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
EXPECT = lambda no: ("single_choice" if no <= 8 else "multi_choice" if no <= 11
                     else "fill_in_blank" if no <= 14 else "detailed_answer")


def cjk_in_math(text):
    return conform.chk_cjk_in_math(text)


def main():
    out = []
    Z = []
    files = sorted(V2.glob("*.成品.json"))
    per = {}
    for f in files:
        recs = json.loads(f.read_text(encoding="utf-8"))
        # 先过一遍入库脚本的 tidy：`$$`、字面 `\\n`、被 Python 吃掉的 `\\v`/`\\f` 它会自动修，
        # 那些不算问题；体检只看**tidy 之后仍会进库**的内容。
        import importlib.util
        spec = importlib.util.spec_from_file_location("lk", ROOT / "脚本/录题入库.py")
        lk = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lk)
        auto = lk.tidy(recs)
        per[f] = recs
        A, B, C, D = [], [], [], []
        if auto:
            Z.append("%s tidy 自动修 %d 处（`$$`/字面 \\n/控制符）" % (f.name.split("_")[0], auto))
        # 整场都没答案 = 无答案卷，按口径是「照录、答案留空」，不该逐题报警
        obj = [r for r in recs if r.get("题型") in ("single_choice", "multi_choice", "fill_in_blank")]
        blank_paper = bool(obj) and not any((r.get("答案") or "").strip() for r in obj)
        for r in recs:
            no = r.get("题号")
            t = r.get("题型")
            miss = {"题号", "题型", "页码", "题干", "选项", "答案", "解析", "粗筛图", "粗筛表"} - set(r)
            if miss:
                A.append("#%s 缺键 %s" % (no, sorted(miss)))
            if t != EXPECT(no):
                A.append("#%s 题型 %s，按题号应为 %s" % (no, t, EXPECT(no)))
            if t in ("single_choice", "multi_choice"):
                if len(r.get("选项") or {}) < 4:
                    A.append("#%s 选项只有 %d 条" % (no, len(r.get("选项") or {})))
                if not blank_paper and not (r.get("答案") or "").strip():
                    A.append("#%s 客观题没答案" % no)
            if t == "single_choice" and re.fullmatch(r"[A-D]{2,}", (r.get("答案") or "").strip()):
                A.append("#%s 单选却多答案 %s" % (no, r["答案"]))
            fields = [r.get("题干", ""), r.get("答案", ""), r.get("解析", "")] + \
                     [o.get("text", "") for o in (r.get("选项") or []) if isinstance(o, dict)]
            for name, v in zip(["题干", "答案", "解析"] + ["选项"] * 9, fields):
                if CTRL.search(v):
                    B.append("#%s %s 有控制符 %r" % (no, name, CTRL.search(v).group()))
                if "$$" in v:
                    B.append("#%s %s 有 $$" % (no, name))
                if v.count("$") % 2:
                    B.append("#%s %s 美元号奇数个" % (no, name))
                if re.search(r"\\\[|\\\]", v):
                    # 本项目行间公式惯例就是 \[ \]，只当提示不算问题
                    Z.append("#%s %s 用了显示式 \\[ \\]" % (no, name))
                hits = cjk_in_math(v)
                if hits:
                    B.append("#%s %s 数学段裸中文 %s" % (no, name, str(hits)[:70]))
            try:
                q = record2.rec_to_question(dict(r), f.stem)
                N.normalize(q, N.ENTRY)
                if not (q.stem or "").strip():
                    C.append("#%s normalize 后题干空了" % no)
            except Exception as e:
                C.append("#%s normalize 抛 %s: %s" % (no, type(e).__name__, str(e)[:80]))
        seen = defaultdict(list)
        for r in recs:
            key = re.sub(r"\W", "", r.get("题干", ""))[:40]
            if len(key) > 12:
                seen[key].append(r["题号"])
        for k, v in seen.items():
            if len(v) > 1:
                D.append("题号 %s 题干前 40 字相同" % v)
        if blank_paper:
            A.append("整场客观题都没答案 = 无答案卷，按口径照录留空（不是漏录）")
        out.append((f, A, B, C, D))

    # E 跨场重复
    fp = defaultdict(list)
    for f, recs in per.items():
        for r in recs:
            h = hashlib.md5(re.sub(r"\W", "", r.get("题干", ""))[:60].encode()).hexdigest()[:10]
            fp[h].append((f.name.split("_")[0], r["题号"]))
    cross = {k: v for k, v in fp.items() if len({x[0] for x in v}) > 1}
    pairs = Counter()
    for v in cross.values():
        pairs[tuple(sorted({x[0] for x in v}))] += 1

    # F 覆盖率
    cov = []
    for f, *_ in out:
        pf = f.with_name(f.name.replace(".成品.json", ".待复核.json"))
        recs = per[f]
        pend = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else []
        norec = [e["题号"] for e in pend if e.get("类型") in ("figure", "table")]
        nos = {int(r["题号"]) for r in recs} | {int(x) for x in norec}
        holes = [i for i in range(1, (max(nos) if nos else 19) + 1) if i not in nos]
        dupno = [n for n, c in Counter(int(r["题号"]) for r in recs).items() if c > 1]
        if holes or dupno:
            cov.append("%s 缺题号 %s%s" % (f.name.split("_")[0], holes,
                                           "；题号重复 %s" % dupno if dupno else ""))

    L = ["# 成品体检报告\n"]
    L.append("扫了 %d 份成品 / %d 题。\n" % (len(files), sum(len(v) for v in per.values())))
    tot = Counter()
    for f, A, B, C, D in out:
        bad = A or B or C or D
        if bad:
            tot["有问题的份数"] += 1
            L.append("## %s" % f.name)
            for tag, arr in (("结构", A), ("LaTeX", B), ("归一化", C), ("同卷重复", D)):
                for x in arr:
                    L.append("- [%s] %s" % (tag, x))
                    tot[tag] += 1
            L.append("")
    if tot["有问题的份数"] == 0:
        L.append("**结构 / LaTeX / 归一化 / 同卷重复 四类全部干净。**\n")
    L.append("## 汇总\n")
    for k, v in tot.most_common():
        L.append("- %s：%s" % (k, v))
    L.append("")
    L.append("## 提示（不算问题，tidy 会自动修 / 项目惯例）\n")
    L.extend(["- %s" % z for z in Z] or ["- 无"])
    L.append("")
    L.append("## 跨场重复（同一道题出现在两份成品里）\n")
    if pairs:
        L.append("共 %d 道题跨场重复，涉及场次对：" % len(cross))
        for p, c in pairs.most_common(20):
            L.append("- #%s ×%d" % ("、#".join(p), c))
    else:
        L.append("- 无")
    L.append("")
    L.append("## 覆盖率（题号有洞 = 既没进成品也没登记待复核）\n")
    L.extend(["- %s" % c for c in cov] or ["- 无"])
    L.append("")
    txt = "\n".join(L)
    (ROOT / "数据/录题/成品体检.md").write_text(txt, encoding="utf-8")
    print(txt[:4000])
    print("\n……完整报告见 数据/录题/成品体检.md")


if __name__ == "__main__":
    main()
