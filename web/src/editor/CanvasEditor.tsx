/** 讲义编辑器（画布式自由排版）。
 *
 *  从 App.tsx 抽出来：审查报告 CPLX-1 / REACT-4 指出编辑器曾是
 *  「一个组件管 8 件事」。这里按职责分三层：
 *    · 状态与逻辑 → 文件内的三个 hook
 *    · 三栏 UI     → 文件内的三个列组件
 *    · 本组件只负责组装
 */
import { useState } from 'react'
import type { Q } from '@/lib/types'
import { useDrawer } from '@/editor/useDrawer'
import { useCanvas } from '@/editor/useCanvas'
import { useHandoutIo } from '@/editor/useHandoutIo'
import PointDrawer from '@/editor/PointDrawer'
import CanvasStage from '@/editor/CanvasStage'
import Inspector from '@/editor/Inspector'
import { RATIO_BOX, DEFAULT_TITLE_FONT, DEFAULT_BODY_FONT } from '@/editor/shared'

export default function CanvasEditor({ handoutQs }: { handoutQs: Q[] }) {
  const [title, setTitle] = useState('未命名讲义')
  const [name, setName] = useState('未命名讲义')
  const [ratio, setRatio] = useState('16:9')
  const [withAns, setWithAns] = useState(false)
  const [titleFont, setTitleFont] = useState(DEFAULT_TITLE_FONT)
  const [bodyFont, setBodyFont] = useState(DEFAULT_BODY_FONT)
  // 左栏（考点树 / 搜索 / 懒加载）→ useDrawer
  const {
    q, setQ, searchResults, topics, openTopic, setOpenTopic,
    openPoint, pointQs, loadingPt, togglePoint,
  } = useDrawer()
  // 画布状态（块/页面/测量/适配缩放/拖拽）→ useCanvas
  const {
    pages, setPages, cur, setCur, sel, setSel, blocks,
    fits, overflowed, natural, blockQs, canvasRef, measRef, probeRef,
    addBlock, addQuestion, patch, remove, bringToFront, startDrag,
  } = useCanvas(ratio)

  // 页面比例（画布宽高比）—— 渲染用，不属于 hook
  const box = RATIO_BOX[ratio] || RATIO_BOX['16:9']
  const aspect = box.w / box.h

  // 字体选择 → 注入 CSS 变量，覆盖 handout.css 的默认字体
  // （用 <style> 而不是内联，因为 .p-hand / .p-t 等在子元素上）
  const fontCss = `
    .handout-canvas { --hc-font-hand: ${titleFont}; --hc-font-song: ${bodyFont}; }
  `



  // 存取与导出 → useHandoutIo
  const { busy, res, err, saved, run, doSave, doLoad } = useHandoutIo({
    pages, setPages, setCur, setSel, title, setTitle, name, setName,
    ratio, setRatio, withAns, setWithAns, titleFont, setTitleFont,
    bodyFont, setBodyFont, fits,
  })

  const selBlock = blocks.find((b) => b.id === sel) || null

  return (
    <div className="flex h-full min-h-0">
      <PointDrawer
        handoutQs={handoutQs}
        q={q} setQ={setQ} searchResults={searchResults} topics={topics}
        openTopic={openTopic} setOpenTopic={setOpenTopic} openPoint={openPoint}
        pointQs={pointQs} loadingPt={loadingPt} togglePoint={togglePoint}
        addQuestion={addQuestion}
      />
      <CanvasStage
        title={title} setTitle={setTitle} name={name} setName={setName}
        titleFont={titleFont} setTitleFont={setTitleFont}
        bodyFont={bodyFont} setBodyFont={setBodyFont}
        run={run} busy={busy} doSave={doSave} err={err} res={res}
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
    </div>
  )
}
