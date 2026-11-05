r"""项目根目录（数据所在目录）的**唯一来源**。

为什么要单独一个模块：免安装版用 PyInstaller 打包后，模块代码在包内部，
`Path(__file__).parent.parent` 指的就不是"数据所在目录"了——题库、图片、知识点
都会被算到包内部去，读不到也写不进。

统一按这个顺序找：
  1. 环境变量 `AMTIKU_ROOT`（显式指定，优先级最高）
  2. 打包运行时：**可执行文件所在目录**（数据就放在 exe 旁边）
  3. 源码运行时：仓库根目录（`amti/` 的上一级）
"""
import os
import sys
from pathlib import Path


def resolve_root() -> Path:
    env = os.environ.get("AMTIKU_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    if getattr(sys, "frozen", False):          # PyInstaller 等打包运行时
        if sys.platform == "darwin":
            # **便携模式**：`.app` 同级如果放了 `题目/`，就把它当数据目录。
            # 用于"含题库的私人包"——整个文件夹拷走就搬家，不碰系统目录。
            beside = Path(sys.executable).resolve().parent.parent.parent.parent
            if (beside / "题目").is_dir():
                return beside
            # 默认：macOS 的 `.app` 是**只读包体**，把题库写进去会破坏代码签名
            # （签名一破，Gatekeeper 下次就说"已损坏"），用户也找不到自己的数据。
            # 放到系统约定位置，卸载 = 删这个目录。
            return Path.home() / "Library" / "Application Support" / "AmTiKu"
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_resources() -> Path:
    r"""**随包只读资源**所在目录（前端 `web/dist`、demo 题库）。

    必须与 `ROOT`（数据目录）分开——这是两种东西：

    * `ROOT`：用户的**数据**（题目/ 图片/ 知识点.json），放在 exe 旁边，
      要能读也要能写，用户换电脑时拷的就是它。
    * 资源：打包进去的**只读**文件，PyInstaller 把它们解在 `sys._MEIPASS`
      （onedir 模式实际就是 exe 旁边的 `_internal/`）。

    混为一谈的后果实测过：免安装版打开 <http://127.0.0.1:8899> **是 404**——
    前端在 `_internal/web/dist`，而代码去 exe 旁边找 `web/dist`，找不到就
    静默跳过了整个界面挂载，于是"接口都能用、界面打不开"。
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def resolve_out_dir() -> Path:
    r"""**导出的试卷 / 讲义放哪儿**。

    默认写在数据目录下的 `试卷/`；但老师多半想让它落在自己的资料文件夹里
    （比如「文档/阿明的辅导讲义」），所以给两个口子改：

      1. 环境变量 `AMTIKU_OUT_DIR`（优先级最高，方便临时切换 / 跑测试）
      2. **数据目录下的 `数据/导出位置.txt`**，里面写一行目录路径

    为什么用配置文件而不是写死在代码里：这一行是**个人路径**，
    写进源码就违反了脱敏那条规矩（`312df91` 就是专门清理个人路径的提交）。
    而整个 `数据/` 不进 git，放那儿最合适。

    文件里以 `#` 开头的行会被跳过，所以可以带注释。
    """
    env = os.environ.get("AMTIKU_OUT_DIR")
    if env:
        return Path(env).expanduser()
    cfg = ROOT / "数据" / "导出位置.txt"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return Path(line).expanduser()
    except OSError:
        pass                                   # 没配置文件 → 用默认
    return ROOT / "试卷"


ROOT = resolve_root()
RESOURCES = resolve_resources()
# 导出位置（试卷与讲义**都**落这儿）。**唯一来源**——以前 export.py、
# web/server.py 各自写了一遍 `"试卷"`，两份必然分叉。
OUT_DIR = resolve_out_dir()

# ── 导出分类：导出位置下的子目录 ──────────────────────────────────────
#
# 用户要的不是「全堆在一个文件夹」，而是按产出类型分开：
#
#     阿明的辅导讲义/试卷/…      高考卷、考点覆盖卷
#     阿明的辅导讲义/测试卷/…    纯测试题
#     阿明的辅导讲义/讲义/…      LaTeX 讲义
#
# 分类名**只此一份**：`export.py` 落盘、`paper.py` 落盘、
# `/api/settings` 告诉界面「存为哪」、界面显示预览路径，全都读这里。
# v1.6.19 的教训就是目录名散在四处、前端写死「试卷/」而后端落到别处。
OUT_KINDS = ("试卷", "测试卷", "讲义")
# 卷型 → 分类。`test` 是「纯测试题」，`handout` 是 A4 讲义；
# 认不出的卷型按试卷算（`kind_of`）。
OUT_KIND_OF = {"gaokao": "试卷", "test": "测试卷", "handout": "讲义"}


def kind_of(mode: str = "gaokao") -> str:
    """卷型 → 分类目录名（`gaokao`/`test`/`handout`；认不出按试卷）。"""
    return OUT_KIND_OF.get(mode, "试卷")


def out_kind_dir(kind: str) -> Path:
    """某一类产出的落盘目录：`<导出位置>/<分类>/`。"""
    return OUT_DIR / kind


def out_kind_label(kind: str) -> str:
    """给界面/导出提示看的相对路径，如 `阿明的辅导讲义/试卷`。"""
    base = OUT_DIR.name or str(OUT_DIR)
    return f"{base}/{kind}"


# **预览**的编译产物放应用数据里，不落用户的资料夹。
# 「编译预览」与「导出并保存」原本是同一个动作（都写 试卷/、都计使用频次），
# 用户点一次预览就在自己文件夹里留一份 PDF，还会把题目的"用过 N 次"+1。
# 预览只需要一个能看的 PDF，放在 `数据/预览/` 最干净（不进 git、不进资料夹）。
PREVIEW_DIR = ROOT / "数据" / "预览"


# 前端构建产物（`npm run build` 的 outDir）。开发机上没构建时可能不存在，
# 所以用之前要判存在——但**打包后必须存在**，见 packaging/amti_frozen.py 的自检。
UI_DIST = RESOURCES / "web" / "dist"
