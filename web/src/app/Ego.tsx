/** 知识链路 · 局部链路图（点选一个考点后的「上下游一目了然」）
 *
 *  为什么星空之外还要这个：星空负责全局与氛围，但把 315 条边画在一屏里
 *  谁也读不出「我这个考点该先补什么」。真正回答这个问题的是**局部图**
 *  —— 一跳之内，左＝先修、右＝学完能学，没有毛线球问题。
 *  这也是和 math-tree 的差别：它的详情面板只把关系列成文字，我们画出来。
 */
type Rel = { pre?: string; post?: string; strength: 'hard' | 'soft'; reason: string }

const ROW = 24, PILL_W = 64, PILL_H = 17, LX = 8, CX = 92, RX = 240

export function Ego({ id, pre, post, onJump }: {
  id: string; pre: Rel[]; post: Rel[]; onJump: (pid: string) => void
}) {
  const n = Math.max(pre.length, post.length, 1)
  const H = n * ROW + 16
  const rowY = (i: number) => 8 + i * ROW
  const midY = 8 + ((n - 1) / 2) * ROW

  const Pill = ({ x, y, text, hard, center, onClick }: {
    x: number; y: number; text: string; hard?: boolean; center?: boolean; onClick?: () => void
  }) => (
    <g transform={`translate(${x},${y})`} onClick={onClick}
      className={onClick ? 'cursor-pointer' : undefined}>
      <rect width={center ? 120 : PILL_W} height={PILL_H} rx={5}
        fill={center ? '#fdf2f8' : hard ? 'rgba(219,39,119,.10)' : 'rgba(100,116,139,.10)'}
        stroke={center ? '#db2777' : hard ? '#f9a8d4' : '#cbd5e1'}
        strokeWidth={center ? 1.5 : 1} />
      <text x={(center ? 120 : PILL_W) / 2} y={12} textAnchor="middle" fontSize={center ? 11 : 10.5}
        fontWeight={center ? 600 : 400} className="tnum"
        fill={center ? '#9d174d' : hard ? '#be185d' : '#64748b'}>{text}</text>
    </g>
  )

  const wire = (x1: number, y1: number, x2: number, y2: number, hard: boolean, k: string) => {
    const dx = Math.max(14, (x2 - x1) * 0.5)
    return <path key={k} d={`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`}
      fill="none" stroke={hard ? '#f472b6' : '#cbd5e1'} strokeWidth={hard ? 1.4 : 1}
      strokeDasharray={hard ? undefined : '3 2.5'} />
  }

  return (
    <div className="mb-3">
      <div className="mb-1 flex items-baseline gap-1.5">
        <span className="text-[11px] font-semibold text-ink-soft">局部链路</span>
        <span className="text-[10.5px] text-ink-faint">左＝先修 · 右＝学完能学 · 点可跳</span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface-2 px-1.5 py-1.5">
        <svg width="312" height={H} className="block">
          {pre.map((e, i) => wire(LX + PILL_W, rowY(i) + PILL_H / 2, CX, midY + PILL_H / 2,
            e.strength === 'hard', 'p' + i))}
          {post.map((e, i) => wire(CX + 120, midY + PILL_H / 2, RX, rowY(i) + PILL_H / 2,
            e.strength === 'hard', 'q' + i))}
          {pre.map((e, i) => (
            <Pill key={'pl' + i} x={LX} y={rowY(i)} text={e.pre || ''} hard={e.strength === 'hard'}
              onClick={() => onJump(e.pre || '')} />
          ))}
          {post.map((e, i) => (
            <Pill key={'ql' + i} x={RX} y={rowY(i)} text={e.post || ''} hard={e.strength === 'hard'}
              onClick={() => onJump(e.post || '')} />
          ))}
          <Pill x={CX} y={midY} text={id} center />
        </svg>
      </div>
      {!pre.length && !post.length && (
        <div className="mt-1 text-[10.5px] text-ink-faint">这个考点没有前置也没有后续</div>
      )}
    </div>
  )
}
