/** 录入工作区的全部状态/handlers。
 *
 *  IngestWorkspace 只负责壳和阶段布局；Source/Review 通过 IngestContext
 *  读这里的字段。这样改录入逻辑不用再碰 JSX，改布局也不用碰状态。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/lib/api'
import {
  blockingOf, DEFAULT_BOOK, DEFAULT_LABEL, DEFAULT_YEAR, DRAFT_KEY, EMPTY,
  loadDraft,
} from './shared'
import type { EditMap, PickMap } from './shared'

export type IngestOptions = {
  ai: boolean
  facets: any
  onClose: () => void
  onDone: () => void
}

export function useIngest({ ai, facets, onClose, onDone }: IngestOptions) {
  const draft0 = useMemo(() => loadDraft(), [])
  const [text, setText] = useState(String(draft0.text || ''))
  const [book, setBook] = useState(String(draft0.book || DEFAULT_BOOK))
  const [label, setLabel] = useState(String(draft0.label || DEFAULT_LABEL))
  const [year, setYear] = useState(String(draft0.year || DEFAULT_YEAR))
  const [region, setRegion] = useState(String(draft0.region || ''))
  // 带 \includegraphics 的材料：图片所在目录（服务器本地路径）。
  // API 的 `src_dir` 早就有，界面一直没暴露；补上。
  const [srcDir, setSrcDir] = useState(String(draft0.srcDir || ''))
  // 手工录入硬规则：库里已有同题 → 整题跳过，不新增、不更新。
  // 不再提供「升级/覆盖」开关；LLM 录题那条线不受影响。
  // 解析后自动用 qwen3.5 补标；**默认关**——不勾就不会加载模型。
  // 要标时再点顶栏「AI 标注空缺」，或在这里勾上。
  const [autoTag, setAutoTag] = useState(!!draft0.autoTag)
  const [mainOnly, setMainOnly] = useState(false)
  const [llmStatus, setLlmStatus] = useState<any>(null)
  /** 整题相似阈值（百分数）：默认 95；> 这个值按规则不录入。 */
  const [nearThreshold, setNearThreshold] = useState(
    Number(draft0.nearThreshold) > 0 ? Math.min(100, Math.max(80, Number(draft0.nearThreshold))) : 95)
  /** 补旧题模式：只更新已有题的空考点/难度，不新增、不改正文。 */
  const [backfill, setBackfill] = useState(!!draft0.backfill)
  const [restored, setRestored] = useState(!!String(draft0.text || '').trim())
  const [pv, setPv] = useState<any>(null)
  const [picks, setPicks] = useState<PickMap>({})
  const [edits, setEdits] = useState<EditMap>({})
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  /** 审阅筛选：全部 / 新题 / 缺考点 / 疑似重复 / 有硬伤。只影响显示。 */
  const [reviewFilter, setReviewFilter] = useState<
    'all' | 'new' | 'missing' | 'suspect' | 'blocked'>('all')
  const [activeCard, setActiveCard] = useState<number>(-1)
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({})
  /** 批量修改：题型/难度/考点，只作用于当前勾选的题。 */
  const [batchType, setBatchType] = useState('')
  const [batchDiff, setBatchDiff] = useState('')
  const [batchPts, setBatchPts] = useState<string[]>([])
  /** 卡片内改源码：{block: 草稿}；保存时替换整份材料里对应的题块再重解析。 */
  const [srcEdit, setSrcEdit] = useState<Record<number, string>>({})
  const [srcOpen, setSrcOpen] = useState<Record<number, boolean>>({})
  /** 这一轮 AI 跑过、但没给出考点的题。卡片上提示「AI 没认出」，
   *  免得人以为模型根本没跑。 */
  const [aiMiss, setAiMiss] = useState<Record<number, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [tagging, setTagging] = useState(false)
  const [repairing, setRepairing] = useState<Record<number, boolean>>({})
  const [repairNote, setRepairNote] = useState<Record<number, string>>({})
  const [drag, setDrag] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [tagErr, setTagErr] = useState('')
  /** 本次提交的报告（有它时右栏显示结果，而不是空态）。 */
  const [report, setReport] = useState<any>(null)
  /** 标注请求的序号：重新解析后，旧请求的结果全部丢掉，不能贴错题。 */
  const tagSeq = useRef(0)
  /** 正在跑的标注请求数：用计数而不是布尔，避免"旧请求 finally 把新请求的
   *  loading 关掉"或"重新解析后 loading 永远卡住"。 */
  const activeTags = useRef(0)
  /** 上一次从标题里认出的出处。换一份材料时，只有当输入框里还是**上一次
   *  自动填的值**（或空）才覆盖；人改过的出处绝不被新标题冲掉。 */
  const lastHint = useRef<{ title: string; year: number | null }>({ title: '', year: null })
  const [vlmReady, setVlmReady] = useState(false)
  const [vlmEngine, setVlmEngine] = useState('')
  /* ── AI 读整份资料（DeepSeek）──
     状态机：没配 key → 设置面板；配了 → 选文件 → 后台跑任务（轮询进度）
     → 结果填进输入框 → 自动解析。**全程不写库**，和粘贴文本走同一条管线。 */
  const [aiCfg, setAiCfg] = useState<any>(null)
  const [aiSetup, setAiSetup] = useState(false)
  const [aiKey, setAiKey] = useState('')
  const [aiBusy, setAiBusy] = useState(false)
  const [aiTesting, setAiTesting] = useState(false)
  const [aiProg, setAiProg] = useState<{ done: number; total: number; msg: string; sec?: number } | null>(null)
  /** 答案 / 解析——**和试题分开的一份文件**。最常见的形态是「一份试题 + 一份答案」，
   *  所以它跟试题一样是必填的引导项，只是允许留空（留空时缺答案的题会被拦下）。 */
  const [aiAns, setAiAns] = useState<{ name: string; b64: string }[]>([])
  const [aiErr, setAiErr] = useState('')
  const [aiNote, setAiNote] = useState('')
  /** 后台任务 id / 是否已点取消。取消接口只发一次，状态靠轮询推进。 */
  const [aiJobId, setAiJobId] = useState('')
  const [aiCancelling, setAiCancelling] = useState(false)
  /** AI 结果的逐题核对元数据：block → {pages, answer_pages, answer_quote, ...} */
  const [aiCards, setAiCards] = useState<Record<number, any>>({})
  /** 最后一次 AI 读取的报告（页数/命中/费用/覆盖/警告）；只给结果卡用。 */
  const [aiReport, setAiReport] = useState<any>(null)
  const [aiPageDir, setAiPageDir] = useState('')
  const [pageView, setPageView] = useState<{ dir: string; name: string; title: string } | null>(null)
  /** 最近任务的源页：准备/继续后显示，点开用现有 pageView 看原页。 */
  const [sourcePages, setSourcePages] = useState<string[]>([])
  const [sourceDir, setSourceDir] = useState('')
  const [sourceJob, setSourceJob] = useState('')
  const [recentJobs, setRecentJobs] = useState<any[]>([])
  /** 高级设置：模型 / 接口地址。规范管线一次读完，没有分批和并发可调。 */
  const [aiModel, setAiModel] = useState('')
  const [aiBase, setAiBase] = useState('')
  /** 任务序号：关掉录入页/换文件时，旧轮询的结果一律丢掉。 */
  const aiSeq = useRef(0)
  const aiSourceName = useRef('')
  const aiSourceFields = useRef<{ book: string; label: string; year: string; region: string } | null>(null)

  useEffect(() => {
    api.vlmStatus().then((s: any) => {
      setVlmReady(!!s?.ready)
      setVlmEngine(s?.engine === 'paddle+27b'
        ? 'PaddleOCR-VL 认字 → 27B 改格式'
        : (s?.engine === 'llama.cpp' ? 'llama.cpp 读图模型' : ''))
    }).catch(() => { setVlmReady(false); setVlmEngine('') })
  }, [])

  const pointInfo = useMemo(() => {
    const m = new Map<string, any>()
    for (const p of (facets?.points || [])) m.set(p.value, p)
    return m
  }, [facets])
  const points = facets?.points || []

  const resetReview = () => {
    tagSeq.current += 1
    setPv(null); setPicks({}); setEdits({}); setExpanded({})
    setSrcEdit({}); setSrcOpen({})
    setReviewFilter('all'); setActiveCard(-1)
    setBatchType(''); setBatchDiff(''); setBatchPts([])
    setReport(null)
    setAiMiss({})
    setMsg(''); setErr(''); setTagErr('')
  }

  const changeText = (v: string) => {
    setText(v)
    resetReview()
  }

  /** 从源材料读文本（.tex/.txt）；图片/PDF 走读图模型。 */
  const readFile = (f: File) => {
    const isImg = f.type.startsWith('image/')
    const isPdf = f.type === 'application/pdf' || /\.pdf$/i.test(f.name)
    // 图片直接读；PDF/Word 先登记任务并渲源页，再走本地读图
    if (isImg) { ocrFile(f); return }
    if (isPdf || /\.docx$/i.test(f.name)) { void prepareSource(f); return }
    const r = new FileReader()
    r.onload = () => { changeText(String(r.result || '')) }
    r.readAsText(f, 'utf-8')
  }

  /** 图片 / PDF → LaTeX，只填进输入框；**不写库**。 */
  const ocrFile = (f: File, jobId = '') => {
    setBusy(true); setErr(''); setMsg(`正在识别 ${f.name} …（首次要等模型加载）`)
    const r = new FileReader()
    r.onload = async () => {
      try {
        const b64 = String(r.result || '').split(',')[1] || ''
        const res: any = await api.vlmExtract(b64, f.name)
        changeText(res.latex || '')
        if (jobId && res.latex) {
          // 缓存识别结果：继续任务时不再重跑本地模型
          api.ingestJobSaveOcr(jobId, {
            latex: res.latex, model: res.model, pages: res.pages,
            seconds: res.seconds, warnings: res.warnings || [],
          }).catch(() => { /* 缓存失败不挡录入 */ })
        }
        setVlmReady(true)
        setMsg(`识别完成（${res.model}，${res.pages} 页，${res.seconds} 秒）`
               + (res.warnings?.length ? ' ⚠ ' + res.warnings.join('；') : '')
               + ' — 核对无误后点「解析成题」')
      } catch (e) {
        setErr(String((e as any)?.message || e)); setMsg('')
      } finally { setBusy(false) }
    }
    r.onerror = () => { setErr('读不出这个文件'); setBusy(false) }
    r.readAsDataURL(f)
  }

  /** DOCX → 后端转 PDF → 本地读图。只填编辑器，不写库；失败不静默。 */
  async function prepareSource(f: File) {
    setBusy(true); setErr(''); setMsg(`正在准备 ${f.name}…`)
    try {
      const r: any = await api.ingestPrepare(f)
      if (r.kind === 'text') {
        changeText(String(r.text || ''))
        setSourcePages([]); setSourceDir(''); setSourceJob(r.job_id || '')
        setMsg(`已读入 ${r.chars || 0} 字（任务 ${r.job_id}）—— 核对后点「解析成题」`)
        setBusy(false)
        api.ingestJobs().then((d: any) => setRecentJobs(d.items || [])).catch(() => {})
        return
      }
      if (r.kind === 'pdf' && r.pdf_b64) {
        setSourcePages(r.pages || []); setSourceDir(r.page_dir || ''); setSourceJob(r.job_id || '')
        const bin = atob(String(r.pdf_b64))
        const arr = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
        const pdf = new File([arr], f.name.replace(/\.docx$/i, '.pdf'),
                             { type: 'application/pdf' })
        setMsg(`已准备 PDF（任务 ${r.job_id}），开始本地读图…`)
        setBusy(false)
        api.ingestJobs().then((d: any) => setRecentJobs(d.items || [])).catch(() => {})
        ocrFile(pdf, r.job_id || '')   // 由 ocrFile 接管 busy/错误
        return
      }
      setErr('这个文件没有可读内容'); setBusy(false)
    } catch (e) {
      setErr(String((e as any)?.message || e)); setBusy(false)
    }
  }

  /** 继续最近任务：文本直接载入；PDF 重新走本地读图（原任务不重复转换）。 */
  async function resumeJob(job: any) {
    setBusy(true); setErr(''); setMsg(`正在打开 ${job.source_name || job.id}…`)
    try {
      const r: any = await api.ingestJob(job.id)
      setSourcePages(r.pages || []); setSourceDir(r.page_dir || ''); setSourceJob(job.id)
      if (r.kind === 'text') {
        changeText(String(r.text || ''))
        setMsg(`已继续「${job.source_name}」（任务 ${job.id}）`)
        setBusy(false)
        return
      }
      if (r.kind === 'pdf' && r.pdf_b64) {
        if (r.ocr_text) {
          changeText(String(r.ocr_text))
          setMsg(`已载入缓存的识别结果（任务 ${job.id}）—— 核对后点「解析成题」`)
          setBusy(false)
          return
        }
        const bin = atob(String(r.pdf_b64))
        const arr = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
        const pdf = new File([arr], `${job.source_name || 'source'}.pdf`,
                             { type: 'application/pdf' })
        setMsg(`已打开「${job.source_name}」，开始本地读图…`)
        setBusy(false)
        ocrFile(pdf, job.id)
        return
      }
      setErr('这个任务没有可继续的文本/PDF'); setBusy(false)
    } catch (e) {
      setErr(String((e as any)?.message || e)); setBusy(false)
    }
  }

  /** 手动清理旧任务：只保留最近 50 个源文件/派生件。 */
  async function pruneJobs() {
    if (!window.confirm('只保留最近 50 个录入任务？更早的源文件、源页和 OCR 缓存会删除。')) return
    try {
      const r: any = await api.ingestJobsPrune(50)
      const d: any = await api.ingestJobs()
      setRecentJobs(d.items || [])
      setMsg(`已清理 ${r.removed?.length || 0} 个旧任务`)
    } catch (e) { setErr(String((e as any)?.message || e)) }
  }

  /* ══ AI 读整份资料 ══════════════════════════════════════════════════
     和「大模型读图」的区别：那个一次读一页、跑在本地；这个把整份 PDF
     拆页后交给 DeepSeek，几分钟读完，回来的是**一整份源材料**。
     结果仍然只填进输入框——核对、勾选、入库一步都不少。 */

  const aiRefresh = async () => {
    try {
      const cfg: any = await api.aiStatus()
      setAiCfg(cfg)
      setAiModel(String(cfg?.model || ''))
      setAiBase(String(cfg?.base_url || ''))
    } catch (e) {
      // 状态接口失败时不能永远停在「正在读取配置」；退回未配置，
      // 让人还能打开设置、填 Key、点「保存并测试」。
      setAiCfg((cur: any) => cur || { ok: false, configured: false })
      setAiErr(`读取 AI 配置失败：${String((e as any)?.message || e)}；仍可在下面重新填写 Key`)
    }
  }
  useEffect(() => { void aiRefresh() }, [])
  useEffect(() => {
    api.ingestJobs().then((d: any) => setRecentJobs(d.items || [])).catch(() => {})
  }, [])

  const aiSaveKey = async () => {
    setAiErr(''); setAiTesting(true)
    try {
      const body: any = { api_key: aiKey.trim() || undefined }
      if (aiModel.trim()) body.model = aiModel.trim()
      if (aiBase.trim()) body.base_url = aiBase.trim()
      const cfg: any = await api.aiConfig(body)
      setAiCfg(cfg); setAiKey('')
      setAiModel(String(cfg?.model || ''))
      setAiBase(String(cfg?.base_url || ''))
      if (!cfg?.configured) { setAiErr('还没填 Key'); return }
      const t: any = await api.aiTest()
      setAiSetup(false)
      setAiNote(`连接正常（${t.model}，${t.ms} 毫秒）—— 现在可以拖资料进来了`)
    } catch (e) {
      setAiErr(String((e as any)?.message || e))
    } finally { setAiTesting(false) }
  }

  const aiClearKey = async () => {
    if (!window.confirm('清掉这台电脑上保存的 API Key？')) return
    try {
      const cfg: any = await api.aiConfig({ api_key: '' })
      setAiCfg(cfg); setAiNote('已清掉 Key')
    } catch (e) { setAiErr(String((e as any)?.message || e)) }
  }

  /** 把一次 AI 结果里的逐题核对/覆盖/用量展开成一句人话。 */
  const aiResultNote = (res: any, cancelled: boolean): string => {
    const st = res.stats || {}
    const cov = res.coverage || {}
    const pendNos = (res.pending || []).map((p: any) => p?.no).filter(Boolean).slice(0, 8)
    const parts = [cancelled
      ? `已取消：保留已核对 ${st.ok || 0} 道`
      : `读完 ${st.pages || 0} 页：${st.ok || 0} 道通过第二遍核对`]
    if (aiAns.length) parts.unshift(`答案册：${aiAns.map((a) => a.name).join('、')}`)
    if (cov.expected) {
      let c = `覆盖 ${cov.transcribed || 0}/${cov.expected}`
      if (cov.flawed?.length) c += `；答案册标错 ${cov.flawed.length} 道（第 ${cov.flawed.join('、')} 题）`
      if (cov.missing?.length) c += `；缺转录 ${cov.missing.length} 道（第 ${cov.missing.join('、')} 题）`
      if (cov.uncertain?.length) c += `；核对未过 ${cov.uncertain.length} 道`
      parts.push(c)
    }
    if (st.pending) {
      parts.push(`${st.pending} 道未入库`
        + (pendNos.length ? `（第 ${pendNos.join('、')} 题）` : ''))
    }
    if (st.usage?.total_tokens) {
      parts.push(`用量 ${st.usage.total_tokens} tokens，约 ¥${Number(st.cost_cny || 0).toFixed(3)}`)
    }
    if (res.warnings?.length) parts.push(`${res.warnings.length} 条提示`)
    if (res.problems?.length) parts.push(`${res.problems.length} 处图/组装问题`)
    return parts.join('；')
  }

  const setAiResult = (res: any, sourceName = '') => {
    const cards: Record<number, any> = {}
    for (const it of (res.items || [])) {
      if (it && typeof it.block === 'number') cards[it.block] = it
    }
    setAiCards(cards)
    setAiPageDir(String(res.page_dir || ''))
    // AI 已经读出卷名时，直接填进「出处 / 地区 / 年份」，不要再让用户对着一堆默认值。
    const p = (res.params && typeof res.params === 'object') ? res.params : {}
    let title = String(p.label || res.title || '').trim()
    if (["", "资料", "数学", "数学试题", "数学试卷", "试卷", "试题"].includes(title)) {
      title = String(sourceName || '').split(/\s+/)[0].replace(/\.pdf$/i, '').trim()
    }
    const src = String(sourceName || '').trim()
    const ym = (String(p.year || '') || (title.match(/(?:19|20)\d{2}/) || [])
      || src.match(/(?:19|20)\d{2}/) || [])[0] || year
    const stem = src.replace(/\.[^.]+$/, '').replace(/^数学[_-]?/, '')
    const regionGuess = stem.split(/20\d{2}/)[0].replace(/[_-]+/g, ' ').trim()
    const bookName = title.replace(/\s*数学(?:试题|试卷|试题卷|试卷).*$/, '').trim()
    const nextBook = String(p.book || '').trim()
      || ((!book.trim() || book === DEFAULT_BOOK) ? (bookName || title || book) : book)
    const nextLabel = title || label
    const nextRegion = String(p.region || '').trim() || (region.trim() ? region : regionGuess)
    if (ym) setYear(ym)
    if (title) {
      setLabel(nextLabel)
      setBook(nextBook)
      if (!region.trim() && regionGuess) setRegion(nextRegion)
    }
    const fields = { book: nextBook, label: nextLabel, year: ym, region: nextRegion }
    aiSourceFields.current = fields
    setAiReport({ ...res, source_label: nextLabel, source_book: nextBook,
                  source_region: nextRegion })
    return fields
  }

  /** 打开历史读取：不用重新上传，也不重新计费；直接恢复上次结果。 */
  const loadAiHistory = async (id: string) => {
    if (aiBusy) { setAiErr('上一份还在读，等它结束再打开历史'); return }
    setAiBusy(true); setAiErr(''); setAiNote('')
    setAiProg({ done: 0, total: 0, msg: '正在恢复上次结果…' })
    try {
      const d: any = await api.aiHistoryItem(id)
      if (!d?.result) {
        setAiErr('这条历史没有保存结果（当时可能失败了），请重新读取')
        setAiBusy(false); setAiProg(null); return
      }
      const res = d.result
      setSrcDir(String(res.crop_dir || ''))
      setAiResult(res, String(d.manifest?.name || ''))
      changeText(String(res.latex || ''))
      setAiNote(aiResultNote(res, false))
      setAiBusy(false); setAiProg(null)
      if (res.latex) void dryRun(String(res.latex), String(res.crop_dir || ''),
        aiSourceFields.current)
    } catch (e) {
      setAiErr(String((e as any)?.message || e)); setAiBusy(false); setAiProg(null)
    }
  }

  const aiWatch = async (id: string, seq: number) => {
    for (let i = 0; i < 3600; i++) {
      await new Promise((r) => setTimeout(r, 1200))
      if (seq !== aiSeq.current) return
      let j: any
      try { j = await api.aiJob(id) }
      catch (e) {
        if (seq === aiSeq.current) {
          setAiErr(String((e as any)?.message || e)); setAiBusy(false)
          setAiCancelling(false)
        }
        return
      }
      if (seq !== aiSeq.current) return
      setAiProg({ done: j.done || 0, total: j.total || 0, msg: j.msg || '',
                  sec: j.elapsed || 0 })
      if (j.state === 'cancelling') {
        // 取消请求已受理：继续轮询，等线程把在飞的批次收尾。
        setAiCancelling(true)
        continue
      }
      if (j.state === 'cancelled') {
        const res = j.result || {}
        if (res.latex) {
          setSrcDir(res.crop_dir || '')
          setAiResult(res, aiSourceName.current)
          changeText(res.latex)
          setAiNote(aiResultNote(res, true))
          void dryRun(res.latex, res.crop_dir || '', aiSourceFields.current)
        } else {
          setAiResult(res, aiSourceName.current)
          setAiNote(aiResultNote(res, true))
        }
        setAiBusy(false); setAiProg(null); setAiCancelling(false); setAiJobId('')
        return
      }
      if (j.state === 'done') {
        const res = j.result || {}
        setSrcDir(res.crop_dir || '')
        setAiResult(res, aiSourceName.current)
        changeText(res.latex || '')
        setAiNote(aiResultNote(res, false))
        setAiBusy(false); setAiProg(null); setAiCancelling(false); setAiJobId('')
        // 自动解析：让用户直接看到题卡，少点一次
        if (res.latex) void dryRun(res.latex, res.crop_dir || '', aiSourceFields.current)
        return
      }
      if (j.state === 'error') {
        setAiErr(j.error || '读失败了'); setAiBusy(false); setAiProg(null)
        setAiCancelling(false); setAiJobId('')
        return
      }
    }
    setAiErr('等了太久还没读完 —— 关掉重试，或把资料拆小（一次最多 14 页）')
    setAiBusy(false); setAiCancelling(false)
  }

  /** 取消：不再发新请求；已读的批次保留，已经在飞的请求仍会计费。 */
  const aiCancel = async () => {
    if (!aiJobId || aiCancelling) return
    if (!window.confirm('取消这次读题？\n\n'
      + '一次请求读完，取消后这次不会产出题卡；已发出的请求收不回来，仍会计费。')) return
    setAiCancelling(true)
    setAiProg((p) => (p ? { ...p, msg: '正在取消…' } : p))
    try { await api.aiCancel(aiJobId) }
    catch (e) {
      setAiErr(String((e as any)?.message || e)); setAiCancelling(false)
    }
  }

  const aiRunFiles = async (files: File[], fillSolutions = false) => {
    setAiErr(''); setAiNote('')
    if (aiBusy) {
      setAiErr('上一份还在读，等它读完再换（同时开两个任务会重复计费）')
      return
    }
    if (!files.length) { setAiErr('先选至少一份试题 PDF / 图片'); return }
    for (const f of files) {
      const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf'
      const isImg = f.type.startsWith('image/')
      if (!isPdf && !isImg) {
        setAiErr(`「${f.name}」不是 PDF / 图片；Word 请先另存为 PDF。`)
        return
      }
      if (f.size > 200 * 1024 * 1024) {
        setAiErr(`「${f.name}」超过 200 MB，请先拆分或压缩。`)
        return
      }
    }
    aiSourceName.current = files.map((f) => f.name).join(' ')
    const seq = ++aiSeq.current
    setAiJobId(''); setAiCancelling(false)
    setAiCards({}); setAiPageDir(''); setPageView(null); setAiReport(null)
    setAiBusy(true); setAiProg({ done: 0, total: 0, msg: '正在读取文件…' })
    const read = (f: File) => new Promise<string>((resolve, reject) => {
      const r = new FileReader()
      r.onload = () => resolve(String(r.result || '').split(',')[1] || '')
      r.onerror = () => reject(new Error(`读不出「${f.name}」`))
      r.readAsDataURL(f)
    })
    try {
      const parts = await Promise.all(files.map(async (f) => ({
        name: f.name, data: await read(f),
      })))
      if (seq !== aiSeq.current) return
      const answers = aiAns.map((a) => ({ name: a.name, data: a.b64 }))
      const j: any = await api.aiRunFiles(parts, answers, fillSolutions)
      if (seq !== aiSeq.current) {
        // 上传途中录入页被关了/换了文件：任务可能刚好开出来，顺手取消，
        // 否则它会继续读、继续计费，而界面已经拿不回这个 job id。
        if (j?.job) void api.aiCancel(j.job).catch(() => { /* 可能已结束 */ })
        return
      }
      setAiJobId(j.job || '')
      setAiProg({ done: 0, total: 0, msg: '排队中…' })
      await aiWatch(j.job, seq)
    } catch (e) {
      if (seq === aiSeq.current) {
        setAiErr(String((e as any)?.message || e)); setAiBusy(false); setAiProg(null)
      }
    }
  }

  const yNum = () => {
    const n = Number(year)
    return Number.isFinite(n) && n > 0 ? n : null
  }
  const badKeyPart = (v: string) => /[\/#]/.test(v)
  const yearBad = !!year.trim() && !/^(19|20)\d{2}$/.test(year.trim())
  // 来源/出处里的 /、# 只影响 key 分隔；后端 `_auto_key` 会自动换成全角，
  // 原文 meta 不变。这里只提示，不再拦住录入（地区字段本来就不进 key）。
  const keyNeedsSanitize = badKeyPart(book) || badKeyPart(label)
  const sourceCheck = () => {
    if (yearBad) {
      setErr('年份请填 4 位数字（如 2026），或留空')
      return false
    }
    const badCardYear = Object.values(edits).some(
      (e) => !!e.year.trim() && !/^(19|20)\d{2}$/.test(e.year.trim()))
    if (badCardYear) {
      setErr('单题年份请填 4 位数字（如 2026），或留空')
      return false
    }
    return true
  }

  // 草稿自动保存：至少保证关掉/刷新后材料还在。卡片勾选等审阅态不存，
  // 因为重新解析才拿得到 block；找回材料已经是最大的一步。
  useEffect(() => {
    const t = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT_KEY, JSON.stringify({
          text, book, label, year, region, srcDir, autoTag, backfill, nearThreshold,
        }))
      } catch { /* quota / privacy mode：草稿失败不影响录入 */ }
    }, 300)
    return () => clearTimeout(t)
  }, [text, book, label, year, region, srcDir, autoTag, backfill, nearThreshold])

  const closeSafely = () => {
    const aiRunning = aiBusy
    if (aiRunning && !window.confirm(
      '这次 AI 读题还在跑（或正在上传）。关闭会同时取消它（已读到的结果不会带回界面），'
      + '已经发出去的请求仍会计费。仍要关闭？')) return
    if (text.trim() && !report
      && !window.confirm('关闭录入？材料已自动保存为本地草稿，下次打开可恢复。')) return
    // 两个确认都过了才真正取消/关页面：否则用户点错「关闭」又取消，
    // 任务已经被取消了，界面却还开着。
    if (aiRunning && aiJobId) {
      void api.aiCancel(aiJobId).catch(() => { /* 任务可能刚好结束 */ })
    }
    aiSeq.current += 1
    onClose()
  }

  const clearDraft = () => {
    try { localStorage.removeItem(DRAFT_KEY) } catch { /* ignore */ }
    setText(''); setBook(DEFAULT_BOOK); setLabel(DEFAULT_LABEL); setYear(DEFAULT_YEAR)
    setRegion(''); setSrcDir(''); setAutoTag(false)
    setAiAns([]); setAiNote(''); setAiErr('')
    setAiCards({}); setAiPageDir(''); setPageView(null); setAiReport(null)
    setRestored(false)
    resetReview()
  }

  const baseBody = (over: Record<string, any> = {}) => ({
    text,
    book: book.trim(),
    label: label.trim(),
    year: yNum(),
    region: region.trim(),
    src_dir: srcDir.trim(),
    source_no: '', points: '', difficulty: '', qtype: '',
    // 默认手工录入规则；`backfill` 由服务端单独放行“只补空字段”。
    update_existing: backfill, update_force: false,
    backfill,
    near_threshold: Math.min(1, Math.max(0.8, nearThreshold / 100)),
    merge_into: {}, merge_blocks: {},
    ...over,
  })

  const itemOverrides = () => (pv?.items || []).map((it: any) => {
    const e = edits[it.block] || EMPTY
    const o: any = {
      block: it.block,
      pick: !!picks[it.block],
      source_no: e.source_no,
      points: e.points,
      difficulty: e.difficulty,
      qtype: e.qtype,
      point_source: e.point_source,
      tag_model: e.tag_model,
      tagged_at: e.tagged_at,
    }
    // 空 = 沿用左栏全局；**不要发空串**（旧后端会把它当“明确清空”）。
    if (e.label.trim()) o.label = e.label
    if (e.year.trim()) o.year = e.year
    return o
  })

  const body = () => ({ ...baseBody(), items: pv ? itemOverrides() : [] })

  const buildEdits = (d: any, old?: EditMap) => {
    const em: EditMap = {}
    for (const it of d.items) {
      const b = it.block
      const prev = old?.[b]
      em[b] = prev
        ? { ...prev }
        : {
            points: Array.isArray(it.points) ? [...it.points] : [],
            difficulty: it.manual_difficulty || '',
            source_no: String(it.source_no || (b + 1)),
            qtype: '',
            point_source: it.point_source
              || (it.points?.length ? 'manual' : ''),
            tag_model: it.tag_model || '',
            tagged_at: it.tagged_at || '',
            // 多卷材料（>1 个 \title）自动把每道题归到最近的那个出处；
            // 单卷留空，沿用左栏全局出处/年份。
            label: (d.source_titles?.length > 1) ? (it.block_title || '') : '',
            year: (d.source_titles?.length > 1 && it.block_year)
              ? String(it.block_year) : '',
          }
    }
    return em
  }

  const buildPicks = (d: any, old?: PickMap) => {
    const pm: PickMap = {}
    for (const it of d.items) {
      // 普通模式：库里已有/相似 >95% 整题跳过；
      // 补旧题模式：只勾**精确重复**的题（提交时只补空字段，新题一律不新增）。
      const ok = blockingOf(it).length === 0
        && (backfill ? !!it.same_key : (!it.same_key && !it.near_dup))
      // 重新解析时保留人的勾选，但**有硬伤/库内已有的题一定不勾**。
      pm[it.block] = ok ? (old?.[it.block] ?? true) : false
    }
    return pm
  }

  /** 干跑：解析 + 规范化 + 查重 + 校验。**什么都不写。**
   *  如果源材料前几行有 `\title{}`，先把出处/年份填进去；因为 key/查重
   *  都跟出处有关，填完再跑一遍，免得看到的是"空出处"的结果。 */
  /** 干跑。`srcArg` 给文本（AI 刚读回来的），`srcDirArg` 给图片来源目录——
   *  两个都从外面传，是因为 setState 还没生效，直接用会拿到旧值。 */
  const dryRun = async (srcArg?: string, srcDirArg?: string,
    overrides?: { book?: string; label?: string; year?: string; region?: string } | null) => {
    const src = srcArg ?? text
    if (!src.trim()) { setErr('先粘贴题目 LaTeX'); return }
    if (!overrides && !sourceCheck()) return
    const bk = overrides?.book ?? book
    const reg = overrides?.region ?? region
    setBusy(true); setErr(''); setMsg(''); setTagErr('')
    tagSeq.current += 1
    try {
      let lab = overrides?.label ?? label
      let yr = overrides?.year ?? year
      let filled = false
      // **先轻量认标题**，再跑整库查重。否则为了填出处要连跑两遍 preview
      // （一遍空出处、一遍填好出处），29k 道的库上就是白等十几秒。
      const autoLab = !overrides && (!lab.trim() || lab === lastHint.current.title)
      const autoYr = !overrides && (!yr.trim() || yr === String(lastHint.current.year || ''))
      if (autoLab || autoYr) {
        try {
          const h: any = await api.ingestSource(src)
          if (h?.title && autoLab) { lab = h.title; filled = true }
          if (h?.year && autoYr) { yr = String(h.year); filled = true }
          if (filled) { setLabel(lab); setYear(yr) }
          lastHint.current = { title: h?.title || '', year: h?.year || null }
        } catch { /* 提示接口失败不挡主流程 */ }
      }
      const withFields = () => baseBody({
        text: src, src_dir: (srcDirArg ?? srcDir).trim(),
        book: bk.trim(), region: reg.trim(),
        label: lab, year: yr ? Number(yr) : null,
        items: pv ? itemOverrides() : [],
      })
      let d: any = await api.ingestPreview(withFields())
      if (!d || typeof d !== 'object') throw new Error('服务端没有返回解析结果')
      if (d.detail) throw new Error(String(d.detail))
      // 兜底：轻量接口没认出来、但 preview 认出来了（正常不会发生，
      // 两条路都调用 `extract_source_hint`）。
      let more = false
      if (!overrides && d.source_hint?.title
          && lab.trim() !== d.source_hint.title
          && (!lab.trim() || lab === lastHint.current.title)) {
        lab = d.source_hint.title; more = true
      }
      if (!overrides && d.source_hint?.year
          && yr.trim() !== String(d.source_hint.year)
          && (!yr.trim() || yr === String(lastHint.current.year || ''))) {
        yr = String(d.source_hint.year); more = true
      }
      if (more) {
        setLabel(lab); setYear(yr); filled = true
        lastHint.current = { title: d.source_hint?.title || '',
                             year: d.source_hint?.year || null }
        d = await api.ingestPreview(withFields())
      }
      if (filled) setMsg(`已从标题识别出处：${lab}${yr ? `（${yr}）` : ''}；可修改`)
      if (!Array.isArray(d.items)) throw new Error('解析结果里没有题卡')
      setPv(d)
      const em = buildEdits(d, edits)
      const pm = buildPicks(d, picks)
      setEdits(em); setPicks(pm)
      if (autoTag && !ai) {
        const need = d.items.some((it: any) => pm[it.block]
          && !(em[it.block]?.points?.length))
        if (need) void tagItems(d, em, { onlyPicked: true, pickMap: pm })
      }
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setBusy(false) }
  }

  const refreshLlm = async () => {
    try { setLlmStatus(await api.llmStatus()) } catch { /* 状态拿不到不影响录入 */ }
  }
  useEffect(() => { void refreshLlm() }, [])

  const unloadLlm = async (model: string, label: string) => {
    if (!model) return
    if (!window.confirm(`卸载 ${label}？会立即释放它占的内存；下次标注/求解时按需再加载。`)) return
    try {
      await api.llmUnload(model)
      setMsg(`已卸载 ${label}`)
      await refreshLlm()
    } catch (e) {
      setErr(String((e as any)?.message || e))
    }
  }

  /** qwen3.5 预标。`blocks` 给了 = 只标这几道并**覆盖**（卡片上的"AI 标注这题"）；
   *  没给 = 只补选中的空标签（顶栏的"AI 标注空缺"）。 */
  const tagItems = async (d: any, snapshot: EditMap,
                         opts: { blocks?: number[]; onlyPicked?: boolean;
                                 pickMap?: PickMap; model?: string;
                                 mainOnly?: boolean } = {}) => {
    if (!d) return
    const pickMap = opts.pickMap || picks
    const targets = (d.items || []).filter((it: any) => {
      if (!(it.stem || '').trim()) return false
      if (opts.blocks && !opts.blocks.includes(it.block)) return false
      if (opts.onlyPicked && !pickMap[it.block]) return false
      return opts.blocks ? true : !(snapshot[it.block]?.points?.length)
    })
    if (!targets.length) return
    const seq = ++tagSeq.current
    activeTags.current += 1
    setTagging(true); setTagErr('')
    try {
      const tagBody = targets.map((it: any) => ({
        stem: it.stem, options: it.options || [], type: it.type || '',
      }))
      const r: any = ai
        ? await api.aiTag(tagBody, 'senior')
        : await api.ingestTag({ items: tagBody, workers: 4, model: opts.model || '' })
      if (seq !== tagSeq.current) return
      if (!r || typeof r !== 'object') { setTagErr('标注服务没有返回结果'); return }
      if (!r.ok && r.error) { setTagErr(String(r.error)); return }
      setEdits((prev) => {
        const out: EditMap = { ...prev }
        targets.forEach((it: any, i: number) => {
          const got = r.items?.[i]
          if (!got) return
          const b = it.block
          const cur = out[b] || snapshot[b] || { ...EMPTY, source_no: String(b + 1) }
          let gotPts = (got.points || []).filter(
            (p: string) => !pointInfo.size || pointInfo.has(p))
          if (opts.mainOnly) gotPts = gotPts.slice(0, 1)
          const gotDiff = got.difficulty || ''
          const overwrite = !!opts.blocks
          const tagModel = String(r.model || opts.model || '')
          const taggedAt = new Date().toISOString()
          if (gotPts.length && (overwrite || !cur.points.length)) {
            out[b] = {
              ...cur,
              points: gotPts,
              point_source: 'llm',
              tag_model: tagModel,
              tagged_at: taggedAt,
              difficulty: overwrite
                ? (gotDiff || cur.difficulty)
                : (cur.difficulty || gotDiff),
            }
          } else if (gotDiff && (overwrite || !cur.difficulty)) {
            out[b] = { ...cur, difficulty: gotDiff, tag_model: tagModel, tagged_at: taggedAt }
          }
        })
        return out
      })
      setAiMiss((prev) => {
        const next = { ...prev }
        targets.forEach((it: any, i: number) => {
          next[it.block] = !(r.items?.[i]?.points?.length)
        })
        return next
      })
      const n = (r.items || []).filter((x: any) => x.points?.length).length
      if (n) {
        setMsg(`${r.model || 'qwen3.5'} 标好 ${n} 道考点/难度`
          + (r.filled ? `（其中 ${r.filled} 道是补标）` : ''))
      }
      if (r.failed) {
        setTagErr(`${r.failed} 道没认出考点（已留空，宁缺勿错）；可手标或点「AI 标注空缺」重试`)
      }
    } catch (e) {
      if (seq === tagSeq.current) {
        setTagErr(String((e as any)?.message || e))
      }
    } finally {
      activeTags.current = Math.max(0, activeTags.current - 1)
      if (activeTags.current === 0) setTagging(false)
      void refreshLlm()
    }
  }

  /** 卡片内改源码：把整份材料里**这一题块**替换掉，再跑一次完整 preview。
   *  其他卡的勾选/考点/难度按 block 保留（`buildEdits/buildPicks` 会合并）。
   *  校验题数必须不变：如果用户把一段粘成两道题，整批 block 会错位，拒绝保存。 */
  const saveSource = async (b: number, nextArg?: string): Promise<boolean> => {
    if (!pv) return false
    const it = pv.items.find((x: any) => x.block === b)
    if (!it) return false
    const old = String(it.tex || "")
    const next = (nextArg ?? srcEdit[b] ?? old).trim()
    if (!next) { setErr('源码不能为空'); return false }
    if (next === old.trim()) {
      setSrcOpen({ ...srcOpen, [b]: false })
      return false
    }
    // 同一段源码可能在材料里出现多次：按 block 顺序数这是第几次。
    let nth = 0
    for (const x of pv.items) {
      if (x.block < b && x.tex === old) nth += 1
    }
    let pos = -1
    let from = 0
    for (let k = 0; k <= nth; k += 1) {
      pos = text.indexOf(old, from)
      if (pos < 0) break
      from = pos + old.length
    }
    if (pos < 0) {
      setErr('找不到这道题在原材料里的位置，请重新解析后再改')
      return false
    }
    const full = text.slice(0, pos) + next + text.slice(pos + old.length)
    setBusy(true); setErr(''); setMsg('')
    try {
      const d: any = await api.ingestPreview({
        ...baseBody({ text: full }), items: itemOverrides(),
      })
      if (!d || !Array.isArray(d.items)) throw new Error('服务端没有返回解析结果')
      if (d.detail) throw new Error(String(d.detail))
      if (d.count !== pv.count || !d.items.some((x: any) => x.block === b)) {
        throw new Error('这段源码没能恰好解析成一道题（题数变了），没有保存；请检查 question/problem 环境是否配对')
      }
      setText(full)
      setPv(d)
      const em = buildEdits(d, edits)
      const pm = buildPicks(d, picks)
      setEdits(em); setPicks(pm)
      setSrcEdit((prev) => { const n = { ...prev }; delete n[b]; return n })
      setSrcOpen((prev) => ({ ...prev, [b]: false }))
      setAiMiss((prev) => ({ ...prev, [b]: false }))
      setMsg(`已更新第 ${it.source_no || b + 1} 题源码`)
      return true
    } catch (e) {
      setErr(String((e as any)?.message || e))
      return false
    } finally { setBusy(false) }
  }

  /** 按当前 conformance 报错让 DeepSeek 只修这一道题；修完仍走 preview 才应用。 */
  const repairQuestion = async (b: number, instruction = '') => {
    if (!pv || repairing[b]) return
    const it = pv.items.find((x: any) => x.block === b)
    if (!it) return
    const old = String(it.tex || "")
    const current = srcEdit[b] ?? old
    const specReasons = (pv.spec?.after || [])
      .filter((x: any) => x.key === it.key)
      .map((x: any) => `${x.check || '规范'}：${x.why || ''}`.trim())
    const problems = [...new Set([
      ...blockingOf(it),
      ...((Array.isArray(it.problems) ? it.problems : []) as string[]),
      ...specReasons,
    ])]
    setRepairing((prev) => ({ ...prev, [b]: true }))
    setRepairNote((prev) => ({ ...prev, [b]: '' }))
    setErr(''); setMsg('')
    try {
      let r: any
      let label = ''
      if (instruction) {
        // 图片转 TikZ 需要原图，仍走带图的单次能力；文本修复走下面的 agent loop。
        r = await api.aiRepair(current, problems, String(it.source_no || ''),
          instruction, srcDir)
        label = '图片转 TikZ'
        if (r?.unfixable) {
          setRepairNote((prev) => ({ ...prev, [b]: `原卷问题：${r.note || '需人工确认'}` }))
          setMsg('DeepSeek 判断这是原卷内容问题，没有自动改；请改源码确认。')
          return
        }
      } else {
        r = await api.aiRepairAgent({
          tex: current, problems, source_no: String(it.source_no || ''), src_dir: srcDir,
        })
        label = 'DeepSeek agent'
        if (!r?.passed) {
          const errs = Array.isArray(r?.errors) ? r.errors : []
          setRepairNote((prev) => ({ ...prev,
            [b]: `${r?.note || '多轮修复未通过'}${errs.length ? '：' + errs.slice(0, 4).join('；') : ''}` }))
          setMsg(`DeepSeek agent 跑了 ${r?.steps?.length || 0} 步，仍未通过单题检查；源码未改动。`)
          return
        }
      }
      const fixed = String(r?.tex || '').trim()
      if (!fixed) { setRepairNote((prev) => ({ ...prev, [b]: 'DeepSeek 没有返回修复结果' })); return }
      // agent / 图片转换都必须再过一次本地单题检查。
      const checked: any = await api.ingestPreview({
        ...baseBody({ text: fixed }), items: [],
      })
      if (!checked || !Array.isArray(checked.items) || checked.items.length !== 1) {
        setRepairNote((prev) => ({ ...prev,
          [b]: '修复后的源码不能恰好解析成一道题，已拒绝应用' }))
        return
      }
      const one = checked.items[0]
      const still = blockingOf(one)
      if (still.length) {
        setRepairNote((prev) => ({ ...prev,
          [b]: `修完后仍有 ${still.length} 条未过：${still.slice(0, 4).join('；')}` }))
        setMsg('修复结果未通过单题检查，已拒绝应用；没有改动当前源码。')
        return
      }
      const ok = await saveSource(b, fixed)
      if (ok) {
        setMsg(`${label} 已修复第 ${it.source_no || b + 1} 题${r?.note ? `（${r.note}）` : ''}`)
      } else {
        setRepairNote((prev) => ({ ...prev, [b]: '单题检查通过，但写回整卷预览时没有应用成功' }))
      }
    } catch (e) {
      setRepairNote((prev) => ({ ...prev, [b]: String((e as any)?.message || e) }))
      setErr(String((e as any)?.message || e))
    } finally {
      setRepairing((prev) => {
        const n = { ...prev }; delete n[b]; return n
      })
    }
  }

  const isDup = (it: any) => backfill
    ? !it?.same_key
    : (!!it?.same_key || !!it?.near_dup)
  const visibleItems = pv ? pv.items.filter((it: any) => {
    if (reviewFilter === 'new') return !isDup(it)
    if (reviewFilter === 'missing') return !(edits[it.block]?.points?.length)
    if (reviewFilter === 'suspect') return !!(it.dups?.length)
    if (reviewFilter === 'blocked') return blockingOf(it).length > 0
    return true
  }) : []
  const filterCounts = pv ? {
    all: pv.items.length,
    new: pv.items.filter((it: any) => !isDup(it)).length,
    missing: pv.items.filter((it: any) => !(edits[it.block]?.points?.length)).length,
    suspect: pv.items.filter((it: any) => it.dups?.length).length,
    blocked: pv.items.filter((it: any) => blockingOf(it).length > 0).length,
  } : { all: 0, new: 0, missing: 0, suspect: 0, blocked: 0 }

  const selected = pv ? pv.items.filter((it: any) => picks[it.block]) : []
  const badSelected = selected.filter((it: any) => blockingOf(it).length > 0)
  const missingSelected = selected.flatMap((it: any) => it.missing_images || [])
  const emptyTagCount = pv
    ? pv.items.filter((it: any) => picks[it.block]
        && !(edits[it.block]?.points?.length)).length
    : 0

  const toggleAll = (on: boolean) => {
    if (!pv) return
    const next: PickMap = { ...picks }
    for (const it of pv.items) {
      // 普通模式库内已有/高度相似不勾；补旧题模式只勾精确重复。
      next[it.block] = on && blockingOf(it).length === 0
        && (backfill ? !!it.same_key : (!it.same_key && !it.near_dup))
    }
    setPicks(next)
  }

  const fillHint = () => {
    if (pv?.source_hint?.title) setLabel(pv.source_hint.title)
    if (pv?.source_hint?.year) setYear(String(pv.source_hint.year))
    lastHint.current = { title: pv?.source_hint?.title || '',
                         year: pv?.source_hint?.year || null }
  }

  const applyBatch = (kind: 'type' | 'diff' | 'points') => {
    if (!selected.length) { setErr('先勾选要批量改的题'); return }
    setEdits((prev) => {
      const out: EditMap = { ...prev }
      for (const it of selected) {
        const b = it.block
        const e = out[b] || { ...EMPTY, source_no: String(b + 1) }
        if (kind === 'type') out[b] = { ...e, qtype: batchType }
        if (kind === 'diff') out[b] = { ...e, difficulty: batchDiff }
        if (kind === 'points') {
          const add = batchPts.filter((p) => !e.points.includes(p))
          const pts = [...e.points, ...add]
          out[b] = { ...e, points: pts, point_source: pts.length ? 'manual' : '' }
        }
      }
      return out
    })
    setErr('')
    setMsg(kind === 'type' ? `已给 ${selected.length} 道设题型`
      : kind === 'diff' ? `已给 ${selected.length} 道设难度`
        : `已给 ${selected.length} 道加考点`)
  }

  // 键盘审阅：j/k 上下、空格勾选、e 展开。输入框里不抢键。
  useEffect(() => {
    if (!pv) return
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'
        || t.tagName === 'SELECT' || t.isContentEditable)) return
      if (!visibleItems.length) return
      const cur = visibleItems.findIndex((it: any) => it.block === activeCard)
      if (e.key === 'j' || e.key === 'k') {
        e.preventDefault()
        const n = e.key === 'j'
          ? (cur < 0 ? 0 : Math.min(visibleItems.length - 1, cur + 1))
          : (cur <= 0 ? 0 : cur - 1)
        const it = visibleItems[n]
        setActiveCard(it.block)
        cardRefs.current[it.block]?.scrollIntoView({ block: 'nearest' })
      } else if (e.key === ' ' && cur >= 0) {
        const it = visibleItems[cur]
        if (!blockingOf(it).length && !isDup(it)) {
          e.preventDefault()
          setPicks({ ...picks, [it.block]: !picks[it.block] })
        }
      } else if (e.key === 'e' && cur >= 0) {
        const it = visibleItems[cur]
        e.preventDefault()
        const open = expanded[it.block] !== false
        setExpanded({ ...expanded, [it.block]: !open })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pv, visibleItems, activeCard, picks, expanded])

  /** 单题入库：只提交这一道。整批校验/整批拒绝的路径之外，给一个
   *  “这道已经确认好了，先落它”的出口；其他卡不受影响。 */
  const commitOne = async (b: number) => {
    if (!pv || !sourceCheck()) return
    const it = pv.items.find((x: any) => x.block === b)
    if (!it || blockingOf(it).length || isDup(it)) return
    setBusy(true); setErr(''); setMsg('')
    try {
      const items = itemOverrides().map((o: any) => ({ ...o, pick: o.block === b }))
      const d: any = await api.ingestCommit({ ...baseBody(), items })
      if (!d || !d.ok) throw new Error(String(d?.error || '入库失败'))
      const nNew = (d.added || []).length
      const nUp = (d.upgraded || []).length
      if (!nNew && !nUp) {
        throw new Error(String(d.skipped?.[0]?.reason || '没有新增/可补字段（可能库里已有）'))
      }
      setPv((prev: any) => prev ? ({
        ...prev,
        count: Math.max(0, (prev.count || 1) - 1),
        items: prev.items.filter((x: any) => x.block !== b),
        dup: prev.dup ? {
          ...prev.dup,
          new: Math.max(0, (prev.dup.new || 1) - (nNew ? 1 : 0)),
          update: Math.max(0, (prev.dup.update || 0) - (nUp ? 1 : 0)),
        } : prev.dup,
      }) : prev)
      setPicks((prev) => { const n = { ...prev }; delete n[b]; return n })
      setEdits((prev) => { const n = { ...prev }; delete n[b]; return n })
      setSrcEdit((prev) => { const n = { ...prev }; delete n[b]; return n })
      setSrcOpen((prev) => ({ ...prev, [b]: false }))
      setMsg(backfill
        ? `第 ${it.source_no || b + 1} 题已补标签`
        : `第 ${it.source_no || b + 1} 题已单独入库`)
      onDone()
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setBusy(false) }
  }

  const doCommit = () => {
    if (!pv) { setErr('先解析成题'); return }
    if (!sourceCheck()) return
    if (!selected.length) {
      setErr(backfill
        ? '补旧题模式：没有勾选可补的已有题'
        : (pv.items.some((it: any) => it.same_key || it.near_dup)
          ? '这些题库里都已有或高度相似（>95%）：按规则整题跳过，不新增也不更新'
          : '至少勾选一道题'))
      return
    }
    if (badSelected.length) {
      setErr(`有 ${badSelected.length} 道勾选的题还不能入库：`
        + badSelected.slice(0, 3).map((it: any) => blockingOf(it)[0]).join('；'))
      return
    }
    if (missingSelected.length) {
      setErr(`有 ${new Set(missingSelected).size} 张图缺失，先补图再导入`); return
    }
    setBusy(true); setErr('')
    api.ingestCommit(body())
      .then((d: any) => {
        if (d?.detail || !d?.ok) { setErr(String(d?.detail || d?.error)); return }
        try { localStorage.removeItem(DRAFT_KEY) } catch { /* ignore */ }
        resetReview()
        setText('')
        setReport(d)
        onDone()
      })
      .catch((e) => setErr(String((e as any)?.message || e)))
      .finally(() => setBusy(false))
  }

  const undoReport = async () => {
    if (!report?.added?.length) { setReport(null); return }
    setBusy(true); setErr('')
    try {
      await api.trashBatch(report.added, '试入库后撤回')
      const n = report.added.length
      setReport(null)
      setMsg(`已撤销本次导入：${n} 道移入回收站`)
      onDone()
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setBusy(false) }
  }

  const fixedCount = (pv?.spec?.fixed || [])
    .reduce((n: number, x: any) => n + (x.hits || 0), 0)
  const specAfter = pv?.spec?.after?.length || 0
  const hintTitle = pv?.source_hint?.title || ''
  const hintYear = pv?.source_hint?.year
  /** AI 模式、还没读到东西：先把出处 / 批量 / LaTeX 三块收起来——
   *  小白一打开就看见三组输入框会直接懵。读到内容后自动恢复。 */
  const aiClean = ai && !text.trim()
  const showHint = !!hintTitle && (label.trim() !== hintTitle
    || (!!hintYear && year.trim() !== String(hintYear)))

  return {
    ai,
    facets,
    draft0,
    text,
    setText,
    book,
    setBook,
    label,
    setLabel,
    year,
    setYear,
    region,
    setRegion,
    srcDir,
    setSrcDir,
    autoTag,
    setAutoTag,
    mainOnly,
    setMainOnly,
    llmStatus,
    setLlmStatus,
    nearThreshold,
    setNearThreshold,
    backfill,
    setBackfill,
    restored,
    setRestored,
    pv,
    setPv,
    picks,
    setPicks,
    edits,
    setEdits,
    expanded,
    setExpanded,
    reviewFilter,
    setReviewFilter,
    activeCard,
    setActiveCard,
    cardRefs,
    batchType,
    setBatchType,
    batchDiff,
    setBatchDiff,
    batchPts,
    setBatchPts,
    srcEdit,
    setSrcEdit,
    srcOpen,
    setSrcOpen,
    aiMiss,
    setAiMiss,
    busy,
    setBusy,
    tagging,
    setTagging,
    drag,
    setDrag,
    msg,
    setMsg,
    err,
    setErr,
    tagErr,
    setTagErr,
    report,
    setReport,
    tagSeq,
    activeTags,
    lastHint,
    vlmReady,
    setVlmReady,
    vlmEngine,
    setVlmEngine,
    aiCfg,
    setAiCfg,
    aiSetup,
    setAiSetup,
    aiKey,
    setAiKey,
    aiBusy,
    setAiBusy,
    aiTesting,
    setAiTesting,
    aiProg,
    setAiProg,
    aiAns,
    setAiAns,
    aiErr,
    setAiErr,
    aiNote,
    setAiNote,
    aiJobId,
    setAiJobId,
    aiCancelling,
    setAiCancelling,
    aiCards,
    setAiCards,
    aiReport,
    setAiReport,
    aiPageDir,
    setAiPageDir,
    pageView,
    setPageView,
    sourcePages,
    setSourcePages,
    sourceDir,
    setSourceDir,
    sourceJob,
    setSourceJob,
    recentJobs,
    setRecentJobs,
    aiModel,
    setAiModel,
    aiBase,
    setAiBase,
    aiSeq,
    pointInfo,
    points,
    resetReview,
    changeText,
    readFile,
    ocrFile,
    prepareSource,
    resumeJob,
    pruneJobs,
    aiRefresh,
    aiSaveKey,
    aiClearKey,
    aiResultNote,
    setAiResult,
    aiWatch,
    aiCancel,
    aiRunFiles,
    loadAiHistory,
    yNum,
    badKeyPart,
    yearBad,
    keyNeedsSanitize,
    sourceCheck,
    closeSafely,
    clearDraft,
    baseBody,
    itemOverrides,
    body,
    buildEdits,
    buildPicks,
    dryRun,
    refreshLlm,
    unloadLlm,
    tagItems,
    saveSource,
    repairQuestion,
    repairing,
    repairNote,
    isDup,
    visibleItems,
    filterCounts,
    selected,
    badSelected,
    missingSelected,
    emptyTagCount,
    toggleAll,
    fillHint,
    applyBatch,
    commitOne,
    doCommit,
    undoReport,
    fixedCount,
    specAfter,
    hintTitle,
    hintYear,
    aiClean,
    showHint,
  }
}

export type IngestBag = ReturnType<typeof useIngest>
