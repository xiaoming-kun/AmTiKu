@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PKG=%~dp0"

echo ======== AmTiKu 高中数学题库与组卷系统 ========
echo.
echo [ 准备运行环境 ]
echo.
echo 这个脚本**只准备运行环境**，不启动程序。它会：
echo     找 Python  ^>  建 .venv  ^>  装依赖  ^>  自检
echo 装完请双击 **启动.bat** 打开程序。
echo.

rem 本文件必须以 GBK(cp936) 编码保存，并在开头 chcp 936：
rem cmd.exe 按系统 ANSI 代码页读 .bat，存成 UTF-8 会把中文拆坏。

rem ── 包完整性自检 ────────────────────────────────────────────────────
rem 解压没解全时，后面会报一堆看不懂的错。先查关键文件。
set "MISSING="
for %%F in (amti.py requirements.txt) do if not exist "%%F" set "MISSING=!MISSING! %%F"
if not exist "依赖\wheels" set "MISSING=!MISSING! 依赖\wheels"
if not exist "demo数据" set "MISSING=!MISSING! demo数据"
if defined MISSING (
  echo [X] 这个文件夹不完整，缺：
  echo     !MISSING!
  echo     多半是解压没解全。请把压缩包**用 7-Zip 完整重新解压一份**，
  echo     不要在压缩包的预览窗口里直接双击里面的文件。
  echo     当前目录： !PKG!
  pause
  exit /b 1
)

rem ══ 0  先检查：已经就绪就**什么都不做**，直接退出 ══════════════════
rem    这一步让本脚本可以随便重复双击 —— 环境好了它就是个"检查器"，
rem    不会再去装一遍依赖、更不会重建 .venv。装环境是**一次性**的事。
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import fastapi,uvicorn,fitz,PIL,numpy" >nul 2>nul
  if not errorlevel 1 goto :already
)

rem ══ 1/3  运行环境 ═══════════════════════════════════════════════════
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    echo [1/3] .venv 可用，只是缺依赖，跳过创建
    goto :deps
  )
  echo [1/3] 包内的 .venv 在这台机器上用不了，重新建一个
  rmdir /s /q ".venv" >nul 2>nul
) else (
  echo [1/3] 还没有 .venv，开始创建
)

call :make_venv
if not errorlevel 1 goto :deps

echo.
echo       本机没有现成可用的 Python（3.11 / 3.12 / 3.13），
echo       改用包里自带的安装包装一个（只装给当前用户，不需要管理员）。。
echo.
call :install_bundled
if errorlevel 1 goto :fail_python
call :make_venv
if errorlevel 1 goto :fail_venv

rem ══ 2/3  依赖 ═══════════════════════════════════════════════════════
:deps
echo [2/3] 安装依赖（优先用包里的 wheel，不需要联网）……
.venv\Scripts\python -m pip install -q --no-index --find-links "!PKG!依赖\wheels" -r requirements.txt >nul 2>nul
if not errorlevel 1 goto :verify
echo       包里的 wheel 没装上，改为联网安装……
.venv\Scripts\python -m pip install -q -r requirements.txt
if errorlevel 1 goto :fail_deps

rem ══ 3/3  自检 ═══════════════════════════════════════════════════════
:verify
echo [3/3] 自检运行环境……
.venv\Scripts\python -c "import fastapi,uvicorn,fitz,PIL,numpy" >nul 2>nul
if errorlevel 1 goto :fail_deps

:already
echo.
echo ================================================================
echo  [OK] 运行环境已就绪。
echo       以后只需要双击 **启动.bat**，本脚本不用再跑。
echo ================================================================
echo.
pause
exit /b 0


rem ═══════════════════════════════════════════════════════════════════════
rem  以下子过程是**运行环境的唯一实现**。
rem  启动.bat 里不再重复这套逻辑 —— 原来两个文件各抄一份，改一处忘一处
rem  （python/python3 死循环那个 bug 就是只在其中一份上暴露的）。
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
rem        用退出码说话：sys.exit(0 if … else 1)，少一层引号嵌套。
rem        窗口是**恰好 3.11/3.12/3.13，不是 >=3.11**：随包 wheel 只到 cp313，
rem        放 3.14 进来会让离线安装必然失败（3.14+ 由 :try_any 兜底）。
rem ═══════════════════════════════════════════════════════════════════════

rem ── :make_venv ── 挨个试 Python，建出**真能用**的 .venv
rem    成功 exit /b 0；全都不行 exit /b 1
rem
rem    【重要】`python -m venv` 返回 0 **不等于**建成功。
rem    MSYS2 / Cygwin 的 Python 会把它造成 Unix 布局（bin\ 而不是 Scripts\），
rem    拷 launcher 失败却仍然退出 0；于是流程一路往下走，最后 pip 报
rem    "系统找不到指定的路径" —— 真正的原因被埋掉，用户完全看不懂（实测踩到）。
rem    所以判据是**真跑一次 .venv\Scripts\python.exe**：不行就把这个 Python
rem    拉黑再试下一个，全都不行才回落「装包里自带的 Python」。
:make_venv
set "BADPY="
set /a VTRY=0
:vm_retry
set /a VTRY+=1
rem  **重试上限**：黑名单再出岔子也绝不许无限循环 ——
rem  死循环比报错难查得多（用户只看到同一句话刷屏，不知道卡在哪）。
if !VTRY! gtr 8 exit /b 1
call :find_python
if not defined PY exit /b 1
echo       正在用 !PY! 建运行环境 .venv ……
if exist ".venv" rmdir /s /q ".venv" >nul 2>nul
%PY% -m venv .venv >nul 2>nul
rem  用**标志变量**判，别用 errorlevel：文件不存在时 `if exist` 后面那条命令
rem  根本不执行，errorlevel 会保留 `python -m venv` 的退出码 —— 而残废布局
rem  的退出码仍是 0，那样会把残废 venv 当成成功（踩过）。
set "VENVOK="
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import sys" >nul 2>nul
  if not errorlevel 1 set "VENVOK=1"
)
if defined VENVOK exit /b 0
echo       ^(这个 Python 建不出可用的运行环境，换下一个^)
rem  【关键】黑名单必须**累积成列表**。原来写的是 set "BADPY=!PY!" ——
rem  那是单值，第二次失败就把上一次覆盖掉，于是 python / python3 来回对倒、
rem  **无限循环**（实测踩到）。统一存**不带引号**的形式：:try_exe 传的是带引号路径。
set "_B=!PY!"
set "_B=!_B:"=!"
set "BADPY=!BADPY!|!_B!|"
goto vm_retry

rem ── :is_bad ── 入参是否已经失败过；在黑名单里则 errorlevel 0
rem    用 find 判子串。**不能用 !VAR:搜=替!** —— Python 路径里有冒号，
rem    那套语法会在第一个冒号处截断，判出错误结果。
rem    两边都加 | 当定界符，这样 python 不会误命中 python3。
:is_bad
if not defined BADPY exit /b 1
echo "!BADPY!"| find /i "|%~1|" >nul
exit /b 0

rem ── :find_python ── 设 PY；找不到就留空
:find_python
set "PY="
call :try_cmd "py -3.13"
if not defined PY call :try_cmd "py -3.12"
if not defined PY call :try_cmd "py -3.11"
if not defined PY call :try_where "python"
if not defined PY call :try_where "python3"
if not defined PY call :scan_dirs
rem  ── 兜底：3.14 及以上 ──
rem     不在随包 wheel 的覆盖范围内（wheel 只到 cp313），离线装不上，
rem     但它们本身能跑 —— 放在最后，用上了就走上面联网装依赖那条退路。
rem     少了这一条，一台只装了 3.14 的机器会被误判成「没有 Python」。
if not defined PY call :try_any "py -3"
if not defined PY call :try_any "python"
if not defined PY call :try_any "python3"
exit /b 0

rem ── :try_any ── 只要求 >=3.11（不设版本上限）
:try_any
set "_T=%~1"
call :is_bad "!_T!"
if not errorlevel 1 exit /b 0
rem  **应用商店的占位程序**（WindowsApps\python.exe）被调用时**退出码是 0**，
rem  于是下面那条版本检查"通过"、PY 被设成 python，直到建 venv 时才炸。
rem  :try_where 早挡过它，但这里直接执行命令名、绕过了 where，得再挡一次。
set "_S="
if "!_T: =!"=="!_T!" for /f "delims=" %%w in ('where !_T! 2^>nul') do if not defined _S set "_S=%%w"
if defined _S if not "!_S:WindowsApps=!"=="!_S!" (
  echo       ^(跳过应用商店占位程序：!_S!^)
  exit /b 0
)
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

rem ── :install_bundled ── 用包里自带的官方安装包静默装（per-user，免管理员）
rem    成功（装完能找到能用的 Python）：exit /b 0
:install_bundled
set "PYEXE="
for /f "delims=" %%I in ('dir /b /a-d "!PKG!依赖\python-*-amd64.exe" 2^>nul') do if not defined PYEXE set "PYEXE=!PKG!依赖\%%I"
if not defined PYEXE (
  echo       ^(包里没有 Python 安装包^)
  exit /b 1
)
echo       安装包： !PYEXE!
"!PYEXE!" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0 Include_doc=0 Shortcuts=0
set "RC=!errorlevel!"
echo       安装结束（退出码 !RC!），重新检测……
rem  装的是 per-user 版，当前进程的 PATH 不会自己刷新 —— 所以直接扫目录找
call :find_python
if defined PY exit /b 0
call :try_cmd "py -3"
if defined PY exit /b 0
echo.
if "!RC!"=="0" (
  echo [X] Python 装上了，但**新装的解释器跑不起来**。
  echo     最常见的原因：注册表里 `PythonPath` 还指向一个已经被删掉的目录，
  echo     于是任何 3.13 一启动就报 `Fatal Python error: Failed to import encodings`。
  echo     排查命令（在 PowerShell 里跑）：
  echo         reg query "HKCU\Software\Python\PythonCore\3.13\PythonPath"
  echo     若指向的目录已不存在，把它删掉即可。
) else (
  echo [X] 随包 Python 安装失败（退出码 !RC!）。
  echo     1603 = 系统里**残留着旧的 Python 安装记录**，Windows 于是走了
  echo     「修复」而不是「安装」，但那些文件早没了，修复必然失败。
  echo     办法：「设置 ^> 应用 ^> 已安装的应用」里卸载所有 Python，再重跑本脚本。
)
exit /b 1

rem ── 失败时的说明 ─────────────────────────────────────────────────────
:fail_python
echo.
echo ================================================================
echo  [X] 这台机器上没有可用的 Python，包里也没能自动装上。
echo      当前目录： !PKG!
echo.
echo      也可以自己装一个（3.11 / 3.12 / 3.13 都行）：
echo        官网：   https://www.python.org/downloads/
echo        国内镜像：https://mirrors.huaweicloud.com/python/
echo      安装时**务必勾上 “Add python.exe to PATH”**，装完重跑本脚本。
echo ================================================================
pause
exit /b 1

:fail_venv
echo.
echo [X] 找到了 Python，但它建不出可用的 .venv。
echo     把上面几行「正在用 … 建运行环境」的报错截图，便于排查。
pause
exit /b 1

:fail_deps
echo.
echo [X] 依赖安装失败。
echo     先确认网络是否正常；仍不行就删掉 .venv 后重跑本脚本。
pause
exit /b 1
