@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PKG=%~dp0"
echo ======== AmTiKu 高中数学题库与组卷系统 ========
echo.

rem 本文件必须以 GBK(cp936) 编码保存，并在开头 chcp 936：
rem cmd.exe 按系统 ANSI 代码页读 .bat，存成 UTF-8 会把中文拆坏。

rem 内置 LaTeX 加进 PATH —— 少了它就不会用随包的编译器，转而去找系统 LaTeX，
rem 找不到就报"找不到 xelatex"，白装了一个引擎。
if exist "%~dp0tex\bin\windows" set "PATH=%~dp0tex\bin\windows;%PATH%"
rem 中文路径需要 UTF-8
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem ── 包完整性自检 ────────────────────────────────────────────────────
rem 解压没解全（或在压缩包窗口里直接双击）时，后面会报一堆看不懂的错。
rem 这里先查关键文件，缺哪个列哪个，并直接告诉用户怎么办。
set "MISSING="
for %%F in (amti.py requirements.txt) do if not exist "%%F" set "MISSING=!MISSING! %%F"
if not exist "tex\bin\windows" set "MISSING=!MISSING! tex\bin\windows"
if not exist "web\dist\index.html" set "MISSING=!MISSING! web\dist\index.html"
if not exist "依赖\wheels" set "MISSING=!MISSING! 依赖\wheels"
if defined MISSING (
  echo [X] 这个文件夹不完整，缺：
  echo     !MISSING!
  echo     多半是解压没解全。请把压缩包**用 7-Zip 完整重新解压一份**，
  echo     不要在压缩包的预览窗口里直接双击里面的文件。
  echo     当前目录： !PKG!
  pause
  exit /b 1
)


rem ══ 1/3  运行环境（优先复用包内现成的 .venv）════════════════════════
call :venv_or_make
if errorlevel 1 goto need_python
if defined VENV_NEW (
  echo [1/3] 已找到 Python !PY!，新建运行环境 .venv
) else (
  echo [1/3] 用包内已建好的运行环境（.venv）
)
.venv\Scripts\python -c "import fastapi,uvicorn,fitz,PIL" >nul 2>nul
if errorlevel 1 (
  echo       运行环境里缺依赖，正在用包里的 wheel 补装（不用联网）……
  call :pip_install
)
goto data_ready

:need_python
echo [1/3] 这台机器上没有 Python 3.11 或更高版本，改用包里自带的安装包……
call :install_bundled_python
if errorlevel 1 goto no_python
echo [2/3] 首次运行：正在准备运行环境，约 1~2 分钟，不用联网……
call :venv_or_make
if errorlevel 1 goto venv_failed
call :pip_install

:data_ready
rem 首次运行：把随包的 demo 题库铺成 题目/ 与 图片/
if not exist 题目 (
  echo       首次运行：放入 demo 题库……
  xcopy /E /I /Y demo数据\题目 题目 >nul
  xcopy /E /I /Y demo数据\图片 图片 >nul
  copy /Y demo数据\知识点.json 知识点.json >nul
  .venv\Scripts\python amti.py snapshot >nul 2>&1
)

rem ══ 3/3  启动 ════════════════════════════════════════════════════════
echo [3/3] 启动服务，浏览器会自动打开： http://127.0.0.1:8899
echo       关掉浏览器页面，服务会在 25 秒后自动退出。
echo.
.venv\Scripts\python -m amti.web.server --open --exit-with-browser
echo.
echo 服务已停止。
pause
exit /b 0

rem ═══════════════════════════════════════════════════════════════════════
rem  公共子过程（启动.bat / 1-安装依赖.bat / 2-起服务.bat 共用，改要一起改）
rem
rem  坑一：**带引号的通配符在 cmd 里不展开**
rem        if exist "…\python-*.exe"     → 恒为假（实测）
rem        for %%I in ("…\python-*.exe") → 一次都不循环
rem        而路径含中文/空格必须加引号。所以列文件只能用
rem        `dir /b /a-d "…\python-*.exe"` —— dir 支持引号内通配符。
rem
rem  坑二：**`where python` 不等于"有 Python"**
rem        Windows 应用商店的 WindowsApps\python.exe 是占位程序，
rem        where 找得到、跑起来只弹商店（退出码 9009）。
rem        所以判据一律是「真跑一次、看退出码」，并显式跳过商店别名。
rem
rem  坑三：判版本别解析 stdout
rem        `sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)`
rem        用退出码说话，
rem        少一层引号嵌套。
rem        窗口是**恰好 3.11/3.12/3.13，不是 >=3.11**：随包 wheel 只到 cp313，
rem        放 3.14 进来会让离线安装必然失败（3.14+ 由 :try_any 兜底）。
rem ═══════════════════════════════════════════════════════════════════════

rem ── :venv_or_make ── 有能用的 .venv 就直接用；否则找一个 Python 建一个
rem    成功：RUNPY 已设好，exit /b 0；新建时另设 VENV_NEW=1
rem    失败（找不到 Python）：exit /b 1
:venv_or_make
set "VENV_NEW="
set "RUNPY="
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "RUNPY=.venv\Scripts\python.exe"
    exit /b 0
  )
  echo       ^(包内的 .venv 已经用不了，重新建一个^)
  rmdir /s /q ".venv" >nul 2>nul
)
rem 【重要】**`python -m venv` 返回 0 不等于建成功。**
rem    MSYS2 / Cygwin 的 Python 会把它造成 Unix 布局（bin\ 而不是 Scripts\），
rem    拷 launcher 失败却仍然退出 0；于是流程一路往下走，最后 pip 报
rem    "系统找不到指定的路径" —— 真正的原因被埋掉，用户完全看不懂（实测踩到）。
rem    所以判据是**真跑一次 .venv\Scripts\python.exe**：不行就把这个 Python
rem    拉黑（BADPY）再试下一个，全都不行才回落「装包里自带的 Python」。
rem  **重试上限**：黑名单再出岔子也绝不许无限循环 ——
rem  死循环比报错难查得多（用户只看到同一句话刷屏，不知道卡在哪）。
set /a VTRY=0
:vm_retry
set /a VTRY+=1
if !VTRY! gtr 8 exit /b 1
call :find_python
if not defined PY exit /b 1
echo       正在用 !PY! 建运行环境 .venv ……
if exist ".venv" rmdir /s /q ".venv" >nul 2>nul
%PY% -m venv .venv >nul 2>nul
rem  用**标志变量**判，别用 errorlevel：文件不存在时 `if exist` 后面那条命令
rem  根本不执行，errorlevel 会保留 `python -m venv` 的退出码 —— 而 MSYS2 的
rem  Python 造出残废布局**退出码仍是 0**，那样会把残废 venv 当成成功（踩过）。
set "VENVOK="
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import sys" >nul 2>nul
  if not errorlevel 1 set "VENVOK=1"
)
if defined VENVOK (
  set "RUNPY=.venv\Scripts\python.exe"
  set "VENV_NEW=1"
  exit /b 0
)
echo       ^(这个 Python 建不出可用的运行环境，换下一个^)
rem  【关键】黑名单必须**累积成列表**。原来写的是 set "BADPY=!PY!" ——
rem  那是个单值，第二次失败就把上一次覆盖掉，于是 python / python3
rem  来回对倒、**无限循环**（实测踩到）。
rem  统一存**不带引号**的形式：:try_exe 传进来的是带引号的路径。
set "_B=!PY!"
set "_B=!_B:"=!"
set "BADPY=!BADPY!|!_B!|"
goto vm_retry

:find_python
set "PY="
call :try_cmd "py -3.13"
if not defined PY call :try_cmd "py -3.12"
if not defined PY call :try_cmd "py -3.11"
if not defined PY call :try_where "python"
if not defined PY call :try_where "python3"
if not defined PY call :scan_dirs
rem ── 兜底：3.14 及以上 ──────────────────────────────────────────────
rem    它们**不在随包 wheel 的覆盖范围内**（wheel 只到 cp313），离线装不上，
rem    但本身能跑 —— 所以放在最后，用上了就走 :pip_install 里那条联网退路。
rem    少了这一条，一台只装了 3.14 的机器会被误判成「没有 Python」。
if not defined PY call :try_any "py -3"
if not defined PY call :try_any "python"
if not defined PY call :try_any "python3"
exit /b 0

rem ── :is_bad ── 入参是否已经失败过；在黑名单里则 errorlevel 0
rem    用 find 判子串。**不能用 !VAR:搜=替!** —— Python 路径里有冒号，
rem    那套语法会在第一个冒号处截断，判出错误结果。
rem    两边都加 | 当定界符，这样 python 不会误命中 python3。
:is_bad
if not defined BADPY exit /b 1
echo "!BADPY!"| find /i "|%~1|" >nul
exit /b 0

rem ── :try_any ── 同 :try_cmd，但只要求 >=3.11（不设版本上限）
:try_any
set "_T=%~1"
rem  **应用商店的占位程序**（WindowsApps\python.exe）被调用时**退出码是 0**，
rem  于是下面那条版本检查"通过"、PY 被设成 python，直到建 venv 时才炸。
rem  :try_where 早挡过它，但这里直接执行命令名、绕过了 where，得再挡一次。
set "_S="
rem  只在参数是**单个命令名**（不含空格）时才查 where；"py -3" 这种带参数的不查。
if "!_T: =!"=="!_T!" for /f "delims=" %%w in ('where !_T! 2^>nul') do if not defined _S set "_S=%%w"
if defined _S if not "!_S:WindowsApps=!"=="!_S!" (
  echo       ^(跳过应用商店占位程序：!_S!^)
  exit /b 0
)
call :is_bad "!_T!"
if not errorlevel 1 exit /b 0
%_T% -c "import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%_T%"
exit /b 0


rem ── :try_cmd ── 参数是能直接执行的命令串，如 "py -3.13"
:try_cmd
set "_T=%~1"
call :is_bad "!_T!"
if not errorlevel 1 exit /b 0
%_T% -c "import sys;sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%_T%"
exit /b 0

rem ── :try_where ── 只在 where 命中的**第一个**不是商店占位程序时才试
:try_where
set "_W="
for /f "delims=" %%w in ('where %~1 2^>nul') do if not defined _W set "_W=%%w"
if not defined _W exit /b 0
if not "!_W:WindowsApps=!"=="!_W!" exit /b 0
call :try_cmd "%~1"
exit /b 0

rem ── :scan_dirs ── PATH 里没有、但机器上装了（安装时没勾 Add to PATH）也能找到
:scan_dirs
call :scan_in "%LOCALAPPDATA%\Programs\Python"
call :scan_in "%ProgramFiles%"
call :scan_in "%ProgramFiles(x86)%"
call :scan_in "C:\"
exit /b 0

:scan_in
for /f "delims=" %%D in ('dir /b /ad "%~1\Python3*" 2^>nul') do if not defined PY if exist "%~1\%%D\python.exe" call :try_exe "%~1\%%D\python.exe"
exit /b 0

:try_exe
set "_E=%~1"
call :is_bad "!_E!"
if not errorlevel 1 exit /b 0
"%_E%" -c "import sys;sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)" >nul 2>nul
if not errorlevel 1 set "PY="%_E%""
exit /b 0

rem ── :install_bundled_python ── 用包里自带的官方安装包静默装（per-user，免管理员）
rem    成功：PY 已设好，exit /b 0；包里没有安装包或装完还找不到：exit /b 1
:install_bundled_python
set "PYEXE="
for /f "delims=" %%I in ('dir /b /a-d "!PKG!依赖\python-*-amd64.exe" 2^>nul') do if not defined PYEXE set "PYEXE=!PKG!依赖\%%I"
if not defined PYEXE exit /b 1
echo       正在自动安装随包带的 Python（只装给当前用户，不需要管理员权限）……
echo       安装包： !PYEXE!
"!PYEXE!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0 Shortcuts=0
rem 装的是 per-user 版，当前进程的 PATH 不会自己刷新 —— 所以下面直接扫目录找
echo       安装结束（退出码 !errorlevel!），重新检测……
call :find_python
if not defined PY call :try_cmd "py -3"
if not defined PY exit /b 1
exit /b 0

rem ── :pip_install ── 装依赖：先用包里的 wheel（不联网），不行再联网
:pip_install
.venv\Scripts\python -m pip install -q --no-index --find-links "!PKG!依赖\wheels" -r requirements.txt
if not errorlevel 1 exit /b 0
echo       包里的 wheel 没装上，改为联网安装……
.venv\Scripts\python -m pip install -q -r requirements.txt
if errorlevel 1 goto deps_failed
exit /b 0

rem ── 收尾：失败时的说明 ─────────────────────────────────────────────
:no_python
echo.
echo [X] 这台机器上没有 Python 3.11 或更高版本，包里也没能自动装上。
echo     当前目录： !PKG!
echo     PATH 里能找到的 python / py：
where python 2>nul || echo       ^(没有 python^)
where py 2>nul || echo       ^(没有 py^)
echo     提示：如果上面出现 WindowsApps\python.exe，那是**应用商店的占位程序**，
echo     不是真的 Python（运行只会弹商店），请按下面地址装一个真正的。
echo     下载： https://www.python.org/downloads/
echo           国内镜像（快）： https://mirrors.huaweicloud.com/python/
echo     版本： 3.11 / 3.12 / 3.13 都行；安装时**务必勾上 “Add python.exe to PATH”**。
pause
exit /b 1

:venv_failed
echo [X] 创建运行环境 .venv 失败。
pause
exit /b 1

:deps_failed
echo [X] 依赖安装失败。检查网络后重试，或双击 Windows一键脚本\1-安装依赖.bat。
pause
exit /b 1
