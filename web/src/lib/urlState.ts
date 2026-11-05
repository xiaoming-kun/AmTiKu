/** 地址栏状态：**刷新不丢、可收藏、可分享**。
 *
 *  以前筛选/搜索只活在 useState 里，按一下刷新就全清空；老师想固定看
 *  「2026精选模拟题 + 导数 + 缺解析」这个组合，每天都要重选一遍。
 *  现在把同一份状态同步到 `?q=…&source=…&page=…&tab=…`。
 *
 *  **用 replaceState 而不是 pushState**：筛选连续变化不该在浏览器历史里
 *  堆几十条，后退键仍然离开页面（而不是在筛选中倒退）。没有引入路由库——
 *  只有「读一次 + 变时写一次」两件事，一个 URLSearchParams 就够。
 *
 *  字段名和 `useQuestionList.filters` 保持一致（都是字符串、数组用逗号拼），
 *  这样两边的映射只有一份，不会改了一边忘了另一边。
 */
export type UrlFilters = {
  q: string
  type: string
  kind: string
  point: string
  diff: string
  year: string
  source: string
  has: string
  missing: string
  scope: string
  paper: string
  star: string
  quality: string
  psrc: string
  asrc: string
  reviewed: string
}

export type UrlSnapshot = {
  filters: UrlFilters
  /** `null` = 地址里没写，按默认 `used`；空串是「题库原序」，要保留 */
  sort: string | null
  page: number
  tab: string
}

const EMPTY: UrlFilters = {
  q: '', type: '', kind: '', point: '', diff: '', year: '', source: '',
  has: '', missing: '', scope: '', paper: '', star: '', quality: '', psrc: '', asrc: '', reviewed: '',
}

/** 短参数名 → filters 字段。地址栏短一点，肉眼也能读懂。 */
const FILTER_KEYS: [keyof UrlFilters, string][] = [
  ['q', 'q'], ['type', 'type'], ['kind', 'kind'], ['point', 'point'],
  ['diff', 'diff'], ['year', 'year'], ['source', 'source'], ['has', 'has'],
  ['missing', 'missing'], ['scope', 'scope'], ['paper', 'paper'],
  ['star', 'star'], ['quality', 'quality'], ['psrc', 'psrc'], ['asrc', 'asrc'],
  ['reviewed', 'rv'],
]

function read(): UrlSnapshot {
  if (typeof window === 'undefined') return { filters: { ...EMPTY }, sort: null, page: 1, tab: '' }
  const sp = new URLSearchParams(window.location.search)
  const filters = { ...EMPTY }
  for (const [field, key] of FILTER_KEYS) {
    filters[field] = sp.get(key) || ''
  }
  const page = Math.max(1, parseInt(sp.get('page') || '1', 10) || 1)
  return {
    filters,
    // 用 `has` 区分「没写」和「写了空串（题库原序）」
    sort: sp.has('sort') ? (sp.get('sort') || '') : null,
    page,
    tab: sp.get('tab') || '',
  }
}

/** 模块加载时读一次。应用是单页；之后由 `writeUrlState` 单向写回。 */
export const INITIAL_URL = read()

export function writeUrlState(s: UrlSnapshot): void {
  if (typeof window === 'undefined') return
  const sp = new URLSearchParams()
  for (const [field, key] of FILTER_KEYS) {
    const v = s.filters[field]
    if (v) sp.set(key, v)
  }
  // 默认排序 `used` 不写；空串（题库原序）要写 `sort=`，否则刷新会变回频次序
  if (s.sort !== null && s.sort !== 'used') sp.set('sort', s.sort)
  if (s.page > 1) sp.set('page', String(s.page))
  if (s.tab && s.tab !== 'workbench') sp.set('tab', s.tab)
  const qs = sp.toString()
  const url = window.location.pathname + (qs ? `?${qs}` : '') + window.location.hash
  const now = window.location.pathname + window.location.search + window.location.hash
  if (url === now) return
  try {
    window.history.replaceState(null, '', url)
  } catch {
    /* file:// 或受限环境里 replaceState 会抛——地址栏不同步，但别阻断界面 */
  }
}
