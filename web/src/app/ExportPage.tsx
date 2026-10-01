/** 导出页：组卷（LaTeX 试卷）的设置面板。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1：App 曾是全文件最大的组件）。
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  AlertTriangle, Check, ChevronDown, ChevronUp, Copy, Download, ExternalLink, Eye,
  FileText, Loader2, Plus, RefreshCw, Save, Shuffle, Trash2, X,
} from 'lucide-react'
import type { Q, ExportResult } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { CloseBtn } from '@/app/ui'
import { SECTION_LABEL, SHORT_NAME, questionScore, paperScore as totalScore } from '@/lib/paper'
import CompileOverlay, { LATEX_STAGES, COVER_STAGES } from '@/app/CompileOverlay'

/** 输入框的统一长相（左栏里到处都是，写一遍省得十处走样）。 */
const INPUT = 'h-[32px] w-full rounded-lg border border-border bg-bg px-2.5 text-[12.5px] outline-none ' +
  'transition-[border-color,box-shadow] duration-150 placeholder:text-ink-faint ' +
  'focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]'

/** 左栏的一个小节：统一的小节标题 + 统一的行间距。纯排版外壳，不碰任何状态。 */
function Group({ title, hint, className = '', children }: {
  title: string; hint?: ReactNode; className?: string; children: ReactNode
}) {
  return (
    <section className={`space-y-2 ${className}`}>
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] font-semibold tracking-[0.08em] text-ink-faint">{title}</span>
        {hint && <span className="tnum text-[10.5px] text-ink-faint">{hint}</span>}
      </div>
      {children}
    </section>
  )
}

/** 细目表达成度：**这份卷子难度对不对、知识面均不均**。
 *
 *  这是「组一套好模拟卷」唯一看得见的凭据——组完拿实际值跟蓝图对账，
 *  差在哪儿直接标出来。没有它，用户只能自己数 19 道题。 */
function Blueprint({ bp }: { bp: any }) {
  if (!bp) return null
  const D = ['简单题', '中档题', '难题']
  const SHORT: Record<string, string> = { 简单题: '易', 中档题: '中', 难题: '难' }
  const dt = bp.diff_target || {}, da = bp.diff_actual || {}
  const diffOk = D.every((d) => (dt[d] || 0) === (da[d] || 0))
  const tt = bp.topic_target || {}, ta = bp.topic_actual || {}
  const keys = Object.keys(tt)
  const badTopics = keys.filter((t) => (tt[t] || 0) !== (ta[t] || 0))
  const total = D.reduce((s, d) => s + (dt[d] || 0), 0) || 1

  return (
    <div className="rounded-[var(--radius-card)] border border-border bg-bg p-3 space-y-2.5">
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
          细目表达成度
        </span>
        <span className={`ml-auto rounded-full px-1.5 py-[1px] text-[10.5px] font-medium ${
          diffOk && !badTopics.length ? 'bg-has-soft text-has' : 'bg-warn-soft text-warn'}`}>
          {diffOk && !badTopics.length ? '✓ 全部达标'
            : `${(diffOk ? 0 : 1) + badTopics.length} 处没达标`}
        </span>
      </div>

      {/* 难度：**按分值**比。一条三段的横条，上排目标、下排实际 */}
      <div>
        <div className="mb-1 flex items-baseline gap-1.5 text-[10.5px] text-ink-faint">
          <span>难度</span><span className="opacity-70">按分值</span>
        </div>
        <div className="flex h-[6px] w-full overflow-hidden rounded-full bg-muted">
          {D.map((d, i) => (
            <span key={d} title={`目标 ${SHORT[d]} ${dt[d] || 0} 分`}
              className={'bar-grow ' + ['bg-has', 'bg-brand', 'bg-danger'][i] + ' opacity-45'}
              style={{ width: `${(dt[d] || 0) / total * 100}%`,
                       animationDelay: `${i * 60}ms` }} />
          ))}
        </div>
        <div className="mt-1 flex h-[6px] w-full overflow-hidden rounded-full bg-muted">
          {D.map((d, i) => (
            <span key={d} title={`实际 ${SHORT[d]} ${da[d] || 0} 分`}
              className={'bar-grow ' + ['bg-has', 'bg-brand', 'bg-danger'][i]}
              style={{ width: `${(da[d] || 0) / total * 100}%`,
                       animationDelay: `${120 + i * 60}ms` }} />
          ))}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[10.5px]">
          {D.map((d) => (
            <span key={d} className={(dt[d] || 0) === (da[d] || 0)
              ? 'text-ink-faint' : 'font-medium text-warn'}>
              {SHORT[d]} {(da[d] || 0)}/{dt[d] || 0} 分
            </span>
          ))}
        </div>
      </div>

      {/* 章节：只列**没达标**的；都达标就一句话 */}
      <div>
        <div className="mb-1 flex items-baseline gap-1.5 text-[10.5px] text-ink-faint">
          <span>小题章节</span><span className="opacity-70">按题量，照近五年真题占比</span>
        </div>
        {badTopics.length === 0 ? (
          <div className="text-[10.5px] text-ink-faint">
            {keys.length} 个章节都按真题占比出满了
          </div>
        ) : (
          <div className="flex flex-wrap gap-1">
            {badTopics.map((t) => (
              <span key={t} className="rounded bg-warn-soft px-1.5 py-[1px] text-[10.5px] text-warn">
                {t} {ta[t] || 0}/{tt[t] || 0}
              </span>
            ))}
          </div>
        )}
      </div>

      {(bp.notes || []).map((n: string) => (
        <div key={n} className="text-[10.5px] leading-relaxed text-warn">⚠ {n}</div>
      ))}
    </div>
  )
}

/** 一排选项（卷型 / 版式 / 存档种类）：选中的实心胶囊，未选的白底描边。 */
function pickCls(on: boolean) {
  return `press inline-flex items-center justify-center gap-1 rounded-full border px-2.5 py-[5px]
          text-[12.5px] font-medium transition-colors ${on
    ? 'border-brand bg-brand text-white'
    : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`
}

type Mode = 'gaokao' | 'test' | 'coverage'

/** 卷型对应的默认卷面标题。
 *
 *  这个名字会**印在卷面上**，也是导出文件名的前缀，所以每种卷型给一个
 *  说得清自己的名字——而不是三种卷型混用同一个。 */
const MODE_TITLE: Record<Mode, string> = {
  gaokao: '数学试卷', test: '测试卷', coverage: '考点覆盖卷',
}

/** 时间戳 `20260923_2034`。
 *
 *  和后端 `amti/export.py` 的 `%Y%m%d_%H%M` **必须一致**——界面上的默认名
 *  就是把后端那条「留空则用 标题_时间戳」的规则**提前显示出来**，
 *  两边格式不一样的话，用户看到的和落盘的就是两个名字。
 *  用本地时间：老师看的是自己表上的时间。 */
function stamp(d = new Date()) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}`
}

/** 默认文件名 = 「卷面标题（没写就用卷型的默认名）+ 时间戳」。 */
function defaultOut(title: string, mode: Mode) {
  return `${title.trim() || MODE_TITLE[mode]}_${stamp()}`
}

/** 后端那行 `re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", out).strip("_")` 的**预览版**。
 *
 *  只用来在界面上提前显示「会存成什么名字」，**落盘的名字以后端为准**
 *  （响应里的 `res.name` 才是真的）。之所以要在前端也算一遍：文件名里有
 *  斜杠、冒号这类字符时，用户得在点导出**之前**就知道它会被换掉。 */
function safeName(out: string) {
  return out.replace(/[^\w\u4e00-\u9fff-]+/g, '_').replace(/^_+|_+$/g, '') || '试卷'
}

export default function ExportPage({ init, pool, from, filters, onClose, closing }: {
  init: Q[]; pool: Q[]; from: string
  filters: Record<string, string>; onClose: () => void
  /** 正在播退场动画（父组件用 `useUnmount` 控制，播完才真卸载）。 */
  closing?: boolean
}) {
  const [list, setList] = useState<Q[]>(init)
  const poolN = pool.length
  /** 卷面标题：**默认就填好**（和下面的文件名同一套规矩）。
   *
   *  以前这里是空的 + 一句 placeholder「留空用…」，而文件名却有默认值——
   *  两栏不对称，用户还得先自己给卷子起个名。现在打开就是
   *  「数学试卷 / 测试卷 / 考点覆盖卷」，想改就地改。 */
  const [title, setTitle] = useState(MODE_TITLE.gaokao)
  /** 用户手改过卷面标题没有。没改 → 换卷型时标题跟着换；改了 → 一切以他写的为准。 */
  const [titleEdited, setTitleEdited] = useState(false)
  // **导出文件名默认就填好**（卷面标题_时间戳），不用先去别处想名字。
  // 老规矩「留空则用 标题_时间戳」还留着：清空这个框，后端照旧兜底。
  const [out, setOut] = useState(() => defaultOut(MODE_TITLE.gaokao, 'gaokao'))
  /** 用户**手动改过**文件名没有。
   *
   *  没有 → 标题/卷型一变，文件名跟着变（默认名是派生的，就该跟着走）；
   *  改过 → 一切以他写的为准，程序不再插手（只在旁边留一个「恢复默认」）。
   *  这就是「给了默认值、又支持就地改」的分寸：默认值不能像个幽灵
   *  一样在你改完之后又把你的输入覆盖掉。 */
  const [outEdited, setOutEdited] = useState(false)
  const [mode, setMode] = useState<Mode>('gaokao')
  // **答案与解析放不放卷末**。真高考卷是"卷面只有题，答案另附"，
  // 所以留空版（学生做）时默认勾上。
  const [ansAtEnd, setAnsAtEnd] = useState(true)
  // 是否在卷面上印答案
  const [showAns, setShowAns] = useState(false)
  const [sep, setSep] = useState('0.6em')
  const [blank, setBlank] = useState('4')
  const [layout, setLayoutRaw] = useState<'compact' | 'roomy'>('roomy')
  /** 忙什么。**必须分开**：组卷是"挑题"（几秒，没有 LaTeX 阶段），
   *  编译是"跑两遍 xelatex"（几十秒，有阶段）。早先共用一个 `busy`，
   *  于是点「按覆盖率组卷」也会弹出「正在编译 PDF」+ 一串 xelatex 阶段，
   *  而且 roll() 没设 `busySince`，秒表直接显示 57 年。 */
  const [busyKind, setBusyKind] = useState<'none' | 'gen' | 'compile'>('none')
  const busy = busyKind !== 'none'
  const [res, setRes] = useState<ExportResult | null>(null)
  const [err, setErr] = useState('')
  const [genMsg, setGenMsg] = useState('')
  /** 组卷后的**细目表达成度**（目标 vs 实际）。只有 gaokao 模式会给。 */
  const [bp, setBp] = useState<any>(null)
  /** 导出位置（后端说了算，别再写死「试卷/」）。 */
  const [outDir, setOutDir] = useState({ name: '试卷', abs: '' })
  useEffect(() => {
    api.settings()
      .then((d: any) => setOutDir({ name: d.out_name || '试卷', abs: d.out_dir || '' }))
      .catch(() => {})     // 取不到就退回默认文案，不打断导出
  }, [])
  // 组卷方案（`coverage`）：**要几道题、想覆盖多少考点**。
  // 目标是「尽量用最少的题把考点铺满」，所以先定题量再谈覆盖率。
  const [want, setWant] = useState('46')
  const [cov, setCov] = useState('0.9')
  /** 覆盖卷要不要保住高考卷面的题型比例。
   *
   *  不保的话贪心只认"考点个数"，实测 46 道题能挑出 23 道解答题——
   *  因为解答题平均挂 2.34 个考点，比单选题的 1.74 高，对目标函数而言
   *  它是"对的"，但那卷子没法用。保住的代价约 2.6 个百分点，
   *  组卷说明里会把这个代价报出来（后端多跑一遍不限题型的）。 */
  const [keepStruct, setKeepStruct] = useState(true)
  const [saved, setSaved] = useState<any[]>([])
  const [saveName, setSaveName] = useState('')
  const [saveKind, setSaveKind] = useState<'试卷' | '合集'>('试卷')
  // **只有点按钮才编译**：进页面不编译，之后改参数、重新组卷、拖动排序、
  // 删题也都不编译。此前是「编译过一次之后，以上动作都防抖 800ms 自动重编」，
  // 随机组卷/排序时会莫名跑起 xelatex——现在编译只在点按钮时发生。
  // `compiled` 仅用于把按钮文案从「编译预览」切成「重新编译」。
  const [compiled, setCompiled] = useState(false)
  // 编译开始时刻。遮罩上的秒表靠它算——**秒表在跳，就说明进程还活着**
  const [busySince, setBusySince] = useState(0)

  const answered = list.filter((q) => q.flags['解析']).length
  const score = totalScore(list)

  // 换卷型时，没手改过的卷面标题跟着换
  useEffect(() => {
    if (!titleEdited) setTitle(MODE_TITLE[mode])
  }, [mode, titleEdited])

  // 卷面标题或卷型一变，默认文件名跟着变（前提是用户没自己改过，见 outEdited）
  useEffect(() => {
    if (!outEdited) setOut(defaultOut(title, mode))
  }, [title, mode, outEdited])

  /**
   * 版式预设。两个数是**起点**，选完还能在上面单独调。
   *
   * 紧凑版：题目紧排、解答题不留白——适合「题目与答题卡分开」的考法，省纸。
   * 留空版：每题间距 **8em** 起、解答题留 5cm——**直接在卷面上写**。
   *         `question/bottom-sep` 管的是每题之后的空白，所以选择填空
   *         也会跟着松，正好够在旁边写过程。
   */
  const setLayout = (v: 'compact' | 'roomy') => {
    setLayoutRaw(v)
    if (v === 'compact') { setSep('0.3em'); setBlank('0') }
    else { setSep('8em'); setBlank('0') }      // 0 = 按难度自动（3/5/8cm）
  }

  const run = () => {
    if (!list.length) { setRes(null); return }
    setBusyKind('compile'); setBusySince(Date.now()); setErr('')
    const keys = list.map((q) => q.key)

    // 没手改过文件名 → 把时间戳刷成「此刻」再导出。面板开着十几分钟才点导出，
    // 不该落一个十几分钟前的名字。刷新的同时更新输入框，
    // 保证**屏幕上显示的就是将要落盘的**。
    const outNow = outEdited ? out : defaultOut(title, mode)
    if (!outEdited) setOut(outNow)

    // **「组卷方案」和「卷面格式」是两回事，两个接口认的模式不是一套。**
    // `/api/generate` 认 gaokao / test / coverage（怎么挑题），
    // `/api/export`  只认 gaokao / test（怎么排版）。
    // 考点覆盖卷挑完题之后，卷面就该按**测试卷**排（小字列考点、每题标难度）——
    // 它本来就是"考点专练"。早先直接把 `coverage` 透传给导出接口，
    // 结果一点「导出」就 HTTP 400「未知卷型 'coverage'」，压根导不出来。
    const renderMode = mode === 'coverage' ? 'test' : mode
    const call = api.export({
          title, out: outNow, mode: renderMode, show_answers: showAns, bottom_sep: sep,
          problem_blank_cm: Number(blank) || 0, compile: true,
          keys, answers_at_end: ansAtEnd,
        })

    call.then((d) => {
      if (d.detail) { setErr(String(d.detail)); setRes(null) }
      else setRes(d)
    }).catch((e) => setErr(String(e))).finally(() => setBusyKind('none'))
  }

  // 这里以前挂着一个 800ms 防抖的自动重编 effect：只要 `compiled` 为真，
  // 改标题/版式/换题/排序都会在背后自动跑一遍 xelatex。已按要求删除——
  // 现在**只有**点「编译预览」或「导出并保存」才编译，不再有隐式触发。

  /** 随机组卷：`gaokao` 按卷面结构填位置；`coverage` 按考点覆盖率挑题。 */
  const roll = () => {
    setBusyKind('gen'); setBusySince(Date.now()); setErr(''); setGenMsg(''); setBp(null)
    api.generate({ ...filters, mode, seed: Math.floor(Math.random() * 1e9),
                   want: Number(want) || 19, coverage: Number(cov) || 0.9,
                   keep_structure: keepStruct })
      .then((d) => {
        if (d.detail) { setErr(String(d.detail)); return }
        setList(d.items || [])
        const rep = d.report || {}
        setBp(rep.blueprint || null)
        const mixTxt = rep.mix
          ? Object.entries(rep.mix).filter(([, n]) => n)
              .map(([t, n]) => `${SHORT_NAME[t] || t}${n}`).join(' ')
          : ''
        // **不要再重复"多少题多少分"**——弹层头部左边已经算过一份了，
        // 这里只说"怎么挑的、挑成什么样"。
        setGenMsg([
          mixTxt,
          rep.ratio != null ? `覆盖 ${Math.round(rep.ratio * 100)}%（${rep.covered}/${rep.reachable}）` : '',
          // 保结构的代价：**明说**，用户才知道这个开关值不值
          rep.ratio_free ? `不限题型可到 ${Math.round(rep.ratio_free * 100)}%` : '',
          rep.unfilled?.length ? `⚠ ${rep.unfilled.length} 个位置没填上` : '',
          rep.note || '',
        ].filter(Boolean).join(' · '))
      })
      .catch((e) => setErr(String(e))).finally(() => setBusyKind('none'))
  }

  /* ── 存档 / 合集 ──────────────────────────────────
     存档只记题号，所以**随时能原样还原**（题目改了也还原成最新版）。
     加载走 `/api/questions?keys=…`，顺序按存档里的顺序。 */
  const refreshSaved = () =>
    api.papers().then((d) => setSaved(d.items || [])).catch(() => {})
  useEffect(() => { refreshSaved() }, [])

  const loadSaved = (name: string) => {
    setBusyKind('gen'); setBusySince(Date.now()); setErr(''); setGenMsg(''); setBp(null)
    fetch('/api/papers/' + encodeURIComponent(name)).then((r) => r.json())
      .then((d) => {
        if (!d || !d.keys) { setErr('没有这份存档'); return }
        const p = d.params || {}
        if (p.mode) setMode(p.mode)
        if (p.show_answers != null) setShowAns(!!p.show_answers)
        if (p.bottom_sep) setSep(String(p.bottom_sep))
        if (p.problem_blank_cm != null) setBlank(String(p.problem_blank_cm))
        if (d.title) setTitle(d.title)
        return fetch('/api/questions?' + new URLSearchParams({
          keys: d.keys.join(','), limit: String(Math.max(1, d.keys.length)),
        })).then((r) => r.json()).then((q) => {
          setList(q.items || [])
          setGenMsg(`载入「${d.name}」 ${(q.items || []).length}/${d.keys.length} 题`)
        })
      })
      .catch((e) => setErr(String(e))).finally(() => setBusyKind('none'))
  }

  const saveCurrent = () => {
    if (!saveName.trim()) { setErr('得给个名字'); return }
    if (!list.length) { setErr('卷子是空的'); return }
    setErr('')
    api.paperSave({
      name: saveName.trim(), keys: list.map((q) => q.key), title: title || saveName.trim(),
      mode, kind: saveKind, note: `${list.length} 题`,
      params: { mode, show_answers: showAns, bottom_sep: sep,
                problem_blank_cm: Number(blank) || 0 },
    }).then(() => { setSaveName(''); setGenMsg('已存档'); refreshSaved() })
      .catch((e) => setErr(String(e)))
  }

  const dropSaved = (name: string) =>
    api.paperDelete(name).then(() => refreshSaved()).catch(() => {})

  const move = (i: number, d: number) => setList((l) => {
    const n = [...l]; const j = i + d
    if (j < 0 || j >= n.length) return l
    ;[n[i], n[j]] = [n[j], n[i]]; return n
  })

  return (
    <div className={`${closing ? 'anim-fade-out' : 'anim-fade-in'} fixed inset-0 z-50
                    flex items-center justify-center bg-ink/25 p-5 backdrop-blur-[2px]`}>
      <div className={`${closing ? 'anim-pop-out' : 'pop-c'} flex h-[min(880px,92vh)]
                      w-[min(1220px,95vw)] flex-col overflow-hidden
                      rounded-[var(--radius-pop)] border border-border bg-surface
                      shadow-[var(--shadow-pop)]`}>

        {/* ── 头 ── */}
        <header className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-3">
          <span className="text-[15px] font-semibold tracking-tight">组卷导出</span>
          <span className="tnum text-[11.5px] text-ink-faint">
            {list.length} 题 · {score} 分 · 有解析 {answered}/{list.length}
          </span>
          {genMsg && <span className="min-w-0 truncate text-[11.5px] text-brand-ink">{genMsg}</span>}
          <CloseBtn onClick={onClose} className="ml-auto" />
        </header>

        <div className="flex min-h-0 flex-1">
          {/* ── 左：设置 ── */}
          <div className="w-[288px] shrink-0 space-y-5 overflow-y-auto border-r border-border
                          bg-surface px-4 py-4">
            <Group title="卷型">
              <div className="grid grid-cols-2 gap-1.5">
                {([['gaokao', '高考卷'], ['test', '纯测试题'],
                   ['coverage', '考点覆盖卷']] as const).map(([v, label]) => (
                  <button key={v} onClick={() => setMode(v)} className={pickCls(mode === v)}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="text-[11px] leading-relaxed text-ink-faint">
                {mode === 'gaokao'
                  ? '与高考真题一致：信息行 + 注意事项 + 四大题分节，卷面不标难度'
                  : mode === 'test'
                  ? '考点专练：小字列出考点，每题标出难度等级，带上出处'
                  : '按考点覆盖率挑题：用尽量少的题把考点铺满，挑完易→难排好'}
              </div>
            </Group>

            {mode === 'coverage' && (
              <Group title="组卷方案"
                className="rounded-[var(--radius-card)] border border-border bg-bg p-3.5">
                <label className="block space-y-1">
                  <span className="block text-[11.5px] text-ink-soft">题量</span>
                  <input value={want} onChange={(e) => setWant(e.target.value)}
                    className={`${INPUT} tnum`} />
                </label>
                <label className="block space-y-1">
                  <span className="block text-[11.5px] text-ink-soft">目标覆盖率</span>
                  <input value={cov} onChange={(e) => setCov(e.target.value)}
                    className={`${INPUT} tnum`} />
                </label>
                <label className={`press inline-flex cursor-pointer items-center gap-1.5 rounded-full
                                   border px-2.5 py-[5px] text-[12.5px] font-medium transition-colors
                                   focus-within:ring-2 focus-within:ring-brand/25 ${
                  keepStruct ? 'border-brand bg-brand text-white'
                             : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                  <input type="checkbox" checked={keepStruct}
                    onChange={(e) => setKeepStruct(e.target.checked)} className="sr-only" />
                  <Check size={12} strokeWidth={2.8}
                    className={keepStruct ? 'shrink-0' : 'shrink-0 opacity-30'} />
                  保持高考卷面比例
                </label>
                <div className="text-[11px] leading-relaxed text-ink-faint">
                  参考：19 题 ≈ 38%，46 题 ≈ 84%，60 题 ≈ 97%，80 题铺满。
                  覆盖率按当前筛选出的 {poolN} 道里能覆盖到的考点算。
                </div>
                <div className="text-[11px] leading-relaxed text-ink-faint">
                  {keepStruct
                    ? '题型按高考比例缩放（46 题 → 单选 20 · 多选 7 · 填空 7 · 解答 12）。'
                      + '贪心只认考点个数，不约束的话会挑出一半解答题（解答题考点密度最高）。'
                    : '⚠ 不限题型：能多覆盖约 2~3 个百分点的考点，但题型分布会失衡'
                      + '（46 题实测挑出 23 道解答题）。'}
                </div>
              </Group>
            )}

            <div className="space-y-2">
              <button onClick={roll} disabled={busy}
                className="press flex w-full items-center justify-center gap-1.5 rounded-lg border
                           border-brand-line bg-brand-soft px-3 py-2 text-[12.5px] font-medium
                           text-brand-ink transition-colors hover:bg-brand-soft/70 disabled:opacity-50">
                <Shuffle size={13} />
                {mode === 'gaokao' ? '随机组卷（按高考结构）'
                  : mode === 'coverage' ? '按覆盖率组卷' : '取筛选结果'}
              </button>
              {poolN > 0 && (
                <button onClick={() => setList(pool)} disabled={busy}
                  className="press flex w-full items-center justify-center gap-1.5 rounded-lg border
                             border-border bg-surface px-3 py-2 text-[11.5px] text-ink-soft
                             transition-colors hover:border-brand-line hover:text-brand-ink
                             disabled:opacity-50">
                  <Plus size={12} />把筛选到的 {poolN} 道全加进来
                </button>
              )}
              <div className="text-[11px] leading-relaxed text-ink-faint">
                {mode === 'gaokao'
                  ? '8 单选 + 3 多选 + 3 填空 + 5 解答，解答题按「三角/数列 → 概率统计 → 立体几何 → 解析几何 → 导数」排布'
                  : '测试题不做结构约束，用当前筛选到的题目'}
              </div>
            </div>

            <Blueprint bp={bp} />

            <Group title="卷面标题">
              <div className="flex items-center gap-1.5">
                <input value={title}
                  onChange={(e) => { setTitle(e.target.value); setTitleEdited(true) }}
                  placeholder={`留空用「${MODE_TITLE[mode]}」`}
                  className={`${INPUT} flex-1`} />
                {titleEdited && (
                  <button onClick={() => { setTitleEdited(false); setTitle(MODE_TITLE[mode]) }}
                    title="改回这个卷型的默认标题"
                    className="press icon-btn h-8 w-8 shrink-0 border border-border">
                    <RefreshCw size={13} />
                  </button>
                )}
              </div>
              {/* 这个名字会**印在卷面第一行**，也是文件名的前缀——说清它去哪了 */}
              <div className="text-[10.5px] text-ink-faint">
                印在卷面上（含答案页）；导出文件名也用它做前缀
              </div>
            </Group>

            <Group title="导出文件名">
              {/* **默认就填好，随时可以就地改。**
                  以前这里是个空框 + 一句 placeholder「留空用 标题_时间戳」，
                  等于让用户先自己猜一个名字，或者干脆不管、导完再去找文件。
                  现在默认名直接摆在这儿：想用就往下点，想改就当场打字。 */}
              <div className="flex items-center gap-1.5">
                <input value={out}
                  onChange={(e) => { setOut(e.target.value); setOutEdited(true) }}
                  placeholder={`留空用「${MODE_TITLE[mode]}_时间戳」`}
                  className={`${INPUT} flex-1`} />
                {outEdited && (
                  <button onClick={() => { setOutEdited(false); setOut(defaultOut(title, mode)) }}
                    title="改回「卷面标题_时间戳」的默认名"
                    className="press icon-btn h-8 w-8 shrink-0 border border-border">
                    <RefreshCw size={13} />
                  </button>
                )}
              </div>
              {/* 文件名里的 `/ \ : *` 这些字符后端会换成下划线——**提前告诉他**，
                  不要等导完在文件夹里找不到。斜杠还会被当成子目录。 */}
              <div className="flex items-baseline gap-1.5 text-[10.5px] text-ink-faint">
                <span className="shrink-0">存为</span>
                <code className="min-w-0 flex-1 truncate font-mono text-ink-soft"
                  title={`${outDir.abs || outDir.name}/${safeName(out)}.pdf`}>
                  {outDir.name}/{safeName(out)}.pdf
                </code>
                {outEdited && <span className="shrink-0 text-brand-ink">已手改</span>}
              </div>
            </Group>

            {/* ── 答案：两个开关是**互斥**的（勾一个就撤另一个），
                   但语义上是两件独立的事，所以不做成单选组。 ── */}
            <div className="space-y-2">
              <div className="text-[11px] font-semibold tracking-[0.08em] text-ink-faint">
                答案与解析
              </div>
              <div className="flex flex-col gap-1.5">
                <label className={`press inline-flex cursor-pointer items-center gap-1.5 rounded-full
                                   border px-2.5 py-[5px] text-[12.5px] font-medium transition-colors
                                   focus-within:ring-2 focus-within:ring-brand/25 ${
                  showAns ? 'border-brand bg-brand text-white'
                          : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                  <input type="checkbox" checked={showAns}
                    onChange={(e) => { setShowAns(e.target.checked)
                                        if (e.target.checked) setAnsAtEnd(false) }}
                    className="sr-only" />
                  <Check size={12} strokeWidth={2.8} className={showAns ? 'shrink-0' : 'shrink-0 opacity-30'} />
                  答案印在题目上（答案卷）
                </label>
                <label className={`press inline-flex cursor-pointer items-center gap-1.5 rounded-full
                                   border px-2.5 py-[5px] text-[12.5px] font-medium transition-colors
                                   focus-within:ring-2 focus-within:ring-brand/25 ${
                  ansAtEnd ? 'border-brand bg-brand text-white'
                           : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                  <input type="checkbox" checked={ansAtEnd}
                    onChange={(e) => { setAnsAtEnd(e.target.checked)
                                        if (e.target.checked) setShowAns(false) }}
                    className="sr-only" />
                  <Check size={12} strokeWidth={2.8} className={ansAtEnd ? 'shrink-0' : 'shrink-0 opacity-30'} />
                  <span>答案与解析放<b>卷末</b>
                    <span className={`ml-1 text-[10.5px] ${ansAtEnd ? 'text-white/75' : 'text-ink-faint'}`}>
                      （真高考卷的做法）
                    </span></span>
                </label>
              </div>
              <div className="text-[11px] leading-relaxed text-ink-faint">
                两个都不勾＝学生卷：卷面干净、解答题留白，没有答案
              </div>
              {showAns && answered < list.length && (
                <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                bg-warn-soft px-2.5 py-2 text-[11px] leading-relaxed text-warn">
                  <AlertTriangle size={12} className="mt-[2px] shrink-0" />
                  <span>本卷 {answered}/{list.length} 题有解析，其余题只有题干</span>
                </div>
              )}
            </div>

            {/* 版式：一键决定「每题之间留多少地方」。
                紧凑版是省纸的（作答另用答题卡），留空版直接在卷面上写。 */}
            <Group title="版式">
              <div className="grid grid-cols-2 gap-1.5">
                {([['compact', '紧凑版'], ['roomy', '留空版']] as const).map(([v, label]) => (
                  <button key={v} onClick={() => setLayout(v)} className={pickCls(layout === v)}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="text-[11px] leading-relaxed text-ink-faint">
                {layout === 'compact'
                  ? '题目紧排、不留解答位，省纸（作答另用纸）'
                  : '每题间距 8em 起、解答题留白，可直接在卷面上作答'}
              </div>
            </Group>

            <Group title="间距与留白">
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <div className="text-[11px] text-ink-soft">
                    题目间距 <span className="text-ink-faint">（带单位）</span>
                  </div>
                  <input value={sep} onChange={(e) => setSep(e.target.value)}
                    placeholder="0.6em" className={`${INPUT} font-mono`} />
                </div>
                <div className="space-y-1">
                  <div className="text-[11px] text-ink-soft">
                    解答留白 cm <span className="text-ink-faint">（0 = 按难度）</span>
                  </div>
                  <input value={blank} onChange={(e) => setBlank(e.target.value)}
                    placeholder="0" className={`${INPUT} tnum font-mono`} />
                </div>
              </div>
              <div className="text-[11px] leading-relaxed text-ink-faint">
                留白填 <b>0</b>：按难度自动留 —— 简单 3 · 中档 5 · 难题 8 cm。
                填正数则一律用它。
                间距要写单位，如 <b>0.6em</b>、<b>8pt</b>；只填数字按 pt 算。
              </div>
            </Group>

            {/* 存档 / 合集：出过的卷子留个名，以后一键还原。
                存档里只记**题号**——题目后来改了，还原出来就是最新版。 */}
            <div className="border-t border-border pt-4">
              <Group title="存档 / 合集" hint={`${saved.length} 份`}>
                <div className="flex gap-1.5">
                  {(['试卷', '合集'] as const).map((k) => (
                    <button key={k} onClick={() => setSaveKind(k)} className={pickCls(saveKind === k)}>
                      {k}
                    </button>
                  ))}
                </div>
                <div className="flex gap-1.5">
                  <input value={saveName} onChange={(e) => setSaveName(e.target.value)}
                    placeholder={saveKind === '合集' ? '如「椭圆专练」' : '如「2026 模拟三」'}
                    className={`${INPUT} min-w-0 flex-1`} />
                  <button onClick={saveCurrent} disabled={!list.length}
                    className="press inline-flex shrink-0 items-center gap-1 rounded-lg border
                               border-border bg-surface px-2.5 text-[11.5px] text-ink-soft
                               transition-colors hover:border-brand-line hover:text-brand-ink
                               disabled:opacity-40">
                    <Save size={12} />存下
                  </button>
                </div>
                {saved.length > 0 && (
                  <div className="anim-fade-in max-h-[190px] space-y-1 overflow-y-auto pt-0.5">
                    {saved.map((p) => (
                      <div key={p.name}
                        className="group flex items-center gap-1.5 rounded-lg border border-border
                                   bg-bg px-2.5 py-1.5 transition-colors hover:border-brand-line">
                        <button onClick={() => loadSaved(p.name)} className="min-w-0 flex-1 text-left">
                          <div className="truncate text-[11.5px] text-ink">{p.name}</div>
                          <div className="tnum truncate text-[10.5px] text-ink-faint">
                            {p.kind || '试卷'} · {(p.keys?.length ?? 0)} 题 · {(p.at || '').slice(5, 16)}
                          </div>
                        </button>
                        <button onClick={() => dropSaved(p.name)} title="删掉这份存档"
                          className="shrink-0 rounded-md p-1 text-ink-faint opacity-0 transition-opacity
                                     hover:bg-danger-soft hover:text-danger group-hover:opacity-100">
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </Group>
            </div>

            {/* ── 编译 / 导出 ── */}
            <div className="space-y-2 border-t border-border pt-4">
              <div className="flex gap-2">
                <button onClick={() => { setCompiled(true); run() }}
                  disabled={busy || !list.length}
                  className="press flex flex-1 items-center justify-center gap-1.5 rounded-lg border
                             border-brand-line bg-brand-soft px-3 py-2 text-[12.5px] font-medium
                             text-brand-ink transition-colors hover:bg-brand-soft/70
                             disabled:opacity-40">
                  {busy ? <Loader2 size={13} className="animate-spin" />
                    : compiled ? <RefreshCw size={13} /> : <Eye size={13} />}
                  {busy ? '编译中…' : compiled ? '重新编译' : '编译预览'}
                </button>
                <button onClick={() => { setCompiled(true); run() }}
                  disabled={busy || !list.length}
                  className="press flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-brand
                             px-3 py-2 text-[12.5px] font-semibold text-white
                             shadow-[var(--shadow-brand)] transition-[filter]
                             hover:brightness-105 disabled:opacity-40">
                  <Download size={13} />
                  导出并保存
                </button>
              </div>

              {err && (
                <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                bg-warn-soft px-2.5 py-2 text-[11.5px] leading-relaxed text-warn">
                  <AlertTriangle size={12} className="mt-[2px] shrink-0" />
                  <span className="min-w-0 break-words">{err}</span>
                </div>
              )}

              {res?.ok && (
                <div className="anim-fade-up space-y-2 rounded-[var(--radius-card)] border
                                border-has-line bg-has-soft/50 p-3">
                  <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-has">
                    <Check size={12} strokeWidth={3} className="shrink-0" />{res.saved_hint}
                  </div>
                  <div className="break-all rounded-md bg-surface/70 px-2 py-1.5 font-mono
                                  text-[11.5px] leading-relaxed text-ink-faint">
                    {res.pdf_abs || res.tex_abs}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <button onClick={() => navigator.clipboard?.writeText(res.pdf_abs || res.tex_abs)}
                      className="press inline-flex items-center gap-1 rounded-md border border-border
                                 bg-surface px-2 py-1 text-[11px] text-ink-soft transition-colors
                                 hover:border-border-strong hover:text-ink">
                      <Copy size={11} />复制路径
                    </button>
                    <button onClick={() => api.reveal(res.pdf_abs || res.tex_abs).catch(reportErr)}
                      className="press inline-flex items-center gap-1 rounded-md border border-border
                                 bg-surface px-2 py-1 text-[11px] text-ink-soft transition-colors
                                 hover:border-border-strong hover:text-ink">
                      <ExternalLink size={11} />在访达中显示
                    </button>
                  </div>
                </div>
              )}

              {res && !res.ok && res.log && (
                <div className="whitespace-pre-wrap rounded-lg border border-warn-line bg-warn-soft
                                p-2.5 font-mono text-[10.5px] leading-relaxed text-warn">
                  {res.log}
                </div>
              )}
            </div>
          </div>

          {/* ── 中：卷子 ── */}
          <div className="flex w-[336px] shrink-0 flex-col border-r border-border bg-surface-2">
            <div className="flex shrink-0 items-center gap-2 border-b border-border px-3.5 py-2.5
                            text-[11.5px] text-ink-faint">
              <span>卷子内容</span>
              <span className="ml-auto min-w-0 truncate" title={from}>{from}</span>
              {list.length > 0 && (
                <button onClick={() => setList([])}
                  className="press shrink-0 rounded-md border border-border px-1.5 py-[2px]
                             text-[10.5px] transition-colors hover:border-warn-line hover:bg-warn-soft
                             hover:text-warn">
                  清空
                </button>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
              {list.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-6
                                text-center text-ink-faint">
                  <FileText size={20} className="text-border-strong" />
                  <span className="text-[12.5px]">卷子是空的</span>
                  <span className="text-[11.5px] leading-relaxed">
                    点上面的「随机组卷」，或回工作台勾选题目
                  </span>
                </div>
              ) : SECTION_LABEL.map(([t, label]) => {
                const items = list.filter((q) => q.type === t)
                if (!items.length) return null
                const sc = totalScore(items)
                return (
                  <div key={t} className="mb-4 last:mb-0">
                    <div className="mb-1.5 flex items-baseline gap-2 text-[11px]">
                      <span className="font-semibold text-ink">{label}</span>
                      <span className="tnum text-ink-faint">{items.length} 题 · {sc} 分</span>
                    </div>
                    <div className="space-y-1">
                      {items.map((q, qi) => {
                        const gi = list.indexOf(q)
                        return (
                          <div key={q.key}
                            className="group flex items-center gap-2 rounded-lg border border-border
                                       bg-surface px-2.5 py-1.5 transition-colors
                                       hover:border-brand-line">
                            <span className="tnum w-4 shrink-0 text-right text-[10.5px] text-ink-faint">
                              {list.filter((x) => x.type === t).indexOf(q) + 1}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[11.5px] font-semibold text-ink-soft">
                                {q.point_titles[0] || q.type_label}
                              </div>
                              <div className="truncate font-mono text-[10.5px] text-ink-faint">
                                {q.key}
                              </div>
                            </div>
                            <span className="tnum shrink-0 text-[10.5px] text-ink-faint">
                              {questionScore(q.type, qi, items.length)}分
                            </span>
                            <div className="flex shrink-0 flex-col opacity-0 transition-opacity
                                            group-hover:opacity-100">
                              <button onClick={() => move(gi, -1)} title="上移"
                                className="rounded p-0.5 text-ink-faint hover:bg-brand-soft hover:text-brand-ink">
                                <ChevronUp size={12} />
                              </button>
                              <button onClick={() => move(gi, 1)} title="下移"
                                className="rounded p-0.5 text-ink-faint hover:bg-brand-soft hover:text-brand-ink">
                                <ChevronDown size={12} />
                              </button>
                            </div>
                            <button onClick={() => setList((l) => l.filter((x) => x.key !== q.key))}
                              title="从卷子移除"
                              className="shrink-0 rounded-md p-1 text-ink-faint transition-colors
                                         hover:bg-danger-soft hover:text-danger">
                              <X size={13} />
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* ── 右：预览 ── */}
          <div className="flex min-w-0 flex-1 flex-col bg-surface-2 p-3">
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-[var(--radius-card)]
                            border border-border bg-bg shadow-[var(--shadow-card)]">
              {/* 编译遮罩：**盖住整块预览区**。原先只有右上角一小行字，
                  人会以为卡死了反复点。现在有秒表在跳、有进度条在动、
                  还分阶段说清楚到哪一步了。 */}
              {busy && (
                <CompileOverlay since={busySince}
                  label={busyKind === 'compile' ? '正在编译 PDF'
                       : mode === 'coverage' ? '正在按覆盖率挑题' : '正在随机组卷'}
                  stages={busyKind === 'compile' ? LATEX_STAGES : COVER_STAGES}
                  hint={busyKind === 'compile'
                    ? '两遍 xelatex，题越多越慢；中途不用重复点，编译完会自动出预览'
                    : '在筛选出的题目里挑，几秒钟；中途不用重复点'} />
              )}
              {res?.pdf_abs ? (
                <iframe key={res.pdf_abs}
                  src={'/api/pdf?path=' + encodeURIComponent(res.name + '.pdf')}
                  className="h-full w-full" title="预览" />
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-2.5 px-6
                                text-center text-ink-faint">
                  {busy ? <Loader2 size={20} className="animate-spin text-brand/60" />
                    : !compiled ? <FileText size={20} className="text-border-strong" />
                      : <AlertTriangle size={20} className="text-warn/70" />}
                  <span className="text-[12.5px] leading-relaxed">
                    {busy ? '正在生成预览…'
                          : !list.length ? '卷子是空的，先组卷'
                          : !compiled ? '点左边「编译预览」生成 PDF'
                                      : '编译没成功，看左边的报错'}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}




/* ══ 导出抽屉 ══════════════════════════════════════ */
