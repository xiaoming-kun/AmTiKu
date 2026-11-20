/** 组卷工作区：左边是卷子，右边是「这份卷子能不能印」的体检和出口。
 *
 *  旧版的组卷藏在「智能组卷」弹层里，而当前卷子又住在题库栏顶部的一条 bar 上；
 *  同一件事分在两个地方，用户得先理解「卷子条 / 组卷页 / 导出弹层」三层关系。
 *  现在统一到一个页面：卷子就是主体，智能组卷和导出是这台机器上的两个动作。
 */
import {
  AlertTriangle, ArrowLeft, CheckCircle2, FileDown, FileStack, FolderOpen,
  Plus, Sparkles, Wand2,
} from 'lucide-react'
import type { Q } from '@/lib/types'
import { STAGE_BY_KEY, type Stage } from '@/lib/stage'
import PaperPanel from '@/app/PaperPanel'

export default function PaperStudio({
  stage, paper, score, answered, onOpenQuestion, onRemove, onMove, onSwap,
  onExport, onBank, onPapers, onGenerate,
}: {
  stage: Stage
  paper: Q[]
  score: number
  answered: number
  onOpenQuestion: (key: string) => void
  onRemove: (k: string) => void
  onMove: (k: string, d: -1 | 1) => void
  onSwap: (oldKey: string, q: Q) => void
  onExport: () => void
  onBank: () => void
  onPapers: () => void
  onGenerate: () => void
}) {
  const missing = paper.length - answered
  const canPrint = paper.length > 0 && missing === 0
  const small = stage !== 'senior'
  const hasStagePaper = paper.some((q) => q.stage === stage)
  if (small && !hasStagePaper) {
    const meta = STAGE_BY_KEY[stage]
    return (
      <div className="b-scroll h-full overflow-y-auto">
        <div className="b-page max-w-[1000px]">
          <div className="b-eyebrow flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
            AmMath · {meta.name} · 组卷
          </div>
          <h2 className="mt-1.5 text-[30px] font-semibold tracking-tight">诊断卷</h2>
          <p className="mt-1 max-w-[660px] text-[12px] leading-relaxed text-ink-faint">
            {meta.name}还没有正式题库，组卷从诊断题走：在诊断题库里按教材位置筛好，
            一键排出学生卷或教师版 PDF。每份最多 20 道，够一次小测。
          </p>
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {[
              ['01', '筛知识点', '按册 / 章 / 难度筛出这次要测的范围'],
              ['02', '选版本', '学生卷留空，教师版带答案与解析'],
              ['03', '打开 PDF', '直接编译；产物在「测试卷」分类下'],
            ].map(([n, t, d]) => (
              <div key={n} className="b-card p-4">
                <div className="text-[10px] font-semibold text-brand-ink">{n}</div>
                <div className="mt-1 text-[12.5px] font-semibold">{t}</div>
                <div className="mt-1 text-[10.5px] leading-relaxed text-ink-faint">{d}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={onBank} className="b-btn b-btn-primary">去诊断题库选题</button>
            <button onClick={onPapers} className="b-btn b-btn-secondary">打开试卷库</button>
          </div>
          {paper.length > 0 && (
            <div className="mt-4 flex items-start gap-2 rounded-xl border border-warn-line
                            bg-warn-soft px-4 py-3 text-[11.5px] leading-relaxed text-warn">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>
                当前卷子里还有 <b>{paper.length}</b> 道题（从其他学段挑的）。
                诊断卷不会使用它们；切回对应学段可以继续编辑那份卷子。
              </span>
            </div>
          )}
          <div className="b-card mt-4 p-5">
            <h3 className="text-[13px] font-semibold">和高中组卷的区别</h3>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-ink-faint">
              高中是「题库挑题 → 卷子 → 导出」，可以反复换题、调顺序、存档；
              {meta.name}的题目还没正式入库，所以这里不做卷子编辑，
              直接按筛选结果出诊断卷。等题目录进题库后，这一页会自动变成完整组卷工作区。
            </p>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="flex h-full min-h-0">
      <section className="flex min-w-0 flex-1 flex-col bg-surface">
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
          <button onClick={onBank} className="icon-btn h-7 w-7" title="回题库挑题">
            <ArrowLeft size={15} />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-[20px] font-semibold tracking-tight">当前卷子</h2>
              <span className="tnum rounded-full bg-muted px-2 py-[1px] text-[10.5px] text-ink-soft">
                {paper.length} 题 · {score} 分
              </span>
              {paper.length > 0 && (
                <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-[1px] text-[10px]
                  ${canPrint ? 'bg-has-soft text-has' : 'bg-warn-soft text-warn'}`}>
                  {canPrint ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}
                  {canPrint ? '可以印' : `${missing} 道缺解析`}
                </span>
              )}
            </div>
            <div className="mt-0.5 text-[10.5px] text-ink-faint">
              卷面按 单选 → 多选 → 填空 → 解答 分节；每题右侧 ▲▼ 在节内调顺序
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={onBank} className="b-btn b-btn-secondary h-8">
              <Plus size={13} />继续挑题
            </button>
            <button onClick={onExport} disabled={!paper.length}
              className="b-btn b-btn-primary h-8">
              <FileDown size={13} />导出
            </button>
          </div>
        </div>
        <PaperPanel paper={paper} onOpen={(q) => onOpenQuestion(q.key)}
          onRemove={onRemove} onMove={onMove} onSwap={onSwap} onBack={onBank} />
      </section>

      <aside className="b-scroll hidden w-[318px] shrink-0 space-y-3 overflow-y-auto border-l
                        border-border bg-surface-2/50 p-3.5 lg:block">
        <div className="b-card p-4">
          <div className="flex items-center gap-2">
            <Wand2 size={15} className="text-brand" />
            <h3 className="text-[12.5px] font-semibold">智能组卷</h3>
          </div>
          <p className="mt-1 text-[10.5px] leading-relaxed text-ink-faint">
            {small
              ? '小初正式题量还少，建议直接在题库里挑；诊断卷请回题库页导出。'
              : '按高考卷面或纯测试自动挑题；挑完仍然回到这里，可以逐题换、调顺序，再导出。'}
          </p>
          {!small && (
            <button onClick={onGenerate} className="b-btn b-btn-primary mt-3 w-full">
              <Sparkles size={13} />打开组卷方案
            </button>
          )}
        </div>

        <div className="b-card p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-[12.5px] font-semibold">导出前检查</h3>
            <span className={`text-[10px] font-medium ${canPrint ? 'text-has' : 'text-warn'}`}>
              {paper.length ? (canPrint ? '通过' : '有缺口') : '还没选题'}
            </span>
          </div>
          <div className="mt-2.5 space-y-2 text-[11px]">
            <Row label="题量" value={`${paper.length} 题`} ok={paper.length > 0} />
            <Row label="有解析" value={`${answered}/${paper.length}`} ok={missing === 0} />
            <Row label="题型分节" value={paper.length ? `${new Set(paper.map((x) => x.type)).size} 类` : '—'} ok={paper.length > 0} />
          </div>
          {missing > 0 && (
            <div className="mt-3 flex items-start gap-1.5 rounded-lg border border-warn-line
                            bg-warn-soft px-2.5 py-2 text-[10.5px] leading-relaxed text-warn">
              <AlertTriangle size={12} className="mt-0.5 shrink-0" />
              有 {missing} 道题缺解析：仍然可以导出，但卷面上这些题只有题干。
            </div>
          )}
          <button onClick={onExport} disabled={!paper.length}
            className="b-btn b-btn-secondary mt-3 w-full">
            <FileDown size={13} />进入导出设置
          </button>
        </div>

        <div className="b-card p-4">
          <div className="flex items-center gap-2">
            <FolderOpen size={14} className="text-ink-faint" />
            <h3 className="text-[12.5px] font-semibold">试卷库</h3>
            <button onClick={onPapers} className="ml-auto text-[10.5px] font-medium text-brand-ink hover:underline">
              全部
            </button>
          </div>
          <p className="mt-1 text-[10.5px] leading-relaxed text-ink-faint">
            出过的卷子和合集都存档在这里，只记题号，随时能原样还原。
          </p>
          <button onClick={onPapers} className="b-btn b-btn-secondary mt-2.5 w-full">
            <FileStack size={13} />打开试卷库
          </button>
        </div>
      </aside>
    </div>
  )
}

function Row({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-faint">{label}</span>
      <span className={`tnum font-medium ${ok ? 'text-ink-soft' : 'text-warn'}`}>{value}</span>
    </div>
  )
}
