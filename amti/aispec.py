r"""把《试卷扫描标准化规范》里**可直接粘给模型**的 §14.1 作为系统提示。

为什么只取 §14.1：整份规范约 94KB，每批都发会挤占页图上下文；
规范自己在 §14.1 标了「可直接粘给模型的 System Prompt」。本地再增加
一条覆盖：本次由程序驱动，按用户消息的 JSON/题块 schema 输出，不写文件；
是否允许模型补答案/解析仍以用户消息为准，不能因为规范默认 B 就擅自补。
"""
from __future__ import annotations

import re

from .paths import ROOT

_CANDIDATES = [
    ROOT / "设计" / "试卷扫描标准化规范-交给大模型_副本.md",
    ROOT / "设计" / "试卷扫描标准化规范-交给大模型.md",
]
#: 网页端实际使用的那份「给网页端大模型」执行说明。
PDF_SPEC = ROOT / "设计" / "PDF题目录入格式要求-给网页端大模型.md"
_CACHE: str | None = None


def _extract() -> str:
    for p in _CANDIDATES:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        # §14.1 后面的 ```text ... ``` 就是规范作者给的短系统提示。
        m = re.search(r"###\s*14\.1[^\n]*\n+```text\n(.*?)\n```", text, re.S)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return ""


def contract() -> str:
    global _CACHE
    if _CACHE is None:
        body = _extract()
        if not body:
            body = (
                "你在把高中数学试卷整理成题库可录入的 LaTeX。题面只准抄；"
                "数学用 $...$ / \\[...\\]；选择题答案放 \\paren，填空放 \\fillin；"
                "缺答案/解析、看不清、原卷矛盾一律写报告，不猜。"
            )
        _CACHE = body
    return _CACHE


def pdf_system_prompt() -> str:
    """网页端同款 PDF 录题要求；API 调用也按这套自由格式输出。"""
    try:
        body = PDF_SPEC.read_text(encoding="utf-8").strip()
    except OSError:
        body = ""
    if not body:
        return system_prompt()
    return (
        "本次通过 API 调用，不能写文件；请**直接按下面文件规定的三段输出**："
        "一个 latex 代码块、未交付/待补表、原题号→第几块表。不要输出 JSON。\n"
        "PDF 文件名会在用户消息里给出；\\title 一律用文件名去掉 .pdf。\n\n"
        + body
    )


def system_prompt() -> str:
    """系统提示：规范正文 + 本次程序驱动的覆盖条款。"""
    return (
        "下面《试卷扫描标准化规范》的规则是本任务的格式与内容要求。\n"
        "本次由本地程序驱动：按用户消息要求的 JSON/题块 schema 输出，"
        "不要写文件、不要输出报告文件；交付物由本地生成。\n"
        "答案/解析是否允许模型补写，以用户消息为准；用户没允许时留空，不得擅自编造。\n\n"
        + contract()
    )
