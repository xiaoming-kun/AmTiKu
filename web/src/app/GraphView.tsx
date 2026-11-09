/** 知识图谱：以选中知识点为中心的**局部先修图**。
 *
 *  形态照参考项目（cn-math-taxonomy 的 explore 页）来：
 *    · 上面是先修，中间是当前知识点，下面是后续（自上而下）；
 *    · 节点按学段配色（小学青 / 初中蓝 / 高中紫），当前节点用强调色描边；
 *    · 连线是灰色平滑曲线，硬先修实线、软先修虚线；
 *    · 工具条只有「向上 N 层 / 缩小 / 放大 / 适配画面」，图下面一行图例和统计。
 *
 *  为什么只画局部：585 个点全铺开是毛线球（`设计/知识链路.md` 量过）。
 *  点任意节点就把它换到中间，一路可以追到小学。
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Maximize2, Minus, Plus, RefreshCw } from 'lucide-react'
import { useMastery } from '@/lib/mastery'

export type GEdge = { from: string; to: string; strength: string; kind: string }
export type Tone = 'p' | 'j' | 'h'

const NW = 168          // 节点宽：够放两行 13 个字
const NH = 42           // 节点高：两行标题
const LINE = 13         // 每行最多几个汉字
const GX = 16           // 同层水平间距
const PAD = 26

/** 学段色。用半透明填充 + 实色描边，明暗两套主题都能看清。 */
const TONE: Record<Tone, { bg: string; border: string }> = {
  p: { bg: 'rgba(15,118,110,.14)', border: '#0f766e' },
  j: { bg: 'rgba(29,78,216,.13)', border: '#1d4ed8' },
  h: { bg: 'rgba(109,40,217,.13)', border: '#6d28d9' },
}

const KIND_OF = (e: GEdge) => (e.strength === 'hard' ? 'hard' : e.kind === 'order' ? 'order' : 'soft')

/** 标题折成两行：优先在「、（：；」这种分隔处断，且尽量靠中间，别把 "教材3.4" 劈开；
 *  两行都还超长才截断。13 个汉字 ≈ 150px，正好塞进 168 的框。 */
function splitTitle(t: string): string[] {
  if (t.length <= LINE) return [t]
  const seps = '、，。；：（）,.: '
  let cut = -1
  let best = Infinity
  for (let i = 3; i < t.length - 2; i++) {
    if (!seps.includes(t[i])) continue
    // 开括号留在第二行开头（不能让「（」吊在行尾），其余标点跟在前半句后面
    const cand = t[i] === '（' || t[i] === '(' ? i : i + 1
    const d = Math.abs(cand - t.length / 2)
    if (d < best) { best = d; cut = cand }
  }
  if (cut < 0) cut = LINE
  let a = t.slice(0, cut)
  let b = t.slice(cut)
  if (a.length > LINE) a = `${a.slice(0, LINE - 1)}…`
  if (b.length > LINE) b = `${b.slice(0, LINE - 1)}…`
  return [a, b]
}

/** 先修线：正交 + 圆角，同一源点出去的边共用一根竖干、一条横向总线，收成"梳子"。
 *
 *  为什么不是曲线：边一多，三次贝塞尔会在中间拧成一团，而且控制点都在两个节点中间，
 *  走向不可预测。正交线只有"竖—横—竖"三段，互相并排时自然并成一条，读起来像接线。
 *
 *  `busAbove` 是"总线离目标顶点多少像素"：不同源点错开 4px（0/4/8），
 *  教材顺序单独再高 11px——不然虚线会和实线共用一条总线，只露出一小截像断线。
 */
function wirePath(x1: number, y1: number, x2: number, y2: number, busAbove: number) {
  if (Math.abs(x2 - x1) < 1) return `M ${x1} ${y1} V ${y2}`
  const gap = y2 - y1
  if (gap < 24) {
    const my = y1 + gap / 2
    return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`
  }
  const bus = Math.min(y2 - 6, Math.max(y1 + 6, y2 - busAbove))
  const r = Math.max(2, Math.min(6, Math.abs(x2 - x1) / 2, (bus - y1) / 2, (y2 - bus) / 2))
  const dir = x2 > x1 ? 1 : -1
  return `M ${x1} ${y1} V ${bus - r} Q ${x1} ${bus} ${x1 + dir * r} ${bus}`
    + ` H ${x2 - dir * r} Q ${x2} ${bus} ${x2} ${bus + r} V ${y2}`
}

export default function GraphView({
  sel, titleOf, orderOf, toneOf, preOf, postOf, allEdges, upDepth, downDepth,
  onSelect, onReset, gapOnly = false, isGap,
}: {
  sel: string
  titleOf: (id: string) => string
  orderOf: (id: string) => number
  toneOf: (id: string) => Tone
  preOf: Map<string, GEdge[]>
  postOf: Map<string, GEdge[]>
  allEdges: GEdge[]
  upDepth: number
  downDepth: number
  /** 只看缺口（地图页的「待建」视图）：非缺口点压暗。 */
  gapOnly?: boolean
  isGap?: (id: string) => boolean
  onSelect: (id: string) => void
  onReset: () => void
}) {
  const known = useMastery()
  const [zoom, setZoom] = useState(1)
  const [hover, setHover] = useState<string | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  /** 局部子图：祖先 upDepth 层 + 后代 downDepth 层。 */
  const nodes = useMemo(() => {
    const set = new Set<string>([sel])
    const walk = (dir: 'up' | 'down', max: number) => {
      let frontier = [sel]
      for (let d = 0; d < max && frontier.length; d++) {
        const next: string[] = []
        for (const id of frontier) {
          for (const e of (dir === 'up' ? preOf : postOf).get(id) || []) {
            const nid = dir === 'up' ? e.from : e.to
            if (!set.has(nid)) { set.add(nid); next.push(nid) }
          }
        }
        frontier = next
      }
    }
    walk('up', upDepth)
    walk('down', downDepth)
    return set
  }, [sel, upDepth, downDepth, preOf, postOf])

  /** 自上而下分层：y = 拓扑深度，x = 层内按教材顺序。 */
  const layout = useMemo(() => {
    const ids = [...nodes].sort((a, b) => orderOf(a) - orderOf(b))
    const depth = new Map<string, number>(ids.map((id) => [id, 0]))
    for (const id of ids) {
      const d = depth.get(id) || 0
      for (const e of postOf.get(id) || []) {
        if (!nodes.has(e.to)) continue
        depth.set(e.to, Math.max(depth.get(e.to) || 0, d + 1))
      }
    }
    const layers = new Map<number, string[]>()
    for (const id of ids) {
      const d = depth.get(id) || 0
      layers.set(d, [...(layers.get(d) || []), id])
    }
    // 一层超过 6 个就折成多行——否则 8 个后续排成一排，整图只能缩到 46%，字全糊
    const CHUNK = 4
    const ROW_GAP = 14
    const LAYER_GAP = 26
    const rowsByLayer = new Map<number, string[][]>()
    for (const [d, list] of layers) {
      const rows: string[][] = []
      for (let i = 0; i < list.length; i += CHUNK) rows.push(list.slice(i, i + CHUNK))
      rowsByLayer.set(d, rows)
    }
    const maxRowN = Math.max(1, ...[...rowsByLayer.values()].flat().map((r) => r.length))
    const width = PAD * 2 + maxRowN * NW + (maxRowN - 1) * GX
    const pos = new Map<string, { x: number; y: number }>()
    let cursor = PAD
    for (const d of [...rowsByLayer.keys()].sort((a, b) => a - b)) {
      const rows = rowsByLayer.get(d)!
      rows.forEach((row, ri) => {
        const offset = PAD + (width - (row.length * NW + (row.length - 1) * GX)) / 2
        row.forEach((id, i) => pos.set(id, { x: offset + i * (NW + GX), y: cursor + ri * (NH + ROW_GAP) }))
      })
      cursor += rows.length * NH + (rows.length - 1) * ROW_GAP + LAYER_GAP
    }
    const height = cursor - LAYER_GAP + PAD
    return { pos, width, height, maxD: Math.max(0, ...layers.keys()) }
  }, [nodes, orderOf, postOf])

  const edges = useMemo(
    () => allEdges.filter((e) => nodes.has(e.from) && nodes.has(e.to)),
    [allEdges, nodes],
  )

  /** 每个源点一条横向车道：按 x 排号，0/1/2 循环，错开 4px。 */
  const laneOf = useMemo(() => {
    const src = [...new Set(edges.map((e) => e.from))]
      .sort((a, b) => (layout.pos.get(a)?.x || 0) - (layout.pos.get(b)?.x || 0))
    return new Map(src.map((id, i) => [id, i]))
  }, [edges, layout])

  /** 适配画面：按容器宽度算缩放，别让用户一进来只看到左上角。 */
  const fit = () => {
    const el = wrapRef.current
    if (!el) return
    const w = el.clientWidth - 20
    const h = el.clientHeight - 20
    const z = Math.min(1.05, Math.max(0.5, Math.min(w / layout.width, h / layout.height)))
    setZoom(+z.toFixed(2))
  }
  useLayoutEffect(() => { fit() /* eslint-disable-next-line react-hooks/exhaustive-deps */ },
    [layout.width, layout.height])

  const focus = hover || sel
  const near = (e: GEdge) => e.from === focus || e.to === focus
  const zoomTo = (z: number) => setZoom(+Math.min(1.8, Math.max(0.35, z)).toFixed(2))

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      {/* 画布 */}
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-[var(--radius-card)]
                      border border-border bg-surface shadow-[var(--shadow-card)]">
        <div className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded-lg border
                        border-border bg-surface/90 px-1 py-0.5 backdrop-blur">
          <button onClick={() => zoomTo(zoom - 0.15)} className="icon-btn h-6 w-6" title="缩小">
            <Minus size={13} />
          </button>
          <span className="tnum w-9 text-center text-[10.5px] text-ink-faint">{Math.round(zoom * 100)}%</span>
          <button onClick={() => zoomTo(zoom + 0.15)} className="icon-btn h-6 w-6" title="放大">
            <Plus size={13} />
          </button>
          <button onClick={fit} className="icon-btn h-6 w-6" title="适配画面">
            <Maximize2 size={12} />
          </button>
          <button onClick={() => { setZoom(1); onReset() }} className="icon-btn h-6 w-6" title="回到中心">
            <RefreshCw size={12} />
          </button>
        </div>

        {/* 不要 justify-center：图比容器宽时 flex 居中会把左右两头都裁掉，
            滚也滚不到起点。改成 mx-auto：装得下居中，装不下从左边开始滚。 */}
        <div ref={wrapRef} className="flex h-full items-center overflow-auto p-2">
          <svg width={layout.width * zoom} height={layout.height * zoom}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            className="mx-auto block max-h-none select-none">
            {edges.map((e) => {
              const a = layout.pos.get(e.from)!
              const b = layout.pos.get(e.to)!
              const kind = KIND_OF(e)
              const x1 = a.x + NW / 2, y1 = a.y + NH
              const x2 = b.x + NW / 2, y2 = b.y
              const on = near(e)
              // 源点按 x 排个号，给每个源点一条独立车道（0/4/8 px），
              // 这样几条总线不会完全重合，还能看出"哪一根连着谁"。
              const lane = (laneOf.get(e.from) || 0) % 3 * 4
              const busAbove = kind === 'order' ? 20 : 9 + lane
              const stroke = on
                ? (kind === 'hard' ? 'var(--color-brand)' : kind === 'order' ? 'var(--color-ink-faint)' : 'var(--color-violet)')
                : 'var(--color-ink-faint)'
              return (
                <path key={`${e.from}-${e.to}-${e.kind}`}
                  d={wirePath(x1, y1, x2, y2, busAbove)}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={kind === 'order' ? 1 : on ? 1.45 : 1.1}
                  strokeDasharray={kind === 'hard' ? undefined : kind === 'order' ? '1.5 3.5' : '4 3'}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={kind === 'order'
                    ? (on ? 0.42 : 0.2)
                    : focus ? (on ? 0.85 : 0.26) : (kind === 'hard' ? 0.5 : 0.38)} />
              )
            })}

            {[...nodes].map((id) => {
              const p = layout.pos.get(id)!
              const on = id === sel
              const hot = id === hover
              const tone = TONE[toneOf(id)] || TONE.h
              const t = titleOf(id)
              const lines = splitTitle(t)
              const mastered = known.has(id)
              const dim = gapOnly && isGap ? !isGap(id) : false
              return (
                <g key={id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer"
                  opacity={dim ? 0.2 : 1}
                  onClick={() => onSelect(id)}
                  onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
                  <title>{t}</title>
                  <rect width={NW} height={NH} rx={8}
                    fill={on ? 'var(--color-brand-soft)' : tone.bg}
                    stroke={on ? 'var(--color-brand)' : tone.border}
                    strokeWidth={on ? 2.6 : hot ? 2 : 1.3} />
                  {mastered && (
                    <path d={`M ${NW - 17} 9 l 2.6 2.6 l 4.6 -4.8`}
                      fill="none" stroke="var(--color-has)" strokeWidth={1.5}
                      strokeLinecap="round" strokeLinejoin="round" />
                  )}
                  {lines.length === 1 ? (
                    <text x={NW / 2} y={NH / 2 + 4} textAnchor="middle"
                      fontSize={11.5} fontWeight={on ? 600 : 500}
                      fill="var(--color-ink)">{lines[0]}</text>
                  ) : (
                    <>
                      <text x={NW / 2} y={NH / 2 - 5} textAnchor="middle"
                        fontSize={11.5} fontWeight={on ? 600 : 500}
                        fill="var(--color-ink)">{lines[0]}</text>
                      <text x={NW / 2} y={NH / 2 + 11} textAnchor="middle"
                        fontSize={11.5} fontWeight={on ? 600 : 500}
                        fill="var(--color-ink)">{lines[1]}</text>
                    </>
                  )}
                </g>
              )
            })}
          </svg>
        </div>
      </div>

      {/* 图例 + 统计：和参考项目底部那行一个作用 */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[10.5px] text-ink-faint">
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-[3px] border"
          style={{ background: TONE.p.bg, borderColor: TONE.p.border }} />小学</span>
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-[3px] border"
          style={{ background: TONE.j.bg, borderColor: TONE.j.border }} />初中</span>
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-[3px] border"
          style={{ background: TONE.h.bg, borderColor: TONE.h.border }} />高中</span>
        <span className="flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-[3px] border-2"
          style={{ background: 'var(--color-brand-soft)', borderColor: 'var(--color-brand)' }} />当前</span>
        <span className="inline-block h-[2px] w-4 rounded bg-brand" />硬先修（实线）
        <span className="inline-block h-[2px] w-4 rounded border-t border-dashed border-violet" />有帮助（虚线）
        <span className="inline-block h-[2px] w-4 rounded border-t border-dotted border-ink-faint" />教材顺序（点线）
        <span className="ml-auto">
          局部图 {nodes.size} 个知识点、{edges.length} 条关系。
          向上 {upDepth === Infinity ? '全部' : `${upDepth} 层`}，向下 {downDepth} 层 · 点节点换中心
        </span>
      </div>
    </div>
  )
}
