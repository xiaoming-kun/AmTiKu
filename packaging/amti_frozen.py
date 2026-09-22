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


def main() -> int:
    root = _root()
    os.environ.setdefault("AMTIKU_ROOT", str(root))
    try:
        os.chdir(root)                     # 打包后工作目录可能是别处
    except OSError:
        pass
    _ensure_data(root)

    if "--selftest" in sys.argv:            # CI 冒烟测试用：不启服务
        from amti import conform, knowledge, store
        qs = store.load_all()
        print("SELFTEST OK  root=%s  questions=%d  points=%d  conform_problems=%d"
              % (root, len(qs), len(knowledge.all_points()), len(conform.run())))
        return 0

    from amti.web import server
    argv = [a for a in sys.argv[1:] if a != "--selftest"]
    sys.argv = [sys.argv[0]] + argv
    return server.main()


if __name__ == "__main__":
    raise SystemExit(main())
