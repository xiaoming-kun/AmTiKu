/** 把网页版讲义的 HTML 拆成顶层块（h2/p/div/table…）。
 *
 *  为什么要拆：题目要能插在"两段之间"。整块 HTML 塞进 innerHTML 之后就没法
 *  在中间塞 React 组件了；拆成块之后，逐块渲染，块与块之间就能挂题。
 *  块的锚点用下标（data-bid），讲义重建后顺序变了就退回到末尾，不会丢题。
 */
export type LecBlock = { html: string; text: string; texStart?: number; texEnd?: number }

export function splitBlocks(html: string): LecBlock[] {
  if (typeof DOMParser === 'undefined') return [{ html, text: '' }]
  const doc = new DOMParser().parseFromString(`<div id="__lec">${html}</div>`, 'text/html')
  const root = doc.getElementById('__lec')
  if (!root) return [{ html, text: '' }]
  // 传进来的是整段 `<div class="lecture">…</div>`：拆它的**子元素**，不是它自己
  const scope = root.querySelector('.lecture') || root
  return [...scope.children].map((el) => ({
    // DOM child 可能是 Element；dataset 只存在于 HTMLElement
    html: el.outerHTML,
    text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40),
    // 新版网页版把每个源码块包成 .lec-src，并带全文件 TeX 偏移；
    // 旧缓存没有这两个属性，前端回退到整节定位。
    texStart: (el as HTMLElement).dataset.texStart != null ? Number((el as HTMLElement).dataset.texStart) : undefined,
    texEnd: (el as HTMLElement).dataset.texEnd != null ? Number((el as HTMLElement).dataset.texEnd) : undefined,
  }))
}
