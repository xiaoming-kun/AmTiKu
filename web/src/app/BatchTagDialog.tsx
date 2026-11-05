/** 批量改标签弹窗。
 *
 *  列表里勾 N 道 → 一次改完、后端**一次写盘**。
 *  以前只能一道一道开详情改：16 道就是 16 次“读全库 + 写 6 卷”。
 *
 *  每个字段都有一个「改」开关：不勾的字段**原样不动**——批量操作最怕
 *  “我只想改年份，结果把考点全清空了”。改完之后整批过 `conform`，
 *  有一条不合规就整批不存。
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Loader2, Tags, X } from 'lucide-react'
import type { Facets } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { toast } from '@/app/Toast'

type Field = 'points' | 'difficulty' | 'stars' | 'year' | 'region' | 'source' | 'reviewed'

const DIFFS = ['简单题', '中档题', '难题']

export default function BatchTagDialog({
  keys, facets, onClose, onDone,
}: {
  keys: string[]
  facets: Facets | null
  onClose: () => void
  onDone: (res: any) => void
}) {
  const [on, setOn] = useState<Set<Field>>(new Set())
  const [form, setForm] = useState({
    point: '', difficulty: '', stars: '0', year: '', region: '',
    book: '', label: '', reviewed: 'yes',
  })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    // **capture 阶段**：App 的全局 Esc 会先关详情抽屉并同步重渲染，
    // 效果清理会把这里的 listener 摘掉——bubble 阶段的监听根本轮不到。
    // capture + stopPropagation 让弹层先关，且不误关背后的详情。
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', h, true)
    return () => window.removeEventListener('keydown', h, true)
  }, [onClose, busy])

  const toggle = (f: Field) => setOn((s) => {
    const n = new Set(s)
    n.has(f) ? n.delete(f) : n.add(f)
    return n
  })
  const set = (k: keyof typeof form, v: string) =>
    setForm((s) => ({ ...s, [k]: v }))

  const submit = async () => {
    if (!on.size) { setErr('先至少勾一个要改的字段'); return }
    if (on.has('points') && !form.point) { setErr('勾了考点，但没选考点'); return }
    if (on.has('source') && (!form.book.trim() || !form.label.trim())) {
      setErr('改书/卷名时，两个都要填'); return
    }
    setBusy(true); setErr('')
    try {
      const body: Parameters<typeof api.batchPatch>[0] = { keys }
      if (on.has('points')) body.points = [form.point]
      if (on.has('difficulty')) body.difficulty = form.difficulty
      if (on.has('stars')) body.stars = Number(form.stars)
      if (on.has('year')) body.year = form.year.trim()
      if (on.has('region')) body.region = form.region
      if (on.has('source')) {
        body.book = form.book.trim()
        body.label = form.label.trim()
      }
      if (on.has('reviewed')) body.reviewed = form.reviewed === 'yes'
      const r = await api.batchPatch(body)
      toast(`已改 ${r?.changed ?? keys.length} 道` + (r?.renamed ? `，改名 ${r.renamed} 道` : ''))
      onDone(r)
    } catch (e) {
      setErr(String((e as any)?.message || e))
      reportErr(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[75] flex items-center justify-center p-5"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose() }}>
      <div className="absolute inset-0 bg-scrim" onClick={() => !busy && onClose()} />
      <div role="dialog" aria-modal="true" aria-label="批量改标签"
        className="anim-pop relative flex max-h-[88vh] w-full max-w-[620px] flex-col
                   overflow-hidden rounded-[var(--radius-pop)] border border-border
                   bg-surface shadow-[var(--shadow-pop)]">

        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
          <Tags size={15} className="text-brand" />
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold tracking-tight">批量改标签</div>
            <div className="truncate text-[11px] text-ink-faint">
              已选 {keys.length} 道 · 只动勾选的字段 · 改完整批过规范审查
            </div>
          </div>
          <button onClick={() => !busy && onClose()} title="关闭（Esc）" className="icon-btn h-8 w-8">
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-4">
          <Row label="考点" on={on.has('points')} onToggle={() => toggle('points')}>
            <select value={form.point} onChange={(e) => set('point', e.target.value)}
              disabled={!on.has('points')} className={CTRL}>
              <option value="">选择考点…</option>
              {(facets?.points || []).map((p) => (
                <option key={p.value} value={p.value}>{p.title}（{p.value}）</option>
              ))}
            </select>
          </Row>

          <Row label="难度" on={on.has('difficulty')} onToggle={() => toggle('difficulty')}>
            <select value={form.difficulty} onChange={(e) => set('difficulty', e.target.value)}
              disabled={!on.has('difficulty')} className={CTRL}>
              <option value="">清空（按主考点派生）</option>
              {DIFFS.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </Row>

          <Row label="星级" on={on.has('stars')} onToggle={() => toggle('stars')}>
            <select value={form.stars} onChange={(e) => set('stars', e.target.value)}
              disabled={!on.has('stars')} className={CTRL}>
              <option value="0">清空（按主考点派生）</option>
              {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n} 星</option>)}
            </select>
          </Row>

          <Row label="年份" on={on.has('year')} onToggle={() => toggle('year')}>
            <input value={form.year} onChange={(e) => set('year', e.target.value)}
              disabled={!on.has('year')} placeholder="如 2026；留空 = 清空" className={CTRL} />
          </Row>

          <Row label="地区" on={on.has('region')} onToggle={() => toggle('region')}>
            <input value={form.region} onChange={(e) => set('region', e.target.value)}
              disabled={!on.has('region')} placeholder="如 湖北；留空 = 清空" className={CTRL} />
          </Row>

          <Row label="书 / 卷名" on={on.has('source')} onToggle={() => toggle('source')}>
            <div className="flex gap-2">
              <input value={form.book} onChange={(e) => set('book', e.target.value)}
                disabled={!on.has('source')} placeholder="书（如 模拟题）"
                className={CTRL + ' min-w-0 flex-1'} />
              <input value={form.label} onChange={(e) => set('label', e.target.value)}
                disabled={!on.has('source')} placeholder="卷名"
                className={CTRL + ' min-w-0 flex-1'} />
            </div>
          </Row>

          <Row label="复核" on={on.has('reviewed')} onToggle={() => toggle('reviewed')}>
            <select value={form.reviewed} onChange={(e) => set('reviewed', e.target.value)}
              disabled={!on.has('reviewed')} className={CTRL}>
              <option value="yes">标记已复核</option>
              <option value="no">取消复核</option>
            </select>
          </Row>

          <div className="rounded-lg border border-border bg-bg px-2.5 py-2 text-[11px] leading-relaxed text-ink-faint">
            批量改书名/卷名时，key 只在“本来就是 <code>书/卷名#号</code> 拼出来的”题上跟着改；
            像 <code>高考真题汇编/2024/新高考I卷#1</code> 这种多一层目录的，只改标签、不动身份。
          </div>
          {err && <div className="rounded-lg bg-warn-soft px-2.5 py-2 text-[12px] text-warn">{err}</div>}
        </div>

        <div className="flex shrink-0 items-center gap-2 border-t border-border px-4 py-3">
          <span className="text-[11.5px] text-ink-faint">
            例：{keys[0]}{keys.length > 1 ? ` 等 ${keys.length} 道` : ''}
          </span>
          <span className="min-w-0 flex-1" />
          <button onClick={() => !busy && onClose()}
            className="press rounded-lg border border-border bg-surface px-3 py-[6px]
                       text-[12.5px] text-ink-soft hover:bg-surface-2">取消</button>
          <button onClick={submit} disabled={busy}
            className="press flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-[6px]
                       text-[12.5px] font-medium text-white shadow-[var(--shadow-brand)]
                       hover:brightness-105 disabled:opacity-60">
            {busy && <Loader2 size={13} className="animate-spin" />}
            改这 {keys.length} 道
          </button>
        </div>
      </div>
    </div>
  )
}

const CTRL = 'w-full rounded-lg border border-border bg-surface px-2.5 py-[7px] ' +
  'text-[12.5px] text-ink outline-none focus:border-brand-line ' +
  'disabled:cursor-not-allowed disabled:opacity-45'

function Row({ label, on, onToggle, children }: {
  label: string; on: boolean; onToggle: () => void; children: ReactNode
}) {
  return (
    <div className={`rounded-xl border p-2.5 transition-colors ${
      on ? 'border-brand-line bg-brand-soft/35' : 'border-border bg-bg'}`}>
      <label className="mb-1.5 flex cursor-pointer items-center gap-2 text-[12px]">
        <input type="checkbox" checked={on} onChange={onToggle}
          className="h-3.5 w-3.5 accent-[var(--brand)]" />
        <span className={on ? 'font-medium text-brand-ink' : 'text-ink-soft'}>{label}</span>
        {!on && <span className="text-[10.5px] text-ink-faint">不改</span>}
      </label>
      {children}
    </div>
  )
}
