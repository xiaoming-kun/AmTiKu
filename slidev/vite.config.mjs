// AmTiKu · Slidev 讲义工程的 Vite 配置 —— **只为一件事**：关掉 markdown 的智能排印。
//
// ## 为什么要关
//
// Slidev 用 `unplugin-vue-markdown` 把讲义 md 编译成 Vue 组件，那个插件建
// markdown 引擎时写死了 `typographer: true`（见 unplugin-vue-markdown 的
// `createMarkdown`）。开着它，markdown 的 replacements 规则会把 **`(c)` / `(r)` /
// `(tm)`（不分大小写）** 替换成 `©` / `®` / `™`。于是：
//
//     (A) …　　(B) …　　(C) $S_5=8$　　(D) …     →   (A) …　　(B) …　　© $S_5=8$　　(D) …
//
// **四个选项里只有 C 中招**，印出来是「© S5 = 8」——2026-10-05 用户报的正是
// `2025全国II卷 第9题` 这一处（讲义 PDF 的文本层里能直接捞到 `©`）。
// 解析正文同理：全库**数学模式之外**有 55 处 `(c)`/`(r)`/`(C)`，都会被换成
// `©`/`®`（数学模式里的 `$L(c)$`、`$f(c)$` 不受影响，那 480 处是安全的）。
//
// 这条规则是给英文散文用的（"…"--"…"、`(c)`→©、直引号变弯引号），
// 数学习题里只会帮倒忙：`(C)` 是选项标号、`(r)` 是半径，不是版权和商标。
//
// ## 怎么起作用的
//
// Slidev 从 **deck 根目录** 找 `vite.config.{mjs,js,mts,ts}`，并把配置里的
// `slidev` 键当作插件选项传下去（`@slidev/cli` 的 `resolveViteConfigs` →
// `ViteSlidevPlugin(options, baseConfig.slidev)`）；插件选项里的
// `markdown.markdownOptions` 会**覆盖** unplugin-vue-markdown 的默认值。
//
// ⚠️ 用 `.mjs` 而不是 `.ts` 是有意的：`测试/知识清单测试.py` 的 markdown 探针要
// **import 这一份配置**再建引擎（见那边的 `_MDPROBE`）。测试和真导出读同一份
// 配置，才不会出现「测试绿、PDF 里还是 ©」这种各说各话。
export default {
  slidev: {
    markdown: {
      markdownOptions: {
        typographer: false,
      },
    },
  },
}
