/** 选题弹窗：从**当前考点**的题里挑，加到讲义下面的练习里。
 *
 *  为什么不复用工作台的列表：工作台一屏是 20 道 + 一堆筛选 + 详情抽屉，
 *  塞进弹窗会挤成一条缝。这里只保留"挑题"必需的：搜索、题型/难度/年份、
 *  排序、只看未添加、多选、加载更多。
 *
 *  已在该专题里的题显示「已添加」并禁用勾选；底部一次提交所选项。
 */
import { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, X } from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import { renderBlocks } from '@/lib/render'
import { useDebounced } from '@/lib/useDebounced'

type Q = {
  key: string; type: string; type_label: string; difficulty: string
  blocks?: { stem?: unknown[] }
  meta?: { year?: number | string; region?: string; source_label?: string }
}
type Facets = {
  types: { value: string; label: string }[]
  difficulties: { value: string }[]
  years: { value: string }[]
}

const LIMIT = 20

const SEL = 'h-[30px] rounded-md border border-border bg-surface-2 px-2 text-[11.5px] ' +
  'text-ink outline-none focus:border-brand-line'

export default function QuestionPicker({
  open, pointId, title, existing, anchor, onClose, onAdd,
}: {
  open: boolean
  pointId: string
  title: string
  existing: Set<string>
  /** 插入位置：''/end = 讲义末尾；数字 = 第几段之后（双击的位置） */
  anchor: string
  onClose: () => void
  onAdd: (keys: string[]) => Promise<void> | void
}) {
  const [q, setQ] = useState('')
  const dq = useDebounced(q, 250)
  const [type, setType] = useState('')
  const [diff, setDiff] = useState('')
  const [year, setYear] = useState('')
  const [sort, setSort] = useState('')
  const [onlyNew, setOnlyNew] = useState(true)
  const [items, setItems] = useState<Q[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [facets, setFacets] = useState<Facets | null>(null)
  const [saving, setSaving] = useState(false)

  // 打开时重置
  useEffect(() => {
    if (!open) return
    setQ(''); setType(''); setDiff(''); setYear(''); setSort(''); setOnlyNew(true)
    setItems([]); setTotal(0); setOffset(0); setSel(new Set())
    // 题型/难度/年份选项
    api.facets().then((d: Facets) => setFacets({
      types: d.types || [], difficulties: d.difficulties || [], years: d.years || [],
    })).catch(() => {})
  }, [open])

  // Esc 关闭
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // 条件变了就重拉第一页
  useEffect(() => {
    if (!open) return
    let alive = true
    setBusy(true)
    api.list({
      point: pointId, q: dq, type, difficulty: diff, year, sort,
      limit: String(LIMIT), offset: '0',
    }).then((r: { items: Q[]; total: number }) => {
      if (!alive) return
      setItems(r.items || []); setTotal(r.total || 0)
      setOffset((r.items || []).length)
    }).catch((e) => { if (alive) reportErr(e) })
      .finally(() => { if (alive) setBusy(false) })
    return () => { alive = false }
  }, [open, pointId, dq, type, diff, year, sort])

  const more = async () => {
    setBusy(true)
    try {
      const r: { items: Q[]; total: number } = await api.list({
        point: pointId, q: dq, type, difficulty: diff, year, sort,
        limit: String(LIMIT), offset: String(offset),
      })
      setItems((xs) => [...xs, ...(r.items || [])])
      setOffset((o) => o + (r.items || []).length)
      setTotal(r.total || 0)
    } catch (e) { reportErr(e) } finally { setBusy(false) }
  }

  const shown = useMemo(
    () => (onlyNew ? items.filter((x) => !existing.has(x.key)) : items),
    [items, onlyNew, existing],
  )

  const toggle = (key: string) => {
    if (existing.has(key)) return
    setSel((s) => {
      const n = new Set(s)
      if (n.has(key)) n.delete(key); else n.add(key)
      return n
    })
  }

  const submit = async () => {
    if (!sel.size) return
    setSaving(true)
    try {
      await onAdd([...sel])
      onClose()
    } catch (e) { reportErr(e) } finally { setSaving(false) }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
      onClick={onClose}>
      <div className="flex h-[84vh] w-full max-w-[1020px] flex-col overflow-hidden rounded-xl
                      border border-border bg-surface shadow-[var(--shadow-pop)]"
        onClick={(e) => e.stopPropagation()}>

        {/* 头部 */}
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <span className="text-[13.5px] font-semibold">添加题目到「{title}」</span>
          <span className="text-[10.5px] text-ink-faint">
            只列本题库里挂这个考点的题 · 插入到{anchor && anchor !== 'end' ? `第 ${anchor} 段之后` : '讲义末尾的练习'}
          </span>
          <span className="tnum ml-auto text-[11px] text-ink-soft">共 {total} 道</span>
          <button onClick={onClose} className="icon-btn h-7 w-7" title="关闭（Esc）">
            <X size={15} />
          </button>
        </div>

        {/* 筛选 */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
          <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder="搜题干 / 答案 / 出处关键词"
            className="h-[30px] min-w-[220px] flex-1 rounded-md border border-border bg-surface-2
                       px-2.5 text-[12px] text-ink outline-none placeholder:text-ink-faint
                       focus:border-brand-line" />
          <select aria-label="题型" value={type} onChange={(e) => setType(e.target.value)} className={SEL}>
            <option value="">全部题型</option>
            {(facets?.types || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <select aria-label="难度" value={diff} onChange={(e) => setDiff(e.target.value)} className={SEL}>
            <option value="">全部难度</option>
            {(facets?.difficulties || []).map((d) => <option key={d.value} value={d.value}>{d.value}</option>)}
          </select>
          <select aria-label="年份" value={year} onChange={(e) => setYear(e.target.value)} className={SEL}>
            <option value="">全部年份</option>
            {(facets?.years || []).map((y) => <option key={y.value} value={y.value}>{y.value} 年</option>)}
          </select>
          <select aria-label="排序" value={sort} onChange={(e) => setSort(e.target.value)} className={SEL}>
            <option value="">题库顺序</option>
            <option value="year">年份从新到旧</option>
            <option value="new">录入从新到旧</option>
          </select>
          <label className="flex cursor-pointer items-center gap-1.5 text-[11.5px] text-ink-soft">
            <input type="checkbox" checked={onlyNew} onChange={(e) => setOnlyNew(e.target.checked)}
              className="h-3.5 w-3.5 accent-[var(--color-brand)]" />
            只看未添加
          </label>
        </div>

        {/* 列表 */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-2">
          {busy && !items.length && (
            <div className="flex items-center justify-center gap-2 py-14 text-[12px] text-ink-faint">
              <Loader2 size={14} className="animate-spin" />正在读题…
            </div>
          )}
          {!busy && shown.length === 0 && (
            <div className="py-14 text-center text-[12px] text-ink-faint">
              没有匹配的题{onlyNew ? '（试试关掉「只看未添加」）' : ''}
            </div>
          )}
          <div className="space-y-1.5">
            {shown.map((x) => {
              const added = existing.has(x.key)
              const on = sel.has(x.key)
              return (
                <label key={x.key}
                  className={`flex cursor-pointer items-start gap-2.5 rounded-lg border px-2.5 py-2
                              transition-colors ${added
                                ? 'cursor-default border-border bg-surface-2/30 opacity-70'
                                : on
                                  ? 'border-brand-line bg-brand-soft/50'
                                  : 'border-border bg-surface-2/40 hover:border-brand-line'}`}>
                  <span className={`mt-[2px] grid h-4 w-4 shrink-0 place-items-center rounded border
                                    ${on ? 'border-brand bg-brand text-white'
                                         : added ? 'border-border bg-muted' : 'border-border bg-surface'}`}>
                    {(on || added) && <Check size={11} strokeWidth={3} />}
                  </span>
                  <input type="checkbox" className="sr-only" checked={on} disabled={added}
                    onChange={() => toggle(x.key)} />
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-1.5 text-[9.5px] text-ink-faint">
                      <span className="rounded border border-border px-1">{x.type_label}</span>
                      <span className="rounded bg-muted px-1">{x.difficulty}</span>
                      {x.meta?.year ? <span>{x.meta.year}</span> : null}
                      {x.meta?.region ? <span className="truncate">{x.meta.region}</span> : null}
                      {added && <span className="rounded bg-brand-soft px-1 text-brand-ink">已添加</span>}
                    </span>
                    <span className="mt-1 line-clamp-2 block text-[12px] leading-relaxed text-ink">
                      {renderBlocks(x.blocks?.stem as never)}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
          {shown.length < (onlyNew ? total : total) && items.length < total && (
            <div className="mt-2 flex justify-center">
              <button onClick={more} disabled={busy}
                className="press rounded-md border border-border px-3 py-1 text-[11px] text-ink-soft
                           hover:border-brand-line disabled:opacity-60">
                {busy ? '正在加载…' : '加载更多'}
              </button>
            </div>
          )}
        </div>

        {/* 底部 */}
        <div className="flex items-center gap-2 border-t border-border px-4 py-2.5">
          <span className="text-[11.5px] text-ink-soft">
            已选 <span className="tnum font-semibold text-brand-ink">{sel.size}</span> 道
          </span>
          {sel.size > 0 && (
            <button onClick={() => setSel(new Set())} className="text-[10.5px] text-ink-faint hover:text-ink">
              清空
            </button>
          )}
          <span className="ml-auto text-[10.5px] text-ink-faint">添加到讲义下面的练习</span>
          <button onClick={onClose}
            className="press rounded-md border border-border px-3 py-1.5 text-[11.5px] text-ink-soft">
            取消
          </button>
          <button onClick={submit} disabled={!sel.size || saving}
            className="press rounded-md bg-brand px-3.5 py-1.5 text-[11.5px] font-semibold
                       text-white disabled:opacity-50">
            {saving ? '添加中…' : sel.size ? `添加 ${sel.size} 道` : '添加'}
          </button>
        </div>
      </div>
    </div>
  )
}
