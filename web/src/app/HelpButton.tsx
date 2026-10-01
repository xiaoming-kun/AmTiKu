/** 右下角那颗「快捷键」浮球。
 *
 *  为什么必须有它：这一版加了一批**单键快捷键**（W/I/K/V/B/P/M/R/C）。
 *  快捷键没有面板可看，就只对写它的人有用——藏在代码注释里的快捷键
 *  等于不存在。所以给一个常驻的入口，随手一点就能查。
 *
 *  样式照着参考图的悬浮圆钮做：白底、细描边、大投影，不抢内容。
 */
import { useEffect, useRef, useState } from 'react'
import { CircleHelp } from 'lucide-react'
import { CloseBtn } from '@/app/ui'
import { NAV_GROUPS } from '@/app/Nav'

/** 键位分组。**顺序按使用的先后**：先找题，再组卷，最后是通用。 */
const GROUPS: { title: string; rows: [string, string][] }[] = [
  {
    title: '导航',
    rows: NAV_GROUPS.flatMap((g) =>
      g.items.map((i) => [`${i.hint}`, `${i.label} · ${i.desc}`] as [string, string])),
  },
  {
    title: '找题与组卷',
    rows: [
      ['⌘ K', '命令面板：什么都能干（推荐先记这个）'],
      ['/', '聚焦顶栏搜索框'],
      ['↑ ↓', '在题目列表里上下移动'],
      ['Enter', '把当前这道题加进卷子'],
      ['⌘ ↵', '打开组卷导出'],
    ],
  },
  {
    title: '通用',
    rows: [
      ['Esc', '关闭弹层'],
      ['?', '打开这张表'],
    ],
  },
]

export default function HelpButton() {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  // 命令面板里那条「查看键盘快捷键」要能把它打开。
  // 用自定义事件解耦：CommandPalette 不必知道 HelpButton 的存在。
  useEffect(() => {
    const open = () => setOpen(true)
    window.addEventListener('amtiku:help', open)
    return () => window.removeEventListener('amtiku:help', open)
  }, [])

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      // 问号要按 Shift 才出得来，所以这里不做大小写限制
      if (e.key === '?' && !e.metaKey && !e.ctrlKey) {
        const el = document.activeElement as HTMLElement | null
        const tag = el?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || el?.isContentEditable) return
        e.preventDefault(); setOpen((v) => !v)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [open])

  return (
    <div ref={box} className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-2.5">
      {open && (
        <div className="pop-c w-[326px] rounded-[var(--radius-pop)] border border-border bg-surface
                        p-4 shadow-[var(--shadow-pop)]">
          <div className="mb-3 flex items-center gap-2">
            <span className="text-[13.5px] font-semibold">键盘快捷键</span>
            <CloseBtn onClick={() => setOpen(false)} className="ml-auto" />
          </div>
          <div className="space-y-3.5">
            {GROUPS.map((g) => (
              <div key={g.title}>
                <div className="mb-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-ink-faint">
                  {g.title}
                </div>
                <div className="space-y-[3px]">
                  {g.rows.map(([k, desc]) => (
                    <div key={k + desc} className="flex items-center gap-2.5 text-[12px]">
                      <kbd className="min-w-[38px] shrink-0 rounded-md border border-border bg-surface-2
                                      px-1.5 text-center text-[11px] font-medium leading-[19px] text-ink-soft">
                        {k}
                      </kbd>
                      <span className="min-w-0 flex-1 truncate text-ink-soft">{desc}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3.5 border-t border-border pt-2.5 text-[10.5px] leading-relaxed text-ink-faint">
            单键只在<b className="font-medium text-ink-soft">没有停在输入框里</b>时生效（打中文时不会误触）。
          </div>
        </div>
      )}

      <button onClick={() => setOpen((v) => !v)} title="键盘快捷键（?）"
        className={`press grid h-11 w-11 place-items-center rounded-full border bg-surface
                    shadow-[var(--shadow-pop)] transition-colors ${open
                      ? 'border-brand-line text-brand-ink'
                      : 'border-border text-ink-faint hover:border-brand-line hover:text-brand-ink'}`}>
        <CircleHelp size={19} />
      </button>
    </div>
  )
}
