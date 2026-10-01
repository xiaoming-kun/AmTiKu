/** 知识链路 —— 考点之间的**先修关系图**。
 *
 *  为什么要独立一页：知识点库只有「树」（大类 → 节 → 考点），答不出
 *  「我 4.3.1 不会，该先补什么」。这里补的就是**边**。
 *
 *  三条设计决定（见 设计/知识链路.md）：
 *  ① **X 轴 = 10 个大类，Y 轴 = hard 边的拓扑深度**。
 *     横向换领域、纵向由浅入深，和 math-tree 的「径向 = 领域、
 *     由内到外 = 学习顺序」是同一套信息结构，但 SVG 手绘就够，
 *     不必为一张图引入 vis-network（math-tree 为此背了 688KB vendor）。
 *  ② **节点不落盘**：id/名称/星级现取自知识点库，本页只画后端给的边。
 *  ③ **掌握度只存 localStorage**，不写进题库数据——那是学习者私有状态，
 *     写进 知识链路.json 就变成多人共用一个进度了。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Crosshair, Loader2, Lock, Route, Search, ShieldAlert, Sparkles, X } from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import { Chip, useFlag } from '@/app/ui'
import { Ego } from '@/app/Ego'

type GNode = {
  id: string; title: string; stars: number; difficulty: string
  topic: string; section: string; depth: number
  n_pre: number; n_post: number; n: number
}
type Edge = { pre: string; post: string; strength: 'hard' | 'soft'; reason: string }
type Graph = {
  version: number; updated: string; drafted: string
  nodes: GNode[]; edges: Edge[]; stats: Record<string, number>
  errors: { code: string; msg: string }[]
}

const LS_KEY = 'amti.chain.mastered'

/** 10 个大类的颜色。挑的是**在白底上都够深**的一组，不用浅色——
 *  浅色描边在小圆角节点上分不出大类。 */
const TOPIC_COLORS = ['#2563eb', '#7c3aed', '#0891b2', '#059669', '#d97706',
  '#dc2626', '#db2777', '#65a30d', '#4f46e5', '#0d9488']

/* 布局常量。
 * 默认**只画 10 个章节卡片**，点开的章节才在它下面长出考点——这是「探索」的核心：
 * 152 个考点 + 315 条边一次全铺出来必然是毛线球（用户截图里那团就是），
 * 而一屏 10 个大节点永远清爽，关系靠「点开一层」逐级展开。 */
const CHAP_W = 168, CHAP_W_OPEN = 186, GAP = 44, PAD = 24
/** 底部总线：跨多列的长边走它，而不是斜着从别的节点身上碾过去 */
const BUS_GAP = 34
const ROW = 24, NODE_W = 48, NODE_H = 18, HEAD = 50
/** 章节卡片的高度；卡片排在一条基线上，**关系弧画在基线上方、展开的考点长在下方**。
 *  早先把展开的列从 y=92 往下排、卡片却钉在 y=300，列直接穿过卡片（用户说的"穿模"）。 */
const CARD_H = 66, BASELINE = 300
/** 深度分层之间留一点空隙：同一深度是一"带"，带与带之间断开，深度才读得出来 */
const BAND_GAP = 9

type Pos = { x: number; y: number; col: number }
type View = { k: number; tx: number; ty: number }

export function Chain({ onPickPoint }: { onPickPoint: (pid: string, title: string) => void }) {
  const [g, setG] = useState<Graph | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState('')
  const [hover, setHover] = useState('')
  const [hardOnly, setHardOnly] = useFlag('amti.chain.hardonly', false)
  const [view, setView] = useState<View>({ k: 1, tx: 0, ty: 0 })
  const [fitNonce, setFitNonce] = useState(0)
  const [q, setQ] = useState('')
  const [audit, setAudit] = useState<any>(null)
  const [showAudit, setShowAudit] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)

  // 掌握度：localStorage。**只影响画法，不改任何题库数据。**
  const [mastered, setMastered] = useState<Set<string>>(() => {
    try { return new Set<string>(JSON.parse(localStorage.getItem(LS_KEY) || '[]')) }
    catch { return new Set<string>() }
  })
  useEffect(() => { localStorage.setItem(LS_KEY, JSON.stringify([...mastered])) }, [mastered])

  useEffect(() => {
    api.chain().then(setG).catch((e) => { setErr(String(e.message || e)); reportErr(e) })
  }, [])

  /* ── 派生：邻接、列、坐标 ───────────────────────────── */
  const pre = useMemo(() => {
    const m = new Map<string, Edge[]>()
    for (const e of g?.edges || []) {
      const a = m.get(e.post) || []; a.push(e); m.set(e.post, a)
    }
    return m
  }, [g])

  /** 展开的章节。默认空 = 只看 10 个大节点。 */
  const [open, setOpen] = useState<Set<string>>(new Set())

  const { chaps, pos, W, H, topicOf, busY } = useMemo(() => {
    const groups: { topic: string; color: string; nodes: GNode[] }[] = []
    for (const n of g?.nodes || []) {
      let c = groups.find((x) => x.topic === n.topic)
      if (!c) { c = { topic: n.topic, color: TOPIC_COLORS[groups.length % 10], nodes: [] }; groups.push(c) }
      c.nodes.push(n)
    }
    // 列内先按 hard 深度（由浅到深），同深度保持知识点库原顺序：
    // 这样「从上往下 = 越来越浅→深」在章节内部也成立。
    for (const c of groups) {
      c.nodes = c.nodes.map((n, i) => ({ n, i }))
        .sort((a, b) => a.n.depth - b.n.depth || a.i - b.i).map((x) => x.n)
    }
    const maxRows = Math.max(0, ...groups.filter((c) => open.has(c.topic)).map((c) => c.nodes.length))
    const height = Math.max(BASELINE + CARD_H + 40,
      BASELINE + CARD_H + 24 + maxRows * ROW + maxRows * BAND_GAP + BUS_GAP + 30)
    let x = PAD
    const chaps = groups.map((c) => {
      const isOpen = open.has(c.topic)
      const w = isOpen ? CHAP_W_OPEN : CHAP_W
      const o = { topic: c.topic, color: c.color, nodes: c.nodes, open: isOpen, x, w,
        y: BASELINE, questions: c.nodes.reduce((a, n) => a + n.n, 0) }
      x += w + GAP
      return o
    })

    /* ── 层内排序：交叉最小化（Sugiyama 三件套里的第二件）──
     *  规则：**深度仍是主序**（"纵向 = 由浅入深"是这张图的读图约定，不能被优化掉），
     *  同一深度内的先后则用**邻居位置的中位数**决定，来回扫描几轮。
     *  这一步盯的是「同一深度带里谁上谁下」——原来用知识点库顺序，
     *  等于没做交叉最小化，边只能互相穿。
     *  参考：Sugiyama 高效实现（Healy & Nikolov）/ dagre 的 ordering 阶段 / d3-dag 的 decross。 */
    const idx = new Map<string, number>()
    for (const c of chaps) for (const n of c.nodes) idx.set(n.id, chaps.indexOf(c))
    const adj = new Map<string, string[]>()
    for (const e of (g?.edges || [])) {
      if (!adj.has(e.pre)) adj.set(e.pre, [])
      if (!adj.has(e.post)) adj.set(e.post, [])
      adj.get(e.pre)!.push(e.post)
      adj.get(e.post)!.push(e.pre)
    }
    const rank = new Map<string, number>()          // 节点在它所在列里的序号
    for (const c of chaps) c.nodes.forEach((n, i) => rank.set(n.id, i))
    const medianOf = (id: string) => {
      const ns = (adj.get(id) || []).filter((t) => (idx.get(t) ?? -1) !== idx.get(id))
      if (!ns.length) return null
      const v = ns.map((t) => rank.get(t) ?? 0).sort((a, b) => a - b)
      const m = v.length >> 1
      return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2
    }
    for (let sweep = 0; sweep < 6; sweep++) {
      for (const c of [...chaps].sort((a, b) => sweep % 2 ? b.x - a.x : a.x - b.x)) {
        c.nodes = c.nodes.map((n, i) => ({ n, i,
          k: [n.depth, medianOf(n.id) ?? Number.MAX_SAFE_INTEGER, i] as (number | string)[] }))
          .sort((a, b) => (a.k[0] as number) - (b.k[0] as number)
            || (a.k[1] as number) - (b.k[1] as number) || (a.i - b.i))
          .map((o) => o.n)
        c.nodes.forEach((n, i) => rank.set(n.id, i))
      }
    }

    let maxBand = 0
    for (const c of chaps) maxBand = Math.max(maxBand, new Set(c.nodes.map((n) => n.depth)).size)
    const pos = new Map<string, Pos>()
    let lowest = 0
    chaps.forEach((c, ci) => {
      if (!c.open) return
      let lastDepth = -1, band = 0
      c.nodes.forEach((n, ri) => {
        if (n.depth !== lastDepth) { band += 1; lastDepth = n.depth }
        const y = BASELINE + CARD_H + 24 + (ri + band) * ROW + band * BAND_GAP
        lowest = Math.max(lowest, y)
        pos.set(n.id, { x: c.x + NODE_W / 2 + 8, y, col: ci })
      })
    })
    // 底部总线的高度：所有展开列的最底端再往下一点。
    // 长边全部走这条线，并按边序分 5 条车道错开（同一条线上会互相盖住）。
    const busY = lowest + BUS_GAP
    const topicOf = new Map<string, string>()
    for (const n of g?.nodes || []) topicOf.set(n.id, n.topic)
    return { chaps, pos, W: x - GAP + PAD, H: height, topicOf, busY }
  }, [g, open])

  const chapOf = useMemo(() => new Map(chaps.map((c) => [c.topic, c])), [chaps])
  const chapIdx = useCallback((t: string) => chaps.findIndex((c) => c.topic === t), [chaps])

  const edges = useMemo(() => {
    const all = g?.edges || []
    return hardOnly ? all.filter((e) => e.strength === 'hard') : all
  }, [g, hardOnly])

  /** 关系数据。渲染策略是**分级显示**（ELK 的 long-edge 策略同理）：
   *  ① 章节弧：永远画——它是这张图的骨架，也是"这一章和那一章有几条关系"的答案；
   *  ② 同一章内部的节点级边：展开就画（那是用户点开这一章想看的东西）；
   *  ③ **跨章的节点级边：默认不画**。它们原来就是"斜着掠过 7 列"的元凶；
   *     悬停/选中某个考点时，只把它自己的那些边单独画出来。
   *  结果是：无论展开多少章，屏幕上的线永远是一小把，而不是 315 条。 */
  const { pairAgg, nodeEdges, crossEdges } = useMemo(() => {
    const m = new Map<string, { a: string; b: string; hard: number; soft: number }>()
    const nodeEdges: Edge[] = []
    const crossEdges: (Edge & { a: string; b: string })[] = []
    for (const e of edges) {
      const ta = topicOf.get(e.pre) || '', tb = topicOf.get(e.post) || ''
      const oa = open.has(ta), ob = open.has(tb)
      const k = ta + '>' + tb
      const cur = m.get(k) || { a: ta, b: tb, hard: 0, soft: 0 }
      cur[e.strength === 'hard' ? 'hard' : 'soft'] += 1
      m.set(k, cur)
      if (oa && ob) nodeEdges.push(e)
      else if (oa || ob) crossEdges.push({ ...e, a: ta, b: tb })
    }
    return { pairAgg: [...m.values()], nodeEdges, crossEdges }
  }, [edges, open, topicOf])

  /** 章节级的入/出条数：收起的卡片上直接写出来，不用点开就知道谁依赖谁 */
  const chapDeg = useMemo(() => {
    const m = new Map<string, { i: number; o: number }>()
    for (const a of pairAgg) {
      const A = m.get(a.a) || { i: 0, o: 0 }, B = m.get(a.b) || { i: 0, o: 0 }
      A.o += a.hard + a.soft; B.i += a.hard + a.soft
      m.set(a.a, A); m.set(a.b, B)
    }
    return m
  }, [pairAgg])

  /** 选中考点的**整条链路**（全部先修 + 全部后续）。
   *  探索的关键：链路会穿过还没展开的章节，那些就画成高亮的聚合边——
   *  顺着亮线点开对应章节，就是一步一步把这条链走出来。 */
  const chain = useMemo(() => {
    if (!sel) return null
    const up = new Set([sel]), down = new Set([sel])
    const walk = (dir: 'up' | 'down', acc: Set<string>) => {
      const stack = [sel]
      while (stack.length) {
        const cur = stack.pop()!
        for (const e of g?.edges || []) {
          const nxt = dir === 'up' ? (e.post === cur ? e.pre : '') : (e.pre === cur ? e.post : '')
          if (nxt && !acc.has(nxt)) { acc.add(nxt); stack.push(nxt) }
        }
      }
    }
    walk('up', up); walk('down', down)
    const upE = new Set<string>(), downE = new Set<string>()
    for (const e of g?.edges || []) {
      const k = e.pre + '>' + e.post
      if (up.has(e.pre) && up.has(e.post)) upE.add(k)
      if (down.has(e.pre) && down.has(e.post)) downE.add(k)
    }
    const topics = new Set<string>()
    for (const id of [...up, ...down]) { const t = topicOf.get(id); if (t) topics.add(t) }
    return { up, down, upE, downE, topics }
  }, [sel, g, topicOf])

  /** 要点名画出来的跨章边：悬停/选中的那一跳，以及选中考点的整条链路 */
  const incident = useMemo(() => {
    const s2 = new Set<string>()
    if (chain) { for (const k of chain.upE) s2.add(k); for (const k of chain.downE) s2.add(k) }
    const f = hover || sel
    if (f) for (const e of edges) if (e.pre === f || e.post === f) s2.add(e.pre + '>' + e.post)
    return s2
  }, [chain, hover, sel, edges])


  const topicColor = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of chaps) m.set(c.topic, c.color)
    return m
  }, [chaps])

  /* 适配画布大小。
   *
   *  ① 初次载入「刚好放下」：10 列宽约 1570px，比大多数窗口宽，不缩的话
   *     一进来只看到左边几个大类，会以为图就这么多。
   *  ② 之后**只在放不下时才缩**——右侧详情面板一打开画布就变窄，
   *     不重算的话最右两三个大类会被挤出可视区（截图里实测到了）。
   *     放得下时一律不动，免得把用户自己放大/平移好的视图顶掉。 */
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const fit = (v: View, reset: boolean): View => {
      const cw = el.clientWidth - 16, ch = el.clientHeight - 16
      if (cw <= 60 || ch <= 60) return v
      const k = Math.max(0.35, Math.min(reset ? 1 : v.k, cw / W, ch / H))
      // 竖直方向居中：图是「宽受限」的，下面留一大片空白比顶到上边好看
      return { k, tx: 8, ty: Math.max(8, (el.clientHeight - H * k) / 2) }
    }
    setView((v) => fit(v, true))
    const ro = new ResizeObserver(() => setView((v) => {
      if (W * v.k <= el.clientWidth - 16 && H * v.k <= el.clientHeight - 16) return v
      return fit(v, false)
    }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [W, H, fitNonce])

  /** 硬性前置没全点亮 → 未解锁。这是 math-tree 那个解锁机制的等价物，
   *  只是在浏览器里算，不动数据。 */
  const locked = useCallback((id: string) => {
    if (mastered.has(id)) return false
    return (pre.get(id) || []).some((e) => e.strength === 'hard' && !mastered.has(e.pre))
  }, [pre, mastered])

  /* 高亮：鼠标悬停优先于选中。只亮「前后各一跳」，再多就看不清了。 */
  const focus = hover || sel
  const near = useMemo(() => {
    if (!focus) return null
    const s = new Set<string>([focus])
    for (const e of g?.edges || []) {
      if (e.pre === focus) s.add(e.post)
      if (e.post === focus) s.add(e.pre)
    }
    return s
  }, [focus, g])

  const hit = useMemo(() => {
    const s = q.trim()
    if (!s) return []
    return (g?.nodes || []).filter((n) => n.title.includes(s) || n.id.startsWith(s)).slice(0, 8)
  }, [q, g])

  /* ── 视图操作 ───────────────────────────────────────── */
  const [pendingFocus, setPendingFocus] = useState('')
  const centerOn = (id: string) => {
    const t = g?.nodes.find((n) => n.id === id)?.topic
    if (t) setOpen((st) => { const x = new Set(st); x.add(t); return x })
    setPendingFocus(id)
  }
  useEffect(() => {
    if (!pendingFocus) return
    const q = pos.get(pendingFocus), el = wrap.current
    if (!q || !el) return
    setView((v) => ({ k: v.k, tx: el.clientWidth / 2 - q.x * v.k, ty: el.clientHeight / 2 - q.y * v.k }))
    setPendingFocus('')
  }, [pendingFocus, pos])

  // 滚轮缩放：**必须挂原生监听并 passive:false** —— React 的 onWheel 是被动的，
  // 在里面 preventDefault 会被浏览器忽略，页面会跟着一起滚。
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      const px = e.clientX - r.left, py = e.clientY - r.top
      setView((v) => {
        const k = Math.min(2.6, Math.max(0.35, v.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)))
        return { k, tx: px - (px - v.tx) * (k / v.k), ty: py - (py - v.ty) * (k / v.k) }
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [g])

  const drag = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null)
  const onDown = (e: React.PointerEvent) => {
    if ((e.target as Element).closest('[data-node]')) return
    drag.current = { x: e.clientX, y: e.clientY, tx: view.tx, ty: view.ty }
    ;(e.currentTarget as Element).setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return
    setView((v) => ({ ...v, tx: drag.current!.tx + (e.clientX - drag.current!.x),
      ty: drag.current!.ty + (e.clientY - drag.current!.y) }))
  }
  const onUp = () => { drag.current = null }

  const toggleMastered = (id: string) =>
    setMastered((s) => { const t = new Set(s); t.has(id) ? t.delete(id) : t.add(id); return t })

  const openAudit = () => {
    setShowAudit(true)
    if (!audit) api.chainAudit().then(setAudit).catch(reportErr)
  }

  if (err) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <ShieldAlert size={22} className="text-warn" />
        <span className="text-[12.5px] text-ink-soft">{err}</span>
      </div>
    )
  }
  if (!g) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-ink-faint">
        <Loader2 size={16} className="animate-spin" /> 正在读知识链路…
      </div>
    )
  }

  const st = g.stats || {}
  const on = g.nodes.filter((n) => mastered.has(n.id)).length
  const nIssue = (audit?.errors?.length || 0) + (audit?.warn?.length || 0)

  return (
    <div className="flex h-full min-h-0">
      {/* ── 左：图 ─────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 工具条 */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface
                        px-3.5 py-2">
          <span className="text-[12.5px] font-semibold">知识链路</span>
          <span className="text-[11px] text-ink-faint">
            <span className="tnum">{st.nodes}</span> 考点 ·
            <span className="tnum"> {st.edges}</span> 条边（硬 <span className="tnum">{st.hard}</span>
            / 软 <span className="tnum">{st.soft}</span>）·
            起点 <span className="tnum">{st.roots}</span> ·
            最深 <span className="tnum">{st.max_depth}</span> 层
          </span>
          <span className="relative">
            <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" />
            <input value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="找考点…"
              className="w-[150px] rounded-lg border border-border bg-surface-2 py-[3px] pl-6 pr-2
                         text-[12px] outline-none focus:border-brand-line focus:bg-surface" />
            {hit.length > 0 && (
              <div className="absolute left-0 top-[26px] z-30 w-[300px] overflow-hidden rounded-lg
                              border border-border bg-surface shadow-lg">
                {hit.map((n) => (
                  <button key={n.id}
                    onClick={() => { setSel(n.id); centerOn(n.id); setQ('') }}
                    className="flex w-full items-baseline gap-2 px-2.5 py-1.5 text-left hover:bg-brand-soft">
                    <span className="tnum shrink-0 text-[11px] text-brand-ink">{n.id}</span>
                    <span className="truncate text-[12px]">{n.title}</span>
                  </button>
                ))}
              </div>
            )}
          </span>
          <span className="min-w-0 flex-1" />
          <Chip size="sm" on={false} onClick={() => setOpen(new Set(chaps.map((c) => c.topic)))}
            title="一次看全 152 个考点——关系会显得很密，适合查覆盖，不适合读链路">
            展开全部</Chip>
          <Chip size="sm" on={false} onClick={() => setOpen(new Set())}
            title="回到 10 个大章节的目录视图">收起全部</Chip>
          <Chip size="sm" on={hardOnly} onClick={() => setHardOnly(!hardOnly)}
            title="软性前置只是「有帮助」，画上会显得链路很密">只看硬性前置</Chip>
          <Chip size="sm" on={false} onClick={() => setFitNonce((v) => v + 1)}
            title="缩放和平移回到初始状态">复位</Chip>
          <Chip size="sm" on={false} onClick={openAudit}
            title="环路 / 悬空 / 无理由边 / 待补清单">
            体检{nIssue ? ` ${nIssue}` : ''}
          </Chip>
          <span className="flex items-center gap-1 rounded-full border border-has-line bg-has-soft
                           px-2 py-[3px] text-[11.5px] text-has">
            <Sparkles size={11} /> 已点亮 <span className="tnum font-semibold">{on}</span>
            <span className="text-has/60">/{st.nodes}</span>
            {on > 0 && (
              <button onClick={() => setMastered(new Set())} title="清空本机进度"
                className="text-has/60 hover:text-has"><X size={11} /></button>
            )}
          </span>
        </div>

        {/* 画布。**只有这一种视图**：径向星空试过，放弃了——
            与浅色主题不搭、常驻 60fps 重绘白耗电，而精读仍旧要靠侧栏的局部链路图
            （决策与证据见 设计/知识链路.md「视图选型」）。 */}
        <div ref={wrap} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
          className="relative min-h-0 flex-1 cursor-grab overflow-hidden bg-surface-2 active:cursor-grabbing">
          <svg width="100%" height="100%" className="select-none">
            <g transform={`translate(${view.tx},${view.ty}) scale(${view.k})`}>
              {/* 章节卡片：默认只有它。点一下展开/收起它的考点。 */}
              {chaps.map((c) => {
                const hidden = false
                const deg2 = chapDeg.get(c.topic) || { i: 0, o: 0 }
                const h = c.open ? HEAD - 6 : 60
                return (
                  <g key={c.topic} data-node className="cursor-pointer"
                    onClick={(ev) => {
                      ev.stopPropagation()
                      setOpen((st) => { const t = new Set(st); t.has(c.topic) ? t.delete(c.topic) : t.add(c.topic); return t })
                    }}>
                    <rect x={c.x} y={c.y} width={c.w} height={h} rx={8}
                      fill={hidden ? '#f8fafc' : c.color + '14'}
                      stroke={hidden ? '#e2e8f0' : c.color + (c.open ? '99' : '55')}
                      strokeWidth={c.open ? 1.6 : 1.2} />
                    <text x={c.x + 10} y={c.y + 18} fontSize={12.5} fontWeight={700}
                      fill={hidden ? '#94a3b8' : c.color}>
                      {(c.open ? '▾ ' : '▸ ') + c.topic.replace(/^[一二三四五六七八九十]+、/, '')}
                    </text>
                    <text x={c.x + c.w - 10} y={c.y + 18} fontSize={10.5} textAnchor="end" fill="#94a3b8"
                      className="tnum">{c.nodes.length} 考点</text>
                    {!c.open && (
                      <>
                        <text x={c.x + 10} y={c.y + 36} fontSize={10.5} fill="#64748b" className="tnum">
                          {c.questions} 道题
                        </text>
                        {/* 章节级的入/出条数：不点开也知道它跟谁有牵连 */}
                        <text x={c.x + 10} y={c.y + 51} fontSize={10.5} fill="#94a3b8" className="tnum">
                          入 {deg2.i} · 出 {deg2.o}
                        </text>
                      </>
                    )}
                  </g>
                )
              })}

              {/* 边。**先画边后画节点**，否则线会盖在节点上。分三层画：
                  聚合 → 跨层细线 → 节点级，越靠下的越具体。 */}
              {/* ① 章节级聚合边：弧图（arc diagram）。
                  节点横排一行，关系画成上方的弧，**弧高按跨了几列递增**：
                  相邻章是小拱、首尾章是大拱，彼此嵌套而不打架。
                  早先按"条数"定弧高 → 所有弧都往天上冲、交叉成一团。 */}
              {[...pairAgg].sort((p1, p2) =>
                (chapIdx(p1.a) - chapIdx(p1.b)) ** 2 - (chapIdx(p2.a) - chapIdx(p2.b)) ** 2
                || p1.a.localeCompare(p2.a)).map((a2) => {
                const A = chapOf.get(a2.a), B = chapOf.get(a2.b)
                if (!A || !B) return null
                const n = a2.hard + a2.soft
                const i = chapIdx(a2.a), j = chapIdx(a2.b)
                const span = Math.abs(i - j)
                const x1 = A.x + A.w / 2, x2 = B.x + B.w / 2
                const y = BASELINE
                const h = 34 + span * 20
                const mx = (x1 + x2) / 2, my = y - h
                const litUp = chain && chain.up.has(a2.a) && chain.up.has(a2.b)
                const litDown = chain && chain.down.has(a2.a) && chain.down.has(a2.b)
                const hot = litUp || litDown
                const col = litUp ? '#0e7490' : litDown ? '#db2777' : a2.hard ? '#94a3b8' : '#cbd5e1'
                return (
                  <g key={a2.a + '>' + a2.b} className="transition-opacity duration-200"
                    opacity={hot ? 1 : chain ? 0.25 : n === 1 ? 0.45 : 0.9}>
                    <path d={`M ${x1} ${y} Q ${mx} ${y - h * 2}, ${x2} ${y}`} fill="none"
                      stroke={col} strokeWidth={hot ? 2.6 : 0.9 + Math.sqrt(n) * 0.75}
                      strokeDasharray={!a2.hard ? '4 3' : undefined} markerEnd="url(#ahg)" />
                    {/* 徽标只在条数 ≥2 时画：40 多条边全挂数字，数字本身就成了噪声 */}
                    {n >= 2 && (
                      <g transform={`translate(${mx},${my - 9})`}>
                        <rect x={-13} y={-9} width={26} height={17} rx={8.5} fill="#fff"
                          stroke={col} strokeWidth={hot ? 1.6 : 1} />
                        <text x={0} y={3.5} fontSize={10.5} textAnchor="middle" className="tnum"
                          fill={litUp ? '#0e7490' : litDown ? '#be185d' : '#64748b'}>{n}</text>
                      </g>
                    )}
                  </g>
                )
              })}

              {/* ② 一端展开、一端收起：细线连过去。看得出"这一章的哪些考点通向那一章" */}
              {crossEdges.map((e, i) => {
                if (!incident.has(e.pre + '>' + e.post)) return null
                const p1 = pos.get(e.pre), p2 = pos.get(e.post)
                const A = chapOf.get(e.a), B = chapOf.get(e.b)
                if (!A || !B) return null
                const from = p1 ? { x: p1.x + NODE_W / 2, y: p1.y } : { x: A.x + A.w / 2, y: A.y + 34 }
                const to = p2 ? { x: p2.x - NODE_W / 2, y: p2.y } : { x: B.x + B.w / 2, y: B.y + 34 }
                const lit = chain && (chain.upE.has(e.pre + '>' + e.post) || chain.downE.has(e.pre + '>' + e.post))
                const hidden = false
                return (
                  <path key={'x' + i} fill="none" className="transition-opacity duration-200"
                    d={`M ${from.x} ${from.y} C ${(from.x + to.x) / 2} ${from.y}, ` +
                       `${(from.x + to.x) / 2} ${to.y}, ${to.x} ${to.y}`}
                    stroke={lit ? (chain!.upE.has(e.pre + '>' + e.post) ? '#0e7490' : '#db2777')
                      : e.strength === 'hard' ? '#cbd5e1' : '#e2e8f0'}
                    strokeWidth={lit ? 2 : 1}
                    strokeDasharray={e.strength === 'soft' && !lit ? '3 2.5' : undefined}
                    opacity={hidden ? 0.04 : lit ? 1 : chain ? 0.12 : 0.5} />
                )
              })}

              {/* ③ 两端都展开：节点级边（原来的画法） */}
              {nodeEdges.map((e, i) => {
                const p1 = pos.get(e.pre), p2 = pos.get(e.post)
                if (!p1 || !p2) return null
                // 同章内部：展开就给看。跨章：只有被点名（悬停/选中/链路）才画
                const sameChap = p1.col === p2.col
                if (!sameChap && !incident.has(e.pre + '>' + e.post)) return null
                const lit = chain && (chain.upE.has(e.pre + '>' + e.post) || chain.downE.has(e.pre + '>' + e.post))
                const hot = hover && near && near.has(e.pre) && near.has(e.post)
                const right = p2.col >= p1.col
                const sameCol = p2.col === p1.col
                // 同列的边**一律从左侧出、往左鼓**：左侧是列间空隙（GAP 44），
                // 右侧是标签文字区。早先这里漏了同列的情形——从左边起笔却往右鼓，
                // 弧线等于横穿自己的节点框（探针把起始点判在框边界上才发现）。
                const x1 = sameCol ? p1.x - NODE_W / 2 : p1.x + (right ? NODE_W / 2 : -NODE_W / 2)
                const x2 = sameCol ? p2.x - NODE_W / 2 : p2.x + (right ? -NODE_W / 2 : NODE_W / 2)
                let d: string
                const A2 = chaps[p1.col], B2 = chaps[p2.col]
                const span = Math.abs(p2.col - p1.col)
                if (sameCol) {
                  const r = -(14 + Math.abs(p2.y - p1.y) * 0.22)     // 负号 = 往左鼓
                  d = `M ${x1} ${p1.y} C ${x1 + r} ${p1.y}, ${x1 + r} ${p2.y}, ${x1} ${p2.y}`
                } else if (span === 1) {
                  // 相邻两列：直接走，跨不过任何别的列
                  const dx = Math.max(18, (x2 - x1) * 0.45)
                  d = `M ${x1} ${p1.y} C ${x1 + dx} ${p1.y}, ${x2 - dx} ${p2.y}, ${x2} ${p2.y}`
                } else {
                  /* **跨两列以上：走底部总线**（正交走线 + 圆角）。
                     直线/斜贝塞尔会从中间那些列的节点身上碾过去 —— 那就是"穿模"。
                     走廊取本列右侧的间隙，竖直段因此也不压同列的其它节点。 */
                  const right = p2.col > p1.col
                  const gA = right ? A2.x + A2.w + GAP * 0.4 : A2.x - GAP * 0.4
                  const gB = right ? B2.x - GAP * 0.4 : B2.x + B2.w + GAP * 0.4
                  const lane = busY + (i % 5) * 7
                  const r0 = 9
                  d = `M ${x1} ${p1.y} L ${gA - r0} ${p1.y} Q ${gA} ${p1.y} ${gA} ${p1.y + r0}` +
                    ` L ${gA} ${lane - r0} Q ${gA} ${lane} ${gA + r0} ${lane}` +
                    ` L ${gB - r0} ${lane} Q ${gB} ${lane} ${gB} ${lane - r0}` +
                    ` L ${gB} ${p2.y + r0} Q ${gB} ${p2.y} ${gB - r0} ${p2.y}` +
                    ` L ${x2} ${p2.y}`
                }
                return (
                  <path key={i} d={d} fill="none" className="transition-opacity duration-200"
                    stroke={lit ? (chain!.upE.has(e.pre + '>' + e.post) ? '#0e7490' : '#db2777')
                      : hot ? '#db2777' : e.strength === 'hard' ? '#94a3b8' : '#cbd5e1'}
                    strokeWidth={lit || hot ? 2.2 : e.strength === 'hard' ? 1.4 : 1}
                    strokeDasharray={e.strength === 'soft' && !lit && !hot ? '3 2.5' : undefined}
                    markerEnd={lit || hot || e.strength === 'hard' ? 'url(#ah)' : undefined}
                    opacity={chain && !lit ? 0.12 : hover && !hot && !lit ? 0.2 : 1} />
                )
              })}

              {/* ④ 节点：只在展开的章节里出现 */}
              {g.nodes.map((n) => {
                const p = pos.get(n.id)
                if (!p) return null
                const c = topicColor.get(n.topic) || '#64748b'
                const lk = locked(n.id), mk = mastered.has(n.id)
                const inChain = chain ? (chain.up.has(n.id) || chain.down.has(n.id)) : true
                const dim = chain ? !inChain : hover && near ? !near.has(n.id) : false
                const isSel = sel === n.id
                return (
                  <g key={n.id} data-node transform={`translate(${p.x - NODE_W / 2},${p.y - NODE_H / 2})`}
                    opacity={dim ? (chain ? 0.16 : 0.3) : 1}
                    className="cursor-pointer transition-opacity duration-200"
                    onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover('')}
                    onClick={(ev) => { ev.stopPropagation(); setSel(n.id) }}>
                    <title>{`${n.id} ${n.title}\n★${n.stars} · ${n.difficulty} · ${n.n} 道题`}</title>
                    <rect width={NODE_W} height={NODE_H} rx={5}
                      fill={mk ? c : lk ? '#f1f5f9' : '#ffffff'}
                      stroke={isSel ? '#db2777' : chain && chain.up.has(n.id) ? '#0e7490'
                        : chain && chain.down.has(n.id) ? '#db2777' : mk ? c : lk ? '#e2e8f0' : c}
                      strokeWidth={isSel ? 2.4 : 1.2} />
                    <text x={NODE_W / 2} y={12.5} fontSize={10.5} textAnchor="middle"
                      className="tnum" fill={mk ? '#fff' : lk ? '#94a3b8' : '#334155'}>
                      {n.id}
                    </text>
                    {lk && <circle cx={NODE_W - 4} cy={4} r={3} fill="#cbd5e1" />}
                    <text x={NODE_W + 5} y={12.5} fontSize={9.5} fill={lk ? '#a8b3c2' : '#64748b'}>
                      {n.title.length > 9 ? n.title.slice(0, 9) + '…' : n.title}
                    </text>
                  </g>
                )
              })}
            </g>
            <defs>
              <marker id="ah" viewBox="0 0 8 8" refX="7" refY="4"
                markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 8 4 L 0 8 z" fill="#db2777" />
              </marker>
              <marker id="ahg" viewBox="0 0 8 8" refX="7" refY="4"
                markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 8 4 L 0 8 z" fill="#94a3b8" />
              </marker>
            </defs>
          </svg>

          <div className="pointer-events-none absolute bottom-2.5 left-3 flex items-center gap-3
                          rounded-lg bg-surface/85 px-2.5 py-1 text-[10.5px] text-ink-faint">
            <span>点章节卡片展开它的考点 · 点考点看右侧局部链路 · 拖拽平移 · 滚轮缩放</span>
            <span className="flex items-center gap-1">
              <svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="#94a3b8" strokeWidth="1.6" /></svg>
              硬性前置
            </span>
            <span className="flex items-center gap-1">
              <svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="#cbd5e1"
                strokeWidth="1.2" strokeDasharray="3 2.5" /></svg>
              软性（有帮助）
            </span>
          </div>

          <div className="pointer-events-none absolute bottom-2.5 right-3 rounded-lg bg-surface/85
                          px-2.5 py-1 text-[10.5px] text-ink-faint">
            实心 = 已点亮 · 灰底 <Lock size={9} className="inline" /> = 硬性前置还没点亮
          </div>
        </div>
      </div>

      {/* ── 右：详情 ───────────────────────────────── */}
      {sel && <Detail id={sel} onPick={onPickPoint} onJump={(id) => { setSel(id); centerOn(id) }}
        mastered={mastered.has(sel)} onToggle={() => toggleMastered(sel)}
        onClose={() => setSel('')} locked={locked(sel)}
        nChap={chain ? chain.topics.size : 1}
        onExpand={() => chain && setOpen((st) => new Set([...st, ...chain.topics]))} />}

      {/* ── 体检抽屉 ───────────────────────────────── */}
      {showAudit && (
        <Audit data={audit} onClose={() => setShowAudit(false)}
          onJump={(id) => { setSel(id); centerOn(id); centerOn(id) }} />
      )}
    </div>
  )
}

/* ══ 侧栏详情 ══════════════════════════════════════ */

function Detail({ id, onPick, onJump, mastered, onToggle, onClose, locked, onExpand, nChap }: {
  id: string; onPick: (pid: string, title: string) => void; onJump: (pid: string) => void
  mastered: boolean; onToggle: () => void; onClose: () => void; locked: boolean
  /** 展开这条链路经过的所有章节（探索的入口：把路径一次铺出来） */
  onExpand: () => void; nChap: number
}) {
  const [d, setD] = useState<any>(null)
  const [open, setOpen] = useState(true)

  useEffect(() => {
    setD(null)
    api.chainNode(id).then(setD).catch(reportErr)
  }, [id])

  const Row = ({ e, dir }: { e: any; dir: 'pre' | 'post' }) => {
    const other = dir === 'pre' ? e.pre : e.post
    return (
      <button onClick={() => onJump(other)}
        className="group flex w-full items-start gap-2 rounded-lg px-1.5 py-1 text-left hover:bg-brand-soft">
        <span className={`mt-[3px] shrink-0 rounded px-1 py-[1px] text-[9.5px] font-medium ${
          e.strength === 'hard' ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-faint'}`}>
          {e.strength === 'hard' ? '硬' : '软'}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-1.5">
            <span className="tnum shrink-0 text-[11px] text-brand-ink">{other}</span>
            <span className="truncate text-[12px] text-ink group-hover:text-brand-ink">{e.title}</span>
          </span>
          <span className="block truncate text-[10.5px] text-ink-faint" title={e.reason}>
            {e.reason}
          </span>
        </span>
        <span className="tnum mt-[3px] shrink-0 text-[10px] text-ink-faint">{e.n} 题</span>
      </button>
    )
  }

  return (
    <aside className="flex w-[336px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-start gap-2 border-b border-border px-3.5 py-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="tnum text-[11px] text-brand-ink">{id}</span>
            <span className="text-[11px] text-ink-faint">{'★'.repeat(d?.stars || 0)}</span>
            {locked && <span className="text-[10.5px] text-ink-faint">硬性前置未点亮</span>}
          </div>
          <div className="mt-[2px] text-[13.5px] font-semibold leading-snug">
            {d ? d.title : <Loader2 size={13} className="animate-spin text-ink-faint" />}
          </div>
        </div>
        <button onClick={onClose} className="press rounded p-1 text-ink-faint hover:bg-muted">
          <X size={14} />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
        {d && (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-1.5">
              <button onClick={() => onPick(id, d.title)}
                className="press rounded-lg border border-brand-line bg-brand-soft px-2.5 py-[4px]
                           text-[12px] font-medium text-brand-ink hover:bg-brand/10">
                <Crosshair size={11} className="mr-1 inline" />
                看这个考点的 <span className="tnum">{d.n}</span> 道题
              </button>
              <button onClick={onToggle}
                className={`press rounded-lg px-2.5 py-[4px] text-[12px] font-medium ${mastered
                  ? 'border border-border bg-surface-2 text-ink-soft hover:bg-muted'
                  : 'border border-has-line bg-has-soft text-has hover:bg-has/10'}`}>
                <Sparkles size={11} className="mr-1 inline" />
                {mastered ? '取消点亮' : '点亮（我掌握了）'}
              </button>
              <button onClick={onExpand}
                title="把这条先修链经过的章节全部展开，一次看清整条路径"
                className="press rounded-lg border border-border bg-surface px-2.5 py-[4px]
                           text-[12px] font-medium text-ink-soft hover:border-brand-line hover:text-brand-ink">
                <Route size={11} className="mr-1 inline" />
                展开整条链路（{nChap} 章）
              </button>
            </div>

            <div className="mb-2.5 text-[11px] text-ink-faint">
              {d.topic} · {d.section}
            </div>

            {/* 精读入口：星空负责全局，这张局部图负责「我该先补什么」 */}
            <Ego id={id} pre={d.pre} post={d.post} onJump={onJump} />

            <Block title={`前置（先学，${d.pre.length}）`} empty="没有前置 —— 这是链路起点">
              {d.pre.map((e: any) => <Row key={e.pre} e={e} dir="pre" />)}
            </Block>
            <Block title={`后续（学完能学，${d.post.length}）`} empty="没有后续 —— 这是链路末端">
              {d.post.map((e: any) => <Row key={e.post} e={e} dir="post" />)}
            </Block>

            {(d.ancestors.length > 0 || d.descendants.length > 0) && (
              <div className="mb-3 rounded-lg border border-border bg-surface-2 px-2.5 py-2">
                <button onClick={() => setOpen(!open)}
                  className="flex w-full items-center gap-1.5 text-[11.5px] font-semibold text-ink-soft">
                  <span className="text-ink-faint">{open ? '▾' : '▸'}</span>
                  整条链路（含间接）
                  <span className="tnum font-normal text-ink-faint">
                    上 {d.ancestors.length} · 下 {d.descendants.length}
                  </span>
                </button>
                {open && (
                  <div className="anim-fade-in mt-1.5 space-y-1.5">
                    {[['全部先修', d.ancestors], ['全部后续', d.descendants]].map(([lab, list]: any) =>
                      list.length > 0 && (
                        <div key={lab}>
                          <div className="text-[10.5px] text-ink-faint">{lab}</div>
                          <div className="mt-[3px] flex flex-wrap gap-1">
                            {list.map((x: any) => (
                              <button key={x.id} onClick={() => onJump(x.id)}
                                title={x.title}
                                className="tnum rounded border border-border bg-surface px-1.5 py-[1px]
                                           text-[10.5px] text-ink-soft hover:border-brand-line hover:text-brand-ink">
                                {x.id}
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                  </div>
                )}
              </div>
            )}

            {/* 五段式字段：知识点库里本来就有，详情页只是把它显示出来 */}
            {Object.entries(d.fields || {}).map(([k, v]: any) => (
              <div key={k} className="mb-2.5">
                <div className="mb-1 text-[11px] font-semibold text-ink-soft">{k}</div>
                <ul className="space-y-[3px]">
                  {(Array.isArray(v) ? v : [v]).map((s: string, i: number) => (
                    <li key={i} className="flex gap-1.5 text-[12px] leading-relaxed text-ink">
                      <span className="mt-[6px] h-[3px] w-[3px] shrink-0 rounded-full bg-border-strong" />
                      <span className="min-w-0 break-words">{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </>
        )}
      </div>
    </aside>
  )
}

function Block({ title, empty, children }: { title: string; empty: string; children: any }) {
  const n = Array.isArray(children) ? children.filter(Boolean).length : 1
  return (
    <div className="mb-3">
      <div className="mb-1 text-[11px] font-semibold text-ink-soft">{title}</div>
      {n ? <div className="-mx-1.5">{children}</div> : <div className="text-[11.5px] text-ink-faint">{empty}</div>}
    </div>
  )
}

/* ══ 体检抽屉 ══════════════════════════════════════ */

function Audit({ data, onClose, onJump }: { data: any; onClose: () => void; onJump: (id: string) => void }) {
  return (
    <aside className="flex w-[320px] shrink-0 flex-col border-l border-border bg-surface">
      <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5">
        <ShieldAlert size={14} className="text-warn" />
        <span className="text-[12.5px] font-semibold">链路体检</span>
        <button onClick={onClose} className="press ml-auto rounded p-1 text-ink-faint hover:bg-muted">
          <X size={14} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
        {!data ? <Loader2 size={14} className="animate-spin text-ink-faint" /> : (
          <>
            <div className={`mb-3 rounded-lg px-2.5 py-2 text-[11.5px] ${
              data.ok ? 'bg-has-soft text-has' : 'bg-danger-soft text-danger'}`}>
              {data.ok ? '✓ 结构没问题：无悬空引用、无自环、硬性前置无环' : '✗ 有结构性问题，见下'}
            </div>

            <Section title={`错误 ${data.errors.length}`} items={data.errors} onJump={onJump} tone="danger" />
            <Section title={`值得看一眼 ${data.warn.length}`} items={data.warn} onJump={onJump} tone="warn" />

            <div className="mb-1 mt-3 text-[11.5px] font-semibold text-ink-soft">
              待补清单（不是错误，是还没铺到的位置）
            </div>
            {[['没有前置（起点）', data.todo.no_pre], ['没有后续（末端）', data.todo.no_post]]
              .map(([lab, list]: any) => (
                <div key={lab} className="mb-2">
                  <div className="text-[10.5px] text-ink-faint">{lab} <span className="tnum">{list.length}</span></div>
                  <div className="mt-[3px] flex flex-wrap gap-1">
                    {list.map((x: any) => (
                      <button key={x.id} onClick={() => onJump(x.id)} title={x.title}
                        className="tnum rounded border border-border bg-surface px-1.5 py-[1px] text-[10.5px]
                                   text-ink-soft hover:border-brand-line hover:text-brand-ink">
                        {x.id}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
          </>
        )}
      </div>
    </aside>
  )
}

function Section({ title, items, onJump, tone }: {
  title: string; items: any[]; onJump: (id: string) => void; tone: 'danger' | 'warn'
}) {
  if (!items.length) return null
  const cls = tone === 'danger' ? 'text-danger' : 'text-warn'
  return (
    <div className="mb-3">
      <div className={`mb-1 text-[11.5px] font-semibold ${cls}`}>{title}</div>
      <ul className="space-y-1">
        {items.map((x, i) => (
          <li key={i} className="flex gap-1.5 text-[11.5px] leading-snug text-ink-soft">
            <span className={`mt-[6px] h-[3px] w-[3px] shrink-0 rounded-full ${tone === 'danger' ? 'bg-danger' : 'bg-warn'}`} />
            <span className="min-w-0 break-words">
              {x.msg}
              {(x.ids || []).length > 0 && (
                <span className="ml-1 inline-flex flex-wrap gap-1">
                  {x.ids.map((id: string) => (
                    <button key={id} onClick={() => onJump(id)}
                      className="tnum rounded border border-border px-1 text-[10px] hover:text-brand-ink">
                      {id}
                    </button>
                  ))}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
