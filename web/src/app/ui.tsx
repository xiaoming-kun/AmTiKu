/** App 内公共小组件（多个页面共用）。
 *
 *  从 App.tsx 抽出来的：列表、详情、录入都要用，留在 App 里会让
 *  搬出去的子页面反向依赖 App（形成循环）。
 */
import { useEffect, useRef, useState } from 'react'
import type { Flags } from '@/lib/types'


export function Flags({ flags, size = 'sm' }: { flags: Flags; size?: 'sm' | 'md' }) {
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
      ? <span className="rounded bg-has-soft px-1.5 py-[2px] text-[11px] font-medium text-has">
          ✓ 答案·解析·图·标签 齐全
        </span>
      : null
  }
  const cls = size === 'md' ? 'text-[11px] px-1.5 py-[2px]' : 'text-[10px] px-1 py-[1px]'
  return (
    <span className="inline-flex flex-wrap gap-1">
      {missing.map(([k, label]) => (
        <span key={k} title={`缺${k}`}
          className={`${cls} rounded font-medium bg-gap-soft text-gap`}>{label}</span>
      ))}
    </span>
  )
}

export function Panel({ title, children }: any) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3.5">
      <div className="mb-2 text-[11.5px] font-semibold text-ink-soft">{title}</div>
      {children}
    </div>
  )
}

export function Report({ n, title, children }: any) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3">
      <div className="mb-1.5 text-[11.5px] font-semibold text-ink-soft">
        <span className="mr-1 text-brand-ink">{n}</span>{title}
      </div>
      {children}
    </div>
  )
}

/* ══ 三栏拖拽手柄 ══════════════════════════════════ */

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

export function Chip({ on, onClick, children, n }: any) {
  return (
    <button onClick={onClick}
      className={`rounded-lg border px-2 py-1 text-[12px] transition-colors ${
        on ? 'border-brand/30 bg-brand-soft font-medium text-brand-ink'
           : 'border-border bg-surface text-ink-soft hover:bg-muted'}`}>
      {children}
      {n != null && <span className={`ml-1 text-[10px] ${on ? 'text-brand-ink/70' : 'text-ink-faint'}`}>{n}</span>}
    </button>
  )
}

/** 一个筛选维度：平时是按钮，点开是面板。
 *
 *  为什么不做成常驻列表：维度有五个（类别/年份/题型/难度/只看有），
 *  每个都铺开会把左边塞满，考点树就没地方了——而**考点才是总纲**。
 *  收成一格一格，谁选中了谁亮起来，一眼看得出当前筛了什么。 */
export function FacetMenu({ label, summary, active, onClear, children, wide }: {
  label: string; summary?: React.ReactNode; active?: boolean
  onClear?: () => void; children: React.ReactNode; wide?: boolean
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  // 点外面收起。不做成模态——筛选时经常要一边点一边看列表
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((v) => !v)}
        className={`flex items-center gap-1 rounded-lg border px-2 py-[3px] text-[11.5px]
                    transition-colors ${active
                      ? 'border-brand/40 bg-brand-soft font-medium text-brand-ink'
                      : 'border-border bg-surface text-ink-soft hover:bg-muted'}`}>
        <span className="text-ink-faint">{label}</span>
        {summary}
        <span className="text-[9px] text-ink-faint">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className={`pop absolute left-0 top-[calc(100%+4px)] z-40 max-h-[380px] overflow-y-auto
                         rounded-xl border border-border bg-surface p-2.5 shadow-lg
                         ${wide ? 'w-[420px]' : 'w-[248px]'}`}>
          {children}
          {active && onClear && (
            <button onClick={() => { onClear(); setOpen(false) }}
              className="mt-2 w-full rounded-md border border-border bg-bg py-1 text-[11px]
                         text-ink-faint hover:border-warn/40 hover:text-warn">
              清除这一项
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** 拖动分栏边界。宽度存 localStorage，下次打开还是你调好的比例。 */
export function Grip({ width, setWidth, min, max }: {
  width: number; setWidth: (w: number) => void; min: number; max: number
}) {
  const start = useRef({ x: 0, w: 0 })
  return (
    <div
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
      title="拖动调整栏宽"
      className="group relative w-[5px] shrink-0 cursor-col-resize bg-border/50 transition-colors
                 hover:bg-brand/50 active:bg-brand"
    >
      <span className="absolute left-1/2 top-1/2 h-6 w-[2px] -translate-x-1/2 -translate-y-1/2
                       rounded-full bg-ink-faint/30 group-hover:bg-white/70" />
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

/** 顶栏明细里的一行：名称 + 数字 + 一句解释。 */
export function BaseRow({ label, n, hint, tone }: {
  label: string; n: number; hint: string; tone?: 'warn'
}) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className={`tabular-nums font-medium ${
        n === 0 ? 'text-ink-faint' : tone === 'warn' ? 'text-warn' : 'text-ink-soft'}`}>
        {n}
      </span>
      <span className={n === 0 ? 'text-ink-faint' : 'text-ink'}>{label}</span>
      <span className="truncate text-[10px] text-ink-faint">{hint}</span>
    </div>
  )
}
