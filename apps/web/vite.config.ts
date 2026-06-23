import path from "node:path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const apiProxyTarget =
    env.VITE_API_PROXY_TARGET?.replace(/\/$/, "") ?? "http://localhost:8080"

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": apiProxyTarget,
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
  }
})
