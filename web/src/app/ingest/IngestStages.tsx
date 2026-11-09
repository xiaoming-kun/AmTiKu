/** 录入抽屉的提交条。
 *
 *  Source/Review 已各自独立；这里只剩 CommitBar：提交按钮、禁用规则、
 *  规则说明只维护一份。
 */
import { Check, Upload, X } from 'lucide-react'

export function CommitBar({
  pv, backfill, nearThreshold, err, msg, busy, tagging,
  selectedCount, badCount, onCommit,
}: {
  pv: any
  backfill: boolean
  nearThreshold: number
  err: string
  msg: string
  busy: boolean
  tagging: boolean
  selectedCount: number
  badCount: number
  onCommit: () => void
}) {
  const hasSameKey = !!(pv?.items || []).some((it: any) => it.same_key || it.near_dup)
  return (
    <div className="shrink-0 border-t border-border bg-surface px-4 py-3">
      {pv && (
        <div className="mb-2 rounded-lg border border-border bg-bg px-2.5 py-2
                        text-[11px] leading-relaxed text-ink-faint">
          {backfill
            ? <>规则：<b className="font-medium text-ink-soft">补旧题模式</b>
                → 只更新已有题的空考点/空难度，不新增、不改答案/解析/已有考点。</>
            : <>规则：库里已有同题，或整题相似 <b className="font-medium text-ink-soft">
                &gt;{nearThreshold}%</b> → 整题跳过，不新增、不更新（不补解析、不改答案、不并考点）。</>}
        </div>
      )}
      {err && pv && (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-warn-line
                        bg-warn-soft px-2.5 py-2 text-[11px] text-warn">
          <X size={12} className="mt-[1px] shrink-0" />{err}
        </div>
      )}
      {msg && pv && (
        <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-has-line
                        bg-has-soft px-2.5 py-2 text-[11px] text-has">
          <Check size={12} className="mt-[1px] shrink-0" />{msg}
        </div>
      )}
      <button onClick={onCommit}
        disabled={busy || tagging || !pv || selectedCount === 0 || badCount > 0}
        title={badCount ? '勾选的题里还有不能入库的'
          : (selectedCount === 0
            ? (hasSameKey ? '库里已有或高度相似，按规则整题跳过' : '先勾选题目')
            : '')}
        className="press flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand
                   px-4 py-2.5 text-[13px] font-semibold text-white
                   shadow-[var(--shadow-brand)] hover:brightness-105 disabled:opacity-40">
        <Upload size={13} className="shrink-0" />
        {backfill
          ? (selectedCount ? `补标签选中（${selectedCount} 道）` : '没有可补的已有题')
          : (selectedCount ? `确认入库选中（${selectedCount} 道）` : '没有可入库的新题')}
      </button>
      <div className="mt-1.5 text-center text-[10px] text-ink-faint">
        {backfill
          ? '补旧题模式 · 只更新已有题的空考点/难度 · 新题不新增、正文不改'
          : `只写入勾选的题 · 缺答案/解析/图的不让入库 · 已有/相似 >${nearThreshold}% 不更新`}
      </div>
    </div>
  )
}
