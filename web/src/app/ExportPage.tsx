/** 导出页：组卷（LaTeX 试卷）与讲义（Slidev）的设置面板。
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
import { SCORE, SECTION_LABEL } from '@/lib/paper'
import CompileOverlay, { LATEX_STAGES } from '@/app/CompileOverlay'

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

/** 一排选项（卷型 / 版式 / 存档种类）：选中的实心胶囊，未选的白底描边。 */
function pickCls(on: boolean) {
  return `press inline-flex items-center justify-center gap-1 rounded-full border px-2.5 py-[5px]
          text-[12.5px] font-medium transition-colors ${on
    ? 'border-brand bg-brand text-white'
    : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`
}

export default function ExportPage({ init, pool, from, filters, onClose }: {
  init: Q[]; pool: Q[]; from: string
  filters: Record<string, string>; onClose: () => void
}) {
  const [list, setList] = useState<Q[]>(init)
  const poolN = pool.length
  const [title, setTitle] = useState('')
  const [out, setOut] = useState('')
  const [mode, setMode] = useState<'gaokao' | 'test' | 'coverage' | 'handout'>('gaokao')
  // **答案与解析放不放卷末**。真高考卷是"卷面只有题，答案另附"，
  // 所以留空版（学生做）时默认勾上，讲义版（要看解析）时自动取消。
  const [ansAtEnd, setAnsAtEnd] = useState(true)
  // 讲义是否印答案（A4 讲义用；上一轮我用正则删 Slidev 参数时误删过它）
  const [showAns, setShowAns] = useState(false)
  // 讲义字号。exam-zh 题干默认五号 10.5pt，iPad 上偏小，默认给小四 12pt。
  const [handoutFont, setHandoutFont] = useState('-4')
  const [sep, setSep] = useState('0.6em')
  const [blank, setBlank] = useState('4')
  const [layout, setLayoutRaw] = useState<'compact' | 'roomy'>('roomy')
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<ExportResult | null>(null)
  const [err, setErr] = useState('')
  const [genMsg, setGenMsg] = useState('')
  // 组卷方案（`coverage`）：**要几道题、想覆盖多少考点**。
  // 目标是「尽量用最少的题把考点铺满」，所以先定题量再谈覆盖率。
  const [want, setWant] = useState('46')
  const [cov, setCov] = useState('0.9')
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
  const score = list.reduce((s, q) => s + (SCORE[q.type] || 0), 0)

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
    setBusy(true); setBusySince(Date.now()); setErr('')
    const keys = list.map((q) => q.key)

    // 幻灯片讲义走独立端点（Slidev 渲染），其余三种走 LaTeX 导出
    const call = api.export({
          title, out, mode, show_answers: showAns, bottom_sep: sep,
          problem_blank_cm: Number(blank) || 0, compile: true,
          keys, answers_at_end: ansAtEnd, handout_font: handoutFont,
        })

    call.then((d) => {
      if (d.detail) { setErr(String(d.detail)); setRes(null) }
      else setRes(d)
    }).catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  // 这里以前挂着一个 800ms 防抖的自动重编 effect：只要 `compiled` 为真，
  // 改标题/版式/换题/排序都会在背后自动跑一遍 xelatex。已按要求删除——
  // 现在**只有**点「编译预览」或「导出并保存」才编译，不再有隐式触发。

  /** 随机组卷：`gaokao` 按卷面结构填位置；`coverage` 按考点覆盖率挑题。 */
  const roll = () => {
    setBusy(true); setErr(''); setGenMsg('')
    api.generate({ ...filters, mode, seed: Math.floor(Math.random() * 1e9),
                   want: Number(want) || 19, coverage: Number(cov) || 0.9 })
      .then((d) => {
        if (d.detail) { setErr(String(d.detail)); return }
        setList(d.items || [])
        const rep = d.report || {}
        setGenMsg(`${(d.items || []).length} 题 · ${d.score} 分`
          + (rep.unfilled?.length ? ` · ⚠ ${rep.unfilled.length} 个位置没填上` : '')
          + (rep.notes?.length ? ` · ${rep.notes[0]}` : ''))
      })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  /* ── 存档 / 合集 ──────────────────────────────────
     存档只记题号，所以**随时能原样还原**（题目改了也还原成最新版）。
     加载走 `/api/questions?keys=…`，顺序按存档里的顺序。 */
  const refreshSaved = () =>
    api.papers().then((d) => setSaved(d.items || [])).catch(() => {})
  useEffect(() => { refreshSaved() }, [])

  const loadSaved = (name: string) => {
    setBusy(true); setErr(''); setGenMsg('')
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
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
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
    <div className="anim-fade-in fixed inset-0 z-50 flex items-center justify-center
                    bg-ink/25 p-5 backdrop-blur-[2px]">
      <div className="pop-c flex h-[min(880px,92vh)] w-[min(1220px,95vw)] flex-col
                      overflow-hidden rounded-[var(--radius-pop)] border border-border
                      bg-surface shadow-[var(--shadow-pop)]">

        {/* ── 头 ── */}
        <header className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-3">
          <span className="text-[15px] font-semibold tracking-tight">组卷导出</span>
          <span className="tnum text-[11.5px] text-ink-faint">
            {list.length} 题 · {score} 分 · 有解析 {answered}/{list.length}
          </span>
          {genMsg && <span className="min-w-0 truncate text-[11.5px] text-brand-ink">{genMsg}</span>}
          <button onClick={onClose} title="关闭"
            className="icon-btn ml-auto h-7 w-7 shrink-0">
            <X size={15} />
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          {/* ── 左：设置 ── */}
          <div className="w-[288px] shrink-0 space-y-5 overflow-y-auto border-r border-border
                          bg-surface px-4 py-4">
            <Group title="卷型">
              <div className="grid grid-cols-2 gap-1.5">
                {([['gaokao', '高考卷'], ['test', '纯测试题'], ['coverage', '考点覆盖卷'],
                   ['handout', '讲义']] as const).map(([v, label]) => (
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
                <div className="text-[11px] leading-relaxed text-ink-faint">
                  参考：19 题 ≈ 38%，46 题 ≈ 84%，60 题 ≈ 97%，80 题铺满。
                  覆盖率按当前筛选出的 {poolN} 道里能覆盖到的考点算。
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

            <Group title="卷面标题">
              <input value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder={mode === 'gaokao' ? '留空用「数学试卷」' : '留空用「考点测试」'}
                className={INPUT} />
            </Group>

            <Group title="导出文件名">
              <input value={out} onChange={(e) => setOut(e.target.value)}
                placeholder="留空用「标题_时间戳」" className={INPUT} />
            </Group>

            {/* 讲义模式说明：把「讲义印成什么样」一次讲清楚 */}
            {mode === 'handout' && (
              <div className="rounded-[var(--radius-card)] border border-brand-line bg-brand-soft/50
                              p-3.5 text-[11.5px] leading-relaxed text-brand-ink">
                <b>讲义模式</b>：一题一页 · <b>A4 横版</b>（iPad 横屏满屏）· 题目下方整片留白给笔写 ·
                <b>不印答案和解析</b>。讲完一题直接翻下一页。
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <span className="text-[10.5px] opacity-70">字号</span>
                  {([['-4', '小四 12'], ['4', '四号 14'],
                     ['3', '三号 16'], ['2', '二号 22']] as const).map(([v, label]) => (
                    <button key={v} onClick={() => setHandoutFont(v)}
                      className={`press inline-flex items-center rounded-full border px-2 py-[3px]
                                  text-[10.5px] font-medium transition-colors ${
                        handoutFont === v ? 'border-brand bg-brand text-white'
                                          : 'border-brand-line bg-surface text-brand-ink hover:bg-brand-soft'}`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── 答案：两个开关是**互斥**的（勾一个就撤另一个），
                   但语义上是两件独立的事，所以不做成单选组。 ── */}
            <div className={mode === 'handout' ? 'hidden' : 'space-y-2'}>
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
                  答案印在题目上（讲义卷）
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
            <Group title="版式" className={mode === 'handout' ? 'hidden' : ''}>
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

            <Group title="间距与留白" className={mode === 'handout' ? 'hidden' : ''}>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <div className="text-[11px] text-ink-soft">题目间距</div>
                  <input value={sep} onChange={(e) => setSep(e.target.value)}
                    className={`${INPUT} font-mono`} />
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
                填 <b>0</b>：按难度自动留 —— 简单 3 · 中档 5 · 难题 8 cm。
                填正数则一律用它。
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
                const sc = items.reduce((a, q) => a + (SCORE[q.type] || 0), 0)
                return (
                  <div key={t} className="mb-4 last:mb-0">
                    <div className="mb-1.5 flex items-baseline gap-2 text-[11px]">
                      <span className="font-semibold text-ink">{label}</span>
                      <span className="tnum text-ink-faint">{items.length} 题 · {sc} 分</span>
                    </div>
                    <div className="space-y-1">
                      {items.map((q) => {
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
                              {SCORE[q.type]}分
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
                  label="正在编译 PDF"
                  stages={LATEX_STAGES}
                  hint={'两遍 xelatex，题越多越慢；中途不用重复点，编译完会自动出预览'} />
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
