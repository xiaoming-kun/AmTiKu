/** 试卷相关的常量（App 与导出页共用，避免两处各写一份）。
 *
 *  原来 SCORE/SECTION_LABEL 定义在 App.tsx 里，导出页搬出去后
 *  两边都要用 → 提到这里做单一来源。
 */

/** 每题分值（与 amti/paper.py 的计分保持一致） */
export const SCORE: Record<string, number> = {
  single_choice: 5, multi_choice: 6, fill_in_blank: 5, detailed_answer: 15,
}

/** 卷面大题顺序与标题 */
export const SECTION_LABEL: [string, string][] = [
  ['single_choice', '一、选择题'], ['multi_choice', '二、多选题'],
  ['fill_in_blank', '三、填空题'], ['detailed_answer', '四、解答题'],
]
