/** 画布状态：块 / 页面 / 测量 / 适配缩放 / 拖拽。
 *
 *  从 CanvasEditor 抽出来的（审查报告 CPLX-1：一个组件管 8 件事）。
 *  只依赖 `ratio`（测量时要按当前页面比例算可用高度）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Q } from '@/lib/types'
import { request, reportErr } from '@/lib/api'
import {
  uid, type CBlock,
  MEASURE_DELAY_MS, FIT_MIN, FIT_MARGIN, RESIZE_SLACK_PCT, DEFAULT_Q_W, DEFAULT_Q_X,
  DEFAULT_Y, GAP_PCT,
} from '@/editor/shared'

export function useCanvas(ratio: string) {
  const [pages, setPages] = useState<{ blocks: CBlock[] }[]>([{ blocks: [] }])
  const [cur, setCur] = useState(0)
  const [sel, setSel] = useState<string | null>(null)
  // 每个块的「适配缩放」：内容比一页高时，自动算出缩小系数，
  // 导出时带给后端用 CSS zoom 缩放 → 一道大题也能收进一页
  const [fits, setFits] = useState<Record<string, number>>({})
  const [overflowed, setOverflowed] = useState<Set<string>>(new Set())
  // 块的**内容固有尺寸**（px）——用来限制缩放下限，
  // 保证「拉框时文字不重排、行距不变」
  const [natural, setNatural] = useState<Record<string, { w: number; h: number }>>({})
  const probeRef = useRef<Record<string, HTMLDivElement | null>>({})
  const fitsRef = useRef<Record<string, number>>({})
  const blocks = pages[cur]?.blocks || []

  /** 画布上引用的题 —— **按 key 精确取**，一个来源。
   *
   *  以前是把 前200样本 / 已选 / 抽屉 / 搜索结果 四处合并来找，
   *  每加一个新入口就漏一次（同一类 bug 修了 4 次）。现在画布需要哪些
   *  key 就拉哪些，来源唯一，不会再漏。
   */
  const [blockQs, setBlockQs] = useState<Map<string, Q>>(new Map())
  const canvasKeys = useMemo(
    () => [...new Set(blocks.filter((b) => b.type === 'question' && b.key)
                             .map((b) => b.key as string))],
    [blocks])
  const blockQsRef = useRef(blockQs)
  blockQsRef.current = blockQs
  const canvasKeysStr = canvasKeys.join('|')

  useEffect(() => {
    const missing = canvasKeys.filter((k) => !blockQsRef.current.has(k))
    if (!missing.length) return
    request(`/api/questions?keys=${missing.map(encodeURIComponent).join(',')}`)
      .then((d) => setBlockQs((prev) => {
        const m = new Map(prev)
        for (const qq of d.items || d.questions || []) m.set(qq.key, qq)
        return m
      }))
      .catch(reportErr)
  }, [canvasKeysStr])
  const canvasRef = useRef<HTMLDivElement>(null)
  const [canvasPx, setCanvasPx] = useState(900)
  const [measureTick, setMeasureTick] = useState(0)
  const measRef = useRef<Record<string, HTMLDivElement | null>>({})
  const draggingRef = useRef(false)        // 拖拽/缩放中：跳过测量，避免每帧强制布局
  const rafRef = useRef(0)                 // 拖拽的 rAF 句柄
  const dragCleanupRef = useRef<(() => void) | null>(null)
  /** 刚被「点进画布」的块 —— 只给它一次机会：在当前页放不下就自己占一页。
   *  用户手拖过的块不在此列，老师摆哪儿就是哪儿。 */
  const autoRef = useRef<string | null>(null)
  /** 测量每个块的内容是否超出框（框高由 h 决定时才有意义）。
   *  直接在浏览器里量真实 DOM，比后端估算准。 */
  const measure = useCallback(() => {
    const bad = new Set<string>()
    for (const [id, el] of Object.entries(measRef.current)) {
      if (!el) continue
      const box = el.parentElement
      if (!box) continue
      const boxH = box.getBoundingClientRect().height
      // 块没设高度（h=0）时不检测：高度自适应，不会溢出
      const explicitH = box.style.height
      if (!explicitH) continue
      if (el.getBoundingClientRect().height > boxH + 2) bad.add(id)
    }
    setOverflowed(bad)
  }, [])

  // 卸载时清掉可能还挂着的拖拽监听器（拖拽中关闭编辑器的情况）
  useEffect(() => () => { dragCleanupRef.current?.() }, [])

  // 跟踪画布实际像素宽（响应式，窗口变了字号也跟着变）
  useEffect(() => {
    const el = canvasRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setCanvasPx(el.clientWidth || 900))
    ro.observe(el)
    setCanvasPx(el.clientWidth || 900)
    return () => ro.disconnect()
  }, [])

  /** 量内容的**固有尺寸**：按画布满宽离屏渲染，量出单行所需的宽与高。
   *  这样缩框时不会低于这个尺寸 → 文字不重排。 */
  const measureNatural = useCallback(() => {
    const out: Record<string, { w: number; h: number }> = {}
    const canvas = canvasRef.current
    const canvasW = canvas?.clientWidth || canvasPx || 900
    const canvasH = canvas?.clientHeight || Math.round(canvasW * 9 / 16)
    const nextFits: Record<string, number> = { ...fitsRef.current }
    for (const b of blocks) {
      const el = probeRef.current[b.id]
      if (!el) continue
      const r = el.getBoundingClientRect()
      out[b.id] = { w: Math.ceil(r.width), h: Math.ceil(r.height) }
      // 自动适配：只处理**自适应高度**（h=0）的块 —— 显式高度的块
      // 走溢出红框警告，由老师自己决定怎么调
      if ((b.h ?? 0) === 0) {
        // 可用高度 = 从块的 y 到页底（再留 1.5% 边距）
        const avail = canvasH * (1 - (b.y ?? 0) / 100) - canvasH * FIT_MARGIN
        if (r.height > avail && avail > 40) {
          nextFits[b.id] = Math.max(FIT_MIN, avail / r.height)
        } else {
          delete nextFits[b.id]
        }
      }
    }
    // 清掉已删除块的残留（长会话下会慢慢累积）
    const live = new Set(blocks.map((b) => b.id))
    for (const k of Object.keys(nextFits)) if (!live.has(k)) delete nextFits[k]

    /** 刚点进来的块在当前页**放不下**（要塞就得缩小，或者干脆溢出页底）→
     *  让它自己占一页。挤成小字或把下半道题切掉，都是「题目显示不全」。
     *
     *  只对**新加的块**做这一次（autoRef 用完即清，也不动老师手摆过的块），
     *  而且页上得已有别的内容 —— 一道题本来就该占满一整页时不再折腾。 */
    const aid = autoRef.current
    if (aid) {
      autoRef.current = null
      const nb = blocks.find((b) => b.id === aid)
      const nat = out[aid]
      // 固有尺寸是按**满宽**量的，块实际 92% 宽 → 留 8% 余量
      const hitBottom = !!nat &&
        ((nb?.y ?? 0) / 100) * canvasH + nat.h * 1.08 > canvasH * (1 - FIT_MARGIN)
      if (nb && blocks.length > 1 && (aid in nextFits || hitBottom)) {
        const at = cur
        // 新页插在**当前页后面**（不是追加到最末）—— 老师在第 2 页接着加题时，
        // 新题该出现在第 3 页，而不是第 9 页
        setPages((prev) => [
          ...prev.slice(0, at + 1).map((p, i) => i === at
            ? { blocks: p.blocks.filter((b) => b.id !== aid) } : p),
          { blocks: [{ ...nb, y: DEFAULT_Y }] },
          ...prev.slice(at + 1),
        ])
        setCur(at + 1)                // 跟过去，让老师看见题去哪了
        return                        // 这一轮测量作废，下一页会重新量
      }
    }

    setNatural(out)
    // 只有真的变了才 set，避免每轮测量都触发重渲染
    const oldF = fitsRef.current
    const changed = Object.keys(nextFits).length !== Object.keys(oldF).length ||
      Object.keys(nextFits).some((k) => Math.abs((nextFits[k] || 1) - (oldF[k] || 1)) > 0.005)
    if (changed) { fitsRef.current = nextFits; setFits(nextFits) }
  }, [blocks, canvasPx])

  // 内容、比例、页面切换后重新测量
  useEffect(() => {
    // 拖拽中先不测 —— 否则每个 mousemove 都会触发全量 getBoundingClientRect
    // （强制同步布局），拖起来发涩（审查报告 PERF-4）
    if (draggingRef.current) return
    const t = setTimeout(() => { measure(); measureNatural() }, MEASURE_DELAY_MS)
    return () => clearTimeout(t)
  }, [blocks, ratio, cur, measure, measureNatural, measureTick])
  const mutate = (fn: (bs: CBlock[]) => CBlock[]) =>
    setPages((prev) => prev.map((p, i) => i === cur ? { ...p, blocks: fn(p.blocks) } : p))

  /** 新块的落点：接在当前页已有内容的**下面**（%）。
   *
   *  以前一律落在 `(4%, 6%)`，于是每加一道题都压在前一道题**同一个位置**上 ——
   *  画布看不出变化，用户报「加号不起作用」（实测：连点两下，两个块完全重叠）。
   *  这里直接量**真实 DOM** 的底边（块的 h 多为 0，只有浏览器知道它多高）。 */
  const nextTop = (): number => {
    const el = canvasRef.current
    const cr = el?.getBoundingClientRect()
    if (!cr?.height) return DEFAULT_Y
    let bottom = 0
    for (const b of blocks) {
      // 外层绝对定位的盒子才是块的真正大小（内层还带着 zoom）
      const box = measRef.current[b.id]?.parentElement
      if (!box) continue
      const r = box.getBoundingClientRect()
      bottom = Math.max(bottom, ((r.bottom - cr.top) / cr.height) * 100)
    }
    return bottom > 0 ? Math.min(100 - GAP_PCT, bottom + GAP_PCT) : DEFAULT_Y
  }

  const addBlock = (b: Partial<CBlock>) => {
    const nb: CBlock = {
      id: uid(), type: b.type || 'text', text: b.text || '',
      key: b.key, x: b.x ?? 6, y: b.y ?? nextTop(), w: b.w ?? 40, h: b.h ?? 0,
      z: blocks.length, fontSize: b.fontSize,
    }
    // 题目：默认满宽靠左 —— 题目是一整块内容，
    // 给 40% 宽会让选项挤成多行、字号也变小（用户截图反馈）
    if (nb.type === 'question') {
      nb.x = DEFAULT_Q_X; nb.w = DEFAULT_Q_W
    }
    // 表情：默认小尺寸，方便放到题目旁边
    if (nb.type === 'emoji') {
      nb.text = nb.text || '😡'
      nb.w = 8; nb.fontSize = nb.fontSize || 16
    }
    // 表格给个默认 2×3，避免空白
    if (nb.type === 'table' && !nb.headers) {
      nb.headers = ['列1', '列2', '列3']
      nb.rows = [['', '', ''], ['', '', '']]
      nb.w = 92
    }
    mutate((bs) => [...bs, nb])
    autoRef.current = nb.id
    setSel(nb.id)
    // 让新块滚进视野 —— 画布可能被滚到别处，光加进去用户是看不到的
    requestAnimationFrame(() => {
      canvasRef.current?.querySelector(`[data-bid="${nb.id}"]`)
        ?.scrollIntoView({ block: 'nearest' })
    })
  }

  /** 加一道题到画布。
   *
   *  同时把它**预置**进查找表 —— 否则在按 key 拉取返回前，
   *  画布上会先闪一下"题目（题号）"。
   */
  const addQuestion = (qq: Q) => {
    if (qq?.key) setBlockQs((m) => new Map(m).set(qq.key, qq))
    addBlock({ type: 'question', key: qq?.key })
  }

  const patch = (id: string, p: Partial<CBlock>) =>
    mutate((bs) => bs.map((b) => (b.id === id ? { ...b, ...p } : b)))

  const remove = (id: string) => {
    mutate((bs) => bs.filter((b) => b.id !== id))
    if (sel === id) setSel(null)
  }

  const bringToFront = (id: string) => {
    const mx = Math.max(0, ...blocks.map((b) => b.z || 0))
    patch(id, { z: mx + 1 })
  }

  /** 拖动移动 / 拖角缩放 */
  const startDrag = (e: React.MouseEvent, b: CBlock, mode: 'move' | 'resize') => {
    e.preventDefault(); e.stopPropagation()
    setSel(b.id)
    const el = canvasRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const sx = e.clientX, sy = e.clientY
    const o = { x: b.x, y: b.y, w: b.w, h: b.h }

    draggingRef.current = true

    const apply = (ev: MouseEvent) => {
      const dx = ((ev.clientX - sx) / rect.width) * 100
      const dy = ((ev.clientY - sy) / rect.height) * 100
      if (mode === 'move') {
        patch(b.id, {
          x: Math.max(0, Math.min(100 - o.w, o.x + dx)),
          y: Math.max(0, Math.min(100, o.y + dy)),
        })
      } else {
        // 缩放下限 = 内容固有尺寸（+0.6% 余量）。上限必须先钳到 100 ——
        // 之前 minW 能到 100.x，Math.max(minW, ...) 就突破 100（用户发现「宽 101%」）
        const nat = natural[b.id]
        const minW = nat ? Math.min(100, (nat.w / rect.width) * 100 + RESIZE_SLACK_PCT) : 2
        const minH = (nat && b.h > 0)
          ? Math.min(100, (nat.h / rect.height) * 100 + RESIZE_SLACK_PCT) : 0
        patch(b.id, {
          w: Math.min(100, Math.max(minW, Math.min(100 - o.x, o.w + dx))),
          h: Math.min(100, Math.max(minH, Math.min(100 - o.y, o.h + dy))),
        })
      }
    }
    // rAF 节流：一帧最多更新一次状态（原来每个 mousemove 都 setState，
    // 会把 1600 行的编辑器整棵重渲染）
    const onMove = (ev: MouseEvent) => {
      if (rafRef.current) return
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = 0
        apply(ev)
      })
    }
    const onUp = (ev: MouseEvent) => {
      if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = 0 }
      apply(ev)                       // 补上最后一帧，避免停在半路
      cleanup()
      draggingRef.current = false
      setMeasureTick((t) => t + 1)    // 拖完再测一次（拖拽中跳过了测量）
    }
    const cleanup = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      dragCleanupRef.current = null
    }
    dragCleanupRef.current = cleanup
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return {
    pages, setPages, cur, setCur, sel, setSel, blocks,
    fits, overflowed, natural, blockQs, canvasRef, measRef, probeRef,
    addBlock, addQuestion, patch, remove, bringToFront, startDrag,
  }
}
