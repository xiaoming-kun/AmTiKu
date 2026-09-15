/** App 内公共小组件（多个页面共用）。
 *
 *  从 App.tsx 抽出来的：列表、详情、录入都要用，留在 App 里会让
 *  搬出去的子页面反向依赖 App（形成循环）。
 */
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
