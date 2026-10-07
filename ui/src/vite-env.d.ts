/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_CUSTOMER_KEY?: string;
  readonly VITE_DEMO_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
