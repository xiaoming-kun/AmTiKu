/** 单题换题弹窗。
 *
 *  只负责“给当前题找替补 + 让人选一道”，替换动作由父组件改卷子状态。
 *  候选用后端 `POST /api/generate/replace` 算：同题型、尽量同板块/同难度，
 *  排除卷内已用的题。
 */
import { useEffect, useState } from 'react'
import { Check, Loader2, RefreshCw, X } from 'lucide-react'
import type { Q } from '@/lib/types'
import { api } from '@/lib/api'
import { renderBlocks } from '@/lib/render'

type Cand = Q & { match?: { topic?: boolean; section?: boolean; difficulty?: boolean } }

export default function SwapDialog({
  current, exclude, onClose, onPick,
}: {
  current: Q
  exclude: string[]
  onClose: () => void
  onPick: (q: Q) => void
}) {
  const [items, setItems] = useState<Cand[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [picked, setPicked] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true); setErr('')
    api.replaceCandidates({
      key: current.key, type: current.type,
      want_diff: current.difficulty, exclude, limit: 8,
    })
      .then((d: any) => { if (alive) setItems(d.items || []) })
      .catch((e) => { if (alive) setErr(String((e as any)?.message || e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [current.key, current.type, current.difficulty]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const pick = (q: Cand) => {
    setPicked(q.key)
    onPick(q)
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-5"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="absolute inset-0 bg-scrim" onClick={onClose} />
      <div role="dialog" aria-modal="true" aria-label="换一题"
        className="anim-pop relative flex max-h-[86vh] w-full max-w-[760px] flex-col
                   overflow-hidden rounded-[var(--radius-pop)] border border-border
                   bg-surface shadow-[var(--shadow-pop)]">
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
          <RefreshCw size={15} className="text-brand" />
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold tracking-tight">换一题</div>
            <div className="truncate text-[11px] text-ink-faint">
              当前：{current.key} · 目标 {current.difficulty || '同类型'} · 已排除卷内 {exclude.length} 道
            </div>
          </div>
          <button onClick={onClose} title="关闭（Esc）" className="icon-btn h-8 w-8">
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-[12.5px] text-ink-faint">
              <Loader2 size={15} className="animate-spin" />正在找同类型/同难度的替补…
            </div>
          ) : err ? (
            <div className="py-16 text-center text-[12.5px] text-warn">{err}</div>
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-[12.5px] text-ink-faint">
              没有可替换的题。试试放宽筛选，或先给题库补同类型题。
            </div>
          ) : (
            <div className="space-y-2">
              {items.map((q, i) => (
                <button key={q.key} onClick={() => pick(q)} disabled={!!picked}
                  className={`press w-full rounded-xl border p-3 text-left transition-colors ${
                    picked === q.key
                      ? 'border-brand bg-brand-soft'
                      : 'border-border bg-bg hover:border-brand-line hover:bg-surface'}`}>
                  <div className="flex items-start gap-2">
                    <span className="tnum mt-[2px] w-4 shrink-0 text-[10.5px] text-ink-faint">
                      {i + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="q-stem q-compact max-h-[5.2em] overflow-hidden text-[13px] leading-[1.7]">
                        {renderBlocks(q.blocks?.stem)}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px]">
                        <span className="rounded bg-muted px-1.5 py-[1px] text-ink-soft">{q.type_label}</span>
                        {q.difficulty && (
                          <span className={`rounded px-1.5 py-[1px] ${
                            q.difficulty === '简单题' ? 'bg-has-soft text-has'
                            : q.difficulty === '难题' ? 'bg-danger-soft text-danger'
                            : 'bg-brand-soft text-brand-ink'}`}>{q.difficulty}</span>
                        )}
                        {q.match?.topic && <span className="rounded bg-has-soft px-1.5 py-[1px] text-has">同主考点</span>}
                        {q.match?.difficulty && <span className="rounded bg-brand-soft px-1.5 py-[1px] text-brand-ink">同难度</span>}
                        <span className="truncate text-ink-faint">
                          {q.point_titles?.[0] || '未标考点'}
                          {q.meta?.year ? ` · ${q.meta.year}` : ''}
                          {q.meta?.source_label ? ` · ${q.meta.source_label}` : ''}
                        </span>
                        {q.flags?.['解析'] && <span className="text-has">有解析</span>}
                        {q.flags?.['答案'] && <span className="text-ink-faint">有答案</span>}
                      </div>
                    </div>
                    <span className={`mt-1 shrink-0 rounded-lg px-2 py-1 text-[11px] font-medium ${
                      picked === q.key ? 'bg-brand text-white' : 'border border-border text-ink-soft'}`}>
                      {picked === q.key ? <Check size={12} /> : '用这道'}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-border bg-surface-2 px-4 py-2 text-[10.5px] text-ink-faint">
          候选按“同主考点 / 同板块 / 同难度 / 有解析 / 用得少”排序；替换只改当前卷子，不写题库。
        </div>
      </div>
    </div>
  )
}
