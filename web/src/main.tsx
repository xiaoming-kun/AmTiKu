import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './handout.css'   // 讲义样式（与 Slidev 侧一致）
import App from './App'
import { initTheme } from './lib/theme'

// 首屏那段内联脚本已经画过一遍了；这里再画一次是兜底（见 lib/theme.ts），幂等。
// 放在 render 之前，避免首帧用错主题。
initTheme()

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
