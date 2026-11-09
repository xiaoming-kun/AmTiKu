# AGENTS.md — 给 AI 助手 / 贡献者的项目说明

> 目标：一次看懂结构与规矩，少返工。用户视角见 `README.md`。

## 一、这是什么

本地 **K12 数学题库 + 组卷系统**（小学 / 初中 / 高中）。全部数据在项目目录内，只监听 `127.0.0.1`，不联任何外部服务。

* 后端：Python 3，自研 HTTP 服务（`amti/`，端口 8899）
* 前端：React 19 + TypeScript + Tailwind 4（`web/src/`，构建产物 `web/dist/`，由后端一起发）
* 界面：BoardUI 浅色设计语言（中性骨架 + 学院蓝 + Bento 卡片），新壳在 `web/src/app/Shell.tsx`，页面在 `web/src/app/pages/`
* 信息架构：**学段优先**（小学/初中/高中）→ 总览 → 知识图谱 → 讲义 → 题库 → 录题 → 组卷
* 题目：**LaTeX**（界面用 KaTeX 渲染）
* 目录：**根目录只放"入口"和"数据区"**，一次性产物进 `归档/`——每个目录的职责见 `docs/目录规范.md`

## 二、改完必须验收

```bash
python3 amti.py accept          # 四层：单元自检 / 规范审查 / 端到端渲染 / 快照——必须全绿
python3 测试/接口测试.py         # 接口回归（项数以实际输出为准）
cd web && npx tsc --noEmit --noUnusedLocals --noUnusedParameters && npm run build
```

层③ 需要服务在跑，它会自己起；动了界面/导出还要在浏览器里真跑一遍。

## 三、唯一入口（不要绕过，也不要重复实现）

| 唯一入口 | 管什么 | 绕过的后果 |
|---|---|---|
| `amti/store.py` | 分卷存储 | 题库唯一真相是 `题目/*.tex`；另建存储 → 数据不一致 |
| `amti/latex_ir.py` + `latex_blocks.py` | LaTeX 解析 + 检索用有损归一化 | 全项目只有这里懂 LaTeX；`math_text()` 只服务搜索，结构化字段仍走 `parse_question`，别处再写解析 → 必然分叉 |
| `amti/normalize.py` | 规范化 | 全库唯一改题目形态的地方；绕过 → 规范审查失败 |
| `amti/images.py` | 图片入库 | 唯一处理图片处（内容寻址命名） |
| `amti/ingest.py` | 录入 | 承诺**存量题目一个字不变**；不要拿它做批量修改 |
| `amti/knowledge_map.py` | 教材知识地图 | 读 `知识地图.json`；另写一份教材顺序 → 与考点库分叉 |
| `amti/topics.py` / `amti/topic_export.py` / `amti/lecture_html.py` | 讲义 | 另起一套讲义数据/渲染 → 与专题页分叉 |
| `amti/lecture_tex.py` | 小初章节讲义 | 小初 content JSON → 与高中同款 elegantbook `.tex` / PDF / manifest；另写一套模板 → 三学段版式分叉 |
| `amti/diagnostic.py` | 小初诊断卷 | 绕过它自己拼 LaTeX → 与正式试卷渲染分叉 |
| `amti/open_lectures.py` | 开源小初**素材**（来源/许可追溯） | 读 `数据/开源讲义/manifest.json`；讲义页不再直接读它，另起一套阅读器 → 与讲义页分叉，且容易丢许可/署名 |
| `amti/readmodel.py` | 题库元数据读模型（派生 SQLite） | 只用于列表筛选/排序/分页；真相仍是 `题目/*.tex`，未就绪时回退旧路径 |
| `amti/lite_cache.py` | 列表块 IR 缓存（派生 SQLite） | 按 content_hash 命中；删了可重建，不能当题库真相 |
| `amti/content_store.py` | 题目内容读模型（派生 SQLite） | 详情主键读 + 公式召回；真相仍是 `题目/*.tex`，删了可重建，未就绪回退 `store.find` |
| `amti/recall.py` | 检索召回（中文 FTS / 公式） | 列表与组卷共用；在路由里各写一套 → 两边搜到的不是同一批题 |
| `amti/similar.py` | 相似题（派生索引） | 同考点 / 公式 / 题型；按卷签名缓存，真相仍是 `题目/*.tex` |
| `amti/duplicates.py` | 重复题标注（派生分组） | 复用 `dedup` 指纹；只提示不合并，真相仍是 `题目/*.tex` |
| `amti/query_syntax.py` | 搜索框语法 | 字段/排除词只解析一次；列表与组卷共用，显式参数优先 |
| `amti/sharepack.py` | 分享包 | 只读打包；导入同 key 跳过、图片哈希校验；不覆盖真相 |
| `amti/docx_export.py` | Word 导出 | 块 IR→Markdown→Pandoc；PDF 仍走 exam-zh，不是第二套解析器 |
| `amti/source_import.py` | 源文件适配 | DOCX→PDF、PDF/图片/文本准备；只准备，不解析不写库 |
| `amti/search.py` | 相关度打分 + 公式等价写法 | `math_forms()` 是查询扩展；新增写法规则只改这里 |
| `amti/web/query.py` | 题目筛选条件（列表与组卷共用） | 两边各写一套 → 列表筛到的和组卷池子不是同一批题；改筛选口径只改这里 |
| `amti/review.py` | 审阅状态、风险队列、分层抽样、Wilson CI | 另写一套复核口径 → 体检页数字再次失真；`reviewed_at` 不得再兼作“编辑过” |

> 新增功能前先问：这件事是不是已经有唯一入口了？有 → 改那个模块；没有 → 才新建。

### 内容库与公式检索

`数据/缓存/content.sqlite` 是**派生**的题目内容库：按 key 存原始题块（压缩），
详情页主键读约 2ms；还存 `math_strict/math_loose` 两列供公式召回，
`math_q` 只存题面（题干/选项/答案，不含解析）供相似题用，
`block_hash` 用于重建时按题块复用旧行的压缩 body 和 math 三列。
卷签名（mtime+size）变了就失效，读时回退 `store.find()` 并后台重建。

重建是**增量**的：题块 hash 没变的行直接复用，只有改过的题跑 `math_text`。
实测 31,505 道：全量 11s，改一道题后约 1s。改 `math_text()` 规则时**必须
bump `SCHEMA`**，否则旧行会按旧规则留下。

```bash
python3 -m amti.content_store status   # 行数 / 大小 / 是否 current
python3 -m amti.content_store build    # 同步重建（约 11 秒 / 31k 题）
python3 -m amti.content_store clear    # 删掉，下次读自动重建
```

检索召回统一走 `amti/recall.py`：纯中文 2 字以上 → FTS5；公式 → 内容库
`math_*`（`cosB`、`cos B`、`\cos(B)` 归一；`1/2` 与 `0.5`、`(x+1)^2` 与
`x^2+2x+1` 走 SymPy 有界等价）；其余 → 原 `kw_hit`。列表与组卷都从
`recall()` 拿候选，再交给 `QuestionFilter`，不要各写一套。

> 公式等价只做**写法归一 + 有限代数改写**（分数/小数、展开/因式分解），
> 不做定理证明；`1/2` 搜不到 `0.5` 说明 SymPy 没装或库没建好，先看
> `content_store.status()`。

### 相似题

`GET /api/questions/{key}/similar?limit=8` → `{key, items, ready}`。

- 特征：`math_q` 的字符 trigram（IDF 加权 Jaccard）+ 考点 Jaccard + 题型/难度/出处；
- 索引：`math_q` 倒排，按卷签名缓存；首次约 0.4s，之后单题 <10ms；
- 内容库没建好时 `ready=false`，前端显示“索引构建中”，**不拿空结果冒充没有相似题**；
- 详情页“相似题”按钮 → 点一条直接切题。

### 重复题

列表卡片：`meta.duplicate_group` / `meta.dup_of` 存在时标“重复题”。
详情页“查重”：`amti/duplicates.py` 复用 `dedup` 的题干+选项指纹，合并
`duplicate_group` / `dup_of` / 完全同指纹三路，只提示，**绝不自动合并**。
实测 8,005 道 / 3,141 组；首次建组约 2.6s，之后 0.28s。没有组返回
`n=0, items=[]`，不编造。

### 搜索语法 / 历史

搜索框支持 `考点:三角 年份:2024 类型:多选 难度:中档 出处:… 地区:…`、
`-词` 排除、引号把空格并进一个字段值。解析在 `amti/query_syntax.py`，
列表与组卷都先 `parse()` 再交给同一个 `QuestionFilter`；**显式筛选参数优先**。

前端最近 8 条搜索存 `localStorage` 的 `amtiku.search.history.v1`，输入框聚焦
时下拉，Enter / 失焦记录。

### 导出与分享

- **PDF** 仍走 `paper.py`（exam-zh）；**Word** 走 `docx_export.py`：
  `latex_blocks` 块 IR → Markdown → Pandoc → DOCX，公式是 OMML，图片走
  `--resource-path 图片/`。TikZ 不渲染，Word 里显示占位文字；复杂版式以 PDF 为准。
- Word 导出依赖本机 **Pandoc**（`brew install pandoc` / `choco install pandoc`），
  没装会明确报错；安装包暂未内置。
- **分享包** `sharepack.py`：zip 内 `manifest.json` + 原题块 + 内容寻址图片；
  导入同 key **跳过不覆盖**，图片校验 sha256，包内路径拒绝 `..`/绝对路径。
  导入最终走 `store.append()`，不另写一套入库。

### 识题源文件

- `amti/source_import.py` 只做“源 → 可读材料”，**不解析题目、不写题库**：
  `.docx` → Pandoc → PDF；`.pdf` 原样；`.tex/.txt/.md` 读出文本；图片原样。
- 每次准备在 `数据/录题/任务/<id>/` 留 `manifest.json`（源文件名、sha256、
  类型、派生 PDF、时间、状态），方便回查来源。
- Word 转出的 PDF 交给现有 VLM/AI 读题，文本交给编辑器；之后仍然只走
  `ingest.preview()` → `ingest.commit()`。**不是第二套录入管线。**
- PDF/Word 准备时渲 `pages/p-001.png` 源页；录入抽屉显示“源页 1/2/3…”，
  点开用现有 `pageView` 对照原页。
- `GET /api/ingest/jobs` / `GET /api/ingest/jobs/{id}` 支持“继续最近任务”；
  任务只保存源材料和派生件，不保存题库正文。


## 三·五、开源素材与小初章节讲义

小学/初中的**讲义正文**在 `数据/专题/小初/content/*.json`，由 `amti/lecture_tex.py`
渲染成与高中同款的 elegantbook `.tex`，再走 `amti/lecture_html.py` 出网页版；
讲义页三学段共用 `web/src/app/TopicsPage.tsx`。

`数据/开源讲义/` 是**来源与许可追溯**：MIT / LPPL 的原文、图片、LICENSE 和署名。
它不再直接出现在讲义阅读器里；生成小初讲义时只从中取材，并在 `source_note` 与
页面标题下保留原作者、许可与链接。
开源素材条目仍要写 `book` / `chapter`，并与 `知识地图.json` 的册/章标题逐字一致；
不匹配的条目不显示。每篇必须保留：来源仓库、作者、LICENSE、原文与本项目内的署名。
MIT / LPPL 的内容可以原样整合，但**不能改掉版权声明**，也不能把第三方讲义声称为原创。
讲义 `source_note` 与页面标题下必须保留这些署名。

## 四、改数据的规矩

1. **先读规范入口**：本地 `设计/题目格式与录题规范-总纲.md`（优先级/验收分级）→ `设计/题目规范.md`（格式真相）；
   公开版见 `docs/题目格式.md`。再动数据。
2. **批量改动**走 `normalize.py`（成片规则）/ `fixups.py`（逐题订正）/ `exchange.collect`（补答案与解析），
   不要直接编辑 `题目/*.tex`。
3. **答案与解析**：没有答案或解析的题**一律不许入库**（`ingest` 会整批拒绝）；
   解答题答案栏写「见解析」；LaTeX 写法与质量要求见 `docs/题目格式.md` 与本地 `设计/答案与解析规范.md`。
   **宁缺勿错**：没把握的解析不要写。
4. 一题一写、写完立刻落盘。

## 五、禁止

* 整体重写 `题目/*.tex`（单卷上万题，必须精准定位改动）
* 用 `.bak` 文件做备份（已启用 git，用 `git commit` 代替）
* 重命名 `图片/` 下的文件（内容寻址命名，改名即断引用）
* 把题库数据、真题文本、真实公司/学校名提交进仓库

## 六、反复踩过的坑（新代码优先防这些）

| 坑 | 表现 | 防法 |
|---|---|---|
| **预览与导出不一致** | 编辑器看着对，PDF 不一样 | 界面（`web/src/lib/qlatex.ts`，KaTeX）与导出（`amti/paper.py`，exam-zh）是两条渲染路径，题干写法**必须两边都验证**，并有测试逐题比对 |
| **构建成功 ≠ 渲染正确** | 静默失败、出空 PDF / 源码泄漏 | 必须看产物的文本层（`accept` 层③ 就是干这个的） |
| **改完没重新构建前端** | 界面还是旧行为 | 改 `web/src` 后必须 `npm run build` |
| **一处漏 catch 就静默失败** | 界面表现成"没数据" | 请求统一走 `lib/api.ts` 的 `request()`，错误有全局提示 |
| **改了接口约束把验收脚本打挂** | `测试/` 报错 | 改约束时全仓搜调用点（`grep -rn "limit="`） |
| **照着旧文档录题** | 图题不录/解析无/题型按题号等旧规则 | 先看总纲 §0 的文档状态表；旧线文档只作历史，不能照做 |

## 七、提交信息

说清**改了什么、为什么**，并写明**验证方式**；修 bug 把**根因**写进去；一次提交一件事，便于回滚。
