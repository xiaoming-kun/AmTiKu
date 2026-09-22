/** 导出页：组卷（LaTeX 试卷）与讲义（Slidev）的设置面板。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1：App 曾是全文件最大的组件）。
 */
import { useEffect, useState } from 'react'
import type { Q, ExportResult } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { SCORE, SECTION_LABEL } from '@/lib/paper'
import CompileOverlay, { LATEX_STAGES, SLIDEV_STAGES } from '@/app/CompileOverlay'

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
    <div className="fixed inset-0 z-50 flex flex-col bg-bg">
      <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
        <span className="text-[14px] font-semibold">组卷导出</span>
        <span className="text-[11.5px] text-ink-faint">
          {list.length} 题 · {score} 分 · 有解析 {answered}/{list.length}
        </span>
        {genMsg && <span className="text-[11.5px] text-brand-ink">{genMsg}</span>}
        <button onClick={onClose}
          className="ml-auto rounded-lg border border-border px-2.5 py-1 text-[12px] text-ink-soft hover:bg-muted">
          关闭
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* ── 左：设置 ── */}
        <div className="w-[272px] shrink-0 space-y-4 overflow-y-auto border-r border-border px-4 py-4">
          <div>
            <div className="mb-1 text-[11px] font-semibold text-ink-faint">卷型</div>
            <div className="flex gap-1">
              {([['gaokao', '高考卷'], ['test', '纯测试题'], ['coverage', '考点覆盖卷'],
                 ['handout', '讲义']] as const).map(([v, label]) => (
                <button key={v} onClick={() => setMode(v)}
                  className={`flex-1 rounded-lg border px-1.5 py-1.5 text-[11.5px] transition-colors ${
                    mode === v ? 'border-brand/40 bg-brand-soft font-medium text-brand-ink'
                               : 'border-border bg-bg text-ink-soft hover:bg-muted'}`}>
                  {label}
                </button>
              ))}
            </div>
            <div className="mt-1 text-[10.5px] leading-relaxed text-ink-faint">
              {mode === 'gaokao'
                ? '与高考真题一致：信息行 + 注意事项 + 四大题分节，卷面不标难度'
                : mode === 'test'
                ? '考点专练：小字列出考点，每题标出难度等级，带上出处'
                : '按考点覆盖率挑题：用尽量少的题把考点铺满，挑完易→难排好'}
            </div>
          </div>

          {mode === 'coverage' && (
            <div className="space-y-2 rounded-lg border border-border bg-bg px-2.5 py-2.5">
              <div className="text-[11px] font-semibold text-ink-faint">组卷方案</div>
              <label className="block text-[11.5px] text-ink-soft">
                题量
                <input value={want} onChange={(e) => setWant(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1
                             text-[12.5px] outline-none focus:border-brand/40" />
              </label>
              <label className="block text-[11.5px] text-ink-soft">
                目标覆盖率
                <input value={cov} onChange={(e) => setCov(e.target.value)}
                  className="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1
                             text-[12.5px] outline-none focus:border-brand/40" />
              </label>
              <div className="text-[10px] leading-relaxed text-ink-faint">
                参考：19 题 ≈ 38%，46 题 ≈ 84%，60 题 ≈ 97%，80 题铺满。
                覆盖率按当前筛选出的 {poolN} 道里能覆盖到的考点算。
              </div>
            </div>
          )}

          <button onClick={roll} disabled={busy}
            className="w-full rounded-lg border border-brand/40 bg-brand-soft px-3 py-2 text-[12.5px]
                       font-medium text-brand-ink hover:bg-brand-soft/70 disabled:opacity-50">
            {mode === 'gaokao' ? '随机组卷（按高考结构）'
              : mode === 'coverage' ? '按覆盖率组卷' : '取筛选结果'}
          </button>
          {poolN > 0 && (
            <button onClick={() => setList(pool)} disabled={busy}
              className="w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-[11.5px]
                         text-ink-soft hover:border-brand/40 hover:text-brand-ink">
              把筛选到的 {poolN} 道全加进来
            </button>
          )}
          <div className="text-[10.5px] leading-relaxed text-ink-faint">
            {mode === 'gaokao'
              ? '8 单选 + 3 多选 + 3 填空 + 5 解答，解答题按「三角/数列 → 概率统计 → 立体几何 → 解析几何 → 导数」排布'
              : '测试题不做结构约束，用当前筛选到的题目'}
          </div>

          <div className="border-t border-border pt-3">
            <div className="mb-1 text-[11px] font-semibold text-ink-faint">卷面标题</div>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder={mode === 'gaokao' ? '留空用「数学试卷」' : '留空用「考点测试」'}
              className="w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 text-[12.5px]
                         outline-none focus:border-brand/40 focus:bg-surface" />
          </div>
          <div>
            <div className="mb-1 text-[11px] font-semibold text-ink-faint">导出文件名</div>
            <input value={out} onChange={(e) => setOut(e.target.value)} placeholder="留空用「标题_时间戳」"
              className="w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 text-[12.5px]
                         outline-none focus:border-brand/40 focus:bg-surface" />
          </div>
          <div className="space-y-1.5">
          {mode === 'handout' && (
            <div className="rounded-lg border border-brand/30 bg-brand-soft/40 px-2.5 py-2
                            text-[11.5px] leading-relaxed text-brand-ink">
              <b>讲义模式</b>：一题一页 · <b>A4 横版</b>（iPad 横屏满屏）· 题目下方整片留白给笔写 ·
              <b>不印答案和解析</b>。讲完一题直接翻下一页。
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                <span className="text-[10.5px] opacity-70">字号</span>
                {([['-4', '小四 12'], ['4', '四号 14'],
                   ['3', '三号 16'], ['2', '二号 22']] as const).map(([v, label]) => (
                  <button key={v} onClick={() => setHandoutFont(v)}
                    className={`press rounded border px-1.5 py-[1px] text-[10.5px] ${
                      handoutFont === v ? 'border-brand bg-brand text-white'
                                        : 'border-brand/30 bg-surface text-brand-ink'}`}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
          <label className={`flex items-center gap-2 text-[12.5px] ${mode === 'handout' ? 'hidden' : ''}`}>
              <input type="checkbox" checked={showAns}
                onChange={(e) => { setShowAns(e.target.checked)
                                    if (e.target.checked) setAnsAtEnd(false) }}
                className="accent-[var(--color-brand)]" />
              答案印在题目上（讲义卷）
            </label>
            <label className={`flex items-center gap-2 text-[12.5px] ${mode === 'handout' ? 'hidden' : ''}`}>
              <input type="checkbox" checked={ansAtEnd}
                onChange={(e) => { setAnsAtEnd(e.target.checked)
                                    if (e.target.checked) setShowAns(false) }}
                className="accent-[var(--color-brand)]" />
              <span>答案与解析放<b>卷末</b>
                <span className="ml-1 text-[10.5px] text-ink-faint">（真高考卷的做法）</span></span>
            </label>
            <div className={`text-[10.5px] leading-relaxed text-ink-faint ${mode === 'handout' ? 'hidden' : ''}`}>
              两个都不勾＝学生卷：卷面干净、解答题留白，没有答案
            </div>
          </div>
          {showAns && answered < list.length && (
            <div className={`rounded-lg border border-warn/30 bg-warn-soft px-2.5 py-1.5 text-[11px] text-warn ${mode === 'handout' ? 'hidden' : ''}`}>
              本卷 {answered}/{list.length} 题有解析，其余题只有题干
            </div>
          )}
          {/* 版式：一键决定「每题之间留多少地方」。
              紧凑版是省纸的（作答另用答题卡），留空版直接在卷面上写。 */}
          <div className={mode === 'handout' ? 'hidden' : ''}>
            <div className="mb-1 text-[11px] font-semibold text-ink-faint">版式</div>
            <div className="flex gap-1">
              {([['compact', '紧凑版'], ['roomy', '留空版']] as const).map(([v, label]) => (
                <button key={v} onClick={() => setLayout(v)}
                  className={`flex-1 rounded-lg border px-2 py-1.5 text-[12px] transition-colors ${
                    layout === v ? 'border-brand/40 bg-brand-soft font-medium text-brand-ink'
                                 : 'border-border bg-bg text-ink-soft hover:bg-muted'}`}>
                  {label}
                </button>
              ))}
            </div>
            <div className="mt-1 text-[10.5px] leading-relaxed text-ink-faint">
              {layout === 'compact'
                ? '题目紧排、不留解答位，省纸（作答另用纸）'
                : '每题间距 8em 起、解答题留白，可直接在卷面上作答'}
            </div>
          </div>

          <div className={`grid grid-cols-2 gap-2 ${mode === 'handout' ? 'hidden' : ''}`}>
            <div>
              <div className="mb-1 text-[11px] font-semibold text-ink-faint">题目间距</div>
              <input value={sep} onChange={(e) => setSep(e.target.value)}
                className="w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 font-mono text-[12px] outline-none" />
            </div>
            <div>
              <div className="mb-1 text-[11px] font-semibold text-ink-faint">
                解答留白 cm <span className="font-normal">（0 = 按难度）</span>
              </div>
              <input value={blank} onChange={(e) => setBlank(e.target.value)}
                placeholder="0"
                className="w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 font-mono
                           text-[12px] outline-none" />
              <div className="mt-1 text-[10px] leading-relaxed text-ink-faint">
                填 <b>0</b>：按难度自动留 —— 简单 3 · 中档 5 · 难题 8 cm。
                填正数则一律用它。
              </div>
            </div>
          </div>

          {/* 存档 / 合集：出过的卷子留个名，以后一键还原。
              存档里只记**题号**——题目后来改了，还原出来就是最新版。 */}
          <div className="border-t border-border pt-3">
            <div className="mb-1.5 flex items-baseline gap-2">
              <span className="text-[11px] font-semibold text-ink-faint">存档 / 合集</span>
              <span className="text-[10px] text-ink-faint">{saved.length} 份</span>
            </div>
            <div className="mb-1.5 flex gap-1">
              {(['试卷', '合集'] as const).map((k) => (
                <button key={k} onClick={() => setSaveKind(k)}
                  className={`rounded-md border px-1.5 py-[3px] text-[10.5px] transition-colors ${
                    saveKind === k ? 'border-brand/40 bg-brand-soft font-medium text-brand-ink'
                                   : 'border-border bg-bg text-ink-soft hover:bg-muted'}`}>
                  {k}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              <input value={saveName} onChange={(e) => setSaveName(e.target.value)}
                placeholder={saveKind === '合集' ? '如「椭圆专练」' : '如「2026 模拟三」'}
                className="min-w-0 flex-1 rounded-lg border border-border bg-bg px-2 py-1.5
                           text-[12px] outline-none focus:border-brand/40 focus:bg-surface" />
              <button onClick={saveCurrent} disabled={!list.length}
                className="shrink-0 rounded-lg border border-border bg-surface px-2 py-1.5
                           text-[11.5px] text-ink-soft hover:border-brand/40 hover:text-brand-ink
                           disabled:opacity-40">
                存下
              </button>
            </div>
            {saved.length > 0 && (
              <div className="mt-2 max-h-[190px] space-y-1 overflow-y-auto">
                {saved.map((p) => (
                  <div key={p.name}
                    className="group flex items-center gap-1.5 rounded-md border border-border
                               bg-bg px-2 py-1.5 hover:border-brand/30">
                    <button onClick={() => loadSaved(p.name)} className="min-w-0 flex-1 text-left">
                      <div className="truncate text-[11.5px] text-ink">{p.name}</div>
                      <div className="text-[10px] text-ink-faint">
                        {p.kind || '试卷'} · {(p.keys?.length ?? 0)} 题 · {(p.at || '').slice(5, 16)}
                      </div>
                    </button>
                    <button onClick={() => dropSaved(p.name)} title="删掉这份存档"
                      className="shrink-0 text-[11px] text-ink-faint opacity-0 transition-opacity
                                 hover:text-warn group-hover:opacity-100">✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-border pt-3">
            <div className="flex gap-2">
              <button onClick={() => { setCompiled(true); run() }}
                disabled={busy || !list.length}
                className="flex-1 rounded-lg border border-brand/40 bg-brand-soft px-3 py-2
                           text-[12.5px] font-medium text-brand-ink hover:bg-brand-soft/70
                           disabled:opacity-40">
                {busy ? '编译中…' : compiled ? '重新编译' : '编译预览'}
              </button>
              <button onClick={() => { setCompiled(true); run() }}
                disabled={busy || !list.length}
                className="flex-1 rounded-lg bg-brand px-3 py-2 text-[12.5px] font-medium text-white
                           hover:opacity-90 disabled:opacity-40">
                导出并保存
              </button>
            </div>
            {err && <div className="mt-2 rounded-lg border border-warn/30 bg-warn-soft p-2 text-[11.5px] text-warn">✗ {err}</div>}
            {res?.ok && (
              <div className="mt-2 space-y-1.5 rounded-xl border border-has/25 bg-has-soft/50 p-2.5">
                <div className="text-[11.5px] font-medium text-has">✓ {res.saved_hint}</div>
                <div className="break-all font-mono text-[10px] text-ink-soft">{res.pdf_abs || res.tex_abs}</div>
                <div className="flex flex-wrap gap-1">
                  <button onClick={() => navigator.clipboard?.writeText(res.pdf_abs || res.tex_abs)}
                    className="rounded-md border border-border bg-surface px-1.5 py-[3px] text-[10.5px] hover:bg-muted">复制路径</button>
                  <button onClick={() => api.reveal(res.pdf_abs || res.tex_abs).catch(reportErr)}
                    className="rounded-md border border-border bg-surface px-1.5 py-[3px] text-[10.5px] hover:bg-muted">在访达中显示</button>
                </div>
              </div>
            )}
            {res && !res.ok && res.log && (
              <div className="mt-2 whitespace-pre-wrap rounded-lg border border-warn/30 bg-warn-soft p-2
                              font-mono text-[10.5px] text-warn">{res.log}</div>
            )}
          </div>
        </div>

        {/* ── 中：卷子 ── */}
        <div className="flex w-[340px] shrink-0 flex-col border-r border-border">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-[11.5px] text-ink-faint">
            <span>卷子内容</span>
            <span className="ml-auto">{from}</span>
            {list.length > 0 && (
              <button onClick={() => setList([])} className="hover:text-warn">清空</button>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2.5">
            {list.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-[12.5px] text-ink-faint">
                <span>卷子是空的</span>
                <span className="text-[11.5px]">点上面的「随机组卷」，或回工作台勾选题目</span>
              </div>
            ) : SECTION_LABEL.map(([t, label]) => {
              const items = list.filter((q) => q.type === t)
              if (!items.length) return null
              const sc = items.reduce((a, q) => a + (SCORE[q.type] || 0), 0)
              return (
                <div key={t} className="mb-3">
                  <div className="mb-1 flex items-baseline gap-2 text-[11px]">
                    <span className="font-semibold text-ink">{label}</span>
                    <span className="text-ink-faint">{items.length} 题 · {sc} 分</span>
                  </div>
                  {items.map((q) => {
                    const gi = list.indexOf(q)
                    return (
                      <div key={q.key}
                        className="group mb-1 flex items-center gap-1.5 rounded-lg border border-border
                                   bg-surface px-2 py-1.5 hover:border-brand/30">
                        <span className="w-4 shrink-0 text-right text-[10.5px] text-ink-faint">
                          {list.filter((x) => x.type === t).indexOf(q) + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[11.5px] font-semibold text-ink-soft">
                            {q.point_titles[0] || q.type_label}
                          </div>
                          <div className="truncate text-[10px] text-ink-faint">{q.key}</div>
                        </div>
                        <span className="shrink-0 text-[10px] tabular-nums text-ink-faint">
                          {SCORE[q.type]}分
                        </span>
                        <div className="flex shrink-0 flex-col opacity-0 transition-opacity group-hover:opacity-100">
                          <button onClick={() => move(gi, -1)} className="text-[9px] leading-none text-ink-faint hover:text-brand-ink">▲</button>
                          <button onClick={() => move(gi, 1)} className="text-[9px] leading-none text-ink-faint hover:text-brand-ink">▼</button>
                        </div>
                        <button onClick={() => setList((l) => l.filter((x) => x.key !== q.key))}
                          className="shrink-0 text-[14px] leading-none text-ink-faint hover:text-warn">×</button>
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        </div>

        {/* ── 右：预览 ── */}
        <div className="relative min-w-0 flex-1 bg-bg">
          {/* 编译遮罩：**盖住整块预览区**。原先只有右上角一小行字，
              人会以为卡死了反复点。现在有秒表在跳、有进度条在动、
              还分阶段说清楚到哪一步了。 */}
          {busy && (
            <CompileOverlay since={busySince}
              label="正在编译 PDF"
              // 幻灯片讲义走 Slidev（起 Chromium）：阶段与耗时都和 xelatex 不同
              stages={mode === 'slidev' ? SLIDEV_STAGES : LATEX_STAGES}
              hint={mode === 'slidev'
                ? '第一次要冷启动浏览器内核；页数越多越慢。中途不用重复点。'
                : '两遍 xelatex，题越多越慢；中途不用重复点，编译完会自动出预览'} />
          )}
          {res?.pdf_abs ? (
            <iframe key={res.pdf_abs}
              src={'/api/pdf?path=' + encodeURIComponent(res.name + '.pdf')}
              className="h-full w-full" title="预览" />
          ) : (
            <div className="flex h-full items-center justify-center text-[12.5px] text-ink-faint">
              {busy ? '正在生成预览…'
                    : !list.length ? '卷子是空的，先组卷'
                    : !compiled ? '点左边「编译预览」生成 PDF'
                                : '编译没成功，看左边的报错'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}




/* ══ 导出抽屉 ══════════════════════════════════════ */

