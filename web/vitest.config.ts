import { defineConfig } from 'vitest/config'
import { resolve } from 'node:path'

// 单测只覆盖 `src/lib/` 的纯逻辑：题库/组卷/导出这些「算错了不会报错、只会算错」的
// 地方，才值得用测试锁住边界。全部在 node 里跑，不需要 jsdom。
//
// 这份配置**不参与** `npm run build`：vite 构建只从 `index.html` 出发，
// 测试文件没人 import，天然不会进产物。
export default defineConfig({
  resolve: { alias: { '@': resolve(import.meta.dirname, 'src') } },
  test: {
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.ts'],
  },
})
