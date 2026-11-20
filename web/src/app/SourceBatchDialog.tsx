/** 批量改出处弹窗：**按「来源 + 出处」在全库搜索，一次改完**。
 *
 *  用户的原话：「在修改出处的时候增加一个批量改的按钮，支持搜索全部符合的
 *  题目，统一把这个出处改正」。典型场景：一份卷子录进来时卷名打错/年份错，
 *  二十多道题都带着同一个错出处；一道一道改既慢又容易漏。
 *
 *  和「保存出处」的区别：
 *    · 保存出处只改当前这一道；
 *    · 这里由后端按当前题的**旧出处**搜索全库，题号各自保留，一次写回。
 *
 *  先预览（`dry_run`）再确认：命中多少道、哪些题、key 会不会跟着改、
 *  有没有撞车，全都摆出来；有撞车或没变化时确认按钮直接禁用。
 *
 *  弹窗用 portal 挂到 body：详情抽屉有 transform 动画，`fixed` 留在里面
 *  会以抽屉为参照，弹窗就跑偏了（和 SourceEditor 同一条理由）。
 */
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, ArrowRight, Layers, Loader2, X } from 'lucide-react'
import { api } from '@/lib/api'
import { toast } from '@/app/Toast'
import type { SourceBatchDone } from '@/lib/types'
import BusyOverlay from '@/app/BusyOverlay'

type PreviewItem = {
  key: string
  no: string
  year?: number | string
  type?: string
  new_key: string
  renamed: boolean
}

type Preview = {
  ok: boolean
  dry_run: boolean
  matched: number
  items: PreviewItem[]
  truncated?: boolean
  renamed: number
  kept: number
  target_existing: number
  noop: boolean
  conflicts: { key: string; new_key: string; why?: string }[]
}

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
const LABEL = 'text-[10.5px] font-semibold tracking-[0.06em] text-ink-faint'

/** 预览里最多列这么多道；再多就只报数量（全库最大的出处有两千多道）。 */
const SHOW_MAX = 100

export default function SourceBatchDialog({
  focusKey, oldBook, oldLabel, newBook, newLabel, year, onClose, onDone,
}: {
  /** 当前题 key：后端回传改后的完整记录（含新出处），详情不用再取一次。 */
  focusKey: string
  /** 匹配条件：当前题在库里的旧出处。 */
  oldBook: string
  oldLabel: string
  /** 统一改成的新值（来自详情页「出处」抽屉里的草稿）。 */
  newBook: string
  newLabel: string
  year: string
  onClose: () => void
  onDone: (res: SourceBatchDone) => void
}) {
  const [pv, setPv] = useState<Preview | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let alive = true
    setLoading(true); setErr(''); setPv(null)
    api.sourceBatch({
      old_book: oldBook, old_label: oldLabel,
      new_book: newBook, new_label: newLabel, new_year: year,
      dry_run: true, focus_key: focusKey,
    })
      .then((d: Preview) => { if (alive) setPv(d) })
      .catch((e) => { if (alive) setErr(msg(e)) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [focusKey, oldBook, oldLabel, newBook, newLabel, year, nonce])

  // Esc 关闭。capture 阶段先关弹层，别让 App 的全局 Esc 把背后的详情也关了。
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', h, true)
    return () => window.removeEventListener('keydown', h, true)
  }, [busy, onClose])

  const apply = async () => {
    if (!pv || busy) return
    setBusy(true); setErr('')
    try {
      const r: Preview & {
        changed: number; renames: SourceBatchDone['renames']; current?: any
      } = await api.sourceBatch({
        old_book: oldBook, old_label: oldLabel,
        new_book: newBook, new_label: newLabel, new_year: year,
        dry_run: false, focus_key: focusKey,
      })
      toast(`已批量改出处 ${r.changed ?? pv.matched} 道`
        + (r.renamed ? `，其中 ${r.renamed} 道 key 跟着改` : ''))
      onDone({ renames: r.renames || [], current: r.current })
    } catch (e) {
      setErr(msg(e))
      setBusy(false)
    }
  }

  const conflicts = pv?.conflicts || []
  const ready = !!pv && !loading && !err && !busy
    && pv.matched > 1 && !pv.noop && conflicts.length === 0
  const n = pv?.matched ?? 0

  return createPortal(
    <div className="fixed inset-0 z-[76] flex items-center justify-center p-5"
      onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose() }}>
      <div className="absolute inset-0 bg-scrim" onClick={() => !busy && onClose()} />
      <div role="dialog" aria-modal="true" aria-label="批量改出处"
        className="anim-pop relative flex max-h-[88vh] w-full max-w-[600px] flex-col
                   overflow-hidden rounded-[var(--radius-pop)] border border-border
                   bg-surface shadow-[var(--shadow-pop)]">

        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-3">
          <Layers size={15} className="text-brand" />
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold tracking-tight">批量改出处</div>
            <div className="truncate text-[11px] text-ink-faint">
              按「来源 + 出处」搜索全库 · 题号各自保留 · 一次写回
            </div>
          </div>
          <button onClick={() => !busy && onClose()} title="关闭（Esc）" className="icon-btn h-8 w-8">
            <X size={16} />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto p-4">
          <div className="grid grid-cols-[1fr_18px_1fr] items-stretch gap-1.5">
            <div className="min-w-0 rounded-xl border border-border bg-bg px-3 py-2.5">
              <div className={LABEL}>旧出处（全库匹配）</div>
              <div className="mt-1 text-[12.5px] font-medium text-ink-soft">
                <span className="truncate">{oldBook}</span>
              </div>
              <div className="mt-0.5 break-words text-[11.5px] leading-relaxed text-ink-faint">
                {oldLabel}
              </div>
            </div>
            <div className="grid place-items-center text-ink-faint">
              <ArrowRight size={14} />
            </div>
            <div className="min-w-0 rounded-xl border border-brand-line bg-brand-soft/60 px-3 py-2.5">
              <div className={`${LABEL} text-brand-ink`}>新出处（统一改成）</div>
              <div className="mt-1 text-[12.5px] font-medium text-ink">
                <span className="truncate">{newBook}</span>
              </div>
              <div className="mt-0.5 break-words text-[11.5px] leading-relaxed text-ink-soft">
                {newLabel}
              </div>
              <div className="mt-1 text-[11px] text-ink-faint">
                年份：{year || '（清空）'}
              </div>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-[12.5px] text-ink-faint">
              <Loader2 size={15} className="animate-spin" />正在搜索全库相同出处的题…
            </div>
          ) : err ? (
            <div className="rounded-xl border border-warn-line bg-warn-soft px-3 py-2.5
                            text-[11.5px] leading-relaxed text-warn">
              <div className="inline-flex items-center gap-1 font-medium">
                <AlertTriangle size={12} />{err}
              </div>
              <div className="mt-1.5">
                <button onClick={() => setNonce((v) => v + 1)}
                  className="press rounded-md border border-warn-line bg-surface px-2 py-[3px]
                             text-[11px] font-medium text-warn hover:bg-warn-soft/70">
                  重新搜索
                </button>
              </div>
            </div>
          ) : pv ? (
            <>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-xl
                              border border-border bg-surface-2 px-3 py-2.5">
                <span className="text-[12.5px] text-ink-soft">全库找到</span>
                <span className="tnum text-[17px] font-semibold text-ink">{pv.matched}</span>
                <span className="text-[12.5px] text-ink-soft">道「来源 + 出处」完全相同的题</span>
                <span className="min-w-0 flex-1" />
                {pv.renamed > 0 && (
                  <span className="rounded-full bg-brand-soft px-2 py-[2px] text-[10.5px] text-brand-ink">
                    key 改名 {pv.renamed} 道
                  </span>
                )}
                {pv.kept > 0 && (
                  <span className="rounded-full bg-muted px-2 py-[2px] text-[10.5px] text-ink-soft">
                    只改标签 {pv.kept} 道
                  </span>
                )}
                {pv.target_existing > 0 && !pv.noop && (
                  <span className="rounded-full bg-warn-soft px-2 py-[2px] text-[10.5px] text-warn">
                    新出处下已有 {pv.target_existing} 道
                  </span>
                )}
              </div>

              {pv.noop && (
                <div className="rounded-xl border border-border bg-muted/60 px-3 py-2.5
                                text-[11.5px] leading-relaxed text-ink-soft">
                  新旧出处（含年份）完全一样，没有可改的内容。
                </div>
              )}

              {!pv.noop && pv.matched === 1 && (
                <div className="rounded-xl border border-border bg-muted/60 px-3 py-2.5
                                text-[11.5px] leading-relaxed text-ink-soft">
                  全库只有这一道是这个出处，直接点上面的「保存出处」就行。
                </div>
              )}

              {!pv.noop && pv.matched > 500 && (
                <div className="rounded-xl border border-warn-line bg-warn-soft px-3 py-2.5
                                text-[11.5px] leading-relaxed text-warn">
                  <span className="inline-flex items-center gap-1 font-medium">
                    <AlertTriangle size={12} />这次要改 {pv.matched} 道，改动面很大
                  </span>
                  <div className="mt-0.5">
                    确认这些题确实都属于同一份卷子再继续；改完会写一份变更记录。
                  </div>
                </div>
              )}

              {conflicts.length > 0 && (
                <div className="rounded-xl border border-danger-line bg-danger-soft px-3 py-2.5
                                text-[11.5px] leading-relaxed text-danger">
                  <div className="inline-flex items-center gap-1 font-medium">
                    <AlertTriangle size={12} />有 {conflicts.length} 道改名后会撞车，不能批量改
                  </div>
                  {conflicts.slice(0, 5).map((c) => (
                    <div key={c.key} className="mt-1 break-all font-mono text-[10.5px]">
                      {c.key} → {c.new_key}
                      {c.why ? `（${c.why}）` : ''}
                    </div>
                  ))}
                  <div className="mt-1">先把目标 key 上的题改走，或改一个不重名的出处。</div>
                </div>
              )}

              {!pv.noop && pv.matched > 1 && (
                <div className="overflow-hidden rounded-xl border border-border">
                  <div className="flex items-center justify-between border-b border-border
                                  bg-surface-2 px-3 py-1.5">
                    <span className="text-[11px] font-medium text-ink-soft">
                      将要修改的题
                    </span>
                    <span className="text-[10.5px] text-ink-faint">
                      {pv.truncated ? `只列前 ${SHOW_MAX} 道` : '按题号排序'}
                    </span>
                  </div>
                  <div className="max-h-[230px] overflow-y-auto bg-surface">
                    {pv.items.map((it) => (
                      <div key={it.key}
                        className={`flex items-center gap-2 border-b border-border/60 px-3
                                    py-1.5 last:border-b-0 ${
                          it.key === focusKey ? 'bg-brand-soft/40' : ''}`}
                        title={it.key === focusKey ? '当前这道题' : undefined}>
                        <span className="tnum w-[62px] shrink-0 text-[11.5px] text-ink-soft">
                          第 {it.no} 题
                        </span>
                        <span className="min-w-0 flex-1 truncate font-mono text-[10.5px]
                                         text-ink-faint" title={it.new_key}>
                          {it.key}
                        </span>
                        {it.renamed && (
                          <span className="shrink-0 rounded bg-brand-soft px-1.5 py-[1px]
                                           text-[10px] text-brand-ink">改名</span>
                        )}
                        <span className="w-[42px] shrink-0 text-right text-[10px] text-ink-faint">
                          {it.year ? String(it.year) : '无年份'}
                        </span>
                      </div>
                    ))}
                    {pv.truncated && (
                      <div className="px-3 py-2 text-center text-[10.5px] text-ink-faint">
                        …还有 {pv.matched - pv.items.length} 道，确认后会一起改
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2 border-t border-border px-4 py-3">
          <span className="min-w-0 flex-1 text-[10.5px] leading-relaxed text-ink-faint">
            题号各自保留；key 跟着改的题会同步迁移卷子/讲义里的引用。
          </span>
          <button onClick={() => !busy && onClose()} disabled={busy}
            className="press h-[32px] rounded-lg border border-border bg-surface px-3
                       text-[12.5px] text-ink-soft transition-colors hover:border-border-strong
                       hover:text-ink disabled:opacity-40">
            取消
          </button>
          <button onClick={apply} disabled={!ready}
            className="press inline-flex h-[32px] items-center gap-1.5 rounded-lg bg-brand px-3
                       text-[12.5px] font-medium text-white shadow-[var(--shadow-brand)]
                       transition-[filter] hover:brightness-105 disabled:opacity-40">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
            {busy ? '正在改…' : `确认改 ${n} 道`}
          </button>
        </div>
      </div>
      {busy && (
        <BusyOverlay title="正在批量改出处…"
          note={pv?.renamed
            ? `共 ${pv.matched} 道；改名会重写分卷并迁移引用，可能要十几秒`
            : `共 ${pv?.matched ?? 0} 道；正在写回题库`} />
      )}
    </div>,
    document.body,
  )
}
