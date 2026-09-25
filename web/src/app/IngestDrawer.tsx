/** 录入抽屉：粘贴 LaTeX 源码 → 预览 → 入库。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。
 */
import { useState } from 'react'
import {
  AlertTriangle, ArrowUp, Check, FileText, Loader2, Merge, Play, Undo2, Upload, X,
} from 'lucide-react'
import { renderBlocks } from '@/lib/render'
import { api } from '@/lib/api'
import { Flags, Report, INGEST_SAMPLE, CloseBtn } from '@/app/ui'

/** 输入框的统一样式（左侧「源材料」一栏里共用）。 */
const FIELD = `h-[32px] rounded-lg border border-border bg-bg px-2.5 text-[12.5px] outline-none
               transition-[border-color,box-shadow] duration-150 placeholder:text-ink-faint
               focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]`
/** 小节标题（抽屉里所有分组标题统一走这一个）。 */
const LABEL = 'text-[11px] font-semibold tracking-[0.08em] text-ink-faint'
/** 次按钮。 */

export default function IngestDrawer({ onClose, onDone, facets, closing }: {
  onClose: () => void; onDone: () => void; facets: any
  /** 正在播退场动画（父组件用 `useUnmount` 控制）。 */
  closing?: boolean
}) {
  const [text, setText] = useState('')
  const [book, setBook] = useState('手工录入')
  const [label, setLabel] = useState('')
  const [year, setYear] = useState('')
  const [no, setNo] = useState('')       // 原卷题号，单题录入时填
  // **难度与考点在界面上直接选**。不填也能录（之后靠 LLM 自动打标），
  // 但手工录入时人就在旁边，顺手指一下比事后回头补准得多——
  // 而且**手动标的不会被自动打标覆盖**（`point_source: manual`）。
  const [diff, setDiff] = useState('')
  // 题型：默认 '' = 按正文推断（见 `amti/latex_ir.py` 的题型判定）。
  // 录多选题最容易踩：答案还没写完时会被判成单选，这里能直接指定。
  const [qtype, setQtype] = useState('')
  const [pts, setPts] = useState<string[]>([])
  // 库里已有的题：手里这份更全就**升级**（默认开）。
  // 「连已有解析也覆盖」默认关——残缺的重录不该冲掉库里好的解析。
  const [updateExisting, setUpdateExisting] = useState(true)
  const [updateForce, setUpdateForce] = useState(false)
  // 「并入这道」：{新题的 key: 库内那道题的 key}。
  // 判重是算出来的，算不准——最终由人拍板。
  const [mergeInto, setMergeInto] = useState<Record<string, string>>({})
  const [ptKw, setPtKw] = useState('')
  const [pv, setPv] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [drag, setDrag] = useState(false)

  /** 拖进来或选一个 `.tex` / `.txt` 文件，读进文本框。
   *  比复制粘贴省事，尤其是几百行的整卷。 */
  const readFile = (f: File) => {
    const r = new FileReader()
    r.onload = () => { setText(String(r.result || '')); setPv(null); setMsg('')
                       setErr('') }
    r.readAsText(f, 'utf-8')
  }
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const body = () => ({
    text, book, label,
    year: year ? Number(year) : null,
    source_no: no,
    difficulty: diff,
    qtype,
    points: pts.join(','),
    update_existing: updateExisting,
    update_force: updateForce,
    merge_into: mergeInto,
  })

  const dryRun = () => {
    if (!text.trim()) { setErr('先粘贴题目 LaTeX'); return }
    setBusy(true); setErr(''); setMsg('')
    api.ingestPreview(body())
      .then((d) => { if (d.detail) setErr(String(d.detail)); else setPv(d) })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  /** **一键更新**：把手里这份并到库里那道题上，升级完直接落盘。
   *
   *  走的就是「干跑 → 确认导入」同一条后端链路（`commit` 的
   *  `merge_into` + `update_existing`），只是省掉中间两次点击。
   *  敢做成一键，是因为升级规则是**只升不降**：补空的解析、并考点、
   *  改答案，任何一个字段都不会因为这次操作变空。
   */
  const updateInto = (newKey: string, targetKey: string) => {
    setBusy(true); setErr(''); setMsg('')
    api.ingestCommit({ ...body(), merge_into: { ...mergeInto, [newKey]: targetKey },
                       update_existing: true })
      .then((d) => {
        if (d.detail || !d.ok) { setErr(String(d.detail || d.error)); return }
        const up = (d.upgraded || []).find((u: any) => u.key === targetKey)
        const label = (f: string) => ({ solution: '解析', answer: '答案',
          points: '考点', difficulty: '难度' } as any)[f] || f
        setMsg(up ? `已更新 ${targetKey.split('/').pop()}：${up.fields.map(label).join('、')}`
                  : `${targetKey.split('/').pop()} 已是最新，无需改动`)
        setPv(null); setText(''); setMergeInto({}); onDone()
      })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  const doCommit = () => {
    if (!pv) { setErr('先干跑一次'); return }
    if (pv.missing_images?.length) {
      setErr(`有 ${pv.missing_images.length} 张图缺失，先补图再导入`); return
    }
    setBusy(true); setErr('')
    api.ingestCommit(body())
      .then((d) => {
        if (d.detail || !d.ok) { setErr(String(d.detail || d.error)); return }
        setMsg(`已导入 ${d.added_count} 道` +
          (d.upgraded?.length ? `，升级 ${d.upgraded.length} 道` : '') +
          (d.skipped?.length ? `，跳过 ${d.skipped.length} 道` : ''))
        setPv(null); setText(''); onDone()
      })
      .catch((e) => setErr(String(e))).finally(() => setBusy(false))
  }

  return (
    <div className={`${closing ? 'anim-slide-r-out' : 'anim-slide-r'} fixed inset-0 z-50
                    flex flex-col border-l border-border bg-surface
                    shadow-[var(--shadow-pop)]`} onClick={onClose}>
      <div className="flex min-h-0 flex-1 flex-col" onClick={(e) => e.stopPropagation()}>
        <header className="flex shrink-0 items-center gap-3 border-b border-border bg-surface px-5 py-3.5">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-ink">
            <FileText size={15} />
          </span>
          <span className="shrink-0 text-[15px] font-semibold tracking-tight text-ink">录入题目</span>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-faint">
            先干跑看清楚，再确认导入 —— 干跑什么都不写
          </span>
          <CloseBtn onClick={onClose} className="ml-auto" />
        </header>

        <div className="flex min-h-0 flex-1">
          {/* 左：源材料。**按"填什么"分成三块**（出处 / 归类 / 题目），
              每块有编号和小标题——以前是三道分隔线堆着，看不出是几步，
              下面还跟着一大片空白 textarea，整屏显得又空又乱。 */}
          <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
            <section className="shrink-0">
              <div className="mb-2 flex items-baseline gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">1</span>
                <span className={LABEL}>出处</span>
                <span className="text-[11px] text-ink-faint">录的是哪张卷的哪道题</span>
              </div>
              <div className="flex flex-wrap items-end gap-3">
              {([['来源', book, setBook, '手工录入'], ['出处', label, setLabel, '如 第14套武汉三调'],
                 ['年份', year, setYear, '2024'], ['题号', no, setNo, '7']] as const).map(([name, val, set, ph]) => (
                <div key={name}>
                  <div className={`mb-1.5 ${LABEL}`}>{name}</div>
                  <input value={val} onChange={(e) => (set as any)(e.target.value)} placeholder={ph}
                    className={`w-[150px] ${FIELD}`} />
                </div>
              ))}
              </div>
            </section>

            {/* ── 难度 / 考点 ──
                留空也能录（之后靠自动打标补），但人就在旁边时顺手指一下，
                比事后回头对 17554 道题找哪道没标要准得多。
                手动标了会记成 `point_source: manual`，自动打标不再覆盖。 */}
            <section className="shrink-0">
              <div className="mb-2 flex items-baseline gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">2</span>
                <span className={LABEL}>归类</span>
                <span className="text-[11px] text-ink-faint">
                  标了就以你标的为准；不标由系统按主考点派生
                </span>
              </div>
              <div className="flex flex-wrap items-start gap-5">
              {/* 题型：**默认按正文推断**（`\begin{problem}` → 解答题、
                  有选项 → 单选/多选、有 `\fillin` → 填空），绝大多数时候对，
                  所以默认那一档叫「自动识别」。但录一道还没写答案的多选题时
                  会被判成单选 —— 所以留一个明确指定的口子。
                  选得和正文对不上（填空题却有选项…）后端会当场拦下来，
                  干跑就能看见。 */}
              <div>
                <div className={`mb-1.5 ${LABEL}`}>
                  题型 <span className="font-normal tracking-normal text-ink-faint/80">（默认按正文识别）</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {[['', '自动识别'], ['single_choice', '单选题'], ['multi_choice', '多选题'],
                    ['fill_in_blank', '填空题'], ['detailed_answer', '解答题']].map(([v, t]) => (
                    <button key={v || 'auto'} onClick={() => setQtype(v)}
                      title={v ? '' : '按 LaTeX 正文推断（problem→解答、有选项→选择、有 \\fillin→填空）'}
                      className={`press rounded-full border px-2.5 py-[5px] text-[12px] font-medium
                                  transition-colors ${
                        qtype === v ? 'border-brand bg-brand text-white shadow-[0_2px_8px_-3px_var(--color-brand)]'
                                    : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <div className={`mb-1.5 ${LABEL}`}>难度</div>
                <div className="flex gap-1.5">
                  {([['简单题', 1], ['中档题', 2], ['难题', 3]] as const).map(([d, k]) => (
                    <button key={d} onClick={() => setDiff(diff === d ? '' : d)}
                      className={`press inline-flex items-center gap-1 rounded-full border px-2.5 py-[5px]
                                  text-[12.5px] font-medium transition-colors ${
                        diff === d ? 'border-brand bg-brand text-white shadow-[0_2px_8px_-3px_var(--color-brand)]'
                                   : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                      <span className="tracking-tight">{'★'.repeat(k)}</span>
                      <span className="text-[11.5px]">{d.replace('题', '')}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="min-w-[280px] flex-1">
                <div className={`mb-1.5 ${LABEL}`}>
                  考点 <span className="font-normal tracking-normal text-ink-faint/80">（第一条为主考点）</span>
                </div>
                {/* 已选：按选中顺序排，第一个就是主考点 */}
                {pts.length > 0 && (
                  <div className="mb-1.5 flex flex-wrap gap-1">
                    {pts.map((p, i) => {
                      const t = (facets?.points || []).find((x: any) => x.value === p)
                      return (
                        <span key={p}
                          className="inline-flex items-center gap-1 rounded-md border border-brand-line
                                     bg-brand-soft px-1.5 py-[2px] text-[11px] text-brand-ink">
                          {i === 0 && <b title="主考点">主</b>}
                          {t?.title || p}
                          <button onClick={() => setPts((xs) => xs.filter((x) => x !== p))}
                            title="移除考点"
                            className="ml-0.5 grid h-3.5 w-3.5 place-items-center rounded text-brand-ink/60
                                       hover:bg-brand-line/50 hover:text-brand-ink">
                            <X size={10} />
                          </button>
                        </span>
                      )
                    })}
                  </div>
                )}
                <input value={ptKw} onChange={(e) => setPtKw(e.target.value)}
                  placeholder="搜索考点…"
                  className={`w-full ${FIELD}`} />
                {ptKw.trim() && (
                  <div className="pop mt-1 max-h-[132px] overflow-y-auto rounded-lg border border-border
                                  bg-surface shadow-[var(--shadow-pop)]">
                    {(facets?.points || [])
                      .filter((p: any) => !pts.includes(p.value) &&
                        (p.title.includes(ptKw.trim()) || p.value.includes(ptKw.trim())))
                      .slice(0, 20)
                      .map((p: any) => (
                        <button key={p.value}
                          onClick={() => { setPts((xs) => [...xs, p.value]); setPtKw('') }}
                          className="flex w-full items-baseline gap-2 px-2.5 py-1.5 text-left
                                     text-[12px] transition-colors hover:bg-muted">
                          <span className="font-mono text-[10.5px] text-ink-faint">{p.value}</span>
                          <span className="min-w-0 flex-1 truncate text-ink-soft">{p.title}</span>
                        </button>
                      ))}
                  </div>
                )}
              </div>
              </div>
            </section>

            {/* ③ 题目：**有边框的输入框**，不再是整片留白。
                表头放「填入示例 / 选文件」——它们是往这个框里灌内容的动作，
                搁在①那一行里既不像输入的一部分，也离框太远。 */}
            <section className="flex min-h-[240px] flex-1 flex-col">
              <div className="mb-2 flex shrink-0 items-center gap-2">
                <span className="grid h-4 w-4 shrink-0 place-items-center rounded bg-muted
                                 text-[10px] font-semibold text-ink-faint">3</span>
                <span className={LABEL}>题目 LaTeX</span>
                <button onClick={() => setText(INGEST_SAMPLE)}
                  className="press ml-auto inline-flex h-[26px] items-center gap-1 rounded-lg border
                             border-border bg-surface px-2 text-[11.5px] text-ink-soft
                             hover:border-brand-line hover:text-brand-ink">
                  <FileText size={12} />填入示例
                </button>
                {/* 选文件：和拖拽一个效果 */}
                <label className="press inline-flex h-[26px] cursor-pointer items-center gap-1 rounded-lg
                                  border border-border bg-surface px-2 text-[11.5px] text-ink-soft
                                  hover:border-brand-line hover:text-brand-ink">
                  <Upload size={12} />选文件…
                  <input type="file" accept=".tex,.txt" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f) }} />
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
                onChange={(e) => { setText(e.target.value); setPv(null); setMsg('') }}
                spellCheck={false}
                placeholder={'粘贴 exam-zh 格式的题目，或把 .tex 文件拖进来：\n\n\\begin{question}\n…\n\\end{question}\n\\begin{solution}\n…\n\\end{solution}'}
                className="h-full w-full resize-none bg-transparent px-4 py-3.5 font-mono
                           text-[12.5px] leading-relaxed outline-none placeholder:text-ink-faint" />
              {drag && (
                <div className="anim-fade-in pointer-events-none absolute inset-3 flex flex-col items-center
                                justify-center gap-2 rounded-[var(--radius-card)] border-2 border-dashed
                                border-brand-line bg-brand-soft/70 text-[12.5px] font-medium text-brand-ink">
                  <Upload size={20} />
                  松手就读这个文件
                </div>
              )}
              </div>

              {/* 干跑**跟着输入走**：它是"把上面这段材料分析一遍"的动作。
                  以前它挂在右栏底部，离输入区一整屏远。 */}
              <div className="mt-2.5 flex shrink-0 flex-col gap-2">
                {err && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-warn-line
                                  bg-warn-soft px-2.5 py-2 text-[11.5px] text-warn">
                    <X size={13} className="mt-[1px] shrink-0" />{err}
                  </div>
                )}
                {msg && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-has-line
                                  bg-has-soft px-2.5 py-2 text-[11.5px] text-has">
                    <Check size={13} className="mt-[1px] shrink-0" />{msg}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-ink-faint">
                    干跑<b className="font-medium text-ink-soft">什么都不写</b>，只是拿它跟库里的题对一遍
                  </span>
                  {/* 一屏只留一个**实心粉**按钮（右下那个「确认导入」）。
                      干跑做成"次级主按钮"：描边 + 浅粉底，分量够但不跟它抢。 */}
                  <button onClick={dryRun} disabled={busy}
                    className="press ml-auto inline-flex items-center gap-1.5 rounded-lg border
                               border-brand-line bg-brand-soft px-4 py-2 text-[13px] font-semibold
                               text-brand-ink transition-colors hover:bg-brand hover:text-white
                               disabled:opacity-40 disabled:hover:bg-brand-soft
                               disabled:hover:text-brand-ink">
                    {busy
                      ? <Loader2 size={13} className="shrink-0 animate-spin" />
                      : <Play size={13} className="shrink-0" />}
                    干跑
                  </button>
                </div>
              </div>
            </section>
          </div>

          {/* 右：干跑报告 */}
          <div className="flex w-[440px] shrink-0 flex-col border-l border-border bg-bg">
            <div className="flex h-[52px] shrink-0 items-center gap-2 border-b border-border
                            bg-surface px-4">
              <span className="text-[13px] font-semibold tracking-tight">干跑结果</span>
              {pv ? (
                <span className="rounded-full bg-brand-soft px-2 py-[1px] text-[11px] font-medium
                                 text-brand-ink">
                  {pv.count} 道
                </span>
              ) : (
                <span className="text-[11px] text-ink-faint">还没跑</span>
              )}
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3.5">
              {/* 空态**说明"会出现什么"**，而不是一片白里放一句话——
                  空白占了大半屏，人不知道这一步能得到什么。 */}
              {!pv && !busy && (
                <div className="anim-fade-in flex h-full flex-col justify-center gap-3 px-1">
                  <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                    <Play size={13} className="shrink-0 text-ink-faint" />
                    点左边「干跑」之后，这里依次给出五样东西：
                  </div>
                  <ol className="space-y-2">
                    {([
                      ['规范：验证 → 修改 → 复核', '不合规的地方在哪、规范器改了什么、复核过没过'],
                      ['解析结果', '识别出几道题、每题题干与选项长什么样'],
                      ['图片', '引用了几张、哪些在库里、哪些缺'],
                      ['查重', '与库中哪道相似、相似度多少，要不要并进去'],
                      ['影响面', '这次会动到几道存量题 —— 最该先看的一行'],
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
              {busy && (
                <div className="anim-fade-in space-y-2">
                  <div className="flex items-center gap-2 text-[12.5px] text-ink-soft">
                    <Loader2 size={14} className="shrink-0 animate-spin text-brand" />
                    正在解析 · 规范化 · 查重 · 查图…
                  </div>
                  <div className="progress-track" />
                  {/* 骨架屏：先给出「报告大概长这样」，比空白等着好 */}
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
              {pv && (<>
                {/* 规范：**验证 → 修改 → 复核**。这是录入流程的第一步，
                    最该让人看见——「改之前哪里不合规、规范器改了什么、
                    复核过没过」三件事一目了然。
                    复核不过就不许导入（后端也会拒）。 */}
                {pv.spec && (
                  <Report n="①" title="规范：验证 → 修改 → 复核">
                    <div className="space-y-2 text-[11.5px]">
                      <div className="flex items-center gap-2">
                        <span className="w-14 shrink-0 text-ink-faint">改之前</span>
                        {pv.spec.before?.length
                          ? <span className="inline-flex items-center gap-1 font-medium text-warn">
                              <X size={12} className="shrink-0" />{pv.spec.before.length} 处不合规
                            </span>
                          : <span className="inline-flex items-center gap-1 font-medium text-has">
                              <Check size={12} className="shrink-0" />本来就合规
                            </span>}
                      </div>
                      {!!pv.spec.before?.length && (
                        <div className="ml-[3.75rem] space-y-0.5 text-[10.5px] text-ink-faint">
                          {pv.spec.before.slice(0, 5).map((b: any, i: number) => (
                            <div key={i} className="truncate">
                              <span className="font-mono">{b.key.split('/').pop()}</span>
                              {' '}[{b.check}] {b.why}
                            </div>
                          ))}
                          {pv.spec.before.length > 5 &&
                            <div>… 其余 {pv.spec.before.length - 5} 处</div>}
                        </div>
                      )}
                      <div className="flex items-center gap-2">
                        <span className="w-14 shrink-0 text-ink-faint">规范器</span>
                        {pv.spec.fixed?.length
                          ? <span className="text-ink-soft">
                              {pv.spec.fixed.map((f: any) => `${f.name} ${f.hits} 道`).join(' · ')}
                            </span>
                          : <span className="text-ink-faint">无需改动</span>}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-14 shrink-0 text-ink-faint">复核后</span>
                        {pv.spec.ok
                          ? <span className="inline-flex items-center gap-1 font-medium text-has">
                              <Check size={12} className="shrink-0" />全部规范，可以导入
                            </span>
                          : <span className="inline-flex items-center gap-1 font-medium text-warn">
                              <X size={12} className="shrink-0" />
                              仍有 {pv.spec.after.length} 处 —— 先改题目，不许导入
                            </span>}
                      </div>
                    </div>
                  </Report>
                )}

                <Report n="②" title={`解析结果：${pv.count} 道`}>
                  {pv.errors?.length > 0 && (
                    <div className="mb-1.5 inline-flex items-center gap-1 text-[11.5px] font-medium text-warn">
                      <AlertTriangle size={12} className="shrink-0" />
                      {pv.errors.length} 个解析问题
                    </div>
                  )}
                  {pv.items.map((it: any, i: number) => (
                    <div key={i} className="mb-1.5 rounded-lg border border-border bg-bg px-2.5 py-2
                                            last:mb-0">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
                        <span className="rounded bg-muted px-1.5 py-[1px]">{it.type_label}</span>
                        {/* 难度：星号 + 名称。**没标就明说「难度未定」**，
                            不要留空——留空看不出是"没标"还是"界面漏了"。 */}
                        {it.stars
                          ? <span className="rounded bg-brand-soft px-1.5 py-[1px] text-brand-ink"
                              title={it.difficulty}>
                              {'★'.repeat(it.stars)} {it.difficulty}
                            </span>
                          : <span className="rounded border border-dashed border-border px-1.5 py-[1px]">
                              难度未定
                            </span>}
                        <Flags flags={it.flags} />
                        <span className="ml-auto font-mono">{it.key.split('/').pop()}</span>
                      </div>
                      <div className="q-stem line-clamp-2 text-[12px]">{renderBlocks(it.blocks?.stem)}</div>
                      {/* 考点：全名。没有就说明"这批题还没打标签"。 */}
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        {it.point_titles?.length
                          ? it.point_titles.map((t: string, k: number) => (
                              <span key={k} title={it.points?.[k] || ''}
                                className={`rounded px-1.5 py-[1px] text-[10.5px] font-semibold ${
                                  k === 0 ? 'bg-brand-soft text-brand-ink'
                                          : 'bg-muted text-ink-soft'}`}>
                                {k === 0 && <span className="mr-0.5 text-[9px] font-normal opacity-70">主</span>}
                                {t}
                              </span>
                            ))
                          : <span className="text-[10.5px] text-ink-faint">
                              未标考点（导入后可在详情页补）
                            </span>}
                      </div>
                    </div>
                  ))}
                </Report>

                <Report n="③" title={`图片检查：${Object.keys(pv.images || {}).length} 张`}>
                  {Object.keys(pv.images || {}).length === 0
                    ? <div className="text-[11.5px] text-ink-faint">没有引用图片</div>
                    : <div className="space-y-1">
                        {Object.entries(pv.images).map(([k, v]: any) => (
                          <div key={k} className="flex items-center gap-2 text-[11.5px]">
                            <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-ink-soft">{k}</span>
                            <span className={`inline-flex shrink-0 items-center gap-1 ${
                              v.status === 'missing' ? 'text-warn' : 'text-has'}`}>
                              {v.status === 'missing'
                                ? <AlertTriangle size={11} className="shrink-0" />
                                : <Check size={11} className="shrink-0" />}
                              {v.note}
                            </span>
                          </div>
                        ))}
                      </div>}
                </Report>

                <Report n="④" title={`查重：新建 ${pv.dup.new} · 并入 ${pv.dup.merge} · 疑似 ${pv.dup.suspect}`
                  + (pv.dup.upgrade ? ` · 升级 ${pv.dup.upgrade}` : '')}>
                  {/* **升级**：题库里已经有这道题，但手里这份更全（带解析／考点更多）
                      ——不新写一份，而是**改库里那一份**。干跑就要讲清楚，
                      否则点完「确认导入」才发现白录了。 */}
                  {pv.dup.upgrade > 0 && (
                    <div className="mb-2 rounded-lg border border-brand-line bg-brand-soft/60 px-2.5 py-2">
                      <div className="flex items-start gap-1.5 text-[11.5px] font-medium text-brand-ink">
                        <ArrowUp size={13} className="mt-[1px] shrink-0" />
                        <span>{pv.dup.upgrade} 道已在库、但这份更全，导入时会升级（不会新增一份）</span>
                      </div>
                      {pv.items.filter((it: any) => it.update_fields?.length).map((it: any) => (
                        <div key={it.key} className="mt-1 text-[11px] text-ink-soft">
                          <span className="font-mono">{it.key.split('/').pop()}</span>
                          {' '}更新：{it.update_fields.map((f: string) =>
                            ({ solution: '解析', answer: '答案', points: '考点',
                               difficulty: '难度' } as any)[f] || f).join('、')}
                        </div>
                      ))}
                    </div>
                  )}
                  {pv.items.filter((it: any) => it.dups?.length).map((it: any) => (
                    <div key={it.key} className="mb-1.5 text-[11.5px] last:mb-0">
                      <div className="truncate text-ink-soft">{it.key}</div>
                      {it.update_fields?.length > 0 && (
                        <div className="ml-2 inline-flex items-center gap-1 text-[11px] text-brand-ink">
                          <ArrowUp size={11} className="shrink-0" />
                          手里这份更全 → 更新 {it.update_fields.join('、')}
                        </div>
                      )}
                      {it.dups.map((d: any) => (
                        <div key={d.key} className="ml-2 mt-1 rounded-lg border border-border
                                                   bg-bg px-2.5 py-2">
                          <div className="flex items-center gap-1.5">
                            <span className={`shrink-0 rounded px-1.5 py-[1px] text-[10.5px] font-medium ${
                              d.verdict === '并入' ? 'bg-warn-soft text-warn' : 'bg-muted text-ink-faint'}`}>
                              {d.verdict}
                            </span>
                            <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-ink-soft">{d.key}</span>
                            <span className="tnum shrink-0 text-[10.5px] text-ink-faint">{d.score.toFixed(3)}</span>
                          </div>
                          {/* **把库内那道题的原文摆出来**——只给题号和分数，
                              人判断不了是不是同一道，等于没提示 */}
                          {d.stem && (
                            <div className="mt-1 line-clamp-2 text-[11px] text-ink-soft">{d.stem}</div>
                          )}
                          <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[10.5px] text-ink-faint">
                            <span>{d.type_label}</span>
                            <span className={`inline-flex items-center gap-0.5 ${
                              d.has_solution ? 'text-has' : 'text-gap'}`}>
                              {d.has_solution
                                ? <Check size={10} className="shrink-0" />
                                : <X size={10} className="shrink-0" />}
                              解析
                            </span>
                            <span className={`inline-flex items-center gap-0.5 ${
                              d.has_answer ? 'text-has' : 'text-gap'}`}>
                              {d.has_answer
                                ? <Check size={10} className="shrink-0" />
                                : <X size={10} className="shrink-0" />}
                              答案
                            </span>
                            {d.point_titles?.length > 0 && <span>{d.point_titles[0]}</span>}
                            {/* 拍板：这其实就是同一道题 → 并入它（走升级那条路） */}
                            <span className="ml-auto inline-flex gap-1">
                              {mergeInto[it.key] === d.key ? (
                                <button onClick={() => { const m = { ...mergeInto }
                                    delete m[it.key]; setMergeInto(m); setPv(null) }}
                                  className="press inline-flex items-center gap-0.5 rounded-md border
                                             border-warn-line bg-warn-soft px-1.5 py-[2px]
                                             font-medium text-warn">
                                  <Undo2 size={10} className="shrink-0" />撤销并入
                                </button>
                              ) : (
                                <button onClick={() => { setMergeInto({ ...mergeInto, [it.key]: d.key })
                                                          setPv(null) }}
                                  className="press inline-flex items-center gap-0.5 rounded-md border
                                             border-border bg-surface px-1.5 py-[2px] text-ink-soft
                                             hover:border-brand-line hover:text-brand-ink">
                                  <Merge size={10} className="shrink-0" />并入这道
                                </button>
                              )}
                              {/* **一键更新**：并进去 + 升级 + 落盘，一步到位 */}
                              <button disabled={busy} onClick={() => updateInto(it.key, d.key)}
                                title="把手里这份并入这道题并升级：补解析、并考点、改答案，然后落盘"
                                className="press inline-flex items-center gap-0.5 rounded-md border
                                           border-brand-line bg-brand-soft px-1.5 py-[2px]
                                           font-medium text-brand-ink hover:bg-brand-soft/70
                                           disabled:opacity-40">
                                <ArrowUp size={10} className="shrink-0" />用这份更新
                              </button>
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ))}
                  {!pv.items.some((it: any) => it.dups?.length) && !pv.dup.upgrade &&
                    <div className="inline-flex items-center gap-1 text-[11.5px] font-medium text-has">
                      <Check size={12} className="shrink-0" />库中没有相似题
                    </div>}
                  {/* 两个开关。允许升级默认开；「连已有解析也覆盖」默认关——
                      重录一份残缺的解析，不该把库里那份好的冲掉。 */}
                  <label className="mt-2.5 flex items-start gap-2 text-[11.5px] text-ink-soft">
                    <input type="checkbox" checked={updateExisting}
                      onChange={(e) => { setUpdateExisting(e.target.checked); setPv(null) }}
                      className="mt-[1px] accent-[var(--color-brand)]" />
                    <span>库里已有这道题时，手里这份更全就升级（补解析 · 并考点 · 改答案）</span>
                  </label>
                  {updateExisting && (
                    <label className="mt-1.5 flex items-start gap-2 text-[11.5px] text-ink-soft">
                      <input type="checkbox" checked={updateForce}
                        onChange={(e) => { setUpdateForce(e.target.checked); setPv(null) }}
                        className="mt-[1px] accent-[var(--color-brand)]" />
                      <span>连已有的解析也覆盖（默认只补空的，不动已有的）</span>
                    </label>
                  )}
                </Report>

                <Report n="⑤" title="类型与字段校验">
                  <div className="mb-2 text-[11.5px] text-ink-soft">
                    {pv.types.map((t: any) => `${t.label} ${t.n}`).join(' · ') || '—'}
                  </div>
                  {pv.problems?.length
                    ? <div className="inline-flex items-center gap-1 text-[11.5px] font-medium text-warn">
                        <AlertTriangle size={12} className="shrink-0" />
                        {pv.problems.length} 道有字段问题
                      </div>
                    : <div className="inline-flex items-center gap-1 text-[11.5px] font-medium text-has">
                        <Check size={12} className="shrink-0" />全部通过
                      </div>}
                </Report>

                <Report n="⑥" title="影响面">
                  <div className={`text-[12px] font-medium ${
                    pv.impact.existing_questions ? 'text-warn' : 'text-has'}`}>
                    存量题目影响：{pv.impact.existing_questions} 道
                  </div>
                  <div className="mt-1 text-[11px] leading-snug text-ink-faint">{pv.impact.note}</div>
                </Report>
              </>)}
            </div>

            <div className="shrink-0 border-t border-border bg-surface px-4 py-3">
              <button onClick={doCommit}
                  disabled={busy || !pv || pv.count === 0 || pv.spec?.ok === false
                            || (pv.missing_images?.length ?? 0) > 0}
                  title={pv?.spec?.ok === false ? '规范复核没过，先改题目'
                         : (pv?.missing_images?.length ? '有缺图，先补图' : '')}
                  className="press flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand
                             px-4 py-2.5 text-[13px] font-semibold text-white
                             shadow-[var(--shadow-brand)] hover:brightness-105 disabled:opacity-40">
                  <Upload size={13} className="shrink-0" />
                  确认导入 {pv?.count ? `(${pv.count} 道)` : ''}
                </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
