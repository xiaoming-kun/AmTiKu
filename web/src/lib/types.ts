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

export type Facets = {
  types: { value: string; label: string; n: number }[]
  kinds: { value: string; n: number }[]
  years: { value: string; n: number }[]
  points: { value: string; n: number; title: string; topic: string
            section: string; stars: number; difficulty: string }[]
  points_covered: number
  difficulties: { value: string; n: number }[]
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
}
