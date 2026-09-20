#!/usr/bin/env python3
r"""批量取「试卷第 1 页」，用于录题开工前的卷面标题预检（便宜：一场一张图）。

用法：python3 脚本/录题取标题页.py 20 21 25 26 ...
输出：/tmp/lu_ti_p1/<序号>_<卷名>_p01.png
"""
import json, sys, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fitz

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/tmp/lu_ti_p1")


def first_page(src, out):
    from importlib import import_module
    m = import_module("脚本.录题取页") if (ROOT / "脚本/__init__.py").exists() else None
    pdf = fitz.open(str(src))
    page = pdf[0]
    r = page.rect
    if r.width > r.height:                      # 横版拼扫：只取左半页（第 1 页）
        mid = (r.x0 + r.x1) / 2
        clip = fitz.Rect(r.x0, r.y0, mid + r.width * 0.02, r.y1)
    else:
        clip = r
    z = 1500 / clip.width
    page.get_pixmap(matrix=fitz.Matrix(z, z), clip=clip).save(str(out))
    return True


def main(nos):
    q = json.loads((ROOT / "数据/录题/Qoder录题队列.json").read_text(encoding="utf-8"))
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    for no in nos:
        it = next((i for i in q["队列"] if i["序号"] == int(no)), None)
        if not it:
            print("跳过：队列没有序号", no)
            continue
        if it["状态"] != "todo":
            print("跳过：序号 %s 状态是 %s" % (no, it["状态"]))
            continue
        src = Path(it["源目录"])
        cands = [src / f for f in it["试卷"] if (src / f).exists()]
        if not cands:
            print("%s %s → 没有试卷文件" % (no, it["卷名"]))
            continue
        p = cands[0]
        out = OUT / ("%03d.png" % int(no))
        if p.suffix.lower() == ".pdf":
            first_page(p, out)
        else:
            import zipfile, re
            tmp = Path("/tmp/lu_ti_p1_docx")
            shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True)
            with zipfile.ZipFile(str(p)) as z:
                names = [n for n in z.namelist() if n.startswith("word/media/") and not n.endswith("/")]
                for n in names:
                    (tmp / Path(n).name).write_bytes(z.read(n))
            fs = sorted(tmp.glob("*"), key=lambda f: int(re.search(r"(\d+)", f.name).group(1))
                        if re.search(r"(\d+)", f.name) else 0)
            if fs:
                shutil.copy(fs[0], out)
            shutil.rmtree(tmp, ignore_errors=True)
        print("%s %s → %s" % (no, it["卷名"], out.name))


if __name__ == "__main__":
    main(sys.argv[1:])
