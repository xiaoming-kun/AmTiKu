/** 讲义的存取与导出。
 *
 *  从 CanvasEditor 抽出来的（审查报告 CPLX-1）。
 *  只管「跟磁盘/后端打交道」这三件事：导出 PDF、保存、加载。
 *  文档状态（页/标题/比例/字体）由调用方持有，通过参数传进来。
 */
import { useEffect, useState } from 'react'
import { api, request, send, reportErr } from '@/lib/api'
import { uid, DEFAULT_TITLE_FONT, DEFAULT_BODY_FONT } from '@/editor/shared'

export type Page = { blocks: any[] }

export function useHandoutIo(params: {
  pages: Page[]
  setPages: (p: any) => void
  setCur: (n: number) => void
  setSel: (id: string | null) => void
  title: string
  setTitle: (s: string) => void
  name: string
  setName: (s: string) => void
  ratio: string
  setRatio: (s: string) => void
  withAns: boolean
  setWithAns: (b: boolean) => void
  titleFont: string
  setTitleFont: (s: string) => void
  bodyFont: string
  setBodyFont: (s: string) => void
  fits: Record<string, number>
  showSource: boolean
  setShowSource: (b: boolean) => void
}) {
  const { pages, setPages, setCur, setSel, title, setTitle, name, setName,
          ratio, setRatio, withAns, setWithAns, titleFont, setTitleFont,
          bodyFont, setBodyFont, fits, showSource, setShowSource } = params

  const [busy, setBusy] = useState(false)
  // 生成开始的时间戳：进度浮层用它显示已用时间/当前阶段
  const [busySince, setBusySince] = useState(0)
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState<any[]>([])

  const loadList = () =>
    api.handouts().then((d) => setSaved(d.items || [])).catch(reportErr)

  useEffect(() => { loadList() }, [])   // 打开时拉一次已存讲义

  /** 序列化：剥掉本地 id，带上算好的适配缩放系数 */
  const serialize = () => pages.map((p: any) => ({
    blocks: p.blocks.map(({ id, ...rest }: any) => ({ ...rest, fit: fits[id] ?? 1 })),
  }))

  const run = () => {
    const clean = serialize()
    if (!clean.some((p) => p.blocks.length)) { setErr('画布是空的'); return }
    setBusy(true); setBusySince(Date.now()); setErr(''); setRes(null)
    send('/api/export/slidev-canvas', 'POST', {
      title, out: name, pages: clean, ratio, with_answers: withAns,
      compile: true, title_font: titleFont, body_font: bodyFont,
      show_source: showSource,
    })
      .then(setRes)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false))
  }

  const doSave = () => {
    send('/api/canvas/save', 'POST', {
      name, title, pages: serialize(), ratio, with_answers: withAns,
      title_font: titleFont, body_font: bodyFont, show_source: showSource,
    })
      .then(loadList)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }

  const doLoad = (n: string) => {
    request(`/api/canvas/${encodeURIComponent(n)}`).then((h) => {
      const ps = (h.blocks || []).map((p: any) => ({
        blocks: (p.blocks || []).map((b: any) => ({ ...b, id: uid() })),
      }))
      setPages(ps.length ? ps : [{ blocks: [] }])
      setCur(0); setSel(null)
      setTitle(h.title || n); setName(h.name || n)
      setRatio(h.ratio || '16:9'); setWithAns(!!h.with_answers)
      setTitleFont(h.title_font || DEFAULT_TITLE_FONT)
      setBodyFont(h.body_font || DEFAULT_BODY_FONT)
      setShowSource(h.show_source !== false)      // 默认开
    }).catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }

  const removeSaved = (n: string) =>
    api.deleteHandout(n).then(loadList).catch(reportErr)

  return { busy, busySince, res, err, setErr, saved, loadList, run, doSave, doLoad, removeSaved }
}
