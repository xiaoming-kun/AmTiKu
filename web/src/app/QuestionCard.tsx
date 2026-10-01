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
import { useEffect, useRef, useState } from 'react'
import { Plus, Check, ChevronDown, Flame, TriangleAlert, Loader2, Maximize2 } from 'lucide-react'
import type { Q } from '@/lib/types'
import { renderBlocks } from '@/lib/render'
import { api, reportErr } from '@/lib/api'
import { DIFF_STARS } from '@/lib/display'
import { Flags } from '@/app/ui'

/** 题干到底有没有被截断。
 *
 *  封顶高度的渐隐**不能无条件画**：一行就放得下的短题干也会被那 22px 盖住，
 *  看起来就像"题目自带一层渐变"。所以要真的量一下 scrollHeight。
 *  依赖里带 `q.key` / `dense`：题换了、密度换了都得重算
 *  （ResizeObserver 只在盒子尺寸变时触发，而"被截断"恰恰是不变尺寸的那种）。 */
function useClamped(deps: unknown[]) {
  const ref = useRef<HTMLDivElement>(null)
  const [over, setOver] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const check = () => setOver(el.scrollHeight > el.clientHeight + 2)
    check()

    // **三件都要听**，少一件就会漏：
    //  · ResizeObserver —— 窗口/面板宽度变了
    //  · MutationObserver —— KaTeX 是**挂载之后**才把公式画进去的，
    //    内容长高了但盒子被 max-height 钉死，ResizeObserver 根本不会响
    //    （实测漏掉过：量出来 29 vs 26 该显示渐隐，却没显示）
    //  · fonts.ready —— 字体到位后行高会再变一次
    const ro = new ResizeObserver(check)
    ro.observe(el)
    const mo = new MutationObserver(check)
    mo.observe(el, { childList: true, subtree: true, characterData: true })
    document.fonts?.ready.then(check).catch(() => {})
    return () => { ro.disconnect(); mo.disconnect() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return [ref, over] as const
}

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
  q, active, inPaper, selectMode, checked, dense,
  onOpen, onDetail, onAdd, onToggle,
}: {
  q: Q; active: boolean; inPaper: boolean
  selectMode: boolean; checked: boolean
  /** 紧凑模式：题干一行、不要选项预览、内边距收小。
   *  挑题时要的是"一屏多扫几道"，读题时才需要宽松（Notion/Linear 同款开关）。 */
  dense?: boolean
  onOpen: () => void; onDetail: () => void
  onAdd: () => void; onToggle: () => void
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

  /** 题干「展开全文」。截断是为了能扫，但**解答题常常有两问**，
   *  只给两行会把第二问整个吃掉——所以给一个随时能看全的出口。
   *  换一道题就自动收起来（不然翻页时一路都是展开的）。 */
  const [stemOpen, setStemOpen] = useState(false)
  useEffect(() => { setStemOpen(false) }, [q.key])
  const [clampRef, over] = useClamped([q.key, dense, stemOpen])
  const clamped = over && !stemOpen

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
      /* 键盘光标停在这一张上时，屏幕阅读器也该知道（↑↓ 移的是它，不是 DOM 焦点） */
      aria-current={active ? 'true' : undefined}
      /* `@container`：下面选项要不要分两列，看**这张卡自己有多宽**，
         不是看窗口多宽（列表栏宽度会被筛选面板/详情抽屉改来改去）。
         以前用 `sm:grid-cols-2`（视口断点），栏很窄时两列挤成一团、
         栏很宽时两列又离得老远。 */
      className={`@container card-lift group cursor-pointer overflow-hidden rounded-[var(--radius-card)]
                  border bg-surface shadow-[var(--shadow-card)] ${
        checked ? 'border-brand-line ring-2 ring-brand/25'
        : active ? 'border-brand-line'
                 : 'border-border'}`}>

      {/* ── ① 元信息 + 动作 ── */}
      <div className={`flex items-start gap-3 ${dense ? 'px-3.5 pt-2.5' : 'px-4 pt-3'}`}>
        {selectMode && (
          <span
            className={`mt-[3px] grid h-[16px] w-[16px] shrink-0 place-items-center rounded-[5px]
                        border transition-all duration-150 ${
              checked ? 'border-brand bg-brand text-white' : 'border-border-strong bg-surface text-transparent'}`}>
            <Check size={11} strokeWidth={3} className={checked ? 'anim-check' : ''} />
          </span>
        )}
        {/* 元信息行。
            **考点全部列出来**，样式与详情抽屉里那排**完全一致**
            （主考点粉色标「主」，其余灰色）——同一个东西在两个界面长得一样，
            不用重新认一遍。多考点就换行，`flex-wrap` 兜住。

            顺手去掉两处冗余：
            · 「来源：」前缀——`source_label` 本身就是「2024年新高考II卷」，
              谁都看得出这是出处，前缀纯占地方；
            · **重复的年份**——实测 82% 的题 source_label 里已经含年份，
              原来会写成「2024年新高考II卷 · 2024 年」，同一个年份说两遍。 */}
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 text-[11.5px]">
          {q.point_titles?.length ? (
            q.point_titles.map((t, i) => (
              <span key={i} title={q.point_titles.join('、')}
                className={`shrink-0 rounded-full px-1.5 py-[1px] text-[11px] font-medium ${
                  i === 0 ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-soft'}`}>
                {i === 0 && <span className="mr-0.5 text-[9.5px] font-normal opacity-70">主</span>}
                {t}
              </span>
            ))
          ) : (
            <span className="shrink-0 rounded-full bg-warn-soft px-1.5 py-[1px] text-[11px]
                             font-medium text-warn">无考点</span>
          )}
          {src && (
            <span className="min-w-0 truncate text-ink-faint" title={src}>{src}</span>
          )}
          {!!year && !src.includes(String(year)) && (
            <span className="shrink-0 text-ink-faint">{year} 年</span>
          )}
          {!!q.used && (
            <span className="ml-auto flex shrink-0 items-center gap-0.5 pl-2 text-warn"
              title={`已被导出 ${q.used} 次，是道常考题`}>
              <Flame size={11} />{q.used}
            </span>
          )}
        </div>

        {/* 动作按钮：**常驻可见**，不藏到悬停里 ——
            选定模式默认开着，藏起来的话老师根本找不到这两个入口（实测踩过）。 */}
        <div className="flex shrink-0 items-center gap-1.5">
          {/* 「详情」是**唯一一个明确打开详情抽屉的入口**。
              卡片本身点一下是"移光标 / 勾选"，多选模式下不该把抽屉也拽出来；
              要看全文、改答案、改考点，就点这颗。 */}
          <button onClick={(e) => { e.stopPropagation(); onDetail() }}
            title="打开详情（看全文 / 改答案 / 改考点 / 源码）"
            className="press icon-btn h-[26px] w-[26px] shrink-0 border border-border
                       text-ink-faint hover:border-brand-line hover:text-brand-ink">
            <Maximize2 size={12} />
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
      <div className={`flex flex-wrap items-center gap-1.5 ${dense ? 'px-3.5 pt-1.5' : 'px-4 pt-2'}`}>
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
            <TriangleAlert size={10} />存疑
          </span>
        )}
      </div>

      {/* ── ③ 题干 + 选项 ── */}
      <div className={`${dense ? 'px-3.5 pt-2' : 'px-4 pt-2.5'}`}>
        <div className="q-stem q-compact text-[14.5px] text-ink">
          <div ref={clampRef} data-over={clamped ? '1' : '0'}
            className={`q-clamp ${stemOpen ? '' : dense ? 'max-h-[1.7em]' : 'max-h-[10em]'}`}>
            {renderBlocks(q.blocks?.stem)}
          </div>
          {/* 封顶高度是**折中**：不封顶的话一道三页的题就占满整屏。
              实测 10em（约 5~6 行）能完整放下 87% 的题干，平均每张卡只比
              4.6em 多 18px（一屏仍是 4 道）——剩下那 13% 用这个按钮兜。 */}
          {(clamped || stemOpen) && (
            <button
              onClick={(e) => { e.stopPropagation(); setStemOpen((v) => !v) }}
              className="press mt-1 text-[11.5px] font-medium text-brand-ink hover:underline">
              {stemOpen ? '收起题干' : '展开题干全文'}
            </button>
          )}
        </div>

        {multi && !dense && (
          <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-0.5 @[600px]:grid-cols-2">
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
          className={`flex w-full items-center gap-2 text-left text-[12px] transition-colors
                      hover:bg-muted/60 ${dense ? 'px-3.5 py-1.5' : 'px-4 py-2'}`}>
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
