#!/bin/bash
# 其他杂项转录 · **收尾**：扫描一跑完就自动把剩下的全部做完。
#
# 顺序（**不能乱**，见 其他杂项录题.py 的 `finish`）：
#   boxes（找带图页的包围盒，**需要模型服务**）→ figs（裁图）→ build（27 个 .tex）
#   → verify（体检）→ audit（明账）→ KaTeX → xelatex 出 PDF
#
# 用法：
#   bash 脚本/其他杂项收尾.sh            # 扫完会自动被看门狗调用，也可手工跑
#   bash 脚本/其他杂项收尾.sh --dry      # 只打印要做什么，不动手
set -u
cd "$(dirname "$0")/.."

PY=.venv/bin/python
BACKEND="$HOME/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.46.0"
GGUF="$HOME/.lmstudio/models/lmstudio-community/Qwen3.8-27B-GGUF"
PORT="${AMTI_API_PORT:-1235}"
export AMTI_API_PORT="$PORT"
LOG=/tmp/zlx/logs
mkdir -p "$LOG"

if [ "${1:-}" = "--dry" ]; then
  echo "会依次执行：boxes → figs → build → verify → audit → KaTeX → 出 PDF"
  exit 0
fi

# ── 模型服务：`boxes` 要问模型"图在哪"，所以必须有一个 ──────────────
# ⚠️ 这段和 `其他杂项跑批.sh` 里的 `start_server` 是**同一套参数，但是独立的一份**。
#    不是偷懒重复：**bash 是边读边执行脚本文件的**，跑批脚本可能正在跑，
#    改它会让运行中的实例从错误偏移继续读、行为错乱（实测踩过一次的同类问题）。
#    等哪天跑批停了，应该把这段抽成一个共用片段。
server_up() {
  curl -s --max-time 3 "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | grep -q '"id"'
}
stop_server() {
  pkill -9 -f "llama-server.*--port $PORT" 2>/dev/null
  for _ in $(seq 1 30); do pgrep -f "llama-server.*--port $PORT" >/dev/null || break; sleep 1; done
}
start_server() {
  stop_server
  # ⚠️ 变量后面**紧跟全角括号**（不加花括号）会被 bash 当成**变量名的一部分**
  # （报 `PORT<乱码>: unbound variable`）—— 相邻非 ASCII 一律用 `${}` 包起来。
  # 这条警告就在 `跑批.sh` 的注释里躺着，我还是在收尾脚本里又犯了一次：
  # **实测** 看门狗自动收尾时，收尾脚本第 41 行挂掉、整条收尾链断在这里。
  echo "[$(date '+%H:%M:%S')] 起服务 :${PORT}（boxes 要用）"
  ( cd "$BACKEND" && DYLD_LIBRARY_PATH="$BACKEND" nohup caffeinate -dimsu \
      "$BACKEND/llama-server" \
      -m "$GGUF/Qwen3.8-27B-Q6_K.gguf" --mmproj "$GGUF/mmproj-Qwen3.8-27B-BF16.gguf" \
      --host 127.0.0.1 --port $PORT -c 32768 -np 4 -ngl 99 --no-webui \
      >> "$LOG/server.log" 2>&1 & )
  for _ in $(seq 1 90); do
    sleep 3
    server_up && { sleep 2; return 0; }
  done
  echo "服务起不来，看 $LOG/server.log"; return 1
}

echo "════ 收尾开始 $(date '+%m-%d %H:%M:%S') ════"

if server_up; then
  echo "  服务已在跑，直接用"
else
  start_server || exit 1
fi

# ① boxes：**按文件跑，每个文件之间重启一次服务**。
# 为什么不能一次跑完：跑批那边的做法是**每 60 页重启服务**，理由是项目记的
# 坑 3（`-c 65536` 跑一阵后 prompt eval 从 50 秒/页涨到 966 秒/页）。
# `boxes` 只处理带图页（粗算全批约 86 页），一次跑完没有那道保险；
# 按文件切、文件之间重启，代价是 27 次服务启动（约 20 分钟），
# 换的是"不会跑到一半整段退化成 966 秒/页、然后卡在半夜"。
echo "── boxes（按文件，逐个重启服务）"
box_rc=0
"$PY" - <<'EOF' > "$LOG/boxplan.txt"
import sys, importlib.util
sys.path.insert(0, '.'); sys.path.insert(0, '脚本')
spec = importlib.util.spec_from_file_location("m", "脚本/其他杂项录题.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for f in m.list_files():
    print(f["slug"])
EOF
while IFS= read -r slug; do
  [ -z "$slug" ] && continue
  server_up || start_server || { box_rc=1; break; }
  echo "[$(date '+%H:%M:%S')] boxes：${slug}"
  "$PY" -u 脚本/其他杂项录题.py boxes --file "$slug" 2>&1 | tee -a "$LOG/finish.log"
  rc=${PIPESTATUS[0]}
  [ "$rc" -ne 0 ] && box_rc=$rc
  stop_server
done < "$LOG/boxplan.txt"

# ② 其余一条龙：figs → build → verify（boxes 已缓存，`finish` 里会跳过）
# ⚠️ 循环里每个文件跑完都 `stop_server` 了，而 `finish` 里**还会再调一次
# `boxes`** —— 万一有没缓存的页（比如上面某个文件失败了），它会连不上服务。
# 所以这里先把服务点起来；`boxes` 全部命中缓存的话它一次请求都不会发。
echo "── figs → build → verify"
server_up || start_server || echo "  ⚠ 服务起不来；boxes 若有漏页会失败（会在下面报出来）"
"$PY" -u 脚本/其他杂项录题.py finish 2>&1 | tee -a "$LOG/finish.log"
fin_rc=$(( box_rc | ${PIPESTATUS[0]} ))

# ③ 明账（要人工看哪些）
"$PY" -u 脚本/其他杂项录题.py audit 2>&1 | tee -a "$LOG/finish.log"

# ④ KaTeX：与前端同一条路
echo "── KaTeX 校验"
node 脚本/赵礼显讲义KaTeX.mjs 数据/录题/其他杂项/out 2>&1 | tee -a "$LOG/finish.log"
katex_rc=${PIPESTATUS[0]}

# ⑤ xelatex：出可直接编译的文档 + PDF（最强证据）
echo "── xelatex 出 PDF"
"$PY" 脚本/赵礼显讲义出卷.py --work 数据/录题/其他杂项 --compile 2>&1 | tee -a "$LOG/finish.log"
tex_rc=${PIPESTATUS[0]}

stop_server
echo "════ 收尾结束 $(date '+%m-%d %H:%M:%S') ════"
echo "  finish=$fin_rc  katex=$katex_rc  xelatex=$tex_rc"
echo "  产物：数据/录题/其他杂项/out/（.tex）、预览/（.pdf）、明账.md"
exit $(( fin_rc | katex_rc | tex_rc ))
