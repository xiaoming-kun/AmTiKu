#!/usr/bin/env bash
# 按考点重排的知识清单讲义 —— 一键生成 + 编译 + 对账
#
#   ./脚本/考点重排讲义.sh              生成 152 份 tex 并整本编译（两遍出目录）
#   ./脚本/考点重排讲义.sh gen          只生成 tex，不编译（改了选题口径后用）
#   ./脚本/考点重排讲义.sh single 1.1.3 只出一份并编译（调版式时用，几十秒）
#   ./脚本/考点重排讲义.sh pages        打印 main.pdf 页数
#
# 依赖：TeX Live（xelatex + exam-zh + ctex）。全程离线。
#
# ⚠️ 编译退出码不算通过：**日志里有 `!` 就是没通过**（构建成功 ≠ 渲染正确，
#    这个项目在导出上栽过好几次），并且要核对印出来的题数 == 选题数。
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=讲义/考点重排
LOG=/tmp/pointbook_build.log

pdf_pages() {
  python3 -c "import fitz,sys; print(fitz.open(sys.argv[1]).page_count)" "$1" 2>/dev/null || echo '?'
}

echo "① 生成 tex（考点五要素 + 讲解 + 分层选题）"
python3 -m amti.pointbook build || { echo "!! 生成失败"; exit 1; }

if [ "${1:-}" = "gen" ]; then echo "只生成，结束"; exit 0; fi

if [ "${1:-}" = "single" ]; then
  pid="${2:-1.1.3}"
  echo "② 单份编译：$pid"
  python3 -m amti.pointbook single --pid "$pid" >/dev/null
  cp "$OUT/_单点-$pid.tex" "$OUT/_try.tex"
  (cd "$OUT" && xelatex -interaction=nonstopmode _try.tex >"$LOG" 2>&1)
  n=$(grep -c '^!' "$LOG" || true)
  echo "  报错 $n 处，页数 $(pdf_pages "$OUT/_try.pdf")"
  [ "$n" = "0" ] || { grep '^!' -A 3 "$LOG" | head -20; exit 1; }
  exit 0
fi

if [ "${1:-}" = "pages" ]; then
  for f in "$OUT"/卷*.pdf; do echo "$(basename "$f") $(pdf_pages "$f")"; done; exit 0
fi

echo "② 分卷编译（10 卷，每卷两遍出目录）"
# 整本 main.tex 会撑爆 XeTeX 的 main memory（«TeX capacity exceeded»，
# 5,000 多页实测死在第二遍），所以整本产出走分卷。
rm -f /tmp/pb_vol.log
for f in "$OUT"/卷*.tex; do
  base=$(basename "$f" .tex)
  (cd "$OUT" && xelatex -interaction=nonstopmode "$base.tex" >>/tmp/pb_vol.log 2>&1 \
    && xelatex -interaction=nonstopmode "$base.tex" >>/tmp/pb_vol.log 2>&1)
  err=$(grep -c '^!' /tmp/pb_vol.log || true)
  echo "  $base → $(pdf_pages "$OUT/$base.pdf") 页（累计报错 $err 处）"
done
err=$(grep -c '^!' /tmp/pb_vol.log || true)
echo "编译报错合计 $err 处"

echo "③ 对账：印出的题数 vs 选题账"
python3 - <<'PY'
import re, pathlib
from amti import pointbook
sels = pointbook.select_all()
want = sum(sum(len(v) for v in s.taken.values()) for s in sels.values())
got = 0
for f in pathlib.Path("讲义/考点重排/points").glob("*.tex"):
    s = f.read_text(encoding="utf-8")
    got += s.count(r"\begin{question}") + s.count(r"\begin{problem}")
print(f"  选题 {want} 道 ｜ 生成物 {got} 道 ｜ {'✓ 一致' if want == got else '✗ 不一致'}")
PY

[ "$err" = "0" ] || { grep '^!' -A 3 "$LOG" | head -30; exit 1; }
echo "全部通过 → $OUT/卷NN-*.pdf（整本 main.tex 只当索引用）"
