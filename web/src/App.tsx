import { useEffect, useMemo, useRef, useState } from 'react'
import type { Q, Base } from '@/lib/types'
import { api, reportErr, setGlobalErrHandler } from '@/lib/api'
import { SCORE, SECTION_LABEL } from '@/lib/paper'
import { DIFF_STARS } from '@/lib/display'
import { useQuestionList } from '@/lib/useQuestionList'
import { Flags, FLAG_KEYS, Chip, FacetMenu, Grip, useWidth, BaseRow } from '@/app/ui'
import QuestionCard from '@/app/QuestionCard'
import { Trash, DeleteModal } from '@/app/Trash'
import { Detail, TexSource } from '@/app/Detail'
import { Stats, Changes, groupTree } from '@/app/Stats'
import CanvasEditor from '@/editor/CanvasEditor'
import ExportPage from '@/app/ExportPage'
import IngestDrawer from '@/app/IngestDrawer'

/* ══ 类型 ══════════════════════════════════════════
   共享类型已移到 `@/lib/types`（编辑器拆成独立模块后两边都要用）。 */

/* ══ 小组件 ════════════════════════════════════════ */




/* ══ 筛选条上的一格 ════════════════════════════════ */


/* ══ 补解析 ════════════════════════════════════════ */




/* ══ 删除弹窗 ══════════════════════════════════════ */



/* ══ 回收站 ════════════════════════════════════════ */



/* ══ 编译遮罩 ══════════════════════════════════════ */


/* ══ 详情 ══════════════════════════════════════════ */















/* ══ 主界面 ════════════════════════════════════════ */


/** 每题分值，和 amti/paper.py 的计分保持一致 */
/** 排序的显示名。默认是「易→难」——复习某个考点时最自然的顺序 */
const SORT_LABEL: Record<string, string> = {
  used: '频次 高→低', diff: '易 → 难', diff2: '难 → 易',
  new: '最新录入', old: '最早录入', solved: '刚解出的', '': '题库原序',
}





/* ══ 录入抽屉 ══════════════════════════════════════ */




/* ══ 统计 ══════════════════════════════════════════ */






export default function App() {
  // 列表数据与筛选 → useQuestionList
  const {
    facets, items, setItems, total, sel, setSel, loading, reload, setReload,
    page, setPage, pageSize, setPageSize, pageInput, setPageInput, jumpPage, listRef,
    q, setQ, type, setType, kind, setKind,
    has, setHas, missing, setMissing, points, setPoints, diffs, setDiffs,
    years, setYears, sort, setSort, openTopics, setOpenTopics,
    selectMode, setSelectMode, checked, setChecked,
    toggleYear, toggleHas, toggleMissing, togglePoint, toggleDiff,
    togglePoints, toggleTopic, toggleCheck, exitSelect,
    activeFilters, scopeName,
  } = useQuestionList()
  const [base, setBase] = useState<Base | null>(null)
  // 顶栏的「存量未改动」状态（与 facets 一起随 reload 刷新）
  useEffect(() => {
    api.baseline().then(setBase).catch(reportErr)
  }, [reload])
  const [tab, setTab] = useState<'detail' | 'tex' | 'paper' | 'handout' | 'stats' | 'changes' | 'trash'>('detail')
  const [handoutN, setHandoutN] = useState(0)
  // 侧边栏显示「已有 N 份讲义」
  useEffect(() => { api.handouts().then((d) => setHandoutN((d.items || []).length))
    .catch(() => {}) }, [tab])
  const [showExport, setShowExport] = useState(false)
  const [showIngest, setShowIngest] = useState(false)

  // 三栏宽度可拖。默认收窄了列表栏——原来 336px 挤掉了主区（详情/预览）。
  // 左栏是**考点树**——名字看不全就没法用（「一、集合与逻辑」被截成
  // 「一、集…」过）。所以默认给到 236，而不是原来的 186。
  // 中栏略收窄一点，把宽度让给左栏和详情。
  const [wFilter, setWFilter] = useWidth('amtiku.w.filter3', 236, 170, 420)
  const [wList, setWList] = useWidth('amtiku.w.list3', 296, 220, 560)
  const searchRef = useRef<HTMLInputElement>(null)

  // 从详情点了考点跳过来时，在列表头上说明一句「现在在看什么」
  const [findNote, setFindNote] = useState('')
  const [paperMap, setPaperMap] = useState<Map<string, Q>>(new Map())
  /** 讲义选取的题（与卷子分开收集）。
   *
   *  为什么分开：卷子要打印成试卷，讲义要排成讲课稿，用途不同。
   *  老师可能同一道题既要进卷子也要进讲义，不能共用一个集合。 */
  const [handoutMap, setHandoutMap] = useState<Map<string, Q>>(new Map())

  /** 全局错误提示。
   *
   *  以前请求失败是**静默**的：接口 400 返回 {detail}，前端当数据用，
   *  界面表现成"没题""没变化"，查起来很费劲。现在 request() 统一抛错，
   *  这里接住并显示出来（代码审查报告 C-1 的配套修复）。
   */
  const [globalErr, setGlobalErr] = useState('')
  useEffect(() => {
    setGlobalErrHandler(setGlobalErr)
    return () => setGlobalErrHandler(null)
  }, [])
  // 「清空」的二次确认。挑好的卷子不该被一次误点清掉。
  const [sureClear, setSureClear] = useState(false)
  // 删题弹窗：`null` = 没开
  /** 删除弹窗要删的一批题。**单个和批量走同一个弹窗**——
   *  规矩一样（原因必选 + 口令 + 整批原子），只是数量不同。 */
  // 更新基线：两段式确认（误点一次不至于把报警基线推掉）
  const [showBase, setShowBase] = useState(false)      // 顶栏明细展开
  const [sureBase, setSureBase] = useState(false)
  const [baseMsg, setBaseMsg] = useState('')
  const doSnapshot = () => {
    api.snapshot().then((d) => {
      setSureBase(false); setBaseMsg(`✓ 基线已更新（${d.questions} 道）`)
      setReload((v) => v + 1)
      setTimeout(() => setBaseMsg(''), 4000)
    }).catch(() => setSureBase(false))
  }
  const [deleteAsk, setDeleteAsk] = useState<{ qs: Q[]; keys?: never } | { keys: string[]; qs?: never } | null>(null)
  const paper = useMemo(() => [...paperMap.values()], [paperMap])
  const handout = useMemo(() => [...handoutMap.values()], [handoutMap])
  // 导出对象**只认卷子**，默认为空。
  // 早先卷子一空就自动拿「当前筛选结果」顶上，于是刚进页面就显示
  // 「导出 38」——用户还没说要导出什么，程序先替他决定了。不对。
  // 筛选结果只是**随机组卷的题库**，要用得显式点一下。
  const exportList = paper
  const exportFrom = paper.length ? `卷子（${paper.length} 题）` : '卷子（空）'
  const paperScore = paper.reduce((s, q) => s + (SCORE[q.type] || 0), 0)
  const answered = paper.filter((q) => q.flags['解析']).length
  const answeredAll = answered === paper.length
  /** 点考点 → 列表立刻切成「只看这个考点」，并把该考点所在大类展开，
   *  这样侧栏能看见自己选中了什么。 */
  const findPoint = (pid: string, title: string) => {
    setPoints([pid])
    setQ(''); setType(''); setKind('')
    setPage(1)
    const p = (facets?.points || []).find((x: any) => x.value === pid)
    if (p) setOpenTopics((s2) => new Set([...s2, p.topic]))
    setFindNote(title)
  }
  /** 删一道题：走 `/api/questions/{key}/trash`，**移进回收站不是真删**。
   *  删完把列表和选中项都刷新一下，否则详情里还留着已经删掉的题。 */
  const deleteQuestions = (keys: string[], reason: string, password: string) =>
    api.trashBatch(keys, reason, password).then(() => {
      const ks = new Set(keys)
      // 卷子里、勾选里的也要一起清掉——不然删除后它们还挂在那儿
      setPaperMap((m) => { const n = new Map(m); for (const k of ks) n.delete(k); return n })
      setChecked((c) => { const n = new Set(c); for (const k of ks) n.delete(k); return n })
      setReload((v) => v + 1)
    }).catch(reportErr)

  const addToPaper = (it: Q) =>
    setPaperMap((m) => { const n = new Map(m); n.set(it.key, it); return n })
  const removeFromPaper = (k: string) =>
    setPaperMap((m) => { const n = new Map(m); n.delete(k); return n })


  // 手动改筛选（不是从详情点考点跳过来）就把那句说明收掉
  useEffect(() => { setFindNote('') }, [q, type, kind, has, missing, diffs, years])

  // **心跳**：页面活着服务器就活着，**页面一关服务器就退出**。
  //
  // 每 8 秒 ping 一次；关页面时用 `sendBeacon` 补最后一声——
  // beacon 在卸载时也能发出去，`fetch` 不保证。
  // 服务端只认「有没有 ping」：浏览器崩溃、断电、强杀都发不出关闭帧，
  // 但心跳停了就说明人走了。
  useEffect(() => {
    const ping = () => fetch('/api/alive', { method: 'POST' }).catch(() => {})
    ping()
    const t = setInterval(ping, 8000)
    const bye = () => {
      try { navigator.sendBeacon('/api/gone') } catch { /* 尽力而为 */ }
    }
    window.addEventListener('pagehide', bye)
    window.addEventListener('beforeunload', bye)
    return () => {
      clearInterval(t)
      window.removeEventListener('pagehide', bye)
      window.removeEventListener('beforeunload', bye)
    }
  }, [])


  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT') {
        e.preventDefault(); searchRef.current?.focus()
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault(); setShowExport(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /** 把选中的题一次性加进卷子 */
  const addChecked = () => {
    setPaperMap((m) => {
      const n = new Map(m)
      for (const q of items) if (checked.has(q.key)) n.set(q.key, q)
      return n
    })
    exitSelect()
    setTab('paper')
  }

  /** 批量加入讲义：与「加入卷子」并列。
   *
   *  加完**直接进讲义编辑页** —— 老师选完题的下一步就是排版，
   *  不跳的话还要自己找入口（用户反馈过）。 */
  const addCheckedToHandout = () => {
    setHandoutMap((m) => {
      const n = new Map(m)
      for (const q of items) if (checked.has(q.key)) n.set(q.key, q)
      return n
    })
    exitSelect()
    setTab('handout')
  }

  /** 单题加入讲义（卡片上的按钮），不跳转，方便连续加。 */
  const addOneToHandout = (it: Q) =>
    setHandoutMap((m) => new Map(m).set(it.key, it))
  /** **整章/整节选中**：把这一章（或这一节）下的考点一次性加进筛选。
   *
   *  为什么要这个：复习是**按章**走的——「导数这一章给我拉出来」。
   *  只有单个考点可点的话，一章十几个考点得点十几下。
   *  再点一次＝取消这一章（只取消本章的，不动别的章已选的）。 */

  return (
    <div className="flex h-full flex-col">
      {globalErr && (
        <div className="flex items-center gap-2 border-b border-warn/40 bg-warn-soft px-4 py-1.5
                        text-[12px] text-warn">
          <span className="font-medium">出错了</span>
          <span className="min-w-0 flex-1 truncate" title={globalErr}>{globalErr}</span>
          <button onClick={() => setGlobalErr('')} className="shrink-0 hover:underline">关闭</button>
        </div>
      )}
      <header className="flex items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
        <span className="text-[15px] font-semibold tracking-tight">AmTiKu</span>
        <span className="text-[11.5px] text-ink-faint">高中数学题库</span>
        <div className="ml-auto flex items-center gap-4 text-[11.5px]">
          {base && (<>
            {/* **顶栏只留一个状态点，细节点开才看。**
                早先是六段文字并排：「基线 17549 · 当前 17529 ✓ 存量未改动
                界面补录 8 规则迁移 398 求解写入 0 更新基线」——把标题都挤没了，
                而这六段里平时只有第一段（有没有异常）需要一眼看到。 */}
            <button onClick={() => setShowBase((v) => !v)}
              title="点开看明细"
              className={`press flex items-center gap-1.5 rounded-full border px-2.5 py-[3px] ${
                base.内容变化 > 0
                  ? 'border-warn/40 bg-warn-soft text-warn'
                  : 'border-has/35 bg-has-soft text-has'}`}>
              <span className="text-[11px] leading-none">
                {base.内容变化 > 0 ? '⚠' : '✓'}
              </span>
              <span className="text-[11.5px] font-medium">
                {base.内容变化 > 0 ? `存量有 ${base.内容变化} 处异常` : '存量未改动'}
              </span>
              <span className="text-[10px] opacity-60">{showBase ? '▴' : '▾'}</span>
            </button>

            {showBase && (
              <span className="anim-pop absolute right-4 top-[46px] z-30 w-[268px] rounded-xl border
                               border-border bg-surface p-3 text-[11.5px] shadow-lg">
                <div className="mb-2 flex items-baseline justify-between">
                  <span className="font-semibold text-ink">存量对账</span>
                  <span className="text-[10.5px] text-ink-faint">
                    基线 {base.基线} · 当前 {base.当前}
                  </span>
                </div>
                <div className="space-y-1">
                  <BaseRow label="内容变化" n={base.内容变化} tone="warn"
                    hint="没登记过的改动，这才要看" />
                  <BaseRow label="界面补录" n={base.界面补录 ?? 0}
                    hint="你在界面上改了答案/解析/题型" />
                  <BaseRow label="规则迁移" n={base.规则迁移 ?? 0}
                    hint="批量规范化改的（有变更记录为证）" />
                  <BaseRow label="求解写入" n={base.求解写入 ?? 0}
                    hint="求解器一道一道做的" />
                  <BaseRow label="录入升级" n={base.录入升级 ?? 0}
                    hint="点「用这份更新」升级的" />
                </div>
                <div className="mt-2 border-t border-border pt-2 text-[10.5px] leading-relaxed text-ink-faint">
                  后四项都是有意的，只作记录。有意改完数据后把当前状态存成新基线，
                  下次报警才是真有事。
                </div>
                <button onClick={() => { setSureBase(true); setBaseMsg('') }}
                  className="press mt-2 w-full rounded-lg border border-border bg-bg px-2 py-1.5
                             text-[11.5px] text-ink-soft hover:border-brand/40 hover:text-brand-ink">
                  把当前 {base.当前} 道存成新基线
                </button>
                {baseMsg && <div className="mt-1.5 text-center text-has">{baseMsg}</div>}
              </span>
            )}
            {sureBase && (
              <span className="anim-pop absolute right-4 top-[46px] z-40 inline-flex items-center
                               gap-1.5 rounded-lg border border-brand/35 bg-brand-soft px-2.5 py-1.5
                               text-[11.5px] shadow-lg">
                <span className="text-brand-ink">把当前 {base.当前} 道存成基线？</span>
                <button onClick={doSnapshot}
                  className="press rounded bg-brand px-2 py-[2px] text-white">确定</button>
                <button onClick={() => setSureBase(false)}
                  className="press rounded border border-border bg-surface px-2 py-[2px] text-ink-soft">
                  取消
                </button>
              </span>
            )}
            {baseMsg && <span className="text-has">{baseMsg}</span>}
          </>)}
          <button onClick={() => setShowIngest(true)}
            className="rounded-lg border border-border bg-bg px-2.5 py-1 text-[12px]
                       text-ink-soft hover:border-brand/40 hover:text-brand-ink">
            录入题目
          </button>
          {/* 导出入口常驻：早先只在「卷子」标签页且卷子非空时才出现，
              卷子一空就找不到导出去哪了 */}
          <button onClick={() => setShowExport(true)}
            title="打开组卷导出：可以随机组卷，也可以把筛选结果加进来"
            className="rounded-lg bg-brand px-2.5 py-1 text-[12px] font-medium text-white
                       hover:opacity-90">
            导出{exportList.length ? ` ${exportList.length}` : ''}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside style={{ width: wFilter }}
          className="shrink-0 overflow-y-auto border-r border-border bg-surface px-3 py-3.5">
          <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="搜索…  按 / 聚焦"
            className="mb-4 w-full rounded-lg border border-border bg-bg px-2.5 py-1.5 text-[12.5px]
                       outline-none placeholder:text-ink-faint focus:border-brand/40 focus:bg-surface" />
          <div className="mb-4">
            <div className="mb-1.5 flex items-baseline gap-1.5 text-[11px] font-semibold tracking-wide text-ink-faint">
              <span>考点</span>
              <span className="font-normal">
                {facets ? `${facets.points_covered}/${facets.points.length}` : ''}
              </span>
              {points.length > 0 && (
                <button onClick={() => setPoints([])}
                  className="ml-auto font-normal text-brand-ink">清空选中的 {points.length}</button>
              )}
            </div>
            {/* 列出知识点库**全部**考点，没有题目的计数为 0 —— 空考点本身就是要看的信息 */}
            {/* 153 个考点全展开太长，会挡住导出流程 —— 按大类折叠，点开才看。
                选中的考点所在大类会自动展开，不然选完就看不见自己选了什么。

                排版三条：① 考点名**加粗**，一眼抓得住；
                ② 计数走固定宽度的右对齐列，不跟着名字长短乱跑；
                ③ 三级层次靠缩进 + 分隔线，不靠字号堆叠。 */}
            <div className="mb-2 flex items-center gap-2 text-[10.5px] text-ink-faint">
              <button onClick={() => setOpenTopics(new Set(
                groupTree(facets?.points || []).map((g) => g.topic)))}
                className="rounded border border-border px-1.5 py-[1px] hover:border-brand/40 hover:text-brand-ink">
                全部展开
              </button>
              <button onClick={() => setOpenTopics(new Set())}
                className="rounded border border-border px-1.5 py-[1px] hover:border-brand/40 hover:text-brand-ink">
                全部收起
              </button>
              <span className="ml-auto tabular-nums text-ink-faint/70">
                {openTopics.size ? `展开 ${openTopics.size}` : '已收起'}
              </span>
            </div>

            <div className="space-y-1 pr-0.5">
              {groupTree(facets?.points || []).map(({ topic, sections }) => {
                const all = sections.flatMap((s) => s.points)
                const cov = all.filter((p) => p.n > 0).length
                const sel = all.filter((p) => points.includes(p.value)).length
                const open = openTopics.has(topic)
                return (
                  <div key={topic}
                    className={`overflow-hidden rounded-lg border transition-colors ${
                      sel ? 'border-brand/35 bg-brand-soft/25'
                          : open ? 'border-border bg-surface' : 'border-transparent'}`}>
                    {/* 大类。**箭头管展开、名字管筛选**——
                        用户要的就是"点这一章，题目就剩这一章的"，
                        所以名字本身必须是可点的筛选入口，不能只是展开。
                        右边那个「全章」是同一件事的第二个入口（点着更顺手），
                        顺带显示"这一章是不是已经全选上了"。 */}
                    <div className={`flex w-full items-center gap-1.5 pr-1.5 transition-colors ${
                      sel ? 'bg-brand-soft/30' : open ? '' : 'hover:bg-muted'}`}>
                      <button onClick={() => toggleTopic(topic)}
                        title={open ? '收起' : '展开'}
                        className="shrink-0 py-[6px] pl-2 pr-0.5 text-[9px] text-ink-faint
                                   hover:text-brand-ink">
                        {open ? '▾' : '▸'}
                      </button>
                      <button onClick={() => { togglePoints(all.map((p) => p.value))
                                               if (!open) setOpenTopics((s2) => new Set([...s2, topic])) }}
                        title={`只看「${topic}」这一章的题目（${all.length} 个考点）`}
                        className="flex min-w-0 flex-1 items-center gap-1.5 py-[6px] text-left">
                        {/* **不截断**——章节名被切掉就没法认了。
                            字小一号，换行显示，最多两行。 */}
                        <span className={`min-w-0 flex-1 text-[11.5px] font-semibold leading-tight ${
                          sel ? 'text-brand-ink' : 'text-ink'}`}>{topic}</span>
                        {sel > 0 && (
                          <span className="shrink-0 rounded-full bg-brand px-1.5 text-[9.5px]
                                           font-medium leading-[15px] text-white">{sel}</span>
                        )}
                        <span className={`w-9 shrink-0 text-right text-[10px] tabular-nums ${
                          cov ? 'text-ink-faint' : 'text-warn/70'}`}>{cov}/{all.length}</span>
                      </button>
                      {cov > 0 && (
                        <button onClick={() => { togglePoints(all.map((p) => p.value))
                                                 if (!open) setOpenTopics((s2) => new Set([...s2, topic])) }}
                          title={`只看「${topic}」这一章的题目`}
                          className={`press shrink-0 rounded border px-1.5 py-[1px] text-[9.5px]
                                      transition-colors ${
                            sel === all.length
                              ? 'border-brand bg-brand text-white'
                              : 'border-border bg-surface text-ink-faint hover:border-brand/40 hover:text-brand-ink'}`}>
                          {sel === all.length ? '已全选' : '全章'}
                        </button>
                      )}
                    </div>

                    {open && (
                      <div className="border-t border-border/60 px-2 pb-1.5 pt-1">
                        {sections.map(({ section, points: list }) => (
                          <div key={section} className="mb-1 last:mb-0">
                            {/* 小类。只有一个考点时不显示——那种情况下小类名和
                                考点名几乎一样，纯属噪声。 */}
                            {list.length > 1 && (() => {
                              const ids = list.map((p) => p.value)
                              const secAll = ids.every((i) => points.includes(i))
                              return (
                                <div className={`mb-[2px] flex items-center gap-1 border-l-2 pl-1.5 ${
                                  secAll ? 'border-brand' : 'border-border'}`}>
                                  {/* 小章节同理：**点名字就只看这一节** */}
                                  <button onClick={() => togglePoints(ids)}
                                    title={`只看「${section}」这一节的题目`}
                                    className={`min-w-0 flex-1 text-left text-[10px] leading-tight
                                                font-medium hover:text-brand-ink ${
                                      secAll ? 'text-brand-ink' : 'text-ink-faint'}`}>
                                    {section}
                                  </button>
                                  <button onClick={() => togglePoints(ids)}
                                    className={`press shrink-0 rounded px-1 text-[9.5px] transition-colors ${
                                      secAll ? 'bg-brand text-white'
                                             : 'text-ink-faint hover:bg-brand-soft hover:text-brand-ink'}`}>
                                    {secAll ? '已选' : '全节'}
                                  </button>
                                </div>
                              )
                            })()}
                            {list.map((p) => {
                              const on = points.includes(p.value)
                              return (
                                <button key={p.value} onClick={() => togglePoint(p.value)}
                                  title={`${p.title}${p.n ? ` · ${p.n} 道` : ' · 暂无题目'}`}
                                  className={`flex w-full items-center gap-2 rounded py-[3px] pl-2 pr-1.5
                                              text-left transition-colors ${
                                    on ? 'bg-brand text-white'
                                       : p.n ? 'hover:bg-muted' : 'hover:bg-muted'}`}>
                                  <span className={`min-w-0 flex-1 truncate text-[11px] font-semibold ${
                                    on ? 'text-white'
                                       : p.n ? 'text-ink-soft' : 'text-ink-faint/60'}`}>
                                    {p.title}
                                  </span>
                                  <span className={`w-6 shrink-0 text-right text-[10px] tabular-nums ${
                                    on ? 'text-white/80'
                                       : p.n ? 'text-ink-faint' : 'text-warn/50'}`}>
                                    {p.n || '—'}
                                  </span>
                                </button>
                              )
                            })}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-faint">只看有</div>
            <div className="flex flex-wrap gap-1">
              {FLAG_KEYS.map(([k, label]) => (
                <Chip key={k} on={has.includes(k)} onClick={() => toggleHas(k)}>{label}</Chip>
              ))}
            </div>
            {activeFilters > 0 && (
              <button onClick={() => { setHas([]); setPoints([]); setDiffs([]); setType(''); setKind('') }}
                className="mt-2 text-[11px] text-ink-faint hover:text-brand-ink">
                清空全部筛选（{activeFilters}）
              </button>
            )}
          </div>

          {/* ── 讲义入口 ──
              与「筛选题库」是两种不同的工作：筛选是为了看题，
              讲义是为了**排版输出**。所以给它一个独立、显眼的入口，
              而不是埋在组卷导出页里。 */}
          <div className="mt-5 border-t border-border pt-3.5">
            <button onClick={() => setTab('handout')}
              className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${
                tab === 'handout'
                  ? 'border-brand/40 bg-brand-soft'
                  : 'border-border bg-bg hover:border-brand/40 hover:bg-brand-soft/40'}`}>
              <div className={`flex items-center gap-2 text-[12.5px] font-medium ${
                tab === 'handout' ? 'text-brand-ink' : 'text-ink'}`}>
                <span>📝</span>
                <span>制作讲义</span>
              </div>
              <div className="mt-0.5 text-[10.5px] leading-relaxed text-ink-faint">
                拖拽排版 · 自写讲解 · 导出 PDF
              </div>
            </button>
            {handoutN > 0 && (
              <div className="mt-1.5 text-[10.5px] text-ink-faint">
                已有 {handoutN} 份讲义
              </div>
            )}
          </div>
        </aside>

        <Grip width={wFilter} setWidth={setWFilter} min={150} max={380} />

        <section style={{ width: wList }} className="flex shrink-0 flex-col">
          {/* **当前作用域**：一眼看出「现在看的是哪一批题」。
              从详情点考点跳过来时，这里会写明看的是哪个考点。 */}
          <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-2 text-[11.5px] text-ink-faint">
            <span className="font-medium text-ink">{loading ? '加载中…' : `${total} 道`}</span>
            <span className="min-w-0 truncate">
              {points.length === 1
                ? `考点 · ${findNote || (facets?.points || []).find((x: any) => x.value === points[0])?.title || points[0]}`
                : scopeName ? scopeName
                : points.length > 1 ? `考点 · ${points.length} 个`
                : findNote
                  || (missing.length === 2 && missing.includes('答案') && missing.includes('解析')
                      ? '没解析也没答案'
                      : missing.length ? `缺：${missing.join('、')}`
                      : has.length ? `有：${has.join('、')}`
                      : '全部题目')}
            </span>
            {findNote && (
              <button onClick={() => { setPoints([]); setFindNote('')
                                       setMissing([]); setHas([]) }}
                className="shrink-0 rounded border border-border px-1.5 py-[1px] text-[10.5px]
                           text-ink-faint hover:border-warn/40 hover:text-warn">返回全部</button>
            )}
            {/* 每页条数。题多了以后一屏铺 200 条根本没法看。 */}
            <select value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value))}
              title="每页显示多少道"
              className="rounded border border-border bg-bg px-1 py-[1px] text-[11px] outline-none">
              {[10, 20, 50, 100, 200].map((n) => (
                <option key={n} value={n}>每页 {n}</option>
              ))}
            </select>
            {activeFilters > 0 && <span className="text-brand-ink">已筛选</span>}
            {!selectMode ? (
              <button onClick={() => setSelectMode(true)} disabled={!items.length}
                className="ml-auto rounded-md border border-border px-2 py-[3px] text-[11px]
                           text-ink-soft hover:border-brand/40 hover:text-brand-ink disabled:opacity-40">
                选定
              </button>
            ) : (
              <button onClick={exitSelect}
                className="ml-auto rounded-md border border-border px-2 py-[3px] text-[11px] hover:bg-muted">
                退出选定
              </button>
            )}
          </div>
          {/* ── 筛选条 ──
              五个维度各占一格，选中的亮起来并显示选了什么。
              常驻展开会把这一列撑满，而**考点在左边才是总纲**。 */}
          <div className="flex flex-wrap items-center gap-1.5 border-b border-border bg-surface px-2.5 py-2">
            <FacetMenu label="排序" active={sort !== ''}
              summary={<span className="text-ink">{SORT_LABEL[sort] || '默认'}</span>}
              onClear={() => setSort('')}>
              <div className="space-y-0.5">
                {([['used', '频次 高→低'], ['diff', '易 → 难'], ['diff2', '难 → 易'],
                   ['', '题库原序'], ['new', '最新录入'], ['old', '最早录入'],
                   ['solved', '刚解出的']] as const).map(([v, label]) => (
                  <button key={v} onClick={() => setSort(v as any)}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-[12px]
                                hover:bg-muted ${sort === v ? 'bg-brand-soft font-medium text-brand-ink' : 'text-ink-soft'}`}>
                    <span className="w-3 text-[10px]">{sort === v ? '✓' : ''}</span>{label}
                  </button>
                ))}
              </div>
            </FacetMenu>

            <FacetMenu label="类别" active={!!kind}
              summary={kind && <span className="text-ink">{kind}题</span>}
              onClear={() => setKind('')}>
              <div className="flex flex-wrap gap-1">
                {facets?.kinds.map((k) => (
                  <Chip key={k.value} n={k.n} on={kind === k.value}
                    onClick={() => setKind(kind === k.value ? '' : k.value)}>{k.value}题</Chip>
                ))}
              </div>
            </FacetMenu>

            <FacetMenu label="题型" active={!!type}
              summary={type && <span className="text-ink">1 项</span>}
              onClear={() => setType('')}>
              <div className="flex flex-wrap gap-1">
                {facets?.types.map((t) => (
                  <Chip key={t.value} n={t.n} on={type === t.value}
                    onClick={() => setType(type === t.value ? '' : t.value)}>{t.label}</Chip>
                ))}
              </div>
            </FacetMenu>

            <FacetMenu label="难度" active={diffs.length > 0}
              summary={diffs.length > 0 &&
                <span className="tracking-tight text-ink">{diffs.map((d) => '★'.repeat(DIFF_STARS[d] || 0)).join(' ')}</span>}
              onClear={() => setDiffs([])}>
              <div className="flex flex-wrap gap-1">
                {facets?.difficulties.map((d) => (
                  <Chip key={d.value} n={d.n} on={diffs.includes(d.value)} onClick={() => toggleDiff(d.value)}>
                    <span className="tracking-tight">{'★'.repeat(DIFF_STARS[d.value] || 0)}</span>
                    <span className="ml-1 text-[10.5px]">{d.value.replace('题', '')}</span>
                  </Chip>
                ))}
              </div>
              <div className="mt-1.5 text-[10px] leading-snug text-ink-faint">
                由主考点派生；手动改过的以手动的为准
              </div>
            </FacetMenu>

            {/* 年份有四五十个，用密的数字格而不是 Chip */}
            <FacetMenu label="年份" wide active={years.length > 0}
              summary={years.length > 0 && <span className="text-ink">{years.length} 个</span>}
              onClear={() => setYears([])}>
              <div className="flex flex-wrap gap-[3px]">
                {facets?.years.map((y) => {
                  const on = years.includes(y.value)
                  return (
                    <button key={y.value} onClick={() => toggleYear(y.value)}
                      title={`${y.value} 年 · ${y.n} 道`}
                      className={`rounded px-1.5 py-[3px] text-[11px] tabular-nums transition-colors ${
                        on ? 'bg-brand text-white'
                           : 'bg-muted text-ink-soft hover:bg-brand-soft hover:text-brand-ink'}`}>
                      {y.value}
                    </button>
                  )
                })}
              </div>
            </FacetMenu>

            <FacetMenu label="有 / 缺" active={has.length + missing.length > 0}
              summary={(has.length + missing.length) > 0 &&
                <span className="text-ink">{has.length + missing.length} 项</span>}
              onClear={() => { setHas([]); setMissing([]) }}>
              {/* 一键：「没解析也没答案」。这是**最常用的一个视角**——
                  它出来的就是还没做的题（求解器的活）。 */}
              <button onClick={() => {
                  const on = missing.length === 2 && missing.includes('答案') && missing.includes('解析')
                  setMissing(on ? [] : ['答案', '解析'])
                }}
                className={`press mb-2 w-full rounded-lg border px-2 py-1.5 text-left text-[12px]
                            transition-colors ${
                  missing.includes('答案') && missing.includes('解析') && missing.length === 2
                    ? 'border-warn/45 bg-warn-soft font-medium text-warn'
                    : 'border-border bg-bg text-ink-soft hover:border-warn/40 hover:text-warn'}`}>
                ⚠ 没解析也没答案 <span className="text-[10.5px] opacity-70">（还没做的题）</span>
              </button>

              <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">只看有</div>
              <div className="mb-2 flex flex-wrap gap-1">
                {FLAG_KEYS.map(([k, label]) => (
                  <Chip key={k} on={has.includes(k)} onClick={() => toggleHas(k)}>{label}</Chip>
                ))}
              </div>

              <div className="mb-1 text-[10.5px] font-semibold text-ink-faint">只看缺</div>
              <div className="flex flex-wrap gap-1">
                {FLAG_KEYS.map(([k, label]) => (
                  <Chip key={k} on={missing.includes(k)} onClick={() => toggleMissing(k)}>{label}</Chip>
                ))}
              </div>
              <div className="mt-1.5 text-[10px] leading-snug text-ink-faint">
                同时选了多个「缺」，表示**这些全都缺**
              </div>
            </FacetMenu>

            {/* 当前筛选的**可删除摘要**——不点开也知道筛了什么 */}
            {(activeFilters > 0 || points.length > 0) && (
              <button onClick={() => { setHas([]); setMissing([]); setPoints([]); setDiffs([])
                                       setType(''); setKind(''); setYears([]) }}
                className="ml-auto rounded-lg border border-border px-2 py-[3px] text-[11px]
                           text-ink-faint hover:border-warn/40 hover:text-warn">
                清除全部（{(activeFilters || 0) + missing.length + points.length}）
              </button>
            )}
          </div>

          {selectMode && (
            <div className="flex items-center gap-2 border-b border-brand/25 bg-brand-soft/40 px-3 py-1.5 text-[11.5px]">
              <span className="font-medium text-brand-ink">已选 {checked.size} 道</span>
              <button onClick={() => setChecked(new Set(items.map((q) => q.key)))}
                className="rounded border border-border bg-surface px-1.5 py-[2px] hover:bg-muted">全选本页</button>
              <button onClick={() => setChecked(new Set())}
                className="rounded border border-border bg-surface px-1.5 py-[2px] hover:bg-muted">清空</button>
              {/* **批量删除**：一道道的删除太慢——"很多题目现在不考了"，
                  所以要能一次勾一批一起删。走的是同一个删除弹窗，
                  原因和口令一样都不能少（批量更危险，规矩一条不减）。 */}
              <button onClick={() => setDeleteAsk({ keys: [...checked] })}
                disabled={!checked.size}
                className="ml-auto rounded border border-warn/40 bg-surface px-2.5 py-[3px]
                           text-warn hover:bg-warn-soft disabled:opacity-40">
                删除选中 {checked.size || ''}
              </button>
              <button onClick={addChecked} disabled={!checked.size}
                className="rounded border border-brand/40 bg-surface px-2.5 py-[3px]
                           font-medium text-brand-ink hover:bg-brand-soft disabled:opacity-40">
                加入卷子
              </button>
              <button onClick={addCheckedToHandout} disabled={!checked.size}
                className="rounded bg-brand px-2.5 py-[3px] font-medium text-white
                           hover:opacity-90 disabled:opacity-40">
                加入讲义
              </button>
            </div>
          )}
          {/* 用 `key` 把这一层绑到「页码 + 筛选条件」上：变了就整块重挂载，
              逐条入场动画才会重新跑一遍。不这么做的话，翻页时新内容会
              "啪"地出现，看不出列表已经换了一批。 */}
          <div key={`${page}|${q}|${type}|${kind}|${points.join()}|${diffs.join()}|${years.join()}|${sort}`}
            className="anim-stagger min-h-0 flex-1 space-y-2 overflow-y-auto p-2.5"
            ref={(el) => { listRef.current = el }}>
            {items.map((it) => (
              <QuestionCard key={it.key} q={it} active={sel?.key === it.key}
                inPaper={paperMap.has(it.key)}
                inHandout={handoutMap.has(it.key)}
                selectMode={selectMode} checked={checked.has(it.key)}
                onOpen={() => {
                  // 详情永远更新；只有不在选定模式时才自动切到详情页
                  // （选定模式下连续勾题，不希望每次都被弹走）
                  setSel(it)
                  if (!selectMode) setTab('detail')
                }}
                onAdd={() => { addToPaper(it); setTab('paper') }}
                onAddHandout={() => addOneToHandout(it)}
                onToggle={() => toggleCheck(it.key)} />
            ))}
            {!loading && items.length === 0 && (
              <div className="py-10 text-center text-[12.5px] text-ink-faint">没有匹配的题</div>
            )}
          </div>

          {/* 分页条。**总页数大于 1 才出现**——只有一页时占地方没意义。 */}
          {total > pageSize && (
            <div className="flex items-center gap-1 border-t border-border px-3 py-1.5 text-[11.5px] text-ink-faint">
              <button onClick={() => { setPage(1); listRef.current?.scrollTo(0, 0) }}
                disabled={page <= 1}
                className="rounded border border-border px-1.5 py-[2px] hover:bg-muted disabled:opacity-30">
                «
              </button>
              <button onClick={() => { setPage((p) => Math.max(1, p - 1)); listRef.current?.scrollTo(0, 0) }}
                disabled={page <= 1}
                className="rounded border border-border px-1.5 py-[2px] hover:bg-muted disabled:opacity-30">
                ‹ 上一页
              </button>
              <span className="px-1">
                第 <input value={pageInput} onChange={(e) => setPageInput(e.target.value)}
                  onBlur={jumpPage} onKeyDown={(e) => { if (e.key === 'Enter') jumpPage() }}
                  className="w-9 rounded border border-border bg-bg px-1 py-[1px] text-center
                             text-[11.5px] outline-none" />
                / {Math.max(1, Math.ceil(total / pageSize))} 页
              </span>
              <button onClick={() => { setPage((p) => p + 1); listRef.current?.scrollTo(0, 0) }}
                disabled={page >= Math.ceil(total / pageSize)}
                className="rounded border border-border px-1.5 py-[2px] hover:bg-muted disabled:opacity-30">
                下一页 ›
              </button>
              <button onClick={() => { setPage(Math.ceil(total / pageSize)); listRef.current?.scrollTo(0, 0) }}
                disabled={page >= Math.ceil(total / pageSize)}
                className="rounded border border-border px-1.5 py-[2px] hover:bg-muted disabled:opacity-30">
                »
              </button>
              <span className="ml-auto">
                {pageSize * (page - 1) + 1}–{Math.min(total, page * pageSize)}
              </span>
            </div>
          )}
        </section>

        <Grip width={wList} setWidth={setWList} min={220} max={560} />

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-1 border-b border-border px-3 py-1.5">
            {/* **源码和「题目详情」「变更记录」平级**——它是要经常翻的东西，
                埋在详情页底部的抽屉里等于藏起来（用户反馈"不好找到"）。 */}
            {(['detail', 'tex', 'paper', 'handout', 'stats', 'changes', 'trash'] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`rounded-lg px-2.5 py-1 text-[12px] transition-colors ${
                  tab === t ? 'bg-brand-soft font-medium text-brand-ink' : 'text-ink-soft hover:bg-muted'}`}>
                {t === 'detail' ? '题目详情' : t === 'tex' ? 'LaTeX 源码'
                  : t === 'paper' ? `卷子 ${paper.length}`
                  : t === 'handout' ? '讲义编辑'
                  : t === 'stats' ? '统计' : t === 'trash' ? '回收站' : '变更记录'}
              </button>
            ))}
            {tab === 'paper' && paper.length > 0 && (
              <button onClick={() => setShowExport(true)}
                className="ml-auto rounded-lg bg-brand px-3 py-1 text-[12px] font-medium text-white hover:opacity-90">
                导出套卷 ⌘↵
              </button>
            )}
            {tab === 'paper' && paper.length === 0 && items.length > 0 && (
              <button onClick={() => { setSelectMode(true); setTab('detail') }}
                className="ml-auto rounded-lg border border-border bg-surface px-3 py-1 text-[12px]
                           text-ink-soft hover:border-brand/40 hover:text-brand-ink">
                去列表选定题目
              </button>
            )}
          </div>

          {tab === 'handout' ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-[13px] text-ink-faint">
              <div>讲议编辑器已全屏打开</div>
              <button onClick={() => setTab('detail')}
                className="rounded-lg border border-border px-3 py-1 text-[12px] hover:border-brand/40">
                关闭全屏编辑器
              </button>
            </div>
            )
            : tab === 'changes' ? <Changes />
            : tab === 'trash' ? <Trash onChanged={() => setReload((v) => v + 1)} />
            : tab === 'stats' ? <Stats key={reload} />
            : tab === 'tex' ? (
              <div className="h-full overflow-y-auto px-5 py-4">
                {sel ? (<>
                  <div className="mb-2 flex flex-wrap items-baseline gap-2">
                    <span className="text-[12.5px] font-medium text-ink">
                      {sel.point_titles?.[0] || sel.key}
                    </span>
                    <span className="text-[11px] text-ink-faint">
                      {sel.type_label} · <code className="font-mono">{sel.key}</code>
                    </span>
                  </div>
                  <TexSource qkey={sel.key} />
                </>) : (
                  <div className="flex h-full items-center justify-center text-[13px] text-ink-faint">
                    先在列表里选一道题
                  </div>
                )}
              </div>
            ) : tab === 'detail' ? (
            <div key={sel?.key} className="anim-slide-r h-full">
            <Detail q={sel} facets={facets} onFindPoint={findPoint}
              onDeleteAsk={() => sel && setDeleteAsk({ qs: [sel] })}
              onSaved={(d) => {
              setSel(d)                              // 详情立刻反映新标签
              setItems((xs) => xs.map((x) => (x.key === d.key ? { ...x, ...d } : x)))
            }} />
            </div>
          ) : (
            <div className="h-full overflow-y-auto px-4 py-3">
              {paper.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 text-[12.5px] text-ink-faint">
                  <span>卷子还是空的</span>
                  <span className="text-[11.5px]">在左侧题目上点 <b className="text-brand-ink">＋</b> 加入</span>
                </div>
              ) : (<>
                {/* 导出前就该看到这卷子齐不齐 */}
                <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-border bg-surface px-3 py-2 text-[11.5px]">
                  <span><b className="text-[13px]">{paper.length}</b> 题</span>
                  <span><b className="text-[13px]">{paperScore}</b> 分</span>
                  <span className={answeredAll ? 'text-has' : 'text-warn'}>
                    有解析 {answered}/{paper.length}
                  </span>
                  <span className="text-ink-faint">
                    {SECTION_LABEL.filter(([t]) => paper.some((q) => q.type === t))
                      .map(([t, label]) => `${label.slice(0, 2)}${paper.filter((q) => q.type === t).length}`)
                      .join(' · ')}
                  </span>
                  {/* **一键清空**：挑卷子经常要推倒重来，一道一道点 ✕ 太慢。
                      但这是手工挑出来的，误点代价大——所以点第一下只是变成
                      「确认清空？」，点第二下才真清，鼠标移开就自动收回。 */}
                  <button
                    onClick={() => {
                      if (sureClear) { setPaperMap(new Map()); setSureClear(false) }
                      else setSureClear(true)
                    }}
                    onMouseLeave={() => setSureClear(false)}
                    className={`ml-auto rounded-md border px-2 py-[3px] text-[11px] transition-colors ${
                      sureClear
                        ? 'border-warn/50 bg-warn-soft font-medium text-warn'
                        : 'border-border bg-bg text-ink-faint hover:border-warn/40 hover:text-warn'}`}>
                    {sureClear ? '确认清空？' : '清空'}
                  </button>
                </div>
                {SECTION_LABEL.map(([t, label]) => {
                  const items = paper.filter((q) => q.type === t)
                  if (!items.length) return null
                  const sc = SCORE[t] * items.length
                  return (
                    <div key={t} className="mb-3">
                      <div className="mb-1 flex items-baseline gap-2 text-[11px] text-ink-faint">
                        <span className="font-semibold text-ink-soft">{label}</span>
                        <span>{items.length} 题 · {sc} 分</span>
                      </div>
                      <ol className="space-y-1.5">
                        {items.map((it, i) => (
                          <li key={it.key}
                            onClick={() => { setSel(it); setTab('detail') }}
                            title="点击看详情"
                            className="press flex cursor-pointer items-center gap-2 rounded-lg border border-border
                                       bg-surface px-3 py-2 transition-colors hover:border-brand/30 hover:bg-muted/50">
                            <span className="w-5 text-right text-[11.5px] text-ink-faint">{i + 1}</span>
                            <span className="min-w-0 flex-1 truncate text-[12.5px]">
                              {it.point_titles[0] || it.key}
                            </span>
                            {it.difficulty && (
                              <span title={it.difficulty}
                                className="shrink-0 rounded bg-muted px-1.5 py-[1px] text-[10.5px]
                                           tracking-tight text-brand-ink">
                                {'★'.repeat(DIFF_STARS[it.difficulty] || 0)}
                              </span>
                            )}
                            <Flags flags={it.flags} />
                            <button onClick={() => removeFromPaper(it.key)}
                              className="text-[15px] leading-none text-ink-faint hover:text-warn">×</button>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )
                })}
              </>)}
            </div>
          )}
        </main>
      </div>

      {showExport && <ExportPage init={exportList} pool={items} from={exportFrom}
        filters={{ q, type, kind, point: points.join(','),
                   difficulty: diffs.join(','), has: has.join(','),
                   year: years.join(',') }}
        onClose={() => setShowExport(false)} />}
      {deleteAsk && (
        <DeleteModal
          qs={deleteAsk.qs ?? items.filter((x) => (deleteAsk.keys || []).includes(x.key))}
          keys={deleteAsk.keys}
          onCancel={() => setDeleteAsk(null)}
          onConfirm={(reason, _note, pw) =>
            deleteQuestions(deleteAsk.keys ?? (deleteAsk.qs || []).map((x) => x.key),
                            reason, pw).then(() => setDeleteAsk(null))} />
      )}
      {showIngest && <IngestDrawer facets={facets} onClose={() => setShowIngest(false)}
                                  onDone={() => setReload((n) => n + 1)} />}
    
      {/* ── 讲义编辑器（全屏覆盖）──
          三栏排版需要整屏宽度；塞在 tab 里会被压成一条。
          这里用 fixed 覆盖整个窗口，自带关闭按钮。 */}
      {tab === 'handout' && (
        <div className="fixed inset-0 z-40 flex flex-col bg-surface">
          <div className="flex items-center gap-2 border-b border-border bg-bg px-4 py-2">
            <span className="text-[13px] font-medium">讲义制作</span>
            <span className="text-[11px] text-ink-faint">
              拖左侧题目到中间 · 拖 ⠿ 调整顺序 · 点文字直接编辑
            </span>
            <button onClick={() => setTab('detail')}
              className="ml-auto rounded-lg border border-border px-2.5 py-1 text-[12px]
                         text-ink-soft hover:border-brand/40 hover:text-brand-ink">
              退出编辑
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <CanvasEditor handoutQs={handout.length ? handout : paper} />
          </div>
        </div>
      )}
</div>
  )
}
