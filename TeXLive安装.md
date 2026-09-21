# 安装 LaTeX（导出试卷 / 讲义 PDF 用）

> **只有"导出 PDF"需要它。** 浏览、搜索、编辑、组卷、预览都不需要 LaTeX，
> 没装也能正常用——导出时程序会提示"找不到 xelatex"，其余功能不受影响。

程序调用的是命令行里的 **`xelatex`**。装好之后**重启一次题库服务**即可。

---

## 一、macOS

### 方案 A：BasicTeX（推荐，约 100MB）

体积小、装得快，缺的宏包再按需补。

1. 下载：<https://tug.org/mactex/more-packages.html> → **BasicTeX**
   （国内镜像更快：<https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/mac/mactex/> 里找 `mactex-basictex-*.pkg`）
2. 双击安装（需要输入开机密码）
3. 装本项目用到的宏包（终端里执行，约 200–400MB）：

```bash
sudo tlmgr update --self
sudo tlmgr install exam-zh ctex xecjk unicode-math newcomputermodern stix2-otf \
                   pgfplots siunitx varwidth tikzpagenodes environ trimspaces
```

4. 验证：`which xelatex && xelatex --version`

### 方案 B：MacTeX 完整版（约 5GB，一次到位）

<https://tug.org/mactex/mactex-download.html> 下载 `.pkg` 双击安装。
装完什么宏包都有，不用再 `tlmgr install`。

> 换镜像（下载慢时）：把地址里的 `tug.org` 换成
> `mirrors.tuna.tsinghua.edu.cn/CTAN`。

---

## 二、Windows

### 方案 A：MiKTeX（推荐，约 300MB）

好处：**缺什么宏包自动装**，不用手动补。

1. 下载：<https://miktex.org/download> → Windows 安装包
2. 安装时选「Install MiKTeX for anyone」+「Always install missing packages on-the-fly」
3. 装完打开 **MiKTeX Console → Updates** 更新一次
4. 验证：命令提示符里 `xelatex --version`

### 方案 B：TeX Live（完整，约 5GB）

<https://tug.org/texlive/acquire-netinstall.html> → `install-tl-windows.exe`，
双击后选「Install」即可（国内镜像见下）。

---

## 三、Linux

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install texlive-xetex texlive-lang-chinese texlive-latex-extra \
                 texlive-fonts-recommended texlive-science latexmk

# 还需要 exam-zh（发行版仓库里可能没有，用 tlmgr 装）
sudo tlmgr install exam-zh ctex xecjk unicode-math newcomputermodern stix2-otf
```

---

## 四、国内下载加速（重要）

官方源在国外，5GB 的 MacTeX 直接下会很慢。用清华 TUNA 镜像替换域名即可：

| 资源 | 镜像地址 |
|---|---|
| CTAN 总入口 | <https://mirrors.tuna.tsinghua.edu.cn/CTAN/> |
| TeX Live 网络安装器 | <https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet/> |
| MacTeX | <https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/mac/mactex/> |
| MiKTeX | <https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/win32/miktex/setup/windows-x64/> |

`tlmgr` 也可以换成清华源（装完 BasicTeX 后执行）：

```bash
sudo tlmgr option repository https://mirrors.tuna.tsinghua.edu.cn/CTAN/systems/texlive/tlnet
```

---

## 五、装完还是编不过？

最常见的两个原因：

1. **缺宏包**。报错长这样：`! LaTeX Error: File 'xxx.sty' not found.`
   → 用报错里的文件名反查包名，再装上：

   ```bash
   tlmgr search --global --file xxx.sty     # 看它属于哪个包
   sudo tlmgr install <包名>
   ```

2. **缺中文字体**。报错形如 `The font "XXX" cannot be found`
   → 装上思源宋体/思源黑体（开源可商用）：
   <https://mirrors.tuna.tsinghua.edu.cn/CTAN/fonts/adobe-source-han-serif/>
   或改用它自带的字体：在导出的 `.tex` 里把 `\setCJKmainfont{...}` 换成系统已有字体。

> 报错原文可以在导出界面看到（会显示前几条错误），也可以看导出目录里的 `.log` 文件。
