/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ARCHIVE_HTTP: string;
  readonly VITE_ARCHIVE_WS: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
