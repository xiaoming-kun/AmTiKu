"""题目**编辑**路由：改标签 / 改答案 / 改题型 / 改出处（PATCH + 批量）。

## 这里守的边界

界面上能改的只有**标签**和**答案**：考点、难度、星级、出处、题型、
以及 `answer`。题干/选项/解析/配图**不许从这里改**——那是数据，
改它要走「重新录入」的正规路径，过规范、查重、影响面三关。

写库一律走 `store` 的唯一入口，并且**写完立刻同步派生索引**
（`fulltext.apply` + `_rm_apply`），否则列表/搜索会停在旧数据上。
这条由 `amti/lint.py` 的 R1 机检。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from amti import fts as fulltext
from amti import knowledge
from amti import readmodel
from amti import review as review_mod
from amti import store
from amti.logutil import get_logger
from amti.paths import ROOT
from amti.render_tex import question_to_tex
from amti.web.core import (
    USAGE_PATH, _rm_apply,
    _usage, _usage_lock,
)
from amti.web.present import brief as _brief
from amti.web.retry import retry_on_concurrent

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["questions"])


# ── 改答案时的格式处理 ────────────────────────────────────────────────
#
# 用户要的是「看到解析但没答案，随手补进去」。随手写的输入五花八门：
# 全角字母、小写、带括号、多打了顿号……所以**统一在这一层规整**，
# 规整不了就明确报错，绝不把半成品写进库。

# 题干里的**作答位置**。有两种写法，比对时都要抹平：
#   · 规范化之后的 `\paren[B]` / `\fillin[$x$]`
#   · 规范化之前的裸括号 `（ ）` / `（\quad）` / `(\qquad)`
#
# 只认前者的话，一道题干写 `（ ）` 的题在补答案时会被护栏判成
# "题干被改了"而拒绝——可那本来就是同一个位置，只是换了写法。
_SLOT = re.compile(
    # `\fillin` 有三种形态，**都要吃掉**：
    #   `\fillin{}`        空的（规范化前）
    #   `\fillin[$18$]`    填好的（规范化后）
    #   `\fillin`          光杆的
    # 早先只认中间那种，于是 `\fillin{}` 被替成占位符后**还剩一个 `{}`**，
    # 而填好的那个替完就没了 `{}`——两边一比就"不一样"，
    # 改答案时被误判成"动了题干"而拒绝。实测踩过。
    r"\\(paren|fillin)\s*(\[[^\]]*\])?\s*(\{[^{}]*\})?"
    r"|[（(]\s*(?:\\quad|\\qquad)?\s*[）)]")


def _content_outside_answer(q) -> tuple:
    r"""**除答案与作答括号之外**的内容快照。

    改答案会正当地改到两处：`answer` 字段，和题干里的 `\paren[…]`／`fillin[…]`。
    除此之外——题干正文、选项、解析、配图——**一个字节都不许变**。
    改完拿这个快照比对，对不上就说明改答案的路上动了别的东西。
    """
    # 两种写法都替换成同一个占位符，并**去掉所有空白**——
    # 我们关心的是"正文有没有被动过"，不是排版空白或作答位置用哪种写法。
    stem = re.sub(r"\s+", "", _SLOT.sub("§", q.stem or ""))
    return (stem, q.solution or "",
            tuple((o.label, o.text) for o in q.options),
            tuple(f.id for f in (q.figures or [])))


def _clean_answer_input(q, raw) -> str:
    r"""把界面上随手写的答案**规整成规范形态**；规整不了就报 400。

    按题型分别处理（这是"注意格式问题"的核心）：

    | 题型 | 收什么 | 规整成 |
    |---|---|---|
    | 单选 | `b` / `Ｂ` / `B、` / `选B` | `B`，**只能一个** |
    | 多选 | `abd` / `A,B,D` / `ABD` | `ABD`，排序去重，2–4 个 |
    | 填空 | 任意结果，如 `$\frac{1}{2}$`、`②③` | 去空白，检查 `$` 配平 |
    | 解答 | 结论文字（一般留空，结论写解析里） | 原样，同样检查 `$` 配平 |

    **不猜**：字母超范围（比如 `E`）、单选题给了两个字母、`$` 不配平——
    一律报错说清楚，而不是硬塞一个进去。
    """
    txt = str(raw or "").strip()
    if not txt:
        return ""                      # 允许清空（等于"这题确实没答案"）

    if q.type in ("single_choice", "multi_choice"):
        # 全角字母先转半角，再去掉所有非 A–D 的字符
        t = "".join(chr(ord(c) - 0xFEE0) if "Ａ" <= c <= "Ｚ" else c for c in txt)
        letters = sorted(set(re.findall(r"[A-Da-d]", t.upper())))
        if not letters:
            raise HTTPException(400, "选择题的答案要写选项字母，比如 B 或 ABD；收到 %r" % txt)
        # 有 E 之后的字母说明写错了（本库选项只有 A–D）
        stray = sorted(set(re.findall(r"[E-Za-z]", t.upper())))
        if stray:
            raise HTTPException(400, "选项只有 A–D，收到 %s" % "、".join(stray))
        if q.type == "single_choice" and len(letters) != 1:
            raise HTTPException(
                400, "这是**单选题**，只能填一个字母；收到 %s。"
                     "如果这题本来就该多选，请先把题型改成多选。" % "".join(letters))
        if q.type == "multi_choice" and len(letters) < 2:
            raise HTTPException(400, "这是**多选题**，至少要两个字母；收到 %s" % "".join(letters))
        return "".join(letters)

    # 填空/解答：结果本身可以是任意 LaTeX，但有两个硬要求
    if txt.count("$") % 2:
        raise HTTPException(400, "答案里的 `$` 个数是奇数（%d 个），数学模式没闭合" % txt.count("$"))
    if _SLOT.search(txt):
        raise HTTPException(400, "答案里不能写 `\\paren`／`\\fillin`——那是题干里的作答位置")
    return txt


# ── 改题型 ────────────────────────────────────────────────────────────
#
# 用户会遇到：**题目其实是多选，却被标成了单选**（选项 B、C、D 都对）。
# 题面里那句「则下列说法正确的是」根本看不出单选还是多选，判错很正常。
#
# 但改题型会**牵动答案的合法性**：
#   单选 → 恰好 1 个字母      多选 → 至少 2 个字母
# 所以这里不许"只改题型"了事——要么现有的答案对新题型也合法，
# 要么在**同一次请求**里把答案一起改好。**绝不悄悄把答案清掉。**
#
# 目前只放开**单选 ↔ 多选**：两者用同一个作答位置 `\paren[…]`，
# 换过去不影响题干。换成填空/解答要动选项和作答位置，那是另一回事，
# 会把题目改残，所以明确拒绝并说明原因。

_CHOICE_TYPES = ("single_choice", "multi_choice")


def _convert_type(q, new_type: str) -> str:
    r"""改题型。返回一句说明；不合法就抛 400。"""
    from amti.schema import QTYPE_LABEL
    if new_type not in QTYPE_LABEL:
        raise HTTPException(400, "没有这个题型：%s（可选：%s）"
                            % (new_type, "、".join(QTYPE_LABEL)))
    old = q.type
    if new_type == old:
        return ""
    if old not in _CHOICE_TYPES or new_type not in _CHOICE_TYPES:
        raise HTTPException(400, (
            "目前只支持**单选 ↔ 多选**互改。%s → %s 要动选项和作答位置，"
            "改下去容易把题目改残——请改题目源文件后重新录入。"
            % (QTYPE_LABEL.get(old, old), QTYPE_LABEL[new_type])))
    # 选择题得有选项，否则改完就是一道空壳
    if len(q.options) < 2:
        raise HTTPException(400, "这道题只有 %d 个选项，不能算选择题" % len(q.options))
    q.type = new_type
    return "%s → %s" % (QTYPE_LABEL[old], QTYPE_LABEL[new_type])


def _audit_tag_change(q, *, before: str, fields) -> None:
    r"""把「界面改标签」记一份档。

    只记标签变化，不记正文 —— 正文根本走不到这里（指纹校验会拦住）。
    记档失败**不阻断**修改，但必须留下日志：审查报告 Important #3 指出，
    原本全项目 0 处 logging，"改了但没记录"这种事没人知道。
    """
    from amti.audit import CHANGE_DIR
    try:
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_界面改标签.md" % time.strftime("%Y%m%d_%H%M%S"))
        f.write_text(
            "# 界面改标签\n\n"
            "- 时间：%s\n- 题目：`%s`\n- 改动：%s\n"
            "- 内容指纹：%s → %s（**没变**，改的只是标签）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), q.key,
               "、".join(sorted(fields)), before, q.content_hash()),
            encoding="utf-8")
    except Exception:
        log.warning("标签变更记档失败（修改已生效）：%s", q.key, exc_info=True)


#: 存档里存的是**题目 key 字符串**（`试卷/存档.json` 的 `keys`、讲义存档的 blocks）。
#: 改 key 不跟着改，那几份卷子/讲义里这一题就**静默消失**——打开只看出来"少一道"，
#: 不报错，也没人知道为什么。
#:
#: `数据/订正台账.json` 也存 key（`patches[].key`、`retired[]`）。不迁的话，
#: 台账里多出一批死账，而 `fixups.run` 是「一条对不上就整批不执行」——
#: 1252 条待办全被卡住（`脚本/批量改出处.py` 把这一条列为必迁落点）。
_KEY_REF_FILES = ("试卷/存档.json", "讲义/讲义存档.json", "数据/订正台账.json",
                  "数据/专题/manifest.json")

#: 改名台账：`store.diff()` 读它，把「改了个名字」和「删一道 + 加一道」分开。
#: 不记的话，每改一次出处，顶栏的「删除」就红一次——那样的红灯很快就没人看了。
#: 路径**只有一处**（`store.RENAME_LEDGER`），这里只引用，别写第二份。


def _migrate_key_refs(old: str, new: str) -> list[str]:
    r"""把存档里引用的 `old` 换成 `new`。返回改到的文件（相对路径）。

    只做**整串替换**（连引号一起比），不解析结构：
    存档是给人看的 JSON，重排一遍会把 diff 弄得面目全非。
    改完**必须仍能 `json.loads`**，否则宁可不动——那说明替换改坏了文件。
    """
    a = json.dumps(old, ensure_ascii=False)
    b = json.dumps(new, ensure_ascii=False)
    hit: list[str] = []
    # `数据/专题/选题/*.json` 里存的是 add/remove/place 三类 key；
    # 不迁的话，改一次出处，高中讲义里那道题就悄悄消失。
    sel = ROOT / "数据" / "专题" / "选题"
    paths = [ROOT / rel for rel in _KEY_REF_FILES]
    if sel.is_dir():
        paths += sorted(sel.glob("*.json"))
    for p in paths:
        if not p.is_file():
            continue
        try:
            rel = str(p.relative_to(ROOT))
        except ValueError:
            rel = str(p)
        try:
            t = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if a not in t:
            continue
        t2 = t.replace(a, b)
        try:
            json.loads(t2)
        except ValueError:
            log.warning("改出处：%s 里替换后不是合法 JSON，跳过（引用会留在旧 key 上）", rel)
            continue
        try:
            p.write_text(t2, encoding="utf-8")
            hit.append(rel)
        except OSError:
            log.warning("改出处：写 %s 失败", rel, exc_info=True)
    return hit


def _migrate_usage(old: str, new: str) -> None:
    r"""改出处 = 改 key：把「被组过几次」也跟着迁到新 key。

    `数据/使用频次.json` 按 key 记次数。不迁的话，改一次出处这道题的
    「用过 N 次」就归零——默认排序按使用频次，用户会发现「我常用的题不见了」。

    **内存缓存必须一起改**：`_usage()` 只读一次盘，缓存里还是旧 key 的话，
    下次 `_usage_bump` 会把旧 key 写回文件，等于把迁移覆盖掉。
    """
    with _usage_lock:
        d = _usage()
        if old not in d:
            return
        n = d.pop(old)
        d[new] = d.get(new, 0) + n
        try:
            USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
            USAGE_PATH.write_text(json.dumps(d, ensure_ascii=False, sort_keys=True),
                                  encoding="utf-8")
        except OSError:
            log.warning("改出处：使用频次迁移写盘失败（改名已生效）", exc_info=True)
        else:
            readmodel.set_used({new: d.get(new, 0)})


def _migrate_meta_refs(qs, old, new: str | None = None) -> int:
    r"""把**别的题 meta 里指向旧 key 的引用**换成新 key。

    `dup_of`（和谁雷同）、`also_in`（还出现在哪）、`merged_keys`（合并过谁）
    存的是题目 key。改出处换了 key 而这里不换，查重提示/孪生题对账就会
    指向一道不存在的题（`semantic.py` 会报 `dup_of_dangling`）。
    返回改了几处。

    批量改出处一次换几十个 key，所以 `old` 也可以是 `{旧 key: 新 key}`：
    一次遍历改完，别为每个 key 把 3 万道题扫一遍。
    """
    mapping = old if isinstance(old, dict) else {old: new}
    if not mapping:
        return 0

    def hit(k):
        return mapping.get(k) if isinstance(k, str) else None

    n = 0
    for x in qs:
        m = x.meta if isinstance(getattr(x, "meta", None), dict) else {}
        nk = hit(m.get("dup_of"))
        if nk is not None:
            m["dup_of"] = nk
            n += 1
        nk = hit(m.get("merged_from"))
        if nk is not None:
            m["merged_from"] = nk
            n += 1
        for f in ("also_in", "merged_keys"):
            v = m.get(f)
            if isinstance(v, list) and any(hit(z) is not None for z in v):
                m[f] = [hit(z) or z for z in v]
                n += 1
    return n


def _ledger_rename(old: str, new: str) -> None:
    r"""把一次改名记进台账（给程序读的那一份）。失败不阻断。"""
    try:
        led = ROOT / store.RENAME_LEDGER
        led.parent.mkdir(parents=True, exist_ok=True)
        with led.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "from": old, "to": new}, ensure_ascii=False) + "\n")
    except OSError:
        log.warning("改出处台账写入失败（改名已生效）：%s", old, exc_info=True)


def _audit_key_rename(old: str, new: str) -> None:
    r"""记两笔：给程序读的台账 + 给人读的报告。**失败不阻断**。"""
    _ledger_rename(old, new)
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f2 = CHANGE_DIR / ("%s_界面改出处.md" % time.strftime("%Y%m%d_%H%M%S"))
        f2.write_text(
            "# 界面改出处\n\n- 时间：%s\n- 原 key：`%s`\n- 新 key：`%s`\n"
            "- 内容指纹：**没变**（改的只是出处）\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), old, new), encoding="utf-8")
    except Exception:
        log.warning("改出处记档失败（改名已生效）：%s", old, exc_info=True)


def _audit_batch_source(*, old_book: str, old_label: str, new_book: str,
                        new_label: str, year, renames: list[tuple[str, str]],
                        touched: int, moved_refs: dict[str, list[str]]) -> None:
    r"""批量改出处记一份**汇总**档。

    单题改出处有 `_audit_key_rename`，但批量改十几道时，如果每道都写一份
    「界面改出处」，同一秒内的文件会互相覆盖（文件名只到秒）。所以这里只
    写一份汇总；台账（`RENAME_LEDGER`）仍按每次改名单条追加，`store.diff()`
    靠它把「改名」和「删一道 + 加一道」区分开。
    """
    for old, new in renames:
        _ledger_rename(old, new)
    try:
        from amti.audit import CHANGE_DIR
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_批量改出处.md" % time.strftime("%Y%m%d_%H%M%S"))
        lines = [
            "# 批量改出处",
            "",
            "- 时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
            "- 旧出处：`%s / %s`" % (old_book, old_label),
            "- 新出处：`%s / %s`" % (new_book, new_label),
            "- 年份：%s" % (year if str(year).strip() else "（清空）"),
            "- 题目：%d 道；其中 key 跟着改 %d 道" % (touched, len(renames)),
            "- 内容指纹：**全部没变**（改的只是出处标签）",
        ]
        if renames:
            lines += ["", "## key 变更", "",
                      "\n".join("- `%s` → `%s`" % (o, n) for o, n in renames)]
        hit = sorted({rel for files in moved_refs.values() for rel in files})
        if hit:
            lines += ["", "## 引用迁移", "",
                      "\n".join("- %s" % rel for rel in hit)]
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        log.warning("批量改出处记档失败（修改已生效）", exc_info=True)


def _source_key(key: str, old_book: str, old_label: str,
                new_book: str, new_label: str,
                new_no: str | None = None) -> str:
    r"""改出处后 key 变成什么——**单题和批量共用这一条判据**。

    key 本来就是 `书/卷名#号` 拼出来的，才跟着改名；历史结构
    （`高考真题汇编/2024/新高考I卷#1`）和出处不同构，只改标签，
    否则等于悄悄换身份：基线里旧 key 变成“被删了”，组过的卷子也断引用。

    单题还能顺手改题号（`new_no`）：不同构的 key 也换掉 `#` 后面那截，
    目录（head）一个字不动。批量改出处不传 `new_no`，题号各自保留。
    """
    head, sep, tail = key.rpartition("#")
    if not sep:
        head, tail = key, "1"
    if new_no is not None:
        tail = new_no
    # 比对前先 strip：meta 里的书/卷名可能带首尾空格，而 key 是编辑时
    # 拼出来的；不 strip 就会出现「预览说会改名、写回却不改」的分叉。
    if head.strip() == ("%s/%s" % (old_book, old_label)).strip():
        return "%s/%s#%s" % (new_book.strip(), new_label.strip(), tail)
    return key if new_no is None else "%s#%s" % (head, tail)


def _apply_question_patch(q, body: dict, *, before: str,
                          content_before: tuple) -> None:
    r"""把白名单里的**非出处**字段应用到 q，并做正文/规范校验。

    单题 `patch_question` 有两条落盘路径：
      · 不带 `source`：`store.read_one()` + `store.write_one()` 只动一卷（热路径）；
      · 带 `source`：可能要改 key/跨卷引用，仍走整库 `load_for_update()`。
    两条路必须用**同一份**字段应用与校验逻辑，否则就会分叉；这个函数是那份逻辑。
    """
    if "points" in body:
        pts = [str(p).strip() for p in (body.get("points") or []) if str(p).strip()]
        bad = [p for p in pts if not knowledge.get(p)]
        if bad:
            raise HTTPException(400, "考点不存在：%s" % "、".join(bad))
        q.points = pts
        # 人工改过的标签，来源标成 human —— 以后一眼能看出哪些不是模型打的
        q.meta["point_source"] = "human"
    if "difficulty" in body:
        d = (body.get("difficulty") or "").strip()
        if d:
            q.meta["difficulty"] = d
        else:
            q.meta.pop("difficulty", None)      # 恢复成按主考点派生
    if "stars" in body:
        try:
            n = int(body["stars"])
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            q.meta["stars"] = n
        else:
            q.meta.pop("stars", None)


    type_note = ""
    if "type" in body:
        type_note = _convert_type(q, str(body.get("type") or "").strip())
        if type_note:
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    if "answer" in body:
        new_ans = _clean_answer_input(q, body.get("answer"))
        q.answer = new_ans
        q.meta["answer_source"] = "human"       # 人补的，和求解器写的分开记
        # **不要在这里写 reviewed_at**：改答案≠审过整道题。
        # 复核状态由 `/api/review/decision` 或详情页的“快速通过”单独写；
        # 正文一变，`reviewed_hash` 对不上，已有复核会自动失效（stale）。
        # **盖时间戳**：`store.diff()` 靠它把"界面补录"和"规则偷偷动数据"分开。
        # 不盖的话，你在界面上改一道答案，顶栏就报一次"⚠ 内容变化"——
        # 自己改的东西被当成异常，那这个报警很快就没人看了。
        q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")
        # **格式问题就出在这一步**：答案要写进题干的 `\paren[…]`／`\fillin[…]`，
        # 否则卷面上不出现作答括号、答案也没地方显示。
        from amti import normalize as _norm
        _norm.normalize(q, _norm.ENTRY)

    # 改了题型但**没同时给答案**时，现有的答案必须对新题型也合法。
    # 否则会出现"单选题只剩一个字母却标成多选"这种自相矛盾的状态。
    if type_note and "answer" not in body and q.answer.strip():
        try:
            _clean_answer_input(q, q.answer)
        except HTTPException:
            q.type = "multi_choice" if q.type == "single_choice" else "single_choice"
            raise HTTPException(400, (
                "现在这个答案是 %r，改成%s后不合法。"
                "改题型时要**同时**把答案改好（比如把 B 改成 BD）。"
                % (q.answer, "多选题" if q.type == "single_choice" else "单选题")))

    if "reviewed" in body:
        # 详情页的快速通过/收回。语义是**一次审阅决定**，不是“改过”的副作用。
        review_mod.apply_decision(
            q, "approved" if body["reviewed"] else "pending",
            note="详情页快速通过" if body["reviewed"] else "",
            reviewer="界面")

    # 没改答案/题型时，指纹必须**一个字节都没变**（改标签不该动正文）
    if "answer" not in body and "type" not in body and q.content_hash() != before:
        raise HTTPException(500, "内容指纹变了——说明动到了正文，已拒绝")
    # 改答案时：除答案与作答括号之外，正文必须一个字节都没变
    if ("answer" in body or "type" in body) and _content_outside_answer(q) != content_before:
        raise HTTPException(500, "改答案时动到了题干正文/选项/解析，已拒绝")

    # **规范审查**：改完必须仍然合规，否则不存。
    # 答案写错格式（`$` 不配平、把 `\paren` 塞进答案里…）在这里被挡住。
    from amti import conform as _cf
    viol = _cf.run([q])
    if viol:
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (viol[0]["why"], viol[0]["check"], viol[0]["field"]))


@router.patch("/questions/{key:path}")
@retry_on_concurrent
def patch_question(key: str, body: dict) -> dict:
    r"""改标签：**考点**和**难度**。

    权威入口是 `store.rewrite_volume`（MIGRATE 级的那个），
    因为改标签必须落到主文件里才算数。安全性由指纹保证：

        内容指纹只覆盖 题干/选项/答案/解析/配图，
        **标签与元数据不在其中**（`schema.HASH_FIELDS`）。

    所以这个接口**改不动一道题的正文**——就算传了别的字段也白传。
    改完把新指纹回给前端，对不上就说明碰了不该碰的。

    请求体（字段都可选）：
        {"points": ["3.2.2","3.2.1"],   # 考点 id，第一条是主考点
         "difficulty": "难题",           # 空字符串 = 恢复成按主考点派生
         "stars": 3,
         "answer": "B",                  # **补答案**
         "type": "multi_choice",         # **改题型**（目前只放开 单选↔多选）
         "source": {"book": "…", "label": "…", "year": 2027,
                    "region": "…", "no": 22}}
                                         # **改出处**：改完 key 跟着改；
                                         # `no` 是题号（key 里 `#` 后面那截）
    """
    # ⚠️ **白名单：只有这几个字段能改，其余一律拒绝。**
    #
    # 界面上「考点」「难度」「出处」是标签，改它们是日常操作；
    # **题目正文（题干/选项/答案/解析/配图）一个字都不许从界面改**——
    # 那是数据，改它要走「改题目 → 重新录入」的正规路径，
    # 而且要过规范验证、查重、影响面这几关。
    #
    # 老写法是「只读认识的字段、其余静默忽略」——安全，但**不响**：
    # 有人想改题干，接口回 200，他会以为改成功了。
    # 现在直接 400 说清楚。
    ALLOWED = {"points", "difficulty", "stars", "answer", "type", "source",
               "reviewed"}
    unknown = set(body) - ALLOWED
    if unknown:
        raise HTTPException(400, (
            "只允许改 %s；收到 %s。"
            "题目正文（题干/选项/解析/配图）**不能从界面改**——"
            "要改请改题目源文件后重新录入。"
            "（**答案**可以改，见 `answer`。）"
            % ("、".join(sorted(ALLOWED)), "、".join(sorted(unknown)))))

    k = urllib.parse.unquote(key)
    # **热路径**：不改出处就不会改 key，不需要把 3 万道题全读进内存。
    # read_one 只解析目标卷；write_one 在写锁内核对全库签名/内容指纹，
    # 只重写那一卷。改答案/题型也走这里（正文变了但 key 不变）。
    if "source" not in body:
        one = store.read_one(k)
        if one is None:
            raise HTTPException(404, f"没有这道题：{k}")
        q, vol, sig, chunk = one
        before = q.content_hash()
        before_record = q.record_hash()
        content_before = _content_outside_answer(q)
        _apply_question_patch(q, body, before=before, content_before=content_before)
        store.write_one(q, volume=vol, expect_hash=before, expect_sig=sig,
                        chunk=chunk, expect_record=before_record)
        fulltext.apply([k], {q.key: q})
        _rm_apply([k], sig, {q.key: q})
        _audit_tag_change(q, before=before, fields=body)
        d = _brief(q)
        d["tex"] = question_to_tex(q)
        return d

    qs, _sig = store.load_for_update()
    q = next((x for x in qs if x.key == k), None)
    if q is None:
        raise HTTPException(404, f"没有这道题：{k}")

    before = q.content_hash()
    # 改答案会**有意**改到正文（答案在指纹里，题干里的作答括号也要跟着变），
    # 所以单独记一份"**除答案和作答括号之外**"的内容快照。
    # 改完拿它比对：只要题干正文、选项、解析、配图有一个字节变了，就拒绝。
    content_before = _content_outside_answer(q)
    # ── 出处（书 / 卷名 / 年份 / 地区）──────────────────────────────
    #
    # 用户的要求：「录入时填错了出处，录完就改不回来了」。
    # 难点不在改 meta —— 在 **key**：`书/卷名#序号` 是自然键，改出处就得改名。
    # 改名要连带三件事，缺一件就是静默损坏：
    #   ① 查重（新 key 不能已存在）
    #   ② 迁引用（`试卷/存档.json`、`讲义/讲义存档.json` 里存的是 key 字符串）
    #   ③ 记账（`数据/改出处.jsonl`）——`store.diff()` 靠它把"改名"和
    #      "一道题被删、另一道题被加"区分开；不记的话顶栏每改一次出处就红一次
    renamed_from = ""
    if "source" in body:
        src = body.get("source")
        if not isinstance(src, dict):
            raise HTTPException(400, "source 要给对象：{book, label, year, region, no}")
        unknown = set(src) - {"book", "label", "year", "region", "no"}
        if unknown:
            raise HTTPException(400, "source 里不认识的字段：%s"
                                % "、".join(sorted(unknown)))
        book = str(src.get("book", (q.meta or {}).get("book", "")) or "").strip()
        label = str(src.get("label", (q.meta or {}).get("source_label", "")) or "").strip()
        if not book or not label:
            raise HTTPException(400, "来源（书）和出处（卷名）都不能空")
        # key 是 `书/卷名#序号`，这三样里出现分隔符会把 key 结构弄坏
        for bad in ("/", "#"):
            if bad in book or bad in label:
                raise HTTPException(400, "来源/出处里不能有 `%s`（key 的分隔符）" % bad)
        # **题号**（key 里 `#` 后面那截）也能和出处一起改：出处录错时，
        # 「第几题」往往跟着错。统一成不带前导零的正整数——库里的 key
        # 尾串统一成不带前导零的正整数，排序与比较才可靠。
        tail = key.rsplit("#", 1)[-1] if "#" in key else "1"
        new_tail = tail
        if "no" in src:
            raw_no = src.get("no")
            new_tail = str(raw_no).strip()
            if not new_tail.isdigit() or int(new_tail) < 1:
                raise HTTPException(400, "题号要是正整数，收到 %r" % (raw_no,))
            new_tail = str(int(new_tail))
        # ⚠️ **改名判据要拿改名前的书/卷名**：下面 q.meta 会被覆盖，
        # 覆盖之后再取等于拿新值跟旧 key 比——那永远不会同构，改名就静默失效。
        old_book = str((q.meta or {}).get("book", "") or "")
        old_label = str((q.meta or {}).get("source_label", "") or "")
        q.meta["book"] = book
        q.meta["source_label"] = label
        year = src.get("year", (q.meta or {}).get("year", ""))
        if str(year).strip():
            try:
                q.meta["year"] = int(str(year).strip())
            except ValueError:
                raise HTTPException(400, "年份要是整数，收到 %r" % (year,))
        else:
            q.meta.pop("year", None)
        region = str(src.get("region", (q.meta or {}).get("region", "")) or "").strip()
        if region:
            q.meta["region"] = region
        else:
            q.meta.pop("region", None)

        # **只有 key 本来就是 `书/卷名#号` 拼出来的，才跟着改名。**
        # 反例（真踩过）：`高考真题汇编/2024/新高考I卷#1` 的出处是
        # `2024年新高考I卷`——key 里多一层年份目录，和出处**不同构**。
        # 按 meta 重拼 key 会把它改成 `书/2024年新高考I卷#1`，等于
        # 悄悄给这道题换了身份：基线上的旧 key 变成"被删了"，
        # 组进卷子里的引用也跟着断。宁可只改标签，把 key 留着。
        #
        # 但**题号是用户明确改的**：不同构的 key 也要换掉 `#` 后面那截，
        # 否则界面上改了题号、卷子里还印旧号。目录（head）一个字不动。
        new_key = _source_key(key, old_book, old_label, book, label, new_tail)
        if new_tail != tail:
            # 卷面/讲义印的「第 N 题」优先读 `meta.source_no`
            # （见 `render_tex.source_tag`）——只改 key 不改它，印出来还是旧题号。
            q.meta["source_no"] = new_tail
        if new_key != q.key:
            if any(x is not q and x.key == new_key for x in qs):
                raise HTTPException(409, "已经有这道题了：%s（出处不能重名，"
                                         "同一卷的多道题请用不同题号）" % new_key)
            renamed_from = q.key
            q.key = new_key
            # 改名是**有意动数据**：和别的"界面补录"一样盖时间戳，
            # 免得 `store.diff()` 把它报成"内容变化"
            q.meta["edited_at"] = time.strftime("%Y-%m-%d %H:%M")

    # 出处已处理完（可能改了 key/meta）；非出处字段与校验走同一份 helper。
    _apply_question_patch(q, body, before=before, content_before=content_before)

    # 改名的**跨题引用**也一起迁（`dup_of`/`also_in`/`merged_keys` 存的是
    # 别的题的 key）；必须在整库重写之前改，才会跟着落盘。
    if renamed_from:
        _migrate_meta_refs(qs, renamed_from, q.key)

    # ⚠️ 用 rewrite_all（**按 PER_VOLUME 重新分卷**），不要用 rewrite_volume(1,…)：
    # 后者会把所有卷的题都写进第 1 卷，而其它卷还在 → 整库重复。
    #
    # `based_on` 是乐观并发校验：读全库之后、写回之前若求解器/别的进程写了库，
    # 这次保存会被**拒绝**而不是把人家的写入覆盖掉。
    # ⚠️ **不要在这里 catch**：`@retry_on_concurrent` 靠捕获 `ConcurrentWrite`
    # 自动重跑一遍。在这里转成 HTTPException 的话装饰器永远接不到，
    # 「自动重试」形同虚设（复核时发现的）。
    _changed = [key, q.key] + ([renamed_from] if renamed_from else [])
    # 改名会改**别的题** meta 里的 dup_of/also_in/merged_keys；那些题可能在
    # 别的卷里。只写旧/新 key 会漏掉这些 meta 改动，必须整库写回。
    store.rewrite_all(qs, based_on=_sig,
                      changed_keys=(None if renamed_from
                                    else list(dict.fromkeys(_changed))))
    fulltext.apply(_changed, {q.key: q})
    _rm_apply(_changed, _sig, {q.key: q})

    # **记档**：标签是人工改的，要留痕（只记标签，不记正文）
    _audit_tag_change(q, before=before, fields=body)

    # 改名才有的三件事：存档里的引用跟着改、使用频次跟着迁、台账记一笔
    if renamed_from:
        moved = _migrate_key_refs(renamed_from, q.key)
        _migrate_usage(renamed_from, q.key)
        _audit_key_rename(renamed_from, q.key)
        log.info("改出处：%s → %s（引用已迁：%s）", renamed_from, q.key,
                 "、".join(moved) or "无")

    d = _brief(q)
    d["tex"] = question_to_tex(q)
    if renamed_from:
        # 前端拿它把选中项/列表里那条旧 key 换掉（否则右栏会停在旧 key 上）
        d["renamed_from"] = renamed_from
    return d


class BatchTagBody(BaseModel):
    r"""批量改标签：列表里勾 N 道，一次改完、**一次写盘**。

    以前只能一道一道开详情改，16 道就是 16 次“读全库 + 写 6 卷”。
    这里只放开标签字段（考点/难度/星级/年份/地区/书/卷名），
    正文（题干/选项/解析/答案）仍然只能走单题详情或重新录入——
    批量接口不该成为绕过规范审查的后门。
    """
    model_config = {"extra": "forbid"}     # 传 stem/solution 进来直接 422，不静默忽略
    keys: list[str]
    points: list[str] | None = None        # 按 point_mode 替换/追加/移除
    # replace = 整组替换（默认，兼容旧客户端）；add = 追加；remove = 移除
    point_mode: str = "replace"
    difficulty: str | None = None          # '' = 恢复按主考点派生
    stars: int | None = None               # 0 = 恢复按主考点派生
    year: int | str | None = None          # '' / 0 = 清空
    region: str | None = None              # '' = 清空
    book: str | None = None                # 改书名（和 label 一起给）
    label: str | None = None               # 改卷名
    reviewed: bool | None = None           # 标记/取消“已复核”


@router.post("/questions/batch")
@retry_on_concurrent
def batch_patch(body: BatchTagBody) -> dict:
    r"""批量改标签（**一次写回**）。语义与 `patch_question` 的单题标签一致。

    · 只改标签，不碰正文；改完仍要过 `conform`，不过就整批不写。
    · 考点默认整体替换；`point_mode=add/remove` 时按题追加/移除（保留原顺序）。
    · 改书名/卷名时按单题同一条规则重拼 key：只有 key 本来就是
      `书/卷名#号` 拼出来的才改，`高考真题汇编/2024/新高考I卷#1` 这种
      “多一层目录”的保持原 key，只改 meta（和单题一致）。
    · 改名撞车 → 整批 409，不写一半。
    """
    from amti import conform as _cf
    if not body.keys:
        raise HTTPException(400, "keys 不能为空")
    keys = list(dict.fromkeys(body.keys))
    if len(keys) > 500:
        raise HTTPException(400, "一次最多改 500 道（再多就分批）")
    fields = {k for k in ("points", "difficulty", "stars", "year", "region",
                          "book", "label", "reviewed")
              if getattr(body, k) is not None}
    if not fields:
        raise HTTPException(400, "没有给任何要改的字段")
    if body.point_mode not in ("replace", "add", "remove"):
        raise HTTPException(400, "point_mode 只能是 replace / add / remove")
    if body.point_mode != "replace" and body.points is None:
        raise HTTPException(400, "point_mode 需要和 points 一起给")

    if body.points is not None:
        unknown = [p for p in body.points if not knowledge.get(p)]
        if unknown:
            raise HTTPException(400, "不认识的考点：%s" % "、".join(unknown[:5]))
    if body.difficulty not in (None, "", "简单题", "中档题", "难题"):
        raise HTTPException(400, "难度只能是 简单题/中档题/难题/空")
    if body.stars is not None and not (0 <= body.stars <= 4):
        raise HTTPException(400, "星级只能是 0–4（0 = 按考点派生）")

    # 批量只改标签（不动 book/label）时 key 不变，可以只读/只写命中的卷。
    fast = body.book is None and body.label is None
    if fast:
        by, vols, chunks, sig = store.read_many_map(keys)
        qs = None
    else:
        qs, sig = store.load_for_update()
        by = {q.key: q for q in qs}
    missing = [k for k in keys if k not in by]
    if missing:
        raise HTTPException(404, "有 %d 道题找不到：%s"
                            % (len(missing), "、".join(missing[:3])))
    before_hashes = {k: by[k].content_hash() for k in keys}

    stamp = time.strftime("%Y-%m-%d %H:%M")
    touched = []
    renamed: list[tuple[str, str]] = []
    taken = set(by)                     # 本批改名后的 key 也要占位，避免批内撞车
    for k in keys:
        q = by[k]
        if body.points is not None:
            pts = list(dict.fromkeys(body.points))
            if body.point_mode == "add":
                q.points = list(dict.fromkeys([*(q.points or []), *pts]))
            elif body.point_mode == "remove":
                drop = set(pts)
                q.points = [p for p in (q.points or []) if p not in drop]
            else:
                q.points = pts
            # 和单题 `patch_question` 同一口径：人工批量改过考点，来源就记 human。
            # 不记的话详情仍显示「AI标注」，体检页的“考点来源”统计也会失真。
            q.meta["point_source"] = "human"
        if body.difficulty is not None:
            if body.difficulty:
                q.meta["difficulty"] = body.difficulty
            else:
                q.meta.pop("difficulty", None)
        if body.stars is not None:
            if body.stars:
                q.meta["stars"] = body.stars
            else:
                q.meta.pop("stars", None)
        if body.year is not None:
            ys = str(body.year).strip()
            if ys in ("", "0"):
                q.meta.pop("year", None)
            else:
                try:
                    q.meta["year"] = int(ys)
                except ValueError:
                    raise HTTPException(400, "年份要是整数：%r" % (body.year,))
        if body.region is not None:
            if body.region.strip():
                q.meta["region"] = body.region.strip()
            else:
                q.meta.pop("region", None)
        if body.reviewed is not None:
            review_mod.apply_decision(
                q, "approved" if body.reviewed else "pending",
                note="批量快速通过（未逐题审阅）" if body.reviewed else "",
                reviewer="批量")

        if body.book is not None or body.label is not None:
            old_book = str(q.meta.get("book") or "")
            old_label = str(q.meta.get("source_label") or "")
            new_book = (body.book if body.book is not None else old_book).strip()
            new_label = (body.label if body.label is not None else old_label).strip()
            if not new_book or not new_label:
                raise HTTPException(400, "书 / 卷名不能为空：%s" % k)
            q.meta["book"] = new_book
            q.meta["source_label"] = new_label
            # 和 patch_question 同一条判据：拿**改名前的**书/卷名比。
            # 别再抄一份比较逻辑——抄出来的那份忘了 strip，就会和
            # /questions/source/batch 的预览结果对不上。
            new_key = _source_key(k, old_book, old_label, new_book, new_label)
            if new_key != q.key:
                if new_key in taken and new_key != k:
                    raise HTTPException(409, "改名撞车：%s" % new_key)
                _migrate_meta_refs(qs, k, new_key)
                taken.discard(k)
                taken.add(new_key)
                q.key = new_key
                renamed.append((k, new_key))

        q.meta["edited_at"] = stamp
        touched.append(q)

    viol = _cf.run(touched)
    if viol:
        v = viol[0]
        raise HTTPException(400, "改完不规范，没有保存：%s（%s/%s）"
                            % (v["why"], v["check"], v["field"]))

    all_changed = list(dict.fromkeys(
        [k for k in keys] + [q.key for q in touched]))
    # 批量改名会改别的题 meta；跨卷引用必须整库写回。
    if fast:
        rep = store.write_many(touched, volumes=vols, chunks=chunks,
                               expect_hashes=before_hashes, expect_sig=sig)
    else:
        rep = store.rewrite_all(qs, based_on=sig,
                                changed_keys=(None if renamed else all_changed))
    fulltext.apply(all_changed, {x.key: x for x in touched})
    _rm_apply(all_changed, sig, {x.key: x for x in touched})

    # 改名后的跨文件引用迁移（存档/讲义/台账）+ 使用频次；写成功之后才做
    for old, new in renamed:
        _migrate_key_refs(old, new)
        _migrate_usage(old, new)
        _audit_key_rename(old, new)

    from amti.audit import CHANGE_DIR
    try:
        CHANGE_DIR.mkdir(parents=True, exist_ok=True)
        f = CHANGE_DIR / ("%s_批量改标签.md" % time.strftime("%Y%m%d_%H%M%S"))
        rmap = dict(renamed)
        lines = ["- `%s`%s" % (k, (" → `%s`" % rmap[k]) if k in rmap else "")
                 for k in keys]
        f.write_text(
            "# 批量改标签\n\n- 时间：%s\n- 题目：%d 道\n- 字段：%s\n"
            "- 改名：%d 道\n\n%s\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), len(touched),
               "、".join(sorted(fields)), len(renamed), "\n".join(lines)),
            encoding="utf-8")
    except Exception:
        log.warning("批量改标签记档失败（修改已生效）", exc_info=True)

    # **改名映射必须回给界面**：批量改书名/卷名会换 key，而界面里
    # 「当前卷子」只存题对象、不跟库自动同步（`App.paperMap`）。
    # 只回一个 `renamed` 数量的话，卷子里那些题仍拿着旧 key，导出时才
    # 报“找不到题”——单题改名有 `remapKey`，批量这里不能漏。
    # 附上新的出处字段，前端不用再逐题 `GET` 就能把卷子里的显示改对。
    renames = [{
        "old": old,
        "new": new,
        "book": str(by[old].meta.get("book") or ""),
        "label": str(by[old].meta.get("source_label") or ""),
        "year": by[old].meta.get("year") or "",
    } for old, new in renamed]

    return {"ok": True, "changed": len(touched), "renamed": len(renamed),
            "renames": renames,
            "volumes": rep.get("volumes"), "partial": rep.get("partial", False)}


# ── 批量改出处（按「来源 + 出处」在全库搜索）────────────────────────
#
# 用户的原话：「在修改出处的时候增加一个批量改的按钮，支持搜索全部符合的
# 题目，统一把这个出处改正」。典型场景：一份卷子录进来时卷名打错/年份错，
# 二十多道题都带着同一个错出处；一道一道改既慢又容易漏。
#
# 和 `/questions/batch`（按勾选的 key 改）的分工：
#   · 那边要先把题勾出来、一次最多 500 道、题号也能统一改；
#   · 这里由**后端按出处搜索**，题号（`#` 后面那截）各自保留——
#     同一份卷子的题不会因为批量改卷名而互相撞车。
#
# 预览（`dry_run=True`，默认）只读元数据，不写库；真正写回和单题改出处
# 走同一套规则：key 本来就由 `书/卷名#号` 拼出来的才改名并迁移引用，
# 历史结构的 key 只改标签；有一条不合规/撞车就整批不写。

