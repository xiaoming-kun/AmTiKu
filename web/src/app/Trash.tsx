/** 回收站 + 删除确认弹窗。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 *  「删除」不是真删：移进回收站，随时能恢复。
 */
import { useEffect, useState } from 'react'
import type { Q } from '@/lib/types'
import { api } from '@/lib/api'


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
    <div className="h-full overflow-y-auto px-4 py-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-[11.5px]">
        <span className="font-medium text-ink">{items.length} 道</span>
        <span className="text-ink-faint">删除的题留在这里，随时能放回去</span>
        {msg && <span className="text-has">{msg}</span>}
        {err && <span className="text-warn">✗ {err}</span>}
        {items.length > 0 && (
          <span className="ml-auto inline-flex gap-1">
            <button disabled={busy} onClick={() => restore(items.map((x) => x.key))}
              className="press rounded-md border border-brand/40 bg-brand-soft px-2 py-[3px]
                         font-medium text-brand-ink hover:bg-brand-soft/70 disabled:opacity-40">
              全部恢复
            </button>
            {surePurge ? (
              <span className="inline-flex items-center gap-1">
                <input type="password" value={pw} autoFocus
                  onChange={(e) => setPw(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') purge([]) }}
                  placeholder="口令"
                  className="w-[76px] rounded-md border border-warn/40 bg-bg px-1.5 py-[2px]
                             text-[11px] outline-none" />
                <button disabled={busy} onClick={() => purge([])}
                  className="press rounded-md border border-warn/50 bg-warn-soft px-2 py-[3px]
                             font-medium text-warn disabled:opacity-40">
                  确认永久删除 {items.length} 道
                </button>
              </span>
            ) : (
              <button onClick={() => setSurePurge(true)} onMouseLeave={() => setSurePurge(false)}
                className="press rounded-md border border-border px-2 py-[3px] text-ink-faint
                           hover:border-warn/40 hover:text-warn">
                清空回收站
              </button>
            )}
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <div className="flex h-[60%] flex-col items-center justify-center gap-2 text-[12.5px] text-ink-faint">
          <span>回收站是空的</span>
          <span className="text-[11.5px]">在题目详情里点「删除」，题目会移到这里</span>
        </div>
      ) : (
        <ul className="anim-stagger space-y-1.5">
          {items.map((x) => (
            <li key={x.key}
              className="flex items-start gap-2 rounded-lg border border-border bg-surface px-3 py-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12.5px] text-ink">
                  {x.stem || x.key}
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10.5px] text-ink-faint">
                  <span className="font-mono">{x.key}</span>
                  <span>删于 {x.deleted_at}</span>
                  {x.reason && <span className="text-warn">原因：{x.reason}</span>}
                  <span className={x.has_solution ? 'text-has' : ''}>
                    {x.has_solution ? '✓解析' : '✗解析'}
                  </span>
                </span>
              </span>
              <span className="flex shrink-0 gap-1">
                <button disabled={busy} onClick={() => restore([x.key])}
                  className="press rounded-md border border-brand/40 bg-brand-soft px-2 py-[3px]
                             text-[11px] font-medium text-brand-ink hover:bg-brand-soft/70
                             disabled:opacity-40">
                  恢复
                </button>
                <button disabled={busy} onClick={() => { setSurePurge(true); setPw('') }}
                  title="永久删除需要口令；先在上面输入口令再点"
                  className="press rounded-md border border-border px-2 py-[3px] text-[11px]
                             text-ink-faint hover:border-warn/40 hover:text-warn disabled:opacity-40">
                  ✕
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
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
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/35 p-4 anim-fade-in"
      onClick={onCancel}>
      <div className="w-[540px] max-w-full overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl anim-pop"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <span className="text-[14px] font-semibold text-warn">
            {n > 1 ? `删除这 ${n} 道题` : '删除这道题'}
          </span>
          <span className="text-[11.5px] text-ink-faint">删掉的题会移进回收站，可以恢复</span>
          <button onClick={onCancel}
            className="ml-auto text-[18px] leading-none text-ink-faint hover:text-ink">×</button>
        </div>

        <div className="px-4 py-3">
          {/* 删的是哪些题——必须让人看清楚，别删错 */}
          {n === 1 && qs[0] ? (
            <div className="mb-3 rounded-lg border border-border bg-muted/40 px-3 py-2">
              <div className="line-clamp-3 text-[12.5px] text-ink">{qs[0].stem}</div>
              <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[10.5px] text-ink-faint">
                <span className="font-mono">{qs[0].key}</span>
                <span>{qs[0].type_label}</span>
                {qs[0].point_titles?.[0] && <span>{qs[0].point_titles[0]}</span>}
              </div>
            </div>
          ) : (
            <div className="mb-3 rounded-lg border border-warn/35 bg-warn-soft/40 px-3 py-2">
              <div className="text-[13px] font-medium text-warn">
                要删 {n} 道题
              </div>
              <div className="mt-1 max-h-[132px] space-y-0.5 overflow-y-auto">
                {(keys || []).slice(0, 40).map((k) => (
                  <div key={k} className="truncate font-mono text-[10.5px] text-ink-soft">{k}</div>
                ))}
                {n > 40 && <div className="text-[10.5px] text-ink-faint">… 其余 {n - 40} 道</div>}
              </div>
            </div>
          )}

          <div className="mb-1.5 text-[11.5px] font-semibold text-ink-faint">
            删除原因 <span className="font-normal">（必选）</span>
          </div>
          <div className="mb-3 space-y-1">
            {reasons.map((r) => (
              <label key={r}
                className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5
                            text-[12.5px] transition-colors ${
                  reason === r ? 'border-warn/45 bg-warn-soft font-medium text-warn'
                               : 'border-border bg-bg text-ink-soft hover:bg-muted'}`}>
                <input type="radio" name="del-reason" checked={reason === r}
                  onChange={() => { setReason(r); setErr('') }}
                  className="accent-[var(--color-warn)]" />
                {r}
              </label>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11.5px] text-ink-faint">口令</span>
            <input type="password" value={pw} autoFocus
              onChange={(e) => { setPw(e.target.value); setErr('') }}
              onKeyDown={(e) => { if (e.key === 'Enter') ok() }}
              placeholder="删除口令"
              className="w-[120px] rounded-lg border border-border bg-bg px-2.5 py-1.5
                         text-[12.5px] outline-none focus:border-warn/50" />
            <span className="text-[10.5px] text-ink-faint">防误点，不是防人</span>
          </div>

          {err && <div className="mt-2 text-[11.5px] text-warn">✗ {err}</div>}
        </div>

        <div className="flex justify-end gap-2 border-t border-border bg-muted/40 px-4 py-3">
          <button onClick={onCancel}
            className="press rounded-lg border border-border bg-surface px-3 py-1.5
                       text-[12.5px] text-ink-soft hover:bg-muted">取消</button>
          <button onClick={ok} disabled={busy || !reason || !pw.trim()}
            className="press rounded-lg bg-warn px-3.5 py-1.5 text-[12.5px] font-medium
                       text-white disabled:opacity-40">
            {busy ? '删除中…' : n > 1 ? `确认删除 ${n} 道` : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  )
}
