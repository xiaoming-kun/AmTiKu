r"""识别引擎：PaddleOCR-VL-1.6（唯一实现）。

2026-10-27 起 MinerU 已从本仓库移除——同一份卷子实测它的选项标签整排丢、
解析还会串到上一题，PaddleOCR-VL 逐块识别干净得多。

`AMTIKU_OCR` 只为兼容旧脚本保留；设不设都是 paddle。
"""
from __future__ import annotations

import os


def name() -> str:
    return (os.environ.get("AMTIKU_OCR") or "paddle").strip().lower()


def get():
    from . import paddle
    return paddle
