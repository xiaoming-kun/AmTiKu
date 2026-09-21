#!/usr/bin/env python3
r"""录题取页：把一场的试卷/答案变成页图，存到 数据/录题/<卷名>/pages/。

用法：python3 脚本/录题取页.py <队列序号>
纯代码（PyMuPDF / zip 抽图），不含任何模型。横版两页拼扫的 PDF 按中线切成左右两页。
"""
import json, re, sys, glob, shutil, zipfile
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "数据/录题"
W = 1500


def render(pdf, out, tag):
    doc = fitz.open(str(pdf))
    n = 0
    for page in doc:
        r = page.rect
        if r.width > r.height:                       # 横版两页拼扫：中线切开
            mid = (r.x0 + r.x1) / 2
            ov = r.width * 0.02
            for clip in (fitz.Rect(r.x0, r.y0, mid + ov, r.y1),
                         fitz.Rect(mid - ov, r.y0, r.x1, r.y1)):
                n += 1
                z = W / clip.width
                page.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip).save(
                    str(out / ("%s_p%02d.png" % (tag, n))))
        else:
            n += 1
            z = W / r.width
            page.get_pixmap(matrix=fitz.Matrix(z, z)).save(
                str(out / ("%s_p%02d.png" % (tag, n))))
    return n


def unzip_docx(docx, out, tag):
    tmp = Path("/tmp/lu_ti_docx")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(str(docx)) as z:
        names = [n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")]
        for n in names:
            (tmp / Path(n).name).write_bytes(z.read(n))
    fs = sorted(tmp.glob("*"), key=lambda p: int(re.search(r"(\d+)", p.name).group(1))
                if re.search(r"(\d+)", p.name) else 0)
    for i, f in enumerate(fs, 1):
        shutil.copy(f, out / ("%s_p%02d%s" % (tag, i, f.suffix)))
    shutil.rmtree(tmp, ignore_errors=True)
    return len(fs)


def _dedup(paths):
    """按文件内容 md5 去重，保留第一次出现的那个名字（顺序不变）。"""
    import hashlib
    seen, out = set(), []
    for p in paths:
        try:
            h = hashlib.md5(p.read_bytes()).hexdigest()
        except OSError:
            continue
        if h not in seen:
            seen.add(h)
            out.append(p)
    return out


def main(no):
    q = json.loads((SRC / "Qoder录题队列.json").read_text(encoding="utf-8"))
    it = next((i for i in q["队列"] if i["序号"] == int(no)), None)
    if not it:
        sys.exit("队列里没有序号 %s" % no)
    src = Path(it["源目录"])
    out = SRC / it["卷名"] / "pages"
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*"):
        f.unlink()
    report = {}
    for tag, files in (("试卷", it["试卷"]), ("答案", it["答案"])):
        exist = [src / f for f in files if (src / f).exists()]
        cands = [p for p in exist if "副本" not in p.name]
        if not cands:
            # 整个目录只登记了「_副本」命名的文件（实测 #300 湖北楚天协作体二模：
            # 试卷、答案各只有两份同名 _副本，压根没有不带副本的正本）。
            # 这时副本就是唯一正本——按内容去重后照用，
            # 别报「缺文件」让整场从队列里悄悄消失。
            cands = _dedup(exist)
        if not cands:
            report[tag] = "缺文件"
            continue
        # 一场可能有多份答案文件（例：「小题解析」+「答案」各一册），
        # 只取第一份会把解答题的解析整块漏掉——所以每份都要取，
        # 依次标 答案 / 答案2 / 答案3。
        for i, p in enumerate(cands, 1):
            t = tag if i == 1 else "%s%d" % (tag, i)
            report[t] = (render if p.suffix.lower() == ".pdf" else unzip_docx)(
                p, out, t)
            report[t + "_文件"] = p.name
    print("%s → %s" % (it["卷名"], report))
    print("页图目录:", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "6")
