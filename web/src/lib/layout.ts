/** 布局预算里要共用的尺寸。
 *
 *  `FILTER_W` 原来定义在 `app/FilterPanel.tsx` 里：面板懒加载之后，App 不能再
 *  为了一个数字把整块面板（219 行 + 考点树）同步拉进首屏，所以搬到 lib。
 */

/** 知识点栏宽。**导出**：布局预算要算「还剩多少给列表」（见 App 的 drawerMax）。 */
export const FILTER_W = 252
