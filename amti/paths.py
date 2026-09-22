r"""项目根目录（数据所在目录）的**唯一来源**。

为什么要单独一个模块：免安装版用 PyInstaller 打包后，模块代码在包内部，
`Path(__file__).parent.parent` 指的就不是"数据所在目录"了——题库、图片、知识点
都会被算到包内部去，读不到也写不进。

统一按这个顺序找：
  1. 环境变量 `AMTIKU_ROOT`（显式指定，优先级最高）
  2. 打包运行时：**可执行文件所在目录**（数据就放在 exe 旁边）
  3. 源码运行时：仓库根目录（`amti/` 的上一级）
"""
import os
import sys
from pathlib import Path


def resolve_root() -> Path:
    env = os.environ.get("AMTIKU_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):          # PyInstaller 等打包运行时
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_resources() -> Path:
    r"""**随包只读资源**所在目录（前端 `web/dist`、demo 题库）。

    必须与 `ROOT`（数据目录）分开——这是两种东西：

    * `ROOT`：用户的**数据**（题目/ 图片/ 知识点.json），放在 exe 旁边，
      要能读也要能写，用户换电脑时拷的就是它。
    * 资源：打包进去的**只读**文件，PyInstaller 把它们解在 `sys._MEIPASS`
      （onedir 模式实际就是 exe 旁边的 `_internal/`）。

    混为一谈的后果实测过：免安装版打开 <http://127.0.0.1:8899> **是 404**——
    前端在 `_internal/web/dist`，而代码去 exe 旁边找 `web/dist`，找不到就
    静默跳过了整个界面挂载，于是"接口都能用、界面打不开"。
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


ROOT = resolve_root()
RESOURCES = resolve_resources()
# 前端构建产物（`npm run build` 的 outDir）。开发机上没构建时可能不存在，
# 所以用之前要判存在——但**打包后必须存在**，见 packaging/amti_frozen.py 的自检。
UI_DIST = RESOURCES / "web" / "dist"
