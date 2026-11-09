/** 录入抽屉 · 来源阶段：选文件/读图/AI、出处、批量、LaTeX 输入。
 *  状态来自 useIngest，本组件只负责这一栏的渲染。 */
import {
  AlertTriangle, Check, FileText, KeyRound, Loader2, Play, Sparkles, Upload, X,
} from 'lucide-react'
import { INGEST_SAMPLE } from '@/app/ui'
import { useIngestCtx } from './IngestContext'
import { DEFAULT_BOOK, DEFAULT_LABEL, DEFAULT_YEAR, FIELD, LABEL, MINI } from './shared'

export default function SourceStage() {
  const bag = useIngestCtx()
  const {
    ai, aiHasText, label, aiFileInput, setDrag, aiRunFile, drag, aiBusy, aiAns, setAiAns, setAiErr, setAiSetup, aiCfg, aiClearKey, aiSetup, aiErr, aiNote, aiKey, setAiKey, aiSaveKey, aiTesting, aiModel, setAiModel, aiBase, setAiBase, aiPages, setAiPages, aiWorkers, setAiWorkers, aiProg, msg, aiCancel, aiJobId, aiCancelling, aiClean, book, setBook, setLabel, region, setRegion, year, setYear, facets, srcDir, setSrcDir, keyNeedsSanitize, yearBad, pv, showHint, fillHint, backfill, setBackfill, resetReview, setMsg, nearThreshold, setNearThreshold, autoTag, setAutoTag, selected, specAfter, llmStatus, unloadLlm, refreshLlm, restored, clearDraft, changeText, readFile, vlmReady, vlmEngine, busy, ocrFile, recentJobs, pruneJobs, resumeJob, sourcePages, setPageView, sourceDir, sourceJob, text, err, dryRun
  } = bag
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">


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

    </div>
  )
}
