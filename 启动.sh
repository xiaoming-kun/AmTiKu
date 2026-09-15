#!/bin/bash
# AmTiKu 题库 · 一键启动
#
# 三样东西：
#   ① 题库服务   http://127.0.0.1:8899     ← 浏览器打开这个
#   ② 本地模型   LM Studio :1234           ← 求解题目要用
#   ③ 求解任务   逐题解模拟题，一道一写
#
# 平时不用直接跑这个脚本——装好的全局命令更省事：
#   AmTiKu 启动      AmTiKu 状态      AmTiKu 停止
#
# 用法：
#   ./启动.sh            只起题库服务（求解器**不会**被自动拉起）
#   ./启动.sh web        只起题库服务
#   ./启动.sh solve      只起求解任务
#   ./启动.sh status     看现在跑着什么
#   ./启动.sh stop       全停

cd "$(dirname "$0")" || exit 1

# ── PROJECT PYTHON ────────────────────────────────────────────────
# **项目自带的 Python。**
#
# 依赖（fastapi/uvicorn/pymupdf/numpy/pillow）装在项目内的 `.venv/`，
# 不用系统或用户级的 site-packages —— 换台机器、或者系统 Python 升级了，
# 这个项目照样能跑。`.venv` 不在就退回 `python3`（老行为），
# 只是会依赖外面装了什么。
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

PORT=8899
export PATH="$HOME/.lmstudio/bin:$PATH"

c_ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
c_bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; }
c_info() { printf "    %s\n" "$1"; }

web_up()   { pgrep -f "amti\.web\.server" >/dev/null; }
lm_up()    { curl -s --max-time 2 -o /dev/null http://127.0.0.1:1234/v1/models; }
solve_up() { pgrep -f "amti.solve" >/dev/null; }

start_lm() {
  if lm_up; then c_ok "本地模型已在跑（:1234）"; return; fi
  if ! command -v lms >/dev/null; then
    c_bad "没装 LM Studio 的命令行工具 lms —— 求解功能用不了"
    c_info "题库本身不受影响，可以先只跑 web"
    return
  fi
  lms server start >/dev/null 2>&1
  sleep 3
  if lm_up; then c_ok "本地模型已启动（:1234）"; else c_bad "本地模型起不来"; fi
}

# `AMTI_HEADLESS=1` 时不自动开浏览器、也不随页面退出——
# 给脚本/后台用。默认是**窗口模式**：开浏览器，关浏览器就退出。
start_web() {
  if web_up; then
    c_ok "题库服务已在跑"
    # **已经在跑也要把浏览器打开**。
    # 早先这里直接 return，于是「服务本来就在跑、但页面没开」时
    # 敲 AmTiKu 毫无反应——用户看到的就是"没反应、不弹浏览器"。
    if [ -z "$AMTI_HEADLESS" ]; then
      open "http://127.0.0.1:$PORT" 2>/dev/null && c_ok "已打开浏览器"
    fi
    return
  fi
  # 端口可能被上一个还没退干净的进程占着，等一等
  for _ in $(seq 1 20); do
    "$PY" - <<'PY' 2>/dev/null && break
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", $PORT)); s.close()
except OSError:
    sys.exit(1)
PY
    sleep 0.5
  done
  : > /tmp/amti_web.log          # 清空日志：新旧混在一起会看花眼
  if [ -n "$AMTI_HEADLESS" ]; then
    nohup "$PY" -u -m amti.web.server --port $PORT >> /tmp/amti_web.log 2>&1 &
    c_info "无头模式（不会自动开浏览器，也不会随页面退出）"
  else
    # `-u` 必须加：输出重定向到文件时 Python 会缓冲，
    # 不加的话日志要等进程结束才出现，等于实时看不了。
    nohup "$PY" -u -m amti.web.server --port $PORT --open --exit-with-browser \
      >> /tmp/amti_web.log 2>&1 &
  fi
  # **轮询等它起来**，不要 sleep 固定秒数就下结论——
  # 机器忙的时候 3 秒不够，会误报"起不来"（实测踩过）。
  for _ in $(seq 1 20); do
    sleep 0.5
    web_up && break
  done
  if web_up; then
    c_ok "题库服务已启动"
    c_info "浏览器打开：http://127.0.0.1:$PORT"
    [ -z "$AMTI_HEADLESS" ] && c_info "关掉页面，服务会自动退出"
  else
    c_bad "题库服务起不来，看日志 /tmp/amti_web.log"
    tail -5 /tmp/amti_web.log | sed 's/^/      /'
  fi
}

start_solve() {
  if solve_up; then c_ok "求解任务已在跑"; return; fi
  if ! lm_up; then c_bad "本地模型没起，先跑 ./启动.sh"; return; fi
  nohup "$PY" -u -m amti.solve > /tmp/amti_solve.log 2>&1 &
  sleep 3
  if solve_up; then
    c_ok "求解任务已启动"
    head -1 /tmp/amti_solve.log | sed 's/^/      /'
  else
    c_bad "求解任务起不来，看 /tmp/amti_solve.log"
  fi
}

case "${1:-all}" in
  web)   start_web ;;
  solve) start_solve ;;
  stop)
    pkill -f "amti.solve" 2>/dev/null && c_ok "求解任务已停" || c_ok "求解任务本来就没跑"
    if pkill -f "amti\.web\.server" 2>/dev/null; then
      # **等它真的死掉、端口真的放开**。不等的话紧接着 start 会撞上
      # "address already in use"，然后误报"起不来"（实测踩过）。
      for _ in $(seq 1 20); do
        sleep 0.5
        web_up || break
      done
      c_ok "题库服务已停"
    else
      c_ok "题库服务本来就没跑"
    fi
    c_info "LM Studio 没动（别的程序可能也在用）"
    ;;
  status)
    echo "AmTiKu 运行状态"
    web_up   && c_ok "题库服务  http://127.0.0.1:$PORT" || c_bad "题库服务没跑"
    lm_up    && c_ok "本地模型  :1234"                 || c_bad "本地模型没跑"
    solve_up && c_ok "求解任务  在跑"                   || c_bad "求解任务没跑"
    echo
    "$PY" - <<'PY' 2>/dev/null
import sys; sys.path.insert(0, '.')
from amti import store
qs = store.load_all()
done = [q for q in qs if q.kind == '模拟' and q.solution.strip()]
print("  库内 %d 道   模拟题已解 %d / %d" % (len(qs), len(done),
      sum(1 for q in qs if q.kind == '模拟')))
PY
    ;;
  all)
    # **默认只起题库服务。**
    #
    # 求解器是个长任务：占着本地模型、占着内存，一跑就是几小时。
    # 早先不带参数会把求解器一起拉起来，用户启动完发现显卡在满载、
    # 却不知道是谁在跑——**长任务应该由人显式发起，不该藏在默认里**。
    # 要跑：`./启动.sh solve`（或 `AmTiKu 求解`）。
    echo "启动 AmTiKu"
    start_lm
    start_web
    if solve_up; then
      c_info "求解任务在跑（停止：./启动.sh stop）"
    else
      c_info "求解任务未启动（要做：./启动.sh solve）"
    fi
    echo
    echo "  浏览器：http://127.0.0.1:$PORT"
    echo "  看状态：AmTiKu 状态"
    echo "  全停：  AmTiKu 停止"
    ;;
  *) echo "用法：./启动.sh [web|solve|stop|status]"; exit 1 ;;
esac
