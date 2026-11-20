/** 单题校对：先像题库一样选题，再让 DeepSeek 独立做一遍。
 *
 *  选题页在 `ProofPicker`（和题库共用检索/筛选口径），这里只管流程切换
 *  与校对详情：
 *    · 选中题目 → 看现有答案/解析/配图 → DeepSeek 校对 → 勾选写回；
 *    · 只生成建议，不自动写库；答案/解析走现有单题接口；
 *    · TikZ 不自动写，复制后到「改源码」里确认。
 */
import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowLeft, Check, CheckCircle2, ChevronRight, Clipboard, Code2,
  FileText, Image as ImageIcon, ImagePlus, Info, ListFilter, Loader2, RefreshCw, ShieldCheck,
  Sparkles, Stamp, Timer, Wand2,
} from 'lucide-react'
import type { Q } from '@/lib/types'
import type { Stage } from '@/lib/stage'
import { STAGE_BY_KEY } from '@/lib/stage'
import { api } from '@/lib/api'
import { useQuestionList } from '@/lib/useQuestionList'
import { EMPTY_FILTERS } from '@/lib/urlState'
import type { Block } from '@/lib/render'
import { dispPoint, hasImageOptions, optionRange, starsLabel, DIFF_STARS } from '@/lib/display'
import { renderBlocks } from '@/lib/render'
import { CloseBtn } from '@/app/ui'
import FilterPanel from '@/app/FilterPanel'
import SourceEditor from '@/app/SourceEditor'
import ProofPicker from '@/app/ingest/ProofPicker'

type Proof = {
  ok: boolean; key: string; model?: string; seconds?: number; cost_cny?: number
  current?: { answer?: string; solution?: string; point_titles?: string[]; difficulty?: string; figures?: number }
  proposal?: {
    verdict: 'pass' | 'fix' | 'uncertain'
    answer_ok: boolean | null
    answer: string
    solution: string
    solution_issues: string[]
    figure_issues: string[]
    answer_blocks?: Block[]
    solution_blocks?: Block[]
    tikz: string
    notes: string[]
  }
}

/** 「补齐缺项」的结果；和 aicurate 的 proposal 同构。 */
type CurateProp = {
  points?: string[]
  point_titles?: string[]
  difficulty?: string
  answer?: string
  solution?: string
  answer_blocks?: Block[]
  solution_blocks?: Block[]
}

type TikzSug = {
  tikz: string
  placement: 'stem' | 'solution'
  reason: string
}

const VERDICT: Record<string, {
  text: string; sub: string; icon: any
  head: string; border: string; iconCls: string; textCls: string
}> = {
  pass: {
    text: '答案与解法基本通过', sub: '独立求解与现有答案一致',
    icon: CheckCircle2,
    head: 'bg-has-soft', border: 'border-has-line', iconCls: 'bg-has text-white',
    textCls: 'text-has',
  },
  fix: {
    text: '发现问题，建议修改', sub: '先看下面的问题清单，再决定写回哪些',
    icon: AlertTriangle,
    head: 'bg-warn-soft', border: 'border-warn-line', iconCls: 'bg-warn text-white',
    textCls: 'text-warn',
  },
  uncertain: {
    text: '无法完全确认，人工再核', sub: '模型没有把握，建议对照原卷或答案册',
    icon: Stamp,
    head: 'bg-muted', border: 'border-border', iconCls: 'bg-ink-faint text-white',
    textCls: 'text-ink-soft',
  },
}

const ASRC_LABEL: Record<string, string> = {
  workbuddy: '模型答案', human: '人工答案', legacy: '历史答案', 无: '来源未记',
}

function Step({ n, label, state, onClick }: {
  n: number; label: string; state: 'done' | 'active' | 'idle'; onClick?: () => void
}) {
  return (
    <button onClick={onClick} disabled={!onClick}
      className={`press flex items-center gap-1 rounded-full border px-1.5 py-[2px] text-[10.5px]
                  font-medium transition-colors ${state === 'active'
        ? 'border-warn-line bg-warn-soft text-warn'
        : state === 'done'
          ? 'border-has-line bg-has-soft text-has hover:brightness-105'
          : 'border-border bg-surface/60 text-ink-faint'}`}>
      <span className={`grid h-4 w-4 shrink-0 place-items-center rounded-full text-[9px] ${
        state === 'active' ? 'bg-warn text-white'
          : state === 'done' ? 'bg-has text-white' : 'bg-muted text-ink-faint'}`}>
        {state === 'done' ? <Check size={9} strokeWidth={3.2} /> : n}
      </span>
      {label}
    </button>
  )
}

/** 服务端的错误文案里有 Markdown 强调（`**没有保存**`）；直接 {err} 会把星号原样画出来。
 *  这里只把成对的 `**…**` 变成粗体，不引入 Markdown 渲染器。 */
function ErrText({ text }: { text: string }) {
  const parts = text.split('**')
  if (parts.length < 3) return <>{text}</>
  return <>{parts.map((p, i) => (i % 2
    ? <b key={i} className="font-semibold">{p}</b>
    : <span key={i}>{p}</span>))}</>
}

function AnswerSource({ src }: { src?: string }) {
  if (!src || src === '无' || !ASRC_LABEL[src]) return null
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-[1px] text-[10.5px] font-medium ${
      src === 'workbuddy' ? 'bg-warn-soft text-warn' : 'bg-muted text-ink-soft'}`}>
      {ASRC_LABEL[src]}
    </span>
  )
}

export default function ProofWorkspace({ stage, onBack, onDone }: {
  stage: Stage; onBack: () => void; onDone: () => void
}) {
  const meta = STAGE_BY_KEY[stage]
  const [view, setView] = useState<'pick' | 'proof'>('pick')
  const [q, setQ] = useState<Q | null>(null)
  const [picking, setPicking] = useState('')
  const [listVersion, setListVersion] = useState(0)
  const [rep, setRep] = useState<Proof | null>(null)
  const [checking, setChecking] = useState(false)
  const [applyAnswer, setApplyAnswer] = useState(true)
  const [applySolution, setApplySolution] = useState(true)
  const [busy, setBusy] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [rewrite, setRewrite] = useState<{ solution: string; note: string; blocks?: Block[] } | null>(null)
  const [curating, setCurating] = useState(false)
  const [curate, setCurate] = useState<CurateProp | null>(null)
  const [applyCurateTags, setApplyCurateTags] = useState(true)
  const [applyCurateAnswer, setApplyCurateAnswer] = useState(true)
  const [applyCurateSolution, setApplyCurateSolution] = useState(true)
  const [tikzing, setTikzing] = useState(false)
  const [tikzSug, setTikzSug] = useState<TikzSug | null>(null)
  const [srcOpen, setSrcOpen] = useState(false)
  const [err, setErr] = useState('')
  /** 写入撞上别的进程（409）时，错误条里直接给一个重试入口；
   *  记下是哪一种写入失败，重试按钮才能点对。 */
  const [retryKind, setRetryKind] = useState<'proof' | 'rewrite' | 'curate' | 'tikz' | ''>('')
  const [msg, setMsg] = useState('')
  const [copied, setCopied] = useState(false)
  /** 请求序号：返回选题页或换题后，在途的列表/校对响应不能再改界面。 */
  const pickSeq = useRef(0)
  const checkSeq = useRef(0)
  const detailScroll = useRef<HTMLDivElement>(null)
  const rightScroll = useRef<HTMLDivElement>(null)
  const L = useQuestionList({ stage, pageSize: 20 })

  // 离开页面时作废所有在途请求，避免异步回来再 setState。
  useEffect(() => () => { pickSeq.current++; checkSeq.current++ }, [])

  // 右栏结果换内容时回到顶部（右栏自己滚动，不抢中栏）。
  useEffect(() => {
    if (!rep?.proposal && !rewrite && !curate && !tikzSug) return
    const t = window.setTimeout(() => {
      rightScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
    }, 80)
    return () => window.clearTimeout(t)
  }, [rep, rewrite, curate, tikzSug])

  // 独立标签页至少能从标题分清“选题”和“正在校对”。
  // 用 setTimeout 让过 Shell 的“录入 · AmMath”：父组件的 effect 晚于子组件执行，
  // 同步写会被它覆盖掉。
  useEffect(() => {
    const prev = document.title
    const t = window.setTimeout(() => {
      document.title = view === 'proof' ? 'AI 整理 / 校对 · AmMath' : 'AI 整理 / 校对 · 选题'
    }, 0)
    return () => { window.clearTimeout(t); document.title = prev }
  }, [view])

  const pick = async (key: string) => {
    const seq = ++pickSeq.current
    setPicking(key); setErr(''); setRetryKind(''); setMsg(''); setRep(null); setCurate(null); setTikzSug(null); setSrcOpen(false)
    try {
      const d: any = await api.get(key)
      if (seq !== pickSeq.current) return
      setQ(d as Q)
      setApplyAnswer(true); setApplySolution(true)
      setView('proof')
    } catch (e) {
      if (seq !== pickSeq.current) return
      setErr(String((e as any)?.message || e))
    } finally {
      if (seq === pickSeq.current) setPicking('')
    }
  }

  const backToPick = () => {
    // 正在跑的校对/打开请求作废：回来后的界面以用户当前的选择为准。
    checkSeq.current++
    pickSeq.current++
    setChecking(false)
    setPicking('')
    setSrcOpen(false)
    setErr(''); setRewrite(null); setCurate(null); setTikzSug(null)
    setRetryKind('')
    setView('pick')
  }

  const check = async () => {
    if (!q) return
    const seq = ++checkSeq.current
    setChecking(true); setErr(''); setRetryKind(''); setMsg(''); setRep(null); setCopied(false)
    try {
      const d: any = await api.aiProofread(q.key)
      if (seq !== checkSeq.current) return
      setRep(d as Proof)
      setApplyAnswer(!!d?.proposal?.answer?.trim())
      setApplySolution(!!d?.proposal?.solution?.trim())
    } catch (e) {
      if (seq !== checkSeq.current) return
      setErr(String((e as any)?.message || e))
      detailScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      if (seq === checkSeq.current) setChecking(false)
    }
  }

  const writeBack = async () => {
    if (!q || !rep?.proposal) return
    setBusy(true); setErr(''); setRetryKind(''); setMsg('')
    const a = applyAnswer ? (rep.proposal.answer || '').trim() : ''
    const s = applySolution ? (rep.proposal.solution || '').trim() : ''
    if (!a && !s) {
      setErr('没有勾选要写入的答案或解析')
      setRetryKind('')
      detailScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
      setBusy(false); return
    }
    try {
      if (s) {
        await api.solution(q.key, {
          solution: s, answer: a || undefined,
          dry_run: false, source: 'deepseek',
        })
      } else if (a) {
        await api.patch(q.key, { answer: a })
      }
      const d: any = await api.get(q.key)
      setQ(d as Q)
      setMsg('已写入；这道题的复核状态会因正文变化自动失效，请重新审阅。')
      setRep(null); setCurate(null)
      detailScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
      rightScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
      setListVersion((v) => v + 1)
      try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
      onDone()
    } catch (e) {
      const text = String((e as any)?.message || e)
      setErr(text)
      setRetryKind(/没有保存|连续写入/.test(text) ? 'proof' : '')
      detailScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
    } finally {
      setBusy(false)
    }
  }

  const rewriteSolution = async () => {
    if (!q || !hasSol) return
    setRewriting(true); setErr(''); setRetryKind(''); setMsg(''); setRewrite(null)
    try {
      const d: any = await api.aiRewriteSolution({
        stem: q.stem, answer: q.answer, solution: q.solution, qtype: q.type,
      })
      setRewrite({ solution: String(d.solution || ''), note: String(d.note || ''),
        blocks: Array.isArray(d.blocks) ? d.blocks : undefined })
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setRewriting(false) }
  }

  // 整理「缺项」走现有 aicurate：只补缺的考点/难度/答案/解析，
  // 和校对共用同一套筛选、三栏和写回按钮。
  const curateTasks = (() => {
    if (!q) return [] as string[]
    const ts = new Set<string>()
    if (!q.points?.length) { ts.add('points'); ts.add('difficulty') }
    else if (!q.difficulty) ts.add('difficulty')
    if (!q.flags?.['答案']) ts.add('answer')
    if (!q.flags?.['解析']) ts.add('solution')
    return [...ts]
  })()

  const runCurate = async () => {
    if (!q || !curateTasks.length) return
    setCurating(true); setErr(''); setRetryKind(''); setMsg(''); setCurate(null)
    try {
      const d: any = await api.aiCurate({ keys: [q.key], tasks: curateTasks, stage })
      const item = d?.items?.[0]
      if (!item?.ok) throw new Error(item?.error || '没有返回补齐建议')
      const p = (item.proposal || {}) as CurateProp
      setCurate(p)
      setApplyCurateTags(!!p.points?.length || !!p.difficulty)
      setApplyCurateAnswer(!!p.answer?.trim())
      setApplyCurateSolution(!!p.solution?.trim())
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setCurating(false) }
  }

  const applyCurate = async () => {
    if (!q || !curate) return
    setBusy(true); setErr(''); setRetryKind(''); setMsg('')
    const pts = applyCurateTags ? (curate.points || []) : []
    const diff = applyCurateTags ? (curate.difficulty || '') : ''
    const ans = applyCurateAnswer ? (curate.answer || '').trim() : ''
    const sol = applyCurateSolution ? (curate.solution || '').trim() : ''
    if (!pts.length && !diff && !ans && !sol) {
      setErr('没有勾选要写入的缺项')
      setBusy(false); return
    }
    try {
      if (pts.length || diff) {
        const body: Record<string, unknown> = {}
        if (pts.length) body.points = pts
        if (diff) body.difficulty = diff
        await api.patch(q.key, body)
      }
      if (sol || ans) {
        await api.solution(q.key, {
          solution: sol || undefined, answer: ans || undefined,
          dry_run: false, source: 'deepseek',
        })
      }
      const d: any = await api.get(q.key)
      setQ(d as Q); setCurate(null)
      setMsg('已写入勾选的缺项；复核状态会因正文变化自动失效。')
      setListVersion((v) => v + 1)
      try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
      onDone()
    } catch (e) {
      const text = String((e as any)?.message || e)
      setErr(text)
      setRetryKind(/没有保存|连续写入/.test(text) ? 'curate' : '')
      // 两个接口可能已经写了一半；重新拉一次，界面别停在旧状态。
      try { const d: any = await api.get(q.key); setQ(d as Q) } catch { /* ignore */ }
    } finally { setBusy(false) }
  }

  const runTikz = async () => {
    if (!q) return
    setTikzing(true); setErr(''); setRetryKind(''); setMsg(''); setTikzSug(null)
    try {
      const d: any = await api.aiTikz(q.key)
      if (!d?.needed || !String(d.tikz || '').trim()) {
        setMsg(String(d?.reason || '模型判断这道题不需要额外配图'))
        return
      }
      setTikzSug({
        tikz: String(d.tikz),
        placement: d.placement === 'solution' ? 'solution' : 'stem',
        reason: String(d.reason || ''),
      })
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setTikzing(false) }
  }

  const insertTikzNow = async (tikz: string, placement: 'stem' | 'solution') => {
    if (!q || !tikz.trim()) return
    setBusy(true); setErr(''); setRetryKind(''); setMsg('')
    try {
      const d: any = await api.insertTikz(q.key, { tikz, placement, dry_run: false })
      if (d && d.ok === false) {
        const why = d.error
          || (Array.isArray(d.after) && d.after[0]?.why)
          || (Array.isArray(d.problems) && d.problems[0])
          || '源码检查没通过'
        throw new Error(String(why))
      }
      const q2: any = await api.get(q.key)
      setQ(q2 as Q); setTikzSug(null)
      setMsg('已把 TikZ 插入' + (placement === 'solution' ? '解析' : '题干') + '；可在「改源码」里调整位置。')
      setListVersion((v) => v + 1)
      try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
      onDone()
    } catch (e) {
      const text = String((e as any)?.message || e)
      setErr(text)
      setRetryKind(/没有保存|连续写入/.test(text) ? 'tikz' : '')
    } finally { setBusy(false) }
  }

  const insertTikz = async () => {
    if (!tikzSug) return
    await insertTikzNow(tikzSug.tikz, tikzSug.placement)
  }

  const applyRewrite = async () => {
    if (!q || !rewrite?.solution.trim()) return
    setBusy(true); setErr(''); setRetryKind(''); setMsg('')
    try {
      await api.solution(q.key, {
        solution: rewrite.solution, dry_run: false, source: 'deepseek',
      })
      const d: any = await api.get(q.key)
      setQ(d as Q); setRewrite(null); setCurate(null)
      setMsg('已把解析重写并保存为规范 LaTeX；原复核状态会因正文变化自动失效。')
      setListVersion((v) => v + 1)
      try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
      onDone()
    } catch (e) {
      const text = String((e as any)?.message || e)
      setErr(text); setRetryKind(/没有保存|连续写入/.test(text) ? 'rewrite' : '')
    } finally { setBusy(false) }
  }

  const copyTikz = async () => {
    const t = rep?.proposal?.tikz || ''
    if (!t) return
    try {
      await navigator.clipboard.writeText(t)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setErr('复制失败，请手动选择代码')
    }
  }

  const v = rep?.proposal ? (VERDICT[rep.proposal.verdict] || VERDICT.uncertain) : null
  const VIcon = v?.icon || ShieldCheck
  const hasProposal = !!(rep?.proposal?.answer?.trim() || rep?.proposal?.solution?.trim())
  const solutionIssues = rep?.proposal?.solution_issues || []
  const figureIssues = rep?.proposal?.figure_issues || []
  const tikz = rep?.proposal?.tikz?.trim() || ''
  const notes = rep?.proposal?.notes || []
  const clearAllFilters = () => L.loadFilters(EMPTY_FILTERS, 'used')
  const canRetrySave = retryKind === 'proof' ? hasProposal
    : retryKind === 'rewrite' ? !!rewrite?.solution.trim()
      : retryKind === 'curate' ? !!curate
        : retryKind === 'tikz' ? !!tikzSug
          : false
  const retrySave = () => {
    if (retryKind === 'proof') void writeBack()
    else if (retryKind === 'rewrite') void applyRewrite()
    else if (retryKind === 'curate') void applyCurate()
    else if (retryKind === 'tikz') void insertTikz()
  }
  const hasAns = !!q?.flags?.['答案']
  const hasSol = !!q?.flags?.['解析']
  const figN = q?.figures?.length || 0
  const stars = q ? (DIFF_STARS[q.difficulty] || q.stars || 0) : 0
  const src = q?.meta?.source_label || q?.meta?.book || ''
  const reviewLabel = q?.review?.status === 'stale' ? '复核过期'
    : q?.review?.status === 'needs_fix' ? '待修正'
      : q?.review?.status === 'flagged' ? '已标疑'
        : q?.review?.status === 'pending' ? '未复核' : ''

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-bg">
      {/* 一层很淡的暖/冷双色氛围，避免独立页变成一整片灰。 */}
      <div className="pointer-events-none absolute inset-0" aria-hidden
        style={{
          background:
            'radial-gradient(48% 60% at 0% 0%, var(--color-warn-soft), transparent 68%),'
            + 'radial-gradient(50% 64% at 100% 0%, var(--color-brand-soft), transparent 70%)',
        }} />

      <div className="relative z-10 flex h-full min-h-0 flex-col">
        <header className="app-chrome flex h-14 shrink-0 items-center gap-2.5 border-b
                           border-border/70 bg-surface/80 px-4 backdrop-blur-2xl md:px-6">
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
            <span className="grid h-6 w-6 place-items-center rounded-lg border border-warn-line
                             bg-warn-soft text-warn">
              <ShieldCheck size={14} />
            </span>
            AI 整理 / 校对
          </span>
          <span className="hidden rounded-full border border-warn-line bg-warn-soft px-1.5 py-[1px]
                           text-[10px] font-medium text-warn sm:inline">考点 · 答案 · 解析 · 配图</span>

          <div className="ml-2 hidden items-center gap-1 md:flex">
            <Step n={1} label="选题" state={view === 'proof' ? 'done' : 'active'}
              onClick={view === 'proof' ? backToPick : undefined} />
            <ChevronRight size={11} className="text-border-strong" />
            <Step n={2} label="核对" state={view === 'proof' ? 'active' : 'idle'} />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-[10.5px] text-ink-faint sm:inline">{meta.name}</span>
            <CloseBtn onClick={onBack} title="返回录题方式选择" />
          </div>
        </header>

        {/* 选题页保留在 DOM 里：从校对页点「重新选题」时，搜索词、筛选、
            页码和滚动位置都还在，不用重新搜一遍。 */}
        <div className={view === 'pick' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
          <ProofPicker stage={stage} L={L}
            activeKey={q?.key}
            pickingKey={picking}
            error={err}
            version={listVersion}
            onPick={(key) => void pick(key)}
            onDismissError={() => setErr('')} />
        </div>

        {view === 'proof' && q && (
          <div className="anim-fade-in flex min-h-0 flex-1 flex-col">
            {/* 本题上下文 */}
            <div className="shrink-0 border-b border-border/70 bg-surface/65 backdrop-blur-xl">
              <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center gap-2.5
                              px-4 py-2.5 md:px-6">
                <button onClick={backToPick}
                  className="press flex h-8 items-center gap-1.5 rounded-lg border border-border
                             bg-surface px-2.5 text-[11.5px] font-medium text-ink-soft
                             hover:border-border-strong hover:text-ink">
                  <ArrowLeft size={13} />重新选题
                </button>
                <button onClick={backToPick}
                  className="press flex h-8 items-center gap-1.5 rounded-lg border border-border
                             bg-surface px-2.5 text-[11.5px] font-medium text-ink-soft
                             hover:border-border-strong hover:text-ink xl:hidden">
                  <ListFilter size={13} />筛选 / 选题
                </button>
                <span className="h-4 w-px bg-border" />
                <span className="text-[11px] text-ink-faint">正在校对</span>
                <span className="max-w-[42ch] truncate font-mono text-[10.5px] text-ink-soft"
                  title={q.key}>{q.key}</span>
                {reviewLabel && (
                  <span className="rounded-md bg-muted px-1.5 py-[1px] text-[10px] font-medium text-ink-soft">
                    {reviewLabel}
                  </span>
                )}
                <span className="ml-auto flex min-w-0 items-center gap-1.5 text-[10.5px] text-ink-faint">
                  <span className="shrink-0 rounded bg-muted px-1.5 py-[1px] text-ink-soft">{q.type_label}</span>
                  {q.point_titles?.[0] && (
                    <span className="max-w-[30ch] truncate">{dispPoint(q.point_titles[0])}</span>
                  )}
                </span>
              </div>
            </div>

            <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center gap-2
                            px-4 pb-1 pt-3 md:px-6">
              <h1 className="text-[18px] font-semibold tracking-[-.02em]">逐项整理 / 校对</h1>
              <span className="text-[10.5px] text-ink-faint">
                中栏原题 · 右栏修改后对照，公式按题库同一套排版渲染
              </span>
              <span className="ml-auto rounded-full border border-border bg-surface/70 px-2 py-[3px]
                               text-[10px] font-medium text-ink-faint">
                只建议 · 确认后写回
              </span>
            </div>

            {(err || msg) && (
              <div className="mx-auto w-full max-w-[1600px] px-4 pb-2 pt-2 md:px-6">
                {err && (
                  <div className="flex flex-wrap items-start gap-2 rounded-xl border border-warn-line
                                  bg-warn-soft px-3 py-2 text-[11.5px] text-warn">
                    <AlertTriangle size={13} className="mt-[1px] shrink-0" />
                    <span className="min-w-0 flex-1">
                      <ErrText text={err.replace('（多半是后台求解器）', '（后台测试 / 整理 / 求解）')} />
                      {retryKind !== '' && (
                        <span className="mt-0.5 block text-[10px] leading-relaxed opacity-80">
                          这次没有改动任何题目；等后台写入结束后再点一次即可。
                        </span>
                      )}
                    </span>
                    {retryKind !== '' && !busy && canRetrySave && (
                      <button onClick={retrySave}
                        className="press inline-flex h-7 shrink-0 items-center gap-1 rounded-lg
                                   border border-warn-line bg-surface px-2 text-[11px] font-medium
                                   text-warn hover:bg-warn-soft">
                        <RefreshCw size={11} />再试一次
                      </button>
                    )}
                    <button onClick={() => { setErr(''); setRetryKind('') }}
                      className="shrink-0 underline">知道了</button>
                  </div>
                )}
                {msg && (
                  <div className="mt-2 rounded-xl border border-has-line bg-has-soft px-3 py-2
                                  text-[11.5px] text-has">{msg}</div>
                )}
              </div>
            )}

            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto xl:flex-row xl:overflow-hidden">
              {/* 左：筛选 */}
              <aside className="hidden w-[280px] shrink-0 flex-col border-r border-border/60
                                bg-surface/45 backdrop-blur-xl xl:flex">
                <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border/60 px-3">
                  <ListFilter size={13} className="text-brand" />
                  <span className="text-[11.5px] font-semibold">匹配</span>
                  <span className="tnum text-[10px] text-ink-faint">{L.total} 道</span>
                  <button onClick={backToPick}
                    className="press ml-auto rounded-md border border-border bg-surface px-2 py-[3px]
                               text-[10.5px] font-medium text-ink-soft hover:border-brand-line hover:text-brand-ink">
                    选题
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-hidden">
                  <div className="mx-auto flex h-full w-[252px]">
                    <FilterPanel L={L} onClearAll={clearAllFilters} />
                  </div>
                </div>
              </aside>

              {/* 中：原题 + 现有解析 */}
              <div ref={detailScroll}
                className="min-w-0 flex-1 xl:b-scroll xl:min-h-0 xl:overflow-y-auto">
                <div className="mx-auto w-full max-w-[780px] px-4 py-3 md:px-5">
                  <div className="flex flex-wrap items-center gap-2 pb-2">
                    <span className="text-[12px] font-semibold">原题与现有解析</span>
                    <span className="rounded-md bg-muted px-1.5 py-[1px] text-[10px] text-ink-faint">只读</span>
                    <span className="ml-auto text-[10px] text-ink-faint">
                      需要换题时点左上角「重新选题」
                    </span>
                  </div>

                  <section className="overflow-hidden rounded-[22px] border border-border
                                      bg-surface shadow-[var(--shadow-card)]">
                    <div className="px-4 pb-4 pt-4 md:px-5">
                      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                        {q.point_titles?.length ? q.point_titles.map((t, i) => (
                          <span key={i} title={q.point_titles.map(dispPoint).join('、')}
                            className={`shrink-0 rounded-full px-1.5 py-[1px] font-medium ${
                              i === 0 ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-soft'}`}>
                            {i === 0 && <span className="mr-0.5 text-[9px] font-normal opacity-60">主</span>}
                            {dispPoint(t)}
                          </span>
                        )) : (
                          <span className="rounded-full bg-warn-soft px-1.5 py-[1px] font-medium text-warn">无考点</span>
                        )}
                        {src && <span className="min-w-0 max-w-[36ch] truncate text-ink-faint" title={src}>{src}</span>}
                        <span className="rounded-md bg-muted px-1.5 py-[1px] text-[10px] text-ink-soft">
                          {q.type_label} · {q.kind}题
                        </span>
                        <span className="rounded-md bg-muted px-1.5 py-[1px] text-[10px] text-ink-soft">
                          <span className={stars ? 'text-warn' : 'text-ink-faint'}>{starsLabel(stars)}</span>
                          {stars > 0 && <span className="ml-0.5">{q.difficulty?.replace('题', '')}</span>}
                        </span>
                        <AnswerSource src={q.meta?.answer_source} />
                        {figN > 0 && (
                          <span className="inline-flex items-center gap-0.5 rounded-md bg-muted px-1.5 py-[1px]
                                           text-[10px] text-ink-soft" title="题干 / 选项 / 解析里的配图">
                            <ImageIcon size={10} />{figN}
                          </span>
                        )}
                        {q.meta?.figure_low_res && (
                          <span className="rounded-md bg-warn-soft px-1.5 py-[1px] text-[10px] font-medium text-warn">
                            低清图
                          </span>
                        )}
                        {!!q.used && (
                          <span className="ml-auto shrink-0 text-[10px] text-warn" title={`被导出 ${q.used} 次`}>
                            已用 {q.used} 次
                          </span>
                        )}
                      </div>

                      <div className="mt-3 text-[14.5px] leading-[1.9] text-ink">
                        {renderBlocks(q.blocks?.stem) || q.stem}
                      </div>

                      {hasImageOptions(q) ? (
                        <div className="mt-2 text-[11.5px] text-ink-faint">选项见图（{optionRange(q)}）</div>
                      ) : (q.options?.length || 0) > 1 && (
                        <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
                          {q.options.map((o, i) => (
                            <div key={o.label} className="flex min-w-0 gap-1.5 text-[12.5px] text-ink-soft">
                              <span className="shrink-0 font-semibold text-ink-faint">{o.label}.</span>
                              <span className="min-w-0">{renderBlocks(q.blocks?.options?.[i]) || o.text}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-1 gap-3 border-t border-border/70 bg-surface-2/55 p-4 md:p-5">
                      <div className="rounded-xl border border-border bg-surface p-3.5">
                        <div className="flex items-center gap-1.5 text-[10.5px] font-semibold tracking-wide text-ink-faint">
                          <span className={`grid h-5 w-5 place-items-center rounded-md ${
                            hasAns ? 'bg-has-soft text-has' : 'bg-warn-soft text-warn'}`}>
                            <CheckCircle2 size={12} />
                          </span>
                          现有答案
                          {!hasAns && <span className="ml-auto text-[10px] font-medium text-warn">缺答案</span>}
                        </div>
                        <div className="mt-2 text-[12.5px] leading-relaxed text-ink">
                          {renderBlocks(q.blocks?.answer) || q.answer
                            || <span className="text-[11px] text-ink-faint">（空）</span>}
                        </div>
                      </div>

                      <div className="rounded-xl border border-border bg-surface p-3.5">
                        <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] font-semibold tracking-wide text-ink-faint">
                          <span className={`grid h-5 w-5 place-items-center rounded-md ${
                            hasSol ? 'bg-brand-soft text-brand' : 'bg-warn-soft text-warn'}`}>
                            <FileText size={12} />
                          </span>
                          现有解析
                          <span className="text-[10px] font-normal text-ink-faint">题库原文，未修复</span>
                          <span className={`ml-auto text-[10px] font-medium ${hasSol ? 'text-has' : 'text-warn'}`}>
                            {hasSol ? '已收录' : '缺解析'}
                          </span>
                          <button onClick={() => void rewriteSolution()}
                            disabled={!hasSol || rewriting || checking || curating || busy}
                            className="press ml-1 inline-flex h-6 items-center gap-1 rounded-md border
                                       border-brand-line bg-brand-soft px-1.5 text-[10px] font-medium
                                       text-brand-ink hover:bg-brand hover:text-white
                                       disabled:cursor-not-allowed disabled:opacity-40"
                            title="只把现有解析改成规范 LaTeX，不改内容；确认后才保存">
                            {rewriting ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                            {rewriting ? '重写中…' : '重写为规范 LaTeX'}
                          </button>
                        </div>
                        <div className="mt-2 text-[11.5px] leading-relaxed text-ink-soft">
                          {renderBlocks(q.blocks?.solution) || q.solution
                            || <span className="text-[11px] text-ink-faint">（空）</span>}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 border-t border-border/70 bg-surface
                                    px-4 py-3 md:px-5">
                      <button onClick={() => void check()}
                        disabled={checking || curating || tikzing || busy}
                        className="press b-btn b-btn-primary h-9">
                        {checking ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                        {checking ? 'DeepSeek 正在独立做…' : 'DeepSeek 校对这道题'}
                      </button>
                      {curateTasks.length > 0 && (
                        <button onClick={() => void runCurate()}
                          disabled={curating || checking || tikzing || busy}
                          title={`补：${curateTasks.join(' / ')}`}
                          className="press b-btn b-btn-secondary h-9">
                          {curating ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
                          {curating ? '正在补缺项…' : 'AI 补齐缺项'}
                        </button>
                      )}
                      <button onClick={() => void runTikz()}
                        disabled={tikzing || checking || curating || busy}
                        title="让 DeepSeek 判断是否缺图，生成 TikZ 后由你确认插入"
                        className="press b-btn b-btn-secondary h-9">
                        {tikzing ? <Loader2 size={14} className="animate-spin" /> : <ImagePlus size={14} />}
                        {tikzing ? '正在补图…' : '补 TikZ'}
                      </button>
                      <span className="ml-1 text-[10px] text-ink-faint">只生成建议，不自动写库</span>
                      <button onClick={() => setSrcOpen(true)}
                        disabled={checking || curating || tikzing || busy}
                        className="press b-btn b-btn-secondary ml-auto h-9">
                        <Code2 size={14} />改源码
                      </button>
                    </div>
                  </section>
                  <div className="h-4" />
                </div>
              </div>

              {/* 右：修改后对照 */}
              <aside className="flex w-full shrink-0 flex-col border-t border-border/60
                                bg-surface/45 xl:min-h-0 xl:w-[520px] xl:border-l xl:border-t-0">
                <div className="flex h-11 shrink-0 items-center gap-2 border-b border-border/60 px-3">
                  <span className="text-[11.5px] font-semibold">修改后对照</span>
                  {rewrite && !rep && (
                    <span className="rounded-md bg-brand-soft px-1.5 py-[1px] text-[10px] font-medium text-brand-ink">
                      规范 LaTeX
                    </span>
                  )}
                  {curate && !rep && !rewrite && (
                    <span className="rounded-md bg-warn-soft px-1.5 py-[1px] text-[10px] font-medium text-warn">
                      补齐缺项
                    </span>
                  )}
                  {tikzSug && !rep && !rewrite && !curate && (
                    <span className="rounded-md bg-warn-soft px-1.5 py-[1px] text-[10px] font-medium text-warn">
                      补图
                    </span>
                  )}
                  <span className="ml-auto text-[10px] text-ink-faint">只建议 · 确认后写回</span>
                </div>
                <div ref={rightScroll}
                  className="min-h-0 flex-1 xl:b-scroll xl:overflow-y-auto">
                  <div className="space-y-3 p-4">
                    {checking && (
                      <section className="anim-fade-in overflow-hidden rounded-[18px] border
                                          border-brand-line bg-surface shadow-[var(--shadow-card)]">
                        <div className="flex items-center gap-3 p-4">
                          <span className="relative grid h-10 w-10 shrink-0 place-items-center
                                           rounded-xl bg-brand-soft text-brand">
                            <Sparkles size={17} />
                            <span className="absolute inset-0 animate-ping rounded-xl border border-brand/25" />
                          </span>
                          <div className="min-w-0">
                            <div className="text-[12.5px] font-semibold text-ink">DeepSeek 正在独立做这道题…</div>
                            <div className="mt-0.5 text-[10.5px] leading-relaxed text-ink-faint">
                              先自己解一遍，再和现有答案、解析、配图逐项对照；通常十几秒。
                            </div>
                          </div>
                          <Loader2 size={16} className="ml-auto shrink-0 animate-spin text-brand" />
                        </div>
                        <div className="progress-track mx-4 mb-3" />
                      </section>
                    )}

                    {curating && (
                      <section className="anim-fade-in overflow-hidden rounded-[18px] border
                                          border-warn-line bg-surface shadow-[var(--shadow-card)]">
                        <div className="flex items-center gap-3 p-4">
                          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl
                                           bg-warn-soft text-warn">
                            <Wand2 size={17} />
                          </span>
                          <div className="min-w-0">
                            <div className="text-[12.5px] font-semibold text-ink">DeepSeek 正在补齐缺项…</div>
                            <div className="mt-0.5 text-[10.5px] leading-relaxed text-ink-faint">
                              只补缺的考点、难度、答案或解析；已有字段不覆盖。
                            </div>
                          </div>
                          <Loader2 size={16} className="ml-auto shrink-0 animate-spin text-warn" />
                        </div>
                        <div className="progress-track mx-4 mb-3" />
                      </section>
                    )}

                    {curate && (
                      <section className="anim-fade-in overflow-hidden rounded-[18px] border
                                          border-warn-line bg-surface shadow-[var(--shadow-card)]">
                        <div className="border-b border-warn-line/50 bg-warn-soft/30 px-4 py-3">
                          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] font-semibold text-warn">
                            <Wand2 size={12} />补齐缺项
                            <span className="ml-auto text-[9.5px] font-normal text-ink-faint">
                              DeepSeek 建议 · 未保存
                            </span>
                          </div>
                          <div className="mt-1 text-[10px] leading-relaxed text-ink-faint">
                            只补缺的字段；已有内容不会被覆盖。
                          </div>
                        </div>
                        <div className="space-y-2.5 p-3.5">
                          {(curate.points?.length || curate.difficulty) && (
                            <div className="rounded-xl border border-border bg-surface p-3">
                              <label className="flex items-center gap-2 text-[11px] font-semibold text-ink">
                                <input type="checkbox" checked={applyCurateTags}
                                  onChange={(e) => setApplyCurateTags(e.target.checked)}
                                  className="accent-[var(--color-brand)]" />
                                写入考点 / 难度
                              </label>
                              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-soft">
                                {curate.point_titles?.length
                                  ? curate.point_titles.map((t, i) => (
                                    <span key={i} className="rounded-full bg-brand-soft px-1.5 py-[1px]
                                                             font-medium text-brand-ink">{t}</span>
                                  ))
                                  : (curate.points || []).map((p) => (
                                    <span key={p} className="rounded-full bg-brand-soft px-1.5 py-[1px]
                                                             font-medium text-brand-ink">{p}</span>
                                  ))}
                                {curate.difficulty && (
                                  <span className="rounded-full bg-warn-soft px-1.5 py-[1px]
                                                   font-medium text-warn">{curate.difficulty}</span>
                                )}
                              </div>
                            </div>
                          )}

                          {curate.answer?.trim() && (
                            <div className="rounded-xl border border-border bg-surface p-3">
                              <label className="flex items-center gap-2 text-[11px] font-semibold text-ink">
                                <input type="checkbox" checked={applyCurateAnswer}
                                  onChange={(e) => setApplyCurateAnswer(e.target.checked)}
                                  className="accent-[var(--color-brand)]" />
                                写入答案
                              </label>
                              <div className="mt-1.5 rounded-lg bg-muted/70 px-3 py-2 text-[12px]
                                              leading-relaxed text-ink">
                                {curate.answer_blocks?.length
                                  ? renderBlocks(curate.answer_blocks)
                                  : <span className="font-mono text-[11px]">{curate.answer}</span>}
                              </div>
                            </div>
                          )}

                          {curate.solution?.trim() && (
                            <div className="rounded-xl border border-border bg-surface p-3">
                              <label className="flex items-center gap-2 text-[11px] font-semibold text-ink">
                                <input type="checkbox" checked={applyCurateSolution}
                                  onChange={(e) => setApplyCurateSolution(e.target.checked)}
                                  className="accent-[var(--color-brand)]" />
                                写入解析
                                <span className="font-normal text-ink-faint">（模型生成，需核对）</span>
                              </label>
                              <div className="q-solution q-compact mt-1.5 text-[12px] leading-relaxed text-ink">
                                {curate.solution_blocks?.length
                                  ? renderBlocks(curate.solution_blocks)
                                  : <div className="whitespace-pre-wrap text-[11px] text-ink-soft">
                                      {curate.solution}
                                    </div>}
                              </div>
                            </div>
                          )}

                          {!curate.points?.length && !curate.difficulty && !curate.answer?.trim()
                            && !curate.solution?.trim() && (
                            <div className="rounded-xl border border-border bg-surface-2/70 px-3 py-3
                                            text-[10.5px] text-ink-faint">
                              模型没有返回可用的缺项建议；可以先人工核对，或换一道题再试。
                            </div>
                          )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2 border-t border-border/70
                                        bg-surface-2/45 px-3.5 py-3">
                          <button onClick={() => void applyCurate()} disabled={busy}
                            className="press b-btn b-btn-primary h-8">
                            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                            写入勾选的缺项
                          </button>
                          <button onClick={() => setCurate(null)} disabled={busy}
                            className="b-btn b-btn-secondary h-8">放弃</button>
                          <span className="text-[9.5px] text-ink-faint">走现有标签/解析写回接口</span>
                        </div>
                      </section>
                    )}

                    {tikzing && (
                      <section className="anim-fade-in overflow-hidden rounded-[18px] border
                                          border-warn-line bg-surface shadow-[var(--shadow-card)]">
                        <div className="flex items-center gap-3 p-4">
                          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl
                                           bg-warn-soft text-warn">
                            <ImagePlus size={17} />
                          </span>
                          <div className="min-w-0">
                            <div className="text-[12.5px] font-semibold text-ink">DeepSeek 正在判断是否需要配图…</div>
                            <div className="mt-0.5 text-[10.5px] leading-relaxed text-ink-faint">
                              只生成 TikZ，不写库；插入前由你确认。
                            </div>
                          </div>
                          <Loader2 size={16} className="ml-auto shrink-0 animate-spin text-warn" />
                        </div>
                        <div className="progress-track mx-4 mb-3" />
                      </section>
                    )}

                    {tikzSug && (
                      <section className="anim-fade-in overflow-hidden rounded-[18px] border
                                          border-warn-line bg-surface shadow-[var(--shadow-card)]">
                        <div className="border-b border-warn-line/50 bg-warn-soft/30 px-4 py-3">
                          <div className="flex flex-wrap items-center gap-1.5 text-[11.5px] font-semibold text-warn">
                            <ImagePlus size={12} />补 TikZ
                            <span className="ml-auto text-[9.5px] font-normal text-ink-faint">
                              DeepSeek 建议 · 未保存
                            </span>
                          </div>
                          {tikzSug.reason && (
                            <div className="mt-1 text-[10px] leading-relaxed text-ink-faint">
                              {tikzSug.reason}
                            </div>
                          )}
                        </div>
                        <div className="space-y-2.5 p-3.5">
                          <div className="flex items-center gap-1.5 text-[10.5px] text-ink-soft">
                            <span className="font-medium">插入位置</span>
                            <div className="flex rounded-lg border border-border bg-bg p-0.5">
                              {([
                                ['stem', '题干'],
                                ['solution', '解析'],
                              ] as const).map(([v, label]) => (
                                <button key={v}
                                  onClick={() => setTikzSug({ ...tikzSug, placement: v })}
                                  className={`press rounded-md px-2 py-[2px] text-[10px] ${
                                    tikzSug.placement === v
                                      ? 'bg-surface font-medium text-warn shadow-sm'
                                      : 'text-ink-faint hover:text-ink'}`}>
                                  {label}
                                </button>
                              ))}
                            </div>
                            <span className="ml-auto text-[9.5px] text-ink-faint">
                              插入后可在「改源码」里调位置
                            </span>
                          </div>
                          <pre className="b-scroll max-h-[220px] overflow-auto rounded-lg bg-bg
                                          p-2.5 text-[10px] leading-relaxed text-ink-soft">{tikzSug.tikz}</pre>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 border-t border-border/70
                                        bg-surface-2/45 px-3.5 py-3">
                          <button onClick={() => void insertTikz()} disabled={busy}
                            className="press b-btn b-btn-primary h-8">
                            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                            插入到题目
                          </button>
                          <button onClick={() => setTikzSug(null)} disabled={busy}
                            className="b-btn b-btn-secondary h-8">放弃</button>
                          <span className="text-[9.5px] text-ink-faint">
                            走改源码的检查与写回；不会跳过规范校验
                          </span>
                        </div>
                      </section>
                    )}

                    {rewrite && (
                      <section className="anim-fade-in overflow-hidden rounded-[18px] border
                                          border-brand-line bg-surface shadow-[var(--shadow-card)]">
                        <div className="border-b border-brand-line/50 bg-brand-soft/35 px-4 py-3">
                          <div className="flex items-center gap-1.5 text-[11.5px] font-semibold text-brand-ink">
                            <Sparkles size={12} />规范 LaTeX 重写
                            <span className="ml-auto text-[9.5px] font-normal text-ink-faint">只改格式 · 未保存</span>
                          </div>
                          {rewrite.note && (
                            <div className="mt-1 text-[10px] leading-relaxed text-ink-faint">{rewrite.note}</div>
                          )}
                        </div>
                        <div className="q-solution q-compact p-4 text-[12.5px] leading-relaxed text-ink">
                          {rewrite.blocks?.length
                            ? renderBlocks(rewrite.blocks)
                            : <div className="whitespace-pre-wrap text-[11px] text-ink-soft">{rewrite.solution}</div>}
                        </div>
                        <div className="flex flex-wrap items-center gap-2 border-t border-border/70
                                        bg-surface-2/45 px-4 py-3">
                          <button onClick={() => void applyRewrite()} disabled={busy}
                            className="press b-btn b-btn-primary h-8">
                            {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                            保存为规范解析
                          </button>
                          <button onClick={() => setRewrite(null)} disabled={busy}
                            className="b-btn b-btn-secondary h-8">放弃</button>
                          <span className="text-[9.5px] text-ink-faint">走现有单题解析接口；保存前过规范检查</span>
                        </div>
                      </section>
                    )}

                    {rep?.proposal && v && (
                      <section className={`anim-fade-in overflow-hidden rounded-[18px] border bg-surface
                                          shadow-[var(--shadow-card)] ${v.border}`}>
                        <div className={`flex flex-wrap items-center gap-2 border-b px-3.5 py-3 ${v.head}`}>
                          <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${v.iconCls}`}>
                            <VIcon size={15} />
                          </span>
                          <div className="min-w-0">
                            <div className={`text-[12.5px] font-semibold ${v.textCls}`}>{v.text}</div>
                            <div className="mt-0.5 text-[10px] text-ink-faint">{v.sub}</div>
                          </div>
                          <span className="ml-auto flex items-center gap-1.5">
                            {rep.model && (
                              <span className="hidden max-w-[14ch] truncate rounded-md border border-border
                                               bg-surface/70 px-1.5 py-[2px] text-[9px] text-ink-faint sm:inline"
                                title={rep.model}>{rep.model}</span>
                            )}
                            <span className="tnum inline-flex items-center gap-1 rounded-md border border-border
                                             bg-surface/70 px-1.5 py-[3px] text-[9.5px] font-medium text-ink-soft">
                              <Timer size={9} />
                              {rep.seconds != null ? `${rep.seconds}s` : '—'} · ¥{Number(rep.cost_cny || 0).toFixed(3)}
                            </span>
                          </span>
                        </div>

                        <div className="space-y-2.5 p-3.5">
                          {notes.length > 0 && (
                            <div className="rounded-xl border border-border bg-surface-2/70 p-3">
                              <div className="flex items-center gap-1.5 text-[10.5px] font-semibold text-ink-soft">
                                <Info size={12} className="text-ink-faint" />校对说明
                              </div>
                              <ul className="mt-1.5 space-y-1 text-[10.5px] leading-relaxed text-ink-soft">
                                {notes.map((x, i) => (
                                  <li key={i} className="flex gap-1.5">
                                    <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-border-strong" />
                                    <span className="min-w-0">{x}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          <div className="rounded-xl border border-border bg-surface p-3">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={`grid h-6 w-6 place-items-center rounded-lg ${
                                rep.proposal.answer_ok === false
                                  ? 'bg-warn-soft text-warn'
                                  : rep.proposal.answer_ok === true
                                    ? 'bg-has-soft text-has'
                                    : 'bg-muted text-ink-faint'}`}>
                                {rep.proposal.answer_ok === false
                                  ? <AlertTriangle size={12} />
                                  : <CheckCircle2 size={12} />}
                              </span>
                              <span className="text-[11px] font-semibold text-ink">答案检查</span>
                              {rep.proposal.answer_ok === true && (
                                <span className="rounded-md bg-has-soft px-1.5 py-[1px] text-[10px]
                                                 font-medium text-has">独立求解一致</span>
                              )}
                              {rep.proposal.answer_ok === false && (
                                <span className="rounded-md bg-warn-soft px-1.5 py-[1px] text-[10px]
                                                 font-medium text-warn">与现有答案不一致</span>
                              )}
                              {rep.proposal.answer_ok === null && (
                                <span className="rounded-md bg-muted px-1.5 py-[1px] text-[10px]
                                                 font-medium text-ink-faint">无法确认</span>
                              )}
                              {rep.proposal.answer?.trim() && (
                                <label className="ml-auto flex items-center gap-1.5 text-[10px]
                                                  font-normal text-ink-soft">
                                  <input type="checkbox" checked={applyAnswer}
                                    onChange={(e) => setApplyAnswer(e.target.checked)}
                                    className="accent-[var(--color-brand)]" />
                                  写入答案
                                </label>
                              )}
                            </div>
                            {rep.proposal.answer?.trim() && (
                              <div className="mt-2 rounded-lg bg-muted/70 px-3 py-2 text-[12px]
                                              leading-relaxed text-ink">
                                {rep.proposal.answer_blocks?.length
                                  ? renderBlocks(rep.proposal.answer_blocks)
                                  : <span className="font-mono text-[11px]">{rep.proposal.answer}</span>}
                              </div>
                            )}
                          </div>

                          {solutionIssues.length > 0 ? (
                            <div className="rounded-xl border border-warn-line bg-warn-soft p-3">
                              <div className="flex items-center gap-1.5 text-[10.5px] font-semibold text-warn">
                                <AlertTriangle size={12} />解析问题
                              </div>
                              <ul className="mt-1.5 space-y-1 text-[10.5px] leading-relaxed text-warn">
                                {solutionIssues.map((x, i) => (
                                  <li key={i} className="flex gap-1.5">
                                    <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-warn/60" />
                                    <span className="min-w-0">{x}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ) : !rep.proposal.solution?.trim() && (
                            <div className="flex items-center gap-2 rounded-xl border border-has-line
                                            bg-has-soft px-3 py-2.5 text-[10.5px] text-has">
                              <CheckCircle2 size={13} />解析步骤未发现明显问题
                            </div>
                          )}

                          {rep.proposal.solution?.trim() && (
                            <div className="rounded-xl border border-border bg-surface p-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="grid h-6 w-6 place-items-center rounded-lg
                                                 bg-brand-soft text-brand">
                                  <FileText size={12} />
                                </span>
                                <span className="text-[11px] font-semibold text-ink">修改后解析</span>
                                <span className="text-[9.5px] text-ink-faint">模型生成 · 需核对</span>
                                <label className="ml-auto flex items-center gap-1.5 text-[10px]
                                                  font-normal text-ink-soft">
                                  <input type="checkbox" checked={applySolution}
                                    onChange={(e) => setApplySolution(e.target.checked)}
                                    className="accent-[var(--color-brand)]" />
                                  写入解析
                                </label>
                              </div>
                              <div className="q-solution q-compact mt-2 text-[12px] leading-relaxed text-ink">
                                {rep.proposal.solution_blocks?.length
                                  ? renderBlocks(rep.proposal.solution_blocks)
                                  : <div className="whitespace-pre-wrap text-[11px] text-ink-soft">
                                      {rep.proposal.solution}
                                    </div>}
                              </div>
                            </div>
                          )}

                          {(figureIssues.length > 0 || tikz) && (
                            <div className="rounded-xl border border-border bg-surface p-3">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="grid h-6 w-6 place-items-center rounded-lg
                                                 bg-muted text-ink-soft">
                                  <ImageIcon size={12} />
                                </span>
                                <span className="text-[11px] font-semibold text-ink">配图检查</span>
                                {tikz && (
                                  <span className="ml-auto flex flex-wrap items-center gap-1">
                                    <button onClick={() => void insertTikzNow(tikz, 'stem')} disabled={busy}
                                      className="press inline-flex items-center gap-1 rounded-md border
                                                 border-warn-line bg-warn-soft px-2 py-1 text-[10px]
                                                 font-medium text-warn hover:bg-warn hover:text-white
                                                 disabled:opacity-40">
                                      <ImagePlus size={10} />插入题干
                                    </button>
                                    <button onClick={() => void insertTikzNow(tikz, 'solution')} disabled={busy}
                                      className="press inline-flex items-center gap-1 rounded-md border
                                                 border-border bg-surface px-2 py-1 text-[10px]
                                                 font-medium text-ink-soft hover:border-warn-line hover:text-warn
                                                 disabled:opacity-40">
                                      插入解析
                                    </button>
                                    <button onClick={() => void copyTikz()}
                                      className="press inline-flex items-center gap-1 rounded-md border
                                                 border-border bg-surface px-2 py-1 text-[10px]
                                                 font-medium text-brand-ink hover:border-brand-line">
                                      {copied ? <Check size={10} /> : <Clipboard size={10} />}
                                      {copied ? '已复制' : '复制'}
                                    </button>
                                  </span>
                                )}
                              </div>
                              {figureIssues.length > 0 && (
                                <ul className="mt-1.5 space-y-1 text-[10.5px] leading-relaxed text-warn">
                                  {figureIssues.map((x, i) => <li key={i}>· {x}</li>)}
                                </ul>
                              )}
                              {tikz && (
                                <pre className="b-scroll mt-2 max-h-[200px] overflow-auto rounded-lg bg-bg
                                                p-2.5 text-[10px] leading-relaxed text-ink-soft">{tikz}</pre>
                              )}
                              <div className="mt-1.5 text-[9.5px] leading-relaxed text-ink-faint">
                                TikZ 由你点「插入题干 / 解析」确认后才写入；也可以复制到「改源码」里调位置。
                              </div>
                            </div>
                          )}
                        </div>

                        {hasProposal ? (
                          <div className="flex flex-wrap items-center gap-2 border-t border-border/70
                                          bg-surface-2/45 px-3.5 py-3">
                            <button onClick={() => void writeBack()} disabled={busy}
                              className="press b-btn b-btn-primary h-8">
                              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                              {busy ? '写入中…' : '写入勾选的建议'}
                            </button>
                            <span className="text-[9.5px] leading-relaxed text-ink-faint">
                              写入后复核失效
                            </span>
                          </div>
                        ) : (
                          <div className="border-t border-border/70 bg-surface-2/45 px-3.5 py-3
                                          text-[10px] text-ink-faint">
                            这次没有可写回的答案或解析建议，只需人工核对问题清单。
                          </div>
                        )}
                      </section>
                    )}

                    {!checking && !curating && !tikzing && !rewrite && !curate && !tikzSug && !rep?.proposal && (
                      <div className="flex flex-col items-center justify-center gap-2 rounded-[18px]
                                      border border-dashed border-border-strong bg-surface/60 px-5 py-12 text-center">
                        <span className="grid h-11 w-11 place-items-center rounded-2xl border border-border
                                         bg-surface text-border-strong">
                          <ShieldCheck size={20} />
                        </span>
                        <div className="text-[12.5px] font-medium text-ink">还没有修改建议</div>
                        <p className="max-w-[360px] text-[10.5px] leading-relaxed text-ink-faint">
                          点中栏「DeepSeek 校对这道题」，或「重写为规范 LaTeX」；
                          结果会按和原题相同的排版渲染在这里，和原题并排对照。
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </aside>
            </div>
          </div>
        )}
      </div>

      {srcOpen && q && (
        <SourceEditor q={q} onClose={() => setSrcOpen(false)}
          onSaved={(d) => {
            setQ(d as Q); setSrcOpen(false); setRep(null); setRewrite(null); setCurate(null); setTikzSug(null); setErr(''); setRetryKind('')
            setListVersion((v) => v + 1)
            setMsg('源码已保存；原复核状态会因正文变化自动失效。')
            detailScroll.current?.scrollTo({ top: 0, behavior: 'smooth' })
            try { localStorage.setItem('ammath.ingest.updated', String(Date.now())) } catch { /* ignore */ }
            onDone()
          }} />
      )}
    </div>
  )
}
