/** 共享类型。
 *
 *  从 App.tsx 抽出来 —— 编辑器拆成独立模块后，App 与编辑器都要用这些类型，
 *  留在 App 里会形成循环引用。
 */
import type { Block } from '@/lib/render'

export type Flags = Record<string, boolean>

/** 审阅状态。`stale` 不落盘：正文改过、原复核指纹对不上时现算。 */
export type ReviewInfo = {
  status: 'pending' | 'approved' | 'needs_fix' | 'flagged' | 'stale'
  label: string
  short: string
  reviewed_at: string
  reviewed_by: string
  note: string
  batch: string
  reviewed_hash: string
  stale: boolean
  /** 0–100，只用于排序；不是对题目正确性的断言。 */
  risk: number
  tier: 'high' | 'medium' | 'low'
  reasons: string[]
}

export type Q = {
  key: string; type: string; type_label: string; kind: string
  stem: string; options: { label: string; text: string }[]
  answer: string; solution: string; points: string[]
  blocks: { stem: Block[]; answer: Block[]; solution: Block[]; options: Block[][] }
  difficulty: string; stars: number; point_titles: string[]
  seq?: number
  /** 原卷题号（套卷视图用；`meta.source_no`）。 */
  source_no?: string
  used?: number                       // 被导出（试卷/讲义）的次数
  /** 被存档里的卷子组过几次、最近一份叫什么（派生自 试卷/存档.json）。 */
  papers?: { n: number; last: string }
  meta: Record<string, any>; hash: string
  /** 配图 id 列表（位图文件名 / TikZ 哈希）。正文是唯一真相，这里只是派生。 */
  figures?: string[]
  /** 学段：primary / junior / senior（后端按考点现推） */
  stage?: string
  missing: string[]; flags: Flags
  /** 有效审阅状态；列表/详情都带。 */
  review?: ReviewInfo
  /** 相似题接口附加：0–1 的相似度。 */
  similarity?: number
}

/** 保存成功后的统一回调（详情页 → 列表）。
 *
 *  `refreshList` 给**标签类**改动用：难度/考点改完，当前筛选下这道题可能
 *  就不该留在这页了（筛「简单题」改成「难题」）。看到它就让列表带着当前
 *  筛选重新拉一遍——这就是「保存后自动刷新」。
 *
 *  `silent`：**后台静默**拉。改源码/答案/解析/题型时用——详情已经用接口
 *  返回的记录更新过了，列表在背后校正就行，别再弹「正在刷新列表…」。
 *  标签改动不能静默：居中遮罩要靠列表的 `loading` 判断什么时候撤。 */
export type SavedHandler = (d: Q, opts?: {
  refreshList?: boolean
  silent?: boolean
}) => void

/** 批量改出处后，后端回传的单题改名映射（old key → new key）。
 *
 *  卷子/列表/详情缓存里存的是 key，不跟着迁的话它们还拿着旧 key，
 *  导出时才报「找不到题」。 */
export type KeyRename = {
  old: string; new: string
  book?: string; label?: string; year?: number | string
}

/** 批量改出处完成：改名映射 + 当前题的最新记录（含新出处）。 */
export type SourceBatchDone = {
  renames: KeyRename[]
  current?: Q
}

/** 改出处后套卷视图要跟到哪一份。
 *
 *  套卷按 `meta.source_label` 分组；改一次出处，旧的套卷名可能消失、并入新名。
 *  `nonce` 自增，让同一对 from→to 连续发生两次也能被识别成新事件。 */
export type SetsFollow = {
  from: string
  to: string
  nonce: number
}

export type Facets = {
  types: { value: string; label: string; n: number }[]
  kinds: { value: string; n: number }[]
  years: { value: string; n: number }[]
  /** 出处（卷别）计数：`source=` 筛选与「出处」面板共用这一份。 */
  sources: { value: string; n: number }[]
  points: { value: string; n: number; title: string; topic: string
            section: string; stars: number; difficulty: string }[]
  points_covered: number
  difficulties: { value: string; n: number }[]
  region_scopes?: { value: string; n: number }[]
  paper_states?: { value: string; n: number }[]
  star_states?: { value: string; n: number }[]
  qualities?: { value: string; n: number }[]
  answer_sources?: { value: string; n: number }[]
  regions?: { value: string; n: number }[]
  reviewed_states?: { value: string; n: number }[]
  review_states?: { value: string; n: number }[]
}

/** 基线对比。`内容变化` 是**没登记过的改动**（要警惕）；
 *  其余三项都是**有意为之**，分开报，免得自己改的东西也被当成异常。 */
export type Base = {
  基线: number; 当前: number; 内容变化: number
  求解写入?: number; 录入升级?: number; 界面补录?: number; 规则迁移?: number
}

export type ExportResult = {
  ok: boolean; name: string; questions: number; missing: string[]
  tex_abs: string; pdf_abs: string | null; dir_abs: string; saved_hint: string; log: string
  /** 分类子目录（试卷 / 测试卷 / 讲义）。 */
  kind?: string
  /** PDF 相对导出位置的路径，如 `试卷/xxx.pdf`——预览 `/api/pdf?path=` 用它。 */
  pdf_rel?: string | null
  /** 后端给的完整预览地址（普通导出 vs 预览目录不同）。 */
  pdf_url?: string
  /** 是不是「编译预览」的产物（不存档、不计使用频次）。 */
  preview?: boolean
  /** PDF 排版体检：总页数 / 每页内容占比、底部空白 / 跨页提示。 */
  pages?: number
  page_stats?: { page: number; fill_pct: number; blank_cm: number; empty: boolean }[]
  warnings?: string[]
  question_pages?: Record<string, string[]>
  /** 排版溢出（编成功也有）：`pt` 超宽多少、落在哪道题。 */
  overfull?: { pt: number; line: number; key: string }[]
  /** 这卷编了几遍、哪些题被强制断页、哪些题比一页还高、讲义有没有降级。 */
  layout?: { passes: number; forced: string[]; still_split: string[]; tight: boolean }
}

/** 学段驾驶舱的返回结构（`/api/overview`）。 */
export type Overview = {
  stage: {
    key: string; name: string; points: number; books: number
    chapters: number; edges: number
  }
  edition: string
  updated: string
  coverage: { points: number; bank: number; diagnostics: number; lectures: number }
  bank: {
    total: number
    types: { label: string; n: number }[]
    difficulty: { value: string; n: number }[]
    missing: Record<string, number>
    untagged_source: number
    unreviewed: number
    review?: {
      pending: number; approved: number; needs_fix: number
      flagged: number; stale: number; reviewed: number; total: number
      review_rate: number
    }
  }
  diagnostics: {
    total: number; points: number
    levels: { value: string; n: number }[]
  }
  lectures: { total: number; points: number }
  open_lectures?: { total: number; by_stage: Record<string, number> }
  papers: {
    total: number
    recent: { name: string; title: string; kind: string; n: number; at: string }[]
  }
  stages: {
    key: string; name: string; points: number
    bank: number; diagnostics: number; lectures: number; open_lectures?: number
  }[]
  tasks: {
    id: string; label: string; n: number; tone: 'warn' | 'info' | 'ok'
    page: string; filters?: Record<string, string>; hint: string
  }[]
}
