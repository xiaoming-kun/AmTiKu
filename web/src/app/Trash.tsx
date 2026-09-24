/** 回收站 + 删除确认弹窗。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 *  「删除」不是真删：移进回收站，随时能恢复。
 */
import { useEffect, useState } from 'react'
import { AlertTriangle, Check, Inbox, RotateCcw, Trash2, X } from 'lucide-react'
import type { Q } from '@/lib/types'
import { api } from '@/lib/api'
import { CloseBtn } from '@/app/ui'


/** 回收站。**删除的题放这儿，随时能放回去。**
 *
 *  为什么单独一个地方：用户要求"删掉的题放在另外的位置，万一误删可以恢复"。
 *  所以删除动作要**看得见去处**——删完能立刻在这儿找到，而不是凭空消失。
 *  真正的「清空」是唯一不可逆的操作，必须二次确认。 */
export function Trash({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<any[]>([])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [surePurge, setSurePurge] = useState(false)
  const [pw, setPw] = useState('')          // 清空回收站的口令（不可逆）

  const load = () => api.trashList().then((d) => setItems(d.items || [])).catch(() => {})
  useEffect(() => { load() }, [])

  const restore = (keys: string[]) => {
    setBusy(true); setErr(''); setMsg('')
    api.trashRestore(keys)
      .then((d) => { setMsg(`已恢复 ${d.restored.length} 道`); load(); onChanged() })
      .catch((e) => setErr(String(e.message || e))).finally(() => setBusy(false))
  }
  const purge = (keys: string[]) => {
    setBusy(true); setErr(''); setMsg('')
    api.trashPurge(keys, pw)
      .then((d) => { setMsg(`已永久删除 ${d.purged} 道（不可恢复）`)
                     setSurePurge(false); setPw(''); load() })
      .catch((e) => setErr(String(e.message || e))).finally(() => setBusy(false))
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ── 页面标题区：是什么 · 有几道 · 能做什么 ── */}
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-surface px-6 py-5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-muted text-ink-faint">
          <Trash2 size={16} />
        </span>
        <span className="shrink-0 text-[15px] font-semibold tracking-tight text-ink">回收站</span>
        <span className="tnum shrink-0 rounded-full bg-muted px-2 py-[2px] text-[11.5px]
                         font-medium text-ink-soft">
          {items.length} 道
        </span>
        <span className="text-[11.5px] text-ink-faint">删除的题留在这里，随时能放回去</span>
        {msg && (
          <span className="inline-flex items-center gap-1 text-[11.5px] font-medium text-has">
            <Check size={12} className="shrink-0" />{msg}
          </span>
        )}
        {err && (
          <span className="inline-flex items-center gap-1 text-[11.5px] font-medium text-warn">
            <X size={12} className="shrink-0" />{err}
          </span>
        )}
        {items.length > 0 && (
          <span className="ml-auto inline-flex flex-wrap items-center gap-2">
            <button disabled={busy} onClick={() => restore(items.map((x) => x.key))}
              className="press inline-flex items-center gap-1.5 rounded-lg border border-border
                         bg-surface px-3 py-2 text-[12.5px] text-ink-soft transition-colors
                         hover:border-border-strong hover:text-ink disabled:opacity-40">
              <RotateCcw size={13} className="shrink-0" />全部恢复
            </button>
            {surePurge ? (
              <span className="anim-fade-in inline-flex items-center gap-1.5">
                <input type="password" value={pw} autoFocus
                  onChange={(e) => setPw(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') purge([]) }}
                  placeholder="口令"
                  className="h-[32px] w-[86px] rounded-lg border border-warn-line bg-bg px-2.5
                             text-[12px] outline-none transition-[border-color,box-shadow] duration-150
                             placeholder:text-ink-faint focus:bg-surface
                             focus:shadow-[0_0_0_3px_var(--color-warn-soft)]" />
                <button disabled={busy} onClick={() => purge([])}
                  className="press inline-flex items-center gap-1.5 rounded-lg border border-warn-line
                             bg-warn-soft px-3 py-2 text-[12.5px] font-medium text-warn
                             transition-colors hover:brightness-[0.98] disabled:opacity-40">
                  <AlertTriangle size={13} className="shrink-0" />
                  确认永久删除 {items.length} 道
                </button>
              </span>
            ) : (
              <button onClick={() => setSurePurge(true)} onMouseLeave={() => setSurePurge(false)}
                className="press inline-flex items-center gap-1.5 rounded-lg border border-border
                           bg-surface px-3 py-2 text-[12.5px] text-ink-faint transition-colors
                           hover:border-warn-line hover:bg-warn-soft hover:text-warn">
                <Trash2 size={13} className="shrink-0" />清空回收站
              </button>
            )}
          </span>
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <Inbox size={22} className="text-border-strong" />
            <span className="text-[12.5px] text-ink-faint">回收站是空的</span>
            <span className="text-[11.5px] text-ink-faint/80">在题目详情里点「删除」，题目会移到这里</span>
          </div>
        ) : (
          <ul className="anim-stagger space-y-2">
            {items.map((x) => (
              <li key={x.key}
                className="card-lift flex items-start gap-3 rounded-[var(--radius-card)] border
                           border-border bg-surface p-3.5 shadow-[var(--shadow-card)]">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] leading-relaxed text-ink">
                    {x.stem || x.key}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px]
                                   text-ink-faint">
                    <span className="font-mono text-[10.5px]">{x.key}</span>
                    <span>删于 {x.deleted_at}</span>
                    {x.reason && (
                      <span className="inline-flex items-center gap-1 rounded-md bg-warn-soft px-1.5
                                       py-[1px] font-medium text-warn">
                        原因：{x.reason}
                      </span>
                    )}
                    <span className={`inline-flex items-center gap-0.5 ${
                      x.has_solution ? 'text-has' : 'text-gap'}`}>
                      {x.has_solution
                        ? <Check size={11} className="shrink-0" />
                        : <X size={11} className="shrink-0" />}
                      解析
                    </span>
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <button disabled={busy} onClick={() => restore([x.key])}
                    className="press inline-flex items-center gap-1 rounded-lg border border-border
                               bg-surface px-2.5 py-[5px] text-[12px] text-ink-soft transition-colors
                               hover:border-border-strong hover:text-ink disabled:opacity-40">
                    <RotateCcw size={12} className="shrink-0" />恢复
                  </button>
                  <button disabled={busy} onClick={() => { setSurePurge(true); setPw('') }}
                    title="永久删除需要口令；先在上面输入口令再点"
                    className="press inline-flex h-[28px] w-[28px] items-center justify-center
                               rounded-lg border border-border bg-surface text-ink-faint
                               transition-colors hover:border-warn-line hover:bg-warn-soft
                               hover:text-warn disabled:opacity-40">
                    <Trash2 size={12} />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

/** 删题的**弹窗**。
 *
 *  用户的要求：「删除操作做成弹窗，这样可操作性比较强」，
 *  并且**原因做成选项**——删题是常态（高考不考的题要清掉），
 *  每条都该有原因；自由文本会写成五花八门，事后统计不出来。
 *
 *  弹窗里一次看全四件事：删的是哪道题、为什么删、口令、删完去哪。
 *  原先挤在详情页底部那一条里，字小、容易被忽略。 */
export function DeleteModal({ qs, keys, onCancel, onConfirm }: {
  qs: Q[]
  keys?: string[]              // 批量删时给题号（列表里可能没有完整对象）
  onCancel: () => void
  onConfirm: (reason: string, note: string, password: string) => Promise<void>
}) {
  const [reasons, setReasons] = useState<string[]>([])
  const [reason, setReason] = useState('')
  const [note] = useState('')
  const [pw, setPw] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const n = keys?.length || qs.length

  useEffect(() => {
    // 默认选中第一条「现在的高考不考了」——绝大多数删除都是这个原因
    api.trashReasons().then((d) => {
      const xs = d.items || []
      setReasons(xs)
      setReason((cur) => cur || xs[0] || '')
    }).catch(() => {})
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [])

  const ok = () => {
    if (!reason) { setErr('先选一个删除原因'); return }
    if (!pw.trim()) { setErr('要填口令'); return }
    setBusy(true); setErr('')
    onConfirm(reason + (note.trim() ? '：' + note.trim() : ''), '', pw)
      .catch((e: any) => setErr(String(e.message || e)))
      .finally(() => setBusy(false))
  }

  return (
    <div className="anim-fade-in fixed inset-0 z-[60] flex items-center justify-center
                    bg-ink/25 p-4 backdrop-blur-[2px]"
      onClick={onCancel}>
      <div className="pop-c w-[540px] max-w-full rounded-[var(--radius-pop)] border border-border
                      bg-surface p-4 shadow-[var(--shadow-pop)]"
        onClick={(e) => e.stopPropagation()}>
        <div className="mb-3.5 flex items-start gap-2.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-warn-soft text-warn">
            <AlertTriangle size={15} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[15px] font-semibold tracking-tight text-warn">
              {n > 1 ? `删除这 ${n} 道题` : '删除这道题'}
            </div>
            <div className="mt-0.5 text-[11.5px] text-ink-faint">删掉的题会移进回收站，可以恢复</div>
          </div>
          <CloseBtn onClick={onCancel} className="-mr-1 -mt-0.5" />
        </div>

        <div>
          {/* 删的是哪些题——必须让人看清楚，别删错 */}
          {n === 1 && qs[0] ? (
            <div className="mb-3.5 rounded-lg border border-border bg-bg px-3 py-2.5">
              <div className="line-clamp-3 text-[12.5px] leading-relaxed text-ink">{qs[0].stem}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-ink-faint">
                <span className="font-mono text-[10.5px]">{qs[0].key}</span>
                <span>{qs[0].type_label}</span>
                {qs[0].point_titles?.[0] && <span>{qs[0].point_titles[0]}</span>}
              </div>
            </div>
          ) : (
            <div className="mb-3.5 rounded-lg border border-warn-line bg-warn-soft/60 px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-[12.5px] font-medium text-warn">
                <AlertTriangle size={13} className="shrink-0" />
                要删 {n} 道题
              </div>
              <div className="mt-1.5 max-h-[132px] space-y-0.5 overflow-y-auto">
                {(keys || []).slice(0, 40).map((k) => (
                  <div key={k} className="truncate font-mono text-[10.5px] text-ink-soft">{k}</div>
                ))}
                {n > 40 && <div className="text-[10.5px] text-ink-faint">… 其余 {n - 40} 道</div>}
              </div>
            </div>
          )}

          <div className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
            删除原因 <span className="font-normal tracking-normal">（必选）</span>
          </div>
          <div className="mb-3.5 space-y-1.5">
            {reasons.map((r) => (
              <label key={r}
                className={`press flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2
                            text-[12.5px] transition-colors ${
                  reason === r ? 'border-warn-line bg-warn-soft font-medium text-warn'
                               : 'border-border bg-surface text-ink-soft hover:border-border-strong hover:bg-muted'}`}>
                <input type="radio" name="del-reason" checked={reason === r}
                  onChange={() => { setReason(r); setErr('') }}
                  className="accent-[var(--color-warn)]" />
                {r}
              </label>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="shrink-0 text-[11.5px] text-ink-faint">口令</span>
            <input type="password" value={pw} autoFocus
              onChange={(e) => { setPw(e.target.value); setErr('') }}
              onKeyDown={(e) => { if (e.key === 'Enter') ok() }}
              placeholder="删除口令"
              className="h-[32px] w-[132px] rounded-lg border border-border bg-bg px-2.5 text-[12.5px]
                         outline-none transition-[border-color,box-shadow] duration-150
                         placeholder:text-ink-faint focus:border-warn-line focus:bg-surface
                         focus:shadow-[0_0_0_3px_var(--color-warn-soft)]" />
            <span className="text-[11px] text-ink-faint">防误点，不是防人</span>
          </div>

          {err && (
            <div className="mt-2.5 flex items-start gap-1.5 rounded-lg border border-warn-line
                            bg-warn-soft px-2.5 py-2 text-[11.5px] text-warn">
              <X size={13} className="mt-[1px] shrink-0" />{err}
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-2 border-t border-border pt-3.5">
          <button onClick={onCancel}
            className="press rounded-lg border border-border bg-surface px-3 py-2 text-[12.5px]
                       text-ink-soft transition-colors hover:border-border-strong hover:text-ink">
            取消
          </button>
          <button onClick={ok} disabled={busy || !reason || !pw.trim()}
            className="press inline-flex items-center gap-1.5 rounded-lg bg-warn px-3.5 py-2 text-[12.5px]
                       font-medium text-white hover:brightness-105 disabled:opacity-40">
            <Trash2 size={13} className="shrink-0" />
            {busy ? '删除中…' : n > 1 ? `确认删除 ${n} 道` : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  )
}
