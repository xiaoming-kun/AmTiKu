@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
echo ======== AmTiKu ========
echo.

rem 本文件必须以 GBK(cp936) 编码保存，并在开头 chcp 936：
rem cmd.exe 按系统 ANSI 代码页读 .bat，若存成 UTF-8，中文会被拆坏，
rem 连 "set PYTHONUTF8=1" 里的 set 都会被吃掉（报 "PYTHONUTF8 不是内部或外部命令"）。
rem 中文说明放在 .md 文件里，本文件只做启动。

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [X] 没找到 Python 3.11+
  echo     请到 https://www.python.org/downloads/ 安装
  echo     安装时勾选 "Add python.exe to PATH"
  pause
  exit /b 1
)

if not exist .venv\Scripts\python.exe (
  echo 首次运行：正在创建虚拟环境...
  %PY% -m venv .venv || (echo [X] 创建虚拟环境失败 & pause & exit /b 1)
  echo 正在安装依赖（先用包内离线依赖）...
  set "PIP_USER=0"
  .venv\Scripts\pip install -q --no-user --no-index --find-links 依赖\wheels -r requirements.txt
  if errorlevel 1 (
    echo 离线依赖不匹配，改为联网安装...
    .venv\Scripts\pip install --no-user -r requirements.txt || (echo [X] 安装失败，请检查网络 & pause & exit /b 1)
  )
  echo 依赖就绪。
)

rem 中文路径与题库需要 UTF-8
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist 题目 (
  echo 首次运行：放入 demo 题库...
  xcopy /E /I /Y demo数据\题目 题目 >nul
  xcopy /E /I /Y demo数据\图片 图片 >nul
  copy /Y demo数据\知识点.json 知识点.json >nul
  .venv\Scripts\python amti.py snapshot >nul 2>&1
)

echo.
echo 正在启动题库服务，几秒后自动打开浏览器：
echo     http://127.0.0.1:8899
echo 关掉那个浏览器页面，服务会自动退出。
echo.
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8899"
.venv\Scripts\python -m amti.web.server
echo.
echo 服务已停止。
pause
