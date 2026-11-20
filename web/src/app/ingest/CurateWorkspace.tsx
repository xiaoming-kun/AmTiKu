/** DeepSeek 整理题库：给**已有题**补考点/难度/答案/解析。
 *
 *  和「DeepSeek 录题」的区别：
 *  - 这里不产生新题，只读已有题；
 *  - DeepSeek 只返回建议，不写库；
 *  - 每条建议都要人在页面上勾选后，才通过现有的 PATCH / solution 接口写入。
 */
import { useEffect, useState } from 'react'
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronRight, Loader2,
  Search, Sparkles, Wand2,
} from 'lucide-react'
import type { Q } from '@/lib/types'
import type { Stage } from '@/lib/stage'
import { STAGE_BY_KEY } from '@/lib/stage'
import { api, reportErr } from '@/lib/api'
import { renderBlocks } from '@/lib/render'
import { CloseBtn } from '@/app/ui'

type Task = 'points' | 'solution' | 'answer'

const TASKS: {
  id: Task; label: string; desc: string; missing: string; backend: string[]
}[] = [
  { id: 'points', label: '缺考点', desc: '顺带建议难度', missing: '标签', backend: ['points', 'difficulty'] },
  { id: 'solution', label: '缺解析', desc: '补写解析正文', missing: '解析', backend: ['solution'] },
  { id: 'answer', label: '缺答案', desc: '只补最终答案', missing: '答案', backend: ['answer'] },
]

type Proposal = {
  points?: string[]; point_titles?: string[]; difficulty?: string
  answer?: string; solution?: string
  answer_blocks?: any[]; solution_blocks?: any[]
}
type CurateItem = {
  key: string; ok: boolean; error?: string
  proposal?: Proposal
  current?: { points?: string[]; difficulty?: string; answer?: string; solution?: string }
}

type ApplySel = { points?: boolean; difficulty?: boolean; answer?: boolean; solution?: boolean }

export default function CurateWorkspace({ stage, onBack, onDone }: {
  stage: Stage
  onBack: () => void
  onDone: () => void
}) {
  const [task, setTask] = useState<Task>('points')
  const [items, setItems] = useState<Q[]>([])
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [scanning, setScanning] = useState(false)
  const [curating, setCurating] = useState(false)
  const [applying, setApplying] = useState(false)
  const [applyAt, setApplyAt] = useState(0)
  const [proposals, setProposals] = useState<CurateItem[]>([])
  const [activeKey, setActiveKey] = useState('')
  const [applySel, setApplySel] = useState<Record<string, ApplySel>>({})
  const [applied, setApplied] = useState<Set<string>>(new Set())
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [cost, setCost] = useState<{ cny: number; seconds: number } | null>(null)

  const meta = STAGE_BY_KEY[stage]
  const currentTask = TASKS.find((x) => x.id === task)!

  useEffect(() => {
    setItems([]); setProposals([]); setSelected(new Set()); setApplied(new Set())
    setErrors({}); setErr(''); setMsg(''); setCost(null); setTotal(0); setActiveKey('')
  }, [task])


  const scan = async () => {
    setScanning(true); setErr(''); setMsg(''); setProposals([]); setApplied(new Set())
    setErrors({}); setCost(null)
    try {
      // 不再截断前 10 道：本地缺口索引有多少取多少（列表接口单页 1000，按页取完）。
      const PAGE = 1000
      const all: Q[] = []
      let offset = 0
      let total = 0
      for (;;) {
        const d: any = await api.list({
          stage, missing: currentTask.missing, limit: String(PAGE), offset: String(offset),
          sort: 'new', lite: '1',
        })
        const page: Q[] = d.items || []
        total = Number(d.total || total || page.length)
        all.push(...page)
        offset += page.length
        if (!page.length || offset >= total || page.length < PAGE) break
      }
      setItems(all)
      setTotal(total || all.length)
      setSelected(new Set(all.map((q) => q.key)))
      setActiveKey(all[0]?.key || '')
      if (!all.length) setMsg(`这个学段暂时没有「${currentTask.label}」的题`)
    } catch (e) {
      setErr(String((e as any)?.message || e)); reportErr(e)
    } finally { setScanning(false) }
  }

  const curate = async () => {
    if (!selected.size) { setErr('先勾选要整理的题'); return }
    setCurating(true); setErr(''); setMsg(''); setProposals([]); setApplied(new Set())
    setErrors({}); setCost(null)
    try {
      const d: any = await api.aiCurate({
        keys: [...selected], tasks: currentTask.backend, stage,
      })
      const ps: CurateItem[] = d.items || []
      setProposals(ps)
      setActiveKey((prev) => prev || ps[0]?.key || '')
      setCost({ cny: Number(d.cost_cny || 0), seconds: Number(d.seconds || 0) })
      const next: Record<string, ApplySel> = {}
      for (const p of ps) {
        next[p.key] = p.ok ? {
          points: !!p.proposal?.points?.length,
          difficulty: !!p.proposal?.difficulty,
          answer: !!p.proposal?.answer?.trim(),
          solution: !!p.proposal?.solution?.trim(),
        } : {}
      }
      setApplySel(next)
      if (d.errors?.length) setMsg(`有 ${d.errors.length} 道没整理成功，已标在卡片上`)
    } catch (e) {
      setErr(String((e as any)?.message || e)); reportErr(e)
    } finally { setCurating(false) }
  }

  const writeProposal = async (chosen: CurateItem[]) => {
    if (!chosen.length) { setErr('没有可写入的建议'); return }
    setApplying(true); setApplyAt(0); setErr(''); setMsg('')
    let ok = 0
    for (let i = 0; i < chosen.length; i++) {
      const p = chosen[i]
      setApplyAt(i + 1)
      const pick = applySel[p.key] || {}
      if (!(pick.points || pick.difficulty || pick.answer || pick.solution)) continue
      try {
        if (pick.points || pick.difficulty) {
          const body: Record<string, unknown> = {}
          if (pick.points && p.proposal?.points?.length) body.points = p.proposal.points
          if (pick.difficulty && p.proposal?.difficulty) body.difficulty = p.proposal.difficulty
          if (Object.keys(body).length) await api.patch(p.key, body)
        }
        if (pick.answer || pick.solution) {
          const body: Record<string, unknown> = { dry_run: false, source: 'deepseek' }
          if (pick.answer && p.proposal?.answer?.trim()) body.answer = p.proposal.answer.trim()
          if (pick.solution && p.proposal?.solution?.trim()) body.solution = p.proposal.solution.trim()
          if (Object.keys(body).length > 2) await api.solution(p.key, body as any)
        }
        setApplied((s) => new Set(s).add(p.key))
        ok++
        try {
          const fresh: Q = await api.get(p.key)
          setItems((old) => old.map((q) => q.key === p.key ? fresh : q))
          if (p.proposal?.points?.length) {
            setProposals((old) => old.map((x) => x.key === p.key ? { ...x,
              current: { points: fresh.points, difficulty: fresh.difficulty,
                         answer: fresh.answer, solution: fresh.solution } } : x))
          }
        } catch { /* 写入成功；刷新详情失败不掩盖成功 */ }
      } catch (e) {
        setErrors((m) => ({ ...m, [p.key]: String((e as any)?.message || e) }))
      }
    }
    setApplying(false)
    if (ok) {
      setMsg(`已写入 ${ok} 道；补解析的题原复核会失效，请重新审阅。`)
      try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
      onDone()
    }
  }

  const apply = async () => {
    const chosen = proposals.filter((p) => p.ok && !applied.has(p.key))
    await writeProposal(chosen)
  }

  const applyOne = async (p: CurateItem) => {
    const pick = applySel[p.key] || {}
    if (!(pick.points || pick.difficulty || pick.answer || pick.solution)) {
      setErr('先勾选要写入的字段'); return
    }
    await writeProposal([p])
  }

  const allOn = items.length > 0 && items.every((q) => selected.has(q.key))
  const active = items.find((q) => q.key === activeKey) || items[0] || null
  const activeP = active ? proposals.find((p) => p.key === active.key) : undefined
  const activePick = active ? (applySel[active.key] || {}) : {}
  const setActivePick = (patch: ApplySel) => {
    if (!active) return
    setApplySel((m) => ({ ...m, [active.key]: { ...activePick, ...patch } }))
  }

  // 列表接口是瘦身版（不带宽高答案/解析块）；详情页才是完整 IR。
  // 三列要像题目详情那样渲染，当前题必须单独取一次 full detail。
  useEffect(() => {
    const key = active?.key
    if (!key) return
    let alive = true
    api.get(key).then((d: Q) => {
      if (!alive) return
      setItems((old) => old.map((q) => q.key === d.key ? { ...q, ...d } : q))
    }).catch(() => { /* 详情取不到就先用列表里的瘦身数据 */ })
    return () => { alive = false }
  }, [active?.key])

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <header className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border bg-surface px-4 md:px-6">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[10px] grad-primary
                         text-[14px] font-bold text-white shadow-[var(--shadow-brand)]" aria-hidden>A</span>
        <span className="hidden text-[14px] font-semibold tracking-[-.02em] sm:inline">AmMath</span>
        <span className="hidden text-border-strong sm:inline">/</span>
        <button onClick={onBack}
          className="press inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-[12px]
                     text-ink-faint hover:bg-muted hover:text-ink">
          <ArrowLeft size={14} /><span className="hidden sm:inline">录入</span>
        </button>
        <span className="hidden text-border-strong sm:inline">/</span>
        <span className="flex items-center gap-1.5 whitespace-nowrap text-[14px] font-semibold">
          <Wand2 size={15} className="text-brand" />DeepSeek 整理题库
        </span>
        <span className="hidden rounded-full border border-brand-line bg-brand-soft px-1.5 py-[1px]
                         text-[10px] font-medium text-brand-ink sm:inline">已有题 · 只生成建议</span>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-[10.5px] text-ink-faint sm:inline">
            {meta.name} · 只读本地缺口
          </span>
          <CloseBtn onClick={onBack} title="返回录题方式选择" />
        </div>
      </header>

      <div className="b-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="b-page max-w-[1480px]">
          <div className="flex flex-wrap items-end gap-2 border-b border-border pb-4">
            <div className="min-w-0 flex-1">
              <h1 className="text-[22px] font-semibold tracking-tight">整理已有题库</h1>
              <p className="mt-1 max-w-[680px] text-[12px] leading-relaxed text-ink-soft">
                DeepSeek 只读题目，给出考点/难度/答案/解析建议；你勾选并确认后才写回。
                不新增题目，不改题干，不覆盖已有字段。
              </p>
            </div>
            <div className="flex items-center gap-1.5 text-[10.5px] text-ink-faint">
              <CheckCircle2 size={12} />写入走现有单题接口
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {TASKS.map((t) => {
              const on = task === t.id
              return (
                <button key={t.id} onClick={() => setTask(t.id)}
                  className={`press rounded-[var(--radius-card)] border p-3 text-left transition-colors ${
                    on ? 'border-brand-line bg-brand-soft/50' : 'border-border bg-surface hover:border-border-strong'}`}>
                  <div className="flex items-center gap-2">
                    <span className={`grid h-6 w-6 place-items-center rounded-md ${
                      on ? 'bg-brand text-white' : 'bg-muted text-ink-faint'}`}>
                      {on ? <Check size={13} /> : <ChevronRight size={13} />}
                    </span>
                    <span className={`text-[12.5px] font-semibold ${on ? 'text-brand-ink' : 'text-ink'}`}>
                      {t.label}
                    </span>
                  </div>
                  <div className="mt-1.5 text-[10.5px] text-ink-faint">{t.desc}</div>
                </button>
              )
            })}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button onClick={() => void scan()} disabled={scanning || curating || applying}
              className="press b-btn b-btn-secondary h-8">
              {scanning ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
              {scanning ? '扫描中…' : '扫描待整理'}
            </button>
            <span className="text-[10.5px] text-ink-faint">
              只查本地缺口索引，有多少取多少；不会把整库发给模型
            </span>
            {!!total && <span className="ml-auto tnum text-[10.5px] text-ink-faint">
              这个学段共 {total} 道「{currentTask.label}」
            </span>}
          </div>

          {err && (
            <div className="mt-3 flex items-start gap-2 rounded-lg border border-warn-line bg-warn-soft
                            px-3 py-2 text-[11.5px] text-warn">
              <AlertTriangle size={13} className="mt-[1px] shrink-0" />
              <span className="min-w-0 flex-1">{err}</span>
              <button onClick={() => setErr('')} className="underline">知道了</button>
            </div>
          )}
          {msg && (
            <div className="mt-3 rounded-lg border border-has-line bg-has-soft px-3 py-2 text-[11.5px] text-has">
              {msg}
            </div>
          )}

          {items.length > 0 && (
            <div className="mt-4 grid gap-3 lg:grid-cols-[280px_minmax(0,1fr)_minmax(0,1fr)]">
              {/* 左：题单 + 批处理 */}
              <aside className="min-h-0 rounded-[var(--radius-card)] border border-border bg-surface">
                <div className="border-b border-border px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <h2 className="text-[12.5px] font-semibold">待整理</h2>
                    <span className="tnum text-[10px] text-ink-faint">{selected.size}/{items.length}</span>
                    <button onClick={() => setSelected(allOn ? new Set() : new Set(items.map((q) => q.key)))}
                      className="ml-auto text-[10px] text-brand-ink underline underline-offset-2">
                      {allOn ? '清空' : '全选'}
                    </button>
                  </div>
                  <button onClick={() => void curate()} disabled={!selected.size || curating || applying}
                    className="press b-btn b-btn-primary mt-2 h-8 w-full">
                    {curating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                    {curating ? 'DeepSeek 整理中…' : `整理选中 ${selected.size} 道`}
                  </button>
                  {curating && <div className="progress-track mt-2" />}
                </div>
                <div className="b-scroll max-h-[calc(100vh-320px)] min-h-[280px] overflow-y-auto p-1.5">
                  {items.map((q) => {
                    const on = selected.has(q.key)
                    const isActive = active?.key === q.key
                    return (
                      <div key={q.key} onClick={() => setActiveKey(q.key)}
                        className={`mb-1 cursor-pointer rounded-lg border px-2 py-1.5 transition-colors ${isActive
                          ? 'border-brand-line bg-brand-soft/50' : 'border-transparent hover:bg-bg'}`}>
                        <div className="flex items-start gap-1.5">
                          <input type="checkbox" checked={on}
                            onClick={(e) => e.stopPropagation()}
                            onChange={() => setSelected((s) => {
                              const n = new Set(s); if (on) n.delete(q.key); else n.add(q.key); return n
                            })}
                            className="mt-[3px] accent-[var(--color-brand)]" />
                          <div className="min-w-0 flex-1">
                            <div className="flex min-w-0 items-center gap-1 text-[9.5px] text-ink-faint">
                              <span className="shrink-0 whitespace-nowrap rounded bg-muted px-1 py-[0.5px] text-ink-soft">{q.type_label}</span>
                              {!q.points?.length && <span className="shrink-0 whitespace-nowrap text-warn">缺考点</span>}
                              <span className="ml-auto min-w-0 max-w-[62px] truncate text-right font-mono">
                                {q.key.split('/').pop()}
                              </span>
                            </div>
                            <div className="mt-0.5 line-clamp-2 text-[10.5px] leading-snug text-ink-soft">
                              {renderBlocks(q.blocks?.stem) || q.stem}
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="border-t border-border p-2">
                  <button onClick={() => void apply()} disabled={applying || curating || !proposals.length}
                    className="press b-btn b-btn-secondary h-7 w-full text-[10.5px]">
                    {applying ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                    {applying ? `写入中 ${applyAt}/${proposals.filter((p) => p.ok).length}` : '写入全部勾选'}
                  </button>
                </div>
              </aside>

              {/* 中：原题 */}
              <section className="min-w-0 rounded-[var(--radius-card)] border border-border bg-surface">
                <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
                  <h2 className="text-[12.5px] font-semibold">原题</h2>
                  <span className="text-[9.5px] text-ink-faint">题库现有内容 · 只读</span>
                  {active && <span className="ml-auto font-mono text-[9px] text-ink-faint">{active.key.split('/').pop()}</span>}
                </div>
                {active ? (
                  <div className="b-scroll max-h-[calc(100vh-320px)] min-h-[280px] overflow-y-auto px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-ink-faint">
                      <span className="rounded bg-muted px-1.5 py-[1px] text-ink-soft">{active.type_label}</span>
                      {active.missing?.map((m) => (
                        <span key={m} className="rounded bg-warn-soft px-1.5 py-[1px] text-warn">缺{m}</span>
                      ))}
                    </div>
                    <div className="mt-2 text-[12.5px] leading-[1.95] text-ink">
                      {renderBlocks(active.blocks?.stem) || active.stem}
                    </div>
                    {active.options?.length > 0 && (
                      <div className="mt-2 space-y-1 text-[11.5px] leading-relaxed text-ink-soft">
                        {active.options.map((o, i) => (
                          <div key={o.label} className="flex gap-1.5">
                            <span className="shrink-0 font-medium text-ink">{o.label}.</span>
                            <span>{renderBlocks(active.blocks?.options?.[i]) || o.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="mt-3 rounded-lg border border-border bg-bg p-2.5">
                      <div className="text-[9.5px] font-medium text-ink-faint">现有答案</div>
                      <div className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-ink-soft">
                        {renderBlocks(active.blocks?.answer) || active.answer || <span className="text-ink-faint">（空）</span>}
                      </div>
                    </div>
                    <div className="mt-2 rounded-lg border border-border bg-bg p-2.5">
                      <div className="text-[9.5px] font-medium text-ink-faint">现有解析</div>
                      <div className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-ink-soft">
                        {renderBlocks(active.blocks?.solution) || active.solution || <span className="text-ink-faint">（空）</span>}
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1 text-[9.5px] text-ink-faint">
                      <span>现有考点：{active.point_titles?.length ? active.point_titles.join(' · ') : '无'}</span>
                      <span>· 难度：{active.difficulty || '无'}</span>
                    </div>
                  </div>
                ) : <div className="p-6 text-[11px] text-ink-faint">左边选一道题</div>}
              </section>

              {/* 右：修改后 */}
              <section className="min-w-0 rounded-[var(--radius-card)] border border-brand-line bg-surface">
                <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
                  <h2 className="text-[12.5px] font-semibold text-brand-ink">修改后</h2>
                  <span className="text-[9.5px] text-ink-faint">DeepSeek 建议 · 未写入</span>
                  {cost && <span className="ml-auto tnum text-[9.5px] font-semibold text-danger">¥{cost.cny.toFixed(3)}</span>}
                </div>
                {!active ? <div className="p-6 text-[11px] text-ink-faint">左边选一道题</div> : !activeP ? (
                  <div className="p-6 text-[11px] leading-relaxed text-ink-faint">
                    左边点「整理选中」后，这里显示这道题的修改后版本。
                  </div>
                ) : !activeP.ok ? (
                  <div className="p-4 text-[11px] text-warn">{activeP.error || '这道题没有返回建议'}</div>
                ) : (
                  <div className="b-scroll max-h-[calc(100vh-320px)] min-h-[280px] overflow-y-auto px-4 py-3">
                    <div className="text-[12.5px] leading-[1.95] text-ink">
                      {renderBlocks(active.blocks?.stem) || active.stem}
                    </div>
                    {active.options?.length > 0 && (
                      <div className="mt-2 space-y-1 text-[11.5px] leading-relaxed text-ink-soft">
                        {active.options.map((o, i) => (
                          <div key={o.label} className="flex gap-1.5">
                            <span className="shrink-0 font-medium text-ink">{o.label}.</span>
                            <span>{renderBlocks(active.blocks?.options?.[i]) || o.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {(activeP.proposal?.points?.length || activeP.proposal?.difficulty) && (
                      <div className="mt-3 rounded-lg border border-brand-line bg-brand-soft/30 p-2.5">
                        <label className="flex items-center gap-2 text-[10.5px] font-semibold text-brand-ink">
                          <input type="checkbox" checked={!!activePick.points || !!activePick.difficulty}
                            onChange={(e) => setActivePick({ points: e.target.checked, difficulty: e.target.checked })}
                            className="accent-[var(--color-brand)]" />
                          写入考点 / 难度
                        </label>
                        <div className="mt-1.5 text-[10.5px] leading-relaxed text-ink-soft">
                          {activeP.proposal.point_titles?.length
                            ? activeP.proposal.point_titles.join(' · ')
                            : '无可靠考点'}
                          {activeP.proposal.difficulty ? ` · ${activeP.proposal.difficulty}` : ''}
                        </div>
                      </div>
                    )}
                    <div className="mt-2 rounded-lg border border-border bg-bg p-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-[9.5px] font-medium text-ink-faint">答案</span>
                        {activeP.proposal?.answer?.trim() && (
                          <label className="ml-auto flex items-center gap-1 text-[9.5px] text-ink-soft">
                            <input type="checkbox" checked={!!activePick.answer}
                              onChange={(e) => setActivePick({ answer: e.target.checked })}
                              className="accent-[var(--color-brand)]" />写入
                          </label>
                        )}
                      </div>
                      <div className="mt-1 text-[11px] leading-relaxed">
                        {activeP.proposal?.answer?.trim()
                          ? <span className="text-has">
                              {renderBlocks(activeP.proposal.answer_blocks as any)
                                || activeP.proposal.answer}
                            </span>
                          : <span className="text-ink-faint">保持原样：{active.answer || '（空）'}</span>}
                      </div>
                    </div>
                    <div className="mt-2 rounded-lg border border-border bg-bg p-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-[9.5px] font-medium text-ink-faint">解析</span>
                        {activeP.proposal?.solution?.trim() && (
                          <label className="ml-auto flex items-center gap-1 text-[9.5px] text-ink-soft">
                            <input type="checkbox" checked={!!activePick.solution}
                              onChange={(e) => setActivePick({ solution: e.target.checked })}
                              className="accent-[var(--color-brand)]" />写入
                          </label>
                        )}
                      </div>
                      <div className="mt-1 max-h-52 overflow-y-auto text-[10.5px] leading-relaxed">
                        {activeP.proposal?.solution?.trim()
                          ? <div className="q-solution text-ink-soft">
                              {renderBlocks(activeP.proposal.solution_blocks as any)
                                || <span className="whitespace-pre-wrap">{activeP.proposal.solution}</span>}
                            </div>
                          : <span className="text-ink-faint">保持原样{active.solution ? '' : '（空）'}</span>}
                      </div>
                    </div>
                    {errors[active.key] && <div className="mt-2 text-[10px] text-warn">写入失败：{errors[active.key]}</div>}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <button onClick={() => void applyOne(activeP)} disabled={applying || applied.has(active.key)}
                        className="press b-btn b-btn-primary h-8">
                        {applying ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                        {applied.has(active.key) ? '这道题已写入' : '写入这道题'}
                      </button>
                      <span className="text-[9.5px] text-ink-faint">只写勾选字段；走现有单题接口</span>
                    </div>
                  </div>
                )}
              </section>
            </div>
          )}

          {!scanning && !items.length && !err && (
            <div className="mt-6 flex flex-col items-center justify-center gap-2 rounded-[var(--radius-card)]
                            border border-dashed border-border-strong px-6 py-12 text-center">
              <Wand2 size={22} className="text-border-strong" />
              <div className="text-[12.5px] font-medium text-ink">先扫描一批待整理的题</div>
              <div className="max-w-[460px] text-[10.5px] leading-relaxed text-ink-faint">
                选择上面的「缺考点 / 缺解析 / 缺答案」，点扫描。扫描只走本地缺口索引，
                取全部本地缺口；DeepSeek 只收到你勾选的题，不会扫描整库。建议确认后才写入。
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
