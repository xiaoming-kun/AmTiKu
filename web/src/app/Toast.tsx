/** 轻提示 + **撤销**。
 *
 *  为什么要它：刚把「加进卷子」改成了不跳视图、只让计数跳一下——回执太弱，
 *  而且**做错了没法退**（批量加了 30 道想撤，只能一道道去卷子里删）。
 *
 *  成熟产品在这件事上的共识是「宁可给撤销，也不要弹确认框」：
 *  「Prefer Undo Over Confirmation for Everyday Actions」——
 *  确认框在**做之前**拦你（每次都要多点一下），撤销在**做之后**兜你（只有真错了才用）。
 *  高频操作上，后者的总成本低得多。Gmail 的「已发送 · 撤销」就是这个形状。
 *
 *  几个照抄成熟产品的细节：
 *  ① **只堆最近 3 条**，再多就是刷屏，不是提示；
 *  ② **鼠标移上去暂停倒计时**（Gmail 的行为）——正要读的时候它不能消失；
 *  ③ 底部一条**倒计时细线**，如实告诉人"这窗口还剩多久"，而不是突然消失；
 *  ④ 有撤销按钮的多给几秒（6s），纯告知的短一点（3.2s）。
 *
 *  调用方式和项目里既有的 `reportErr` 一致（模块级注入 + 直接调用），
 *  这样任何组件都能 `toast(...)`，不必把 push 一路当 prop 传下去。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, TriangleAlert, X } from 'lucide-react'

export type ToastAction = { label: string; run: () => void }

export type Item = {
  id: number
  text: string
  action?: ToastAction
  ms: number
  tone: 'ok' | 'info' | 'warn'
}

type Sink = (t: Omit<Item, 'id'>) => void
let sink: Sink | null = null
let dismisser: (() => void) | null = null

/** Toaster 挂载时把自己注册进来；卸载时摘掉（不留悬空引用）。 */
export function setToastSink(fn: Sink | null) { sink = fn }
export function setToastDismisser(fn: (() => void) | null) { dismisser = fn }

/** 把现在挂着的提示全收掉。
 *
 *  什么时候要它：**一个动作把之前的撤销都作废了**的时候。
 *  比如刚「加入卷子」两条、接着「清空卷子」——那两条的撤销这时候去点，
 *  只会把已经不在卷子里的题再删一遍（无害但莫名其妙）。
 *  清空的那条自己带完整撤销，所以旧的就没必要留着了。 */
export function dismissToasts() { dismisser?.() }

/** 弹一条提示。`action` 给了就有撤销按钮，自动多留几秒。 */
export function toast(text: string, opts?: { action?: ToastAction; tone?: Item['tone']; ms?: number }) {
  sink?.({
    text,
    action: opts?.action,
    tone: opts?.tone ?? 'ok',
    ms: opts?.ms ?? (opts?.action ? 6000 : 3200),
  })
}

const MAX_STACK = 3
let seq = 0

export function Toaster() {
  const [list, setList] = useState<Item[]>([])
  // 正在退场的那些：先标上，动画播完再从列表里删
  const [leaving, setLeaving] = useState<Set<number>>(new Set())
  useEffect(() => {
    setToastSink((t) => setList((xs) => [...xs, { ...t, id: ++seq }].slice(-MAX_STACK)))
    setToastDismisser(() => setList([]))
    return () => { setToastSink(null); setToastDismisser(null) }
  }, [])
  /** 先播退场再移除。**不能直接删** —— 那样提示是"啪"地消失的。 */
  const done = useCallback((id: number) => {
    setLeaving((s) => new Set(s).add(id))
    setTimeout(() => {
      setList((xs) => xs.filter((x) => x.id !== id))
      setLeaving((s) => { const n = new Set(s); n.delete(id); return n })
    }, 150)
  }, [])
  if (!list.length) return null
  return (
    <div className="pointer-events-none fixed bottom-6 left-1/2 z-[60] flex -translate-x-1/2
                    flex-col items-center gap-2">
      {list.map((t) => <One key={t.id} t={t} onDone={done} leaving={leaving.has(t.id)} />)}
    </div>
  )
}

function One({ t, onDone, leaving }: {
  t: Item; onDone: (id: number) => void; leaving: boolean
}) {
  const [paused, setPaused] = useState(false)
  const left = useRef(t.ms)                    // 还剩多久（暂停时不再走）
  const since = useRef(0)

  useEffect(() => {
    if (paused) return
    since.current = Date.now()
    const h = setTimeout(() => onDone(t.id), left.current)
    return () => {
      clearTimeout(h)
      left.current -= Date.now() - since.current   // 暂停时把已过去的那段扣掉
    }
  }, [paused, onDone, t.id])

  const Tone = t.tone === 'warn' ? TriangleAlert : Check

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className={`${leaving ? 'anim-toast-out' : 'anim-fade-up'} pointer-events-auto relative
                 flex items-center gap-3 overflow-hidden rounded-full bg-ink py-2 pl-3.5 pr-2
                 text-[12.5px] text-white shadow-[var(--shadow-pop)]`}>
      <Tone size={14} strokeWidth={2.4}
        className={t.tone === 'warn' ? 'shrink-0 text-warn-line' : 'shrink-0 text-has-line'} />
      <span className="max-w-[42ch] truncate">{t.text}</span>
      {t.action && (
        <button
          onClick={() => { t.action!.run(); onDone(t.id) }}
          className="press shrink-0 rounded-full px-2 py-[3px] font-medium text-brand-soft
                     underline underline-offset-2 hover:bg-white/10 hover:text-white">
          {t.action.label}
        </button>
      )}
      <button onClick={() => onDone(t.id)} title="关掉"
        className="press grid h-5 w-5 shrink-0 place-items-center rounded-full
                   text-white/45 hover:bg-white/10 hover:text-white">
        <X size={12} />
      </button>
      {/* 倒计时细线：**如实告诉人还剩多久**，而不是突然消失 */}
      <span className="absolute bottom-0 left-0 h-[2px] w-full bg-white/15">
        <span
          className="block h-full origin-left bg-brand-line"
          style={{
            animation: `toast-bar ${t.ms}ms linear forwards`,
            animationPlayState: paused ? 'paused' : 'running',
          }} />
      </span>
    </div>
  )
}
