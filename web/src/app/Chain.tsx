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
import { Crosshair, Loader2, Lock, Orbit, Rows3, Search, ShieldAlert, Sparkles, X } from 'lucide-react'
import { api, reportErr } from '@/lib/api'
import { Chip, useFlag } from '@/app/ui'
import { Galaxy } from '@/app/Galaxy'
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

/* 布局常量。ROW 定 24 是因为最多的列（概率统计 20 个）要能塞进一屏高。 */
const COL_W = 152, ROW = 24, NODE_W = 48, NODE_H = 18, PAD = 26, HEAD = 30

type Pos = { x: number; y: number; col: number }
type View = { k: number; tx: number; ty: number }

export function Chain({ onPickPoint }: { onPickPoint: (pid: string, title: string) => void }) {
  const [g, setG] = useState<Graph | null>(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState('')
  const [hover, setHover] = useState('')
  const [hardOnly, setHardOnly] = useFlag('amti.chain.hardonly', false)
  const [off, setOff] = useState<Set<string>>(new Set())   // 隐藏的大类
  const [view, setView] = useState<View>({ k: 1, tx: 0, ty: 0 })
  const [q, setQ] = useState('')
  /** 视图模式：星系（默认，全局与氛围）/ 层级（按顺序精读、查覆盖）。
   *  两种模式共用同一份数据、同一套筛选与进度，切换不丢状态。 */
  const [galaxy, setGalaxy] = useFlag('amti.chain.galaxy', true)
  const [resetNonce, setResetNonce] = useState(0)
  const [jump, setJump] = useState<{ id: string; nonce: number } | null>(null)
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

  const { cols, pos, W, H } = useMemo(() => {
    const cols: { topic: string; color: string; nodes: GNode[] }[] = []
    for (const n of g?.nodes || []) {
      let c = cols.find((x) => x.topic === n.topic)
      if (!c) { c = { topic: n.topic, color: TOPIC_COLORS[cols.length % 10], nodes: [] }; cols.push(c) }
      c.nodes.push(n)
    }
    // 列内先按 hard 深度（由浅到深），同深度保持知识点库原顺序：
    // 这样「从上往下 = 越来越难」在每一列内也成立。
    for (const c of cols) {
      c.nodes = c.nodes
        .map((n, i) => ({ n, i }))
        .sort((a, b) => a.n.depth - b.n.depth || a.i - b.i)
        .map((x) => x.n)
    }
    const pos = new Map<string, Pos>()
    let maxRow = 0
    cols.forEach((c, ci) => {
      c.nodes.forEach((n, ri) => {
        pos.set(n.id, { x: PAD + ci * COL_W + NODE_W / 2, y: PAD + HEAD + ri * ROW, col: ci })
        maxRow = Math.max(maxRow, ri)
      })
    })
    return { cols, pos, W: PAD * 2 + cols.length * COL_W, H: PAD * 2 + HEAD + (maxRow + 1) * ROW }
  }, [g])

  const topicColor = useMemo(() => {
    const m = new Map<string, string>()
    for (const c of cols) m.set(c.topic, c.color)
    return m
  }, [cols])

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
    // 依赖里必须有 galaxy：切回「层级」时那个 div 才刚挂上，
    // 不重跑的话 wrap.current 还是 null，适配一次都不会发生（首屏会偏）。
  }, [W, H, galaxy])

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

  const edges = useMemo(() => {
    const all = g?.edges || []
    return hardOnly ? all.filter((e) => e.strength === 'hard') : all
  }, [g, hardOnly])

  const hit = useMemo(() => {
    const s = q.trim()
    if (!s) return []
    return (g?.nodes || []).filter((n) => n.title.includes(s) || n.id.startsWith(s)).slice(0, 8)
  }, [q, g])

  /* ── 视图操作 ───────────────────────────────────────── */
  const centerOn = useCallback((id: string) => {
    const el = wrap.current
    setJump((f) => ({ id, nonce: (f?.nonce || 0) + 1 }))      // 星系模式认这个
    const q = pos.get(id)                                      // 层级模式自己挪
    if (!q || !el) return
    setView((v) => ({ k: v.k, tx: el.clientWidth / 2 - q.x * v.k, ty: el.clientHeight / 2 - q.y * v.k }))
  }, [pos])

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
  }, [g, galaxy])

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
          {/* 两种模式共用同一份数据、筛选与进度：星系负责「看全局、有感觉」，
              层级负责「按顺序读、查覆盖」。默认星系。 */}
          <span className="flex items-center gap-1 rounded-full border border-border bg-surface-2 p-[2px]">
            <button onClick={() => setGalaxy(true)}
              title="径向星空：角度=大类、半径=由浅入深；适合看全局与找位置"
              className={`flex items-center gap-1 rounded-full px-2 py-[3px] text-[11.5px] ${galaxy
                ? 'bg-brand text-white' : 'text-ink-soft hover:text-brand-ink'}`}>
              <Orbit size={11} /> 星系
            </button>
            <button onClick={() => setGalaxy(false)}
              title="分层图：横轴=大类、纵轴=层级；适合按顺序精读与查覆盖"
              className={`flex items-center gap-1 rounded-full px-2 py-[3px] text-[11.5px] ${!galaxy
                ? 'bg-brand text-white' : 'text-ink-soft hover:text-brand-ink'}`}>
              <Rows3 size={11} /> 层级
            </button>
          </span>
          <Chip size="sm" on={hardOnly} onClick={() => setHardOnly(!hardOnly)}
            title="软性前置只是「有帮助」，画上会显得链路很密">只看硬性前置</Chip>
          <Chip size="sm" on={false}
            onClick={() => { setResetNonce((v) => v + 1); setView({ k: 1, tx: 0, ty: 0 }) }}
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

        {/* 画布 */}
        {galaxy ? (
          <Galaxy nodes={g.nodes} edges={g.edges} mastered={mastered} locked={locked}
            sel={sel} onSelect={setSel} onToggleMastered={toggleMastered}
            hardOnly={hardOnly} off={off}
            onToggleTopic={(t) => setOff((x) => {
              const n = new Set(x); n.has(t) ? n.delete(t) : n.add(t); return n
            })}
            resetNonce={resetNonce} focus={jump} />
        ) : (
        <div ref={wrap} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
          className="relative min-h-0 flex-1 cursor-grab overflow-hidden bg-surface-2 active:cursor-grabbing">
          <svg width="100%" height="100%" className="select-none">
            <g transform={`translate(${view.tx},${view.ty}) scale(${view.k})`}>
              {/* 列头：点一下隐藏/显示这个大类的节点（**布局不动**，
                  只压暗——重排会让整张图跳一下，用户会迷路） */}
              {cols.map((c) => {
                const x = PAD + (pos.get(c.nodes[0].id)?.col || 0) * COL_W
                const hidden = off.has(c.topic)
                return (
                  <g key={c.topic} data-node
                    onClick={() => setOff((s) => {
                      const t = new Set(s); t.has(c.topic) ? t.delete(c.topic) : t.add(c.topic); return t
                    })}
                    className="cursor-pointer">
                    <rect x={x} y={PAD} width={COL_W - 12} height={HEAD - 8} rx={6}
                      fill={hidden ? '#f1f5f9' : c.color + '18'} stroke={hidden ? '#e2e8f0' : c.color + '55'} />
                    <text x={x + 8} y={PAD + 15} fontSize={11.5} fontWeight={600}
                      fill={hidden ? '#94a3b8' : c.color}>
                      {c.topic.replace(/^[一二三四五六七八九十]+、/, '')}
                    </text>
                    <text x={x + COL_W - 20} y={PAD + 15} fontSize={10} fill="#94a3b8"
                      textAnchor="end">{c.nodes.length}</text>
                  </g>
                )
              })}

              {/* 边。**先画边后画节点**，否则线会盖在节点上。 */}
              {edges.map((e, i) => {
                const a = pos.get(e.pre), b = pos.get(e.post)
                if (!a || !b) return null
                const dim = off.has(g.nodes.find((n) => n.id === e.pre)?.topic || '')
                  || off.has(g.nodes.find((n) => n.id === e.post)?.topic || '')
                const lit = near && (near.has(e.pre) && near.has(e.post))
                const hot = focus && lit
                const x1 = a.x + NODE_W / 2, x2 = b.x - NODE_W / 2
                let d: string
                if (b.col > a.col) {
                  const dx = Math.max(18, (x2 - x1) * 0.45)
                  d = `M ${x1} ${a.y} C ${x1 + dx} ${a.y}, ${x2 - dx} ${b.y}, ${x2} ${b.y}`
                } else if (b.col === a.col) {
                  // 同列相邻（如「集合运算 → 新题型」）：从右侧绕一个小弧，
                  // 直线会正好压在节点之间，看不出方向。
                  const r = 16 + Math.abs(b.y - a.y) * 0.25
                  d = `M ${x1} ${a.y} C ${x1 + r} ${a.y}, ${x1 + r} ${b.y}, ${x1} ${b.y}`
                } else {
                  const r = 40
                  d = `M ${x1} ${a.y} C ${x1 + r} ${a.y + 26}, ${x2 - r} ${b.y + 26}, ${x2} ${b.y}`
                }
                return (
                  <path key={i} d={d} fill="none"
                    stroke={hot ? '#db2777' : e.strength === 'hard' ? '#94a3b8' : '#cbd5e1'}
                    strokeWidth={hot ? 2 : e.strength === 'hard' ? 1.4 : 1}
                    strokeDasharray={e.strength === 'soft' && !hot ? '3 2.5' : undefined}
                    markerEnd={hot ? 'url(#ah)' : e.strength === 'hard' ? 'url(#ah)' : undefined}
                    opacity={dim ? 0.06 : hover ? (lit ? 1 : 0.15) : sel && !lit ? 0.5 : 1} />
                )
              })}

              {/* 节点 */}
              {g.nodes.map((n) => {
                const p = pos.get(n.id)
                if (!p) return null
                const c = topicColor.get(n.topic) || '#64748b'
                const lk = locked(n.id), mk = mastered.has(n.id)
                // 压暗**只在悬停时**做（临时聚焦）；选中是"停在这儿看"的持久状态，
                // 那时把 150 个节点压成灰的，整页会显得像坏了。
                const dim = off.has(n.topic) || (hover && near && !near.has(n.id))
                const isSel = sel === n.id
                return (
                  <g key={n.id} data-node transform={`translate(${p.x - NODE_W / 2},${p.y - NODE_H / 2})`}
                    opacity={dim ? 0.3 : 1} className="cursor-pointer"
                    onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover('')}
                    onClick={(ev) => { ev.stopPropagation(); setSel(n.id) }}>
                    <title>{`${n.id} ${n.title}\n★${n.stars} · ${n.difficulty} · ${n.n} 道题`}</title>
                    <rect width={NODE_W} height={NODE_H} rx={5}
                      fill={mk ? c : lk ? '#f1f5f9' : '#ffffff'}
                      stroke={isSel ? '#db2777' : mk ? c : lk ? '#e2e8f0' : c}
                      strokeWidth={isSel ? 2.2 : 1.2} />
                    <text x={NODE_W / 2} y={12.5} fontSize={10.5} textAnchor="middle"
                      className="tnum" fill={mk ? '#fff' : lk ? '#94a3b8' : '#334155'}>
                      {n.id}
                    </text>
                    {lk && <circle cx={NODE_W - 4} cy={4} r={3} fill="#cbd5e1" />}
                    <text x={NODE_W + 5} y={12.5} fontSize={9.5}
                      fill={lk ? '#a8b3c2' : '#64748b'}>
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
            </defs>
          </svg>

          <div className="pointer-events-none absolute bottom-2.5 left-3 flex items-center gap-3
                          rounded-lg bg-surface/85 px-2.5 py-1 text-[10.5px] text-ink-faint">
            <span>拖拽平移 · 滚轮缩放 · 点节点看详情 · 点列头隐藏大类</span>
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
        )}
      </div>

      {/* ── 右：详情 ───────────────────────────────── */}
      {sel && <Detail id={sel} onPick={onPickPoint} onJump={(id) => { setSel(id); centerOn(id) }}
        mastered={mastered.has(sel)} onToggle={() => toggleMastered(sel)}
        onClose={() => setSel('')} locked={locked(sel)} />}

      {/* ── 体检抽屉 ───────────────────────────────── */}
      {showAudit && (
        <Audit data={audit} onClose={() => setShowAudit(false)}
          onJump={(id) => { setSel(id); centerOn(id); centerOn(id) }} />
      )}
    </div>
  )
}

/* ══ 侧栏详情 ══════════════════════════════════════ */

function Detail({ id, onPick, onJump, mastered, onToggle, onClose, locked }: {
  id: string; onPick: (pid: string, title: string) => void; onJump: (pid: string) => void
  mastered: boolean; onToggle: () => void; onClose: () => void; locked: boolean
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
