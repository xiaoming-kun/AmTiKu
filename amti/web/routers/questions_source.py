"""题目**源码**路由：补/改解析、改源码、插 TikZ、批量改出处。

写回前统一过 `ingest.preview` 的规范复核与 `latex_ir.preserve_figures`
（漏配图不静默丢），然后交给 `patch_ops` 里那套改名/台账/引用迁移的规则——
**规则只有一份**，在 `questions_edit.py` 的 helper 里，这里 import 过来用。
"""
from __future__ import annotations

import re
import time
import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from amti import fts as fulltext
from amti import store
from amti.logutil import get_logger
from amti.images import IMG_DIR
from amti.render_tex import question_to_tex
from amti.schema import QTYPE_LABEL
from amti.web.core import (
    _rm_apply,
)
from amti.web.present import brief as _brief
from amti.web.retry import retry_on_concurrent

from amti.web.routers.questions import _load_question  # noqa: E402
from amti.web.routers.questions_edit import (  # noqa: E402
    _audit_batch_source, _audit_key_rename, _clean_answer_input,
    _content_outside_answer, _migrate_key_refs, _migrate_meta_refs,
    _migrate_usage, _source_key,
)

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["questions"])


class SourceBatchBody(BaseModel):
    r"""按「来源 + 出处」批量改题。

    `old_book/old_label` 是**匹配条件**（当前题上存的那一份），
    `new_book/new_label/new_year` 是统一改成的新值；题号不动。
    """
    model_config = {"extra": "forbid"}
    old_book: str
    old_label: str
    new_book: str
    new_label: str
    new_year: int | str = ""          # 空 = 清空年份
    dry_run: bool = True              # 默认只预览命中，不写库
    #: 当前题 key。回传改后的完整记录，前端不用再 GET 一次。
    focus_key: str = ""


def _year_int(v) -> int | None:
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        raise HTTPException(400, "年份要是整数，收到 %r" % (v,))


@router.post("/questions/source/batch")
@retry_on_concurrent
def batch_source(body: SourceBatchBody) -> dict:
    old_book = body.old_book.strip()
    old_label = body.old_label.strip()
    new_book = body.new_book.strip()
    new_label = body.new_label.strip()
    year_v = _year_int(body.new_year)
    if not old_book or not old_label:
        raise HTTPException(400, "这道题还没标「来源 / 出处」，先保存一次再用批量改")
    if not new_book or not new_label:
        raise HTTPException(400, "新的来源和出处都不能空")
    # key 是 `书/卷名#号`，这几样里出现分隔符会把 key 结构弄坏（同单题改动）
    for bad in ("/", "#"):
        if bad in new_book or bad in new_label:
            raise HTTPException(400, "新的来源/出处里不能有 `%s`（key 的分隔符）" % bad)

    # ① 只读元数据搜索命中。32k 道约 0.7 秒，比 load_all 解析正文快得多。
    rows = store.scan_meta()
    matched = [r for r in rows if r["book"].strip() == old_book
               and r["label"].strip() == old_label]
    if not matched:
        raise HTTPException(404, "全库没有「%s / %s」的题" % (old_book, old_label))
    all_keys = {r["key"] for r in rows}
    matched_keys = {r["key"] for r in matched}

    plan = {r["key"]: _source_key(r["key"], r["book"], r["label"],
                                  new_book, new_label) for r in matched}
    # 撞车分两种：目标 key 已经有别的题；本次两道题改完同名（极少见，
    # 但历史 key 不是由出处拼的，确实可能和新 key 撞上）。
    conflicts: list[dict] = []
    seen_final: dict[str, str] = {}
    for r in matched:
        nk = plan[r["key"]]
        if nk in seen_final:
            conflicts.append({"key": r["key"], "new_key": nk,
                              "why": "和本次另一道题改完同名"})
        else:
            seen_final[nk] = r["key"]
        if nk != r["key"] and nk in all_keys and nk not in matched_keys:
            conflicts.append({"key": r["key"], "new_key": nk,
                              "why": "新 key 已经有别的题"})
    renamed_n = sum(1 for k, nk in plan.items() if k != nk)
    target_existing = sum(
        1 for r in rows if r["key"] not in matched_keys
        and r["book"].strip() == new_book and r["label"].strip() == new_label)

    def _year_of(r: dict):
        s = str(r["year"]).strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return s

    noop = (new_book == old_book and new_label == old_label
            and all(_year_of(r) == year_v for r in matched))

    def _no_int(r: dict) -> int:
        try:
            return int(str(r["no"]))
        except (TypeError, ValueError):
            return 10 ** 9

    ordered = sorted(matched, key=lambda r: (_no_int(r), r["key"]))
    items = [{
        "key": r["key"],
        "no": r["no"],
        "year": r["year"],
        "type": r["type"],
        "new_key": plan[r["key"]],
        "renamed": plan[r["key"]] != r["key"],
    } for r in ordered]

    base = {
        "ok": True,
        "matched": len(matched),
        "renamed": renamed_n,
        "kept": len(matched) - renamed_n,
        "target_existing": target_existing,
        "noop": noop,
        "conflicts": conflicts[:20],
        "items": items[:100],
        "truncated": len(items) > 100,
    }

    # ② 预览：不写库。冲突只报不拦（前端据此禁用确认按钮）。
    if body.dry_run:
        return {**base, "dry_run": True, "changed": 0, "renames": [],
                "current": None}

    if conflicts:
        v = conflicts[0]
        raise HTTPException(409, (
            "批量改会撞车：`%s` 改完是 `%s`（%s）。"
            "同一卷的多道题请用不同题号，或先把目标 key 上的题改走。"
            % (v["key"], v["new_key"], v["why"])))

    from amti import conform as _cf
    stamp = time.strftime("%Y-%m-%d %H:%M")

    # ③ 不改 key（出处没变，或 key 不是由出处拼出来的）→ 只动命中卷。
    #    用户截图里的那种卷名缺字就是这条路：二十多道题一次写一卷。
    if not renamed_n:
        by, vols, chunks, sig = store.read_many_map(list(plan))
        missing = [k for k in plan if k not in by]
        if missing:
            raise HTTPException(404, "有 %d 道题找不到：%s"
                                % (len(missing), "、".join(missing[:3])))
        before_hashes = {k: q.content_hash() for k, q in by.items()}
        changed = []
        for k in plan:
            q = by[k]
            # 扫元数据和读卷之间有人改过出处：跳过，不拿旧条件去覆盖新值。
            if (str(q.meta.get("book") or "").strip() != old_book
                    or str(q.meta.get("source_label") or "").strip() != old_label):
                continue
            q.meta["book"] = new_book
            q.meta["source_label"] = new_label
            if year_v is None:
                q.meta.pop("year", None)
            else:
                q.meta["year"] = year_v
            q.meta["edited_at"] = stamp
            changed.append(q)
        if not changed:
            raise HTTPException(409, "这些题的出处刚被别处改过，请重新打开详情再试")
        viol = _cf.run(changed)
        if viol:
            raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                                % (viol[0]["why"], viol[0]["check"],
                                   viol[0]["field"]))
        rep = store.write_many(changed, volumes=vols, chunks=chunks,
                               expect_hashes=before_hashes, expect_sig=sig,
                               by="界面改解析")
        keys = [q.key for q in changed]
        fulltext.apply(keys, {q.key: q for q in changed})
        _rm_apply(keys, sig, {q.key: q for q in changed})
        _audit_batch_source(old_book=old_book, old_label=old_label,
                            new_book=new_book, new_label=new_label, year=year_v,
                            renames=[], touched=len(changed), moved_refs={})
        cur = next((q for q in changed if q.key == body.focus_key), None)
        current = None
        if cur is not None:
            current = _brief(cur)
            current["tex"] = question_to_tex(cur)
        return {**base, "dry_run": False, "matched": len(changed),
                "changed": len(changed), "renamed": 0, "kept": len(changed),
                "renames": [], "current": current,
                "volumes": rep.get("volumes"),
                "partial": rep.get("partial", False)}

    # ④ 要改名 → 整库读改写（改名会牵动别的题 meta 里的引用，单卷写不了）。
    qs, sig = store.load_for_update()
    by = {q.key: q for q in qs}
    missing = [k for k in plan if k not in by]
    if missing:
        raise HTTPException(404, "有 %d 道题找不到：%s"
                            % (len(missing), "、".join(missing[:3])))
    todo = []
    for k in plan:
        q = by[k]
        if (str(q.meta.get("book") or "").strip() != old_book
                or str(q.meta.get("source_label") or "").strip() != old_label):
            continue
        todo.append(q)
    if not todo:
        raise HTTPException(409, "这些题的出处刚被别处改过，请重新打开详情再试")
    focus_q = next((q for q in todo if q.key == body.focus_key), None)

    # 改名判据要拿**改名前的**书/卷名比（下面会覆盖 meta）
    todo_keys = {q.key for q in todo}
    occupied = set(by) - todo_keys
    final: list[tuple] = []
    for q in todo:
        old_key = q.key
        new_key = _source_key(old_key, q.meta.get("book") or "",
                              q.meta.get("source_label") or "",
                              new_book, new_label)
        final.append((q, old_key, new_key))
    finals = [nk for _q, _o, nk in final]
    if len(set(finals)) != len(finals):
        raise HTTPException(409, "批量改完有两道题同名，没有保存")
    taken = next(((o, nk) for _q, o, nk in final
                  if nk != o and nk in occupied), None)
    if taken:
        raise HTTPException(409, "改名撞车：`%s` → `%s`（新 key 已经有别的题）"
                            % taken)

    renamed: list[tuple[str, str]] = []
    for q, old_key, new_key in final:
        q.meta["book"] = new_book
        q.meta["source_label"] = new_label
        if year_v is None:
            q.meta.pop("year", None)
        else:
            q.meta["year"] = year_v
        q.meta["edited_at"] = stamp
        if new_key != old_key:
            q.key = new_key
            renamed.append((old_key, new_key))
    # 改名会动**别的题** meta 里的 dup_of/also_in/merged_keys；必须在写回前改。
    _migrate_meta_refs(qs, dict(renamed))

    viol = _cf.run(todo)
    if viol:
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (viol[0]["why"], viol[0]["check"], viol[0]["field"]))
    all_changed = list(dict.fromkeys([q.key for q in todo]
                                     + [o for o, _n in renamed]))
    store.rewrite_all(qs, based_on=sig,
                      changed_keys=(None if renamed else all_changed))
    fulltext.apply(all_changed, {q.key: q for q in todo})
    _rm_apply(all_changed, sig, {q.key: q for q in todo})
    moved: dict[str, list[str]] = {}
    for old, new in renamed:
        moved[old] = _migrate_key_refs(old, new)
        _migrate_usage(old, new)
    _audit_batch_source(old_book=old_book, old_label=old_label,
                        new_book=new_book, new_label=new_label, year=year_v,
                        renames=renamed, touched=len(todo), moved_refs=moved)
    current = None
    if focus_q is not None:
        current = _brief(focus_q)
        current["tex"] = question_to_tex(focus_q)
    renames_out = [{
        "old": old, "new": new,
        "book": new_book, "label": new_label,
        "year": year_v if year_v is not None else "",
    } for old, new in renamed]
    return {**base, "dry_run": False, "matched": len(todo),
            "changed": len(todo), "renamed": len(renamed),
            "kept": len(todo) - len(renamed), "renames": renames_out,
            "current": current,
            "volumes": None, "partial": False}


# ── 补解析／补答案 ────────────────────────────────────────────────────
#
# 用户的原话：「没有解析也没有答案，我可以在题目界面直接录入 latex 代码，
# 经规范审查后，可以把解析写入，答案我也可以录进去了」。
#
# 这是**从界面改正文**，比改答案重，所以按录入那条路的规矩来，一步不少：
#
#     ① 规范化   过一遍 `normalize`（答案进作答括号、行间公式去壳…）
#     ② 规范审查 `conform` 必须 0 违规
#     ③ 落盘     写库 + 记 `变更记录/`
#
# **仍然改不了题干和选项**——那两个字段不在这个接口的射程里。
# 题干是题目的本体，改它等于换了一道题，必须走重新录入。

# ── 从整份文档里取出解析 ──────────────────────────────────────────────
#
# 用户是**直接粘整份 `.tex`** 的：`\documentclass`、`\usepackage`、
# `\begin{document}`、题目环境、解析环境全在里面。原样塞进 `solution`
# 会被规范检查拦住（`\documentclass` 会当正文渲染成一堆反斜杠）——
# 拦得对，但对用户没用：他要的是"贴进去就能用"。
#
# 所以这里把**解析那一段**取出来，其余部分丢掉。

_SOL_ENV = re.compile(r"\\begin\{solution\}(.*?)\\end\{solution\}", re.S)
_DOC_ENV = re.compile(r"\\begin\{document\}(.*?)\\end\{document\}", re.S)
_PREAMBLE = re.compile(
    r"\\(documentclass|usepackage|RequirePackage|geometry|examsetup)"
    r"\s*(\[[^\]]*\])?\s*\{[^}]*\}")
_Q_ENV = re.compile(r"\\begin\{question\}(.*?)\\end\{question\}", re.S)
# 解里若混进选题的 `choices`，说明取错了范围
_CHOICES = re.compile(r"\\begin\{choices\}")


def _extract_solution(raw: str) -> tuple[str, list[str]]:
    r"""把用户贴进来的东西**规整成纯解析正文**。返回 (正文, 做了什么)。

    处理顺序（每一步都记进 `notes`，干跑时给人看）：

      ① 有 `\begin{solution}…\end{solution}` → 只取里面
      ② 有 `\begin{document}…\end{document}`   → 只取里面
      ③ 去掉导言区命令（`\documentclass`／`\usepackage`…）
      ④ 若还剩 `\begin{question}…\end{question}` → 整段丢掉
         （那是题面，不是解析；**解析里不该有题面**）

    只认这几种，别的**不猜**：剩下的内容照原样交给规范器去审。
    """
    notes: list[str] = []
    t = raw or ""

    m = _SOL_ENV.search(t)
    if m:
        t = m.group(1)
        notes.append("从 `\\begin{solution}…\\end{solution}` 里取出解析")
    else:
        m2 = _DOC_ENV.search(t)
        if m2:
            t = m2.group(1)
            notes.append("从 `\\begin{document}…\\end{document}` 里取出正文")

    t2, n = _PREAMBLE.subn("", t)
    if n:
        t = t2
        notes.append("去掉了 %d 条导言区命令" % n)

    t2, n = _Q_ENV.subn("", t)
    if n:
        t = t2
        notes.append("去掉了 %d 个题目环境（那是题面，不该进解析）" % n)

    if _CHOICES.search(t):
        notes.append("⚠ 解析里还留着 `choices` 环境——请确认取的范围对不对")

    return t.strip(), notes


# 从解析里**读**答案（不是解题）。只认明说的写法，读不到就留空。
_ANS_BOXED = re.compile(r"\\boxed\{\\text\{([^}]*)\}\}|\\boxed\{([^}]*)\}")
_ANS_SAID = re.compile(r"(?:故选|答案为|答案[：:])\s*([A-D](?:\s*[、,，]?\s*[A-D])*)")


def _answer_from_solution(sol: str, q) -> str:
    r"""解析里明写了答案就顺手读出来。**读不到就返回空**，不猜。

    用户的原文以 `\boxed{\text{A、B、C}}` 收尾——这种一眼能看出来的，
    没必要让人再手填一遍。
    """
    if not sol:
        return ""
    m = _ANS_BOXED.search(sol)
    if m:
        txt = m.group(1) or m.group(2) or ""
        letters = "".join(sorted(set(re.findall(r"[A-D]", txt.upper()))))
        if letters:
            return letters
    m = _ANS_SAID.search(sol)
    if m:
        letters = "".join(sorted(set(re.findall(r"[A-D]", m.group(1).upper()))))
        if letters:
            return letters
    return ""


class SolutionBody(BaseModel):
    solution: str = ""
    answer: str = ""
    dry_run: bool = True                # 默认只审不写
    #: 谁写的：human（详情页手录） / deepseek（整理题库的 suggestions）。
    source: str = "human"


@router.post("/questions/{key:path}/solution")
@retry_on_concurrent
def question_solution(key: str, body: SolutionBody) -> dict:
    r"""补/改**解析与答案**。默认干跑，`dry_run=false` 才落盘。"""
    from amti import conform as _cf
    from amti import latex_ir as _lir
    from amti import normalize as _norm

    k = urllib.parse.unquote(key)
    # 解析/答案不改 key：只读/只写目标卷，别把全库拉进来。
    one = store.read_one(k)
    if one is None:
        raise HTTPException(404, "没有这道题：%s" % k)
    q, vol, sig, chunk = one
    before = q.content_hash()
    before_record = q.record_hash()

    # 在一份**副本**上试，干跑和落盘走的是同一条路——
    # 不然"预览看到的"和"真写进去的"就不是一个东西了。
    from copy import deepcopy
    t = deepcopy(q)

    before_viol = [{"check": v["check"], "why": v["why"], "field": v["field"]}
                   for v in _cf.run([t])]

    notes: list[str] = []
    if body.solution.strip():
        # **贴整份文档也认**：把解析那一段取出来，导言区和题面丢掉
        sol, notes = _extract_solution(body.solution)
        if not sol.strip():
            return {"ok": False, "saved": False, "error":
                    "没找到解析内容。可以贴整份文档（含 \begin{solution}…），"
                    "也可以只贴解析正文。", "notes": notes}
        sol, kept = _lir.preserve_figures(q.solution, sol)
        if kept:
            notes.append("原解析里的配图已保留在末尾：%s" % "、".join(kept))
        t.solution = sol
    # 答案：手填的优先；没填就从解析里读（只认明写的写法）
    if body.answer.strip():
        t.answer = _clean_answer_input(t, body.answer)
        t.answer, kept = _lir.preserve_figures(q.answer, t.answer)
        if kept:
            notes.append("原答案里的配图已保留在末尾：%s" % "、".join(kept))
    elif t.solution:
        got = _answer_from_solution(t.solution, t)
        if got:
            t.answer = _clean_answer_input(t, got)
            notes.append("从解析里读出了答案：%s" % got)

    fixed = _norm.normalize(t, _norm.ENTRY)         # ① 规范化
    after_viol = [{"check": v["check"], "why": v["why"], "field": v["field"]}
                  for v in _cf.run([t])]            # ② 规范审查
    if after_viol:
        return {"ok": False, "saved": False,
                "before": before_viol, "fixed": fixed, "after": after_viol,
                "error": "规范审查没通过：%s（%s）"
                         % (after_viol[0]["why"], after_viol[0]["check"])}

    if body.dry_run:
        return {"ok": True, "saved": False, "before": before_viol,
                "fixed": fixed, "after": [], "solution": t.solution,
                "answer": t.answer, "stem": t.stem, "notes": notes}

    # ③ 落盘。**改的只能是解析和答案**，别的字段一个字都不许动。
    #
    # ⚠️ 题干要**先抹掉作答括号再比**：规范化本来就会把答案写进
    # `\paren[…]`／`\fillin[…]`（这正是「答案进作答括号」那条规则干的事），
    # 拿原样题干去比必然误报。除掉这个位置之后，正文才是一个字节都不许变。
    def _guard_of(x):
        return (_content_outside_answer(x)[0],
                [(o.label, o.text) for o in x.options],
                [f.id for f in (x.figures or [])],
                list(x.points))

    guard = _guard_of(q)
    old_sol, old_ans, old_stem = q.solution, q.answer, q.stem
    q.solution, q.answer = t.solution, t.answer
    # ⚠️ **题干也要跟着规范化后的走**。
    # 「答案进作答括号」改的正是题干（往里插 `\paren[B]`）——只拷答案不拷题干的话，
    # 这条规则白做，卷面上不出现作答括号、答案也没地方显示。
    # 安全性由上面那道 `_guard_of` 保证：除作答位置外，题干正文一个字节都没变。
    q.stem = t.stem
    if _guard_of(q) != guard:
        q.solution, q.answer, q.stem = old_sol, old_ans, old_stem   # 回滚
        raise HTTPException(500, "改解析时动到了题干正文/选项/配图/考点，已拒绝")
    writer = "deepseek" if str(body.source or "").strip() == "deepseek" else "human"
    # 只给实际写了的字段盖来源，别在“只补答案”时把原解析来源改成 deepseek。
    if body.solution.strip():
        q.meta["solution_source"] = writer
    # 同样：改解析≠审过整题。已有复核会因 content_hash 变化自动 stale。
    if body.answer.strip():
        q.meta["answer_source"] = writer
    q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    # 同 patch_question：**交给 @retry_on_concurrent 处理**，别在这里转 409，
    # 否则装饰器永远接不到 ConcurrentWrite、自动重试失效。
    store.write_one(q, volume=vol, expect_hash=before, expect_sig=sig,
                    chunk=chunk, expect_record=before_record,
                    by="界面改出处")
    fulltext.apply([q.key], {q.key: q})
    _rm_apply([q.key], sig, {q.key: q})

    try:
        from amti.audit import CHANGE_DIR
        import time as _t
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面补解析.md" % _t.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面补解析\n\n- 时间：%s\n- 题目：`%s`\n"
            "- 解析：%d → %d 字\n- 答案：%r → %r\n"
            "- 规范化改动：%s\n- 规范审查：通过（0 违规）\n"
            % (_t.strftime("%Y-%m-%d %H:%M:%S"), q.key,
               len(old_sol or ""), len(q.solution or ""), old_ans, q.answer,
               "、".join(fixed) if fixed else "无"),
            encoding="utf-8")
    except Exception:
        log.warning("解析变更记档失败（修改已生效）：%s", "", exc_info=True)
        pass

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    d.update({"ok": True, "saved": True, "before": before_viol,
              "fixed": fixed, "after": [], "notes": notes})
    return d


# ── 改源码 ────────────────────────────────────────────────────────────
#
# 详情页的「改源码」：把整道题的 LaTeX 正文（`\begin{question}…\end{question}`）
# 拿来直接改。**不设口令**（用户明确说没必要）：打开就是编辑器；
# 安全性由下面几道校验兜住，而不是靠多输一次密码——
#   · 只改正文，`%% @q` 元数据行不进来（key/出处/考点不会被手改坏）；
#   · 解析 → 规范化 → 规范审查，结构/格式不过一律不写；
#   · `expect_hash` 防并发覆盖；`store.update` 的写锁 + 临时文件 + rename
#     保证不会写半截。
#
# 保存走 `store.update`：读全库、改这一道、整库写回都在同一把锁里，
# 不会覆盖别人同时写进来的题。`expect_hash` 再挡一层「这道题本身被改过」。

class SourceBody(BaseModel):
    tex: str | None = None             # 不给 = 把当前源码发回来
    dry_run: bool = True               # 默认只检查不写盘
    expect_hash: str = ""              # 打开编辑器时那道题的内容指纹


def _source_candidate(old, tex: str):
    r"""界面上的源码 → 一道题。**只碰正文，元数据一律沿用库里的。**

    返回 `(候选题, 改之前的问题, 规范化改动, 复核后的问题, 结构问题)`。
    解析不出来直接 400 —— 这种情况没有"部分成功"可言。
    """
    from amti import conform as _cf
    from amti import normalize as _norm
    from amti.latex_ir import parse_question

    text = (tex or "").strip()
    # 用户可能把 `%% @q` 那行一起贴回来；元数据不在编辑范围内，直接丢掉。
    text = re.sub(r"(?m)^[ \t]*%%[ \t]*@q[^\n]*\n?", "", text).strip()
    if not text:
        raise HTTPException(400, "源码是空的")

    # **只允许一道题。** 多贴一道时 `parse_question` 会静默只取第一道，
    # 后面的内容看起来"保存成功"其实丢了——宁可当场拒绝。
    if len(re.findall(r"\\begin\{(?:question|problem)\}", text)) != 1:
        raise HTTPException(
            400, r"这里只改一道题：源码里要恰好有一个 \begin{question} 或 \begin{problem}")
    if not re.search(r"\\end\{(?:question|problem)\}\s*$", text):
        raise HTTPException(
            400, r"源码要在 \end{question}（或 \end{problem}）结束，后面不要带别的题")

    cand = parse_question(text)
    if cand is None:
        raise HTTPException(
            400, r"没认出题目环境：源码里要有 \begin{question} … \end{question}")

    # key / 考点不能从源码里改（源码里也没有它们）。
    cand.key = old.key
    cand.points = list(old.points)
    # 分值由正文的 `[points=…]` 表达；其余元数据（出处/年份/难度/来源）
    # 沿用库里的。旧分值先删掉，否则把 `[points=…]` 删了也改不回去。
    meta = dict(old.meta or {})
    meta.pop("points", None)
    meta.update(cand.meta or {})
    cand.meta = meta

    # **改之前**：用户这份源码本身合不合规。必须跑在规范化**之前**——
    # 跑在后面的话"改之前"和"复核后"是同一份，报告就成了摆设。
    before = [{"check": v["check"], "why": v["why"], "field": v["field"]}
              for v in _cf.run([cand])]

    fixed = _norm.normalize(cand, _norm.ENTRY)
    after = [{"check": v["check"], "why": v["why"], "field": v["field"]}
             for v in _cf.run([cand])]
    problems = cand.problems()

    # **防手滑删光。** 源码编辑是整段替换：少写一行 `\paren[A]`、把
    # `\begin{solution}` 连同内容一起删掉，格式上都是合法的，`conform`
    # 也看不出来——但题目会悄悄变成"没答案/没解析"。
    # 库的规矩是「没答案或没解析一律不许入库」，所以这里必须拦；
    # 真想清空就走「改答案」那条路（那里本来就有明确的提示）。
    if (old.answer or "").strip() and not (cand.answer or "").strip():
        problems.insert(0, "答案被清空了——如果是有意换答案，请在同一份源码里把新答案写进去")
    if old.has_solution and not cand.has_solution:
        problems.insert(0, "解析被删空了——可以改写，但不能把整段解析删掉")
    return cand, before, fixed, after, problems


def _source_images(q) -> dict:
    r"""这道题引用了哪些图、在不在库里。

    `改源码` 不能上传图片（那是录入那条路的事），所以这里只**如实报**：
    缺的图保存后会露在卷面上，必须在按保存之前看见。
    """
    from amti import images as _im
    out: dict[str, dict] = {}
    for text in [q.stem, q.solution] + [o.text for o in q.options]:
        for name in _im.collect(text or ""):
            if name in out:
                continue
            out[name] = ({"status": "ok", "note": "已在库"}
                         if (IMG_DIR / name).is_file()
                         else {"status": "missing", "note": "库里没有这张图"})
    return out


def _source_report(cand, before, fixed, after, problems) -> dict:
    r"""检查结果 + 渲染预览。**检查与保存走同一个构造函数**，
    所以"预览看到的"就是"真写进去的"（和补解析接口同一个原则）。

    报告的**分块与录入页那套一致**（`spec` / `images` / `impact`）：
    改源码和录新题是同一件事的两半，界面不该有两套说法。
    """
    try:
        d = _brief(cand)
    except Exception:
        # 源码坏到连预览都解析不了时，仍然把审查报告交回去；
        # 不能因为预览失败就让整个接口 500（那样用户什么也看不到）。
        log.warning("源码预览解析失败：%s", cand.key, exc_info=True)
        d = {
            "key": cand.key, "type": cand.type,
            "type_label": QTYPE_LABEL.get(cand.type, cand.type),
            "stem": cand.stem,
            "options": [{"label": o.label, "text": o.text} for o in cand.options],
            "answer": cand.answer, "solution": cand.solution,
            "blocks": {"stem": [], "answer": [], "solution": [], "options": []},
            "points": cand.points, "difficulty": cand.difficulty, "stars": cand.stars,
            "point_titles": cand.point_titles, "meta": cand.meta, "kind": cand.kind,
            "hash": cand.content_hash(), "missing": cand.missing(),
            "problems": problems, "figures": [f.id for f in cand.figures],
            "flags": {},
        }
    d.update({
        "ok": not after and not problems,
        "saved": False,
        "tex": question_to_tex(cand),
        "fixed": fixed,
        "after": after,
        "problems": problems,
        # ── 与录入页同一套报告字段 ──
        "spec": {"before": before, "fixed": fixed, "after": after,
                 "ok": not after and not problems},
        "images": _source_images(cand),
        "impact": {
            "existing_questions": 0,
            "note": "只改这一道；其余题目内容一个字节不动"
                    "（保存时整卷重写，但别的题逐字不变）。",
        },
    })
    return d


def _source_audit(q, before: str, after: str, fixed) -> None:
    r"""改源码的记档。失败**不阻断**保存，但必须留日志——
    「改了但没记录」正是审查报告 Important #3 要防的事。"""
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面改源码.md" % time.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面改源码\n\n- 时间：%s\n- 题目：`%s`\n"
            "- 内容指纹：%s → %s\n- 规范化改动：%s\n"
            "- 规范审查：通过（0 违规）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), q.key, before, after,
               "、".join(fixed) if fixed else "无"),
            encoding="utf-8")
    except Exception:
        log.warning("改源码记档失败（修改已生效）：%s", q.key, exc_info=True)


@router.post("/questions/{key:path}/source")
def question_source(key: str, body: SourceBody) -> dict:
    r"""改一道题的 LaTeX 源码。

    三种用法（同一个接口，只差参数）：

        {}                                              → 返回当前源码
        {"tex": "…"}                                    → 只检查（dry_run 默认 true）
        {"tex": "…", "dry_run": false}                  → 检查 → 写盘

    不设口令（用户明确说没必要）；安全性靠解析/规范化/规范审查、
    `expect_hash` 并发校验和原子写盘。
    """
    k = urllib.parse.unquote(key)

    # ── 取源码 ──
    if body.tex is None:
        q = _load_question(k)
        if q is None:
            raise HTTPException(404, f"没有这道题：{k}")
        return {"ok": True, "key": q.key, "tex": question_to_tex(q),
                "hash": q.content_hash()}

    # ── 干跑：只看不写 ──
    if body.dry_run:
        q = _load_question(k)
        if q is None:
            raise HTTPException(404, f"没有这道题：{k}")
        if body.expect_hash and q.content_hash() != body.expect_hash:
            raise HTTPException(
                409, "这道题刚被别的进程改过（内容指纹变了），"
                     "为免覆盖别人的改动，请关掉重开再改。")
        cand, before, fixed, after, problems = _source_candidate(q, body.tex)
        return _source_report(cand, before, fixed, after, problems)

    # ── 快速档：没改动 / 改坏了 → 根本不进写锁 ──
    #
    # 真写要「读全库 → 改一道 → 整库重写」，实测约 8 秒。可用户点保存时
    # 经常一个字都没改（先点检查再保存），或者源码明显不合规——这两种情况
    # 都**不需要写盘**。下面先拿当前快照算一遍：
    #   · 内容指纹一样 → 直接回「没有改动」；
    #   · 结构/规范不过 → 直接把报告交回去（写进去也会被同一套检查拒绝）。
    # 真正要写时，`store.update` 里还会**再算一遍**，所以这里只省时间，
    # 不放松「保存前必须过检查」这条。
    q0 = _load_question(k)
    if q0 is None:
        raise HTTPException(404, f"没有这道题：{k}")
    if body.expect_hash and q0.content_hash() != body.expect_hash:
        raise HTTPException(
            409, "这道题刚被别的进程改过（内容指纹变了），"
                 "为免覆盖别人的改动，请关掉重开再改。")
    cand0, before0, fixed0, after0, problems0 = _source_candidate(q0, body.tex)
    if after0 or problems0:
        return _source_report(cand0, before0, fixed0, after0, problems0)
    if cand0.content_hash() == q0.content_hash():
        rep = _source_report(cand0, before0, fixed0, after0, problems0)
        rep.update({"ok": True, "saved": False, "unchanged": True})
        return rep

    same_key = bool(cand0.key == q0.key)
    # ── 热路径：源码没改出处（key 不变）→ 只读/只写目标卷 ──
    if same_key:
        one = store.read_one(k)
        if one is None:
            raise HTTPException(404, f"没有这道题：{k}")
        q, vol, sig, chunk = one
        before_record = q.record_hash()
        if body.expect_hash and q.content_hash() != body.expect_hash:
            raise HTTPException(
                409, "这道题刚被别的进程改过（内容指纹变了），"
                     "为免覆盖别人的改动，请关掉重开再改。")
        cand, before, fixed, after, problems = _source_candidate(q, body.tex)
        rep = _source_report(cand, before, fixed, after, problems)
        if after or problems:
            return rep
        after_hash = cand.content_hash()
        if after_hash == before:
            rep.update({"ok": True, "saved": False, "unchanged": True})
            return rep
        cand.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
        try:
            store.write_one(cand, volume=vol, expect_hash=before,
                            expect_sig=sig, chunk=chunk,
                            expect_record=before_record,
                            by="界面插图")
        except store.ConcurrentWrite:
            raise HTTPException(
                409, "这道题在你改的时候被别的进程改过了，"
                     "为免覆盖别人的改动，**没有保存**。请关掉重开再改。")
        fulltext.apply([k], {k: cand})
        _rm_apply([k], sig, {k: cand})
        _source_audit(cand, before, after_hash, fixed)
        rep.update({"ok": True, "saved": True, "unchanged": False,
                    "hash": after_hash})
        return rep

    # ── 真写：改出处可能换 key，需要整库处理跨题引用 ──
    out: dict = {}

    def _do(qs):
        for i, q in enumerate(qs):
            if q.key != k:
                continue
            before = q.content_hash()
            if body.expect_hash and before != body.expect_hash:
                out["conflict"] = True
                return store.NO_WRITE

            cand, before, fixed, after, problems = _source_candidate(q, body.tex)
            out["report"] = _source_report(cand, before, fixed, after, problems)
            if problems or after:
                out["invalid"] = True
                return store.NO_WRITE

            after_hash = cand.content_hash()
            if after_hash == before:
                # 一个字没改：**不写盘**。否则整库重写会把所有卷的 mtime
                # 都改掉，别的进程的 `based_on` 校验会白失败一次。
                out["unchanged"] = True
                return store.NO_WRITE

            cand.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
            # 源码里改了 `\source{}` 也可能换 key。和「改出处」一样，
            # 跨题 meta 引用要在整库写回之前跟着换；存档/台账在写回后迁。
            if cand.key != q.key:
                out["renamed_from"] = q.key
                _migrate_meta_refs(qs, q.key, cand.key)
            qs[i] = cand
            out.update({"before": before, "after_hash": after_hash,
                        "fixed": fixed, "cand": cand})
            return qs
        out["missing"] = True
        return store.NO_WRITE

    # 走到这里说明源码改了出处/key：别的题 meta 里的 dup_of/also_in
    # 等引用要一起改，必须整库写回。
    old_sig = store.volume_signature()
    store.update(_do)

    if out.get("missing"):
        raise HTTPException(404, f"没有这道题：{k}")
    if out.get("conflict"):
        raise HTTPException(
            409, "这道题在你改的时候被别的进程改过了，"
                 "为免覆盖别人的改动，**没有保存**。请关掉重开再改。")
    rep = out["report"]
    if out.get("invalid"):
        return rep
    if out.get("unchanged"):
        rep.update({"ok": True, "saved": False, "unchanged": True})
        return rep

    fulltext.apply([k, out["cand"].key], {out["cand"].key: out["cand"]})
    _rm_apply([k, out["cand"].key], old_sig,
              {out["cand"].key: out["cand"]})

    # 源码改出处 → 换 key：存档/使用频次/改名台账在写回之后迁
    # （和 `patch_question` 同一套；不然改一次 `\source{}` 引用就全断了）
    renamed_from = out.get("renamed_from") or ""
    if renamed_from:
        moved = _migrate_key_refs(renamed_from, out["cand"].key)
        _migrate_usage(renamed_from, out["cand"].key)
        _audit_key_rename(renamed_from, out["cand"].key)
        rep["renamed_from"] = renamed_from
        log.info("源码改出处：%s → %s（引用已迁：%s）", renamed_from,
                 out["cand"].key, "、".join(moved) or "无")

    _source_audit(out["cand"], out["before"], out["after_hash"], out["fixed"])
    rep.update({"ok": True, "saved": True, "unchanged": False,
                "hash": out["after_hash"]})
    return rep


class TikzInsertBody(BaseModel):
    tikz: str = ""
    placement: str = "stem"       # stem | solution
    dry_run: bool = False


@router.post("/questions/{key:path}/tikz")
def question_tikz(key: str, body: TikzInsertBody) -> dict:
    r"""把一段 TikZ 插进题干/解析，**复用 `/source` 的检查与写回**。

    AI 只负责生成 TikZ；真正落盘仍走源码接口的规范化、结构校验、并发保护。
    插到末尾是保守做法，具体位置可在「改源码」里再调。
    """
    from copy import deepcopy

    k = urllib.parse.unquote(key)
    q = _load_question(k)
    if q is None:
        raise HTTPException(404, f"没有这道题：{k}")
    tikz = (body.tikz or "").strip()
    if not tikz:
        raise HTTPException(400, "TikZ 源码为空")
    if "\\begin{tikzpicture}" not in tikz:
        tikz = "\\begin{tikzpicture}\n%s\n\\end{tikzpicture}" % tikz
    placement = body.placement if body.placement in ("stem", "solution") else "stem"
    q2 = deepcopy(q)
    if placement == "solution":
        q2.solution = (q2.solution.rstrip() + "\n\n" + tikz).strip()
    else:
        q2.stem = (q2.stem.rstrip() + "\n\n" + tikz).strip()
    tex = question_to_tex(q2)
    # 同一套源码检查/写回入口；expect_hash 用刚读到的指纹做并发校验。
    return question_source(k, SourceBody(
        tex=tex, dry_run=body.dry_run, expect_hash=q.content_hash()))
