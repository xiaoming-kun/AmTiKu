/** 编辑器中栏：画布 + 顶部工具条 + 翻页条。
 *
 *  从 CanvasEditor 拆出来的（审查报告 REACT-4）。
 *
 *  视觉：中栏整块是 bg-bg（比左右面板暗一档），白色纸张靠
 *  shadow-pop 浮起来；工具条拆成两行——上行放标题与主按钮（52px），
 *  下行放字体与插入块（小一档），两行都用 border-b 收边。
 */
import type { Dispatch, MutableRefObject, SetStateAction } from 'react'
import {
  Check, ChevronLeft, ChevronRight, Download, FileText, LayoutGrid, Loader2,
  Plus, Save, TriangleAlert,
} from 'lucide-react'
import type { Q } from '@/lib/types'
import {
  CBlockView, blockFontSize, CB_TYPES, TITLE_FONTS, BODY_FONTS,
  DEFAULT_LH, type CBlock,
} from '@/editor/shared'
import CompileOverlay, { SLIDEV_STAGES } from '@/app/CompileOverlay'

/** 工具条上的输入框 / 下拉：统一的描边与聚焦圈（字号、高度由调用点给，
 *  避免同一个属性出现两条 Tailwind 类、优先顺序由生成顺序决定）。 */
const BAR_FIELD = `rounded-lg border border-border bg-bg px-2.5 text-ink outline-none
  transition-[border-color,box-shadow] duration-150 placeholder:text-ink-faint
  focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]`

export default function CanvasStage({ title, setTitle, name, setName,
  titleFont, setTitleFont, bodyFont, setBodyFont, run, busy, busySince, doSave, err, res,
  canvasRef, aspect, pages, cur, setCur, setPages, blocks, sel, setSel,
  fits, overflowed, startDrag, measRef, probeRef, blockQs,
  addBlock, fontCss, showSource }: {
  title: string; setTitle: Dispatch<SetStateAction<string>>
  name: string; setName: Dispatch<SetStateAction<string>>
  titleFont: string; setTitleFont: Dispatch<SetStateAction<string>>
  bodyFont: string; setBodyFont: Dispatch<SetStateAction<string>>
  run: () => void; busy: boolean; busySince: number; doSave: () => void
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
      {/* ── 工具条上行：标题 / 文件名 → 保存 / 生成 ── */}
      <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border bg-surface px-3.5">
        <FileText size={15} className="shrink-0 text-brand" />
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="标题"
          className={`${BAR_FIELD} h-[30px] w-40 text-[13px] font-medium`} />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="文件名"
          className={`${BAR_FIELD} h-[30px] w-32 text-[12.5px] text-ink-soft`} />
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <button onClick={doSave}
            className="press inline-flex h-[32px] items-center gap-1.5 rounded-lg border
                       border-border bg-surface px-3 text-[12.5px] text-ink-soft
                       transition-colors hover:border-border-strong hover:text-ink">
            <Save size={13} />保存
          </button>
          <button onClick={run} disabled={busy}
            className="press inline-flex h-[32px] items-center gap-1.5 rounded-lg bg-brand
                       px-3 text-[12.5px] font-medium text-white shadow-[var(--shadow-brand)]
                       transition-[filter,opacity] hover:brightness-105 disabled:opacity-50">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {busy ? '生成中…' : '生成 PDF'}
          </button>
        </div>
      </div>

      {/* ── 工具条下行：字体 + 插入块 ── */}
      <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1.5 border-b
                      border-border bg-surface px-3.5 py-2">
        <span className="text-[11px] font-semibold tracking-[0.08em] text-ink-faint">字体</span>
        <select value={titleFont} onChange={(e) => setTitleFont(e.target.value)}
          title="标题字体"
          className={`${BAR_FIELD} h-[28px] text-[11.5px] text-ink-soft`}>
          {TITLE_FONTS.map((f) => (
            <option key={f.v} value={f.v}>标 · {f.label}</option>
          ))}
        </select>
        <select value={bodyFont} onChange={(e) => setBodyFont(e.target.value)}
          title="正文字体"
          className={`${BAR_FIELD} h-[28px] text-[11.5px] text-ink-soft`}>
          {BODY_FONTS.map((f) => (
            <option key={f.v} value={f.v}>文 · {f.label}</option>
          ))}
        </select>

        <span className="mx-0.5 h-4 w-px shrink-0 bg-border" />

        <span className="text-[11px] font-semibold tracking-[0.08em] text-ink-faint">插入</span>
        <div className="flex flex-wrap gap-1">
          {CB_TYPES.map((k) => (
            <button key={k.v} title={k.hint} onClick={() => addBlock({ type: k.v, text: '' })}
              className="press inline-flex items-center gap-1 rounded-lg border border-border
                         bg-bg px-2 py-[3px] text-[11.5px] text-ink-soft transition-colors
                         hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink">
              <Plus size={11} />{k.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── 画布本体 ── */}
      <div className="relative min-h-0 flex-1 overflow-auto bg-bg p-5">
        {/* 生成中：转圈 + 阶段清单 + 计时（等 30~60 秒，得让人知道在干嘛） */}
        {busy && (
          <CompileOverlay since={busySince} label="正在生成讲义 PDF"
            stages={SLIDEV_STAGES}
            hint="第一次导出要冷启动浏览器内核，会慢一些；页数越多越慢。中途不用重复点。" />
        )}
        <style>{fontCss}</style>
        <div ref={canvasRef}
          onClick={() => setSel(null)}
          className="handout-canvas relative mx-auto rounded-[3px] shadow-[var(--shadow-pop)]
                     ring-1 ring-border"
          style={{ width: '100%', maxWidth: 900, aspectRatio: String(aspect) }}>
          {blocks.map((b) => (
            <div key={b.id}
              onMouseDown={(e) => startDrag(e, b, 'move')}
              onClick={(e) => { e.stopPropagation(); setSel(b.id) }}
              className={`group absolute cursor-move select-none rounded-[3px]
                          transition-shadow duration-150 ${
                overflowed.has(b.id)
                  ? 'ring-2 ring-danger/60'
                  : sel === b.id ? 'ring-2 ring-brand' : 'hover:ring-1 hover:ring-brand-line'}`}
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
                  className="absolute -right-1.5 -top-1.5 grid h-4 w-4 place-items-center rounded-full
                             bg-danger text-white shadow-[var(--shadow-card)]">
                  <TriangleAlert size={10} />
                </div>
              )}
              {sel === b.id && (
                <div onMouseDown={(e) => startDrag(e, b, 'resize')}
                  title="拖动改大小"
                  className="absolute -bottom-[3px] -right-[3px] h-2.5 w-2.5 cursor-se-resize
                             rounded-[3px] border border-white bg-brand opacity-0
                             shadow-[var(--shadow-card)] transition-[opacity,transform]
                             duration-150 hover:scale-125 group-hover:opacity-100" />
              )}
            </div>
          ))}
          {!blocks.length && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2
                            text-ink-faint">
              <LayoutGrid size={20} className="opacity-50" />
              <div className="text-[12.5px]">点左上按钮添加块，或从左侧点题目加入</div>
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

      {/* ── 页面条 ── */}
      <div className="flex shrink-0 items-center gap-1.5 border-t border-border bg-surface
                      px-3.5 py-2 text-[11.5px] text-ink-faint">
        <button onClick={() => setCur((c) => Math.max(0, c - 1))} disabled={cur === 0}
          title="上一页" className="icon-btn h-6 w-6 disabled:pointer-events-none disabled:opacity-30">
          <ChevronLeft size={14} />
        </button>
        <span className="tnum px-0.5 text-ink-soft">第 {cur + 1} / {pages.length} 页</span>
        <button onClick={() => setCur((c) => Math.min(pages.length - 1, c + 1))}
          disabled={cur >= pages.length - 1}
          title="下一页" className="icon-btn h-6 w-6 disabled:pointer-events-none disabled:opacity-30">
          <ChevronRight size={14} />
        </button>
        <button onClick={() => { setPages((p) => [...p, { blocks: [] }]); setCur(pages.length) }}
          className="press ml-1 inline-flex items-center gap-1 rounded-lg border border-border
                     bg-surface px-2 py-[3px] text-[11.5px] text-ink-soft transition-colors
                     hover:border-border-strong hover:text-ink">
          <Plus size={12} />加页
        </button>
        {pages.length > 1 && (
          <button onClick={() => {
            setPages((p) => p.filter((_, i) => i !== cur))
            setCur((c) => Math.max(0, c - 1))
          }} className="press inline-flex items-center gap-1 rounded-lg border border-border
                        bg-surface px-2 py-[3px] text-[11.5px] text-ink-faint transition-colors
                        hover:border-danger/40 hover:bg-danger-soft hover:text-danger">
            <TriangleAlert size={12} />删本页
          </button>
        )}
        {overflowed.size > 0 && (
          <span className="inline-flex items-center gap-1 rounded-md bg-danger-soft px-1.5 py-[2px]
                           text-[11px] font-medium text-danger">
            <TriangleAlert size={11} />{overflowed.size} 个块内容溢出（红框标出）
          </span>
        )}
        <span className="tnum ml-auto text-ink-faint">{blocks.length} 个块</span>
        {err && <span className="text-danger">{err}</span>}
        {res?.saved_hint && (
          <span className="inline-flex items-center gap-1 text-has">
            <Check size={12} strokeWidth={2.6} />{res.saved_hint}
          </span>
        )}
      </div>
    </div>
  )
}
