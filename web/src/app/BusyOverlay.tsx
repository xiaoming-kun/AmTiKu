/** 居中的阻塞遮罩：保存/刷新期间**挡住所有操作**。
 *
 *  用户的原话是「动画出现在中间位置，刷新期间我做不了其他事情」——
 *  所以它不是一个角落里的进度条，而是：
 *    · 屏幕正中一张小卡片 + 转圈 + 不定长进度条；
 *    · 全屏 scrim 挡住鼠标；
 *    · 键盘事件在 window 捕获阶段截住，`W` / `⌘K` / 空格都别想切页面；
 *    · 不可点掉——保存/刷新结束后自己消失。
 *
 *  用 portal 挂到 body：详情抽屉带 transform 动画，`fixed` 留在里面会以
 *  抽屉为参照，遮罩就只盖住半个屏幕了。
 */
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Loader2 } from 'lucide-react'

export default function BusyOverlay({ title, note }: {
  title: string
  note?: string
}) {
  useEffect(() => {
    // 只 stopPropagation，不 preventDefault：
    // 应用自己的快捷键（window 上的监听）全被挡住，
    // 但浏览器级的刷新/关标签仍然可用——真卡住了还有逃生通道。
    const stop = (e: KeyboardEvent) => { e.stopPropagation() }
    window.addEventListener('keydown', stop, true)
    window.addEventListener('keyup', stop, true)
    return () => {
      window.removeEventListener('keydown', stop, true)
      window.removeEventListener('keyup', stop, true)
    }
  }, [])

  return createPortal(
    <div role="alertdialog" aria-modal="true" aria-busy="true" aria-live="assertive"
      className="anim-fade-in fixed inset-0 z-[90] grid place-items-center bg-scrim p-4
                 backdrop-blur-[2px]">
      <div className="pop-c w-[min(360px,92vw)] rounded-2xl border border-border bg-surface
                      p-5 text-center shadow-[var(--shadow-pop)]">
        <Loader2 size={28} className="mx-auto animate-spin text-brand" />
        <div className="mt-3 text-[14px] font-semibold tracking-tight text-ink">{title}</div>
        {note && (
          <div className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">{note}</div>
        )}
        <div className="progress-track mt-4" />
        <div className="mt-2 text-[10.5px] text-ink-faint">请稍候，完成后自动继续</div>
      </div>
    </div>,
    document.body,
  )
}
