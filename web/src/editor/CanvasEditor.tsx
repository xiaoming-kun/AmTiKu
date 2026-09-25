/** 讲义编辑器（画布式自由排版）。
 *
 *  从 App.tsx 抽出来：审查报告 CPLX-1 / REACT-4 指出编辑器曾是
 *  「一个组件管 8 件事」。这里按职责分三层：
 *    · 状态与逻辑 → 文件内的三个 hook
 *    · 三栏 UI     → 文件内的三个列组件
 *    · 本组件只负责组装
 */
import { useEffect, useState } from 'react'
import { FileText, Plus } from 'lucide-react'
import type { Q } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { Detail } from '@/app/Detail'
import { CloseBtn } from '@/app/ui'
import { useDrawer } from '@/editor/useDrawer'
import { useCanvas } from '@/editor/useCanvas'
import { useHandoutIo } from '@/editor/useHandoutIo'
import PointDrawer from '@/editor/PointDrawer'
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
  // 点左栏题目 → 右侧弹出整道题（题干/答案/解析），跟主页面同一个 Detail
  const [preview, setPreview] = useState<Q | null>(null)
  const [pvFull, setPvFull] = useState<Q | null>(null)
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

  const onPreviewSaved = (d: Q) => {
    setPreview(d); setPvFull(d)
    refreshQ(d)          // 这道题要是在画布上，别让它显示旧答案/旧解析
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

  return (
    // 三栏骨架：左右是 bg-surface 的面板，中间画布区 bg-bg 暗一档，
    // 画布上的白色纸张才浮得起来（分割一律用 border-border）。
    <div className="relative flex h-full min-h-0 bg-bg">
      <PointDrawer
        handoutQs={handoutQs}
        q={q} setQ={setQ} searchResults={searchResults} topics={topics}
        openTopic={openTopic} setOpenTopic={setOpenTopic} openPoint={openPoint}
        pointQs={pointQs} loadingPt={loadingPt} togglePoint={togglePoint}
        addQuestion={addQuestion} previewQuestion={setPreview}
      />
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
          浮在最上层、盖住右侧属性面板：跟主页面一样是「从右边滑出来的抽屉」，
          看完点「加入画布」直接进当前页，Esc / 关闭回画布。 */}
      {preview && (
        <aside className="anim-slide-r absolute inset-y-0 right-0 z-30 flex w-[470px]
                          max-w-[70%] flex-col border-l border-border bg-surface
                          shadow-[var(--shadow-pop)]">
          <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border px-3.5">
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
