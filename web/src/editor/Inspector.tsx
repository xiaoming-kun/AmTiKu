/** 编辑器右栏：选中块的属性 / 页面设置 / 已存讲义。
 *
 *  从 CanvasEditor 拆出来的（审查报告 REACT-4）。
 *
 *  视觉：每个属性都是**一条**——左边固定宽度的 11.5px 标签（宽度固定，
 *  所以纵向扫下来不会左右抖），右边控件。控件按类型收敛成四种：
 *  滑块 / 数字输入 / 开关 / 分段按钮，不再每处各写一套描边。
 */
import { ArrowUpToLine, FileText, Minus, Plus, SlidersHorizontal, Trash2 } from 'lucide-react'
import {
  blockFontSize, CB_TYPES, EMOJIS, DEFAULT_FS, DEFAULT_LH,
  RESIZE_SLACK_PCT, type CBlock,
} from '@/editor/shared'

/** 输入类控件的公共外观（高度、字号、对齐由调用点给）。 */
const FIELD = `rounded-lg border border-border bg-bg text-ink outline-none
  transition-[border-color,box-shadow] duration-150 placeholder:text-ink-faint
  focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]`

/** 页面比例：横排 2×2 的分段按钮（外壳 bg-muted，选中项浮成卡片） */
const RATIOS: [string, string, string][] = [
  ['16:9', '16:9', '16:9（讲课、录屏）'],
  ['a4', 'A4', 'A4 竖版（打印用）'],
  ['4:3', '4:3·iPad', 'iPad 12.9″/13″/10.2″ 等（4:3）'],
  ['ipad11', 'iPad 11″', 'iPad 11″/10.9″/Air（2360×1640，≈1.439）'],
]

/** 一条属性：左边固定宽度的标签，右边控件 */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-[46px] shrink-0 text-[11.5px] text-ink-faint">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

/** 小节标题（区块之间靠它分段，不再靠边框） */
function GroupTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
      {children}
    </div>
  )
}

export default function Inspector({ selBlock, patch, remove, bringToFront,
  ratio, setRatio, withAns, setWithAns, saved, doLoad, natural, canvasRef }: {
  selBlock: CBlock | null
  patch: (id: string, p: Partial<CBlock>) => void
  remove: (id: string) => void
  bringToFront: (id: string) => void
  ratio: string; setRatio: (s: string) => void
  withAns: boolean; setWithAns: (b: boolean) => void
  saved: any[]; doLoad: (n: string) => void
  natural: Record<string, { w: number; h: number }>
  canvasRef: React.MutableRefObject<HTMLDivElement | null>
}) {
  return (
    <aside className="flex w-[242px] shrink-0 flex-col border-l border-border bg-surface">
      {/* ── 面板头 ── */}
      <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border px-3.5">
        <SlidersHorizontal size={15} className="shrink-0 text-brand" />
        <span className="text-[14px] font-semibold tracking-tight">属性</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3.5">
        {/* ⚠️ **页面级设置常驻**，不因为选中了某个块就整组消失。
            以前这里是 `!selBlock ? 页面设置 : 块设置` 的二选一——于是
            「把题拖进画布」（会自动选中它）之后，「页面比例 / 显示答案 / 已存讲义」
            整组**不见了**。而"刚加完题想勾显示答案"恰恰是最常见的一刻，
            用户只会觉得这个功能不存在。
            现在：选中块时**块设置在最上**（就近操作），页面设置在**下面接着**。 */}
        <div className="space-y-5">
          {selBlock && (
            <div className="space-y-4 rounded-[var(--radius-card)] border border-brand-line
                            bg-brand-soft/25 p-2.5">
              <div className="flex items-center gap-2">
                <span className="rounded-md bg-brand-soft px-1.5 py-[2px] text-[11px] font-medium
                                 text-brand-ink">
                  {CB_TYPES.find((k) => k.v === selBlock.type)?.label || selBlock.type}
                </span>
                <button onClick={() => remove(selBlock.id)}
                  className="press ml-auto inline-flex items-center gap-1 rounded-lg px-1.5 py-1
                             text-[11.5px] text-ink-faint transition-colors
                             hover:bg-danger-soft hover:text-danger">
                  <Trash2 size={12} />删除
                </button>
              </div>

              {selBlock.type === 'emoji' ? (
                <div className="space-y-2.5">
                  <div className="text-[11.5px] leading-snug text-ink-faint">
                    点一下换表情。文字块里也能直接打表情。
                  </div>
                  <div className="grid grid-cols-5 gap-1.5">
                    {EMOJIS.map(([e, label]) => (
                      <button key={e} title={label}
                        onClick={() => patch(selBlock.id, { text: e })}
                        className={`press grid h-9 place-items-center rounded-lg border text-[17px]
                                    leading-none transition-colors ${selBlock.text === e
                                      ? 'border-brand-line bg-brand-soft'
                                      : 'border-border bg-bg hover:border-brand-line hover:bg-brand-soft/40'}`}>
                        {e}
                      </button>
                    ))}
                  </div>
                  <input value={selBlock.text || ''}
                    onChange={(e) => patch(selBlock.id, { text: e.target.value })}
                    placeholder="或自己输入任意表情"
                    className={`${FIELD} h-[34px] w-full text-[13px]`} />
                </div>
              ) : selBlock.type === 'table' ? (
                <div className="space-y-2">
                  <div className="text-[11.5px] leading-snug text-ink-faint">
                    单元格支持 $公式$。改完自动同步到画布。
                  </div>
                  {/* 表头 */}
                  <div className="flex gap-2">
                    <span className="w-8 shrink-0 pt-1.5 text-[11px] text-ink-faint">表头</span>
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      {(selBlock.headers || ['', '', '']).map((h, i) => (
                        <input key={i} value={h}
                          onChange={(e) => {
                            const hs = [...(selBlock.headers || ['', '', ''])]
                            hs[i] = e.target.value
                            patch(selBlock.id, { headers: hs })
                          }}
                          className={`${FIELD} h-[28px] w-full text-[11.5px]`} />
                      ))}
                    </div>
                  </div>
                  {/* 数据行 */}
                  {(selBlock.rows || []).map((row, ri) => (
                    <div key={ri} className="flex gap-2">
                      <span className="w-8 shrink-0 pt-1.5 text-[11px] text-ink-faint">行{ri + 1}</span>
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        {row.map((v, ci) => (
                          <input key={ci} value={v}
                            onChange={(e) => {
                              const rs = (selBlock.rows || []).map((r) => [...r])
                              rs[ri][ci] = e.target.value
                              patch(selBlock.id, { rows: rs })
                            }}
                            className={`${FIELD} h-[28px] w-full text-[11.5px]`} />
                        ))}
                      </div>
                    </div>
                  ))}
                  {/* 增删行列 */}
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    <button onClick={() => {
                      const cols = (selBlock.headers || []).length || 1
                      patch(selBlock.id, {
                        headers: [...(selBlock.headers || []), `列${cols + 1}`],
                        rows: (selBlock.rows || []).map((r) => [...r, '']),
                      })
                    }} className="press inline-flex items-center gap-1 rounded-lg border border-border
                                  bg-surface px-2 py-[3px] text-[11px] text-ink-soft transition-colors
                                  hover:border-border-strong hover:text-ink">
                      <Plus size={11} />列
                    </button>
                    <button onClick={() => {
                      const cols = (selBlock.headers || []).length || 1
                      if (cols <= 1) return
                      patch(selBlock.id, {
                        headers: (selBlock.headers || []).slice(0, -1),
                        rows: (selBlock.rows || []).map((r) => r.slice(0, -1)),
                      })
                    }} className="press inline-flex items-center gap-1 rounded-lg border border-border
                                  bg-surface px-2 py-[3px] text-[11px] text-ink-soft transition-colors
                                  hover:border-border-strong hover:text-ink">
                      <Minus size={11} />列
                    </button>
                    <button onClick={() => {
                      const cols = (selBlock.headers || []).length || 1
                      patch(selBlock.id, {
                        rows: [...(selBlock.rows || []), Array(cols).fill('')],
                      })
                    }} className="press inline-flex items-center gap-1 rounded-lg border border-border
                                  bg-surface px-2 py-[3px] text-[11px] text-ink-soft transition-colors
                                  hover:border-border-strong hover:text-ink">
                      <Plus size={11} />行
                    </button>
                    <button onClick={() => {
                      const rs = selBlock.rows || []
                      if (rs.length <= 1) return
                      patch(selBlock.id, { rows: rs.slice(0, -1) })
                    }} className="press inline-flex items-center gap-1 rounded-lg border border-border
                                  bg-surface px-2 py-[3px] text-[11px] text-ink-soft transition-colors
                                  hover:border-border-strong hover:text-ink">
                      <Minus size={11} />行
                    </button>
                  </div>
                </div>
              ) : selBlock.type !== 'question' && selBlock.type !== 'blank' && (
                <textarea value={selBlock.text || ''} rows={3}
                  onChange={(e) => patch(selBlock.id, { text: e.target.value })}
                  placeholder={selBlock.type === 'formula' ? '$$公式$$' : '输入内容…'}
                  className={`${FIELD} w-full resize-y py-2 text-[12.5px] leading-relaxed`} />
              )}

              {/* ── 位置与尺寸 ── */}
              <section className="space-y-1.5">
                <GroupTitle>位置与尺寸</GroupTitle>
                {(['x', 'y', 'w', 'h'] as const).map((k) => (
                  <Row key={k} label={k === 'x' ? 'X %' : k === 'y' ? 'Y %' : k === 'w' ? '宽 %' : '高 %'}>
                    <input type="number" step="1" value={Math.round(selBlock[k] ?? 0)}
                      onChange={(e) => {
                        let v = Number(e.target.value)
                        if (!Number.isFinite(v)) return
                        v = Math.max(0, Math.min(100, v))       // 先钳到画布内
                        const nat = natural[selBlock.id]
                        const cw = canvasRef.current?.clientWidth || 900
                        const ch = canvasRef.current?.clientHeight || 500
                        // 再抬高到内容固有尺寸（同样不超 100）
                        if (k === 'w' && nat) {
                          v = Math.min(100, Math.max(v, (nat.w / cw) * 100 + RESIZE_SLACK_PCT))
                        }
                        if (k === 'h' && nat && selBlock.h > 0) {
                          v = Math.min(100, Math.max(v, (nat.h / ch) * 100 + RESIZE_SLACK_PCT))
                        }
                        patch(selBlock.id, { [k]: Math.round(v) } as any)
                      }}
                      className={`${FIELD} tnum h-[28px] w-full font-mono text-[11.5px]`} />
                  </Row>
                ))}
              </section>

              {/* ── 文字 ── */}
              <section className="space-y-3">
                <GroupTitle>文字</GroupTitle>
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <span className="w-[46px] shrink-0 text-[11.5px] text-ink-faint">字号</span>
                    <input type="range" min="8" max="72" step="1"
                      value={blockFontSize(selBlock)}
                      onChange={(e) => patch(selBlock.id, { fontSize: Number(e.target.value) })}
                      className="h-1 min-w-0 flex-1 accent-[var(--color-brand)]" />
                    <span className="tnum w-10 shrink-0 text-right text-[11.5px] font-medium text-ink-soft">
                      {blockFontSize(selBlock)}px
                    </span>
                    {selBlock.fontSize && (
                      <button onClick={() => patch(selBlock.id, { fontSize: undefined })}
                        title="恢复默认"
                        className="press shrink-0 rounded-md px-1 py-[1px] text-[10.5px]
                                   text-brand-ink hover:bg-brand-soft">默认</button>
                    )}
                  </div>
                  <div className="flex justify-between pl-[56px] text-[10.5px] text-ink-faint">
                    <span>8</span>
                    <span>默认 {DEFAULT_FS}</span>
                    <span>72</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <span className="w-[46px] shrink-0 text-[11.5px] text-ink-faint">行距</span>
                    <input type="range" min="1" max="3" step="0.05"
                      value={selBlock.lineHeight ?? DEFAULT_LH}
                      onChange={(e) => patch(selBlock.id, { lineHeight: Number(e.target.value) })}
                      className="h-1 min-w-0 flex-1 accent-[var(--color-brand)]" />
                    <span className="tnum w-10 shrink-0 text-right text-[11.5px] font-medium text-ink-soft">
                      {(selBlock.lineHeight ?? DEFAULT_LH).toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between pl-[56px] text-[10.5px] text-ink-faint">
                    <span>紧凑 1.0</span><span>默认 2.0</span><span>宽松 3.0</span>
                  </div>
                </div>
              </section>

              <button onClick={() => bringToFront(selBlock.id)}
                className="press inline-flex w-full items-center justify-center gap-1.5 rounded-lg
                           border border-border bg-surface py-2 text-[12px] text-ink-soft
                           transition-colors hover:border-border-strong hover:text-ink">
                <ArrowUpToLine size={13} />移到最上层
              </button>
            </div>
          )}

            <section>
              <GroupTitle>页面比例</GroupTitle>
              <div className="grid grid-cols-2 gap-[3px] rounded-[9px] bg-muted p-[3px]">
                {RATIOS.map(([v, label, hint]) => (
                  <button key={v} onClick={() => setRatio(v)} title={hint}
                    className={`press rounded-[7px] py-[5px] text-[11.5px] font-medium
                                transition-colors ${ratio === v
                                  ? 'bg-surface text-ink shadow-[var(--shadow-card)]'
                                  : 'text-ink-faint hover:text-ink-soft'}`}>{label}</button>
                ))}
              </div>
            </section>

            <section className="space-y-1.5">
              <GroupTitle>显示</GroupTitle>
              <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border
                                border-border bg-bg px-2.5 py-2 text-[12.5px] text-ink-soft
                                transition-colors hover:border-border-strong hover:text-ink">
                <input type="checkbox" checked={withAns} onChange={(e) => setWithAns(e.target.checked)}
                  className="accent-[var(--color-brand)]" />显示答案
              </label>
              {/* 「高考题标出处」的开关删了：每题都有出处，标上是默认行为。
                  后端仍留着 `show_source` 参数（测试覆盖了关掉的情形）。 */}
            </section>

            <section>
              <GroupTitle>已存讲义</GroupTitle>
              <div className="space-y-1">
                {saved.map((h) => (
                  <button key={h.name} onClick={() => doLoad(h.name)}
                    className="press flex w-full items-center gap-1.5 rounded-lg border border-border
                               bg-bg px-2.5 py-1.5 text-left text-[11.5px] text-ink-soft
                               transition-colors hover:border-brand-line hover:bg-brand-soft/40
                               hover:text-brand-ink">
                    <FileText size={12} className="shrink-0 text-ink-faint" />
                    <span className="min-w-0 flex-1 truncate">{h.title || h.name}</span>
                  </button>
                ))}
              </div>
            </section>
        </div>
      </div>
    </aside>
  )
}
