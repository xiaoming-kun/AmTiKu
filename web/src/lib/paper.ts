/** 试卷相关的常量与**计分**（App、导出页、卷子面板共用，避免几处各写一份）。
 *
 *  ⚠️ 这里的算法必须和 `amti/generate.py` 的 `score_of()` / `answer_scores()`
 *  一字不差地对上 —— 界面上的「多少分」和 PDF 上印的「共 X 分」是同一个数，
 *  两边算错就是 AGENTS.md 里点名的那个坑（预览和导出不一致）。
 */

/** 小分值题型：固定分 */
export const MINOR_SCORE: Record<string, number> = {
  single_choice: 5, multi_choice: 6, fill_in_blank: 5,
}

/** 解答题**整块固定 77 分**。
 *
 *  这不是"15 分一道"：`amti/generate.py` 的 `answer_scores(n)` 把 77 分
 *  按题数摊开（标准 5 道 → 13/15/15/17/17），用最大余数法保证**加起来仍是 77**，
 *  不管几道题。所以：
 *
 *      8×5 + 3×6 + 3×5 + 77 = 150   ← 正好是真高考卷的总分
 *
 *  旧代码写的是 `detailed_answer: 15` 这种"一道 15 分"的假表，
 *  于是「考点覆盖卷」挑出 23 道解答题时，界面报 484 分，而卷面上只有 196 分。 */
export const ANSWER_TOTAL = 77

/** 标准 5 道解答题的分值表（满分 77）。 */
const ANSWER_SCORES = [13, 15, 15, 17, 17]

/** 解答题分值表：题数不是 5 时按 77 分同比例摊，用**最大余数法**保证加起来仍是 77。
 *
 *  **逐行照抄 `amti/generate.py` 的 `answer_scores()`**（那里是权威）。
 *  两处算法必须一致——不一致就意味着界面上的分值跟 PDF 上印的不一样。 */
export function answerScores(n: number): number[] {
  if (n <= 0) return []
  if (n === ANSWER_SCORES.length) return [...ANSWER_SCORES]
  const total = ANSWER_TOTAL
  const exact = total / n
  const base = Array.from({ length: n }, () => Math.floor(exact))
  const rest = total - base.reduce((a, b) => a + b, 0)
  // 余数大的先加；余数一样就按次序（Python 的 sorted 是稳定的，这里显式写出来）
  const order = [...base.keys()].sort((i, j) => (exact - base[j]) - (exact - base[i]) || i - j)
  for (const i of order.slice(0, rest)) base[i] += 1
  return base
}

/** 某一道题在卷面上的分值（解答题**按位置**取，其余固定）。
 *  对应 `amti/generate.py` 的 `score_of()`。 */
export function questionScore(type: string, indexInType: number, countOfType: number): number {
  if (type === 'detailed_answer') return answerScores(countOfType)[indexInType] ?? 15
  return MINOR_SCORE[type] ?? 5
}

/** 某个题型 n 道题占多少分。 */
export function scoreOf(type: string, n: number): number {
  if (n <= 0) return 0
  if (type === 'detailed_answer') return ANSWER_TOTAL
  return (MINOR_SCORE[type] ?? 5) * n
}

/** 整卷总分。 */
export function paperScore(qs: { type: string }[]): number {
  const n: Record<string, number> = {}
  for (const q of qs) n[q.type] = (n[q.type] || 0) + 1
  return Object.entries(n).reduce((s, [t, c]) => s + scoreOf(t, c), 0)
}

/** 题型短名（说明文字里用，和后端的 SHORT_NAME 一致） */
export const SHORT_NAME: Record<string, string> = {
  single_choice: '单选', multi_choice: '多选',
  fill_in_blank: '填空', detailed_answer: '解答',
}

/** 卷面大题顺序与标题 */
export const SECTION_LABEL: [string, string][] = [
  ['single_choice', '一、选择题'], ['multi_choice', '二、多选题'],
  ['fill_in_blank', '三、填空题'], ['detailed_answer', '四、解答题'],
]
