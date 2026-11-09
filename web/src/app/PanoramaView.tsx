/** 知识图谱 · 教材全景（按参考图的"底部中心 + 扇形散点 + 横向标签"来）
 *
 *  参考图不是同心环，而是：
 *    · 中心节点在**底部中间**，所有节点散在上方的一大片扇形里；
 *    · 节点用**类型小方块/圆点 + 横向文字标签**，不画环、不转字；
 *    · 从中心到每个节点一根**细直线**，几十根并在一起就是那把"扇子"；
 *    · 左下角图例、顶部"N 条关系"、悬停看联系。
 *
 *  我们的数据没有"核心素养/解题方法"这些层，就把中心换成**学段**、节点换成
 *  **册 / 章 / 知识点**；先修关系不硬塞进扇子，只画聚焦那一章的（悬停/点章），
 *  这样默认是一张干净的全景，需要时再拉出那张网。
 *
 *  位置用"贪心 + 标签避让"算：每个章给一个理想角度，从内往外试半径/微调角度，
 *  第一个不和已放标签打架的位置就落子。纯确定性，刷新不跳位。
 */
import { useMemo, useState } from 'react'
import type { Tone } from '@/app/GraphView'
import { useMastery } from '@/lib/mastery'

export type PanoNode = {
  id: string
  title: string
  book: string
  chapter: string
  order: number
  tone: Tone
  q?: number
  nq?: number
}
export type PanoEdge = {
  from: string
  to: string
  strength: string
  kind: string
}

type Kind = 'hard' | 'soft' | 'order'
const kindOf = (e: PanoEdge): Kind =>
  (e.strength === 'hard' ? 'hard' : e.kind === 'order' ? 'order' : 'soft')

/** 画布（逻辑坐标，原点在正中）。 */
const VIEW = { w: 780, h: 720, hubY: 292 }
const FAN = { a0: -142, a1: -38 }          // 扇形角度范围（度，负数=向上）
const RADII = [210, 248, 288, 330, 376, 424, 478, 536, 596]
const JITTER = [0, 3, -3, 6, -6, 9, -9, 12, -12, 15, -15]
const TAU = Math.PI * 2

const CABLE: Record<Kind, { stroke: string; opacity: number; dash?: string }> = {
  hard: { stroke: 'var(--color-brand)', opacity: 0.62 },
  soft: { stroke: 'var(--color-violet)', opacity: 0.5 },
  order: { stroke: 'var(--color-ink-faint)', opacity: 0.34, dash: '2 4' },
}
const TYPE = {
  book: 'var(--color-brand)',
  chapter: 'var(--color-cyan)',
  point: 'var(--color-warn)',
}

const CJK = /[\u2e80-\u9fff\uff00-\uffef]/
function textW(s: string, size: number) {
  let w = 0
  for (const ch of s) w += CJK.test(ch) ? size : size * 0.56
  return w
}
function clip(s: string, px: number, size: number) {
  let w = 0
  for (let i = 0; i < s.length; i++) {
    const cw = CJK.test(s[i]) ? size : size * 0.56
    if (w + cw > px) return `${s.slice(0, Math.max(1, i - 1))}…`
    w += cw
  }
  return s
}

type Box = { x: number; y: number; w: number; h: number }
const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.w + 5 && a.x + a.w + 5 > b.x && a.y < b.y + b.h + 2 && a.y + a.h + 2 > b.y
const inView = (b: Box) =>
  b.x >= -VIEW.w / 2 + 6 && b.x + b.w <= VIEW.w / 2 - 6
  && b.y >= -VIEW.h / 2 + 6 && b.y + b.h <= VIEW.h / 2 - 6

/** 册签文字：6 册写全称，12 册写「一上/二下」这种短名。 */
function bookLabel(name: string, books: number) {
  const short = name.replace('选择性必修第', '选必').replace('必修第', '必修').replace(/册$/, '')
  if (books > 8) return short.replace('年级', '').replace('上册', '上').replace('下册', '下')
  return short
}

export default function PanoramaView({
  nodes, edges, sel, onSelect, centerLabel, centerCount, gapOnly = false,
}: {
  nodes: PanoNode[]
  edges: PanoEdge[]
  sel: string | null
  onSelect: (id: string) => void
  centerLabel: string
  centerCount: number
  /** 只看缺口（地图页的「待建」视图）；当前视图暂不消费。 */
  gapOnly?: boolean
}) {
  const known = useMastery()
  const [hoverCh, setHoverCh] = useState<string | null>(null)
  const [lockedCh, setLockedCh] = useState<string | null>(null)
  const [hoverPt, setHoverPt] = useState<string | null>(null)
  const [focusBook, setFocusBook] = useState<string | null>(null)

  /** 树 + 每个节点的落点（贪心避让标签）。 */
  const model = useMemo(() => {
    const ordered = [...nodes].sort((a, b) => a.order - b.order)
    const byId = new Map(ordered.map((n) => [n.id, n]))
    const chapters: {
      key: string; title: string; book: string; points: PanoNode[]
      x: number; y: number; side: 1 | -1; label: string; hidden: boolean; angle: number
    }[] = []
    const books: { name: string; chapters: typeof chapters; x: number; y: number; n: number }[] = []
    const index = new Map<string, (typeof books)[number]>()
    for (const n of ordered) {
      let b = index.get(n.book)
      if (!b) {
        b = { name: n.book, chapters: [], x: 0, y: 0, n: 0 }
        index.set(n.book, b)
        books.push(b)
      }
      let c = chapters.find((x) => x.key === `${n.book}\u0000${n.chapter}`)
      if (!c) {
        c = {
          key: `${n.book}\u0000${n.chapter}`, title: n.chapter, book: n.book,
          points: [], x: 0, y: 0, side: 1, label: '', hidden: false, angle: 0,
        }
        chapters.push(c)
        b.chapters.push(c)
      }
      c.points.push(n)
      b.n += 1
    }

    const placed: Box[] = []
    const total = Math.max(1, chapters.length)
    const fan0 = (FAN.a0 * Math.PI) / 180
    const fanSpan = ((FAN.a1 - FAN.a0) * Math.PI) / 180
    const hub = { x: 0, y: VIEW.hubY }

    // 册：每个册的扇区中点，放得尽量靠内，标签就是名字本身
    books.forEach((b, bi) => {
      const a = fan0 + ((bi + 0.5) / books.length) * fanSpan
      const bw = 76, bh = 22
      let ok = false
      for (const r of [272, 312, 236, 352, 200]) {
        for (const da of [0, 4, -4, 8, -8]) {
          const ang = a + (da * Math.PI) / 180
          const x = Math.cos(ang) * r
          const y = hub.y + Math.sin(ang) * r
          const box = { x: x - bw / 2, y: y - bh / 2, w: bw, h: bh }
          if (!inView(box) || placed.some((p) => overlap(p, box))) continue
          b.x = x; b.y = y
          placed.push(box)
          ok = true
          break
        }
        if (ok) break
      }
      if (!ok) {
        b.x = Math.cos(a) * 260
        b.y = hub.y + Math.sin(a) * 260
      }
    })

    // 章：理想角度按教材顺序均分，从内往外试半径，直到标签不打架
    chapters.forEach((c, i) => {
      const ideal = fan0 + ((i + 0.5) / total) * fanSpan
      c.angle = ideal
      const fs = 10
      const label = clip(c.title, 118, fs)
      const tw = textW(label, fs)
      let done = false
      // 每个章从一个错开的半径起试，避免全部挤在最外圈或最内圈；
      // 试不通再往下一档收，碰撞检测负责把标签铺开。
      const startR = (i * 4) % RADII.length
      for (let k = 0; k < RADII.length; k++) {
        const r = RADII[(startR + k) % RADII.length]
        for (const da of JITTER) {
          const ang = ideal + (da * Math.PI) / 180
          const x = Math.cos(ang) * r
          const y = hub.y + Math.sin(ang) * r
          const side: 1 | -1 = x >= 0 ? 1 : -1
          const dot: Box = { x: x - 7, y: y - 7, w: 14, h: 14 }
          const lb: Box = side === 1
            ? { x: x + 12, y: y - 9, w: tw, h: 18 }
            : { x: x - 12 - tw, y: y - 9, w: tw, h: 18 }
          if (!inView(dot) || !inView(lb)) continue
          if (placed.some((p) => overlap(p, dot) || overlap(p, lb))) continue
          c.x = x; c.y = y; c.side = side; c.label = label
          placed.push(dot, lb)
          done = true
          break
        }
        if (done) break
      }
      if (!done) {
        // 挤不下就不挂字：点还在，悬停有 title；比叠成一团字好
        const r = 300
        c.x = Math.cos(ideal) * r
        c.y = hub.y + Math.sin(ideal) * r
        c.side = c.x >= 0 ? 1 : -1
        c.label = label
        c.hidden = true
      }
    })

    return { books, chapters, byId, hub }
  }, [nodes])

  const selNode = sel ? model.byId.get(sel) : undefined
  const selCh = selNode ? `${selNode.book}\u0000${selNode.chapter}` : null
  const focusCh = hoverCh || lockedCh || selCh
  const focusNode = focusCh ? model.chapters.find((c) => c.key === focusCh) : undefined

  /** 聚焦章的进出边：一条直线落到目标章节点。 */
  const links = useMemo(() => {
    if (!focusNode) return []
    const agg = new Map<string, { at: { x: number; y: number }; kind: Kind; n: number }>()
    for (const e of edges) {
      const A = model.byId.get(e.from)
      const B = model.byId.get(e.to)
      if (!A || !B) continue
      const ka = `${A.book}\u0000${A.chapter}`
      const kb = `${B.book}\u0000${B.chapter}`
      if (ka !== focusCh && kb !== focusCh) continue
      const other = ka === focusCh ? kb : ka
      if (other === focusCh) continue
      const dst = model.chapters.find((c) => c.key === other)
      if (!dst) continue
      const kind = kindOf(e)
      const key = `${other}|${kind}`
      const cur = agg.get(key)
      if (cur) cur.n += 1
      else agg.set(key, { at: { x: dst.x, y: dst.y }, kind, n: 1 })
    }
    return [...agg.values()]
  }, [focusNode, focusCh, edges, model])

  const relCount = edges.filter((e) => model.byId.has(e.from) && model.byId.has(e.to)).length
  const hoverNode = hoverCh ? model.chapters.find((c) => c.key === hoverCh) : null

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--radius-card)]
                    border border-border bg-surface shadow-[var(--shadow-card)]">
      <div className="pointer-events-none absolute inset-0 opacity-50"
        style={{
          backgroundImage: 'radial-gradient(var(--color-border-strong) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
          maskImage: 'radial-gradient(ellipse 85% 80% at 50% 45%, #000 25%, transparent 92%)',
        }} />

      <div className="pointer-events-none absolute left-4 top-3 z-10 inline-flex items-center gap-2
                      rounded-full border border-border bg-surface/90 px-2.5 py-[4px]
                      text-[9.5px] text-ink-faint backdrop-blur">
        <span className="font-medium tracking-[0.06em] text-ink-soft">
          {centerLabel} · 知识全景
        </span>
        <span>{model.books.length} 册 · {model.chapters.length} 章 · {nodes.length} 点 · {relCount} 条关系</span>
      </div>

      <div className="relative z-[1] min-h-0 flex-1">
        <svg viewBox={`${-VIEW.w / 2} ${-VIEW.h / 2} ${VIEW.w} ${VIEW.h}`}
          className="h-full w-full select-none"
          role="img" aria-label="教材知识全景"
          onMouseLeave={() => { setHoverCh(null); setHoverPt(null) }}>
          <defs>
            <radialGradient id="pano-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="var(--color-brand)" stopOpacity=".10" />
              <stop offset="100%" stopColor="var(--color-brand)" stopOpacity="0" />
            </radialGradient>
            <filter id="pano-dot" x="-80%" y="-80%" width="260%" height="260%">
              <feDropShadow dx="0" dy="1" stdDeviation="1.4" floodColor="#0f172a" floodOpacity=".16" />
            </filter>
          </defs>

          <ellipse cx={0} cy={model.hub.y - 150} rx={360} ry={230} fill="url(#pano-glow)" />

          {/* 中心 → 册/章：那把扇子 */}
          <g stroke="var(--color-ink-faint)" strokeWidth={1} opacity={0.26}>
            {model.books.map((b) => (
              <line key={`lb-${b.name}`} x1={model.hub.x} y1={model.hub.y - 30}
                x2={b.x} y2={b.y} />
            ))}
            {model.chapters.map((c) => (
              <line key={`lc-${c.key}`} x1={model.hub.x} y1={model.hub.y - 30}
                x2={c.x} y2={c.y} />
            ))}
          </g>

          {/* 聚焦章的先修线：从章节点直连目标章节点 */}
          <g strokeLinecap="round">
            {focusNode && links.map((l, i) => (
              <g key={i}>
                <line x1={focusNode.x} y1={focusNode.y} x2={l.at.x} y2={l.at.y}
                  stroke={CABLE[l.kind].stroke}
                  strokeWidth={1.1 + Math.min(1.1, Math.log2(l.n + 1) * 0.45)}
                  strokeDasharray={CABLE[l.kind].dash}
                  opacity={CABLE[l.kind].opacity} />
                <circle cx={l.at.x} cy={l.at.y} r={5}
                  fill="none" stroke={CABLE[l.kind].stroke} strokeWidth={1.2} opacity={0.7} />
              </g>
            ))}
          </g>

          {/* 知识点：章节点旁边的一小簇点，点本身可点，标题走 title / 右栏 */}
          {model.chapters.map((c) => {
            return c.points.map((p, i) => {
              const ring = Math.floor(i / 8)
              const k = i % 8
              const ang = (k / 8) * TAU + ring * 0.4
              const rr = 10 + ring * 8
              const x = c.x + Math.cos(ang) * rr
              const y = c.y + Math.sin(ang) * rr
              const on = p.id === sel
              const hot = p.id === hoverPt
              const mastered = known.has(p.id)
              const gap = !(p.nq || 0) && !(p.q || 0)
              return (
                <g key={p.id} className="cursor-pointer"
                  opacity={gapOnly && !gap ? 0.1
                    : focusBook && c.book !== focusBook ? 0.12 : on || hot ? 1 : 0.72}
                  onClick={() => onSelect(p.id)}
                  onMouseEnter={() => setHoverPt(p.id)} onMouseLeave={() => setHoverPt(null)}>
                  <title>{p.title}</title>
                  {on && <circle cx={x} cy={y} r={7} fill="var(--color-brand)" opacity={0.16} />}
                  <circle cx={x} cy={y} r={on ? 3.6 : hot ? 3 : 2.1}
                    fill={on ? 'var(--color-brand)' : mastered ? 'transparent' : TYPE.point}
                    stroke={mastered && !on ? TYPE.point : undefined} strokeWidth={1.2} />
                </g>
              )
            })
          })}

          {/* 册：蓝色方块 + 横向名字 */}
          {model.books.map((b) => {
            const name = clip(bookLabel(b.name, model.books.length), 90, 10.5)
            const w = textW(name, 10.5) + 22
            return (
              <g key={b.name} className="cursor-pointer"
                onClick={() => setFocusBook((cur) => (cur === b.name ? null : b.name))}>
                <title>{`${b.name} · ${b.chapters.length} 章 · ${b.n} 个知识点 · 点一下聚焦`}</title>
                <rect x={b.x - w / 2} y={b.y - 11} width={w} height={22} rx={7}
                  fill="var(--color-brand-soft)"
                  stroke="var(--color-brand-line)"
                  strokeWidth={focusBook === b.name ? 2 : 1.1}
                  opacity={gapOnly && b.chapters.every((c) => c.points.every((p) => (p.nq || 0) || (p.q || 0)))
                    ? 0.2 : focusBook && focusBook !== b.name ? 0.45 : 1} />
                <rect x={b.x - w / 2 + 7} y={b.y - 3.5} width={7} height={7} rx={1.6}
                  fill={TYPE.book} opacity={0.9} />
                <text x={b.x - w / 2 + 18} y={b.y + 3.6} fontSize={10.5} fontWeight={600}
                  fill="var(--color-brand-ink)">
                  {name}
                </text>
              </g>
            )
          })}

          {/* 章：青色方块 + 横向标签（文本加一圈 surface 描边，压在线上也不糊） */}
          {model.chapters.map((c) => {
            const active = c.key === selCh
            const hot = c.key === hoverCh
            const locked = c.key === lockedCh
            const gapN = c.points.filter((p) => !(p.nq || 0) && !(p.q || 0)).length
            const dim = gapOnly && gapN === 0
            const allKnown = c.points.length > 0 && c.points.every((p) => known.has(p.id))
            return (
              <g key={c.key} className="cursor-pointer"
                opacity={dim ? 0.18 : focusBook && c.book !== focusBook ? 0.18 : 1}
                onClick={() => setLockedCh((cur) => (cur === c.key ? null : c.key))}
                onMouseEnter={() => setHoverCh(c.key)} onMouseLeave={() => setHoverCh(null)}>
                <title>{`${c.title} · ${c.points.length} 个知识点`}</title>
                {(active || locked) && (
                  <circle cx={c.x} cy={c.y} r={9} fill="var(--color-brand)" opacity={0.1} />
                )}
                <rect x={c.x - 3.5} y={c.y - 3.5} width={7} height={7} rx={1.6}
                  fill={active ? 'var(--color-brand)' : allKnown ? 'var(--color-has)' : TYPE.chapter}
                  opacity={active || hot ? 1 : 0.9} />
                {!c.hidden && (
                  <text x={c.side === 1 ? c.x + 12 : c.x - 12} y={c.y + 3.6}
                    textAnchor={c.side === 1 ? 'start' : 'end'}
                    fontSize={10}
                    fontWeight={active ? 600 : 400}
                    fill={active ? 'var(--color-brand-ink)' : hot ? 'var(--color-ink)' : 'var(--color-ink-soft)'}
                    stroke="var(--color-surface)" strokeWidth={2.6} paintOrder="stroke">
                    {c.label}
                  </text>
                )}
              </g>
            )
          })}

          {/* 中心：学段 */}
          <g>
            <rect x={-62} y={model.hub.y - 32} width={124} height={64} rx={16}
              fill="var(--color-solid)" filter="url(#pano-dot)" />
            <text x={0} y={model.hub.y - 10} textAnchor="middle" fontSize={9.5}
              fill="var(--color-solid-ink)" opacity={0.65} letterSpacing=".08em">{centerLabel}</text>
            <text x={0} y={model.hub.y + 14} textAnchor="middle" fontSize={23} fontWeight={700}
              fill="var(--color-solid-ink)">{centerCount}</text>
            <text x={0} y={model.hub.y + 27} textAnchor="middle" fontSize={8}
              fill="var(--color-solid-ink)" opacity={0.55}>个知识点</text>
          </g>

          {/* 悬停/锁定提示：右下角浮一条，补足 title 看不见的信息 */}
          {hoverNode && (
            <g pointerEvents="none">
              <text x={VIEW.w / 2 - 16} y={VIEW.h / 2 - 18}
                textAnchor="end" fontSize={10} fill="var(--color-ink-soft)">
                {`${hoverNode.title} · ${hoverNode.points.length} 个知识点 · 点一下锁定`}
              </text>
            </g>
          )}
        </svg>
      </div>

      {/* 图例：类型 + 关系 */}
      <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex flex-col gap-1.5 rounded-xl
                      border border-border bg-surface/90 px-3 py-2 text-[9px] text-ink-faint backdrop-blur">
        <span className="flex items-center gap-1.5">
          <i className="h-2 w-2 rounded-[2px]" style={{ background: TYPE.book }} />教材（册）
        </span>
        <span className="flex items-center gap-1.5">
          <i className="h-2 w-2 rounded-[1.5px]" style={{ background: TYPE.chapter }} />章节
        </span>
        <span className="flex items-center gap-1.5">
          <i className="h-1.5 w-1.5 rounded-full" style={{ background: TYPE.point }} />知识点
        </span>
        <span className="mt-0.5 flex items-center gap-1.5">
          <i className="h-[2px] w-4 rounded-full" style={{ background: CABLE.hard.stroke }} />硬先修
        </span>
        <span className="flex items-center gap-1.5">
          <i className="h-[2px] w-4 rounded-full" style={{ background: CABLE.soft.stroke }} />有帮助
        </span>
      </div>
    </div>
  )
}
