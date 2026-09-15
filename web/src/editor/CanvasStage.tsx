/** 编辑器中栏：画布 + 顶部工具条 + 翻页条。
 *
 *  从 CanvasEditor 拆出来的（审查报告 REACT-4）。
 */
import type { Dispatch, MutableRefObject, SetStateAction } from 'react'
import type { Q } from '@/lib/types'
import {
  CBlockView, blockFontSize, CB_TYPES, TITLE_FONTS, BODY_FONTS,
  DEFAULT_LH, type CBlock,
} from '@/editor/shared'

export default function CanvasStage({ title, setTitle, name, setName,
  titleFont, setTitleFont, bodyFont, setBodyFont, run, busy, doSave, err, res,
  canvasRef, aspect, pages, cur, setCur, setPages, blocks, sel, setSel,
  fits, overflowed, startDrag, measRef, probeRef, blockQs,
  addBlock, fontCss, showSource }: {
  title: string; setTitle: Dispatch<SetStateAction<string>>
  name: string; setName: Dispatch<SetStateAction<string>>
  titleFont: string; setTitleFont: Dispatch<SetStateAction<string>>
  bodyFont: string; setBodyFont: Dispatch<SetStateAction<string>>
  run: () => void; busy: boolean; doSave: () => void
  err: string; res: any
  canvasRef: MutableRefObject<HTMLDivElement | null>
  aspect: number
  pages: { blocks: CBlock[] }[]
  cur: number
  setCur: Dispatch<SetStateAction<number>>
  setPages: Dispatch<SetStateAction<{ blocks: CBlock[] }[]>>
  blocks: CBlock[]
  sel: string | null; setSel: Dispatch<SetStateAction<string | null>>
  fits: Record<string, number>
  overflowed: Set<string>
  startDrag: (e: React.MouseEvent, b: CBlock, mode: 'move' | 'resize') => void
  measRef: MutableRefObject<Record<string, HTMLDivElement | null>>
  probeRef: MutableRefObject<Record<string, HTMLDivElement | null>>
  blockQs: Map<string, Q>
  addBlock: (b: Partial<CBlock>) => void
  fontCss: string
  showSource: boolean
}) {
  return (
        <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="标题"
          className="w-40 rounded-md border border-border bg-surface px-2 py-1 text-[12.5px]
                     font-medium outline-none focus:border-brand/40" />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="文件名"
          className="w-32 rounded-md border border-border bg-surface px-2 py-1 text-[12px]
                     outline-none focus:border-brand/40" />
        <div className="flex items-center gap-1">
          <span className="text-[10.5px] text-ink-faint">字体</span>
          <select value={titleFont} onChange={(e) => setTitleFont(e.target.value)}
            title="标题字体"
            className="rounded border border-border bg-surface px-1.5 py-[3px] text-[11px]
                       outline-none focus:border-brand/40">
            {TITLE_FONTS.map((f) => (
              <option key={f.v} value={f.v}>标 · {f.label}</option>
            ))}
          </select>
          <select value={bodyFont} onChange={(e) => setBodyFont(e.target.value)}
            title="正文字体"
            className="rounded border border-border bg-surface px-1.5 py-[3px] text-[11px]
                       outline-none focus:border-brand/40">
            {BODY_FONTS.map((f) => (
              <option key={f.v} value={f.v}>文 · {f.label}</option>
            ))}
          </select>
        </div>
        <div className="flex gap-1">
          {CB_TYPES.map((k) => (
            <button key={k.v} title={k.hint} onClick={() => addBlock({ type: k.v, text: '' })}
              className="rounded border border-border bg-surface px-1.5 py-[3px] text-[11px]
                         text-ink-soft hover:border-brand/40 hover:text-brand-ink">
              +{k.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex gap-1.5">
          <button onClick={doSave}
            className="rounded-lg border border-border px-2.5 py-1 text-[12px] text-ink-soft
                       hover:border-brand/40 hover:text-brand-ink">保存</button>
          <button onClick={run} disabled={busy}
            className="rounded-lg bg-brand px-3 py-1 text-[12px] font-medium text-white
                       disabled:opacity-50">{busy ? '生成中…' : '生成 PDF'}</button>
        </div>
      </div>

      {/* 画布本体 */}
      <div className="min-h-0 flex-1 overflow-auto bg-muted/40 p-5">
        <style>{fontCss}</style>
        <div ref={canvasRef}
          onClick={() => setSel(null)}
          className="handout-canvas relative mx-auto shadow-lg"
          style={{ width: '100%', maxWidth: 900, aspectRatio: String(aspect) }}>
          {blocks.map((b) => (
            <div key={b.id}
              onMouseDown={(e) => startDrag(e, b, 'move')}
              onClick={(e) => { e.stopPropagation(); setSel(b.id) }}
              className={`absolute cursor-move select-none rounded ${
                overflowed.has(b.id)
                  ? 'ring-2 ring-red-400'
                  : sel === b.id ? 'ring-2 ring-brand/50' : 'hover:ring-1 hover:ring-brand/30'}`}
              style={{
                left: `${b.x}%`, top: `${b.y}%`, width: `${b.w}%`,
                height: b.h > 0 ? `${b.h}%` : 'auto', zIndex: (b.z || 0) + 1,
                padding: 2,
              }}>
              {/* zoom：<1 时把整块内容等比缩小 → 大题收进一页。
                  zoom（而非 transform）会**按整宽重排**再缩放，
                  不会把文字横向压扁。 */}
              <div ref={(el) => { measRef.current[b.id] = el }}
                style={{ zoom: fits[b.id] || 1 }}>
                <CBlockView b={b} qmap={blockQs}
                  fs={blockFontSize(b)} showSource={showSource} />
              </div>
              {overflowed.has(b.id) && (
                <div title="内容超出框高，拖右下角放大，或在右侧调大「高 %」"
                  className="absolute -top-2 -right-2 flex h-4 w-4 items-center justify-center
                             rounded-full bg-red-500 text-[10px] font-bold text-white shadow">
                  !
                </div>
              )}
              {sel === b.id && (
                <div onMouseDown={(e) => startDrag(e, b, 'resize')}
                  title="拖动改大小"
                  className="absolute -bottom-1 -right-1 h-3 w-3 cursor-se-resize
                             rounded-sm border border-white bg-brand" />
              )}
            </div>
          ))}
          {!blocks.length && (
            <div className="absolute inset-0 flex items-center justify-center
                            text-[12px] text-ink-faint">
              点左上按钮添加块，或从左侧点题目加入
            </div>
          )}

          {/* 离屏测量：满宽渲染，量出内容固有尺寸（不显示） */}
          <div aria-hidden
            style={{ position: 'absolute', left: -99999, top: 0,
                     width: '100%', visibility: 'hidden', pointerEvents: 'none' }}>
            {blocks.map((b) => (
              <div key={`probe-${b.id}`}
                ref={(el) => { probeRef.current[b.id] = el }}
                style={{ width: '100%', lineHeight: b.lineHeight ?? DEFAULT_LH }}>
                <CBlockView b={b} qmap={blockQs} fs={blockFontSize(b)} showSource={showSource} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 页面条 */}
      <div className="flex items-center gap-2 border-t border-border px-3 py-1.5 text-[11.5px]">
        <button onClick={() => setCur((c) => Math.max(0, c - 1))} disabled={cur === 0}
          className="rounded border border-border px-1.5 py-[1px] disabled:opacity-30">‹</button>
        <span className="tabular-nums">第 {cur + 1} / {pages.length} 页</span>
        <button onClick={() => setCur((c) => Math.min(pages.length - 1, c + 1))}
          disabled={cur >= pages.length - 1}
          className="rounded border border-border px-1.5 py-[1px] disabled:opacity-30">›</button>
        <button onClick={() => { setPages((p) => [...p, { blocks: [] }]); setCur(pages.length) }}
          className="rounded border border-border px-1.5 py-[1px] hover:border-brand/40">+ 加页</button>
        {pages.length > 1 && (
          <button onClick={() => {
            setPages((p) => p.filter((_, i) => i !== cur))
            setCur((c) => Math.max(0, c - 1))
          }} className="rounded border border-border px-1.5 py-[1px] text-red-600
                        hover:border-red-300">删本页</button>
        )}
        {overflowed.size > 0 && (
          <span className="rounded bg-red-50 px-1.5 py-[1px] text-red-600">
            ⚠ {overflowed.size} 个块内容溢出（红框标出）
          </span>
        )}
        <span className="ml-auto text-ink-faint">{blocks.length} 个块</span>
        {err && <span className="text-red-600">{err}</span>}
        {res?.saved_hint && <span className="text-brand-ink">✓ {res.saved_hint}</span>}
      </div>
    </div>
  )
}
