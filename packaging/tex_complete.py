r"""把随包 TeX Live 的宏包补全：反复编译参考卷，缺哪个包就 tlmgr 装哪个。

为什么需要它：最小 scheme 只带几十个包，而 exam-zh 一条链下来要用上百个；
靠人猜清单必然漏（第一次就漏在 l3draw.sty 上）。这个脚本用「编译报错 → 反查包名
→ 装上 → 再编」的循环把它补到能编出 PDF 为止，本机与 CI 共用同一套逻辑。

    python3 packaging/tex_complete.py --tex dist/tex --papers packaging/test-paper.tex

`--tex` 是 TeX Live 的根目录（bin/ 与 texmf-dist/ 在它下面）。
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

def _safe_console() -> None:
    r"""把 stdout/stderr 改成容错编码。

    坑（CI 上炸过两次）：Windows 控制台默认 cp1252——脚本里任何一句中文 print
    都会抛 UnicodeEncodeError 把流程打挂（英文版 Windows 亦然）。
    改成 UTF-8 + errors=replace，编不下的字符退化成 "?"，而不是让流程失败。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_safe_console()

MISSING_FILE = re.compile(r"[`'\"]([^`'\"]+?\.(?:sty|cls|def|cfg|ldf|fd|clo|tex))['\"]")
MISSING_FONT = re.compile(r'The font "([^"]+)" cannot be found')


def tlmgr_path(tex: Path) -> Path:
    for name in ("tlmgr.bat", "tlmgr"):
        hits = list((tex / "bin").glob(f"*/{name}"))
        if hits:
            return hits[0]
    raise SystemExit(f"在 {tex}/bin 下找不到 tlmgr")


def xelatex_path(tex: Path) -> Path:
    for name in ("xelatex.exe", "xelatex"):
        hits = [p for p in (tex / "bin").glob(f"*/{name}") if p.exists()]
        if hits:
            return hits[0]
    raise SystemExit(f"在 {tex}/bin 下找不到 xelatex")


def run(cmd, cwd, env, timeout=900):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tex", required=True, help="TeX Live 根目录")
    ap.add_argument("--papers", nargs="+", default=["packaging/test-paper.tex"])
    ap.add_argument("--rounds", type=int, default=30)
    a = ap.parse_args()

    tex = Path(a.tex).resolve()
    tlmgr, xelatex = tlmgr_path(tex), xelatex_path(tex)
    env = {**os.environ, "PATH": f"{xelatex.parent}{os.pathsep}{os.environ.get('PATH', '')}",
           "TEXMFROOT": str(tex), "TEXMFDIST": str(tex / "texmf-dist"),
           "TEXMFVAR": str(tex / "texmf-var"), "TEXMFSYSVAR": str(tex / "texmf-var")}
    work = Path("/tmp/tex_complete_work")
    work.mkdir(parents=True, exist_ok=True)

    installed: set[str] = set()
    last_names: list[str] = []
    for paper in a.papers:
        src = Path(paper).resolve()
        (work / "t.tex").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        for i in range(1, a.rounds + 1):
            for f in ("t.aux", "t.log", "t.pdf"):
                (work / f).unlink(missing_ok=True)
            # 必须带 -halt-on-error：nonstopmode 下字体缺失/宏包报错也照样产出 PDF，
            # 会把残缺的 TeX 判成"通过"（本机就漏了 Asana-Math 字体，自检才暴露）
            r = run([str(xelatex), "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
                    work, env, timeout=300)
            log = r.stdout + r.stderr
            if (work / "t.pdf").exists():
                print(f"  ✓ {src.name}：第 {i} 轮编出 PDF")
                break
            names = list(dict.fromkeys(MISSING_FILE.findall(log) + MISSING_FONT.findall(log)))
            pkgs: set[str] = set()
            for name in names:
                q = run([str(tlmgr), "search", "--global", "--file", name], work, env, timeout=300)
                # tlmgr 的**信息行都以 `tlmgr.pl:` 开头**（例如 "tlmgr.pl: searching..."），
                # 按 "含冒号" 取包名会把它们也当成包 → 于是无限"补 tlmgr.pl"（CI 上空转 30 轮）。
                # 只认「整行以冒号结尾」的包名行，并排掉 tlmgr 自身。
                for line in q.stdout.split("\n"):
                    if not line.endswith(":"):
                        continue
                    p = line[:-1].strip()
                    if not p or " " in p or p.lower().startswith("tlmgr"):
                        continue
                    pkgs.add(p)
            if not pkgs:
                errs = [l for l in log.split("\n") if l.startswith("!")][:3]
                # 一定要把日志尾部打出来：只用 "! Package fontspec Error:" 这种首行
                # 根本判断不出缺哪个字体（CI 上就吃过这个亏，白跑一轮）
                print(f"  ✗ {src.name}：第 {i} 轮卡在非缺文件错误 {errs}\n"
                      f"----- 日志尾部 -----\n{log[-1200:]}")
                return 1
            if names == last_names:      # 同一批缺文件又来了 → 补包没用，别再空转
                errs = [l for l in log.split("\n") if l.startswith("!")][:3]
                print(f"  ✗ {src.name}：第 {i} 轮仍缺同样的文件 {names[:3]}，停止。"
                      f"真正的错误：{errs}\n----- 日志尾部 -----\n{log[-800:]}")
                return 1
            last_names = names
            print(f"  · {src.name} 第 {i} 轮：补 {', '.join(sorted(pkgs)[:5])}")
            run([str(tlmgr), "install"] + sorted(pkgs), work, env, timeout=1800)
            installed |= pkgs
        else:
            print(f"  ✗ {src.name}：{a.rounds} 轮仍未编出 PDF")
            return 1
    print("累计补装 %d 个包：%s" % (len(installed), ", ".join(sorted(installed))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
