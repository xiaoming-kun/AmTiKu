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

ANSWER_WORD = re.compile(r"答案|解析|全解全析|参考答案|评分标准|教师版")
SHEET_WORD = re.compile(r"答题卡|答题纸")
PREFIX = re.compile(r"^\s*\d{1,4}[\.\-、_\s]+")


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
def _norm_ws(name: str) -> str:
    return re.sub(r"[\s（）()【】\[\]]+", "", PREFIX.sub("", name)).lower()


def workspaces() -> list[Path]:
    return [p for p in WORK.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))]


def _manifest() -> dict:
    """`v2批跑清单.json` → `{卷名: {试卷:[目录], 答案:[目录]}}`。

    清单里的 `work`/`ans` 是**跑批时确认过的原卷工作区**，比按名字猜可靠。
    那 10 条只有 `pdf`（"相似度 0.78"猜出来的）的一律不采信——实测全是错的
    （绍兴一模指向榆林一模），宁可报"找不到原卷"。
    """
    f = WORK / "v2批跑清单.json"
    out: dict[str, dict] = {}
    if not f.exists():
        return out
    for t in json.loads(f.read_text(encoding="utf-8")).get("todo") or []:
        hit = {"试卷": [], "答案": []}
        for side in ("work", "ans"):
            p = t.get(side)
            if not p or "pdf" in t:
                continue                      # 只有 `pdf` 的那 10 条是猜的，不采信
            ws = _ws_of(Path(p))
            if ws:
                hit["答案" if ANSWER_WORD.search(ws.name) else "试卷"].append(ws)
        if any(hit.values()):
            out[t["label"]] = hit
    return out


def _ws_of(p: Path) -> Path | None:
    """清单里的路径 → 工作区目录（可能是目录，也可能是原卷 PDF 的路径）。

    路径规则复用 `record2.work_of`，不在这里另写一套（它对
    `187.湖南长郡…` 这种带序号的目录名做过修正）。
    """
    ws = R2.work_of(p)
    return ws if ws.is_dir() else None


_MAN: dict = {}


def locate(label: str) -> dict:
    r"""卷名 → `{试卷: [目录…], 答案: [目录…]}`。

    先查清单（跑批时确认过的路径），查不到再按工作区名匹配。
    """
    if not _MAN:
        _MAN.update(_manifest())
    if label in _MAN:
        return _MAN[label]
    want = _norm_ws(label)
    cand = []
    for d in workspaces():
        if SHEET_WORD.search(d.name):
            continue
        n = _norm_ws(d.name)
        if n and (n.startswith(want) or want.startswith(n)):
            cand.append(d)
    exact = [d for d in cand if _norm_ws(d.name) == want]
    good = exact or [d for d in cand if min(len(_norm_ws(d.name)), len(want)) >= 8]
    hit: dict[str, list[Path]] = {"试卷": [], "答案": []}
    for d in good:
        hit["答案" if ANSWER_WORD.search(d.name) else "试卷"].append(d)
    return {k: sorted(v) for k, v in hit.items()}


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


def check(label: str, *, corpus: str | None = None) -> dict:
    d = FIX / safe(label)
    book = json.loads((d / "model.json").read_text(encoding="utf-8"))
    want = {it["no"] for it in pending_now().get(label) or []}
    have = {it["no"]: (it.get("库里") or {})
            for it in json.loads((d / "task.json").read_text(encoding="utf-8"))["待修"]}
    errs, warns = [], []
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
           "题数": len(recs), "待修": sorted(want)}
    (d / "check.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    print("%s  交来 %d 道 / 待修 %d 道" % ("✓ 通过" if out["ok"] else "✗ 不合格",
                                       len(recs), len(want)))
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
def apply(label: str, *, yes: bool = False) -> dict:
    r"""把这一场的 JSON 写回库里。规则（交接文档 11.2，别改）：

    * **只动待修清单里的题**
    * JSON 给得出的字段 → 覆盖；给不出的（答案/解析为空）→ 保留库里原值
    * JSON 里明确 `notfound` 的 → 进回收站（可恢复）
    """
    d = FIX / safe(label)
    chk = json.loads((d / "check.json").read_text(encoding="utf-8"))
    if not chk.get("ok"):
        raise SystemExit("check 没过，不许入库：%s" % "; ".join(chk["errors"][:5]))
    book = json.loads((d / "model.json").read_text(encoding="utf-8"))
    recs = {r["no"]: r for r in book.get("questions") or []}
    drop = {int(x["no"]) for x in book.get("notfound") or []}
    want = {it["no"] for it in pending_now().get(label) or []}

    qs = store.load_all()
    idx = {}
    for i, q in enumerate(qs):
        if q.meta.get("source_label") == label:
            idx[q.meta.get("source_no")] = i
    stamp = time.strftime("%Y-%m-%d %H:%M")
    fixed, dropped, untouched = [], [], sorted(want - set(recs) - drop)

    for no in sorted(want & set(recs)):
        if no not in idx:
            untouched.append(no)
            continue
        old = qs[idx[no]]
        new = R2.rec_to_question({"题号": no, "题型": recs[no]["type"],
                                  "题干": recs[no]["stem"], "选项": recs[no].get("options") or {},
                                  "答案": recs[no].get("answer") or "",
                                  "解析": recs[no].get("solution") or ""}, label)
        old.type, old.stem, old.options = new.type, new.stem, new.options
        old.answer = new.answer or old.answer
        old.solution = new.solution or old.solution
        old.meta["migrated_at"], old.meta["migrated_by"] = stamp, "回原卷重扫修复"
        fixed.append(no)
    for no in sorted(want & drop):
        if no in idx:
            dropped.append(qs[idx[no]].key)

    rep = {"label": label, "when": stamp,
           "修补": [{"题号": n} for n in fixed],
           "舍弃": dropped, "未处理": untouched}
    if not yes:
        print("干跑：修补 %d、舍弃 %d、未处理 %d（加 --yes 才落盘）"
              % (len(fixed), len(dropped), len(untouched)))
        return rep
    if dropped:
        r = trash.delete(dropped, reason="无", password="0808")
        if not r.get("ok"):
            raise SystemExit("回收站写入失败，题库未改动：%s" % r.get("error"))
    store.rewrite_all(qs)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rep, ensure_ascii=False) + "\n")
    print("已落盘：修补 %d、舍弃 %d、未处理 %d" % (len(fixed), len(dropped), len(untouched)))
    return rep


# ── prompt ─────────────────────────────────────────────────────────
PROMPT = """\
你是 AmTiKu 题库的录题员。这一场是《{label}》，**扫描版**高中数学试卷。
库里这一场有 {n} 道题缺数据，你只负责把它们**照原卷抄对**：{nos}

页图（按阅读顺序；横版双页已切成单页）：
【试卷】
{paper}
【答案】
{answer}{source}

库里这几道题现在缺什么（**只补这些，别改编号以外的题**）：
{current}

规矩（违反任何一条，这一场就算废）：
1. 题型按题号定：1-8 单选 single_choice、9-11 多选 multi_choice、
   12-14 填空 fill_in_blank、15-19 解答 detailed_answer。**不许按选项个数猜**。
2. **一个字都不许改**：每个字段都要能在原图上逐字找到；看不清写 `\\text{{【?】}}`，
   不许猜、不许"顺手改正"、不许解题、不许补条件。
3. 选择题必须 A/B/C/D 四个选项（标签印坏了也按顺序补成 A）；答案写字母；
   填空题答案写那个值本身（≤40 字）；解答题 answer 写 ""。
4. 答案去【答案】页找；**绝不许拿别的题的答案顶上**。解析里有"故选 CD"而答案栏空 → 把 CD 填进 answer。
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
{{"label":"{label}","book":"模拟题","year":{year},
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
    return PROMPT.format(label=label, n=len(card["待修"]), nos=nos,
                         current="\n".join(cur(x) for x in card["待修"]),
                         year=y.group(1) if y else 2026, source=source,
                         out=str(FIX / safe(label) / "model.json"),
                         paper=fmt(card["页图"]["试卷"]), answer=fmt(card["页图"]["答案"]))


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


def main() -> int:
    ap = argparse.ArgumentParser(description="回原卷修复执行器")
    ap.add_argument("what", choices=["prep", "check", "apply", "prompt", "list", "report"])
    ap.add_argument("label", nargs="*", default=[])
    ap.add_argument("--yes", action="store_true", help="apply 时真的落盘")
    ap.add_argument("--all", action="store_true", help="prep 时对全部待修场次跑")
    ap.add_argument("--refresh", action="store_true", help="重算待修清单")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if a.what == "list":
        cmd_list(a.limit)
    elif a.what == "report":
        cmd_report()
    else:
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
            apply(label, yes=a.yes)
        else:
            print(prompt(label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
