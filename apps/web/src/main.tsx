import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'

import { App } from './App'
import { initSentry } from './lib/sentry'
import './index.css'

// Errors from the very first render onwards (no-op without VITE_SENTRY_DSN).
initSentry()

// Offline shell + update prompt: when a new version is waiting, <UpdatePrompt> offers a reload.
const updateSW = registerSW({
  onNeedRefresh() {
    window.dispatchEvent(new CustomEvent('sqm:update-ready', { detail: () => void updateSW(true) }))
  },
})

const root = document.getElementById('root')
if (!root) throw new Error('#root missing')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
