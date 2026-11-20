/** 审阅工作台。
 *
 *  三件事：
 *  ① 风险队列：按“来源不可追溯 / 解析悬空图 / 模型标注 / 内容改过”排序；
 *  ② 分层抽样：按 book × 题型抽 N 道，固定 seed 可复现，复核后按批次算错误率 + Wilson CI；
 *  ③ 一次决定：通过 / 需修改 / 存疑，写复核人、备注和 content_hash；
 *     正文一变，原复核自动失效（stale），不会再冒充“已复核”。
 *
 *  答案默认遮住：先自己判一遍，避免被答案锚定。快捷键 J/K 上下、V 显示、
 *  A 通过、F 需修改、G 存疑。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Check, ChevronLeft, ChevronRight, CircleAlert, ClipboardCheck,
  Download, Eye, EyeOff, FileCode2, Flag, Pencil, RefreshCw, Scale, Search,
  Shuffle, SkipForward, TriangleAlert,
} from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import type { Q, ReviewInfo } from '@/lib/types'
import { renderBlocks } from '@/lib/render'
import { useDebounced } from '@/lib/useDebounced'
import { STAGE_BY_KEY, type Stage } from '@/lib/stage'
import { toast } from '@/app/Toast'

type Tier = 'high' | 'medium' | 'low'
type ReviewItem = Q & {
  review: ReviewInfo
  stratum?: string
  stratum_n?: number
  sample_n?: number
}

type ReviewStats = {
  total: number; reviewed: number; pending: number
  approved: number; needs_fix: number; flagged: number; stale: number
  review_rate: number
  risk: Record<Tier, number>
  by_book: {
    book: string; total: number; pending: number; approved: number
    needs_fix: number; flagged: number; stale: number; high: number
  }[]
  batches: {
    batch: string; n: number; approved: number; needs_fix: number
    flagged: number; error_rate: number; ci_low: number; ci_high: number
  }[]
  last_reviewed_at: string
}
type QueueData = { total: number; items: ReviewItem[] }
type SampleData = {
  batch_id: string; seed: number; requested: number; population: number
  strata: { key: string; book: string; type: string; type_label: string
            population: number; sample: number }[]
  items: ReviewItem[]
}
type Mode = 'risk' | 'queue' | 'sample'

const TYPE_OPTIONS = [
  ['', '全部题型'],
  ['single_choice', '单选题'],
  ['multi_choice', '多选题'],
  ['fill_in_blank', '填空题'],
  ['detailed_answer', '解答题'],
]
const TIER_CLS: Record<Tier, string> = {
  high: 'border-danger/30 bg-danger-soft text-danger',
  medium: 'border-warn-line bg-warn-soft text-warn',
  low: 'border-border bg-muted text-ink-faint',
}
const TIER_LABEL: Record<Tier, string> = { high: '高风险', medium: '中风险', low: '低风险' }
const STATUS_CLS: Record<string, string> = {
  pending: 'border-border bg-muted text-ink-soft',
  approved: 'border-has-line bg-has-soft text-has',
  needs_fix: 'border-warn-line bg-warn-soft text-warn',
  flagged: 'border-danger/30 bg-danger-soft text-danger',
  stale: 'border-border bg-surface text-ink-faint',
}
const DECIDE = [
  { s: 'approved', label: '通过', icon: Check, cls: 'bg-has text-white hover:brightness-105' },
  { s: 'needs_fix', label: '需修改', icon: Pencil, cls: 'bg-warn text-white hover:brightness-105' },
  { s: 'flagged', label: '存疑', icon: Flag, cls: 'bg-danger text-white hover:brightness-105' },
]

function srcLabel(v: string): string {
  if (v === 'human' || v === 'manual') return '人工'
  if (v === 'workbuddy' || v === 'llm' || v === 'deepseek') return '模型'
  if (v === 'legacy') return '历史存量'
  if (v === 'answer_sheet') return '答案册'
  if (v === 'model') return '模型推定'
  if (v === 'point') return '按考点'
  if (v === '库里同题' || v === 'dup') return '库内同题'
  if (!v || v === '无') return '未登记'
  return v
}
function plain(s: string): string {
  return (s || '')
    .replace(/\\paren\s*\[[^\]]*\]/g, '（ ）')
    .replace(/\\fillin\s*\[[^\]]*\]/g, '＿＿')
    .replace(/\\begin\{enumerate\}/g, ' ')
    .replace(/\\end\{enumerate\}/g, ' ')
    .replace(/\\item/g, ' ')
    .replace(/\\triangle/g, '△')
    .replace(/\\perp/g, '⊥')
    .replace(/\\angle/g, '∠')
    .replace(/\\sqrt/g, '√')
    .replace(/\\[a-zA-Z]+/g, '')
    .replace(/[{}$]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}
function srcTone(v: string): string {
  if (v === 'human') return 'border-has-line bg-has-soft text-has'
  if (v === 'workbuddy') return 'border-warn-line bg-warn-soft text-warn'
  return 'border-border bg-bg text-ink-faint'
}
function pct(x: number): string {
  const v = x * 100
  return v > 0 && v < 0.01 ? '<0.01%' : `${v.toFixed(2)}%`
}
function csvCell(v: unknown): string {
  const s = String(v ?? '')
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export default function Review({ stage, onChanged, onOpenSource }: {
  stage: Stage
  onChanged?: () => void
  /** 去题库详情并直接打开「改源码」。 */
  onOpenSource?: (key: string) => void
}) {
  const [stats, setStats] = useState<ReviewStats | null>(null)
  const [items, setItems] = useState<ReviewItem[]>([])
  const [total, setTotal] = useState(0)
  const [selKey, setSelKey] = useState('')
  const [mode, setMode] = useState<Mode>('risk')
  const [status, setStatus] = useState('pending')
  const [risk, setRisk] = useState('')
  const [book, setBook] = useState('')
  const [type, setType] = useState('')
  const [yearFrom, setYearFrom] = useState('')
  const [kw, setKw] = useState('')
  const [page, setPage] = useState(1)
  const [sampleN, setSampleN] = useState('100')
  const [batch, setBatch] = useState<SampleData | null>(null)
  const [note, setNote] = useState('')
  const [reviewer, setReviewer] = useState(() => {
    try { return localStorage.getItem('amtiku.reviewer') || '' } catch { return '' }
  })
  const [mask, setMask] = useState(() => {
    try { return localStorage.getItem('amtiku.review.mask') !== '0' } catch { return true }
  })
  const [revealed, setRevealed] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [reload, setReload] = useState(0)
  const kwD = useDebounced(kw, 240)
  const senior = stage === 'senior'
  const cur = useMemo(
    () => items.find((x) => x.key === selKey) || items[0] || null,
    [items, selKey])

  useEffect(() => {
    try { localStorage.setItem('amtiku.reviewer', reviewer) } catch { /* ignore */ }
  }, [reviewer])
  useEffect(() => {
    try { localStorage.setItem('amtiku.review.mask', mask ? '1' : '0') } catch { /* ignore */ }
  }, [mask])

  const loadStats = useCallback(() => {
    if (!senior) return
    api.reviewStats().then(setStats).catch(reportErr)
  }, [senior])
  useEffect(() => { loadStats() }, [loadStats])

  useEffect(() => { setPage(1) }, [mode, status, risk, book, type, yearFrom, kwD])

  useEffect(() => {
    if (!senior || mode === 'sample') return
    let alive = true
    setLoading(true)
    const p: Record<string, string> = {
      status: mode === 'risk' ? 'pending' : status,
      risk, book, type, kw: kwD,
      year_from: yearFrom || '0',
      sort: mode === 'risk' ? 'risk' : 'seq',
      limit: '50', offset: String((page - 1) * 50),
    }
    api.reviewQueue(p)
      .then((d: QueueData) => {
        if (!alive) return
        setItems(d.items)
        setTotal(d.total)
        setSelKey((k) => (d.items.some((x) => x.key === k) ? k : (d.items[0]?.key || '')))
      })
      .catch((e) => { if (alive) reportErr(e) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [senior, mode, status, risk, book, type, yearFrom, kwD, page, reload])

  useEffect(() => {
    setRevealed(false)
    setNote(cur?.review?.note || '')
  }, [cur?.key, cur?.review?.note])

  const step = useCallback((d: number) => {
    if (!items.length) return
    const i = Math.max(0, items.findIndex((x) => x.key === selKey))
    const j = Math.max(0, Math.min(items.length - 1, i + d))
    setSelKey(items[j].key)
  }, [items, selKey])

  const decide = useCallback(async (s: string) => {
    if (!cur || saving) return
    setSaving(true)
    try {
      const d: any = await api.reviewDecision({
        items: [{ key: cur.key, status: s, note }],
        reviewer,
        batch_id: batch?.batch_id || '',
      })
      const info = d?.items?.[0]?.review as ReviewInfo | undefined
      const nextItems = items
        .map((x) => (x.key === cur.key && info ? { ...x, review: info } : x))
        .filter((x) => (mode === 'sample' || s === 'pending' || x.key !== cur.key))
      setItems(nextItems)
      if (mode !== 'sample' && s !== 'pending') setTotal((t) => Math.max(0, t - 1))
      const i = items.findIndex((x) => x.key === cur.key)
      let next = nextItems[Math.min(i, nextItems.length - 1)]
        || nextItems[i - 1] || null
      if (mode === 'sample') {
        // 抽样模式不删题：自动跳到下一道还没决定的，省一次 J。
        const open = (x: ReviewItem) => x.review.status === 'pending' || x.review.status === 'stale'
        next = nextItems.slice(i + 1).find(open)
          || nextItems.find(open)
          || nextItems[i] || null
      }
      setSelKey(next?.key || '')
      setNote('')
      setRevealed(false)
      setReload((v) => v + 1)
      loadStats()
      onChanged?.()
      toast(`已记录 · ${cur.key.split('#').pop()} ${s === 'approved' ? '通过'
        : s === 'needs_fix' ? '需修改' : '存疑'}`, { tone: s === 'approved' ? 'info' : 'warn' })
    } catch (e) {
      reportErr(e)
    } finally {
      setSaving(false)
    }
  }, [cur, saving, note, reviewer, batch, items, mode, loadStats, onChanged])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const el = document.activeElement as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
        || el.tagName === 'SELECT' || el.isContentEditable)) return
      const k = e.key.toLowerCase()
      if (k === 'j') { e.preventDefault(); step(1) }
      else if (k === 'k') { e.preventDefault(); step(-1) }
      else if (k === 'v') { e.preventDefault(); setRevealed((v) => !v) }
      else if (k === 'a') { e.preventDefault(); decide('approved') }
      else if (k === 'f') { e.preventDefault(); decide('needs_fix') }
      else if (k === 'g') { e.preventDefault(); decide('flagged') }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [step, decide])

  const runSample = async () => {
    if (loading || saving) return
    setLoading(true)
    try {
      const d: SampleData = await api.reviewSample({
        n: Number(sampleN) || 100,
        book, type, year_from: Number(yearFrom) || 0, risk,
      })
      setBatch(d)
      setMode('sample')
      setItems(d.items)
      setTotal(d.items.length)
      setSelKey(d.items[0]?.key || '')
      setRevealed(false)
      setNote('')
      toast(`已抽 ${d.items.length} 道 · 批次 ${d.batch_id}`, { tone: 'info' })
    } catch (e) {
      reportErr(e)
    } finally {
      setLoading(false)
    }
  }

  const exportCsv = () => {
    const head = ['key', 'status', 'risk', 'tier', 'reasons', 'book', 'year',
      'type', 'answer_source', 'solution_source', 'point_source',
      'reviewed_at', 'reviewed_by', 'note', 'batch']
    const rows = items.map((x) => [
      x.key, x.review.status, x.review.risk, x.review.tier,
      x.review.reasons.join('；'), x.meta?.book || '', x.meta?.year || '',
      x.type, x.meta?.answer_source || '', x.meta?.solution_source || '',
      x.meta?.point_source || '', x.review.reviewed_at, x.review.reviewed_by,
      x.review.note, x.review.batch,
    ])
    const csv = [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\n')
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `审阅清单_${batch?.batch_id || new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const batchStat = batch
    ? stats?.batches.find((b) => b.batch === batch.batch_id)
    : null
  const decided = cur ? cur.review.status !== 'pending' : false
  const totalPages = Math.max(1, Math.ceil(total / 50))
  const meta = STAGE_BY_KEY[stage]

  if (!senior) {
    return (
      <div className="b-page max-w-[900px]">
        <div className="rounded-[var(--radius-card)] border border-border bg-surface p-5">
          <div className="text-[13px] font-semibold text-ink">正式题库目前只有高中</div>
          <p className="mt-1.5 max-w-[640px] text-[11.5px] leading-relaxed text-ink-faint">
            审阅队列统计的是 {meta.name} 的正式题；目前这一学段以诊断题和章节讲义为主。
            等正式题入库后，这一页会自动接上，不需要另建一套审阅。
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="b-scroll h-full overflow-y-auto bg-bg">
      <div className="mx-auto w-full max-w-[1440px] px-5 py-5">
        <header className="flex flex-wrap items-center gap-2">
          <p className="min-w-0 flex-1 text-[11px] leading-relaxed text-ink-faint">
            先自己判，再看答案。通过 / 需修改 / 存疑都会记住复核人和正文指纹；正文一改，原复核自动失效。
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-[11px] text-ink-faint">复核人</label>
            <input value={reviewer} onChange={(e) => setReviewer(e.target.value)}
              placeholder="可空" className="b-input h-8 w-[120px] text-[11.5px]" />
            <button onClick={() => { setReload((v) => v + 1); loadStats() }}
              className="b-btn b-btn-secondary h-8" title="刷新">
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />刷新
            </button>
            <button onClick={exportCsv} disabled={!items.length}
              className="b-btn b-btn-secondary h-8" title="导出当前队列/样本">
              <Download size={13} />CSV
            </button>
          </div>
        </header>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
          <Kpi label="总题" n={stats?.total || 0} />
          <Kpi label="已审" n={stats?.reviewed || 0} tone="has" />
          <Kpi label="待审" n={stats?.pending || 0} tone="warn" />
          <Kpi label="需修改" n={stats?.needs_fix || 0} tone="warn" />
          <Kpi label="存疑" n={stats?.flagged || 0} tone="danger" />
          <Kpi label="原复核失效" n={stats?.stale || 0} />
          <Kpi label="审阅覆盖率" text={stats ? pct(stats.review_rate) : '—'}
            tone={stats && stats.review_rate >= 0.8 ? 'has' : 'warn'} />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-[var(--radius-card)]
                        border border-border bg-surface px-3 py-2 shadow-[var(--shadow-card)]">
          <div className="flex rounded-lg bg-muted p-0.5">
            {([
              ['risk', '风险优先'],
              ['queue', '全部待审'],
              ['sample', '分层抽样'],
            ] as const).map(([v, label]) => (
              <button key={v} onClick={() => { setMode(v); if (v !== 'sample') setBatch(null) }}
                className={`rounded-md px-2.5 py-1 text-[11.5px] transition-colors
                  ${mode === v ? 'bg-surface text-ink shadow-[var(--shadow-card)]' : 'text-ink-faint hover:text-ink'}`}>
                {label}
              </button>
            ))}
          </div>
          {mode !== 'sample' ? (
            <>
              {mode !== 'risk' && (
                <select value={status} onChange={(e) => setStatus(e.target.value)}
                  className="h-8 rounded-lg border border-border bg-surface px-2 text-[11.5px] text-ink-soft">
                  <option value="pending">待审（含失效）</option>
                  <option value="approved">已通过</option>
                  <option value="needs_fix">需修改</option>
                  <option value="flagged">存疑</option>
                  <option value="all">全部</option>
                </select>
              )}
              <select value={risk} onChange={(e) => setRisk(e.target.value)}
                className="h-8 rounded-lg border border-border bg-surface px-2 text-[11.5px] text-ink-soft">
                <option value="">全部风险</option>
                <option value="high">高风险</option>
                <option value="medium">中风险</option>
                <option value="low">低风险</option>
              </select>
            </>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-ink-faint">抽</span>
              <input value={sampleN} onChange={(e) => setSampleN(e.target.value)}
                className="b-input h-8 w-[66px] text-[11.5px]" />
              <span className="text-[11px] text-ink-faint">道</span>
              <button onClick={runSample} disabled={loading}
                className="b-btn b-btn-primary h-8 px-2.5 text-[11.5px]">
                <Shuffle size={13} />{loading ? '抽样中…' : '抽一批'}
              </button>
            </div>
          )}
          <select value={book} onChange={(e) => setBook(e.target.value)}
            className="h-8 max-w-[180px] rounded-lg border border-border bg-surface px-2 text-[11.5px] text-ink-soft">
            <option value="">全部来源</option>
            {(stats?.by_book || []).map((b) => <option key={b.book} value={b.book}>{b.book}</option>)}
          </select>
          <select value={type} onChange={(e) => setType(e.target.value)}
            className="h-8 rounded-lg border border-border bg-surface px-2 text-[11.5px] text-ink-soft">
            {TYPE_OPTIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
          <input value={yearFrom} onChange={(e) => setYearFrom(e.target.value)}
            placeholder="年份 ≥" className="b-input h-8 w-[74px] text-[11.5px]" />
          <div className="relative">
            <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input value={kw} onChange={(e) => setKw(e.target.value)}
              placeholder="搜题干 / 出处 / 考点" className="b-input h-8 w-[190px] pl-6 text-[11.5px]" />
          </div>
          <button onClick={() => { setMask((v) => !v); setRevealed(false) }}
            className="b-chip ml-auto" title="默认遮住答案，先自己判一遍">
            {mask ? <EyeOff size={12} /> : <Eye size={12} />}
            {mask ? '遮住答案' : '显示答案'}
          </button>
        </div>

        {mode === 'sample' && batch && (
          <div className="mt-3 rounded-[var(--radius-card)] border border-border bg-surface p-3 shadow-[var(--shadow-card)]">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-[12px] font-semibold">批次 {batch.batch_id}</span>
              <span className="text-[11px] text-ink-faint">seed {batch.seed} · 总体 {batch.population} 道 · 抽 {batch.items.length} 道</span>
              {batchStat && (
                <span className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-ink-soft">
                  已审 {batchStat.n} · 要求修改/存疑 {batchStat.needs_fix + batchStat.flagged} ·
                  错误率 <b className="tnum">{pct(batchStat.error_rate)}</b>
                  <span className="text-ink-faint">（95% CI {pct(batchStat.ci_low)}–{pct(batchStat.ci_high)}）</span>
                </span>
              )}
            </div>
            <details className="mt-1.5">
              <summary className="cursor-pointer text-[10.5px] text-ink-faint">
                分层明细（{batch.strata.length} 层）
              </summary>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {batch.strata.map((s) => (
                  <span key={s.key} className="rounded-full border border-border bg-bg px-2 py-[2px] text-[10.5px] text-ink-faint">
                    {s.book} · {s.type_label} · 抽 {s.sample.toLocaleString()}/{s.population.toLocaleString()}
                  </span>
                ))}
              </div>
            </details>
          </div>
        )}

        <div className="mt-4 grid gap-4 xl:grid-cols-[330px_minmax(0,1fr)_300px]">
          {/* 队列 */}
          <aside className="min-w-0">
            <div className="b-card overflow-hidden">
              <div className="flex items-center justify-between border-b border-border px-3 py-2">
                <span className="text-[12px] font-semibold">
                  {mode === 'sample' ? '抽样清单' : '待审队列'}
                </span>
                <span className="tnum text-[10.5px] text-ink-faint">{total.toLocaleString()} 道</span>
              </div>
              <div className="max-h-[calc(100vh-310px)] min-h-[220px] overflow-y-auto">
                {loading && !items.length && (
                  <div className="space-y-2 p-3">
                    {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-16 rounded-lg" />)}
                  </div>
                )}
                {!loading && !items.length && (
                  <div className="b-empty m-3">
                    <ClipboardCheck size={24} className="text-border-strong" />
                    <div className="text-[12px] font-medium text-ink-soft">这个条件下没有题</div>
                    <div className="text-[11px]">换风险档/来源，或点“抽一批”做分层抽样</div>
                  </div>
                )}
                {items.map((x) => (
                  <button key={x.key} onClick={() => setSelKey(x.key)}
                    className={`block w-full border-b border-border/60 px-3 py-2 text-left
                      transition-colors last:border-b-0 ${x.key === cur?.key ? 'bg-brand-soft/50' : 'hover:bg-muted/60'}`}>
                    <div className="flex items-center gap-1.5">
                      <span className={`rounded-full border px-1.5 py-[1px] text-[9.5px] ${TIER_CLS[x.review.tier]}`}>
                        {TIER_LABEL[x.review.tier]}
                      </span>
                      <span className={`rounded-full border px-1.5 py-[1px] text-[9.5px] ${STATUS_CLS[x.review.status]}`}>
                        {x.review.short}
                      </span>
                      <span className="tnum ml-auto text-[9.5px] text-ink-faint">R{x.review.risk}</span>
                    </div>
                    <div className="mt-1 line-clamp-2 text-[11.5px] leading-snug text-ink-soft">
                      {plain(x.stem).slice(0, 90)}
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-[9.5px] text-ink-faint">
                      <span className="truncate">{x.meta?.book || '未标'} · {x.meta?.year || '—'}</span>
                      {!!x.review.reasons.length && (
                        <span className="ml-auto shrink-0 text-warn">{x.review.reasons.length} 条线索</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
              {mode !== 'sample' && totalPages > 1 && (
                <div className="flex items-center justify-between border-t border-border px-3 py-2">
                  <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}
                    className="b-btn b-btn-ghost h-7 px-2 text-[11px]"><ChevronLeft size={13} />上一页</button>
                  <span className="tnum text-[10.5px] text-ink-faint">{page}/{totalPages}</span>
                  <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages}
                    className="b-btn b-btn-ghost h-7 px-2 text-[11px]">下一页<ChevronRight size={13} /></button>
                </div>
              )}
            </div>
          </aside>

          {/* 审阅卡 */}
          <main className="min-w-0">
            {!cur ? (
              <div className="b-card b-empty min-h-[360px]">
                <Scale size={28} className="text-border-strong" />
                <div className="text-[13px] font-medium text-ink-soft">队列是空的</div>
                <div className="text-[11px]">点“抽一批”做分层抽样，或换筛选条件</div>
              </div>
            ) : (
              <article className="b-card overflow-hidden">
                <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
                  <span className="rounded-full border border-border bg-muted px-2 py-[1px] text-[10.5px] text-ink-soft">
                    {cur.type_label || cur.type}
                  </span>
                  <span className={`rounded-full border px-2 py-[1px] text-[10.5px] ${STATUS_CLS[cur.review.status]}`}>
                    {cur.review.label}
                  </span>
                  <span className={`rounded-full border px-2 py-[1px] text-[10.5px] ${TIER_CLS[cur.review.tier]}`}>
                    {TIER_LABEL[cur.review.tier]} · R{cur.review.risk}
                  </span>
                  {cur.review.batch && (
                    <span className="rounded-full border border-border px-2 py-[1px] text-[10px] text-ink-faint">
                      批次 {cur.review.batch}
                    </span>
                  )}
                  <button onClick={() => onOpenSource?.(cur.key)}
                    disabled={!onOpenSource}
                    title="去题库打开这道题，并直接进入改源码"
                    className="press ml-auto inline-flex h-7 items-center gap-1.5 rounded-lg
                               border border-border bg-surface px-2.5 text-[11px] text-ink-soft
                               hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink
                               disabled:opacity-40">
                    <FileCode2 size={12} />去题库改源码
                  </button>
                  <span className="text-[10.5px] text-ink-faint">
                    {cur.review.reviewed_by ? `复核：${cur.review.reviewed_by} · ` : ''}
                    {cur.review.reviewed_at || '未复核'}
                  </span>
                </div>

                <div className="px-4 py-3">
                  <div className="text-[10.5px] text-ink-faint">
                    {cur.meta?.book || '未标来源'} · {cur.meta?.source_label || '—'}
                    {cur.meta?.year ? ` · ${cur.meta.year}` : ''}
                    {cur.meta?.region ? ` · ${cur.meta.region}` : ''}
                  </div>
                  <div className="q-stem mt-2 text-[13.5px] leading-relaxed text-ink">
                    {cur.blocks?.stem?.length
                      ? renderBlocks(cur.blocks.stem, '')
                      : <span className="whitespace-pre-wrap">{cur.stem}</span>}
                  </div>
                  {!!cur.options?.length && (
                    <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                      {cur.options.map((o, i) => (
                        <div key={o.label} className="flex gap-1.5 text-[12.5px] leading-relaxed text-ink-soft">
                          <b className="shrink-0 text-ink">{o.label}.</b>
                          <span className="min-w-0">
                            {cur.blocks?.options?.[i]?.length
                              ? renderBlocks(cur.blocks.options[i], '')
                              : <span className="whitespace-pre-wrap">{o.text}</span>}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-1.5 rounded-xl border border-border bg-bg px-2.5 py-2 text-[10.5px]">
                    <span className="text-ink-faint">来源</span>
                    <Prov label={`答案 ${srcLabel(cur.meta?.answer_source)}`} tone={srcTone(cur.meta?.answer_source)} />
                    <Prov label={`解析 ${srcLabel(cur.meta?.solution_source)}`} tone={srcTone(cur.meta?.solution_source)} />
                    <Prov label={`考点 ${srcLabel(cur.meta?.point_source)}`} tone={srcTone(cur.meta?.point_source)} />
                    <Prov label={`难度 ${srcLabel(cur.meta?.difficulty_source)}`} tone={srcTone(cur.meta?.difficulty_source)} />
                    {!!cur.review.reasons.length && (
                      <span className="ml-auto inline-flex items-center gap-1 text-warn">
                        <TriangleAlert size={11} />{cur.review.reasons.length} 条风险线索
                      </span>
                    )}
                  </div>

                  {!!cur.review.reasons.length && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {cur.review.reasons.map((r) => (
                        <span key={r} className="rounded-full border border-warn-line bg-warn-soft px-2 py-[1px] text-[10.5px] text-warn">
                          {r}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-3">
                    {mask && !revealed ? (
                      <button onClick={() => setRevealed(true)}
                        className="flex w-full flex-col items-center gap-1 rounded-xl border border-dashed border-border-strong bg-bg px-3 py-5 text-ink-faint transition-colors hover:border-brand-line hover:bg-brand-soft/30 hover:text-brand-ink">
                        <Eye size={18} />
                        <span className="text-[12px] font-medium">先自己判一遍，再显示答案与解析</span>
                        <span className="text-[10.5px]">快捷键 V</span>
                      </button>
                    ) : (
                      <>
                        <div className="rounded-xl border border-danger/20 bg-danger-soft/40 px-3 py-2">
                          <div className="text-[10px] font-semibold tracking-wide text-danger">答案</div>
                          <div className="mt-0.5 text-[14px] font-semibold text-danger">
                            {cur.answer || '（没有答案）'}
                          </div>
                          {!!cur.point_titles?.length && (
                            <div className="mt-1 text-[10.5px] text-ink-faint">
                              考点：{cur.point_titles.join(' · ')}
                            </div>
                          )}
                        </div>
                        <div className="mt-2 rounded-xl border border-border bg-surface px-3 py-2">
                          <div className="flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-ink-faint">
                            <ClipboardCheck size={11} />解析
                          </div>
                          <div className="q-solution mt-1 text-[12px] leading-relaxed text-ink-soft">
                            {cur.blocks?.solution?.length
                              ? renderBlocks(cur.blocks.solution, '')
                              : <span className="whitespace-pre-wrap">{cur.solution || '（没有解析）'}</span>}
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  <div className="mt-3 rounded-xl border border-border bg-bg p-2.5">
                    <div className="mb-1.5 flex items-center gap-1.5">
                      <CircleAlert size={12} className="text-ink-faint" />
                      <span className="text-[11px] font-semibold text-ink-soft">审阅备注</span>
                      <span className="text-[10px] text-ink-faint">会记在题目 meta 里，跟着复核指纹走</span>
                    </div>
                    <textarea value={note} onChange={(e) => setNote(e.target.value)}
                      rows={2} placeholder="例：图 2 缺失；解析第 3 步符号反了；答案 B 应为 C…"
                      className="w-full resize-y rounded-lg border border-border bg-surface px-2.5 py-2 text-[11.5px] leading-relaxed text-ink outline-none focus:border-brand-line" />
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      {DECIDE.map((d) => {
                        const Icon = d.icon
                        return (
                          <button key={d.s} onClick={() => decide(d.s)} disabled={saving}
                            className={`press inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-[11.5px] font-medium text-white disabled:opacity-50 ${d.cls}`}>
                            <Icon size={13} />{d.label}
                          </button>
                        )
                      })}
                      <button onClick={() => decide('pending')} disabled={saving || !decided}
                        className="b-btn b-btn-ghost h-8 px-2.5 text-[11px]">
                        <SkipForward size={13} />撤销复核
                      </button>
                      <span className="ml-auto text-[10px] text-ink-faint">
                        {saving ? '保存中…' : 'A 通过 · F 需改 · G 存疑 · V 显示答案 · J/K 上下'}
                      </span>
                    </div>
                  </div>
                </div>
              </article>
            )}
          </main>

          {/* 统计 */}
          <aside className="min-w-0 space-y-3">
            <div className="b-card p-3">
              <div className="flex items-baseline justify-between">
                <span className="text-[12px] font-semibold">审阅进度</span>
                <span className="tnum text-[11px] text-ink-faint">
                  {stats ? `${stats.reviewed.toLocaleString()}/${stats.total.toLocaleString()}` : '—'}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-has"
                  style={{ width: `${Math.max(0.5, Math.min(100, (stats?.review_rate || 0) * 100))}%` }} />
              </div>
              <div className="mt-2 space-y-1 text-[10.5px] text-ink-faint">
                <Row k="待审（含失效）" v={stats?.pending || 0} />
                <Row k="已通过" v={stats?.approved || 0} />
                <Row k="需修改" v={stats?.needs_fix || 0} tone="warn" />
                <Row k="存疑" v={stats?.flagged || 0} tone="danger" />
                <Row k="原复核失效" v={stats?.stale || 0} />
                <Row k="最近复核" v={stats?.last_reviewed_at || '—'} />
              </div>
            </div>

            <div className="b-card p-3">
              <div className="text-[12px] font-semibold">风险分布</div>
              <div className="mt-2 space-y-1.5">
                {(['high', 'medium', 'low'] as Tier[]).map((t) => {
                  const n = stats?.risk[t] || 0
                  const max = Math.max(1, stats?.risk.high || 0, stats?.risk.medium || 0, stats?.risk.low || 0)
                  return (
                    <div key={t}>
                      <div className="flex items-center justify-between text-[10.5px] text-ink-faint">
                        <span>{TIER_LABEL[t]}</span><span className="tnum">{n.toLocaleString()}</span>
                      </div>
                      <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className={`h-full rounded-full ${t === 'high' ? 'bg-danger' : t === 'medium' ? 'bg-warn' : 'bg-has'}`}
                          style={{ width: `${Math.max(2, (n / max) * 100)}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="b-card p-3">
              <div className="text-[12px] font-semibold">按来源</div>
              <div className="mt-2 space-y-1">
                {(stats?.by_book || []).slice(0, 7).map((b) => (
                  <div key={b.book} className="flex items-center gap-2 text-[10.5px]">
                    <span className="min-w-0 flex-1 truncate text-ink-soft">{b.book}</span>
                    <span className="tnum text-ink-faint">{b.pending.toLocaleString()}/{b.total.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="b-card p-3">
              <div className="text-[12px] font-semibold">抽样批次</div>
              {!stats?.batches?.length ? (
                <div className="mt-1.5 text-[10.5px] text-ink-faint">还没有抽样复核记录</div>
              ) : (
                <div className="mt-2 space-y-2">
                  {stats.batches.slice(0, 5).map((b) => (
                    <div key={b.batch}>
                      <div className="flex items-center gap-1.5 text-[10px]">
                        <span className="min-w-0 flex-1 truncate text-ink-soft">{b.batch}</span>
                        <span className="tnum text-ink-faint">{b.n} 道</span>
                      </div>
                      <div className="mt-0.5 text-[10px] text-ink-faint">
                        错误率 <b className="tnum text-warn">{pct(b.error_rate)}</b>
                        <span className="ml-1">95% CI {pct(b.ci_low)}–{pct(b.ci_high)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}

function Kpi({ label, n, text, tone = 'ink' }: {
  label: string; n?: number; text?: string
  tone?: 'ink' | 'has' | 'warn' | 'danger'
}) {
  const color = { ink: 'text-ink', has: 'text-has', warn: 'text-warn', danger: 'text-danger' }[tone]
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface px-3 py-2 shadow-[var(--shadow-card)]">
      <div className="text-[10px] text-ink-faint">{label}</div>
      <div className={`tnum mt-0.5 text-[19px] font-semibold leading-none ${color}`}>
        {text ?? (n ?? 0).toLocaleString()}
      </div>
    </div>
  )
}
function Row({ k, v, tone = '' }: { k: string; v: string | number; tone?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span>{k}</span>
      <span className={`tnum ${tone === 'warn' ? 'text-warn' : tone === 'danger' ? 'text-danger' : 'text-ink-soft'}`}>
        {typeof v === 'number' ? v.toLocaleString() : v}
      </span>
    </div>
  )
}
function Prov({ label, tone }: { label: string; tone: string }) {
  return (
    <span className={`rounded-full border px-1.5 py-[1px] text-[10px] ${tone}`}>{label}</span>
  )
}
