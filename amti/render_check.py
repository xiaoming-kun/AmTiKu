r"""用项目自带的 KaTeX 真渲染一遍，把"看着没问题、渲染就炸"的公式揪出来。

为什么值得单独做：括号配平、`$` 成对这类启发式只能挡住一部分，
像 `\\frac` 缺参数、未知命令、`\\left` 配错括号类型，规则看不出来，
但 KaTeX 一秒就能告诉我们哪一段炸了。

走 Node（`web/node_modules` 里就有 katex），**一次进程批量校验**，
几十道题也就一两秒。拿不到 node / katex 时静默跳过，不影响主流程。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

_JS = r"""
const katex = require('katex');
let buf = '';
process.stdin.on('data', d => buf += d);
process.stdin.on('end', () => {
  let items = [];
  try { items = JSON.parse(buf); } catch (e) { console.log('[]'); return; }
  const out = items.map(it => {
    const errs = [];
    for (const seg of it.segs || []) {
      try { katex.renderToString(seg, { throwOnError: true, displayMode: false }); }
      catch (e) { errs.push(String(e.message).replace(/^KaTeX parse error:\s*/, '').slice(0, 80)); }
    }
    return { id: it.id, errors: errs.slice(0, 3) };
  });
  console.log(JSON.stringify(out));
});
"""


def _node() -> str | None:
    import shutil
    return shutil.which("node")


def available() -> bool:
    return _node() is not None and (WEB / "node_modules" / "katex").is_dir()


def segments(text: str) -> list[str]:
    """把一段正文里的公式段抠出来（`$…$` 与 `\\[…\\]`）。"""
    out: list[str] = []
    i, n = 0, len(text or "")
    while i < n:
        if text.startswith("\\[", i):
            j = text.find("\\]", i + 2)
            if j < 0:
                break
            out.append(text[i + 2:j])
            i = j + 2
            continue
        if text[i] == "$" and not text.startswith("$$", i):
            j = text.find("$", i + 1)
            if j < 0:
                break
            seg = text[i + 1:j]
            if seg.strip() and "\n" not in seg:
                out.append(seg)
            i = j + 1
            continue
        i += 1
    return out


def check(items: list[dict]) -> dict:
    """`[{id, segs}]` → `{id: [错误信息]}`。跑不了就返回空字典。"""
    if not items or not available():
        return {}
    try:
        r = subprocess.run([_node(), "-e", _JS], cwd=str(WEB),
                           input=json.dumps(items), capture_output=True,
                           text=True, timeout=120)
        data = json.loads(r.stdout or "[]")
        return {d["id"]: d["errors"] for d in data if d.get("errors")}
    except Exception:                                         # noqa: BLE001
        return {}
