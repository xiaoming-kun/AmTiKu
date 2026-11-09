/** 学段：小学 / 初中 / 高中。
 *
 *  这不是一个筛选项，而是整个软件的**视角**：切到小学，知识图谱、讲义、
 *  题库、组卷都换成小学的口径。所以它有自己的 URL 参数（stage），
 *  不塞进 `UrlFilters` —— 筛选是「在同一批内容里再挑」，学段是换一批内容。
 */
export type Stage = 'primary' | 'junior' | 'senior'

export type StageMeta = {
  key: Stage
  name: string
  /** 单字标记，给窄条/小徽章用 */
  short: string
  grades: string
  /** 学段色：只用于图谱节点、阶段徽章这类需要一眼区分的地方 */
  color: string
  soft: string
  line: string
  blurb: string
}

export const STAGES: StageMeta[] = [
  { key: 'primary', name: '小学', short: '小', grades: '1–6 年级',
    color: '#0f766e', soft: '#f0fdfa', line: '#99f6e4',
    blurb: '诊断题起步，讲义与题库正在建设' },
  { key: 'junior', name: '初中', short: '初', grades: '7–9 年级',
    color: '#1d4ed8', soft: '#eff6ff', line: '#bfdbfe',
    blurb: '诊断题起步，讲义与题库正在建设' },
  { key: 'senior', name: '高中', short: '高', grades: '高一–高三',
    color: '#6d28d9', soft: '#f5f3ff', line: '#ddd6fe',
    blurb: '题库、讲义、组卷的完整生产线' },
]

export const STAGE_BY_KEY: Record<Stage, StageMeta> =
  Object.fromEntries(STAGES.map((s) => [s.key, s])) as Record<Stage, StageMeta>

export function isStage(v: unknown): v is Stage {
  return v === 'primary' || v === 'junior' || v === 'senior'
}

/** 从地址栏 / 上次选择 / 默认「高中」三处取一个合法学段。 */
export function readStage(urlValue?: string): Stage {
  if (isStage(urlValue)) return urlValue
  try {
    const v = localStorage.getItem('amtiku.stage')
    if (isStage(v)) return v
  } catch { /* 隐私模式 */ }
  return 'senior'
}

export function rememberStage(s: Stage) {
  try { localStorage.setItem('amtiku.stage', s) } catch { /* 不记忆 */ }
}

export function stageName(s: Stage): string {
  return STAGE_BY_KEY[s].name
}
