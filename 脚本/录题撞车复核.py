#!/usr/bin/env python3
r"""撞车复核：验证「这场库里真有」的判断，抓出误判。

为什么需要：撞车登记里有 72 场是早期批量预检写的，只按文件名/标题匹配、没比过题干。
2026-09-20 抽查发现 13 场是**误判**（把贵州/青岛/芜湖的卷子判成了郴州同一场），
等于白白丢掉 13 场题。判据必须落到题干文字上。

两条判据，按可信度排序：
  1) 文字层重合度：试卷 PDF/docx 有文字层时，拿它的汉字二元组去比库里那卷的题干+选项+解析。
     同卷 ≥0.55（实测 0.56~0.91），不同卷 ≤0.36，中间没有模糊地带。
  2) 没有文字层（扫描/图片 docx）→ 只能看卷面：脚本把试卷第 1 页渲染到 /tmp/lu_ti_p1chk/，
     并打印声称那卷的 #1 题干，交人/模型比对。

用法：
  python3 脚本/录题撞车复核.py            # 复核所有「无备注」的登记（判据 1，能判就判）
  python3 脚本/录题撞车复核.py 56 78 90   # 只复核这些序号
  python3 脚本/录题撞车复核.py --pages    # 顺便把无文字层的第 1 页渲染出来
输出：数据/录题/撞车复核.json（覆盖写，留证据）
"""
import json, re, shutil, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fitz

fitz.TOOLS.mupdf_display_errors(False)
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "数据/录题"
OUT = SRC / "撞车复核.json"
IMG = Path("/tmp/lu_ti_p1chk")
CJK = re.compile(r"[\u4e00-\u9fff]")
SAME, DIFF = 0.55, 0.55          # ≥SAME 判同卷；<DIFF 判误判


def bigs(s):
    t = "".join(CJK.findall(s or ""))
    return {t[i:i + 2] for i in range(len(t) - 1)}


def lib_stems():
    from amti import store
    out = {}
    for x in store.load_all():
        m = x.meta or {}
        if m.get("book") != "模拟题":
            continue
        lab = m.get("source_label")
        if not lab:
            continue
        opts = " ".join((o.get("text") or "") if isinstance(o, dict) else str(o)
                        for o in (x.options or []))
        out.setdefault(lab, []).append((m.get("source_no") or 0,
                                        " ".join([x.stem or "", x.answer or "",
                                                  x.solution or "", opts])))
    return out


def paper_bigs(it):
    src = Path(it["源目录"])
    acc, suffix = set(), ""
    for f in it["试卷"]:
        p = src / f
        if not p.exists():
            continue                       # 复核只看重合度，「副本」也是同一场，不必排除
        suffix = p.suffix.lower()
        txt = ""
        if suffix == ".pdf":
            try:
                txt = "".join(pg.get_text() for pg in fitz.open(str(p)))
            except Exception:
                txt = ""
        elif suffix in (".docx", ".doc"):
            try:
                with zipfile.ZipFile(str(p)) as z:
                    txt = re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode("utf8", "ignore"))
            except Exception:
                txt = ""
        acc |= bigs(txt)
    return acc, suffix, src


def first_page(it, src, _unused, out):
    for f in it["试卷"]:
        p = src / f
        if not p.exists():
            continue
        suffix = p.suffix.lower()
        if suffix == ".pdf":
            pg = fitz.open(str(p))[0]
            r = pg.rect
            clip = (fitz.Rect(r.x0, r.y0, (r.x0 + r.x1) / 2 + r.width * 0.02, r.y1)
                    if r.width > r.height else r)
            pg.get_pixmap(matrix=fitz.Matrix(1500 / clip.width, 1500 / clip.width),
                          clip=clip).save(str(out))
            return True
        if suffix in (".docx", ".doc"):
            tmp = Path("/tmp/lu_ti_p1chk_docx")
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            with zipfile.ZipFile(str(p)) as z:
                for n in z.namelist():
                    if n.startswith("word/media/") and not n.endswith("/"):
                        (tmp / Path(n).name).write_bytes(z.read(n))
            fs = sorted(tmp.glob("*"), key=lambda f: int(re.search(r"(\d+)", f.name).group(1))
                        if re.search(r"(\d+)", f.name) else 0)
            if fs:
                shutil.copy(fs[0], out)
            shutil.rmtree(tmp, ignore_errors=True)
            return True
    return False


def main(argv):
    want_pages = "--pages" in argv
    nos = [int(a) for a in argv if a.isdigit()]
    reg = json.loads((SRC / "撞车核对.json").read_text(encoding="utf-8"))
    q = {x["序号"]: x for x in json.loads((SRC / "Qoder录题队列.json").read_text(encoding="utf-8"))["队列"]}
    lib = lib_stems()
    if want_pages:
        shutil.rmtree(IMG, ignore_errors=True)
        IMG.mkdir(parents=True)
    rows = []
    for e in reg:
        no = e["序号"]
        if nos and no not in nos:
            continue
        if e.get("备注") and not nos:
            continue                       # 已经人工核过的不重复判
        it = q.get(no)
        if not it:
            rows.append({"序号": no, "判定": "队列里已没有这场"})
            continue
        pb, suffix, src = paper_bigs(it)
        lab = e["库里卷名"]
        lb = set()
        for n, s in lib.get(lab, []):
            lb |= bigs(s)
        if len(lb) < 200:
            rows.append({"序号": no, "卷名": it["卷名"], "库里卷名": lab, "判定": "库里查不到这卷"})
            continue
        if len(pb) < 200:
            r = {"序号": no, "卷名": it["卷名"], "库里卷名": lab, "判定": "无文字层-要看卷面"}
            if want_pages:
                out = IMG / ("%03d.png" % no)
                if first_page(it, src, suffix, out):
                    s1 = sorted(lib.get(lab, []))
                    r["第1页"] = str(out)
                    r["库里#1"] = (s1[0][1][:80] if s1 else "")
            rows.append(r)
            continue
        ov = round(len(pb & lb) / max(1, min(len(pb), len(lb))), 3)
        rows.append({"序号": no, "卷名": it["卷名"], "库里卷名": lab, "重合": ov,
                     "判定": "确认同卷" if ov >= SAME else "误判-应恢复todo"})
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bad = [r for r in rows if r.get("判定") == "误判-应恢复todo"]
    need = [r for r in rows if r.get("判定") == "无文字层-要看卷面"]
    for r in rows:
        print("#%-4s %-8s %-9s %s" % (r["序号"], r.get("重合", "—"), r.get("判定", ""),
                                      (r.get("卷名") or "")[:36]))
    print("\n%d 场：误判 %d，确认同卷 %d，待看卷面 %d（证据见 %s）"
          % (len(rows), len(bad), sum(1 for r in rows if r.get("判定") == "确认同卷"),
             len(need), OUT.relative_to(ROOT)))
    if bad:
        print("误判序号: " + " ".join(str(r["序号"]) for r in bad))
    if need and not want_pages:
        print("加 --pages 可把待看卷面的第 1 页渲染到 " + str(IMG))


if __name__ == "__main__":
    main(sys.argv[1:])
