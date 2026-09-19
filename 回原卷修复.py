#!/usr/bin/env python3
r"""回原卷修复 —— 把「读原卷得到的 JSON」写回题库的执行器。

背景见 `设计/录题工作交接-交给大模型.md`。存量里有 721 道题**缺数据**
（选项整片丢、答案空、填空没空位），处置方案是**回原卷重读**：
能修的全修，修不了的进回收站。

分工（**这一步不含任何模型**）：

    prep   <卷名>   切页图 + 生成任务卡（要修哪几号、库里现在长什么样）
    check  <卷名>   机械校验读出来的 JSON（第八节 12 条 + record2 闸门）
    apply  <卷名>   回写题库（默认干跑，`--yes` 才落盘）
    prompt <卷名>   打印这一场的读图提示词（提示词只有一个出处）
    list            待办场次（按题数降序）
    report          进度 + 图/表题登记表

**只动待修清单里的题**，其余一个字不碰；JSON 给不出的字段保留库里原值。

    python3 回原卷修复.py list
    python3 回原卷修复.py prep   2026届湖北省十一校高三上学期12月质量检测
    python3 回原卷修复.py check  2026届湖北省十一校高三上学期12月质量检测
    python3 回原卷修复.py apply  2026届湖北省十一校高三上学期12月质量检测 --yes
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from amti import pagegeom as G
from amti import record2 as R2
from amti import store, trash

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "数据" / "录题"
FIX = WORK / "_修复"
LOG = ROOT / "变更记录" / "回原卷修复.jsonl"

ANSWER_WORD = re.compile(r"答案|解析|全解全析|参考答案|评分标准|教师版|DA")
SHEET_WORD = re.compile(r"答题卡|答题纸")
# 名字**结尾**是角色词的，按结尾算——"…数学试题及答案 高三数学—答案" 这种
# 一套三件的命名，中间那个"及答案"是系列名，不是"这份文件里含答案"。
TAIL_ANSWER = re.compile(r"(答案|解析|全解全析|参考答案|评分标准|细则|DA)\s*$")
TAIL_PAPER = re.compile(r"(试题|试卷|原卷|卷)\s*$")
# 「试题+答案」合一（名字以"试题+答案""（含答案）"收尾）：按**试卷**算，
# 答案就在同几页里。判成答案卷会让试卷侧空掉。
COMBINED = re.compile(r"(试题|试卷|卷)\s*[+＋]\s*(答案|解析|全解全析)$"
                      r"|(含|附)\s*答案\s*[)）]?$")
PREFIX = re.compile(r"^\s*\d{1,4}[\.\-、_\s]+")


def role_of_ws(name: str) -> str:
    """工作区/文件名 → `试卷` / `答案`。先判合一，再判结尾，最后判含不含。"""
    n = (name or "").strip()
    if COMBINED.search(n):
        return "试卷"
    if TAIL_ANSWER.search(n):
        return "答案"
    if TAIL_PAPER.search(n):
        return "试卷"
    return "答案" if ANSWER_WORD.search(n) else "试卷"


def safe(label: str) -> str:
    """卷名 → 目录名（保留中文，别的都换成 _，末尾挂 8 位指纹防重名）。"""
    keep = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", label or "").strip("_")[:48]
    return "%s_%s" % (keep, hashlib.sha1(label.encode()).hexdigest()[:8])


def key_of(label: str, no: int) -> str:
    return "模拟题/%s#%d" % (label, no)


# ── 待修清单：真相在库里，不在旧 JSON ────────────────────────────────
def pending_now(*, refresh: bool = False) -> dict[str, list[dict]]:
    r"""按 `record2.retype_by_no` 的判据从**当前题库**算出还缺数据的题。

    ⚠️ 不读 `数据/录题/待修-题型.json`——那是 22:29 的快照，已经修掉的
    14 道还躺在里面。清单必须每次从库里重算，否则会把修好的题再盖一次。
    """
    f = FIX / "pending.json"
    if refresh or not f.exists():
        pend = R2.retype_by_no(store.load_all())["pending"]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(pend, ensure_ascii=False, indent=1), encoding="utf-8")
    out: dict[str, list[dict]] = defaultdict(list)
    for p in json.loads(f.read_text(encoding="utf-8")):
        label, no = p["key"].split("#")[0].replace("模拟题/", ""), int(p["key"].split("#")[-1])
        out[label].append({"no": no, "原因": p["原因"], "key": p["key"]})
    return {k: sorted(v, key=lambda x: x["no"]) for k, v in out.items()}


# ── 原卷定位 ────────────────────────────────────────────────────────
def workspaces() -> list[Path]:
    return [p for p in WORK.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))]


_ROLE = re.compile(r"数学|试题|试卷|参考答案|答案与解析|答案|全解全析|解析|详解|及"
                   r"|及评分细则|评分标准|标答|教师版|学生版|图片版|word版"
                   r"|副本|含|补充|（|）|\(|\)|\s|[【】\[\]]")


def canon(name: str) -> str:
    r"""工作区/卷名 → **去掉角色词**的"同一场"键。

    `十一校数学试卷` 与 `十一校数学答案` 去掉角色词后都是 `十一校`，
    于是能成对配上；而 `长郡中学月考一` 与 `月考三` 的差别（序号）**保留**，
    不会被误并。清单 `v2批跑清单.json` 里有 20 多条是按"相似度 0.7x"猜的
    （德州开学考配成了济南摸底考），所以配对**不信清单，信这个键**。
    """
    s = PREFIX.sub("", name or "")
    s = re.sub(r"^\d+", "", s)
    s = _ROLE.sub("", s)
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]", "", s)


def locate(label: str) -> dict:
    r"""卷名 → `{试卷: [目录…], 答案: [目录…]}`，按 `canon()` 找同一场的工作区。

    先要**完全同键**的；一个都没有才退而求其次取公共前缀最长的一批
    （像 `十一校` 对上 `2026届湖北省十一校…` 这种缩写）。
    """
    want = canon(label)
    groups: dict[str, list[Path]] = defaultdict(list)
    for d in workspaces():
        if SHEET_WORD.search(d.name):
            continue
        groups[canon(d.name)].append(d)
    keys = [k for k in groups if k and want and (k == want or k in want or want in k)]
    if not keys:
        pref = [k for k in groups if k and want and _common(k, want) >= 3]
        keys = sorted(pref, key=lambda k: -_common(k, want))[:1]
    hit = {"试卷": [], "答案": []}
    for k in keys:
        for d in groups[k]:
            hit[role_of_ws(d.name)].append(d)
    return {k: sorted(v) for k, v in hit.items()}


def _common(a: str, b: str) -> int:
    """两段键的最长公共前缀长度。"""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def _source_of(label: str) -> Path | None:
    """工作区里没有页图时，`来源.json` 里登记的原卷文件（人工核对过名字）。"""
    f = FIX / "来源.json"
    if not f.exists():
        return None
    hit = (json.loads(f.read_text(encoding="utf-8")) or {}).get(label)
    p = Path(hit["file"]) if hit else None
    return p if p and p.exists() else None


def render_docx(docx: Path, out_dir: Path) -> list[Path]:
    r""".docx 也是图片壳子：解 zip 取 `word/media/*`，按文件名顺序就是页序。"""
    import zipfile

    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx) as z:
        names = sorted(n for n in z.namelist()
                       if n.startswith("word/media/")
                       and n.lower().endswith((".png", ".jpg", ".jpeg")))
        out = []
        for i, n in enumerate(names, 1):
            dst = out_dir / ("p%03d%s" % (i, Path(n).suffix))
            dst.write_bytes(z.read(n))
            out.append(dst)
    return out


def render_pdf(pdf: Path, out_dir: Path, dpi: int = 200) -> list[Path]:
    r"""PDF → 整页图。**一定渲染整页，不抽内嵌图**（有些 PDF 的 xref 是坏的，
    抽出来的图会张冠李戴，同一张图对应好几页）。"""
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    with fitz.open(str(pdf)) as doc:
        for i, page in enumerate(doc, 1):
            dst = out_dir / ("p%03d.png" % i)
            page.get_pixmap(dpi=dpi).save(str(dst))
            out.append(dst)
    return out


def render_from_source(label: str, d: Path) -> tuple[list[Path], str]:
    r"""原卷（PDF/Word）→ `(单页图, 出处)`。

    **不去猜哪几页是答案**——这一批的原始文件常常是"试题+答案"合一，
    按文件名判角色会把整份判成答案卷。页图统一交给读图的人自己分。
    """
    src = _source_of(label)
    if not src:
        return [], ""
    raw = (render_docx(src, d / "src") if src.suffix.lower() in (".docx", ".doc")
           else render_pdf(src, d / "src"))
    pages = [q for p in raw for q in G.split_spread(p, d / "pages_src")]
    return pages, str(src)


def half_pages(ws: Path, out_dir: Path) -> list[Path]:
    r"""工作区 → 单页图（横版双页按 L0 几何切开，纯代码不碰模型）。"""
    done = sorted(p for p in (ws / "v2" / "pages").glob("p???_[LR].png"))
    if done:
        return done
    src = sorted((ws / "pages").glob("p???.png"))
    if not src:
        return []
    out: list[Path] = []
    for p in src:
        out += [q for q in G.split_spread(p, out_dir) if q.exists()]
    return out


# ── prep ────────────────────────────────────────────────────────────
def prep(label: str) -> dict:
    items = pending_now().get(label) or []
    if not items:
        raise SystemExit("这一场没有待修的题（或卷名不对）：%s" % label)
    loc = locate(label)
    d = FIX / safe(label)
    d.mkdir(parents=True, exist_ok=True)
    qs = {q.meta.get("source_no"): q for q in store.load_cached()
          if q.meta.get("source_label") == label}
    paper, answer = [], []
    for ws in loc["试卷"]:
        paper += half_pages(ws, d / "pages")
    for ws in loc["答案"]:
        answer += half_pages(ws, d / "pages_ans")
    src_pages, src_from = ([], "")
    if not paper and not answer:
        src_pages, src_from = render_from_source(label, d)
    card = {
        "label": label,
        "待修": [{"no": it["no"], "原因": it["原因"],
                 "库里": _brief(qs.get(it["no"]))} for it in items],
        "页图": {"试卷": [str(p) for p in paper], "答案": [str(p) for p in answer],
                 "原卷": [str(p) for p in src_pages]},
        "有答案卷": bool(answer),
        "答案同册": bool(not answer and any(COMBINED.search(ws.name)
                                          for ws in loc["试卷"])),
        "出处": src_from or {k: [str(p) for p in v] for k, v in loc.items()},
    }
    (d / "task.json").write_text(json.dumps(card, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    print("任务卡 → %s" % (d / "task.json"))
    print("  待修 %d 道；页图：试卷 %d、答案 %d、原卷渲染 %d"
          % (len(card["待修"]), len(paper), len(answer), len(src_pages)))
    if not (paper or answer or src_pages):
        print("  ✗ 没有任何页图——这一场找不到原卷，只能舍弃")
    return card


def _brief(q) -> dict:
    if q is None:
        return {}
    return {"type": q.type, "stem": (q.stem or "")[:120],
            "options": {o.label: o.text[:60] for o in q.options},
            "answer": q.answer or "", "solution": (q.solution or "")[:120],
            "有解析": bool((q.solution or "").strip() and q.solution.strip() != "解析无")}


# ── check ───────────────────────────────────────────────────────────
FURNITURE_STEM = re.compile(r"满分|第\s*\d+\s*页|共\s*\d+\s*页|答题卡|数学试题|QQ|微信|群")
SECTION_HEAD = re.compile(r"^\s*[一二三四五六]\s*[、.．]")


def _loose(s: str) -> str:
    r"""只留汉字和字母数字——**quote 跟本地 OCR 对账用**。

    OCR 把「，」认成「,」、「”」干脆丢掉，按原样比会满屏假警报。
    """
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]", "", s or "")


def _ocr_corpus(label: str) -> str:
    """这一场自己的本地 OCR 页文本——**只用来抽查 quote 是不是真在卷面上**。

    只搜本场：全库的 txt 有几百场，跨场撞上一句话就把假 quote 放过了。
    """
    loc = locate(label)
    txt = []
    for ws in loc["试卷"] + loc["答案"]:
        for f in sorted((ws / "v2" / "txt").glob("*.txt")):
            txt.append(f.read_text(encoding="utf-8", errors="ignore"))
    return _loose("\n".join(txt))


def page_sig(label: str) -> str:
    """这一场**当前**用的页图清单指纹。

    check 和 apply 各算一次，对不上就说明中间原卷定位变了（改过 `locate()`、
    重跑过 prep），model.json 就是照着旧页图写的——**不许入库**。
    """
    c = json.loads((FIX / safe(label) / "task.json").read_text(encoding="utf-8"))
    blob = "\n".join(str(x) for v in c["页图"].values() for x in v)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


def check(label: str, *, corpus: str | None = None) -> dict:
    d = FIX / safe(label)
    book = json.loads((d / "model.json").read_text(encoding="utf-8"))
    want = {it["no"] for it in pending_now().get(label) or []}
    card = json.loads((d / "task.json").read_text(encoding="utf-8"))
    have = {it["no"]: (it.get("库里") or {}) for it in card["待修"]}
    errs, warns = [], []
    if (book.get("错卷") or "").strip():
        errs.append("读图方判定**页图不是这一场**：%s —— 要重新定位原卷"
                    % book["错卷"])
    title = (book.get("卷面标题") or "").strip()
    loc = locate(label)
    exact = any(canon(label) == canon(ws.name)
                for ws in loc["试卷"] + loc["答案"])
    if not exact and not title:
        # 名字不是逐字对上的（清单里有二十来场是"相似度 0.7x"猜的），
        # 必须拿卷头那行大字再核一遍，否则会拿 A 场的页去修 B 场的题。
        errs.append("页图出处与卷名不是完全同名，必须写 卷面标题（第 1 页卷头大字）核对")
    if (book.get("答案出处") or "").strip():
        warns.append("答案出自**自己找到的**卷：%s —— 第一页核对过卷名了吗？"
                     % book["答案出处"])
    elif not card.get("有答案卷") and not card.get("答案同册"):
        warns.append("这一场没登记答案卷：所有答案都必须有出处，否则留空并进 notfound")
    if (book.get("label") or "").strip() != label:
        warns.append("JSON 的 label 与任务卡不一致：%r" % book.get("label"))
    recs = book.get("questions") or []
    seen = set()
    for r in recs:
        no = r.get("no")
        tag = "#%s" % no
        if not isinstance(no, int):
            errs.append("%s 题号不是整数" % tag)
            continue
        if no in seen:
            errs.append("%s 题号重复" % tag)
        seen.add(no)
        if no not in want:
            errs.append("%s 不在待修清单里（只许交清单上的题）" % tag)
            continue
        errs += ["%s %s" % (tag, m) for m in _check_one(r, have.get(no) or {})]
    got = {r["no"] for r in recs if isinstance(r.get("no"), int)}
    given = {x.get("no") for x in book.get("notfound") or []}
    for no in sorted(want - got):
        if no not in given:
            errs.append("#%d 既没修也没声明找不到（要放进 notfound 并写原因）" % no)
    for x in book.get("notfound") or []:
        if not (x.get("note") or "").strip():
            warns.append("#%s notfound 没写原因" % x.get("no"))
    if corpus is None:
        corpus = _ocr_corpus(label)
    if corpus:
        for r in recs:
            q = _loose(r.get("quote") or "")
            if q and q not in corpus:
                warns.append("#%s quote 在本地 OCR 文本里找不到"
                             "（可能只是 OCR 认错，人工看一眼）" % r.get("no"))
    out = {"label": label, "ok": not errs, "errors": errs, "warnings": warns,
           "卷面标题": title, "页图指纹": page_sig(label),
           "题数": len(recs), "待修": sorted(want)}
    (d / "check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    print("%s  交来 %d 道 / 待修 %d 道  卷面标题：%s"
          % ("✓ 通过" if out["ok"] else "✗ 不合格", len(recs), len(want),
             title or "（没写）"))
    for m in errs:
        print("   ✗ %s" % m)
    for m in warns:
        print("   · %s" % m)
    return out


def _check_one(r: dict, old: dict) -> list[str]:
    r"""单题的机械校验（第八节 12 条里能自动化的部分 + record2 闸门）。

    `old` 是库里这一题现在的样子：**解析可以留空**——留空表示"沿用库里那份"
    （回原卷只补选项/答案，把几百字解析重抄一遍只会多制造错字）。
    """
    no, qt = r["no"], r.get("type")
    out: list[str] = []
    want_qt = R2.TYPE_EN.get(R2.BY_NO.get(no, ""))
    if qt != want_qt:
        out.append("题型 %r 应为 %r（题型按题号定，不许按选项个数猜）" % (qt, want_qt))
        return out
    stem, ans = r.get("stem") or "", (r.get("answer") or "").strip()
    sol = r.get("solution") or ""
    opts = r.get("options") or {}
    if qt in ("single_choice", "multi_choice"):
        if set(opts) != set("ABCD"):
            out.append("选项标签 %s（必须 A/B/C/D 四个）" % sorted(opts))
        if not ans and not old.get("answer"):
            out.append("选择题没有答案（库里也没有）")
        if ans and not re.fullmatch(r"[A-D]{1,4}", ans):
            out.append("答案 %r 不是字母" % ans[:20])
    elif qt == "fill_in_blank":
        if not ans and not old.get("answer"):
            out.append("填空题答案为空（库里也没有）")
    elif qt == "detailed_answer" and ans:
        out.append("解答题不该有短答案")
    if not stem.strip():
        out.append("题干为空")
    if not sol.strip() and not old.get("solution"):
        out.append("解析为空（库里也没有；确实没有解析写「解析无」）")
    if len(ans) > 40:
        out.append("客观题答案 %d 字（像整段解析）" % len(ans))
    if FURNITURE_STEM.search(stem):
        out.append("题干里混着分值/页脚/水印")
    if "□" in stem + sol + "".join(str(v) for v in opts.values()):
        out.append("留着卷面的方框 □ 没处理（能确定就补成 LaTeX 并写 note，不能确定就 notfound）")
    if SECTION_HEAD.search(stem):
        out.append("题干里混着小节标题")
    if r.get("figure") or r.get("table"):
        out.append("带图/带表的题不许进 questions，要放 skipped")
    q = R2.norm(r.get("quote") or "")
    if not (10 <= len(q) <= 60):
        out.append("quote %d 字（要 10–25 字，归一化后 10–60）" % len(q))
    elif q and q not in R2.norm(stem):
        out.append("quote 对不上题干（说明改写了原文）")
    out += R2.gate(qt, stem, opts, ans, sol)
    return out


# ── apply ───────────────────────────────────────────────────────────
def _load_plan(label: str) -> dict:
    """check 没过、或页图清单在 check 之后变过，就不许入库。"""
    d = FIX / safe(label)
    chk = json.loads((d / "check.json").read_text(encoding="utf-8"))
    if not chk.get("ok"):
        raise SystemExit("check 没过：%s ← %s"
                         % (label, "; ".join(chk["errors"][:3])))
    if chk.get("页图指纹") != page_sig(label):
        raise SystemExit("页图清单在 check 之后变过：%s ——JSON 是照旧页图写的，重读再入库"
                         % label)
    return json.loads((d / "model.json").read_text(encoding="utf-8"))


def apply_into(qs: list, label: str, book: dict, *,
               allow_drop: bool = False, stamp: str = "") -> dict:
    r"""把一场的 JSON 落到 `qs`（**只改内存，不写盘**）。规则（交接文档 11.2）：

    * **只动待修清单里的题**
    * JSON 给得出的字段 → 覆盖；给不出的（答案/解析为空）→ 保留库里原值
    * `notfound` 的 → 要另加 `--drop` 才移进回收站：读图方判"找不到"常常是
      **原卷配错了**（齐鲁名校那场卷面是第三次检测、册内答案却是第二次的），
      先让人看一眼再删。
    """
    recs = {r["no"]: r for r in book.get("questions") or []}
    drop = {int(x["no"]) for x in book.get("notfound") or []}
    want = {it["no"] for it in pending_now().get(label) or []}
    idx = {q.meta.get("source_no"): i for i, q in enumerate(qs)
           if q.meta.get("source_label") == label}
    fixed, dropped, held = [], [], []
    untouched = sorted(want - set(recs) - drop)

    for no in sorted(want & set(recs)):
        if no not in idx:
            untouched.append(no)
            continue
        old = qs[idx[no]]
        new = R2.rec_to_question({"题号": no, "题型": recs[no]["type"],
                                  "题干": recs[no]["stem"],
                                  "选项": recs[no].get("options") or {},
                                  "答案": recs[no].get("answer") or "",
                                  "解析": recs[no].get("solution") or ""}, label)
        old.type, old.stem, old.options = new.type, new.stem, new.options
        old.answer = new.answer or old.answer
        sol = new.solution or old.solution
        # 库里本来有解析、这次只抄出个"解析无" → 不许抹掉已有解析
        # （任务卡要求"有解析"的题 solution 留空，这里兜住没照做的）。
        if sol.strip() == "解析无" and (old.solution or "").strip() not in ("", "解析无"):
            sol = old.solution
        old.solution = sol
        old.meta["migrated_at"], old.meta["migrated_by"] = stamp, "回原卷重扫修复"
        fixed.append(no)
    for no in sorted(want & drop):
        if no in idx:
            (dropped if allow_drop else held).append(qs[idx[no]].key)

    return {"label": label, "when": stamp,
            "修补": [{"题号": n} for n in fixed],
            "舍弃": dropped, "待确认舍弃": held, "未处理": untouched}


def ready_labels() -> list:
    """check 通过、还没入库的场次。"""
    done = {json.loads(l)["label"]
            for l in LOG.read_text(encoding="utf-8").splitlines()} if LOG.exists() else set()
    out = []
    for label in pending_now():
        d = FIX / safe(label)
        if (d / ".applied").exists() or label in done:
            continue
        if (d / "check.json").exists():
            try:
                _load_plan(label)
            except SystemExit as e:
                print("跳过 %s：%s" % (label, e))
                continue
            out.append(label)
    return out


def apply_batch(labels: list, *, yes: bool = False,
                allow_drop: bool = False) -> list:
    r"""**一批一次读库、一次写库**——把并发窗口从"每场一次"压到"每批一次"。

    另一个会话也在改题库（逐题校对），一场一次整体写回的话，
    中间那一两秒里它写的题会被我盖掉。
    """
    stamp = time.strftime("%Y-%m-%d %H:%M")
    qs = store.load_all()
    reps, all_drop = [], []
    for label in labels:
        rep = apply_into(qs, label, _load_plan(label),
                         allow_drop=allow_drop, stamp=stamp)
        all_drop += rep["舍弃"]
        reps.append(rep)
        print("  %-52s 修补 %2d 待确认 %d 未处理 %d"
              % (label[:52], len(rep["修补"]), len(rep["待确认舍弃"]),
                 len(rep["未处理"])))
    n = sum(len(r["修补"]) for r in reps)
    if not yes:
        print("干跑：%d 场 / %d 道（加 --yes 才落盘）" % (len(reps), n))
        return reps
    store.rewrite_all(qs)
    if all_drop:
        r = trash.delete(all_drop, reason="无", password="0808")
        if not r.get("ok"):
            raise SystemExit("回收站写入失败（题库已改，舍弃未执行）：%s" % r.get("error"))
    with LOG.open("a", encoding="utf-8") as f:
        for rep in reps:
            f.write(json.dumps(rep, ensure_ascii=False) + "\n")
            (FIX / safe(rep["label"]) / ".applied").write_text(stamp, encoding="utf-8")
    print("已落盘：%d 场 / %d 道" % (len(reps), n))
    return reps


def apply(label: str, *, yes: bool = False, allow_drop: bool = False) -> dict:
    """单场入库（批量请用 `apply-batch`）。"""
    return apply_batch([label], yes=yes, allow_drop=allow_drop)[0]


# ── prompt ─────────────────────────────────────────────────────────
PROMPT = """\
你是 AmTiKu 题库的录题员。这一场是《{label}》，**扫描版**高中数学试卷。
库里这一场有 {n} 道题缺数据，你只负责把它们**照原卷抄对**：{nos}

页图（按阅读顺序；横版双页已切成单页）：
【试卷】
{paper}
【答案】
{answer}{source}{noans}

库里这几道题现在缺什么（**只补这些，别改编号以外的题**）：
{current}

规矩（违反任何一条，这一场就算废）：
0. **先核对卷面**：看【试卷】第 1 页卷头那行大字，原样写进 JSON 顶层
   `"卷面标题":"…"`. 如果它和卷名明显不是同一场（城市、次数、月份对不上），
   **立刻停手**：questions 留空，顶层再写 `"错卷":"页面上实际看到的标题"` 并在报告里说明。
   （清单里有二十来场原卷是"相似度 0.7x"猜的，德州开学考配成了济南摸底考——**别信路径，信页面**。）
1. 题型按题号定：1-8 单选 single_choice、9-11 多选 multi_choice、
   12-14 填空 fill_in_blank、15-19 解答 detailed_answer。**不许按选项个数猜**。
2. **一个字都不许改**：每个字段都要能在原图上逐字找到；看不清写 `\\text{{【?】}}`，
   不许猜、不许"顺手改正"、不许解题、不许补条件。
   卷面把符号印成**方框**（□，原 PDF 缺字）时：能从上下文确定是哪个命令
   （如 `\\triangle`、`\\mid`）就照上下文写，并在这一题加 `"note":"卷面印成方框，按上下文补为 \\triangle"`；
   确定不了就别猜，写 `\\text{{【?】}}` 或整题进 notfound。
3. 选择题必须 A/B/C/D 四个选项（标签印坏了也按顺序补成 A）；答案写字母；
   填空题答案写那个值本身（≤40 字）；解答题 answer 写 ""。
4. 答案去【答案】页找；**绝不许拿别的题的答案顶上**。解析里有"故选 CD"而答案栏空 → 把 CD 填进 answer。
   答案卷没登记时按下面【答案】里的说法自己找，**但必须先核对卷名**。
   `solution`：**任务卡标了「有解析」的题写 ""**（表示沿用库里那份，不要重抄）；
   库里也没有解析的，才照答案页抄，实在没有写 "解析无"。
5. 不录：分值「（本小题满分17分）」、页眉页脚「第 3 页 共 8 页」、考试说明、
   答题卡提示、小节标题「一、选择题：本题共8小题」、水印（QQ 群号）。
6. 跨页的题（题在页尾、选项在下页开头）**必须合并**，不许丢选项。
7. LaTeX：行内公式 `$…$`；数学里的中文包 `\\text{{…}}`；虚数单位 `$\\mathrm{{i}}$`；
   禁止 HTML 实体（`&lt;`）、字面量 `\\n`、`^'`、`\\{{` 不配平、`$` 不成对。
8. 题干里**真有图或真表格**的题：不进 questions，进 `skipped`，
   `kind` 写 "figure"/"table"，`note` 说明图/表在页面什么位置、画的是什么。
   只是文字里提到"图象/如图"而版面上没画 → 照常录入。
9. 原卷上确实找不到、或残缺到没法修的题号：放进 `notfound`，
   `note` 写清为什么（不许默默漏掉，也不许硬凑）。

只输出 JSON，不要代码块围栏、不要解释。**完整内容写到这个文件**：
{out}

JSON 结构：
{{"label":"{label}","book":"模拟题","year":{year},"卷面标题":"卷头那行大字",
 "questions":[{{"no":9,"type":"multi_choice","stem":"…","options":{{"A":"…","B":"…","C":"…","D":"…"}},
   "answer":"CD","solution":"","figure":false,"table":false,"pages":[2],"quote":"逐字摘 10-25 字（尽量摘不含公式的那段）"}}],
 "skipped":[{{"no":18,"kind":"figure","pages":[4],"quote":"…","note":"…"}}],
 "notfound":[{{"no":13,"kind":"fill_in_blank","quote":"…","note":"原卷此处被装订线遮住，看不清"}}]}}

交之前自查：题号齐、题型对、选择题四选项、客观题答案短、
quote 逐字对得上、题干没有分值/页脚/小节标题、图表题都在 skipped 里、
`$` 成对。任何一条不过，宁可放进 skipped/notfound，也不交半成品。
"""


def prompt(label: str) -> str:
    card = json.loads((FIX / safe(label) / "task.json").read_text(encoding="utf-8"))
    nos = "、".join("#%d（%s）" % (x["no"], x["原因"]) for x in card["待修"])
    y = re.search(r"(20\d\d)", label)

    def fmt(ps):
        return "\n".join("第 %d 页：%s" % (i, p) for i, p in enumerate(ps, 1)) or "（无）"

    def cur(x):
        o = x["库里"] or {}
        return ("#%d 缺：%s｜库里题干开头：%r｜选项 %d 个｜答案 %r｜%s"
                % (x["no"], x["原因"], (o.get("stem") or "")[:40],
                   len(o.get("options") or {}), o.get("answer") or "",
                   "有解析" if o.get("有解析") else "无解析"))

    src = card["页图"].get("原卷") or []
    source = ("\n【原卷】这一场没有分开扫的试卷/答案，下面是同一份原卷渲染出的页"
              "（试题和答案都在这几页里，自己按页码分）\n" + fmt(src)) if src else ""
    cd = card["页图"].get("答案") or []
    if cd:
        noans = ""
    elif card.get("答案同册"):
        noans = ("\n（这一份是**试题+答案合一**：答案就在上面【试卷】那几页的后半，"
                 "往后翻，别处不用找。）")
    else:
        noans = ("\n（这一场**没有登记过答案卷**。）要找答案，先 "
                 "`ls 数据/录题 | grep 关键词`，或去原卷所在目录看有没有配套的答案文件；"
                 "**找到后必须读它第一页核对卷名**，对不上就不许用"
                 "（答案留空、题号进 notfound）。确实用了，"
                 "就在 JSON 顶层加一项 `\"答案出处\":\"<目录名或文件名>\"`。")
    return PROMPT.format(label=label, n=len(card["待修"]), nos=nos,
                         current="\n".join(cur(x) for x in card["待修"]),
                         year=y.group(1) if y else 2026, source=source, noans=noans,
                         out=str(FIX / safe(label) / "model.json"),
                         paper=fmt(card["页图"]["试卷"]), answer=fmt(cd))


# ── list / report ──────────────────────────────────────────────────
def has_pages(ws: Path) -> bool:
    return bool(list((ws / "v2" / "pages").glob("p???_[LR].png"))
                or list((ws / "pages").glob("p???.png")))


def cmd_list(limit: int = 0) -> None:
    pend = pending_now()
    rows = sorted(pend.items(), key=lambda kv: -len(kv[1]))
    print("合计 %d 场 / %d 道" % (len(rows), sum(len(v) for v in pend.values())))
    for label, items in (rows[:limit] if limit else rows):
        loc = locate(label)
        print("%-58s %2d 道  %s" % (label[:58], len(items),
                                    "有页图" if any(map(has_pages, loc["试卷"] + loc["答案"]))
                                    else "✗ 无页图"))


def cmd_todo(limit: int = 0) -> None:
    r"""**从库里重算**还剩哪些场真缺数据（修好的会自动从单子上消失）。

    不用 FIX/pending.json 的旧快照，也不用 .applied 标记——
    判"修没修好"的唯一标准是库里现在这道题完不完整。
    """
    pend = pending_now(refresh=True)
    rows = []
    for label, items in pend.items():
        d = FIX / safe(label)
        npg = 0
        if (d / "task.json").exists():
            c = json.loads((d / "task.json").read_text(encoding="utf-8"))
            npg = sum(len(v) for v in c["页图"].values())
        rows.append((len(items), npg, label))
    rows.sort(key=lambda x: (-x[0], x[1] or 999))
    noimg = [r for r in rows if not r[1]]
    print("还剩 %d 场 / %d 道（其中 %d 场找不到原卷）"
          % (len(rows), sum(r[0] for r in rows), len(noimg)))
    for n, pg, label in (rows[:limit] if limit else rows):
        if pg:
            print(" %2d道 %2d页 %s" % (n, pg, label))


def cmd_report() -> None:
    pend = pending_now()
    done = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines()] \
        if LOG.exists() else []
    fixed = {d["label"] for d in done}
    rows = []
    for label, items in pend.items():
        d = FIX / safe(label)
        st = "已修" if label in fixed else ("待入库" if (d / "check.json").exists()
                                            else ("待校验" if (d / "model.json").exists()
                                                  else ("待读" if (d / "task.json").exists()
                                                        else "无原卷")))
        rows.append((st, label, len(items)))
    print("| 状态 | 场次 | 题数 |\n|---|---|---|")
    for st in ("已修", "待入库", "待校验", "待读", "无原卷"):
        g = [r for r in rows if r[0] == st]
        if g:
            print("| %s | %d | %d |" % (st, len(g), sum(x[2] for x in g)))
    fig = []
    for d in sorted(FIX.glob("*/model.json")) if FIX.exists() else []:
        b = json.loads(d.read_text(encoding="utf-8"))
        for s in b.get("skipped") or []:
            fig.append((b.get("label"), s.get("no"), s.get("kind"), s.get("note")))
    out = FIX / "图表题登记.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("# 图题 / 表题登记（不录正文，交人工）\n\n"
                   "| 卷名 | 题号 | 类型 | 说明 |\n|---|---|---|---|\n"
                   + "".join("| %s | %s | %s | %s |\n" % f for f in fig), encoding="utf-8")
    print("\n图/表题登记 %d 条 → %s" % (len(fig), out))


def _selftest() -> int:
    """用例全部来自**真实踩到的目录名**——定位错一场就把 A 场的题写进 B 场。"""
    fails = 0

    def ck(name, cond, extra=""):
        nonlocal fails
        print("  %s %s" % ("✓" if cond else "✗", name) + ("" if cond else "  " + str(extra)))
        if not cond:
            fails += 1

    print("回原卷修复 自检")
    ck("合一：…数学试题+答案 算试卷",
       role_of_ws("厦门外国语学校2026届高三上学期十月月考数学试题+答案") == "试卷")
    ck("合一：…（含答案）算试卷",
       role_of_ws("江苏省扬州市2025-2026学年高三上学期11月期中考试数学试题（含答案）") == "试卷")
    ck("结尾：…数学答案 算答案",
       role_of_ws("湖南名校联考联合体2026届高三上学期10月月考数学答案") == "答案")
    ck("一套三件：…试题及答案 高三数学—答案 算答案",
       role_of_ws("山东省德州市2025-2026学年高三上学期开学考数学试题及答案 高三数学—答案") == "答案")
    ck("一套三件：…试题及答案 高三数学—试题 算试卷",
       role_of_ws("山东省德州市2025-2026学年高三上学期开学考数学试题及答案 高三数学—试题") == "试卷")
    ck("DA 后缀算答案", role_of_ws("【数学DA】安徽省县中联盟2025-2026学年高三上学期学情检测") == "答案")
    ck("【数学】算试卷", role_of_ws("【数学】安徽省县中联盟2025-2026学年高三上学期学情检测") == "试卷")
    ck("答题卡不进这里（由 SHEET_WORD 挡）",
       bool(SHEET_WORD.search("2026届高三数学答题卡")))
    ck("canon：试卷/答案配成同一场",
       canon("十一校数学试卷") == canon("十一校数学答案") == "十一校",
       canon("十一校数学试卷"))
    ck("canon：卷名缩写也能对上",
       canon("2026届湖北省十一校高三上学期12月质量检测") == "届湖北省十一校高三上学期12月质量检测")
    ck("canon：月考一 / 月考三 **不许**混",
       canon("湖南长郡中学2026届高三上学期月考一") != canon("湖南长郡中学2026届高三上学期月考三"))
    ck("canon：德州卷名与目录名一致",
       canon("山东省德州市2025-2026学年高三上学期开学考 高三—")
       == canon("山东省德州市2025-2026学年高三上学期开学考数学试题及答案 高三数学—试题"),
       canon("山东省德州市2025-2026学年高三上学期开学考 高三—"))
    ck("canon：济南/德州不许混",
       canon("山东省德州市2025-2026学年高三上学期开学考 高三—")
       != canon("山东省济南市2025-2026学年高三上学期摸底考试数学试题"))
    ck("闸门：题型按题号（#9 必须多选）",
       "应为 'multi_choice'" in " ".join(_check_one(
           {"no": 9, "type": "single_choice", "stem": "x（ ）", "options": {},
            "answer": "A", "solution": "s", "quote": ""}, {})))
    ck("闸门：选项缺 A 就拒收",
       any("选项标签" in m for m in _check_one(
           {"no": 1, "type": "single_choice", "stem": "x（ ）", "options": {"B": "b"},
            "answer": "A", "solution": "s", "quote": "x"}, {})))
    ck("闸门：库里已有解析时允许 solution 留空",
       not any("解析为空" in m for m in _check_one(
           {"no": 15, "type": "detailed_answer", "stem": "已知 $x$。", "options": {},
            "answer": "", "solution": "", "quote": "已知 $x$"}, {"solution": "原解析"})))
    ck("闸门：库里没有解析又不写 → 拒收",
       any("解析为空" in m for m in _check_one(
           {"no": 15, "type": "detailed_answer", "stem": "已知 $x$。", "options": {},
            "answer": "", "solution": "", "quote": "已知 $x$"}, {})))
    ck("闸门：卷面方框没处理 → 拒收",
       any("方框" in m for m in _check_one(
           {"no": 1, "type": "single_choice", "stem": "□ABC 中", "options": {
               "A": "a", "B": "b", "C": "c", "D": "d"}, "answer": "A",
            "solution": "s", "quote": "□ABC 中"}, {})))
    print("自检 %s（%d 项失败）" % ("通过" if not fails else "未通过", fails))
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="回原卷修复执行器")
    ap.add_argument("what", choices=["prep", "check", "apply", "apply-batch",
                                     "prompt", "list", "todo", "report", "selftest"])
    ap.add_argument("label", nargs="*", default=[])
    ap.add_argument("--yes", action="store_true", help="apply 时真的落盘")
    ap.add_argument("--drop", action="store_true",
                    help="apply 时把 notfound 的题真的移进回收站")
    ap.add_argument("--all", action="store_true", help="prep 时对全部待修场次跑")
    ap.add_argument("--refresh", action="store_true", help="重算待修清单")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.what == "selftest":
        return _selftest()
    if a.what == "list":
        cmd_list(a.limit)
    elif a.what == "todo":
        cmd_todo(a.limit)
    elif a.what == "report":
        cmd_report()
    else:
        if a.what == "apply-batch":
            apply_batch(a.label or ready_labels(), yes=a.yes, allow_drop=a.drop)
            return 0
        if not a.label and not (a.what == "prep" and a.all):
            raise SystemExit("要给卷名")
        label = (a.label or [""])[0]
        if a.what == "prep":
            pending_now(refresh=a.refresh)
            if a.all:
                for label in sorted(pending_now()):
                    try:
                        prep(label)
                    except SystemExit as e:      # 没待修/卷名不对：记下继续
                        print("跳过 %s：%s" % (label, e))
            else:
                prep(a.label[0])
        elif a.what == "check":
            sys.exit(0 if check(label)["ok"] else 1)
        elif a.what == "apply":
            apply(label, yes=a.yes, allow_drop=a.drop)
        else:
            print(prompt(label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
