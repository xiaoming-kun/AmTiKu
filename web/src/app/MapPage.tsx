/** 知识地图：左边目录、中间局部先修图、右边详情——照参考项目 explore 页的三栏结构。
 *
 *  客户的两条反馈：
 *  ①「没有小学初中的知识点」→ 全学段 585 个知识点，左栏按册/章/知识点展开；
 *  ②「要有前置后置」→ 中间以选中点为中心画先修（上）与后续（下），
 *    右边给出直接关系和**完整先修链**（按教材顺序，就是推荐补课顺序）。
 *
 *  为什么只画局部：585 个点全铺开是毛线球（`设计/知识链路.md` 量过）。
 *  点任意节点就把它换到中间，一路可以追到小学。
 */
import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft, BookOpen, ChevronRight, FilePlus2, RefreshCw, Search, X,
} from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import { toast } from '@/app/Toast'
import { toggleMastered, useMastery } from '@/lib/mastery'
import GraphView from '@/app/GraphView'
import MindMapView from '@/app/MindMapView'
import PanoramaView from '@/app/PanoramaView'
import type { Tone } from '@/app/GraphView'
import type { Stage } from '@/lib/stage'
import type { Q } from '@/lib/types'

type MPoint = {
  id: string; title: string; note: string
  stars: number; difficulty: string; fields: Record<string, string[]>
  q?: number     // 诊断题（小初）
  nq?: number    // 题库里的题（高中）
}
type MQ = {
  prompt: string; answer: string; explanation?: string
  type: string; level: string; choices?: [string, string][]; via?: string
}
type MEdge = { from: string; to: string; strength: string; kind: string; reason?: string }
type MChapter = { title: string; n: number; points: MPoint[] }
type MBook = {
  name: string; grade: number; semester: string; note: string
  n: number; chapters: MChapter[]
}
type MStage = { key: Stage; name: string; n: number; books: MBook[] }
type MData = {
  version: number; updated: string; edition: string; total: number
  stages: MStage[]; edges: MEdge[]
  stats: { points: number; covered: number; edges: number; hard: number; soft: number; prereq: number; order: number }
}

type Loc = { stage: string; skey: Stage; book: string; grade: number; chapter: string; order: number; name: string; p: MPoint }

const GRADE_LABEL: Record<number, string> = {
  1: '一年级', 2: '二年级', 3: '三年级', 4: '四年级', 5: '五年级', 6: '六年级',
  7: '七年级', 8: '八年级', 9: '九年级', 10: '高一', 11: '高二', 12: '高三',
}
const TONE_OF_STAGE: Record<string, Tone> = { primary: 'p', junior: 'j', senior: 'h' }
const DOT: Record<Tone, string> = { p: '#0f766e', j: '#1d4ed8', h: '#6d28d9' }
/** 考点标题里带着「1.2 」这种编号，显示时去掉；教材位置由右栏的册/章负责。 */
const disp = (t: string) => t.replace(/^\d+(\.\d+)*\s+/, '')

/** 关系标签：硬先修 / 有帮助 / 教材顺序。 */
function EdgeBadge({ e }: { e: MEdge }) {
  const [label, cls] = e.strength === 'hard'
    ? ['先修', 'border-brand-line bg-brand-soft text-brand-ink']
    : e.kind === 'order'
      ? ['顺序', 'border-dashed border-border text-ink-faint']
      : ['有帮助', 'border-border bg-muted text-ink-soft']
  return <span className={`shrink-0 rounded border px-1 py-[1px] text-[9.5px] ${cls}`}>{label}</span>
}

/** 右侧详情：教材位置 + 直接先修/后续 + 完整先修链。 */
function Detail({ loc, pre, post, ancestors, prereqsOf, locs, onPick, onClose, onJump,
  titleOf, onBuildPaper, building }: {
  loc: Loc; pre: MEdge[]; post: MEdge[]; ancestors: string[]
  prereqsOf: (id: string) => string[]
  locs: Map<string, Loc>
  onPick: (id: string) => void
  onClose: () => void
  onJump: (id: string, stage: Stage) => void
  titleOf: (id: string) => string
  onBuildPaper: (ids: string[]) => void
  building: boolean
}) {
  const known = useMastery()
  const [openChain, setOpenChain] = useState(true)
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const [qs, setQs] = useState<MQ[] | null>(null)
  const [openQs, setOpenQs] = useState(false)
  useEffect(() => { setQs(null); setOpenQs(false) }, [loc.p.id])
  const loadQs = () => {
    if (qs || !loc.p.q) return
    api.mapQuestions(loc.p.id)
      .then((r: { qs: MQ[] }) => setQs(r.qs || []))
      .catch((e) => { reportErr(e); setQs([]) })
  }
  const unknown = ancestors.filter((id) => !known.has(id))
  const unk = new Set(unknown)
  // 根因 = 还要补、且它的直接先修都已经会了（或本来就没有）——就是「该从哪一条开始」
  const roots = new Set(unknown.filter((id) => prereqsOf(id).every((q) => !unk.has(q))))
  /** 路径按「册 · 章」分组：35 条平铺看不出在补哪几课。 */
  const groups = useMemo(() => {
    const out: { key: string; book: string; chapter: string; items: string[] }[] = []
    // 用全部祖先：勾成「已会」的仍然留在列表里（划线），不然勾完就消失、再也点不回来
    for (const id of ancestors) {
      const l = locs.get(id)
      if (!l) continue
      const key = `${l.book}\u0000${l.chapter}`
      let g = out.find((x) => x.key === key)
      if (!g) { g = { key, book: l.book, chapter: l.chapter, items: [] }; out.push(g) }
      g.items.push(id)
    }
    return out
  }, [ancestors, locs])
  const nq = loc.p.nq || 0
  const qd = loc.p.q || 0
  // 推荐路径会一路追到小学/初中；组卷只挑**真有题库题**的点（高中），
  // 否则前 12 个全是小初点，一道题也挑不出来。
  const paperIds = unknown.filter((id) => ((locs.get(id)?.p.nq) || 0) > 0)
  const senior = loc.skey === 'senior'
  const Rows = ({ edges, dir }: { edges: MEdge[]; dir: 'pre' | 'post' }) => (
    <div className="space-y-1">
      {edges.length === 0 && (
        <div className="rounded-lg border border-dashed border-border px-2 py-2 text-[11px] text-ink-faint">
          {dir === 'pre' ? '没有先修，这一课是起点' : '没有后续，这一课是终点'}
        </div>
      )}
      {edges.map((e) => {
        const id = dir === 'pre' ? e.from : e.to
        return (
          <button key={`${e.from}-${e.to}-${e.kind}`} onClick={() => onPick(id)}
            title={e.reason || (e.kind === 'order' ? '教材顺序上排在前面' : '')}
            className="flex w-full items-center gap-1.5 rounded-lg border border-border bg-surface
                       px-2 py-1.5 text-left hover:border-brand-line">
            <span className="min-w-0 flex-1 truncate text-[12px] text-ink">{titleOf(id)}</span>
            <EdgeBadge e={e} />
          </button>
        )
      })}
    </div>
  )
  return (
    <aside className="flex w-[300px] shrink-0 flex-col overflow-hidden rounded-[var(--radius-card)]
                      max-lg:w-full
                      border border-border bg-surface shadow-[var(--shadow-card)]">
      <div className="flex items-start gap-2 border-b border-border px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-[10.5px] text-ink-faint">
            <i className="h-2 w-2 rounded-[2px]" style={{ background: DOT[TONE_OF_STAGE[loc.skey]] }} />
            {loc.stage} · {GRADE_LABEL[loc.grade]}
          </div>
          <h3 className="mt-0.5 text-[14.5px] font-semibold leading-snug text-ink">{loc.name}</h3>
          <div className="mt-0.5 text-[10.5px] text-ink-faint">{loc.book} · {loc.chapter}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-faint">
            <span className="tnum rounded bg-muted px-1.5 py-[1px]">题 {nq}</span>
            <span className="tnum rounded bg-muted px-1.5 py-[1px]">诊断 {qd}</span>
            {nq === 0 && qd === 0 && <span className="rounded bg-warn-soft px-1.5 py-[1px] text-warn">待建</span>}
            {senior && loc.p.difficulty && (
              <span className="tnum">{loc.p.difficulty} · {'★'.repeat(loc.p.stars || 0)}</span>
            )}
          </div>
        </div>
        <button onClick={onClose} title="关闭" className="icon-btn h-6 w-6 shrink-0">
          <X size={13} />
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-2.5">
        {loc.p.note && (
          <p className="text-[11.5px] leading-relaxed text-ink-soft">{loc.p.note}</p>
        )}

        <button onClick={() => onJump(loc.p.id, loc.skey)}
          className="press w-full rounded-lg bg-brand px-3 py-2 text-[12px] font-semibold text-white">
          {senior ? '看这些题 →' : '看诊断题 →'}
        </button>

        {!senior && (
          <div className="rounded-lg border border-border">
            <button
              onClick={() => { setOpenQs((v) => !v); loadQs() }}
              className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left">
              <ChevronRight size={11}
                className={`shrink-0 text-ink-faint transition-transform ${openQs ? 'rotate-90' : ''}`} />
              <span className="text-[11.5px] font-semibold text-ink-soft">诊断题</span>
              <span className="tnum text-[10.5px] text-ink-faint">{loc.p.q || 0}</span>
              <span className="ml-auto text-[9.5px] text-ink-faint">点开自测 · 含答案</span>
            </button>
            {openQs && (
              <div className="space-y-1.5 border-t border-border px-2 py-2">
                {qs === null && <div className="text-[11px] text-ink-faint">正在读题…</div>}
                {qs?.length === 0 && (
                  <div className="text-[11px] text-ink-faint">这个点还没有诊断题</div>
                )}
                {(qs || []).map((q, i) => (
                  <details key={i} className="rounded-md border border-border bg-surface-2/50">
                    <summary className="cursor-pointer list-none px-2 py-1.5 text-[11.5px] leading-snug text-ink">
                      <span className="tnum mr-1 text-[9.5px] text-ink-faint">{i + 1}</span>
                      {q.prompt}
                      {q.via === 'chapter' && (
                        <span className="ml-1 rounded bg-muted px-1 text-[9px] text-ink-faint">本章</span>
                      )}
                    </summary>
                    <div className="space-y-1 border-t border-border px-2 py-1.5 text-[11px]">
                      {q.choices?.map(([k, t]) => (
                        <div key={k} className="text-ink-soft">
                          <span className="mr-1 font-medium text-ink-faint">{k}.</span>{t}
                        </div>
                      ))}
                      <div className="font-medium text-ink">答案：{q.answer}</div>
                      {q.explanation && (
                        <div className="leading-relaxed text-ink-faint">{q.explanation}</div>
                      )}
                    </div>
                  </details>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <div className="mb-1 flex items-baseline gap-1.5">
            <ArrowLeft size={12} className="text-ink-faint" />
            <span className="text-[11.5px] font-semibold text-ink-soft">直接先修</span>
            <span className="tnum text-[10.5px] text-ink-faint">{pre.length}</span>
          </div>
          <Rows edges={pre} dir="pre" />
        </div>

        {ancestors.length > 0 && (
          <div>
            <button onClick={() => setOpenChain((v) => !v)}
              className="mb-1 flex w-full items-baseline gap-1.5 text-left">
              <ChevronRight size={12}
                className={`text-ink-faint transition-transform ${openChain ? 'rotate-90' : ''}`} />
              <span className="text-[11.5px] font-semibold text-ink-soft">推荐学习路径</span>
              <span className="tnum text-[10.5px] text-ink-faint">{unknown.length}/{ancestors.length}</span>
              <span className="ml-auto text-[10px] text-ink-faint">勾掉已会 · 从根因补起</span>
            </button>
            {openChain && (
              <>
                <p className="mb-1.5 text-[10.5px] leading-relaxed text-ink-faint">
                  按教材顺序排好了：会了就勾掉，路径会自动缩短；带「根因」的是现在就该补的第一课。
                </p>
                {loc.skey === 'senior' ? (
                  <button onClick={() => onBuildPaper(paperIds)}
                    disabled={building || paperIds.length === 0}
                    className="press mb-2 flex w-full items-center justify-center gap-1.5 rounded-lg border
                               border-brand-line bg-brand-soft px-2 py-1.5 text-[11px] font-medium
                               text-brand-ink disabled:opacity-45">
                    <FilePlus2 size={12} />
                    {building ? '正在按路径挑题…' : `按这条路径组卷（${Math.min(paperIds.length, 12)} 个点）`}
                  </button>
                ) : (
                  <div className="mb-2 rounded-lg border border-dashed border-border px-2 py-1.5
                                  text-[10px] leading-relaxed text-ink-faint">
                    小初题库还在建设，组卷只在高中可用：先按上面的诊断题一课一课补。
                  </div>
                )}
                <div className="space-y-1.5">
                  {groups.map((g) => {
                    const shut = closed.has(g.key)
                    return (
                      <div key={g.key} className="overflow-hidden rounded-lg border border-border">
                        <button
                          onClick={() => setClosed((s) => {
                            const n = new Set(s)
                            if (n.has(g.key)) n.delete(g.key); else n.add(g.key)
                            return n
                          })}
                          className="flex w-full items-center gap-1 bg-surface-2/70 px-2 py-1.5 text-left">
                          <ChevronRight size={10}
                            className={`shrink-0 text-ink-faint transition-transform ${shut ? '' : 'rotate-90'}`} />
                          <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-soft">
                            <b className="font-medium">{g.book}</b> · {g.chapter}
                          </span>
                          <span className="tnum shrink-0 text-[9.5px] text-ink-faint">{g.items.length}</span>
                        </button>
                        {!shut && (
                          <ol className="space-y-1 px-1.5 py-1.5">
                            {g.items.map((id) => {
                              const l = locs.get(id)
                              const p = l?.p
                              const done = known.has(id)
                              const pnq = p?.nq || 0
                              const pq = p?.q || 0
                              return (
                                <li key={id} className="flex items-center gap-1">
                                  <button onClick={() => toggleMastered(id)}
                                    title={done ? '标记为未掌握' : '标记为已掌握'}
                                    className={`grid h-4 w-4 shrink-0 place-items-center rounded border
                                                ${done ? 'border-has bg-has text-white' : 'border-border'}`}>
                                    {done && <span className="text-[9px] leading-none">✓</span>}
                                  </button>
                                  <button onClick={() => onPick(id)}
                                    className={`flex min-w-0 flex-1 items-center gap-1.5 rounded-lg border px-2 py-1.5
                                                text-left ${done
                                                  ? 'border-border/60 bg-muted/40 opacity-55'
                                                  : 'border-border bg-surface hover:border-brand-line'}`}>
                                    <span className={`min-w-0 flex-1 truncate text-[11.5px] ${
                                      done ? 'text-ink-faint line-through' : 'text-ink'}`}>{titleOf(id)}</span>
                                    {roots.has(id) && (
                                      <span className="shrink-0 rounded bg-danger/15 px-1 text-[9px] text-danger">
                                        根因
                                      </span>
                                    )}
                                    {pnq === 0 && pq === 0 && (
                                      <span className="shrink-0 rounded bg-warn-soft px-1 text-[9px] text-warn"
                                        title="没有题，也没有诊断题">缺</span>
                                    )}
                                  </button>
                                  {pnq > 0 && l && (
                                    <button onClick={() => onJump(id, l.skey)}
                                      title={`看这 ${pnq} 道题`}
                                      className="shrink-0 rounded px-1 py-1 text-[9px] text-ink-faint
                                                 hover:bg-muted hover:text-brand-ink">题</button>
                                  )}
                                </li>
                              )
                            })}
                          </ol>
                        )}
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </div>
        )}
        <div>
          <div className="mb-1 text-[11.5px] font-semibold text-ink-soft">
            后续 <span className="tnum text-[10.5px] font-normal text-ink-faint">{post.length}</span>
          </div>
          <Rows edges={post} dir="post" />
        </div>
      </div>
    </aside>
  )
}

export default function MapPage({ stage: stageProp, onPickPoint, onAddPaper, onOpenLecture }: {
  stage: Stage
  onPickPoint: (id: string, stage?: Stage) => void
  /** 按路径组卷：地图页把带解析的题并进当前卷子。 */
  onAddPaper?: (items: Q[]) => void
  /** 知识点卡片 → 对应讲义 */
  onOpenLecture?: (topicId: string) => void
}) {
  const [d, setD] = useState<MData | null>(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [viewMode, setViewMode] = useState<'mind' | 'panorama' | 'focus' | 'cards'>('mind')
  const [sel, setSel] = useState<string | null>(null)
  const [upDepth, setUpDepth] = useState(2)
  const [downDepth, setDownDepth] = useState(1)
  const [openBooks, setOpenBooks] = useState<Set<string>>(new Set())
  const [openChapters, setOpenChapters] = useState<Set<string>>(new Set())
  const [gapOnly, setGapOnly] = useState(false)
  const [building, setBuilding] = useState(false)
  const [cardSel, setCardSel] = useState<Set<string>>(new Set())
  const [topicByPoint, setTopicByPoint] = useState<Map<string, string>>(new Map())
  const [dragging, setDragging] = useState('')

  const load = () => {
    setErr('')
    api.map()
      .then((x: MData) => setD(x))
      .catch((e) => { setErr(String((e as Error)?.message || e)); reportErr(e) })
  }
  useEffect(load, [])

  // 知识点 → 讲义 id；卡片上的「讲义」入口用。只读 manifest，不生成讲义。
  useEffect(() => {
    let alive = true
    api.topics(stageProp)
      .then((d: { topics: { id: string; points?: string[] }[] }) => {
        if (!alive) return
        const m = new Map<string, string>()
        for (const t of d.topics || []) {
          for (const p of t.points || []) m.set(p, t.id)
          if (!t.points?.length) m.set(t.id, t.id)
        }
        setTopicByPoint(m)
      })
      .catch(() => { if (alive) setTopicByPoint(new Map()) })
    return () => { alive = false }
  }, [stageProp])

  const stage = d?.stages.find((s) => s.key === stageProp) || d?.stages[0]

  // 切学段：回到这个学段的第一个册/章，别把上一学段的选中项留着。
  useEffect(() => {
    if (!d) return
    setSel(null)
    setCardSel(new Set())
    const first = d.stages.find((s) => s.key === stageProp)?.books[0]
    setOpenBooks(first ? new Set([first.name]) : new Set())
    setOpenChapters(new Set())
  }, [stageProp, d])

  const loc = useMemo(() => {
    const m = new Map<string, Loc>()
    let n = 0
    for (const s of d?.stages || []) {
      for (const b of s.books) {
        for (const c of b.chapters) {
          for (const p of c.points) {
            m.set(p.id, {
              stage: s.name, skey: s.key, book: b.name, grade: b.grade,
              chapter: c.title, order: n++, name: disp(p.title), p,
            })
          }
        }
      }
    }
    return m
  }, [d])

  const { preOf, postOf } = useMemo(() => {
    const pre = new Map<string, MEdge[]>()
    const post = new Map<string, MEdge[]>()
    for (const e of d?.edges || []) {
      post.set(e.from, [...(post.get(e.from) || []), e])
      pre.set(e.to, [...(pre.get(e.to) || []), e])
    }
    const rank = (e: MEdge) => (e.strength === 'hard' ? 0 : e.kind === 'order' ? 2 : 1)
    for (const arr of [pre, post]) for (const v of arr.values()) v.sort((a, b) => rank(a) - rank(b))
    return { preOf: pre, postOf: post }
  }, [d])

  /** 当前学段的枢纽知识点：没有选中时拿它当中心。 */
  const hub = useMemo(() => {
    let best = '', bs = -1
    for (const [id, l] of loc) {
      if (l.skey !== stage?.key) continue
      const deg = (preOf.get(id)?.length || 0) + (postOf.get(id)?.length || 0)
      if (deg > bs) { bs = deg; best = id }
    }
    return best
  }, [loc, stage, preOf, postOf])

  const center = sel || hub
  const selected = sel ? loc.get(sel) : undefined

  /** 导图只画当前学段；每个点带上册/章，作为分组依据。 */
  const mapNodes = useMemo(() => {
    if (!stage) return []
    const out: {
      id: string; title: string; book: string; chapter: string; order: number
      tone: Tone; q: number; nq: number
    }[] = []
    for (const b of stage.books) {
      for (const c of b.chapters) {
        for (const p of c.points) {
          const l = loc.get(p.id)
          if (!l) continue
          out.push({ id: p.id, title: disp(p.title), book: b.name, chapter: c.title,
                     order: l.order, tone: TONE_OF_STAGE[l.skey],
                     q: p.q || 0, nq: p.nq || 0 })
        }
      }
    }
    return out
  }, [stage, loc])

  /** 缺口：既没有题、也没有诊断题——「待建」视图就靠它。 */
  const gapCount = useMemo(
    () => mapNodes.filter((n) => !(n.nq || 0) && !(n.q || 0)).length,
    [mapNodes],
  )

  /** 卡片检索：知识点标题/章节/册名/备注都能搜；缺口筛选复用。 */
  const cards = useMemo(() => {
    const key = q.trim().toLowerCase()
    return mapNodes
      .filter((n) => (!gapOnly || (!(n.nq || 0) && !(n.q || 0))))
      .filter((n) => {
        if (!key) return true
        const l = loc.get(n.id)
        return [n.title, n.book, n.chapter, l?.p.note || '']
          .some((x) => String(x || '').toLowerCase().includes(key))
      })
      .map((n) => ({ ...n, l: loc.get(n.id) }))
  }, [mapNodes, q, gapOnly, loc])

  /** 按路径组卷：每个未掌握的点挑 1–2 道**带解析**的题，并进当前卷子。 */
  const buildPaper = async (ids: string[]) => {
    if (!onAddPaper) return
    const targets = ids.slice(0, 12)
    setBuilding(true)
    try {
      const res = await Promise.all(targets.map((id) =>
        api.list({ point: id, limit: '2', sort: 'used' }).catch(() => null)))
      const seen = new Set<string>()
      const items: Q[] = []
      for (const r of res) {
        for (const it of ((r as any)?.items || [])) {
          if (seen.has(it.key) || !it.flags?.['解析']) continue
          seen.add(it.key)
          items.push(it)
        }
      }
      if (!items.length) { toast('这条路径上还没有带解析的题'); return }
      onAddPaper(items)
    } catch (e) {
      reportErr(e)
    } finally {
      setBuilding(false)
    }
  }


  // 第一次拿到数据 / 切学段后，把枢纽点选中——右边详情一开始就有内容。
  useEffect(() => {
    if (hub) setSel((cur) => cur || hub)
  }, [hub])

  /** 完整先修链：全部祖先，按教材顺序排——就是「先补什么」的推荐顺序。 */
  const ancestors = useMemo(() => {
    if (!center) return []
    const seen = new Set<string>()
    let frontier = [center]
    while (frontier.length) {
      const next: string[] = []
      for (const id of frontier) {
        for (const e of preOf.get(id) || []) {
          if (!seen.has(e.from) && e.from !== center) { seen.add(e.from); next.push(e.from) }
        }
      }
      frontier = next
    }
    return [...seen].sort((a, b) => (loc.get(a)?.order || 0) - (loc.get(b)?.order || 0))
  }, [center, preOf, loc])

  /** 选中点变化时，把它的册和章展开，别让目录里找不到人。 */
  useEffect(() => {
    if (!sel) return
    const l = loc.get(sel)
    if (!l) return
    setOpenBooks((s) => new Set([...s, l.book]))
    setOpenChapters((s) => new Set([...s, `${l.book}::${l.chapter}`]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel])

  const hits = useMemo(() => {
    const key = q.trim().toLowerCase()
    if (!key) return []
    return [...loc.values()].filter((l) =>
      l.skey === stage?.key
      && (l.name.toLowerCase().includes(key) || l.p.note.toLowerCase().includes(key)
          || l.chapter.toLowerCase().includes(key)))
  }, [q, loc])

  const toggle = (set: Set<string>, v: string, fn: (s: Set<string>) => void) => {
    const n = new Set(set)
    if (n.has(v)) n.delete(v); else n.add(v)
    fn(n)
  }

  if (!d) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center text-[13px] text-ink-faint">
        {err ? (
          <div className="text-center">
            <div className="mb-2 text-warn">{err}</div>
            <button onClick={load} className="press rounded-lg border border-border px-3 py-1.5">
              重试
            </button>
          </div>
        ) : '正在读知识地图…'}
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
      {/* ── 学段上下文条：标题在顶栏，这里只放教材口径 ── */}
      <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b
                         border-border bg-surface px-4 py-2">
        <span className="inline-flex items-center gap-1.5 text-[11.5px] text-ink-soft">
          <i className="h-2 w-2 rounded-full" style={{ background: DOT[TONE_OF_STAGE[stage?.key || 'senior']] }} />
          <b className="font-semibold">{stage?.name}</b>
          <span className="tnum text-ink-faint">{stage?.n} 个知识点</span>
        </span>
        <span className="text-[10.5px] text-ink-faint">{d.edition}</span>
        <span className="hidden text-[10.5px] text-ink-faint md:inline">
          全库 {d.total} 点 · {d.stats.edges} 条前后关系（可跨学段追根）
        </span>
        <button onClick={load} title="重新读取" className="icon-btn ml-auto h-7 w-7 text-ink-faint">
          <RefreshCw size={14} />
        </button>
      </header>

      <div className="flex min-h-0 min-w-0 flex-1 gap-3 p-3 max-lg:flex-col max-lg:overflow-y-auto">
        {/* ── 左：目录 ── */}
        <aside className="flex w-[264px] shrink-0 flex-col overflow-hidden rounded-[var(--radius-card)]
                          max-lg:h-[260px] max-lg:w-full
                          border border-border bg-surface shadow-[var(--shadow-card)]">
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜索名称、章节"
                className="w-full rounded-lg border border-border bg-surface-2 py-1.5 pl-7 pr-2
                           text-[12px] text-ink outline-none placeholder:text-ink-faint focus:border-brand-line"
              />
            </div>
            <div className="mt-2 flex items-center gap-1.5 px-0.5 text-[10.5px] text-ink-faint">
              <i className="h-1.5 w-1.5 rounded-full"
                style={{ background: DOT[TONE_OF_STAGE[stage?.key || 'senior']] }} />
              <span className="font-medium text-ink-soft">{stage?.name}</span>
              <span className="tnum">· {stage?.books.length} 册 · {stage?.n} 点</span>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-1.5">
            {q.trim() ? (
              <>
                <div className="px-1.5 pb-1 text-[10.5px] text-ink-faint">命中 {hits.length} 个</div>
                {hits.slice(0, 120).map((l) => (
                  <button key={l.p.id} onClick={() => setSel(l.p.id)}
                    className={`flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left
                                hover:bg-muted ${sel === l.p.id ? 'bg-brand-soft' : ''}`}>
                    <i className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ background: DOT[TONE_OF_STAGE[l.skey]] }} />
                    <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink">{l.name}</span>
                    <span className="shrink-0 text-[9.5px] text-ink-faint">{l.book}</span>
                  </button>
                ))}
              </>
            ) : (
              (stage?.books || []).map((b) => {
                const open = openBooks.has(b.name)
                return (
                  <div key={b.name} className="mb-0.5">
                    <button onClick={() => toggle(openBooks, b.name, setOpenBooks)}
                      className="flex w-full items-center gap-1.5 rounded-md px-1.5 py-1 text-left
                                 hover:bg-muted">
                      <ChevronRight size={11}
                        className={`shrink-0 text-ink-faint transition-transform ${open ? 'rotate-90' : ''}`} />
                      <BookOpen size={12} className="shrink-0 text-ink-faint" />
                      <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-ink">
                        {b.name}
                      </span>
                      <span className="tnum shrink-0 text-[9.5px] text-ink-faint">{b.n}</span>
                    </button>
                    {open && (
                      <div className="ml-2 border-l border-border pl-1">
                        {b.chapters.map((c) => {
                          const ck = `${b.name}::${c.title}`
                          const copen = openChapters.has(ck)
                          return (
                            <div key={ck}>
                              <button onClick={() => toggle(openChapters, ck, setOpenChapters)}
                                className="flex w-full items-center gap-1 rounded-md px-1 py-[3px] text-left
                                           hover:bg-muted">
                                <ChevronRight size={10}
                                  className={`shrink-0 text-ink-faint transition-transform ${copen ? 'rotate-90' : ''}`} />
                                <span className="min-w-0 flex-1 truncate text-[10.5px] text-ink-soft">
                                  {c.title}
                                </span>
                                <span className="tnum shrink-0 text-[9px] text-ink-faint">{c.n}</span>
                              </button>
                              {copen && c.points.map((p) => (
                                <button key={p.id} onClick={() => setSel(p.id)}
                                  className={`ml-3 flex w-[calc(100%-12px)] items-center rounded-md px-1.5 py-[3px]
                                              text-left hover:bg-muted ${sel === p.id ? 'bg-brand-soft' : ''}`}>
                                  <span className={`min-w-0 flex-1 truncate text-[10.5px] ${
                                    sel === p.id ? 'font-medium text-brand-ink' : 'text-ink-soft'}`}>
                                    {disp(p.title)}
                                  </span>
                                </button>
                              ))}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </aside>

        {/* ── 中：图谱 ── */}
        <section className="flex min-w-0 flex-1 flex-col gap-2 max-lg:min-h-[420px] max-lg:w-full">
          <div className="flex flex-wrap items-center gap-1.5">
            {viewMode === 'focus' && (
              <>
                <span className="text-[11px] text-ink-faint">向上</span>
                {[1, 2, 3, 0].map((dep) => (
                  <button key={dep} data-on={upDepth === (dep || Infinity) ? '1' : '0'}
                    onClick={() => setUpDepth(dep || Infinity)}
                    className="press rounded-md border border-border px-2 py-0.5 text-[10.5px]
                               text-ink-faint hover:border-brand-line data-[on=1]:border-brand-line
                               data-[on=1]:bg-brand-soft data-[on=1]:text-brand-ink">
                    {dep ? `${dep} 层` : '全部'}
                  </button>
                ))}
                <span className="ml-2 text-[11px] text-ink-faint">向下</span>
                {[1, 2].map((dep) => (
                  <button key={dep} data-on={downDepth === dep ? '1' : '0'}
                    onClick={() => setDownDepth(dep)}
                    className="press rounded-md border border-border px-2 py-0.5 text-[10.5px]
                               text-ink-faint hover:border-brand-line data-[on=1]:border-brand-line
                               data-[on=1]:bg-brand-soft data-[on=1]:text-brand-ink">
                    {dep} 层
                  </button>
                ))}
              </>
            )}
            <button onClick={() => setGapOnly((v) => !v)}
              disabled={gapCount === 0}
              title={gapCount === 0
                ? '这个学段每个点都有题或诊断题——没有待建缺口'
                : '只亮出既没有题、也没有诊断题的知识点'}
              className={`ml-auto rounded-full border px-2.5 py-[3px] text-[10px] font-medium transition-colors ${
                gapCount === 0 ? 'cursor-default border-border text-ink-faint/45'
                  : gapOnly ? 'border-warn-line bg-warn-soft text-warn'
                  : 'border-border text-ink-faint hover:border-brand-line hover:text-ink'}`}>
              只看缺口 <span className="tnum">{gapCount}</span>
            </button>
            <div className="flex items-center gap-1 rounded-full border border-border/80
                            bg-white/[.03] p-0.5">
              {([['mind', '导图'], ['panorama', '全景'], ['focus', '先修图'], ['cards', '卡片']] as const).map(([v, label]) => (
                <button key={v} onClick={() => setViewMode(v)}
                  className={`rounded-full px-2.5 py-[3px] text-[10px] font-medium transition-all ${
                    viewMode === v ? 'grad-primary text-white shadow-[var(--glow-cyan)]'
                                   : 'text-ink-faint hover:text-ink'}`}>
                  {label}
                </button>
              ))}
            </div>
            <span className="text-[10.5px] text-ink-faint">
              {viewMode === 'mind' ? '点册/章展开 · 悬停看线束 · 点知识点看详情'
                : viewMode === 'panorama' ? '悬停章看线束 · 点册聚焦 · 点知识点看详情'
                : viewMode === 'focus' ? '点节点换中心 · 滚轮横向滚动'
                : '搜索/筛选知识点 · 勾选后一键组卷'}
            </span>
          </div>

          {viewMode === 'cards' ? (
            <div className="flex min-h-0 flex-1 flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="tnum text-[11px] text-ink-faint">{cards.length} 个知识点</span>
                {cards.length > 0 && (<>
                  <button onClick={() => setCardSel(new Set(cards.map((n) => n.id)))}
                    className="press rounded-md border border-border bg-surface px-2 py-[3px]
                               text-[10.5px] text-ink-soft hover:border-border-strong">全选当前</button>
                  {cardSel.size > 0 && (
                    <button onClick={() => setCardSel(new Set())}
                      className="press rounded-md border border-border bg-surface px-2 py-[3px]
                                 text-[10.5px] text-ink-faint hover:text-ink">清空</button>
                  )}
                </>)}
                <span className="min-w-0 flex-1" />
                {cardSel.size > 0 && onAddPaper && (
                  <button onClick={() => buildPaper([...cardSel])} disabled={building}
                    className="press rounded-lg bg-brand px-3 py-[4px] text-[11px] font-medium text-white
                               shadow-[var(--shadow-brand)] disabled:opacity-45">
                    {building ? '正在挑题…' : `组卷 · ${cardSel.size} 个知识点`}
                  </button>
                )}
              </div>
              <div className="b-scroll min-h-0 flex-1 overflow-y-auto pr-0.5">
                {cards.length === 0 ? (
                  <div className="flex h-40 items-center justify-center text-[12px] text-ink-faint">
                    没有匹配的知识点
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                    {cards.map((n) => {
                      const on = sel === n.id
                      const checked = cardSel.has(n.id)
                      const gap = !(n.nq || 0) && !(n.q || 0)
                      return (
                        <article key={n.id} onClick={() => setSel(n.id)}
                          draggable
                          onDragStart={(e) => {
                            e.dataTransfer.setData('text/amtiku-point', n.id)
                            e.dataTransfer.effectAllowed = 'copy'
                            setDragging(n.id)
                          }}
                          onDragEnd={() => setDragging('')}
                          className={`group cursor-pointer rounded-[16px] border bg-surface p-3
                                      ${dragging === n.id ? 'opacity-55' : ''}
                                      transition-[border-color,box-shadow,transform] duration-200
                                      hover:-translate-y-0.5 hover:shadow-[var(--shadow-hover)]
                                      ${on ? 'border-brand-line shadow-[0_0_0_3px_color-mix(in_srgb,var(--color-brand)_9%,transparent)]'
                                           : 'border-border shadow-[var(--shadow-card)]'}`}>
                          <div className="flex items-start gap-1.5">
                            <button type="button" onClick={(e) => { e.stopPropagation(); setCardSel((s) => { const x = new Set(s); x.has(n.id) ? x.delete(n.id) : x.add(n.id); return x }) }}
                              aria-label="勾选知识点" aria-pressed={checked}
                              className="-ml-0.5 mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md
                                         border border-border bg-surface hover:border-brand-line">
                              {checked && <span className="h-2.5 w-2.5 rounded-[3px] bg-brand" />}
                            </button>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-1.5">
                                <span className="truncate text-[12.5px] font-semibold text-ink">{n.title}</span>
                                {gap && <span className="shrink-0 rounded bg-warn-soft px-1 py-[1px] text-[9px] text-warn">待建</span>}
                              </div>
                              <div className="mt-0.5 truncate text-[10px] text-ink-faint">{n.book} · {n.chapter}</div>
                            </div>
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-faint">
                            <span className="tnum rounded bg-muted px-1.5 py-[1px]">{n.nq || 0} 题</span>
                            {(n.q || 0) > 0 && <span className="tnum rounded bg-muted px-1.5 py-[1px]">诊断 {n.q}</span>}
                            {n.l?.p.difficulty && (
                              <span className="tnum">{n.l.p.difficulty} · {'★'.repeat(n.l.p.stars || 0)}</span>
                            )}
                          </div>
                          <div className="mt-2 flex items-center gap-1.5 border-t border-border/70 pt-2">
                            <button type="button" onClick={(e) => { e.stopPropagation(); onPickPoint(n.id, n.l?.skey) }}
                              className="press rounded-md bg-brand px-2 py-[3px] text-[10px] font-medium text-white">
                              看题
                            </button>
                            {onAddPaper && (
                              <button type="button" onClick={(e) => { e.stopPropagation(); buildPaper([n.id]) }}
                                disabled={building}
                                className="press rounded-md border border-border bg-surface px-2 py-[3px]
                                           text-[10px] text-ink-soft hover:border-brand-line hover:text-brand-ink disabled:opacity-45">
                                组卷
                              </button>
                            )}
                            {onOpenLecture && topicByPoint.get(n.id) && (
                              <button type="button" onClick={(e) => { e.stopPropagation(); onOpenLecture(topicByPoint.get(n.id)!) }}
                                className="press rounded-md border border-border bg-surface px-2 py-[3px]
                                           text-[10px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
                                讲义
                              </button>
                            )}
                            <span className="ml-auto text-[9.5px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100">
                              详情 →
                            </span>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                )}
              </div>
              {cardSel.size > 0 && (
                <div
                  onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
                  onDrop={(e) => {
                    e.preventDefault()
                    const id = e.dataTransfer.getData('text/amtiku-point')
                    if (id) setCardSel((s) => new Set(s).add(id))
                    setDragging('')
                  }}
                  className="sticky bottom-1 z-20 flex items-center gap-2 rounded-xl border border-brand-line
                             bg-surface/95 px-3 py-2 shadow-[var(--shadow-pop)] backdrop-blur">
                  <span className="tnum text-[11px] text-ink-soft">已选 {cardSel.size} 个知识点</span>
                  <span className="text-[10px] text-ink-faint max-sm:hidden">拖卡片到这里也可加入</span>
                  <span className="min-w-0 flex-1" />
                  <button onClick={() => setCardSel(new Set())}
                    className="press rounded-md border border-border bg-surface px-2 py-[3px] text-[10.5px] text-ink-faint">
                    清空
                  </button>
                  {onAddPaper && (
                    <button onClick={() => buildPaper([...cardSel])} disabled={building}
                      className="press rounded-md bg-brand px-3 py-[4px] text-[10.5px] font-medium text-white disabled:opacity-45">
                      {building ? '正在挑题…' : '按知识点组卷'}
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : viewMode === 'mind' && mapNodes.length > 0 ? (
            <MindMapView nodes={mapNodes} edges={d.edges}
              sel={sel || hub} onSelect={setSel} gapOnly={gapOnly}
              centerLabel={stage?.name || ''} centerCount={stage?.n || 0} />
          ) : viewMode === 'panorama' && mapNodes.length > 0 ? (
            <PanoramaView nodes={mapNodes} edges={d.edges}
              sel={sel || hub} onSelect={setSel} gapOnly={gapOnly}
              centerLabel={stage?.name || ''} centerCount={stage?.n || 0} />
          ) : center ? (
            <GraphView sel={center} titleOf={(id) => loc.get(id)?.name || id}
              orderOf={(id) => loc.get(id)?.order || 0}
              toneOf={(id) => TONE_OF_STAGE[loc.get(id)?.skey || 'senior']}
              preOf={preOf} postOf={postOf} allEdges={d.edges}
              upDepth={upDepth} downDepth={downDepth} gapOnly={gapOnly}
              isGap={(id) => {
                const p = loc.get(id)?.p
                return !(p?.nq || 0) && !(p?.q || 0)
              }}
              onSelect={setSel} onReset={() => setSel(null)} />
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-[var(--radius-card)]
                            border border-dashed border-border text-[12.5px] text-ink-faint">
              这一学段还没有知识点
            </div>
          )}
        </section>

        {/* ── 右：详情 ── */}
        {selected && (
          <Detail
            loc={selected}
            pre={preOf.get(selected.p.id) || []}
            post={postOf.get(selected.p.id) || []}
            ancestors={ancestors}
            prereqsOf={(id) => (preOf.get(id) || []).map((e) => e.from)}
            locs={loc}
            onBuildPaper={buildPaper}
            building={building}
            onPick={setSel}
            onClose={() => setSel(null)}
            onJump={onPickPoint}
            titleOf={(id) => loc.get(id)?.name || id}
          />
        )}
      </div>
    </div>
  )
}
