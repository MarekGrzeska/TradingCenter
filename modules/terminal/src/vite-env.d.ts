/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_GATEWAY_HTTP: string;
  readonly VITE_GATEWAY_WS: string;
  readonly VITE_DEFAULT_SOURCE: "gateway" | "mock";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
