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
  AlertTriangle, Check, FileText, Loader2, Play, Sparkles, Undo2, Upload, X,
} from 'lucide-react'
import { renderBlocks } from '@/lib/render'
import { api } from '@/lib/api'
import { Flags, Report, INGEST_SAMPLE, CloseBtn } from '@/app/ui'
import { PointPicker, DiffPills } from '@/app/IngestControls'

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
  return [...new Set(out)]
}

const DRAFT_KEY = 'amtiku.ingest.draft.v1'

function loadDraft(): any {
  try {
    if (typeof localStorage === 'undefined') return {}
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}') || {}
  } catch { return {} }
}

export default function IngestDrawer({ onClose, onDone, facets, closing }: {
  onClose: () => void; onDone: () => void; facets: any
  /** 正在播退场动画（父组件用 `useUnmount` 控制）。 */
  closing?: boolean
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
    if (isImg || isPdf) { ocrFile(f); return }
    const r = new FileReader()
    r.onload = () => { changeText(String(r.result || '')) }
    r.readAsText(f, 'utf-8')
  }

  /** 图片 / PDF → LaTeX，只填进输入框；**不写库**。 */
  const ocrFile = (f: File) => {
    setBusy(true); setErr(''); setMsg(`正在识别 ${f.name} …（首次要等模型加载）`)
    const r = new FileReader()
    r.onload = async () => {
      try {
        const b64 = String(r.result || '').split(',')[1] || ''
        const res: any = await api.vlmExtract(b64, f.name)
        changeText(res.latex || '')
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
    if (text.trim() && !report
      && !window.confirm('关闭录入？材料已自动保存为本地草稿，下次打开可恢复。')) return
    onClose()
  }

  const clearDraft = () => {
    try { localStorage.removeItem(DRAFT_KEY) } catch { /* ignore */ }
    setText(''); setBook(DEFAULT_BOOK); setLabel(DEFAULT_LABEL); setYear(DEFAULT_YEAR)
    setRegion(''); setSrcDir(''); setAutoTag(false)
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
  const dryRun = async () => {
    if (!text.trim()) { setErr('先粘贴题目 LaTeX'); return }
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
          const h: any = await api.ingestSource(text)
          if (h?.title && autoLab) { lab = h.title; filled = true }
          if (h?.year && autoYr) { yr = String(h.year); filled = true }
          if (filled) { setLabel(lab); setYear(yr) }
          lastHint.current = { title: h?.title || '', year: h?.year || null }
        } catch { /* 提示接口失败不挡主流程 */ }
      }
      const withFields = () => baseBody({
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
      if (autoTag) {
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
  const showHint = !!hintTitle && (label.trim() !== hintTitle
    || (!!hintYear && year.trim() !== String(hintYear)))

  return (
    <div className={`${closing ? 'anim-slide-r-out' : 'anim-slide-r'} fixed inset-0 z-50
                    flex flex-col border-l border-border bg-surface
                    shadow-[var(--shadow-pop)]`} onClick={closeSafely}>
      <div className="flex min-h-0 flex-1 flex-col" onClick={(e) => e.stopPropagation()}>
        <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-5 py-3.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-ink">
            <FileText size={15} />
          </span>
          <span className="shrink-0 text-[15px] font-semibold tracking-tight text-ink">录入题目</span>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
            粘贴整份试卷 → 自动切题 → 逐题确认 → 勾选入库（干跑什么都不写）
          </span>
          <CloseBtn onClick={closeSafely} className="ml-auto" />
        </header>

        <div className="flex min-h-0 flex-1">
          {/* 左：源材料。出处 / 批量 / LaTeX 三块。 */}
          <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
            <section className="shrink-0">
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

            {/* 批量：AI 只补空标签；逐题在右栏改。 */}
            <section className="shrink-0">
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
            <section className="flex min-h-[240px] flex-1 flex-col">
              {restored && (
                <div className="mb-2 flex items-center gap-2 rounded-md border border-border
                                bg-surface-2 px-2 py-1 text-[10.5px] text-ink-faint">
                  已恢复上次未提交的草稿
                  <button onClick={clearDraft} className="underline hover:text-ink-soft">清空重来</button>
                </div>
              )}
              <div className="mb-2 flex shrink-0 items-center gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">3</span>
                <span className={LABEL}>题目 LaTeX</span>
                <button onClick={() => { changeText(INGEST_SAMPLE); setMsg('已填入示例') }}
                  className="press ml-auto inline-flex h-[26px] items-center gap-1 rounded-lg border
                             border-border bg-surface px-2 text-[11.5px] text-ink-soft
                             hover:border-brand-line hover:text-brand-ink">
                  <FileText size={12} />填入示例
                </button>
                <label className="press inline-flex h-[26px] cursor-pointer items-center gap-1 rounded-lg
                                  border border-border bg-surface px-2 text-[11.5px] text-ink-soft
                                  hover:border-brand-line hover:text-brand-ink">
                  <Upload size={12} />选文件…
                  <input type="file" accept=".tex,.txt" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f) }} />
                </label>
                <label title={vlmReady
                    ? `读图链路已就绪${vlmEngine ? '：' + vlmEngine : ''}`
                    : '点这里会按需启动本地模型（PaddleOCR-VL 认字 → 27B 改格式；首次约 10–60 秒）'}
                  className="press inline-flex h-[26px] cursor-pointer items-center gap-1 rounded-lg
                             border border-brand-line bg-brand-soft px-2 text-[11.5px] font-medium
                             text-brand-ink hover:border-brand">
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                  大模型读图…
                  <span className={`ml-0.5 h-1.5 w-1.5 rounded-full ${
                    vlmReady ? 'bg-has' : 'bg-ink-faint'}`} />
                  <input type="file" accept="image/*,.pdf" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) ocrFile(f) }} />
                </label>
              </div>
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
                  placeholder={'粘贴整份试卷（exam-zh 格式）；\n或把 .tex 文件拖进来；\n或把题目截图 / PDF 拖进来 —— 由本地大模型识别成 LaTeX：\n\n\\title{2025年长沙市高三调研}\n\\begin{question}\n…\n\\end{question}\n\\begin{solution}\n…\n\\end{solution}'}
                  className="h-full w-full resize-none bg-transparent px-4 py-3.5 font-mono
                             text-[12.5px] leading-relaxed outline-none placeholder:text-ink-faint" />
                {drag && (
                  <div className="anim-fade-in pointer-events-none absolute inset-3 flex flex-col items-center
                                  justify-center gap-2 rounded-[var(--radius-card)] border-2 border-dashed
                                  border-brand-line bg-brand-soft/70 text-[12.5px] font-medium text-brand-ink">
                    <Upload size={20} />
                    松手就读 · 图片 / PDF 交给大模型识别
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
                  <button onClick={dryRun} disabled={busy}
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
          </div>

          {/* 右：逐题确认。 */}
          <div className="flex w-[min(880px,62vw)] min-w-[520px] shrink-0 flex-col border-l
                          border-border bg-bg">
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
                    点左边「解析成题」之后，这里会变成一张张题卡：
                  </div>
                  <ol className="space-y-2">
                    {([
                      ['自动切题', '一份卷子里的 question/problem 全切出来，不用一道一道粘'],
                      ['脚本规范 + 查重', '先验证、再修改、最后复核；跟库里已有的题对一遍'],
                      ['qwen3.5 粗标', '考点/难度先填一版，卡片里逐题可改'],
                      ['人拍板', '勾选要入库的题；缺答案/解析/图的会被拦住'],
                    ] as const).map(([t, d], i) => (
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

            {!report && <div className="shrink-0 border-t border-border bg-surface px-4 py-3">
              {pv && (
                <div className="mb-2 rounded-lg border border-border bg-bg px-2.5 py-2
                                text-[11px] leading-relaxed text-ink-faint">
                  {backfill
                    ? <>规则：<b className="font-medium text-ink-soft">补旧题模式</b>
                        → 只更新已有题的空考点/空难度，不新增、不改答案/解析/已有考点。</>
                    : <>规则：库里已有同题，或整题相似 <b className="font-medium text-ink-soft">
                        &gt;{nearThreshold}%</b> → 整题跳过，不新增、不更新（不补解析、不改答案、不并考点）。</>}
                </div>
              )}
              {err && pv && (
                <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-warn-line
                                bg-warn-soft px-2.5 py-2 text-[11px] text-warn">
                  <X size={12} className="mt-[1px] shrink-0" />{err}
                </div>
              )}
              {msg && pv && (
                <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-has-line
                                bg-has-soft px-2.5 py-2 text-[11px] text-has">
                  <Check size={12} className="mt-[1px] shrink-0" />{msg}
                </div>
              )}
              <button onClick={doCommit}
                disabled={busy || tagging || !pv || !selected.length || badSelected.length > 0}
                title={badSelected.length ? '勾选的题里还有不能入库的'
                       : (!selected.length
                          ? (pv?.items.some((it: any) => it.same_key || it.near_dup)
                             ? '库里已有或高度相似，按规则整题跳过' : '先勾选题目')
                          : '')}
                className="press flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand
                           px-4 py-2.5 text-[13px] font-semibold text-white
                           shadow-[var(--shadow-brand)] hover:brightness-105 disabled:opacity-40">
                <Upload size={13} className="shrink-0" />
                {backfill
                  ? (selected.length ? `补标签选中（${selected.length} 道）` : '没有可补的已有题')
                  : (selected.length ? `确认入库选中（${selected.length} 道）` : '没有可入库的新题')}
              </button>
              <div className="mt-1.5 text-center text-[10px] text-ink-faint">
                {backfill
                  ? '补旧题模式 · 只更新已有题的空考点/难度 · 新题不新增、正文不改'
                  : `只写入勾选的题 · 缺答案/解析/图的不让入库 · 已有/相似 >${nearThreshold}% 不更新`}
              </div>
            </div>}
          </div>
        </div>
      </div>
    </div>
  )
}
