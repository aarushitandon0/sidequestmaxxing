/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_GEMMA_MODEL_URL?: string
  /** E2E builds only: swap in a fake on-device verifier (headless has no WebGPU). */
  readonly VITE_E2E_FAKE_VERIFIER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
