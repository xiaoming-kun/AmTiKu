/** 考点专题：一个考点一页——讲义 + 易错点 + 总结 + 精选题。
 *
 *  这是客户「题型专题」那条的落地版：不再是光秃秃的题库，而是「讲 → 错 → 练」。
 *  数据在 `数据/专题/`（清单 + 每个考点一份讲义 PDF），后端只读。
 *
 *  讲义用浏览器内置 PDF 阅读器直接预览（iframe），不自己造 PDF 渲染器。
 */
import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import katex from 'katex'
import {
  BookOpen, BookOpenText, ChevronLeft, ChevronRight, FileText, GraduationCap, History,
  ListTree, Maximize2, Menu, Minimize2, Pencil, Plus, Printer, RefreshCw, Sparkles,
  TriangleAlert, Type, UserRound, X,
} from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import { type Stage } from '@/lib/stage'
import { renderBlocks } from '@/lib/render'
import QuestionPicker from '@/app/QuestionPicker'
import { toast } from '@/app/Toast'
import NewLectureDialog from '@/app/NewLectureDialog'
import TopicQCard, { type TQ } from '@/app/TopicQCard'
import { splitBlocks } from '@/lib/lectureBlocks'
import { diffCount, diffLines } from '@/lib/textdiff'

type Rel = { id: string; title: string }
type Summary = { label: string; items: string[] }
type Source = { series?: string; author?: string; license?: string; url?: string }
type Topic = {
  id: string; title: string; topic: string; section: string
  stars: number; difficulty: string; pdf: string; pages?: number
  summary: Summary[]; pre?: Rel[]; post?: Rel[]; n: number; placements?: Record<string, string>
  stage?: string; book?: string; chapter?: string; points?: string[]; source?: Source
}
type Q = {
  key: string; type_label: string; difficulty: string; stars: number
  stem: string; options: { label: string; text: string }[]
  answer: string; solution: string
  blocks?: { stem?: unknown[]; options?: unknown[][]; answer?: unknown[]; solution?: unknown[] }
  points: string[]
}

type Heading = { bid: number; level: number; text: string }
type Prefs = { audience: 'teacher' | 'student'; zoom: number; wide: boolean; reading: boolean }
type Progress = { pct: number; bid: number; at: number }
type InlineEdit = { bid: number; title: string; start: number; end: number; tex: string; before: string; caret: number; busy: boolean; err: string }

const PREF_KEY = 'amtiku.lecture.prefs.v1'
const PROGRESS_KEY = 'amtiku.lecture.progress.v1'
const TOPIC_CACHE = new Map<string, { topic: Topic; questions: Q[] }>()
const LECT_CACHE = new Map<string, string>()

function readPrefs(): Prefs {
  try {
    const v = JSON.parse(localStorage.getItem(PREF_KEY) || '{}')
    return {
      audience: v.audience === 'student' ? 'student' : 'teacher',
      zoom: [0.9, 1, 1.1, 1.2].includes(Number(v.zoom)) ? Number(v.zoom) : 1,
      wide: !!v.wide,
      reading: !!v.reading,
    }
  } catch {
    return { audience: 'teacher', zoom: 1, wide: false, reading: false }
  }
}

function readProgress(): Record<string, Progress> {
  try {
    const v = JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}')
    return v && typeof v === 'object' ? v : {}
  } catch {
    return {}
  }
}

/** 网页版讲义：HTML 里的 `.math.*` 交给 KaTeX。
 *  pandoc 把 `\begin{equation}` 原样塞进 span，这里去掉环境壳、align 换成 aligned。 */
const KATEX_MACROS: Record<string, string> = {
  '\\R': '\\mathbb{R}', '\\Z': '\\mathbb{Z}', '\\N': '\\mathbb{N}',
  '\\Q': '\\mathbb{Q}', '\\C': '\\mathbb{C}',
  '\\degree': '^{\\circ}', '\\d': '\\mathrm{d}',
}

function cleanTex(raw: string, display: boolean): string {
  let t = raw
    .replace(/\\label\{[^}]*\}/g, '')
    .replace(/\\tag\{[^}]*\}/g, '')
    .replace(/\\(notag|nonumber)/g, '')
  if (display) {
    t = t.replace(/^\s*\\begin\{equation\}/, '').replace(/\\end\{equation\}\s*$/, '')
      .replace(/\\begin\{align\}/, '\\begin{aligned}').replace(/\\end\{align\}/, '\\end{aligned}')
  }
  return t.trim()
}

function LectureBlocks({ html, blocks: provided, placements, qs, onOpenQ, onRemoveQ, onInsert, editable = true, showAnswer = true, editMode = false,
  inlineEdit, onEditStart, onEditChange, onEditSave, onEditCancel }: {
  html: string
  blocks?: ReturnType<typeof splitBlocks>
  placements: Record<string, string>
  qs: TQ[]
  onOpenQ: (key: string) => void
  onRemoveQ: (key: string) => void
  onInsert: (anchor: string) => void
  editable?: boolean
  showAnswer?: boolean
  editMode?: boolean
  inlineEdit?: InlineEdit | null
  onEditStart?: (bid: number) => void
  onEditChange?: (tex: string) => void
  onEditSave?: () => void
  onEditCancel?: () => void
}) {
  const blocks = useMemo(() => provided ?? splitBlocks(html), [provided, html])
  const ref = useRef<HTMLDivElement>(null)
  const editorRef = useRef<HTMLTextAreaElement>(null)
  const [diffOpen, setDiffOpen] = useState(false)
  const sourceMapped = blocks.some((b) => b.texStart != null && b.texEnd != null)
  const diffRows = useMemo(
    () => inlineEdit ? diffLines(inlineEdit.before, inlineEdit.tex) : [],
    [inlineEdit?.before, inlineEdit?.tex],
  )
  const dcount = diffCount(diffRows)

  useEffect(() => { setDiffOpen(false) }, [inlineEdit?.bid])

  // 点击哪一段，光标尽量落到那一句对应的大致位置（源码里的段落文本）。
  useEffect(() => {
    const ta = editorRef.current
    if (!ta || inlineEdit?.caret == null) return
    const pos = Math.max(0, Math.min(inlineEdit.tex.length, inlineEdit.caret))
    ta.focus()
    ta.setSelectionRange(pos, pos)
  }, [inlineEdit?.bid])

  useEffect(() => {
    const root = ref.current
    if (!root) return
    root.querySelectorAll<HTMLElement>('.lec-block .math.inline, .lec-block .math.display').forEach((el) => {
      if (el.dataset.rendered) return
      const display = el.classList.contains('display')
      try {
        katex.render(cleanTex(el.textContent || '', display), el, {
          displayMode: display, throwOnError: false, strict: false, macros: KATEX_MACROS,
        })
        el.dataset.rendered = '1'
      } catch { /* 渲染失败就留原文，别把整页搞崩 */ }
    })
  }, [blocks])

  return (
    <div ref={ref} className="lecture"
      onDoubleClick={editable ? (e) => {
        const el = (e.target as HTMLElement).closest('.lec-block') as HTMLElement | null
        onInsert(el?.dataset.bid ?? 'end')
      } : undefined}>
      {blocks.map((b, i) => {
        const placed = qs.filter((q) => placements[q.key] === String(i))
        return (
          <Fragment key={i}>
            <div className={`lec-block group relative ${editable && editMode ? 'cursor-text rounded-md outline-offset-4 hover:bg-brand-soft/20 hover:outline hover:outline-1 hover:outline-brand-line' : ''}`}
              data-bid={i}
              onClick={editable && editMode ? (e) => {
                if ((e.target as HTMLElement).closest('button, a, textarea, .inline-editor')) return
                if (sourceMapped && (blocks[i].texStart == null || blocks[i].texEnd == null)) return
                e.stopPropagation(); onEditStart?.(i)
              } : undefined}>
              <div dangerouslySetInnerHTML={{ __html: b.html }} />
              {editable && onEditStart && (!sourceMapped || (blocks[i].texStart != null && blocks[i].texEnd != null)) && (
                <button type="button"
                  onClick={(e) => { e.stopPropagation(); onEditStart(i) }}
                  className="no-print absolute right-2 top-1 z-10 hidden items-center gap-1 rounded-md border
                             border-border bg-surface/95 px-1.5 py-[2px] text-[9.5px] text-ink-faint
                             shadow-[var(--shadow-card)] backdrop-blur group-hover:flex hover:border-brand-line hover:text-brand-ink">
                  ✎ 编辑本节
                </button>
              )}
              {inlineEdit?.bid === i && (
                <div className="no-print relative z-20 my-2 rounded-xl border border-brand-line bg-surface
                                p-3 shadow-[var(--shadow-pop)]" onClick={(e) => e.stopPropagation()}>
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="text-[11.5px] font-semibold text-brand-ink">编辑这一段 · {inlineEdit.title || '本段'}</span>
                    <span className="text-[9.5px] text-ink-faint">只替换这一段/这一块的 TeX，不影响其它段落</span>
                  </div>
                  {!diffOpen ? (
                    <textarea ref={editorRef} value={inlineEdit.tex} disabled={inlineEdit.busy}
                      onChange={(e) => onEditChange?.(e.target.value)} rows={9} spellCheck={false}
                      className="w-full resize-y rounded-lg border border-border bg-surface-2 p-2.5 font-mono
                                 text-[11px] leading-relaxed text-ink outline-none focus:border-brand-line" />
                  ) : (
                    <div className="max-h-[38vh] overflow-auto rounded-lg border border-border bg-surface-2
                                    font-mono text-[10.5px] leading-[1.55]">
                      <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border
                                      bg-surface px-2 py-1 text-[9.5px] text-ink-faint">
                        <span className="text-ok">+{dcount.add}</span>
                        <span className="text-danger">−{dcount.del}</span>
                        <span className="ml-auto">确认后只写回这一段 TeX</span>
                      </div>
                      {diffRows.map((r, k) => (
                        <div key={k}
                          className={`flex gap-2 whitespace-pre-wrap px-2 py-[1px]
                                      ${r.kind === 'add' ? 'bg-ok-soft text-ok'
                                        : r.kind === 'del' ? 'bg-danger-soft text-danger'
                                        : 'text-ink-soft'}`}>
                          <span className="w-5 shrink-0 select-none text-right text-[9px] opacity-55">
                            {r.a ?? r.b ?? ''}
                          </span>
                          <span className="w-3 shrink-0 select-none text-center opacity-65">
                            {r.kind === 'add' ? '+' : r.kind === 'del' ? '−' : ' '}
                          </span>
                          <span className="min-w-0 flex-1">{r.text || ' '}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {inlineEdit.err && <div className="mt-1 text-[10px] text-danger">{inlineEdit.err}</div>}
                  <div className="mt-2 flex items-center gap-1.5">
                    <span className="text-[9.5px] text-ink-faint">
                      {diffOpen ? '先看 diff，再决定是否写回' : `保存会重新生成网页版，约 5–10 秒`}
                    </span>
                    {!diffOpen ? (
                      <>
                        <button onClick={() => setDiffOpen(true)}
                          disabled={inlineEdit.busy || (dcount.add === 0 && dcount.del === 0)}
                          className="press ml-auto rounded-md bg-brand px-3 py-1 text-[10.5px] font-medium text-white disabled:opacity-45">
                          预览并保存
                        </button>
                        <button onClick={onEditCancel} disabled={inlineEdit.busy}
                          className="press rounded-md border border-border bg-surface px-2.5 py-1 text-[10.5px] text-ink-soft">取消</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => setDiffOpen(false)} disabled={inlineEdit.busy}
                          className="press ml-auto rounded-md border border-border bg-surface px-2.5 py-1 text-[10.5px] text-ink-soft">返回编辑</button>
                        <button onClick={onEditSave} disabled={inlineEdit.busy}
                          className="press rounded-md bg-brand px-3 py-1 text-[10.5px] font-medium text-white disabled:opacity-45">
                          {inlineEdit.busy ? '正在生成…' : '确认保存'}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
            {placed.map((q) => (
              <div key={q.key} className="my-3">
                <TopicQCard q={q} onOpen={onOpenQ} onRemove={onRemoveQ} showAnswer={showAnswer} />
              </div>
            ))}
          </Fragment>
        )
      })}
      {editable && <div className="lec-hint">双击讲义任意位置，可以在那里插入题目</div>}
    </div>
  )
}

const SUM_TONE: Record<string, string> = {
  易错点: 'border-warn-line bg-warn-soft text-warn',
  概念: 'border-border bg-muted text-ink-soft',
  方法: 'border-border bg-muted text-ink-soft',
  公式: 'border-border bg-muted text-ink-soft',
  题型: 'border-border bg-muted text-ink-soft',
  应用: 'border-border bg-muted text-ink-soft',
  技巧: 'border-border bg-muted text-ink-soft',
}

export default function TopicsPage({
  stage, onPickPoint, onOpenQuestion, initialPick,
}: {
  stage: Stage
  onPickPoint: (id: string) => void
  onOpenQuestion: (key: string) => void
  /** 从知识卡片跳进来：id + 自增序号（同一份讲义也可以再次定位）。 */
  initialPick?: { id: string; n: number } | null
}) {
  const [list, setList] = useState<Topic[] | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<string>('')
  const [detail, setDetail] = useState<{ topic: Topic; questions: Q[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [exp, setExp] = useState<'teacher' | 'student' | ''>('')
  const [tq, setTq] = useState('')
  const [lect, setLect] = useState<string | null>(null)
  const [picker, setPicker] = useState(false)
  const [anchor, setAnchor] = useState('end')
  const [texOpen, setTexOpen] = useState(false)
  const [texText, setTexText] = useState('')
  const [texBusy, setTexBusy] = useState(false)
  const [prefs, setPrefs] = useState<Prefs>(readPrefs)
  const [progress, setProgress] = useState<Record<string, Progress>>(readProgress)
  const [activeBid, setActiveBid] = useState(0)
  const [pct, setPct] = useState(0)
  const [tocOpen, setTocOpen] = useState(false)
  const [libOpen, setLibOpen] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const [inlineEdit, setInlineEdit] = useState<InlineEdit | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [histOpen, setHistOpen] = useState(false)
  const [hist, setHist] = useState<{ name: string; mtime: number; size: number }[] | null>(null)
  const [histBusy, setHistBusy] = useState(false)
  const srcRef = useRef<{ id: string; text: string } | null>(null)
  const [lectLoading, setLectLoading] = useState(false)
  const pageRef = useRef<HTMLDivElement>(null)
  const restored = useRef('')
  const lastSave = useRef(0)
  const progressRef = useRef(progress)
  progressRef.current = progress

  useEffect(() => {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)) } catch { /* ignore */ }
  }, [prefs])

  const load = () => {
    setErr('')
    api.topics(stage)
      .then((d: { topics: Topic[] }) => {
        setList(d.topics || [])
      })
      .catch((e) => { setErr(String((e as Error)?.message || e)); reportErr(e) })
  }
  useEffect(load, [stage])

  // 首次进入优先恢复上次读到的那份讲义；没有就选第一份。
  useEffect(() => {
    if (!list?.length) return
    setSel((s) => {
      if (s && list.some((t) => t.id === s)) return s
      const last = Object.entries(progressRef.current)
        .sort((a, b) => (b[1]?.at || 0) - (a[1]?.at || 0))[0]?.[0]
      if (last && list.some((t) => t.id === last)) return last
      return list[0].id
    })
  }, [list])

  // 从知识卡片点「讲义」进来：即使当前已经在讲义页，也要切到目标讲义。
  useEffect(() => {
    if (!initialPick || !list?.length) return
    if (list.some((t) => t.id === initialPick.id)) setSel(initialPick.id)
  }, [initialPick?.n, list])

  useEffect(() => {
    if (!sel) return
    const cached = TOPIC_CACHE.get(sel)
    if (cached) { setDetail(cached); setBusy(false); return }
    setBusy(true)
    api.topic(sel)
      .then((d) => { TOPIC_CACHE.set(sel, d); setDetail(d) })
      .catch((e) => { reportErr(e); setDetail(null) })
      .finally(() => setBusy(false))
  }, [sel])

  /** 改讲义：取 LaTeX 源 → 编辑 → 保存并重新生成。 */
  const openTex = async () => {
    if (!t) return
    setTexBusy(true)
    try {
      const r = await fetch(`/api/topics/${t.id}/tex`)
      if (!r.ok) throw new Error('取不到讲义源')
      setTexText((await r.json()).tex || '')
      setTexOpen(true)
    } catch (e) { reportErr(e) } finally { setTexBusy(false) }
  }

  const saveTex = async () => {
    if (!t) return
    setTexBusy(true)
    try {
      const r = await fetch(`/api/topics/${t.id}/tex`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tex: texText }),
      })
      if (!r.ok) {
        let m = '保存失败'
        try { m = (await r.json())?.detail || m } catch { /* ignore */ }
        throw new Error(m)
      }
      const d = await r.json()
      setLect(d.html || null)
      setTexOpen(false)
      setDetail(await api.topic(t.id))
    } catch (e) { reportErr(e) } finally { setTexBusy(false) }
  }

  /** 导出「讲义 + 练习」PDF：取回 blob 再开新窗口（先显示生成中，别让人对着空白等）。 */
  const doExport = async (teacher: boolean) => {
    if (!t) return
    setExp(teacher ? 'teacher' : 'student')
    try {
      const r = await fetch(`/api/topics/${t.id}/export?answers=${teacher ? 1 : 0}`)
      if (!r.ok) {
        let msg = '导出失败'
        try { msg = (await r.json())?.detail || msg } catch { /* 非 JSON */ }
        throw new Error(msg)
      }
      const url = URL.createObjectURL(await r.blob())
      window.open(url, '_blank')
    } catch (e) { reportErr(e) } finally { setExp('') }
  }

  /** 增删题目：写 数据/专题/选题/，再拉一遍详情。 */
  const mutateQs = async (body: { add?: string[]; remove?: string[]; place_after?: string }) => {
    if (!sel) return
    try {
      const r = await fetch(`/api/topics/${sel}/questions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!r.ok) {
        let m = '保存失败'
        try { m = (await r.json())?.detail || m } catch { /* ignore */ }
        throw new Error(m)
      }
      setDetail(await api.topic(sel))
    } catch (e) { reportErr(e); throw e }
  }

  useEffect(() => {
    if (!sel) { setLect(null); setLectLoading(false); return }
    const cached = LECT_CACHE.get(sel)
    if (cached !== undefined) { setLect(cached); setLectLoading(false); return }
    let alive = true
    setLect(null)
    setLectLoading(true)
    api.topicLecture(sel)
      .then((d: { html: string }) => {
        LECT_CACHE.set(sel, d.html)
        if (alive) setLect(d.html)
      })
      .catch(() => { if (alive) setLect(null) })      // 没有网页版就回落页图
      .finally(() => { if (alive) setLectLoading(false) })
    return () => { alive = false }
  }, [sel])

  const blocks = useMemo(() => lect ? splitBlocks(lect) : [], [lect])

  // 从讲义 HTML 的 h2/h3 生成目录；块下标就是滚动锚点。
  const toc = useMemo<Heading[]>(() => {
    if (typeof DOMParser === 'undefined') return []
    return blocks.flatMap((b, bid) => {
      const doc = new DOMParser().parseFromString(b.html, 'text/html')
      const h = doc.querySelector('h2, h3')
      if (!h) return []
      const text = (h.textContent || '').replace(/\s+/g, ' ').trim()
      if (!text) return []
      return [{ bid, level: h.tagName === 'H2' ? 2 : 3, text }]
    })
  }, [blocks])

  const jumpTo = (bid: number, smooth = true) => {
    const root = pageRef.current
    const el = root?.querySelector<HTMLElement>(`[data-bid="${bid}"]`)
    if (!root || !el) return
    const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top
      + root.scrollTop - 64
    root.scrollTo({ top: Math.max(0, top), behavior: smooth ? 'smooth' : 'auto' })
  }

  useEffect(() => {
    if (!sel || !lect) return
    if (restored.current === sel) return
    const root = pageRef.current
    const p = progressRef.current[sel]
    if (!root || !p) { restored.current = sel; return }
    const id = window.requestAnimationFrame(() => {
      if (p.bid) jumpTo(p.bid, false)
      else if (p.pct) root.scrollTop = (root.scrollHeight - root.clientHeight) * p.pct / 100
      restored.current = sel
    })
    return () => window.cancelAnimationFrame(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, lect])

  useEffect(() => {
    if (!sel || !lect) return
    const root = pageRef.current
    if (!root) return
    const onScroll = () => {
      const max = Math.max(1, root.scrollHeight - root.clientHeight)
      const nowPct = Math.round(Math.max(0, Math.min(1, root.scrollTop / max)) * 100)
      setPct(nowPct)
      let cur = toc[0]?.bid ?? 0
      if (toc.length) {
        const line = root.getBoundingClientRect().top + 92
        for (const h of toc) {
          const el = root.querySelector<HTMLElement>(`[data-bid="${h.bid}"]`)
          if (el && el.getBoundingClientRect().top <= line) cur = h.bid
        }
        setActiveBid(cur)
      }
      const t = Date.now()
      if (t - lastSave.current > 500) {
        lastSave.current = t
        const next = {
          ...progressRef.current,
          [sel]: { pct: nowPct, bid: cur, at: t },
        }
        progressRef.current = next
        setProgress(next)
        try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(next)) } catch { /* ignore */ }
      }
    }
    root.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => root.removeEventListener('scroll', onScroll)
    // activeBid deliberately read from closure; only attach per lecture
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, lect, toc])

  useEffect(() => {
    if (!texOpen && !tocOpen && !picker && !libOpen && !newOpen && !histOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setTexOpen(false); setTocOpen(false); setLibOpen(false); setNewOpen(false); setHistOpen(false) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [texOpen, tocOpen, picker, libOpen, newOpen, histOpen])

  const prefetch = (id: string) => {
    if (!TOPIC_CACHE.has(id)) {
      api.topic(id).then((d) => { TOPIC_CACHE.set(id, d); if (sel === id) setDetail(d) }).catch(() => {})
    }
    if (!LECT_CACHE.has(id)) {
      api.topicLecture(id).then((d: { html: string }) => { LECT_CACHE.set(id, d.html); if (sel === id) setLect(d.html) }).catch(() => {})
    }
  }

  const groups = useMemo(() => {
    const kw = tq.trim()
    const m = new Map<string, Topic[]>()
    for (const t of list || []) {
      if (kw && !t.title.includes(kw) && !t.topic.includes(kw)) continue
      m.set(t.topic, [...(m.get(t.topic) || []), t])
    }
    return [...m.entries()]
  }, [list, tq])

  const existingIds = useMemo(() => {
    const s = new Set<string>()
    for (const t of list || []) {
      s.add(t.id)
      for (const p of t.points || []) s.add(p)
    }
    return s
  }, [list])

  if (!list) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-[13px] text-ink-faint">
        {err ? (
          <div className="text-center">
            <div className="mb-2 text-warn">{err}</div>
            <button onClick={load} className="press rounded-lg border border-border px-3 py-1.5">重试</button>
          </div>
        ) : '正在读讲义…'}
      </div>
    )
  }

  if (!list.length) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 text-[13px] text-ink-faint">
        <BookOpen size={22} />
        还没有讲义。把讲义放进 <code className="rounded bg-muted px-1">数据/专题/</code> 并写 manifest.json 即可。
      </div>
    )
  }

  const t = detail?.topic
  const qs = detail?.questions || []
  const paper = !!lect
  const isSenior = stage === 'senior'
  const idx = t ? list.findIndex((x) => x.id === t.id) : -1
  const prevTopic = idx > 0 ? list[idx - 1] : null
  const nextTopic = idx >= 0 && idx < list.length - 1 ? list[idx + 1] : null
  const lastTopic = (() => {
    const last = Object.entries(progress).sort((a, b) => (b[1]?.at || 0) - (a[1]?.at || 0))[0]?.[0]
    return last ? list.find((x) => x.id === last) || null : null
  })()
  const activeHeading = toc.find((h) => h.bid === activeBid)?.text || ''
  const showAnswer = prefs.audience === 'teacher'

  /** 点击某段 → 只编辑它所在的 \section 源码，而不是打开整份讲义。 */
  const openInlineEdit = async (bid: number) => {
    if (!t || !isSenior) return
    let full = srcRef.current?.id === t.id ? srcRef.current.text : ''
    if (!full) {
      try {
        const r = await fetch(`/api/topics/${t.id}/tex`)
        if (!r.ok) throw new Error('取不到讲义源')
        full = String((await r.json()).tex || '')
        srcRef.current = { id: t.id, text: full }
      } catch (e) {
        toast(String((e as Error)?.message || e), { tone: 'warn' })
        return
      }
    }
    const h = toc.filter((x) => x.level === 2 && x.bid <= bid).pop()
    const mapped = blocks[bid]
    const hasMap = blocks.some((x) => x.texStart != null && x.texEnd != null)
    if (hasMap && (mapped?.texStart == null || mapped?.texEnd == null)) {
      toast('这一段来自知识点摘要/附加内容，请在对应数据源里改', { tone: 'info' })
      return
    }
    let a: number
    let b: number
    if (mapped?.texStart != null && mapped?.texEnd != null
        && mapped.texStart >= 0 && mapped.texEnd > mapped.texStart && mapped.texEnd <= full.length) {
      a = mapped.texStart
      b = mapped.texEnd
    } else {
      // 旧缓存没有 sourcepos：回退到所在 section。
      const norm = (x: string) => x.replace(/\\[a-zA-Z]+\s*/g, '')
        .replace(/[{}]/g, '').replace(/\s+/g, '').replace(/^\d+(?:\.\d+)*/, '')
      const target = h ? norm(h.text) : ''
      const secs = [...full.matchAll(/\\section\*?\{([^{}]*)\}/g)]
      const hit = target ? secs.find((m) => norm(m[1]) === target) : undefined
      const start = hit?.index ?? full.indexOf('\\begin{document}')
      const next = hit ? secs[secs.indexOf(hit) + 1] : undefined
      const end = next?.index ?? full.indexOf('\\end{document}')
      a = start >= 0 ? start : 0
      b = end > a ? end : full.length
    }
    const sectionTex = full.slice(a, b)
    const snippet = (blocks[bid]?.text || '').trim().slice(0, 16)
    const caret = snippet ? Math.max(0, sectionTex.indexOf(snippet)) : 0
    setInlineEdit({ bid, title: h?.text || '本段', start: a, end: b,
                    tex: sectionTex, before: sectionTex, caret, busy: false, err: '' })
  }

  const saveInlineEdit = async () => {
    if (!t || !inlineEdit || !srcRef.current) return
    const next = srcRef.current.text.slice(0, inlineEdit.start)
      + inlineEdit.tex + srcRef.current.text.slice(inlineEdit.end)
    setInlineEdit({ ...inlineEdit, busy: true, err: '' })
    try {
      const r = await fetch(`/api/topics/${t.id}/tex`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tex: next }),
      })
      if (!r.ok) {
        let m = '保存失败'
        try { m = (await r.json())?.detail || m } catch { /* ignore */ }
        throw new Error(m)
      }
      const d = await r.json()
      srcRef.current = { id: t.id, text: next }
      LECT_CACHE.set(t.id, d.html || '')
      setLect(d.html || null)
      setInlineEdit(null)
      TOPIC_CACHE.delete(t.id)
      api.topic(t.id).then((x) => { TOPIC_CACHE.set(t.id, x); setDetail(x) }).catch(() => {})
    } catch (e) {
      setInlineEdit((cur) => cur ? { ...cur, busy: false, err: String((e as Error)?.message || e) } : cur)
    }
  }

  const openHistory = async () => {
    if (!t) return
    setHistOpen(true); setHist(null)
    try {
      const d = await api.topicHistory(t.id)
      setHist(d.versions || [])
    } catch (e) { reportErr(e); setHist([]) }
  }

  const restoreHistory = async (name: string) => {
    if (!t || histBusy) return
    setHistBusy(true)
    try {
      const d = await api.topicRestore(t.id, name)
      LECT_CACHE.set(t.id, d.html || '')
      srcRef.current = null
      setLect(d.html || null)
      setInlineEdit(null); setHistOpen(false)
      TOPIC_CACHE.delete(t.id)
      api.topic(t.id).then((x) => { TOPIC_CACHE.set(t.id, x); setDetail(x) }).catch(() => {})
      toast('已恢复到这个版本')
    } catch (e) { reportErr(e) } finally { setHistBusy(false) }
  }

  return (
    <div ref={pageRef} className="b-scroll h-full overflow-y-auto">
    <div className={`mx-auto w-full px-4 py-3 ${prefs.reading ? 'max-w-[1500px]' : 'max-w-[1280px]'}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2 no-print">
        <BookOpenText size={16} className="text-brand" />
        <span className="text-[15px] font-semibold tracking-tight">讲义库</span>
        <span className="tnum rounded-full bg-muted px-2 py-[1px] text-[10.5px] text-ink-soft">
          {list.length} 份
        </span>
        <span className="text-[10.5px] text-ink-faint max-sm:hidden">
          {isSenior ? '一个知识点一份 · 讲 · 错 · 练在同一页' : '一个章节一份 · 与高中同一套讲义模板'}
        </span>
        <button onClick={load} title="重新读取" className="icon-btn h-7 w-7 text-ink-faint">
          <RefreshCw size={14} />
        </button>
        <button onClick={() => setLibOpen(true)} title="打开讲义目录"
          className="press icon-btn h-7 w-7 lg:hidden">
          <Menu size={14} />
        </button>
        {isSenior && (
          <button onClick={() => setNewOpen(true)} title="从高中考点新建讲义"
            className="press flex h-7 items-center gap-1 rounded-lg border border-border bg-surface px-2
                       text-[10.5px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
            <Plus size={12} /><span className="max-sm:hidden">新建讲义</span>
          </button>
        )}
        <button onClick={() => setPrefs((p) => ({ ...p, reading: !p.reading }))}
          title={prefs.reading ? '退出专注阅读' : '专注阅读'}
          className={`press ml-auto flex h-7 items-center gap-1.5 rounded-lg border px-2 text-[11px]
                      ${prefs.reading ? 'border-brand-line bg-brand-soft text-brand-ink' : 'border-border bg-surface text-ink-soft'}`}>
          {prefs.reading ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          <span className="max-sm:hidden">{prefs.reading ? '退出专注' : '专注阅读'}</span>
        </button>
      </div>

      <div className="flex items-start gap-3">
        {libOpen && <div className="fixed inset-0 z-40 bg-scrim lg:hidden" onClick={() => setLibOpen(false)} />}
        {/* 左：专题目录 */}
        <aside className={`${prefs.reading ? 'hidden' : ''} sticky top-0 max-h-[calc(100vh-118px)] w-[238px] shrink-0 space-y-3
                          overflow-y-auto rounded-xl border border-border bg-surface p-2
                          shadow-[var(--shadow-card)] max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-50
                          max-lg:h-full max-lg:max-h-none max-lg:w-[292px] max-lg:rounded-none max-lg:border-0
                          max-lg:p-3 max-lg:shadow-[var(--shadow-pop)] ${libOpen ? '' : 'max-lg:hidden'}`}>
          <div className="flex items-center gap-1 lg:hidden">
            <span className="text-[11.5px] font-semibold">讲义库</span>
            <button onClick={() => setLibOpen(false)} className="icon-btn ml-auto h-7 w-7"><X size={14} /></button>
          </div>
          {lastTopic && (
            <button onClick={() => { setSel(lastTopic.id); setLibOpen(false) }}
              className="press flex w-full items-center gap-2 rounded-lg bg-brand-soft px-2 py-1.5
                         text-left text-[11px] text-brand-ink">
              <BookOpen size={12} />
              <span className="min-w-0 flex-1 truncate">继续 · {lastTopic.title}</span>
              {progress[lastTopic.id]?.pct ? <span className="tnum text-[9.5px]">{progress[lastTopic.id].pct}%</span> : null}
            </button>
          )}
          <input value={tq} onChange={(e) => setTq(e.target.value)}
            placeholder="搜讲义 / 章节"
            className="mb-1 w-full rounded-lg border border-border bg-surface-2 px-2.5 py-1.5
                       text-[11.5px] text-ink outline-none placeholder:text-ink-faint
                       focus:border-brand-line" />
          {groups.map(([topic, items]) => (
            <div key={topic}>
              <div className="mb-1 px-1 text-[10.5px] font-semibold tracking-[0.06em] text-ink-faint">
                {topic}
              </div>
              <div className="space-y-1">
                {items.map((x) => (
                  <button key={x.id} onClick={() => { setSel(x.id); setLibOpen(false) }}
                    onMouseEnter={() => prefetch(x.id)} onFocus={() => prefetch(x.id)}
                    className={`press relative flex w-full items-center gap-2 overflow-hidden rounded-lg px-2 py-[7px] text-left
                                ${sel === x.id
                                  ? 'bg-brand-soft font-semibold text-brand-ink'
                                  : 'text-ink-soft hover:bg-muted hover:text-ink'}`}>
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${sel === x.id ? 'bg-brand' : 'bg-border-strong'}`} />
                    <span className="min-w-0 flex-1 truncate text-[12px]">{x.title}</span>
                    {progress[x.id]?.pct ? (
                      <span className="tnum shrink-0 text-[9px] text-ink-faint">{progress[x.id].pct}%</span>
                    ) : (
                      <span className="tnum shrink-0 text-[9.5px] text-warn">
                        {x.stars ? '★'.repeat(x.stars) : ''}
                      </span>
                    )}
                    {progress[x.id]?.pct ? (
                      <span className="absolute inset-x-2 bottom-0 h-[2px] overflow-hidden rounded-full bg-border">
                        <span className="block h-full bg-brand" style={{ width: `${progress[x.id].pct}%` }} />
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </aside>

        {/* 右：一个专题 */}
        <main className="min-w-0 flex-1 space-y-3">
          {!t ? (
            <div className="flex h-48 items-center justify-center text-[12.5px] text-ink-faint">
              {busy ? '正在读讲义…' : '选一份讲义'}
            </div>
          ) : (
            <>
              {/* ── 阅读工具条：上/下一份、进度、目录、教师/学生、字号 ── */}
              <div className="no-print sticky top-0 z-30 -mx-1 mb-1 border-b border-border/70
                              bg-[color-mix(in_srgb,var(--color-surface)_92%,transparent)]
                              px-1 pb-1.5 pt-1.5 backdrop-blur-xl">
                <div className="flex items-center gap-1.5">
                  <button onClick={() => prevTopic && setSel(prevTopic.id)} disabled={!prevTopic}
                    title={prevTopic ? `上一份：${prevTopic.title}` : '已经是第一份'}
                    className="icon-btn h-7 w-7 disabled:opacity-25">
                    <ChevronLeft size={15} />
                  </button>
                  <button onClick={() => nextTopic && setSel(nextTopic.id)} disabled={!nextTopic}
                    title={nextTopic ? `下一份：${nextTopic.title}` : '已经是最后一份'}
                    className="icon-btn h-7 w-7 disabled:opacity-25">
                    <ChevronRight size={15} />
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[11.5px] font-semibold">{t.title}</div>
                    <div className="truncate text-[9.5px] text-ink-faint">
                      {activeHeading || (isSenior ? `${t.topic} · ${t.section}` : `${t.book || t.topic} · ${t.chapter || t.section}`)}
                    </div>
                  </div>
                  <span className="tnum shrink-0 text-[10px] text-ink-faint">{pct}%</span>

                  {toc.length > 0 && (
                    <div className="relative shrink-0">
                      <button onClick={() => setTocOpen((v) => !v)} title="讲义目录"
                        className={`press flex h-7 items-center gap-1 rounded-lg border px-2 text-[10.5px]
                                    ${tocOpen ? 'border-brand-line bg-brand-soft text-brand-ink'
                                              : 'border-border bg-surface text-ink-soft hover:border-border-strong'}`}>
                        <ListTree size={12} /><span className="max-sm:hidden">目录</span>
                      </button>
                      {tocOpen && (
                        <div className="pop absolute right-0 top-[calc(100%+6px)] z-50 max-h-[58vh] w-[300px]
                                        overflow-y-auto rounded-xl border border-border bg-surface p-1.5
                                        shadow-[var(--shadow-pop)]">
                          {toc.map((h) => (
                            <button key={h.bid} onClick={() => { jumpTo(h.bid); setTocOpen(false) }}
                              className={`flex w-full items-start gap-1.5 rounded-lg px-2 py-[5px] text-left
                                          text-[11px] ${activeBid === h.bid
                                            ? 'bg-brand-soft font-medium text-brand-ink'
                                            : 'text-ink-soft hover:bg-muted'}`}>
                              <span className={`mt-[2px] h-1 w-1 shrink-0 rounded-full ${activeBid === h.bid ? 'bg-brand' : 'bg-border-strong'}`} />
                              <span className={`min-w-0 flex-1 ${h.level === 3 ? 'pl-2 text-[10.5px] text-ink-faint' : ''}`}>
                                {h.text}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* 教师版 / 学生版：网页里也支持，不再只能导出 PDF */}
                  <div className="flex shrink-0 rounded-lg bg-muted p-0.5" role="group" aria-label="讲义版本">
                    <button onClick={() => setPrefs((p) => ({ ...p, audience: 'teacher' }))}
                      title="教师版：显示答案与解析"
                      aria-pressed={showAnswer}
                      className={`press flex h-6 items-center gap-1 rounded-md px-1.5 text-[10px]
                                  ${showAnswer ? 'bg-surface font-medium text-brand-ink shadow-[var(--shadow-card)]' : 'text-ink-faint'}`}>
                      <GraduationCap size={12} /><span className="max-sm:hidden">教师</span>
                    </button>
                    <button onClick={() => setPrefs((p) => ({ ...p, audience: 'student' }))}
                      title="学生版：隐藏答案与解析"
                      aria-pressed={!showAnswer}
                      className={`press flex h-6 items-center gap-1 rounded-md px-1.5 text-[10px]
                                  ${!showAnswer ? 'bg-surface font-medium text-brand-ink shadow-[var(--shadow-card)]' : 'text-ink-faint'}`}>
                      <UserRound size={12} /><span className="max-sm:hidden">学生</span>
                    </button>
                  </div>

                  <div className="hidden shrink-0 items-center gap-0.5 rounded-lg border border-border bg-surface p-0.5 lg:flex">
                    <Type size={11} className="mx-0.5 text-ink-faint" />
                    <button onClick={() => setPrefs((p) => ({ ...p, zoom: Math.max(0.9, +(p.zoom - 0.1).toFixed(1)) }))}
                      disabled={prefs.zoom <= 0.9} title="缩小字号"
                      className="press h-6 w-6 rounded-md text-[10px] text-ink-soft hover:bg-muted disabled:opacity-30">A−</button>
                    <button onClick={() => setPrefs((p) => ({ ...p, zoom: Math.min(1.2, +(p.zoom + 0.1).toFixed(1)) }))}
                      disabled={prefs.zoom >= 1.2} title="放大字号"
                      className="press h-6 w-6 rounded-md text-[10px] text-ink-soft hover:bg-muted disabled:opacity-30">A＋</button>
                  </div>
                  {isSenior && (
                    <button onClick={openHistory}
                      title="讲义版本历史"
                      className="press flex h-7 shrink-0 items-center gap-1 rounded-lg border border-border
                                 bg-surface px-1.5 text-[10px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
                      <History size={12} /><span className="max-sm:hidden">历史</span>
                    </button>
                  )}
                  {isSenior && (
                    <button onClick={() => setEditMode((v) => !v)}
                      title={editMode ? '退出编辑模式' : '编辑模式：点击任意段落直接改本节'}
                      className={`press flex h-7 shrink-0 items-center gap-1 rounded-lg border px-1.5 text-[10px]
                                  ${editMode ? 'border-brand-line bg-brand-soft text-brand-ink'
                                             : 'border-border bg-surface text-ink-soft'}`}>
                      <Pencil size={12} /><span className="max-sm:hidden">编辑</span>
                    </button>
                  )}
                  <button onClick={() => setPrefs((p) => ({ ...p, reading: !p.reading }))}
                    title={prefs.reading ? '退出专注阅读' : '专注阅读'}
                    className={`press flex h-7 shrink-0 items-center gap-1 rounded-lg border px-1.5 text-[10px]
                                ${prefs.reading ? 'border-brand-line bg-brand-soft text-brand-ink'
                                                : 'border-border bg-surface text-ink-soft'}`}>
                    {prefs.reading ? <Minimize2 size={12} /> : <Maximize2 size={12} />}
                    <span className="max-sm:hidden">专注</span>
                  </button>
                  <button onClick={() => window.print()} title="打印讲义"
                    className="icon-btn hidden h-7 w-7 sm:inline-flex"><Printer size={13} /></button>
                </div>
                <div className="mt-1 h-[2px] overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-brand transition-[width] duration-200"
                    style={{ width: `${pct}%` }} />
                </div>
              </div>

              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h2 className="text-[22px] font-semibold tracking-tight">{t.title}</h2>
                <span className="text-[11px] text-ink-faint">
                  {isSenior ? `${t.topic} · ${t.section}` : `${t.book || t.topic} · ${t.chapter || t.section}`}
                  {' '}· {t.difficulty} {'★'.repeat(t.stars || 0)}
                </span>
                <div className="ml-auto flex items-center gap-1.5">
                  {isSenior && (
                    <>
                      <button onClick={() => doExport(true)} disabled={!!exp}
                        title="讲义 + 精选题（含答案与解析）"
                        className="b-btn b-btn-primary h-7 px-2.5 text-[11px]">
                        {exp === 'teacher' ? '正在生成…' : '导出教师版'}
                      </button>
                      <button onClick={() => doExport(false)} disabled={!!exp}
                        title="讲义 + 精选题（答案留空）"
                        className="b-btn b-btn-secondary h-7 px-2.5 text-[11px]">
                        {exp === 'student' ? '正在生成…' : '学生版'}
                      </button>
                    </>
                  )}
                  {isSenior && (
                    <button onClick={openTex} disabled={texBusy}
                      className="b-btn b-btn-secondary h-7 px-2.5 text-[11px]">
                      {texBusy ? '读取中…' : '改讲义'}
                    </button>
                  )}
                  <button onClick={() => onPickPoint((t.points && t.points[0]) || t.id)}
                    className="b-btn b-btn-ghost h-7 px-2.5 text-[11px]">
                    {isSenior ? '看这些题 →' : '看诊断题 →'}
                  </button>
                </div>
              </div>
              {!isSenior && t.source?.author && (
                <div className="text-[10.5px] text-ink-faint">
                  内容来源：{t.source.author}
                  {t.source.license ? ` · ${t.source.license}` : ''}
                  {t.source.url ? (
                    <> · <a href={t.source.url} target="_blank" rel="noreferrer"
                      className="text-brand-ink hover:underline">GitHub 原文</a></>
                  ) : null}
                </div>
              )}

              {/* 讲义 + 练习：有网页版时合成一张纸，界面统一 */}
              <div className={`${paper ? 'lecture-paper lecture-print-area' : 'space-y-3'}`}
                style={paper ? ({
                  '--lec-font': `${14 * prefs.zoom}px`,
                  '--lec-width': prefs.wide ? '1080px' : '900px',
                  '--lec-paper': prefs.wide ? '1120px' : '920px',
                } as CSSProperties) : undefined}>
              <section className={paper ? '' : 'space-y-3'}>
                <div className={`flex items-center gap-2 text-[11px] text-ink-faint ${paper ? 'px-8 pt-3' : 'px-1'}`}>
                  <FileText size={13} className="text-brand" />
                  讲义 · {lect ? '网页版（KaTeX）' : `${t.pages || 0} 页`}
                  <a href={`/api/topics/${t.id}/pdf`} target="_blank" rel="noreferrer"
                    className="ml-auto text-[10.5px] text-brand-ink hover:underline">
                    打开 PDF 原件
                  </a>
                </div>
                {lect ? (
                  <LectureBlocks html={lect} blocks={blocks}
                    placements={(t.placements || {}) as Record<string, string>}
                    qs={(qs as unknown) as TQ[]}
                    onOpenQ={onOpenQuestion}
                    onRemoveQ={(k) => { if (isSenior) mutateQs({ remove: [k] }) }}
                    editable={isSenior} showAnswer={showAnswer} editMode={editMode}
                    onInsert={(a) => { if (editMode) return; setAnchor(a); setPicker(true) }}
                    inlineEdit={inlineEdit}
                    onEditStart={openInlineEdit}
                    onEditChange={(tex) => setInlineEdit((cur) => cur ? { ...cur, tex } : cur)}
                    onEditSave={saveInlineEdit}
                    onEditCancel={() => setInlineEdit(null)} />
                ) : lectLoading ? (
                  <div className="space-y-3 px-8 py-8">
                    <div className="skeleton h-5 w-40" />
                    <div className="skeleton h-3.5 w-[92%]" />
                    <div className="skeleton h-3.5 w-[84%]" />
                    <div className="skeleton h-3.5 w-[76%]" />
                    <div className="skeleton mt-4 h-24 w-full" />
                  </div>
                ) : (
                  Array.from({ length: t.pages || 0 }, (_, i) => (
                    <img key={i} src={`/api/topics/${t.id}/page/${i + 1}`}
                      alt={`讲义第 ${i + 1} 页`}
                      loading={i < 2 ? 'eager' : 'lazy'}
                      className="w-full rounded-md border border-border bg-white
                                 shadow-[0_2px_12px_rgba(0,0,0,.28)]" />
                  ))
                )}
                {!t.pages && (
                  <div className="rounded-lg border border-dashed border-border px-3 py-10 text-center
                                  text-[12px] text-ink-faint">这个知识点还没有讲义</div>
                )}
              </section>

              {/* 易错点 / 总结 / 关系（网页版讲义里已经并进正文，这里只在页图模式显示） */}
              <div className={paper ? 'hidden' : 'grid gap-3 lg:grid-cols-3'}>
                <section className="rounded-[var(--radius-card)] border border-border bg-surface p-3
                                    shadow-[var(--shadow-card)]">
                  <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold">
                    <TriangleAlert size={13} className="text-warn" />
                    易错点
                  </div>
                  <ul className="space-y-1.5">
                    {(t.summary.find((s) => s.label === '易错点')?.items || []).map((x, i) => (
                      <li key={i} className="text-[11.5px] leading-relaxed text-ink-soft">· {x}</li>
                    ))}
                    {!t.summary.some((s) => s.label === '易错点') && (
                      <li className="text-[11px] text-ink-faint">这个考点还没有易错点</li>
                    )}
                  </ul>
                </section>

                <section className="rounded-[var(--radius-card)] border border-border bg-surface p-3
                                    shadow-[var(--shadow-card)] lg:col-span-2">
                  <div className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold">
                    <Sparkles size={13} className="text-brand" />
                    总结
                  </div>
                  <div className="space-y-2">
                    {t.summary.filter((s) => s.label !== '易错点').map((s) => (
                      <div key={s.label} className="flex gap-2">
                        <span className={`mt-[1px] h-fit shrink-0 rounded border px-1.5 py-[1px] text-[9.5px] ${
                          SUM_TONE[s.label] || SUM_TONE.概念}`}>{s.label}</span>
                        <div className="min-w-0 flex-1 space-y-1">
                          {s.items.map((x, i) => (
                            <p key={i} className="text-[11.5px] leading-relaxed text-ink-soft">{x}</p>
                          ))}
                        </div>
                      </div>
                    ))}
                    {!t.summary.some((s) => s.label !== '易错点') && (
                      <p className="text-[11px] text-ink-faint">这个考点只有易错点，没有其他总结（讲义里有展开）。</p>
                    )}
                  </div>
                  {(t.pre?.length || t.post?.length) ? (
                    <div className="mt-2 flex flex-wrap items-center gap-1 border-t border-border pt-2
                                    text-[10.5px] text-ink-faint">
                      {t.pre?.length ? <span>先修</span> : null}
                      {t.pre?.map((r) => (
                        <span key={r.id} className="rounded bg-muted px-1.5 py-[1px]">{r.title}</span>
                      ))}
                      {t.post?.length ? <span className="ml-2">后续</span> : null}
                      {t.post?.map((r) => (
                        <span key={r.id} className="rounded bg-muted px-1.5 py-[1px]">{r.title}</span>
                      ))}
                    </div>
                  ) : null}
                </section>
              </div>

              {/* 精选题：高中接题库；小初只做讲义，不排练习 */}
              {isSenior && (
              <section className={paper ? 'lecture-practice' : ''}>
                <div className="mb-2 flex items-baseline gap-2">
                  <h3 className="text-[12.5px] font-semibold">练习</h3>
                  <span className="text-[10.5px] text-ink-faint">
                    {qs.length} 道 · 按难度挑的（简单 3 / 中档 3 / 难题 2），答案与解析都在
                  </span>
                  <button onClick={() => { setAnchor('end'); setPicker(true) }}
                    className="press ml-auto rounded-md border border-border px-2 py-[2px]
                               text-[10.5px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
                    ＋ 添加题目
                  </button>
                </div>
                <div className="space-y-2">
                  {qs.filter((q) => !t.placements?.[q.key]).map((q, i) => (
                    <article key={q.key}
                      className="rounded-[var(--radius-card)] border border-border bg-surface p-3
                                 shadow-[var(--shadow-card)]">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-faint">
                        <span className="tnum font-semibold text-ink-soft">{i + 1}</span>
                        <span className="rounded border border-border px-1 py-[1px]">{q.type_label}</span>
                        <span className="rounded bg-muted px-1 py-[1px]">{q.difficulty}</span>
                        <button onClick={() => mutateQs({ remove: [q.key] })}
                          className="ml-auto shrink-0 rounded border border-border px-1.5 py-[1px]
                                     text-[9.5px] text-ink-faint hover:border-danger hover:text-danger">
                          移出
                        </button>
                        <button onClick={() => onOpenQuestion(q.key)}
                          className="shrink-0 rounded border border-border px-1.5 py-[1px]
                                     text-[9.5px] text-ink-faint hover:border-brand-line
                                     hover:text-brand-ink">工作台打开 ↗</button>
                      </div>
                      <div className="q-stem text-[12.5px] text-ink">{renderBlocks(q.blocks?.stem as never)}</div>
                      {!!q.blocks?.options?.length && (
                        <div className="mt-1.5 grid gap-1 sm:grid-cols-2">
                          {(q.blocks.options as never[][]).map((opt, j) => (
                            <div key={j} className="flex items-baseline gap-1 text-[12px] text-ink-soft">
                              <span className="font-medium text-ink-faint">{q.options?.[j]?.label || j + 1}.</span>
                              <span className="min-w-0">{renderBlocks(opt)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {showAnswer ? <details className="mt-1.5 border-t border-border pt-1.5">
                        <summary className="cursor-pointer text-[10.5px] text-ink-faint">答案与解析</summary>
                        <div className="mt-1 space-y-1 text-[12px]">
                          <div className="flex gap-1.5">
                            <span className="shrink-0 text-[10.5px] font-semibold text-brand">答案</span>
                            <div className="min-w-0 flex-1 text-ink">{renderBlocks(q.blocks?.answer as never)}</div>
                          </div>
                          {q.blocks?.solution?.length ? (
                            <div className="flex gap-1.5">
                              <span className="shrink-0 text-[10.5px] font-semibold text-ink-faint">解析</span>
                              <div className="min-w-0 flex-1 text-ink-soft">{renderBlocks(q.blocks.solution as never)}</div>
                            </div>
                          ) : null}
                        </div>
                      </details> : (
                        <div className="mt-1.5 border-t border-border pt-1.5 text-[10.5px] text-ink-faint">
                          答案与解析已隐藏 · 学生版
                        </div>
                      )}
                    </article>
                  ))}
                  {!qs.length && (
                    <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center
                                    text-[12px] text-ink-faint">这份讲义还没有精选题</div>
                  )}
                </div>
              </section>
              )}
              {!isSenior && (
                <div className="rounded-lg border border-dashed border-border px-4 py-5 text-[11.5px] leading-relaxed text-ink-faint">
                  本章只做讲义，不排练习。需要做题时，点右上角「看诊断题」，按本章知识点进入诊断题库。
                </div>
              )}
              </div>

              {/* 读完这一份，直接去下一份；不用回左侧目录找。 */}
              <div className="no-print flex items-center gap-2 pb-4 pt-1">
                <button onClick={() => prevTopic && setSel(prevTopic.id)} disabled={!prevTopic}
                  className="press flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-border
                             bg-surface px-3 py-2 text-left disabled:opacity-35">
                  <ChevronLeft size={15} className="shrink-0 text-ink-faint" />
                  <span className="min-w-0">
                    <span className="block text-[9.5px] text-ink-faint">上一份</span>
                    <span className="block truncate text-[11.5px] text-ink-soft">{prevTopic?.title || '已经到第一份'}</span>
                  </span>
                </button>
                <span className="tnum shrink-0 text-[10px] text-ink-faint">{idx + 1} / {list.length}</span>
                <button onClick={() => nextTopic && setSel(nextTopic.id)} disabled={!nextTopic}
                  className="press flex min-w-0 flex-1 items-center justify-end gap-2 rounded-xl border border-border
                             bg-surface px-3 py-2 text-right disabled:opacity-35">
                  <span className="min-w-0">
                    <span className="block text-[9.5px] text-ink-faint">下一份</span>
                    <span className="block truncate text-[11.5px] text-ink-soft">{nextTopic?.title || '已经到最后一份'}</span>
                  </span>
                  <ChevronRight size={15} className="shrink-0 text-ink-faint" />
                </button>
              </div>
            </>
          )}
        </main>
      </div>

      {newOpen && (
        <NewLectureDialog existing={existingIds}
          onClose={() => setNewOpen(false)}
          onCreated={(id) => {
            TOPIC_CACHE.delete(id); LECT_CACHE.delete(id)
            restored.current = ''
            setNewOpen(false); setLibOpen(false); setSel(id); load()
          }} />
      )}

      {histOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
          onClick={() => !histBusy && setHistOpen(false)}>
          <div className="flex max-h-[72vh] w-full max-w-[520px] flex-col overflow-hidden rounded-[18px]
                          border border-border bg-surface shadow-[var(--shadow-pop)]"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 border-b border-border px-4 py-3">
              <History size={14} className="text-brand" />
              <span className="text-[13px] font-semibold">讲义版本历史</span>
              <span className="text-[10px] text-ink-faint">每次保存前自动留档</span>
              <button onClick={() => setHistOpen(false)} className="icon-btn ml-auto h-7 w-7"><X size={14} /></button>
            </div>
            <div className="b-scroll min-h-0 flex-1 overflow-y-auto p-2">
              {hist === null ? (
                <div className="py-10 text-center text-[11.5px] text-ink-faint">正在读历史…</div>
              ) : !hist.length ? (
                <div className="py-10 text-center text-[11.5px] text-ink-faint">还没有历史版本；保存一次后会出现。</div>
              ) : hist.map((v) => (
                <div key={v.name} className="flex items-center gap-2 rounded-lg px-2 py-2 hover:bg-muted">
                  <span className="tnum shrink-0 text-[10px] text-ink-faint">
                    {new Date(v.mtime * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-ink-soft">{v.name}</span>
                  <span className="tnum shrink-0 text-[9.5px] text-ink-faint">{Math.max(1, Math.round(v.size / 1024))}K</span>
                  <button onClick={() => restoreHistory(v.name)} disabled={histBusy}
                    className="press shrink-0 rounded-md border border-border bg-surface px-2 py-[3px]
                               text-[10px] text-ink-soft hover:border-brand-line hover:text-brand-ink disabled:opacity-40">
                    恢复
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {texOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
          onClick={() => !texBusy && setTexOpen(false)}>
          <div className="flex h-[84vh] w-full max-w-[1000px] flex-col overflow-hidden rounded-xl
                          border border-border bg-surface shadow-[var(--shadow-pop)]"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
              <span className="text-[13.5px] font-semibold">修改讲义源 · {t?.title}</span>
              <span className="text-[10.5px] text-ink-faint">
                改的是 数据/专题 里的副本；保存后自动重新生成网页版
              </span>
              <button onClick={() => setTexOpen(false)} disabled={texBusy}
                className="icon-btn ml-auto h-7 w-7"><X size={15} /></button>
            </div>
            <textarea value={texText} onChange={(e) => setTexText(e.target.value)} spellCheck={false}
              className="min-h-0 flex-1 resize-none bg-[#0f1218] p-4 font-mono text-[12px]
                         leading-relaxed text-[#d6dde8] outline-none" />
            <div className="flex items-center gap-2 border-t border-border px-4 py-2.5">
              <span className="text-[10.5px] text-ink-faint">
                LaTeX 源；保存后 xelatex + pandoc 重新生成，约 5–10 秒
              </span>
              <button onClick={() => setTexOpen(false)} disabled={texBusy}
                className="press ml-auto rounded-md border border-border px-3 py-1.5 text-[11.5px] text-ink-soft">
                取消
              </button>
              <button onClick={saveTex} disabled={texBusy}
                className="press rounded-md bg-brand px-3.5 py-1.5 text-[11.5px] font-semibold
                           text-white disabled:opacity-60">
                {texBusy ? '正在重新生成…' : '保存并重新生成'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isSenior && (
        <QuestionPicker
          open={picker}
          pointId={t?.id || ''}
          title={t?.title || ''}
          existing={new Set(qs.map((q) => q.key))}
          onClose={() => setPicker(false)}
          anchor={anchor}
          onAdd={(keys) => mutateQs({ add: keys, place_after: anchor === 'end' ? '' : anchor })}
        />
      )}
    </div>
    </div>
  )
}
