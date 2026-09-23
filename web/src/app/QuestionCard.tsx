/** 题目卡片（列表里的一张）。
 *
 *  这是整个界面里出现次数最多的元素（一屏十几张），所以它的信息密度
 *  决定了界面「好不好用」。
 *
 *  旧卡片的问题：**只有两行题干 + 一行来源**。想知道「有没有答案」
 *  得点进去看详情——而老师找题时最常问的恰恰就是"这题能不能直接印"。
 *
 *  新版按参考图重排成四层：
 *  ① 元信息行：来源 · 考点 · 导出次数，右边挂着两个动作按钮
 *  ② 标签行：题型 / 类别 / 难度 / 完整度（缺答案·缺解析在这里就报警）
 *  ③ 题干 + **选项两列预览**（选择题一眼看得出选项长什么样）
 *  ④ 折叠的答案与解析：不展开也看得见"答案 C / 有解析"，
 *     展开才去拉全量（答案与解析的块 IR 列表接口不带，见 server.py 的说明）
 */
import { useEffect, useState } from 'react'
import { Plus, BookPlus, Check, ChevronDown, Flame, AlertTriangle, Loader2 } from 'lucide-react'
import type { Q } from '@/lib/types'
import { renderBlocks } from '@/lib/render'
import { api, reportErr } from '@/lib/api'
import { DIFF_STARS } from '@/lib/display'
import { Flags } from '@/app/ui'

/** 答案的**纯文字**预览。只认两种情况，其余一律让用户展开看：
 *  选择题的字母（`C` / `ABD`）、解答题的「见解析」。
 *  为什么不干脆把 LaTeX 画出来——列表接口不带答案的块 IR，
 *  而**前端不解析 LaTeX** 是这个项目的硬规矩（AGENTS.md 第三节）。 */
function answerPreview(ans: string): string {
  const a = (ans || '').trim()
  if (/^[A-D]{1,4}$/.test(a)) return a
  if (a.includes('见解析')) return '见解析'
  return ''
}

export default function Card({
  q, active, inPaper, inHandout, selectMode, checked,
  onOpen, onAdd, onAddHandout, onToggle,
}: {
  q: Q; active: boolean; inPaper: boolean; inHandout: boolean
  selectMode: boolean; checked: boolean
  onOpen: () => void; onAdd: () => void; onAddHandout: () => void; onToggle: () => void
}) {
  const [open, setOpen] = useState(false)
  const [full, setFull] = useState<Q | null>(null)

  // 展开时才去拉全量。列表接口只带题干的块 IR，
  // 答案/解析要按 key 补一次（服务端有缓存，重复点开几乎不花时间）。
  useEffect(() => {
    if (!open || full) return
    let alive = true
    api.get(q.key).then((d) => { if (alive) setFull(d) }).catch(reportErr)
    return () => { alive = false }
  }, [open, full, q.key])

  // 换了一道题，展开状态跟着重置
  useEffect(() => { setFull(null); setOpen(false) }, [q.key])

  /**
   * 点卡片：**详情永远跟着走**，选定模式下再顺带勾选。
   *
   * 早先是 `selectMode ? onToggle : onOpen` —— 选定模式一开（现在是默认），
   * 点卡片就只切勾选、右侧详情纹丝不动，看起来像"点了没反应"。
   * 勾选和看题是两件事，不该互斥。
   */
  const pick = () => { onOpen(); if (selectMode) onToggle() }

  const ans = answerPreview(q.answer)
  const hasSol = !!q.flags['解析']
  const hasAns = !!q.flags['答案']
  const stars = DIFF_STARS[q.difficulty] || q.stars || 0
  const src = q.meta?.source_label || q.meta?.book || ''
  const year = q.meta?.year || ''
  const multi = q.options && q.options.length > 1

  return (
    <article
      onClick={pick}
      className={`card-lift group cursor-pointer overflow-hidden rounded-[var(--radius-card)]
                  border bg-surface shadow-[var(--shadow-card)] ${
        checked ? 'border-brand-line ring-2 ring-brand/25'
        : active ? 'border-brand-line'
                 : 'border-border'}`}>

      {/* ── ① 元信息 + 动作 ── */}
      <div className="flex items-start gap-3 px-4 pt-3">
        {selectMode && (
          <span
            className={`mt-[3px] grid h-[16px] w-[16px] shrink-0 place-items-center rounded-[5px]
                        border transition-all duration-150 ${
              checked ? 'border-brand bg-brand text-white' : 'border-border-strong bg-surface text-transparent'}`}>
            <Check size={11} strokeWidth={3} />
          </span>
        )}
        <div className="min-w-0 flex-1 truncate text-[11.5px] leading-5 text-ink-faint">
          {src && <span>来源：<span className="text-ink-soft">{src}</span></span>}
          {src && q.point_titles?.length ? <span className="mx-1.5 text-border-strong">·</span> : null}
          {q.point_titles?.length ? (
            <span className="font-medium text-ink-soft">
              {q.point_titles[0]}
              {q.point_titles.length > 1 && <span className="font-normal text-ink-faint"> 等 {q.point_titles.length} 个考点</span>}
            </span>
          ) : null}
          {year ? <span><span className="mx-1.5 text-border-strong">·</span>{year} 年</span> : null}
          {!!q.used && (
            <span className="ml-1.5 inline-flex items-center gap-0.5 text-warn" title={`已被导出 ${q.used} 次，是道常考题`}>
              <Flame size={11} />{q.used}
            </span>
          )}
        </div>

        {/* 动作按钮：**常驻可见**，不藏到悬停里 ——
            选定模式默认开着，藏起来的话老师根本找不到这两个入口（实测踩过）。 */}
        <div className="flex shrink-0 items-center gap-1.5">
          <button onClick={(e) => { e.stopPropagation(); onAddHandout() }}
            title={inHandout ? '已在讲义里' : '加入讲义'}
            className={`press flex h-[26px] items-center gap-1 rounded-lg border px-2 text-[11.5px]
                        font-medium transition-colors ${inHandout
                          ? 'border-brand-line bg-brand-soft text-brand-ink'
                          : 'border-border bg-surface text-ink-faint hover:border-brand-line hover:text-brand-ink'}`}>
            {inHandout ? <Check size={12} strokeWidth={2.6} /> : <BookPlus size={12} />}
            <span className="hidden xl:inline">{inHandout ? '已入讲义' : '讲义'}</span>
          </button>
          <button onClick={(e) => { e.stopPropagation(); onAdd() }}
            title={inPaper ? '已在卷子里' : '加入卷子（Enter）'}
            className={`press flex h-[26px] items-center gap-1 rounded-lg border px-2.5 text-[11.5px]
                        font-medium transition-colors ${inPaper
                          ? 'border-has-line bg-has-soft text-has'
                          : 'border-ink/85 bg-ink text-white hover:bg-ink/85'}`}>
            {inPaper ? <Check size={12} strokeWidth={2.8} /> : <Plus size={12} strokeWidth={2.8} />}
            {inPaper ? '已入卷' : '加入组卷'}
          </button>
        </div>
      </div>

      {/* ── ② 标签行 ── */}
      <div className="flex flex-wrap items-center gap-1.5 px-4 pt-2">
        <Tag>{q.type_label}</Tag>
        <Tag>{q.kind}题</Tag>
        {stars > 0 && (
          <Tag title={`难度：${q.difficulty}`}>
            <span className="tracking-tight text-warn">{'★'.repeat(stars)}</span>
            <span className="ml-0.5">{q.difficulty?.replace('题', '')}</span>
          </Tag>
        )}
        {/* 完整度：这里是**列表**，只报缺什么。齐全就什么都不说。 */}
        <Flags flags={q.flags} />
        {/* 求解自相矛盾（解析说 D、答案写 C）：这个必须在列表上就跳出来 */}
        {q.flags['存疑'] && (
          <span className="inline-flex items-center gap-0.5 rounded-md bg-warn-soft px-1.5 py-[1px]
                           text-[10.5px] font-medium text-warn">
            <AlertTriangle size={10} />存疑
          </span>
        )}
      </div>

      {/* ── ③ 题干 + 选项 ── */}
      <div className="px-4 pt-2.5">
        <div className="q-stem q-compact text-[14.5px] text-ink">
          <div className="q-clamp max-h-[4.6em]">{renderBlocks(q.blocks?.stem)}</div>
        </div>

        {multi && (
          <div className="mt-2 grid grid-cols-1 gap-x-5 gap-y-0.5 sm:grid-cols-2">
            {q.options.slice(0, 6).map((o, i) => (
              <div key={o.label} className="q-options flex min-w-0 gap-1.5 text-[13.5px]">
                <span className="lbl shrink-0">{o.label}.</span>
                <span className="line-clamp-1 min-w-0 text-ink-soft">
                  {renderBlocks(q.blocks?.options?.[i])}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── ④ 答案与解析 ── */}
      <div className="mt-2.5 border-t border-border/70">
        <button
          onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
          className="flex w-full items-center gap-2 px-4 py-2 text-left text-[12px]
                     transition-colors hover:bg-muted/60">
          <span className="shrink-0 font-semibold text-ink-faint">答案</span>
          {hasAns ? (
            ans
              ? <span className="rounded bg-has-soft px-1.5 py-[1px] font-mono text-[12px]
                               font-semibold text-has">{ans}</span>
              : <span className="text-[11.5px] text-ink-faint">含公式，展开看</span>
          ) : (
            <span className="rounded bg-warn-soft px-1.5 py-[1px] text-[11px] font-medium text-warn">缺答案</span>
          )}

          <span className="ml-1 shrink-0 font-semibold text-ink-faint">解析</span>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
            {hasSol ? '已收录，展开阅读' : <span className="font-medium text-warn">这题还没有解析</span>}
          </span>

          <span className="flex shrink-0 items-center gap-1 text-[11.5px] text-ink-faint">
            {open ? '收起' : '展开'}
            <ChevronDown size={13} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
          </span>
        </button>

        {open && (
          <div className="reveal" onClick={(e) => e.stopPropagation()}>
            <div>
              <div className="border-t border-border/70 bg-surface-2 px-4 py-3">
                {!full ? (
                  <div className="flex items-center gap-2 py-1 text-[12px] text-ink-faint">
                    <Loader2 size={13} className="animate-spin" />正在取答案与解析…
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {/* 展开后答案走**块 IR**，和试卷上印出来的是同一份渲染 */}
                    {full.blocks?.answer?.length ? (
                      <div className="flex gap-2">
                        <span className="mt-[3px] shrink-0 text-[11.5px] font-semibold text-ink-faint">答案</span>
                        <div className="q-solution min-w-0 flex-1 text-ink">{renderBlocks(full.blocks.answer)}</div>
                      </div>
                    ) : null}
                    {full.blocks?.solution?.length ? (
                      <div className="flex gap-2">
                        <span className="mt-[3px] shrink-0 text-[11.5px] font-semibold text-ink-faint">解析</span>
                        <div className="q-solution q-compact min-w-0 flex-1">{renderBlocks(full.blocks.solution)}</div>
                      </div>
                    ) : (
                      <div className="text-[12px] text-ink-faint">这题没有解析。</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </article>
  )
}

/** 卡片上的小标签。统一成一个形状，避免每种信息各画一套。 */
function Tag({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span title={title}
      className="inline-flex items-center rounded-md bg-muted px-1.5 py-[1px] text-[11px]
                 font-medium text-ink-soft">
      {children}
    </span>
  )
}
