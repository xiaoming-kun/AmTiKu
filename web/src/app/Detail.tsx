/** 题目详情：题干 / 答案 / 解析 / 标签编辑。
 *
 *  从 App.tsx 搬出来的（审查报告 CPLX-1）。这几个组件互相引用，
 *  所以放在同一个文件里（TagsEditor 用 Drawer，DetailBody 用 SolutionEditor）。
 */
import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, Check, ChevronDown, ChevronRight, FileCode2,
  Loader2, Pencil, Plus, Save, Search, Trash2, X,
} from 'lucide-react'
import { Highlight, renderBlocks } from '@/lib/render'
import type { Q, SavedHandler } from '@/lib/types'
import { api, reportErr } from '@/lib/api'
import { Flags } from '@/app/ui'
import SourceEditor from '@/app/SourceEditor'
import BusyOverlay from '@/app/BusyOverlay'
import { DIFF_STARS, hasImageOptions, optionRange, starsLabel } from '@/lib/display'

/** 直接录 LaTeX 解析与答案，**经规范审查后**才写入。
 *
 *  用户的原话：「没有解析也没有答案，我可以在题目界面直接录入 latex 代码，
 *  经规范审查后，可以把解析写入，答案我也可以录进去了」。
 *
 *  所以流程和「录入题目」一致，一步不少：
 *
 *      写 → **审查**（规范化 + 规范审查）→ 看报告 → **保存**
 *
 *  审查和保存走**同一个后端接口**（只差 `dry_run`），所以
 *  "预览看到的" 和 "真写进去的" 必然是同一个东西。 */
export function SolutionEditor({ q, onSaved, onCancel }: {
  q: Q; onSaved: SavedHandler; onCancel: () => void
}) {
  const [sol, setSol] = useState(q.solution || '')
  const [ans, setAns] = useState(q.answer || '')
  const [rep, setRep] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const call = (dry: boolean) => {
    setBusy(true); setErr('')
    fetch('/api/questions/' + encodeURIComponent(q.key) + '/solution', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ solution: sol, answer: ans, dry_run: dry }),
    }).then(async (r) => {
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || '出错了')
      return d
    }).then((d) => {
      if (d.ok === false) { setErr(d.error || '规范审查没通过'); setRep(d) }
      else if (dry) setRep(d)
      else { onSaved(d, { refreshList: true, silent: true }); onCancel() }
    }).catch((e) => setErr(String(e.message || e)))
      .finally(() => setBusy(false))
  }

  const input =
    'h-[32px] rounded-lg border border-border bg-bg px-2.5 text-[12.5px] outline-none ' +
    'placeholder:text-ink-faint transition-[border-color,box-shadow] duration-150 ' +
    'focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]'
  const btnPrimary =
    'press inline-flex h-[32px] items-center gap-1.5 rounded-lg bg-brand px-3 text-[12.5px] ' +
    'font-medium text-white shadow-[var(--shadow-brand)] transition-[filter] ' +
    'hover:brightness-105 disabled:opacity-40'
  const btnGhost =
    'press inline-flex h-[32px] items-center gap-1.5 rounded-lg border border-border bg-surface ' +
    'px-3 text-[12.5px] text-ink-soft transition-colors hover:border-border-strong ' +
    'hover:text-ink disabled:opacity-40'

  return (
    <div className="pop rounded-[var(--radius-card)] border border-border bg-surface p-3.5
                    shadow-[var(--shadow-card)]">
      <div className="mb-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-ink">
          <Pencil size={13} className="shrink-0 text-brand" />
          录解析与答案
        </span>
        <span className="text-[11.5px] leading-relaxed text-ink-faint">
          解析正文；<b className="font-medium text-ink-soft">整份 .tex 直接粘进来也行</b>
          （会自动取出解析、丢掉导言区）
        </span>
      </div>
      <textarea value={sol} autoFocus rows={7}
        onChange={(e) => { setSol(e.target.value); setRep(null); setErr('') }}
        placeholder={'由题意得 $x=1$，于是\n\[\nf(x)=x^2\n\]\n故选 B.'}
        className="w-full resize-y rounded-lg border border-border bg-bg p-2.5 font-mono
                   text-[12.5px] leading-relaxed text-ink outline-none
                   placeholder:text-ink-faint transition-[border-color,box-shadow] duration-150
                   focus:border-brand-line focus:bg-surface
                   focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <span className="text-[11.5px] text-ink-faint">答案</span>
        <input value={ans} onChange={(e) => { setAns(e.target.value); setRep(null); setErr('') }}
          onKeyDown={(e) => { if (e.key === 'Enter') call(true) }}
          placeholder={q.type === 'single_choice' ? '如 B'
            : q.type === 'multi_choice' ? '如 ABD' : '如 $\\frac{1}{2}$'}
          className={`w-[150px] font-mono ${input}`} />
        <span className="text-[11px] text-ink-faint">大小写/全角/顿号会自动规整</span>
      </div>

      {/* 审查报告：规范器改了什么、还有没有违规 */}
      {rep && (
        <div className="anim-fade-in mt-2.5 rounded-lg border border-border bg-bg p-2.5 text-[11.5px]">
          {/* **取出说明**：贴整份文档时，告诉人"我从里面拿了什么、丢掉了什么"。
              不显示的话，用户不知道 `\documentclass` 那些去哪了。 */}
          {rep.notes?.length > 0 && (
            <div className="mb-1.5 space-y-0.5">
              {rep.notes.map((nt: string, i: number) => (
                <div key={i} className="text-ink-soft">· {nt}</div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-ink-faint">规范器改动</span>
            {rep.fixed?.length
              ? <span className="text-brand-ink">{rep.fixed.join('、')}</span>
              : <span className="text-ink-faint">无需改动</span>}
          </div>
          {rep.after?.length ? (
            <div className="mt-1.5 text-warn">
              <span className="inline-flex items-center gap-1">
                <X size={12} className="shrink-0" />
                还有 {rep.after.length} 处不规范：
              </span>
              {rep.after.slice(0, 3).map((v: any, i: number) => (
                <div key={i} className="ml-4">[{v.check}] {v.why}</div>
              ))}
            </div>
          ) : (
            <div className="mt-1.5 inline-flex items-center gap-1 text-has">
              <Check size={12} className="shrink-0" />
              规范审查通过，可以保存
            </div>
          )}
        </div>
      )}
      {err && (
        <div className="mt-2 flex items-start gap-1.5 text-[11.5px] text-warn">
          <X size={12} className="mt-[2px] shrink-0" />{err}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <button onClick={() => call(true)} disabled={busy || !sol.trim()} className={btnGhost}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
          审查
        </button>
        <button onClick={() => call(false)} disabled={busy || !sol.trim() || !rep?.ok}
          title={rep?.ok ? '' : '先点「审查」，通过后才能保存'} className={btnPrimary}>
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          保存
        </button>
        <button onClick={onCancel} className={btnGhost}>取消</button>
      </div>
    </div>
  )
}

export function Detail({ q, onSaved, facets, onFindPoint, onDeleteAsk, refreshing = false, kw }: {
  q: Q | null
  onSaved: SavedHandler
  facets: any
  /** 搜索词：详情里的题干/答案/解析也高亮命中（可选） */
  kw?: string
  /** 列表正在重新拉取（标签保存后的自动刷新）。详情顶部给一条进度条，
   *  让人看见"页面正在刷新"，而不是数据悄悄换了。 */
  refreshing?: boolean
  /** 透传给 DetailBody：点考点 → 去列表看同类题 */
  onFindPoint?: (pid: string, title: string) => void
  onDeleteAsk?: () => void
}) {
  if (!q) return <div className="flex h-full items-center justify-center text-[13px] text-ink-faint">选一道题</div>

  return <DetailBody q={q} onSaved={onSaved} facets={facets} refreshing={refreshing}
                     onFindPoint={onFindPoint} onDeleteAsk={onDeleteAsk} kw={kw} />
}

/** 出处输入框的统一样式（三行共用，别再各写一份）。 */
const SRC_INPUT = 'h-[30px] w-full rounded-lg border border-border bg-bg px-2 text-[12.5px] ' +
  'outline-none placeholder:text-ink-faint transition-[border-color,box-shadow] ' +
  'duration-150 focus:border-brand-line focus:bg-surface ' +
  'focus:shadow-[0_0_0_3px_var(--color-brand-soft)]'

/** 难度、考点、出处的**编辑**控件（下拉抽屉式）。 */
export function TagsEditor({ q, onSaved, facets, refreshing = false, searchKw }: {
  q: Q; onSaved: SavedHandler; facets: any
  /** 列表正在重新拉取（由 App 的 loading 传下来） */
  refreshing?: boolean
  /** 搜索词：考点名也高亮命中（注意和下面管搜索框的 `kw` 区分） */
  searchKw?: string
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [kw, setKw] = useState('')
  // 出处四件套：只在这张抽屉里当草稿，**不点保存就不写库**——
  // 边打字边写库的话，key 会一路跟着变（`书/卷名#题号`），列表刷得停不下来。
  const [srcBook, setSrcBook] = useState('')
  const [srcLabel, setSrcLabel] = useState('')
  const [srcNo, setSrcNo] = useState('')     // 题号 = key 里 `#` 后面那截
  const [srcYear, setSrcYear] = useState('')
  // 保存成功后**这一行闪一下 + 冒一个「已保存」**。改难度/考点是高频动作，
  // 值虽然当场就变了，但没有"收到了"的反馈，人不知道到底存没存。
  const [flash, setFlash] = useState<'' | '难度' | '考点' | '出处'>('')
  // 正在存哪一项。整库写回要几秒；这期间 + 之后的列表刷新期间，
  // 屏幕正中会有一个**阻塞遮罩**（用户要的：刷新时做不了别的事）。
  const [savingWhat, setSavingWhat] = useState<'' | '难度' | '考点' | '出处'>('')
  // 保存完了、但列表还没刷完：遮罩留在原地，换成「正在刷新页面…」。
  const [refreshingTag, setRefreshingTag] = useState(false)
  const [sawRefresh, setSawRefresh] = useState(false)
  const flashTimer = useRef<number | null>(null)
  useEffect(() => () => {
    if (flashTimer.current) window.clearTimeout(flashTimer.current)
  }, [])
  useEffect(() => {
    if (!refreshingTag) return
    // 先等列表真的开始拉（refreshing=true），再等它结束（false）才撤遮罩。
    // 少了"先见到 true"这一步，保存刚结束那一瞬间的 false 会误撤。
    if (refreshing) setSawRefresh(true)
    else if (sawRefresh) { setRefreshingTag(false); setSawRefresh(false) }
  }, [refreshing, refreshingTag, sawRefresh])
  useEffect(() => {
    // **兜底**：有些入口没有「列表刷新」这回事（`refreshing` 一直是 false）。
    // 2 秒内没见到列表开始拉，就认为这次没有刷新，撤掉。
    if (!refreshingTag || sawRefresh) return
    const t = window.setTimeout(() => {
      setRefreshingTag(false); setSawRefresh(false)
    }, 2000)
    return () => window.clearTimeout(t)
  }, [refreshingTag, sawRefresh])

  // 换题/保存完 → 草稿跟着当前值重置（改名后 key 变了也算换了题，
  // 否则输入框里还是旧书名，再点一次保存又把它改回去）
  useEffect(() => {
    setSrcBook(String(q.meta?.book || ''))
    setSrcLabel(String(q.meta?.source_label || ''))
    setSrcNo(q.key.includes('#') ? q.key.slice(q.key.lastIndexOf('#') + 1) : '1')
    setSrcYear(q.meta?.year ? String(q.meta.year) : '')
  }, [q.key, q.meta?.book, q.meta?.source_label, q.meta?.year])

  /** 改完出处，key 会变成什么（预览给用户看，别让人保存完才发现动了身份）。 */
  const keyTail = q.key.includes('#') ? q.key.slice(q.key.lastIndexOf('#') + 1) : '1'
  const keyHead = q.key.includes('#') ? q.key.slice(0, q.key.lastIndexOf('#')) : q.key
  const no = srcNo.trim()
  // 题号统一成不带前导零的正整数——和后端 `patch_question` 同一套规则，
  // 也保证 `#` 后面那截永远是纯数字。
  const noOk = /^[1-9]\d*$/.test(no)
  // key 是不是**由出处拼出来的**。历史数据里有 `书/年份/卷名#号` 这种多一层
  // 目录的 key，和 `meta.book`+`source_label` 不同构；那种题改出处只动标签，
  // key 的目录保持原样（否则等于换身份，组过的卷子就断引用）。规则与后端同一份。
  const keyDerivable = q.key === `${q.meta?.book || ''}/${q.meta?.source_label || ''}#${keyTail}`
  // **题号是另一回事**：哪怕 key 不同构，用户明确改了题号也该换掉 `#` 后面那截，
  // 只是别把 `书/年份/卷名` 那层目录重拼（那就成换身份了）。
  const nextKey = keyDerivable
    ? `${srcBook.trim()}/${srcLabel.trim()}#${no || keyTail}`
    : `${keyHead}#${no || keyTail}`

  const saveSrc = () => {
    const book = srcBook.trim()
    const label = srcLabel.trim()
    if (!book || !label) { setErr('来源和出处都不能空'); return }
    if (!noOk) { setErr('题号要是正整数，如 22'); return }
    save({ source: { book, label, year: srcYear.trim(), no } }, '出处')
  }

  const markSaved = (what: '难度' | '考点' | '出处') => {
    setFlash(what)
    if (flashTimer.current) window.clearTimeout(flashTimer.current)
    flashTimer.current = window.setTimeout(() => setFlash(''), 1600)
  }

  const save = async (body: Record<string, unknown>, what: '难度' | '考点' | '出处') => {
    setBusy(true); setErr(''); setSavingWhat(what)
    setRefreshingTag(false); setSawRefresh(false)
    try {
      // `refreshList`：标签一改，当前筛选下的列表/计数就可能变，
      // 让列表带着筛选条件**重新拉一遍**（用户说的「自动刷新」）。
      onSaved(await api.patch(q.key, body), { refreshList: true })
      markSaved(what)
      // 遮罩不撤：从「保存」平滑过渡到「刷新」，直到列表拉完
      setSavingWhat('')
      setRefreshingTag(true)
    } catch (e: any) {
      setErr(e.message || '保存失败')
      setSavingWhat('')
      setRefreshingTag(false); setSawRefresh(false)
    } finally {
      setBusy(false)
    }
  }

  const allPoints: { value: string; title: string; topic?: string }[] =
    facets?.points || []
  const info = (id: string) => allPoints.find((p) => p.value === id)
  /** 与**主考点**不同章 → 很可能是标错了，在界面上标出来让老师一眼看到。 */
  const offChapter = (id: string, i: number) => {
    if (i === 0) return ''
    const mine = info(id)?.topic || ''
    const main = info(q.points[0])?.topic || ''
    return mine && main && mine !== main
      ? mine.replace(/^[一二三四五六七八九十]+、/, '') : ''
  }
  const picked = new Set(q.points)
  const hits = kw.trim()
    ? allPoints.filter((p) => !picked.has(p.value) &&
        (p.title.includes(kw.trim()) || p.value.includes(kw.trim()))).slice(0, 12)
    : []

  const n = DIFF_STARS[q.difficulty] || 0
  return (
    <div className="space-y-2">
      {/* ── 难度：抽屉 ── */}
      <Drawer label="难度" flash={flash === '难度'}
        summary={
          <span className={`inline-flex items-baseline gap-1.5 rounded px-1 -mx-1 ${
            flash === '难度' ? 'anim-flash' : ''}`}>
            <span className={`tracking-tight ${n > 0 ? 'text-warn' : 'text-ink-faint'}`}>
              {starsLabel(n)}
            </span>
            <span className="text-[11.5px] text-ink-soft">{q.difficulty || '未评级'}</span>
            <span className="text-[11px] text-ink-faint">
              {q.meta?.difficulty_source === 'model' ? '（模型推定）'
                : q.meta?.difficulty ? '（手动）' : '（按主考点）'}
            </span>
            {savingWhat === '难度' ? (
              <span className="anim-fade-in inline-flex items-center gap-0.5 text-[10.5px] text-brand-ink">
                <Loader2 size={10} className="animate-spin" />保存中…
              </span>
            ) : flash === '难度' ? (
              <span className="anim-fade-up inline-flex items-center gap-0.5 text-[10.5px]
                               font-medium text-has">
                <Check size={10} />已保存
              </span>
            ) : null}
          </span>}>
        <div className="flex flex-wrap gap-1.5">
          {['简单题', '中档题', '难题'].map((d) => {
            const on = q.difficulty === d
            const k = DIFF_STARS[d] || 0
            return (
              <button key={d} disabled={busy}
                onClick={() => save({ difficulty: d, stars: k }, '难度')}
                className={`press flex flex-1 items-center justify-center gap-1 rounded-full border
                            px-2 py-[5px] text-[12px] font-medium transition-colors ${
                  on ? 'border-brand bg-brand text-white shadow-[0_2px_8px_-3px_var(--color-brand)]'
                     : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}
                            ${on && flash === '难度' ? 'anim-bump' : ''}`}>
                <span className="tracking-tight">{'★'.repeat(k)}</span>
                <span className="text-[11px]">{d.replace('题', '')}</span>
              </button>
            )
          })}
          {q.meta?.difficulty && (
            <button disabled={busy} onClick={() => save({ difficulty: '', stars: 0 }, '难度')}
              title="清掉手改的难度，恢复成按主考点自动派生"
              className="press rounded-full border border-border bg-surface px-2.5 py-[5px]
                         text-[11.5px] text-ink-faint transition-colors hover:border-border-strong
                         hover:text-ink">
              自动
            </button>
          )}
        </div>
      </Drawer>

      {/* ── 考点：抽屉 ── */}
      <Drawer label="考点" flash={flash === '考点'}
        warn={q.point_titles.length > 3 ? `${q.point_titles.length} 个` : undefined}
        summary={
          <span className={`inline-flex flex-wrap items-baseline gap-1 rounded px-1 -mx-1 ${
            flash === '考点' ? 'anim-flash' : ''}`}>
            {q.point_titles.length === 0
              ? <span className="text-[11.5px] text-ink-faint">未标</span>
              : q.point_titles.map((t, i) => (
                  <span key={i} className={`rounded-full px-1.5 py-[1px] text-[11px] font-medium ${
                    i === 0 ? 'bg-brand-soft text-brand-ink' : 'bg-muted text-ink-soft'}`}>
                    {i === 0 && <span className="mr-0.5 text-[9.5px] font-normal opacity-70">主</span>}
                    <Highlight text={t} kw={searchKw} />
                  </span>
                ))}
            {q.meta?.point_source && (
              <span className="rounded-full border border-border px-1.5 py-[1px] text-[10px] text-ink-faint"
                title="考点标注来源">
                {q.meta.point_source === 'human' ? '人工标注' : 'AI标注'}
              </span>
            )}
            {savingWhat === '考点' ? (
              <span className="anim-fade-in inline-flex items-center gap-0.5 text-[10.5px] text-brand-ink">
                <Loader2 size={10} className="animate-spin" />保存中…
              </span>
            ) : flash === '考点' ? (
              <span className="anim-fade-up inline-flex items-center gap-0.5 text-[10.5px]
                               font-medium text-has">
                <Check size={10} />已保存
              </span>
            ) : null}
          </span>}>
        <div className="text-[11px] leading-relaxed text-ink-faint">
          <X size={11} className="mr-1 inline-block align-middle" />
          删掉这条 · 下面搜名字加一条 · 与主考点<b className="font-medium text-ink-soft">不同章</b>的会标出章名
        </div>
        <div className={`mt-2 flex flex-wrap items-center gap-1.5 ${
          flash === '考点' ? 'anim-bump' : ''}`}>
          {q.point_titles.map((t, i) => {
            const off = offChapter(q.points[i], i)
            return (
              <span key={i} title={`${info(q.points[i])?.topic || ''} · ${q.points[i]}`}
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-[3px]
                            text-[11.5px] font-medium ${
                  i === 0 ? 'border-brand-line bg-brand-soft text-brand-ink'
                          : 'border-border bg-surface text-ink-soft'}`}>
                {i === 0 && <span className="text-[9.5px] font-normal opacity-70">主</span>}
                <Highlight text={t} kw={searchKw} />
                {off && (
                  <span className="rounded-full bg-warn-soft px-1 text-[9.5px] font-normal text-warn"
                    title="与主考点不在同一章，留神是不是标错了">
                    {off}
                  </span>
                )}
                {i > 0 && (
                  <button disabled={busy}
                    onClick={() => save({
                      points: [q.points[i], ...q.points.filter((_, j) => j !== i)] }, '考点')}
                    title="设为主考点（难度按主考点派生）"
                    className="text-[9.5px] font-normal text-ink-faint transition-colors
                               hover:text-brand-ink">
                    设为主
                  </button>
                )}
                <button disabled={busy}
                  onClick={() => save({ points: q.points.filter((_, j) => j !== i) }, '考点')}
                  title="从这道题上删掉这个考点"
                  className="grid h-4 w-4 shrink-0 place-items-center rounded-full text-ink-faint
                             transition-colors hover:bg-warn-soft hover:text-warn">
                  <X size={11} />
                </button>
              </span>
            )
          })}
        </div>
        <div className="relative mt-2">
          <Search size={13}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <input value={kw} onChange={(e) => setKw(e.target.value)}
            placeholder="搜考点名或编号，如「椭圆」或 5.2.1"
            className="h-[32px] w-full rounded-lg border border-border bg-bg pl-7 pr-2.5
                       text-[12.5px] outline-none placeholder:text-ink-faint
                       transition-[border-color,box-shadow] duration-150
                       focus:border-brand-line focus:bg-surface
                       focus:shadow-[0_0_0_3px_var(--color-brand-soft)]" />
        </div>
        {kw.trim() && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {hits.map((p) => (
              <button key={p.value}
                onClick={() => { save({ points: [...q.points, p.value] }, '考点'); setKw('') }}
                className="press rounded-full border border-border bg-surface px-2 py-[3px]
                           text-[11.5px] text-ink-soft transition-colors hover:border-brand-line
                           hover:bg-brand-soft/50 hover:text-brand-ink">
                {p.title}
              </button>
            ))}
            {!hits.length && <span className="text-[11.5px] text-ink-faint">没有匹配的考点</span>}
          </div>
        )}
      </Drawer>

      {/* ── 出处：抽屉 ──
          用户的原话：「录入时出处填错了，录完就改不回来」。四样都能改，
          而 key 是 `书/卷名#题号` 拼出来的，所以**改名会连 key 一起改**——
          下面直接把新 key 摆出来，别让人保存完才发现自己动了身份。 */}
      <Drawer label="出处" flash={flash === '出处'}
        summary={
          <span className={`inline-flex min-w-0 items-baseline gap-1 rounded px-1 -mx-1 ${
            flash === '出处' ? 'anim-flash' : ''}`}>
            <span className="truncate text-[11.5px] text-ink-soft">
              {q.meta.book || '未标来源'}
            </span>
            <span className="text-[11px] text-ink-faint">/</span>
            <span className="truncate text-[11.5px] text-ink-soft">
              {q.meta.source_label || '未标出处'}
            </span>
            {q.meta.year ? (
              <span className="text-[11px] text-ink-faint">· {q.meta.year}</span>
            ) : null}
            {savingWhat === '出处' ? (
              <span className="anim-fade-in inline-flex items-center gap-0.5 text-[10.5px] text-brand-ink">
                <Loader2 size={10} className="animate-spin" />保存中…
              </span>
            ) : flash === '出处' ? (
              <span className="anim-fade-up inline-flex items-center gap-0.5 text-[10.5px]
                               font-medium text-has">
                <Check size={10} />已保存
              </span>
            ) : null}
          </span>}>
        <div className="space-y-1.5">
          <div className="grid grid-cols-[38px_1fr] items-center gap-1.5">
            <span className="text-[11.5px] text-ink-faint">来源</span>
            <input value={srcBook} onChange={(e) => setSrcBook(e.target.value)}
              placeholder="书 / 大类，如 2027模拟卷" className={SRC_INPUT} />
          </div>
          <div className="grid grid-cols-[38px_1fr] items-center gap-1.5">
            <span className="text-[11.5px] text-ink-faint">出处</span>
            <input value={srcLabel} onChange={(e) => setSrcLabel(e.target.value)}
              placeholder="卷名，如 陕晋青百师联盟10月测试" className={SRC_INPUT} />
          </div>
          <div className="grid grid-cols-[38px_1fr] items-center gap-1.5">
            <span className="text-[11.5px] text-ink-faint">题号</span>
            <input value={srcNo} onChange={(e) => setSrcNo(e.target.value)}
              placeholder="第几题，如 22" inputMode="numeric" className={SRC_INPUT} />
          </div>
          <div className="grid grid-cols-[38px_1fr] items-center gap-1.5">
            <span className="text-[11.5px] text-ink-faint">年份</span>
            <input value={srcYear} onChange={(e) => setSrcYear(e.target.value)}
              placeholder="如 2027（可空）" inputMode="numeric" className={SRC_INPUT} />
          </div>
        </div>
        <div className="mt-2 text-[11px] leading-relaxed text-ink-faint">
          {!noOk ? (
            <span className="text-warn">题号要是正整数（如 22）——它同时决定 key 和卷面上的出处。</span>
          ) : nextKey !== q.key ? (
            <>key 会跟着改 → <code className="font-mono text-ink-soft">{nextKey}</code>
              <div className="mt-0.5">
                旧：<code className="font-mono line-through opacity-70">{q.key}</code>
                <span className="ml-1">（已组进卷子/讲义的会一起改）</span>
              </div>
            </>
          ) : !keyDerivable ? (
            <>key 不动：这道题的 key 是历史结构（如 <code className="font-mono">书/年份/卷名#号</code>），
              不是出处拼出来的 —— 保存只改出处标签。</>
          ) : (
            <>key 不变：<code className="font-mono text-ink-soft">{q.key}</code></>
          )}
        </div>
        <button disabled={busy || !srcBook.trim() || !srcLabel.trim() || !noOk} onClick={saveSrc}
          className="press mt-2 h-[28px] w-full rounded-lg border border-brand-line bg-brand-soft
                     text-[12px] font-medium text-brand-ink transition-colors
                     hover:bg-brand hover:text-white disabled:cursor-not-allowed
                     disabled:border-border disabled:bg-muted disabled:text-ink-faint">
          保存出处
        </button>
      </Drawer>

      {err && (
        <div className="flex items-center gap-1.5 text-[11.5px] text-warn">
          <X size={12} className="shrink-0" />{err}
        </div>
      )}
      {busy && (
        <div className="flex items-center gap-1.5 text-[11.5px] text-ink-faint">
          <Loader2 size={12} className="animate-spin" />保存中…
        </div>
      )}

      {/* **居中阻塞遮罩**：保存和随后的列表刷新期间，屏幕正中一张卡片，
          鼠标/键盘都过不去。保存完不立刻撤，等列表真的刷完再撤。 */}
      {(savingWhat || refreshingTag) && (
        <BusyOverlay
          title={savingWhat ? `正在保存${savingWhat}…` : '已保存，正在刷新页面…'}
          note={savingWhat
            ? '正在写回题库，请稍候（约需几秒）'
            : '列表和筛选项正在重新加载'} />
      )}
    </div>
  )
}

export function DetailBody({ q, onSaved, facets, onFindPoint, onDeleteAsk, refreshing = false, kw }: {
  q: Q; onSaved: SavedHandler; facets: any
  refreshing?: boolean
  kw?: string
  onFindPoint?: (pid: string, title: string) => void
  onDeleteAsk?: () => void
}) {
  // 改答案。用户的原话：「看到解析了，但是没有答案，我随手就给写进去了」——
  // 所以入口要显眼，别藏在抽屉里。
  // 改题型。**改题型会牵动答案的合法性**（单选恰好 1 个字母、多选至少 2 个），
  // 所以界面上**题型和答案一起提交**，不让后端把答案悄悄清掉。
  const [typeEdit, setTypeEdit] = useState(false)
  const [typeNew, setTypeNew] = useState('')
  const [typeAns, setTypeAns] = useState('')
  const [typeErr, setTypeErr] = useState('')
  const [typeBusy, setTypeBusy] = useState(false)
  const saveType = () => {
    setTypeBusy(true); setTypeErr('')
    const body: Record<string, unknown> = { type: typeNew }
    if (typeAns !== (q.answer || '')) body.answer = typeAns
    api.patch(q.key, body)
      .then((d) => { onSaved(d, { refreshList: true, silent: true }); setTypeEdit(false) })
      .catch((e: any) => setTypeErr(String(e.message || e)))
      .finally(() => setTypeBusy(false))
  }
  const [solEdit, setSolEdit] = useState(false)
  // 改源码：**整道题的 LaTeX 正文**（不是只改答案/解析）。入口要显眼，
  // 题干里的公式写坏时不用再去找 `题目/*.tex`。
  const [srcEdit, setSrcEdit] = useState(false)
  const [ansEdit, setAnsEdit] = useState(false)
  const [ansText, setAnsText] = useState('')
  const [ansBusy, setAnsBusy] = useState(false)
  const [ansErr, setAnsErr] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)
  const toggleReview = () => {
    setReviewBusy(true)
    api.patch(q.key, { reviewed: !q.meta?.reviewed_at })
      .then((d) => onSaved(d, { refreshList: true, silent: true }))
      .catch(reportErr)
      .finally(() => setReviewBusy(false))
  }
  const saveAnswer = () => {
    setAnsBusy(true); setAnsErr('')
    api.patch(q.key, { answer: ansText })
      .then((d) => { onSaved(d, { refreshList: true, silent: true }); setAnsEdit(false) })
      .catch((e: any) => setAnsErr(String(e.message || e)))
      .finally(() => setAnsBusy(false))
  }
  const input =
    'h-[32px] rounded-lg border border-border bg-bg px-2.5 text-[12.5px] outline-none ' +
    'placeholder:text-ink-faint transition-[border-color,box-shadow] duration-150 ' +
    'focus:border-brand-line focus:bg-surface focus:shadow-[0_0_0_3px_var(--color-brand-soft)]'
  const btnPrimary =
    'press inline-flex h-[32px] items-center gap-1.5 rounded-lg bg-brand px-3 text-[12.5px] ' +
    'font-medium text-white shadow-[var(--shadow-brand)] transition-[filter] ' +
    'hover:brightness-105 disabled:opacity-40'
  const btnGhost =
    'press inline-flex h-[32px] items-center gap-1.5 rounded-lg border border-border bg-surface ' +
    'px-3 text-[12.5px] text-ink-soft transition-colors hover:border-border-strong ' +
    'hover:text-ink disabled:opacity-40'
  const sectionTitle = 'text-[11px] font-semibold tracking-[0.08em] text-ink-faint'
  const panel = 'pop rounded-[var(--radius-card)] border border-border bg-surface p-3 ' +
    'shadow-[var(--shadow-card)]'
  return (
    <div className="h-full overflow-y-auto px-5 py-4">
      {/* **页面正在刷新**：标签保存后列表会带着筛选重新拉一遍。
          数据变化本身是无声的，所以给一条不定长进度条——不假装知道百分比，
          只说明"还在动"。sticky 保证滚到解析中段时也看得见。 */}
      {refreshing && (
        <div className="anim-fade-in sticky top-0 z-30 -mx-5 -mt-4 mb-3 border-b border-border
                        bg-surface/95 px-5 py-2 backdrop-blur-sm">
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-[10.5px] font-medium text-brand-ink">正在刷新列表…</span>
            <div className="progress-track flex-1" />
          </div>
        </div>
      )}

      {/* ── 状态行：题型 / 类别 / 完整度 / hash ── */}
      <div className="mb-4 flex flex-wrap items-center gap-1.5">
        <button onClick={() => { setTypeEdit(true); setTypeNew(q.type); setTypeAns(q.answer || ''); setTypeErr('') }}
          title="改题型（单选 ↔ 多选）"
          className="press inline-flex items-center gap-1.5 rounded-full border border-brand-line
                     bg-brand-soft px-2.5 py-[5px] text-[12.5px] font-medium text-brand-ink
                     transition-colors hover:bg-brand-soft/70">
          {q.type_label}
          <Pencil size={13} className="opacity-60" />
        </button>
        <span className={`inline-flex items-center rounded-full border px-2.5 py-[5px]
                          text-[12.5px] font-medium ${
          q.kind === '高考' ? 'border-brand bg-brand text-white' : 'border-border bg-surface text-ink-soft'}`}>
          {q.kind}题
        </span>
        <Flags flags={q.flags} size="md" type={q.type} />
        {/* **改源码**：题干/选项/答案/解析整段 LaTeX 都在这里改。
            不设口令；打开就是编辑器，保存前过规范审查。 */}
        <button onClick={() => setSrcEdit(true)}
          title="直接改这道题的 LaTeX 源码"
          className="press inline-flex items-center gap-1.5 rounded-full border border-border
                     bg-surface px-2.5 py-[5px] text-[12.5px] text-ink-faint
                     transition-colors hover:border-brand-line hover:bg-brand-soft/50
                     hover:text-brand-ink">
          <FileCode2 size={13} />改源码
        </button>
        <span className="ml-auto font-mono text-[10.5px] text-ink-faint">#{q.hash}</span>
      </div>

      {typeEdit && (
        <div className={`${panel} mb-4`}>
          <div className="mb-2.5 flex items-start gap-1.5 text-[12.5px] font-semibold text-ink">
            <Pencil size={13} className="mt-[2px] shrink-0 text-brand" />
            <span>
              改题型
              <span className="ml-1 text-[11px] font-normal leading-relaxed text-ink-faint">
                （题目其实是多选却被标成单选，是常事——题面那句「下列说法正确的是」看不出来）
              </span>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {([['single_choice', '单选题'], ['multi_choice', '多选题']] as const).map(([v, label]) => (
              <button key={v} onClick={() => { setTypeNew(v); setTypeErr('') }}
                className={`press inline-flex items-center rounded-full border px-2.5 py-[5px]
                            text-[12.5px] font-medium transition-colors ${
                  typeNew === v
                    ? 'border-brand bg-brand text-white shadow-[0_2px_8px_-3px_var(--color-brand)]'
                    : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                {label}
              </button>
            ))}
            <span className="ml-1 text-[11.5px] text-ink-faint">答案</span>
            <input value={typeAns} onChange={(e) => { setTypeAns(e.target.value); setTypeErr('') }}
              onKeyDown={(e) => { if (e.key === 'Enter') saveType() }}
              placeholder={typeNew === 'multi_choice' ? '如 ABD' : '如 B'}
              className={`w-[110px] font-mono ${input}`} />
            <button onClick={saveType} disabled={typeBusy || !typeNew} className={btnPrimary}>
              {typeBusy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              {typeBusy ? '保存中…' : '保存'}
            </button>
            <button onClick={() => setTypeEdit(false)} className={btnGhost}>取消</button>
          </div>
          <div className="mt-2 text-[11px] leading-relaxed text-ink-faint">
            单选题恰好 1 个字母，多选题至少 2 个——<b className="font-medium text-ink-soft">题型和答案要一起改</b>，否则会被拒。
            改成填空/解答请走重新录入（要动选项和作答位置，容易改残）。
          </div>
          {typeErr && (
            <div className="mt-2 flex items-start gap-1.5 text-[11.5px] text-warn">
              <X size={12} className="mt-[2px] shrink-0" />{typeErr}
            </div>
          )}
        </div>
      )}

      {/* ── 题干 ── */}
      <div className="mb-5">
        <div className={`mb-1.5 ${sectionTitle}`}>题干</div>
        <div className="q-stem text-ink">{renderBlocks(q.blocks?.stem, kw)}</div>
        {q.options.length > 0 && !hasImageOptions(q) && (
          <ul className="q-options mt-3 space-y-1">
            {q.options.map((o, i) => (
              <li key={o.label}>
                <span className="lbl">{o.label}.</span>
                <span>{renderBlocks(q.blocks?.options?.[i], kw)}</span>
              </li>
            ))}
          </ul>
        )}
        {hasImageOptions(q) && (
          <div className="mt-2 text-[11.5px] text-ink-faint">
            选项见图（{optionRange(q)}，图片在题干中）
          </div>
        )}
      </div>

      {/* **答案**：可以直接改。
          用户的原话是「看到解析了，但是没有答案，我随手就给写进去了」——
          所以① 没答案时按钮要显眼（不是藏在抽屉里）；
          ② 输入随手写没问题（全角、小写、带顿号都认），由后端统一规整；
          ③ 规整不了就**明确报错**，不猜、不硬塞。 */}
      <div className="mb-5">
        <div className="mb-1.5 flex items-center gap-2">
          <span className="text-[11px] font-semibold tracking-[0.08em] text-danger">答案</span>
          {!ansEdit && (
            <button onClick={() => { setAnsEdit(true); setAnsText(q.answer || ''); setAnsErr('') }}
              className={`press inline-flex items-center gap-1.5 rounded-md border px-2 py-[3px]
                          text-[11.5px] transition-colors ${
                q.answer ? 'border-border bg-surface text-ink-faint hover:border-border-strong hover:text-ink'
                         : 'border-warn-line bg-warn-soft text-warn hover:bg-warn-soft/70'}`}>
              {q.answer ? <Pencil size={13} /> : <Plus size={13} />}
              {q.answer ? '改' : '补答案'}
            </button>
          )}
          {q.meta?.answer_source && (
            <span className="rounded-full border border-border px-1.5 py-[1px] text-[10px] text-ink-faint"
              title="答案来源：human=人工改过 / workbuddy=模型生成 / legacy=历史存量">
              {q.meta.answer_source === 'human' ? '人工'
                : q.meta.answer_source === 'workbuddy' ? '模型' : '历史存量'}
            </span>
          )}
          <button onClick={toggleReview} disabled={reviewBusy}
            title={q.meta?.reviewed_at ? `已复核：${q.meta.reviewed_at}` : '标记为已复核（答案和解析都看过了）'}
            className={`press rounded-full border px-1.5 py-[1px] text-[10px] transition-colors ${
              q.meta?.reviewed_at
                ? 'border-has-line bg-has-soft text-has'
                : 'border-border bg-surface text-ink-faint hover:border-brand-line hover:text-brand-ink'}`}>
            {q.meta?.reviewed_at ? '已复核' : '标记复核'}
          </button>
        </div>
        {ansEdit ? (
          <div className={panel}>
            <div className="flex flex-wrap items-center gap-1.5">
              <input value={ansText} autoFocus
                onChange={(e) => setAnsText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveAnswer()
                  if (e.key === 'Escape') setAnsEdit(false)
                }}
                placeholder={q.type === 'single_choice' ? '如 B'
                  : q.type === 'multi_choice' ? '如 ABD' : '如 $\\frac{1}{2}$'}
                className={`min-w-[160px] flex-1 font-mono ${input}`} />
              <button onClick={saveAnswer} disabled={ansBusy} className={btnPrimary}>
                {ansBusy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {ansBusy ? '保存中…' : '保存'}
              </button>
              <button onClick={() => setAnsEdit(false)} className={btnGhost}>取消</button>
            </div>
            <div className="mt-2 text-[11px] leading-relaxed text-ink-faint">
              {q.type === 'single_choice' ? '单选题填一个字母，如 B'
                : q.type === 'multi_choice' ? '多选题填 2–4 个字母，如 ABD'
                : '填空/解答直接写结果，数学用 $…$ 括起来'}
              ：大小写、全角、顿号都会自动规整
            </div>
            {ansErr && (
              <div className="mt-2 flex items-start gap-1.5 text-[11.5px] text-warn">
                <X size={12} className="mt-[2px] shrink-0" />{ansErr}
              </div>
            )}
          </div>
        ) : q.answer ? (
          // 答案**标红**（用户要求：要一眼看到）。学生版/题目列表不受影响。
          <div className="text-[14.5px] font-semibold leading-relaxed text-danger">
            {renderBlocks(q.blocks?.answer, kw)}
          </div>
        ) : (
          <div className="text-[12.5px] text-ink-faint">（暂时没有答案）</div>
        )}
      </div>

      {/* ── 解析 ── */}
      <div className="mb-1">
        <div className="mb-1.5 flex items-center gap-2">
          <span className={sectionTitle}>解析</span>
          {!solEdit && (
            <button onClick={() => setSolEdit(true)}
              className={`press inline-flex items-center gap-1.5 rounded-md border px-2 py-[3px]
                          text-[11.5px] transition-colors ${
                q.solution ? 'border-border bg-surface text-ink-faint hover:border-border-strong hover:text-ink'
                           : 'border-warn-line bg-warn-soft text-warn hover:bg-warn-soft/70'}`}>
              {q.solution ? <Pencil size={13} /> : <Plus size={13} />}
              {q.solution ? '改' : '录解析'}
            </button>
          )}
          {q.meta?.solution_source === 'human' && (
            <span className="text-[11px] text-ink-faint">人工录的</span>
          )}
        </div>
        {solEdit
          ? <SolutionEditor q={q} onSaved={onSaved} onCancel={() => setSolEdit(false)} />
          : q.solution
            ? <div className="q-solution text-ink-soft">{renderBlocks(q.blocks?.solution, kw)}</div>
            : <div className="text-[12.5px] text-ink-faint">（暂时没有解析）</div>}
      </div>

      <div className="mt-5 space-y-3 border-t border-border pt-4">
        {/* 考点与难度：**下拉抽屉**，点开才占地方。
            详情页本来就窄，两个常驻控件会把解析挤没。 */}
        {/* **考点行**：常驻、可点。点一下就把列表切成「只看这个考点」——
            这是从一道题跳到同类题最直接的一条路。
            不做进下面的抽屉里：抽屉要展开才看得见，而这条动线是高频的。 */}
        {q.points.length > 0 && (
          <div>
            <div className={`mb-1.5 ${sectionTitle}`}>考点</div>
            <div className="flex flex-wrap items-center gap-1.5">
              {q.points.map((pid, i) => {
                const t = (facets?.points || []).find((x: any) => x.value === pid)
                const title = t?.title || pid
                return (
                  <button key={pid} onClick={() => onFindPoint?.(pid, title)}
                    title={`找「${title}」的全部题目`}
                    className={`press inline-flex items-center gap-1 rounded-full border px-2.5 py-[4px]
                                text-[11.5px] transition-colors ${
                      i === 0 ? 'border-brand-line bg-brand-soft font-medium text-brand-ink hover:bg-brand-soft/70'
                              : 'border-border bg-surface text-ink-soft hover:border-brand-line hover:bg-brand-soft/50 hover:text-brand-ink'}`}>
                    {i === 0 && <span className="text-[9.5px] font-semibold opacity-70">主</span>}
                    {title}
                    <span className="inline-flex items-center gap-0.5 text-[10.5px] opacity-60">
                      找同类
                      <ChevronRight size={11} />
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        )}
        <TagsEditor q={q} onSaved={onSaved} facets={facets} refreshing={refreshing} searchKw={kw} />
        {q.missing.length > 0 && (
          <div className="flex items-center gap-1.5 text-[11.5px] text-warn">
            <AlertTriangle size={12} className="shrink-0" />缺：{q.missing.join('、')}
          </div>
        )}
        {/* **删除**：唤起弹窗。原因、口令、删的是哪道题，弹窗里一次看全。 */}
        {onDeleteAsk && (
          <button onClick={onDeleteAsk}
            className="press inline-flex items-center gap-1.5 rounded-lg border border-border
                       bg-surface px-2.5 py-1.5 text-[11.5px] text-ink-faint transition-colors
                       hover:border-warn-line hover:bg-warn-soft hover:text-warn">
            <Trash2 size={13} />删除这道题…
          </button>
        )}
        <div className="text-[11.5px] text-ink-faint">
          {q.meta.solved_by && (
            <span className="mr-1.5 inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-[2px] text-[11px]"
              title={q.meta.solved_at || ''}>AI 求解</span>
          )}
          {q.meta.solve_warn && (
            <span className="mr-1.5 inline-flex items-center gap-1 rounded-md bg-warn-soft px-1.5 py-[2px]
                             text-[11px] text-warn"
              title={q.meta.solve_warn}>
              <AlertTriangle size={11} />求解存疑
            </span>
          )}
          {q.meta.source_label || q.meta.book}
          {q.meta.year ? ` · ${q.meta.year}` : ''} · <code className="font-mono">{q.key}</code>
        </div>
      </div>

      {/* 源码编辑器用 portal 挂到 body（详情抽屉带 transform 动画，
          `fixed` 留在里面会以抽屉为参照跑偏），这里只负责开关。 */}
      {srcEdit && (
        <SourceEditor q={q} onSaved={onSaved} onClose={() => setSrcEdit(false)} />
      )}
    </div>
  )
}

/** 难度与考点的**编辑**控件。 */
/** 通用**下拉抽屉**：点标题展开，收起时只占一行。
 *  考点和难度都用它——详情页本来就窄，两排常驻控件太占地方。 */
export function Drawer({ label, summary, children, warn, flash }: {
  label: string; summary: React.ReactNode; children: React.ReactNode; warn?: string
  /** 刚保存完：外圈扩一下（标签类修改的「收到了」反馈） */
  flash?: boolean
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface
                     shadow-[var(--shadow-card)] transition-colors hover:border-border-strong
                     ${flash ? 'anim-saved-ring' : ''}`}>
      {/* ⚠️ 用 `div role=button` 而不是 `<button>`：抽屉标题里可能要放
          **可点的考点标签**，而按钮不能嵌套按钮——浏览器会直接忽略里层，
          点了没反应（实测踩过）。 */}
      <div role="button" tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setOpen((v) => !v) }}
        className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left
                   transition-colors hover:bg-muted/60">
        {open
          ? <ChevronDown size={13} className="shrink-0 text-ink-faint" />
          : <ChevronRight size={13} className="shrink-0 text-ink-faint" />}
        <span className="shrink-0 text-[11.5px] font-semibold text-ink-soft">{label}</span>
        <span className="min-w-0 flex-1 truncate">{summary}</span>
        {warn && (
          <span className="inline-flex shrink-0 items-center gap-1 text-[11px] text-warn">
            <AlertTriangle size={11} />{warn}
          </span>
        )}
      </div>
      {open && (
        <div className="anim-fade-in border-t border-border bg-surface-2 px-3 py-2.5">{children}</div>
      )}
    </div>
  )
}
