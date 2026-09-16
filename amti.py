#!/usr/bin/env python3
"""AmTiKu 命令行入口。

日常就四条命令：

    python3 amti.py status            看库的现状（卷数/题数）
    python3 amti.py diff              **存量题有没有被改** ← 最重要
    python3 amti.py snapshot          把当前状态存为基线
    python3 amti.py verify            全库校验（题型字段是否自洽）

改内容才用到的：

    python3 amti.py show  "key"       看某一道题
    python3 amti.py audit             列出所有不合法的题
"""
from __future__ import annotations

import os
import re
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from amti import store                                    # noqa: E402
from amti.schema import QTYPE_LABEL                        # noqa: E402
from amti.render_tex import question_to_tex                # noqa: E402


def cmd_status(_a) -> int:
    vols = store.existing_volumes()
    total = sum(store.vol_count(p) for p in vols)
    print(f"卷 {len(vols)} 个   题目 {total} 道")
    for p in vols:
        n = store.vol_count(p)
        bar = "█" * min(30, int(n / store.PER_VOLUME * 30))
        print(f"  {p.name:10} {n:5} 题  {bar}")
    base = store.load_snapshot()
    print(f"\n基线 {len(base)} 道" if base else "\n（还没存基线，跑 snapshot）")
    return 0


def cmd_diff(_a) -> int:
    d = store.diff()
    if not d["基线题数"]:
        print("还没有基线。先跑：python3 amti.py snapshot")
        return 1
    print(f"基线 {d['基线题数']} 道  →  当前 {d['当前题数']} 道\n")
    print(f"  新增        {len(d['新增']):5}")
    print(f"  内容变化    {len(d['内容变化']):5}   ← 这个必须是 0")
    print(f"  求解写入    {len(d.get('求解写入', [])):5}   ← 求解器一道一道做的，正常产出")
    print(f"  录入升级    {len(d.get('录入升级', [])):5}   ← 界面点「用这份更新」改的，有意为之")
    print(f"  界面补录    {len(d.get('界面补录', [])):5}   ← 界面改了答案/解析/题型，有意为之")
    print(f"  规则迁移    {len(d.get('规则迁移', [])):5}   ← 批量规范化改的，有意为之")
    print(f"  删除        {len(d['删除']):5}")
    if d.get("回收站"):
        print(f"  进回收站    {len(d['回收站']):5}   ← 人工删的，可恢复")
    if d.get("求解写入"):
        print("\n求解器写入的题（可以忽略，但确认一下是你要它做的）：")
        for k in d["求解写入"][:10]:
            print(f"   · {k}")
    if d["内容变化"]:
        print("\n被改动的题：")
        for k in d["内容变化"][:30]:
            print(f"   ✗ {k}")
        print("\n如果这不是你改的，说明有规则动了存量数据——去查最近的改动。")
        return 1
    print("\n✓ 存量题目一个字都没动")
    return 0


def cmd_snapshot(_a) -> int:
    d = store.snapshot()
    print(f"已存基线：{d['questions']} 道 → {store.SNAPSHOT.name}")
    return 0


def cmd_backup(a) -> int:
    r"""备份：列出 / 恢复。"""
    from amti import store
    if a.restore is not None:
        if not a.yes:
            print("恢复备份会覆盖当前库。加 --yes 确认。")
            return 1
        r = store.restore_backup(a.restore or "")
        if not r.get("ok"):
            print("✗ %s" % r.get("error")); return 1
        print("已从 %s 恢复：%d 卷 / %d 道" % (r["from"], r["volumes"], r["questions"]))
        return 0
    bs = store.list_backups()
    if not bs:
        print("还没有备份。每次重写整库前会自动留一代。")
        return 0
    print("备份（新→旧）：")
    for d in bs:
        n = sum(store.vol_count(f) for f in sorted(d.glob("*.tex")))
        mb = sum(f.stat().st_size for f in d.glob("*.tex")) / 1048576
        print("  %-20s %2d 卷 / %5d 道 / %6.1f MB" % (d.name, len(list(d.glob("*.tex"))), n, mb))
    print("\n恢复最近一代：python3 amti.py backup --restore --yes")
    return 0


def cmd_export_unsolved(a) -> int:
    r"""把**没解析也没答案**的题导成一份文档，拿去别处做。"""
    from amti import exchange as X
    if a.split:
        # 一次把符合条件的**全部**切成若干批
        r = X.export_split(a.outdir, per=a.split, kind=a.kind,
                           difficulty=a.difficulty, book=a.book, stage=a.stage)
        if not r.get("ok"):
            print("✗ %s" % r.get("error")); return 1
        print("共 %d 道，切成 %d 批 → %s" % (r["total"], len(r["files"]), a.outdir))
        for f in r["files"]:
            print("   %-34s %3d 道  %s" % (f["name"], f["count"],
                  "、".join("%s %d" % (k, v) for k, v in f["by_difficulty"].items())))
        print()
        print("  清单：%s" % r["index"])
        return 0
    r = X.export(a.out, limit=a.limit, kind=a.kind, difficulty=a.difficulty,
                 book=a.book, stage=a.stage)
    if not r.get("ok"):
        print("✗ %s" % r.get("error")); return 1
    print("已导出 %d 道 → %s" % (r["count"], r["path"]))
    print("  难度分布：%s" % "  ".join("%s %d" % (k, v)
                                       for k, v in r["by_difficulty"].items()))
    print()
    print("  用法：把这份文件贴到别的模型（如 WorkBuddy）里，让它按文档开头的")
    print("        格式逐题填【答案】【解析】，拿回来再跑 `收回解答`。")
    return 0


def cmd_collect(a) -> int:
    r"""把回收的解答写进题库。**默认干跑**，加 --yes 才写。"""
    from amti import exchange as X
    r = X.collect(a.file, dry_run=not a.yes)
    if not r.get("ok"):
        print("✗ %s" % r.get("error"))
        for nt in r.get("notes", [])[:10]:
            print("   · %s" % nt)
        return 1
    if r.get("dry_run"):
        print("干跑：将写入 %d 道" % r["would_write"])
        for s_ in r.get("sample", []):
            print("   · %-42s 答案=%r 解析 %d 字"
                  % (s_["key"][:42], s_["answer"], len(s_["solution"])))
        if r["missing"]:
            print("  ⚠ 题库里没有这些题号（跳过）：%s%s"
                  % ("、".join(r["missing"][:5]),
                     " 等 %d 个" % len(r["missing"]) if len(r["missing"]) > 5 else ""))
        if r["bad"]:
            print("  ⚠ 这些不合规，不会写入：")
            for b in r["bad"][:8]:
                print("     · %-40s %s" % (b["key"][:40], b["why"][:60]))
        if r["notes"]:
            print("  · 说明：%s" % "；".join(r["notes"][:5]))
        print()
        print("  确认无误后加 --yes 落盘。")
        return 0
    print("已写入 %d 道" % r["written"])
    if r["bad"]:
        print("  跳过不合规 %d 道：" % len(r["bad"]))
        for b in r["bad"][:8]:
            print("     · %-40s %s" % (b["key"][:40], b["why"][:60]))
    if r["missing"]:
        print("  题库里没有的题号 %d 个" % len(r["missing"]))
    return 0


def cmd_render_tikz(a) -> int:
    r"""把全库的 TikZ 预渲染成矢量图（卷子里就只剩 \includegraphics 了）。"""
    from amti import tikzfig as T
    print("渲染全库 TikZ…（已渲染过的会跳过）")
    r = T.render_all(force=a.force)
    print()
    print("新渲染 %d 张，跳过 %d 张（已有缓存）" % (r["rendered"], r["skipped"]))
    if r["fails"]:
        print("✗ %d 张渲染不出来：" % len(r["fails"]))
        for f in r["fails"][:20]:
            print("   %-44s %s" % (f["key"][:44], f["why"][:80]))
        return 1
    print("✓ 全部渲染完成")
    return 0


def cmd_compilecheck(a) -> int:
    r"""全库编译体检：把"抽到才炸"的编译错误提前查出来。"""
    from amti import compilecheck as CC
    if a.keys:
        keys = [k.strip() for k in a.keys.split(",") if k.strip()]
        print("只查指定的 %d 道" % len(keys))
    else:
        keys = None
        from amti import store as _st
        n = sum(1 for _f, q in _st.iter_questions() if CC.risky(q))
        print("全库体检：%d 道带 TikZ／配图的题（其余是纯文本，不可能编译不过）" % n)
        print("分批编译 + 二分定位，请稍候…")
    r = CC.check(keys, verbose=not a.quiet)
    print()
    print("检查 %d 道，用了 %d 次编译" % (r["checked"], r["runs"]))
    if not r["fails"]:
        print("✓ 全部能编译")
        return 0
    print("✗ %d 道编译不过：" % len(r["fails"]))
    for f in r["fails"][:40]:
        print("   %-46s %s" % (f["key"][:46], f["why"][:90]))
    if len(r["fails"]) > 40:
        print("   … 其余 %d 道" % (len(r["fails"]) - 40))
    return 1


def cmd_trash(a) -> int:
    r"""回收站：看 / 恢复 / 清空。"""
    from amti import trash as T
    if a.purge:
        if not a.yes:
            print("清空回收站**不可恢复**。加 --yes 确认。")
            return 1
        r = T.purge(a.purge_keys or None, password=a.password, confirm_all=True)
        if not r.get("ok"):
            print("✗ %s" % r.get("error")); return 1
        print("已永久删除 %d 道%s" % (r["purged"], "（整个回收站）" if r.get("all") else ""))
        return 0
    if a.restore:
        r = T.restore(a.restore)
        if not r["ok"]:
            print("✗ %s" % r["error"])
            for k in r.get("not_found", []) + r.get("clash", []):
                print("   · %s" % k)
            return 1
        print("已恢复 %d 道：" % len(r["restored"]))
        for x in r["restored"]:
            print("   · %s" % x["key"])
        return 0

    items = T.all_items()
    if not items:
        print("回收站是空的")
        return 0
    print("回收站：%d 道（用 `--restore 题号` 恢复，`--purge --yes` 永久删除）\n" % len(items))
    for x in items[:40]:
        q = x.get("question") or {}
        print("  %-44s %-6s %s" % (x["key"][:44], x.get("type", ""),
                                   (q.get("stem") or "")[:34].replace("\n", " ")))
        print("      删于 %s%s" % (x.get("deleted_at", "?"),
                                   "　原因：" + x["reason"] if x.get("reason") else ""))
    if len(items) > 40:
        print("  … 其余 %d 道" % (len(items) - 40))
    return 0


def cmd_dedup(a) -> int:
    r"""去掉库里重复的 key（同一个 key 只留最后一份）。

    重复的来源是**写库姿势不对**：`rewrite_volume(1, load_all())` 会把
    所有卷的题再写一份进第 1 卷，而其它卷还在。现在：
      * `rewrite_volume` 加了单卷上限护栏
      * 改库统一走 `rewrite_all`（按 PER_VOLUME 重新分卷）
      * `verify` 会报重复
    这个命令用来收拾历史遗留。
    """
    dup = store.duplicate_keys()
    if not dup:
        print("没有重复 key ✓")
        return 0
    print("重复 key %d 个，多出 %d 条" % (len(dup), sum(n - 1 for n in dup.values())))
    if not a.apply:
        print("\n[干跑] 什么都没写。确认后加 --apply")
        return 0
    before = sum(store.vol_count(p) for p in store.existing_volumes())
    r = store.rewrite_all(store.load_unique())
    after = sum(store.vol_count(p) for p in store.existing_volumes())
    print("\n%d 条 → %d 条（去掉 %d），重写为 %d 卷"
          % (before, after, before - after, r["volumes"]))
    for rep in r["reports"]:
        print("   %s  %d 道" % (rep["volume"], rep["count"]))
    return 0


def cmd_verify(_a) -> int:
    # ① 重复 key —— 最危险的一种损坏，因为它不报错
    dup = store.duplicate_keys()
    if dup:
        print("✗ 库里有 %d 个重复 key，共多出 %d 条："
              % (len(dup), sum(n - 1 for n in dup.values())))
        for k, n in list(dup.items())[:10]:
            print("   · %-46s ×%d" % (k, n))
        print("\n  修：python3 amti.py dedup --apply")
        return 1
    print("重复 key：无 ✓")

    bad = 0
    total = 0
    for f, q in store.iter_questions():
        total += 1
        probs = q.problems()
        if probs:
            bad += 1
            print(f"  ✗ {q.key or '(无key)'}  [{QTYPE_LABEL.get(q.type, q.type)}]")
            for p in probs:
                print(f"      {p}")
    print(f"\n{total} 道题，{bad} 道不合法")
    return 1 if bad else 0


def cmd_audit(a) -> int:
    r"""影响面审计 + **MIGRATE 强制流程**（顶层设计 §4.3）。

        audit                  列出不合法的题
        audit --rules          列出全部规则（含作用域与依据）
        audit --rule 名字       干跑：这条规则会改哪些题（**不动**）
        audit --rule 名字 --yes 真正执行，并写 变更记录/
    """
    from amti import audit as aud

    if getattr(a, "rules", False):
        print("规则清单：")
        for r in aud.list_rules():
            print("  [%-7s] %-20s %s" % (r["scope"], r["name"], r["why"][:58]))
        return 0

    if getattr(a, "rule", ""):
        pv = aud.preview(a.rule)
        if not pv.get("ok", True):
            print("✗ %s" % pv["error"])
            return 1
        print("规则「%s」将影响 %d 道（全库 %d 道）"
              % (a.rule, pv["affected"], pv["total"]))
        for k, fired in pv["sample"]:
            print("   · %s" % k)
        if pv["affected"] > len(pv["sample"]):
            print("   … 其余 %d 道" % (pv["affected"] - len(pv["sample"])))
        if not getattr(a, "yes", False):
            print("\n[干跑] 什么都没写。确认后加 --yes")
            return 0
        r = aud.apply(a.rule, yes=True)
        if not r.get("ok"):
            print("✗ %s" % r.get("error"))
            return 1
        print("\n已改 %d 道，其中指纹变化 %d 道"
              % (r["affected"], r.get("fingerprints_changed", 0)))
        print("变更报告：%s" % r.get("report"))
        return 0

    keys = [q.key for _f, q in store.iter_questions() if q.problems()]
    print(f"不合法 {len(keys)} 道")
    for k in keys:
        print("  ", k)
    return 1 if keys else 0


def _ensure_server(root: Path):
    r"""层③ 要连服务（`web/check.mjs` 走 HTTP 取全库）。

    ⚠️ 原来的坑：验收**不会自己起服务**，没起就必失败，
    报的还是「✗ 未通过：端到端渲染」这种看不出原因的提示。
    服务本身又会在页面关掉 25 秒后自动退出 —— 所以"别的都绿、就差层③"
    是很容易踩到的。

    现在：先探一下；没跑就**自己起一个**（跑完关掉），已经跑着就直接用。
    """
    import subprocess
    import sys
    import time
    import urllib.request

    url = "http://127.0.0.1:8899/api/facets"

    def up() -> bool:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return True
        except Exception:
            return False

    if up():
        return None                          # 已经跑着，不动它
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "amti.web.server:app",
         "--host", "127.0.0.1", "--port", "8899"],
        cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):                      # 最多等 20 秒（要读全库）
        if up():
            print("  （验收自己起了一个临时服务，跑完会关掉）")
            return proc
        if proc.poll() is not None:
            print("  ⚠️ 临时服务没起来，层③ 会失败")
            return None
        time.sleep(0.5)
    print("  ⚠️ 临时服务 20 秒没就绪")
    return proc


def cmd_accept(_a) -> int:
    r"""**一条命令跑完全部验收。**「过了」= 这个命令退出码 0。

    四层，缺一不可：

      ① 单元自检   每个模块自己的回归用例（含检查器的控制样本）
      ② 规范审查   11 项，全库
      ③ 端到端渲染 用**前端同一条渲染路径**跑全库，查 KaTeX / LaTeX 泄漏 / 图片
      ④ 快照       存量题内容有没有被无故改动

    为什么要有这个命令：以前我说"全部规范"，依据是 `conform` 报了个 ✓——
    而 `conform` 自己可能漏报、可能误报。现在"过了"指的是**四层全绿**，
    而且第 ① 层里 `conform --selftest` 会**先证明检查器管用**再报结论。
    """
    import subprocess
    import sys as _s
    root = Path(__file__).resolve().parent
    fails: list[str] = []

    temp_server = None

    def run(title: str, argv: list[str], grep: str | None = None) -> None:
        print("\n【%s】" % title)
        r = subprocess.run(argv, cwd=root, capture_output=True, text=True,
                           env={**os.environ, "PYTHONWARNINGS": "error::SyntaxWarning"})
        out = (r.stdout or "") + (r.stderr or "")
        if grep:
            for line in out.splitlines():
                if re.search(grep, line):
                    print("  " + line.strip())
        else:
            print("\n".join("  " + x for x in out.splitlines()[-8:]))
        if r.returncode != 0:
            fails.append(title)

    print("═" * 56)
    print("AmTiKu 验收")
    print("═" * 56)
    # **逐个 `-m` 跑**，不能只 import——自检写在 `__main__` 里，
    # import 一下什么都不执行，那一层就成了摆设（实测踩过）。
    for m in ("schema", "latex_blocks", "render_tex", "images", "dedup",
              "ingest", "generate", "normalize"):
        run("单元自检 · %s" % m, [_s.executable, "-m", "amti." + m], r"通过|失败")
    run("题目解析回归", [_s.executable, "-m", "amti.latex_ir", "--selftest"], r"通过|失败")
    run("求解器自检", [_s.executable, "-m", "amti.solve", "--selftest"], r"通过|失败")
    run("录题自检", [_s.executable, "-m", "amti.record", "--selftest"], r"通过|失败")
    run("逐题订正自检", [_s.executable, "-m", "amti.fixups", "--selftest"], r"通过|失败")
    run("回收站自检", [_s.executable, "-m", "amti.trash"], r"通过|失败")
    # **删题是危险操作**，单独一层：证明"只动该动的那一道、其余一个字节不变、
    # 能原样恢复、坏路径不执行、改库前留备份"。自检完把库还原并核对指纹。
    run("删题安全自检", [_s.executable, str(root / "测试" / "删题安全自检.py")],
        r"安全测试|✗")
    run("检查器自证", [_s.executable, "-m", "amti.conform", "--selftest"], r"通过|失败")
    run("规范审查", [_s.executable, "amti.py", "conform"], r"^共|全部规范")
    temp_server = _ensure_server(root)
    try:
        run("端到端渲染", ["node", "web/check.mjs"],
            r"题目 |✓|✗|全部通过|未通过")
    finally:
        if temp_server is not None:
            temp_server.terminate()
            try:
                temp_server.wait(timeout=10)
            except Exception:
                temp_server.kill()
    run("快照", [_s.executable, "amti.py", "diff"], r"内容变化|新增|删除|存量")

    print("\n" + "═" * 56)
    if fails:
        print("✗ 未通过：%s" % "、".join(fails))
        return 1
    print("✓ 四层全绿")
    return 0


def cmd_conform(_a) -> int:
    r"""**规范化验证**：全库写法是不是一个样子（只报不改）。"""
    from amti import conform
    return conform.main()


def cmd_rules(_a) -> int:
    r"""列出规则及其作用域（顶层设计 §4.3 的 ENTRY / MIGRATE）。"""
    from amti import audit as aud
    for r in aud.list_rules():
        print("  [%-7s] %-20s %s" % (r["scope"], r["name"], r["why"]))
    return 0


def cmd_show(a) -> int:
    q = store.find(a.key)
    if not q:
        print(f"没有 key 为 {a.key!r} 的题")
        return 1
    print(f"key    {q.key}")
    print(f"题型   {QTYPE_LABEL.get(q.type, q.type)}")
    print(f"指纹   {q.content_hash()}")
    print(f"标签   {q.points or '（无）'}")
    print(f"校验   {q.problems() or '合法'}")
    print("\n—— LaTeX ——")
    print(question_to_tex(q))
    return 0


def cmd_images(a) -> int:
    r"""图片入库：复制进项目 + 改成内容寻址名。**未来录入新题也走这条。**

    默认**干跑**——先看清楚会复制什么、有没有缺的，确认无误再加 `--apply`。
    缺图会导致 PDF 编译失败，所以有缺失时返回码是 1。
    """
    from amti import images as im

    vols = store.existing_volumes()
    if not vols:
        print("还没有任何题目")
        return 1
    src = [a.src] if getattr(a, "src", None) else None

    tot = {"copied": 0, "reused": 0, "already": 0, "missing": []}
    for path in vols:
        qs = [q for f, q in store.iter_questions() if f == path.name]
        if not qs:
            continue
        rep = im.ingest_all(qs, src_dirs=src, dry_run=not a.apply)
        print("  %s  %5d 题   复制 %3d  复用 %3d  已迁移 %3d  缺失 %3d"
              % (path.name, len(qs), rep["copied"], rep["reused"],
                 rep["already"], len(rep["missing"])))
        for k, n in rep["missing"][:10]:
            print("      ✗ %s → %s" % (k, n))
        if len(rep["missing"]) > 10:
            print("      … 其余 %d 处" % (len(rep["missing"]) - 10))
        tot["copied"] += rep["copied"]
        tot["reused"] += rep["reused"]
        tot["already"] += rep["already"]
        tot["missing"] += rep["missing"]

        if a.apply and (rep["copied"] or rep["reused"] or rep["missing"]):
            r = store.rewrite_volume(int(path.stem), qs)
            print("      重写 %s：内容变化 %d 道%s"
                  % (r["volume"], len(r["changed"]),
                     "（图片引用改写，属预期）" if r["changed"] else ""))

    print("\n复制 %d  复用 %d  已迁移 %d  缺失 %d"
          % (tot["copied"], tot["reused"], tot["already"], len(tot["missing"])))
    st = im.stats()
    print("图片目录：%s" % st["dir"])
    print("          %d 个文件，%.0f KB" % (st["files"], st["bytes"] / 1024))
    if not a.apply:
        print("\n[干跑] 什么都没写。确认后加 --apply")
    return 1 if tot["missing"] else 0


def cmd_ingest(a) -> int:
    r"""录入题目。默认**干跑**，`--yes` 才真的写。

    干跑报告五块：解析结果 · 图片检查 · 查重 · 字段校验 · 影响面。
    只要影响面写着 0，存量题就是安全的——录入只走 `store.append`。
    """
    from amti import ingest as ig
    from pathlib import Path as _P

    if a.file:
        src = _P(a.file).read_text(encoding="utf-8")
    else:
        src = a.text
    if not src.strip():
        print("没有源材料。用 --file 给文件，或 --text 给内容")
        return 1

    src_dirs = [a.src] if a.src else None
    if not a.yes:
        pv = ig.preview(src, src_dirs=src_dirs, book=a.book, label=a.label,
                        region=a.region, year=a.year)
        print("① 解析结果：%d 道" % pv["count"])
        for i, it in enumerate(pv["items"], 1):
            print("  %2d. [%s] %s" % (i, it["type_label"], it["stem"][:56].replace("\n", " ")))
        if pv["errors"]:
            print("\n  ⚠ 解析问题：")
            for e in pv["errors"]:
                print("     %s" % e)

        print("\n② 图片检查：%d 张" % len(pv["images"]))
        for k, v in pv["images"].items():
            mark = {"found": "找到", "reused": "已在库", "missing": "⚠ 缺失"}[v["status"]]
            print("    %-34s %s" % (k, mark))

        print("\n③ 查重：新建 %d · 并入 %d · 疑似 %d"
              % (pv["dup"]["new"], pv["dup"]["merge"], pv["dup"]["suspect"]))
        for it in pv["items"]:
            for d in it.get("dups", []):
                print("    %s  %s  相似 %.3f  [%s]" % (it["key"], d["key"], d["score"], d["verdict"]))

        sp = pv.get("spec", {})
        print("\n④ 规范：验证 → 修改 → 复核")
        print("   改之前：%s" % (
            "✓ 全部规范" if not sp.get("before")
            else "✗ %d 处不规范" % len(sp["before"])))
        for b in (sp.get("before") or [])[:8]:
            print("      · %s [%s] %s" % (b["key"].split("/", 2)[-1], b["check"], b["why"][:44]))
        if sp.get("fixed"):
            print("   规范器改：")
            for f in sp["fixed"]:
                print("      · %-18s %d 道" % (f["name"], f["hits"]))
        else:
            print("   规范器改：无需改动")
        print("   复核后：%s" % ("✓ 全部规范" if sp.get("ok") else "✗ 仍有 %d 处" % len(sp["after"])))

        print("\n⑤ 类型分布：" + " · ".join("%s %d" % (t["label"], t["n"]) for t in pv["types"]))
        if pv["problems"]:
            print("   字段问题：")
            for p in pv["problems"]:
                print("     %s %s" % (p["key"], p["problems"]))
        else:
            print("   字段约束：全部通过")

        print("\n⑥ 影响面")
        print("   ⚠ 存量题目影响：%d 道   （%s）"
              % (pv["impact"]["existing_questions"], pv["impact"]["note"]))
        if not pv.get("spec", {}).get("ok", True):
            print("\n✗ 规范复核未通过，**不允许录入**。先按上面列出的问题改题目。")
            return 1
        print("\n[干跑] 什么都没写。确认后加 --yes")
        return 0

    r = ig.commit(src, src_dirs=src_dirs, book=a.book, label=a.label,
                  region=a.region, year=a.year)
    if not r.get("ok"):
        print("✗ %s" % r.get("error"))
        return 1
    print("已导入 %d 道：" % r["added_count"])
    for k in r["added"]:
        print("   + %s" % k)
    if r["skipped"]:
        print("\n跳过 %d 道：" % len(r["skipped"]))
        for s in r["skipped"]:
            print("   - %s  %s%s" % (s["key"], s["reason"],
                                     ("（与 %s 相似 %.3f）" % (s["of"], s["score"]))
                                     if s.get("of") else ""))
    im = r["images"]
    print("\n图片：复制 %d · 复用 %d · 缺失 %d"
          % (im["copied"], im["reused"], len(im["missing"])))
    print("\n跑 `python3 amti.py diff` 看变更报告（内容变化必须是 0）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="AmTiKu 题库工具")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("status", help="库的现状").set_defaults(fn=cmd_status)
    sub.add_parser("diff", help="存量题有没有被改").set_defaults(fn=cmd_diff)
    sub.add_parser("snapshot", help="把当前状态存为基线").set_defaults(fn=cmd_snapshot)
    sub.add_parser("verify", help="全库校验").set_defaults(fn=cmd_verify)
    # ⚠️ 别用 `ap` 当变量名——那是主解析器，覆盖掉之后 parse_args 会走错
    aud_p = sub.add_parser("audit", help="影响面审计 + MIGRATE 强制流程")
    aud_p.add_argument("--rules", action="store_true", help="列出全部规则")
    aud_p.add_argument("--rule", default="", help="对某条规则干跑（加 --yes 才执行）")
    aud_p.add_argument("--yes", action="store_true", help="确认执行迁移")
    aud_p.set_defaults(fn=cmd_audit)
    sub.add_parser("accept", help="一条命令跑完全部验收").set_defaults(fn=cmd_accept)
    bk = sub.add_parser("backup", help="备份：列出 / 从备份恢复")
    bk.add_argument("--restore", nargs="?", const="", default=None, metavar="时间戳",
                    help="恢复某一代备份；不带值=最近一代")
    bk.add_argument("--yes", action="store_true", help="恢复要显式确认")
    bk.set_defaults(fn=cmd_backup)

    ex = sub.add_parser("export-unsolved", aliases=["导出待解"],
                        help="把没解析也没答案的题导成一份文档")
    ex.add_argument("--out", default="待解题目.md", help="写到哪个文件")
    ex.add_argument("--limit", type=int, default=100, help="导出几道（默认 100）")
    ex.add_argument("--split", type=int, default=0, metavar="每批几道",
                    help="给这个数就**全部导出并切批**，写到 --outdir")
    ex.add_argument("--outdir", default="待解", help="切批时的输出目录")
    ex.add_argument("--kind", default="", help="只要高考/模拟")
    ex.add_argument("--difficulty", default="", help="只要这一档难度")
    ex.add_argument("--book", default="", help="只要这本书")
    ex.add_argument("--stage", default="both", choices=["both", "solution"],
                    help="both=答案解析都缺（默认）；solution=只补解析（有答案没解析）")
    ex.set_defaults(fn=cmd_export_unsolved)

    co = sub.add_parser("collect", aliases=["收回解答"],
                        help="把回收的解答写进题库（默认干跑）")
    co.add_argument("file", help="回收的文档")
    co.add_argument("--yes", action="store_true", help="真的落盘")
    co.set_defaults(fn=cmd_collect)

    rt = sub.add_parser("render-tikz", aliases=["渲染TikZ"],
                        help="把全库 TikZ 预渲染成矢量图（卷子编译就不再依赖 TikZ 环境）")
    rt.add_argument("--force", action="store_true", help="已有缓存也重画")
    rt.set_defaults(fn=cmd_render_tikz)

    cc = sub.add_parser("compilecheck", aliases=["编译体检"],
                        help="全库编译体检：提前查出抽到才炸的编译错误")
    cc.add_argument("--keys", default="", help="只查这几道（逗号分隔）")
    cc.add_argument("--quiet", action="store_true", help="不逐批打印进度")
    cc.set_defaults(fn=cmd_compilecheck)

    tr = sub.add_parser("trash", help="回收站：查看 / 恢复 / 清空")
    tr.add_argument("--restore", nargs="*", default=[], metavar="题号",
                    help="恢复这些题号")
    tr.add_argument("--purge", action="store_true", help="永久删除（不可恢复）")
    tr.add_argument("--purge-keys", nargs="*", default=[], metavar="题号",
                    help="只永久删除这些；不给就清空整个回收站")
    tr.add_argument("--yes", action="store_true", help="清空必须显式确认")
    tr.add_argument("--password", default="", help="删题/清空的口令")
    tr.set_defaults(fn=cmd_trash)

    sp = sub.add_parser("dedup", help="去掉库里重复的 key")
    sp.add_argument("--apply", action="store_true", help="真的写盘")
    sp.set_defaults(fn=cmd_dedup)
    sub.add_parser("conform", help="规范化验证（全库写法一致性）").set_defaults(fn=cmd_conform)
    sub.add_parser("rules", help="列出规则与作用域").set_defaults(fn=cmd_rules)
    sp = sub.add_parser("show", help="看某一道题")
    sp.add_argument("key")
    sp.set_defaults(fn=cmd_show)

    ip = sub.add_parser("images", help="图片入库（默认干跑，--apply 落盘）")
    ip.add_argument("--apply", action="store_true", help="真的复制并改写引用")
    ip.add_argument("--src", default="", help="图片来源目录（默认旧项目图片目录）")
    ip.set_defaults(fn=cmd_images)

    gp = sub.add_parser("ingest", help="录入题目（默认干跑，--yes 才写）")
    gp.add_argument("--file", default="", help="源材料 .tex 路径")
    gp.add_argument("--text", default="", help="直接给内容（与 --file 二选一）")
    gp.add_argument("--src", default="", help="图片来源目录")
    gp.add_argument("--book", default="手工录入", help="书名/来源大类")
    gp.add_argument("--label", default="", help="出处，如「第14套武汉三调」")
    gp.add_argument("--region", default="", help="地区")
    gp.add_argument("--year", type=int, default=None, help="年份")
    gp.add_argument("--yes", action="store_true", help="确认导入")
    gp.set_defaults(fn=cmd_ingest)

    args = ap.parse_args()
    if not getattr(args, "fn", None):
        ap.print_help()
        return 0
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
