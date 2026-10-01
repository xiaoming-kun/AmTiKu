/** App 内公共小组件（多个页面共用）。
 *
 *  从 App.tsx 抽出来的：列表、详情、录入都要用，留在 App 里会让
 *  搬出去的子页面反向依赖 App（形成循环）。
 */
import { useEffect, useRef, useState } from 'react'
import { ChevronRight, X } from 'lucide-react'
import type { Flags as FlagMap } from '@/lib/types'

export function Flags({ flags, size = 'sm' }: { flags: FlagMap; size?: 'sm' | 'md' }) {
  /**
   * **只把"缺"的标出来，"有"的一律不显示。**
   *
   * 早先是五个方块全画（`✓答 ✓析 ✗图 ✓签`）。问题是：**有答案、有解析是常态**——
   * 一屏二十道题，八十个绿方块，全是噪音，真正要看的"缺图"反而淹在里面。
   * 现在反过来了：什么都没有＝干净，**冒出一个红方块就说明这儿缺东西**。
   */
  const items: [string, string][] = [['答案', '缺答'], ['解析', '缺析'], ['图', '缺图'], ['标签', '缺签'], ['小问', '缺问']]
  const missing = items.filter(([k]) => !flags[k])
  if (!missing.length) {
    // 全都有 → 列表里**什么都不画**（干净）；详情页要显式说一句"齐全"，
    // 不然用户会以为这块坏了。
    return size === 'md'
      ? <span className="rounded-md bg-has-soft px-1.5 py-[2px] text-[11px] font-medium text-has">
          ✓ 答案·解析·图·标签 齐全
        </span>
      : null
  }
  const cls = size === 'md' ? 'text-[11px] px-1.5 py-[2px]' : 'text-[10.5px] px-1.5 py-[1px]'
  return (
    <span className="inline-flex flex-wrap gap-1">
      {missing.map(([k, label]) => (
        <span key={k} title={`缺${k}`}
          className={`${cls} rounded-md bg-gap-soft font-medium text-gap`}>{label}</span>
      ))}
    </span>
  )
}

/** 弹层/抽屉右上角那颗关闭按钮。
 *
 *  以前是五个地方各写一行，而且**都是"一个没边框的小灰 ✕"**（图标 14~16px）——
 *  又小又不显眼，是整个弹层里最难找到、最不好点的一个东西。
 *  关闭是**逃生通道**，该一眼看到、闭着眼能点到，所以统一成：
 *  32px 的方块 + 描边 + 图标 18px，悬停时底色浮出来。
 *
 *  抽成组件是为了以后不再各写一份——这次就是五处各写各的，一起小。
 */
export function CloseBtn({ onClick, title = '关闭', className = '' }: {
  onClick: () => void; title?: string; className?: string
}) {
  return (
    <button onClick={onClick} title={title} aria-label={title}
      className={`press grid h-8 w-8 shrink-0 place-items-center rounded-lg border
                  border-border bg-surface text-ink-soft transition-colors
                  hover:border-border-strong hover:bg-muted hover:text-ink ${className}`}>
      <X size={18} strokeWidth={2.2} />
    </button>
  )
}

/** 卡片式面板。`pad` 控不控内边距——有些面板要自己画表头 */
export function Panel({ title, children, right, pad = true }: any) {
  return (
    <div className="overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface shadow-[var(--shadow-card)]">
      {title && (
        <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5">
          <span className="text-[12.5px] font-semibold">{title}</span>
          {right && <span className="ml-auto">{right}</span>}
        </div>
      )}
      <div className={pad ? 'p-3.5' : ''}>{children}</div>
    </div>
  )
}

export function Report({ n, title, children }: any) {
  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-surface p-3 shadow-[var(--shadow-card)]">
      <div className="mb-1.5 text-[12px] font-semibold text-ink-soft">
        <span className="mr-1.5 text-brand-ink">{n}</span>{title}
      </div>
      {children}
    </div>
  )
}

export const FLAG_KEYS = [['答案', '答'], ['解析', '析'], ['图', '图'], ['标签', '签']] as const

export const INGEST_SAMPLE = `\\begin{question}
设集合 $A=\\{x\\mid -1<x<3\\}$，$B=\\{0,1,2,3\\}$，则 $A\\cap B=$（\\quad）
\\begin{choices}
  \\item* $\\{0,1,2\\}$
  \\item $\\{1,2,3\\}$
\\end{choices}
\\end{question}
\\begin{solution}
由交集定义得 $\\{0,1,2\\}$.
\\end{solution}`

/* ══ 筛选用的胶囊 ══════════════════════════════════
   选中态用**品牌色实心 + 白字**，未选中是白底细描边。
   参考图里选中的胶囊是黑色的——同理，实心才有"选中"的分量；
   描边+浅底那套太软，一屏十几个看不出选了哪个。 */
export function Chip({ on, onClick, children, n, title, size = 'md' }: any) {
  const pad = size === 'sm' ? 'px-2 py-[3px] text-[11.5px]' : 'px-2.5 py-[5px] text-[12.5px]'
  return (
    <button onClick={onClick} title={title}
      className={`press inline-flex items-center gap-1 rounded-full border ${pad}
                  font-medium transition-colors ${on
                    ? 'border-brand bg-brand text-white shadow-[0_2px_8px_-3px_var(--color-brand)]'
                    : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
      {children}
      {n != null && (
        <span className={`tnum text-[10.5px] font-normal ${on ? 'text-white/75' : 'text-ink-faint'}`}>{n}</span>
      )}
    </button>
  )
}

/** 筛选面板里的一个维度。可折叠，折叠状态由父组件持有（这样才能「全部收起」）。 */
export function Section({ title, hint, right, open, onToggle, children }: {
  title: string; hint?: React.ReactNode; right?: React.ReactNode
  open: boolean; onToggle: () => void; children: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-1.5 flex items-center gap-1.5">
        <button onClick={onToggle}
          className="group flex min-w-0 items-center gap-1 text-[11.5px] font-semibold
                     tracking-wide text-ink-soft hover:text-ink">
          <ChevronRight size={12} strokeWidth={2.6}
            className={`shrink-0 text-ink-faint transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
          <span className="truncate">{title}</span>
        </button>
        {hint && <span className="tnum shrink-0 text-[10.5px] text-ink-faint">{hint}</span>}
        {right && <span className="ml-auto shrink-0">{right}</span>}
      </div>
      {open && <div className="anim-fade-in">{children}</div>}
    </section>
  )
}

/* ══ 分栏拖拽手柄 ══════════════════════════════════ */

/** 拖动分栏边界。宽度存 localStorage，下次打开还是你调好的比例。
 *
 *  做得**几乎看不见**：一条 1px 的线 + 悬停时才浮出来的把手。
 *  旧版是一条 5px 的灰带，常驻在界面上，是三栏里最显眼的元素——
 *  它不该有这种分量。 */
export function Grip({ width, setWidth, min, max }: {
  width: number; setWidth: (w: number) => void; min: number; max: number
}) {
  const [hot, setHot] = useState(false)
  const start = useRef({ x: 0, w: 0 })
  return (
    <div
      onPointerEnter={() => setHot(true)}
      onPointerLeave={() => setHot(false)}
      onPointerDown={(e) => {
        e.preventDefault()
        start.current = { x: e.clientX, w: width }
        const move = (ev: PointerEvent) => {
          const w = start.current.w + (ev.clientX - start.current.x)
          setWidth(Math.max(min, Math.min(max, w)))
        }
        const up = () => {
          window.removeEventListener('pointermove', move)
          window.removeEventListener('pointerup', up)
          document.body.style.cursor = ''
          document.body.style.userSelect = ''
        }
        window.addEventListener('pointermove', move)
        window.addEventListener('pointerup', up)
        document.body.style.cursor = 'col-resize'
        document.body.style.userSelect = 'none'
      }}
      title="拖动调整宽度"
      className="relative z-10 -mx-[3px] w-[7px] shrink-0 cursor-col-resize"
    >
      <span className={`absolute left-1/2 top-1/2 h-8 w-[2px] -translate-x-1/2 -translate-y-1/2
                        rounded-full transition-all duration-150 ${hot
                          ? 'bg-brand/70 opacity-100'
                          : 'bg-border-strong opacity-0'}`} />
    </div>
  )
}

/** 栏宽：带 localStorage 记忆 */
export function useWidth(key: string, init: number, min: number, max: number) {
  const [w, setW] = useState(() => {
    const v = Number(localStorage.getItem(key))
    return v >= min && v <= max ? v : init
  })
  useEffect(() => { localStorage.setItem(key, String(w)) }, [key, w])
  return [w, setW] as const
}

/** **让退场动画有时间播完**再卸载。
 *
 *  React 里 `open=false` 就直接不渲染了，元素"啪"地消失——进场有动画、
 * 退场没有，界面会显得生硬。这个钩子把"该不该渲染"和"该不该显示"
 * 拆开：`shown` 管渲染（延迟到动画播完），`closing` 管挂哪个 class。
 *
 *  用法：
 *      const { shown, closing } = useUnmount(open, 160)
 *      if (!shown) return null
 *      <div className={closing ? 'anim-slide-r-out' : 'anim-slide-r'}>…</div>
 *
 *  `ms` 要和 CSS 里那条退场动画的时长对上（宁可略长一两帧，别短）。
 */
export function useUnmount(open: boolean, ms: number) {
  const [shown, setShown] = useState(open)
  const [closing, setClosing] = useState(false)
  useEffect(() => {
    if (open) { setShown(true); setClosing(false); return }
    if (!shown) return
    setClosing(true)
    const t = setTimeout(() => { setShown(false); setClosing(false) }, ms)
    return () => clearTimeout(t)
  }, [open, shown, ms])
  return { shown, closing }
}

/** 数字变化时**滚一下**，而不是直接跳。
 *
 *  卷子从 2 题变 3 题、36 分变 41 分，直接替换数字人眼是跟不上的；
 *  300ms 内滚过去，既看得见变化又不会拖。尊重「减少动态效果」——
 *  那种情况下直接给终值。
 *
 *  **幅度大的变化不滚**：从 20934 滚到 1 会一路穿过几千个**任何筛选都给不出**
 *  的数字。用户盯着屏（或截图）看到的是「搜「断臂」→ 8840 道」这种假答案。
 *  滚动只在"加了一道题"这种小增量上才有意义，那里也才看得清。
 */
const SPIN_MAX = 200

export function Num({ value, className = '' }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value)
  // 屏幕上**当前画着**的数字。动画中途来新值就从这里续，
  // 而不是从上一段的起点跳回去（旧写法只在动画跑完才更新起点）。
  const cur = useRef(value)
  const raf = useRef(0)
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const a = cur.current, b = value
    if (reduce || a === b || Math.abs(b - a) > SPIN_MAX) {
      cur.current = b; setShown(b); return
    }
    const t0 = performance.now(), D = 300
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / D)
      // easeOutCubic：先快后慢，数字"落"在终值上
      const e = 1 - Math.pow(1 - k, 3)
      const v = Math.round(a + (b - a) * e)
      cur.current = v; setShown(v)
      if (k < 1) raf.current = requestAnimationFrame(tick)
      else cur.current = b
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [value])
  return <span className={`tnum ${className}`}>{shown}</span>
}

/** 开关型记忆（折叠状态）。懒得每处再写一遍 localStorage。 */
export function useFlag(key: string, init = false) {
  const [v, setV] = useState(() => {
    const s = localStorage.getItem(key)
    return s === null ? init : s === '1'
  })
  useEffect(() => { localStorage.setItem(key, v ? '1' : '0') }, [key, v])
  return [v, setV] as const
}

/** 顶栏明细里的一行：名称 + 数字 + 一句解释。 */
export function BaseRow({ label, n, hint, tone }: {
  label: string; n: number; hint: string; tone?: 'warn'
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={`tnum font-medium ${
        n === 0 ? 'text-ink-faint' : tone === 'warn' ? 'text-warn' : 'text-ink-soft'}`}>
        {n}
      </span>
      <span className={n === 0 ? 'text-ink-faint' : 'text-ink'}>{label}</span>
      <span className="truncate text-[10.5px] text-ink-faint">{hint}</span>
    </div>
  )
}
