import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'
import { readFileSync } from 'node:fs'

// 版本号在**构建期**注入。这样产物里带的是确切版本，运行时不必再发请求去问后端，
// 也不会出现"界面显示 v1.0.0、后端其实是旧包"的对不上。
// 唯一来源是仓库根的 `VERSION`，与 `amti/version.py` 保持一致（发布脚本会校验）。
const APP_VERSION = readFileSync(resolve(import.meta.dirname, '../VERSION'), 'utf8').trim()

export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify(APP_VERSION) },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': resolve(import.meta.dirname, 'src') } },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // 把不常变的库拆成独立 chunk：改业务代码时它们仍可命中浏览器缓存，
        // 首屏也不必一次下载整个 770 KB。
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (/node_modules\/(react|react-dom|scheduler)\//.test(id)) {
            return 'react-vendor'
          }
          if (id.includes('node_modules/katex/')) return 'katex'
          if (/node_modules\/(lucide-react|dompurify|clsx|tailwind-merge|class-variance-authority)\//.test(id)) {
            return 'ui-vendor'
          }
        },
      },
    },
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8899' } },
})
