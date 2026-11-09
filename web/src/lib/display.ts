/** 界面显示用的常量（多个页面共用）。 */

/** 难度 → 星级（仅用于显示） */
export const DIFF_STARS: Record<string, number> = {
  简单题: 1, 中档题: 2, 难题: 3,
}

/** 星级文本：0 不再显示成空白，而是明确写「未评级」。 */
export function starsLabel(stars: number | null | undefined): string {
  const n = Math.max(0, Math.floor(Number(stars) || 0))
  return n > 0 ? '★'.repeat(n) : '未评级'
}


/** 图片选项题：选项文字全空、选项图在题干里（如“韦恩图是”四选一）。
 *  这类题不要渲染四个空选项行，只提示“选项见图”。 */
export function hasImageOptions(q: { options: { text: string }[] }): boolean {
  return q.options.length > 0 && q.options.every((o) => !o.text.trim())
}


/** 选项标签范围，如 A–D；只有一个选项时就是 A。 */
export function optionRange(q: { options: { label: string }[] }): string {
  if (!q.options.length) return ''
  const first = q.options[0].label
  const last = q.options[q.options.length - 1].label
  return first === last ? first : `${first}–${last}`
}

/** 考点标题里常带「1.2 」「2.4.3 」这种教材编号。列表/卷面里它会被误读成
 *  题号（「2 基本不等式」看起来像第 2 题），显示时统一去掉；教材位置由
 *  知识地图/详情里的册章负责，不需要在标题里再背一遍。 */
export const dispPoint = (t: string) => (t || '').replace(/^\d+(?:\.\d+)*\s+/, '')
