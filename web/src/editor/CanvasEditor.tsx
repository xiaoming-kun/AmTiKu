/** 讲义编辑器（画布式自由排版）。
 *
 *  从 App.tsx 抽出来：审查报告 CPLX-1 / REACT-4 指出编辑器曾是
 *  「一个组件管 8 件事」。这里按职责分三层：
 *    · 状态与逻辑 → 文件内的三个 hook
 *    · 三栏 UI     → 文件内的三个列组件
 *    · 本组件只负责组装
 */
import { useEffect, useRef, useState } from 'react'
import { FileText, GripHorizontal, Plus } from 'lucide-react'
import type { Q } from '@/lib/types'
import type { Block } from '@/lib/render'
import { api, reportErr } from '@/lib/api'
import { Detail } from '@/app/Detail'
import { CloseBtn } from '@/app/ui'
import { useDrawer } from '@/editor/useDrawer'
import { useCanvas } from '@/editor/useCanvas'
import { useHandoutIo } from '@/editor/useHandoutIo'
import PointDrawer from '@/editor/PointDrawer'
import KlistDrawer from '@/editor/KlistDrawer'
import CanvasStage from '@/editor/CanvasStage'
import Inspector from '@/editor/Inspector'
import { RATIO_BOX, DEFAULT_TITLE_FONT, DEFAULT_BODY_FONT } from '@/editor/shared'

/** 讲义编辑器。
 *
 *  `facets` 只透传给右侧的题目详情（考点树一样要能展开，
 *  跟主页面是同一个组件、同一份数据）。
 */
export default function CanvasEditor({ handoutQs, facets }: {
  handoutQs: Q[]; facets?: any
}) {
  const [title, setTitle] = useState('未命名讲义')
  const [name, setName] = useState('未命名讲义')
  const [ratio, setRatio] = useState('16:9')
  const [withAns, setWithAns] = useState(false)
  const [titleFont, setTitleFont] = useState(DEFAULT_TITLE_FONT)
  const [bodyFont, setBodyFont] = useState(DEFAULT_BODY_FONT)
  // 点左栏题目 → 悬空弹出整道题（题干/答案/解析），跟主页面同一个 Detail
  const [preview, setPreview] = useState<Q | null>(null)
  const [pvFull, setPvFull] = useState<Q | null>(null)
  const panelRef = useRef<HTMLElement | null>(null)
  const hostRef = useRef<HTMLDivElement | null>(null)
  /** 面板被拖到哪儿了（px，相对编辑器内容区）。null = 还停在默认位（上方居中）。
   *  拖动后**记住**：换一道题看时不会又跳回默认位。 */
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  /** 左栏内容源：题库的题 / 知识清单的讲解（同一栏切换） */
  const [src, setSrc] = useState<'bank' | 'klist'>('bank')
  // 左栏（考点树 / 搜索 / 懒加载）→ useDrawer
  const {
    q, setQ, searchResults, topics, openTopic, setOpenTopic,
    openPoint, pointQs, loadingPt, togglePoint,
  } = useDrawer()
  // 画布状态（块/页面/测量/适配缩放/拖拽）→ useCanvas
  const {
    pages, setPages, cur, setCur, sel, setSel, blocks,
    fits, overflowed, natural, blockQs, canvasRef, measRef, probeRef,
    addBlock, addQuestion, patch, remove, bringToFront, startDrag, refreshQ,
  } = useCanvas(ratio)

  /** 详情要**全量**记录：列表接口只为省 CPU 返回题干块 IR，
   *  答案/解析得按 key 再补一次（和主页面 `App.tsx` 的做法一致）。 */
  useEffect(() => {
    const k = preview?.key
    if (!k) { setPvFull(null); return }
    let alive = true
    api.get(k).then((d) => { if (alive) setPvFull(d) }).catch(reportErr)
    return () => { alive = false }
  }, [preview?.key])

  // Esc 关掉详情（和主页面一致）
  useEffect(() => {
    if (!preview) return
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') setPreview(null) }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [preview])

  /** 点面板以外的任何地方 → 收起来。悬空的板子不该赖着不走。
   *
   *  用 `mousedown` 而不是 `click`：`click` 要等鼠标抬起，拖画布上的块时
   *  板子会一直挡着；按下就收，看不见的东西不参与拖拽。
   *
   *  **左栏例外**：点另一道题时先收再开会在按住鼠标那一瞬间闪一下，
   *  所以左栏里的点击交给它自己（点了就直接换成新题）。 */
  useEffect(() => {
    if (!preview) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Element | null
      if (panelRef.current?.contains(t as Node)) return
      if (t?.closest?.('[data-qdrawer]')) return
      setPreview(null)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [preview])

  const onPreviewSaved = (d: Q) => {
    setPreview(d); setPvFull(d)
    refreshQ(d)          // 这道题要是在画布上，别让它显示旧答案/旧解析
  }

  /** 拖标题栏挪面板 —— 位置由老师自己定，爱放哪儿放哪儿。
   *
   *  用 px 而不是 %：面板是「看题用的小窗」，跟画布比例无关。
   *  第一次拖之前面板靠 CSS 居中（`left-1/2 -translate-x-1/2`），
   *  这里先量一次真实位置再转成 px，所以起步不会跳。 */
  const startPanelDrag = (e: React.MouseEvent) => {
    // 点在「加入画布 / 关闭」上时是点按钮，不是拖
    if ((e.target as Element)?.closest?.('button')) return
    const panel = panelRef.current, host = hostRef.current
    if (!panel || !host) return
    e.preventDefault()
    const pr = panel.getBoundingClientRect()
    const hr = host.getBoundingClientRect()
    const offX = e.clientX - pr.left          // 抓住的位置相对面板左上角
    const offY = e.clientY - pr.top
    const clamp = (v: number, hi: number) => Math.max(0, Math.min(v, Math.max(0, hi)))
    setPos({ x: clamp(pr.left - hr.left, hr.width - pr.width), y: clamp(pr.top - hr.top, 0) })
    const move = (ev: MouseEvent) => setPos({
      x: clamp(ev.clientX - hr.left - offX, hr.width - pr.width),
      y: clamp(ev.clientY - hr.top - offY, hr.height - Math.min(pr.height, hr.height)),
    })
    const up = () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }

  // 页面比例（画布宽高比）—— 渲染用，不属于 hook
  const box = RATIO_BOX[ratio] || RATIO_BOX['16:9']
  const aspect = box.w / box.h

  // 字体选择 → 注入 CSS 变量，覆盖 handout.css 的默认字体
  // （用 <style> 而不是内联，因为 .p-hand / .p-t 等在子元素上）
  const fontCss = `
    .handout-canvas { --hc-font-hand: ${titleFont}; --hc-font-song: ${bodyFont}; }
  `



  // 存取与导出 → useHandoutIo
  const { busy, busySince, res, err, saved, run, doSave, doLoad } = useHandoutIo({
    pages, setPages, setCur, setSel, title, setTitle, name, setName,
    ratio, setRatio, withAns, setWithAns, titleFont, setTitleFont,
    bodyFont, setBodyFont, fits,
  })

  const selBlock = blocks.find((b) => b.id === sel) || null

  /** 左栏来源：题库 / 知识清单。两个来源**共用同一个开关** ——
   *  各画一份的话，改样式就要记得改两处（这个项目栽过的 DUP 坑）。 */
  const switchSrc = (
    <div className="flex shrink-0 items-center gap-0.5 rounded-lg bg-muted p-0.5">
      {([['bank', '题库'], ['klist', '知识清单']] as const).map(([v, label]) => (
        <button key={v} onClick={() => setSrc(v)}
          className={`press rounded-[6px] px-2 py-[3px] text-[11.5px] font-medium transition-colors ${
            src === v ? 'bg-surface text-ink shadow-[0_1px_2px_rgba(0,0,0,.06)]'
                      : 'text-ink-faint hover:text-ink-soft'}`}>
          {label}
        </button>
      ))}
    </div>
  )

  /** 知识清单的一节 → 画布上的一整块讲解（块级 IR 快照一并存下去）。 */
  const addKlist = (n: { id: string; title: string; blocks: Block[] }) =>
    addBlock({ type: 'klist', text: n.title, nid: n.id, ir: n.blocks })

  return (
    // 三栏骨架：左右是 bg-surface 的面板，中间画布区 bg-bg 暗一档，
    // 画布上的白色纸张才浮得起来（分割一律用 border-border）。
    <div ref={hostRef} className="relative flex h-full min-h-0 bg-bg">
      {src === 'klist' ? (
        <KlistDrawer head={switchSrc} onAdd={addKlist} />
      ) : (
        <PointDrawer
          head={switchSrc}
          handoutQs={handoutQs}
          q={q} setQ={setQ} searchResults={searchResults} topics={topics}
          openTopic={openTopic} setOpenTopic={setOpenTopic} openPoint={openPoint}
          pointQs={pointQs} loadingPt={loadingPt} togglePoint={togglePoint}
          addQuestion={addQuestion} previewQuestion={setPreview}
        />
      )}
      <CanvasStage
        title={title} setTitle={setTitle} name={name} setName={setName}
        titleFont={titleFont} setTitleFont={setTitleFont}
        bodyFont={bodyFont} setBodyFont={setBodyFont}
        withAns={withAns}
        run={run} busy={busy} busySince={busySince} doSave={doSave} err={err} res={res}
        canvasRef={canvasRef} aspect={aspect}
        pages={pages} cur={cur} setCur={setCur} setPages={setPages}
        blocks={blocks} sel={sel} setSel={setSel}
        fits={fits} overflowed={overflowed} startDrag={startDrag}
        measRef={measRef} probeRef={probeRef} blockQs={blockQs}
        addBlock={addBlock} fontCss={fontCss}
      />
      <Inspector
        selBlock={selBlock} patch={patch} remove={remove} bringToFront={bringToFront}
        ratio={ratio} setRatio={setRatio} withAns={withAns} setWithAns={setWithAns}
        saved={saved} doLoad={doLoad} natural={natural} canvasRef={canvasRef}
      />

      {/* ── 题目详情（点左栏题目弹出来）──
          **悬空**的小窗：默认落在上方居中，四边不贴边、圆角 + 大投影。
          拖标题栏可以挪到任意位置，挪过之后就一直记着（换题不跳回原位）。
          点别处 / Esc / ✕ 收起，看完点「加入画布」进当前页。 */}
      {preview && (
        <aside ref={panelRef}
          /* 高度上限跟着落点走：拖到下面时自动矮一点，再长的题也不会从窗口
             底下冒出去（`100%` = 编辑器内容区的高度） */
          style={pos ? { left: pos.x, top: pos.y,
                         maxHeight: `calc(100% - ${pos.y + 16}px)` } : undefined}
          className={`anim-pop absolute z-30 flex max-h-[calc(100%-2rem)] w-[540px]
                      max-w-[calc(100%-2rem)] flex-col overflow-hidden rounded-2xl
                      border border-border bg-surface shadow-[var(--shadow-pop)]
                      ring-1 ring-black/[0.03] ${pos ? '' : 'left-1/2 top-4 -translate-x-1/2'}`}>
          {/* 标题栏 = 拖动把手 */}
          <div onMouseDown={startPanelDrag} title="按住这里可以拖动整个窗口"
            className="flex h-[52px] shrink-0 cursor-move items-center gap-2 border-b
                       border-border px-3.5 select-none">
            <GripHorizontal size={15} className="shrink-0 text-ink-faint" />
            <FileText size={15} className="shrink-0 text-brand" />
            <span className="text-[13.5px] font-semibold">题目详情</span>
            <span className="ml-auto shrink-0" />
            <button onClick={() => { addQuestion(preview); setPreview(null) }}
              className="press inline-flex h-[30px] shrink-0 items-center gap-1.5 rounded-lg
                         bg-brand px-3 text-[12.5px] font-medium text-white
                         shadow-[var(--shadow-brand)] transition-[filter] hover:brightness-105">
              <Plus size={13} />加入画布
            </button>
            <CloseBtn onClick={() => setPreview(null)} title="关闭（Esc）" />
          </div>
          <div key={preview.key} className="anim-fade-in min-h-0 flex-1">
            <Detail q={pvFull && pvFull.key === preview.key ? pvFull : preview}
              facets={facets} onSaved={onPreviewSaved} />
          </div>
        </aside>
      )}
    </div>
  )
}
