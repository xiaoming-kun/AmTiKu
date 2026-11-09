/** 录入抽屉：粘贴 LaTeX → 自动切题 → 逐题确认 → 勾选入库。
 *
 *  这一版是**多题录入**：粘一整份卷子（`\title{…}` + 一串 question/problem），
 *  脚本负责切题、规范化、查重；qwen3.5 只做粗标（考点/难度），人逐题改、
 *  逐题勾，最后才写库——先看清楚再落盘。
 *
 *  几个刻意的约束：
 *   - **干跑什么都不写**；写库仍走 `/api/ingest/commit` 那一条唯一管线。
 *   - 出处从源材料前几行的 `\title{…}` 认，填进输入框，**人还能改**。
 *   - 每道题的状态/标签按 `block` 对回源材料的题块——改出处后 key 会变，
 *     块下标不会变。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, Check, FileText, KeyRound, Loader2, Play, Sparkles, Undo2, Upload, X,
} from 'lucide-react'
import { renderBlocks } from '@/lib/render'
import { api } from '@/lib/api'
import { Flags, Report, INGEST_SAMPLE, CloseBtn } from '@/app/ui'
import { PointPicker, DiffPills } from '@/app/IngestControls'
import { SourceStage, ReviewStage, CommitBar } from '@/app/ingest/IngestStages'

/** 输入框的统一样式（左侧「源材料」一栏里共用）。 */
const FIELD = `h-[32px] rounded-lg border border-border bg-bg px-2.5 text-[12.5px] outline-none
               transition-[border-color,box-shadow] duration-150 placeholder:text-ink-faint
               focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]`
/** 小节标题（抽屉里所有分组标题统一走这一个）。 */
const LABEL = 'text-[11px] font-semibold tracking-[0.08em] text-ink-faint'
/** 小号次按钮。 */
const MINI = `press inline-flex items-center gap-1 rounded-md border border-border bg-surface
              px-1.5 py-[2px] text-[10.5px] text-ink-soft hover:border-brand-line
              hover:text-brand-ink disabled:opacity-40`

const QTYPE_OPTS: [string, string][] = [
  ['', '自动识别'], ['single_choice', '单选题'], ['multi_choice', '多选题'],
  ['fill_in_blank', '填空题'], ['detailed_answer', '解答题'],
]
const QTYPE_LABEL: Record<string, string> = {
  single_choice: '单选题', multi_choice: '多选题',
  fill_in_blank: '填空题', detailed_answer: '解答题',
}
const STARS: Record<string, number> = { 简单题: 1, 中档题: 2, 难题: 3 }
/** 手工录入的默认出处 / 年份：多数材料来自「精选模拟题」，年份 2026。
 *  只做预填，人随时能改；有 `\title{…}` 时作为**建议**，点「填入出处」采用。 */
const DEFAULT_BOOK = '2026精选模拟题'
const DEFAULT_LABEL = '精选模拟题'
const DEFAULT_YEAR = '2026' 

type Edit = {
  points: string[]
  difficulty: string   // '' = 跟着主考点派生
  source_no: string
  qtype: string        // '' = 自动识别
  point_source: string
  tag_model: string     // AI 标注用的模型（空 = 手填）
  tagged_at: string
  label: string         // 单题出处；空 = 沿用全局
  year: string          // 单题年份；空 = 沿用全局
}
type EditMap = Record<number, Edit>
type PickMap = Record<number, boolean>

const EMPTY: Edit = {
  points: [], difficulty: '', source_no: '', qtype: '',
  point_source: '', tag_model: '', tagged_at: '', label: '', year: '',
}

/** 这道题**为什么不能入库**。后端在 `preview.items[].blocking` 里已经算好；
 *  前端再兜一层 flags，防老响应没带 blocking 时误放行。 */
function blockingOf(it: any): string[] {
  const out: string[] = [...(it?.blocking || [])]
  if (it?.flags && !it.flags['答案']) out.push('缺答案')
  if (it?.flags && !it.flags['解析']) out.push('缺解析')
  // AI 读出来的图没画好/没裁好：源码里会有「【图：…请补图】」占位。
  // 服务端 `_structure_errors` 也会拦，这里提前取消勾选，免得用户漏看。
  const src = String(it?.tex || '')
  if (src.includes('【图：') || src.includes('请补图') || src.includes('请手工补')) {
    out.push('缺图待补')
  }
  return [...new Set(out)]
}

const DRAFT_KEY = 'amtiku.ingest.draft.v1'

function loadDraft(): any {
  try {
    if (typeof localStorage === 'undefined') return {}
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}') || {}
  } catch { return {} }
}

export default function IngestDrawer({ onClose, onDone, facets, closing, ai = false }: {
  onClose: () => void; onDone: () => void; facets: any
  /** 正在播退场动画（父组件用 `useUnmount` 控制）。 */
  closing?: boolean
  /** **大模型录题**模式：左栏第一屏只放"选一份资料"，
   *  出题之后自动切回和「录入题目」完全一样的逐题确认界面（同一套代码）。 */
  ai?: boolean
}) {
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
  const [aiAns, setAiAns] = useState<{ name: string; b64: string } | null>(null)
  const [aiErr, setAiErr] = useState('')
  const [aiNote, setAiNote] = useState('')
  /** 后台任务 id / 是否已点取消。取消接口只发一次，状态靠轮询推进。 */
  const [aiJobId, setAiJobId] = useState('')
  const [aiCancelling, setAiCancelling] = useState(false)
  /** AI 结果的逐题核对元数据：block → {pages, answer_pages, answer_quote, ...} */
  const [aiCards, setAiCards] = useState<Record<number, any>>({})
  const [aiPageDir, setAiPageDir] = useState('')
  const [pageView, setPageView] = useState<{ dir: string; name: string; title: string } | null>(null)
  /** 最近任务的源页：准备/继续后显示，点开用现有 pageView 看原页。 */
  const [sourcePages, setSourcePages] = useState<string[]>([])
  const [sourceDir, setSourceDir] = useState('')
  const [sourceJob, setSourceJob] = useState('')
  const [recentJobs, setRecentJobs] = useState<any[]>([])
  /** 高级设置：模型 / 接口地址 / 每批页数 / 并发。 */
  const [aiModel, setAiModel] = useState('')
  const [aiBase, setAiBase] = useState('')
  const [aiPages, setAiPages] = useState('')
  const [aiWorkers, setAiWorkers] = useState('')
  /** 任务序号：关掉抽屉/换文件时，旧轮询的结果一律丢掉。 */
  const aiSeq = useRef(0)

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
      setAiPages(String(cfg?.pages_per_call || 6))
      setAiWorkers(String(cfg?.workers || 2))
    } catch { /* 状态拿不到不挡录入 */ }
  }
  useEffect(() => { void aiRefresh() }, [])
  useEffect(() => {
    api.ingestJobs().then((d: any) => setRecentJobs(d.items || [])).catch(() => {})
  }, [])

  const aiSaveKey = async () => {
    setAiErr(''); setAiTesting(true)
    try {
      const pg = Math.round(Number(aiPages))
      const wk = Math.round(Number(aiWorkers))
      if (aiPages.trim() && (!Number.isFinite(pg) || pg < 1 || pg > 12)) {
        setAiErr('每批页数填 1–12'); return
      }
      if (aiWorkers.trim() && (!Number.isFinite(wk) || wk < 1 || wk > 4)) {
        setAiErr('并发填 1–4'); return
      }
      const body: any = { api_key: aiKey.trim() || undefined }
      if (aiModel.trim()) body.model = aiModel.trim()
      if (aiBase.trim()) body.base_url = aiBase.trim()
      if (aiPages.trim()) body.pages_per_call = pg
      if (aiWorkers.trim()) body.workers = wk
      const cfg: any = await api.aiConfig(body)
      setAiCfg(cfg); setAiKey('')
      setAiModel(String(cfg?.model || ''))
      setAiBase(String(cfg?.base_url || ''))
      setAiPages(String(cfg?.pages_per_call || 6))
      setAiWorkers(String(cfg?.workers || 2))
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

  /** 轮询任务。**不设死循环**：最多等 2 小时（100 页也用不了这么久）。 */
  /** 把一次 AI 结果里的逐题核对/覆盖/用量展开成一句人话。 */
  const aiResultNote = (res: any, cancelled: boolean): string => {
    const st = res.stats || {}
    const cov = res.coverage || {}
    const pendNos = (res.pending || []).map((p: any) => p?.no).filter(Boolean).slice(0, 8)
    const parts = [cancelled
      ? `已取消：保留已核对 ${st.ok || 0} 道`
      : `读完 ${st.pages || 0} 页：${st.ok || 0} 道通过第二遍核对`]
    if (aiAns?.name) parts.unshift(`答案册：${aiAns.name}`)
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

  const setAiResult = (res: any) => {
    const cards: Record<number, any> = {}
    for (const it of (res.items || [])) {
      if (it && typeof it.block === 'number') cards[it.block] = it
    }
    setAiCards(cards)
    setAiPageDir(String(res.page_dir || ''))
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
          setAiResult(res)
          changeText(res.latex)
          setAiNote(aiResultNote(res, true))
          void dryRun(res.latex, res.crop_dir || '')
        } else {
          setAiResult(res)
          setAiNote(aiResultNote(res, true))
        }
        setAiBusy(false); setAiProg(null); setAiCancelling(false); setAiJobId('')
        return
      }
      if (j.state === 'done') {
        const res = j.result || {}
        setSrcDir(res.crop_dir || '')
        setAiResult(res)
        changeText(res.latex || '')
        setAiNote(aiResultNote(res, false))
        setAiBusy(false); setAiProg(null); setAiCancelling(false); setAiJobId('')
        // 自动解析：让用户直接看到题卡，少点一次
        if (res.latex) void dryRun(res.latex, res.crop_dir || '')
        return
      }
      if (j.state === 'error') {
        setAiErr(j.error || '读失败了'); setAiBusy(false); setAiProg(null)
        setAiCancelling(false); setAiJobId('')
        return
      }
    }
    setAiErr('等了太久还没读完 —— 关掉重试，或把「每批页数」调小')
    setAiBusy(false); setAiCancelling(false)
  }

  /** 取消：不再发新请求；已读的批次保留，已经在飞的请求仍会计费。 */
  const aiCancel = async () => {
    if (!aiJobId || aiCancelling) return
    if (!window.confirm('取消这次读题？\n\n'
      + '已读到的题会保留；已经发给 DeepSeek 的请求收不回来，仍会计费。')) return
    setAiCancelling(true)
    setAiProg((p) => (p ? { ...p, msg: '正在取消…' } : p))
    try { await api.aiCancel(aiJobId) }
    catch (e) {
      setAiErr(String((e as any)?.message || e)); setAiCancelling(false)
    }
  }

  const aiRunFile = (f: File) => {
    setAiErr(''); setAiNote('')
    if (aiBusy) {
      setAiErr('上一份还在读，等它读完再换（同时开两个任务会重复计费）')
      return
    }
    const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf'
    const isImg = f.type.startsWith('image/')
    if (!isPdf && !isImg) {
      setAiErr('AI 整份读只吃 PDF 和图片；Word 可直接拖到上方输入框，会先转 PDF 再本地读图')
      return
    }
    // **换卷必须清掉旧答案册**。否则模型会把上一份卷子的答案按题号抄到
    // 这一份上，answer_quote 还是题号，unverified=0，界面看不出错。
    if (aiAns) {
      const keep = window.confirm(
        `这次要带上答案 / 解析《${aiAns.name}》吗？\n\n`
        + '点「确定」= 带上它（同一份卷子重读时用）。\n'
        + '点「取消」= 清掉它。换一份卷子时必须清掉，不然会把上一份的答案按题号抄到这一份上。')
      if (!keep) {
        setAiAns(null)
        setAiErr('已清掉上次的答案 / 解析。请先选这次卷子的答案文件，再选试题。')
        return
      }
    }
    const seq = ++aiSeq.current
    setAiJobId(''); setAiCancelling(false)
    setAiCards({}); setAiPageDir(''); setPageView(null)
    setAiBusy(true); setAiProg({ done: 0, total: 0, msg: '正在上传…' })
    const r = new FileReader()
    r.onload = async () => {
      try {
        if (seq !== aiSeq.current) return
        const b64 = String(r.result || '').split(',')[1] || ''
        const j: any = await api.aiRun(b64, f.name, aiAns?.b64 || '', aiAns?.name || '')
        if (seq !== aiSeq.current) {
          // 上传途中抽屉被关了/换了文件：任务可能刚好开出来，顺手取消，
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
    r.onerror = () => { setAiErr('读不出这个文件'); setAiBusy(false); setAiProg(null) }
    r.readAsDataURL(f)
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
    // 两个确认都过了才真正取消/关抽屉：否则用户点错「关闭」又取消，
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
    setAiAns(null); setAiNote(''); setAiErr('')
    setAiCards({}); setAiPageDir(''); setPageView(null)
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
  const dryRun = async (srcArg?: string, srcDirArg?: string) => {
    const src = srcArg ?? text
    if (!src.trim()) { setErr('先粘贴题目 LaTeX'); return }
    if (!sourceCheck()) return
    setBusy(true); setErr(''); setMsg(''); setTagErr('')
    tagSeq.current += 1
    try {
      let lab = label
      let yr = year
      let filled = false
      // **先轻量认标题**，再跑整库查重。否则为了填出处要连跑两遍 preview
      // （一遍空出处、一遍填好出处），29k 道的库上就是白等十几秒。
      const autoLab = !lab.trim() || lab === lastHint.current.title
      const autoYr = !yr.trim() || yr === String(lastHint.current.year || '')
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
        label: lab, year: yr ? Number(yr) : null,
        items: pv ? itemOverrides() : [],
      })
      let d: any = await api.ingestPreview(withFields())
      if (!d || typeof d !== 'object') throw new Error('服务端没有返回解析结果')
      if (d.detail) throw new Error(String(d.detail))
      // 兜底：轻量接口没认出来、但 preview 认出来了（正常不会发生，
      // 两条路都调用 `extract_source_hint`）。
      let more = false
      if (d.source_hint?.title
          && lab.trim() !== d.source_hint.title
          && (!lab.trim() || lab === lastHint.current.title)) {
        lab = d.source_hint.title; more = true
      }
      if (d.source_hint?.year
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
      const r: any = await api.ingestTag({
        items: targets.map((it: any) => ({
          stem: it.stem, options: it.options || [], type: it.type || '',
        })),
        workers: 4,
        model: opts.model || '',
      })
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
  const saveSource = async (b: number) => {
    if (!pv) return
    const it = pv.items.find((x: any) => x.block === b)
    if (!it) return
    const old = String(it.tex || "")
    const next = (srcEdit[b] ?? old).trim()
    if (!next) { setErr('源码不能为空'); return }
    if (next === old.trim()) {
      setSrcOpen({ ...srcOpen, [b]: false })
      return
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
      return
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
    } catch (e) {
      setErr(String((e as any)?.message || e))
    } finally { setBusy(false) }
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
  const aiHasText = ai && !!text.trim()
  /** 选资料的隐藏 input：大框和"换一份"窄条共用同一个处理函数。 */
  const aiFileInput = (
    <input type="file" accept=".pdf,image/*" className="hidden"
      onChange={(e) => {
        const f = e.target.files?.[0]
        e.currentTarget.value = ''
        if (!f) return
        // **只在"明确没配"时才拦**。`aiCfg` 还没拉回来（null）时照跑不误：
        // 配置的真假以服务端为准，这里拦一下反而会误伤——页面刚打开就选文件，
        // 会看到「先把 API Key 填上」，其实早就配好了。
        if (aiCfg && !aiCfg.configured) {
          setAiSetup(true)
          setAiErr('先把 API Key 填上（只需一次），填好后再选一次文件')
          return
        }
        aiRunFile(f)
      }} />
  )

  const showHint = !!hintTitle && (label.trim() !== hintTitle
    || (!!hintYear && year.trim() !== String(hintYear)))

  return (
    <div className={`${closing ? 'anim-slide-r-out' : 'anim-slide-r'} fixed inset-0 z-50
                    flex flex-col border-l border-border bg-surface
                    shadow-[var(--shadow-pop)]`} onClick={closeSafely}>
      <div className="flex min-h-0 flex-1 flex-col" onClick={(e) => e.stopPropagation()}>
        <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-5 py-3.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-ink">
            {ai ? <Sparkles size={15} /> : <FileText size={15} />}
          </span>
          <span className="shrink-0 text-[15px] font-semibold tracking-tight text-ink">
            {ai ? '大模型录题' : '录入题目'}
          </span>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
            {ai
              ? '整份 PDF / 照片交给 DeepSeek → 逐题核对 → 勾选入库（读的过程中不写库）'
              : '粘贴整份试卷 → 自动切题 → 逐题确认 → 勾选入库（干跑什么都不写）'}
          </span>
          <CloseBtn onClick={closeSafely} className="ml-auto" />
        </header>

        <div className="flex min-h-0 flex-1">
          <SourceStage>

            {/* ── 大模型录题：第一屏只做一件事——选资料 ──
                之前把 AI 藏进「录入题目」的工具条里，小白根本找不到。
                现在从「录题」页的卡片进（没有独立导航项），打开就是这张卡。 */}
            {ai && (
              <section className="shrink-0 rounded-[var(--radius-card)] border border-brand-line
                                  bg-brand-soft/30 p-4">
                <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                  <Sparkles size={15} className="text-brand-ink" />
                  选一份资料，交给大模型读
                </div>
                {aiHasText ? (
                  /* 已经读完一份：大框收成一条，把地方让给下面的出处/源材料 */
                  <label className="mt-2.5 flex cursor-pointer items-center justify-center gap-2
                                    rounded-lg border border-dashed border-brand-line bg-surface
                                    py-2 text-[11.5px] text-ink-soft hover:border-brand
                                    hover:text-brand-ink">
                    <Upload size={12} />换一份资料（把 PDF 拖进来，或点这里）
                    {aiFileInput}
                  </label>
                ) : (
                  <label
                    onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
                    onDragLeave={() => setDrag(false)}
                    onDrop={(e) => {
                      e.preventDefault(); setDrag(false)
                      const f = e.dataTransfer.files?.[0]
                      if (f) aiRunFile(f)
                    }}
                    className={`mt-3 flex h-[168px] cursor-pointer flex-col items-center justify-center
                                gap-2 rounded-xl border-2 border-dashed bg-surface text-center
                                transition-colors ${drag
                                  ? 'border-brand bg-brand-soft'
                                  : 'border-brand-line hover:border-brand hover:bg-brand-soft/40'}`}>
                    {aiBusy ? <Loader2 size={22} className="animate-spin text-brand-ink" />
                      : <Upload size={22} className="text-brand-ink" />}
                    <span className="text-[13.5px] font-semibold text-ink">
                      {aiBusy ? '正在读，别关窗口…' : '把 PDF 拖到这里，或点一下选文件'}
                    </span>
                    <span className="text-[11.5px] leading-relaxed text-ink-faint">
                      照片也行（一页一张）；Word 可直接拖到上方输入框（会先转 PDF 本地读图）
                    </span>
                    <span className="text-[10.5px] text-ink-faint">
                      按页计费：100 页约几毛钱 · 读完自动切到逐题核对
                    </span>
                    {aiFileInput}
                  </label>
                )}
                {/* 答案 / 解析：最常见的形态是**试题一份、答案一份**，所以单列一行。
                    留空也能跑，只是缺答案的题会被拦下（库里要求答案+解析齐全）。 */}
                <div className={`mt-2 flex items-center gap-1.5 rounded-lg border px-2 py-1.5 ${
                  aiAns ? 'border-has-line bg-has-soft/40' : 'border-border bg-surface'}`}>
                  <FileText size={12} className={`shrink-0 ${aiAns ? 'text-has' : 'text-ink-faint'}`} />
                  <span className="shrink-0 text-[11px] font-medium text-ink-soft">答案 / 解析</span>
                  <span className="min-w-0 flex-1 truncate text-[11px] text-ink-faint">
                    {aiAns ? aiAns.name : '另一份文件（只抄不解；不选的话缺答案的题会被拦下）'}
                  </span>
                  {aiAns && (
                    <button onClick={() => setAiAns(null)}
                      className="shrink-0 text-[10.5px] text-ink-faint underline hover:text-warn">
                      清掉
                    </button>
                  )}
                  <label className="press inline-flex h-[22px] shrink-0 cursor-pointer items-center
                                    gap-1 whitespace-nowrap rounded-md border border-border
                                    bg-surface px-1.5 text-[10.5px] text-ink-soft
                                    hover:border-brand-line hover:text-brand-ink">
                    <Upload size={11} />{aiAns ? '换一份' : '选文件'}
                    <input type="file" accept=".pdf,image/*" className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0]
                        e.currentTarget.value = ''
                        if (!f) return
                        const rd = new FileReader()
                        rd.onload = () => setAiAns({
                          name: f.name,
                          b64: String(rd.result || '').split(',')[1] || '',
                        })
                        rd.onerror = () => setAiErr('读不出这个答案文件')
                        rd.readAsDataURL(f)
                      }} />
                  </label>
                </div>

                <div className="mt-2 flex items-center gap-2 text-[10.5px] text-ink-faint">
                  <button onClick={() => { setAiSetup((v) => !v); setAiErr('') }}
                    className="inline-flex items-center gap-1 rounded-md border border-border
                               bg-surface px-1.5 py-[2px] hover:border-brand-line hover:text-brand-ink">
                    <KeyRound size={11} />
                    {aiCfg?.configured ? `DeepSeek 已配置（${aiCfg.model}${aiCfg.key_hint}）` : '设置 API Key'}
                  </button>
                  {aiCfg?.configured && (
                    <button onClick={() => void aiClearKey()}
                      className="underline hover:text-warn">清掉 Key</button>
                  )}
                  <span className="ml-auto">教程：docs/AI录题.md</span>
                </div>
              </section>
            )}
            {ai && (aiSetup || ((aiCfg && !aiCfg.configured) ?? false) || aiBusy || !!aiErr || !!aiNote) && (
              <div className="shrink-0 space-y-1.5">
                {(aiSetup || (aiCfg && !aiCfg.configured)) && (
                  <div className="rounded-lg border border-brand-line bg-brand-soft/40 p-2.5">
                    <div className="flex items-center gap-1.5 text-[12px] font-semibold text-brand-ink">
                      <KeyRound size={13} />第一次用：填一次 DeepSeek 的 API Key
                    </div>
                    <ol className="mt-1.5 space-y-0.5 text-[11px] leading-relaxed text-ink-soft">
                      <li>1. 浏览器打开 <b className="font-mono">platform.deepseek.com</b> 登录 → 左侧「API keys」→「创建 API key」→ 复制 `sk-` 开头那串</li>
                      <li>2. 粘贴到下面 → 点「保存并测试」（通过会显示毫秒数）</li>
                      <li>3. 以后直接把试卷 PDF 拖进上面的虚线框；按量计费：100 页约几毛钱</li>
                    </ol>
                    <div className="mt-2 flex items-center gap-1.5">
                      <input type="password" value={aiKey} spellCheck={false}
                        onChange={(e) => setAiKey(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter' && aiKey.trim()) void aiSaveKey() }}
                        placeholder="sk-…（只存这台电脑，界面只显示末四位）"
                        className={`${FIELD} min-w-0 flex-1 font-mono`} />
                      <button onClick={() => void aiSaveKey()}
                        disabled={aiTesting || (!aiKey.trim() && !aiCfg?.configured)}
                        className="press inline-flex h-[32px] shrink-0 items-center gap-1 rounded-lg
                                   bg-brand px-2.5 text-[11.5px] font-semibold text-white
                                   disabled:opacity-40">
                        {aiTesting ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                        保存并测试
                      </button>
                      {aiCfg?.configured && (
                        <button onClick={() => setAiSetup(false)} className={MINI}>收起</button>
                      )}
                    </div>
                    <details className="mt-2 text-[10.5px] text-ink-faint">
                      <summary className="cursor-pointer select-none">
                        高级设置（模型 / 地址 / 每批页数 / 并发；一般不用改）
                      </summary>
                      <div className="mt-1.5 grid grid-cols-2 gap-1.5">
                        <label className="col-span-2">
                          <span className="mb-0.5 block">模型</span>
                          <input value={aiModel} spellCheck={false}
                            onChange={(e) => setAiModel(e.target.value)}
                            placeholder="deepseek-flash"
                            className={`${FIELD} h-[28px] w-full font-mono`} />
                        </label>
                        <label className="col-span-2">
                          <span className="mb-0.5 block">接口地址</span>
                          <input value={aiBase} spellCheck={false}
                            onChange={(e) => setAiBase(e.target.value)}
                            placeholder="https://api.deepseek.com"
                            className={`${FIELD} h-[28px] w-full font-mono`} />
                        </label>
                        <label>
                          <span className="mb-0.5 block">每批页数（1–12）</span>
                          <input type="number" min={1} max={12} value={aiPages}
                            onChange={(e) => setAiPages(e.target.value)}
                            placeholder="6"
                            className={`${FIELD} h-[28px] w-full`} />
                        </label>
                        <label>
                          <span className="mb-0.5 block">并发（1–4）</span>
                          <input type="number" min={1} max={4} value={aiWorkers}
                            onChange={(e) => setAiWorkers(e.target.value)}
                            placeholder="2"
                            className={`${FIELD} h-[28px] w-full`} />
                        </label>
                      </div>
                      <div className="mt-1">改完点上面的「保存并测试」生效；页数越多越容易截断。</div>
                    </details>
                    {aiCfg?.configured && (
                      <div className="mt-1.5 flex items-center gap-2 text-[10.5px] text-ink-faint">
                        <span>已保存 {aiCfg.key_hint}（{aiCfg.model}）</span>
                        <button onClick={() => void aiClearKey()} className="underline hover:text-warn">清掉 Key</button>
                      </div>
                    )}
                  </div>
                )}
                {aiBusy && (
                  <div className="rounded-lg border border-brand-line bg-surface px-2.5 py-2">
                    <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-brand-ink">
                      <Loader2 size={12} className="animate-spin shrink-0" />
                      <span className="min-w-0 truncate">{aiProg?.msg || '正在准备…'}</span>
                      <span className="ml-auto shrink-0 text-[10.5px] font-normal text-ink-faint">
                        {aiProg?.sec ? `已等 ${aiProg.sec} 秒 · ` : ''}别关窗口
                      </span>
                      <button onClick={() => void aiCancel()}
                        disabled={!aiJobId || aiCancelling}
                        className="shrink-0 text-[10.5px] underline text-ink-faint
                                   hover:text-warn disabled:opacity-40">
                        {aiCancelling ? '正在取消…' : '取消'}
                      </button>
                    </div>
                    <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-brand transition-[width] duration-300"
                        style={{ width: aiProg?.total
                          ? `${Math.max(3, Math.round(aiProg.done / aiProg.total * 100))}%` : '30%' }} />
                    </div>
                  </div>
                )}
                {aiErr && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                  bg-warn-soft px-2.5 py-2 text-[11.5px] leading-relaxed text-warn">
                    <AlertTriangle size={13} className="mt-[1px] shrink-0" />
                    <span className="min-w-0 break-words">{aiErr}</span>
                    <button onClick={() => setAiErr('')} className="ml-auto shrink-0 underline">知道了</button>
                  </div>
                )}
                {aiNote && !aiBusy && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-has-line
                                  bg-has-soft px-2.5 py-2 text-[11.5px] leading-relaxed text-has">
                    <Check size={13} className="mt-[1px] shrink-0" />
                    <span className="min-w-0 break-words">{aiNote}</span>
                  </div>
                )}
              </div>
            )}
            <section className={`shrink-0 ${aiClean ? 'hidden' : ''}`}>
              <div className="mb-2 flex items-baseline gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">1</span>
                <span className={LABEL}>出处</span>
                <span className="text-[11px] text-ink-faint">
                  默认「{DEFAULT_BOOK} / {DEFAULT_LABEL} / {DEFAULT_YEAR}」；有
                  <code className="font-mono text-[10.5px]"> \title&#123;…&#125; </code>
                  时可点「填入出处」采用
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                {([['来源', book, setBook, '手工录入', 'ingest-books'],
                   ['出处', label, setLabel, '如 2025年长沙市高三调研', 'ingest-sources'],
                   ['地区', region, setRegion, '如 新高考I卷 / 武汉', 'ingest-regions'],
                   ['年份', year, setYear, '2025', '']] as const).map(([name, val, set, ph, list]) => (
                  <div key={name}>
                    <div className={`mb-1.5 ${LABEL}`}>{name}</div>
                    <input value={val} onChange={(e) => (set as any)(e.target.value)} placeholder={ph}
                      list={list || undefined}
                      inputMode={name === '年份' ? 'numeric' : undefined}
                      className={`${name === '出处' ? 'w-[230px]' : 'w-[160px]'} ${FIELD}`} />
                  </div>
                ))}
              </div>
              <datalist id="ingest-books">
                {(facets?.books || []).map((x: any) => <option key={x.value} value={x.value} />)}
              </datalist>
              <datalist id="ingest-sources">
                {(facets?.sources || []).slice(0, 400).map((x: any) => <option key={x.value} value={x.value} />)}
              </datalist>
              <datalist id="ingest-regions">
                {(facets?.regions || []).map((x: any) => <option key={x.value} value={x.value} />)}
              </datalist>
              <div className="mt-2">
                <div className={`mb-1.5 ${LABEL}`}>
                  图片来源目录 <span className="font-normal tracking-normal text-ink-faint/80">（可选；带 \includegraphics 时填）</span>
                </div>
                <input value={srcDir} onChange={(e) => setSrcDir(e.target.value)}
                  placeholder="例如 /Users/…/待录入图片（服务器本地路径；留空用默认目录）"
                  className={`w-full ${FIELD}`} />
              </div>
              {keyNeedsSanitize && (
                <div className="mt-2 text-[10.5px] text-ink-faint">
                  提示：来源/出处里的 “/” 或 “#” 只影响内部 key，后端会自动换成全角；
                  显示出处保持原文。
                </div>
              )}
              {yearBad && (
                <div className="mt-2 text-[10.5px] text-warn">
                  年份请填 4 位数字，如 2026。
                </div>
              )}
              {pv?.source_hint?.title && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                  <Sparkles size={11} className="shrink-0 text-brand" />
                  标题识别：{pv.source_hint.title}
                  {pv.source_hint.year ? ` · ${pv.source_hint.year}` : ''}
                  {showHint && (
                    <button onClick={fillHint} className={MINI}>填入出处</button>
                  )}
                </div>
              )}
              <label className="mt-3 flex items-start gap-2 rounded-md border border-border
                                bg-bg px-2 py-1.5 text-[11px] text-ink-soft">
                <input type="checkbox" checked={backfill}
                  onChange={(ev) => {
                    const on = ev.target.checked
                    setBackfill(on)
                    resetReview()
                    setMsg(on
                      ? '补旧题模式：只给库里已有题补空考点/难度；请重新解析'
                      : '已切回普通录入；请重新解析')
                  }}
                  className="mt-[1px] accent-[var(--color-brand)]" />
                <span>
                  <b className="font-medium text-ink">补旧题模式</b>
                  <span className="text-ink-faint">
                    ：只更新库里**已有题**的空考点/空难度，不新增、不改答案/解析/已有考点
                  </span>
                </span>
              </label>
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                <span>整题相似阈值</span>
                <input type="number" min={80} max={100} value={nearThreshold}
                  onChange={(ev) => {
                    const n = Number(ev.target.value)
                    setNearThreshold(Number.isFinite(n) ? Math.min(100, Math.max(80, n)) : 95)
                  }}
                  className="h-[24px] w-[62px] rounded-md border border-border bg-surface px-1.5
                             text-[11px] text-ink-soft outline-none focus:border-brand-line" />
                <span>%</span>
                <span>· 超过这个值按规则不录入；改动后请重新解析</span>
              </div>
            </section>

            {/* 批量：AI 只补空标签；逐题在右栏改。
                **大模型录题模式下整块不显示** —— 那边的考点/难度是 DeepSeek 读出来的，
                再去勾一个「解析后用 qwen3.5 自动标」只会让小白以为还得装个本地模型。 */}
            <section className={`shrink-0 ${ai ? 'hidden' : ''}`}>
              <div className="mb-2 flex items-baseline gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">2</span>
                <span className={LABEL}>批量</span>
                <span className="text-[11px] text-ink-faint">qwen3.5 只做粗标，人最后拍板</span>
              </div>
              <label className="flex items-start gap-2 text-[11.5px] text-ink-soft">
                <input type="checkbox" checked={autoTag}
                  onChange={(e) => setAutoTag(e.target.checked)}
                  className="mt-[1px] accent-[var(--color-brand)]" />
                <span>解析后用 <b className="font-medium text-ink">qwen3.5</b> 自动标考点/难度
                  <span className="text-ink-faint">
                    （默认关闭：不勾就不会启动模型；勾选后解析完才加载 9B。
                    不勾可点顶栏「AI 标注空缺」手动标）
                  </span></span>
              </label>
              {pv && (
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-ink-faint">
                  <span>已选 <b className="text-ink-soft">{selected.length}</b> / {pv.count} 道</span>
                  <span className="text-border">·</span>
                  <span>{pv.spec?.ok ? '规范复核通过' : `${specAfter} 处规范复核未过`}</span>
                </div>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-faint">
                <span>AI 模型：</span>
                {(() => {
                  const loaded: any[] = llmStatus?.loaded || []
                  const tagModel = String(llmStatus?.tag_model || 'qwen3.5-9b-mlx')
                  const tagRow = loaded.find((r) => r.identifier === tagModel
                    || r.model_key === tagModel
                    || String(r.identifier || '').includes(tagModel))
                  const bigRow = loaded.find((r) => String(r.identifier || '').includes('27b')
                    || String(r.model_key || '').includes('27b'))
                  return (<>
                    {tagRow ? (
                      <span className="inline-flex items-center gap-1 rounded bg-brand-soft px-1.5
                                       py-[1px] text-brand-ink">
                        9B 已加载
                        <button onClick={() => void unloadLlm(tagRow.identifier, '9B 标注模型')}
                          className="underline">卸载</button>
                      </span>
                    ) : <span className="rounded bg-muted px-1.5 py-[1px]">9B 未加载</span>}
                    {bigRow ? (
                      <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-[1px]">
                        27B 已加载
                        <button onClick={() => void unloadLlm(bigRow.identifier, '27B')}
                          className="underline">卸载</button>
                      </span>
                    ) : <span className="rounded bg-muted px-1.5 py-[1px]">27B 未加载</span>}
                    <button onClick={() => void refreshLlm()} className="underline">刷新</button>
                  </>)
                })()}
              </div>
            </section>

            {/* 题目：输入框有边框；文件名/读图按钮跟着它。 */}
            <section className={`flex min-h-[240px] flex-1 flex-col ${aiClean ? 'hidden' : ''}`}>
              {restored && (
                <div className="mb-2 flex items-center gap-2 rounded-md border border-border
                                bg-surface-2 px-2 py-1 text-[10.5px] text-ink-faint">
                  已恢复上次未提交的草稿
                  <button onClick={clearDraft} className="underline hover:text-ink-soft">清空重来</button>
                </div>
              )}
              {/* 工具条：**允许换行**。按钮从 2 个长到 4 个之后，窄一点的窗口
                  会把「AI 读整份资料…」挤成三行——先给容器 flex-wrap，再让每个
                  按钮不折行，宁可整组掉到第二行。 */}
              <div className="mb-2 flex shrink-0 flex-wrap items-center gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">3</span>
                <span className={`${LABEL} shrink-0 whitespace-nowrap`}>题目 LaTeX</span>
                <div className="ml-auto flex flex-wrap items-center justify-end gap-1.5">
                <button onClick={() => { changeText(INGEST_SAMPLE); setMsg('已填入示例') }}
                  className="press inline-flex h-[26px] shrink-0 items-center gap-1 whitespace-nowrap
                             rounded-lg border border-border bg-surface px-2 text-[11.5px] text-ink-soft
                             hover:border-brand-line hover:text-brand-ink">
                  <FileText size={12} />填入示例
                </button>
                <label className="press inline-flex h-[26px] shrink-0 cursor-pointer items-center
                                  gap-1 whitespace-nowrap rounded-lg border border-border bg-surface
                                  px-2 text-[11.5px] text-ink-soft
                                  hover:border-brand-line hover:text-brand-ink">
                  <Upload size={12} />选文件…
                  <input type="file" accept=".tex,.txt,.md,.docx" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f) }} />
                </label>
                <label title={vlmReady
                    ? `读图链路已就绪${vlmEngine ? '：' + vlmEngine : ''}`
                    : '点这里会按需启动本地模型（PaddleOCR-VL 认字 → 27B 改格式；首次约 10–60 秒）'}
                  className="press inline-flex h-[26px] shrink-0 cursor-pointer items-center gap-1
                             whitespace-nowrap rounded-lg bg-brand px-2 text-[11.5px] font-semibold
                             text-white transition-[filter] hover:brightness-105">
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                  大模型读图…
                  <span className={`ml-0.5 h-1.5 w-1.5 rounded-full ${
                    vlmReady ? 'bg-has' : 'bg-ink-faint'}`} />
                  <input type="file" accept="image/*,.pdf,.docx" className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) { if (/\.docx$/i.test(f.name)) readFile(f); else ocrFile(f) }
                    }} />
                </label>

                {/* AI 读整份资料：第一次先填 key；之后选文件 → 后台读 → 自动解析。
                    **不和「大模型读图」合并**：那个跑本地小模型（免费、慢、只认一页），
                    这个跑 DeepSeek（按量计费、几分钟读上百页）。两件事，两个按钮。 */}
                <label title="用 DeepSeek 读整份资料（PDF 或照片）：按页计费，100 页几毛钱"
                  className="press inline-flex h-[26px] shrink-0 cursor-pointer items-center gap-1
                             whitespace-nowrap rounded-lg border border-brand-line bg-brand-soft
                             px-2 text-[11.5px] font-medium text-brand-ink hover:border-brand">
                  <Sparkles size={12} />AI 读整份资料…
                  <input type="file" accept=".pdf,image/*" className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      e.currentTarget.value = ''
                      if (!f) return
                      // 同 AI 卡里那条：只在**明确没配**时拦，配置还没拉回来就照跑
                      if (aiCfg && !aiCfg.configured) {
                        setAiSetup(true)
                        setAiErr('先把 API Key 填上（只需一次），填好后再选一次文件')
                        return
                      }
                      aiRunFile(f)
                    }} />
                </label>
                <button onClick={() => { setAiSetup((v) => !v); setAiErr('') }}
                  title={aiCfg?.configured ? `DeepSeek 设置（当前 ${aiCfg.model}${aiCfg.key_hint}）` : 'DeepSeek 设置'}
                  className="press icon-btn h-[26px] w-[26px] shrink-0 rounded-lg border border-border bg-surface">
                  <KeyRound size={12} className={aiCfg?.configured ? 'text-has' : 'text-ink-faint'} />
                </button>
                </div>
              </div>
              {recentJobs.length > 0 && (
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                  <span className="shrink-0">最近任务</span>
                  <button onClick={() => void pruneJobs()} disabled={busy}
                    title="只保留最近 50 个任务"
                    className="press rounded-full border border-border bg-surface px-1.5 py-[1px]
                               text-[10px] text-ink-faint hover:border-brand-line hover:text-ink-soft
                               disabled:opacity-40">清理</button>
                  {recentJobs.slice(0, 4).map((j: any) => (
                    <button key={j.id} onClick={() => resumeJob(j)}
                      disabled={busy}
                      title={`${j.source_name} · ${j.created_at || ''} · ${j.status || ''}`}
                      className="press max-w-[170px] truncate rounded-full border border-border
                                 bg-surface px-2 py-[2px] text-[10.5px] text-ink-soft
                                 hover:border-brand-line hover:text-brand-ink disabled:opacity-40">
                      {j.source_name} · {String(j.created_at || '').slice(5, 16)}
                    </button>
                  ))}
                </div>
              )}
              {sourcePages.length > 0 && (
                <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                  <span className="shrink-0">源页</span>
                  {sourcePages.slice(0, 10).map((name, i) => (
                    <button key={name} onClick={() => setPageView({
                      dir: sourceDir, name, title: `源文件第 ${i + 1} 页`,
                    })}
                      className="press grid h-6 min-w-6 place-items-center rounded-md border border-border
                                 bg-surface px-1.5 text-[10.5px] text-ink-soft
                                 hover:border-brand-line hover:text-brand-ink">
                      {i + 1}
                    </button>
                  ))}
                  {sourcePages.length > 10 && <span>… 共 {sourcePages.length} 页</span>}
                  {sourceJob && <span className="ml-auto truncate">任务 {sourceJob}</span>}
                </div>
              )}
              <div className="relative min-h-0 flex-1 overflow-hidden rounded-[var(--radius-card)]
                              border border-border bg-surface-2
                              focus-within:border-brand-line
                              focus-within:shadow-[0_0_0_3px_var(--color-brand-soft)]"
                onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
                onDragLeave={() => setDrag(false)}
                onDrop={(e) => {
                  e.preventDefault(); setDrag(false)
                  const f = e.dataTransfer.files?.[0]
                  if (f) readFile(f)
                }}>
                <textarea value={text}
                  onChange={(e) => changeText(e.target.value)}
                  spellCheck={false}
                  placeholder={'粘贴整份试卷（exam-zh 格式）；\n或把 .tex / .md / Word 文件拖进来；\n或把题目截图 / PDF 拖进来 —— 由本地大模型识别成 LaTeX：\n\n\\title{2025年长沙市高三调研}\n\\begin{question}\n…\n\\end{question}\n\\begin{solution}\n…\n\\end{solution}'}
                  className="h-full w-full resize-none bg-transparent px-4 py-3.5 font-mono
                             text-[12.5px] leading-relaxed outline-none placeholder:text-ink-faint" />
                {drag && (
                  <div className="anim-fade-in pointer-events-none absolute inset-3 flex flex-col items-center
                                  justify-center gap-2 rounded-[var(--radius-card)] border-2 border-dashed
                                  border-brand-line bg-brand-soft/70 text-[12.5px] font-medium text-brand-ink">
                    <Upload size={20} />
                    松手就读 · 图片 / PDF / Word 交给大模型识别
                  </div>
                )}
              </div>

              <div className="mt-2.5 flex shrink-0 flex-col gap-2">
                {err && !pv && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                  bg-warn-soft px-2.5 py-2 text-[11.5px] text-warn">
                    <X size={13} className="mt-[1px] shrink-0" />{err}
                  </div>
                )}
                {msg && !pv && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-has-line
                                  bg-has-soft px-2.5 py-2 text-[11.5px] text-has">
                    <Check size={13} className="mt-[1px] shrink-0" />{msg}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-ink-faint">
                    脚本会先验证、再规范化、最后复核；不合规的不让入库
                  </span>
                  <button onClick={() => void dryRun()} disabled={busy}
                    className="press ml-auto inline-flex items-center gap-1.5 rounded-lg border
                               border-brand-line bg-brand-soft px-4 py-2 text-[13px] font-semibold
                               text-brand-ink transition-colors hover:bg-brand hover:text-white
                               disabled:opacity-40 disabled:hover:bg-brand-soft
                               disabled:hover:text-brand-ink">
                    {busy ? <Loader2 size={13} className="shrink-0 animate-spin" />
                          : <Play size={13} className="shrink-0" />}
                    {pv ? '重新解析' : '解析成题'}
                  </button>
                </div>
                {busy && <div className="progress-track" />}
              </div>
            </section>
          </SourceStage>

          <ReviewStage>
            <div className="flex min-h-[52px] shrink-0 flex-wrap items-center gap-2 border-b
                            border-border bg-surface px-4 py-2">
              <span className="text-[13px] font-semibold tracking-tight">逐题确认</span>
              {pv ? (
                <span className="rounded-full bg-brand-soft px-2 py-[1px] text-[11px] font-medium
                                 text-brand-ink">{pv.count} 道</span>
              ) : (
                <span className="text-[11px] text-ink-faint">还没解析</span>
              )}
              {pv && (<>
                <button onClick={() => toggleAll(true)} className={MINI}>全选有效</button>
                <button onClick={() => toggleAll(false)} className={MINI}>全不选</button>
                <button onClick={() => {
                  const open = pv.items.every((it: any) => expanded[it.block] !== false)
                  setExpanded(Object.fromEntries(
                    pv.items.map((it: any) => [it.block, !open])))
                }} className={MINI}>
                  {pv.items.every((it: any) => expanded[it.block] !== false)
                    ? '全部收起' : '全部展开'}
                </button>
              </>)}
              {!ai && (
                <button onClick={() => pv && void tagItems(pv, edits, { onlyPicked: true, mainOnly })}
                  disabled={!pv || !emptyTagCount || tagging}
                  title="用 qwen3.5 只给还没标考点的题补标；已标的不动"
                  className="press ml-auto inline-flex h-[26px] items-center gap-1 rounded-lg border
                             border-brand-line bg-brand-soft px-2 text-[11px] font-medium
                             text-brand-ink hover:border-brand disabled:opacity-40">
                  {tagging ? <Loader2 size={12} className="animate-spin" />
                           : <Sparkles size={12} />}
                  AI 标注空缺{emptyTagCount ? ` (${emptyTagCount})` : ''}
                </button>
              )}
            </div>

            {pv && (
              <div className="shrink-0 border-b border-border bg-surface px-4 py-1.5">
                <div className="flex flex-wrap items-center gap-1.5">
                  {([['all', '全部'], ['new', '新题'], ['missing', '缺考点'],
                     ['suspect', '疑似重复'], ['blocked', '有硬伤']] as const).map(([k, t]) => (
                    <button key={k} onClick={() => setReviewFilter(k)}
                      className={`press rounded-full border px-2 py-[2px] text-[10.5px] font-medium
                                  transition-colors ${reviewFilter === k
                        ? 'border-brand bg-brand text-white'
                        : 'border-border bg-surface text-ink-soft hover:border-brand-line'}`}>
                      {t}<span className="ml-1 opacity-70">{filterCounts[k]}</span>
                    </button>
                  ))}
                  <details className="relative ml-auto">
                    <summary className="cursor-pointer select-none rounded-md border border-border
                                        bg-surface px-2 py-[2px] text-[10.5px] text-ink-soft
                                        hover:border-brand-line">
                      批量设置（已选 {selected.length}）
                    </summary>
                    <div className="absolute right-0 z-30 mt-1 w-[420px] space-y-1.5 rounded-lg
                                    border border-border bg-surface p-2 shadow-[var(--shadow-pop)]">
                      <div className="flex items-center gap-1.5">
                        <select value={batchType} onChange={(e) => setBatchType(e.target.value)}
                          className="h-[26px] min-w-0 flex-1 rounded-md border border-border bg-bg px-1 text-[11px]">
                          {QTYPE_OPTS.map(([v, t]) => <option key={v || 'auto'} value={v}>{v ? t : '自动题型'}</option>)}
                        </select>
                        <button onClick={() => applyBatch('type')} className={MINI}>应用题型</button>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <select value={batchDiff} onChange={(e) => setBatchDiff(e.target.value)}
                          className="h-[26px] min-w-0 flex-1 rounded-md border border-border bg-bg px-1 text-[11px]">
                          <option value="">按主考点派生</option>
                          <option value="简单题">简单题</option>
                          <option value="中档题">中档题</option>
                          <option value="难题">难题</option>
                        </select>
                        <button onClick={() => applyBatch('diff')} className={MINI}>应用难度</button>
                      </div>
                      <div className="flex items-start gap-1.5">
                        <div className="min-w-0 flex-1">
                          <PointPicker value={batchPts} points={points} onChange={setBatchPts} />
                        </div>
                        <button onClick={() => applyBatch('points')} disabled={!batchPts.length}
                          className={MINI}>加考点</button>
                      </div>
                      <label className="flex items-center gap-1.5 text-[10.5px] text-ink-faint">
                        <input type="checkbox" checked={mainOnly}
                          onChange={(ev) => setMainOnly(ev.target.checked)}
                          className="accent-[var(--color-brand)]" />
                        AI 只取主考点（更稳；次考点手加）
                      </label>
                    </div>
                  </details>
                </div>
              </div>
            )}

            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3.5">
              {report && (
                <div className="anim-fade-in space-y-3">
                  <div className="rounded-[var(--radius-card)] border border-has-line
                                  bg-has-soft p-4">
                    <div className="flex items-center gap-2 text-[14px] font-semibold text-has">
                      <Check size={16} /> {backfill ? '本次补标签完成' : '本次入库完成'}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-3 text-[12px] text-ink-soft">
                      <span>{backfill ? '补标签' : '新增'} <b className="text-ink">{
                        backfill ? (report.upgraded?.length || 0) : (report.added?.length || 0)
                      }</b> 道</span>
                      <span>跳过 <b className="text-ink">{report.skipped?.length || 0}</b> 道</span>
                      {!backfill && report.upgraded?.length
                        ? <span>升级 <b>{report.upgraded.length}</b> 道</span> : null}
                    </div>
                    <div className="mt-2 text-[10.5px] text-ink-faint">
                      {backfill
                        ? '只补已有题的空考点/空难度；新题、正文、已有考点都不动。'
                        : `库里已有/整题相似 >${nearThreshold}% 的题按规则跳过，不新增、不更新。`}
                    </div>
                  </div>

                  {report.added?.length > 0 && (
                    <details className="rounded-[var(--radius-card)] border border-border bg-surface p-3">
                      <summary className="cursor-pointer text-[12px] font-medium text-ink-soft">
                        新增的题（{report.added.length}）
                      </summary>
                      <div className="mt-2 space-y-0.5 font-mono text-[10.5px] text-ink-faint">
                        {report.added.slice(0, 50).map((k: string) => <div key={k} className="truncate">{k}</div>)}
                        {report.added.length > 50 && <div>… 其余 {report.added.length - 50} 道</div>}
                      </div>
                    </details>
                  )}
                  {report.skipped?.length > 0 && (
                    <details className="rounded-[var(--radius-card)] border border-border bg-surface p-3">
                      <summary className="cursor-pointer text-[12px] font-medium text-ink-soft">
                        跳过的题（{report.skipped.length}）
                      </summary>
                      <div className="mt-2 space-y-1 text-[10.5px] text-ink-faint">
                        {report.skipped.slice(0, 50).map((x: any, i: number) => (
                          <div key={i} className="truncate">
                            <span className="font-mono">{String(x.key).split('/').pop()}</span> · {x.reason}
                          </div>
                        ))}
                        {report.skipped.length > 50 && <div>… 其余 {report.skipped.length - 50} 道</div>}
                      </div>
                    </details>
                  )}

                  <div className="flex flex-wrap items-center gap-2">
                    {report.added?.length > 0 && (
                      <button onClick={() => void undoReport()} disabled={busy}
                        className="press rounded-lg border border-warn-line bg-warn-soft px-3 py-2
                                   text-[12px] font-medium text-warn hover:border-warn disabled:opacity-40">
                        <Undo2 size={12} className="mr-1 inline" />撤销本次导入
                      </button>
                    )}
                    <button onClick={() => { setReport(null) }}
                      className="press rounded-lg border border-border bg-surface px-3 py-2
                                 text-[12px] text-ink-soft hover:border-border-strong">
                      再录一批
                    </button>
                  </div>
                </div>
              )}
              {!report && !pv && !busy && (
                <div className="anim-fade-in flex h-full flex-col justify-center gap-3 px-1">
                  <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                    <Play size={13} className="shrink-0 text-ink-faint" />
                    {ai
                      ? '左边选一份资料、等它读完，这里就会出现一张张题卡：'
                      : '点左边「解析成题」之后，这里会变成一张张题卡：'}
                  </div>
                  <ol className="space-y-2">
                    {(ai ? ([
                      ['大模型读题', '整份 PDF 一页页交给 DeepSeek，题干/选项/答案/解析一起抄出来'],
                      ['只抄不解', '原文没有答案就留空；缺答案/缺解析的题不会进来'],
                      ['脚本规范 + 查重', '先验证、再修改、最后复核；跟库里已有的题对一遍'],
                      ['人拍板', '勾选要入库的题；图没画好/没裁好的会被标出来'],
                    ] as const) : ([
                      ['自动切题', '一份卷子里的 question/problem 全切出来，不用一道一道粘'],
                      ['脚本规范 + 查重', '先验证、再修改、最后复核；跟库里已有的题对一遍'],
                      ['qwen3.5 粗标', '考点/难度先填一版，卡片里逐题可改'],
                      ['人拍板', '勾选要入库的题；缺答案/解析/图的会被拦住'],
                    ] as const)).map(([t, d], i) => (
                      <li key={t} className="flex gap-2.5 rounded-[var(--radius-card)] border
                                             border-border bg-surface p-2.5">
                        <span className="mt-[1px] grid h-4 w-4 shrink-0 place-items-center rounded
                                         bg-muted text-[10px] font-semibold text-ink-faint">
                          {i + 1}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[12px] font-medium text-ink">{t}</span>
                          <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-faint">
                            {d}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
              {!report && busy && !pv && (
                <div className="anim-fade-in space-y-2">
                  <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                    <Loader2 size={14} className="shrink-0 animate-spin text-brand" />
                    正在切题 · 规范化 · 查重 · 查图…
                  </div>
                  <div className="progress-track" />
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="rounded-[var(--radius-card)] border border-border bg-surface
                                            p-3 shadow-[var(--shadow-card)]">
                      <div className="skeleton mb-2 h-3 w-24" />
                      <div className="skeleton h-2.5 w-full" />
                      <div className="skeleton mt-1.5 h-2.5 w-3/5" />
                    </div>
                  ))}
                </div>
              )}

              {!report && pv && (<>
                {/* 汇总条：解析/规范/查重/图片。 */}
                <div className="grid grid-cols-2 gap-2">
                  {([
                    ['解析', `${pv.count} 道`,
                     pv.errors?.length ? `${pv.errors.length} 个问题` : '全部认出',
                     pv.errors?.length ? 'warn' : 'has'],
                    ['规范', pv.spec?.ok ? '复核通过' : `${specAfter} 处未过`,
                     pv.spec?.ok ? `自动修 ${fixedCount} 处` : '只拦勾选的题',
                     pv.spec?.ok ? 'has' : 'warn'],
                    backfill
                      ? ['补旧题', `已有 ${pv.items.filter((it: any) => it.same_key).length
                          } 道 · 已选 ${selected.length}`,
                         '只补空考点/难度，不新增、不改正文', 'has']
                      : ['查重', `新 ${pv.dup.new} · 跳过 ${
                          pv.dup.skip ?? (pv.dup.merge + (pv.dup.near || 0))}`,
                         `疑似 ${pv.dup.suspect} · 已有/相似不更新`,
                         pv.dup.suspect ? 'warn' : 'has'],
                    ['图片', pv.missing_images?.length
                      ? `缺 ${pv.missing_images.length} 张` : '齐全',
                     `${Object.keys(pv.images || {}).length} 张引用`,
                     pv.missing_images?.length ? 'warn' : 'has'],
                  ] as const).map(([k, v, note, tone]) => (
                    <div key={k} className="rounded-lg border border-border bg-surface px-2.5 py-2">
                      <div className="text-[10px] text-ink-faint">{k}</div>
                      <div className={`text-[12.5px] font-semibold ${
                        tone === 'warn' ? 'text-warn' : 'text-ink'}`}>{v}</div>
                      <div className="mt-0.5 truncate text-[10px] text-ink-faint">{note}</div>
                    </div>
                  ))}
                </div>

                {tagErr && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                  bg-warn-soft px-2.5 py-2 text-[11px] text-warn">
                    <AlertTriangle size={12} className="mt-[1px] shrink-0" />
                    AI 标注：{tagErr}
                  </div>
                )}

                {pv.errors?.length > 0 && (
                  <div className="rounded-lg border border-warn-line bg-warn-soft px-2.5 py-2
                                  text-[11px] text-warn">
                    <div className="flex items-center gap-1.5 font-medium">
                      <AlertTriangle size={12} className="shrink-0" />
                      {pv.errors.length} 个解析问题（有题块可能没切出来）
                    </div>
                    <ul className="mt-1 list-disc pl-4">
                      {pv.errors.slice(0, 4).map((e: any, i: number) => (
                        <li key={i} className="truncate">{e.reason || e}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 题卡 */}
                {visibleItems.length === 0 && pv && (
                  <div className="rounded-[var(--radius-card)] border border-dashed border-border
                                  bg-surface px-4 py-8 text-center text-[12px] text-ink-faint">
                    当前筛选下没有题目
                  </div>
                )}
                {visibleItems.map((it: any) => {
                  const b = it.block
                  const am = aiCards[b]
                  const e = edits[b] || { ...EMPTY, source_no: String(b + 1) }
                  const hard = blockingOf(it)
                  const picked = !!picks[b]
                  const pt = pointInfo.get(e.points[0])
                  const diff = e.difficulty || pt?.difficulty || it.difficulty || ''
                  const stars = e.difficulty
                    ? (STARS[e.difficulty] || 0)
                    : (pt?.stars || it.stars || 0)
                  const typeLabel = e.qtype ? (QTYPE_LABEL[e.qtype] || e.qtype) : it.type_label
                  const dup = it.dups?.[0]
                  const isDup = backfill ? !it.same_key
                    : (!!it.same_key || !!it.near_dup)
                  const sim = Math.round((dup?.score_full ?? dup?.score ?? 0) * 100)
                  // 默认展开：审题时先看完整的题干/选项/答案/解析，
                  // 不让人为了核对一句话再点一次。`undefined` 视为开。
                  const isOpen = expanded[b] !== false
                  return (
                    <div key={b}
                      ref={(el) => { cardRefs.current[b] = el }}
                      onClick={() => setActiveCard(b)}
                      className={`rounded-[var(--radius-card)] border bg-surface p-4
                                  shadow-[var(--shadow-card)] transition-opacity ${
                        activeCard === b ? 'border-brand-line ring-2 ring-brand-line/40' : 'border-border'} ${
                        picked || isDup ? '' : 'opacity-60'}`}>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <input type="checkbox" checked={picked} disabled={hard.length > 0 || isDup}
                          onChange={(ev) => setPicks({ ...picks, [b]: ev.target.checked })}
                          className="accent-[var(--color-brand)]" />
                        <span className="text-[12px] font-semibold text-ink">
                          第 {e.source_no || b + 1} 题
                        </span>
                        <span className="rounded bg-muted px-1.5 py-[1px] text-[10.5px] text-ink-soft">
                          {typeLabel}
                        </span>
                        <span className={`rounded px-1.5 py-[1px] text-[10.5px] font-medium ${
                          diff ? 'bg-brand-soft text-brand-ink' : 'border border-dashed border-border text-ink-faint'}`}
                          title={e.difficulty ? '手动指定' : '按主考点派生'}>
                          {stars ? '★'.repeat(Math.min(stars, 4)) + ' ' : ''}{diff || '未评级'}
                        </span>
                        <Flags flags={{ ...it.flags, 标签: e.points.length > 0 }}
                          type={it.type} />
                        {!e.points.length && aiMiss[b] && (
                          <span className="rounded bg-warn-soft px-1.5 py-[1px] text-[10px]
                                           font-medium text-warn"
                            title="qwen3.5 这轮没认出考点；已留空，可手标或重试">
                            AI 没认出
                          </span>
                        )}
                        {it.same_key && !backfill && (
                          <span className="rounded bg-warn-soft px-1.5 py-[1px] text-[10px]
                                           font-medium text-warn"
                            title="库里已有同题：按规则整题跳过，不新增、不更新">
                            库内已有 · 跳过
                          </span>
                        )}
                        {backfill && it.same_key && (
                          <span className="rounded bg-brand-soft px-1.5 py-[1px] text-[10px]
                                           font-medium text-brand-ink"
                            title="补旧题模式：只给这道库里已有的题补空考点/难度，不新增、不改正文">
                            库内已有 · 补标签
                          </span>
                        )}
                        {backfill && !it.same_key && (
                          <span className="rounded bg-muted px-1.5 py-[1px] text-[10px]
                                           font-medium text-ink-faint"
                            title="补旧题模式不新增题">
                            补旧题模式 · 不新增
                          </span>
                        )}
                        {it.near_dup && !it.same_key && !backfill && (
                          <span className="rounded bg-warn-soft px-1.5 py-[1px] text-[10px]
                                           font-medium text-warn"
                            title={`整题相似 ${Math.round((it.near_score || 0) * 100)}%`
                              + `（>${nearThreshold}%）：按规则整题跳过，不新增、不更新`}>
                            相似 {Math.round((it.near_score || 0) * 100)}% · 跳过
                          </span>
                        )}
                        <span className="ml-auto font-mono text-[10px] text-ink-faint">#{b + 1}</span>
                      </div>

                      <div className="q-stem mt-1.5 text-[12.5px] leading-relaxed">
                        {renderBlocks(it.blocks?.stem)}
                      </div>

                      {am && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px]">
                          <span className={`rounded px-1.5 py-[1px] font-medium ${
                            am.verified ? 'bg-has-soft text-has' : 'bg-warn-soft text-warn'}`}>
                            {am.verified ? '答案已复核' : `核对未过${am.verdict ? `：${am.verdict}` : ''}`}
                          </span>
                          {am.answer_source === 'answer_sheet' && (
                            <span className="text-ink-faint">答案：答案册原文</span>
                          )}
                          {am.answer_source === 'inline' && (
                            <span className="text-ink-faint">答案：题页原文</span>
                          )}
                          {am.pages?.length > 0 && aiPageDir && (
                            <button onClick={() => setPageView({
                              dir: aiPageDir, name: `q-${am.pages[0]}.png`,
                              title: `原卷第 ${am.pages[0]} 页`,
                            })} className={MINI}>看原页</button>
                          )}
                          {am.answer_pages?.length > 0 && aiPageDir && (
                            <button onClick={() => setPageView({
                              dir: aiPageDir, name: `a-${am.answer_pages[0]}.png`,
                              title: `答案册第 ${am.answer_pages[0]} 页`,
                            })} className={MINI}>看答案页</button>
                          )}
                          {typeof am.confidence === 'number' && (
                            <span className="text-ink-faint">
                              置信度 {Math.round(am.confidence * 100)}%
                            </span>
                          )}
                          {am.problems?.length > 0 && (
                            <span className="text-warn" title={am.problems.join('；')}>
                              {am.problems.length} 处核对提示
                            </span>
                          )}
                        </div>
                      )}

                      {Object.keys(it.figure_previews || {}).length > 0 && (
                        <div className="mt-2 rounded-md border border-border bg-bg p-2">
                          <div className="mb-1 text-[10px] text-ink-faint">
                            待入库图片（干跑预览；提交后复制进库）
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {Object.entries(it.figure_previews).map(([id, raw]) => {
                              const path = String(raw || '')
                              const src = `/api/ingest/preview-image?path=${encodeURIComponent(path)}`
                                + (srcDir.trim() ? `&src_dir=${encodeURIComponent(srcDir.trim())}` : '')
                              return (
                                <a key={id} href={src} target="_blank" rel="noreferrer"
                                  className="block rounded border border-border bg-surface p-1">
                                  <img src={src} alt="题图" className="h-20 max-w-[180px] object-contain" />
                                </a>
                              )
                            })}
                          </div>
                        </div>
                      )}

                      <div className="mt-2 grid grid-cols-[92px_1fr] gap-x-2 gap-y-2">
                        <div>
                          <div className={`mb-1 ${LABEL}`}>题型</div>
                          <select value={e.qtype}
                            onChange={(ev) => {
                              const v = ev.target.value
                              setEdits({ ...edits, [b]: { ...e, qtype: v } })
                            }}
                            className="h-[26px] w-full rounded-md border border-border bg-surface
                                       px-1 text-[11px] text-ink-soft outline-none
                                       focus:border-brand-line">
                            {QTYPE_OPTS.map(([v, t]) => (
                              <option key={v || 'auto'} value={v}>
                                {v ? t : `自动（${it.type_label}）`}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <div className={`mb-1 ${LABEL}`}>原卷题号</div>
                          <input value={e.source_no}
                            onChange={(ev) => setEdits({
                              ...edits, [b]: { ...e, source_no: ev.target.value },
                            })}
                            placeholder={String(b + 1)}
                            className="h-[26px] w-[70px] rounded-md border border-border bg-bg px-1.5
                                       text-[11px] outline-none focus:border-brand-line" />
                        </div>
                        <div className="col-span-2">
                          <div className="mb-1 flex items-center gap-1.5">
                            <span className={LABEL}>单题出处 / 年份</span>
                            <span className="text-[10px] text-ink-faint">
                              留空沿用左栏全局；多卷材料会按 \title 自动分段
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <input value={e.label}
                              onChange={(ev) => setEdits({
                                ...edits, [b]: { ...e, label: ev.target.value },
                              })}
                              placeholder={label || '沿用全局出处'}
                              className="h-[26px] min-w-0 flex-1 rounded-md border border-border
                                         bg-surface px-1.5 text-[11px] outline-none
                                         focus:border-brand-line" />
                            <input value={e.year}
                              onChange={(ev) => setEdits({
                                ...edits, [b]: { ...e, year: ev.target.value },
                              })}
                              placeholder={year || '全局年份'}
                              inputMode="numeric"
                              className="h-[26px] w-[92px] rounded-md border border-border
                                         bg-surface px-1.5 text-[11px] outline-none
                                         focus:border-brand-line" />
                          </div>
                        </div>
                        <div className="col-span-2">
                          <div className="mb-1 flex items-center gap-1.5">
                            <span className={LABEL}>难度</span>
                            <span className="text-[10px] text-ink-faint">
                              不选就按主考点派生
                            </span>
                          </div>
                          <DiffPills value={e.difficulty} derived={pt?.difficulty || it.difficulty || ''}
                            onChange={(v) => setEdits({ ...edits, [b]: { ...e, difficulty: v } })} />
                          {e.difficulty && pt?.stars && Math.abs(
                            (STARS[e.difficulty] || 0) - (pt.stars || 0)) >= 1 && (
                            <div className="mt-1 flex items-center gap-1.5 text-[10px] text-warn">
                              <AlertTriangle size={10} />
                              难度与主考点星级差 {Math.abs(
                                (STARS[e.difficulty] || 0) - (pt.stars || 0))} 档
                              <button onClick={() => setEdits({
                                ...edits, [b]: { ...e, difficulty: '' },
                              })} className="underline hover:text-ink-soft">按主考点</button>
                            </div>
                          )}
                        </div>
                        <div className="col-span-2">
                          <div className="mb-1 flex items-center gap-1.5">
                            <span className={LABEL}>考点</span>
                            <span className="text-[10px] text-ink-faint">第一条为主考点</span>
                            {e.point_source === 'llm' && (
                              <span className="rounded bg-brand-soft px-1 py-[1px] text-[9.5px]
                                               text-brand-ink"
                                title={e.tag_model ? `AI 标注：${e.tag_model}` : 'AI 标注'}>
                                AI 标{e.tag_model ? ` · ${e.tag_model.split('/').pop()}` : ''}
                              </span>
                            )}
                            {e.point_source === 'manual' && (
                              <span className="rounded bg-muted px-1 py-[1px] text-[9.5px]
                                               text-ink-faint">手标</span>
                            )}
                          </div>
                          <PointPicker value={e.points} points={points}
                            onChange={(v) => setEdits({
                              ...edits,
                              [b]: { ...e, points: v, point_source: v.length ? 'manual' : '' },
                            })} />
                        </div>
                      </div>

                      {hard.length > 0 && (
                        <div className="mt-2 flex items-start gap-1.5 rounded-md border border-warn-line
                                        bg-warn-soft px-2 py-1.5 text-[10.5px] text-warn">
                          <AlertTriangle size={11} className="mt-[1px] shrink-0" />
                          <span>不能入库：{hard.join('；')}</span>
                        </div>
                      )}
                      {it.spec_before?.length > 0 && (
                        <div className="mt-1.5 text-[10px] text-ink-faint">
                          规范器修了 {it.spec_before.length} 处
                          {it.spec_after?.length ? ` · 复核还剩 ${it.spec_after.length} 处` : ''}
                        </div>
                      )}

                      {/* 查重只读：库内已有 → 整题跳过；疑似重复只提示，不提供"并入"。 */}
                      {dup && (
                        <div className="mt-2 rounded-md border border-border bg-bg px-2 py-1.5">
                          <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                            <span className={`rounded px-1 py-[1px] font-medium ${
                              isDup ? 'bg-warn-soft text-warn'
                                    : 'bg-muted text-ink-faint'}`}>
                              {backfill
                                ? (it.same_key ? '已有 · 补标签' : '补旧题模式 · 不新增')
                                : it.same_key
                                  ? '已有 · 跳过'
                                  : it.near_dup
                                    ? '高度相似 · 跳过'
                                    : (dup.verdict === '变式' ? '变式' : '疑似重复')}
                            </span>
                            <span className="tnum">整题相似 {sim}%</span>
                            <span className="min-w-0 flex-1 truncate text-ink-soft">{dup.stem}</span>
                            <span className="shrink-0">
                              {backfill
                                ? (it.same_key ? '只补空考点/难度，不改正文' : '补旧题模式不新增')
                                : (isDup ? '不新增、不更新' : '不完全相同，仍可入库')}
                            </span>
                          </div>
                          {(isDup || (backfill && it.same_key)) && (
                            <div className="mt-1 text-[10px] text-ink-faint">
                              {it.same_key ? '库里已有：' : '最相似的库内题：'}
                              <span className="font-mono">
                                {it.same_key ? (dup?.key || it.dup_key) : (it.near_key || dup?.key)}
                              </span>
                              {it.near_dup && ` · 整题相似 ${Math.round((it.near_score || 0) * 100)}%`}
                            </div>
                          )}
                          {dup?.point_titles?.length > 0 && (
                            <div className="mt-1 text-[10px] text-ink-faint">
                              库内考点：{dup.point_titles.join('、')}
                            </div>
                          )}
                          {(dup?.answer_preview || dup?.solution_preview) && (
                            <details className="mt-1 text-[10px] text-ink-faint">
                              <summary className="cursor-pointer select-none">对比库内答案/解析</summary>
                              {dup.answer_preview && (
                                <div className="mt-1 whitespace-pre-wrap break-words rounded bg-surface-2 p-1.5 font-mono">
                                  答案：{dup.answer_preview}
                                </div>
                              )}
                              {dup.solution_preview && (
                                <div className="mt-1 max-h-[180px] overflow-y-auto whitespace-pre-wrap
                                                break-words rounded bg-surface-2 p-1.5 font-mono">
                                  解析：{dup.solution_preview}
                                </div>
                              )}
                            </details>
                          )}
                        </div>
                      )}

                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <button onClick={() => setExpanded({ ...expanded, [b]: !isOpen })}
                          className={MINI}>
                          {isOpen ? '收起' : '选项 / 答案 / 解析'}
                        </button>
                        <button onClick={() => setSrcOpen({ ...srcOpen, [b]: !srcOpen[b] })}
                          aria-label="改这道题的源码" title="改这道题的源码"
                          className={MINI}>
                          {srcOpen[b] ? '收起源码' : '改源码'}
                        </button>
                        {!ai && (<>
                          <button onClick={() => void tagItems(pv, edits, { blocks: [b], mainOnly })}
                            disabled={tagging}
                            className={MINI} title="只重标这一道，覆盖卡片上的考点/难度">
                            <Sparkles size={10} />AI 标注这题
                          </button>
                          <button onClick={() => void tagItems(pv, edits, {
                            blocks: [b], mainOnly, model: 'qwen/qwen3.8-27b',
                          })}
                            disabled={tagging}
                            className={MINI}
                            title="用 27B 慢标这一道；更准，但会占 16GB 内存">
                            27B 重标
                          </button>
                        </>)}
                        {!picked && hard.length === 0 && !isDup && (
                          <button onClick={() => setPicks({ ...picks, [b]: true })}
                            className={MINI}>选这道</button>
                        )}
                        {hard.length === 0 && !isDup && (
                          <button onClick={() => void commitOne(b)}
                            disabled={busy || tagging}
                            className={MINI}
                            title="只把这题写入题库；其他卡不动">
                            <Upload size={10} />{backfill ? '补标签' : '入库这题'}
                          </button>
                        )}
                      </div>

                      {srcOpen[b] && (
                        <div className="mt-2 rounded-md border border-border bg-bg p-2">
                          <textarea
                            value={srcEdit[b] ?? it.tex ?? ''}
                            onChange={(ev) => setSrcEdit({ ...srcEdit, [b]: ev.target.value })}
                            spellCheck={false}
                            className="h-[180px] w-full resize-y rounded-md border border-border
                                       bg-surface-2 p-2 font-mono text-[11px] leading-relaxed
                                       outline-none focus:border-brand-line" />
                          <div className="mt-1.5 flex items-center gap-2">
                            <span className="text-[10px] text-ink-faint">
                              只重解析这一题，其他卡的勾选/考点保留
                            </span>
                            <button onClick={() => {
                              const n = { ...srcEdit }; delete n[b]
                              setSrcEdit(n); setSrcOpen({ ...srcOpen, [b]: false })
                            }} className={MINI}>取消</button>
                            <button onClick={() => void saveSource(b)} disabled={busy}
                              className={MINI}>
                              {busy ? <Loader2 size={10} className="animate-spin" /> : null}
                              保存并重解析
                            </button>
                          </div>
                        </div>
                      )}

                      {isOpen && (
                        <div className="mt-2 space-y-1.5 rounded-md border border-border bg-bg p-3">
                          {it.options?.length > 0 && (
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                              {it.options.map((o: any, k: number) => (
                                <div key={k} className="flex gap-1 text-[11.5px] text-ink-soft">
                                  <b className="shrink-0">{o.label}.</b>
                                  <div className="min-w-0">{renderBlocks(it.blocks?.options?.[k])}</div>
                                </div>
                              ))}
                            </div>
                          )}
                          <div className="text-[10.5px] text-ink-faint">答案</div>
                          <div className="text-[12px] text-ink-soft">
                            {renderBlocks(it.blocks?.answer)}
                          </div>
                          <div className="text-[10.5px] text-ink-faint">解析</div>
                          <div className="text-[11.5px] leading-relaxed">
                            {renderBlocks(it.blocks?.solution)}
                          </div>
                          {am?.answer_quote && (
                            <div className="text-[10.5px] leading-relaxed text-ink-faint">
                              答案原文：{am.answer_quote}
                            </div>
                          )}
                          {am?.solution_quote && (
                            <div className="max-h-28 overflow-y-auto text-[10.5px] leading-relaxed text-ink-faint">
                              解析原文：{am.solution_quote}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}

                {/* 技术细节折叠：不抢题卡的位置，但都能查。 */}
                <details className="rounded-[var(--radius-card)] border border-border bg-surface
                                    shadow-[var(--shadow-card)]">
                  <summary className="cursor-pointer px-3 py-2 text-[11.5px] font-medium text-ink-soft">
                    规范 / 图片 / 校验 / 影响面详情
                  </summary>
                  <div className="space-y-3 border-t border-border p-3">
                    <Report n="①" title="规范：验证 → 修改 → 复核">
                      <div className="space-y-1.5 text-[11px]">
                        <div className="flex items-center gap-2">
                          <span className="w-12 shrink-0 text-ink-faint">改之前</span>
                          {pv.spec.before?.length
                            ? <span className="text-warn">{pv.spec.before.length} 处不合规</span>
                            : <span className="text-has">本来就合规</span>}
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="w-12 shrink-0 text-ink-faint">规范器</span>
                          <span className="min-w-0 text-ink-soft">
                            {pv.spec.fixed?.length
                              ? pv.spec.fixed.map((f: any) => `${f.name} ${f.hits} 道`).join(' · ')
                              : '无需改动'}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="w-12 shrink-0 text-ink-faint">复核后</span>
                          {pv.spec.ok
                            ? <span className="text-has">全部规范，可以导入</span>
                            : <span className="text-warn">仍有 {specAfter} 处未过</span>}
                        </div>
                        {!pv.spec.ok && (
                          <div className="max-h-[120px] space-y-0.5 overflow-y-auto text-[10px] text-warn">
                            {(pv.spec.after || []).slice(0, 20).map((b: any, i: number) => (
                              <div key={i} className="truncate">
                                <span className="font-mono">{String(b.key).split('/').pop()}</span>
                                {' '}[{b.check}] {b.why}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </Report>
                    <Report n="②" title={`图片：${Object.keys(pv.images || {}).length} 张`}>
                      {!Object.keys(pv.images || {}).length
                        ? <div className="text-[11px] text-ink-faint">没有引用图片</div>
                        : <div className="space-y-0.5">
                            {Object.entries(pv.images || {}).map(([k, v]: any) => (
                              <div key={k} className="flex items-center gap-2 text-[10.5px]">
                                <span className="min-w-0 flex-1 truncate font-mono text-ink-soft">{k}</span>
                                <span className={v.status === 'missing' ? 'text-warn' : 'text-has'}>
                                  {v.note}
                                </span>
                              </div>
                            ))}
                          </div>}
                    </Report>
                    <Report n="③" title="字段校验">
                      {pv.problems?.length
                        ? <div className="space-y-0.5 text-[10.5px] text-warn">
                            {pv.problems.slice(0, 20).map((p: any, i: number) => (
                              <div key={i} className="truncate">
                                <span className="font-mono">{String(p.key).split('/').pop()}</span>
                                {' '}{p.problems.join('；')}
                              </div>
                            ))}
                          </div>
                        : <div className="text-[11px] text-has">全部通过</div>}
                    </Report>
                    <Report n="④" title="影响面">
                      <div className="text-[11.5px] font-medium text-has">
                        存量题目影响：{pv.impact.existing_questions} 道
                      </div>
                      <div className="mt-1 text-[10.5px] leading-snug text-ink-faint">
                        {pv.impact.note}
                      </div>
                    </Report>
                  </div>
                </details>
              </>)}
            </div>

            {!report && (
              <CommitBar
                pv={pv} backfill={backfill} nearThreshold={nearThreshold}
                err={err} msg={msg} busy={busy} tagging={tagging}
                selectedCount={selected.length} badCount={badSelected.length}
                onCommit={doCommit}
              />
            )}
          </ReviewStage>
        </div>
      </div>

      {pageView && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-6"
          onClick={(e) => { e.stopPropagation(); setPageView(null) }}>
          <div className="max-h-full max-w-[min(1100px,92vw)] overflow-auto rounded-xl
                          border border-border bg-surface p-2 shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 px-2 py-1">
              <span className="text-[12px] font-medium text-ink-soft">{pageView.title}</span>
              <button onClick={() => setPageView(null)}
                className="text-[11px] text-ink-faint underline hover:text-ink">关闭</button>
            </div>
            <img
              src={`/api/ingest/preview-image?path=${encodeURIComponent(pageView.name)}`
                + `&src_dir=${encodeURIComponent(pageView.dir)}`}
              alt={pageView.title}
              className="max-h-[82vh] max-w-full object-contain" />
          </div>
        </div>
      )}
    </div>
  )
}
