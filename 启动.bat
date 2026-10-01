@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PKG=%~dp0"

echo ======== AmTiKu 高中数学题库与组卷系统 ========
echo.

rem 本文件必须以 GBK(cp936) 编码保存，并在开头 chcp 936：
rem cmd.exe 按系统 ANSI 代码页读 .bat，存成 UTF-8 会把中文拆坏。

rem ####################################################################
rem  # 这个脚本**只负责启动**。                                          #
rem  # 找 Python / 装 Python / 建 .venv / 装依赖 —— 一律在 安装环境.bat。  #
rem  # 这里一个都不做：两处各写一份，改一处忘一处，就是以前反复出错的原因。  #
rem ####################################################################

rem 内置 LaTeX 加进 PATH —— 少了它就不会用随包的编译器，转而去找系统 LaTeX，
rem 找不到就报"找不到 xelatex"，白装了一个引擎。
if exist "%~dp0tex\bin\windows" set "PATH=%~dp0tex\bin\windows;%PATH%"
rem 中文路径需要 UTF-8
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem ── 包完整性自检 ────────────────────────────────────────────────────
set "MISSING="
for %%F in (amti.py requirements.txt) do if not exist "%%F" set "MISSING=!MISSING! %%F"
if not exist "tex\bin\windows" set "MISSING=!MISSING! tex\bin\windows"
if not exist "web\dist\index.html" set "MISSING=!MISSING! web\dist\index.html"
if defined MISSING (
  echo [X] 这个文件夹不完整，缺：
  echo     !MISSING!
  echo     多半是解压没解全。请把压缩包**用 7-Zip 完整重新解压一份**，
  echo     不要在压缩包的预览窗口里直接双击里面的文件。
  echo     当前目录： !PKG!
  pause
  exit /b 1
)

rem ── 运行环境就绪检查：**只查，不动手** ───────────────────────────────
if not exist ".venv\Scripts\python.exe" goto :no_env
.venv\Scripts\python.exe -c "import fastapi,uvicorn,fitz,PIL" >nul 2>nul
if errorlevel 1 goto :no_env

rem ── 首次运行：把随包的 demo 题库铺成 题目/ 与 图片/ ──────────────────
if not exist 题目 (
  echo       首次运行：放入 demo 题库……
  xcopy /E /I /Y demo数据\题目 题目 >nul
  xcopy /E /I /Y demo数据\图片 图片 >nul
  copy /Y demo数据\知识点.json 知识点.json >nul
  .venv\Scripts\python amti.py snapshot >nul 2>&1
)

rem ── 启动 ────────────────────────────────────────────────────────────
echo 启动服务，浏览器会自动打开： http://127.0.0.1:8899
echo       关掉浏览器页面，服务会在 25 秒后自动退出。
echo.
.venv\Scripts\python -m amti.web.server --open --exit-with-browser
echo.
echo 服务已停止。
pause
exit /b 0

rem ── 环境没准备好：说清楚该干什么，然后退出（不在这里找 Python）──────
:no_env
echo [X] 运行环境还没准备好。
echo.
echo     请先双击**同一个文件夹里的 安装环境.bat**，
echo     等它显示「[OK] 运行环境已就绪」之后，再回来双击本文件。
echo.
echo     当前目录： !PKG!
pause
exit /b 1
