/** 知识图谱 · 教材导图（替掉原来的"星座/太阳系"）
 *
 *  为什么换：星图把 165 个点撒成一圈，位置不表达教材顺序，线与点一样密，
 *  读不出"先学什么、后学什么"（`设计/知识链路.md` 对旧版星空有完整复盘）。
 *  这里改成**左→右的教材树**：
 *
 *      学段 —— 七年级上册 —— 第一章 有理数 ……
 *           ╲                 第二章 有理数的运算
 *            ╲— 七年级下册 —— ……
 *
 *  先修关系不画成点与点之间的乱线，而是**沿层级骨架捆成线束**：同一册的关系
 *  共用一条竖干，跨册的收到学段主干上。这正好是旧星空唯一留下来的一条经验：
 *  "边要沿层级骨架捆扎，不要穿圆心"。
 *
 *  三条取舍：
 *  1. **默认只展开册和章**（34 章一屏刚好），点章才长出知识点——不然 165 个点
 *     会把图撑成一页文档，而"一屏读完"正是这个页面存在的理由。
 *  2. **线束画在卡片底下**：从卡片中心起笔，被卡片自身盖住，视觉上就是"插到
 *     卡片背后"，不用算端口，也不会留半截线头。
 *  3. **没有常驻动画**：只保留 hover/选中时的一次性透明度过渡。
 *
 *  横向是流式的：容器越宽，册/章/知识点三列越舒展（节点本身不变形，只拉开间距），
 *  纵向按高度适配——这样 1440 和 1778 两种窗口都不会把图缩成邮票。
 *
 *  交互：点册展开/收起章节、点章展开/收起知识点、点知识点选中（右侧详情）。
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minus, Plus } from 'lucide-react'
import type { Tone } from '@/app/GraphView'
import { useMastery } from '@/lib/mastery'

export type MindNode = {
  id: string
  title: string
  book: string
  chapter: string
  order: number
  tone: Tone
  q?: number      // 诊断题
  nq?: number     // 题库题量
}
export type MindEdge = {
  from: string
  to: string
  strength: string
  kind: string
}

type Kind = 'hard' | 'soft' | 'order'
const kindOf = (e: MindEdge): Kind =>
  (e.strength === 'hard' ? 'hard' : e.kind === 'order' ? 'order' : 'soft')

const BOOK_H = 32
const CH_H = 15
const CH_PITCH = 17
const PT_H = 15
const PT_PITCH = 17
const BOOK_GAP = 8
const PAD = 12

const TONE: Record<Tone, { bg: string; border: string }> = {
  p: { bg: 'rgba(15,118,110,.10)', border: '#0f766e' },
  j: { bg: 'rgba(29,78,216,.09)', border: '#1d4ed8' },
  h: { bg: 'rgba(109,40,217,.09)', border: '#6d28d9' },
}

/** 线束：硬先修=品牌蓝，有帮助=紫，教材顺序=灰虚线。 */
const CABLE: Record<Kind, { stroke: string; opacity: number; dash?: string }> = {
  hard: { stroke: 'var(--color-brand)', opacity: 0.3 },
  soft: { stroke: 'var(--color-violet)', opacity: 0.26 },
  order: { stroke: 'var(--color-ink-faint)', opacity: 0.16, dash: '2 4' },
}

const chKey = (book: string, chapter: string) => `${book}\u0000${chapter}`

/** 题量角标：上千就折成 2.7k，别让四位数字把章行撑爆。 */
const fmtN = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`)

/** 册签只放得下 6 个字。高中「选择性必修第一册」缩成「选必一」是通行叫法，
 *  完整名称留在 title 提示里，左侧目录也照旧。 */
const shortBook = (n: string) => (n.includes('必修')
  ? n.replace('选择性必修第', '选必').replace('必修第', '必修').replace(/册$/, '')
  : n)

/** 中文按 1em、西文按 0.56em 估宽：截断和"贴字宽度"都靠它，够用且便宜。 */
const CJK = /[\u2e80-\u9fff\uff00-\uffef]/
function textW(s: string, fontSize: number) {
  let w = 0
  for (const ch of s) w += CJK.test(ch) ? fontSize : fontSize * 0.56
  return w
}
function clip(s: string, px: number, fontSize: number) {
  let w = 0
  for (let i = 0; i < s.length; i++) {
    const cw = CJK.test(s[i]) ? fontSize : fontSize * 0.56
    if (w + cw > px) return `${s.slice(0, Math.max(1, i - 1))}…`
    w += cw
  }
  return s
}

/** 正交折线 + 圆角：线束用它，横向走线 + 圆角转弯像线槽。 */
function elbow(pts: [number, number][], r = 8) {
  if (pts.length < 2) return ''
  let d = `M ${pts[0][0]} ${pts[0][1]}`
  for (let i = 1; i < pts.length; i++) {
    const [x, y] = pts[i]
    const next = pts[i + 1]
    if (!next) { d += ` L ${x} ${y}`; continue }
    const [px, py] = pts[i - 1]
    const v1x = x - px, v1y = y - py
    const v2x = next[0] - x, v2y = next[1] - y
    const l1 = Math.hypot(v1x, v1y) || 1
    const l2 = Math.hypot(v2x, v2y) || 1
    const rr = Math.min(r, l1 / 2, l2 / 2)
    if (Math.abs(v1x * v2y - v1y * v2x) < 0.01) { d += ` L ${x} ${y}`; continue }
    d += ` L ${x - (v1x / l1) * rr} ${y - (v1y / l1) * rr}`
      + ` Q ${x} ${y} ${x + (v2x / l2) * rr} ${y + (v2y / l2) * rr}`
  }
  return d
}

/** 思维导图的枝条：起笔横着出去、收笔横着进来，中间自然弯。 */
function branch(x1: number, y1: number, x2: number, y2: number) {
  const dx = Math.max(16, (x2 - x1) * 0.6)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

export default function MindMapView({
  nodes, edges, sel, onSelect, centerLabel, centerCount, gapOnly = false,
}: {
  nodes: MindNode[]
  edges: MindEdge[]
  sel: string | null
  onSelect: (id: string) => void
  centerLabel: string
  centerCount: number
  /** 只看缺口（地图页的「待建」视图）。 */
  gapOnly?: boolean
}) {
  const known = useMastery()
  const [zoom, setZoom] = useState(1)
  const [box, setBox] = useState({ w: 0, h: 0 })
  const [hoverCh, setHoverCh] = useState<string | null>(null)
  const [hoverPt, setHoverPt] = useState<string | null>(null)
  const [hoverBook, setHoverBook] = useState<string | null>(null)
  const [bookPref, setBookPref] = useState<{ stage: string; v: Set<string> } | null>(null)
  const [chapPref, setChapPref] = useState<{ stage: string; v: Set<string> } | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  /** 教材树：册 → 章 → 知识点，顺序就是 `order`（教材顺序）。 */
  const model = useMemo(() => {
    const ordered = [...nodes].sort((a, b) => a.order - b.order)
    const byId = new Map(ordered.map((n) => [n.id, n]))
    const books: { name: string; chapters: { key: string; title: string; points: MindNode[] }[] }[] = []
    const index = new Map<string, (typeof books)[number]>()
    for (const n of ordered) {
      let b = index.get(n.book)
      if (!b) {
        b = { name: n.book, chapters: [] }
        index.set(n.book, b)
        books.push(b)
      }
      let c = b.chapters.find((x) => x.title === n.chapter)
      if (!c) {
        c = { key: chKey(n.book, n.chapter), title: n.chapter, points: [] }
        b.chapters.push(c)
      }
      c.points.push(n)
    }
    return { books, byId }
  }, [nodes])

  const tone = TONE[nodes[0]?.tone || 'j']
  const selNode = sel ? model.byId.get(sel) : undefined
  const selCh = selNode ? chKey(selNode.book, selNode.chapter) : null

  /** 展开状态：默认值直接算出来（不放进 effect），首帧就能按最终高度适配画面。 */
  const stage = centerLabel
  const defaultBooks = useMemo(() => {
    const names = model.books.map((b) => b.name)
    if (names.length <= 6) return new Set(names)
    // 小学有 12 册：默认只展开选中点所在那册（没有选中就第一册）。
    // 必须算在首帧里——放到 effect 里展开，首帧会按"只有一册"的矮版本适配，
    // 等展开完就溢出了。
    return new Set([selNode?.book || names[0]])
  }, [model, selNode?.book])
  const openBooks = useMemo(
    () => (bookPref?.stage === stage ? bookPref.v : defaultBooks),
    [bookPref, stage, defaultBooks],
  )
  const defaultChapters = useMemo(() => new Set(selCh ? [selCh] : []), [selCh])
  const openChapters = useMemo(
    () => (chapPref?.stage === stage ? chapPref.v : defaultChapters),
    [chapPref, stage, defaultChapters],
  )

  /** 从目录/右侧/别处点进来一个知识点：只在那一下把它所在的册和章展开。
   *  展开是"跟随选中"，用户之后仍可以手动收起——不然那个章节就永远关不掉。 */
  const openedFor = useRef('')
  useEffect(() => {
    if (!selNode || !selCh) return
    const key = `${selNode.id}`
    if (openedFor.current === key) return
    openedFor.current = key
    setBookPref((prev) => {
      const base = prev?.stage === stage ? prev.v : defaultBooks
      return base.has(selNode.book) ? prev : { stage, v: new Set([...base, selNode.book]) }
    })
    setChapPref((prev) => {
      const base = prev?.stage === stage ? prev.v : new Set<string>()
      return base.has(selCh) ? prev : { stage, v: new Set([...base, selCh]) }
    })
  }, [selNode, selCh, stage, defaultBooks])

  /** 横向流式版心：容器越宽，列越舒展；节点本身不缩放。 */
  const contentW = box.w ? Math.max(540, Math.min(700, Math.round(box.w - 16))) : 640
  const L = useMemo(() => {
    const extra = Math.max(0, contentW - 600)
    const rootX = 14, rootW = 64
    const bookX = 104 + extra * 0.12
    const bookW = 100 + extra * 0.03
    const chapterX = 232 + extra * 0.3
    const chapterW = 168 + extra * 0.22
    const ptX = chapterX + chapterW + 16
    const ptW = Math.max(140, contentW - ptX - 10)
    return {
      W: contentW, rootX, rootW, bookX, bookW, chapterX, chapterW, ptX, ptW,
      crossX: 92, bookLaneX: chapterX - 18, ptSpineX: ptX - 8,
    }
  }, [contentW])

  const layout = useMemo(() => {
    const chPos = new Map<string, { y: number; book: string; right: number; label: string }>()
    const ptPos = new Map<string, number>()
    const bookPos = new Map<string, { y: number }>()
    let y = PAD
    for (const b of model.books) {
      const top = y
      if (openBooks.has(b.name)) {
        for (const c of b.chapters) {
          const open = openChapters.has(c.key)
          const slot = open ? Math.max(CH_PITCH, c.points.length * PT_PITCH) : CH_PITCH
          const cy = y + slot / 2
          const label = clip(c.title, L.chapterW - 24, 11)
          const right = L.chapterX - 7 + Math.min(
            L.chapterW,
            textW(label, 11) + textW(String(c.points.length), 9) + 22,
          )
          chPos.set(c.key, { y: cy, book: b.name, right, label })
          if (open) {
            c.points.forEach((p, i) => {
              ptPos.set(p.id, cy + (i - (c.points.length - 1) / 2) * PT_PITCH)
            })
          }
          y += slot
        }
      } else {
        y += BOOK_H
      }
      const h = Math.max(y - top, BOOK_H)
      bookPos.set(b.name, { y: top + h / 2 })
      y = top + h + BOOK_GAP
    }
    const height = Math.max(y - BOOK_GAP + PAD, 160)
    return { chPos, ptPos, bookPos, height, rootY: height / 2 }
  }, [model, openBooks, openChapters, L])

  /** 章级线束：一对章节之间所有边收成一条，粗细看条数，颜色看最强的那种关系。 */
  const cables = useMemo(() => {
    const agg = new Map<string, {
      a: string; b: string; n: number; hard: number; soft: number; order: number
    }>()
    for (const e of edges) {
      const A = model.byId.get(e.from)
      const B = model.byId.get(e.to)
      if (!A || !B) continue
      const ka = chKey(A.book, A.chapter)
      const kb = chKey(B.book, B.chapter)
      if (ka === kb || !layout.chPos.has(ka) || !layout.chPos.has(kb)) continue
      const [x, z] = ka < kb ? [ka, kb] : [kb, ka]
      // 跨册的线不在默认视图里画：几十条长横线会像尺子一样划穿整张图；
      // 选中知识点时再沿"册签 → 主干"把它的跨册链路画出来。
      if (layout.chPos.get(x)!.book !== layout.chPos.get(z)!.book) continue
      let a = agg.get(`${x}|${z}`)
      if (!a) {
        a = { a: x, b: z, n: 0, hard: 0, soft: 0, order: 0 }
        agg.set(`${x}|${z}`, a)
      }
      a.n++
      a[kindOf(e)]++
    }
    return [...agg.values()].sort((p, q) => q.n - p.n)
  }, [edges, model, layout])

  /** 章与章之间怎么走线（从 a 的左端起笔，接到 b 的左端，路径以 L/C 续写）：
   *  同册走章列旁的短竖干；跨册沿枝条退到册签、走学段主干、再从另一册下来——
   *  这样几十条关系会并成册脊/主干上的线束，而不是横穿整张图的长横线。 */
  const cableFrom = (a: { y: number; book: string }, b: { y: number; book: string }) => {
    if (a.book === b.book) {
      return ` L ${L.bookLaneX} ${a.y} L ${L.bookLaneX} ${b.y} L ${L.chapterX} ${b.y}`
    }
    const pA = layout.bookPos.get(a.book)?.y ?? a.y
    const pB = layout.bookPos.get(b.book)?.y ?? b.y
    const pr = L.bookX + L.bookW
    const dx = Math.max(16, (L.chapterX - pr) * 0.6)
    return ` C ${L.chapterX - dx} ${a.y}, ${pr + dx} ${pA}, ${pr} ${pA}`
      + ` L ${L.crossX} ${pA} L ${L.crossX} ${pB} L ${pr} ${pB}`
      + ` C ${pr + dx} ${pB}, ${L.chapterX - dx} ${b.y}, ${L.chapterX} ${b.y}`
  }

  /** 悬停一章：把这一章进出的边一条条亮出来（含跨册），就是"线束"该有的样子。 */
  const hoverLinks = useMemo(() => {
    if (!hoverCh) return []
    const out: { d: string; kind: Kind }[] = []
    for (const e of edges) {
      const a = model.byId.get(e.from)
      const b = model.byId.get(e.to)
      if (!a || !b) continue
      const ka = chKey(a.book, a.chapter)
      const kb = chKey(b.book, b.chapter)
      if (ka === kb || (ka !== hoverCh && kb !== hoverCh)) continue
      const ca = layout.chPos.get(ka)
      const cb = layout.chPos.get(kb)
      if (!ca || !cb) continue
      out.push({ d: `M ${L.chapterX} ${ca.y}${cableFrom(ca, cb)}`, kind: kindOf(e) })
    }
    return out
  }, [hoverCh, edges, model, layout, L])

  /** 选中/悬停的那个知识点的上下游：一条一条画，粗一点、亮一点，方向看得出。 */
  const focusPt = hoverPt || sel
  const links = useMemo(() => {
    const p = focusPt ? model.byId.get(focusPt) : undefined
    if (!p) return []
    const src = layout.chPos.get(chKey(p.book, p.chapter))
    const srcY = layout.ptPos.get(p.id)
    if (!src || srcY == null) return []
    const out: { d: string; kind: Kind; x: number; y: number }[] = []
    for (const e of edges) {
      if (e.from !== p.id && e.to !== p.id) continue
      const other = model.byId.get(e.from === p.id ? e.to : e.from)
      if (!other) continue
      const kind = kindOf(e)
      const dst = layout.chPos.get(chKey(other.book, other.chapter))
      const dstY = layout.ptPos.get(other.id)
      if (!dst) {
        // 目标在收起的册里（小学默认只展开一册）：连到那本册签，
        // 至少让「这一课跨到哪一册」看得出来；精确的章节留给右栏。
        const bp = layout.bookPos.get(other.book)
        if (!bp || other.book === p.book) continue
        const pr = L.bookX + L.bookW
        const dx = Math.max(16, (L.chapterX - pr) * 0.6)
        const pA = layout.bookPos.get(p.book)?.y ?? src.y
        const d = `M ${L.ptX - 4} ${srcY} C ${src.right + 14} ${srcY}, ${src.right + 14} ${src.y}, ${src.right} ${src.y}`
          + ` L ${L.chapterX} ${src.y}`
          + ` C ${L.chapterX - dx} ${src.y}, ${pr + dx} ${pA}, ${pr} ${pA}`
          + ` L ${L.crossX} ${pA} L ${L.crossX} ${bp.y} L ${L.bookX} ${bp.y}`
        out.push({ d, kind, x: L.bookX, y: bp.y })
        continue
      }
      if (dst === src) {
        if (dstY == null) continue
        out.push({
          d: `M ${L.ptX} ${srcY} C ${L.ptX - 16} ${srcY}, ${L.ptX - 16} ${dstY}, ${L.ptX} ${dstY}`,
          kind, x: L.ptX, y: dstY,
        })
        continue
      }
      const sx = L.ptX - 4
      // 起笔：知识点 → 本章那一行（藏在行底），再沿行走到章的左端
      let d = `M ${sx} ${srcY} C ${src.right + 14} ${srcY}, ${src.right + 14} ${src.y}, ${src.right} ${src.y}`
      d += ` L ${L.chapterX} ${src.y}`
      d += cableFrom(src, dst)
      if (dstY != null) {
        d += ` L ${dst.right} ${dst.y} C ${dst.right + 14} ${dst.y}, ${dst.right + 14} ${dstY}, ${sx} ${dstY}`
      } else {
        d += ` L ${L.chapterX} ${dst.y}`
      }
      out.push({ d, kind, x: dstY != null ? sx : L.chapterX, y: dstY ?? dst.y })
    }
    return out
  }, [focusPt, edges, model, layout, L])

  /** 适配：高度定缩放，宽度定版心。只在换学段/第一次进来时算一次。 */
  const fitZoom = useMemo(() => {
    if (!box.h || !box.w) return 1
    // 高度和宽度都要放得下：高中只有 18 章，按高度能放到 115%，
    // 但版心只有一屏宽，放大后会横向溢出（右侧知识点被裁掉）。
    return Math.max(0.62, Math.min(1.15, (box.h - 16) / layout.height, (box.w - 16) / contentW))
  }, [box, layout.height, contentW])
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const fitted = useRef('')
  useLayoutEffect(() => {
    // 只在「换学段 / 容器尺寸变了」时重新适配。展开一章不重算——否则每点一下
    // 字就缩一圈；但右侧详情面板开合会改容器宽度，那种必须重新适配。
    if (!box.h || !box.w) return
    // 切学段的第一帧里 sel 还是上一个学段的点（MapPage 随后才换），那一帧的树
    // 是"只展开第一册、没有知识点"的矮版本，照它适配会把整张图放大到溢出。
    // 把"当前有没有有效选中点"也放进 key：等它落定再适配一次。
    const key = `${stage}|${box.w}x${box.h}|${selNode ? 1 : 0}`
    if (fitted.current === key) return
    fitted.current = key
    setZoom(+fitZoom.toFixed(3))
  }, [stage, box.w, box.h, fitZoom, selNode])

  /** 选中知识点：滚到画面中间（图比一屏长的时候得看得见）。 */
  useEffect(() => {
    const el = wrapRef.current
    if (!el || !sel) return
    const y = layout.ptPos.get(sel)
    if (y == null) return
    const top = y * zoom - el.clientHeight / 2
    if (Math.abs(el.scrollTop - top) > 12) el.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
  }, [sel, layout, zoom])

  const toggleBook = (name: string) => {
    const next = new Set(openBooks)
    if (next.has(name)) next.delete(name); else next.add(name)
    setBookPref({ stage, v: next })
  }
  const toggleChapter = (key: string) => {
    const next = new Set(openChapters)
    if (next.has(key)) next.delete(key); else next.add(key)
    setChapPref({ stage, v: next })
  }

  const focusActive = Boolean(hoverCh || hoverPt)
  const dimOf = (a: string, b: string) => {
    if (hoverCh) return a === hoverCh || b === hoverCh ? 1 : 0.18
    if (selCh) return a === selCh || b === selCh ? 1 : 0.6
    return 1
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--radius-card)]
                    border border-border bg-surface shadow-[var(--shadow-card)]">
      <div className="pointer-events-none absolute inset-0 opacity-50"
        style={{
          backgroundImage: 'radial-gradient(var(--color-border-strong) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          maskImage: 'radial-gradient(ellipse 88% 78% at 50% 42%, #000 24%, transparent 90%)',
        }} />

      <div className="absolute right-3 top-2.5 z-20 flex items-center gap-1">
        <button onClick={() => setZoom((z) => Math.min(1.8, +(z + 0.12).toFixed(2)))}
          title="放大" className="grid h-7 w-7 place-items-center rounded-lg border border-border
          bg-surface/90 text-ink-faint backdrop-blur hover:border-brand-line hover:text-brand-ink">
          <Plus size={13} />
        </button>
        <span className="tnum w-9 text-center text-[10px] text-ink-faint">{Math.round(zoom * 100)}%</span>
        <button onClick={() => setZoom((z) => Math.max(0.5, +(z - 0.12).toFixed(2)))}
          title="缩小" className="grid h-7 w-7 place-items-center rounded-lg border border-border
          bg-surface/90 text-ink-faint backdrop-blur hover:border-brand-line hover:text-brand-ink">
          <Minus size={13} />
        </button>
        <button onClick={() => setZoom(+fitZoom.toFixed(3))} title="适配画面"
          className="grid h-7 w-7 place-items-center rounded-lg border border-border bg-surface/90
                     text-ink-faint backdrop-blur hover:border-brand-line hover:text-brand-ink">
          <Maximize2 size={13} />
        </button>
      </div>

      <div ref={wrapRef} className="relative z-[1] min-h-0 flex-1 overflow-auto p-2">
        <svg width={contentW * zoom} height={layout.height * zoom}
          viewBox={`0 0 ${contentW} ${layout.height}`}
          style={{ marginTop: Math.max(0, (box.h - layout.height * zoom) / 2 - 10) }}
          className="mx-auto block select-none"
          role="img" aria-label="教材知识导图"
          onMouseLeave={() => { setHoverCh(null); setHoverPt(null); setHoverBook(null) }}>
          <defs>
            <filter id="mind-shadow" x="-40%" y="-60%" width="180%" height="220%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#0f172a" floodOpacity=".14" />
            </filter>
            <radialGradient id="mind-glow">
              <stop offset="0%" stopColor={tone.border} stopOpacity=".18" />
              <stop offset="100%" stopColor={tone.border} stopOpacity="0" />
            </radialGradient>
          </defs>

          <circle cx={L.rootX + L.rootW / 2} cy={layout.rootY} r={150} fill="url(#mind-glow)" />

          {/* ── 线束（画在卡片底下，被卡片盖住，看起来就是插到卡片背后） ── */}
          <g fill="none" strokeLinecap="round" strokeLinejoin="round">
            {cables.map((c) => {
              const A = layout.chPos.get(c.a)
              const B = layout.chPos.get(c.b)
              if (!A || !B) return null
              const kind: Kind = c.hard ? 'hard' : c.soft ? 'soft' : 'order'
              const lane = A.book === B.book ? L.bookLaneX : L.crossX
              const on = hoverCh ? (c.a === hoverCh || c.b === hoverCh) : false
              const w = on ? 0.9 + Math.min(2, Math.log2(c.n + 1) * 0.55) : 0.9
              return (
                <path key={`${c.a}|${c.b}`}
                  d={elbow([[L.chapterX, A.y], [lane, A.y],
                    [lane, B.y], [L.chapterX, B.y]], 8)}
                  stroke={CABLE[kind].stroke}
                  strokeWidth={w}
                  strokeDasharray={CABLE[kind].dash}
                  opacity={(on ? 0.66 : CABLE[kind].opacity * 0.5) * (hoverCh ? dimOf(c.a, c.b) : 1)}
                  style={{ transition: 'opacity .18s' }} />
              )
            })}
            {hoverLinks.map((l, i) => (
              <path key={`h${i}`} d={l.d}
                stroke={CABLE[l.kind].stroke}
                strokeWidth={1.2}
                strokeDasharray={CABLE[l.kind].dash}
                opacity={0.55} />
            ))}
            {links.map((l, i) => (
              <path key={`l${i}`} d={l.d}
                stroke={CABLE[l.kind].stroke}
                strokeWidth={l.kind === 'order' ? 0.9 : 1.3}
                strokeDasharray={CABLE[l.kind].dash}
                opacity={focusActive && !hoverPt ? 0.45 : 0.72} />
            ))}
          </g>

          {/* ── 枝条：学段 → 册 → 章（曲线，才是思维导图的骨架） ── */}
          <g fill="none" strokeLinecap="round">
            {model.books.map((b) => {
              const p = layout.bookPos.get(b.name)!
              const open = openBooks.has(b.name)
              const dim = hoverBook && hoverBook !== b.name ? 0.4 : 1
              return (
                <g key={`br-${b.name}`} opacity={dim}>
                  <path d={branch(L.rootX + L.rootW, layout.rootY, L.bookX, p.y)}
                    stroke="var(--color-ink-faint)" strokeWidth={1.4} opacity={0.6} />
                  {open && b.chapters.map((c) => {
                    const ch = layout.chPos.get(c.key)!
                    const active = c.key === selCh
                    return (
                      <path key={c.key}
                        d={branch(L.bookX + L.bookW, p.y, L.chapterX, ch.y)}
                        stroke={active ? tone.border : 'var(--color-ink-faint)'}
                        strokeWidth={active ? 1.6 : 1.2}
                        opacity={active ? 0.7 : 0.42} />
                    )
                  })}
                </g>
              )
            })}
          </g>

          {/* 章 → 知识点的小枝条（比主轴更淡） */}
          <g fill="none" stroke="var(--color-ink-faint)" strokeWidth={1} opacity={0.34}>
            {model.books.flatMap((b) => b.chapters.map((c) => {
              if (!openChapters.has(c.key)) return null
              const p = layout.chPos.get(c.key)!
              return c.points.map((pt) => {
                const y = layout.ptPos.get(pt.id)
                if (y == null) return null
                return (
                  <path key={pt.id}
                    d={`M ${p.right} ${p.y} C ${p.right + 16} ${p.y}, ${L.ptX - 12} ${y}, ${L.ptX - 2} ${y}`} />
                )
              })
            }))}
          </g>

          {/* ── 学段根 ── */}
          <g filter="url(#mind-shadow)">
            <rect x={L.rootX} y={layout.rootY - 38} width={L.rootW} height={76}
              rx={16} fill="var(--color-solid)" />
            <text x={L.rootX + L.rootW / 2} y={layout.rootY - 13} textAnchor="middle"
              fontSize={9.5} fill="var(--color-solid-ink)" opacity={0.6}
              letterSpacing=".08em">{centerLabel}</text>
            <text x={L.rootX + L.rootW / 2} y={layout.rootY + 14} textAnchor="middle"
              fontSize={23} fontWeight={700} fill="var(--color-solid-ink)">{centerCount}</text>
            <text x={L.rootX + L.rootW / 2} y={layout.rootY + 28} textAnchor="middle"
              fontSize={8.5} fill="var(--color-solid-ink)" opacity={0.55}>个知识点</text>
          </g>

          {/* ── 册 ── */}
          {model.books.map((b) => {
            const p = layout.bookPos.get(b.name)!
            const open = openBooks.has(b.name)
            const n = b.chapters.reduce((s, c) => s + c.points.length, 0)
            const hot = hoverBook === b.name
            const gapN = b.chapters.reduce((s, c) =>
              s + c.points.filter((p) => !(p.nq || 0) && !(p.q || 0)).length, 0)
            const dim = gapOnly && gapN === 0
            return (
              <g key={b.name} className="cursor-pointer" opacity={dim ? 0.2 : 1}
                onClick={() => toggleBook(b.name)}
                onMouseEnter={() => setHoverBook(b.name)} onMouseLeave={() => setHoverBook(null)}>
                <title>{`${b.name} · ${n} 个知识点 · ${open ? '点一下收起' : '点一下展开'}`}</title>
                <rect x={L.bookX} y={p.y - BOOK_H / 2} width={L.bookW} height={BOOK_H} rx={10}
                  fill={hot
                    ? 'var(--color-surface)'
                    : `color-mix(in srgb, ${tone.border} 5%, var(--color-surface))`}
                  stroke={hot ? tone.border : 'var(--color-border-strong)'}
                  strokeOpacity={hot ? 0.75 : 1}
                  strokeWidth={hot ? 1.4 : 1}
                  filter={hot ? 'url(#mind-shadow)' : undefined} />
                <rect x={L.bookX + 6} y={p.y - 9} width={2.6} height={18} rx={1.3}
                  fill={tone.border} opacity={open ? 0.75 : 0.35} />
                <path d={open ? 'M -3 -1.5 L 0 1.5 L 3 -1.5' : 'M -1.5 -3 L 1.5 0 L -1.5 3'}
                  transform={`translate(${L.bookX + 15},${p.y})`}
                  fill="none" stroke="var(--color-ink-faint)" strokeWidth={1.4}
                  strokeLinecap="round" strokeLinejoin="round" />
                <text x={L.bookX + 23} y={p.y - 2} fontSize={11} fontWeight={600}
                  fill="var(--color-ink)">{clip(shortBook(b.name), L.bookW - 30, 11)}</text>
                <text x={L.bookX + 23} y={p.y + 11} fontSize={9}
                  fill="var(--color-ink-faint)">{`${n} 点 · ${b.chapters.length} 章`}</text>
              </g>
            )
          })}

          {/* ── 章 ── */}
          {model.books.flatMap((b) => b.chapters.map((c) => {
            if (!openBooks.has(b.name)) return null
            const p = layout.chPos.get(c.key)!
            const active = c.key === selCh
            const hot = c.key === hoverCh
            const fs = 11
            const title = p.label
            const tw = textW(title, fs)
            const badge = `${c.points.length}`
            const w = p.right - (L.chapterX - 7)
            const gapN = c.points.filter((p) => !(p.nq || 0) && !(p.q || 0)).length
            const dim = gapOnly && gapN === 0
            const allKnown = c.points.length > 0 && c.points.every((p) => known.has(p.id))
            const nqSum = c.points.reduce((s, p) => s + (p.nq || 0), 0)
            const qSum = c.points.reduce((s, p) => s + (p.q || 0), 0)
            return (
              <g key={c.key} className="cursor-pointer" opacity={dim ? 0.2 : 1}
                onClick={() => toggleChapter(c.key)}
                onMouseEnter={() => setHoverCh(c.key)} onMouseLeave={() => setHoverCh(null)}>
                <title>{`${c.title} · ${c.points.length} 个知识点 · ${nqSum} 题 · ${qSum} 道诊断 · ${openChapters.has(c.key) ? '点一下收起' : '点一下展开知识点'}`}</title>
                <rect x={L.chapterX - 7} y={p.y - CH_H / 2} width={w + 7} height={CH_H} rx={5}
                  fill={active ? 'var(--color-brand-soft)' : hot ? 'var(--color-muted)' : 'var(--color-surface)'}
                  stroke={active ? 'var(--color-brand-line)' : hot ? 'var(--color-border-strong)' : 'transparent'}
                  strokeWidth={1} />
                {active && (
                  <rect x={L.chapterX - 4} y={p.y - 4.5} width={2.4} height={9} rx={1.2}
                    fill="var(--color-brand)" />
                )}
                <text x={L.chapterX + 3} y={p.y + 3.6} fontSize={fs}
                  fontWeight={active ? 600 : 500}
                  fill={active ? 'var(--color-brand-ink)' : 'var(--color-ink)'}>{title}</text>
                <text x={L.chapterX + 3 + tw + 6} y={p.y + 3.2} fontSize={9}
                  fill={allKnown ? 'var(--color-has)' : 'var(--color-ink-faint)'}
                  opacity={0.9}>{allKnown ? '✓' : badge}</text>
                {nqSum > 0 && (
                  <text x={L.chapterX + 3 + tw + 16} y={p.y + 3.2} fontSize={8}
                    fill="var(--color-warn)" opacity={0.75}>{`${fmtN(nqSum)}题`}</text>
                )}
              </g>
            )
          }))}

          {/* ── 知识点 ── */}
          {model.books.flatMap((b) => b.chapters.map((c) => {
            if (!openChapters.has(c.key)) return null
            return c.points.map((pt) => {
              const y = layout.ptPos.get(pt.id)
              if (y == null) return null
              const on = pt.id === sel
              const hot = pt.id === hoverPt
              const fs = 11
              const label = clip(pt.title, L.ptW - 22, fs)
              const tw = textW(label, fs)
              const w = Math.min(L.ptW, tw + 22)
              const mastered = known.has(pt.id)
              const gap = !(pt.nq || 0) && !(pt.q || 0)
              const dim = gapOnly && !gap
              return (
                <g key={pt.id} className="cursor-pointer" opacity={dim ? 0.18 : 1}
                  onClick={() => onSelect(pt.id)}
                  onMouseEnter={() => setHoverPt(pt.id)} onMouseLeave={() => setHoverPt(null)}>
                  <title>{pt.title}</title>
                  <rect x={L.ptX - 8} y={y - PT_H / 2} width={w} height={PT_H} rx={5}
                    fill={on ? 'var(--color-brand-soft)' : hot ? 'var(--color-muted)' : 'transparent'}
                    stroke={on ? 'var(--color-brand-line)' : 'transparent'} strokeWidth={1} />
                  {mastered && !on ? (
                    <path d={`M ${L.ptX - 5} ${y} l 2.6 2.6 l 4.4 -4.6`}
                      fill="none" stroke="var(--color-has)" strokeWidth={1.4}
                      strokeLinecap="round" strokeLinejoin="round" />
                  ) : (
                    <circle cx={L.ptX - 1} cy={y} r={2.2}
                      fill={on ? 'var(--color-brand)' : tone.border} opacity={on ? 1 : 0.55} />
                  )}
                  <text x={L.ptX + 6} y={y + 3.6} fontSize={fs}
                    fontWeight={on ? 600 : 400}
                    opacity={mastered && !on ? 0.6 : 1}
                    fill={on ? 'var(--color-brand-ink)' : 'var(--color-ink-soft)'}>{label}</text>
                  {(pt.nq || 0) > 0 && (
                    <text x={L.ptX + 8 + tw} y={y + 3.2} fontSize={8}
                      fill="var(--color-warn)" opacity={0.75}>{`${fmtN(pt.nq || 0)}题`}</text>
                  )}
                </g>
              )
            })
          }))}

          {/* 线束端点：表示"这根线插在这里" */}
          {links.map((l, i) => (
            <circle key={`t${i}`} cx={l.x} cy={l.y} r={2.2}
              fill={CABLE[l.kind].stroke} stroke="var(--color-surface)" strokeWidth={1} opacity={0.9} />
          ))}
        </svg>
      </div>

      <div className="pointer-events-none absolute bottom-3 right-3 z-10 flex items-center gap-2.5
                      rounded-full border border-border bg-surface/85 px-3 py-1 text-[9px] text-ink-faint
                      backdrop-blur">
        <span className="inline-flex items-center gap-1">
          <i className="h-[3px] w-3.5 rounded-full" style={{ background: CABLE.hard.stroke }} />硬先修
        </span>
        <span className="inline-flex items-center gap-1">
          <i className="h-[3px] w-3.5 rounded-full" style={{ background: CABLE.soft.stroke }} />有帮助
        </span>
        <span className="inline-flex items-center gap-1">
          <i className="h-[3px] w-3.5 rounded-full" style={{ background: CABLE.order.stroke, opacity: 0.5 }} />教材顺序
        </span>
      </div>
    </div>
  )
}
