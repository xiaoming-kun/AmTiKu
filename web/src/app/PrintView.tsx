/** 打印视图：把选中的题渲染成一张 A4 卷面，交给浏览器「打印 → 存储为 PDF」。
 *
 *  为什么走这条路（而不是内置 TeX）：发布包不用背上几百 MB 的 LaTeX，
 *  也不会在别人机器上因字体 / 映射 / ls-R 缺失而"编不出来"。
 *  公式仍由 KaTeX 渲染 —— 与界面所见完全一致。
 */
import { useState } from 'react'
import { renderBlocks } from '@/lib/render'
import type { Q } from '@/lib/types'

export default function PrintView({ list, title, onClose }: {
  list: Q[]; title: string; onClose: () => void
}) {
  const [withAnswers, setWithAnswers] = useState(false)
  const t = title.trim() || '数学试卷'

  return (
    <div className="print-root min-h-screen bg-white text-black">
      {/* 工具条：只在屏幕上出现，打印时隐藏（no-print） */}
      <div className="no-print sticky top-0 z-10 flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-2">
        <button onClick={() => window.print()}
          className="rounded bg-brand px-3 py-1 text-[13px] font-medium text-white hover:opacity-90">
          打印 / 存为 PDF
        </button>
        <label className="flex items-center gap-1.5 text-[12.5px] text-ink-soft">
          <input type="checkbox" checked={withAnswers} onChange={(e) => setWithAnswers(e.target.checked)} />
          附答案与解析（另起一页）
        </label>
        <span className="text-[12px] text-ink-faint">打印对话框里把「目标」选成「存储为 PDF / Save as PDF」</span>
        <button onClick={onClose}
          className="ml-auto rounded border border-border px-3 py-1 text-[13px] hover:bg-muted">
          返回
        </button>
      </div>

      <div className="mx-auto max-w-[190mm] px-6 py-8">
        <h1 className="text-center text-[20px] font-semibold tracking-wide">{t}</h1>
        <div className="mt-1 text-center text-[12px] text-ink-faint">
          本卷共 {list.length} 题{withAnswers ? ' · 附答案与解析' : ''}
        </div>

        <ol className="mt-6 space-y-5">
          {list.map((q, i) => (
            <li key={q.key} className="q-block">
              <div className="flex gap-2">
                <span className="shrink-0 font-semibold">{i + 1}.</span>
                <div className="min-w-0 flex-1">
                  <div className="q-stem text-ink">{renderBlocks(q.blocks?.stem)}</div>
                  {q.options.length > 0 && (
                    <ul className="q-options mt-2 space-y-1">
                      {q.options.map((o, j) => (
                        <li key={o.label} className="flex gap-1.5">
                          <span className="shrink-0 font-medium">{o.label}.</span>
                          <span className="min-w-0">{renderBlocks(q.blocks?.options?.[j])}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>

        {withAnswers && (
          <section className="ans-section">
            <h2 className="border-b border-black/30 pb-1 text-[16px] font-semibold">答案与解析</h2>
            <ol className="mt-4 space-y-5">
              {list.map((q, i) => (
                <li key={q.key} className="q-block">
                  <div className="flex gap-2">
                    <span className="shrink-0 font-semibold">{i + 1}.</span>
                    <div className="min-w-0 flex-1">
                      {q.answer && <div className="q-answer font-semibold text-red-600">{renderBlocks(q.blocks?.answer)}</div>}
                      {q.solution && <div className="q-solution mt-1 text-ink">{renderBlocks(q.blocks?.solution)}</div>}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </div>
  )
}
