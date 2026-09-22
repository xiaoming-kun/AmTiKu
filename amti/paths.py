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


ROOT = resolve_root()
