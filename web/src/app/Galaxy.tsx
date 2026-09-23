/** 知识链路 · 径向星空
 *
 *  为什么是径向、为什么用 Canvas（决策见 设计/知识链路.md「视图选型」）：
 *
 *  ① 我们的数据是「层次 + 额外关系」：152 个考点有 10 个大类骨架，
 *     但 19% 的边是**跨大类**的（`二次不等式 → 导数单调区间`），
 *     而那部分正是这个功能的全部价值。思维导图每个节点只能有一个父节点，
 *     塞不下这些弦；力导向又没有方向、位置每次都不重样，回答不了「先补什么」。
 *     径向 + 层次边绑定（Holten 2006）是这类数据的标准解法：
 *     **角度 = 大类、半径 = 由浅入深**，跨分支的边沿骨架束成弧。
 *  ② 补上小初之后是 ~676 个节点 / ~1300 条边，DOM/SVG 每帧改 1300 条路径
 *     撑不住；Canvas 2D + 预烘焙光球 sprite 才能 60fps（math-tree 700 节点同法）。
 *  ③ 但**星空负责全局与氛围，不负责精读**：真正回答「先补什么」的是
 *     点选后侧栏那张局部链路图（`Ego.tsx`）——那里没有毛线球问题。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type GNode = {
  id: string; title: string; stars: number; topic: string; section: string
  depth: number; n_pre: number; n_post: number; n: number
}
export type Edge = { pre: string; post: string; strength: 'hard' | 'soft'; reason: string }

type Props = {
  nodes: GNode[]
  edges: Edge[]
  mastered: Set<string>
  locked: (id: string) => boolean
  sel: string
  onSelect: (id: string) => void
  onToggleMastered: (id: string) => void
  hardOnly: boolean
  off: Set<string>
  onToggleTopic: (topic: string) => void
  resetNonce: number
  focus: { id: string; nonce: number } | null
}

/* 布局常量。R_STEP=46：最深的 hard 链是 10 层，110+10*46=570 的半径
   正好落在 1200×1200 的世界里，一屏能缩到 0.8 看全。 */
const R0 = 112, R_STEP = 46, SECTOR_F = 0.72, MIN_SPACING = 15

/** 10 个大类的色相。夜色底上用高饱和霓虹，和白天主题的粉品牌色是两套
 *  —— 这块画布是「另一个模式」，硬套浅色只会两头不讨好。 */
const HUES = ['#5ac8fa', '#a78bfa', '#34d399', '#fbbf24', '#f472b6',
  '#60a5fa', '#22d3ee', '#c084fc', '#4ade80', '#fb923c']

/** 稀有度按度数（入+出）分档。我们这张图度数中位数 4、最大 15、
 *  只有 6 个枢纽，所以阈值取 3/7/10 而不是平均分。 */
const RARITY = [
  { min: 10, color: '#ffcf4d', label: '传说' },
  { min: 7, color: '#b86bff', label: '史诗' },
  { min: 4, color: '#4f9dff', label: '稀有' },
  { min: 0, color: '#5b6577', label: '普通' },
]
const rarityOf = (deg: number) => RARITY.find((r) => deg >= r.min)!

type Pos = { x: number; y: number; r: number; a: number; col: string }

export function Galaxy(p: Props) {
  const box = useRef<HTMLDivElement>(null)
  const cv = useRef<HTMLCanvasElement>(null)
  const view = useRef({ k: 0.8, tx: 0, ty: 0 })
  const [tip, setTip] = useState<{ x: number; y: number; id: string } | null>(null)
  const [hoverId, setHoverId] = useState('')
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; moved: number } | null>(null)
  const needFit = useRef(true)

  /* ── 布局：角度 = 大类（sqrt 加权），半径 = hard 深度 ────────────── */
  const { pos, sectors, maxR } = useMemo(() => {
    const groups: { topic: string; nodes: GNode[]; color: string }[] = []
    for (const n of p.nodes) {
      let g = groups.find((x) => x.topic === n.topic)
      if (!g) { g = { topic: n.topic, nodes: [], color: HUES[groups.length % HUES.length] }; groups.push(g) }
      g.nodes.push(n)
    }
    // sqrt 加权：不然 25 个考点的大类会把 6 个考点的挤成一条缝
    const w = groups.map((g) => Math.sqrt(g.nodes.length))
    const total = w.reduce((a, b) => a + b, 0)
    const pos = new Map<string, Pos>()
    const midAngle = new Map<string, number>()
    const sectors: { topic: string; a0: number; a1: number; far: number; color: string; n: number }[] = []
    let acc = -Math.PI / 2                       // 从正上方开始
    groups.forEach((g, gi) => {
      const span = (w[gi] / total) * Math.PI * 2
      const mid = acc + span / 2
      const inner = span * SECTOR_F
      // 层内按深度排；同一层按知识点库原顺序（数组顺序就是库顺序）
      const layers = new Map<number, GNode[]>()
      g.nodes.forEach((n, i) => {
        const l = layers.get(n.depth) || []
        l.push({ ...n })
        layers.set(n.depth, l)
        void i
      })
      let far = R0
      for (const [depth, list] of [...layers.entries()].sort((a, b) => a[0] - b[0])) {
        let ring = depth
        let rest = list
        while (rest.length) {
          const r = R0 + ring * R_STEP
          const arc = r * inner
          const cap = Math.max(1, Math.floor(arc / MIN_SPACING))
          const take = rest.slice(0, cap)
          take.forEach((n, j) => {
            // 层内均匀铺开；只有一颗时落在正中，读起来是「这一层的代表」
            const f = take.length === 1 ? 0.5 : j / (take.length - 1)
            const a = mid - inner / 2 + f * inner
            pos.set(n.id, { x: Math.cos(a) * r, y: Math.sin(a) * r, r, a, col: g.color })
          })
          far = Math.max(far, r)
          rest = rest.slice(cap)
          ring += 1                                  // 摆不下就往外溢一层
          if (ring > depth + 40) break               // 防御：绝不在这里死循环
        }
      }
      sectors.push({ topic: g.topic, a0: acc, a1: acc + span, far, color: g.color, n: g.nodes.length })
      midAngle.set(g.topic, mid)
      acc += span
    })
    let maxR = 0
    for (const q of pos.values()) maxR = Math.max(maxR, q.r)
    // 大类标签统一放到最外圈的同一个半径上：标签自己也能当图例读。
    // 早先按「本类最深那颗星」的高度摆，结果 集合(浅) 的标签贴在圆心旁边，
    // 既压住星点又让整圈标签参差不齐。
    const lr = maxR + 40
    return {
      pos,
      sectors: sectors.map((s) => ({ ...s, label: {
        x: Math.cos(midAngle.get(s.topic)!) * lr, y: Math.sin(midAngle.get(s.topic)!) * lr } })),
      maxR: lr + 30,
    }
  }, [p.nodes])

  const byId = useMemo(() => new Map(p.nodes.map((n) => [n.id, n])), [p.nodes])
  const deg = useMemo(() => {
    const d = new Map<string, number>()
    for (const e of p.edges) {
      d.set(e.pre, (d.get(e.pre) || 0) + 1)
      d.set(e.post, (d.get(e.post) || 0) + 1)
    }
    return d
  }, [p.edges])
  const edges = useMemo(
    () => (p.hardOnly ? p.edges.filter((e) => e.strength === 'hard') : p.edges), [p.edges, p.hardOnly])

  /** 高亮集：悬停优先于选中。只亮前后一跳，再多就看不清了。 */
  const focus = hoverId || p.sel
  const near = useMemo(() => {
    if (!focus) return null
    const s = new Set([focus])
    for (const e of p.edges) {
      if (e.pre === focus) s.add(e.post)
      if (e.post === focus) s.add(e.pre)
    }
    return s
  }, [focus, p.edges])

  /* ── 烘焙光球 sprite ─────────────────────────────────────────
   *  全节点共用 3 张预着色 canvas，运行时只 drawImage——这是 700 节点
   *  还能 60fps 的关键（实时 shadowBlur 会直接跪）。 */
  const sprites = useMemo(() => {
    const bake = (color: string, size = 96) => {
      const off = document.createElement('canvas')
      off.width = off.height = size
      const c = off.getContext('2d')!
      const g = c.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
      g.addColorStop(0, hexA(color, 0.95))
      g.addColorStop(0.2, hexA(color, 0.5))
      g.addColorStop(0.55, hexA(color, 0.14))
      g.addColorStop(1, hexA(color, 0))
      c.fillStyle = g
      c.fillRect(0, 0, size, size)
      return off
    }
    return { cyan: bake('#6ef0ff'), violet: bake('#a070ff'), gray: bake('#8ea2cc') }
  }, [])

  /* 背景星野：烘焙成一张 data URL，交给 **CSS 背景**去平铺，每帧只改
     `background-position` —— 视差因此是零像素成本的。
     （先写成每帧 canvas drawImage 平铺，3 层 × 9 块 × 1024² 直接把页面拖死，
     测试脚本都超时了；这类装饰绝不该走逐帧绘制。） */
  const starfield = useMemo(() => {
    const S = 512
    const off = document.createElement('canvas')
    off.width = off.height = S
    const c = off.getContext('2d')!
    let seed = 20260923
    const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff
    for (let i = 0; i < 260; i++) {
      const x = rnd() * S, y = rnd() * S, r = rnd() * 1.05 + 0.22
      c.globalAlpha = 0.16 + rnd() * 0.45
      c.fillStyle = rnd() > 0.82 ? '#bcd7ff' : '#ffffff'
      c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); c.fill()
    }
    return off.toDataURL('image/png')
  }, [])

  /* ── 尺寸 / 适配 ─────────────────────────────────────────── */
  const fit = useCallback(() => {
    const el = box.current
    if (!el) return
    const k = Math.min(1, (el.clientWidth - 40) / (maxR * 2), (el.clientHeight - 40) / (maxR * 2))
    view.current = { k: Math.max(0.3, k), tx: el.clientWidth / 2, ty: el.clientHeight / 2 }
  }, [maxR])

  useEffect(() => { needFit.current = true }, [maxR, p.resetNonce])

  // 跳到某个考点：把它摆到画面正中（搜索命中、点链路 chip 都用这条）
  useEffect(() => {
    if (!p.focus) return
    const el = box.current, q = pos.get(p.focus.id)
    if (!el || !q) return
    const k = Math.max(view.current.k, 1.4)
    view.current = { k, tx: el.clientWidth / 2 - q.x * k, ty: el.clientHeight / 2 - q.y * k }
  }, [p.focus, pos])

  /* ── 交互：拖拽平移 / 滚轮缩放 / 悬停命中 / 点击选中 ─────────── */
  const toWorld = (cx: number, cy: number) => {
    const el = box.current!
    const r = el.getBoundingClientRect()
    const v = view.current
    return {
      x: (cx - r.left - v.tx) / v.k,
      y: (cy - r.top - v.ty) / v.k,
      sx: cx - r.left, sy: cy - r.top,
    }
  }
  const hit = useCallback((wx: number, wy: number) => {
    let best = '', bd = Infinity
    for (const [id, q] of pos) {
      const d = (q.x - wx) ** 2 + (q.y - wy) ** 2
      if (d < bd) { bd = d; best = id }
    }
    return bd < 14 ** 2 ? best : ''
  }, [pos])

  const onDown = (e: React.PointerEvent) => {
    const el = box.current!
    const r = el.getBoundingClientRect()
    drag.current = { x: e.clientX - r.left, y: e.clientY - r.top,
      tx: view.current.tx, ty: view.current.ty, moved: 0 }
    el.setPointerCapture(e.pointerId)
  }
  const onMove = (e: React.PointerEvent) => {
    const w = toWorld(e.clientX, e.clientY)
    if (drag.current) {
      const dx = w.sx - drag.current.x, dy = w.sy - drag.current.y
      drag.current.moved = Math.max(drag.current.moved, Math.abs(dx) + Math.abs(dy))
      const v = view.current
      v.tx = drag.current.tx + dx
      v.ty = drag.current.ty + dy
      return
    }
    const id = hit(w.x, w.y)
    setHoverId(id)
    setTip(id ? { x: w.sx, y: w.sy, id } : null)
  }
  const onUp = (e: React.PointerEvent) => {
    const el = box.current!
    el.releasePointerCapture?.(e.pointerId)
    const w = toWorld(e.clientX, e.clientY)
    const moved = drag.current?.moved || 0
    drag.current = null
    if (moved > 4) return                       // 拖过就不算点
    // 先看有没有点在大类标签上（那是个筛选开关）
    const v = view.current
    for (const s of sectors) {
      const sx = s.label.x * v.k + v.tx, sy = s.label.y * v.k + v.ty
      if (Math.abs(w.sx - sx) < 46 && Math.abs(w.sy - sy) < 13) {
        p.onToggleTopic(s.topic)
        return
      }
    }
    const id = hit(w.x, w.y)
    if (id) p.onSelect(id)
  }
  // 滚轮缩放必须挂**原生**监听并 passive:false：React 的 onWheel 是被动的，
  // 在里面 preventDefault 会被忽略，缩放的同时页面也跟着滚（层级视图踩过）。
  useEffect(() => {
    const el = box.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      const px = e.clientX - r.left, py = e.clientY - r.top
      const v = view.current
      const k = Math.min(10, Math.max(0.25, v.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)))
      v.tx = px - (px - v.tx) * (k / v.k)
      v.ty = py - (py - v.ty) * (k / v.k)
      v.k = k
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  /* ── 渲染循环 ─────────────────────────────────────────────
   *  呼吸动效要连续帧，所以常驻 rAF；但只画视口内的节点（外圈在缩小时
   *  直接剔除），并且全程 drawImage 预烘焙 sprite。 */
  useEffect(() => {
    const el = box.current, c = cv.current
    if (!el || !c) return
    const ctx = c.getContext('2d')!
    let raf = 0, t0 = performance.now()

    const draw = (now: number) => {
      raf = requestAnimationFrame(draw)
      const t = (now - t0) / 1000
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      const W = el.clientWidth, H = el.clientHeight
      if (c.width !== W * dpr || c.height !== H * dpr) {
        c.width = W * dpr; c.height = H * dpr
        c.style.width = W + 'px'; c.style.height = H + 'px'
      }
      if (needFit.current) { needFit.current = false; fit() }
      const v = view.current
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, W, H)

      // 视差：只改一个样式字符串，不动一个像素
      el.style.backgroundPosition = `${-v.tx * 0.12}px ${-v.ty * 0.12}px, center`

      ctx.save()
      ctx.translate(v.tx, v.ty)
      ctx.scale(v.k, v.k)

      // ① 深度环：把「由内到外 = 由浅入深」这条读图规则画出来
      ctx.lineWidth = 1 / v.k
      for (let d = 0; d <= 10; d++) {
        const r = R0 + d * R_STEP
        ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2)
        ctx.strokeStyle = d === 0 ? 'rgba(140,170,255,.20)' : 'rgba(120,150,230,.075)'
        ctx.stroke()
      }
      // ② 大类扇形：极淡的底色 + 边界线，给每个大类一块「地盘」
      for (const s of sectors) {
        if (p.off.has(s.topic)) continue
        ctx.beginPath()
        ctx.moveTo(0, 0)
        ctx.arc(0, 0, maxR, s.a0, s.a1)
        ctx.closePath()
        ctx.fillStyle = hexA(s.color, 0.05)
        ctx.fill()
        ctx.beginPath()
        ctx.moveTo(Math.cos(s.a0) * (R0 - 26), Math.sin(s.a0) * (R0 - 26))
        ctx.lineTo(Math.cos(s.a0) * maxR, Math.sin(s.a0) * maxR)
        ctx.strokeStyle = hexA(s.color, 0.18); ctx.stroke()
      }

      // ③ 边：跨分支的先修沿骨架束成弧，控制点往圆心收，天生就有束状感
      for (const e of edges) {
        const a = pos.get(e.pre), b = pos.get(e.post)
        if (!a || !b) continue
        const hidden = p.off.has(byId.get(e.pre)?.topic || '')
          || p.off.has(byId.get(e.post)?.topic || '')
        const lit = focus ? near!.has(e.pre) && near!.has(e.post) : false
        if (hidden && !lit) continue
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2
        const pull = 0.42 + 0.35 * (Math.hypot(a.x - b.x, a.y - b.y) / (maxR * 2))
        const cx = mx * (1 - pull), cy = my * (1 - pull)   // 往圆心收 = 束状
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.quadraticCurveTo(cx, cy, b.x, b.y)
        if (lit) {
          ctx.strokeStyle = 'rgba(255,110,170,.95)'
          ctx.lineWidth = 1.9 / v.k
          ctx.setLineDash([7 / v.k, 5 / v.k])
          ctx.lineDashOffset = -(t * 22) % 12          // 流动：方向就是 pre → post
        } else {
          ctx.strokeStyle = e.strength === 'hard'
            ? (focus ? 'rgba(150,180,255,.13)' : 'rgba(150,180,255,.26)')
            : (focus ? 'rgba(120,140,190,.06)' : 'rgba(120,140,190,.13)')
          ctx.lineWidth = (e.strength === 'hard' ? 1.1 : 0.9) / v.k
          ctx.setLineDash(e.strength === 'soft' ? [3 / v.k, 3 / v.k] : [])
          ctx.lineDashOffset = 0
        }
        ctx.stroke()
      }
      ctx.setLineDash([])

      // ④ 节点：光球（状态色）+ 核心 + 稀有度环
      const labelAt = v.k >= 1.5, nameAt = v.k >= 2.6
      ctx.textAlign = 'center'
      for (const [id, q] of pos) {
        const nd = byId.get(id)!
        if (p.off.has(nd.topic)) continue
        const sx = q.x * v.k + v.tx, sy = q.y * v.k + v.ty
        if (sx < -60 || sy < -60 || sx > W + 60 || sy > H + 60) continue   // 视口剔除
        const degv = deg.get(id) || 0
        const rar = rarityOf(degv)
        const mk = p.mastered.has(id), lk = p.locked(id)
        const dim = focus ? !near!.has(id) : false
        const glow = mk ? sprites.violet : lk ? sprites.gray : sprites.cyan
        const pulse = 1 + 0.08 * Math.sin(t * 1.6 + (degv * 1.7 + id.length))
        const base = (mk ? 36 : lk ? 21 : 29) * pulse
        ctx.globalAlpha = dim ? 0.18 : 1
        ctx.drawImage(glow, q.x - base / 2, q.y - base / 2, base, base)
        ctx.beginPath()
        ctx.arc(q.x, q.y, mk ? 4.6 : lk ? 2.6 : 3.6, 0, Math.PI * 2)
        ctx.fillStyle = mk ? '#ffe9a8' : lk ? '#7f8db0' : '#dff6ff'
        ctx.fill()
        ctx.beginPath()
        ctx.arc(q.x, q.y, (mk ? 8.2 : lk ? 5.4 : 6.9) + (id === p.sel ? 2.6 : 0), 0, Math.PI * 2)
        ctx.strokeStyle = id === p.sel ? '#ff6eaa' : rar.color
        ctx.lineWidth = (id === p.sel ? 2.4 : 1.2) / v.k
        ctx.globalAlpha = dim ? 0.25 : mk ? 1 : lk ? 0.5 : 0.85
        ctx.stroke()
        ctx.globalAlpha = dim ? 0.2 : 1
        if (labelAt) {
          ctx.font = `${11 / v.k}px ui-sans-serif, system-ui`
          ctx.fillStyle = mk ? '#ffe9a8' : lk ? '#94a3c4' : '#cfe0ff'
          ctx.fillText(nameAt ? nd.title.slice(0, 12) : id, q.x, q.y - 11 / v.k)
        }
      }
      ctx.globalAlpha = 1

      // ⑤ 中心罗盘：整体规模一目了然
      const core = 44
      const cg = ctx.createRadialGradient(0, 0, 2, 0, 0, core)
      cg.addColorStop(0, 'rgba(255,214,120,.9)'); cg.addColorStop(0.5, 'rgba(255,170,90,.22)')
      cg.addColorStop(1, 'rgba(255,150,80,0)')
      ctx.fillStyle = cg
      ctx.beginPath(); ctx.arc(0, 0, core, 0, Math.PI * 2); ctx.fill()
      ctx.beginPath(); ctx.arc(0, 0, 26, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(255,206,120,.55)'; ctx.lineWidth = 1.4 / v.k; ctx.stroke()
      ctx.fillStyle = '#ffe9b8'
      ctx.font = `600 ${13 / v.k}px ui-sans-serif, system-ui`
      ctx.fillText(String(p.nodes.length), 0, -2 / v.k)
      ctx.font = `${9 / v.k}px ui-sans-serif, system-ui`
      ctx.fillStyle = 'rgba(255,233,184,.75)'
      ctx.fillText('考点', 0, 10 / v.k)

      // ⑥ 大类标签（点它 = 隐藏/显示这一类）
      ctx.font = `600 ${12.5 / v.k}px ui-sans-serif, system-ui`
      for (const s of sectors) {
        const on = !p.off.has(s.topic)
        ctx.fillStyle = on ? s.color : 'rgba(120,140,190,.35)'
        ctx.fillText(s.topic.replace(/^[一二三四五六七八九十]+、/, '') + ' ' + s.n, s.label.x, s.label.y)
      }
      ctx.restore()
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [pos, sectors, edges, byId, deg, sprites, starfield, focus, near, p.mastered, p.off,
      p.sel, p.nodes.length, p.locked, fit, maxR])

  return (
    <div ref={box} className="relative min-h-0 flex-1 cursor-grab overflow-hidden active:cursor-grabbing"
      style={{
        // 两层：星野平铺（可平移做视差）+ 中心稍亮的深空渐变
        backgroundImage: `url(${starfield}), radial-gradient(circle at center, #111a34 0%, #05070f 75%)`,
        backgroundRepeat: 'repeat, no-repeat',
        backgroundSize: 'auto, cover',
      }}
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
      onPointerLeave={() => { setTip(null); setHoverId(''); drag.current = null }}>
      <canvas ref={cv} className="block h-full w-full" />
      {tip && (
        <div className="pointer-events-none absolute z-20 max-w-[280px] rounded-lg border
                        border-white/10 bg-[#0b1226]/95 px-2.5 py-1.5 text-[11.5px] text-white/90
                        shadow-xl backdrop-blur"
          style={{ left: Math.min(tip.x + 14, (box.current?.clientWidth || 400) - 290), top: tip.y + 12 }}>
          <div className="flex items-baseline gap-1.5">
            <span className="tnum text-[10.5px] text-cyan-300">{tip.id}</span>
            <span className="font-medium">{byId.get(tip.id)?.title}</span>
          </div>
          <div className="mt-[2px] text-[10.5px] text-white/55">
            前置 {byId.get(tip.id)?.n_pre} · 后续 {byId.get(tip.id)?.n_post} ·
            <span className="tnum"> {byId.get(tip.id)?.n}</span> 道题 ·
            {rarityOf(deg.get(tip.id) || 0).label}
          </div>
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2.5 left-3 rounded-lg bg-black/35 px-2.5 py-1
                      text-[10.5px] text-white/45">
        拖拽平移 · 滚轮缩放 · 点星看详情 · 点大类标签隐藏 · 由内到外 = 由浅入深
      </div>
    </div>
  )
}

function hexA(hex: string, a: number) {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${a})`
}
