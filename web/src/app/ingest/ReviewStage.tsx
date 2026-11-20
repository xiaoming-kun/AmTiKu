/** 录入工作区 · 逐题确认阶段：题卡、批量、报告和提交条。
 *  状态来自 useIngest，本组件只负责右栏渲染。 */
import {
  AlertTriangle, Check, Loader2, Play, RefreshCw, Sparkles, Undo2, Upload, Wrench,
} from 'lucide-react'
import { renderBlocks } from '@/lib/render'
import { Flags, Report } from '@/app/ui'
import { PointPicker, DiffPills } from '@/app/IngestControls'
import { useIngestCtx } from './IngestContext'
import { blockingOf, EMPTY, LABEL, MINI, QTYPE_OPTS, QTYPE_LABEL, STARS } from './shared'
import { CommitBar } from './IngestStages'

export default function ReviewStage() {
  const bag = useIngestCtx()
  const {
    pv, toggleAll, expanded, setExpanded, ai, tagItems, edits, mainOnly, emptyTagCount, tagging, setReviewFilter, reviewFilter, filterCounts, selected, batchType, setBatchType, applyBatch, batchDiff, setBatchDiff, batchPts, points, setBatchPts, label, setMainOnly, report, backfill, nearThreshold, undoReport, busy, setReport, specAfter, fixedCount, tagErr, visibleItems, aiCards, picks, pointInfo, cardRefs, setActiveCard, activeCard, setPicks, aiMiss, aiPageDir, setPageView, srcDir, setEdits, year, setSrcOpen, srcOpen, commitOne, srcEdit, setSrcEdit, saveSource, repairQuestion, repairing, repairNote, err, msg, badSelected, doCommit, dryRun
  } = bag
  const blockedItems = pv ? pv.items.filter((it: any) => blockingOf(it).length > 0) : []
  const missingAns = blockedItems.filter((it: any) => blockingOf(it).some((x) => x.includes('答案'))).length
  const missingSol = blockedItems.filter((it: any) => blockingOf(it).some((x) => x.includes('解析'))).length
  const missingPointCount = pv ? pv.items.filter((it: any) => !(edits[it.block]?.points?.length)).length : 0
  const generatedCount = pv ? pv.items.filter((it: any) => it.solution_generated).length : 0
  // 一道题可能同时缺答案和解析；总数按题去重，别把同一道算两次。
  const missingAnswerTotal = blockedItems.filter((it: any) =>
    blockingOf(it).some((x) => x.includes('答案') || x.includes('解析'))).length
  const checkOk = !!pv && !pv.errors?.length && blockedItems.length === 0
    && !!pv.spec?.ok && !(pv.missing_images?.length)
    && !(pv.dup?.suspect) && missingPointCount === 0 && generatedCount === 0
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-bg">

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
              <button onClick={() => void dryRun()} disabled={busy || !pv}
                title="按当前来源重新解析并检查"
                className={`${MINI} ml-auto`}>
                <RefreshCw size={11} className={busy ? 'animate-spin' : ''} />重新检查
              </button>
              <button onClick={() => pv && void tagItems(pv, edits, { onlyPicked: true, mainOnly })}
                disabled={!pv || !emptyTagCount || tagging}
                title={ai
                  ? '用 DeepSeek 给还没标考点的题补标；已标的不动'
                  : '用 qwen3.5 只给还没标考点的题补标；已标的不动'}
                className="press inline-flex h-[26px] items-center gap-1 rounded-lg border
                           border-brand-line bg-brand-soft px-2 text-[11px] font-medium
                           text-brand-ink hover:border-brand disabled:opacity-40">
                {tagging ? <Loader2 size={12} className="animate-spin" />
                         : <Sparkles size={12} />}
                {ai ? 'DeepSeek 补考点' : 'AI 标注空缺'}
                {emptyTagCount ? ` (${emptyTagCount})` : ''}
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
                    {ai
                      ? '左边连接 DeepSeek、选好试题与答案，点「开始读取」；这里会出现题卡：'
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
                {/* 入库前检查：不是装饰，是「这份材料能不能入库」的六项事实。 */}
                {checkOk && (
                  <div className="flex items-center gap-1.5 rounded-lg border border-has-line
                                  bg-has-soft px-2.5 py-2 text-[11px] font-medium text-has">
                    <Check size={12} className="shrink-0" />
                    结构、规范、查重、答案与图片全部通过；可以勾选入库。
                  </div>
                )}
                {!checkOk && (
                  <div className="rounded-lg border border-warn-line bg-warn-soft/70 px-2.5 py-2
                                  text-[11px] leading-relaxed text-warn">
                    <div className="flex items-center gap-1.5 font-medium">
                      <AlertTriangle size={12} className="shrink-0" />
                      入库前还有几项值得确认
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10.5px]">
                      {pv.errors?.length ? <span>解析问题 {pv.errors.length}</span> : null}
                      {blockedItems.length ? <span>硬伤 {blockedItems.length} 道</span> : null}
                      {pv.dup?.suspect ? <span>疑似重复 {pv.dup.suspect} 道</span> : null}
                      {missingPointCount ? <span>缺考点 {missingPointCount} 道</span> : null}
                      {generatedCount ? <span>补写解析 {generatedCount} 道</span> : null}
                      {missingAnswerTotal ? <span>答案/解析待补 {missingAnswerTotal} 道</span> : null}
                      {pv.missing_images?.length ? <span>缺图 {pv.missing_images.length} 张</span> : null}
                      {badSelected.length ? <span>勾选里 {badSelected.length} 道有硬伤</span> : null}
                    </div>
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">
                  {([
                    ['切题', `${pv.count} 道`,
                     pv.errors?.length ? `${pv.errors.length} 个解析问题` : '题块完整',
                     pv.errors?.length ? 'warn' : 'has'],
                    ['规范', pv.spec?.ok ? '通过' : `${specAfter} 处未过`,
                     pv.spec?.ok ? `自动修 ${fixedCount} 处` : '只拦勾选的题',
                     pv.spec?.ok ? 'has' : 'warn'],
                    backfill
                      ? ['补旧题', `已有 ${pv.items.filter((it: any) => it.same_key).length} 道`,
                         `已选 ${selected.length} 道；只补空考点/难度`, 'has']
                      : ['查重', `新 ${pv.dup.new} · 跳过 ${pv.dup.skip ?? (pv.dup.merge + (pv.dup.near || 0))}`,
                         `疑似 ${pv.dup.suspect} 道；已有/相似不更新`,
                         pv.dup.suspect ? 'warn' : 'has'],
                    ['图片', pv.missing_images?.length
                      ? `缺 ${pv.missing_images.length} 张` : '齐全',
                     `${Object.keys(pv.images || {}).length} 张引用`,
                     pv.missing_images?.length ? 'warn' : 'has'],
                    ['答案/解析', missingAnswerTotal
                      ? `${missingAnswerTotal} 道待补`
                      : generatedCount ? `${generatedCount} 道补写` : '齐全',
                     missingAnswerTotal
                       ? `缺答案 ${missingAns} · 缺解析 ${missingSol}`
                       : generatedCount ? 'DeepSeek 生成，需逐题核对' : '每道都有答案与解析',
                     missingAnswerTotal || generatedCount ? 'warn' : 'has'],
                    ['入库', `${selected.length} / ${pv.items.length} 道`,
                     badSelected.length ? `${badSelected.length} 道勾选有硬伤` : '当前勾选可入库',
                     badSelected.length ? 'warn' : 'has'],
                  ] as const).map(([k, v, note, tone]) => (
                    <div key={k} className="rounded-lg border border-border bg-surface px-2.5 py-2">
                      <div className="text-[10px] text-ink-faint">{k}</div>
                      <div className={`text-[12.5px] font-semibold ${
                        tone === 'warn' ? 'text-warn' : 'text-ink'}`}>{v}</div>
                      <div className="mt-0.5 truncate text-[10px] text-ink-faint">{note}</div>
                    </div>
                  ))}
                </div>

                {blockedItems.length > 0 && (
                  <details className="rounded-lg border border-warn-line bg-warn-soft/50">
                    <summary className="cursor-pointer select-none px-2.5 py-2 text-[11px]
                                        font-medium text-warn">
                      逐题检查：{blockedItems.length} 道有硬伤，展开看原因
                    </summary>
                    <div className="max-h-[180px] divide-y divide-warn-line/60 overflow-y-auto
                                    border-t border-warn-line/60 px-2.5">
                      {blockedItems.slice(0, 50).map((it: any) => (
                        <div key={it.block} className="flex items-baseline gap-2 py-1.5 text-[10.5px]">
                          <span className="tnum w-8 shrink-0 text-ink-faint">
                            {it.source_no || it.block + 1}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-ink-soft">
                            {blockingOf(it).join('、')}
                          </span>
                        </div>
                      ))}
                      {blockedItems.length > 50 && (
                        <div className="py-1.5 text-[10px] text-ink-faint">
                          … 其余 {blockedItems.length - 50} 道
                        </div>
                      )}
                    </div>
                  </details>
                )}

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
                  const hasFigure = (it.figures?.length || 0) > 0
                    || /\\includegraphics/.test(String(it.tex || ''))
                  const repairReasons = [...new Set([
                    ...hard,
                    ...((Array.isArray(am?.problems) ? am.problems : []) as string[]),
                  ])]
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
                            am.solution_generated ? 'bg-warn-soft text-warn'
                              : am.verified ? 'bg-has-soft text-has' : 'bg-warn-soft text-warn'}`}>
                            {am.solution_generated ? '解析补写 · 需核对'
                              : am.verified ? '答案已复核'
                                : `核对未过${am.verdict ? `：${am.verdict}` : ''}`}
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
                            {/* 库内题的题干/答案/解析都是 LaTeX：当纯文本摊开只会看到
                                一片 `$\{a_n\}$`、`\[ ... \]`，人根本没法比对。
                                后端给块 IR，这里和题库卡片用同一个渲染器。 */}
                            <span className="min-w-0 flex-1 truncate text-ink-soft">
                              {dup.stem_blocks?.length ? renderBlocks(dup.stem_blocks) : dup.stem}
                            </span>
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
                              {dup.answer_blocks?.length ? (
                                <div className="q-compact mt-1 rounded bg-surface-2 p-1.5 text-[11.5px] text-ink">
                                  <span className="mr-1 text-ink-faint">答案：</span>
                                  {renderBlocks(dup.answer_blocks)}
                                </div>
                              ) : dup.answer_preview && (
                                <div className="mt-1 whitespace-pre-wrap break-words rounded bg-surface-2 p-1.5 font-mono">
                                  答案：{dup.answer_preview}
                                </div>
                              )}
                              {dup.solution_blocks?.length ? (
                                <div className="q-compact mt-1 max-h-[220px] overflow-y-auto rounded
                                                bg-surface-2 p-1.5 text-[11.5px] text-ink">
                                  <span className="mr-1 text-ink-faint">解析：</span>
                                  {renderBlocks(dup.solution_blocks)}
                                </div>
                              ) : dup.solution_preview && (
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
                          className={MINI} title={ai
                            ? '用 DeepSeek 只重标这一道'
                            : '只重标这一道，覆盖卡片上的考点/难度'}>
                          <Sparkles size={10} />{ai ? 'DeepSeek 标这题' : 'AI 标注这题'}
                        </button>
                        <button onClick={() => void repairQuestion(b)}
                          disabled={busy || repairing[b]}
                          className="press inline-flex h-8 items-center gap-1.5 rounded-lg
                                     border border-brand-line bg-brand-soft px-3 text-[11.5px]
                                     font-semibold text-brand-ink hover:bg-brand hover:text-white
                                     disabled:cursor-not-allowed disabled:opacity-40"
                          title={repairReasons.length
                            ? `把这道题的 ${repairReasons.length} 条报错提交给 DeepSeek，只修这一道`
                            : '让 DeepSeek 按规范检查并修复这道题；不改题意'}>
                          {repairing[b]
                            ? <Loader2 size={13} className="animate-spin" />
                            : <Wrench size={13} />}
                          {repairing[b] ? 'DeepSeek 修复中…' : 'DeepSeek 修复这道题'}
                        </button>
                        {hasFigure && (
                          <button onClick={() => void repairQuestion(b,
                            '把题中的位图图片改成可编译的 TikZ：用 tikzpicture 重画，保留图形语义、标注、题干和答案，不要改题意、选项、解析。')}
                            disabled={busy || repairing[b]}
                            className="press inline-flex h-8 items-center gap-1.5 rounded-lg
                                       border border-warn-line bg-warn-soft px-3 text-[11.5px]
                                       font-semibold text-warn hover:border-warn
                                       disabled:cursor-not-allowed disabled:opacity-40"
                            title="把这道题里的图片重画成 TikZ，其他内容不动">
                            {repairing[b]
                              ? <Loader2 size={13} className="animate-spin" />
                              : <Wrench size={13} />}
                            图片转 TikZ
                          </button>
                        )}
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

                      {(hard.length > 0 || repairNote[b]) && (
                        <div className="mt-1.5 rounded-md border border-warn-line bg-warn-soft
                                        px-2 py-1.5 text-[9.5px] leading-relaxed text-warn">
                          {repairReasons.length > 0 && (
                            <div>
                              将提交给 DeepSeek 的报错：
                              {repairReasons.slice(0, 3).join('；')}
                              {repairReasons.length > 3 ? `；…共 ${repairReasons.length} 条` : ''}
                            </div>
                          )}
                          {repairNote[b] && <div className="mt-0.5">修复结果：{repairNote[b]}</div>}
                        </div>
                      )}

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
                          {am?.solution_generated && (
                            <div className="rounded border border-warn-line bg-warn-soft px-2 py-1
                                            text-[10px] leading-relaxed text-warn">
                              这份解析由 DeepSeek 根据题干/答案补写，不是原卷原文；入库前请核对。
                            </div>
                          )}
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

    </div>
  )
}
