/** 编辑器右栏：选中块的属性 / 页面设置 / 已存讲义。
 *
 *  从 CanvasEditor 拆出来的（审查报告 REACT-4）。
 */
import {
  blockFontSize, CB_TYPES, EMOJIS, DEFAULT_FS, DEFAULT_LH,
  RESIZE_SLACK_PCT, type CBlock,
} from '@/editor/shared'

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
        <div className="flex w-[230px] shrink-0 flex-col border-l border-border">
      <div className="border-b border-border px-3 py-2 text-[11px] font-semibold text-ink-faint">
        属性
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2.5">
        {!selBlock ? (
          <div className="space-y-3 text-[11.5px]">
            <div className="text-ink-faint">未选中块</div>
            <div>
              <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">页面比例</div>
              <div className="flex gap-1">
                {(['16:9', 'a4', '4:3'] as const).map((v) => (
                  <button key={v} onClick={() => setRatio(v)}
                    className={`flex-1 rounded border px-1.5 py-1 text-[11px] ${
                      ratio === v ? 'border-brand/40 bg-brand-soft text-brand-ink'
                                  : 'border-border bg-bg text-ink-soft'}`}>{v}</button>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={withAns} onChange={(e) => setWithAns(e.target.checked)}
                className="accent-[var(--color-brand)]" />显示答案
            </label>

            <div>
              <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">已存讲义</div>
              {saved.map((h) => (
                <button key={h.name} onClick={() => doLoad(h.name)}
                  className="mb-1 block w-full truncate rounded border border-border bg-bg
                             px-2 py-1 text-left text-[11.5px] hover:border-brand/40">
                  {h.title || h.name}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-2.5 text-[11.5px]">
            <div className="flex items-center gap-2">
              <span className="rounded bg-brand-soft px-1.5 py-[1px] text-[10.5px] text-brand-ink">
                {CB_TYPES.find((k) => k.v === selBlock.type)?.label || selBlock.type}
              </span>
              <button onClick={() => remove(selBlock.id)}
                className="ml-auto text-[11px] text-ink-faint hover:text-red-500">删除</button>
            </div>
            {selBlock.type === 'emoji' ? (
              <div className="space-y-2">
                <div className="text-[10.5px] text-ink-faint">
                  点一下换表情。文字块里也能直接打表情。
                </div>
                <div className="grid grid-cols-4 gap-1">
                  {EMOJIS.map(([e, label]) => (
                    <button key={e} title={label}
                      onClick={() => patch(selBlock.id, { text: e })}
                      className={`rounded border py-1 text-[17px] leading-none ${
                        selBlock.text === e
                          ? 'border-brand/50 bg-brand-soft'
                          : 'border-border bg-bg hover:border-brand/40'}`}>
                      {e}
                    </button>
                  ))}
                </div>
                <input value={selBlock.text || ''}
                  onChange={(e) => patch(selBlock.id, { text: e.target.value })}
                  placeholder="或自己输入任意表情"
                  className="w-full rounded border border-border bg-bg px-2 py-1
                             text-[15px] outline-none focus:border-brand/40" />
              </div>
            ) : selBlock.type === 'table' ? (
              <div className="space-y-1.5">
                <div className="text-[10.5px] text-ink-faint">
                  单元格支持 $公式$。改完自动同步到画布。
                </div>
                {/* 表头 */}
                <div className="flex gap-1">
                  <span className="w-8 shrink-0 pt-1 text-[10px] text-ink-faint">表头</span>
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    {(selBlock.headers || ['', '', '']).map((h, i) => (
                      <input key={i} value={h}
                        onChange={(e) => {
                          const hs = [...(selBlock.headers || ['', '', ''])]
                          hs[i] = e.target.value
                          patch(selBlock.id, { headers: hs })
                        }}
                        className="w-full rounded border border-border bg-bg px-1.5 py-0.5
                                   text-[11px] outline-none focus:border-brand/40" />
                    ))}
                  </div>
                </div>
                {/* 数据行 */}
                {(selBlock.rows || []).map((row, ri) => (
                  <div key={ri} className="flex gap-1">
                    <span className="w-8 shrink-0 pt-1 text-[10px] text-ink-faint">行{ri + 1}</span>
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      {row.map((v, ci) => (
                        <input key={ci} value={v}
                          onChange={(e) => {
                            const rs = (selBlock.rows || []).map((r) => [...r])
                            rs[ri][ci] = e.target.value
                            patch(selBlock.id, { rows: rs })
                          }}
                          className="w-full rounded border border-border bg-bg px-1.5 py-0.5
                                     text-[11px] outline-none focus:border-brand/40" />
                      ))}
                    </div>
                  </div>
                ))}
                {/* 增删行列 */}
                <div className="flex flex-wrap gap-1 pt-1">
                  <button onClick={() => {
                    const cols = (selBlock.headers || []).length || 1
                    patch(selBlock.id, {
                      headers: [...(selBlock.headers || []), `列${cols + 1}`],
                      rows: (selBlock.rows || []).map((r) => [...r, '']),
                    })
                  }} className="rounded border border-border px-1.5 py-[2px] text-[10.5px]
                                hover:border-brand/40">+ 列</button>
                  <button onClick={() => {
                    const cols = (selBlock.headers || []).length || 1
                    if (cols <= 1) return
                    patch(selBlock.id, {
                      headers: (selBlock.headers || []).slice(0, -1),
                      rows: (selBlock.rows || []).map((r) => r.slice(0, -1)),
                    })
                  }} className="rounded border border-border px-1.5 py-[2px] text-[10.5px]
                                hover:border-brand/40">− 列</button>
                  <button onClick={() => {
                    const cols = (selBlock.headers || []).length || 1
                    patch(selBlock.id, {
                      rows: [...(selBlock.rows || []), Array(cols).fill('')],
                    })
                  }} className="rounded border border-border px-1.5 py-[2px] text-[10.5px]
                                hover:border-brand/40">+ 行</button>
                  <button onClick={() => {
                    const rs = selBlock.rows || []
                    if (rs.length <= 1) return
                    patch(selBlock.id, { rows: rs.slice(0, -1) })
                  }} className="rounded border border-border px-1.5 py-[2px] text-[10.5px]
                                hover:border-brand/40">− 行</button>
                </div>
              </div>
            ) : selBlock.type !== 'question' && selBlock.type !== 'blank' && (
              <textarea value={selBlock.text || ''} rows={3}
                onChange={(e) => patch(selBlock.id, { text: e.target.value })}
                placeholder={selBlock.type === 'formula' ? '$$公式$$' : '输入内容…'}
                className="w-full resize-y rounded border border-border bg-bg px-2 py-1
                           text-[12px] outline-none focus:border-brand/40" />
            )}
            <div className="grid grid-cols-2 gap-1.5">
              {(['x', 'y', 'w', 'h'] as const).map((k) => (
                <label key={k} className="block">
                  <span className="text-[10.5px] text-ink-faint">
                    {k === 'x' ? 'X %' : k === 'y' ? 'Y %' : k === 'w' ? '宽 %' : '高 %'}
                  </span>
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
                    className="mt-0.5 w-full rounded border border-border bg-bg px-1.5 py-0.5
                               font-mono text-[11.5px] outline-none" />
                </label>
              ))}
            </div>
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-[10.5px] text-ink-faint">字号</span>
                <span className="ml-auto font-mono text-[10.5px] text-ink-soft">
                  {blockFontSize(selBlock)}px
                </span>
                {selBlock.fontSize && (
                  <button onClick={() => patch(selBlock.id, { fontSize: undefined })}
                    title="恢复默认"
                    className="text-[10px] text-brand-ink hover:underline">默认</button>
                )}
              </div>
              <input type="range" min="8" max="72" step="1"
                value={blockFontSize(selBlock)}
                onChange={(e) => patch(selBlock.id, { fontSize: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--color-brand)]" />
              <div className="flex justify-between text-[9.5px] text-ink-faint">
                <span>8</span>
                <span>默认 {DEFAULT_FS}</span>
                <span>72</span>
              </div>
            </div>
            <div>
              <div className="flex items-baseline gap-1">
                <span className="text-[10.5px] text-ink-faint">行距</span>
                <span className="ml-auto font-mono text-[10.5px] text-ink-soft">
                  {(selBlock.lineHeight ?? DEFAULT_LH).toFixed(2)}
                </span>
              </div>
              <input type="range" min="1" max="3" step="0.05"
                value={selBlock.lineHeight ?? DEFAULT_LH}
                onChange={(e) => patch(selBlock.id, { lineHeight: Number(e.target.value) })}
                className="mt-1 w-full accent-[var(--color-brand)]" />
              <div className="flex justify-between text-[9.5px] text-ink-faint">
                <span>紧凑 1.0</span><span>默认 2.0</span><span>宽松 3.0</span>
              </div>
            </div>
            <button onClick={() => bringToFront(selBlock.id)}
              className="w-full rounded border border-border px-2 py-1 text-[11.5px]
                         text-ink-soft hover:border-brand/40">移到最上层</button>
          </div>
        )}
      </div>
    </div>
  )
}
