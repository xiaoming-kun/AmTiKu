/** 筛选预设：老师每天看的组合就那么几套，存下来一键回来。
 *
 *  存的是 `useQuestionList.filters` 那份口径（字符串、数组逗号拼接）+
 *  排序。**不存页码**：应用预设从第 1 页开始。
 *  只用 localStorage，不进题库数据——这是视图偏好，不是题目内容。
 */
import type { UrlFilters } from '@/lib/urlState'

export type FilterPreset = {
  name: string
  /** 存下时的时间（只用于排序/展示，不做业务判断） */
  at: string
  filters: UrlFilters
  sort: string
}

const KEY = 'amtiku.filter.presets'
/** 别的标签页也可能改这份预设；`storage` 事件用它判断。 */
export const FILTER_PRESETS_KEY = KEY

export function loadPresets(): FilterPreset[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '[]')
    if (!Array.isArray(v)) return []
    return v
      .filter((x) => x && typeof x.name === 'string' && x.name && x.filters)
      .slice(0, 30)
  } catch {
    return []
  }
}

export function savePresets(list: FilterPreset[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, 30)))
  } catch {
    /* 隐私模式/配额满：存不下就只是不记忆，不阻断界面 */
  }
}
