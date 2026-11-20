"""结构检查：把 AGENTS.md 的「唯一入口」从文档变成断言。

## 为什么需要它

文档拦不住复制粘贴。同一套规则被抄成 N 份之后，改一处、漏两处，
问题就长在这种缝里——本轮修出的 3 个 bug 全是这样：

    airepair   只认 `question` 环境（解答题是 `problem`）——规则的第 2 份拷贝
    ai_agent   每轮重新开题（chat 没有会话）——调用约定的第 2 份拷贝
    _source_key 三处比较方式不一致（一处 strip、一处不 strip）——同一判据的第 3 份

`conform` 查题目的写法，`verify` 查字段自洽，`ruff` 查单个文件内部；
**没有一条查"模块之间的边界"**。这里补上，只查三条能机检的：

    R1  路由层写库必须**同步派生索引**
        ——`store.write_*` 改了题库，`_rm_apply`/全文索引没跟上，
        列表和搜索就停在旧数据上（界面看起来"改了没生效"）。
        规则是"成对出现"，不是"不许写"：写事务就该在端点里一次做完，
        拆成两个模块反而更难保证原子性。
    R2  AI 模块（ai_*.py / aicurate / aiproof / airepair / aispec / deepseek）只读
        ——AI 只出建议，写回永远走 HTTP 路由那一条路
    R3  记账类模块（store / deepseek / ai_history / ai_cases / *_ops）
        不得 `except Exception: pass`
        ——台账、用量、审计写失败必须是**可见**的，不能假装写成功

另外 R1b：路由层不得自己 `open()` 写 `题目/` 下的文件——那是 store 的地盘，
绕过它就没有指纹/并发/分卷校验。

跑法：

    python3 -m amti.lint              # 违例 → 退出码 1
    python3 -m amti.lint --selftest   # 规则本身要自证：三种违例都抓得到

规则宁可少，不可误报：每条都只匹配 AST 里明确的结构（`store.xxx()` 调用、
`except Exception` 且函数体只有一个 `pass`），不做文本猜测。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

AMTI = Path(__file__).resolve().parent

# store 的写入口。读（find / read_one / read_many / load_*）不在此列。
STORE_WRITES = frozenset({
    "append", "delete", "replace_question", "restore_backup",
    "rewrite_all", "rewrite_volume", "update", "write_many", "write_one",
})

# 记账/审计类模块：写失败必须留痕（R3）。
AUDIT_MODULES = frozenset({
    "store.py", "deepseek.py", "ai_history.py", "ai_cases.py",
    "patch_ops.py", "source_ops.py",
})

# AI 模块：只读（R2）。
AI_FILES = frozenset({
    "aicurate.py", "aiproof.py", "airepair.py", "aispec.py", "deepseek.py",
})


# ── 规则 ──────────────────────────────────────────────────────────────

def _is_ai_module(name: str) -> bool:
    return name.startswith("ai_") or name in AI_FILES


def _is_router(rel: str) -> bool:
    return rel.startswith("web/routers/")


SYNC_CALLS = frozenset({"_rm_apply", "set_used", "upsert"})


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def store_writes(tree: ast.AST) -> list[tuple[int, str]]:
    r"""`store.write_one(...)` 这一类调用，以及 `from amti.store import write_one`。"""
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            f = node.func
            if (isinstance(f.value, ast.Name) and f.value.id == "store"
                    and f.attr in STORE_WRITES):
                out.append((node.lineno, f.attr))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "amti.store" or mod.endswith(".store"):
                for a in node.names:
                    if a.name in STORE_WRITES:
                        out.append((node.lineno, a.name))
    return sorted(out)


def unsynced_writes(tree: ast.AST) -> list[tuple[int, str, str]]:
    r"""路由函数里"写了库但没同步派生索引"的位置：(行, 函数名, 写函数)。"""
    out: list[tuple[int, str, str]] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        writes: list[tuple[int, str]] = []
        synced = False
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            name = _call_name(n)
            if isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                    and n.func.value.id == "store" and name in STORE_WRITES:
                writes.append((n.lineno, name))
            if name in SYNC_CALLS:
                synced = True
        if writes and not synced:
            out.extend((line, fn.name, attr) for line, attr in writes)
    return sorted(out)


def raw_question_writes(tree: ast.AST) -> list[int]:
    r"""路由层自己往 `题目/` 写文件（绕过 store 的指纹/并发/分卷）。

    只看**写入目标**，不看参数文本——台账文件里写「题目：xxx」不是违规。
    """
    out: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in ("write_text", "write_bytes"):
            target = ast.unparse(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        elif name == "open" and node.args:
            mode = ""
            if len(node.args) > 1:
                mode = ast.unparse(node.args[1])
            for kw in node.keywords:
                if kw.arg == "mode":
                    mode = ast.unparse(kw.value)
            if not any(ch in mode for ch in "wax+"):
                continue
            target = ast.unparse(node.args[0])
        else:
            continue
        if "题目" in target:
            out.append(node.lineno)
    return sorted(out)


def silent_broad_handlers(tree: ast.AST) -> list[int]:
    r"""`except Exception: pass` / 裸 `except: pass`（只吞不留痕）。"""
    out: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if not (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
            continue
        t = node.type
        if t is None:
            out.append(node.lineno)
        elif isinstance(t, ast.Name) and t.id in ("Exception", "BaseException"):
            out.append(node.lineno)
    return sorted(out)


def check_text(rel: str, src: str) -> list[str]:
    r"""单一文件的违例清单（自检也复用它）。"""
    tree = ast.parse(src)
    bad: list[str] = []
    if _is_router(rel):
        for line, fn, attr in unsynced_writes(tree):
            bad.append("%s:%d R1 %s() 写库（store.%s）后没同步派生索引"
                       % (rel, line, fn, attr))
        for line in raw_question_writes(tree):
            bad.append("%s:%d R1b 路由层直接写 题目/ 文件" % (rel, line))
    for line, attr in store_writes(tree):
        if _is_ai_module(Path(rel).name):
            bad.append("%s:%d R2 AI 模块调 store.%s()" % (rel, line, attr))
    if Path(rel).name in AUDIT_MODULES:
        for line in silent_broad_handlers(tree):
            bad.append("%s:%d R3 记账路径静默吞异常" % (rel, line))
    return bad


def check() -> list[str]:
    bad: list[str] = []
    for p in sorted(AMTI.rglob("*.py")):
        rel = p.relative_to(AMTI).as_posix()
        if rel.startswith("__pycache__"):
            continue
        try:
            bad.extend(check_text(rel, p.read_text(encoding="utf-8")))
        except SyntaxError as e:            # 解析不了的模块本身就该修
            bad.append("%s: 语法错 %s" % (rel, e))
    return bad


# ── 自检 ──────────────────────────────────────────────────────────────

_SAMPLE = {
    "router": (
        "web/routers/questions.py",
        "from amti import store\n"
        "def f(q):\n"
        "    store.write_one(q, volume=0, expect_hash='x', expect_sig=())\n",
        "R1",
    ),
    "router_raw": (
        "web/routers/questions.py",
        "from pathlib import Path\n"
        "def f():\n"
        "    (Path('题目') / '001.tex').write_text('x', encoding='utf-8')\n",
        "R1b",
    ),
    "ai": (
        "ai_agent.py",
        "import store\n"
        "def f(q):\n"
        "    store.append([q])\n",
        "R2",
    ),
    "audit": (
        "deepseek.py",
        "def f():\n"
        "    try:\n"
        "        boom()\n"
        "    except Exception:\n"
        "        pass\n",
        "R3",
    ),
}

_CLEAN = (
    "web/routers/questions.py",
    "from amti import store\n"
    "def f(q):\n"
    "    store.write_one(q, volume=0, expect_hash='x', expect_sig=())\n"
    "    _rm_apply([q.key], (), {q.key: q})\n",
)


def selftest() -> int:
    fails = 0
    for name, (rel, src, rule) in _SAMPLE.items():
        got = check_text(rel, src)
        if not any(rule in x for x in got):
            print("✗ 自检失败：样本 %s 没被 %s 抓到（得到 %r）" % (name, rule, got))
            fails += 1
    rel, src = _CLEAN
    got = check_text(rel, src)
    if got:
        print("✗ 自检失败：干净样本被误报 %r" % (got,))
        fails += 1
    if fails:
        print("✗ 结构检查自检失败")
        return 1
    print("结构检查自检通过（R1/R2/R3 各抓一例，干净样本不误报）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="结构检查：唯一入口是否为真")
    ap.add_argument("--selftest", action="store_true", help="只跑规则自检")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    bad = check()
    if bad:
        for x in bad:
            print("  ✗ " + x)
        print("\n✗ 结构检查未通过：%d 处" % len(bad))
        return 1
    print("结构检查通过（R1 写库同步索引 / R2 AI 只读 / R3 记账不静默）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
