/// <reference types="vitest/config" />
import { createReadStream, existsSync, readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

import { writeStoryData } from './scripts/build_story_data.ts'

const WEB_ROOT = import.meta.dirname
const WASM_DIR = resolve(WEB_ROOT, 'node_modules/@mediapipe/tasks-genai/wasm')
const WASM_URL = '/mediapipe-wasm/'
// The non-module SIMD + no-SIMD builds are what FilesetResolver.forGenAiTasks() asks for.
const WASM_FILES = /^genai_wasm(_nosimd)?_internal\.(js|wasm)$/

/** Regenerates src/story/data.json from evals/ (Receipts scene; never hand-typed numbers). */
function storyData(): Plugin {
  return {
    name: 'sqm-story-data',
    buildStart() {
      writeStoryData(WEB_ROOT)
    },
  }
}

/** Self-hosts the MediaPipe GenAI WASM (no third-party CDN; cached by the SW for offline). */
function mediapipeWasm(): Plugin {
  return {
    name: 'sqm-mediapipe-wasm',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const name = req.url?.startsWith(WASM_URL) ? req.url.slice(WASM_URL.length).split('?')[0] : null
        if (!name || !WASM_FILES.test(name) || !existsSync(resolve(WASM_DIR, name))) return next()
        res.setHeader('Content-Type', name.endsWith('.wasm') ? 'application/wasm' : 'text/javascript')
        createReadStream(resolve(WASM_DIR, name)).pipe(res)
      })
    },
    generateBundle() {
      if (!existsSync(WASM_DIR)) return
      for (const name of readdirSync(WASM_DIR).filter((n) => WASM_FILES.test(n))) {
        this.emitFile({ type: 'asset', fileName: `mediapipe-wasm/${name}`, source: readFileSync(resolve(WASM_DIR, name)) })
      }
    },
  }
}

export default defineConfig({
  plugins: [
    storyData(),
    mediapipeWasm(),
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'prompt',
      includeAssets: ['icon.svg', 'fonts/*.woff2'],
      manifest: {
        name: 'Sidequestmaxxing',
        short_name: 'Sidequest',
        description: 'Real places. Meaningful quests. A more interesting you.',
        theme_color: '#1d2c22',
        background_color: '#fbf2e7',
        display: 'standalone',
        start_url: '/home',
        scope: '/',
        icons: [
          { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
          { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/mediapipe-wasm\//],
        // App shell + art + fonts are precached (offline Walk Mode). The ~27 MB verifier WASM
        // is NOT precached; it is cached on first use, only when the player installs the verifier.
        globPatterns: ['**/*.{js,css,html,svg,webp,woff2}'],
        globIgnores: ['mediapipe-wasm/**'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith(WASM_URL),
            handler: 'CacheFirst',
            options: { cacheName: 'sqm-verifier-wasm', expiration: { maxEntries: 4 } },
          },
        ],
      },
    }),
  ],
  server: {
    // Prompts live in the repo-root /prompts (single source for API, web and training).
    fs: { allow: [resolve(WEB_ROOT, '../..')] },
  },
  build: {
    chunkSizeWarningLimit: 600,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    exclude: ['e2e/**', 'node_modules/**'],
    // The Story page renders every scene synchronously; on a loaded machine that one render has
    // come in just over Vitest's 5 s default while 13 jsdom environments compete. The test isn't
    // slow because it waits for anything — raise the ceiling rather than lose the assertions.
    testTimeout: 20_000,
  },
})
