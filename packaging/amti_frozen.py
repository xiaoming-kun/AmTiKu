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


def _tex_runs(xelatex: Path) -> bool:
    r"""探一下这个 xelatex 在**当前路径下**能不能启动（`--version` 真跑一次）。

    为什么不直接看"路径里有没有中文"：能不能跑取决于系统区域设置——中文 Windows
    的 ANSI 代码页是 GBK，中文路径照跑；英文 Windows 才必挂。macOS/Linux 用 UTF-8
    文件名也没事。与其按平台猜，不如花 200 毫秒试一次。
    """
    import subprocess
    try:
        r = subprocess.run([str(xelatex), "--version"], capture_output=True,
                           encoding="utf-8", errors="replace", timeout=20)
        return r.returncode == 0 and "TeX" in (r.stdout or "")
    except Exception:                          # noqa: BLE001
        return False


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
            # **内置引擎可能起不来**：kpathsea 启动时要按自身位置推 SELFAUTOPARENT，
            # 路径含非 ASCII 字符时，英文区域设置的 Windows 上直接
            # `(null): fatal: Can't get long name for D:\?? ??\AmTiKu.`
            # ——30 毫秒退出、日志里连 `!` 都没有（CI 上定位了好几轮）。
            # 但中文 Windows 的 ANSI 代码页是 GBK，同样路径反而能跑，
            # 所以**不猜，花 200 毫秒真跑一次 `--version`**。
            if any(ord(c) > 127 for c in str(root)) and not _tex_runs(d / exe):
                print("⚠ 内置 LaTeX 在这个路径下起不来：", root)
                print("  原因：路径含中文/非 ASCII 字符，kpathsea 无法启动"
                      "（报 Can't get long name）。")
                sys_xe = shutil.which(exe)
                if sys_xe:
                    print("  已改用系统里的 LaTeX：", sys_xe)
                    return
                print("  系统里也没有别的 LaTeX。请二选一：")
                print("    1) 把整个文件夹移到纯英文路径，例如 D:\\AmTiKu；")
                print("    2) 自行安装 TeX Live（见《TeXLive安装.md》），它会装在英文路径下。")
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


def _export_smoke() -> bool | None:
    r"""走**程序自己的导出代码**编一份 PDF，而不只是看 xelatex 在不在。

    被一个真 bug 逼出来的：server.py 的 export() 里用了 _paper 却没导入，
    只在 handout_font 为空时触发 NameError——只测 xelatex 的自检完全发现不了。
    返回 True 通过 / False 失败 / None 跳过（没有数据或没装 TeX）。
    """
    import tempfile
    try:
        from amti import export as ex
        from amti import paper, store
    except Exception as e:                       # noqa: BLE001
        print("导出自检：跳过（%s）" % e)
        return None
    qs = [q for _f, q in store.iter_questions()][:4]
    if not qs:
        print("导出自检：跳过（库里没有题）")
        return None
    try:
        tex = paper.render_paper(qs, mode="gaokao", title="导出自检（自动）",
                                 show_answers=True, answers_at_end=True,
                                 graphicspath=str(store.PKG / "图片"))
        d = Path(tempfile.mkdtemp())
        src = d / "t.tex"
        src.write_text(tex, encoding="utf-8")
        ok, log = ex.compile_tex(src)
        if ok:
            print("导出自检：通过，PDF %d 字节" % (d / "t.pdf").stat().st_size)
            return True
        # 只打日志尾部会被 Warning 挤掉真正的 Error（Windows 上就吃过这个亏：
        # 尾部是 "Reference LastPage undefined" 这种警告，真错误在前面看不到）。
        errs = [l for l in (log or "").split("\n") if l.startswith("!")][:3]
        print("导出自检：失败 ｜ PDF 存在=%s ｜ 错误行=%s" % ((d / "t.pdf").exists(), errs))
        for l in (log or "").split("\n"):
            if l.startswith("!") or "not found" in l or "Error" in l:
                print("   ", l[:160])
        print("   最后几行：", (log or "")[-200:].replace("\n", " ⏎ "))
        return False
    except Exception:                            # noqa: BLE001
        import traceback
        traceback.print_exc()
        return False


def _setup_node(root: Path) -> None:
    r"""把随包的 Node 与 Chromium 接上（幻灯片式讲义导出要用 npx slidev export）。

    slidev 会 fork node + 自带 chromium 出 PDF，所以三样都得随包：
    node/bin（便携 Node）、slidev/（工程 + node_modules）、playwright/（浏览器缓存）。
    """
    nb = root / "node" / "bin"
    if nb.is_dir():
        os.environ["PATH"] = str(nb) + os.pathsep + os.environ.get("PATH", "")
        print("已加载内置 Node:", nb.parent.name)
    pw = root / "playwright"
    if pw.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(pw))


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
    _setup_node(root)

    if "--selftest" in sys.argv:            # CI 冒烟测试用：不启服务
        from amti import conform, knowledge, store
        from amti import paths
        qs = store.load_all()
        from amti import images
        # 把关键目录一起打出来：打包后路径指错（例如图片目录指向包内部）时一眼可见
        print("SELFTEST OK  root=%s  questions=%d  points=%d  conform_problems=%d"
              % (root, len(qs), len(knowledge.all_points()), len(conform.run())))
        print("  图片目录=%s（存在 %s，%d 张）｜ 知识点=%s"
              % (images.IMG_DIR, images.IMG_DIR.is_dir(),
                 len(list(images.IMG_DIR.glob("*.png"))), knowledge.KB_PATH))
        # **前端必须在包里**。少了它，`server.py` 那句 `if UI_DIST.exists()`
        # 会静默跳过整个界面挂载：接口全都能用、首页却 404，用户以为程序坏了。
        # （免安装版曾经就是这样——只测接口的冒烟测试发现不了。）
        print("  前端目录=%s（存在 %s）" % (paths.UI_DIST, paths.UI_DIST.is_dir()))
        if not (paths.UI_DIST / "index.html").is_file():
            print("自检失败：包内找不到前端 %s —— 免安装版会打不开界面"
                  % (paths.UI_DIST / "index.html"))
            return 1
        # 三态：None=跳过（合法）→ 通过；False=失败 → **必须让流程失败**，
        # 否则残缺的 TeX 或导出代码里的 bug 会蒙混过关，用户拿到才发现导不出 PDF。
        # 先走程序自己的导出路径（更强），没有数据/没装 TeX 时退回只测引擎。
        r = _export_smoke()
        if r is None:
            r = _tex_smoke()
        return 0 if r is not False else 1

    from amti.web import server
    argv = [a for a in sys.argv[1:] if a != "--selftest"]
    sys.argv = [sys.argv[0]] + argv
    return server.main()


if __name__ == "__main__":
    raise SystemExit(main())
