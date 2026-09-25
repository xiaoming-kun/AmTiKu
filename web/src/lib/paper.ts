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

/** 解答题**按高考卷面上的位置**给分，不是均分。
 *
 *  真卷就是这样：15 题 13 分，16/17 题各 15 分，18/19 题各 17 分，合计 77。
 *
 *  以前这里把 77 分按题数**摊平**，保证「解答题板块恒为 77 分」——
 *  那是为了让标准高考卷正好 150 分。可测试卷的题量是老师筛出来多少算多少：
 *
 *      1 道  → [77]        ← 一道解答题 77 分（用户：「解答题怎么能够是 77 分呢」）
 *      23 道 → 每道 3 分
 *
 *  一道题值多少分，不该由卷上还有几道题决定。高考卷恒为 5 道 →
 *  [13,15,15,17,17] → 合计 77，全卷 150 分，一个字没变。 */
export const ANSWER_SCORES = [13, 15, 15, 17, 17]

/** 第 6 道起的分值（测试卷解答题可能一道都没有，也可能二十道）。 */
export const ANSWER_EXTRA = 15

/** 解答题分值表。**逐行照抄 `amti/generate.py` 的 `answer_scores()`**（那里是权威）。
 *  两处算法必须一致——不一致就意味着界面上的分值跟 PDF 上印的不一样。 */
export function answerScores(n: number): number[] {
  if (n <= 0) return []
  return Array.from({ length: n }, (_, i) => ANSWER_SCORES[i] ?? ANSWER_EXTRA)
}

/** 某一道题在卷面上的分值（解答题**按位置**取，其余固定）。
 *  对应 `amti/generate.py` 的 `score_of()`。 */
export function questionScore(type: string, indexInType: number, countOfType: number): number {
  if (type === 'detailed_answer') return answerScores(countOfType)[indexInType] ?? ANSWER_EXTRA
  return MINOR_SCORE[type] ?? 5
}

/** 某个题型 n 道题占多少分。 */
export function scoreOf(type: string, n: number): number {
  if (n <= 0) return 0
  if (type === 'detailed_answer') return answerScores(n).reduce((a, b) => a + b, 0)
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
