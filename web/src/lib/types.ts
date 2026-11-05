/** 共享类型。
 *
 *  从 App.tsx 抽出来 —— 编辑器拆成独立模块后，App 与编辑器都要用这些类型，
 *  留在 App 里会形成循环引用。
 */
import type { Block } from '@/lib/render'

export type Flags = Record<string, boolean>

export type Q = {
  key: string; type: string; type_label: string; kind: string
  stem: string; options: { label: string; text: string }[]
  answer: string; solution: string; points: string[]
  blocks: { stem: Block[]; answer: Block[]; solution: Block[]; options: Block[][] }
  difficulty: string; stars: number; point_titles: string[]
  seq?: number
  used?: number                       // 被导出（试卷/讲义）的次数
  meta: Record<string, any>; hash: string
  missing: string[]; flags: Flags
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
}
