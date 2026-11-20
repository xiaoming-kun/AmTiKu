/** 分值算法：界面上的「共 X 分」和 PDF 上印的必须是同一个数。
 *  这里的期望值不是随手写的——它就是 `amti/generate.py` 的 `answer_scores()`
 *  在标准高考卷上的结果（13/15/15/17/17，解答题合计 77）。 */
import { describe, expect, it } from 'vitest'
import {
  ANSWER_EXTRA, ANSWER_SCORES, MINOR_SCORE, SECTION_LABEL, SHORT_NAME,
  answerScores, paperScore, questionScore, scoreOf,
} from '@/lib/paper'

describe('answerScores（解答题按位置给分）', () => {
  it('0 道和负数都返回空表，不抛错', () => {
    expect(answerScores(0)).toEqual([])
    expect(answerScores(-3)).toEqual([])
  })

  it('标准 5 道解答题正好 77 分（高考卷 150 分的那 77）', () => {
    expect(answerScores(5)).toEqual([13, 15, 15, 17, 17])
    expect(answerScores(5).reduce((a, b) => a + b, 0)).toBe(77)
  })

  it('第 6 道起按 ANSWER_EXTRA 给，不是把 77 摊平', () => {
    // 曾经这里按题数摊平：1 道解答题 = 77 分。现在一道题值多少分与卷上数量无关。
    expect(answerScores(1)).toEqual([13])
    expect(answerScores(7)).toEqual([13, 15, 15, 17, 17, 15, 15])
    expect(answerScores(7).at(-1)).toBe(ANSWER_EXTRA)
    expect(ANSWER_SCORES).toHaveLength(5)
  })
})

describe('questionScore（某一道题的分值）', () => {
  it('解答题按它在解答题里的位置取分', () => {
    expect(questionScore('detailed_answer', 0, 5)).toBe(13)
    expect(questionScore('detailed_answer', 3, 5)).toBe(17)
    // 位置超出题数表（数据不一致的兜底）→ ANSWER_EXTRA，而不是 NaN/undefined
    expect(questionScore('detailed_answer', 9, 5)).toBe(ANSWER_EXTRA)
    expect(questionScore('detailed_answer', 2, 3)).toBe(15)
    expect(questionScore('detailed_answer', 0, 0)).toBe(ANSWER_EXTRA)
  })

  it('小分值题型固定给分，未知题型兜底 5 分', () => {
    expect(questionScore('single_choice', 0, 40)).toBe(MINOR_SCORE.single_choice)
    expect(questionScore('multi_choice', 2, 3)).toBe(6)
    expect(questionScore('fill_in_blank', 1, 4)).toBe(5)
    expect(questionScore('no_such_type', 0, 1)).toBe(5)
  })
})

describe('scoreOf / paperScore', () => {
  it('n <= 0 不打负分', () => {
    expect(scoreOf('single_choice', 0)).toBe(0)
    expect(scoreOf('detailed_answer', -1)).toBe(0)
  })

  it('分题型求和：3 单选 + 2 多选 + 5 解答 = 15 + 12 + 77', () => {
    expect(scoreOf('single_choice', 3)).toBe(15)
    expect(scoreOf('multi_choice', 2)).toBe(12)
    expect(scoreOf('detailed_answer', 5)).toBe(77)
    expect(scoreOf('detailed_answer', 6)).toBe(92)   // 77 + 15
  })

  it('整卷总分按题型分组，与题目顺序无关；未知题型按 5 分计', () => {
    const qs = [
      ...Array.from({ length: 3 }, () => ({ type: 'single_choice' })),
      ...Array.from({ length: 2 }, () => ({ type: 'multi_choice' })),
      ...Array.from({ length: 5 }, () => ({ type: 'detailed_answer' })),
    ]
    expect(paperScore(qs)).toBe(104)
    expect(paperScore([...qs].reverse())).toBe(104)
    expect(paperScore([])).toBe(0)
    expect(paperScore([{ type: 'mystery' }, { type: 'mystery' }])).toBe(10)
  })

  it('题型短名与卷面大题顺序覆盖四种题型（漏一种就会在卷面上消失）', () => {
    expect(Object.keys(SHORT_NAME).sort()).toEqual(
      ['detailed_answer', 'fill_in_blank', 'multi_choice', 'single_choice'])
    expect(SECTION_LABEL.map(([k]) => k)).toEqual(
      ['single_choice', 'multi_choice', 'fill_in_blank', 'detailed_answer'])
    expect(SECTION_LABEL.map(([, v]) => v)).toEqual(['一、选择题', '二、多选题', '三、填空题', '四、解答题'])
  })
})
