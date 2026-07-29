/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Build-time flag: '1' serves the app from the in-browser demo dataset (MSW). */
  readonly VITE_DEMO?: string
  /** Legacy build-time flag for the hand-rolled mock layer in `api/mock.ts`. */
  readonly VITE_USE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare const __APP_VERSION__: string
