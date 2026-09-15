import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './handout.css'   // 讲义样式（与 Slidev 侧一致）
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
)
