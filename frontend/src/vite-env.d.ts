/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OHMATIC_API_BASE_URL?: string;
  readonly VITE_OHMATIC_API_KEY?: string;
  readonly VITE_OHMATIC_USE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
