import path from "node:path"
import vue from "@vitejs/plugin-vue"
import { defineConfig } from "vite"

// Build: dist/, served by the Chronicle server at / (the JSON API lives under /api).
// Dev: `yarn dev` proxies /api to the server on port 8000 (`chronicle serve`).
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 8080,
    host: true,
    allowedHosts: true,
    proxy: { "/api": { target: process.env.CHRONICLE_API ?? "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
})
