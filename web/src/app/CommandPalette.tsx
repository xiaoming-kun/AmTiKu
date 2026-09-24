/** 命令面板（⌘K / Ctrl+K）。
 *
 *  这是设计文档 `设计/UI设计.md` §原则4 里就写下的东西
 *  （「Cmd+K 命令面板（跳转/换卷/导出）」），一直没做。成熟产品里它是标配：
 *  Linear / Notion / Raycast / VS Code 都是同一个形状——
 *  **一个输入框 + 一串可执行项 + ↑↓ 选 + Enter 跑**。
 *  它解决的问题是"功能藏在三层菜单里"：导航有九个入口、动作有十几个，
 *  全记快捷键不现实，全铺在界面上又会把界面塞满。
 *
 *  无障碍按 WAI-ARIA combobox 写（输入框 role=combobox 指着一个 listbox，
 *  用 aria-activedescendant 报当前项）：屏幕阅读器能念出"第 3 项，共 12 项"，
 *  而不是只知道有个输入框。
 *
 *  几个刻意的取舍：
 *  ① **不做嵌套子命令**。一层平铺 + 搜索，比多级菜单快得多。
 *  ② **拼音/英文别名也能搜**（keywords）——中文输入法切来切去很烦。
 *  ③ 搜不到就让"回车去题库里搜这个词"顶上来，**不留死胡同**。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Search, CornerDownLeft, ArrowUp, ArrowDown } from 'lucide-react'
import { useUnmount } from '@/app/ui'

export type Cmd = {
  id: string
  label: string
  group: string
  icon?: ReactNode
  /** 右侧那个灰色小字（一般是快捷键） */
  hint?: string
  /** 额外匹配词：拼音、英文名、同义词。不进界面，只给搜索用。 */
  keywords?: string
  run: () => void
}

/** 极简打分：越靠前、越连续，分越高。够用就行，不引 fuse.js。 */
function score(c: Cmd, q: string): number {
  if (!q) return 1
  const hay = `${c.label} ${c.group} ${c.keywords || ''}`.toLowerCase()
  const label = c.label.toLowerCase()
  const i = hay.indexOf(q)
  if (i < 0) {
    // 退化成"按顺序出现的字符"（输入法打一半也能命中）
    let k = 0
    for (const ch of label) if (ch === q[k]) k++
    return k === q.length ? 2 : 0
  }
  if (label.startsWith(q)) return 100
  if (label.includes(q)) return 60
  return 30 - Math.min(i, 20)
}

export default function CommandPalette({ open, onClose, commands, onSearch }: {
  open: boolean
  onClose: () => void
  commands: Cmd[]
  /** 搜不到东西时，回车把这个词丢给题库搜索 */
  onSearch: (q: string) => void
}) {
  const [q, setQ] = useState('')
  const [idx, setIdx] = useState(0)
  // 退场也要有动画（见 ui.tsx 的 useUnmount）
  const { shown, closing } = useUnmount(open, 150)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  // 每次打开都从干净状态开始——上次搜的词留在框里只会让人困惑
  useEffect(() => {
    if (open) { setQ(''); setIdx(0); setTimeout(() => inputRef.current?.focus(), 20) }
  }, [open])

  const hits = useMemo(() => {
    const nq = q.trim().toLowerCase()
    // **没有关键词时保持作者写下的顺序**，不要按分数/字典序排。
    // 空面板的第一项会被预选中（回车就跑），所以它必须是"最常用的那个"，
    // 而不是"碰巧按拼音排第一的那个"。
    if (!nq) return commands.slice(0, 40)
    return commands
      .map((c) => ({ c, s: score(c, nq) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s || a.c.label.localeCompare(b.c.label, 'zh'))
      .slice(0, 40)
      .map((x) => x.c)
  }, [commands, q])

  // 分组只是为了好看，顺序仍按分数走
  const groups = useMemo(() => {
    const out: { name: string; items: Cmd[] }[] = []
    for (const c of hits) {
      const g = out.find((x) => x.name === c.group)
      if (g) g.items.push(c)
      else out.push({ name: c.group, items: [c] })
    }
    return out
  }, [hits])

  // 命中项变了就把光标收回第一项（否则会停在一个越界的位置）
  useEffect(() => { setIdx(0) }, [q])

  useEffect(() => {
    if (!open) return
    listRef.current?.querySelectorAll('[role="option"]')[idx]
      ?.scrollIntoView({ block: 'nearest' })
  }, [idx, open])

  const plain = hits.length === 0 && q.trim().length > 0
  const active = hits[idx]

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); return }
    if (e.key === 'ArrowDown' || (e.key === 'n' && e.ctrlKey)) {
      e.preventDefault(); setIdx((i) => Math.min(hits.length - 1, i + 1)); return
    }
    if (e.key === 'ArrowUp' || (e.key === 'p' && e.ctrlKey)) {
      e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      if (plain) { onSearch(q.trim()); onClose(); return }
      if (active) { active.run(); onClose() }
    }
  }

  if (!shown) return null

  return (
    <div className={`${closing ? 'anim-fade-out' : 'anim-fade-in'} fixed inset-0 z-[70]
                    flex items-start justify-center bg-ink/25 px-4 pt-[12vh] backdrop-blur-[2px]`}
      onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label="命令面板"
        onMouseDown={(e) => e.stopPropagation()}
        className={`${closing ? 'anim-pop-out' : 'pop-c'} flex max-h-[min(560px,70vh)]
                   w-[min(620px,100%)] flex-col overflow-hidden rounded-[var(--radius-pop)]
                   border border-border bg-surface shadow-[var(--shadow-pop)]`}>

        {/* 输入框 = combobox，指着下面的 listbox */}
        <div className="flex shrink-0 items-center gap-2.5 border-b border-border px-4">
          <Search size={16} className="shrink-0 text-ink-faint" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
            role="combobox"
            aria-expanded="true"
            aria-controls="cmdk-list"
            aria-activedescendant={active ? `cmdk-${active.id}` : undefined}
            placeholder="输入命令、考点、动作…（拼音也行，如 daoshu）"
            className="h-[52px] min-w-0 flex-1 bg-transparent text-[14px] outline-none
                       placeholder:text-ink-faint"
          />
          <kbd className="shrink-0 rounded border border-border bg-surface-2 px-1.5 text-[10.5px]
                          leading-[18px] text-ink-faint">Esc</kbd>
        </div>

        <div ref={listRef} id="cmdk-list" role="listbox" aria-label="命令"
          className="min-h-0 flex-1 overflow-y-auto p-2">

          {plain ? (
            /* 搜不到不是死胡同：回车就把这个词丢给题库搜索 */
            <button role="option" aria-selected="true"
              onClick={() => { onSearch(q.trim()); onClose() }}
              className="flex w-full items-center gap-2.5 rounded-lg bg-brand-soft px-3 py-2.5 text-left">
              <Search size={15} className="shrink-0 text-brand-ink" />
              <span className="min-w-0 flex-1 truncate text-[13px] text-brand-ink">
                在题库里搜索「{q.trim()}」
              </span>
              <CornerDownLeft size={13} className="shrink-0 text-brand-ink/60" />
            </button>
          ) : hits.length === 0 ? (
            <div className="px-3 py-8 text-center text-[12.5px] text-ink-faint">
              没有匹配的命令
            </div>
          ) : (
            groups.map((g) => (
              <div key={g.name} role="group" aria-label={g.name} className="mb-1 last:mb-0">
                <div className="px-3 pb-1 pt-2 text-[10.5px] font-semibold tracking-[0.08em]
                                text-ink-faint">
                  {g.name}
                </div>
                {g.items.map((c) => {
                  const i = hits.indexOf(c)
                  const on = i === idx
                  return (
                    <button key={c.id} id={`cmdk-${c.id}`} role="option" aria-selected={on}
                      onMouseMove={() => setIdx(i)}
                      onClick={() => { c.run(); onClose() }}
                      className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left
                                  transition-colors ${on ? 'bg-brand-soft' : 'hover:bg-muted'}`}>
                      <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-md ${
                        on ? 'bg-surface text-brand-ink' : 'bg-muted text-ink-faint'}`}>
                        {c.icon}
                      </span>
                      <span className={`min-w-0 flex-1 truncate text-[13px] ${
                        on ? 'font-medium text-brand-ink' : 'text-ink'}`}>{c.label}</span>
                      {c.hint && (
                        <kbd className={`shrink-0 rounded border px-1.5 text-[10.5px] leading-[18px] ${
                          on ? 'border-brand-line bg-surface text-brand-ink'
                             : 'border-border bg-surface-2 text-ink-faint'}`}>{c.hint}</kbd>
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* 底部是操作提示，不是装饰 */}
        <div className="flex shrink-0 items-center gap-3 border-t border-border px-4 py-2
                        text-[11px] text-ink-faint">
          <span className="flex items-center gap-1"><ArrowUp size={11} /><ArrowDown size={11} />选择</span>
          <span className="flex items-center gap-1"><CornerDownLeft size={11} />执行</span>
          <span className="ml-auto tnum">{hits.length} 项</span>
        </div>
      </div>
    </div>
  )
}
