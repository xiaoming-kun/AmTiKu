/** 录入抽屉的共享常量/类型：Source、Review、useIngest 都用这一份。 */
export const FIELD = `h-[32px] rounded-lg border border-border bg-bg px-2.5 text-[12.5px] outline-none
               transition-[border-color,box-shadow] duration-150 placeholder:text-ink-faint
               focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]`
export const LABEL = 'text-[11px] font-semibold tracking-[0.08em] text-ink-faint'
export const MINI = `press inline-flex items-center gap-1 rounded-md border border-border bg-surface
              px-1.5 py-[2px] text-[10.5px] text-ink-soft hover:border-brand-line
              hover:text-brand-ink disabled:opacity-40`

export const QTYPE_OPTS: [string, string][] = [
  ['', '自动识别'], ['single_choice', '单选题'], ['multi_choice', '多选题'],
  ['fill_in_blank', '填空题'], ['detailed_answer', '解答题'],
]
export const QTYPE_LABEL: Record<string, string> = {
  single_choice: '单选题', multi_choice: '多选题',
  fill_in_blank: '填空题', detailed_answer: '解答题',
}
export const STARS: Record<string, number> = { 简单题: 1, 中档题: 2, 难题: 3 }

/** 手工录入的默认出处 / 年份：只预填，人随时能改。 */
export const DEFAULT_BOOK = '2026精选模拟题'
export const DEFAULT_LABEL = '精选模拟题'
export const DEFAULT_YEAR = '2026'

export type Edit = {
  points: string[]
  difficulty: string
  source_no: string
  qtype: string
  point_source: string
  tag_model: string
  tagged_at: string
  label: string
  year: string
}
export type EditMap = Record<number, Edit>
export type PickMap = Record<number, boolean>

export const EMPTY: Edit = {
  points: [], difficulty: '', source_no: '', qtype: '',
  point_source: '', tag_model: '', tagged_at: '', label: '', year: '',
}

/** 这道题为什么不能入库；后端已算 blocking，前端再兜一层。 */
export function blockingOf(it: any): string[] {
  const out: string[] = [...(it?.blocking || [])]
  if (it?.flags && !it.flags['答案']) out.push('缺答案')
  if (it?.flags && !it.flags['解析']) out.push('缺解析')
  const src = String(it?.tex || '')
  if (src.includes('【图：') || src.includes('请补图') || src.includes('请手工补')) {
    out.push('缺图待补')
  }
  return [...new Set(out)]
}

export const DRAFT_KEY = 'amtiku.ingest.draft.v1'

export function loadDraft(): any {
  try {
    if (typeof localStorage === 'undefined') return {}
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}') || {}
  } catch { return {} }
}
