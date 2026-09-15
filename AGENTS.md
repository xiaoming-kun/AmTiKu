# AGENTS.md — AmTiKu 项目 AI 协作指令

> 本文件供 AI 编码助手（DSH / Claude Code / Codex 等）阅读。
> 目标：让 AI 一次理解项目规矩，**减少反复返工**。

## 一、项目是什么

本地**高中数学题库 + 组卷系统**。数据全部在项目目录内，不依赖任何外部路径。

| | 数量 |
|---|---|
| 题目 | 17,249 道（高考真题 13,251 + 模拟 4,004） |
| 有解析 | 13,425 道（77.8%） |
| 配图 | 2,893 道有图 |
| 待解 | 3,474 道 |

## 二、技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3，**自研 HTTP server**（无 FastAPI/Flask），`amti/` 25 个模块 ≈11,700 行 |
| 前端 | React 18 + Vite + Tailwind + TypeScript，`web/src/` |
| 文档格式 | **LaTeX**（前端用 KaTeX 渲染） |
| 求解 | 本地 LM Studio（Qwen3.8-27B，端口 1234） |

## 三、常用命令

### 启动/停止（全局命令，任何目录可用）

```bash
AmTiKu          # 启动（题库 8899 + 本地模型 1234 + 求解）
AmTiKu 状态      # 看跑着什么、解了多少题
AmTiKu 停止      # 停止（不动 LM Studio）
AmTiKu 网页      # 起题库并打开浏览器
AmTiKu 验收      # 跑四层验收
```

支持拼音：`AmTiKu qidong / zhuangtai / tingzhi / wangye / qiujie / yanshou`

### ⭐ 改完代码或数据**必须**验收

```bash
python3 amti.py accept          # 四层全绿才算过（权威门槛；层③ 要服务，它会自己起）
python3 测试/接口测试.py         # 接口回归 14 项（不起服务）
python3 测试/讲义测试.py         # 讲义/出处标签 6 项 + 前后端一致性
```

四层全绿才算过：

```
① 单元自检   8 个模块 + 解析回归 + 检查器自证
② 规范审查   12 项，全库
③ 端到端渲染 前端同一条渲染路径跑全库（KaTeX / LaTeX 泄漏 / 图片）
④ 快照       内容变化必须是 0
```

### 诊断命令

```bash
python3 amti.py status     # 库有多大
python3 amti.py diff       # 跟基线比（存量内容变化必须为 0）
python3 amti.py conform    # 规范审查（只报不改）
python3 amti.py changes    # 变更记录列表
```

其他子命令：`snapshot verify audit backup export-unsolved collect render-tikz compilecheck trash dedup rules show images ingest`

## 四、目录结构（关键项）

```
AmTiKu/
├── amti.py              命令行入口（CLI 子命令都在这里定义）
├── amti/                Python 核心（25 模块，≈11,700 行）
│   ├── store.py         分卷存储：唯一真相是 题目/001.tex…（每卷 ≤5000 题）
│   ├── normalize.py     规范化器：**全库唯一**改题目形态的地方
│   ├── latex_blocks.py  正文 → 块级 IR：**全项目唯一**的正文解析器
│   ├── latex_ir.py      LaTeX → 结构化字段：**全项目只有这里懂 LaTeX**
│   ├── fixups.py        逐题订正（normalize 的补充：成片规则之外的单点修补）
│   ├── ingest.py        录入（核心承诺：**存量题目一个字都不变**）
│   ├── images.py        图片入库（内容寻址）：**全项目唯一**处理图片的地方
│   ├── paper.py         组卷（高考卷等卷型）
│   ├── papers.py        试卷存档（出了什么卷、用了哪些题）
│   ├── render_tex.py    Question → exam-zh LaTeX
│   ├── export.py        组卷导出（渲染 + 编译 PDF）
│   ├── generate.py      随机组卷（按高考真题的结构与排布惯例）
│   ├── slidev_handout.py Slidev 讲义导出
│   ├── solve.py         模拟题求解（本地大模型，**一题一写**）
│   ├── conform.py       规范化验证（全库题目是否同构）
│   ├── dedup.py         查重（录入前先问"库里是不是已有"）
│   ├── audit.py         影响面审计（MIGRATE 强制流程）
│   ├── exchange.py      待解题目的导出 / 回收
│   ├── schema.py        数据模型与校验
│   ├── knowledge.py     知识点库（难度/考点从这里派生）
│   ├── tikzfig.py       TikZ 预渲染成矢量图
│   ├── trash.py         回收站（删除可恢复）
│   ├── compilecheck.py  全库编译体检
│   ├── sample.py        抽取测试集（100 道）
│   ├── migrate.py       旧题库迁移（一次性工具，**已废弃**）
│   └── web/server.py    Web 服务（自研 HTTP server，1681 行）
├── web/                 前端（React + Vite + Tailwind）
│   └── src/             **重构中，见下节**
├── 题目/                **题库主文件** 001.tex … 004.tex（超大，最大 12M）
├── 图片/                配图 + TikZ 预渲染矢量图（3758 个，内容寻址命名）
├── 知识点.json          153 个考点大纲
├── 归档快照.json         基线指纹（"存量有没有被改"）
├── 设计/题目规范.md      **唯一的格式定义** ← 改数据前必读
├── 变更记录/            每次批量改数据的报告
├── 回收站/回收站.json    删掉的题（可恢复）
└── 测试/删题安全自检.py   危险操作的专项验收
```

**题目长什么样**：一道题 = 一个 `question` 环境，前面一行元数据（JSON）

```latex
%% @q {"key": "高考真题汇编/2024/新高考I卷#1", "type": "single_choice", ...}
\begin{question}
...
```

### ⭐ 核心设计原则（改动时必须遵守）

本项目刻意保持**单一职责**——每个领域只有**一个入口**。改动时**不要绕过，也不要重复实现**：

| 唯一入口 | 管什么 | 违反了会怎样 |
|---|---|---|
| `store.py` | 分卷存储 | 题库唯一真相是 `题目/*.tex`；另建存储 → 数据不一致 |
| `latex_ir.py` + `latex_blocks.py` | LaTeX 解析 | **全项目只有这里懂 LaTeX**；在别处写解析 → 必然与它分叉 |
| `normalize.py` | 规范化 | 全库唯一改题目形态的地方；绕过 → `conform` 审查失败 |
| `images.py` | 图片入库 | 唯一处理图片处（内容寻址命名）；手工改图 → 引用断裂 |
| `ingest.py` | 录入 | 承诺**存量题目一个字不变**；不要拿它做批量修改 |

> **新增功能前先问**：这件事是不是已经有唯一入口了？
> 有 → 改那个模块；没有 → 才新建。

## 五、✅ 前端结构（重构已完成，2026-09-15）

`App.tsx` 从 **4741 行降到 1014 行**（−79%）。当前结构：

| 目录 | 文件 | 职责 |
|---|---|---|
| `web/src/` | `App.tsx`（1014） | 页面级状态 + 三栏布局组装 |
| `web/src/editor/` | `CanvasEditor` 87 / `useCanvas` 253 / `CanvasStage` 180 / `Inspector` 243 / `PointDrawer` 117 / `useDrawer` 74 / `useHandoutIo` 91 / `shared` 370 | 讲义编辑器：一整块独立模块，新功能加在这里 |
| `web/src/app/` | `Detail` / `ExportPage` / `IngestDrawer` / `Stats` / `Trash` / `QuestionCard` / `ui` | 页面级组件 |
| `web/src/lib/` | `api`（统一请求+错误上报）/ `types` / `qlatex` / `render` / `paper` / `display` / `useQuestionList` | 与后端打交道、共享类型与转换 |

**动前端代码时的约定**：

- ❗**不要往 `App.tsx` 里加新组件** —— 页面组件放 `app/`，编辑器相关放 `editor/`
- 请求一律走 `lib/api.ts` 的 `request()`（它统一处理 `r.ok` + 错误提示），
  不要裸 `fetch(...).then(r => r.json())`
- 类型放 `lib/types.ts`（`Q` / `Facets` / `Base` / `ExportResult`）
- 转换规则改动 → 见第九节「预览与导出不一致」

### 文档在哪（先读这三份）

| 文档 | 什么时候读 |
|---|---|
| `README.md` | 全局：项目有什么、日常怎么用、下一步能做什么 |
| `设计/讲义系统.md` | **改讲义/画布相关代码前必读**（含「预览与导出必须一致」的规矩和踩过的坑） |
| `CHANGELOG.md` | 想知道「这版做了什么、怎么验证的」 |
| `设计/题目规范.md` | **改数据前必读**（唯一格式定义） |

## 六、协作约定（减少返工的 5 条）

1. **改数据前**：先读 `设计/题目规范.md`（唯一格式定义）
2. **改代码前**：说明方案；复杂改动先出计划（plan mode），不要直接动手
3. **改完必须**：跑 `python3 amti.py accept` 四层验收
4. **禁止**：
   - 整体重写 `题目/*.tex`（最大 12M，必须精准定位改动）
   - 用 `.bak` 文件做备份（已启用 git，用 `git commit` 代替）
   - 重命名 `图片/` 下的文件（内容寻址命名）
5. **求解任务在跑时**：`amti.py diff` 报"内容变化"是**正常的**；要检查存量是否被误改，先停求解再 diff

## 七、已知坑

- 网页关掉 **25 秒后服务自动退出**（这是设计行为，不是故障）
- `题目/*.tex` 是超大文件，读取时**不要整体读**，用 key 定位
- 日志位置：`/tmp/amti_web.log`（题库）、`/tmp/amti_solve.log`（求解进度）
- 停 LM Studio：`lms server stop`（`AmTiKu 停止` 不碰它，因为别的程序也在用）

## 八、版本管理

本项目已启用 git（2026-09-15 初始化）。改动流程：

```bash
git add -A && git commit -m "说明改了什么"    # 每完成一小步就提交
git checkout -- <文件>                       # 改坏了，回滚单个文件
git log --oneline                            # 看历史
```

> 数据文件的版本管理仍由项目自有机制负责（`amti.py snapshot` + `归档快照.json`），
> git 主要管理**代码、配置和文档**。

## 九、⭐ 代码审查约定（用户长期要求）

> 用户的原话：**「后续的代码你做好审查」**。
> 不是一次性任务，而是**每次改代码都要走的流程**。

### 改动的固定流程

```bash
# 1. 改之前：说明方案（复杂改动先出计划），不要闷头写
# 2. 改的过程中：一步一提交，别攒一大批
git add -A && git commit -m "说明改了什么"

# 3. 改完必须全绿（缺一不可）
python3 amti.py accept                 # 项目自己的四层验收（权威门槛）
python3 测试/接口测试.py                # 接口回归 14 项
python3 测试/讲义测试.py                # 讲义/出处标签 6 项
cd web && npx tsc --noEmit --noUnusedLocals --noUnusedParameters   # 0 问题
cd web && npm run build                # 构建通过
# 4. 动了界面/导出 → 还要在浏览器里真跑一遍（改题库 → 加讲义 → 导出 PDF）
```

### 审查清单（两份报告就是清单本体）

- 前端：`MiniMaxH3/_集成/前端代码审查报告.md`（依据 [front-review skill](https://github.com/Effeilo/claude-code-frontend-skills)）
- 后端：`MiniMaxH3/_集成/后端代码审查报告.md`（依据 [fastapi-best-practices 18k★](https://github.com/zhanymkanov/fastapi-best-practices) + [wshobson/agents 39.7k★](https://github.com/wshobson/agents)）

改完代码后**对着这两份清单自查**：新代码有没有踩同类问题
（未使用的导入/声明、无 timeout 的子进程、无上界的 limit、静默吞异常、
硬编码的魔法数字、巨型函数、`any`）。

### 本项目的「反复踩过的坑」（新代码优先防这些）

| 坑 | 表现 | 防法 |
|---|---|---|
| **预览与导出不一致** | 编辑器看着对，PDF 不一样 | 前后端成对的转换函数**必须同步改**（`web/src/lib/qlatex.ts` ↔ `amti/slidev_handout.py`），并有测试逐题比对 |
| **HTML/markdown 的换行** | 公式不渲染、解答题挤成一段 | `<div>` 与内容之间**必须空行**；单换行要转硬换行 |
| **构建成功 ≠ 渲染正确** | Slidev 静默失败，出空 PDF / 源码泄漏 | 必须看 PDF 文本层（`amti.py accept` 层③ 就是干这个的） |
| **改完没重新构建前端** | 界面还是旧行为 | 改 `web/src` 后必须 `npm run build` 并重启服务 |
| **一处漏 catch 就静默失败** | 界面表现成"没数据" | 统一走 `lib/api.ts` 的 `request()`；错误有全局提示条 |
| **脚本/客户端的隐含前提** | 改了后端限制，把验收脚本打挂 | 改接口约束时**全仓搜调用点**（`grep -rn "limit="`） |

### 提交信息要求

- 说清**改了什么、为什么**，并在涉及功能时写明**验证方式**
- 修 bug 时把**根因**写进去（例：「原来 Promise.all 3491 个 fetch 打满线程池」）
- 一次提交一件事，便于 `git checkout` 回滚

