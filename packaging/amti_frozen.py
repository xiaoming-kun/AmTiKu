r"""免安装版入口（PyInstaller 打包用）。

双击 exe → 起服务 → 自动打开浏览器；关掉页面 25 秒后自动退出。
数据放在 **exe 同目录**（题目/ 图片/ 知识点.json）；没有就先用随包的 demo 题库。
"""
import os
import shutil
import sys
from pathlib import Path


def _root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _ensure_data(root: Path) -> None:
    r"""第一次运行时，把随包的 demo 题库放到 exe 旁边（已有题库则不动）。"""
    if (root / "题目").exists():
        return
    bundle = Path(getattr(sys, "_MEIPASS", root))
    demo = bundle / "demo数据"
    if not (demo / "题目").exists():
        return
    print("首次运行：放入 demo 题库（15 秒后自动打开浏览器）...")
    shutil.copytree(demo / "题目", root / "题目")
    if (demo / "图片").exists():
        shutil.copytree(demo / "图片", root / "图片")
    if (demo / "知识点.json").exists():
        shutil.copy2(demo / "知识点.json", root / "知识点.json")


def _safe_console() -> None:
    r"""把标准输出/错误改成容错编码。

    坑（CI 上第一次就炸）：Windows 控制台默认 cp1252/cp936，
    程序里任何一句中文 print 都可能抛 UnicodeEncodeError 把程序打崩
    （英文版 Windows、或输出被重定向时必然发生）。改成 UTF-8 + replace，
    编码不下的字符退化成 "?"，而不是让整个程序挂掉。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _setup_tex(root: Path) -> None:
    r"""把随包的 LaTeX 加进 PATH 与环境变量，让「导出 PDF」开箱可用。

    随包目录布局：
        tex/bin/<arch>/{xelatex,xelatex.exe}   ← 引擎（windows / universal-darwin / x86_64-linux）
        tex/texmf-dist/  texmf-var/            ← 宏包与格式文件
    TeX Live 自己会用 $SELFAUTOPARENT 定位这些树，所以理论上只需把 bin 放进 PATH；
    这里把 TEXMF* 也显式设上，避免用户机器上装了别的 TeX 时被抢走。
    """
    binroot = root / "tex" / "bin"
    if not binroot.is_dir():
        return
    exe = "xelatex.exe" if os.name == "nt" else "xelatex"
    for d in sorted(binroot.iterdir()):
        if (d / exe).exists():
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            tex = root / "tex"
            os.environ.setdefault("TEXMFCNF", str(tex / "texmf-dist" / "web2c"))
            os.environ.setdefault("TEXMFROOT", str(tex))
            os.environ.setdefault("TEXMFDIST", str(tex / "texmf-dist"))
            os.environ.setdefault("TEXMFVAR", str(tex / "texmf-var"))
            os.environ.setdefault("TEXMFSYSVAR", str(tex / "texmf-var"))
            print("已加载内置 LaTeX:", d.name)
            return


_TEX_SMOKE = r"""\documentclass{exam-zh}
\title{TeX 自检}
\begin{document}
\begin{question}
已知 $a>0$，求 $a+\dfrac{1}{a}$ 的最小值。
\end{question}
\begin{solution}
由均值不等式，$a+\dfrac{1}{a}\geqslant 2$，当且仅当 $a=1$ 时取等。
\end{solution}
\end{document}
"""


def _tex_smoke() -> bool | None:
    r"""真编一份最小 exam-zh 卷子，确认「导出 PDF」这条路是通的。

    只看 xelatex 在不在 PATH 里是不够的——宏包缺一个就编不出来（本机第一次就漏在
    l3draw.sty 上）。这里实际编两遍（第二遍定页码），出 PDF 才算过。
    """
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("xelatex"):
        print("TeX 自检：跳过（这个包没有内置 LaTeX）")
        return None
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "t.tex"
        src.write_text(_TEX_SMOKE, encoding="utf-8")
        for _ in range(2):
            r = subprocess.run(["xelatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
                               cwd=d, capture_output=True, text=True, timeout=300)
        pdf = Path(d) / "t.pdf"
        ok = pdf.exists()
        print("TeX 自检：%s%s" % ("通过，PDF %d 字节" % pdf.stat().st_size if ok else "失败",
                                 "" if ok else "  ← 最后几行：" + (r.stdout or "")[-300:]))
        return ok


def main() -> int:
    _safe_console()
    root = _root()

    os.environ.setdefault("AMTIKU_ROOT", str(root))
    try:
        os.chdir(root)                     # 打包后工作目录可能是别处
    except OSError:
        pass
    _ensure_data(root)
    _setup_tex(root)

    if "--selftest" in sys.argv:            # CI 冒烟测试用：不启服务
        from amti import conform, knowledge, store
        qs = store.load_all()
        print("SELFTEST OK  root=%s  questions=%d  points=%d  conform_problems=%d"
              % (root, len(qs), len(knowledge.all_points()), len(conform.run())))
        # TeX 自检：None=没装（合法）→ 通过；False=装了却编不出来 → **必须让流程失败**，
        # 否则残缺的 TeX（少宏包）会蒙混过关，用户拿到才发现导不出 PDF。
        return 0 if _tex_smoke() is not False else 1

    from amti.web import server
    argv = [a for a in sys.argv[1:] if a != "--selftest"]
    sys.argv = [sys.argv[0]] + argv
    return server.main()


if __name__ == "__main__":
    raise SystemExit(main())
