import path from "node:path"
import vue from "@vitejs/plugin-vue"
import frappeui from "frappe-ui/vite"
import { defineConfig } from "vite"

// Build: ../hozur/public/frontend (served at /assets/hozur/frontend/), and index.html is copied to
// ../hozur/www/hozur.html so Frappe serves the app at /hozur with the boot data rendered in.
export default defineConfig({
  plugins: [
    frappeui({
      frontendRoute: "/hozur",
      // explicit, so the build does not depend on the checkout living in frappe-bench/apps/hozur
      buildConfig: {
        outDir: path.resolve(__dirname, "../hozur/public/frontend"),
        indexHtmlPath: path.resolve(__dirname, "../hozur/www/hozur.html"),
        baseUrl: "/assets/hozur/frontend/",
      },
    }),
    vue(),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 8080, host: true, allowedHosts: true },
  build: { chunkSizeWarningLimit: 1200 },
})
